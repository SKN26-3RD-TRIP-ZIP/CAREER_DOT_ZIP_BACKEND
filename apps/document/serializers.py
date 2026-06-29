from rest_framework import serializers

from .models import UploadedDocument
from .services.document_guardrails import validate_upload_file


class DocumentUploadSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True, allow_empty_file=True)

    class Meta:
        model = UploadedDocument
        fields = ('file', 'document_type')

    def validate_file(self, value):
        validate_upload_file(value)
        return value

    def create(self, validated_data):
        uploaded_file = validated_data['file']
        return UploadedDocument.objects.create(
            user=self.context['request'].user,
            document_type=validated_data['document_type'],
            file=uploaded_file,
            original_filename=uploaded_file.original_filename,
            file_type=uploaded_file.file_type,
            file_size=uploaded_file.size,
            parse_status=validated_data.get('parse_status', 'pending'),
            extracted_text=validated_data.get('extracted_text'),
            error_message=validated_data.get('error_message', ''),
        )


class DocumentListSerializer(serializers.ModelSerializer):
    document_id = serializers.UUIDField(source='id', read_only=True)

    class Meta:
        model = UploadedDocument
        fields = (
            'document_id',
            'document_type',
            'original_filename',
            'file_type',
            'file_size',
            'parse_status',
            'created_at',
        )


class DocumentDetailSerializer(DocumentListSerializer):
    class Meta(DocumentListSerializer.Meta):
        fields = DocumentListSerializer.Meta.fields + (
            'extracted_text',
            'error_message',
            'updated_at',
        )
