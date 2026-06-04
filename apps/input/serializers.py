from rest_framework import serializers
from .models import JobDescription, ResumeMaster, UserProfile


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


class UserProfileCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ('career_type', 'major_type', 'desired_job', 'career_year')


class UserProfileDetailSerializer(serializers.ModelSerializer):
    profile_id = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = (
            'profile_id',
            'career_type',
            'major_type',
            'desired_job',
            'career_year',
            'github_url',
            'updated_at',
        )

    def get_profile_id(self, obj):
        return str(obj.id)


class UserProfilePatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ('career_type', 'major_type', 'desired_job', 'career_year', 'github_url')
        extra_kwargs = {
            'career_type': {'required': False},
            'major_type': {'required': False},
            'desired_job': {'required': False},
            'career_year': {'required': False},
            'github_url': {'required': False},
        }


class ResumeMasterCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeMaster
        fields = ('name', 'phone', 'email', 'address', 'github_url', 'original_text')


class ResumeMasterDetailSerializer(serializers.ModelSerializer):
    resume_id = serializers.SerializerMethodField()
    education = serializers.SerializerMethodField()
    careers = serializers.SerializerMethodField()
    skills = serializers.SerializerMethodField()
    certificates = serializers.SerializerMethodField()

    class Meta:
        model = ResumeMaster
        fields = (
            'resume_id',
            'name',
            'original_text',
            'extracted_keywords',
            'is_active',
            'education',
            'careers',
            'skills',
            'certificates',
            'updated_at',
        )

    def get_resume_id(self, obj):
        return str(obj.id)

    def get_education(self, obj):
        return []

    def get_careers(self, obj):
        return []

    def get_skills(self, obj):
        return []

    def get_certificates(self, obj):
        return []
