"""
gap_service 단위 테스트

테스트 대상:
  calculate_gap()      갭 항목 계산
  build_gap_message()  신입/경력 분기 메시지 생성

실행:
  pytest apps/analysis/tests/test_gap_service.py -v -s
"""

import unittest
try:
    import pytest
except ModuleNotFoundError:
    raise unittest.SkipTest("pytest is required for this pytest-style analysis test module")
from apps.analysis.services.gap_service import calculate_gap, build_gap_message


# ══════════════════════════════════════════════════════════════
# calculate_gap
# ══════════════════════════════════════════════════════════════

class TestCalculateGap:

    def test_no_gap(self, jd_req_entry, resume_entry):
        """갭이 없는 이상적인 케이스"""
        gap = calculate_gap(
            jd_keywords={},
            jd_requirements=jd_req_entry,
            resume_analysis=resume_entry,
            unmatched_keywords=[],
        )
        print(f"\n갭 없음: {gap}")
        assert gap["years_gap"]     == 0
        assert gap["education_ok"]  == True
        assert gap["missing_required_tech"] == []
        assert gap["missing_preferred_tech"] == []

    def test_years_gap(self, jd_req_mid, resume_entry):
        """연차 갭 계산 (3년 요구, 0년 보유 → 갭 3)"""
        gap = calculate_gap(
            jd_keywords={},
            jd_requirements=jd_req_mid,
            resume_analysis=resume_entry,
            unmatched_keywords=[],
        )
        print(f"\n연차 갭: required={gap['required_years']} current={gap['current_years']} gap={gap['years_gap']}")
        assert gap["years_gap"]      == 3.0
        assert gap["required_years"] == 3
        assert gap["current_years"]  == 0

    def test_education_gap(self, resume_entry):
        """학력 미충족 케이스"""
        jd_req = {"min_years": 0, "education": "석사이상", "job_type": "", "required_tech": [], "preferred_tech": []}
        gap = calculate_gap(
            jd_keywords={},
            jd_requirements=jd_req,
            resume_analysis=resume_entry,  # 대졸
            unmatched_keywords=[],
        )
        print(f"\n학력 갭: education_ok={gap['education_ok']}")
        assert gap["education_ok"] == False

    @pytest.mark.parametrize("req_edu, cur_edu, expected_ok", [
        ("무관",    "고졸",    True),
        ("대졸",    "대졸",    True),
        ("대졸",    "석사이상", True),
        ("석사이상","대졸",    False),
        ("석사이상","고졸",    False),
    ])
    def test_education_matrix(self, req_edu, cur_edu, expected_ok):
        jd_req = {"min_years": 0, "education": req_edu, "job_type": "", "required_tech": [], "preferred_tech": []}
        resume = {"years_of_experience": 0, "education": cur_edu}
        gap = calculate_gap(jd_keywords={}, jd_requirements=jd_req, resume_analysis=resume, unmatched_keywords=[])
        print(f"\n학력: 요구={req_edu} 보유={cur_edu} ok={gap['education_ok']}")
        assert gap["education_ok"] == expected_ok

    def test_missing_required_tech(self, jd_req_mid, resume_entry):
        """필수 기술 갭 — required_tech와 unmatched 교집합"""
        unmatched = ["redis", "docker", "kubernetes"]
        gap = calculate_gap(
            jd_keywords={},
            jd_requirements=jd_req_mid,  # required_tech: [Python, Django, Redis, Docker]
            resume_analysis=resume_entry,
            unmatched_keywords=unmatched,
        )
        print(f"\n필수 기술 갭: {gap['missing_required_tech']}")
        # Redis, Docker가 required이고 unmatched에 있으므로 포함되어야 함
        assert "redis" in gap["missing_required_tech"]
        assert "docker" in gap["missing_required_tech"]
        # Kubernetes는 preferred이므로 missing_preferred에 있어야 함
        assert "kubernetes" in gap["missing_preferred_tech"]

    def test_weak_traits_threshold(self, jd_req_entry, resume_entry, trait_details_mixed):
        """유사도 0.5 미만만 weak_traits에 포함"""
        gap = calculate_gap(
            jd_keywords={},
            jd_requirements=jd_req_entry,
            resume_analysis=resume_entry,
            unmatched_keywords=[],
            trait_details=trait_details_mixed,
        )
        print(f"\nweak_traits: {gap['weak_traits']}")
        sims = [t["similarity"] for t in gap["weak_traits"]]
        assert all(s < 0.5 for s in sims), "0.5 이상이 포함됨"

    def test_no_weak_traits_when_high(self, jd_req_entry, resume_entry, trait_details_high):
        """모든 유사도가 0.5 이상이면 weak_traits 비어야 함"""
        gap = calculate_gap(
            jd_keywords={},
            jd_requirements=jd_req_entry,
            resume_analysis=resume_entry,
            unmatched_keywords=[],
            trait_details=trait_details_high,
        )
        print(f"\nweak_traits (high): {gap['weak_traits']}")
        assert gap["weak_traits"] == []

    def test_all_gaps(self, jd_req_senior, resume_entry, trait_details_low):
        """최악의 케이스 — 모든 갭 존재"""
        unmatched = ["kubernetes", "kafka", "terraform"]
        gap = calculate_gap(
            jd_keywords={},
            jd_requirements=jd_req_senior,
            resume_analysis=resume_entry,   # 0년, 대졸
            unmatched_keywords=unmatched,
            trait_details=trait_details_low,
        )
        print(f"\n전체 갭 요약: years_gap={gap['years_gap']} edu_ok={gap['education_ok']} "
              f"missing_req={gap['missing_required_tech']} weak={len(gap['weak_traits'])}개")
        assert gap["years_gap"]     > 0
        assert gap["education_ok"]  == False
        assert len(gap["missing_required_tech"]) > 0
        assert len(gap["weak_traits"]) > 0

    def test_years_gap_negative_means_surplus(self):
        """years_gap 음수 = 초과 충족"""
        jd_req = {"min_years": 2, "education": "무관", "job_type": "", "required_tech": [], "preferred_tech": []}
        resume = {"years_of_experience": 5, "education": "대졸"}
        gap = calculate_gap(jd_keywords={}, jd_requirements=jd_req, resume_analysis=resume, unmatched_keywords=[])
        print(f"\n초과 충족: years_gap={gap['years_gap']}")
        assert gap["years_gap"] < 0


# ══════════════════════════════════════════════════════════════
# build_gap_message
# ══════════════════════════════════════════════════════════════

class TestBuildGapMessage:

    def test_entry_tone_keywords(self):
        """신입 메시지는 '준비' 키워드를 포함해야 한다"""
        gap = {
            "missing_required_tech":  ["Kubernetes"],
            "missing_preferred_tech": [],
            "years_gap":              0,
            "required_years":         0,
            "current_years":          0,
            "education_ok":           True,
            "weak_traits":            [],
        }
        msg = build_gap_message(gap, "entry")
        print(f"\n신입 tech_gaps: {msg['tech_gaps']}")
        assert any("준비" in t or "학습" in t for t in msg["tech_gaps"])

    def test_experienced_tone_keywords(self):
        """경력 메시지는 '부족' 또는 '실무' 키워드를 포함해야 한다"""
        gap = {
            "missing_required_tech":  ["Kubernetes"],
            "missing_preferred_tech": [],
            "years_gap":              2,
            "required_years":         5,
            "current_years":          3,
            "education_ok":           True,
            "weak_traits":            [],
        }
        msg = build_gap_message(gap, "experienced")
        print(f"\n경력 career_gap: {msg['career_gap']}")
        assert msg["career_gap"] is not None
        assert "부족" in msg["career_gap"] or "갭" in msg["career_gap"]

    @pytest.mark.parametrize("career_level", ["entry", "experienced"])
    def test_message_structure(self, career_level):
        """반환 딕셔너리 키 5개 모두 존재"""
        gap = {
            "missing_required_tech":  [],
            "missing_preferred_tech": [],
            "years_gap":              0,
            "required_years":         0,
            "current_years":          0,
            "education_ok":           True,
            "weak_traits":            [],
        }
        msg = build_gap_message(gap, career_level)
        required_keys = {"summary", "tech_gaps", "career_gap", "trait_gaps", "action_items"}
        print(f"\n[{career_level}] keys={set(msg.keys())}")
        assert required_keys.issubset(set(msg.keys()))

    def test_no_gap_positive_summary(self):
        """갭이 없으면 긍정적인 summary"""
        gap = {
            "missing_required_tech":  [],
            "missing_preferred_tech": [],
            "years_gap":              0,
            "required_years":         0,
            "current_years":          0,
            "education_ok":           True,
            "weak_traits":            [],
        }
        msg = build_gap_message(gap, "entry")
        print(f"\n갭 없음 summary: {msg['summary']}")
        assert len(msg["summary"]) > 0
        assert msg["tech_gaps"] == []
        assert msg["trait_gaps"] == []

    def test_action_items_generated(self):
        """missing_required_tech 있으면 action_items 생성"""
        gap = {
            "missing_required_tech":  ["Kubernetes", "Kafka", "Terraform"],
            "missing_preferred_tech": [],
            "years_gap":              0,
            "required_years":         0,
            "current_years":          0,
            "education_ok":           True,
            "weak_traits":            [{"trait": "주도적 문제 해결", "similarity": 0.3}],
        }
        msg = build_gap_message(gap, "entry")
        print(f"\naction_items: {msg['action_items']}")
        assert len(msg["action_items"]) > 0

    def test_education_gap_in_career_gap(self):
        """학력 미충족이면 career_gap에 학력 언급"""
        gap = {
            "missing_required_tech":  [],
            "missing_preferred_tech": [],
            "years_gap":              0,
            "required_years":         0,
            "current_years":          0,
            "education_ok":           False,
            "weak_traits":            [],
        }
        msg = build_gap_message(gap, "experienced")
        print(f"\n학력 갭 career_gap: {msg['career_gap']}")
        assert msg["career_gap"] is not None
        assert "학력" in msg["career_gap"]

    @pytest.mark.parametrize("years_gap, career_level, should_have_career_gap", [
        (0,   "entry",      False),
        (0,   "experienced", False),
        (1,   "entry",      True),
        (2,   "experienced", True),
        (0.5, "experienced", True),
    ])
    def test_career_gap_presence(self, years_gap, career_level, should_have_career_gap):
        gap = {
            "missing_required_tech":  [],
            "missing_preferred_tech": [],
            "years_gap":              years_gap,
            "required_years":         years_gap,
            "current_years":          0,
            "education_ok":           True,
            "weak_traits":            [],
        }
        msg = build_gap_message(gap, career_level)
        print(f"\n[{career_level}] years_gap={years_gap} career_gap={msg['career_gap']}")
        if should_have_career_gap:
            assert msg["career_gap"] is not None
        else:
            assert msg["career_gap"] is None
