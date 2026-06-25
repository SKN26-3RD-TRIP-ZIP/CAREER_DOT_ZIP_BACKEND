"""Bridge evaluation pipeline with interview team's answer sufficiency chain."""

import logging

from django.conf import settings

from apps.interview.services.ai_chain_service import InterviewAIChainService

logger = logging.getLogger("feedback_ai.sufficiency_bridge")


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

  # OPENAI_USE_MOCK=True 이면 OpenAI API Key 없는 로컬 환경 → sufficiency 호출 스킵
  if getattr(settings, 'OPENAI_USE_MOCK', False):
    return [], None

  # weakness tags 는 선택 입력(파이프라인이 cbi_res 태그로 폴백)이므로, 여기서 예외를
  # 격리해 평가 전체가 죽지 않게 graceful degrade 한다.
  #
  # interview 팀 공개 인터페이스만 호출한다. payload 빌드와 answer text(STT/타이핑)
  # 선택은 interview 내부(evaluate_answer_sufficiency)가 소유하므로 evaluation 은
  # answer 인스턴스만 넘긴다.
  try:
    service = InterviewAIChainService()
    result = service.evaluate_answer_sufficiency(answer)
    return result.get('answer_weakness_tags', []), result.get('selected_weakness_tag')
  except Exception:
    logger.warning(
        "answer sufficiency 조회 실패 (answer=%s) — weakness tags 없이 진행",
        getattr(answer, 'id', '?'),
        exc_info=True,
    )
    return [], None
