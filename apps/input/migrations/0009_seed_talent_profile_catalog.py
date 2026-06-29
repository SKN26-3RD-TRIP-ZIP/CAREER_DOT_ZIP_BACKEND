from django.db import migrations


CATEGORIES = [
    {
        "category_code": "EXECUTION_RESPONSIBILITY",
        "category_name": "실행과 책임",
        "short_description": "목표를 행동과 결과로 연결하고 맡은 일에 끝까지 책임지는 역량",
        "detailed_description": "일의 목적을 이해하고 우선순위를 정해 실행하며 결과를 끝까지 관리하는 영역입니다.",
        "display_order": 1,
    },
    {
        "category_code": "THINKING_PROBLEM_SOLVING",
        "category_name": "사고와 문제 해결",
        "short_description": "문제를 구조화하고 근거를 바탕으로 해결책을 찾는 역량",
        "detailed_description": "복잡한 상황을 분석하고 원인을 파악해 현실적인 대안을 설계하는 영역입니다.",
        "display_order": 2,
    },
    {
        "category_code": "COLLABORATION_COMMUNICATION",
        "category_name": "협업과 커뮤니케이션",
        "short_description": "다른 사람과 정보를 맞추고 함께 성과를 만드는 역량",
        "detailed_description": "팀 안팎의 이해관계자와 명확히 소통하고 갈등을 조율하는 영역입니다.",
        "display_order": 3,
    },
    {
        "category_code": "GROWTH_ADAPTABILITY",
        "category_name": "성장과 적응",
        "short_description": "피드백과 변화 속에서 빠르게 배우고 개선하는 역량",
        "detailed_description": "새로운 환경을 학습하고 경험을 다음 행동으로 전환하는 영역입니다.",
        "display_order": 4,
    },
    {
        "category_code": "CUSTOMER_BUSINESS_VALUE",
        "category_name": "고객과 비즈니스 가치",
        "short_description": "고객 문제와 사업 목표를 연결해 가치를 만드는 역량",
        "detailed_description": "사용자, 고객, 시장의 관점에서 일의 효과를 판단하는 영역입니다.",
        "display_order": 5,
    },
    {
        "category_code": "TECHNOLOGY_QUALITY",
        "category_name": "기술과 품질",
        "short_description": "기술적 판단과 품질 기준으로 안정적인 결과물을 만드는 역량",
        "detailed_description": "기술 선택, 구현 품질, 운영 안정성을 균형 있게 관리하는 영역입니다.",
        "display_order": 6,
    },
    {
        "category_code": "LEADERSHIP_ORGANIZATION",
        "category_name": "리더십과 조직 기여",
        "short_description": "주변의 실행을 돕고 조직의 성과에 기여하는 역량",
        "detailed_description": "영향력, 의사결정, 지식 공유를 통해 팀의 생산성을 높이는 영역입니다.",
        "display_order": 7,
    },
    {
        "category_code": "TRUST_ETHICS",
        "category_name": "신뢰와 윤리",
        "short_description": "정직하고 책임 있는 태도로 신뢰를 쌓는 역량",
        "detailed_description": "보안, 윤리, 투명성, 약속 이행을 바탕으로 장기적 신뢰를 만드는 영역입니다.",
        "display_order": 8,
    },
]


TRAITS = [
    ("EXECUTION_RESPONSIBILITY", "OWNERSHIP", "주도성", "지시를 기다리지 않고 필요한 문제를 스스로 발견해 행동하는 역량", 1),
    ("EXECUTION_RESPONSIBILITY", "ACCOUNTABILITY", "책임감", "맡은 결과에 대해 끝까지 설명하고 개선하는 역량", 2),
    ("EXECUTION_RESPONSIBILITY", "EXECUTION_SPEED", "실행력", "결정된 일을 빠르게 시도하고 결과를 만드는 역량", 3),
    ("EXECUTION_RESPONSIBILITY", "RESULT_ORIENTATION", "결과지향", "활동보다 측정 가능한 결과와 영향을 중시하는 역량", 4),
    ("THINKING_PROBLEM_SOLVING", "PROBLEM_SOLVING", "문제 해결", "현상을 구조화하고 원인을 찾아 해결책을 실행하는 역량", 1),
    ("THINKING_PROBLEM_SOLVING", "ANALYTICAL_THINKING", "분석적 사고", "데이터와 근거를 바탕으로 판단하는 역량", 2),
    ("THINKING_PROBLEM_SOLVING", "CREATIVE_THINKING", "창의적 사고", "익숙한 방식 밖에서 대안을 탐색하는 역량", 3),
    ("THINKING_PROBLEM_SOLVING", "DECISION_MAKING", "의사결정", "불확실성 속에서도 기준을 세워 선택하는 역량", 4),
    ("COLLABORATION_COMMUNICATION", "COLLABORATION", "협업", "공동 목표를 위해 역할과 정보를 맞추며 일하는 역량", 1),
    ("COLLABORATION_COMMUNICATION", "COMMUNICATION", "커뮤니케이션", "상황과 상대에 맞게 명확히 전달하고 확인하는 역량", 2),
    ("COLLABORATION_COMMUNICATION", "CONFLICT_RESOLUTION", "갈등 조율", "의견 차이를 다루고 합의 가능한 방향을 찾는 역량", 3),
    ("COLLABORATION_COMMUNICATION", "EMPATHY", "공감", "상대의 관점과 제약을 이해하고 반영하는 역량", 4),
    ("GROWTH_ADAPTABILITY", "LEARNING_AGILITY", "학습 민첩성", "새 지식과 피드백을 빠르게 흡수해 적용하는 역량", 1),
    ("GROWTH_ADAPTABILITY", "ADAPTABILITY", "적응력", "변화한 조건에서도 우선순위를 재정렬하는 역량", 2),
    ("GROWTH_ADAPTABILITY", "RESILIENCE", "회복탄력성", "실패나 압박 이후 다시 실행을 이어가는 역량", 3),
    ("GROWTH_ADAPTABILITY", "GROWTH_MINDSET", "성장 마인드셋", "부족함을 인정하고 개선 계획으로 연결하는 역량", 4),
    ("CUSTOMER_BUSINESS_VALUE", "CUSTOMER_ORIENTATION", "고객지향", "고객 문제와 사용 경험을 우선 고려하는 역량", 1),
    ("CUSTOMER_BUSINESS_VALUE", "BUSINESS_IMPACT", "비즈니스 임팩트", "일의 결과가 사업 목표에 주는 영향을 판단하는 역량", 2),
    ("CUSTOMER_BUSINESS_VALUE", "VALUE_CREATION", "가치 창출", "제한된 자원으로 의미 있는 효과를 만드는 역량", 3),
    ("CUSTOMER_BUSINESS_VALUE", "SERVICE_MINDSET", "서비스 마인드", "사용자가 안정적으로 가치를 얻도록 책임지는 역량", 4),
    ("TECHNOLOGY_QUALITY", "TECHNICAL_EXCELLENCE", "기술 전문성", "기술 원리와 구현 품질을 바탕으로 문제를 해결하는 역량", 1),
    ("TECHNOLOGY_QUALITY", "QUALITY_ORIENTATION", "품질지향", "결함 예방과 검증 기준을 중요하게 여기는 역량", 2),
    ("TECHNOLOGY_QUALITY", "SYSTEM_THINKING", "시스템 사고", "전체 구조와 영향 범위를 고려해 설계하는 역량", 3),
    ("TECHNOLOGY_QUALITY", "OPERATIONAL_STABILITY", "운영 안정성", "배포 이후의 안정성과 대응 가능성을 고려하는 역량", 4),
    ("LEADERSHIP_ORGANIZATION", "LEADERSHIP", "리더십", "목표와 기준을 제시하고 주변의 실행을 돕는 역량", 1),
    ("LEADERSHIP_ORGANIZATION", "INFLUENCE", "영향력", "권한보다 신뢰와 근거로 사람을 움직이는 역량", 2),
    ("LEADERSHIP_ORGANIZATION", "MENTORING", "성장 지원", "동료의 학습과 실행을 돕는 역량", 3),
    ("LEADERSHIP_ORGANIZATION", "ORGANIZATIONAL_COMMITMENT", "조직 기여", "개인의 성과를 넘어 팀의 기준과 자산을 만드는 역량", 4),
    ("TRUST_ETHICS", "INTEGRITY", "정직성", "사실과 한계를 투명하게 말하고 책임지는 역량", 1),
    ("TRUST_ETHICS", "RELIABILITY", "신뢰성", "약속한 일을 예측 가능하게 수행하는 역량", 2),
    ("TRUST_ETHICS", "ETHICAL_JUDGMENT", "윤리적 판단", "성과와 원칙 사이에서 책임 있는 선택을 하는 역량", 3),
    ("TRUST_ETHICS", "SECURITY_AWARENESS", "보안 의식", "정보 보호와 안전한 처리 기준을 지키는 역량", 4),
]


def _trait_defaults(category, code, name, short_description, display_order):
    return {
        "category": category,
        "trait_name": name,
        "short_description": short_description,
        "detailed_description": f"{name}은 사용자가 면접 연습 기준으로 선택할 수 있는 세부 인재상입니다.",
        "positive_signals": [
            "구체적인 상황, 본인 행동, 결과가 함께 설명됨",
            "판단 기준과 개선 행동이 드러남",
        ],
        "negative_signals": [
            "의지나 성향만 있고 행동 근거가 부족함",
            "본인의 역할과 결과가 불명확함",
        ],
        "question_templates": [
            f"{name}을 보여준 경험을 상황, 행동, 결과 중심으로 설명해주세요.",
        ],
        "followup_templates": [
            "그때 본인이 직접 결정하거나 실행한 부분은 무엇이었나요?",
            "그 경험을 다음 상황에 어떻게 다시 적용할 수 있나요?",
        ],
        "evaluation_dimensions": [
            "상황 적합성",
            "본인 행동의 구체성",
            "결과 또는 변화",
            "회고와 재적용 가능성",
        ],
        "display_order": display_order,
        "is_active": True,
    }


def seed_talent_profiles(apps, schema_editor):
    category_model = apps.get_model("input", "TalentProfileCategory")
    trait_model = apps.get_model("input", "TalentProfileTrait")

    categories = {}
    for category in CATEGORIES:
        obj, _ = category_model.objects.update_or_create(
            category_code=category["category_code"],
            defaults={**category, "is_active": True},
        )
        categories[obj.category_code] = obj

    for category_code, trait_code, trait_name, short_description, display_order in TRAITS:
        category = categories[category_code]
        trait_model.objects.update_or_create(
            trait_code=trait_code,
            defaults=_trait_defaults(category, trait_code, trait_name, short_description, display_order),
        )


def deactivate_talent_profiles(apps, schema_editor):
    # User selections may reference these master rows via PROTECT. Reverse keeps
    # referential integrity by deactivating seeded data instead of deleting it.
    category_model = apps.get_model("input", "TalentProfileCategory")
    trait_model = apps.get_model("input", "TalentProfileTrait")
    trait_codes = [trait[1] for trait in TRAITS]
    category_codes = [category["category_code"] for category in CATEGORIES]
    trait_model.objects.filter(trait_code__in=trait_codes).update(is_active=False)
    category_model.objects.filter(category_code__in=category_codes).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("input", "0008_jdtalentprofile_talentprofilecategory_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_talent_profiles, deactivate_talent_profiles),
    ]
