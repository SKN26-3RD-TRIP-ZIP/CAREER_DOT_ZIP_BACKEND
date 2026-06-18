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


def generate_star_answers(
    questions: list[dict],
    job_role: str,
    company_name: str,
    jd_text: str,
    resume_text: str,
    cover_letter_text: str,
) -> list[dict]:
    """
    질문 목록 각각에 대해 STAR 구조 모범 답변을 생성한다.
    GPT를 한 번만 호출해 전체 질문의 답변을 한꺼번에 생성한다.

    반환 형식:
    [
        {
            "type":   "technical",
            "text":   "질문 내용",
            "source": "jd",
            "basis":  "근거 원문",
            "answer": {
                "summary":      "두괄식 오프닝 한 문장",
                "situation":    "상황 설명",
                "task":         "역할·과제",
                "action":       "구체적 행동 및 선택 근거",
                "result":       "결과 및 배운 점",
                "basis_source": "project:중고거래앱" | "coverletter" | "resume" 등
            }
        },
        ...
    ]

    STAR 항목별 basis_source 태그:
      - 특정 프로젝트 기반  → "project:{프로젝트명}"
      - 자소서 내용 기반    → "coverletter"
      - 이력서 경험 기반    → "resume"
      - JD 기반 일반 답변  → "jd"
    """
    client = get_client()

    question_list_str = "\n".join(
        f"{i+1}. [{q['type']}] {q['text']}"
        for i, q in enumerate(questions)
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.5,
        messages=[
            {
                "role": "system",
                "content": (
                    "당신은 IT 직무 취업 전문 면접 코치입니다.\n"
                    "지원자의 JD, 이력서, 자기소개서를 바탕으로 각 면접 질문에 대한 STAR 기법 모범 답안을 생성합니다.\n\n"
                    "STAR 기법 작성 기준:\n"
                    "- summary     : 두괄식 오프닝. 핵심 결론을 한 문장으로 먼저 제시 (30자 내외)\n"
                    "- situation   : 언제, 어디서, 어떤 배경인지 (2~3문장)\n"
                    "- task        : 지원자 본인이 책임진 역할과 과제. 본인 주도성 강조 (1~2문장)\n"
                    "- action      : 실제로 취한 구체적 행동과 선택 이유 (3~4문장)\n"
                    "- result      : 정량 수치 우선, 없으면 정성 성과 + 배운 점 (2~3문장)\n"
                    "- basis_source: 이 답변의 근거 출처. 복수 출처는 '|'로 구분 (공백 없음)\n"
                    "  단일 예: 'project:중고거래앱', 'coverletter', 'resume', 'jd'\n"
                    "  복수 예: 'resume|coverletter', 'project:중고거래앱|jd'\n\n"
                    "공통 규칙:\n"
                    "- 이력서·자소서에 없는 내용 창작 금지\n"
                    "- 구어체 자연스러운 말투 사용\n"
                    "- 반드시 아래 JSON 배열 형식으로만 응답. 마크다운 블록 금지.\n\n"
                    "[\n"
                    "  {\n"
                    '    "question_index": 1,\n'
                    '    "summary":      "두괄식 오프닝",\n'
                    '    "situation":    "상황 설명",\n'
                    '    "task":         "역할·과제",\n'
                    '    "action":       "구체적 행동 및 선택 근거",\n'
                    '    "result":       "결과 및 배운 점",\n'
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
    answer_map  = {item["question_index"]: item for item in answer_list}

    result = []
    for i, q in enumerate(questions):
        ans = answer_map.get(i + 1, {})
        basis_raw = ans.get("basis_source", "")
        # LLM이 "resume, coverletter" 처럼 복수 값을 반환할 경우 "|" 구분자로 정규화
        basis_source = "|".join(v.strip() for v in basis_raw.split(",")) if "," in basis_raw else basis_raw
        result.append({
            **q,
            "answer": {
                "summary":      ans.get("summary", ""),
                "situation":    ans.get("situation", ""),
                "task":         ans.get("task", ""),
                "action":       ans.get("action", ""),
                "result":       ans.get("result", ""),
                "basis_source": basis_source,
            },
        })

    return result
