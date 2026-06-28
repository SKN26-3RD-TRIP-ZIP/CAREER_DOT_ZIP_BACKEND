from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.interview.models import InterviewSession
from apps.report.models import ActionPlan, FinalReport


class ActionPlanAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="plan@example.com",
            password="Password123!",
            name="Plan User",
            is_verified=True,
        )
        self.other = User.objects.create_user(
            email="other-plan@example.com",
            password="Password123!",
            name="Other User",
            is_verified=True,
        )
        self.session = InterviewSession.objects.create(
            user=self.user,
            interview_type="technical",
            persona="practical",
            status="completed",
        )
        self.report = FinalReport.objects.create(
            session=self.session,
            summary={"score_summary": {"overall_score": 82}},
        )
        other_session = InterviewSession.objects.create(
            user=self.other,
            interview_type="technical",
            persona="practical",
            status="completed",
        )
        self.other_report = FinalReport.objects.create(session=other_session, summary={})
        self.client.force_authenticate(self.user)

    def test_create_action_plan_for_owned_report(self):
        response = self.client.post(
            f"/api/v1/reports/{self.report.id}/action-plans",
            {"title": "구체적 근거 보강", "description": "STAR 결과 수치를 추가한다.", "source_tag": "specificity"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "구체적 근거 보강")
        self.assertEqual(response.data["status"], ActionPlan.STATUS_TODO)
        self.assertEqual(ActionPlan.objects.filter(report=self.report).count(), 1)

    def test_create_action_plan_blocks_other_user_report(self):
        response = self.client.post(
            f"/api/v1/reports/{self.other_report.id}/action-plans",
            {"title": "권한 없음"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_report_action_plan_limit_is_three(self):
        for index in range(3):
            ActionPlan.objects.create(report=self.report, title=f"plan-{index}")

        response = self.client.post(
            f"/api/v1/reports/{self.report.id}/action-plans",
            {"title": "네 번째"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ActionPlan.objects.filter(report=self.report).count(), 3)

    def test_list_my_action_plans_is_paginated(self):
        ActionPlan.objects.create(report=self.report, title="첫 과제")

        response = self.client.get("/api/v1/users/me/action-plans?page=1&size=10")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["results"][0]["title"], "첫 과제")

    def test_patch_owned_action_plan_status(self):
        action_plan = ActionPlan.objects.create(report=self.report, title="상태 변경")

        response = self.client.patch(
            f"/api/v1/action-plans/{action_plan.id}",
            {"status": ActionPlan.STATUS_IN_PROGRESS},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        action_plan.refresh_from_db()
        self.assertEqual(action_plan.status, ActionPlan.STATUS_IN_PROGRESS)

    def test_patch_other_user_action_plan_is_blocked(self):
        action_plan = ActionPlan.objects.create(report=self.other_report, title="타인 과제")

        response = self.client.patch(
            f"/api/v1/action-plans/{action_plan.id}",
            {"status": ActionPlan.STATUS_DONE},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
