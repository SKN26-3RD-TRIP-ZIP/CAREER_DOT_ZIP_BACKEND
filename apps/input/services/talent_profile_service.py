USER_DEFINED_NOTICE = (
    '아래 인재상은 회사가 공식적으로 공개한 정보가 아니라\n'
    '사용자가 면접 연습을 위해 직접 설정한 기준입니다.\n\n'
    '회사 공식 인재상으로 단정하지 말고\n'
    '질문 생성과 답변 피드백의 참고 기준으로만 사용하세요.'
)


AI_EXTRACTED_NOTICE = (
    '아래 인재상은 JD 또는 사용자 입력에서 추출된 자유 텍스트 요약입니다. '
    '회사 공식 인재상으로 단정하지 말고 참고 기준으로만 사용하세요.'
)


def _selected_profile_to_dict(profile):
    items = []
    for item in profile.items.select_related('trait', 'trait__category').order_by('priority_order'):
        description = item.custom_description or item.trait.short_description
        items.append(
            {
                'trait_code': item.trait.trait_code,
                'trait_name': item.trait.trait_name,
                'category_code': item.trait.category.category_code,
                'category_name': item.trait.category.category_name,
                'priority_order': item.priority_order,
                'description': description,
            }
        )

    return {
        'source_type': profile.source_type,
        'is_official': profile.source_type == 'OFFICIAL',
        'confirmed_by_user': profile.confirmed_by_user,
        'summary': profile.custom_summary or profile.source_text or '',
        'items': items,
        'prompt_notice': USER_DEFINED_NOTICE if profile.source_type == 'USER_DEFINED' else '',
    }


def resolve_effective_talent_profile(jd):
    """Return the talent profile context that should be used downstream.

    Priority:
    1. Confirmed structured profile.
    2. Existing JobDescription.talent_profile free text.
    3. Empty fallback.
    """
    if jd is None:
        return {
            'source_type': None,
            'is_official': False,
            'confirmed_by_user': False,
            'summary': '',
            'items': [],
            'prompt_notice': '',
        }

    profile = getattr(jd, 'custom_talent_profile', None)
    if profile and profile.confirmed_by_user:
        return _selected_profile_to_dict(profile)

    fallback = (getattr(jd, 'talent_profile', None) or '').strip()
    if fallback:
        return {
            'source_type': 'AI_EXTRACTED',
            'is_official': False,
            'confirmed_by_user': False,
            'summary': fallback,
            'items': [],
            'prompt_notice': AI_EXTRACTED_NOTICE,
        }

    return {
        'source_type': None,
        'is_official': False,
        'confirmed_by_user': False,
        'summary': '',
        'items': [],
        'prompt_notice': '',
    }
