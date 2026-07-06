import pytest

from apps.analysis.services.company_service import classify_company, get_industry_talent_keywords


@pytest.mark.django_db
class TestClassifyCompany:
    def test_대기업집단_계열사는_large를_반환한다(self):
        assert classify_company("삼성전자") == "large"

    def test_계열사명을_포함한_입력도_large로_매칭된다(self):
        assert classify_company("주식회사 삼성전자") == "large"

    def test_대기업집단에_없는_회사는_sme를_반환한다(self):
        assert classify_company("존재하지않는스타트업") == "sme"


@pytest.mark.django_db
class TestGetIndustryTalentKeywords:
    def test_존재하는_업종은_해당_업종_키워드를_반환한다(self):
        keywords, matched_industry = get_industry_talent_keywords("IT서비스")

        assert matched_industry == "IT서비스"
        assert keywords

    def test_존재하지_않는_업종은_스타트업으로_fallback한다(self):
        keywords, matched_industry = get_industry_talent_keywords("존재하지않는업종")

        assert matched_industry == "스타트업"
        assert keywords

    def test_스타트업_자체_조회는_그대로_반환된다(self):
        keywords, matched_industry = get_industry_talent_keywords("스타트업")

        assert matched_industry == "스타트업"
        assert keywords
