import json
from openai import OpenAI


def analyze_resume(resume_text: str, cover_letter_text: str) -> dict:
    """
    이력서 + 자소서를 분석해 구조화된 딕셔너리로 반환.

    반환 형식:
    {
        "tech_stack": ["Python", "Django"],
        "key_experiences": ["A 프로젝트에서 백엔드 API 설계 담당"],
        "strengths": ["문제 해결력"],
        "projects": [
            {"name": "커머스 플랫폼", "role": "백엔드 개발", "tech": ["Python", "Django"], "result": "MAU 1만 달성"}
        ]
    }
    """
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        messages=[
            {
                "role": "system",
                "content": (
                    "당신은 IT 직무 채용 전문가이자 이력서 분석가입니다.\n"
                    "이력서와 자기소개서를 읽고, 면접 질문 생성에 활용할 수 있도록 핵심 정보를 구조화해 추출합니다.\n\n"
                    "추출 기준:\n"
                    "1. tech_stack\n"
                    "   - 이력서·자소서에 명시된 기술만 포함 (추측·유추 금지)\n"
                    "   - 언어, 프레임워크, 라이브러리, DB, 인프라, 툴 포함\n"
                    "   - 원문 표기 그대로 사용 (예: 'React', 'Spring Boot')\n\n"
                    "2. key_experiences\n"
                    "   - 지원자가 주도적으로 수행한 경험만 포함\n"
                    "   - '~했습니다' 요약 금지. 행동 + 맥락 포함한 1~2문장으로 작성\n"
                    "   - 예: '3인 팀에서 백엔드 리드로 REST API 15개 설계 및 구현'\n\n"
                    "3. strengths\n"
                    "   - 이력서·자소서에서 반복되거나 강조된 역량만 추출\n"
                    "   - 추상적 단어('성실', '열정') 단독 사용 금지. 근거가 있는 역량만\n"
                    "   - 예: '데이터 기반 의사결정 (A/B 테스트 경험 보유)'\n\n"
                    "4. projects\n"
                    "   - 프로젝트별로 name / role / tech / result 4개 필드 필수\n"
                    "   - result는 정량 수치 우선 (없으면 정성적 성과 명시)\n"
                    "   - role은 팀 내 본인의 실제 기여 범위만 (팀 전체 성과를 본인 것처럼 쓰지 말 것)\n\n"
                    "반드시 아래 JSON 형식으로만 응답하세요. 마크다운 블록, 설명 텍스트 금지.\n"
                    "{\n"
                    "  \"tech_stack\": [\"기술1\", \"기술2\"],\n"
                    "  \"key_experiences\": [\"경험 1문장\", \"경험 1문장\"],\n"
                    "  \"strengths\": [\"역량 + 근거\"],\n"
                    "  \"projects\": [\n"
                    "    {\n"
                    "      \"name\": \"프로젝트명\",\n"
                    "      \"role\": \"본인의 역할\",\n"
                    "      \"tech\": [\"사용 기술\"],\n"
                    "      \"result\": \"정량 또는 정성 성과\"\n"
                    "    }\n"
                    "  ]\n"
                    "}"
                ),
            },
            {
                "role": "user",
                "content": (
                    "아래 이력서와 자기소개서를 분석해주세요.\n"
                    "지원자가 직접 작성한 내용만 근거로 삼고, 없는 내용은 절대 추가하지 마세요.\n\n"
                    f"[이력서]\n{resume_text}\n\n"
                    f"[자기소개서]\n{cover_letter_text}"
                ),
            },
        ],
    )
    raw = _clean_json(response.choices[0].message.content)
    return json.loads(raw)


def _clean_json(text: str) -> str:
    # GPT가 ```json ... ``` 마크다운 블록으로 감쌀 때 제거
    return text.strip().replace("```json", "").replace("```", "").strip()
