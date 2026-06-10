from rest_framework import serializers
from apps.input.models import JobDescription, ResumeMaster, CoverLetter


class JDListSerializer(serializers.ModelSerializer):
    jd_id = serializers.UUIDField(source='id')

    class Meta:
        model = JobDescription
        fields = ('jd_id', 'company_name', 'position', 'input_method', 'created_at', 'updated_at')


class ResumeListSerializer(serializers.ModelSerializer):
    resume_id = serializers.UUIDField(source='id')

    class Meta:
        model = ResumeMaster
        fields = ('resume_id', 'name', 'is_active', 'created_at', 'updated_at')


class CoverLetterListSerializer(serializers.ModelSerializer):
    cover_letter_id = serializers.UUIDField(source='id')

    class Meta:
        model = CoverLetter
        fields = ('cover_letter_id', 'title', 'company_name', 'is_active', 'created_at', 'updated_at')
