from rest_framework import serializers
from apps.input.models import (
    JobDescription, ResumeMaster, CoverLetter,
    ResumeCareer, ResumeEducation, ResumeSkill, ResumeCertificate,
)


class JDListSerializer(serializers.ModelSerializer):
    jd_id = serializers.UUIDField(source='id')

    class Meta:
        model = JobDescription
        fields = ('jd_id', 'company_name', 'position', 'input_method', 'created_at', 'updated_at')


class ResumeListSerializer(serializers.ModelSerializer):
    resume_id = serializers.UUIDField(source='id')
    has_career = serializers.SerializerMethodField()
    has_education = serializers.SerializerMethodField()
    has_skills = serializers.SerializerMethodField()
    has_certificates = serializers.SerializerMethodField()

    class Meta:
        model = ResumeMaster
        fields = (
            'resume_id', 'name', 'is_active', 'created_at', 'updated_at',
            'has_career', 'has_education', 'has_skills', 'has_certificates',
        )

    def get_has_career(self, obj):
        return obj.careers.exists()

    def get_has_education(self, obj):
        return obj.education.exists()

    def get_has_skills(self, obj):
        return obj.skills.exists()

    def get_has_certificates(self, obj):
        return obj.certificates.exists()


# ── Resume 전체 생성용 Serializers (analysis 전용) ──────────────────────────

class ResumeCareerInputSerializer(serializers.Serializer):
    company_name = serializers.CharField(max_length=100)
    position = serializers.CharField(max_length=100)
    start_date = serializers.CharField(max_length=7, required=False, allow_blank=True, default='')
    end_date = serializers.CharField(max_length=7, required=False, allow_blank=True, default='')
    is_current = serializers.BooleanField(required=False, default=False)
    description = serializers.CharField(required=False, allow_blank=True, default='')


class ResumeEducationInputSerializer(serializers.Serializer):
    DEGREE_CHOICES = ['high_school', 'associate', 'bachelor', 'master', 'doctor']
    STATUS_CHOICES = ['graduated', 'enrolled', 'leave_of_absence', 'dropped_out']

    school_name = serializers.CharField(max_length=100)
    major = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    degree = serializers.ChoiceField(choices=DEGREE_CHOICES)
    start_date = serializers.CharField(max_length=7, required=False, allow_blank=True, default='')
    end_date = serializers.CharField(max_length=7, required=False, allow_blank=True, default='')
    status = serializers.ChoiceField(choices=STATUS_CHOICES)


class ResumeCertificateInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    issued_by = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    issued_at = serializers.CharField(max_length=7, required=False, allow_blank=True, default='')


class ResumeFullCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=50)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default='')
    email = serializers.EmailField(required=False, allow_blank=True, default='')
    address = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    github_url = serializers.URLField(required=False, allow_blank=True, default='')
    original_text = serializers.CharField(required=False, allow_blank=True, default='')

    careers = ResumeCareerInputSerializer(many=True, required=False, default=list)
    education = ResumeEducationInputSerializer(many=True, required=False, default=list)
    skills = serializers.ListField(
        child=serializers.CharField(max_length=50), required=False, default=list
    )
    certificates = ResumeCertificateInputSerializer(many=True, required=False, default=list)

    def create(self, validated_data):
        careers = validated_data.pop('careers', [])
        education = validated_data.pop('education', [])
        skills = validated_data.pop('skills', [])
        certificates = validated_data.pop('certificates', [])
        user = self.context['user']

        if not validated_data.get('email'):
            validated_data['email'] = 'noreply@career.zip'

        resume = ResumeMaster.objects.create(user=user, **validated_data)

        for career in careers:
            ResumeCareer.objects.create(resume=resume, **career)
        for edu in education:
            ResumeEducation.objects.create(resume=resume, **edu)
        for skill_name in skills:
            ResumeSkill.objects.create(resume=resume, name=skill_name)
        for cert in certificates:
            ResumeCertificate.objects.create(resume=resume, **cert)

        return resume


class CoverLetterListSerializer(serializers.ModelSerializer):
    cover_letter_id = serializers.UUIDField(source='id')

    class Meta:
        model = CoverLetter
        fields = ('cover_letter_id', 'title', 'company_name', 'is_active', 'created_at', 'updated_at')
