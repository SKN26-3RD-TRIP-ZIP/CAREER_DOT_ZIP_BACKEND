"""
analysis/services 통합 테스트 스크립트
실제 OpenAI API를 호출합니다. OPENAI_API_KEY 환경변수가 필요합니다.

실행 방법:
    cd CAREER_DOT_ZIP_BACKEND
    python manage.py shell < apps/analysis/test_analysis_services.py

또는 Django shell에서:
    python manage.py shell
    exec(open('apps/analysis/test_analysis_services.py').read())

[DB 적재 테스트 포함]
- 테스트용 User / JobDescription / ResumeMaster / CoverLetter를 임시 생성
- _run_analysis() 를 직접 호출해 AnalysisSession → JdAnalysis → GeneratedQuestion 적재 확인
- 테스트 종료 후 생성된 데이터를 모두 삭제 (rollback)
"""

import json
import time

# ── 목 데이터 ──────────────────────────────────────────────────────────────

JD_TEXT = """
[회사] 커리어닷집 (스타트업, 50인 이하)
[직무] 백엔드 개발자 (Python/Django)

[담당 업무]
- Django REST Framework 기반 API 설계 및 개발
- PostgreSQL 스키마 설계 및 쿼리 최적화
- AWS EC2 / S3 / RDS 인프라 운영
- CI/CD 파이프라인 구축 및 유지보수 (GitHub Actions)
- Redis 캐싱 레이어 설계

[자격 요건]
- Python 개발 경력 1년 이상 또는 관련 프로젝트 경험
- Django / DRF REST API 개발 경험
- RDB 설계 및 ORM 활용 능력
- Git 기반 협업 경험

[우대 사항]
- AWS 배포 경험 (EC2, S3, RDS)
- Docker / Docker Compose 경험
- Redis 또는 Celery 활용 경험
- 스타트업 환경 적응력
"""

RESUME_TEXT = """
이름: 김백엔드
이메일: backend@example.com
GitHub: github.com/kimbackend

[기술 스택]
Python, Django, DRF, PostgreSQL, Redis, Docker, AWS(EC2/S3/RDS), GitHub Actions, Git

[프로젝트 경험]

1. 커머스 플랫폼 백엔드 (2023.03 ~ 2023.08, 팀 3인)
   - 역할: 백엔드 리드, REST API 20개 설계 및 구현
   - 기술: Django, DRF, PostgreSQL, Redis, Docker
   - 성과: API 응답 속도 40% 개선 (쿼리 최적화), MAU 5,000 달성

2. 실시간 채팅 서비스 (2023.09 ~ 2023.12, 팀 2인)
   - 역할: 백엔드 전담 개발
   - 기술: Django Channels, Redis, PostgreSQL, AWS EC2
   - 성과: 동시 접속 500명 처리, 메시지 전달 지연 100ms 이하

[경력]
- (없음, 신입)

[학력]
- 한국대학교 컴퓨터공학과 졸업 (2019.03 ~ 2023.02)
"""

COVER_LETTER_TEXT = """
[지원 동기]
백엔드 개발에 관심을 갖게 된 것은 대학교 2학년 때 직접 만든 토이 프로젝트가 실제 사용자 200명을 돌파했을 때입니다.
그 경험으로 Python과 Django를 깊이 파고들었고, 이후 커머스 플랫폼과 채팅 서비스를 팀 프로젝트로 완성했습니다.
커리어닷집이 추구하는 '데이터 기반 채용 매칭'은 제가 직접 느낀 취업 준비의 어려움을 해소해주는 서비스라 생각해 지원했습니다.

[성격 및 역량]
저는 성능 수치에 집착하는 편입니다. 커머스 프로젝트에서 쿼리 실행 계획을 분석해 N+1 문제를 해결하고
응답 속도를 40% 개선한 경험이 대표적입니다. 팀원들에게 결과를 공유하며 코드 리뷰 문화를 만든 것도 보람 있었습니다.

[입사 후 포부]
첫 1개월은 코드베이스와 인프라를 완전히 파악하고, 3개월 내에 신규 API 기능을 독립적으로 기여하는 것이 목표입니다.
"""


# ── 헬퍼 ───────────────────────────────────────────────────────────────────

def _sep(title):
    print(f"\n{'=' * 60}")
    print(title)
    print('=' * 60)


# ── PART 1: 서비스 함수 단독 호출 테스트 ──────────────────────────────────

def run_service_test():
    from apps.analysis.services import (
        extract_jd_keywords,
        analyze_resume,
        generate_all_questions,
    )
    from apps.analysis.services.match_service import calculate_match_score

    _sep("STEP 1: JD 키워드 추출")
    jd_keywords = extract_jd_keywords(JD_TEXT)
    print(json.dumps(jd_keywords, ensure_ascii=False, indent=2))

    _sep("STEP 2: 이력서·자소서 분석")
    resume_analysis = analyze_resume(RESUME_TEXT, COVER_LETTER_TEXT)
    print(json.dumps(resume_analysis, ensure_ascii=False, indent=2))

    _sep("STEP 3: 매칭 점수 계산")
    match_result = calculate_match_score(
        jd_keywords=jd_keywords,
        resume_analysis=resume_analysis,
        cover_letter_text=COVER_LETTER_TEXT,
    )
    print(json.dumps(match_result, ensure_ascii=False, indent=2))

    _sep("STEP 4: 면접 질문 + STAR 답안 생성")
    questions = generate_all_questions(
        job_role="백엔드 개발자",
        company_name="커리어닷집",
        jd_keywords=jd_keywords,
        resume_analysis=resume_analysis,
        jd_text=JD_TEXT,
        resume_text=RESUME_TEXT,
        cover_letter_text=COVER_LETTER_TEXT,
    )
    for i, q in enumerate(questions, 1):
        print(f"\n[{i}] ({q['type']}) {q['text']}")
        answer = q.get("answer", {})
        print(f"  ▶ summary  : {answer.get('summary', '')}")
        print(f"  ▶ situation: {answer.get('situation', '')[:60]}...")
        print(f"  ▶ action   : {answer.get('action', '')[:60]}...")
        print(f"  ▶ result   : {answer.get('result', '')[:60]}...")

    print("\n✅ 서비스 함수 테스트 완료")
    return jd_keywords, resume_analysis, match_result, questions


# ── PART 2: DB 적재 전체 파이프라인 테스트 ────────────────────────────────

def run_db_test():
    from django.contrib.auth import get_user_model
    from apps.input.models import JobDescription, ResumeMaster, CoverLetter
    from apps.analysis.models import AnalysisSession, JdAnalysis, GeneratedQuestion
    from apps.analysis.views import _run_analysis

    User = get_user_model()

    _sep("DB 테스트: 임시 데이터 생성")

    # 테스트용 유저 생성 (이미 있으면 재사용)
    user, user_created = User.objects.get_or_create(
        username="test_analysis_user",
        defaults={"email": "test_analysis@example.com"},
    )
    if user_created:
        user.set_password("testpass1234!")
        user.save()
        print(f"  ✔ 유저 생성: {user.username} (id={user.id})")
    else:
        print(f"  ✔ 유저 재사용: {user.username} (id={user.id})")

    # 테스트용 JobDescription 생성
    jd = JobDescription.objects.create(
        user=user,
        company_name="커리어닷집",
        position="백엔드 개발자",
        original_text=JD_TEXT,
        analysis_status="COMPLETED",
    )
    print(f"  ✔ JobDescription 생성: id={jd.id}")

    # 테스트용 ResumeMaster 생성
    resume = ResumeMaster.objects.create(
        user=user,
        name="김백엔드",
        email="backend@example.com",
        original_text=RESUME_TEXT,
    )
    print(f"  ✔ ResumeMaster 생성: id={resume.id}")

    # 테스트용 CoverLetter 생성
    cover_letter = CoverLetter.objects.create(
        user=user,
        jd=jd,
        title="커리어닷집 백엔드 개발자 자기소개서",
        company_name="커리어닷집",
    )
    print(f"  ✔ CoverLetter 생성: id={cover_letter.id}")

    # AnalysisSession 생성
    session = AnalysisSession.objects.create(
        user=user,
        jd=jd,
        resume=resume,
        cover_letter=cover_letter,
        job_role="백엔드 개발자",
        company_name="커리어닷집",
        jd_text=JD_TEXT,
        resume_text=RESUME_TEXT,
        cover_letter_text=COVER_LETTER_TEXT,
        status="analyzing",
    )
    print(f"  ✔ AnalysisSession 생성: id={session.id}, status={session.status}")

    # 파이프라인 실행 (동기, 스레드 없이 직접 호출)
    _sep("DB 테스트: 분석 파이프라인 실행 중...")
    print("  (OpenAI API 호출 포함 — 약 1~2분 소요)")
    _run_analysis(session.id)

    # 결과 확인
    _sep("DB 테스트: 적재 결과 확인")

    session.refresh_from_db()
    print(f"  AnalysisSession.status : {session.status}")
    assert session.status == "ready", f"❌ 세션 상태가 'ready'여야 하는데 '{session.status}'입니다."
    print(f"  AnalysisSession.jd_analysis_id : {session.jd_analysis_id}")

    jd_analysis = JdAnalysis.objects.get(id=session.jd_analysis_id)
    print(f"\n  JdAnalysis (id={jd_analysis.id})")
    print(f"    match_score : {jd_analysis.match_score}")
    print(f"    jd_keywords : {jd_analysis.jd_keywords[:3]}...")
    print(f"    strengths   : {jd_analysis.strengths[:2]}...")
    print(f"    weaknesses  : {jd_analysis.weaknesses[:2]}...")
    print(f"    cl_points   : {jd_analysis.cl_points[:1]}...")

    questions = list(jd_analysis.questions.all())
    print(f"\n  GeneratedQuestion 수 : {len(questions)} (기대: 10)")
    assert len(questions) == 10, f"❌ 질문이 10개여야 하는데 {len(questions)}개입니다."
    for q in questions:
        print(f"    [{q.order}] ({q.question_type}) {q.question_text[:40]}")

    print("\n  ✅ DB 적재 확인 완료")

    # 테스트 데이터 정리
    _sep("DB 테스트: 임시 데이터 삭제")
    jd_analysis.delete()
    session.delete()
    cover_letter.delete()
    resume.delete()
    jd.delete()
    if user_created:
        user.delete()
        print("  ✔ 테스트 유저 삭제")
    print("  ✔ JdAnalysis / GeneratedQuestion 삭제")
    print("  ✔ AnalysisSession 삭제")
    print("  ✔ CoverLetter / ResumeMaster / JobDescription 삭제")
    print("\n  ✅ 정리 완료 — DB에 잔여 데이터 없음")


# ── 진입점 ─────────────────────────────────────────────────────────────────

print("\n[1] 서비스 함수 단독 테스트를 실행하려면 : run_service_test()")
print("[2] DB 적재 전체 파이프라인 테스트      : run_db_test()")
print("\n둘 다 실행하려면 : run_service_test(); run_db_test()\n")
