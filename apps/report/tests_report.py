import uuid
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.interview.models import InterviewSession, InterviewQuestion, InterviewAnswer
from apps.evaluation.models import Evaluation, StrengthTag, WeaknessTag, AnswerStrengthTag, AnswerWeaknessTag
from apps.report.models import FinalReport
from apps.report.services.report_generator import generate_final_report


class FinalReportIntegrationTests(APITestCase):
    def setUp(self):
        """테스트를 위한 유저, 공통 태그, 세션 데이터 초기화"""
        User = get_user_model()
        
        self.user = User.objects.create_user(
            email='analyst@example.com',
            password='password123',
            name='분석가'
        )
        self.other_user = User.objects.create_user(
            email='other@example.com',
            password='password123',
            name='타인'
        )
        
        # 기본 인증 설정
        self.client.force_authenticate(self.user)

        # evaluation 모델 구조에 매핑되는 핵심 정적 태그 선언 및 생성
        self.strength_tag_1 = StrengthTag.objects.create(tag_name="data_driven_achievement")
        self.strength_tag_2 = StrengthTag.objects.create(tag_name="logical_structuring")
        self.weakness_tag_1 = WeaknessTag.objects.create(tag_name="lack_of_metric_grounding")
        self.weakness_tag_2 = WeaknessTag.objects.create(tag_name="excessive_filler_words")

    def create_complete_interview_environment(self, user=None, status_value='completed', filler_count=2):
        """
        evaluation 앱의 실제 관계형 데이터베이스 모델 구조를 100% 반영한
        인터뷰 세션, 질문, 답변, 평가 데이터 세트 빌더 메소드
        """
        target_user = user or self.user
        
        # 1) 인터뷰 세션 생성 (views.py의 직렬화 요구 필드 반영)
        session = InterviewSession.objects.create(
            user=target_user,
            interview_type='technical',
            persona='practical',
            interview_mode='video',
            status=status_value,
        )

        if status_value == 'completed':
            # 2) 질문 생성 (order_index NOT NULL 제약조건 반영)
            q1 = InterviewQuestion.objects.create(
                session=session, 
                question_text="프로젝트의 기술적 한계를 극복한 경험을 설명해주세요.",
                order_index=1
            )
            q2 = InterviewQuestion.objects.create(
                session=session, 
                question_text="사용한 프레임워크의 최적화 방식에 대해 설명해주세요.",
                order_index=2
            )

            # 3) 답변 생성 (InterviewAnswer)
            ans1 = InterviewAnswer.objects.create(session=session, question=q1, answer_text="FastAPI와 Redis를 활용해 개선했습니다.")
            ans2 = InterviewAnswer.objects.create(session=session, question=q2, answer_text="인덱싱 구조를 튜닝하여 속도를 올렸습니다.")

            # 4) 실제 Evaluation 레코드 생성 및 answers 매핑 (OneToOne 관계)
            eval1 = Evaluation.objects.create(
                answer=ans1,
                final_tech_score=85,
                llm_concept_score=80,
                bei_score={"situation": {"score": 22}, "task": {"score": 20}, "action": {"score": 23}, "result": {"score": 21}},
                cbi_score={"level": 4, "score": 85},
                filler_words={"total": filler_count, "counts": {"어": filler_count, "음": 0}}
            )
            
            eval2 = Evaluation.objects.create(
                answer=ans2,
                final_tech_score=95,
                llm_concept_score=90,
                bei_score={"situation": {"score": 24}, "task": {"score": 22}, "action": {"score": 25}, "result": {"score": 24}},
                cbi_score={"level": 5, "score": 95},
                filler_words={"total": 1, "counts": {"그니까": 1}}
            )

            # 5) 다대다(M2M) 매핑 중간 테이블 레코드 생성 (AnswerStrengthTag, AnswerWeaknessTag)
            AnswerStrengthTag.objects.create(answer=ans1, strength_tag=self.strength_tag_1, priority_rank=1)
            AnswerStrengthTag.objects.create(answer=ans1, strength_tag=self.strength_tag_2, priority_rank=2)
            AnswerWeaknessTag.objects.create(answer=ans1, weakness_tag=self.weakness_tag_1, priority_rank=1)

            AnswerStrengthTag.objects.create(answer=ans2, strength_tag=self.strength_tag_1, priority_rank=1)
            AnswerWeaknessTag.objects.create(answer=ans2, weakness_tag=self.weakness_tag_2, priority_rank=1)

        return session

    # =========================================================================
    # 1. Views 및 API 엔드포인트 기능 테스트 (views.py 기반)
    # =========================================================================

    def test_session_final_report_endpoint_success(self):
        """정상 완료된 세션의 리포트 조회 시, 최초 자동 생성 기능 및 포맷 검증"""
        session = self.create_complete_interview_environment()
        
        url = reverse('session-final-report', kwargs={'session_id': session.id})
        response = self.client.get(url)

        # 검증: Status Code 200 OK
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # 검증