from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import APIException, ValidationError

from apps.external.services.worknet_service import WorknetService


class Command(BaseCommand):
    help = 'Test the Worknet job search API connection without saving data.'

    def add_arguments(self, parser):
        parser.add_argument('--keyword', required=True, help='Job search keyword')
        parser.add_argument('--page', type=int, default=1, help='Result page number')
        parser.add_argument('--size', type=int, default=10, help='Results per page')

    def handle(self, *args, **options):
        keyword = options['keyword']
        page = options['page']
        size = options['size']

        self.stdout.write('[Worknet API 연결 테스트]')
        self.stdout.write(f'WORKNET_BASE_URL: {self._configured(settings.WORKNET_BASE_URL)}')
        self.stdout.write(f'WORKNET_API_KEY: {self._configured(settings.WORKNET_API_KEY)}')
        self.stdout.write(f'keyword: {keyword}')
        self.stdout.write(f'page: {page}')
        self.stdout.write(f'size: {size}')
        self.stdout.write('')

        try:
            result = WorknetService().search_jobs(keyword, page=page, size=size)
        except ValidationError as exc:
            self.stderr.write(self.style.ERROR('호출 실패: 검색 조건을 확인해주세요.'))
            raise CommandError(self._format_detail(exc.detail)) from exc
        except APIException as exc:
            self.stderr.write(self.style.ERROR('호출 실패: 워크넷 API 연결을 확인해주세요.'))
            self.stderr.write(f'오류 유형: {exc.default_code}')
            self.stderr.write(f'상태 코드: {exc.status_code}')
            if getattr(exc, 'http_status', None) is not None:
                self.stderr.write(f'HTTP status code: {exc.http_status}')
            if getattr(exc, 'content_type', None):
                self.stderr.write(f'Content-Type: {exc.content_type}')
            if getattr(exc, 'response_preview', None):
                self.stderr.write(f'응답 본문 앞부분: {exc.response_preview}')
            diagnostic = self._safe_diagnostic(exc.__cause__)
            if diagnostic:
                self.stderr.write(f'원인: {diagnostic}')
            raise CommandError(self._format_detail(exc.detail)) from exc

        self.stdout.write(self.style.SUCCESS('호출 성공'))
        self.stdout.write(f"total: {result.get('total', 0)}")
        self.stdout.write('')

        results = result.get('results') or []
        if not results:
            self.stdout.write('검색 결과가 없습니다.')
            return

        for index, job in enumerate(results[:3], start=1):
            self.stdout.write(
                f"{index}. {self._display(job.get('company_name'))} / "
                f"{self._display(job.get('position'))} / "
                f"{self._display(job.get('region'))} / "
                f"{self._display(job.get('deadline'))}"
            )
            self.stdout.write(f"   URL: {self._display(job.get('source_url'))}")
            self.stdout.write('')

    @staticmethod
    def _configured(value):
        return '설정됨' if value else '미설정'

    @staticmethod
    def _display(value):
        return value if value not in (None, '') else '-'

    @staticmethod
    def _format_detail(detail):
        if isinstance(detail, dict):
            return '; '.join(f'{key}: {value}' for key, value in detail.items())
        return str(detail)

    @staticmethod
    def _safe_diagnostic(cause):
        if cause is None:
            return ''

        try:
            import requests
        except ImportError:
            return 'requests 패키지를 사용할 수 없습니다.'

        if isinstance(cause, requests.Timeout):
            return '요청 시간이 5초를 초과했습니다.'
        if isinstance(cause, requests.HTTPError):
            response = cause.response
            status_code = response.status_code if response is not None else '알 수 없음'
            return f'워크넷 서버가 HTTP {status_code} 응답을 반환했습니다.'
        if isinstance(cause, requests.ConnectionError):
            return '워크넷 서버에 연결할 수 없습니다. WORKNET_BASE_URL을 확인해주세요.'
        if cause.__class__.__name__ == 'ParseError':
            return '워크넷 응답을 XML 형식으로 해석하지 못했습니다.'
        if isinstance(cause, requests.RequestException):
            return f'HTTP 요청 오류가 발생했습니다. ({cause.__class__.__name__})'
        if isinstance(cause, (ValueError, TypeError)):
            return '워크넷 응답을 JSON 형식으로 해석하지 못했습니다.'
        return f'알 수 없는 오류가 발생했습니다. ({cause.__class__.__name__})'
