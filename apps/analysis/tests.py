"""
analysis API 흐름 테스트

전체 흐름:
  1. POST /api/v1/analysis/analyze/   → 분석 시작, session_id 반환
  2. POST /api/v1/analysis/status/    → 분석 상태 폴링
  3. POST /api/v1/analysis/match/     → 분석 결과 + 질문 목록 조회
"""
import pprint
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import AnalysisSession, GeneratedQuestion

User = get_user_model()


# ──────────────────────────────────────────────
# 테스트용 Mock 데이터 (GPT 호출 대체)
# ──────────────────────────────────────────────

MOCK_JD_KEYWORDS = ["Python", "Django", "REST API", "PostgreSQL"]

MOCK_RESUME_ANALYSIS = {
    "tech_stack": ["Python", "Django", "React"],
    "key_experiences": ["백엔드 API 설계 및 개발", "DB 모델링"],
    "strengths": ["문제 해결력", "커뮤니케이션"],
    "projects": [
        {"name": "커리어닷집", "role": "백엔드 개발", "result": "MVP 출시"}
    ],
}

MOCK_QUESTIONS = [
    {"type": "personality", "text": "팀 내 갈등이 생겼을 때 어떻게 해결하시나요?"},
    {"type": "personality", "text": "본인의 강점과 약점은 무엇인가요?"},
    {"type": "personality", "text": "왜 이 직무에 지원했나요?"},
    {"type": "technical",   "text": "Django ORM의 N+1 문제를 어떻게 해결하나요?"},
    {"type": "technical",   "text": "REST API 설계 시 고려하는 원칙은 무엇인가요?"},
    {"type": "technical",   "text": "PostgreSQL 인덱스를 어떻게 활용하나요?"},
    {"type": "technical",   "text": "Python에서 비동기 처리를 어떻게 구현하나요?"},
    {"type": "experience",  "text": "백엔드 API 설계 경험을 구체적으로 말씀해주세요."},
    {"type": "experience",  "text": "커리어닷집 프로젝트에서 가장 어려웠던 점은?"},
    {"type": "experience",  "text": "DB 모델링 과정에서 어떤 고민을 했나요?"},
]


# ──────────────────────────────────────────────
# 1단계: POST /api/v1/analysis/analyze/
# ──────────────────────────────────────────────

class AnalyzeAPITest(APITestCase):
    """
    [1단계] 분석 시작 API

    REQUEST:
        POST /api/v1/analysis/analyze/
        {
            "job_role":          "백엔드 개발자",
            "company_name":      "커리어닷집",
            "jd_text":           "Python, Django 기반 백엔드 개발자를 모집합니다.",
            "resume_text":       "Python, Django, React 경험 보유.",
            "cover_letter_text": "저는 문제 해결을 좋아하는 개발자입니다."
        }

    RESPONSE (201):
        {
            "session_id": 1,
            "status": "analyzing"
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="analyze@example.com",
            password="password123",
            name="테스트유저",
        )
        self.client.force_authenticate(self.user)
        self.url = reverse("analysis-analyze")

    @patch("apps.analysis.views.threading.Thread")
    def test_분석시작_요청시_session_id와_analyzing_상태_반환(self, mock_thread):
        request_body = {
            "job_role":          "백엔드 개발자",
            "company_name":      "커리어닷집",
            "jd_text":           "Python, Django 기반 백엔드 개발자를 모집합니다.",
            "resume_text":       "Python, Django, React 경험 보유.",
            "cover_letter_text": "저는 문제 해결을 좋아하는 개발자입니다.",
        }

        response = self.client.post(self.url, request_body, format="json")

        print("\n[analyze] REQUEST :", request_body)
        print("[analyze] RESPONSE:", response.data)

        # 응답 검증
        self.assertEqual(response.status_code, 201)
        self.assertIn("session_id", response.data)
        self.assertEqual(response.data["status"], "analyzing")

        # DB 저장 검증
        session = AnalysisSession.objects.get(id=response.data["session_id"])
        self.assertEqual(session.user,         self.user)
        self.assertEqual(session.job_role,     "백엔드 개발자")
        self.assertEqual(session.company_name, "커리어닷집")
        self.assertEqual(session.status,       "analyzing")

    @patch("apps.analysis.views.threading.Thread")
    def test_분석시작_백그라운드_스레드_실행_확인(self, mock_thread):
        request_body = {
            "job_role": "백엔드 개발자",
            "jd_text":  "Python Django 개발자 채용",
        }

        self.client.post(self.url, request_body, format="json")

        # 백그라운드 스레드가 실행됐는지 확인
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()

    def test_미인증_요청시_401_반환(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(self.url, {}, format="json")

        print("\n[analyze] 미인증 RESPONSE:", response.data)
        self.assertEqual(response.status_code, 401)


# ──────────────────────────────────────────────
# 2단계: POST /api/v1/analysis/status/
# ──────────────────────────────────────────────

class StatusAPITest(APITestCase):
    """
    [2단계] 분석 상태 폴링 API

    REQUEST:
        POST /api/v1/analysis/status/
        { "session_id": 1 }

    RESPONSE (200) - 분석 중:
        {
            "status": "analyzing",
            "jd_keywords": []
        }

    RESPONSE (200) - 분석 완료:
        {
            "status": "ready",
            "jd_keywords": ["Python", "Django", "REST API", "PostgreSQL"]
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="status@example.com",
            password="password123",
            name="테스트유저",
        )
        self.client.force_authenticate(self.user)
        self.url = reverse("analysis-status")

    def _create_session(self, **kwargs):
        return AnalysisSession.objects.create(
            user=self.user,
            job_role="백엔드 개발자",
            jd_text="JD 텍스트",
            **kwargs,
        )

    def test_분석중_상태일때_keywords_빈배열_반환(self):
        session = self._create_session(status="analyzing")
        request_body = {"session_id": session.id}

        response = self.client.post(self.url, request_body, format="json")

        print("\n[status - analyzing] REQUEST :", request_body)
        print("[status - analyzing] RESPONSE:", response.data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"],       "analyzing")
        self.assertEqual(response.data["jd_keywords"],  [])

    def test_분석완료_상태일때_keywords_포함_반환(self):
        session = self._create_session(status="ready", jd_keywords=MOCK_JD_KEYWORDS)
        request_body = {"session_id": session.id}

        response = self.client.post(self.url, request_body, format="json")

        print("\n[status - ready] REQUEST :", request_body)
        print("[status - ready] RESPONSE:", response.data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"],      "ready")
        self.assertEqual(response.data["jd_keywords"], MOCK_JD_KEYWORDS)

    def test_분석실패_상태일때_failed_반환(self):
        session = self._create_session(status="failed")

        response = self.client.post(self.url, {"session_id": session.id}, format="json")

        print("\n[status - failed] RESPONSE:", response.data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "failed")

    def test_타유저_세션_조회시_404_반환(self):
        other_user = User.objects.create_user(
            email="other@example.com", password="pw", name="다른유저"
        )
        other_session = AnalysisSession.objects.create(
            user=other_user, job_role="프론트엔드", jd_text="JD", status="ready"
        )

        response = self.client.post(
            self.url, {"session_id": other_session.id}, format="json"
        )

        print("\n[status - 타유저] RESPONSE:", response.data)
        self.assertEqual(response.status_code, 404)

    def test_미인증_요청시_401_반환(self):
        self.client.force_authenticate(user=None)
        session = self._create_session(status="analyzing")

        response = self.client.post(self.url, {"session_id": session.id}, format="json")

        self.assertEqual(response.status_code, 401)


# ──────────────────────────────────────────────
# 3단계: POST /api/v1/analysis/match/
# ──────────────────────────────────────────────

class MatchAPITest(APITestCase):
    """
    [3단계] 분석 결과 조회 API

    REQUEST:
        POST /api/v1/analysis/match/
        { "session_id": 1 }

    RESPONSE (200):
        {
            "session_id": 1,
            "job_role": "백엔드 개발자",
            "company_name": "커리어닷집",
            "jd_keywords": ["Python", "Django", "REST API", "PostgreSQL"],
            "resume_analysis": {
                "tech_stack": ["Python", "Django", "React"],
                "key_experiences": ["백엔드 API 설계 및 개발", "DB 모델링"],
                "strengths": ["문제 해결력", "커뮤니케이션"],
                "projects": [{"name": "커리어닷집", "role": "백엔드 개발", "result": "MVP 출시"}]
            },
            "questions": [
                {"id": 1, "question_type": "personality", "question_text": "...", "order": 0},
                ...총 10개...
            ]
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="match@example.com",
            password="password123",
            name="테스트유저",
        )
        self.client.force_authenticate(self.user)
        self.url = reverse("analysis-match")

    def _create_ready_session(self, user=None):
        session = AnalysisSession.objects.create(
            user=user or self.user,
            job_role="백엔드 개발자",
            company_name="커리어닷집",
            jd_text="Python, Django 기반 백엔드 개발자 채용",
            status="ready",
            jd_keywords=MOCK_JD_KEYWORDS,
            resume_analysis=MOCK_RESUME_ANALYSIS,
        )
        GeneratedQuestion.objects.bulk_create([
            GeneratedQuestion(
                session=session,
                question_type=q["type"],
                question_text=q["text"],
                order=i,
            )
            for i, q in enumerate(MOCK_QUESTIONS)
        ])
        return session

    def test_분석완료_세션_전체결과_반환(self):
        session = self._create_ready_session()
        request_body = {"session_id": session.id}

        response = self.client.post(self.url, request_body, format="json")

        print("\n[match] REQUEST :", request_body)
        print("[match] RESPONSE:")
        pprint.pprint(dict(response.data))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["session_id"],   session.id)
        self.assertEqual(response.data["job_role"],     "백엔드 개발자")
        self.assertEqual(response.data["company_name"], "커리어닷집")
        self.assertEqual(response.data["jd_keywords"],  MOCK_JD_KEYWORDS)
        self.assertEqual(response.data["resume_analysis"], MOCK_RESUME_ANALYSIS)
        self.assertEqual(len(response.data["questions"]), 10)

    def test_질문_타입별_개수_확인(self):
        session = self._create_ready_session()

        response = self.client.post(self.url, {"session_id": session.id}, format="json")

        types = [q["question_type"] for q in response.data["questions"]]
        print("\n[match] 질문 타입 분포:", {t: types.count(t) for t in set(types)})

        self.assertEqual(types.count("personality"), 3)
        self.assertEqual(types.count("technical"),   4)
        self.assertEqual(types.count("experience"),  3)

    def test_질문_순서_확인(self):
        session = self._create_ready_session()

        response = self.client.post(self.url, {"session_id": session.id}, format="json")

        orders = [q["order"] for q in response.data["questions"]]
        print("\n[match] 질문 순서:", orders)

        self.assertEqual(orders, list(range(10)))

    def test_분석미완료_세션_조회시_400_반환(self):
        session = AnalysisSession.objects.create(
            user=self.user,
            job_role="백엔드 개발자",
            jd_text="JD 텍스트",
            status="analyzing",
        )

        response = self.client.post(self.url, {"session_id": session.id}, format="json")

        print("\n[match - 미완료] RESPONSE:", response.data)

        self.assertEqual(response.status_code, 400)
        self.assertIn("error",  response.data)
        self.assertIn("status", response.data)

    def test_타유저_세션_조회시_404_반환(self):
        other_user = User.objects.create_user(
            email="other-match@example.com", password="pw", name="다른유저"
        )
        other_session = self._create_ready_session(user=other_user)

        response = self.client.post(
            self.url, {"session_id": other_session.id}, format="json"
        )

        print("\n[match - 타유저] RESPONSE:", response.data)
        self.assertEqual(response.status_code, 404)

    def test_미인증_요청시_401_반환(self):
        self.client.force_authenticate(user=None)
        session = self._create_ready_session()

        response = self.client.post(self.url, {"session_id": session.id}, format="json")

        self.assertEqual(response.status_code, 401)
