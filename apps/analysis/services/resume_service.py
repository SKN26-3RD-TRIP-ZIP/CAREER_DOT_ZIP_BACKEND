import json
from openai import OpenAI

client = OpenAI()


def analyze_resume(resume_text: str, cover_letter_text: str) -> dict:
    """
    이력서 + 자소서를 분석해 구조화된 딕셔너리로 반환.

    반환 형식:
    {
        "tech_stack": ["Python", "Django"],
        "key_experiences": ["A 프로젝트에서 백엔드 API 설계 담당"],
        "strengths": ["문제 해결력"],
        "projects": [
            {"name": "커머스 플랫폼", "role": "백엔드 개발", "result": "MAU 1만 달성"}
        ]
    }
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        messages=[
            {
                "role": "system",
                "content": (
                    "이력서와 자소서를 분석해 핵심 정보를 추출하는 전문가입니다.\n"
                    "반드시 아래 JSON 형식으로만 응답하세요:\n"
                    "{\n"
                    "  \"tech_stack\": [\"기술1\"],\n"
                    "  \"key_experiences\": [\"경험 요약\"],\n"
                    "  \"strengths\": [\"강점1\"],\n"
                    "  \"projects\": [\n"
                    "    {\"name\": \"프로젝트명\", \"role\": \"역할\", \"result\": \"성과\"}\n"
                    "  ]\n"
                    "}"
                ),
            },
            {
                "role": "user",
                "content": f"[이력서]\n{resume_text}\n\n[자소서]\n{cover_letter_text}",
            },
        ],
    )
    raw = _clean_json(response.choices[0].message.content)
    return json.loads(raw)


def _clean_json(text: str) -> str:
    # GPT가 ```json ... ``` 마크다운 블록으로 감쌀 때 제거
    return text.strip().replace("```json", "").replace("```", "").strip()
