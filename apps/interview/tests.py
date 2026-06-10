from datetime import timedelta
import uuid

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.common.choices import (
    INTERVIEW_SESSION_STATUS_CANCELLED,
    INTERVIEW_SESSION_STATUS_COMPLETED,
)
from apps.evaluation.models import Evaluation
from apps.input.models import JobDescription, ResumeMaster
from apps.question_bank.models import QuestionBankItem

from .models import InterviewAnswer, InterviewQuestion, InterviewSession


class InterviewSessionCompleteAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='owner@example.com',
            password='password123',
            name='Owner',
        )
        self.other_user = user_model.objects.create_user(
            email='other@example.com',
            password='password123',
            name='Other',
        )
        self.client.force_authenticate(self.user)

    def create_session(self, **kwargs):
        defaults = {
            'user': self.user,
            'interview_type': 'technical',
            'persona': 'coach',
        }
        defaults.update(kwargs)
        return InterviewSession.objects.create(**defaults)

    def complete_url(self, session):
        return reverse('interview-session-complete', kwargs={'session_id': session.id})

    def test_complete_session(self):
        started_at = timezone.now() - timedelta(minutes=30)
        session = self.create_session(status='in_progress', started_at=started_at)

        response = self.client.patch(self.complete_url(session), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['session_id'], str(session.id))
        self.assertEqual(response.data['status'], INTERVIEW_SESSION_STATUS_COMPLETED)
        self.assertIsNotNone(response.data['ended_at'])
        session.refresh_from_db()
        self.assertEqual(session.status, INTERVIEW_SESSION_STATUS_COMPLETED)
        self.assertIsNotNone(session.ended_at)

    def test_completed_session_is_returned_without_changing_ended_at(self):
        ended_at = timezone.now() - timedelta(minutes=5)
        session = self.create_session(
            status=INTERVIEW_SESSION_STATUS_COMPLETED,
            ended_at=ended_at,
        )

        response = self.client.patch(self.complete_url(session), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        session.refresh_from_db()
        self.assertEqual(session.ended_at, ended_at)

    def test_cancelled_session_cannot_be_completed(self):
        session = self.create_session(status=INTERVIEW_SESSION_STATUS_CANCELLED)

        response = self.client.patch(self.complete_url(session), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        session.refresh_from_db()
        self.assertEqual(session.status, INTERVIEW_SESSION_STATUS_CANCELLED)

    def test_other_users_session_returns_not_found(self):
        session = self.create_session(user=self.other_user)

        response = self.client.patch(self.complete_url(session), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_authentication_is_required(self):
        session = self.create_session()
        self.client.force_authenticate(user=None)

        response = self.client.patch(self.complete_url(session), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class InterviewSessionTurnsAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='turn-owner@example.com',
            password='password123',
            name='Turn Owner',
        )
        self.other_user = user_model.objects.create_user(
            email='turn-other@example.com',
            password='password123',
            name='Turn Other',
        )
        self.client.force_authenticate(self.user)
        self.session = InterviewSession.objects.create(
            user=self.user,
            interview_type='technical',
            persona='practical',
            status='in_progress',
        )

    def turns_url(self, session=None):
        return reverse(
            'interview-session-turns',
            kwargs={'session_id': (session or self.session).id},
        )

    def test_turns_include_answers_evaluations_and_follow_ups(self):
        main_question = InterviewQuestion.objects.create(
            session=self.session,
            order_index=1,
            question_type='main',
            question_text='Main question',
            source_type='general',
        )
        main_answer = InterviewAnswer.objects.create(
            session=self.session,
            question=main_question,
            answer_text='Main answer',
        )
        Evaluation.objects.create(
            answer=main_answer,
            final_tech_score=88,
            llm_concept_score=85,
            score_detail={'summary': 'Good answer'},
        )
        follow_up = InterviewQuestion.objects.create(
            session=self.session,
            order_index=2,
            question_type='follow_up',
            question_text='Follow-up question',
            source_type='general',
            parent_question=main_question,
            source_answer=main_answer,
        )
        InterviewAnswer.objects.create(
            session=self.session,
            question=follow_up,
            answer_text='Follow-up answer',
        )

        response = self.client.get(self.turns_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total'], 1)
        turn = response.data['turns'][0]
        self.assertEqual(turn['turn_index'], 1)
        self.assertEqual(turn['answer']['answer_text'], 'Main answer')
        self.assertEqual(turn['evaluation']['final_tech_score'], 88)
        self.assertEqual(len(turn['follow_up_questions']), 1)
        self.assertEqual(
            turn['follow_up_questions'][0]['answer']['answer_text'],
            'Follow-up answer',
        )
        self.assertIsNone(turn['follow_up_questions'][0]['evaluation'])

    def test_turn_without_answer_returns_null_values(self):
        InterviewQuestion.objects.create(
            session=self.session,
            order_index=1,
            question_type='main',
            question_text='Unanswered question',
            source_type='general',
        )

        response = self.client.get(self.turns_url())

        turn = response.data['turns'][0]
        self.assertIsNone(turn['answer'])
        self.assertIsNone(turn['evaluation'])
        self.assertEqual(turn['follow_up_questions'], [])

    def test_other_users_session_returns_not_found(self):
        other_session = InterviewSession.objects.create(
            user=self.other_user,
            interview_type='technical',
            persona='coach',
        )

        response = self.client.get(self.turns_url(other_session))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_authentication_is_required(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(self.turns_url())

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class InterviewQuestionGenerationIntegrationTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='question-owner@example.com',
            password='password123',
            name='Question Owner',
        )
        self.other_user = user_model.objects.create_user(
            email='question-other@example.com',
            password='password123',
            name='Question Other',
        )
        self.jd = JobDescription.objects.create(
            user=self.user,
            company_name='Career Zip',
            position='Backend Developer',
            original_text='Python Django API backend development',
            keywords='["Python", "Django", "API"]',
        )
        self.other_jd = JobDescription.objects.create(
            user=self.other_user,
            company_name='Other',
            position='Backend Developer',
            original_text='Python backend development',
        )
        self.client.force_authenticate(self.user)

    def sessions_url(self):
        return reverse('interview-session-list-create')

    def create_session(self, **overrides):
        payload = {
            'jd_id': str(self.jd.id),
            'interview_type': 'technical',
            'persona': 'practical',
            'total_question_count': 3,
        }
        payload.update(overrides)
        return self.client.post(self.sessions_url(), payload, format='json')

    def questions_generate_url(self, session_id):
        return reverse(
            'interview-question-generate',
            kwargs={'session_id': session_id},
        )

    def questions_list_url(self, session_id):
        return reverse(
            'interview-question-list',
            kwargs={'session_id': session_id},
        )

    def test_session_creation_requires_jd_id(self):
        response = self.client.post(
            self.sessions_url(),
            {
                'interview_type': 'technical',
                'persona': 'practical',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('jd_id', response.data)

    def test_session_creation_accepts_owned_jd_id(self):
        response = self.create_session()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        session = InterviewSession.objects.get(id=response.data['session_id'])
        self.assertEqual(session.jd, self.jd)

    def test_session_creation_rejects_other_users_jd_id(self):
        response = self.create_session(jd_id=str(self.other_jd.id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('jd_id', response.data)

    def test_question_generation_uses_ai_chain_then_bank_fallback(self):
        bank_question = QuestionBankItem.objects.create(
            question_text='How do you design a Django REST API?',
            answer_example='Explain resource design and validation.',
            question_type='technical',
            difficulty='medium',
            keywords=['Django', 'API'],
        )
        session_response = self.create_session()
        session_id = session_response.data['session_id']

        response = self.client.post(
            self.questions_generate_url(session_id),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['total'], 3)

        questions = response.data['questions']
        self.assertEqual(questions[0]['source_type'], 'jd')

        for question in questions:
            self.assertIn(
                question['source_type'],
                [
                    'jd',
                    'resume',
                    'cover_letter',
                    'project_experience',
                    'combined',
                    'prepared_question',
                    'question_bank',
                    'rule',
                    'general',
                ],
            )
            self.assertTrue(question['source_reference'])

        self.assertEqual(
            list(
                InterviewQuestion.objects.filter(session_id=session_id)
                .order_by('order_index')
                .values_list('order_index', flat=True)
            ),
            [1, 2, 3],
        )

    def test_force_regenerate_and_question_list(self):
        QuestionBankItem.objects.create(
            question_text='Explain Python API transaction handling.',
            answer_example='Discuss transaction boundaries.',
            question_type='technical',
            difficulty='hard',
            keywords=['Python', 'API', 'transaction'],
        )
        session_response = self.create_session(total_question_count=2)
        session_id = session_response.data['session_id']
        first_response = self.client.post(
            self.questions_generate_url(session_id),
            {},
            format='json',
        )
        first_ids = {
            question['question_id']
            for question in first_response.data['questions']
        }

        regenerate_response = self.client.post(
            self.questions_generate_url(session_id),
            {'force_regenerate': True},
            format='json',
        )
        regenerated_ids = {
            question['question_id']
            for question in regenerate_response.data['questions']
        }
        list_response = self.client.get(self.questions_list_url(session_id))

        self.assertEqual(regenerate_response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(first_ids.isdisjoint(regenerated_ids))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data['total'], 2)


class MVPTextInterviewFlowTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='mvp-owner@example.com',
            password='password123',
            name='MVP Owner',
        )
        self.other_user = user_model.objects.create_user(
            email='mvp-other@example.com',
            password='password123',
            name='MVP Other',
        )
        self.jd = JobDescription.objects.create(
            user=self.user,
            company_name='Career Zip',
            position='Backend Developer',
            original_text='Python Django REST API',
        )
        self.other_jd = JobDescription.objects.create(
            user=self.other_user,
            company_name='Other',
            position='Backend Developer',
            original_text='Java Spring API',
        )
        self.resume = ResumeMaster.objects.create(
            user=self.user,
            name='Owner',
            email='mvp-owner@example.com',
            original_text='Python backend developer',
        )
        self.client.force_authenticate(self.user)

    def create_payload(self, **overrides):
        payload = {
            'jd_id': str(self.jd.id),
            'resume_id': str(self.resume.id),
            'persona_type': 'practical',
            'interview_mode': 'text',
        }
        payload.update(overrides)
        return payload

    def create_session(self, **overrides):
        return self.client.post(
            reverse('mvp-session-create'),
            self.create_payload(**overrides),
            format='json',
        )

    def test_authenticated_user_creates_text_session(self):
        response = self.create_session()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'ready')
        self.assertEqual(response.data['persona_type'], 'practical')
        self.assertEqual(response.data['interview_mode'], 'text')
        session = InterviewSession.objects.get(id=response.data['session_id'])
        self.assertEqual(session.user, self.user)
        self.assertEqual(session.jd, self.jd)
        self.assertEqual(session.resume, self.resume)

    def test_session_creation_requires_jd(self):
        # jd_id는 필수, resume_id는 선택(JD-only 플로우 지원)
        missing_jd = self.create_payload()
        missing_jd.pop('jd_id')
        missing_resume = self.create_payload()
        missing_resume.pop('resume_id')

        jd_response = self.client.post(reverse('mvp-session-create'), missing_jd, format='json')
        resume_response = self.client.post(
            reverse('mvp-session-create'),
            missing_resume,
            format='json',
        )

        self.assertEqual(jd_response.status_code, status.HTTP_400_BAD_REQUEST)
        # resume_id는 optional — resume 없이도 세션 생성 가능
        self.assertEqual(resume_response.status_code, status.HTTP_201_CREATED)

    def test_session_creation_rejects_other_users_jd(self):
        response = self.create_session(jd_id=str(self.other_jd.id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_session_creation_rejects_invalid_persona_and_mode(self):
        # pressure는 유효한 페르소나로 추가됨. 완전히 잘못된 값으로 검증
        persona_response = self.create_session(persona_type='invalid_persona')
        mode_response = self.create_session(interview_mode='video')

        self.assertEqual(persona_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(mode_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_session_creation_accepts_pressure_persona(self):
        # pressure 페르소나가 JD-only 플로우에서 허용되는지 확인
        response = self.create_session(persona_type='pressure')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_session_detail_and_status_update(self):
        created = self.create_session()
        session_id = created.data['session_id']

        detail = self.client.get(
            reverse('mvp-session-detail', kwargs={'session_id': session_id})
        )
        status_response = self.client.patch(
            reverse('mvp-session-status', kwargs={'session_id': session_id}),
            {'status': 'completed'},
            format='json',
        )

        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data['status'], 'ready')
        self.assertEqual(status_response.status_code, status.HTTP_200_OK)
        self.assertEqual(status_response.data['status'], 'completed')
        self.assertIsNotNone(status_response.data['ended_at'])

    def test_question_generation_defaults_to_three_and_prevents_duplicates(self):
        created = self.create_session()
        session_id = created.data['session_id']
        generate_url = reverse('mvp-question-generate', kwargs={'session_id': session_id})

        first = self.client.post(generate_url, {}, format='json')
        second = self.client.post(generate_url, {}, format='json')
        question_list = self.client.get(
            reverse('mvp-question-list', kwargs={'session_id': session_id})
        )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data['generated_count'], 3)
        self.assertEqual(second.data['generated_count'], 3)
        self.assertEqual(InterviewQuestion.objects.filter(session_id=session_id).count(), 3)
        self.assertEqual(question_list.data['total'], 3)
        self.assertEqual(
            [item['order_index'] for item in question_list.data['results']],
            [1, 2, 3],
        )

    def test_other_users_session_returns_not_found(self):
        session = InterviewSession.objects.create(
            user=self.other_user,
            jd=self.other_jd,
            interview_type='technical',
            persona='practical',
        )

        detail = self.client.get(
            reverse('mvp-session-detail', kwargs={'session_id': session.id})
        )
        generate = self.client.post(
            reverse('mvp-question-generate', kwargs={'session_id': session.id}),
            {},
            format='json',
        )

        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(generate.status_code, status.HTTP_404_NOT_FOUND)


class MVPAnswerFollowupAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='answer-owner@example.com',
            password='password123',
            name='Answer Owner',
        )
        self.other_user = user_model.objects.create_user(
            email='answer-other@example.com',
            password='password123',
            name='Answer Other',
        )
        self.session = InterviewSession.objects.create(
            user=self.user,
            interview_type='technical',
            persona='practical',
        )
        self.question = InterviewQuestion.objects.create(
            session=self.session,
            order_index=1,
            question_type='main',
            question_text='Explain your project contribution.',
            source_type='rule',
        )
        self.other_session = InterviewSession.objects.create(
            user=self.other_user,
            interview_type='technical',
            persona='practical',
        )
        self.other_question = InterviewQuestion.objects.create(
            session=self.other_session,
            order_index=1,
            question_type='main',
            question_text='Other question',
            source_type='rule',
        )
        self.client.force_authenticate(self.user)

    def answer_payload(self, **overrides):
        payload = {
            'session_id': str(self.session.id),
            'question_id': str(self.question.id),
            'answer_text': '저는 해당 기능을 직접 구현했습니다.',
            'speech_duration': 45.25,
        }
        payload.update(overrides)
        return payload

    def create_answer(self, **overrides):
        return self.client.post(
            reverse('mvp-answer-create'),
            self.answer_payload(**overrides),
            format='json',
        )

    def test_create_answer_returns_created(self):
        response = self.create_answer()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('answer_id', response.data)
        self.assertIn('created_at', response.data)

    def test_blank_answer_text_returns_bad_request(self):
        response = self.create_answer(answer_text='   ')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_session_and_question_return_not_found(self):
        missing_session = self.create_answer(session_id=str(uuid.uuid4()))
        missing_question = self.create_answer(question_id=str(uuid.uuid4()))

        self.assertEqual(missing_session.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(missing_question.status_code, status.HTTP_404_NOT_FOUND)

    def test_other_users_session_returns_forbidden(self):
        response = self.create_answer(
            session_id=str(self.other_session.id),
            question_id=str(self.other_question.id),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_answer_returns_bad_request(self):
        first = self.create_answer()
        second = self.create_answer(answer_text='두 번째 답변입니다.')

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(InterviewAnswer.objects.filter(question=self.question).count(), 1)

    def test_short_answer_creates_one_linked_followup(self):
        answer_response = self.create_answer(answer_text='짧은 답변')
        followup_url = reverse(
            'mvp-answer-followup-create',
            kwargs={'answer_id': answer_response.data['answer_id']},
        )

        first = self.client.post(followup_url, {}, format='json')
        second = self.client.post(followup_url, {}, format='json')

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.data['next_action'], 'GENERATE_FOLLOWUP')
        self.assertEqual(
            first.data['followup_question']['parent_question_id'],
            str(self.question.id),
        )

        followup_id = first.data["followup_question"]["question_id"]
        followup = InterviewQuestion.objects.get(id=followup_id)

        self.assertTrue(followup.source_reference.startswith("ai_chain_mock:"))

        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(
            InterviewQuestion.objects.filter(
                parent_question=self.question,
                question_type='follow_up',
            ).count(),
            1,
        )

    def test_sufficient_answer_moves_to_next_question(self):
        answer_response = self.create_answer(
            answer_text = (
                "제가 직접 LangChain 기반 질문 생성 체인을 설계했고, 일반 함수 호출 방식과 비교했을 때 "
                "프롬프트 단계 분리와 추후 RAG 검색 결과 연결이 쉬웠기 때문에 선택했습니다. "
                "또한 답변 평가와 꼬리질문 생성을 분리해 유지보수성과 확장성을 높이는 것을 기준으로 판단했습니다."
            )
        )

        response = self.client.post(
            reverse(
                'mvp-answer-followup-create',
                kwargs={'answer_id': answer_response.data['answer_id']},
            ),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['next_action'], 'NEXT_QUESTION')
        self.assertIsNone(response.data['followup_question'])

    def test_other_users_answer_returns_forbidden(self):
        other_answer = InterviewAnswer.objects.create(
            session=self.other_session,
            question=self.other_question,
            answer_text='Other answer',
        )

        response = self.client.post(
            reverse(
                'mvp-answer-followup-create',
                kwargs={'answer_id': other_answer.id},
            ),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
