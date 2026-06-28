"""
분석 파이프라인 성능 벤치마크

실행:
    python benchmark_analysis.py

각 단계별 소요 시간을 측정하고 최종 요약을 출력한다.
"""

import os
import sys
import time
import django
from concurrent.futures import ThreadPoolExecutor

# Windows 콘솔 UTF-8 강제 설정
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

# ── 샘플 데이터 ────────────────────────────────────────────────────────────────

JD_TEXT = """
[백엔드 개발자 채용]

[자격 요건]
- Python, Django 기반 백엔드 개발 경험 2년 이상
- PostgreSQL, Redis 사용 경험
- RESTful API 설계 및 구현 경험
- Docker 기반 개발 환경 경험

[우대 사항]
- Kubernetes 운영 경험
- AWS 클라우드 서비스 활용 경험
- 대용량 트래픽 처리 경험

[인재상]
- 주도적으로 문제를 해결하는 분
- 데이터 기반으로 의사결정하는 분
- 팀과 적극적으로 소통하는 분
"""

RESUME_TEXT = """
[경력]
- (주)테크스타트 / 백엔드 개발자 / 2022.03 ~ 현재 (1년 6개월)
  - Django + PostgreSQL 기반 커머스 플랫폼 API 20개 설계 및 운영
  - Redis 캐싱 도입으로 API 응답 속도 40% 개선
  - Docker Compose 기반 개발/스테이징 환경 구성

[기술 스택]
Python, Django, PostgreSQL, Redis, Docker, Git, AWS EC2

[프로젝트]
- 배달 플랫폼 (2021.09 ~ 2022.02)
  - 역할: 백엔드 리드 (3인 팀)
  - 기술: Python, Django, MySQL
  - 성과: DAU 3천 달성, 주문 처리 API 안정화

[학력]
- 한국대학교 컴퓨터공학과 졸업 (2022.02)
"""

COVER_LETTER_TEXT = """
[지원 동기]
저는 데이터를 기반으로 의사결정하는 문화를 중요하게 생각합니다.
이전 직장에서 Redis 캐싱 성능을 수치로 증명하며 팀을 설득한 경험이 있습니다.

[강점]
팀원과의 코드리뷰를 통해 코드 품질을 높이는 협업을 즐깁니다.
주도적으로 기술 개선안을 제안하고, 데이터로 근거를 만들어 설득하는 방식으로 일합니다.
"""

JD_KEYWORDS = {
    "tech_keywords": ["Python", "Django", "PostgreSQL", "Redis", "Docker", "Kubernetes", "AWS"],
    "trait_keywords": ["주도적으로 문제를 해결하는 분", "데이터 기반으로 의사결정하는 분", "팀과 적극적으로 소통하는 분"],
}

JD_REQUIREMENTS = {
    "min_years": 2,
    "education": "대졸",
    "job_type": "백엔드",
    "required_tech": ["Python", "Django", "PostgreSQL", "Redis", "Docker"],
    "preferred_tech": ["Kubernetes", "AWS"],
}

RESUME_ANALYSIS = {
    "tech_stack": ["Python", "Django", "PostgreSQL", "Redis", "Docker", "Git", "AWS"],
    "key_experiences": [
        "Django + PostgreSQL 기반 커머스 플랫폼 API 20개 설계 및 운영",
        "Redis 캐싱 도입으로 API 응답 속도 40% 개선",
    ],
    "strengths": ["성능 최적화 경험 (Redis 캐싱, 쿼리 튜닝)", "백엔드 API 설계 및 운영 경험"],
    "trait_evidence": [
        "데이터를 근거로 팀 의사결정을 이끈 경험 (Redis 성능 수치로 팀 설득)",
        "팀원과 코드리뷰를 통해 코드 품질을 지속적으로 개선한 경험",
    ],
    "projects": [
        {
            "name": "배달플랫폼",
            "role": "백엔드 리드",
            "tech": ["Python", "Django", "MySQL"],
            "result": "DAU 3천 달성",
            "domain": "logistics",
        }
    ],
    "years_of_experience": 1.5,
    "education": "대졸",
    "career_level": "experienced",
}

# ── 벤치마크 헬퍼 ──────────────────────────────────────────────────────────────

class Timer:
    def __init__(self, label: str):
        self.label = label
        self.elapsed = 0.0

    def __enter__(self):
        self._start = time.time()
        return self

    def __exit__(self, *_):
        self.elapsed = time.time() - self._start
        print(f"  ✓ {self.label:<45} {self.elapsed:>6.2f}s")


def section(title: str):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


# ── 현재 파이프라인 측정 (순차 구조) ─────────────────────────────────────────

def run_current_pipeline():
    from apps.analysis.services.jd_service import extract_jd_keywords, extract_jd_requirements
    from apps.analysis.services.resume_service import analyze_resume
    from apps.analysis.services.match_service import calculate_match_score
    from apps.analysis.services.result_service import build_match_result
    from apps.analysis.services.gap_service import calculate_gap, build_gap_message
    from apps.analysis.services.question_rag_service import search_similar_questions
    from apps.analysis.services.question_gen_service import generate_questions
    from apps.analysis.services.question_merge_service import merge_and_deduplicate
    from apps.analysis.services.star_service import generate_star_answers

    timings = {}
    t_total = time.time()

    section("BEFORE: 현재 파이프라인")

    # Step 1: 병렬 (jd_kw + jd_req + resume)
    with Timer("Step1 [병렬] jd_kw + jd_req + resume") as t:
        with ThreadPoolExecutor(max_workers=3) as ex:
            f_jd_kw  = ex.submit(extract_jd_keywords, JD_TEXT)
            f_jd_req = ex.submit(extract_jd_requirements, JD_TEXT)
            f_resume = ex.submit(analyze_resume, RESUME_TEXT, COVER_LETTER_TEXT)
        jd_kw         = f_jd_kw.result()
        jd_req        = f_jd_req.result()
        resume_summary = f_resume.result()
    timings["step1_parallel"] = t.elapsed

    inferred_level = resume_summary.get("career_level", "entry")

    # Step 2: match_score (순차)
    with Timer("Step2 calculate_match_score (임베딩+LLM)") as t:
        match_result = calculate_match_score(
            jd_keywords=jd_kw,
            resume_analysis=resume_summary,
            cover_letter_text=COVER_LETTER_TEXT,
            career_level=inferred_level,
            jd_requirements=jd_req,
            job_role="백엔드 개발자",
        )
        match_result = build_match_result(match_result, inferred_level)
    timings["step2_match"] = t.elapsed

    # Step 3: gap (순차)
    with Timer("Step3 calculate_gap + build_gap_message") as t:
        gap_result  = calculate_gap(
            jd_keywords=jd_kw,
            jd_requirements=jd_req,
            resume_analysis=resume_summary,
            unmatched_keywords=match_result["unmatched_keywords"],
            trait_details=match_result.get("trait_details"),
        )
        gap_message = build_gap_message(gap_result, inferred_level)
    timings["step3_gap"] = t.elapsed

    # Step 4: 질문 생성 (내부 병렬 + STAR 순차)
    with Timer("Step4a [병렬] RAG + question_gen") as t:
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_rag = ex.submit(search_similar_questions, jd_kw, 20)
            f_llm = ex.submit(
                generate_questions,
                job_role="백엔드 개발자",
                company_name="테크스타트",
                jd_keywords=jd_kw,
                resume_analysis=resume_summary,
            )
        rag_questions = f_rag.result()
        llm_questions = f_llm.result()
    timings["step4a_rag_gen"] = t.elapsed

    with Timer("Step4b merge_and_deduplicate (임베딩)") as t:
        questions = merge_and_deduplicate(rag_questions, llm_questions)
    timings["step4b_merge"] = t.elapsed

    with Timer("Step4c generate_star_answers (LLM 1번, 전체 질문)") as t:
        questions_with_star = generate_star_answers(
            questions=questions,
            job_role="백엔드 개발자",
            company_name="테크스타트",
            jd_text=JD_TEXT,
            resume_text=RESUME_TEXT,
            cover_letter_text=COVER_LETTER_TEXT,
        )
    timings["step4c_star"] = t.elapsed

    total = time.time() - t_total
    timings["total"] = total

    print(f"\n  {'총 소요 시간':<45} {total:>6.2f}s")
    return timings, questions


# ── 최적화 파이프라인 측정 ─────────────────────────────────────────────────────

def run_optimized_pipeline():
    from apps.analysis.services.jd_service import extract_jd_keywords, extract_jd_requirements
    from apps.analysis.services.resume_service import analyze_resume
    from apps.analysis.services.match_service import calculate_match_score
    from apps.analysis.services.result_service import build_match_result
    from apps.analysis.services.gap_service import calculate_gap, build_gap_message
    from apps.analysis.services.question_rag_service import search_similar_questions
    from apps.analysis.services.question_gen_service import generate_questions
    from apps.analysis.services.question_merge_service import merge_and_deduplicate
    from apps.analysis.services.star_service import generate_star_answers

    timings = {}
    t_total = time.time()

    section("AFTER: 최적화 파이프라인")

    # Step 1: 병렬 (jd_kw + jd_req + resume) — 동일
    with Timer("Step1 [병렬] jd_kw + jd_req + resume") as t:
        with ThreadPoolExecutor(max_workers=3) as ex:
            f_jd_kw  = ex.submit(extract_jd_keywords, JD_TEXT)
            f_jd_req = ex.submit(extract_jd_requirements, JD_TEXT)
            f_resume = ex.submit(analyze_resume, RESUME_TEXT, COVER_LETTER_TEXT)
        jd_kw         = f_jd_kw.result()
        jd_req        = f_jd_req.result()
        resume_summary = f_resume.result()
    timings["step1_parallel"] = t.elapsed

    inferred_level = resume_summary.get("career_level", "entry")

    # Step 2+4a: match_score ↔ (RAG + question_gen) 병렬
    with Timer("Step2+4a [병렬] match_score ↔ RAG+question_gen") as t:
        with ThreadPoolExecutor(max_workers=4) as ex:
            f_match   = ex.submit(
                calculate_match_score,
                jd_keywords=jd_kw,
                resume_analysis=resume_summary,
                cover_letter_text=COVER_LETTER_TEXT,
                career_level=inferred_level,
                jd_requirements=jd_req,
                job_role="백엔드 개발자",
            )
            f_rag = ex.submit(search_similar_questions, jd_kw, 20)
            f_llm = ex.submit(
                generate_questions,
                job_role="백엔드 개발자",
                company_name="테크스타트",
                jd_keywords=jd_kw,
                resume_analysis=resume_summary,
            )
        match_result_raw = f_match.result()
        rag_questions    = f_rag.result()
        llm_questions    = f_llm.result()

    match_result = build_match_result(match_result_raw, inferred_level)
    timings["step2_and_4a_parallel"] = t.elapsed

    # Step 3+4b: gap(순수 로직) + merge 병렬
    with Timer("Step3+4b [병렬] gap ↔ merge_deduplicate") as t:
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_gap   = ex.submit(
                calculate_gap,
                jd_keywords=jd_kw,
                jd_requirements=jd_req,
                resume_analysis=resume_summary,
                unmatched_keywords=match_result["unmatched_keywords"],
                trait_details=match_result.get("trait_details"),
            )
            f_merge = ex.submit(merge_and_deduplicate, rag_questions, llm_questions)
        gap_result = f_gap.result()
        questions  = f_merge.result()

    gap_message = build_gap_message(gap_result, inferred_level)
    timings["step3_and_4b_parallel"] = t.elapsed

    # Step 4c: STAR 병렬 (타입별 3그룹)
    with Timer("Step4c [병렬] STAR 3그룹 동시 생성") as t:
        personality_qs = [q for q in questions if q.get("type") == "personality"]
        technical_qs   = [q for q in questions if q.get("type") == "technical"]
        experience_qs  = [q for q in questions if q.get("type") == "experience"]

        star_kwargs = dict(
            job_role="백엔드 개발자",
            company_name="테크스타트",
            jd_text=JD_TEXT,
            resume_text=RESUME_TEXT,
            cover_letter_text=COVER_LETTER_TEXT,
        )

        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = [
                ex.submit(generate_star_answers, questions=g, **star_kwargs)
                for g in [personality_qs, technical_qs, experience_qs]
                if g
            ]
        questions_with_star = []
        for f in futures:
            questions_with_star.extend(f.result())
    timings["step4c_star_parallel"] = t.elapsed

    total = time.time() - t_total
    timings["total"] = total

    print(f"\n  {'총 소요 시간':<45} {total:>6.2f}s")
    return timings, questions_with_star


# ── 비교 요약 ─────────────────────────────────────────────────────────────────

def print_summary(before: dict, after: dict):
    section("비교 요약")

    rows = [
        ("Step1  [병렬] jd_kw+jd_req+resume",       "step1_parallel",          "step1_parallel"),
        ("Step2  match_score",                        "step2_match",             None),
        ("Step3  gap",                                "step3_gap",               None),
        ("Step4a RAG + question_gen",                 "step4a_rag_gen",          None),
        ("Step4b merge (임베딩)",                     "step4b_merge",            None),
        ("Step4c STAR 생성",                          "step4c_star",             None),
        ("Step2+4a [병렬] match ↔ RAG+gen",          None,                      "step2_and_4a_parallel"),
        ("Step3+4b [병렬] gap ↔ merge",              None,                      "step3_and_4b_parallel"),
        ("Step4c  [병렬] STAR 3그룹",                None,                      "step4c_star_parallel"),
    ]

    print(f"\n  {'단계':<42} {'BEFORE':>8}  {'AFTER':>8}  {'절감':>8}")
    print(f"  {'─'*70}")

    for label, bkey, akey in rows:
        bval = before.get(bkey, 0) if bkey else 0
        aval = after.get(akey, 0)  if akey else 0
        if bkey and akey:
            diff = bval - aval
            print(f"  {label:<42} {bval:>7.2f}s  {aval:>7.2f}s  {diff:>+7.2f}s")
        elif bkey:
            print(f"  {label:<42} {bval:>7.2f}s  {'(병합됨)':>8}")
        else:
            print(f"  {label:<42} {'(병합됨)':>8}  {aval:>7.2f}s")

    print(f"  {'─'*70}")
    b_total = before["total"]
    a_total = after["total"]
    saved   = b_total - a_total
    pct     = saved / b_total * 100 if b_total > 0 else 0
    print(f"  {'총 소요 시간':<42} {b_total:>7.2f}s  {a_total:>7.2f}s  {saved:>+7.2f}s  ({pct:.0f}% 절감)")


# ── 진입점 ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  분석 파이프라인 성능 벤치마크")
    print("  (실제 LLM/임베딩 API 호출 포함)")
    print("=" * 60)

    before_timings, _ = run_current_pipeline()
    after_timings,  _ = run_optimized_pipeline()

    print_summary(before_timings, after_timings)

    print("\n  LangSmith 트레이스 확인:")
    print("  → https://smith.langchain.com  (프로젝트: career-dot-zip)")
    print()
