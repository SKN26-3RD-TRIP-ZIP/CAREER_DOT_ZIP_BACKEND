from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import UploadedDocument
from .serializers import (
    DocumentDetailSerializer,
    DocumentListSerializer,
    DocumentUploadSerializer,
)
from .services.document_guardrails import (
    map_text_extraction_error,
    validate_extracted_text,
)
from .services.document_parser import extract_text_from_file


class DocumentUploadView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = DocumentUploadSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        uploaded_file = serializer.validated_data['file']
        document_type = serializer.validated_data['document_type']
        try:
            extracted_text = extract_text_from_file(uploaded_file, uploaded_file.file_type)
            validate_extracted_text(extracted_text, document_type, uploaded_file.file_type)
        except Exception as exc:
            if hasattr(exc, 'status_code') and hasattr(exc, 'detail'):
                raise
            raise map_text_extraction_error(exc) from exc

        document = serializer.save(
            parse_status='completed',
            extracted_text=extracted_text,
            error_message='',
        )

        return Response(
            DocumentDetailSerializer(document).data,
            status=status.HTTP_201_CREATED,
        )


class DocumentListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        documents = UploadedDocument.objects.filter(user=request.user).order_by('-created_at')
        serializer = DocumentListSerializer(documents, many=True)
        return Response(
            {'total': documents.count(), 'results': serializer.data},
            status=status.HTTP_200_OK,
        )


class DocumentDetailView(generics.RetrieveDestroyAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DocumentDetailSerializer
    lookup_field = 'id'
    lookup_url_kwarg = 'document_id'

    def get_queryset(self):
        return UploadedDocument.objects.filter(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        document = self.get_object()
        document.file.delete(save=False)
        document.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
