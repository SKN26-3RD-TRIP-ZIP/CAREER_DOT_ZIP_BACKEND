# Generated for industry talent profile fallback seeding

from django.db import migrations


# apps/analysis/services/company_service.py의 _ALLOWED_INDUSTRIES와 동일한 업종 목록.
# talent_keywords는 apps/input/migrations/0009_seed_talent_profile_catalog.py에서
# 시딩된 TalentProfileTrait.trait_name과 정확히 일치해야 fallback 조회가 매칭된다.
INDUSTRY_PROFILES = [
    (
        "IT서비스", ["기술 전문성", "문제 해결", "협업"],
        "빠른 기술 변화에 대응하고 협업을 통해 서비스를 만들어가는 역량을 중시하는 업종입니다.",
    ),
    (
        "제조업", ["품질지향", "운영 안정성", "책임감"],
        "공정 품질과 안정적인 생산 관리, 맡은 공정에 대한 책임을 중시하는 업종입니다.",
    ),
    (
        "금융/핀테크", ["신뢰성", "정직성", "윤리적 판단"],
        "신뢰와 규제 준수, 정확한 판단을 중시하는 업종입니다.",
    ),
    (
        "유통/이커머스", ["고객지향", "실행력", "적응력"],
        "빠르게 변하는 시장과 고객 요구에 민첩하게 대응하는 역량을 중시하는 업종입니다.",
    ),
    (
        "건설/엔지니어링", ["운영 안정성", "시스템 사고", "책임감"],
        "안전과 품질 기준을 지키며 전체 공정을 조율하는 역량을 중시하는 업종입니다.",
    ),
    (
        "바이오/헬스케어", ["윤리적 판단", "품질지향", "분석적 사고"],
        "엄격한 규제와 데이터 기반 검증, 윤리적 기준을 중시하는 업종입니다.",
    ),
    (
        "미디어/콘텐츠", ["창의적 사고", "커뮤니케이션", "적응력"],
        "트렌드에 민감하고 창의적인 아이디어를 빠르게 구현하는 역량을 중시하는 업종입니다.",
    ),
    (
        "컨설팅/전문서비스", ["분석적 사고", "커뮤니케이션", "문제 해결"],
        "고객 문제를 구조화하고 논리적으로 설득하는 역량을 중시하는 업종입니다.",
    ),
    (
        "공공/공기업", ["신뢰성", "정직성", "협업"],
        "공정성과 절차 준수, 이해관계자 간 협업을 중시하는 업종입니다.",
    ),
    (
        "스타트업", ["주도성", "실행력", "학습 민첩성"],
        "적은 자원으로 빠르게 시도하고 배우며 스스로 문제를 찾아 해결하는 역량을 중시하는 업종입니다. "
        "업종 분류가 불확실한 경우의 기본 fallback으로도 사용됩니다.",
    ),
]


def seed_industry_talent_profiles(apps, schema_editor):
    IndustryTalentProfile = apps.get_model("analysis", "IndustryTalentProfile")
    for industry, keywords, description in INDUSTRY_PROFILES:
        IndustryTalentProfile.objects.update_or_create(
            industry=industry,
            defaults={"talent_keywords": keywords, "description": description},
        )


def remove_industry_talent_profiles(apps, schema_editor):
    IndustryTalentProfile = apps.get_model("analysis", "IndustryTalentProfile")
    industries = [industry for industry, _, _ in INDUSTRY_PROFILES]
    IndustryTalentProfile.objects.filter(industry__in=industries).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0009_alter_generatedquestion_question_type'),
    ]

    operations = [
        migrations.RunPython(seed_industry_talent_profiles, remove_industry_talent_profiles),
    ]
