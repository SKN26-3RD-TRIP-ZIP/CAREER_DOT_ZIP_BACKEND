from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.interview.models import GuardrailEvent, InterviewAnswer, InterviewQuestion, InterviewSession


class InterviewGuardrailTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="guard@example.com",
            password="Password123!",
            name="Guard User",
            is_verified=True,
        )
        self.admin = User.objects.create_user(
            email="guard-admin@example.com",
            password="Password123!",
            name="Guard Admin",
            is_verified=True,
            is_staff=True,
        )
        self.session = InterviewSession.objects.create(
            user=self.user,
            interview_type="technical",
            persona="practical",
            status="in_progress",
        )
        self.question = InterviewQuestion.objects.create(
            session=self.session,
            order_index=1,
            question_type="main",
            question_text="프로젝트 경험을 설명해 주세요.",
        )
        self.url = f"/api/v1/interviews/sessions/{self.session.id}/questions/{self.question.id}/answer"
        self.client.force_authenticate(self.user)

    def test_blocks_secret_pattern_without_saving_raw_answer(self):
        response = self.client.post(
            self.url,
            {"answer_text": "api_key=sk-abcdefghijklmnopqrstuvwxyz123456"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(InterviewAnswer.objects.exists())
        event = GuardrailEvent.objects.get()
        self.assertEqual(event.category, "G3")
        self.assertEqual(event.action, "BLOCK_INPUT")
        self.assertNotIn("sk-", event.masked_excerpt)

    def test_short_answer_is_guided_and_saved(self):
        response = self.client.post(self.url, {"answer_text": "네"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["guardrail"]["category"], "G1")
        self.assertEqual(InterviewAnswer.objects.count(), 1)
        self.assertEqual(GuardrailEvent.objects.get().answer_id, InterviewAnswer.objects.get().id)

    def test_admin_can_list_guardrail_events(self):
        GuardrailEvent.objects.create(
            user=self.user,
            session=self.session,
            question=self.question,
            category="G3",
            action="BLOCK_INPUT",
            reason_code="PROMPT_INJECTION_PATTERN",
            masked_excerpt="[MASKED]",
            endpoint="interview_answer_save",
        )
        self.client.force_authenticate(self.admin)

        response = self.client.get("/api/v1/admin/guardrails/events?category=G3")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["results"][0]["reason_code"], "PROMPT_INJECTION_PATTERN")
