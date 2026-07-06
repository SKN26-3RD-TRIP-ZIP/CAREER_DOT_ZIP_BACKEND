# Generated for large-company classification seeding

from django.db import migrations


# 공정거래위원회 대기업집단 지정 기준 주요 그룹의 대표 계열사 샘플 데이터.
# 전체 대기업집단 계열사 명단(수천 개)은 공공데이터포털 등 외부 데이터 연동이 필요하며,
# 이 시드는 classify_company()의 대기업 분류 경로를 실제로 동작시키기 위한 대표 샘플이다.
CONGLOMERATE_COMPANIES = [
    ("삼성그룹", ["삼성전자", "삼성SDI", "삼성생명", "삼성물산", "삼성C&T", "삼성증권", "삼성화재", "삼성바이오로직스", "삼성엔지니어링", "삼성중공업"]),
    ("SK그룹", ["SK하이닉스", "SK텔레콤", "SK이노베이션", "SK네트웍스", "SK바이오사이언스", "SK바이오팜", "SK에코플랜트", "SK스퀘어", "SK쉴더스", "SK C&C"]),
    ("현대자동차그룹", ["현대자동차", "기아", "현대모비스", "현대제철", "현대건설", "현대글로비스", "현대로템", "현대위아", "현대카드", "이노션"]),
    ("LG그룹", ["LG전자", "LG화학", "LG유플러스", "LG디스플레이", "LG생활건강", "LG이노텍", "LG에너지솔루션", "LG헬로비전", "LG CNS"]),
    ("롯데그룹", ["롯데쇼핑", "롯데케미칼", "롯데제과", "롯데칠성음료", "롯데면세점", "롯데카드", "롯데정보통신", "롯데건설", "롯데렌탈"]),
    ("포스코그룹", ["포스코홀딩스", "포스코퓨처엠", "포스코인터내셔널", "포스코이앤씨", "포스코DX"]),
    ("한화그룹", ["한화솔루션", "한화에어로스페이스", "한화생명", "한화투자증권", "한화오션", "한화시스템", "한화갤러리아"]),
    ("GS그룹", ["GS리테일", "GS건설", "GS칼텍스", "GS EPS", "GS홈쇼핑", "GS에너지"]),
    ("신세계그룹", ["이마트", "신세계백화점", "신세계인터내셔날", "신세계푸드", "SSG닷컴", "스타벅스코리아"]),
    ("HD현대그룹", ["HD현대중공업", "HD현대오일뱅크", "HD현대일렉트릭", "HD현대인프라코어", "HD현대건설기계"]),
    ("KT그룹", ["KT", "KT스카이라이프", "KT알파", "KT클라우드", "비씨카드"]),
    ("한진그룹", ["대한항공", "진에어", "한진", "한국공항"]),
    ("CJ그룹", ["CJ제일제당", "CJ ENM", "CJ대한통운", "CJ올리브영", "CJ프레시웨이", "CJ CGV"]),
    ("두산그룹", ["두산에너빌리티", "두산밥캣", "두산로보틱스", "두산퓨얼셀"]),
    ("LS그룹", ["LS전선", "LS일렉트릭", "LS엠트론", "E1"]),
    ("카카오그룹", ["카카오", "카카오뱅크", "카카오페이", "카카오모빌리티", "카카오게임즈", "카카오엔터테인먼트"]),
    ("네이버그룹", ["네이버", "네이버클라우드", "네이버파이낸셜", "네이버웹툰"]),
    ("효성그룹", ["효성첨단소재", "효성중공업", "효성티앤씨", "효성화학"]),
    ("HDC그룹", ["HDC현대산업개발", "HDC아이앤콘스"]),
    ("셀트리온그룹", ["셀트리온", "셀트리온제약", "셀트리온헬스케어"]),
]


def seed_conglomerate_companies(apps, schema_editor):
    ConglomerateCompany = apps.get_model("analysis", "ConglomerateCompany")
    for group_name, company_names in CONGLOMERATE_COMPANIES:
        for company_name in company_names:
            ConglomerateCompany.objects.update_or_create(
                company_name=company_name,
                defaults={"group_name": group_name},
            )


def remove_conglomerate_companies(apps, schema_editor):
    ConglomerateCompany = apps.get_model("analysis", "ConglomerateCompany")
    company_names = [name for _, names in CONGLOMERATE_COMPANIES for name in names]
    ConglomerateCompany.objects.filter(company_name__in=company_names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0010_seed_industry_talent_profiles'),
    ]

    operations = [
        migrations.RunPython(seed_conglomerate_companies, remove_conglomerate_companies),
    ]
