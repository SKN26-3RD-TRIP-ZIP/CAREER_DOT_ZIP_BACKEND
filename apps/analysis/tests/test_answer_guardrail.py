"""
answer_guardrail 단위 테스트 (순수 함수, LLM/네트워크 없음)

실행:
  pytest apps/analysis/tests/test_answer_guardrail.py -v
"""

from apps.analysis.services.answer_guardrail import check_groundedness, check_answer


class TestCheckGroundedness:

    def test_원본에_있는_수치는_통과(self):
        src = "Redis 캐싱으로 응답속도를 40% 개선했고 MAU 1만을 달성했습니다."
        ans = "응답속도를 40% 개선한 경험이 있습니다."
        r = check_groundedness(ans, src)
        assert r["grounded"] is True
        assert r["unsupported"] == []

    def test_지어낸_수치_적발(self):
        src = "백엔드 API를 설계하고 운영했습니다."   # 수치 없음
        ans = "응답속도를 40% 개선하고 처리량을 2배 늘렸습니다."
        r = check_groundedness(ans, src)
        assert r["grounded"] is False
        assert "40%" in r["unsupported"]
        assert "2배" in r["unsupported"]

    def test_일부만_근거있을때(self):
        src = "MAU 1만을 달성했습니다."
        ans = "MAU 1만을 달성했고 전환율을 15% 높였습니다."  # 15%는 원본에 없음
        r = check_groundedness(ans, src)
        assert r["grounded"] is False
        assert r["unsupported"] == ["15%"]

    def test_퍼센트_표기_정규화(self):
        src = "전환율을 30퍼센트 개선했습니다."
        ans = "전환율 30% 개선"
        r = check_groundedness(ans, src)
        assert r["grounded"] is True       # '30퍼센트' == '30%'

    def test_콤마_숫자_정규화(self):
        src = "월 매출 1,000만원을 달성했습니다."
        ans = "매출 1000만원 기여"
        r = check_groundedness(ans, src)
        assert r["grounded"] is True       # 1,000 == 1000

    def test_단위없는_숫자는_무시(self):
        # 단위 없는 맨 숫자는 위험도 낮아 검사 대상 아님
        src = "팀 프로젝트를 했습니다."
        ans = "저희 팀은 다같이 협업했습니다."
        r = check_groundedness(ans, src)
        assert r["grounded"] is True

    def test_빈_입력_안전(self):
        assert check_groundedness("", "")["grounded"] is True
        assert check_groundedness(None, None)["grounded"] is True


class TestCheckAnswer:

    def test_STAR_dict_전체_검사(self):
        source = "백엔드 API 20개를 설계했습니다."
        answer = {
            "summary": "API 설계 경험이 있습니다.",
            "situation": "스타트업에서 근무했습니다.",
            "task": "API 설계를 맡았습니다.",
            "action": "REST API 20개를 설계했습니다.",   # 근거 있음
            "result": "응답속도를 50% 개선했습니다.",       # 근거 없음 → 적발
        }
        r = check_answer(answer, source)
        assert r["grounded"] is False
        assert "50%" in r["unsupported"]
        assert "20개" not in r["unsupported"]   # 원본에 있으므로 통과
