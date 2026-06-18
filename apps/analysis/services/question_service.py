"""
Pipeline 3 - 예상 질문 & STAR 답변 생성 / 오케스트레이터

역할:
  Pipeline 3의 ②~⑥ 단계를 순서대로 조율한다.
  views.py는 이 파일의 generate_all_questions()만 호출하면 된다.

현재 구현 상태:
  - ② RAG:    question_rag_service  (Pinecone 미연동, MySQL 폴백 사용 중)
  - ③ 생성:   question_gen_service  (구현 완료)
  - ④ 통합:   question_merge_service (구현 완료 — 임베딩 유사도 기반 중복 제거)
  - ⑤ STAR:   star_service          (구현 완료)
  - ⑥ 출력:   question_output_service (구현 완료)

포함 함수:
  generate_all_questions()   ②~⑥ 순서 조율 → 최종 질문 + STAR 목록 반환
"""

from concurrent.futures import ThreadPoolExecutor

from .question_rag_service    import search_similar_questions
from .question_gen_service    import generate_questions, generate_github_questions_for_projects
from .star_service            import generate_star_answers
from .question_merge_service  import merge_and_deduplicate
from .question_output_service import build_question_output


def generate_all_questions(
    job_role: str,
    company_name: str,
    jd_keywords: list[str] | dict,
    resume_analysis: dict,
    jd_text: str = "",
    resume_text: str = "",
    cover_letter_text: str = "",
    projects: list[dict] | None = None,
) -> list[dict]:
    """
    Pipeline 3 ②~⑥를 순서대로 실행해 최종 질문 + STAR 답변 목록을 반환한다.

    jd_keywords 하위 호환:
      - dict  {"tech_keywords": [...], "trait_keywords": [...]} → 신규 형식
      - list  ["Python", "Django", ...] → 구형 형식 (tech_keywords로 래핑)

    projects:
      merge_with_github()를 거친 ProjectProfile 리스트 (선택).
      GitHub 검증된 repo가 있으면 코드 기반 질문(③')을 추가로 생성한다.
      None이거나 검증된 repo가 없으면 GitHub 가지는 건너뛴다 (하위 호환).

    실행 순서:
      ②  RAG 검색       (question_rag_service — MySQL 폴백)
      ③  LLM 질문 생성   (question_gen_service)
      ③' GitHub 검증 질문 (question_gen_service — repo+이력서+자소서 결합)
      ④  통합/중복 제거   (question_merge_service)
      ⑤  STAR 답변 생성   (star_service)
      ⑥  출력 포맷 변환   (question_output_service)

    반환 형식:
    [
        {
            "type":   "personality" | "technical" | "experience",
            "text":   "질문 내용",
            "source": "jd" | "resume" | "coverletter" | "project" | "question_bank" | "combined",
            "basis":  "근거 원문 스니펫",
            "answer": {
                "summary":      "두괄식 오프닝",
                "situation":    "상황 설명",
                "task":         "역할·과제",
                "action":       "구체적 행동",
                "result":       "결과 및 배운 점",
                "basis_source": "project:중고거래앱" | "coverletter" | "resume" | "jd"
            }
        },
        ...
    ]
    """
    # jd_keywords 하위 호환 처리
    if isinstance(jd_keywords, list):
        jd_keywords_dict = {"tech_keywords": jd_keywords, "trait_keywords": []}
    else:
        jd_keywords_dict = jd_keywords

    projects = projects or []

    # ②③③' RAG 검색 + LLM 질문 생성 + GitHub 검증 질문 — 병렬 실행
    with ThreadPoolExecutor(max_workers=3) as executor:
        f_rag = executor.submit(search_similar_questions, jd_keywords_dict, 20)
        f_llm = executor.submit(
            generate_questions,
            job_role=job_role,
            company_name=company_name,
            jd_keywords=jd_keywords_dict,
            resume_analysis=resume_analysis,
        )
        # projects가 GitHub 검증(merge_with_github)을 거친 경우에만 코드 기반 질문 생성.
        # 검증된 repo가 없으면 generate_github_questions_for_projects가 [] 반환.
        f_github = executor.submit(
            generate_github_questions_for_projects,
            projects,
            resume_analysis,
            cover_letter_text,
        )
        rag_questions    = f_rag.result()
        llm_questions    = f_llm.result()
        github_questions = f_github.result()

    # ④ RAG + LLM + GitHub 질문 통합 & 중복 제거
    questions = merge_and_deduplicate(
        rag_questions, llm_questions, github_questions=github_questions
    )

    # ⑤ STAR 답변 생성
    questions_with_star = generate_star_answers(
        questions=questions,
        job_role=job_role,
        company_name=company_name,
        jd_text=jd_text,
        resume_text=resume_text,
        cover_letter_text=cover_letter_text,
    )

    # ⑥ 최종 출력 포맷 변환
    return build_question_output(questions_with_star)
