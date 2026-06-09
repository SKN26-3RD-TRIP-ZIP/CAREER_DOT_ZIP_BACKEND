"""
match_service 단위 테스트

테스트 대상:
  _calc_tech_score()   기술 스펙 점수 (집합 연산)
  _calc_rule_score()   룰베이스 점수 (연차/학력/직군)
  CAREER_WEIGHTS       가중치 합산 검증

실행:
  pytest apps/analysis/tests/test_match_service.py -v
  pytest apps/analysis/tests/test_match_service.py -v -s   # print 출력 포함
"""

import pytest
from unittest.mock import patch
from apps.analysis.services.match_service import (
    _calc_tech_score,
    _calc_trait_score,
    _calc_rule_score,
    calculate_match_score,
    CAREER_WEIGHTS,
)


# ══════════════════════════════════════════════════════════════
# _calc_tech_score
# ══════════════════════════════════════════════════════════════

class TestCalcTechScore:

    @pytest.mark.parametrize("jd, resume, expected_score, desc", [
        # 완전 매칭
        (["Python", "Django", "Redis"],
         ["Python", "Django", "Redis"],
         100.0, "완전 매칭"),

        # 부분 매칭 — 2/3
        (["Python", "Django", "Kubernetes"],
         ["Python", "Django"],
         66.7, "부분 매칭 (2/3)"),

        # 부분 매칭 — 1/4
        (["Python", "Django", "Kafka", "Kubernetes"],
         ["Python"],
         25.0, "부분 매칭 (1/4)"),

        # 매칭 없음
        (["Java", "Spring Boot", "Kafka"],
         ["Python", "Django"],
         0.0, "매칭 없음"),

        # 이력서가 JD보다 더 많아도 JD 기준 100점
        (["Python"],
         ["Python", "Django", "Redis", "Kubernetes"],
         100.0, "이력서 초과 보유"),

        # JD 비어있음
        ([],
         ["Python", "Django"],
         0.0, "JD 키워드 없음"),

        # 이력서 비어있음
        (["Python", "Django"],
         [],
         0.0, "이력서 기술 없음"),
    ])
    def test_score_range(self, jd, resume, expected_score, desc):
        score, matched, unmatched = _calc_tech_score(jd, resume)
        print(f"\n[{desc}] score={score} matched={matched} unmatched={unmatched}")
        assert 0.0 <= score <= 100.0, f"점수 범위 초과: {score}"
        assert abs(score - expected_score) < 0.5, f"기대={expected_score}, 실제={score}"

    @pytest.mark.parametrize("jd_kw, resume_kw, should_match, desc", [
        (["PostgreSQL"], ["Postgres"],     True,  "Postgres → PostgreSQL 별칭"),
        (["Node.js"],    ["nodejs"],       True,  "nodejs → Node.js 별칭"),
        (["Node.js"],    ["node"],         True,  "node → Node.js 별칭"),
        (["Kubernetes"], ["k8s"],          True,  "k8s → Kubernetes 별칭"),
        (["JavaScript"], ["js"],           True,  "js → JavaScript 별칭"),
        (["Vue"],        ["vuejs"],        True,  "vuejs → Vue 별칭"),
        (["Spring Boot"],["springboot"],   True,  "springboot → Spring Boot 별칭"),
        (["MongoDB"],    ["mongo"],        True,  "mongo → MongoDB 별칭"),
        (["React"],      ["Vue"],          False, "별칭 아닌 다른 기술"),
    ])
    def test_tech_aliases(self, jd_kw, resume_kw, should_match, desc):
        score, matched, unmatched = _calc_tech_score(jd_kw, resume_kw)
        print(f"\n[{desc}] jd={jd_kw} resume={resume_kw} score={score}")
        if should_match:
            assert score == 100.0, f"별칭 정규화 실패 — {desc}"
            assert len(unmatched) == 0
        else:
            assert score == 0.0, f"잘못된 매칭 — {desc}"

    def test_matched_unmatched_sum(self):
        jd = ["Python", "Django", "Redis", "Kubernetes", "Kafka"]
        resume = ["Python", "Django", "Redis"]
        score, matched, unmatched = _calc_tech_score(jd, resume)
        print(f"\nmatched={matched} unmatched={unmatched}")
        assert len(matched) + len(unmatched) == len(set(k.lower() for k in jd))

    def test_case_insensitive(self):
        score1, _, _ = _calc_tech_score(["python"], ["Python"])
        score2, _, _ = _calc_tech_score(["PYTHON"], ["python"])
        print(f"\n대소문자 무관 score1={score1} score2={score2}")
        assert score1 == 100.0
        assert score2 == 100.0


# ══════════════════════════════════════════════════════════════
# _calc_rule_score
# ══════════════════════════════════════════════════════════════

class TestCalcRuleScore:

    @pytest.mark.parametrize("min_years, current_years, expected_years_score, desc", [
        (0,   0,   40.0, "신입 포지션 신입 지원 (완전 충족)"),
        (3,   3,   40.0, "3년 요구 3년 보유 (딱 충족)"),
        (3,   4,   40.0, "3년 요구 4년 보유 (초과 충족)"),
        (3,   2,   30.0, "3년 요구 2년 보유 (1년 부족)"),
        (3,   1,   20.0, "3년 요구 1년 보유 (2년 부족)"),
        (3,   0,   10.0, "3년 요구 0년 보유 (3년 부족)"),
        (5,   0,    0.0, "5년 요구 0년 보유 (5년 부족 → 최저 0점)"),
        (10,  0,    0.0, "10년 요구 0년 보유 (음수 방지)"),
        (3,   2.5,  35.0, "3년 요구 2.5년 보유 (0.5년 부족)"),
    ])
    def test_years_score(self, min_years, current_years, expected_years_score, desc):
        jd_req = {"min_years": min_years, "education": "무관", "job_type": ""}
        resume = {"years_of_experience": current_years, "education": "대졸"}
        score, detail = _calc_rule_score(jd_req, resume)
        print(f"\n[{desc}] years_score={detail.get('years_score')} total={score}")
        assert detail["years_score"] == expected_years_score, f"years_score 불일치: {detail}"
        assert score >= 0.0, "점수 음수 방지 실패"

    @pytest.mark.parametrize("req_edu, cur_edu, expected_ok, desc", [
        ("무관",    "고졸",    True,  "무관 요구 → 고졸도 통과"),
        ("무관",    "대졸",    True,  "무관 요구 → 대졸 통과"),
        ("고졸",    "대졸",    True,  "고졸 요구 → 대졸 통과 (상위 학력)"),
        ("대졸",    "대졸",    True,  "대졸 요구 → 대졸 통과"),
        ("대졸",    "석사이상", True, "대졸 요구 → 석사 통과 (상위 학력)"),
        ("석사이상","석사이상", True, "석사 요구 → 석사 통과"),
        ("대졸",    "고졸",    False, "대졸 요구 → 고졸 미충족"),
        ("석사이상","대졸",    False, "석사 요구 → 대졸 미충족"),
        ("석사이상","고졸",    False, "석사 요구 → 고졸 미충족"),
    ])
    def test_education(self, req_edu, cur_edu, expected_ok, desc):
        jd_req = {"min_years": 0, "education": req_edu, "job_type": ""}
        resume = {"years_of_experience": 0, "education": cur_edu}
        score, detail = _calc_rule_score(jd_req, resume)
        print(f"\n[{desc}] edu_ok={detail.get('education_ok')} edu_score={detail.get('edu_score')}")
        assert detail["education_ok"] == expected_ok

    @pytest.mark.parametrize("req_job, job_role, expected_match, desc", [
        ("백엔드",    "백엔드 개발자",    True,  "백엔드 포함"),
        ("백엔드",    "시니어 백엔드",    True,  "백엔드 포함 (역순)"),
        ("프론트엔드","프론트엔드 개발자", True,  "프론트엔드 포함"),
        ("백엔드",    "프론트엔드 개발자", False, "직군 불일치"),
        ("",          "백엔드 개발자",    False, "JD 직군 미명시"),
        ("백엔드",    "",                 False, "지원자 직군 미입력"),
    ])
    def test_job_type(self, req_job, job_role, expected_match, desc):
        jd_req = {"min_years": 0, "education": "무관", "job_type": req_job}
        resume = {"years_of_experience": 0, "education": "대졸"}
        score, detail = _calc_rule_score(jd_req, resume, job_role=job_role)
        print(f"\n[{desc}] job_match={detail.get('job_type_match')} job_score={detail.get('job_score')}")
        assert detail["job_type_match"] == expected_match

    def test_perfect_score(self):
        """연차/학력/직군 모두 충족 → 100점"""
        jd_req = {"min_years": 3, "education": "대졸", "job_type": "백엔드"}
        resume = {"years_of_experience": 5, "education": "대졸"}
        score, detail = _calc_rule_score(jd_req, resume, job_role="백엔드 개발자")
        print(f"\n완벽 충족 score={score} detail={detail}")
        assert score == 100.0

    def test_zero_score(self):
        """연차 5년+ 부족 + 학력 미충족 + 직군 불일치 → 0점"""
        jd_req = {"min_years": 5, "education": "석사이상", "job_type": "백엔드"}
        resume = {"years_of_experience": 0, "education": "고졸"}
        score, detail = _calc_rule_score(jd_req, resume, job_role="프론트엔드 개발자")
        print(f"\n최악 조합 score={score} detail={detail}")
        assert score == 0.0

    def test_empty_jd_requirements(self):
        """빈 jd_requirements → 0점 + 빈 detail (예외 없음)"""
        score, detail = _calc_rule_score({}, {"years_of_experience": 3, "education": "대졸"})
        print(f"\n빈 jd_req score={score} detail={detail}")
        assert score == 0.0
        assert detail == {}

    def test_score_never_negative(self):
        """어떤 조합이어도 점수는 음수가 되지 않는다"""
        jd_req = {"min_years": 100, "education": "석사이상", "job_type": "백엔드"}
        resume = {"years_of_experience": 0, "education": "고졸"}
        score, _ = _calc_rule_score(jd_req, resume, job_role="")
        assert score >= 0.0


# ══════════════════════════════════════════════════════════════
# CAREER_WEIGHTS 가중치 합산 검증
# ══════════════════════════════════════════════════════════════

class TestCareerWeights:

    @pytest.mark.parametrize("career_level", ["entry", "experienced"])
    def test_weights_sum_to_one(self, career_level):
        w = CAREER_WEIGHTS[career_level]
        total = w["tech_w"] + w["trait_w"] + w["rule_w"]
        print(f"\n[{career_level}] tech={w['tech_w']} trait={w['trait_w']} rule={w['rule_w']} 합={total:.2f}")
        assert abs(total - 1.0) < 1e-9, f"{career_level} 가중치 합이 1이 아님: {total}"

    def test_experienced_has_higher_rule_weight(self):
        """경력직은 신입보다 rule_w(연차/학력) 비중이 높아야 한다"""
        assert CAREER_WEIGHTS["experienced"]["rule_w"] > CAREER_WEIGHTS["entry"]["rule_w"]

    def test_entry_tech_trait_balanced(self):
        """신입은 tech와 trait 비중이 동일하다"""
        w = CAREER_WEIGHTS["entry"]
        assert w["tech_w"] == w["trait_w"]

    @pytest.mark.parametrize("career_level", ["entry", "experienced"])
    def test_weighted_sum_formula(self, career_level):
        """가중 합산 공식 검증: match = tech*w + trait*w + rule*w"""
        w = CAREER_WEIGHTS[career_level]
        tech_score  = 80.0
        trait_score = 60.0
        rule_score  = 70.0
        expected = round(
            tech_score  * w["tech_w"]  +
            trait_score * w["trait_w"] +
            rule_score  * w["rule_w"],
            1,
        )
        print(f"\n[{career_level}] tech={tech_score} trait={trait_score} rule={rule_score} → {expected}")
        assert 0.0 <= expected <= 100.0


# ══════════════════════════════════════════════════════════════
# _calc_trait_score (임베딩 모킹)
# ══════════════════════════════════════════════════════════════

def _make_vec(i: int, dim: int = 8) -> list[float]:
    """i번째 기저 벡터 (직교)"""
    v = [0.0] * dim
    v[i % dim] = 1.0
    return v


class TestCalcTraitScore:

    def test_빈_trait_keywords_0점(self):
        client = object()
        score, details = _calc_trait_score([], ["증거 문장"], client)
        assert score == 0.0
        assert details == []

    def test_빈_trait_evidence_0점(self):
        client = object()
        score, details = _calc_trait_score(["인재상 키워드"], [], client)
        assert score == 0.0
        assert details == []

    def test_동일_벡터_100점(self):
        """키워드와 증거가 동일 벡터 → 유사도 1.0 → 100점"""
        v = [1.0, 0.0, 0.0, 0.0]
        with patch("apps.analysis.services.match_service.get_embeddings", return_value=[v, v]):
            score, details = _calc_trait_score(["키워드"], ["증거"], object())
        print(f"\n동일 벡터 score={score}")
        assert score == pytest.approx(100.0, abs=0.5)

    def test_직교_벡터_0점(self):
        """키워드와 증거가 직교 → 유사도 0.0 → 0점"""
        kw_vec = [1.0, 0.0]
        ev_vec = [0.0, 1.0]
        with patch("apps.analysis.services.match_service.get_embeddings", return_value=[kw_vec, ev_vec]):
            score, details = _calc_trait_score(["키워드"], ["증거"], object())
        print(f"\n직교 벡터 score={score}")
        assert score == pytest.approx(0.0, abs=0.5)

    def test_다중_인재상_평균(self):
        """인재상 2개: 첫 번째 유사도 1.0, 두 번째 유사도 0.0 → 평균 50점"""
        # 벡터 순서: [kw1_vec, kw2_vec, ev_vec]
        kw1 = [1.0, 0.0]
        kw2 = [0.0, 1.0]
        ev  = [1.0, 0.0]  # kw1과 동일, kw2와 직교
        with patch("apps.analysis.services.match_service.get_embeddings", return_value=[kw1, kw2, ev]):
            score, details = _calc_trait_score(["인재상1", "인재상2"], ["증거"], object())
        print(f"\n다중 인재상 score={score} details={details}")
        assert score == pytest.approx(50.0, abs=1.0)

    def test_max_pooling_최고유사도_채택(self):
        """증거 여러 개 중 가장 높은 유사도를 채택 (Max Pooling)"""
        kw_vec  = [1.0, 0.0, 0.0]
        ev1_vec = [1.0, 0.0, 0.0]   # 유사도 1.0 (최고)
        ev2_vec = [0.0, 1.0, 0.0]   # 유사도 0.0
        ev3_vec = [0.0, 0.0, 1.0]   # 유사도 0.0
        with patch("apps.analysis.services.match_service.get_embeddings", return_value=[kw_vec, ev1_vec, ev2_vec, ev3_vec]):
            score, details = _calc_trait_score(["인재상"], ["증거1", "증거2", "증거3"], object())
        print(f"\nMax Pooling score={score} best_match={details[0]['best_match']}")
        assert score == pytest.approx(100.0, abs=0.5)
        assert details[0]["best_match"] == "증거1"

    def test_반환_형식(self):
        """trait_details 각 항목에 trait / best_match / similarity 키 존재"""
        kw_vec = [1.0, 0.0]
        ev_vec = [1.0, 0.0]
        with patch("apps.analysis.services.match_service.get_embeddings", return_value=[kw_vec, ev_vec]):
            score, details = _calc_trait_score(["인재상1"], ["증거1"], object())
        assert len(details) == 1
        assert "trait"      in details[0]
        assert "best_match" in details[0]
        assert "similarity" in details[0]


# ══════════════════════════════════════════════════════════════
# calculate_match_score (실제 GPT + 임베딩 호출)
# ══════════════════════════════════════════════════════════════

class TestCalculateMatchScore:

    JD_KEYWORDS = {
        "tech_keywords":  ["Python", "Django", "Redis", "PostgreSQL"],
        "trait_keywords": ["주도적으로 문제를 해결하는 분", "데이터 기반으로 의사결정하는 분"],
    }

    RESUME_BACKEND = {
        "tech_stack":      ["Python", "Django", "PostgreSQL", "Redis", "Docker"],
        "key_experiences": ["스타트업에서 백엔드 API 20개 설계", "Redis 캐싱으로 응답 속도 40% 개선"],
        "strengths":       ["성능 최적화 경험"],
        "trait_evidence":  ["데이터를 근거로 팀 의사결정을 이끈 경험"],
        "projects": [
            {"name": "배달플랫폼", "role": "백엔드 리드", "tech": ["Python", "Django", "Redis"], "result": "DAU 3천", "domain": "logistics"},
        ],
        "years_of_experience": 2,
        "education":           "대졸",
        "career_level":        "experienced",
    }

    RESUME_ENTRY = {
        "tech_stack":      ["Python", "Django"],
        "key_experiences": ["팀 프로젝트에서 REST API 5개 설계"],
        "strengths":       ["빠른 학습력"],
        "trait_evidence":  ["JWT 토큰 오류를 3일 동안 탐색해 해결"],
        "projects": [
            {"name": "중고거래앱", "role": "백엔드 개발", "tech": ["Python", "Django"], "result": "팀 프로젝트 완성", "domain": "e-commerce"},
        ],
        "years_of_experience": 0,
        "education":           "대졸",
        "career_level":        "entry",
    }

    def _assert_structure(self, result: dict):
        required = {"match_score", "tech_score", "trait_score", "rule_score",
                    "matched_keywords", "unmatched_keywords", "trait_details",
                    "rule_detail", "strengths", "weaknesses", "cl_points"}
        missing = required - set(result.keys())
        assert not missing, f"필드 누락: {missing}"

    def _assert_score_range(self, result: dict):
        for key in ["match_score", "tech_score", "trait_score", "rule_score"]:
            assert 0.0 <= result[key] <= 100.0, f"{key}={result[key]} 범위 초과"

    def test_기본_구조_경력자(self):
        result = calculate_match_score(
            jd_keywords=self.JD_KEYWORDS,
            resume_analysis=self.RESUME_BACKEND,
            career_level="experienced",
        )
        print(f"\n[경력 매칭] {result}")
        self._assert_structure(result)
        self._assert_score_range(result)

    def test_기본_구조_신입(self):
        result = calculate_match_score(
            jd_keywords=self.JD_KEYWORDS,
            resume_analysis=self.RESUME_ENTRY,
            career_level="entry",
        )
        print(f"\n[신입 매칭] match_score={result['match_score']}")
        self._assert_structure(result)
        self._assert_score_range(result)

    def test_tech_score_100_when_perfect_match(self):
        """JD 기술 키워드를 이력서가 모두 보유하면 tech_score=100"""
        jd = {"tech_keywords": ["Python", "Django"], "trait_keywords": []}
        resume = dict(self.RESUME_BACKEND, tech_stack=["Python", "Django"])
        result = calculate_match_score(jd, resume, career_level="entry")
        print(f"\n완전 기술 매칭 tech_score={result['tech_score']}")
        assert result["tech_score"] == 100.0

    def test_tech_score_0_when_no_match(self):
        """JD 기술 키워드가 이력서에 전혀 없으면 tech_score=0"""
        jd = {"tech_keywords": ["Java", "Spring Boot", "Kafka"], "trait_keywords": []}
        resume = dict(self.RESUME_ENTRY, tech_stack=["Python", "Django"])
        result = calculate_match_score(jd, resume, career_level="entry")
        print(f"\n기술 불일치 tech_score={result['tech_score']}")
        assert result["tech_score"] == 0.0

    def test_matched_unmatched_일관성(self):
        """matched + unmatched = JD 기술 키워드 수"""
        result = calculate_match_score(
            jd_keywords=self.JD_KEYWORDS,
            resume_analysis=self.RESUME_BACKEND,
            career_level="experienced",
        )
        jd_count = len({k.lower() for k in self.JD_KEYWORDS["tech_keywords"]})
        total = len(result["matched_keywords"]) + len(result["unmatched_keywords"])
        print(f"\njd={jd_count} matched={len(result['matched_keywords'])} unmatched={len(result['unmatched_keywords'])}")
        assert total == jd_count

    def test_strengths_weaknesses_반환(self):
        """LLM이 strengths와 weaknesses를 반환해야 함"""
        result = calculate_match_score(
            jd_keywords=self.JD_KEYWORDS,
            resume_analysis=self.RESUME_BACKEND,
            career_level="experienced",
        )
        print(f"\n강점: {result['strengths']}")
        print(f"약점: {result['weaknesses']}")
        assert isinstance(result["strengths"],  list)
        assert isinstance(result["weaknesses"], list)
        assert isinstance(result["cl_points"],  list)

    def test_jd_requirements_있을때_rule_score_반영(self):
        """jd_requirements 전달 시 rule_score가 0이 아니어야 함"""
        jd_req = {
            "min_years":      0,
            "education":      "대졸",
            "job_type":       "백엔드",
            "required_tech":  ["Python"],
            "preferred_tech": [],
        }
        result = calculate_match_score(
            jd_keywords=self.JD_KEYWORDS,
            resume_analysis=self.RESUME_BACKEND,
            career_level="experienced",
            jd_requirements=jd_req,
            job_role="백엔드 개발자",
        )
        print(f"\nrule_score={result['rule_score']} rule_detail={result['rule_detail']}")
        assert result["rule_score"] > 0.0, "jd_requirements 전달 시 rule_score가 0이면 안 됨"

    def test_경력자_신입보다_높은_기술점수_가중치(self):
        """동일 조건에서 경력자는 기술 점수 가중치가 신입보다 높아야 함"""
        entry_w = CAREER_WEIGHTS["entry"]["tech_w"]
        exp_w   = CAREER_WEIGHTS["experienced"]["tech_w"]
        assert exp_w > entry_w, "경력자의 tech_w가 신입보다 커야 함"
