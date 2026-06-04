from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework import status

from .models import JobDescription
from .serializers import (
    JobDescriptionCreateSerializer,
    JobDescriptionListSerializer,
    JobDescriptionDetailSerializer,
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
