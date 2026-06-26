from pathlib import Path

from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser

from apps.document.services.document_parser import extract_text_from_file

from .models import (
    JobDescription,
    ProjectExperience,
    CoverLetter,
    ResumeMaster,
    UserProfile,
    ResumeEducation,
    ResumeCareer,
    ResumeSkill,
    ResumeCertificate,
)
from .serializers import (
    JobDescriptionCreateSerializer,
    JobDescriptionListSerializer,
    JobDescriptionDetailSerializer,
    ProjectExperienceCreateSerializer,
    ProjectExperienceListSerializer,
    CoverLetterCreateSerializer,
    CoverLetterListSerializer,
    CoverLetterDetailSerializer,
    UserProfileCreateSerializer,
    UserProfileDetailSerializer,
    UserProfilePatchSerializer,
    ResumeMasterCreateSerializer,
    ResumeMasterDetailSerializer,
    ResumeEducationCreateSerializer,
    ResumeEducationListSerializer,
    ResumeCareerCreateSerializer,
    ResumeCareerListSerializer,
    ResumeSkillCreateSerializer,
    ResumeSkillListSerializer,
    ResumeCertificateCreateSerializer,
    ResumeCertificateListSerializer,
)


UPLOAD_MAX_SIZE = 10 * 1024 * 1024  # 10MB
UPLOAD_ALLOWED_TYPES = {'pdf', 'docx'}


def _existing_order_fields(model, *field_names):
    available = {field.name for field in model._meta.get_fields()}
    order_fields = []

    for field_name in field_names:
        normalized = field_name.lstrip('-')
        if normalized in available:
            order_fields.append(field_name)

    return order_fields


def _validate_upload(file_obj, allowed_types=None):
    """업로드 파일 공통 검증. 통과 시 (file_type, filename) 반환, 실패 시 ValueError(메시지)."""
    allowed_types = allowed_types or UPLOAD_ALLOWED_TYPES
    if file_obj is None:
        raise ValueError('파일이 필요합니다.')
    filename = Path(file_obj.name).name
    file_type = Path(filename).suffix.lower().lstrip('.')
    if file_type not in allowed_types:
        if allowed_types == {'pdf'}:
            raise ValueError('PDF 파일만 업로드할 수 있습니다.')
        raise ValueError('PDF 또는 DOCX 파일만 업로드할 수 있습니다.')
    if file_obj.size == 0:
        raise ValueError('빈 파일은 업로드할 수 없습니다.')
    if file_obj.size > UPLOAD_MAX_SIZE:
        raise ValueError('파일 크기는 10MB를 초과할 수 없습니다.')
    return file_type, filename


def _extract_or_error(file_obj, file_type):
    """텍스트 추출. 성공 시 (text, None), 실패/빈내용 시 (None, error_response)."""
    try:
        text = (extract_text_from_file(file_obj, file_type) or '').strip()
    except Exception as exc:  # noqa: BLE001
        return None, Response(
            {'detail': f'텍스트 추출에 실패했습니다: {exc}'},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    if not text:
        return None, Response(
            {'detail': '파일에서 텍스트를 추출하지 못했습니다. (빈 내용)'},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return text, None


class JDUploadView(APIView):
    """JD PDF 업로드 → 텍스트 추출 → JobDescription 저장. POST /api/v1/jds/upload"""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        file_obj = request.FILES.get('file')
        try:
            file_type, filename = _validate_upload(file_obj, allowed_types={'pdf'})
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        text, error = _extract_or_error(file_obj, file_type)
        if error is not None:
            return error

        jd = JobDescription.objects.create(
            user=request.user,
            company_name=(request.data.get('company_name') or '').strip() or '미입력',
            position=(request.data.get('position') or '').strip() or (Path(filename).stem[:100] or '미입력'),
            original_text=text,
            input_method='PDF',
            analysis_status='PENDING',
        )
        return Response(JobDescriptionListSerializer(jd).data, status=status.HTTP_201_CREATED)


class ResumeUploadView(APIView):
    """이력서 PDF/DOCX 업로드 → 텍스트 추출 → ResumeMaster.original_text 저장. POST /api/v1/resumes/upload"""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        file_obj = request.FILES.get('file')
        try:
            file_type, filename = _validate_upload(file_obj)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        text, error = _extract_or_error(file_obj, file_type)
        if error is not None:
            return error

        resume = ResumeMaster.objects.create(
            user=request.user,
            name=(request.data.get('name') or '').strip() or (Path(filename).stem[:50] or '업로드 이력서'),
            email=request.user.email,
            original_text=text,
        )
        return Response(
            {
                'resume_id': str(resume.id),
                'name': resume.name,
                'original_text_length': len(text),
                'created_at': resume.created_at,
                'updated_at': resume.updated_at,
            },
            status=status.HTTP_201_CREATED,
        )


class UserSummaryView(APIView):
    """마이페이지 요약 집계. GET /api/v1/users/me/summary (request.user 기준, 집계만 — DB 변경 없음)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from apps.interview.models import InterviewSession
        from apps.report.models import FinalReport

        user = request.user
        jds = JobDescription.objects.filter(user=user)
        resumes = ResumeMaster.objects.filter(user=user)
        interviews = InterviewSession.objects.filter(user=user)
        reports = FinalReport.objects.filter(session__user=user).select_related('session')
        latest_jd = jds.order_by('-created_at').first()
        latest_resume = resumes.order_by(
            *_existing_order_fields(ResumeMaster, '-updated_at', '-created_at', '-id')
        ).first()
        latest_interview = interviews.order_by('-created_at').first()
        latest_report = reports.order_by('-generated_at').first()
        return Response(
            {
                'jd_count': jds.count(),
                'latest_jd': (
                    {
                        'jd_id': str(latest_jd.id),
                        'company_name': latest_jd.company_name,
                        'position': latest_jd.position,
                        'analysis_status': latest_jd.analysis_status,
                        'created_at': latest_jd.created_at,
                    }
                    if latest_jd
                    else None
                ),
                'latest_jd_created_at': latest_jd.created_at if latest_jd else None,
                'latest_jd_analysis_status': latest_jd.analysis_status if latest_jd else None,
                'resume_count': resumes.count(),
                'latest_resume': (
                    {
                        'resume_id': str(latest_resume.id),
                        'name': latest_resume.name,
                        'updated_at': latest_resume.updated_at,
                    }
                    if latest_resume
                    else None
                ),
                'latest_resume_updated_at': latest_resume.updated_at if latest_resume else None,
                'cover_letter_count': CoverLetter.objects.filter(user=user).count(),
                'project_count': ProjectExperience.objects.filter(user=user).count(),
                'interview_count': interviews.count(),
                'latest_interview': (
                    {
                        'session_id': str(latest_interview.id),
                        'interview_type': latest_interview.interview_type,
                        'persona': latest_interview.persona,
                        'status': latest_interview.status,
                        'created_at': latest_interview.created_at,
                        'ended_at': latest_interview.ended_at,
                    }
                    if latest_interview
                    else None
                ),
                'latest_report': (
                    {
                        'report_id': str(latest_report.id),
                        'session_id': str(latest_report.session_id),
                        'overall_score': latest_report.overall_score,
                        'score_status': latest_report.score_status,
                        'evaluation_status': latest_report.evaluation_status,
                        'is_mock': latest_report.is_mock,
                        'generated_at': latest_report.generated_at,
                    }
                    if latest_report
                    else None
                ),
                'point_balance': getattr(user, 'point_balance', 0),
                'point_last_updated_at': getattr(user, 'point_last_updated_at', None),
            },
            status=status.HTTP_200_OK,
        )


class JDListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = JobDescriptionListSerializer

    def get_queryset(self):
        return JobDescription.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return JobDescriptionCreateSerializer
        return JobDescriptionListSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        jd = serializer.instance
        # Use list serializer to ensure consistent field formatting (created_at serialization)
        from .serializers import JobDescriptionListSerializer
        data = JobDescriptionListSerializer(jd).data
        return Response(data, status=status.HTTP_201_CREATED)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = JobDescriptionListSerializer(queryset, many=True)
        return Response({'total': queryset.count(), 'results': serializer.data}, status=status.HTTP_200_OK)


class JDDetailView(generics.RetrieveDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = JobDescriptionDetailSerializer
    lookup_field = 'id'
    lookup_url_kwarg = 'jd_id'

    def get_queryset(self):
        return JobDescription.objects.filter(user=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ResumeMasterCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """현재 사용자의 이력서 목록 (선택/마이페이지용). GET /api/v1/resumes"""
        resumes = ResumeMaster.objects.filter(user=request.user).order_by('-updated_at')
        results = [
            {
                'resume_id': str(r.id),
                'name': r.name,
                'is_active': r.is_active,
                'has_text': bool(r.original_text),
                'created_at': r.created_at,
                'updated_at': r.updated_at,
            }
            for r in resumes
        ]
        return Response({'total': len(results), 'results': results}, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ResumeMasterCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resume = serializer.save(user=request.user)
        return Response(
            {
                'resume_id': str(resume.id),
                'is_active': resume.is_active,
                'created_at': resume.created_at,
            },
            status=status.HTTP_201_CREATED,
        )


class ResumeMasterDetailView(generics.RetrieveDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ResumeMasterDetailSerializer
    lookup_field = 'id'
    lookup_url_kwarg = 'resume_id'

    def get_queryset(self):
        return ResumeMaster.objects.filter(user=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return UserProfile.objects.get(user=self.request.user)

    def post(self, request):
        if UserProfile.objects.filter(user=request.user).exists():
            return Response(
                {'error': 'Profile already exists.'},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = UserProfileCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save(user=request.user)

        return Response(
            {
                'profile_id': str(profile.id),
                'career_type': profile.career_type,
                'major_type': profile.major_type,
                'desired_job': profile.desired_job,
                'career_year': profile.career_year,
                'created_at': profile.created_at,
            },
            status=status.HTTP_201_CREATED,
        )

    def get(self, request):
        try:
            profile = self.get_object()
        except UserProfile.DoesNotExist:
            return Response({'detail': 'Profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserProfileDetailSerializer(profile)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        try:
            profile = self.get_object()
        except UserProfile.DoesNotExist:
            return Response({'detail': 'Profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserProfilePatchSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()

        return Response(
            {
                'profile_id': str(profile.id),
                'desired_job': profile.desired_job,
                'github_url': profile.github_url,
                'updated_at': profile.updated_at,
            },
            status=status.HTTP_200_OK,
        )


class ResumeEducationCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_resume(self, resume_id):
        try:
            return ResumeMaster.objects.get(id=resume_id, user=self.request.user)
        except ResumeMaster.DoesNotExist:
            return None

    def post(self, request, resume_id):
        resume = self.get_resume(resume_id)
        if not resume:
            return Response({'detail': 'Resume not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ResumeEducationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        education = serializer.save(resume=resume)

        return Response(
            {
                'resume_edu_id': str(education.id),
                'school_name': education.school_name,
            },
            status=status.HTTP_201_CREATED,
        )


class ResumeCareerCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_resume(self, resume_id):
        try:
            return ResumeMaster.objects.get(id=resume_id, user=self.request.user)
        except ResumeMaster.DoesNotExist:
            return None

    def post(self, request, resume_id):
        resume = self.get_resume(resume_id)
        if not resume:
            return Response({'detail': 'Resume not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ResumeCareerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        career = serializer.save(resume=resume)

        return Response(
            {
                'resume_career_id': str(career.id),
                'company_name': career.company_name,
            },
            status=status.HTTP_201_CREATED,
        )


class ResumeSkillCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_resume(self, resume_id):
        try:
            return ResumeMaster.objects.get(id=resume_id, user=self.request.user)
        except ResumeMaster.DoesNotExist:
            return None

    def post(self, request, resume_id):
        resume = self.get_resume(resume_id)
        if not resume:
            return Response({'detail': 'Resume not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ResumeSkillCreateSerializer(data=request.data, context={'resume_id': resume_id})
        serializer.is_valid(raise_exception=True)
        skills = serializer.save()

        skill_ids = [str(skill.id) for skill in skills]
        return Response(
            {'resume_skill_ids': skill_ids},
            status=status.HTTP_201_CREATED,
        )


class ProjectExperienceListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ProjectExperience.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ProjectExperienceCreateSerializer
        return ProjectExperienceListSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        project = serializer.instance
        return Response(
            {
                'project_id': str(project.id),
                'project_name': project.project_name,
                'created_at': project.created_at,
            },
            status=status.HTTP_201_CREATED,
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = ProjectExperienceListSerializer(queryset, many=True)
        return Response(
            {
                'total': queryset.count(),
                'results': serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class ProjectExperienceDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'
    lookup_url_kwarg = 'project_id'

    def get_queryset(self):
        return ProjectExperience.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.request.method in ['PATCH', 'PUT']:
            return ProjectExperienceCreateSerializer
        return ProjectExperienceListSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                'project_id': str(instance.id),
                'updated_at': instance.updated_at,
            },
            status=status.HTTP_200_OK,
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CoverLetterListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CoverLetter.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CoverLetterCreateSerializer
        return CoverLetterListSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        cover_letter = serializer.instance
        return Response(
            {
                'cover_letter_id': str(cover_letter.id),
                'title': cover_letter.title,
                'is_active': cover_letter.is_active,
                'created_at': cover_letter.created_at,
            },
            status=status.HTTP_201_CREATED,
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = CoverLetterListSerializer(queryset, many=True)
        return Response(
            {
                'total': queryset.count(),
                'results': serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class CoverLetterDetailView(generics.RetrieveDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CoverLetterDetailSerializer
    lookup_field = 'id'
    lookup_url_kwarg = 'cover_letter_id'

    def get_queryset(self):
        return CoverLetter.objects.filter(user=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ResumeCertificateCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_resume(self, resume_id):
        try:
            return ResumeMaster.objects.get(id=resume_id, user=self.request.user)
        except ResumeMaster.DoesNotExist:
            return None

    def post(self, request, resume_id):
        resume = self.get_resume(resume_id)
        if not resume:
            return Response({'detail': 'Resume not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ResumeCertificateCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        certificate = serializer.save(resume=resume)

        return Response(
            {
                'resume_certificate_id': str(certificate.id),
                'name': certificate.name,
            },
            status=status.HTTP_201_CREATED,
        )
