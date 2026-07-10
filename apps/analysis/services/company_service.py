"""
기업 맞춤형 컨텍스트 서비스.

회사명으로 대기업/중소기업을 판별하고, JD 텍스트에서 업종을 분류하며,
질문 생성 프롬프트에 주입할 기업 맞춤형 컨텍스트 문자열을 조립한다.
"""

import logging
from .utils import get_client
from .analysis_prompt import ALLOWED_INDUSTRIES, build_industry_classify_user

logger = logging.getLogger(__name__)


def classify_company(company_name: str) -> str:
    """회사명으로 대기업/중소기업 여부를 판별한다.

    ConglomerateCompany 테이블에서 완전일치 우선, 없으면 contains 검색.
    매칭되면 'large', 없으면 'sme'를 반환한다.
    예외 발생 시 'sme'를 반환한다 (예외 전파 금지).
    """
    try:
        from apps.analysis.models import ConglomerateCompany
        if ConglomerateCompany.objects.filter(company_name=company_name).exists():
            return "large"
        known_names = ConglomerateCompany.objects.values_list("company_name", flat=True)
        if any(name in company_name for name in known_names):
            return "large"
        return "sme"
    except Exception as e:
        logger.warning("classify_company 실패 (fallback=sme): %s", e)
        return "sme"


def get_industry_from_jd(jd_text: str) -> str:
    """JD 텍스트에서 업종을 분류한다. gpt-4o-mini 사용.

    extract_jd_requirements()가 이미 industry를 함께 추출하므로, 정상 흐름에서는
    이 함수 대신 resolve_industry()를 통해 그 결과를 재사용해야 한다.
    이 함수는 저장된 값이 없거나 유효하지 않을 때만 호출되는 재분류 fallback이다.

    반환값이 허용 목록에 없거나 예외 발생 시 '스타트업'을 반환한다.
    """
    try:
        client = get_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[{"role": "user", "content": build_industry_classify_user(jd_text)}],
        )
        result = response.choices[0].message.content.strip()
        return result if result in ALLOWED_INDUSTRIES else "스타트업"
    except Exception as e:
        logger.warning("get_industry_from_jd 실패 (fallback=스타트업): %s", e)
        return "스타트업"


def resolve_industry(stored_industry: str | None, jd_text: str) -> str:
    """extract_jd_requirements()에서 이미 추출된 industry 값을 우선 재사용한다.

    저장된 값이 없거나(레거시 분석 데이터) 허용 목록 밖이면 그때만
    get_industry_from_jd()로 새로 분류한다 — 정상 흐름에서는 AI를 다시 호출하지 않는다.
    """
    if stored_industry in ALLOWED_INDUSTRIES:
        return stored_industry
    return get_industry_from_jd(jd_text)


_DEFAULT_INDUSTRY_FALLBACK = "스타트업"


def get_industry_talent_keywords(industry: str) -> tuple[list, str | None]:
    """업종별 인재상 키워드를 조회한다.

    1) 해당 업종으로 IndustryTalentProfile을 검색한다 (검색 가능 여부 확인).
    2) 검색 결과가 없거나 키워드가 비어 있으면, 기본 업종("스타트업")으로 재검색해 fallback한다.
    3) 기본 업종에도 데이터가 없으면 빈 결과를 반환한다 (예외 전파 금지).

    반환값: (talent_keywords, 실제 매칭된 industry). 매칭 실패 시 ([], None).
    """
    from apps.analysis.models import IndustryTalentProfile

    try:
        itp = IndustryTalentProfile.objects.filter(industry=industry).first()
        if itp and itp.talent_keywords:
            return itp.talent_keywords, industry

        if industry != _DEFAULT_INDUSTRY_FALLBACK:
            itp = IndustryTalentProfile.objects.filter(industry=_DEFAULT_INDUSTRY_FALLBACK).first()
            if itp and itp.talent_keywords:
                return itp.talent_keywords, _DEFAULT_INDUSTRY_FALLBACK

        return [], None
    except Exception as e:
        logger.warning("get_industry_talent_keywords 실패 (industry=%s): %s", industry, e)
        return [], None


_SOURCE_LABEL = {
    "OFFICIAL":     "회사가 공식적으로 공개한 인재상",
    "AI_EXTRACTED": "채용공고에서 추출한 인재상 (사용자 미확정)",
    "USER_DEFINED": "사용자가 면접 연습을 위해 직접 설정한 인재상",
    "JOB_DEFAULT":  "지원 직무 기준 기본 추천 인재상",
    "HYBRID":       "공식 정보와 사용자 설정을 조합한 인재상",
}


def build_company_context(
    company_name: str,
    company_type: str,
    industry: str | None,
    confirmed_traits: list,
    talent_source: str | None = None,
    talent_summary: str = "",
    recent_trends: str = "",
) -> str:
    """질문 생성 프롬프트에 주입할 기업 맞춤형 컨텍스트를 조립한다."""
    type_label = "대기업" if company_type == "large" else "중소기업"

    header_lines = [
        "=== 기업 맞춤형 컨텍스트 ===",
        f"회사명: {company_name}",
        f"기업 유형: {type_label}",
    ]
    if company_type == "sme" and industry:
        header_lines.append(f"업종: {industry}")
    if company_type == "large" and recent_trends:
        header_lines.append("최근 동향:")
        header_lines.extend(f"  {line}" for line in recent_trends.splitlines())
    header_lines.append("============================")
    header = "\n".join(header_lines)

    if not confirmed_traits:
        return header

    source_label = _SOURCE_LABEL.get(talent_source or "", "참고 인재상")
    talent_lines = [
        "",
        f"=== 인재상 기준 ({source_label}) ===",
    ]
    if talent_source in ("AI_EXTRACTED", "JOB_DEFAULT"):
        talent_lines.append(
            "※ 아래 인재상은 회사가 공식적으로 공개한 정보가 아닙니다. "
            "질문 생성과 답변 피드백의 참고 기준으로만 사용하고, "
            "회사 공식 인재상으로 단정하지 마세요."
        )

    for item in confirmed_traits:
        trait = item.trait if hasattr(item, "trait") else item
        priority = item.priority_order if hasattr(item, "priority_order") else "-"
        custom_desc = getattr(item, "custom_description", "") or ""
        display_desc = custom_desc if custom_desc else trait.short_description
        talent_lines.append(f"{priority}순위 {trait.trait_name}: {display_desc}")

    if talent_summary:
        talent_lines.append(f"종합 설명: {talent_summary}")
    talent_lines.append("=" * 40)

    return header + "\n" + "\n".join(talent_lines)
