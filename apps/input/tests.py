import json

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.question_bank.models import QuestionBankItem
from apps.question_bank.services.question_selector import select_questions_from_bank

from .models import JobDescription


class JDDropdownCreateTests(APITestCase):
    """드롭다운 + 직접입력 기반 JD 생성 테스트"""

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='test@example.com',
            password='password123',
            name='Tester',
        )
        self.client.force_authenticate(self.user)
        self.url = reverse('jd-list-create')

    def test_dropdown_input_creates_jd(self):
        """드롭다운 + 직접입력으로 JD 생성 성공 및 original_text/keywords 검증"""
        payload = {
            'company_name': 'Career.zip',
            'position': 'Backend Developer',
            'job_category': 'backend',
            'experience_level': 'junior',
            'tech_stacks': ['Python', 'Django', 'MySQL'],
            'custom_tech_stacks': ['DRF'],
            'main_tasks': 'Django REST Framework 기반 API 개발',
            'requirements': 'REST API 설계 경험, MySQL 사용 경험',
            'preferences': 'AWS 배포 경험 우대',
            'jd_text': '소규모 애자일 팀에서 백엔드 개발',
            'custom_keywords': ['API', '인증', '배포'],
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        jd = JobDescription.objects.get(user=self.user)

        # original_text에 구조화된 섹션 포함 확인
        self.assertIn('[직무 카테고리] backend', jd.original_text)
        self.assertIn('[경력 구분] junior', jd.original_text)
        self.assertIn('[기술스택]', jd.original_text)
        self.assertIn('Python', jd.original_text)
        self.assertIn('DRF', jd.original_text)
        self.assertIn('[주요업무]', jd.original_text)
        self.assertIn('[자격요건]', jd.original_text)
        self.assertIn('[우대사항]', jd.original_text)
        self.assertIn('[추가 설명]', jd.original_text)

        # keywords에 카테고리, 경력, 기술스택, 직접입력 키워드 포함 확인
        keywords = json.loads(jd.keywords)
        self.assertIn('backend', keywords)
        self.assertIn('junior', keywords)
        self.assertIn('Python', keywords)
        self.assertIn('Django', keywords)
        self.assertIn('MySQL', keywords)
        self.assertIn('DRF', keywords)
        self.assertIn('API', keywords)
        self.assertIn('인증', keywords)
        self.assertIn('배포', keywords)

        # 중복 키워드 없음 확인
        self.assertEqual(len(keywords), len(set(keywords)))

        # job_requirements에 requirements 저장 확인
        self.assertIsNotNone(jd.job_requirements)
        self.assertIn('REST API', jd.job_requirements)

    def test_list_returns_dropdown_fields_for_jd_cards(self):
        """목록 카드가 원문의 구조화 필드를 표시할 수 있도록 값을 반환한다."""
        payload = {
            'company_name': 'Career.zip',
            'position': 'Backend Developer',
            'job_category': 'backend',
            'experience_level': 'junior',
            'tech_stacks': ['Python', 'Django'],
            'custom_tech_stacks': ['DRF'],
        }
        create_response = self.client.post(self.url, payload, format='json')
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        items = response.data.get('results', response.data)
        self.assertEqual(items[0]['job_category'], 'backend')
        self.assertEqual(items[0]['experience_level'], 'junior')
        self.assertEqual(items[0]['tech_stacks'], ['Python', 'Django', 'DRF'])

    def test_existing_manual_original_text_method(self):
        """기존 original_text 직접입력 방식이 그대로 동작하는지 확인"""
        payload = {
            'company_name': 'OldCo',
            'position': 'Frontend Developer',
            'original_text': '기존 방식으로 입력한 JD 원문입니다.',
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        jd = JobDescription.objects.get(user=self.user)
        self.assertEqual(jd.original_text, '기존 방식으로 입력한 JD 원문입니다.')
        self.assertIsNone(jd.keywords)

    def test_empty_lists_and_optional_fields_are_safe(self):
        """빈 배열 및 선택 필드 미입력 시 오류 없이 생성"""
        payload = {
            'company_name': 'SafeCo',
            'position': 'Data Engineer',
            'job_category': 'data',
            'tech_stacks': [],
            'custom_tech_stacks': [],
            'custom_keywords': [],
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        jd = JobDescription.objects.get(user=self.user)
        self.assertIn('[직무 카테고리] data', jd.original_text)
        keywords = json.loads(jd.keywords)
        self.assertIn('data', keywords)

    def test_missing_all_inputs_returns_validation_error(self):
        """original_text도 드롭다운 입력도 없으면 400 반환"""
        payload = {
            'company_name': 'NoCo',
            'position': 'Developer',
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_original_text_and_dropdown_are_merged(self):
        """original_text와 드롭다운 입력이 함께 오면 병합"""
        payload = {
            'company_name': 'MergeCo',
            'position': 'Fullstack Developer',
            'job_category': 'fullstack',
            'tech_stacks': ['React', 'Node.js'],
            'original_text': '기존 JD 원문도 유지됩니다.',
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        jd = JobDescription.objects.get(user=self.user)
        self.assertIn('[직무 카테고리] fullstack', jd.original_text)
        self.assertIn('기존 JD 원문도 유지됩니다.', jd.original_text)


class JDQuestionBankIntegrationTests(APITestCase):
    """JD keywords → question_bank 매칭 연동 테스트"""

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='qb_test@example.com',
            password='password123',
            name='QBTester',
        )
        self.client.force_authenticate(self.user)
        self.url = reverse('jd-list-create')

    def _create_question_bank_item(self, question_text, question_type, keywords):
        return QuestionBankItem.objects.create(
            question_text=question_text,
            question_type=question_type,
            difficulty='medium',
            keywords=keywords,
            source_file='test.json',
            source_ref=f'test-{question_text[:10]}',
        )

    def test_jd_keywords_matched_by_question_bank(self):
        """생성된 JD의 keywords 기반으로 question_bank 질문이 반환되는지 확인"""
        self._create_question_bank_item(
            question_text='Python과 Django를 사용한 REST API 개발 경험을 설명해주세요.',
            question_type='technical',
            keywords=['Python', 'Django', 'API'],
        )
        self._create_question_bank_item(
            question_text='팀 협업에서 갈등을 해결한 경험을 말씀해주세요.',
            question_type='personality',
            keywords=['팀워크', '소통'],
        )

        jd_keywords = ['backend', 'junior', 'Python', 'Django', 'MySQL', 'API']

        results = select_questions_from_bank(
            jd_keywords=jd_keywords,
            interview_type='technical',
            question_count=3,
        )

        self.assertGreater(len(results), 0)
        for result in results:
            self.assertEqual(result['source_type'], 'question_bank')
            self.assertIn('question_text', result)
            self.assertIn('source_reference', result)

    def test_question_bank_returns_per_interview_type(self):
        """interview_type별로 question_bank 결과가 깨지지 않는지 확인"""
        self._create_question_bank_item(
            question_text='기술적 역량을 보여주는 프로젝트를 설명해주세요.',
            question_type='technical',
            keywords=['backend', 'Python'],
        )
        self._create_question_bank_item(
            question_text='본인의 강점을 구체적인 사례와 함께 설명해주세요.',
            question_type='personality',
            keywords=['강점', '리더십'],
        )

        jd_keywords = ['backend', 'Python']

        for interview_type in ('technical', 'personality', 'comprehensive'):
            with self.subTest(interview_type=interview_type):
                results = select_questions_from_bank(
                    jd_keywords=jd_keywords,
                    interview_type=interview_type,
                    question_count=2,
                )
                self.assertIsInstance(results, list)
                for result in results:
                    self.assertEqual(result['source_type'], 'question_bank')
