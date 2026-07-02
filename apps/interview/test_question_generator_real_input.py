import json

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.analysis.models import AnalysisSession, GeneratedQuestion, JdAnalysis
from apps.input.models import (
    CoverLetter,
    CoverLetterItem,
    JobDescription,
    JDTalentProfile,
    JDTalentProfileItem,
    ProjectExperience,
    ResumeCareer,
    ResumeMaster,
    ResumeSkill,
    TalentProfileCategory,
    TalentProfileTrait,
)
from apps.interview.models import InterviewQuestion, InterviewSession, QuestionSourceTag
from apps.interview.services.ai_chain_openai_engine import AIChainOpenAIError
from apps.interview.services.question_generator import (
    _build_ai_generation_payload,
    generate_interview_questions,
)


class InterviewQuestionCategoryDistributionTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='category-owner@example.com',
            password='password123',
            name='Category Owner',
        )

    def create_session(self, interview_type):
        return InterviewSession.objects.create(
            user=self.user,
            interview_type=interview_type,
            persona='practical',
            total_question_count=5,
        )

    def test_question_generation_payload_contains_canonical_persona_policy(self):
        expected_personas = {
            'coach': 'coach',
            'friendly': 'coach',
            'practical': 'practical',
            'verifier': 'verifier',
            'verify': 'verifier',
        }

        for stored_persona, canonical_persona in expected_personas.items():
            session = self.create_session('technical')
            session.persona = stored_persona
            payload = _build_ai_generation_payload(session, 3)

            self.assertEqual(
                payload['persona']['persona_type'],
                canonical_persona,
            )
            self.assertIn('question_focus', payload['persona']['policy'])
            self.assertIn('followup_style', payload['persona']['policy'])
            self.assertIn('feedback_tone', payload['persona']['policy'])
            self.assertIn('verification_depth', payload['persona']['policy'])
            self.assertIn('forbidden_tone', payload['persona']['policy'])

    def generate_with_empty_ai_sources(self, session):
        ai_result = {
            'session_id': str(session.id),
            'questions': [
                {
                    'client_question_key': f'q_{index:03d}',
                    'question_text': f'Generated question {index}',
                    'question_type': 'main',
                    'difficulty': 'medium',
                    'order_index': index,
                    'source_tags': [{'source_type': 'general'}],
                }
                for index in range(1, 6)
            ],
        }

        with patch('apps.interview.services.question_generator.InterviewAIChainService') as service_class, \
                patch('apps.interview.services.question_generator.select_questions_for_session') as selector:
            service = service_class.return_value
            service.generate_questions.return_value = ai_result
            selector.return_value = []
            questions = generate_interview_questions(session)

        return questions, service.generate_questions.call_args.args[0]

    def test_technical_interview_generates_all_technical_categories(self):
        questions, payload = self.generate_with_empty_ai_sources(
            self.create_session('technical')
        )

        self.assertEqual([q['question_category'] for q in questions], ['technical'] * 5)
        self.assertEqual(
            payload['generation_options']['question_category_plan'],
            ['technical'] * 5,
        )

    def test_personality_interview_generates_all_personality_categories(self):
        questions, payload = self.generate_with_empty_ai_sources(
            self.create_session('personality')
        )

        self.assertEqual([q['question_category'] for q in questions], ['personality'] * 5)
        self.assertEqual(
            payload['generation_options']['question_category_plan'],
            ['personality'] * 5,
        )

    def test_comprehensive_interview_generates_three_to_two_mix(self):
        questions, payload = self.generate_with_empty_ai_sources(
            self.create_session('comprehensive')
        )

        categories = [q['question_category'] for q in questions]
        self.assertEqual(categories.count('technical'), 3)
        self.assertEqual(categories.count('personality'), 2)
        self.assertEqual(
            payload['generation_options']['question_category_plan'],
            ['technical', 'technical', 'technical', 'personality', 'personality'],
        )


class InterviewQuestionGeneratorRealInputTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='real-input-owner@example.com',
            password='password123',
            name='Real Input Owner',
        )
        self.jd = JobDescription.objects.create(
            user=self.user,
            company_name='Career Zip',
            position='Backend Developer',
            original_text='Django REST Framework와 OpenAI API 연동 경험을 요구합니다.',
            job_requirements='Django API 설계, LLM 연동, 협업 경험',
            keywords='Django, DRF, OpenAI, REST API',
        )
        self.resume = ResumeMaster.objects.create(
            user=self.user,
            name='Real Input Owner',
            email='real-input-owner@example.com',
            github_url='https://github.com/example',
            original_text='Django 기반 API와 AI Chain을 구현했습니다.',
            extracted_keywords='Django, API, AI Chain',
        )
        ResumeSkill.objects.create(
            resume=self.resume,
            name='Django',
        )
        ResumeCareer.objects.create(
            resume=self.resume,
            company_name='Sample Company',
            position='Backend Intern',
            description='REST API 개발 및 테스트를 담당했습니다.',
        )
        self.cover_letter = CoverLetter.objects.create(
            user=self.user,
            jd=self.jd,
            title='Career Zip 지원 자기소개서',
            company_name='Career Zip',
        )
        CoverLetterItem.objects.create(
            cover_letter=self.cover_letter,
            question='프로젝트 경험을 설명해주세요.',
            answer_text='AI 모의면접 프로젝트에서 질문 생성과 꼬리질문 생성을 담당했습니다.',
            order_index=1,
        )
        ProjectExperience.objects.create(
            user=self.user,
            project_name='AI Mock Interview',
            description='AI 기반 모의면접 서비스',
            contribution='질문 생성, 답변 평가, 꼬리질문 생성 API 구현',
            tech_stack=['Django', 'OpenAI', 'DRF'],
            github_url='https://github.com/example/ai-interview',
        )
        self.analysis = JdAnalysis.objects.create(
            user=self.user,
            jd=self.jd,
            resume=self.resume,
            cover_letter=self.cover_letter,
            match_score=85.0,
            jd_keywords={'tech_keywords': ['Django', 'OpenAI'], 'trait_keywords': ['협업']},
            resume_analysis={'projects': ['AI Mock Interview']},
        )
        self.prepared_question = GeneratedQuestion.objects.create(
            jd_analysis=self.analysis,
            question_type='technical',
            question_text='분석 단계에서 생성된 Django API 설계 질문입니다.',
            source='combined',
            source_ref='JD(Django) + 프로젝트(AI Mock Interview)',
            order=1,
            answer={'summary': 'Django API 설계 경험 요약'},
        )
        self.session = InterviewSession.objects.create(
            user=self.user,
            jd=self.jd,
            resume=self.resume,
            cover_letter=self.cover_letter,
            interview_type='technical',
            persona='practical',
            total_question_count=3,
        )

    def test_real_input_and_prepared_questions_are_passed_to_ai_chain_first(self):
        ai_result = {
            'session_id': str(self.session.id),
            'questions': [
                {
                    'client_question_key': 'q_001',
                    'question_text': 'JD에 있는 Django REST API 요구사항과 본인 경험을 연결해서 설명해주세요.',
                    'question_type': 'main',
                    'difficulty': 'medium',
                    'order_index': 1,
                    'generation_reason': 'JD 요구사항과 이력서 경험 연결 확인',
                    'source_tags': [
                        {
                            'source_type': 'job_description',
                            'source_label': 'JD 기반',
                            'source_text_excerpt': 'Django REST Framework와 OpenAI API 연동 경험',
                        }
                    ],
                },
                {
                    'client_question_key': 'q_002',
                    'question_text': 'AI 모의면접 프로젝트에서 본인이 맡은 기여를 구체적으로 설명해주세요.',
                    'question_type': 'main',
                    'difficulty': 'medium',
                    'order_index': 2,
                    'generation_reason': '프로젝트 기여도 확인',
                    'source_tags': [
                        {
                            'source_type': 'project',
                            'source_label': '프로젝트 경험 기반',
                            'source_text_excerpt': '질문 생성, 답변 평가, 꼬리질문 생성 API 구현',
                        }
                    ],
                },
            ],
            'fallback_used': False,
        }

        with patch('apps.interview.services.question_generator.InterviewAIChainService') as service_class, \
                patch('apps.interview.services.question_generator.select_questions_for_session') as selector:
            service = service_class.return_value
            service.generate_questions.return_value = ai_result

            questions = generate_interview_questions(self.session)

        self.assertEqual(len(questions), 3)
        self.assertEqual(questions[0]['question_type'], 'main')
        self.assertEqual(questions[0]['question_category'], 'technical')
        self.assertEqual(questions[0]['source_type'], 'jd')
        self.assertEqual(questions[1]['source_type'], 'project_experience')
        self.assertEqual(questions[2]['source_type'], 'combined')
        self.assertEqual(questions[2]['question_category'], 'technical')
        self.assertIn('analysis_generated_question', questions[2]['source_reference'])

        selector.assert_not_called()

        payload = service.generate_questions.call_args.args[0]
        self.assertEqual(payload['session_id'], str(self.session.id))
        self.assertTrue(payload['generation_options']['prefer_input_sources'])
        self.assertTrue(payload['generation_options']['use_prepared_questions_as_reference'])
        self.assertEqual(
            payload['input_sources']['job_description']['original_text'],
            self.jd.original_text,
        )
        self.assertEqual(
            payload['input_sources']['resume']['skills'][0]['skill_name'],
            'Django',
        )
        self.assertEqual(
            payload['input_sources']['cover_letter']['items'][0]['answer_text'],
            'AI 모의면접 프로젝트에서 질문 생성과 꼬리질문 생성을 담당했습니다.',
        )
        self.assertEqual(
            payload['input_sources']['project_experiences'][0]['project_name'],
            'AI Mock Interview',
        )
        self.assertEqual(
            payload['input_sources']['prepared_questions'][0]['question_text'],
            self.prepared_question.question_text,
        )

    def test_selected_project_ids_limit_project_input_sources(self):
        other_project = ProjectExperience.objects.create(
            user=self.user,
            project_name='Unselected Project',
            description='선택하지 않은 프로젝트',
            contribution='프론트엔드 구현',
            tech_stack=['React'],
            github_url='https://github.com/example/unselected',
        )
        selected_project = ProjectExperience.objects.get(
            user=self.user,
            project_name='AI Mock Interview',
        )
        self.session._project_ids = [str(selected_project.id)]

        payload = _build_ai_generation_payload(self.session, 3)

        project_sources = payload['input_sources']['project_experiences']
        self.assertEqual(len(project_sources), 1)
        self.assertEqual(project_sources[0]['project_id'], str(selected_project.id))
        self.assertEqual(project_sources[0]['project_name'], 'AI Mock Interview')
        self.assertEqual(project_sources[0]['github_url'], 'https://github.com/example/ai-interview')
        self.assertIn('period', project_sources[0])
        self.assertEqual(
            payload['generation_options']['selected_project_ids'],
            [str(selected_project.id)],
        )
        self.assertNotEqual(project_sources[0]['project_id'], str(other_project.id))

    def test_without_selected_project_ids_keeps_all_project_sources(self):
        ProjectExperience.objects.create(
            user=self.user,
            project_name='Second Project',
            description='두 번째 프로젝트',
            contribution='API 구현',
            tech_stack=['FastAPI'],
            github_url='https://github.com/example/second',
        )

        payload = _build_ai_generation_payload(self.session, 3)

        project_names = {
            project['project_name']
            for project in payload['input_sources']['project_experiences']
        }
        self.assertIn('AI Mock Interview', project_names)
        self.assertIn('Second Project', project_names)
        self.assertEqual(payload['generation_options']['selected_project_ids'], [])

    def test_github_summary_is_added_to_payload_and_generation_metadata(self):
        github_summary = {
            'project_name': 'AI Mock Interview',
            'project_overview': 'README 기반 AI 모의면접 서비스',
            'tech_stack': ['Django', 'OpenAI'],
            'key_features': ['질문 생성', '꼬리질문 생성'],
            'technical_challenges': ['LLM 응답 안정화'],
            'architecture': 'Django API + OpenAI',
            'interview_points': ['프롬프트 메타데이터 설계'],
        }
        self.analysis.github_url = 'https://github.com/example/ai-interview'
        self.analysis.github_summary = github_summary
        self.analysis.save(update_fields=['github_url', 'github_summary'])

        ai_result = {
            'session_id': str(self.session.id),
            'generation_source': 'openai',
            'questions': [
                {
                    'client_question_key': 'q_github',
                    'question_text': 'README에 적힌 꼬리질문 생성 기능을 실제로 어떻게 구현했나요?',
                    'question_type': 'main',
                    'question_category': 'technical',
                    'order_index': 1,
                    'source_tags': [
                        {
                            'source_type': 'project_experience',
                            'source_label': 'github_readme_context',
                            'source_text_excerpt': '꼬리질문 생성',
                            'source_reference': 'https://github.com/example/ai-interview',
                        }
                    ],
                }
            ],
        }

        with patch('apps.interview.services.question_generator.InterviewAIChainService') as service_class, \
                patch('apps.interview.services.question_generator.select_questions_for_session') as selector:
            service = service_class.return_value
            service.generate_questions.return_value = ai_result
            selector.return_value = []

            questions = generate_interview_questions(self.session)

        payload = service.generate_questions.call_args.args[0]
        github_context = payload['input_sources']['github_readme_context']
        self.assertEqual(github_context['source_table'], 'jd_analysis')
        self.assertEqual(github_context['jd_analysis_id'], str(self.analysis.id))
        self.assertEqual(github_context['github_url'], 'https://github.com/example/ai-interview')
        self.assertEqual(github_context['github_summary'], github_summary)
        self.assertEqual(github_context['project_name'], 'AI Mock Interview')
        self.assertTrue(payload['generation_options']['github_readme_context_included'])

        readme_tag = next(
            tag for tag in questions[0]['source_tags']
            if tag['source_label'] == 'github_readme_context'
        )
        self.assertEqual(readme_tag['source_type'], 'project_experience')

        metadata_tag = next(
            tag for tag in questions[0]['source_tags']
            if tag['source_label'] == 'generation_metadata'
        )
        metadata = json.loads(metadata_tag['source_text_excerpt'])
        self.assertTrue(metadata['github_readme_context_included'])
        self.assertTrue(metadata['project_deepdive_enabled'])

    def test_confirmed_talent_profile_adds_generation_metadata_flags(self):
        category = TalentProfileCategory.objects.create(
            category_code='TEST_WORK_STYLE',
            category_name='일하는 방식',
            short_description='업무 수행 방식',
            display_order=1,
        )
        ownership = TalentProfileTrait.objects.create(
            category=category,
            trait_code='TEST_OWNERSHIP',
            trait_name='주도성',
            short_description='문제를 주도적으로 정의하고 해결합니다.',
            detailed_description='프로젝트와 기술 선택에서 주도적으로 판단한 근거를 확인합니다.',
            display_order=1,
        )
        collaboration = TalentProfileTrait.objects.create(
            category=category,
            trait_code='TEST_COLLABORATION',
            trait_name='협업',
            short_description='동료와 효과적으로 협업합니다.',
            detailed_description='협업 상황에서의 조율과 커뮤니케이션을 확인합니다.',
            display_order=2,
        )
        profile = JDTalentProfile.objects.create(
            jd=self.jd,
            source_type=JDTalentProfile.SOURCE_TYPE_USER_DEFINED,
            custom_summary='사용자가 확정한 JD 인재상',
            confirmed_by_user=True,
        )
        JDTalentProfileItem.objects.create(
            jd_talent_profile=profile,
            trait=collaboration,
            priority_order=2,
        )
        JDTalentProfileItem.objects.create(
            jd_talent_profile=profile,
            trait=ownership,
            priority_order=1,
        )
        ai_result = {
            'session_id': str(self.session.id),
            'generation_source': 'openai',
            'questions': [
                {
                    'client_question_key': 'q_talent',
                    'question_text': '프로젝트에서 주도성이 드러난 기술 선택 사례를 설명해주세요.',
                    'question_type': 'main',
                    'question_category': 'personality',
                    'order_index': 1,
                    'source_tags': [
                        {
                            'source_type': 'jd',
                            'source_label': 'effective_talent_profile',
                            'source_text_excerpt': 'TEST_OWNERSHIP',
                        }
                    ],
                }
            ],
        }

        with patch('apps.interview.services.question_generator.InterviewAIChainService') as service_class, \
                patch('apps.interview.services.question_generator.select_questions_for_session') as selector:
            service = service_class.return_value
            service.generate_questions.return_value = ai_result
            selector.return_value = []

            questions = generate_interview_questions(self.session)

        payload = service.generate_questions.call_args.args[0]
        talent_profile = payload['input_sources']['job_description']['effective_talent_profile']
        self.assertTrue(talent_profile['confirmed_by_user'])
        self.assertEqual(
            [item['trait_code'] for item in talent_profile['items']],
            ['TEST_OWNERSHIP', 'TEST_COLLABORATION'],
        )
        self.assertIn(
            '면접 연습',
            payload['input_sources']['job_description']['talent_profile_prompt_notice'],
        )

        metadata_tag = next(
            tag for tag in questions[0]['source_tags']
            if tag['source_label'] == 'generation_metadata'
        )
        metadata = json.loads(metadata_tag['source_text_excerpt'])
        self.assertTrue(metadata['talent_profile_included'])
        self.assertTrue(metadata['talent_profile_confirmed_by_user'])

    def test_ai_question_prompt_metadata_is_added_to_source_tags(self):
        ai_result = {
            'session_id': str(self.session.id),
            'generation_source': 'openai',
            'prompt_type': 'question_generation',
            'prompt_source': 'db',
            'prompt_template_id': 12,
            'prompt_template_name': 'Practical question prompt',
            'prompt_version_id': 34,
            'prompt_version_label': 'v3',
            'is_active_prompt_version': True,
            'questions': [
                {
                    'client_question_key': 'q_001',
                    'question_text': 'DB prompt metadata question.',
                    'question_type': 'main',
                    'question_category': 'technical',
                    'order_index': 1,
                    'source_tags': [{'source_type': 'general'}],
                }
            ],
        }

        with patch('apps.interview.services.question_generator.InterviewAIChainService') as service_class, \
                patch('apps.interview.services.question_generator.select_questions_for_session') as selector:
            service = service_class.return_value
            service.generate_questions.return_value = ai_result
            selector.return_value = []

            questions = generate_interview_questions(self.session)

        metadata_tag = next(
            tag for tag in questions[0]['source_tags']
            if tag['source_label'] == 'generation_metadata'
        )
        metadata = json.loads(metadata_tag['source_text_excerpt'])
        self.assertEqual(metadata['generation_source'], 'openai')
        self.assertEqual(metadata['prompt_type'], 'question_generation')
        self.assertEqual(metadata['prompt_source'], 'db')
        self.assertEqual(metadata['prompt_template_id'], 12)
        self.assertEqual(metadata['prompt_template_name'], 'Practical question prompt')
        self.assertEqual(metadata['prompt_version_id'], 34)
        self.assertEqual(metadata['prompt_version_label'], 'v3')
        self.assertTrue(metadata['is_active_prompt_version'])
        self.assertEqual(metadata['persona'], 'practical')

    def test_question_bank_is_used_after_ai_and_prepared_questions(self):
        self.session.total_question_count = 4
        self.session.save(update_fields=['total_question_count'])

        ai_result = {
            'session_id': str(self.session.id),
            'questions': [
                {
                    'client_question_key': 'q_001',
                    'question_text': 'JD 요구사항과 본인 경험을 연결해서 설명해주세요.',
                    'question_type': 'main',
                    'difficulty': 'medium',
                    'order_index': 1,
                    'generation_reason': 'JD 기반 질문',
                    'source_tags': [
                        {
                            'source_type': 'job_description',
                            'source_label': 'JD 기반',
                            'source_text_excerpt': 'Django API 설계',
                        }
                    ],
                }
            ],
            'fallback_used': False,
        }

        with patch('apps.interview.services.question_generator.InterviewAIChainService') as service_class, \
                patch('apps.interview.services.question_generator.select_questions_for_session') as selector:
            service = service_class.return_value
            service.generate_questions.return_value = ai_result
            selector.return_value = [
                {
                    'question_text': '질문은행에서 보충된 기술 질문입니다.',
                    'source_type': 'question_bank',
                    'source_reference': 'question_bank:item-001',
                }
            ]

            questions = generate_interview_questions(self.session)

        self.assertEqual(len(questions), 4)
        self.assertEqual(questions[0]['source_type'], 'jd')
        self.assertEqual(questions[1]['source_type'], 'combined')
        self.assertEqual(questions[2]['source_type'], 'question_bank')
        self.assertEqual(questions[3]['source_type'], 'rule')
        generation_sources = []
        for question in questions:
            metadata_tag = next(
                tag for tag in question['source_tags']
                if tag['source_label'] == 'generation_metadata'
            )
            generation_sources.append(
                json.loads(metadata_tag['source_text_excerpt'])['generation_source']
            )
        self.assertEqual(
            generation_sources,
            ['unknown_ai', 'prepared_question', 'question_bank', 'rule_fallback'],
        )
        selector.assert_called_once_with(self.session, 2)

    def test_ai_generation_failure_uses_prepared_bank_and_rule_fallback(self):
        self.session.total_question_count = 3
        self.session.save(update_fields=['total_question_count'])

        with patch('apps.interview.services.question_generator.InterviewAIChainService') as service_class, \
                patch('apps.interview.services.question_generator.select_questions_for_session') as selector:
            service = service_class.return_value
            service.generate_questions.side_effect = AIChainOpenAIError(
                'question_generation',
                'invalid json',
            )
            selector.return_value = [
                {
                    'question_text': 'OpenAI ?ㅽ뙣 ??question bank fallback 吏덈Ц?낅땲??',
                    'source_type': 'question_bank',
                    'source_reference': 'question_bank:item-fallback',
                }
            ]

            questions = generate_interview_questions(self.session)

        self.assertEqual(len(questions), 3)
        self.assertEqual(questions[0]['source_type'], 'combined')
        self.assertEqual(questions[1]['source_type'], 'question_bank')
        self.assertEqual(questions[2]['source_type'], 'rule')
        selector.assert_called_once_with(self.session, 2)

        metadata_by_source = {}
        for question in questions:
            metadata_tag = next(
                tag for tag in question['source_tags']
                if tag['source_label'] == 'generation_metadata'
            )
            metadata_by_source[question['source_type']] = json.loads(
                metadata_tag['source_text_excerpt']
            )

        self.assertEqual(
            metadata_by_source['combined']['generation_source'],
            'prepared_question',
        )
        self.assertEqual(
            metadata_by_source['question_bank']['generation_source'],
            'question_bank',
        )
        self.assertEqual(
            metadata_by_source['rule']['generation_source'],
            'rule_fallback',
        )
        for metadata in metadata_by_source.values():
            self.assertTrue(metadata['ai_generation_failed'])
            self.assertTrue(metadata['ai_generation_fallback_used'])
            self.assertEqual(metadata['ai_generation_error_type'], 'question_generation')

    def test_ai_generation_failure_with_prompt_version_id_is_not_swallowed(self):
        with patch('apps.interview.services.question_generator.InterviewAIChainService') as service_class:
            service = service_class.return_value
            service.generate_questions.side_effect = AIChainOpenAIError(
                'question_generation',
                'invalid json',
            )

            with self.assertRaises(AIChainOpenAIError):
                generate_interview_questions(self.session, prompt_version_id=123)


class InterviewQuestionGenerateSourceTagsAPITest(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='source-tag-api-owner@example.com',
            password='password123',
            name='Source Tag API Owner',
        )
        self.jd = JobDescription.objects.create(
            user=self.user,
            company_name='Career Zip',
            position='Backend Developer',
            original_text='Django API 설계 경험을 요구합니다.',
        )
        self.session = InterviewSession.objects.create(
            user=self.user,
            jd=self.jd,
            interview_type='technical',
            persona='practical',
            total_question_count=1,
        )
        self.client.force_authenticate(self.user)

    def test_question_generate_saves_source_tags(self):
        generated = [
            {
                'question_text': 'JD의 Django API 요구사항과 본인 경험을 연결해서 설명해주세요.',
                'question_type': 'main',
                'question_category': 'technical',
                'order_index': 1,
                'difficulty': 'medium',
                'source_type': 'jd',
                'source_reference': 'ai_chain:q_001:jd',
                'source_tags': [
                    {
                        'source_type': 'jd',
                        'source_label': 'JD 기반',
                        'source_text_excerpt': 'Django API 설계 경험',
                        'source_reference': 'ai_chain:q_001:jd',
                    }
                ],
            }
        ]

        with patch('apps.interview.views.generate_interview_questions', return_value=generated):
            response = self.client.post(
                reverse(
                    'interview-question-generate',
                    kwargs={'session_id': self.session.id},
                ),
                {},
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        question = InterviewQuestion.objects.get(session=self.session)
        self.assertEqual(question.difficulty, 'medium')
        self.assertEqual(question.source_type, 'jd')
        self.assertEqual(question.question_category, 'technical')
        self.assertEqual(QuestionSourceTag.objects.filter(question=question).count(), 1)
        self.assertEqual(response.data['questions'][0]['question_category'], 'technical')
        self.assertEqual(response.data['questions'][0]['source_tags'][0]['source_type'], 'jd')

    def test_mvp_question_generate_passes_selected_project_ids_at_runtime(self):
        project = ProjectExperience.objects.create(
            user=self.user,
            project_name='Selected Deep Dive Project',
            description='README 기반 딥다이브 대상 프로젝트',
            tech_stack=['Django'],
            github_url='https://github.com/example/deep-dive',
        )
        generated = [
            {
                'question_text': '선택한 프로젝트의 README 기능을 어떻게 구현했나요?',
                'question_type': 'main',
                'question_category': 'technical',
                'order_index': 1,
                'difficulty': 'medium',
                'source_type': 'project_experience',
                'source_reference': 'ai_chain:q_001:project_experience',
                'source_tags': [
                    {
                        'source_type': 'project_experience',
                        'source_label': 'github_readme_context',
                        'source_text_excerpt': 'README 기반 딥다이브 대상 프로젝트',
                    }
                ],
            }
        ]

        def _generate(session, **kwargs):
            self.assertEqual(getattr(session, '_project_ids'), [str(project.id)])
            return generated

        with patch('apps.interview.mvp_views.generate_interview_questions', side_effect=_generate):
            response = self.client.post(
                reverse(
                    'mvp-question-generate',
                    kwargs={'session_id': self.session.id},
                ),
                {
                    'question_count': 1,
                    'project_ids': [str(project.id)],
                },
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['generated_count'], 1)
        self.assertEqual(
            response.data['questions'][0]['source_tags'][0]['source_label'],
            'github_readme_context',
        )

    def test_question_generate_saves_expected_technical_keywords_source_tag_once(self):
        generated = [
            {
                'question_text': 'Explain how you designed the Django API transaction boundary.',
                'question_type': 'main',
                'question_category': 'technical',
                'order_index': 1,
                'difficulty': 'medium',
                'source_type': 'jd',
                'source_reference': 'ai_chain:q_001:jd',
                'source_tags': [
                    {
                        'source_type': 'jd',
                        'source_label': 'JD basis',
                        'source_text_excerpt': 'Django API transaction experience',
                        'source_reference': 'ai_chain:q_001:jd',
                    },
                    {
                        'source_type': 'jd',
                        'source_label': 'expected_technical_keywords',
                        'source_text_excerpt': 'transaction.atomic, rollback, idempotency',
                        'source_reference': 'ai_chain:q_001:jd',
                    },
                    {
                        'source_type': 'jd',
                        'source_label': 'expected_technical_keywords',
                        'source_text_excerpt': 'duplicate should not be stored',
                        'source_reference': 'ai_chain:q_001:jd',
                    },
                ],
            }
        ]

        with patch('apps.interview.views.generate_interview_questions', return_value=generated):
            response = self.client.post(
                reverse(
                    'interview-question-generate',
                    kwargs={'session_id': self.session.id},
                ),
                {},
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        question = InterviewQuestion.objects.get(session=self.session)
        keyword_tags = QuestionSourceTag.objects.filter(
            question=question,
            source_label='expected_technical_keywords',
        )

        self.assertEqual(keyword_tags.count(), 1)
        self.assertEqual(
            keyword_tags.get().source_text_excerpt,
            'transaction.atomic, rollback, idempotency',
        )

    def test_question_generate_skips_expected_technical_keywords_for_non_technical_question(self):
        self.session.interview_type = 'personality'
        self.session.save(update_fields=['interview_type'])
        generated = [
            {
                'question_text': 'Describe a team conflict and how you handled it.',
                'question_type': 'main',
                'question_category': 'personality',
                'order_index': 1,
                'difficulty': 'medium',
                'source_type': 'general',
                'source_reference': 'ai_chain:q_001:general',
                'source_tags': [
                    {
                        'source_type': 'general',
                        'source_label': 'expected_technical_keywords',
                        'source_text_excerpt': 'should not be stored',
                    },
                ],
            }
        ]

        with patch('apps.interview.views.generate_interview_questions', return_value=generated):
            response = self.client.post(
                reverse(
                    'interview-question-generate',
                    kwargs={'session_id': self.session.id},
                ),
                {},
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        question = InterviewQuestion.objects.get(session=self.session)
        self.assertFalse(
            QuestionSourceTag.objects.filter(
                question=question,
                source_label='expected_technical_keywords',
            ).exists()
        )


class MVPAnalysisQuestionLinkAPITest(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='analysis-link-owner@example.com',
            password='password123',
            name='Analysis Link Owner',
        )
        self.jd = JobDescription.objects.create(
            user=self.user,
            company_name='Career Zip',
            position='Backend Developer',
            original_text='Django API and OpenAI integration experience required.',
        )
        self.resume = ResumeMaster.objects.create(
            user=self.user,
            name='Analysis Link Owner',
            email='analysis-link-owner@example.com',
            original_text='Built Django APIs with OpenAI integration.',
        )
        self.analysis = JdAnalysis.objects.create(
            user=self.user,
            jd=self.jd,
            resume=self.resume,
            match_score=88,
        )
        self.generated_question = GeneratedQuestion.objects.create(
            jd_analysis=self.analysis,
            question_type='technical',
            question_text='How did the analysis-stage Django API question reach the interview?',
            source='combined',
            source_ref='JD(Django) + Resume(OpenAI)',
            order=1,
            answer={
                'summary': 'Explain the linked analysis question.',
                'expected_technical_keywords': 'Django API, OpenAI integration, source tag persistence',
            },
        )
        self.analysis_session = AnalysisSession.objects.create(
            user=self.user,
            jd=self.jd,
            resume=self.resume,
            jd_analysis=self.analysis,
            job_role='Backend Developer',
            company_name='Career Zip',
            jd_text=self.jd.original_text,
            resume_text=self.resume.original_text,
            status='ready',
        )
        self.client.force_authenticate(self.user)

    def test_mvp_session_can_use_analysis_session_generated_questions(self):
        session_response = self.client.post(
            reverse('mvp-session-create'),
            {
                'analysis_session_id': self.analysis_session.id,
                'persona_type': 'practical',
                'interview_mode': 'text',
            },
            format='json',
        )

        self.assertEqual(session_response.status_code, status.HTTP_201_CREATED)
        session = InterviewSession.objects.get(id=session_response.data['session_id'])
        self.assertEqual(session.jd_id, self.jd.id)
        self.assertEqual(session.resume_id, self.resume.id)

        with patch('apps.interview.services.question_generator.InterviewAIChainService') as service_class:
            service = service_class.return_value
            service.generate_questions.return_value = {
                'session_id': str(session.id),
                'questions': [],
            }

            response = self.client.post(
                reverse('mvp-question-generate', kwargs={'session_id': session.id}),
                {
                    'question_count': 1,
                    'analysis_session_id': self.analysis_session.id,
                },
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['generated_count'], 1)
        self.assertEqual(response.data['questions'][0]['question_type'], 'main')
        self.assertEqual(response.data['questions'][0]['question_category'], 'technical')

        question = InterviewQuestion.objects.get(session=session)
        self.assertEqual(question.question_text, self.generated_question.question_text)
        self.assertEqual(question.source_type, 'combined')
        self.assertEqual(question.question_category, 'technical')
        self.assertEqual(
            question.source_reference,
            f'analysis_generated_question:{self.generated_question.id}',
        )
        keyword_tag = question.source_tags.get(source_label='expected_technical_keywords')
        self.assertEqual(
            keyword_tag.source_text_excerpt,
            'Django API, OpenAI integration, source tag persistence',
        )

        payload = service.generate_questions.call_args.args[0]
        self.assertEqual(
            payload['input_sources']['prepared_questions'][0]['generated_question_id'],
            str(self.generated_question.id),
        )
