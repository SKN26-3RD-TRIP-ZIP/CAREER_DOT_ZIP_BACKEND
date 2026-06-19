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
    ProjectExperience,
    ResumeCareer,
    ResumeMaster,
    ResumeSkill,
)
from apps.interview.models import InterviewQuestion, InterviewSession, QuestionSourceTag
from apps.interview.services.question_generator import generate_interview_questions


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
        selector.assert_called_once_with(self.session, 2)


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
