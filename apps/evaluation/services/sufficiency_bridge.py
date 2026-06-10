"""Bridge evaluation pipeline with interview team's answer sufficiency chain."""

from apps.interview.services.ai_chain_service import InterviewAIChainService
from apps.interview.services.follow_up_generator import FollowupGenerator


def get_answer_text_for_evaluation(answer):
  """Use STT text for voice interviews, otherwise the typed answer."""
  if answer.session.interview_mode == 'voice' and answer.stt_text:
    return answer.stt_text
  return answer.answer_text or ''


def resolve_answer_sufficiency(answer, request_sufficiency=None):
  """
  Prefer sufficiency payload supplied by the interview flow (turns API).
  Fall back to the shared InterviewAIChainService contract.
  """
  if isinstance(request_sufficiency, dict):
    tags = request_sufficiency.get('answer_weakness_tags')
    if tags is not None:
      return tags, request_sufficiency.get('selected_weakness_tag')

  service = InterviewAIChainService()
  payload = FollowupGenerator._build_sufficiency_payload(answer)
  payload['answer']['answer_text'] = get_answer_text_for_evaluation(answer)
  result = service.judge_answer_sufficiency(payload)
  return result.get('answer_weakness_tags', []), result.get('selected_weakness_tag')
