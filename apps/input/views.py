from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

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
