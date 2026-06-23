"""대시보드 error_count(최근 24h API 5xx 수) 및 에러 기록 미들웨어 테스트."""
from datetime import timedelta

from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.admin_api.models import ApiErrorLog
from apps.admin_api.services.dashboard_service import build_dashboard_stats
from config.middleware import ResponseTimeMiddleware


class DashboardErrorCountTests(TestCase):
    def test_counts_errors_in_last_24h(self):
        ApiErrorLog.objects.create(path='/api/a', method='GET', status_code=500)
        ApiErrorLog.objects.create(path='/api/b', method='POST', status_code=502)

        self.assertEqual(build_dashboard_stats()['error_count'], 2)

    def test_excludes_errors_older_than_24h(self):
        log = ApiErrorLog.objects.create(path='/api/a', method='GET', status_code=500)
        old = timezone.now() - timedelta(hours=25)
        ApiErrorLog.objects.filter(pk=log.pk).update(created_at=old)

        self.assertEqual(build_dashboard_stats()['error_count'], 0)

    def test_system_health_block_removed(self):
        # 가짜였던 system_health(stt/error_rate)는 응답에서 제거됨
        self.assertNotIn('system_health', build_dashboard_stats())


class ErrorLoggingMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _run(self, path, status_code):
        mw = ResponseTimeMiddleware(lambda req: HttpResponse(status=status_code))
        mw(self.factory.get(path))

    def test_records_5xx_on_api_path(self):
        self._run('/api/v1/something', 500)

        self.assertEqual(ApiErrorLog.objects.count(), 1)
        log = ApiErrorLog.objects.first()
        self.assertEqual(log.status_code, 500)
        self.assertEqual(log.path, '/api/v1/something')

    def test_ignores_non_api_path(self):
        self._run('/admin/', 500)
        self.assertEqual(ApiErrorLog.objects.count(), 0)

    def test_ignores_success_response(self):
        self._run('/api/v1/something', 200)
        self.assertEqual(ApiErrorLog.objects.count(), 0)
