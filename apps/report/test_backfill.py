"""백필 회귀 테스트.

실제 MVP 면접 플로우는 답변만 저장하고 평가(Evaluation)를 트리거하지 않는다.
이 테스트는 '평가 없는 완료 세션'의 리포트를 요청했을 때
generate_final_report 가 누락된 평가를 자동 생성(백필)하고,
그 결과가 리포트에 반영되는지 검증한다.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.interview.models import InterviewSession, InterviewQuestion, InterviewAnswer
from apps.evaluation.models import Evaluation
from apps.report.models import FinalReport


def _mock_llm_chains():
  """eval_llm_chains_parallel 의 (grounding, competency) 반환값 모킹."""
  grounding = {
      'tech_stack': 'FastAPI',
      'before_metric': '100ms',
      'after_metric': '20ms',
      'is_grounded': True,
  }
  competency = {
      'bei_star': {
          'situation': {'desc': '상황', 'score': 20},
          'task': {'desc': '과제', 'score': 20},
          'action': {'desc': '행동', 'score': 20},
          'result': {'desc': '결과', 'score': 20},
      },
      'cbi_competency': {'assigned_level': 3, 'score': 60, 'evidence_sentence': '근거'},
  }
  return grounding, competency


class ReportBackfillTests(APITestCase):
  def setUp(self):
    User = get_user_model()
    self.user = User.objects.create_user(
        email='backfill@example.com',
        password='password123',
        name='백필',
    )
    self.client.force_authenticate(self.user)

  def _completed_session_without_evaluation(self):
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
    InterviewAnswer.objects.create(
        session=session,
        question=question,
        answer_text='FastAPI와 Redis를 활용해 응답 속도를 100ms에서 20ms로 개선했습니다.',
        long_pause_count=0,
    )
    return session

  @patch('apps.evaluation.services.evaluation_services.eval_llm_chains_parallel')
  def test_report_request_backfills_missing_evaluation(self, mock_llm):
    mock_llm.return_value = _mock_llm_chains()
    session = self._completed_session_without_evaluation()

    # 사전 조건: 평가가 아직 하나도 없다(= 단절 상태 재현).
    self.assertEqual(Evaluation.objects.filter(answer__session=session).count(), 0)

    url = reverse('session-final-report', kwargs={'session_id': session.id})
    response = self.client.get(url)

    # 리포트 요청만으로 평가가 자동 생성되어야 한다.
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(Evaluation.objects.filter(answer__session=session).count(), 1)

    summary = response.data['summary']
    self.assertGreater(summary['score_summary']['overall_score'], 0)
    self.assertEqual(summary['evaluation_metadata']['evaluated_answer_count'], 1)
    questions = summary['score_detail']['questions']
    self.assertEqual(len(questions), 1)
    self.assertGreater(questions[0]['score'], 0)

  @patch('apps.evaluation.services.evaluation_services.eval_llm_chains_parallel')
  def test_backfill_is_idempotent_on_regenerate(self, mock_llm):
    mock_llm.return_value = _mock_llm_chains()
    session = self._completed_session_without_evaluation()

    url = reverse('session-final-report', kwargs={'session_id': session.id})
    self.client.get(url)
    first_count = Evaluation.objects.filter(answer__session=session).count()

    # 두 번째 호출에서도 평가가 중복 생성되지 않아야 한다(멱등).
    self.client.get(url)
    second_count = Evaluation.objects.filter(answer__session=session).count()

    self.assertEqual(first_count, 1)
    self.assertEqual(second_count, 1)
    self.assertEqual(FinalReport.objects.filter(session=session).count(), 1)
