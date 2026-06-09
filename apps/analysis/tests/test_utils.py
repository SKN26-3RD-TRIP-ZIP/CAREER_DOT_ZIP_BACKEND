"""
utils 단위 테스트 (API 호출 없음)

테스트 대상:
  clean_json()         LLM 응답 마크다운 블록 제거
  cosine_similarity()  코사인 유사도 계산

실행:
  pytest apps/analysis/tests/test_utils.py -v
"""

import math
import pytest
from apps.analysis.services.utils import clean_json, cosine_similarity


# ══════════════════════════════════════════════════════════════
# clean_json
# ══════════════════════════════════════════════════════════════

class TestCleanJson:

    def test_순수_json_그대로_반환(self):
        raw = '{"key": "value"}'
        assert clean_json(raw) == '{"key": "value"}'

    def test_json_코드블록_제거(self):
        raw = '```json\n{"key": "value"}\n```'
        result = clean_json(raw)
        assert result == '{"key": "value"}'
        assert "```" not in result

    def test_코드블록만_제거(self):
        """``` 블록 (json 명시 없음)"""
        raw = '```\n{"key": "value"}\n```'
        result = clean_json(raw)
        assert "```" not in result
        assert "key" in result

    def test_앞뒤_공백_제거(self):
        raw = '  {"key": "value"}  '
        result = clean_json(raw)
        assert result == '{"key": "value"}'

    def test_빈_문자열(self):
        assert clean_json("") == ""

    def test_줄바꿈_포함_json(self):
        raw = '```json\n{\n  "a": 1,\n  "b": 2\n}\n```'
        result = clean_json(raw)
        assert "```" not in result
        assert '"a"' in result

    def test_배열_json(self):
        raw = '```json\n[{"q": "질문1"}, {"q": "질문2"}]\n```'
        result = clean_json(raw)
        assert result.startswith("[")

    def test_이중_코드블록_없는_경우(self):
        """마크다운 블록이 아예 없는 경우도 정상"""
        raw = '{"tech": ["Python", "Django"]}'
        assert clean_json(raw) == raw


# ══════════════════════════════════════════════════════════════
# cosine_similarity
# ══════════════════════════════════════════════════════════════

class TestCosineSimilarity:

    def test_동일_벡터_유사도_1(self):
        v = [1.0, 0.0, 0.0]
        assert cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-6)

    def test_직교_벡터_유사도_0(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-6)

    def test_반대_방향_벡터_유사도_음수(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        result = cosine_similarity(a, b)
        assert result == pytest.approx(-1.0, abs=1e-6)

    def test_영벡터_a_입력시_0반환(self):
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert cosine_similarity(a, b) == 0.0

    def test_영벡터_b_입력시_0반환(self):
        a = [1.0, 2.0, 3.0]
        b = [0.0, 0.0, 0.0]
        assert cosine_similarity(a, b) == 0.0

    def test_두_영벡터_0반환(self):
        assert cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0

    def test_유사도_범위(self):
        """결과는 항상 -1.0 ~ 1.0"""
        a = [1.0, 2.0, 3.0]
        b = [4.0, 5.0, 6.0]
        result = cosine_similarity(a, b)
        assert -1.0 <= result <= 1.0

    @pytest.mark.parametrize("a, b, expected", [
        ([1.0, 1.0], [1.0, 1.0], 1.0),
        ([1.0, 0.0], [0.0, 1.0], 0.0),
        ([3.0, 4.0], [3.0, 4.0], 1.0),   # 크기 다른 동방향 벡터
        ([1.0, 2.0], [-1.0, -2.0], -1.0), # 반대 방향
    ])
    def test_parametrized_cases(self, a, b, expected):
        assert cosine_similarity(a, b) == pytest.approx(expected, abs=1e-6)

    def test_스케일_불변(self):
        """벡터 크기를 2배로 해도 유사도는 동일해야 함"""
        a = [1.0, 2.0, 3.0]
        b = [4.0, 5.0, 6.0]
        a2 = [x * 2 for x in a]
        b2 = [x * 3 for x in b]
        assert cosine_similarity(a, b) == pytest.approx(cosine_similarity(a2, b2), abs=1e-6)

    def test_대칭성(self):
        """cosine_similarity(a, b) == cosine_similarity(b, a)"""
        a = [1.0, 2.0, 3.0]
        b = [4.0, 5.0, 6.0]
        assert cosine_similarity(a, b) == pytest.approx(cosine_similarity(b, a), abs=1e-6)
