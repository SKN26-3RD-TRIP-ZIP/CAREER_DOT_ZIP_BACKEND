"""
품질 평가용 케이스 데이터셋.

처음엔 대표 케이스 몇 개로 시작하고, 운영하면서 "품질이 나빴던 실제 사례"를
계속 추가하면 회귀 테스트로 쌓인다. expect_min_overall 미만이면 품질 저하로 간주.

구조:
  QUESTION_CASES: {context, question, expect_min_overall}
  ANSWER_CASES:   {source, answer(STAR dict), expect_min_overall}
"""

QUESTION_CASES = [
    {
        "label": "GitHub 미검증 추궁",
        "context": "JD 기술: Python, Django, Redis. 이력서 주장: Redis 사용. "
                   "GitHub repo에서 Redis 사용 근거 못 찾음.",
        "question": "이력서에 Redis를 사용했다고 하셨는데 repo에서 사용 흔적을 찾지 "
                    "못했습니다. 어디에 어떤 목적으로 적용하셨나요?",
        "expect_min_overall": 4.0,
    },
    {
        "label": "뻔한 일반 질문 (낮은 점수 기대)",
        "context": "JD 기술: Python, Django.",
        "question": "본인의 장점과 단점은 무엇인가요?",
        "expect_min_overall": 2.5,   # 일부러 낮은 기준 — 이 질문은 걸러져야 정상
    },
]

ANSWER_CASES = [
    {
        "label": "근거 있는 답변",
        "source": "스타트업에서 백엔드 API 20개를 설계했고 Redis 캐싱으로 응답속도 40% 개선.",
        "answer": {
            "summary": "Redis 캐싱으로 응답속도를 크게 개선한 경험이 있습니다.",
            "situation": "스타트업에서 트래픽 증가로 API 응답이 느려지는 문제가 있었습니다.",
            "task": "응답속도 개선을 제가 주도적으로 맡았습니다.",
            "action": "병목 API에 Redis 캐싱을 도입하고 키 전략을 설계했습니다.",
            "result": "응답속도를 40% 개선했습니다.",
            "basis_source": "resume",
        },
        "expect_min_overall": 4.0,
    },
    {
        "label": "수치 창작 답변 (가드레일이 잡아야 함)",
        "source": "백엔드 API를 설계하고 운영했습니다.",   # 수치 전혀 없음
        "answer": {
            "summary": "성능을 크게 개선했습니다.",
            "situation": "서비스가 느렸습니다.",
            "task": "성능 개선을 맡았습니다.",
            "action": "쿼리를 최적화했습니다.",
            "result": "응답속도를 70% 개선하고 처리량을 3배 늘렸습니다.",  # 창작
            "basis_source": "resume",
        },
        "expect_min_overall": 2.5,   # groundedness 강제 하향으로 낮아져야 정상
    },
]
