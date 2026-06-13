import json

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


def _build_original_text_from_dropdown(data: dict) -> str:
    parts = []
    if data.get('job_category'):
        parts.append(f'[직무 카테고리] {data["job_category"]}')
    if data.get('experience_level'):
        parts.append(f'[경력 구분] {data["experience_level"]}')
    all_tech = [
        t.strip()
        for t in (data.get('tech_stacks', []) + data.get('custom_tech_stacks', []))
        if t.strip()
    ]
    if all_tech:
        parts.append(f'[기술스택] {", ".join(all_tech)}')
    if data.get('main_tasks'):
        parts.append(f'[주요업무] {data["main_tasks"]}')
    if data.get('requirements'):
        parts.append(f'[자격요건] {data["requirements"]}')
    if data.get('preferences'):
        parts.append(f'[우대사항] {data["preferences"]}')
    if data.get('jd_text'):
        parts.append(f'[추가 설명] {data["jd_text"]}')
    return '\n'.join(parts)


def _build_keywords_from_dropdown(data: dict) -> list:
    raw = []
    if data.get('job_category'):
        raw.append(data['job_category'])
    if data.get('experience_level'):
        raw.append(data['experience_level'])
    raw.extend(t.strip() for t in data.get('tech_stacks', []) if t.strip())
    raw.extend(t.strip() for t in data.get('custom_tech_stacks', []) if t.strip())
    raw.extend(k.strip() for k in data.get('custom_keywords', []) if k.strip())
    seen = set()
    unique = []
    for kw in raw:
        if kw and kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique


class JobDescriptionCreateSerializer(serializers.ModelSerializer):
    job_category = serializers.CharField(required=False, allow_blank=True, write_only=True)
    experience_level = serializers.CharField(required=False, allow_blank=True, write_only=True)
    tech_stacks = serializers.ListField(
        child=serializers.CharField(allow_blank=False),
        required=False,
        default=list,
        write_only=True,
    )
    custom_tech_stacks = serializers.ListField(
        child=serializers.CharField(allow_blank=False),
        required=False,
        default=list,
        write_only=True,
    )
    main_tasks = serializers.CharField(required=False, allow_blank=True, write_only=True)
    requirements = serializers.CharField(required=False, allow_blank=True, write_only=True)
    preferences = serializers.CharField(required=False, allow_blank=True, write_only=True)
    jd_text = serializers.CharField(required=False, allow_blank=True, write_only=True)
    custom_keywords = serializers.ListField(
        child=serializers.CharField(allow_blank=False),
        required=False,
        default=list,
        write_only=True,
    )

    class Meta:
        model = JobDescription
        fields = (
            'company_name',
            'position',
            'original_text',
            'input_method',
            'job_category',
            'experience_level',
            'tech_stacks',
            'custom_tech_stacks',
            'main_tasks',
            'requirements',
            'preferences',
            'jd_text',
            'custom_keywords',
        )
        extra_kwargs = {
            'original_text': {'required': False, 'allow_blank': True},
        }

    def validate(self, attrs):
        original_text = (attrs.get('original_text') or '').strip()
        text_fields = [
            attrs.get('job_category', ''),
            attrs.get('experience_level', ''),
            attrs.get('main_tasks', ''),
            attrs.get('requirements', ''),
            attrs.get('preferences', ''),
            attrs.get('jd_text', ''),
        ]
        has_dropdown_text = any((v or '').strip() for v in text_fields)
        has_dropdown_list = bool(
            attrs.get('tech_stacks') or
            attrs.get('custom_tech_stacks') or
            attrs.get('custom_keywords')
        )
        if not original_text and not has_dropdown_text and not has_dropdown_list:
            raise serializers.ValidationError(
                'original_text 또는 드롭다운 입력값(job_category, tech_stacks 등) 중 하나는 필수입니다.'
            )
        return attrs

    def create(self, validated_data):
        dropdown_data = {
            'job_category': validated_data.pop('job_category', '') or '',
            'experience_level': validated_data.pop('experience_level', '') or '',
            'tech_stacks': validated_data.pop('tech_stacks', []) or [],
            'custom_tech_stacks': validated_data.pop('custom_tech_stacks', []) or [],
            'main_tasks': validated_data.pop('main_tasks', '') or '',
            'requirements': validated_data.pop('requirements', '') or '',
            'preferences': validated_data.pop('preferences', '') or '',
            'jd_text': validated_data.pop('jd_text', '') or '',
            'custom_keywords': validated_data.pop('custom_keywords', []) or [],
        }

        dropdown_text = _build_original_text_from_dropdown(dropdown_data)
        existing_text = (validated_data.get('original_text') or '').strip()
        if dropdown_text:
            validated_data['original_text'] = '\n'.join(filter(None, [dropdown_text, existing_text]))
        elif not existing_text:
            validated_data['original_text'] = ''

        new_keywords = _build_keywords_from_dropdown(dropdown_data)
        if new_keywords:
            validated_data['keywords'] = json.dumps(new_keywords, ensure_ascii=False)

        requirements = dropdown_data.get('requirements', '')
        if requirements and not validated_data.get('job_requirements'):
            validated_data['job_requirements'] = requirements

        return super().create(validated_data)


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


CAREER_TYPE_INPUT_CHOICES = ('new', 'career')
MAJOR_TYPE_INPUT_CHOICES = ('major', 'non_major')


class UserProfileCreateSerializer(serializers.ModelSerializer):
    career_type = serializers.ChoiceField(choices=CAREER_TYPE_INPUT_CHOICES)
    major_type = serializers.ChoiceField(choices=MAJOR_TYPE_INPUT_CHOICES)

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
    career_type = serializers.ChoiceField(choices=CAREER_TYPE_INPUT_CHOICES, required=False)
    major_type = serializers.ChoiceField(choices=MAJOR_TYPE_INPUT_CHOICES, required=False)

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
