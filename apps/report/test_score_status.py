from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.interview.models import InterviewSession
from apps.report.models import FinalReport
from apps.report.serializers import FinalReportSerializer

User = get_user_model()


class FinalReportScoreStatusTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="report-status@example.com",
            password="testpass123",
            name="Report Status",
            is_verified=True,
        )
        self.session = InterviewSession.objects.create(
            user=self.user,
            interview_type="technical",
            persona="practical",
            status="completed",
        )

    def test_zero_score_is_scored_not_missing(self):
        report = FinalReport.objects.create(
            session=self.session,
            summary={"score_summary": {"overall_score": 0}},
        )
        data = FinalReportSerializer(report).data
        self.assertEqual(data["overall_score"], 0)
        self.assertEqual(data["score_status"], "SCORED")
        self.assertEqual(data["evaluation_status"], "COMPLETED")
        self.assertFalse(data["is_mock"])

    def test_null_score_is_not_evaluated(self):
        report = FinalReport.objects.create(
            session=self.session,
            summary={"evaluation_metadata": {"answer_count": 0, "evaluated_answer_count": 0}},
        )
        data = FinalReportSerializer(report).data
        self.assertIsNone(data["overall_score"])
        self.assertEqual(data["score_status"], "NOT_EVALUATED")
        self.assertEqual(data["evaluation_status"], "PENDING")

    def test_evaluation_failure_status(self):
        report = FinalReport.objects.create(
            session=self.session,
            summary={"evaluation_metadata": {"answer_count": 2, "evaluated_answer_count": 0}},
        )
        data = FinalReportSerializer(report).data
        self.assertEqual(data["score_status"], "NOT_EVALUATED")
        self.assertEqual(data["evaluation_status"], "FAILED")

    def test_mock_report_status(self):
        report = FinalReport.objects.create(
            session=self.session,
            summary={
                "source": "CAREER_ZIP_MOCK",
                "is_mock": True,
                "score_summary": {"overall_score": 70},
            },
        )
        data = FinalReportSerializer(report).data
        self.assertEqual(data["score_status"], "MOCK")
        self.assertEqual(data["evaluation_status"], "MOCK")
        self.assertTrue(data["is_mock"])
