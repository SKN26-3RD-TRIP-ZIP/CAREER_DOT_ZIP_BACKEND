인재상 마스터 데이터 적재 순서
================================
반드시 아래 순서대로 실행해야 합니다.
(traits가 categories를 참조하기 때문에 categories를 먼저 적재해야 합니다.)

1. python manage.py loaddata apps/analysis/fixtures/talent_profile_categories.json
2. python manage.py loaddata apps/analysis/fixtures/talent_profile_traits.json
3. python manage.py loaddata apps/analysis/fixtures/conglomerate_companies.json

또는 앱 루트에서 단축 경로로:
1. python manage.py loaddata talent_profile_categories
2. python manage.py loaddata talent_profile_traits
3. python manage.py loaddata conglomerate_companies
