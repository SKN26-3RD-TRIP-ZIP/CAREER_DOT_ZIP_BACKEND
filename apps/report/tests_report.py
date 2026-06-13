from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.interview.models import InterviewSession, InterviewQuestion, InterviewAnswer
from apps.evaluation.models import Evaluation, StrengthTag, WeaknessTag, AnswerStrengthTag, AnswerWeaknessTag
from apps.report.models import FinalReport
from apps.report.services.report_generator import generate_final_report


@override_settings(OPENAI_USE_MOCK=True)
class FinalReportIntegrationTests(APITestCase):
  def setUp(self):
    User = get_user_model()
    self.user = User.objects.create_user(
        email='analyst@example.com',
        password='password123',
        name='분석가',
    )
    self.client.force_authenticate(self.user)

    self.strength_tag = StrengthTag.objects.create(tag_name='data_driven_achievement')
    self.weakness_tag = WeaknessTag.objects.create(tag_name='excessive_filler_words')

  def create_evaluated_session(self, filler_count=2):
    session = InterviewSession.objects.create(
        user=self.user,
        interview_type='technical',
        persona='practical',
        interview_mode='text',
        status='completed',
    )
    question = InterviewQuestion.objects.create(
        session=session,
        question_text='기술적 한계를 극복한 경험을 설명해주세요.',
        order_index=1,
    )
    answer = InterviewAnswer.objects.create(
        session=session,
        question=question,
        answer_text='FastAPI와 Redis를 활용해 응답 속도를 개선했습니다.',
        long_pause_count=1,
    )
    Evaluation.objects.create(
        answer=answer,
        final_tech_score=85,
        bei_score={
            'situation': {'score': 22},
            'task': {'score': 20},
            'action': {'score': 23},
            'result': {'score': 21},
        },
        cbi_score={'assigned_level': 4, 'score': 85},
        filler_words={'total': filler_count, 'counts': {'어': filler_count}},
        score_detail={
            'speech_delivery': {'speech_score': 90, 'total_filler_count': filler_count},
            'technical_depth': {'is_grounded': True},
        },
    )
    AnswerStrengthTag.objects.create(answer=answer, strength_tag=self.strength_tag, priority_rank=1)
    AnswerWeaknessTag.objects.create(answer=answer, weakness_tag=self.weakness_tag, priority_rank=1)
    return session

  def test_generate_final_report_matches_design_doc_summary_shape(self):
    session = self.create_evaluated_session()
    summary = generate_final_report(session)

    self.assertEqual(
        set(summary.keys()),
        {'evaluation_metadata', 'score_summary', 'score_detail', 'dynamically_triggered_tags'},
    )
    self.assertEqual(summary['score_summary']['overall_score'], 85)
    self.assertIn('metrics', summary['score_summary'])
    self.assertIn('speech_diagnostics', summary['score_detail'])
    self.assertTrue(summary['dynamically_triggered_tags']['strength_tags'])

  def test_session_final_report_endpoint_success(self):
    session = self.create_evaluated_session()
    url = reverse('session-final-report', kwargs={'session_id': session.id})

    response = self.client.get(url)

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertIn('summary', response.data)
    self.assertEqual(response.data['summary']['score_summary']['overall_score'], 85)

  @patch('apps.evaluation.services.evaluation_services.eval_llm_chains_parallel')
  def test_evaluation_create_uses_interview_sufficiency_bridge(self, mock_llm):
    mock_llm.return_value = (
        {
            'tech_stack': 'FastAPI',
            'before_metric': '100ms',
            'after_metric': '20ms',
            'is_grounded': True,
        },
        {
            'bei_star': {
                'situation': {'desc': '상황', 'score': 20},
                'task': {'desc': '과제', 'score': 20},
                'action': {'desc': '행동', 'score': 20},
                'result': {'desc': '결과', 'score': 20},
            },
            'cbi_competency': {'assigned_level': 3, 'score': 60, 'evidence_sentence': '근거'},
        },
    )

    session = InterviewSession.objects.create(
        user=self.user,
        interview_type='technical',
        persona='practical',
        status='in_progress',
    )
    question = InterviewQuestion.objects.create(
        session=session,
        question_text='질문',
        order_index=1,
    )
    answer = InterviewAnswer.objects.create(
        session=session,
        question=question,
        answer_text='어 그러니까 FastAPI로 개선했습니다.',
        long_pause_count=5,
    )

    response = self.client.post(
        reverse('evaluation-create'),
        {'answer_id': str(answer.id)},
        format='json',
    )

    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    self.assertTrue(Evaluation.objects.filter(answer=answer).exists())
