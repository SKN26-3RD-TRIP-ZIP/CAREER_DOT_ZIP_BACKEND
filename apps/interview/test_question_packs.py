from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.accounts.services.points import earn_points
from apps.interview.models import InterviewSession, QuestionPack


class QuestionPackAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='pack@example.com',
            password='Password123!',
            name='Pack User',
            is_verified=True,
        )
        earn_points(user=self.user, amount=1000, reason_code='ADMIN.SEED')
        access = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

    def test_create_and_apply_question_pack(self):
        create = self.client.post(
            '/api/v1/interviews/question-packs',
            {'interview_type': 'technical', 'question_count': 3, 'mix': {'technical': 60}},
            format='json',
        )

        self.assertEqual(create.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(create.data['questions']), 3)
        pack = QuestionPack.objects.get(id=create.data['question_pack_id'])
        session = InterviewSession.objects.create(
            user=self.user,
            interview_type='technical',
            persona='practical',
            status='created',
        )

        apply = self.client.post(
            f'/api/v1/interviews/question-packs/{pack.id}/apply',
            {'session_id': str(session.id)},
            format='json',
        )

        self.assertEqual(apply.status_code, status.HTTP_201_CREATED)
        self.assertEqual(apply.data['applied_count'], 3)
        self.assertEqual(session.questions.count(), 3)
