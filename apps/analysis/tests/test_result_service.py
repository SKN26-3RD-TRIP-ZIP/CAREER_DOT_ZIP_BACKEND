"""
result_service 단위 테스트

테스트 대상:
  calc_confidence_interval()  CI 구간 + 라벨 산출
  build_match_result()        최종 응답 조립

실행:
  pytest apps/analysis/tests/test_result_service.py -v -s
"""

import pytest
from apps.analysis.services.result_service import (
    calc_confidence_interval,
    build_match_result,
)


# ══════════════════════════════════════════════════════════════
# calc_confidence_interval
# ══════════════════════════════════════════════════════════════

class TestCalcConfidenceInterval:

    @pytest.mark.parametrize("score, expected_label", [
        (0,    "낮음"),
        (20,   "낮음"),
        (39,   "낮음"),
        (40,   "가능성 있음"),
        (55,   "가능성 있음"),
        (59,   "가능성 있음"),
        (60,   "높음"),
        (70,   "높음"),
        (79,   "높음"),
        (80,   "매우 높음"),
        (90,   "매우 높음"),
        (100,  "매우 높음"),
    ])
    def test_label_by_score(self, score, expected_label):
        ci = calc_confidence_interval(score, score, score, 50.0)
        print(f"\nscore={score} → label={ci['label']} low={ci['low']} high={ci['high']}")
        assert ci["label"] == expected_label

    @pytest.mark.parametrize("score", [0, 20, 40, 55, 60, 75, 80, 95, 100])
    def test_ci_range_valid(self, score):
        """low ≤ score ≤ high, 모두 0~100 범위"""
        ci = calc_confidence_interval(score, score, score, 50.0)
        print(f"\nscore={score} → [{ci['low']}, {ci['high']}]")
        assert ci["low"]  >= 0.0
        assert ci["high"] <= 100.0
        assert ci["low"]  <= ci["high"]

    def test_rule_score_zero_widens_ci(self):
        """rule_score=0이면 CI가 더 넓어진다 (불확실성 반영)"""
        ci_with_rule    = calc_confidence_interval(60.0, 60.0, 60.0, rule_score=60.0)
        ci_without_rule = calc_confidence_interval(60.0, 60.0, 60.0, rule_score=0.0)
        width_with    = ci_with_rule["high"]    - ci_with_rule["low"]
        width_without = ci_without_rule["high"] - ci_without_rule["low"]
        print(f"\nrule=60: [{ci_with_rule['low']}, {ci_with_rule['high']}] width={width_with}")
        print(f"rule=0:  [{ci_without_rule['low']}, {ci_without_rule['high']}] width={width_without}")
        assert width_without > width_with

    @pytest.mark.parametrize("score, rule_score", [
        (5,   0),   # 낮음 + rule없음 → low가 0 이하로 안 내려가야 함
        (98,  0),   # 매우 높음 + rule없음 → high가 100 초과 안 해야 함
        (100, 100), # 경계값
        (0,   0),   # 경계값
    ])
    def test_ci_never_out_of_bounds(self, score, rule_score):
        ci = calc_confidence_interval(score, score, score, rule_score)
        print(f"\nscore={score} rule={rule_score} → [{ci['low']}, {ci['high']}]")
        assert ci["low"]  >= 0.0,   f"low 음수 발생: {ci['low']}"
        assert ci["high"] <= 100.0, f"high 100 초과: {ci['high']}"

    def test_all_four_labels_reachable(self):
        """네 가지 라벨이 모두 도달 가능한지"""
        labels = {
            calc_confidence_interval(20,  20,  20,  50)["label"],
            calc_confidence_interval(50,  50,  50,  50)["label"],
            calc_confidence_interval(70,  70,  70,  50)["label"],
            calc_confidence_interval(90,  90,  90,  50)["label"],
        }
        expected = {"낮음", "가능성 있음", "높음", "매우 높음"}
        print(f"\n도달된 라벨: {labels}")
        assert labels == expected


# ══════════════════════════════════════════════════════════════
# build_match_result
# ══════════════════════════════════════════════════════════════

class TestBuildMatchResult:

    @pytest.fixture
    def sample_match_result(self):
        return {
            "match_score":        72.5,
            "tech_score":         80.0,
            "trait_score":        65.0,
            "rule_score":         60.0,
            "matched_keywords":   ["python", "django"],
            "unmatched_keywords": ["kubernetes", "kafka"],
            "trait_details":      [{"trait": "주도적 문제해결", "best_match": "경험", "similarity": 0.75}],
            "rule_detail":        {"years_gap": -1, "education_ok": True, "job_type_match": True},
            "strengths":          ["Python 백엔드 개발 경험"],
            "weaknesses":         ["Kubernetes 경험 부족"],
            "cl_points":          ["팀 리딩 경험 강조"],
        }

    def test_confidence_interval_added(self, sample_match_result):
        """build_match_result는 confidence_interval을 추가해야 한다"""
        result = build_match_result(sample_match_result, "experienced")
        print(f"\nCI: {result['confidence_interval']}")
        assert "confidence_interval" in result
        ci = result["confidence_interval"]
        assert "low" in ci and "high" in ci and "label" in ci

    def test_original_fields_preserved(self, sample_match_result):
        """기존 필드가 그대로 유지되는지"""
        result = build_match_result(sample_match_result, "entry")
        for key in sample_match_result:
            assert key in result, f"필드 누락: {key}"

    @pytest.mark.parametrize("match_score, expected_label", [
        (30.0, "낮음"),
        (50.0, "가능성 있음"),
        (70.0, "높음"),
        (85.0, "매우 높음"),
    ])
    def test_label_matches_score(self, match_score, expected_label):
        match_result = {
            "match_score": match_score, "tech_score": match_score,
            "trait_score": match_score, "rule_score": 50.0,
            "matched_keywords": [], "unmatched_keywords": [],
            "trait_details": [], "rule_detail": {},
            "strengths": [], "weaknesses": [], "cl_points": [],
        }
        result = build_match_result(match_result, "entry")
        label  = result["confidence_interval"]["label"]
        print(f"\nmatch_score={match_score} → label={label}")
        assert label == expected_label

    def test_result_scores_in_range(self, sample_match_result):
        """모든 점수가 0~100 범위"""
        result = build_match_result(sample_match_result, "experienced")
        for key in ["match_score", "tech_score", "trait_score", "rule_score"]:
            assert 0.0 <= result[key] <= 100.0, f"{key}={result[key]} 범위 초과"

    @pytest.mark.parametrize("career_level", ["entry", "experienced"])
    def test_both_career_levels(self, sample_match_result, career_level):
        """entry/experienced 모두 정상 동작"""
        result = build_match_result(sample_match_result, career_level)
        print(f"\n[{career_level}] CI={result['confidence_interval']}")
        assert result["confidence_interval"]["label"] in {"낮음", "가능성 있음", "높음", "매우 높음"}
