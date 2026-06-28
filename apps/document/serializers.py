from pathlib import Path

from rest_framework import serializers

from .models import UploadedDocument


MAX_UPLOAD_SIZE = 10 * 1024 * 1024
ALLOWED_FILE_TYPES = {'pdf', 'docx', 'txt'}


class DocumentUploadSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True)

    class Meta:
        model = UploadedDocument
        fields = ('file', 'document_type')

    def validate_file(self, value):
        original_filename = Path(value.name).name
        file_type = Path(original_filename).suffix.lower().lstrip('.')

        if file_type not in ALLOWED_FILE_TYPES:
            raise serializers.ValidationError('Only PDF, DOCX, and TXT files are allowed.')
        if value.size > MAX_UPLOAD_SIZE:
            raise serializers.ValidationError('File size must not exceed 10MB.')
        if len(original_filename) > 255:
            raise serializers.ValidationError('Filename must not exceed 255 characters.')

        value.original_filename = original_filename
        value.file_type = file_type
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
