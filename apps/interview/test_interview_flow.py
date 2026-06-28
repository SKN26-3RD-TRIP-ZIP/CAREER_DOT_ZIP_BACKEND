from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.input.models import JobDescription, ResumeMaster
from apps.interview.models import InterviewAnswer, InterviewQuestion, InterviewSession


@override_settings(
    INTERVIEW_AI_CHAIN_ENGINE='mock',
    INTERVIEW_AI_OPENAI_ENABLE_REAL_CALL=False,
)
class MVPInterviewFlowAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="flow-owner@example.com",
            password="password123",
            name="Flow Owner",
        )
        self.client.force_authenticate(self.user)

        self.jd = JobDescription.objects.create(
            user=self.user,
            company_name="Career Zip",
            position="Backend Developer",
            original_text="Django REST Framework 기반 백엔드 API 개발자를 채용합니다.",
            keywords='["Django", "DRF", "API"]',
        )

        self.resume = ResumeMaster.objects.create(
            user=self.user,
            name="Flow Owner",
            email="flow-owner@example.com",
            original_text="Django와 DRF를 활용해 API 서버를 개발한 경험이 있습니다.",
        )

    def mock_questions(self):
        return [
            {
                "order_index": 1,
                "question_type": "main",
                "question_text": "Django REST Framework를 사용해 본 경험을 설명해주세요.",
                "source_type": "general",
                "source_reference": "flow-test:q1",
            },
            {
                "order_index": 2,
                "question_type": "main",
                "question_text": "API 설계 시 중요하게 생각하는 기준은 무엇인가요?",
                "source_type": "general",
                "source_reference": "flow-test:q2",
            },
            {
                "order_index": 3,
                "question_type": "main",
                "question_text": "프로젝트에서 본인이 직접 기여한 부분을 설명해주세요.",
                "source_type": "general",
                "source_reference": "flow-test:q3",
            },
        ]

    def create_session(self):
        return self.client.post(
            reverse("mvp-session-create"),
            {
                "jd_id": str(self.jd.id),
                "resume_id": str(self.resume.id),
                "persona_type": "practical",
                "interview_mode": "text",
            },
            format="json",
        )

    def start_session(self, session_id):
        return self.client.patch(
            reverse("mvp-session-status", kwargs={"session_id": session_id}),
            {"status": "in_progress"},
            format="json",
        )

    def generate_questions(self, session_id):
        return self.client.post(
            reverse("mvp-question-generate", kwargs={"session_id": session_id}),
            {
                "jd_id": str(self.jd.id),
                "resume_id": str(self.resume.id),
                "project_ids": [],
                "question_count": 3,
            },
            format="json",
        )

    def list_questions(self, session_id):
        return self.client.get(
            reverse("mvp-question-list", kwargs={"session_id": session_id})
        )

    def create_answer(self, session_id, question_id, answer_text):
        return self.client.post(
            reverse("mvp-answer-create"),
            {
                "session_id": str(session_id),
                "question_id": str(question_id),
                "answer_text": answer_text,
                "speech_duration": 30.0,
            },
            format="json",
        )

    def create_followup(self, answer_id):
        return self.client.post(
            reverse("mvp-answer-followup-create", kwargs={"answer_id": answer_id}),
            {},
            format="json",
        )

    def complete_session(self, session_id):
        return self.client.patch(
            reverse("mvp-session-status", kwargs={"session_id": session_id}),
            {"status": "completed"},
            format="json",
        )

    @patch("apps.interview.mvp_views.generate_interview_questions")
    def test_text_interview_flow_runs_from_session_to_completed(self, mock_generate):
        mock_generate.return_value = self.mock_questions()

        session_response = self.create_session()

        self.assertEqual(session_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(session_response.data["status"], "ready")
        self.assertEqual(session_response.data["persona_type"], "practical")
        self.assertEqual(session_response.data["interview_mode"], "text")

        session_id = session_response.data["session_id"]

        start_response = self.start_session(session_id)

        self.assertEqual(start_response.status_code, status.HTTP_200_OK)
        self.assertEqual(start_response.data["status"], "in_progress")

        generate_response = self.generate_questions(session_id)

        self.assertEqual(generate_response.status_code, status.HTTP_200_OK)
        self.assertEqual(generate_response.data["generated_count"], 3)

        list_response = self.list_questions(session_id)

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data["total"], 3)

        questions = list_response.data["results"]
        self.assertEqual(questions[0]["order_index"], 1)

        sufficient_answer = (
            "제가 직접 LangChain 기반 질문 생성 체인을 설계했고, 일반 함수 호출 방식과 비교했을 때 "
            "프롬프트 단계 분리와 추후 RAG 검색 결과 연결이 쉬웠기 때문에 선택했습니다. "
            "또한 답변 평가와 꼬리질문 생성을 분리해 유지보수성과 확장성을 높이는 것을 기준으로 판단했습니다."
        )

        for question in questions:
            answer_response = self.create_answer(
                session_id=session_id,
                question_id=question["question_id"],
                answer_text=sufficient_answer,
            )

            self.assertEqual(answer_response.status_code, status.HTTP_201_CREATED)
            self.assertIn("answer_id", answer_response.data)

            followup_response = self.create_followup(answer_response.data["answer_id"])

            self.assertEqual(followup_response.status_code, status.HTTP_200_OK)
            self.assertEqual(followup_response.data["next_action"], "NEXT_QUESTION")
            self.assertIsNone(followup_response.data["followup_question"])

        complete_response = self.complete_session(session_id)

        self.assertEqual(complete_response.status_code, status.HTTP_200_OK)
        self.assertEqual(complete_response.data["status"], "completed")

        session = InterviewSession.objects.get(id=session_id)
        self.assertEqual(session.status, "completed")
        self.assertIsNotNone(session.ended_at)
        self.assertEqual(InterviewAnswer.objects.filter(session=session).count(), 3)

    @patch("apps.interview.mvp_views.generate_interview_questions")
    def test_short_answer_generates_followup_during_flow(self, mock_generate):
        mock_generate.return_value = self.mock_questions()

        session_response = self.create_session()
        session_id = session_response.data["session_id"]

        self.start_session(session_id)
        self.generate_questions(session_id)

        question = self.list_questions(session_id).data["results"][0]

        answer_response = self.create_answer(
            session_id=session_id,
            question_id=question["question_id"],
            answer_text="짧은 답변",
        )

        self.assertEqual(answer_response.status_code, status.HTTP_201_CREATED)

        followup_response = self.create_followup(answer_response.data["answer_id"])

        self.assertEqual(followup_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(followup_response.data["next_action"], "GENERATE_FOLLOWUP")
        self.assertIsNotNone(followup_response.data["followup_question"])

        followup_question_id = followup_response.data["followup_question"]["question_id"]

        followup_question = InterviewQuestion.objects.get(id=followup_question_id)
        self.assertEqual(followup_question.question_type, "follow_up")
        self.assertEqual(str(followup_question.parent_question_id), question["question_id"])
