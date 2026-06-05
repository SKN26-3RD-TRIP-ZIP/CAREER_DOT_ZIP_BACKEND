from django.db import transaction
from django.db.models import Max, Q

from apps.interview.models import InterviewQuestion


FOLLOWUP_TRIGGERS = {
    'TOO_SHORT': 'Answer is too short.',
    'MISSING_REASON': 'The reason for the choice is missing.',
    'UNCLEAR_ROLE': 'The applicant role and contribution are unclear.',
    'NO_RESULT': 'The result or outcome is missing.',
    'TECH_DEPTH_LOW': 'Technical depth is insufficient.',
}

FOLLOWUP_QUESTIONS = {
    'TOO_SHORT': '방금 답변을 조금 더 구체적인 사례를 들어 설명해주시겠어요?',
    'MISSING_REASON': '그 방식을 선택한 이유와 다른 대안과 비교했을 때의 장점을 설명해주세요.',
    'UNCLEAR_ROLE': '그 과정에서 본인이 직접 담당한 역할과 기여도를 구체적으로 설명해주세요.',
    'NO_RESULT': '그 경험의 결과나 성과는 무엇이었나요?',
    'TECH_DEPTH_LOW': '해당 기술을 실제로 적용할 때 주의해야 할 점이나 한계를 설명해주세요.',
}


class FollowupGenerator:
    REASON_WORDS = ('왜', '이유', '때문', '선택')
    ROLE_WORDS = ('제가', '저는', '담당', '구현', '기여')
    RESULT_WORDS = ('결과', '성과', '개선', '증가', '감소', '%')

    @classmethod
    def determine_trigger(cls, answer_text):
        text = (answer_text or '').strip()
        if len(text) < 30:
            return 'TOO_SHORT'
        if not any(word in text for word in cls.REASON_WORDS):
            return 'MISSING_REASON'
        if not any(word in text for word in cls.ROLE_WORDS):
            return 'UNCLEAR_ROLE'
        if not any(word in text for word in cls.RESULT_WORDS):
            return 'NO_RESULT'
        return None

    @classmethod
    def create_followup(cls, answer):
        existing = (
            InterviewQuestion.objects.filter(
                Q(source_answer=answer) | Q(parent_question=answer.question),
                question_type='follow_up',
            )
            .order_by('order_index')
            .first()
        )
        if existing:
            return existing, False

        trigger = cls.determine_trigger(answer.answer_text)
        if trigger is None:
            return None, False

        with transaction.atomic():
            last_index = (
                InterviewQuestion.objects.filter(session=answer.session)
                .aggregate(last=Max('order_index'))['last']
                or 0
            )
            question = InterviewQuestion.objects.create(
                session=answer.session,
                parent_question=answer.question,
                source_answer=answer,
                question_text=FOLLOWUP_QUESTIONS[trigger],
                question_type='follow_up',
                source_type='rule',
                source_reference=trigger,
                order_index=last_index + 1,
            )
        return question, True


def generate_follow_up_questions(answer):
    trigger = FollowupGenerator.determine_trigger(answer.answer_text)
    if trigger is None:
        return []
    return [
        {
            'question_type': 'follow_up',
            'question_text': FOLLOWUP_QUESTIONS[trigger],
            'source_type': 'rule',
            'source_reference': trigger,
        }
    ]
