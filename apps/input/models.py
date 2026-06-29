import uuid
from django.db import models
from django.conf import settings


class JobDescription(models.Model):
    INPUT_METHOD_CHOICES = [
        ('TEXT', 'Text'),
        ('PDF', 'PDF'),
        ('URL', 'URL'),
        ('OCR', 'OCR'),
    ]

    ANALYSIS_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='job_descriptions')
    company_name = models.CharField(max_length=100)
    position = models.CharField(max_length=100)
    original_text = models.TextField()
    input_method = models.CharField(max_length=10, choices=INPUT_METHOD_CHOICES, default='TEXT')
    company_summary = models.TextField(blank=True, null=True)
    talent_profile = models.TextField(blank=True, null=True)
    job_requirements = models.TextField(blank=True, null=True)
    keywords = models.TextField(blank=True, null=True)
    analysis_status = models.CharField(max_length=20, choices=ANALYSIS_STATUS_CHOICES, default='PENDING')
    source_url = models.URLField(blank=True, null=True)
    source_fetched_at = models.DateTimeField(blank=True, null=True)
    extraction_confidence = models.FloatField(default=0)
    extracted_fields = models.JSONField(default=dict, blank=True)
    is_mock_source = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'input_jobdescription'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.company_name} - {self.position}"


class TalentProfileCategory(models.Model):
    category_id = models.BigAutoField(primary_key=True)
    category_code = models.CharField(max_length=50, unique=True)
    category_name = models.CharField(max_length=50)
    short_description = models.CharField(max_length=200)
    detailed_description = models.TextField(blank=True, null=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'talent_profile_categories'
        ordering = ['display_order', 'category_id']

    def __str__(self):
        return self.category_name


class TalentProfileTrait(models.Model):
    trait_id = models.BigAutoField(primary_key=True)
    category = models.ForeignKey(TalentProfileCategory, on_delete=models.PROTECT, related_name='traits')
    trait_code = models.CharField(max_length=50, unique=True)
    trait_name = models.CharField(max_length=50)
    short_description = models.CharField(max_length=250)
    detailed_description = models.TextField(blank=True, null=True)
    positive_signals = models.JSONField(default=list, blank=True)
    negative_signals = models.JSONField(default=list, blank=True)
    question_templates = models.JSONField(default=list, blank=True)
    followup_templates = models.JSONField(default=list, blank=True)
    evaluation_dimensions = models.JSONField(default=list, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'talent_profile_traits'
        ordering = ['category__display_order', 'display_order', 'trait_id']

    def __str__(self):
        return self.trait_name


class JDTalentProfile(models.Model):
    SOURCE_TYPE_OFFICIAL = 'OFFICIAL'
    SOURCE_TYPE_AI_EXTRACTED = 'AI_EXTRACTED'
    SOURCE_TYPE_USER_DEFINED = 'USER_DEFINED'
    SOURCE_TYPE_JOB_DEFAULT = 'JOB_DEFAULT'
    SOURCE_TYPE_HYBRID = 'HYBRID'
    SOURCE_TYPE_CHOICES = [
        (SOURCE_TYPE_OFFICIAL, 'Official'),
        (SOURCE_TYPE_AI_EXTRACTED, 'AI Extracted'),
        (SOURCE_TYPE_USER_DEFINED, 'User Defined'),
        (SOURCE_TYPE_JOB_DEFAULT, 'Job Default'),
        (SOURCE_TYPE_HYBRID, 'Hybrid'),
    ]

    jd_talent_profile_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    jd = models.OneToOneField(JobDescription, on_delete=models.CASCADE, related_name='custom_talent_profile')
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES)
    source_text = models.TextField(blank=True, null=True)
    custom_summary = models.TextField(blank=True, null=True)
    confirmed_by_user = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'jd_talent_profiles'
        ordering = ['-updated_at']

    def __str__(self):
        return f"Talent profile for JD {self.jd_id}"


class JDTalentProfileItem(models.Model):
    item_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    jd_talent_profile = models.ForeignKey(JDTalentProfile, on_delete=models.CASCADE, related_name='items')
    trait = models.ForeignKey(TalentProfileTrait, on_delete=models.PROTECT, related_name='selected_items')
    priority_order = models.PositiveSmallIntegerField()
    custom_description = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'jd_talent_profile_items'
        ordering = ['priority_order', 'created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['jd_talent_profile', 'trait'],
                name='unique_jd_talent_profile_trait',
            ),
            models.UniqueConstraint(
                fields=['jd_talent_profile', 'priority_order'],
                name='unique_jd_talent_profile_priority',
            ),
            models.CheckConstraint(
                check=models.Q(priority_order__gte=1) & models.Q(priority_order__lte=5),
                name='jd_talent_profile_priority_1_5',
            ),
        ]

    def __str__(self):
        return f"{self.jd_talent_profile_id} - {self.trait_id}"


class ProjectExperience(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='projects')
    project_name = models.CharField(max_length=100)
    description = models.TextField()
    contribution = models.TextField(blank=True, null=True)
    tech_stack = models.JSONField(default=list)
    github_url = models.URLField(blank=True, null=True)
    start_date = models.CharField(max_length=7, blank=True, null=True)
    end_date = models.CharField(max_length=7, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'input_projectexperience'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.project_name} ({self.user})"


class CoverLetter(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cover_letters')
    jd = models.ForeignKey('input.JobDescription', on_delete=models.SET_NULL, null=True, blank=True, related_name='cover_letters')
    title = models.CharField(max_length=150)
    company_name = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'input_coverletter'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.user})"


class CoverLetterItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cover_letter = models.ForeignKey(CoverLetter, on_delete=models.CASCADE, related_name='items')
    question = models.TextField()
    answer_text = models.TextField()
    max_length = models.PositiveIntegerField(blank=True, null=True)
    order_index = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'input_coverletteritem'
        ordering = ['order_index', 'created_at']

    def __str__(self):
        return f"{self.cover_letter.title} item {self.order_index}"


class ResumeMaster(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='resumes')
    name = models.CharField(max_length=50)
    phone = models.CharField(max_length=30, blank=True, null=True)
    email = models.EmailField()
    address = models.CharField(max_length=255, blank=True, null=True)
    github_url = models.URLField(blank=True, null=True)
    original_text = models.TextField(blank=True, null=True)
    extracted_keywords = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'input_resumemaster'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.user})"


class UserProfile(models.Model):
    CAREER_TYPE_CHOICES = [
        ('신입', '신입'),
        ('경력', '경력'),
    ]
    MAJOR_TYPE_CHOICES = [
        ('전공', '전공'),
        ('비전공', '비전공'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    career_type = models.CharField(max_length=10, choices=CAREER_TYPE_CHOICES)
    major_type = models.CharField(max_length=10, choices=MAJOR_TYPE_CHOICES)
    desired_job = models.CharField(max_length=100)
    career_year = models.PositiveIntegerField(default=0)
    github_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'input_userprofile'
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user} Profile"


class ResumeEducation(models.Model):
    DEGREE_CHOICES = [
        ('high_school', 'High School'),
        ('associate', 'Associate'),
        ('bachelor', 'Bachelor'),
        ('master', 'Master'),
        ('doctor', 'Doctor'),
    ]
    STATUS_CHOICES = [
        ('graduated', 'Graduated'),
        ('enrolled', 'Enrolled'),
        ('leave_of_absence', 'Leave of Absence'),
        ('dropped_out', 'Dropped Out'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resume = models.ForeignKey(ResumeMaster, on_delete=models.CASCADE, related_name='education')
    school_name = models.CharField(max_length=100)
    major = models.CharField(max_length=100, blank=True, null=True)
    degree = models.CharField(max_length=20, choices=DEGREE_CHOICES)
    start_date = models.CharField(max_length=7, blank=True, null=True)
    end_date = models.CharField(max_length=7, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'input_resumeeducation'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.school_name} ({self.resume.user})"


class ResumeCareer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resume = models.ForeignKey(ResumeMaster, on_delete=models.CASCADE, related_name='careers')
    company_name = models.CharField(max_length=100)
    position = models.CharField(max_length=100)
    start_date = models.CharField(max_length=7, blank=True, null=True)
    end_date = models.CharField(max_length=7, blank=True, null=True)
    is_current = models.BooleanField(default=False)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'input_resumecareer'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.company_name} - {self.position} ({self.resume.user})"


class ResumeSkill(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resume = models.ForeignKey(ResumeMaster, on_delete=models.CASCADE, related_name='skills')
    name = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'input_resumeskill'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.resume.user})"


class ResumeCertificate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resume = models.ForeignKey(ResumeMaster, on_delete=models.CASCADE, related_name='certificates')
    name = models.CharField(max_length=100)
    issued_by = models.CharField(max_length=100, blank=True, null=True)
    issued_at = models.CharField(max_length=7, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'input_resumecertificate'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.resume.user})"

