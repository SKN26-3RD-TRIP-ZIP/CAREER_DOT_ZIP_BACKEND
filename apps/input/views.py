from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

from .models import JobDescription, UserProfile
from .serializers import (
    JobDescriptionCreateSerializer,
    JobDescriptionListSerializer,
    JobDescriptionDetailSerializer,
    UserProfileCreateSerializer,
    UserProfileDetailSerializer,
    UserProfilePatchSerializer,
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
