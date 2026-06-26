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

import json
from .utils import get_client, clean_json, log_llm_usage
from .answer_guardrail import check_answer


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
            {
                "role": "system",
                "content": (
                    "당신은 IT 직무 전문 면접 코치입니다.\n"
                    "지원자의 JD, 이력서, 자기소개서를 분석해 각 질문에 대한 STAR 모범 답안을 생성합니다.\n"
                    "이 답안은 지원자가 실제 면접에서 참고할 '뼈대 스크립트'입니다 — 구체적이고 자연스러워야 합니다.\n\n"
                    "━━━ STAR 항목별 작성 기준 ━━━\n"
                    "- summary  : 두괄식 오프닝. '결론(핵심 역량/성과)'을 먼저 제시 (40~60자)\n"
                    "  나쁜 예: '실험과 수치로 팀원들을 설득했습니다.' (너무 짧고 모호)\n"
                    "  좋은 예: '쿼리 실행 계획 분석과 인덱스 재설계로 팀 내 의견 충돌을 해소하고 API 응답속도를 개선한 경험이 있습니다.'\n\n"
                    "- situation: 프로젝트명·시기·팀 규모·배경을 구체적으로 (2~3문장)\n"
                    "  나쁜 예: '팀 프로젝트 중 갈등이 발생했습니다.'\n"
                    "  좋은 예: '[프로젝트명] 개발 당시 API 응답이 2초를 초과하는 병목이 발생했고, 팀 내에서 캐싱 추가 vs 쿼리 최적화 방향 의견이 갈렸습니다.'\n\n"
                    "- task     : 본인이 맡은 역할과 해결 과제 (1~2문장)\n\n"
                    "- action   : ★ 가장 중요. 단계별 구체적 행동 (4~6문장)\n"
                    "  ① 문제 분석 방법 (도구·방법론 명시)\n"
                    "  ② 해당 방법 선택 이유 (트레이드오프 인식)\n"
                    "  ③ 구체적으로 무엇을 변경/구현했는지\n"
                    "  ④ 팀/이해관계자와의 소통 (있으면)\n\n"
                    "- result   : 성과 서술 (2~3문장)\n"
                    "  ★ 이력서·자소서에 실제 수치가 있으면 반드시 인용\n"
                    "  ★ 수치가 없으면 '[성과 수치 입력]' 플레이스홀더 대신 정성적 성과로 서술\n\n"
                    "━━━ 질문 유형별 작성 방향 ━━━\n"
                    "- [personality] action에 본인의 가치관·원칙이 드러나도록 내면 서술 포함\n"
                    "- [experience]  프로젝트명·기술명 직접 인용, 본인 기여분 명확히\n\n"
                    "━━━ 공통 규칙 ━━━\n"
                    "- 이력서·자소서에 없는 내용 창작 금지\n"
                    "- 구어체 자연스러운 말투\n"
                    "- basis_source: 'project:프로젝트명', 'coverletter', 'resume', 'jd' (복수는 '|'로 구분)\n"
                    "- 반드시 아래 JSON 배열 형식으로만 응답. 마크다운 블록 금지.\n\n"
                    "[\n"
                    "  {\n"
                    '    "question_index": 1,\n'
                    '    "summary":      "두괄식 오프닝 (40~60자)",\n'
                    '    "situation":    "구체적 상황 (프로젝트명·배경 포함)",\n'
                    '    "task":         "본인 역할과 과제",\n'
                    '    "action":       "단계별 구체적 행동 (도구·판단근거 포함)",\n'
                    '    "result":       "정량 또는 정성 성과 + 배운 점",\n'
                    '    "basis_source": "project:중고거래앱|resume"\n'
                    "  }\n"
                    "]"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"[지원 직무] {job_role}\n"
                    f"[지원 회사] {company_name or '미입력'}\n\n"
                    f"[채용공고 JD]\n{jd_text or '미입력'}\n\n"
                    f"[이력서]\n{resume_text or '미입력'}\n\n"
                    f"[자기소개서]\n{cover_letter_text or '미입력'}\n\n"
                    f"[면접 질문 목록]\n{question_list_str}\n\n"
                    "위 질문 각각에 대해 STAR 모범 답안을 생성해주세요.\n"
                    "이력서·자소서의 실제 프로젝트명·수치·기술 스택을 최대한 인용하고,\n"
                    "없는 내용은 만들지 말고 해당 필드를 짧게 유지해주세요."
                ),
            },
        ],
    )
    log_llm_usage(response)

    answer_list = json.loads(clean_json(response.choices[0].message.content))
    answer_map_local = {item["question_index"]: item for item in answer_list}

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
            {
                "role": "system",
                "content": (
                    "당신은 IT 직무 전문 면접 코치입니다.\n"
                    "기술 면접 질문에 대해 지원자가 실제 면접에서 말할 수 있는 모범 답안을 생성합니다.\n"
                    "기술 질문은 STAR 구조가 아니라 아래 3단 구조로 작성합니다.\n\n"
                    "━━━ 기술 답변 3단 구조 ━━━\n"
                    "- summary    : 핵심 결론 한 줄 요약 (40~60자). 개념+경험을 압축해서 선언\n"
                    "  나쁜 예: 'JavaScript와 Node.js의 차이를 설명하겠습니다.' (단순 예고)\n"
                    "  좋은 예: '저는 [프로젝트명]에서 인덱스 전략을 직접 설계하며 쿼리 최적화의 트레이드오프를 실제로 검증한 경험이 있습니다.'\n\n"
                    "- concept    : 해당 기술/개념에 대한 본인의 이해 설명 (3~4문장)\n"
                    "  단순 정의 나열 금지. 왜 중요한지, 어떤 원리인지, 어떤 상황에서 쓰는지 중심으로\n"
                    "  나쁜 예: 'JavaScript는 클라이언트 사이드 언어이고 Node.js는 런타임입니다.'\n"
                    "  좋은 예: 'B-Tree 인덱스는 정렬된 트리 구조 덕분에 범위 조회에 강하지만, 쓰기 시 리밸런싱 비용이 발생합니다. 조회가 잦은 컬럼에는 효과적이지만, 카디널리티가 낮은 컬럼(예: boolean)에 인덱스를 걸면 오히려 풀 스캔보다 느려질 수 있습니다.'\n\n"
                    "- experience : 해당 기술을 실제 프로젝트에서 적용한 경험 (3~5문장)\n"
                    "  프로젝트명·상황·본인이 한 판단과 행동·결과를 구체적으로\n"
                    "  이력서·자소서에 없는 내용 창작 금지. 없으면 '직접 적용 경험은 없지만...'으로 솔직하게\n\n"
                    "- tradeoff   : 이 기술의 한계·대안·선택 기준 (2~3문장)\n"
                    "  면접관이 가장 보고 싶어하는 '엔지니어적 사고'를 보여주는 파트\n"
                    "  '단점도 알고 있다', '언제 다른 선택을 할지 안다'를 보여줄 것\n\n"
                    "━━━ 공통 규칙 ━━━\n"
                    "- 이력서·자소서에 없는 프로젝트명·수치 창작 금지\n"
                    "- 구어체 자연스러운 말투\n"
                    "- basis_source: 'project:프로젝트명', 'resume', 'jd' 등 (복수는 '|'로 구분)\n"
                    "- 반드시 아래 JSON 배열 형식으로만 응답. 마크다운 블록 금지.\n\n"
                    "[\n"
                    "  {\n"
                    '    "question_index": 1,\n'
                    '    "summary":    "핵심 결론 한 줄 (40~60자)",\n'
                    '    "concept":    "개념/원리 설명 (왜 중요한지·어떻게 동작하는지)",\n'
                    '    "experience": "실제 적용 경험 (프로젝트명·판단·결과 포함)",\n'
                    '    "tradeoff":   "한계·대안·선택 기준",\n'
                    '    "basis_source": "project:중고거래앱|jd"\n'
                    "  }\n"
                    "]"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"[지원 직무] {job_role}\n"
                    f"[지원 회사] {company_name or '미입력'}\n\n"
                    f"[채용공고 JD]\n{jd_text or '미입력'}\n\n"
                    f"[이력서]\n{resume_text or '미입력'}\n\n"
                    f"[자기소개서]\n{cover_letter_text or '미입력'}\n\n"
                    f"[기술 면접 질문 목록]\n{question_list_str}\n\n"
                    "각 질문에 대해 summary·concept·experience·tradeoff 구조로 답변을 생성해주세요.\n"
                    "이력서·자소서의 실제 프로젝트명·기술 스택을 최대한 인용하세요."
                ),
            },
        ],
    )
    log_llm_usage(response)

    answer_list = json.loads(clean_json(response.choices[0].message.content))
    answer_map_local = {item["question_index"]: item for item in answer_list}

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
