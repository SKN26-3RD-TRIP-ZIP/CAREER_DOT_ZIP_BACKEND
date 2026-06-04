from rest_framework import serializers
from .models import JobDescription


class JobDescriptionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobDescription
        fields = ('company_name', 'position', 'original_text', 'input_method')


class JobDescriptionListSerializer(serializers.ModelSerializer):
    jd_id = serializers.SerializerMethodField()

    class Meta:
        model = JobDescription
        fields = ('jd_id', 'company_name', 'position', 'input_method', 'created_at')

    def get_jd_id(self, obj):
        return str(obj.id)


class JobDescriptionDetailSerializer(serializers.ModelSerializer):
    jd_id = serializers.SerializerMethodField()

    class Meta:
        model = JobDescription
        fields = (
            'jd_id',
            'company_name',
            'position',
            'original_text',
            'company_summary',
            'talent_profile',
            'job_requirements',
            'keywords',
            'analysis_status',
            'created_at',
        )

    def get_jd_id(self, obj):
        return str(obj.id)
