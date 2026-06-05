import json
from openai import OpenAI

client = OpenAI()


def generate_all_questions(
    job_role: str,
    company_name: str,
    jd_keywords: list[str],
    resume_analysis: dict,
) -> list[dict]:
    """인성 3개 + 기술 4개 + 경험 3개, 총 10개 면접 질문 생성."""
    questions = []
    questions += _generate_personality(job_role, company_name)
    questions += _generate_technical(job_role, jd_keywords)
    questions += _generate_experience(resume_analysis)
    return questions


def _generate_personality(job_role: str, company_name: str) -> list[dict]:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.7,
        messages=[
            {
                "role": "system",
                "content": (
                    "IT 직무 인성 면접관입니다.\n"
                    "JSON 배열 형식으로만 응답하세요: [\"질문1\", \"질문2\", ...]"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"직무: {job_role}\n"
                    f"회사: {company_name or '미입력'}\n\n"
                    "이 직무에 적합한 인성 면접 질문 3개를 생성해주세요."
                ),
            },
        ],
    )
    items = json.loads(_clean_json(response.choices[0].message.content))
    return [{"type": "personality", "text": q} for q in items]


def _generate_technical(job_role: str, jd_keywords: list[str]) -> list[dict]:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.5,
        messages=[
            {
                "role": "system",
                "content": (
                    "IT 직무 기술 면접관입니다.\n"
                    "JSON 배열 형식으로만 응답하세요: [\"질문1\", \"질문2\", ...]"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"직무: {job_role}\n"
                    f"핵심 기술 키워드: {', '.join(jd_keywords)}\n\n"
                    "기술 면접 질문 4개를 생성해주세요."
                ),
            },
        ],
    )
    items = json.loads(_clean_json(response.choices[0].message.content))
    return [{"type": "technical", "text": q} for q in items]


def _generate_experience(resume_analysis: dict) -> list[dict]:
    experiences = resume_analysis.get("key_experiences", [])
    projects    = resume_analysis.get("projects", [])

    # 프롬프트 가독성을 위해 문자열로 변환
    exp_str  = "\n".join(f"- {e}" for e in experiences)
    proj_str = "\n".join(
        f"- {p['name']}: {p.get('role', '')} / 성과: {p.get('result', '')}"
        for p in projects
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.6,
        messages=[
            {
                "role": "system",
                "content": (
                    "IT 직무 면접관입니다.\n"
                    "JSON 배열 형식으로만 응답하세요: [\"질문1\", \"질문2\", ...]"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"[핵심 경험]\n{exp_str}\n\n"
                    f"[프로젝트]\n{proj_str}\n\n"
                    "이 경험을 구체적으로 파고드는 경험 기반 질문 3개를 생성해주세요."
                ),
            },
        ],
    )
    items = json.loads(_clean_json(response.choices[0].message.content))
    return [{"type": "experience", "text": q} for q in items]


def _clean_json(text: str) -> str:
    # GPT가 ```json ... ``` 마크다운 블록으로 감쌀 때 제거
    return text.strip().replace("```json", "").replace("```", "").strip()
