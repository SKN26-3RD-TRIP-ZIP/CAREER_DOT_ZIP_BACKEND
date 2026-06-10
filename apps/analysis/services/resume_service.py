"""
Pipeline 1 - ② 사용자 문서 분석

역할:
  이력서·자기소개서를 읽고 매칭·갭 분석에 필요한 지원자 정보를 구조화해 추출한다.

포함 함수:
  analyze_resume()  이력서 + 자소서 통합 분석
"""

import json
from .utils import get_client, clean_json


def analyze_resume(resume_text: str, cover_letter_text: str) -> dict:
    """
    이력서 + 자기소개서를 분석해 구조화된 딕셔너리로 반환한다.

    반환 형식:
    {
        # ─ 기술 분석 ─────────────────────────────────────────
        "tech_stack":        ["Python", "Django"],

        # ─ 경험 분석 ─────────────────────────────────────────
        "key_experiences":   ["3인 팀에서 백엔드 리드로 REST API 15개 설계"],
        "projects": [
            {
                "name":   "커머스 플랫폼",
                "role":   "백엔드 개발",
                "tech":   ["Python", "Django"],
                "result": "MAU 1만 달성",
                "domain": "e-commerce"
            }
        ],

        # ─ 역량·인재상 분석 ───────────────────────────────────
        "strengths":         ["데이터 기반 의사결정 (A/B 테스트 경험 보유)"],
        "trait_evidence":    ["의견 충돌 시 데이터를 근거로 설득해 팀 합의를 이끌어낸 경험"],

        # ─ 자격 조건 분석 (룰베이스 점수용) ─────────────────
        "years_of_experience": 2,        # 실무 경력 연수 (정규직·계약직·인턴 합산)
        "education":           "대졸",   # 최종 학력 ("고졸" | "대졸" | "석사이상")
        "career_level":        "entry",  # 이력서 기반 자동 추론 ("entry" | "experienced")
    }
    """
    client = get_client()
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
                    "4. trait_evidence\n"
                    "   - 이력서·자소서에서 인재상·소프트 스킬·태도를 증명하는 문장 추출\n"
                    "   - '~했습니다' 단순 나열 금지. 행동 + 맥락이 담긴 1~2문장으로 작성\n"
                    "   - 예: '의견 충돌 시 데이터를 근거로 설득해 팀 합의를 이끌어낸 경험'\n"
                    "   - 기술 스택과 겹치는 내용 제외, 태도·협업·문제해결 방식 중심으로\n\n"
                    "5. projects\n"
                    "   - 프로젝트별로 name / role / tech / result / domain 5개 필드 필수\n"
                    "   - result는 정량 수치 우선 (없으면 정성적 성과 명시)\n"
                    "   - role은 팀 내 본인의 실제 기여 범위만\n"
                    "   - domain: 서비스 도메인 (예: e-commerce, fintech, healthcare, logistics, edu-tech 등)\n\n"
                    "6. years_of_experience\n"
                    "   - 정규직·계약직·인턴 등 실무 경험 합산 연수 (소수점 0.5 단위 허용)\n"
                    "   - 프로젝트·공모전·학교 활동은 포함하지 않음\n"
                    "   - 명시된 기간이 없으면 0\n\n"
                    "7. education\n"
                    "   - 최종 학력 또는 재학 중 학력을 아래 중 하나로만 반환\n"
                    "   - 반환값: \"고졸\" | \"대졸\" | \"석사이상\"\n\n"
                    "8. career_level\n"
                    "   - \"experienced\": 정규직·계약직·인턴 실무 경험 합산 1년 이상 명시된 경우\n"
                    "   - \"entry\": 재학 중, 졸업예정, 프로젝트·공모전만 있는 경우\n\n"
                    "반드시 아래 JSON 형식으로만 응답하세요. 마크다운 블록, 설명 텍스트 금지.\n"
                    "{\n"
                    '  "tech_stack":           ["기술1", "기술2"],\n'
                    '  "key_experiences":      ["경험 1문장", "경험 1문장"],\n'
                    '  "strengths":            ["역량 + 근거"],\n'
                    '  "trait_evidence":       ["태도·역량 증거 문장1", "태도·역량 증거 문장2"],\n'
                    '  "projects": [\n'
                    '    {"name": "프로젝트명", "role": "본인의 역할", '
                    '"tech": ["사용 기술"], "result": "정량 또는 정성 성과", "domain": "e-commerce"}\n'
                    '  ],\n'
                    '  "years_of_experience":  0,\n'
                    '  "education":            "대졸",\n'
                    '  "career_level":         "entry"\n'
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
    raw = clean_json(response.choices[0].message.content)
    return json.loads(raw)
