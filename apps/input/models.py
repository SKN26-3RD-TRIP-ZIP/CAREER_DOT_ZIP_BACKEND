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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'input_jobdescription'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.company_name} - {self.position}"


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

