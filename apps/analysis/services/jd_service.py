import json
from openai import OpenAI

client = OpenAI()


def extract_jd_keywords(jd_text: str) -> list[str]:
    """JD 텍스트에서 기술 스택·역량·우대사항 키워드를 추출해 리스트로 반환."""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        messages=[
            {
                "role": "system",
                "content": (
                    "당신은 채용공고 분석 전문가입니다.\n"
                    "JD에서 기술 스택, 역량, 우대사항 키워드를 추출하세요.\n"
                    "반드시 JSON 배열 형식으로만 응답하세요. 예: [\"Python\", \"Django\"]"
                ),
            },
            {
                "role": "user",
                "content": f"다음 JD에서 핵심 키워드를 추출해주세요:\n\n{jd_text}",
            },
        ],
    )
    raw = _clean_json(response.choices[0].message.content)
    return json.loads(raw)


def _clean_json(text: str) -> str:
    # GPT가 ```json ... ``` 마크다운 블록으로 감쌀 때 제거
    return text.strip().replace("```json", "").replace("```", "").strip()
