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
                # 'grounding' 키 사용 — report_generator는 score_detail.get("grounding")을 읽음.
                # 이전 'technical_depth' 키는 읽히지 않아 grounding_flags가 항상 비어
                # grounding_avg=None이 되는 버그였음.
                'grounding': {'is_grounded': True},
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
    self.assertAlmostEqual(summary['score_summary']['overall_score'], 90.6, places=0)  # persona(practical): BEI86×.30+CBI85×.25+Grounding100×.30+Speech90×.15=90.6
    self.assertIn('metrics', summary['score_summary'])
    self.assertIn('speech_diagnostics', summary['score_detail'])
    self.assertTrue(summary['dynamically_triggered_tags']['strength_tags'])

  def test_session_final_report_endpoint_success(self):
    session = self.create_evaluated_session()
    url = reverse('session-final-report', kwargs={'session_id': session.id})

    response = self.client.get(url)

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertIn('summary', response.data)
    self.assertAlmostEqual(response.data['summary']['score_summary']['overall_score'], 90.6, places=0)  # persona(practical): BEI86×.30+CBI85×.25+Grounding100×.30+Speech90×.15=90.6

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


  def test_personality_session_grounding_is_null(self):
    """personality 세션은 grounding_avg가 None이어야 한다.

    session.interview_type='personality'이면 report_generator는
    grounding_flags를 수집하지 않으므로 grounding_score=None.
    PDF에서 None 크래시 없이 '—' 표기가 돼야 한다(pdf_generator None 가드).
    """
    session = InterviewSession.objects.create(
        user=self.user,
        interview_type='personality',
        persona='coach',
        interview_mode='text',
        status='completed',
    )
    question = InterviewQuestion.objects.create(
        session=session,
        question_text='자신의 강점을 말해보세요.',
        order_index=1,
    )
    answer = InterviewAnswer.objects.create(
        session=session, question=question,
        answer_text='저는 문제 해결력이 뛰어납니다.',
        long_pause_count=0,
    )
    Evaluation.objects.create(
        answer=answer,
        final_tech_score=70,
        bei_score={'situation': {'score': 18}, 'task': {'score': 17}, 'action': {'score': 16}, 'result': {'score': 15}},
        cbi_score={'assigned_level': 3, 'score': 70},
        filler_words={'total': 0, 'counts': {}},
        score_detail={
            'speech_delivery': {'speech_score': 75},
            # personality 세션: grounding 키 없음 → grounding_avg=None 이 정상
        },
    )
    AnswerStrengthTag.objects.create(answer=answer, strength_tag=self.strength_tag, priority_rank=1)

    summary = generate_final_report(session)

    grounding = summary['score_summary']['metrics']['grounding_score']
    self.assertIsNone(grounding, "personality 세션 grounding_score는 None이어야 함")
    # 종합 점수가 grounding 없이도 정상 산출되는지
    self.assertGreater(summary['score_summary']['overall_score'], 0)

