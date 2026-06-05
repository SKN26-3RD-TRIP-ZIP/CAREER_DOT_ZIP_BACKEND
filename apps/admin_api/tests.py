from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.interview.models import InterviewSession

from .models import AuditLog


class AdminQueryAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            email='query-admin@example.com',
            password='password123',
            name='Admin',
            is_staff=True,
        )
        self.member = user_model.objects.create_user(
            email='query-member@example.com',
            password='password123',
            name='Member',
        )
        self.regular_user = user_model.objects.create_user(
            email='query-regular@example.com',
            password='password123',
            name='Regular',
        )
        self.client.force_authenticate(self.admin_user)

    def test_member_list_filters_and_returns_practice_count(self):
        InterviewSession.objects.create(
            user=self.member,
            interview_type='technical',
            persona='coach',
        )

        response = self.client.get(
            reverse('admin-member-list'),
            {'status': 'active', 'page': 1, 'size': 20},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result = next(item for item in response.data['results'] if item['id'] == self.member.id)
        self.assertEqual(result['practice_count'], 1)

    def test_member_status_change_creates_audit_log(self):
        response = self.client.patch(
            reverse('admin-member-status', kwargs={'member_id': self.member.id}),
            {'status': 'suspended'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.member.refresh_from_db()
        self.assertEqual(self.member.status, 'suspended')
        audit_log = AuditLog.objects.get(action_type='member_status_change')
        self.assertEqual(audit_log.before_value, {'status': 'active'})
        self.assertEqual(audit_log.after_value, {'status': 'suspended'})

    def test_admin_cannot_suspend_self(self):
        response = self.client.patch(
            reverse('admin-member-status', kwargs={'member_id': self.admin_user.id}),
            {'status': 'suspended'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_audit_log_list_filters_results(self):
        AuditLog.objects.create(
            actor=self.admin_user,
            action_type='member_status_change',
            target_type='accounts_user',
            target_id=str(self.member.id),
        )
        AuditLog.objects.create(
            actor=None,
            action_type='prompt_template_create',
            target_type='prompt_template',
            target_id='1',
        )

        response = self.client.get(
            reverse('admin-audit-log-list'),
            {
                'action_type': 'member_status_change',
                'actor_id': self.admin_user.id,
            },
        )

        self.assertEqual(response.data['total'], 1)

    def test_regular_user_is_forbidden(self):
        self.client.force_authenticate(self.regular_user)

        response = self.client.get(reverse('admin-member-list'))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
