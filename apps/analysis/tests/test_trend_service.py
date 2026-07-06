from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from apps.analysis.services.trend_service import get_company_recent_trends


class TestGetCompanyRecentTrends(TestCase):
    @override_settings(TAVILY_API_KEY="")
    def test_api_key_미설정시_빈문자열을_반환한다(self):
        self.assertEqual(get_company_recent_trends("삼성전자"), "")

    @override_settings(TAVILY_API_KEY="test-key")
    def test_회사명이_없으면_빈문자열을_반환한다(self):
        self.assertEqual(get_company_recent_trends(""), "")

    @override_settings(TAVILY_API_KEY="test-key")
    @patch("requests.post")
    def test_검색_결과를_요약해서_반환한다(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "results": [
                {"title": "삼성전자, 신규 채용 확대", "content": "삼성전자가 하반기 공채를 확대한다고 밝혔다."},
                {"title": "삼성전자 실적 발표", "content": ""},
            ]
        }
        response.raise_for_status = Mock()
        mock_post.return_value = response

        result = get_company_recent_trends("삼성전자")

        self.assertIn("삼성전자, 신규 채용 확대", result)
        self.assertIn("삼성전자 실적 발표", result)
        mock_post.assert_called_once()

    @override_settings(TAVILY_API_KEY="test-key")
    @patch("requests.post")
    def test_api_실패시_예외를_전파하지_않고_빈문자열을_반환한다(self, mock_post):
        import requests

        mock_post.side_effect = requests.RequestException("timeout")

        self.assertEqual(get_company_recent_trends("삼성전자"), "")

    @override_settings(TAVILY_API_KEY="test-key")
    @patch("requests.post")
    def test_검색_결과가_없으면_빈문자열을_반환한다(self, mock_post):
        response = Mock()
        response.json.return_value = {"results": []}
        response.raise_for_status = Mock()
        mock_post.return_value = response

        self.assertEqual(get_company_recent_trends("삼성전자"), "")
