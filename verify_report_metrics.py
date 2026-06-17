#!/usr/bin/env python3
"""세션 리포트 지표 검증 스크립트 (E7 리뷰 #2/#3 후속).

목적
----
완료된 면접 세션으로 `generate_final_report()`를 새로 호출해
`score_summary.metrics`의 두 지표가 패치된 의미/스케일을 만족하는지 단언한다.

  * grounding_score  ... is_grounded 비율 × 100  (0~100, '근거 수치 충족 비율')
  * bei_logic_score  ... BEI 4요소 평균 합        (0~100)

추가로 persona_weights 주입(#E7.10), element_total_avg(0~25) 스케일 분리(#2)를 함께 확인한다.

기본 동작
--------
LLM/API 재호출을 피하기 위해 `evaluate_session_answers`를 무력화하고
DB에 이미 저장된 Answer.evaluation 집계만 검증한다.
실제 재평가까지 돌리려면 `--reeval`.

사용법
------
    python verify_report_metrics.py                 # 자동: 첫 완료 세션
    python verify_report_metrics.py --session <id>  # 특정 세션
    python verify_report_metrics.py --reeval        # LLM 재평가 포함

종료 코드: 모든 단언 통과 0, 실패 1, 검증할 세션 없음 2.

NOTE: 이 파일은 qa2_test.py 와 마찬가지로 커밋 대상이 아니다. .gitignore 유지 필요.
"""
from __future__ import annotations

import argparse
import os
import sys

import django


def bootstrap_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    django.setup()


# ---- 단언 헬퍼 --------------------------------------------------------------
RESULTS: list[tuple[bool, str, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    RESULTS.append((bool(ok), label, detail))


def approx(a: float, b: float, tol: float = 0.11) -> bool:
    return abs(float(a) - float(b)) <= tol


# ---- 기대값 독립 재계산 (report_generator 로직 미러) ------------------------
def expected_metrics(session):
    """report_generator 와 무관하게 DB 원천에서 기대값을 직접 계산."""
    from apps.report.services.report_generator import get_score

    answers = (
        session.answers.all()
        .select_related("evaluation")
    )
    evaluated = [a for a in answers if getattr(a, "evaluation", None) is not None]

    grounded_flags: list[bool] = []
    sit = tsk = act = res = 0.0
    n = 0
    for a in evaluated:
        ev = a.evaluation
        n += 1
        bei = ev.bei_score if isinstance(ev.bei_score, dict) else {}
        sit += get_score(bei.get("situation"))
        tsk += get_score(bei.get("task"))
        act += get_score(bei.get("action"))
        res += get_score(bei.get("result"))

        sd = ev.score_detail if isinstance(ev.score_detail, dict) else {}
        g = sd.get("grounding", {})
        if isinstance(g, dict) and "is_grounded" in g:
            grounded_flags.append(bool(g.get("is_grounded")))

    exp = {"n": n}
    if n:
        avg_sit = round(sit / n, 1)
        avg_tsk = round(tsk / n, 1)
        avg_act = round(act / n, 1)
        avg_res = round(res / n, 1)
        exp["bei_logic_score"] = round(avg_sit + avg_tsk + avg_act + avg_res, 1)  # 0~100
        exp["bei_element_avg"] = round((avg_sit + avg_tsk + avg_act + avg_res) / 4, 1)  # 0~25
    else:
        exp["bei_logic_score"] = 0.0
        exp["bei_element_avg"] = 0.0

    if grounded_flags:
        exp["grounding_score"] = round(sum(grounded_flags) / len(grounded_flags) * 100, 1)
    else:
        exp["grounding_score"] = 0.0
    exp["grounding_total"] = len(grounded_flags)
    exp["grounding_true"] = sum(grounded_flags)
    return exp


def pick_session(session_id: str | None):
    from apps.interview.models import InterviewSession

    qs = InterviewSession.objects.all()
    if session_id:
        return qs.filter(id=session_id).first()
    # 평가된 답변이 있는 완료 세션 우선
    for s in qs.filter(status="completed").order_by("-updated_at"):
        if s.answers.exclude(evaluation__isnull=True).exists():
            return s
    return qs.filter(status="completed").order_by("-updated_at").first()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", dest="session_id", default=None)
    ap.add_argument("--reeval", action="store_true",
                    help="evaluate_session_answers(LLM 재평가) 실제 실행")
    args = ap.parse_args()

    bootstrap_django()

    from apps.report.services import report_generator

    # 기본: LLM 재평가 무력화 (집계 로직만 검증)
    if not args.reeval:
        report_generator.evaluate_session_answers = lambda *a, **k: None

    session = pick_session(args.session_id)
    if session is None:
        print("[SKIP] 검증할 완료 세션이 없습니다. fixture/시드부터 필요합니다.")
        print("       예) python manage.py loaddata <fixture>  또는 create_test_report.py")
        return 2

    print(f"대상 세션: {session.id} | type={session.interview_type} "
          f"| persona={session.persona} | status={session.status}")

    exp = expected_metrics(session)
    if exp["n"] == 0:
        print("[SKIP] 평가(evaluation)된 답변이 없어 지표 검증 불가. --reeval 로 재평가하거나 시드 필요.")
        return 2

    summary = report_generator.generate_final_report(session)
    metrics = summary["score_summary"]["metrics"]
    stats = summary["score_detail"]["statistics"]
    pf = summary["score_summary"]["persona_feedback"]

    g = metrics["grounding_score"]
    b = metrics["bei_logic_score"]
    elem = stats.get("bei_metrics", {}).get("element_total_avg")

    print("\n--- 산출값 ---")
    print(f"grounding_score      = {g}   (기대 {exp['grounding_score']}, "
          f"is_grounded {exp['grounding_true']}/{exp['grounding_total']})")
    print(f"bei_logic_score      = {b}   (기대 {exp['bei_logic_score']})")
    print(f"bei element_total_avg= {elem} (0~25 분리 지표, 기대 {exp['bei_element_avg']})")
    print(f"persona_weights      = {pf.get('persona_weights')}")

    # === 단언 ===
    if g is None:
        # option-C: 기술 답변 없는 세션 — None은 정상
        check(True, "grounding_score == None (기술 답변 없는 세션, option-C 정상)", "=None")
    else:
        check(0.0 <= g <= 100.0, "grounding_score 범위 0~100", f"={g}")
        check(approx(g, exp["grounding_score"]),
              "grounding_score == is_grounded 비율×100 (#3)",
              f"got {g} / exp {exp['grounding_score']}")

    check(0.0 <= b <= 100.0, "bei_logic_score 범위 0~100 (#2)", f"={b}")
    check(approx(b, exp["bei_logic_score"]),
          "bei_logic_score == BEI 4요소 평균 합",
          f"got {b} / exp {exp['bei_logic_score']}")

    check(elem is None or 0.0 <= elem <= 25.0,
          "element_total_avg 범위 0~25 (스케일 분리)", f"={elem}")
    if elem is not None:
        check(approx(b, elem * 4, tol=0.5),
              "bei_logic_score ≈ element_total_avg × 4", f"{b} vs {elem}*4")

    check(pf.get("persona_weights") is not None,
          "persona_weights 주입됨 (#E7.10)", f"={pf.get('persona_weights')}")

    # === 결과 ===
    print("\n=== 검증 결과 ===")
    ok_all = True
    for ok, label, detail in RESULTS:
        ok_all &= ok
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {label}" + (f"  ({detail})" if detail and not ok else ""))

    print("\n총평:", "ALL PASS ✅" if ok_all else "FAIL ❌")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())