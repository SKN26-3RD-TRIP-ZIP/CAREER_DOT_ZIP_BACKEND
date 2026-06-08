import json
import os

from django.conf import settings
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

# LangSmith 트레이싱 설정
os.environ["LANGCHAIN_TRACING_V2"] = settings.LANGCHAIN_TRACING_V2
os.environ["LANGCHAIN_API_KEY"]    = settings.LANGCHAIN_API_KEY
os.environ["LANGCHAIN_PROJECT"]    = settings.LANGCHAIN_PROJECT


def generate_all_questions(
    job_role: str,
    company_name: str,
    jd_keywords: list[str],
    resume_analysis: dict,
    jd_text: str = "",
    resume_text: str = "",
    cover_letter_text: str = "",
) -> list[dict]:
    """
    질문 10개 생성 → STAR 모범 답안 생성.

    반환 형태:
    [
        {
            "type": "personality" | "technical" | "experience",
            "text": "질문 내용",
            "answer": {
                "summary":   "두괄식 한 문장 오프닝",
                "situation": "...",
                "task":      "...",
                "action":    "...",
                "result":    "..."
            }
        },
        ...총 10개...
    ]
    """
    questions = _generate_questions(job_role, company_name, jd_keywords, resume_analysis)
    questions_with_answers = _generate_star_answers(
        questions, job_role, company_name, jd_text, resume_text, cover_letter_text
    )
    return questions_with_answers


# ─────────────────────────────────────────
# Step 1. 질문 10개 생성 (GPT 1회 호출)
# ─────────────────────────────────────────
def _generate_questions(
    job_role: str,
    company_name: str,
    jd_keywords: list[str],
    resume_analysis: dict,
) -> list[dict]:

    experiences = resume_analysis.get("key_experiences", [])
    projects    = resume_analysis.get("projects", [])

    exp_str  = "\n".join(f"- {e}" for e in experiences)
    proj_str = "\n".join(
        f"- {p['name']}: {p.get('role', '')} / 기술: {', '.join(p.get('tech', []))} / 성과: {p.get('result', '')}"
        for p in projects
    )

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.6)

    messages = [
        SystemMessage(content=(
            "당신은 IT 직무 면접관입니다.\n"
            "지원자의 이력서 분석 결과와 JD 키워드를 바탕으로 맞춤형 면접 질문을 생성합니다.\n\n"
            "질문 유형별 기준:\n\n"
            "[인성 질문 — 3개]\n"
            "- 지원 동기, 협업 경험, 갈등 해결, 성장 과정, 가치관 관련\n"
            "- 지원자의 자소서·경험과 연결된 구체적 질문으로 작성\n"
            "- 예: '팀 내 의견 충돌 상황에서 어떻게 대처했나요?' (일반적 질문 지양)\n\n"
            "[기술 질문 — 4개]\n"
            "- JD 핵심 키워드에서 최소 2개 이상 반드시 포함\n"
            "- 개념 설명형 1개, 실제 적용·트레이드오프 판단형 2개, 문제 상황 대응형 1개\n"
            "- 예: 'Django ORM과 직접 SQL 쿼리 중 어떤 상황에서 어떤 걸 선택하나요?'\n\n"
            "[경험 기반 질문 — 3개]\n"
            "- 이력서의 key_experiences, projects에서 직접 인용해 질문 생성\n"
            "- STAR 답변을 유도할 수 있는 '~했던 경험에 대해 말씀해주세요' 형태\n"
            "- 지원자가 명시한 성과·기술을 검증하는 방향으로 작성\n\n"
            "공통 규칙:\n"
            "- 모든 질문은 한 문장으로 명확하게 (두 가지를 한꺼번에 묻는 질문 금지)\n"
            "- '~에 대해 설명해주세요'만 반복하지 말고 다양한 질문 형태 사용\n"
            "- 반드시 아래 JSON 형식으로만 응답. 마크다운 블록 금지.\n\n"
            "{\n"
            '  "personality": ["질문1", "질문2", "질문3"],\n'
            '  "technical":   ["질문1", "질문2", "질문3", "질문4"],\n'
            '  "experience":  ["질문1", "질문2", "질문3"]\n'
            "}"
        )),
        HumanMessage(content=(
            f"[지원 직무] {job_role}\n"
            f"[지원 회사] {company_name or '미입력'}\n"
            f"[JD 핵심 키워드] {', '.join(jd_keywords)}\n\n"
            f"[지원자 핵심 경험]\n{exp_str}\n\n"
            f"[지원자 프로젝트]\n{proj_str}\n\n"
            "위 정보를 최대한 반영해 인성 3개, 기술 4개, 경험 기반 3개 질문을 생성해주세요.\n"
            "특히 기술 질문은 JD 키워드와 직접 연결되도록, 경험 질문은 프로젝트 내용을 인용해주세요."
        )),
    ]

    response = llm.invoke(messages)
    data = json.loads(_clean_json(response.content))

    questions = []
    for q in data["personality"]:
        questions.append({"type": "personality", "text": q})
    for q in data["technical"]:
        questions.append({"type": "technical", "text": q})
    for q in data["experience"]:
        questions.append({"type": "experience", "text": q})

    return questions


# ─────────────────────────────────────────
# Step 2. STAR 모범 답안 생성 (GPT 1회 호출)
# ─────────────────────────────────────────
def _generate_star_answers(
    questions: list[dict],
    job_role: str,
    company_name: str,
    jd_text: str,
    resume_text: str,
    cover_letter_text: str,
) -> list[dict]:

    question_list_str = "\n".join(
        f"{i+1}. [{q['type']}] {q['text']}"
        for i, q in enumerate(questions)
    )

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.5)

    messages = [
        SystemMessage(content=(
            "당신은 IT 직무 취업 전문 면접 코치입니다.\n"
            "지원자의 JD, 이력서, 자기소개서를 바탕으로 각 면접 질문에 대한 STAR 기법 모범 답안을 생성합니다.\n\n"
            "STAR 기법 작성 기준:\n"
            "- summary  : 두괄식 오프닝. 핵심 결론을 한 문장으로 먼저 제시 (30자 내외)\n"
            "- situation: 언제, 어디서, 어떤 배경인지. 면접관이 맥락을 이해할 수 있도록 (2~3문장)\n"
            "- task     : 지원자 본인이 책임진 역할과 해결해야 할 과제. '우리 팀' 표현 지양, 본인 주도성 강조 (1~2문장)\n"
            "- action   : 실제로 취한 구체적 행동. 왜 그 방법을 선택했는지 이유 포함 (3~4문장)\n"
            "- result   : 정량 수치 우선, 없으면 정성 성과. 배운 점·성장한 부분 1문장 추가 (2~3문장)\n\n"
            "질문 유형별 추가 기준:\n"
            "- personality(인성): 지원자의 가치관·태도가 드러나도록. 지나치게 모범 답안 느낌 지양\n"
            "- technical(기술)  : situation·task는 간략히, action에서 기술 개념 설명·선택 근거·트레이드오프 포함\n"
            "- experience(경험) : 이력서·자소서의 실제 프로젝트명·수치·역할을 반드시 인용\n\n"
            "공통 규칙:\n"
            "- 이력서·자소서에 없는 내용 창작 금지. 없는 수치·경험 추가 금지\n"
            "- 구어체 자연스러운 말투 사용 (문어체·보고서체 금지)\n"
            "- 반드시 아래 JSON 배열 형식으로만 응답. 마크다운 블록 금지.\n\n"
            "[\n"
            "  {\n"
            '    "question_index": 1,\n'
            '    "summary":   "두괄식 오프닝",\n'
            '    "situation": "상황 설명",\n'
            '    "task":      "역할·과제",\n'
            '    "action":    "구체적 행동 및 선택 근거",\n'
            '    "result":    "결과 및 배운 점"\n'
            "  }\n"
            "]"
        )),
        HumanMessage(content=(
            f"[지원 직무] {job_role}\n"
            f"[지원 회사] {company_name or '미입력'}\n\n"
            f"[채용공고 JD]\n{jd_text or '미입력'}\n\n"
            f"[이력서]\n{resume_text or '미입력'}\n\n"
            f"[자기소개서]\n{cover_letter_text or '미입력'}\n\n"
            f"[면접 질문 목록]\n{question_list_str}\n\n"
            "위 질문 10개 각각에 대해 STAR 모범 답안을 생성해주세요.\n"
            "이력서·자소서에 실제로 적힌 프로젝트명, 수치, 기술 스택을 최대한 인용하고,\n"
            "없는 내용은 만들지 말고 해당 필드를 짧게 유지해주세요."
        )),
    ]

    response = llm.invoke(messages)
    answer_list = json.loads(_clean_json(response.content))

    answer_map = {item["question_index"]: item for item in answer_list}

    result = []
    for i, q in enumerate(questions):
        answer_data = answer_map.get(i + 1, {})
        result.append({
            "type": q["type"],
            "text": q["text"],
            "answer": {
                "summary":   answer_data.get("summary", ""),
                "situation": answer_data.get("situation", ""),
                "task":      answer_data.get("task", ""),
                "action":    answer_data.get("action", ""),
                "result":    answer_data.get("result", ""),
            }
        })

    return result


# ─────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────
def _clean_json(text: str) -> str:
    return text.strip().replace("```json", "").replace("```", "").strip()
