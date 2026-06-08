import json
from openai import OpenAI


def extract_jd_keywords(jd_text: str) -> list[str]:
    """JD 텍스트에서 기술 스택·역량·우대사항 키워드를 추출해 리스트로 반환."""
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        messages=[
            {
                "role": "system",
                "content": (
                    "당신은 IT 채용공고 분석 전문가입니다.\n"
                    "JD를 읽고 아래 기준으로 키워드를 분류·추출하세요.\n\n"
                    "추출 기준:\n"
                    "1. 기술 스택: 프로그래밍 언어, 프레임워크, 라이브러리, 인프라, DB, 툴\n"
                    "2. 직무 역량: 설계, 개발, 운영, 커뮤니케이션 등 행동 기반 역량\n"
                    "3. 우대사항: '우대', '있으면 좋은', '경험자 우대' 표현과 연결된 항목\n\n"
                    "규칙:\n"
                    "- 키워드는 원문에서 사용한 표현 그대로 추출 (임의 번역·축약 금지)\n"
                    "- 동의어 중복 제거 (예: 'AWS' 와 'Amazon Web Services' 중 하나만)\n"
                    "- 회사명, 복지, 연봉 등 직무와 무관한 내용은 제외\n"
                    "- 반드시 JSON 배열로만 응답. 마크다운 블록, 설명 텍스트 금지\n\n"
                    "출력 예시: [\"Python\", \"Django\", \"REST API\", \"문제 해결력\", \"Docker\"]"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"아래 채용공고에서 핵심 키워드를 추출해주세요.\n"
                    f"필수 기술·역량과 우대사항을 모두 포함하되, 중요도 높은 순으로 정렬해주세요.\n\n"
                    f"[채용공고 JD]\n{jd_text}"
                ),
            },
        ],
    )
    raw = _clean_json(response.choices[0].message.content)
    return json.loads(raw)


def _clean_json(text: str) -> str:
    # GPT가 ```json ... ``` 마크다운 블록으로 감쌀 때 제거
    return text.strip().replace("```json", "").replace("```", "").strip()
