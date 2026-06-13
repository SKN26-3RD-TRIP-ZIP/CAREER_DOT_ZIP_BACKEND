"""
Mock 채용공고 API 테스트.

실행: python manage.py test apps.external.tests_mock_jobs
- 서비스 로직(검색/필터/페이징/정렬/상세) + API 인증/응답 검증.
- 사람인 무단 수집이 아닌, 직접 작성한 Mock 데이터(source='MOCK') 기준.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.external.services.mock_jobs_service import MockJobsService

User = get_user_model()


class MockJobsServiceTests(APITestCase):
    def test_load_all_marks_source_mock(self):
        svc = MockJobsService()
        r = svc.list_jobs(filters={}, sort="latest", page=1, size=100)
        self.assertEqual(r["source"], "MOCK")
        self.assertGreaterEqual(r["total"], 1)
        self.assertTrue(all(j["source"] == "MOCK" for j in r["results"]))

    def test_paging(self):
        svc = MockJobsService()
        r = svc.list_jobs(filters={}, sort="latest", page=2, size=5)
        self.assertEqual(r["page"], 2)
        self.assertLessEqual(len(r["results"]), 5)

    def test_filters(self):
        svc = MockJobsService()
        r = svc.list_jobs(filters={"position": "백엔드"}, sort="latest", page=1, size=100)
        self.assertTrue(all("백엔드" in j["position"] for j in r["results"]))

        r = svc.list_jobs(filters={"tech": "django"}, sort="latest", page=1, size=100)
        self.assertTrue(
            all(any("django" in t.lower() for t in j["tech_stack"]) for j in r["results"])
        )

    def test_sort_deadline_ascending(self):
        svc = MockJobsService()
        r = svc.list_jobs(filters={}, sort="deadline", page=1, size=100)
        deadlines = [j["deadline"] for j in r["results"]]
        self.assertEqual(deadlines, sorted(deadlines))

    def test_get_job_hit_and_miss(self):
        svc = MockJobsService()
        first = svc.list_jobs(filters={}, sort="latest", page=1, size=1)["results"][0]
        self.assertEqual(svc.get_job(first["job_id"])["job_id"], first["job_id"])
        self.assertIsNone(svc.get_job("does-not-exist-xyz"))


class MockJobsAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="qa_mock_jobs@example.com", password="testpass123", name="QA"
        )
        self.user.is_verified = True
        self.user.save(update_fields=["is_verified"])
        access = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_list_requires_auth(self):
        self.client.credentials()  # 인증 제거
        res = self.client.get("/api/v1/external/jobs")
        self.assertEqual(res.status_code, 401)

    def test_list_ok(self):
        res = self.client.get("/api/v1/external/jobs", {"size": 5})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["source"], "MOCK")
        self.assertIn("total", res.data)
        self.assertLessEqual(len(res.data["results"]), 5)

    def test_list_filter_and_search(self):
        res = self.client.get("/api/v1/external/jobs", {"q": "django", "career_type": "신입"})
        self.assertEqual(res.status_code, 200)
        for job in res.data["results"]:
            self.assertEqual(job["career_type"], "신입")

    def test_detail_ok_and_404(self):
        first = self.client.get("/api/v1/external/jobs", {"size": 1}).data["results"][0]
        ok = self.client.get(f"/api/v1/external/jobs/{first['job_id']}")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["job_id"], first["job_id"])

        miss = self.client.get("/api/v1/external/jobs/no-such-id")
        self.assertEqual(miss.status_code, 404)
