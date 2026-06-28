"""
Pipeline 3 - ⑤ STAR 답변 생성

역할:
  통합된 질문 목록 각각에 대해 LLM이 STAR 구조 모범 답변을 생성한다.
  사용자 실제 경험(이력서·자소서·프로젝트)을 근거로 채우며,
  각 STAR 항목에 출처 태그(basis_source)를 부착한다.

  기존 question_service.py의 _generate_star_answers()를 이 파일로 이관.

포함 함수:
  generate_star_answers()   STAR 모범 답변 생성 + basis_source 태그 부착
"""

from .utils import get_client, log_llm_usage, parse_json_array
from .answer_guardrail import check_answer
from .analysis_prompt import (
    STAR_ANSWER_SYSTEM, build_star_answer_user,
    TECHNICAL_ANSWER_SYSTEM, build_technical_answer_user,
)


def generate_star_answers(
    questions: list[dict],
    job_role: str,
    company_name: str,
    jd_text: str,
    resume_text: str,
    cover_letter_text: str,
) -> list[dict]:
    """
    질문 목록 각각에 대해 모범 답변을 생성한다.
    - technical 질문: 개념·적용·트레이드오프 구조
    - personality / experience 질문: STAR 구조

    GPT를 두 번 호출한다 (technical / non-technical 분리).
    """
    source_text = f"{resume_text or ''}\n{cover_letter_text or ''}\n{jd_text or ''}"

    technical_qs     = [(i, q) for i, q in enumerate(questions) if q.get("type") == "technical"]
    non_technical_qs = [(i, q) for i, q in enumerate(questions) if q.get("type") != "technical"]

    answer_map: dict[int, dict] = {}

    if non_technical_qs:
        answer_map.update(_generate_star(non_technical_qs, job_role, company_name, jd_text, resume_text, cover_letter_text))

    if technical_qs:
        answer_map.update(_generate_technical(technical_qs, job_role, company_name, jd_text, resume_text, cover_letter_text))

    result = []
    for i, q in enumerate(questions):
        answer = answer_map.get(i, {})
        answer["groundedness"] = check_answer(answer, source_text)
        result.append({**q, "answer": answer})

    return result


def _generate_star(
    indexed_questions: list[tuple[int, dict]],
    job_role: str,
    company_name: str,
    jd_text: str,
    resume_text: str,
    cover_letter_text: str,
) -> dict[int, dict]:
    """인성·경험 질문에 대해 STAR 구조 답변을 생성한다."""
    client = get_client()

    question_list_str = "\n".join(
        f"{local_i+1}. [{q['type']}] {q['text']}"
        for local_i, (orig_i, q) in enumerate(indexed_questions)
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.5,
        messages=[
            {"role": "system", "content": STAR_ANSWER_SYSTEM},
            {"role": "user",   "content": build_star_answer_user(
                job_role, company_name, jd_text, resume_text, cover_letter_text, question_list_str,
            )},
        ],
    )
    log_llm_usage(response)

    answer_list = parse_json_array(response.choices[0].message.content)
    answer_map_local = {
        item["question_index"]: item
        for item in answer_list
        if isinstance(item, dict) and "question_index" in item
    }

    # question_index는 이 함수에 넘긴 순서 기준(1-based) → 원래 인덱스로 매핑
    result: dict[int, dict] = {}
    for local_i, (orig_i, _) in enumerate(indexed_questions):
        ans = answer_map_local.get(local_i + 1, {})
        basis_raw = ans.get("basis_source", "")
        basis_source = "|".join(v.strip() for v in basis_raw.split(",")) if "," in basis_raw else basis_raw
        result[orig_i] = {
            "summary":      ans.get("summary", ""),
            "situation":    ans.get("situation", ""),
            "task":         ans.get("task", ""),
            "action":       ans.get("action", ""),
            "result":       ans.get("result", ""),
            "basis_source": basis_source,
        }
    return result


def _generate_technical(
    indexed_questions: list[tuple[int, dict]],
    job_role: str,
    company_name: str,
    jd_text: str,
    resume_text: str,
    cover_letter_text: str,
) -> dict[int, dict]:
    """기술 질문에 대해 개념·적용 경험·트레이드오프 구조 답변을 생성한다."""
    client = get_client()

    question_list_str = "\n".join(
        f"{local_i+1}. {q['text']}"
        for local_i, (_, q) in enumerate(indexed_questions)
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.4,
        messages=[
            {"role": "system", "content": TECHNICAL_ANSWER_SYSTEM},
            {"role": "user",   "content": build_technical_answer_user(
                job_role, company_name, jd_text, resume_text, cover_letter_text, question_list_str,
            )},
        ],
    )
    log_llm_usage(response)

    answer_list = parse_json_array(response.choices[0].message.content)
    answer_map_local = {
        item["question_index"]: item
        for item in answer_list
        if isinstance(item, dict) and "question_index" in item
    }

    result: dict[int, dict] = {}
    for local_i, (orig_i, _) in enumerate(indexed_questions):
        ans = answer_map_local.get(local_i + 1, {})
        basis_raw = ans.get("basis_source", "")
        basis_source = "|".join(v.strip() for v in basis_raw.split(",")) if "," in basis_raw else basis_raw
        result[orig_i] = {
            "summary":      ans.get("summary", ""),
            "concept":      ans.get("concept", ""),
            "experience":   ans.get("experience", ""),
            "tradeoff":     ans.get("tradeoff", ""),
            "basis_source": basis_source,
        }
    return result
