import re
import xml.etree.ElementTree as ElementTree

from django.conf import settings
from rest_framework.exceptions import APIException, ValidationError


class WorknetAPIException(APIException):
    status_code = 502
    default_detail = 'Failed to retrieve jobs from Worknet.'
    default_code = 'worknet_api_error'

    def __init__(
        self,
        detail=None,
        code=None,
        *,
        http_status=None,
        content_type=None,
        response_preview=None,
    ):
        super().__init__(detail=detail, code=code)
        if code:
            self.default_code = code
        self.http_status = http_status
        self.content_type = content_type
        self.response_preview = response_preview


class WorknetConfigurationException(APIException):
    status_code = 503
    default_detail = 'Worknet API is not configured.'
    default_code = 'worknet_not_configured'


class WorknetService:
    TIMEOUT_SECONDS = 5

    def search_jobs(self, keyword, page=1, size=10):
        keyword = (keyword or '').strip()
        if not keyword:
            raise ValidationError({'keyword': 'This query parameter is required.'})

        page = self._parse_positive_integer(page, 'page')
        size = self._parse_positive_integer(size, 'size')
        if size > 100:
            raise ValidationError({'size': 'Ensure this value is less than or equal to 100.'})
        if not settings.WORKNET_API_KEY or not settings.WORKNET_BASE_URL:
            raise WorknetConfigurationException()

        try:
            import requests

            response = requests.get(
                settings.WORKNET_BASE_URL,
                params={
                    'authKey': settings.WORKNET_API_KEY,
                    'callTp': 'L',
                    'returnType': 'XML',
                    'startPage': page,
                    'display': size,
                    'keyword': keyword,
                },
                timeout=self.TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            response = getattr(exc, 'response', None)
            raise WorknetAPIException(
                http_status=getattr(response, 'status_code', None),
                content_type=self._response_content_type(response),
                response_preview=self._response_preview(response),
            ) from exc

        return self.normalize_xml_response(
            response.text,
            page=page,
            size=size,
            http_status=response.status_code,
            content_type=self._response_content_type(response),
        )

    def normalize_xml_response(
        self,
        xml_text,
        page=1,
        size=10,
        http_status=None,
        content_type=None,
    ):
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError as exc:
            raise WorknetAPIException(
                detail='Failed to parse Worknet XML response.',
                code='worknet_xml_parse_error',
                http_status=http_status,
                content_type=content_type,
                response_preview=self._sanitize_preview(xml_text),
            ) from exc

        job_nodes = [
            element
            for element in root.iter()
            if self._local_name(element.tag).lower() in {'wanted', 'item', 'job'}
        ]
        error_message = self._find_xml_text(root, {'error'})
        message = error_message or self._find_xml_text(root, {'message'})
        message_code = self._find_xml_text(root, {'messagecd', 'messagecode'})
        if error_message or (message and message_code not in (None, '', '0', '000')):
            raise WorknetAPIException(
                detail=f'Worknet API error: {message}',
                code='worknet_remote_error',
                http_status=http_status,
                content_type=content_type,
                response_preview=self._sanitize_preview(xml_text),
            )

        jobs = [self._xml_element_to_dict(element) for element in job_nodes]
        results = [self._normalize_job(job) for job in jobs]

        total = None
        for element in root.iter():
            if self._local_name(element.tag).lower() in {'total', 'totalcount'}:
                total = (element.text or '').strip()
                if total:
                    break
        try:
            total = int(total)
        except (TypeError, ValueError):
            total = len(results)

        return {
            'total': total,
            'page': page,
            'size': size,
            'results': results,
        }

    def normalize_search_response(self, payload, page=1, size=10):
        payload = payload if isinstance(payload, dict) else {}
        root = payload.get('wantedRoot') or payload.get('response') or {}
        root = root if isinstance(root, dict) else {}
        jobs = (
            payload.get('wanted')
            or payload.get('jobs')
            or payload.get('result')
            or root.get('wanted')
            or root.get('jobs')
            or []
        )
        if isinstance(jobs, dict):
            jobs = [jobs]
        if not isinstance(jobs, list):
            jobs = []

        results = [self._normalize_job(job) for job in jobs if isinstance(job, dict)]
        total = self._first_value(
            payload,
            ('total', 'totalCount'),
            default=self._first_value(root, ('total', 'totalCount'), default=len(results)),
        )
        try:
            total = int(total)
        except (TypeError, ValueError):
            total = len(results)

        return {
            'total': total,
            'page': page,
            'size': size,
            'results': results,
        }

    def _normalize_job(self, job):
        return {
            'worknet_job_id': self._first_value(
                job,
                ('wantedAuthNo', 'wantedAuthno', 'wanted_auth_no'),
            ),
            'company_name': self._first_value(
                job,
                ('company', 'businoNm', 'corpNm', 'companyNm'),
            ),
            'position': self._first_value(
                job,
                ('title', 'wantedTitle', 'wantedTitleNm'),
            ),
            'region': self._first_value(
                job,
                ('region', 'workRegion', 'regionCd', 'basicAddr'),
            ),
            'deadline': self._first_value(
                job,
                ('closeDt', 'receiptCloseDt', 'regDt'),
            ),
            'employment_type': self._first_value(
                job,
                ('empTpNm', 'employmentType', 'holidayTpNm'),
            ),
            'source_url': self._first_value(
                job,
                ('wantedInfoUrl', 'detailUrl', 'wantedMobileInfoUrl'),
            ),
        }

    @staticmethod
    def _parse_positive_integer(value, field_name):
        try:
            parsed_value = int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError({field_name: 'A valid integer is required.'}) from exc
        if parsed_value < 1:
            raise ValidationError({field_name: 'Ensure this value is greater than or equal to 1.'})
        return parsed_value

    @staticmethod
    def _first_value(data, keys, default=None):
        lowered_data = {str(key).lower(): value for key, value in data.items()}
        for key in keys:
            value = data.get(key, lowered_data.get(key.lower()))
            if value not in (None, ''):
                return value
        return default

    @classmethod
    def _xml_element_to_dict(cls, element):
        return {
            cls._local_name(child.tag): (child.text or '').strip()
            for child in element.iter()
            if child is not element and len(child) == 0
        }

    @classmethod
    def _find_xml_text(cls, root, tag_names):
        for element in root.iter():
            if cls._local_name(element.tag).lower() in tag_names:
                value = (element.text or '').strip()
                if value:
                    return value
        return None

    @staticmethod
    def _local_name(tag):
        return str(tag).split('}', 1)[-1]

    @staticmethod
    def _response_content_type(response):
        if response is None:
            return None
        return response.headers.get('Content-Type')

    @classmethod
    def _response_preview(cls, response):
        return cls._sanitize_preview(response.text) if response is not None else None

    @staticmethod
    def _sanitize_preview(text, limit=300):
        preview = re.sub(r'\s+', ' ', text or '').strip()[:limit]
        api_key = settings.WORKNET_API_KEY
        if api_key:
            preview = preview.replace(api_key, '[REDACTED]')
        return preview
