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
from .services.document_parser import extract_text_from_document


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
        document = serializer.save()

        document.parse_status = 'processing'
        document.save(update_fields=('parse_status', 'updated_at'))
        try:
            document.extracted_text = extract_text_from_document(document)
            document.parse_status = 'completed'
            document.error_message = ''
        except Exception as exc:
            document.parse_status = 'failed'
            document.error_message = str(exc)
        document.save(
            update_fields=(
                'parse_status',
                'extracted_text',
                'error_message',
                'updated_at',
            )
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
