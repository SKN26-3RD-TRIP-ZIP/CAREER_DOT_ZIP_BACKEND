#!/usr/bin/env python3
"""verify_report_metrics.py 용 결정적 fixture 시드.

DB에 이미 있는 완료 세션은 grounding 블록/BEI 점수가 비어 있어
grounding_score·bei_logic_score 의 '0이 아닌 비율/스케일'을 실증할 수 없다.
이 스크립트는 evaluation 을 직접 심어 기대값이 명확한 세션을 만든다.

  답변 4개의 grounding.is_grounded = [True, True, False, False]  -> grounding_score 기대 50.0
  BEI 4요소 = situation20 / task15 / action18 / result22 (동일)     -> bei_logic_score 기대 75.0
                                                                       element_total_avg 기대 18.75

실행:
    python seed_verify_fixture.py
    python verify_report_metrics.py --session <출력된 세션 id>

NOTE: 커밋 대상 아님. qa2_test.py 와 함께 .gitignore 유지.
"""
import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.contrib.auth import get_user_model
from apps.interview.models import InterviewSession, InterviewQuestion, InterviewAnswer
from apps.evaluation.models import Evaluation

User = get_user_model()

user, _ = User.objects.get_or_create(
    email="verify_metrics@career.zip",
    defaults={"name": "검증픽스처", "is_active": True, "is_verified": True},
)

session = InterviewSession.objects.create(
    user=user,
    status="completed",
    interview_type="technical",
    persona="practical",
    interview_mode="text",
)

BEI = {"situation": 20, "task": 15, "action": 18, "result": 22}
GROUNDED = [True, True, False, False]

for i, grounded in enumerate(GROUNDED, start=1):
    q = InterviewQuestion.objects.create(
        session=session,
        question_text=f"검증용 질문 {i}",
        question_type="technical",
        order_index=i,
    )
    a = InterviewAnswer.objects.create(
        session=session, question=q,
        answer_text=f"검증용 답변 {i}", stt_text=f"검증용 답변 {i}",
    )
    Evaluation.objects.create(
        answer=a,
        bei_score=dict(BEI),
        cbi_score={"assigned_level": 3, "score": 70},
        answer_score=70,
        score_detail={
            "grounding": {
                "is_grounded": grounded,
                "tech_stack": grounded,
                "before_metric": grounded,
                "after_metric": grounded,
            },
            "speech_delivery": {"speech_score": 80},
        },
    )

print("=" * 60)
print(f"세션 id            : {session.id}")
print("기대 grounding_score: 50.0  (is_grounded 2/4)")
print("기대 bei_logic_score: 75.0  (20+15+18+22)")
print("기대 element_total  : 18.75")
print("=" * 60)
print(f"\n검증: python verify_report_metrics.py --session {session.id}")