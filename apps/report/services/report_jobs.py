"""비동기 리포트 생성 작업 레이어.

목적: 무거운 generate_final_report(LLM 다수 호출 + 세션 평가 백필)를
요청/DB락 밖의 백그라운드 스레드에서 실행하고, FinalReport.status로
진행 상태를 노출한다. 프론트는 status가 done/failed가 될 때까지 폴링한다.

설계 메모:
  - 브로커(Celery/Redis) 미도입 환경을 위한 스레드 기반 구현.
    인터페이스(ensure_report_generation)만 유지하면 추후 Celery task로
    무중단 교체할 수 있다.
  - 클레임(상태 선점)은 select_for_update 락 안에서 '짧게'만 수행하고,
    LLM 호출은 락 밖 스레드에서 돌린다 → 락/커넥션 장기 점유 제거.
  - 스레드는 daemon=True. 워커가 처리 중 죽으면 행은 'processing'으로 남고,
    is_stale_processing(타임아웃 초과)으로 다음 요청에서 재시작된다.
"""

import logging
import threading

from django.conf import settings
from django.db import IntegrityError, close_old_connections, transaction
from django.utils import timezone

from apps.interview.models import InterviewSession
from ..models import FinalReport
from .report_generator import generate_final_report

logger = logging.getLogger("feedback_ai.report_jobs")

REPORT_FAILED_CODE = "AI_REPORT_GENERATION_FAILED"


def _claim_processing(report):
    """기존 FinalReport 행을 processing으로 선점한다.

    summary는 보존한다(#3): force 재생성 중에도 직전 done 결과를 유지해,
    완료 시점에 _run_generation 이 새 summary로 원자적으로 덮어쓰게 한다.
    update_fields에 updated_at을 포함해 auto_now가 발화하도록 한다.
    """
    report.status = FinalReport.STATUS_PROCESSING
    report.error_code = None
    report.save(update_fields=["status", "error_code", "updated_at"])


def summary_indicates_failure(summary) -> bool:
    """평가가 0건이면(answer는 있는데 evaluated=0) 생성 실패로 간주한다."""
    metadata = (summary or {}).get("evaluation_metadata", {})
    answer_count = int(metadata.get("answer_count") or 0)
    evaluated_count = int(metadata.get("evaluated_answer_count") or 0)
    return answer_count > 0 and evaluated_count == 0


def _run_generation(session_id, report_id):
    """리포트 생성 핵심 로직.

    주의: 여기서는 DB 커넥션 관리(close_old_connections)를 하지 않는다.
    EAGER(인라인) 모드에서는 요청/테스트와 '같은' 커넥션·트랜잭션을 공유하므로,
    여기서 커넥션을 닫으면 호출자의 트랜잭션이 깨진다(TransactionManagementError).
    커넥션 정리는 실제 스레드 경로(_run_generation_threaded)에서만 수행한다.
    """
    try:
        session = InterviewSession.objects.get(pk=session_id)
        summary = generate_final_report(session)
        failed = summary_indicates_failure(summary)
        # QuerySet.update()는 auto_now를 트리거하지 않으므로 updated_at을 명시 갱신한다(#1).
        FinalReport.objects.filter(pk=report_id).update(
            summary=summary,
            status=FinalReport.STATUS_FAILED if failed else FinalReport.STATUS_DONE,
            error_code=REPORT_FAILED_CODE if failed else None,
            updated_at=timezone.now(),
        )
        # 재생성으로 약점 태그가 바뀌었을 수 있으므로 추천 캐시를 무효화한다(#5).
        from .recommendation_service import invalidate_weakness_reco_cache
        invalidate_weakness_reco_cache(session_id)
        logger.info(
            "리포트 생성 완료 (session=%s, report=%s, failed=%s)",
            session_id, report_id, failed,
        )
    except Exception:
        logger.exception(
            "리포트 생성 실패 (session=%s, report=%s)", session_id, report_id
        )
        FinalReport.objects.filter(pk=report_id).update(
            status=FinalReport.STATUS_FAILED,
            error_code=REPORT_FAILED_CODE,
            updated_at=timezone.now(),
        )


def _run_generation_threaded(session_id, report_id):
    """백그라운드 스레드 진입점.

    새 스레드는 자체 DB 커넥션을 갖게 되므로, 작업이 끝나면 close_old_connections()로
    스레드 로컬 커넥션을 정리해 누수를 막는다. (EAGER 인라인 경로에서는 호출하지 않는다.)
    """
    try:
        _run_generation(session_id, report_id)
    finally:
        close_old_connections()


def ensure_report_generation(session, force=False):
    """리포트 생성을 보장한다(필요 시 백그라운드 시작).

    상태 전이:
      - done & not force                -> 그대로 반환 (started=False)
      - processing & not stale          -> 진행 중 그대로 반환 (started=False)
      - 없음 / failed / stale / force    -> processing으로 선점 후 스레드 시작 (started=True)

    Returns:
        (report: FinalReport, started: bool)
    """
    # 1) 상태 선점: 락은 여기서만 '짧게' 잡는다(LLM 호출 없음).
    with transaction.atomic():
        InterviewSession.objects.select_for_update().get(pk=session.pk)
        report = FinalReport.objects.filter(session=session).first()

        if report is not None and not force:
            if report.status == FinalReport.STATUS_DONE:
                return report, False
            if report.status == FinalReport.STATUS_PROCESSING and not report.is_stale_processing:
                return report, False

        if report is None:
            try:
                report = FinalReport.objects.create(
                    session=session, summary={}, status=FinalReport.STATUS_PROCESSING
                )
            except IntegrityError:
                # SQLite(dev)에서는 select_for_update가 no-op이라, 동시 요청이 같은 세션에
                # 동시에 create를 시도하면 OneToOne UNIQUE 제약으로 한쪽이 IntegrityError가 난다(#2).
                # 진 쪽은 방금 선점된 행을 다시 읽어 이어받는다(중복 생성·예외 전파 방지).
                report = FinalReport.objects.get(session=session)
                if (
                    not force
                    and report.status == FinalReport.STATUS_PROCESSING
                    and not report.is_stale_processing
                ):
                    # 상대 요청이 이미 생성을 시작함 → 그대로 폴링 대상으로 반환.
                    return report, False
                _claim_processing(report)
        else:
            _claim_processing(report)

        report_id = report.id
        session_id = session.id

    # 2) EAGER 모드: 테스트/동기 환경에서는 스레드 없이 인라인 실행
    #    (Celery의 task_always_eager 와 동일한 결정성 보장).
    if getattr(settings, "REPORT_GENERATION_EAGER", False):
        _run_generation(session_id, report_id)
        return FinalReport.objects.get(pk=report_id), True

    # 3) 락 밖에서 백그라운드 생성 시작.
    thread = threading.Thread(
        target=_run_generation_threaded,
        args=(session_id, report_id),
        name=f"report-gen-{session_id}",
        daemon=True,
    )
    thread.start()
    return report, True
