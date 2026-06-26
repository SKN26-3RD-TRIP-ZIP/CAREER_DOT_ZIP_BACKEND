"""
파이프라인 시나리오 비교 테스트

단위 테스트를 넘어 실제 지원자 프로필 조합별 점수를 비교한다.
GPT/임베딩 호출 없이 순수 계산 함수만으로 수치 비교가 가능하다.

테스트 시나리오:
  1. 동일 JD에 4종 지원자(신입/주니어/미드/시니어) 점수 비교
  2. 동일 지원자에 4종 JD 점수 비교
  3. rule_score 연차 민감도 분석

실행:
  pytest apps/analysis/tests/test_pipeline_scenarios.py -v -s
"""

import unittest
try:
    import pytest
except ModuleNotFoundError:
    raise unittest.SkipTest("pytest is required for this pytest-style analysis test module")
from apps.analysis.services.match_service import _calc_tech_score, _calc_rule_score, CAREER_WEIGHTS
from apps.analysis.services.gap_service   import calculate_gap, build_gap_message
from apps.analysis.services.result_service import calc_confidence_interval


def weighted_score(tech, trait, rule, career_level):
    w = CAREER_WEIGHTS[career_level]
    return round(tech * w["tech_w"] + trait * w["trait_w"] + rule * w["rule_w"], 1)


# ══════════════════════════════════════════════════════════════
# 시나리오 1: 동일 JD(미드레벨 포지션)에 4종 지원자 점수 비교
# ══════════════════════════════════════════════════════════════

class TestScenario_SameJD_DifferentCandidates:
    """
    JD: 백엔드 3년+, 대졸, required=[Python, Django, Redis, Docker]
    예상 순서: senior > mid > junior > entry
    """

    JD_REQ = {
        "min_years":      3,
        "education":      "대졸",
        "job_type":       "백엔드",
        "required_tech":  ["Python", "Django", "Redis", "Docker"],
        "preferred_tech": ["Kubernetes", "AWS"],
    }
    JD_TECH = ["Python", "Django", "PostgreSQL", "Redis", "Docker", "Kubernetes"]
    JOB_ROLE = "백엔드 개발자"

    @pytest.fixture
    def scores(self, resume_entry, resume_junior, resume_mid, resume_senior):
        results = {}
        for name, resume in [
            ("entry",  resume_entry),
            ("junior", resume_junior),
            ("mid",    resume_mid),
            ("senior", resume_senior),
        ]:
            tech_score, _, _ = _calc_tech_score(self.JD_TECH, resume["tech_stack"])
            rule_score, detail = _calc_rule_score(self.JD_REQ, resume, job_role=self.JOB_ROLE)
            career_level = resume["career_level"]
            trait_score = 65.0  # 임베딩 없이 고정값 사용
            match = weighted_score(tech_score, trait_score, rule_score, career_level)
            results[name] = {
                "tech_score":  tech_score,
                "rule_score":  rule_score,
                "match_score": match,
                "career_level": career_level,
                "detail":      detail,
            }
            print(f"\n[{name}] tech={tech_score} rule={rule_score} match={match} detail={detail}")
        return results

    def test_senior_scores_highest(self, scores):
        """시니어 rule_score > 나머지 (연차·학력 기준 — tech_stack은 JD와 다를 수 있음)"""
        assert scores["senior"]["rule_score"] >= scores["mid"]["rule_score"]
        assert scores["senior"]["rule_score"] >= scores["junior"]["rule_score"]
        assert scores["senior"]["rule_score"] >= scores["entry"]["rule_score"]

    def test_entry_scores_lowest_rule(self, scores):
        """신입은 rule_score(연차)가 가장 낮아야 한다"""
        assert scores["entry"]["rule_score"] <= scores["junior"]["rule_score"]
        assert scores["entry"]["rule_score"] <= scores["mid"]["rule_score"]

    def test_tech_score_increases_with_experience(self, scores):
        """경험이 많을수록 tech_score가 높거나 같아야 한다"""
        assert scores["entry"]["tech_score"] <= scores["mid"]["tech_score"]
        assert scores["junior"]["tech_score"] <= scores["mid"]["tech_score"]

    def test_all_scores_in_range(self, scores):
        """모든 점수 0~100 범위"""
        for name, s in scores.items():
            assert 0 <= s["match_score"] <= 100, f"{name} match_score 범위 초과"
            assert 0 <= s["tech_score"]  <= 100, f"{name} tech_score 범위 초과"
            assert 0 <= s["rule_score"]  <= 100, f"{name} rule_score 범위 초과"

    def test_score_spread_meaningful(self, scores):
        """신입과 시니어 사이에 의미있는 점수 차이 존재 (5점 이상)"""
        diff = scores["senior"]["match_score"] - scores["entry"]["match_score"]
        print(f"\n시니어-신입 점수 차이: {diff}")
        assert diff >= 5.0, f"점수 차이가 너무 작음: {diff}"


# ══════════════════════════════════════════════════════════════
# 시나리오 2: 동일 지원자(미드)에 4종 JD 점수 비교
# ══════════════════════════════════════════════════════════════

class TestScenario_SameCandidate_DifferentJD:
    """
    지원자: 미드레벨 (3년, 대졸, Python/Django/FastAPI/PostgreSQL/Redis/K8s/Docker/AWS)
    예상: entry JD > junior JD ≈ mid JD > senior JD (rule_score 기준)
    """

    JOB_ROLE = "백엔드 개발자"

    @pytest.fixture
    def scores(self, resume_mid, jd_req_entry, jd_req_junior, jd_req_mid, jd_req_senior):
        results = {}
        jd_map = {
            "entry":  (jd_req_entry,  ["Python", "Django"]),
            "junior": (jd_req_junior, ["Python", "Django", "PostgreSQL", "Redis", "Docker"]),
            "mid":    (jd_req_mid,    ["Python", "Django", "Redis", "Docker", "Kubernetes"]),
            "senior": (jd_req_senior, ["Python", "Kubernetes", "Kafka", "Terraform", "AWS", "Java"]),
        }
        for name, (jd_req, jd_tech) in jd_map.items():
            tech_score, _, _ = _calc_tech_score(jd_tech, resume_mid["tech_stack"])
            rule_score, detail = _calc_rule_score(jd_req, resume_mid, job_role=self.JOB_ROLE)
            match = weighted_score(tech_score, 65.0, rule_score, "experienced")
            results[name] = {"tech_score": tech_score, "rule_score": rule_score, "match_score": match}
            print(f"\n[JD:{name}] tech={tech_score} rule={rule_score} match={match}")
        return results

    def test_entry_jd_has_max_rule_score(self, scores):
        """신입 JD에 지원하면 rule_score 최대 (연차 초과 충족)"""
        assert scores["entry"]["rule_score"] == 100.0

    def test_senior_jd_has_lower_rule_score(self, scores):
        """시니어 JD는 연차 미충족으로 rule_score 낮아야 함"""
        assert scores["senior"]["rule_score"] < scores["mid"]["rule_score"]

    def test_senior_jd_tech_score_lower(self, scores):
        """시니어 JD는 Java/Kafka 같은 미보유 기술이 많아 tech_score 낮아야 함"""
        assert scores["senior"]["tech_score"] < scores["entry"]["tech_score"]


# ══════════════════════════════════════════════════════════════
# 시나리오 3: 연차 민감도 분석
# ══════════════════════════════════════════════════════════════

class TestYearsSensitivity:
    """
    JD 3년 요구 포지션에서 보유 연차별 rule_score 변화 추적
    """

    JD_REQ = {"min_years": 3, "education": "무관", "job_type": ""}

    @pytest.mark.parametrize("years, expected_years_score", [
        (0,   10.0),   # 3년 부족 → 40-30=10
        (0.5, 15.0),   # 2.5년 부족 → 40-25=15
        (1,   20.0),   # 2년 부족 → 40-20=20
        (1.5, 25.0),   # 1.5년 부족 → 40-15=25
        (2,   30.0),   # 1년 부족 → 40-10=30
        (2.5, 35.0),   # 0.5년 부족 → 40-5=35
        (3,   40.0),   # 정확히 충족 → 40
        (4,   40.0),   # 초과 충족 → 40 (상한 유지)
        (10,  40.0),   # 대폭 초과 → 40 (상한 유지)
    ])
    def test_years_sensitivity(self, years, expected_years_score):
        resume = {"years_of_experience": years, "education": "대졸"}
        score, detail = _calc_rule_score(self.JD_REQ, resume)
        print(f"\n보유={years}년 → years_score={detail['years_score']} (기대={expected_years_score})")
        assert detail["years_score"] == expected_years_score


# ══════════════════════════════════════════════════════════════
# 시나리오 4: CI 라벨과 점수 분포 확인
# ══════════════════════════════════════════════════════════════

class TestCIDistribution:
    """다양한 점수 분포에서 CI 라벨과 구간 너비 비교"""

    @pytest.mark.parametrize("score, rule_score, min_expected_width", [
        (20,  0,    15),   # 낮음 + rule없음 → 넓은 구간
        (20,  60,   8),    # 낮음 + rule있음
        (60,  0,    20),   # 높음 + rule없음 → 넓은 구간
        (60,  60,   14),   # 높음 + rule있음
        (85,  0,    13),   # 매우높음 + rule없음
        (85,  60,   7),    # 매우높음 + rule있음
    ])
    def test_ci_width(self, score, rule_score, min_expected_width):
        ci = calc_confidence_interval(score, score, score, rule_score)
        width = ci["high"] - ci["low"]
        print(f"\nscore={score} rule={rule_score} → [{ci['low']}, {ci['high']}] 너비={width} label={ci['label']}")
        assert width >= min_expected_width, f"CI 너비 {width}가 최소 기대값 {min_expected_width}보다 작음"
