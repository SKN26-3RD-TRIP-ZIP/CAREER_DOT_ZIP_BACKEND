"""
analysis views 단위 테스트 (DB 없음 — 전체 ORM Mock 처리)

테스트 대상:
  POST /api/v1/analysis/analyze/   → AnalysisStartView
  POST /api/v1/analysis/status/    → AnalysisStatusView
  POST /api/v1/analysis/match/     → AnalysisMatchView

DB 연결 없이 ORM을 모두 Mock으로 대체합니다.
리턴 데이터 구조·값·엣지케이스 검증에 집중합니다.

실행:
  pytest apps/analysis/tests/test_views.py -v -s
  pytest apps/analysis/tests/test_views.py -v -s -k "start"
  pytest apps/analysis/tests/test_views.py -v -s -k "status"
  pytest apps/analysis/tests/test_views.py -v -s -k "match"
"""

import uuid
import pprint
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework.test import APIClient


# ══════════════════════════════════════════════════════════════
# Mock 데이터
# ══════════════════════════════════════════════════════════════

MOCK_USER_ID    = 1
MOCK_SESSION_ID = 42
MOCK_JD_ID      = str(uuid.uuid4())
MOCK_RESUME_ID  = str(uuid.uuid4())
MOCK_CL_ID      = str(uuid.uuid4())
MOCK_ANALYSIS_ID = str(uuid.uuid4())

MOCK_JD_KEYWORDS = {
    "tech_keywords":  ["Python", "Django", "PostgreSQL", "Redis", "Docker"],
    "trait_keywords": ["주도적으로 문제를 해결하는 분", "데이터 기반으로 의사결정하는 분"],
    "requirements": {
        "min_years":      2,
        "education":      "대졸",
        "job_type":       "백엔드",
        "required_tech":  ["Python", "Django"],
        "preferred_tech": ["Redis", "Docker"],
    },
}

MOCK_RESUME_ANALYSIS = {
    "tech_stack":          ["Python", "Django", "PostgreSQL", "Redis"],
    "key_experiences":     ["스타트업에서 백엔드 API 20개 설계 및 운영"],
    "strengths":           ["데이터 기반 의사결정 (A/B 테스트 경험 보유)"],
    "trait_evidence":      ["데이터를 근거로 팀 의사결정을 이끈 경험"],
    "projects": [
        {
            "name":   "배달플랫폼",
            "role":   "백엔드 리드",
            "tech":   ["Python", "Django"],
            "result": "DAU 3천 달성",
            "domain": "logistics",
        }
    ],
    "years_of_experience": 2,
    "education":           "대졸",
    "career_level":        "experienced",
    "gap": {
        "tech_gap":  ["Docker"],
        "year_gap":  0,
        "edu_gap":   False,
        "trait_gap": [],
    },
    "gap_message": {
        "summary":   "전반적으로 적합한 지원자입니다.",
        "tech":      "Docker 경험이 부족합니다.",
        "year":      "",
        "education": "",
        "trait":     "",
    },
}

MOCK_STRENGTHS  = ["Django 실무 경험", "REST API 설계 능력"]
MOCK_WEAKNESSES = ["Docker 경험 부족"]
MOCK_CL_POINTS  = ["배달 플랫폼 API 성능 개선 경험 강조"]

MOCK_QUESTIONS = [
    {
        "id":            str(uuid.uuid4()),
        "question_type": "personality",
        "question_text": "팀 내 갈등이 생겼을 때 어떻게 해결하시나요?",
        "answer": {
            "summary":   "갈등은 대화로 해결합니다.",
            "situation": "팀 프로젝트 중 의견 충돌",
            "task":      "조율 역할 수행",
            "action":    "1:1 면담 및 공통 목표 재확인",
            "result":    "합의 도출 및 일정 준수",
        },
        "order": 0,
    },
    {
        "id":            str(uuid.uuid4()),
        "question_type": "technical",
        "question_text": "Django ORM의 N+1 문제를 어떻게 해결하나요?",
        "answer": {
            "summary":   "select_related / prefetch_related를 사용합니다.",
            "situation": "배달 플랫폼 주문 조회 API에서 N+1 발생",
            "task":      "쿼리 최적화",
            "action":    "select_related 적용 + 쿼리 수 모니터링",
            "result":    "쿼리 수 20개 → 2개로 감소",
        },
        "order": 1,
    },
    {
        "id":            str(uuid.uuid4()),
        "question_type": "experience",
        "question_text": "백엔드 API 설계 경험을 구체적으로 말씀해주세요.",
        "answer": {
            "summary":   "스타트업에서 20개 API를 설계했습니다.",
            "situation": "배달 플랫폼 MVP 개발",
            "task":      "백엔드 API 전담",
            "action":    "DRF 기반 RESTful API 설계, 문서화",
            "result":    "서비스 출시 및 DAU 3천 달성",
        },
        "order": 2,
    },
]


# ══════════════════════════════════════════════════════════════
# Mock 객체 팩토리
# ══════════════════════════════════════════════════════════════

def _mock_user():
    user = MagicMock()
    user.id            = MOCK_USER_ID
    user.is_authenticated = True
    user.pk            = MOCK_USER_ID
    return user


def _mock_session(status="analyzing", jd_keywords=None):
    session = MagicMock()
    session.id           = MOCK_SESSION_ID
    session.status       = status
    session.jd_keywords  = jd_keywords or {}
    session.career_level = "experienced"
    session.jd_analysis_id = MOCK_ANALYSIS_ID
    return session


def _mock_jd_analysis():
    jd_analysis = MagicMock()
    jd_analysis.id                = uuid.UUID(MOCK_ANALYSIS_ID)
    jd_analysis.match_score       = 82.5
    jd_analysis.tech_score        = 78.0
    jd_analysis.trait_score       = 85.0
    jd_analysis.matched_keywords  = ["Python", "Django", "PostgreSQL", "Redis"]
    jd_analysis.unmatched_keywords = ["Docker"]
    jd_analysis.jd_keywords       = MOCK_JD_KEYWORDS
    jd_analysis.resume_analysis   = MOCK_RESUME_ANALYSIS
    jd_analysis.strengths         = MOCK_STRENGTHS
    jd_analysis.weaknesses        = MOCK_WEAKNESSES
    jd_analysis.cl_points         = MOCK_CL_POINTS
    jd_analysis.questions.values.return_value = MOCK_QUESTIONS
    return jd_analysis


# ══════════════════════════════════════════════════════════════
# POST /api/v1/analysis/analyze/
# ══════════════════════════════════════════════════════════════

@patch("apps.analysis.views.threading.Thread")
@patch("apps.analysis.views.AnalysisSession.objects.create")
class TestAnalysisStartView(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()
        self.user   = _mock_user()
        self.client.force_authenticate(user=self.user)
        self.url  = reverse("analysis-analyze")
        self.jd = MagicMock()
        self.jd.id = MOCK_JD_ID
        self.jd.position = "백엔드 개발자"
        self.jd.company_name = "커리어닷집"
        self.jd.original_text = "Python, Django 기반 백엔드 개발자 채용"
        self.resume = MagicMock()
        self.resume.id = MOCK_RESUME_ID
        self.resume.original_text = "Python Django 2년 경력"
        self.jd_get_patcher = patch("apps.analysis.views.JobDescription.objects.get")
        self.resume_get_patcher = patch("apps.analysis.views.ResumeMaster.objects.get")
        self.mock_jd_get = self.jd_get_patcher.start()
        self.mock_resume_get = self.resume_get_patcher.start()
        self.mock_jd_get.return_value = self.jd
        self.mock_resume_get.return_value = self.resume
        self.addCleanup(self.jd_get_patcher.stop)
        self.addCleanup(self.resume_get_patcher.stop)
        self.body = {
            "jd_id":             MOCK_JD_ID,
            "resume_id":         MOCK_RESUME_ID,
            "job_role":          "백엔드 개발자",
            "company_name":      "커리어닷집",
            "jd_text":           "Python, Django 기반 백엔드 개발자 채용",
            "resume_text":       "Python Django 2년 경력",
            "cover_letter_text": "저는 문제 해결을 좋아하는 개발자입니다.",
            "career_level":      "experienced",
        }

    def test_정상요청_201_반환(self, mock_create, mock_thread):
        mock_create.return_value = _mock_session()
        res = self.client.post(self.url, self.body, format="json")

        print("\n[analyze] REQUEST :")
        pprint.pprint(self.body)
        print("[analyze] RESPONSE:")
        pprint.pprint(res.data)

        self.assertEqual(res.status_code, 201)

    def test_리턴_필드_session_id_status(self, mock_create, mock_thread):
        mock_create.return_value = _mock_session()
        res = self.client.post(self.url, self.body, format="json")

        print("\n[analyze] 리턴 필드:", list(res.data.keys()))

        self.assertIn("session_id", res.data)
        self.assertIn("status",     res.data)
        self.assertEqual(res.data["session_id"], MOCK_SESSION_ID)
        self.assertEqual(res.data["status"],     "analyzing")

    def test_리턴_session_id_타입_int(self, mock_create, mock_thread):
        mock_create.return_value = _mock_session()
        res = self.client.post(self.url, self.body, format="json")

        self.assertIsInstance(res.data["session_id"], int)

    def test_career_level_기본값_entry(self, mock_create, mock_thread):
        """career_level 미전송 시 기본값 entry로 create 호출되어야 함"""
        mock_create.return_value = _mock_session()
        body = {"jd_id": MOCK_JD_ID, "resume_id": MOCK_RESUME_ID}
        self.client.post(self.url, body, format="json")

        _, kwargs = mock_create.call_args
        print(f"\n[analyze] create 호출 kwargs: {kwargs}")
        self.assertEqual(kwargs.get("career_level"), "entry")

    def test_create_호출시_전달값_검증(self, mock_create, mock_thread):
        mock_create.return_value = _mock_session()
        self.client.post(self.url, self.body, format="json")

        _, kwargs = mock_create.call_args
        print(f"\n[analyze] create kwargs:")
        pprint.pprint(kwargs)

        self.assertEqual(kwargs["job_role"],          "백엔드 개발자")
        self.assertEqual(kwargs["company_name"],      "커리어닷집")
        self.assertEqual(kwargs["jd_id"],             MOCK_JD_ID)
        self.assertEqual(kwargs["resume_id"],         MOCK_RESUME_ID)
        self.assertIsNone(kwargs["cover_letter_id"])
        self.assertEqual(kwargs["career_level"],      "experienced")
        self.assertEqual(kwargs["status"],            "analyzing")

    def test_백그라운드_스레드_실행(self, mock_create, mock_thread):
        mock_create.return_value = _mock_session()
        self.client.post(self.url, self.body, format="json")

        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
        print("\n[analyze] 백그라운드 스레드 실행 확인")

    def test_미인증_401(self, mock_create, mock_thread):
        res = APIClient().post(self.url, {}, format="json")

        print(f"\n[analyze] 미인증 응답: {res.status_code}")
        self.assertEqual(res.status_code, 401)


# ══════════════════════════════════════════════════════════════
# POST /api/v1/analysis/status/
# ══════════════════════════════════════════════════════════════

@patch("apps.analysis.views.AnalysisSession.objects.get")
class TestAnalysisStatusView(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()
        self.user   = _mock_user()
        self.client.force_authenticate(user=self.user)
        self.url    = reverse("analysis-status")

    def test_analyzing_상태_리턴(self, mock_get):
        mock_get.return_value = _mock_session(status="analyzing")
        res = self.client.post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        print("\n[status - analyzing] RESPONSE:")
        pprint.pprint(res.data)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"],      "analyzing")
        self.assertEqual(res.data["jd_keywords"], [])  # 분석 중에는 빈 배열

    def test_ready_상태_jd_keywords_포함(self, mock_get):
        mock_get.return_value = _mock_session(status="ready", jd_keywords=MOCK_JD_KEYWORDS)
        res = self.client.post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        print("\n[status - ready] RESPONSE:")
        pprint.pprint(res.data)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"],      "ready")
        self.assertEqual(res.data["jd_keywords"], MOCK_JD_KEYWORDS)

    def test_failed_상태_리턴(self, mock_get):
        mock_get.return_value = _mock_session(status="failed")
        res = self.client.post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        print("\n[status - failed] RESPONSE:")
        pprint.pprint(res.data)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "failed")

    def test_pending_상태_jd_keywords_빈배열(self, mock_get):
        mock_get.return_value = _mock_session(status="pending")
        res = self.client.post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        self.assertEqual(res.data["jd_keywords"], [])

    def test_리턴_필드_구조(self, mock_get):
        mock_get.return_value = _mock_session(status="ready", jd_keywords=MOCK_JD_KEYWORDS)
        res = self.client.post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        print("\n[status] 리턴 필드:", list(res.data.keys()))
        self.assertIn("status",      res.data)
        self.assertIn("jd_keywords", res.data)

    def test_세션_없을때_404(self, mock_get):
        from apps.analysis.models import AnalysisSession
        mock_get.side_effect = AnalysisSession.DoesNotExist
        res = self.client.post(self.url, {"session_id": 99999}, format="json")

        print(f"\n[status - 없는세션] 응답: {res.status_code} / {res.data}")
        self.assertEqual(res.status_code, 404)
        self.assertIn("error", res.data)

    def test_미인증_401(self, mock_get):
        res = APIClient().post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        self.assertEqual(res.status_code, 401)


# ══════════════════════════════════════════════════════════════
# POST /api/v1/analysis/match/
# ══════════════════════════════════════════════════════════════

@patch("apps.analysis.views.JdAnalysis.objects.get")
@patch("apps.analysis.views.AnalysisSession.objects.get")
class TestAnalysisMatchView(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()
        self.user   = _mock_user()
        self.client.force_authenticate(user=self.user)
        self.url    = reverse("analysis-match")

    def test_정상요청_200_반환(self, mock_session_get, mock_jd_get):
        mock_session_get.return_value = _mock_session(status="ready")
        mock_jd_get.return_value      = _mock_jd_analysis()
        res = self.client.post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        print("\n[match] RESPONSE:")
        pprint.pprint(dict(res.data))

        self.assertEqual(res.status_code, 200)

    def test_리턴_필드_전체_구조(self, mock_session_get, mock_jd_get):
        mock_session_get.return_value = _mock_session(status="ready")
        mock_jd_get.return_value      = _mock_jd_analysis()
        res = self.client.post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        expected_keys = [
            "jd_analysis_id", "match_score", "tech_score", "trait_score",
            "matched_keywords", "unmatched_keywords",
            "jd_keywords", "resume_analysis",
            "gap", "gap_message",
            "strengths", "weaknesses", "cl_points",
            "questions",
        ]
        print("\n[match] 리턴 필드:", list(res.data.keys()))
        for key in expected_keys:
            self.assertIn(key, res.data, msg=f"'{key}' 필드가 응답에 없음")

    def test_점수_값_검증(self, mock_session_get, mock_jd_get):
        mock_session_get.return_value = _mock_session(status="ready")
        mock_jd_get.return_value      = _mock_jd_analysis()
        res = self.client.post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        print(f"\n[match] match_score={res.data['match_score']}"
              f"  tech_score={res.data['tech_score']}"
              f"  trait_score={res.data['trait_score']}")

        self.assertEqual(res.data["match_score"], 82.5)
        self.assertEqual(res.data["tech_score"],  78.0)
        self.assertEqual(res.data["trait_score"], 85.0)

    def test_jd_analysis_id_uuid_형식(self, mock_session_get, mock_jd_get):
        mock_session_get.return_value = _mock_session(status="ready")
        mock_jd_get.return_value      = _mock_jd_analysis()
        res = self.client.post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        jd_id = res.data["jd_analysis_id"]
        print(f"\n[match] jd_analysis_id: {jd_id}")
        try:
            uuid.UUID(jd_id)
        except ValueError:
            self.fail(f"jd_analysis_id가 UUID 형식이 아님: {jd_id}")

    def test_keywords_검증(self, mock_session_get, mock_jd_get):
        mock_session_get.return_value = _mock_session(status="ready")
        mock_jd_get.return_value      = _mock_jd_analysis()
        res = self.client.post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        print(f"\n[match] matched={res.data['matched_keywords']}"
              f"  unmatched={res.data['unmatched_keywords']}")

        self.assertEqual(res.data["matched_keywords"],   ["Python", "Django", "PostgreSQL", "Redis"])
        self.assertEqual(res.data["unmatched_keywords"], ["Docker"])

    def test_strengths_weaknesses_cl_points_검증(self, mock_session_get, mock_jd_get):
        mock_session_get.return_value = _mock_session(status="ready")
        mock_jd_get.return_value      = _mock_jd_analysis()
        res = self.client.post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        print(f"\n[match] strengths:  {res.data['strengths']}")
        print(f"[match] weaknesses: {res.data['weaknesses']}")
        print(f"[match] cl_points:  {res.data['cl_points']}")

        self.assertEqual(res.data["strengths"],  MOCK_STRENGTHS)
        self.assertEqual(res.data["weaknesses"], MOCK_WEAKNESSES)
        self.assertEqual(res.data["cl_points"],  MOCK_CL_POINTS)

    def test_gap_gap_message_포함(self, mock_session_get, mock_jd_get):
        mock_session_get.return_value = _mock_session(status="ready")
        mock_jd_get.return_value      = _mock_jd_analysis()
        res = self.client.post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        print(f"\n[match] gap:         {res.data['gap']}")
        print(f"[match] gap_message: {res.data['gap_message']}")

        self.assertIsInstance(res.data["gap"],         dict)
        self.assertIsInstance(res.data["gap_message"], dict)
        self.assertIn("tech_gap",  res.data["gap"])
        self.assertIn("summary",   res.data["gap_message"])

    def test_questions_개수_및_구조(self, mock_session_get, mock_jd_get):
        mock_session_get.return_value = _mock_session(status="ready")
        mock_jd_get.return_value      = _mock_jd_analysis()
        res = self.client.post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        questions = res.data["questions"]
        print(f"\n[match] 질문 {len(questions)}개:")
        for q in questions:
            print(f"  [{q['question_type']:12}] {q['question_text'][:50]}")

        self.assertEqual(len(questions), 3)
        for q in questions:
            self.assertIn("id",            q)
            self.assertIn("question_type", q)
            self.assertIn("question_text", q)
            self.assertIn("answer",        q)
            self.assertIn("order",         q)

    def test_questions_answer_STAR_구조(self, mock_session_get, mock_jd_get):
        mock_session_get.return_value = _mock_session(status="ready")
        mock_jd_get.return_value      = _mock_jd_analysis()
        res = self.client.post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        star_keys = {"summary", "situation", "task", "action", "result"}
        for q in res.data["questions"]:
            missing = star_keys - set(q["answer"].keys())
            self.assertFalse(missing,
                             f"STAR 필드 누락: {missing} — {q['question_text'][:30]}")
        print("\n[match] 모든 질문 STAR 구조 확인")

    def test_questions_타입별_분포(self, mock_session_get, mock_jd_get):
        mock_session_get.return_value = _mock_session(status="ready")
        mock_jd_get.return_value      = _mock_jd_analysis()
        res = self.client.post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        types = [q["question_type"] for q in res.data["questions"]]
        dist  = {t: types.count(t) for t in set(types)}
        print(f"\n[match] 질문 타입 분포: {dist}")

        self.assertIn("personality", types)
        self.assertIn("technical",   types)
        self.assertIn("experience",  types)

    def test_questions_순서_정렬(self, mock_session_get, mock_jd_get):
        mock_session_get.return_value = _mock_session(status="ready")
        mock_jd_get.return_value      = _mock_jd_analysis()
        res = self.client.post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        orders = [q["order"] for q in res.data["questions"]]
        print(f"\n[match] 질문 순서: {orders}")
        self.assertEqual(orders, sorted(orders))

    def test_분석미완료_세션_400(self, mock_session_get, mock_jd_get):
        mock_session_get.return_value = _mock_session(status="analyzing")
        res = self.client.post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        print(f"\n[match - 미완료] RESPONSE: {res.data}")
        self.assertEqual(res.status_code, 400)
        self.assertIn("error",  res.data)
        self.assertIn("status", res.data)
        self.assertEqual(res.data["status"], "analyzing")

    def test_failed_세션_400(self, mock_session_get, mock_jd_get):
        mock_session_get.return_value = _mock_session(status="failed")
        res = self.client.post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        print(f"\n[match - failed] RESPONSE: {res.data}")
        self.assertEqual(res.status_code, 400)

    def test_세션_없을때_404(self, mock_session_get, mock_jd_get):
        from apps.analysis.models import AnalysisSession
        mock_session_get.side_effect = AnalysisSession.DoesNotExist
        res = self.client.post(self.url, {"session_id": 99999}, format="json")

        print(f"\n[match - 없는세션] 응답: {res.status_code} / {res.data}")
        self.assertEqual(res.status_code, 404)

    def test_미인증_401(self, mock_session_get, mock_jd_get):
        res = APIClient().post(self.url, {"session_id": MOCK_SESSION_ID}, format="json")

        self.assertEqual(res.status_code, 401)
