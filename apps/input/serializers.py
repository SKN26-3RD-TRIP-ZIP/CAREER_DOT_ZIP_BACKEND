from rest_framework import serializers
from .models import (
    JobDescription,
    ProjectExperience,
    CoverLetter,
    CoverLetterItem,
    ResumeMaster,
    UserProfile,
    ResumeEducation,
    ResumeCareer,
    ResumeSkill,
    ResumeCertificate,
)


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


class ProjectExperienceCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectExperience
        fields = (
            'project_name',
            'description',
            'contribution',
            'tech_stack',
            'github_url',
            'start_date',
            'end_date',
        )
        extra_kwargs = {
            'contribution': {'required': False},
            'tech_stack': {'required': False, 'default': list},
            'github_url': {'required': False},
            'start_date': {'required': False},
            'end_date': {'required': False},
        }


class ProjectExperienceListSerializer(serializers.ModelSerializer):
    project_id = serializers.SerializerMethodField()

    class Meta:
        model = ProjectExperience
        fields = (
            'project_id',
            'project_name',
            'description',
            'contribution',
            'tech_stack',
            'github_url',
            'start_date',
            'end_date',
            'created_at',
            'updated_at',
        )

    def get_project_id(self, obj):
        return str(obj.id)


class CoverLetterItemCreateSerializer(serializers.Serializer):
    question = serializers.CharField()
    answer_text = serializers.CharField()
    max_length = serializers.IntegerField(required=False, allow_null=True)
    order_index = serializers.IntegerField(required=False, default=1)


class CoverLetterItemDetailSerializer(serializers.ModelSerializer):
    cover_letter_item_id = serializers.SerializerMethodField()
    length = serializers.SerializerMethodField()

    class Meta:
        model = CoverLetterItem
        fields = (
            'cover_letter_item_id',
            'question',
            'answer_text',
            'length',
            'max_length',
            'order_index',
        )

    def get_cover_letter_item_id(self, obj):
        return str(obj.id)

    def get_length(self, obj):
        return len(obj.answer_text or '')


class CoverLetterCreateSerializer(serializers.ModelSerializer):
    jd_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    items = CoverLetterItemCreateSerializer(many=True)

    class Meta:
        model = CoverLetter
        fields = ('title', 'company_name', 'jd_id', 'items')
        extra_kwargs = {
            'company_name': {'required': False, 'allow_blank': True, 'allow_null': True},
        }

    def validate_jd_id(self, value):
        if value is None:
            return None

        user = self.context['request'].user
        try:
            return JobDescription.objects.get(id=value, user=user)
        except JobDescription.DoesNotExist:
            raise serializers.ValidationError('Job description not found.')

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        jd = validated_data.pop('jd_id', None)
        if jd is not None:
            validated_data['jd'] = jd

        cover_letter = CoverLetter.objects.create(**validated_data)

        for item_data in items_data:
            CoverLetterItem.objects.create(cover_letter=cover_letter, **item_data)

        return cover_letter


class CoverLetterListSerializer(serializers.ModelSerializer):
    cover_letter_id = serializers.SerializerMethodField()

    class Meta:
        model = CoverLetter
        fields = ('cover_letter_id', 'title', 'company_name', 'is_active', 'created_at')

    def get_cover_letter_id(self, obj):
        return str(obj.id)


class CoverLetterDetailSerializer(serializers.ModelSerializer):
    cover_letter_id = serializers.SerializerMethodField()
    jd_id = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()

    class Meta:
        model = CoverLetter
        fields = ('cover_letter_id', 'title', 'jd_id', 'items', 'updated_at')

    def get_cover_letter_id(self, obj):
        return str(obj.id)

    def get_jd_id(self, obj):
        return str(obj.jd.id) if obj.jd else None

    def get_items(self, obj):
        return CoverLetterItemDetailSerializer(obj.items.all().order_by('order_index'), many=True).data


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
        return ResumeEducationListSerializer(obj.education.all(), many=True).data

    def get_careers(self, obj):
        return ResumeCareerListSerializer(obj.careers.all(), many=True).data

    def get_skills(self, obj):
        return ResumeSkillListSerializer(obj.skills.all(), many=True).data

    def get_certificates(self, obj):
        return ResumeCertificateListSerializer(obj.certificates.all(), many=True).data


class ResumeEducationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeEducation
        fields = ('school_name', 'major', 'degree', 'start_date', 'end_date', 'status')


class ResumeEducationListSerializer(serializers.ModelSerializer):
    resume_edu_id = serializers.SerializerMethodField()

    class Meta:
        model = ResumeEducation
        fields = ('resume_edu_id', 'school_name', 'major', 'degree', 'start_date', 'end_date', 'status', 'created_at')

    def get_resume_edu_id(self, obj):
        return str(obj.id)


class ResumeCareerCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeCareer
        fields = ('company_name', 'position', 'start_date', 'end_date', 'is_current', 'description')


class ResumeCareerListSerializer(serializers.ModelSerializer):
    resume_career_id = serializers.SerializerMethodField()

    class Meta:
        model = ResumeCareer
        fields = ('resume_career_id', 'company_name', 'position', 'start_date', 'end_date', 'is_current', 'description', 'created_at')

    def get_resume_career_id(self, obj):
        return str(obj.id)


class ResumeSkillCreateSerializer(serializers.Serializer):
    skills = serializers.ListField(child=serializers.CharField(max_length=50))

    def create(self, validated_data):
        resume_id = self.context.get('resume_id')
        resume = ResumeMaster.objects.get(id=resume_id)
        skills = validated_data['skills']
        created_skills = []
        for skill_name in skills:
            skill = ResumeSkill.objects.create(resume=resume, name=skill_name)
            created_skills.append(skill)
        return created_skills


class ResumeSkillListSerializer(serializers.ModelSerializer):
    resume_skill_id = serializers.SerializerMethodField()

    class Meta:
        model = ResumeSkill
        fields = ('resume_skill_id', 'name', 'created_at')

    def get_resume_skill_id(self, obj):
        return str(obj.id)


class ResumeCertificateCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeCertificate
        fields = ('name', 'issued_by', 'issued_at')


class ResumeCertificateListSerializer(serializers.ModelSerializer):
    resume_certificate_id = serializers.SerializerMethodField()

    class Meta:
        model = ResumeCertificate
        fields = ('resume_certificate_id', 'name', 'issued_by', 'issued_at', 'created_at')

    def get_resume_certificate_id(self, obj):
        return str(obj.id)
