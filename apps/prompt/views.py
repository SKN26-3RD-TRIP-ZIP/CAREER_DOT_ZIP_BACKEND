from django.db import transaction
from django.db.models import Count, Max
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.input.models import (
    CoverLetter,
    CoverLetterItem,
    JobDescription,
    ProjectExperience,
    ResumeMaster,
)
from .models import AdminPromptTestRun, PersonaConfig, PromptTemplate, PromptVersion
from .permissions import IsPromptAdmin
from .serializers import (
    PersonaActiveTemplateSerializer,
    PersonaConfigSerializer,
    PromptDefaultVersionSerializer,
    PromptTemplateCreateSerializer,
    PromptTemplateSerializer,
    PromptVersionCreateSerializer,
    PromptVersionSerializer,
)


class PromptAdminAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsPromptAdmin]


class PersonaListView(PromptAdminAPIView):
    def get(self, request):
        personas = PersonaConfig.objects.select_related('active_template').all()
        serializer = PersonaConfigSerializer(personas, many=True)
        return Response({'total': personas.count(), 'results': serializer.data})


class PersonaActiveTemplateView(PromptAdminAPIView):
    def patch(self, request, persona_id):
        persona = get_object_or_404(PersonaConfig, id=persona_id)
        serializer = PersonaActiveTemplateSerializer(
            data=request.data,
            context={'persona': persona},
        )
        serializer.is_valid(raise_exception=True)
        persona.active_template = serializer.validated_data['active_template_id']
        persona.save(update_fields=('active_template', 'updated_at'))
        return Response(
            {
                'persona_id': persona.id,
                'active_template_id': persona.active_template_id,
                'updated_at': persona.updated_at,
            }
        )


class PromptTemplateListCreateView(PromptAdminAPIView):
    def get(self, request):
        templates = PromptTemplate.objects.filter(is_active=True).select_related(
            'persona_config',
            'default_version',
        ).annotate(version_count=Count('versions'))
        persona_type = request.query_params.get('persona_type')
        prompt_type = request.query_params.get('prompt_type')
        if persona_type:
            templates = templates.filter(persona_config__persona_type=persona_type)
        if prompt_type:
            templates = templates.filter(prompt_type=prompt_type)

        serializer = PromptTemplateSerializer(templates, many=True)
        return Response({'total': templates.count(), 'results': serializer.data})

    def post(self, request):
        serializer = PromptTemplateCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        template = serializer.save()
        return Response(
            PromptTemplateSerializer(template).data,
            status=status.HTTP_201_CREATED,
        )


class PromptTemplateDeleteView(PromptAdminAPIView):
    def delete(self, request, template_id):
        template = get_object_or_404(PromptTemplate, id=template_id, is_active=True)
        if template.active_personas.exists():
            return Response(
                {'detail': 'Active persona template cannot be deleted.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        template.is_active = False
        template.save(update_fields=('is_active', 'updated_at'))
        return Response(status=status.HTTP_204_NO_CONTENT)


class PromptVersionListCreateView(PromptAdminAPIView):
    def get_template(self, template_id):
        return get_object_or_404(PromptTemplate, id=template_id, is_active=True)

    def get(self, request, template_id):
        template = self.get_template(template_id)
        versions = template.versions.order_by('-version_number')
        serializer = PromptVersionSerializer(versions, many=True)
        return Response({'total': versions.count(), 'results': serializer.data})

    def post(self, request, template_id):
        serializer = PromptVersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            template = get_object_or_404(
                PromptTemplate.objects.select_for_update(),
                id=template_id,
                is_active=True,
            )
            last_version = template.versions.aggregate(
                number=Max('version_number')
            )['number']
            version = serializer.save(
                template=template,
                version_number=(last_version or 0) + 1,
                created_by=request.user,
            )
            if template.default_version_id is None:
                template.default_version = version
                template.save(update_fields=('default_version', 'updated_at'))

        return Response(
            PromptVersionSerializer(version).data,
            status=status.HTTP_201_CREATED,
        )


class PromptDefaultVersionView(PromptAdminAPIView):
    def patch(self, request, template_id):
        template = get_object_or_404(PromptTemplate, id=template_id, is_active=True)
        serializer = PromptDefaultVersionSerializer(
            data=request.data,
            context={'template': template},
        )
        serializer.is_valid(raise_exception=True)
        template.default_version = serializer.validated_data['default_version']
        template.save(update_fields=('default_version', 'updated_at'))
        return Response(
            {
                'template_id': template.id,
                'default_version_id': template.default_version_id,
                'updated_at': template.updated_at,
            }
        )


class PromptVersionTestSetupView(PromptAdminAPIView):
    def get(self, request, version_id):
        version = get_object_or_404(
            PromptVersion.objects.select_related('template__persona_config'),
            id=version_id,
        )
        template = version.template
        if not template.is_active:
            return Response(
                {'detail': 'Prompt template is inactive.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if template.prompt_type != 'question_generation':
            return Response(
                {'detail': 'Only question generation prompts can be tested here.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        materials = self._get_or_create_sample_materials(request.user)
        return Response(
            {
                'prompt_version': {
                    'prompt_ver_id': version.id,
                    'version_number': version.version_number,
                    'change_note': version.change_note,
                    'created_at': version.created_at,
                    'is_default': template.default_version_id == version.id,
                },
                'template': {
                    'template_id': template.id,
                    'title': template.title,
                    'prompt_type': template.prompt_type,
                },
                'persona': {
                    'persona_config_id': template.persona_config_id,
                    'persona_type': template.persona_config.persona_type,
                    'description': template.persona_config.description,
                },
                'materials': materials,
                'defaults': {
                    'interview_type': 'comprehensive',
                    'interview_mode': 'voice',
                    'question_count': 5,
                },
            }
        )

    def _get_or_create_sample_materials(self, user):
        jd, _ = JobDescription.objects.update_or_create(
            user=user,
            company_name='커리어집 관리자 테스트',
            position='Python 백엔드 개발자',
            defaults={
                'original_text': (
                    'AI 모의면접 서비스를 함께 개발할 Python 백엔드 개발자를 채용합니다.\n\n'
                    '[주요 업무]\n'
                    '- Django REST Framework 기반 면접 세션, 질문 생성, 답변 저장 API 설계 및 개발\n'
                    '- OpenAI 기반 질문 생성 프롬프트와 면접관 페르소나 버전 테스트 기능 연동\n'
                    '- STT/TTS 음성 면접 흐름, 리포트 생성, 관리자 검수 플로우 개선\n'
                    '- React 프론트엔드와 협업하여 API 계약을 정리하고 운영 중 이슈를 디버깅\n\n'
                    '[자격 요건]\n'
                    '- Python, Django 또는 DRF 기반 REST API 개발 경험\n'
                    '- PostgreSQL/MySQL 등 관계형 데이터베이스 모델링 및 쿼리 최적화 이해\n'
                    '- 외부 AI API 연동, 비동기 작업, 장애 로그 분석에 대한 기본 이해\n'
                    '- Git 기반 협업과 코드 리뷰 경험\n\n'
                    '[우대 사항]\n'
                    '- 음성 인식(STT), 음성 합성(TTS), 프롬프트 엔지니어링 경험\n'
                    '- Docker 기반 배포 환경과 운영 모니터링 경험'
                ),
                'input_method': 'TEXT',
                'job_requirements': (
                    'Python, Django REST Framework, PostgreSQL, OpenAI API 연동, '
                    'STT/TTS 음성 처리, 프롬프트 버전 테스트, 운영 로그 분석 역량'
                ),
                'keywords': 'Python,Django,DRF,PostgreSQL,OpenAI,STT,TTS,React,프롬프트',
                'analysis_status': 'COMPLETED',
            },
        )
        resume, _ = ResumeMaster.objects.update_or_create(
            user=user,
            email='admin-test@careerzip.local',
            defaults={
                'name': '김테스트',
                'phone': '010-0000-0000',
                'github_url': 'https://github.com/careerzip/admin-test',
                'original_text': (
                    '김테스트 | Python 백엔드 개발자\n'
                    '이메일: admin-test@careerzip.local | GitHub: github.com/careerzip/admin-test\n\n'
                    '[경력]\n'
                    '2024.03 ~ 현재 커리어집 | 백엔드 개발자\n'
                    '- Django REST Framework 기반 면접 세션 및 질문 생성 API 개발\n'
                    '- OpenAI 프롬프트 버전 관리와 면접관 페르소나 테스트 플로우 연동\n'
                    '- STT/TTS 음성 면접 상태 관리 API와 리포트 생성 흐름 개선\n'
                    '- PostgreSQL 쿼리 최적화와 운영 로그 기반 장애 원인 분석 수행\n\n'
                    '2022.07 ~ 2024.02 이커머스 솔루션팀 | 주니어 백엔드 개발자\n'
                    '- Django 기반 상품/주문 관리 REST API 개발\n'
                    '- MySQL 스키마 설계, 인덱스 개선, Docker 개발 환경 표준화 참여\n\n'
                    '[기술 스택]\n'
                    'Python, Django, Django REST Framework, PostgreSQL, MySQL, Redis, Docker, React API 연동, OpenAI API\n\n'
                    '[프로젝트]\n'
                    'AI 모의면접 음성 플로우\n'
                    '- 질문 생성, TTS 재생, STT 답변 인식, 리포트 생성까지 이어지는 면접 흐름 구현\n'
                    '- 관리자 프롬프트 버전 테스트를 위한 mock 세션 생성 및 정리 로직 설계'
                ),
                'extracted_keywords': 'Python,Django,DRF,PostgreSQL,MySQL,OpenAI,React,STT,TTS,프롬프트',
                'is_active': True,
            },
        )
        cover_letter, _ = CoverLetter.objects.update_or_create(
            user=user,
            title='관리자 테스트용 백엔드 개발자 자기소개서',
            defaults={
                'jd': jd,
                'company_name': '커리어집 관리자 테스트',
                'is_active': True,
            },
        )
        CoverLetterItem.objects.update_or_create(
            cover_letter=cover_letter,
            order_index=1,
            defaults={
                'question': 'AI 면접 서비스 백엔드 개발 직무에 본인이 적합하다고 생각하는 이유를 작성해 주세요.',
                'answer_text': (
                    '저는 Django REST Framework 기반 API를 설계하고 프론트엔드와 계약을 맞춰 '
                    '서비스 흐름을 끝까지 연결한 경험이 있습니다. 특히 AI 모의면접 프로젝트에서 '
                    '질문 생성, TTS 재생, STT 답변 저장, 리포트 생성까지 이어지는 흐름을 다루며 '
                    '프롬프트 변경이 사용자 경험과 평가 결과에 어떤 영향을 주는지 확인했습니다. '
                    '운영 중 발생한 오류 로그를 분석하고 DB 조회 병목을 개선한 경험도 있어, '
                    '커리어집의 면접 품질 검증과 안정적인 백엔드 운영에 기여할 수 있습니다.'
                ),
            },
        )
        project, _ = ProjectExperience.objects.update_or_create(
            user=user,
            project_name='AI 모의면접 음성 플로우',
            defaults={
                'description': (
                    'AI 면접관이 질문을 생성하고 TTS로 읽어주면 사용자가 음성으로 답변하고, '
                    'STT 전사 결과를 저장한 뒤 답변 평가와 최종 리포트 생성까지 이어지는 '
                    '모의면접 플로우를 구현했습니다.'
                ),
                'contribution': (
                    '면접 세션 생성/상태 변경 API를 설계하고, 프롬프트 버전이 질문 생성에 '
                    '반영되도록 연결했습니다. 또한 음성 면접 화면의 녹음/전사/답변 제출 상태를 '
                    '백엔드 데이터 흐름과 맞추고, 테스트 종료 후 생성 데이터를 정리하는 로직을 구현했습니다.'
                ),
                'tech_stack': ['Python', 'Django', 'React', 'OpenAI', 'STT', 'TTS'],
                'github_url': 'https://github.com/careerzip/admin-test',
            },
        )

        return {
            'jd': self._serialize_jd(jd),
            'resume': self._serialize_resume(resume),
            'cover_letter': self._serialize_cover_letter(cover_letter),
            'projects': [self._serialize_project(project)],
        }

    @staticmethod
    def _serialize_jd(jd):
        return {
            'jd_id': jd.id,
            'company_name': jd.company_name,
            'position': jd.position,
            'created_at': jd.created_at,
        }

    @staticmethod
    def _serialize_resume(resume):
        return {
            'resume_id': resume.id,
            'name': resume.name,
            'updated_at': resume.updated_at,
        }

    @staticmethod
    def _serialize_cover_letter(cover_letter):
        return {
            'cover_letter_id': cover_letter.id,
            'title': cover_letter.title,
            'company_name': cover_letter.company_name,
            'created_at': cover_letter.created_at,
        }

    @staticmethod
    def _serialize_project(project):
        return {
            'project_id': project.id,
            'project_name': project.project_name,
            'description': project.description,
            'contribution': project.contribution,
            'tech_stack': project.tech_stack,
            'created_at': project.created_at,
        }


class AdminPromptTestRunCleanupView(PromptAdminAPIView):
    def delete(self, request, session_id):
        test_run = (
            AdminPromptTestRun.objects.select_related('session')
            .filter(session_id=session_id, admin_user=request.user)
            .first()
        )
        if test_run is None:
            return Response(status=status.HTTP_204_NO_CONTENT)

        with transaction.atomic():
            test_run.session.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
