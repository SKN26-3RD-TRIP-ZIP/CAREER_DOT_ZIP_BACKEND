from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.input.models import JobDescription
from apps.external.services.mock_jobs_service import SOURCE, MockJobsService, generate_mock_jobs

User = get_user_model()


@override_settings(
    MOCK_JOBS_COUNT=120,
    MOCK_JOBS_SEED=2026,
    MOCK_JOBS_DATA_FILE="C:/tmp/careerzip-test-mock-jobs-does-not-exist.json",
)
class MockJobsServiceTests(APITestCase):
    def setUp(self):
        MockJobsService._cache = None

    def test_seed_reproducibility(self):
        first = generate_mock_jobs(count=20, seed=2026)
        second = generate_mock_jobs(count=20, seed=2026)
        self.assertEqual(first, second)

    def test_generate_10000_jobs(self):
        jobs = generate_mock_jobs(count=10000, seed=2026)
        self.assertEqual(len(jobs), 10000)
        self.assertEqual(jobs[0]["job_id"], "mock-job-000001")
        self.assertTrue(all(job["source"] == SOURCE and job["is_mock"] is True for job in jobs[:50]))

    def test_list_contract(self):
        result = MockJobsService().list_jobs(filters={}, sort="latest", page=1, size=5)
        self.assertEqual(result["source"], SOURCE)
        self.assertTrue(result["is_mock"])
        self.assertEqual(result["total"], 120)
        self.assertEqual(len(result["results"]), 5)

    def test_filters_with_new_and_legacy_aliases(self):
        service = MockJobsService()
        by_keyword = service.list_jobs(filters={"keyword": "백엔드"}, sort="latest", page=1, size=100)
        self.assertTrue(by_keyword["results"])
        self.assertTrue(all("백엔드" in job["position"] for job in by_keyword["results"]))

        by_tech = service.list_jobs(filters={"tech_stack": "Python,Django"}, sort="latest", page=1, size=100)
        self.assertTrue(by_tech["results"])
        for job in by_tech["results"]:
            tech_stack = [tech.lower() for tech in job["tech_stack"]]
            self.assertIn("python", tech_stack)
            self.assertIn("django", tech_stack)

        legacy = service.list_jobs(filters={"q": "react", "tech": "React"}, sort="latest", page=1, size=100)
        self.assertTrue(legacy["results"])

    def test_sort_deadline_and_invalid_page(self):
        service = MockJobsService()
        result = service.list_jobs(filters={}, sort="deadline", page=1, size=20)
        deadlines = [job["deadline"] for job in result["results"]]
        self.assertEqual(deadlines, sorted(deadlines))

        empty = service.list_jobs(filters={}, sort="latest", page=999, size=20)
        self.assertEqual(empty["results"], [])

    def test_get_job_hit_and_miss(self):
        service = MockJobsService()
        first = service.list_jobs(filters={}, sort="latest", page=1, size=1)["results"][0]
        self.assertEqual(service.get_job(first["job_id"])["job_id"], first["job_id"])
        self.assertIsNone(service.get_job("does-not-exist-xyz"))


@override_settings(
    MOCK_JOBS_COUNT=120,
    MOCK_JOBS_SEED=2026,
    MOCK_JOBS_DATA_FILE="C:/tmp/careerzip-test-mock-jobs-does-not-exist.json",
)
class MockJobsAPITests(APITestCase):
    def setUp(self):
        MockJobsService._cache = None
        self.user = User.objects.create_user(
            email="qa_mock_jobs@example.com",
            password="testpass123",
            name="QA",
            is_verified=True,
        )
        self.other = User.objects.create_user(
            email="qa_mock_jobs_other@example.com",
            password="testpass123",
            name="Other",
            is_verified=True,
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._token(self.user)}")

    def _token(self, user):
        return str(RefreshToken.for_user(user).access_token)

    def test_list_requires_auth(self):
        self.client.credentials()
        response = self.client.get("/api/v1/external/jobs")
        self.assertEqual(response.status_code, 401)

    def test_list_ok_with_requested_params(self):
        response = self.client.get(
            "/api/v1/external/jobs",
            {"keyword": "백엔드", "tech_stack": "Python", "page": 1, "size": 5, "ordering": "deadline"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["source"], SOURCE)
        self.assertTrue(response.data["is_mock"])
        self.assertLessEqual(len(response.data["results"]), 5)
        self.assertTrue(all(job["is_mock"] for job in response.data["results"]))

    def test_detail_ok_and_404(self):
        first = self.client.get("/api/v1/external/jobs", {"size": 1}).data["results"][0]
        ok = self.client.get(f"/api/v1/external/jobs/{first['job_id']}")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["job_id"], first["job_id"])
        self.assertTrue(ok.data["is_mock"])

        missing = self.client.get("/api/v1/external/jobs/no-such-id")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.data["code"], "MOCK_JOB_NOT_FOUND")

    def test_save_job_as_user_owned_jd(self):
        first = self.client.get("/api/v1/external/jobs", {"size": 1}).data["results"][0]
        response = self.client.post(f"/api/v1/external/jobs/{first['job_id']}/save-jd")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["source"], SOURCE)
        self.assertTrue(response.data["is_mock"])

        jd = JobDescription.objects.get(id=response.data["jd_id"])
        self.assertEqual(jd.user, self.user)
        self.assertIn(SOURCE, jd.original_text)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._token(self.other)}")
        forbidden = self.client.get(f"/api/v1/jds/{jd.id}")
        self.assertEqual(forbidden.status_code, 404)
