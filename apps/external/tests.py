from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import ValidationError

from .services.worknet_service import WorknetAPIException, WorknetService


@override_settings(
    WORKNET_API_KEY='test-key',
    WORKNET_BASE_URL='https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do',
)
class WorknetServiceTests(SimpleTestCase):
    @patch('requests.get')
    def test_search_jobs_normalizes_xml_response_and_hides_api_key(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.headers = {'Content-Type': 'application/xml'}
        response.raise_for_status.return_value = None
        response.text = '''
            <wantedRoot>
                <total>1</total>
                <wanted>
                    <wantedAuthNo>JOB-1</wantedAuthNo>
                    <corpNm>Career.zip</corpNm>
                    <wantedTitle>Backend Developer</wantedTitle>
                    <workRegion>Seoul</workRegion>
                    <receiptCloseDt>2026-06-30</receiptCloseDt>
                    <empTpNm>Full-time</empTpNm>
                    <wantedInfoUrl>https://example.com/jobs/1</wantedInfoUrl>
                </wanted>
            </wantedRoot>
        '''
        mock_get.return_value = response

        result = WorknetService().search_jobs('backend', page='1', size='10')

        self.assertEqual(result['results'][0]['worknet_job_id'], 'JOB-1')
        self.assertEqual(result['results'][0]['company_name'], 'Career.zip')
        self.assertNotIn('authKey', result)
        self.assertEqual(mock_get.call_args.kwargs['timeout'], 5)
        self.assertEqual(
            mock_get.call_args.args[0],
            'https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do',
        )
        self.assertEqual(
            mock_get.call_args.kwargs['params'],
            {
                'authKey': 'test-key',
                'callTp': 'L',
                'returnType': 'XML',
                'startPage': 1,
                'display': 10,
                'keyword': 'backend',
            },
        )

    def test_normalize_xml_supports_alternate_keys_and_namespaces(self):
        xml_text = '''
            <ns:wantedRoot xmlns:ns="urn:worknet">
                <ns:totalCount>1</ns:totalCount>
                <ns:item>
                    <ns:wanted_auth_no>JOB-2</ns:wanted_auth_no>
                    <ns:companyNm>Company</ns:companyNm>
                    <ns:wantedTitleNm>Developer</ns:wantedTitleNm>
                    <ns:basicAddr>Busan</ns:basicAddr>
                    <ns:regDt>2026-06-30</ns:regDt>
                    <ns:holidayTpNm>Full-time</ns:holidayTpNm>
                    <ns:wantedMobileInfoUrl>https://example.com/jobs/2</ns:wantedMobileInfoUrl>
                </ns:item>
            </ns:wantedRoot>
        '''

        result = WorknetService().normalize_xml_response(xml_text)

        self.assertEqual(result['total'], 1)
        self.assertEqual(result['results'][0]['worknet_job_id'], 'JOB-2')
        self.assertEqual(result['results'][0]['company_name'], 'Company')

    def test_normalize_xml_raises_for_worknet_error_message(self):
        xml_text = '''
            <wantedRoot>
                <message>Invalid API key.</message>
                <messageCd>002</messageCd>
            </wantedRoot>
        '''

        with self.assertRaises(WorknetAPIException) as context:
            WorknetService().normalize_xml_response(
                xml_text,
                http_status=200,
                content_type='application/xml',
            )

        self.assertEqual(context.exception.default_code, 'worknet_remote_error')
        self.assertEqual(context.exception.http_status, 200)

    def test_normalize_xml_raises_for_work24_error_element(self):
        xml_text = '''
            <GO24>
                <error>Personal accounts cannot use this Open API.</error>
            </GO24>
        '''

        with self.assertRaises(WorknetAPIException) as context:
            WorknetService().normalize_xml_response(xml_text, http_status=200)

        self.assertEqual(context.exception.default_code, 'worknet_remote_error')

    def test_search_jobs_requires_keyword_and_valid_pagination(self):
        service = WorknetService()

        with self.assertRaises(ValidationError):
            service.search_jobs('')
        with self.assertRaises(ValidationError):
            service.search_jobs('backend', page=0)
        with self.assertRaises(ValidationError):
            service.search_jobs('backend', size='invalid')

    @patch('requests.get')
    def test_search_jobs_wraps_external_failures(self, mock_get):
        import requests

        mock_get.side_effect = requests.RequestException()

        with self.assertRaises(WorknetAPIException):
            WorknetService().search_jobs('backend')
