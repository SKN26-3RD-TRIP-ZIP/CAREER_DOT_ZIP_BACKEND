from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import connection
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """Custom user manager for email-based authentication."""

    def _has_legacy_role_column(self):
        """Return whether the current DB still has the removed role column."""
        try:
            with connection.cursor() as cursor:
                columns = connection.introspection.get_table_description(cursor, self.model._meta.db_table)
            return any(column.name == 'role' for column in columns)
        except Exception:
            return False
    
    def create_user(self, email, password, name, **extra_fields):
        """Create and save a regular user."""
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        legacy_role = extra_fields.pop('role', None)
        user = self.model(email=email, name=name, **extra_fields)
        user.set_password(password)
        if self._has_legacy_role_column():
            now = timezone.now()
            role = legacy_role or ('admin' if user.is_staff or user.is_superuser else 'user')
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO accounts_user (
                        password, last_login, is_superuser, email, name,
                        is_verified, status, is_staff, is_active,
                        point_balance, created_at, updated_at, role
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        user.password,
                        user.last_login,
                        user.is_superuser,
                        user.email,
                        user.name,
                        user.is_verified,
                        user.status,
                        user.is_staff,
                        user.is_active,
                        user.point_balance,
                        now,
                        now,
                        role,
                    ],
                )
                user.id = cursor.lastrowid
            user.created_at = now
            user.updated_at = now
            return user
        user.save(using=self._db)
        return user

    def create_user_with_password_hash(self, email, password_hash, name, **extra_fields):
        """Create a user from an already-generated Django password hash."""
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        legacy_role = extra_fields.pop('role', None)
        user = self.model(email=email, name=name, password=password_hash, **extra_fields)
        if self._has_legacy_role_column():
            now = timezone.now()
            role = legacy_role or ('admin' if user.is_staff or user.is_superuser else 'user')
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO accounts_user (
                        password, last_login, is_superuser, email, name,
                        is_verified, status, is_staff, is_active,
                        point_balance, created_at, updated_at, role
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        user.password,
                        user.last_login,
                        user.is_superuser,
                        user.email,
                        user.name,
                        user.is_verified,
                        user.status,
                        user.is_staff,
                        user.is_active,
                        user.point_balance,
                        now,
                        now,
                        role,
                    ],
                )
                user.id = cursor.lastrowid
            user.created_at = now
            user.updated_at = now
            return user
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password, name, **extra_fields):
        """Create and save a superuser."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(email, password, name, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model with email-based authentication."""
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('dormant', 'Dormant'),
        ('banned', 'Banned'),
        ('withdrawn', 'Withdrawn'),
    ]

    id = models.BigAutoField(primary_key=True)
    email = models.EmailField(unique=True, db_index=True)
    name = models.CharField(max_length=255)
    is_verified = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    dormancy_warning_sent_at = models.DateTimeField(null=True, blank=True, default=None)
    point_balance = models.PositiveIntegerField(default=0)
    point_last_updated_at = models.DateTimeField(null=True, blank=True, default=None)
    withdrawn_at = models.DateTimeField(null=True, blank=True, default=None)
    attendance_record = models.DateField(null=True, blank=True, default=None)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True, default=None)
    onboarding_version = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']
    
    class Meta:
        db_table = 'accounts_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-created_at']

    def __str__(self):
        return self.email


class EmailVerificationCode(models.Model):
    """
    회원가입 이메일 인증용 6자리 인증번호 저장.

    - 평문 코드는 저장하지 않고 해시(code_hash)만 보관한다.
    - 만료(expires_at), 입력 시도 횟수(attempt_count), 사용 여부(is_used)로
      만료/무차별 대입 방지/재발송 쿨다운을 제어한다.
    """
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='email_codes',
    )
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempt_count = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_email_verification_code'
        verbose_name = 'Email Verification Code'
        verbose_name_plural = 'Email Verification Codes'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_used'], name='evc_user_isused_idx'),
            models.Index(fields=['expires_at'], name='evc_expires_idx'),
        ]

    def __str__(self):
        return f'EmailVerificationCode(user_id={self.user_id}, used={self.is_used})'


class PendingRegistration(models.Model):
    """Pending signup data stored until the email code is verified."""

    id = models.BigAutoField(primary_key=True)
    email = models.EmailField(unique=True, db_index=True)
    password_hash = models.CharField(max_length=128)
    name = models.CharField(max_length=255)
    code_hash = models.CharField(max_length=128, blank=True)
    expires_at = models.DateTimeField()
    resend_available_at = models.DateTimeField()
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    is_used = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    terms_version = models.CharField(max_length=50, default='v1')
    privacy_version = models.CharField(max_length=50, default='v1')
    terms_agreed = models.BooleanField(default=False)
    privacy_agreed = models.BooleanField(default=False)
    marketing_agreed = models.BooleanField(default=False)
    agreed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'accounts_pending_registration'
        verbose_name = 'Pending Registration'
        verbose_name_plural = 'Pending Registrations'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', 'is_used'], name='pending_email_used_idx'),
            models.Index(fields=['expires_at'], name='pending_expires_idx'),
        ]

    def __str__(self):
        return f'PendingRegistration(email={self.email}, used={self.is_used})'


class TermsDocument(models.Model):
    KIND_TERMS = 'TERMS'
    KIND_PRIVACY = 'PRIVACY'
    KIND_MARKETING = 'MARKETING'

    KIND_CHOICES = [
        (KIND_TERMS, 'Terms'),
        (KIND_PRIVACY, 'Privacy'),
        (KIND_MARKETING, 'Marketing'),
    ]

    id = models.BigAutoField(primary_key=True)
    kind = models.CharField(max_length=30, choices=KIND_CHOICES)
    version = models.CharField(max_length=50)
    title = models.CharField(max_length=150, blank=True, default='')
    content_hash = models.CharField(max_length=128, blank=True, default='')
    is_required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    effective_at = models.DateTimeField(default=timezone.now)
    retired_at = models.DateTimeField(null=True, blank=True, default=None)
    retention_policy = models.CharField(max_length=200, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'terms_documents'
        ordering = ['kind', '-effective_at', '-id']
        constraints = [
            models.UniqueConstraint(fields=['kind', 'version'], name='unique_terms_document_version'),
        ]
        indexes = [
            models.Index(fields=['kind', 'is_active'], name='terms_kind_active_idx'),
        ]

    def __str__(self):
        return f'{self.kind} {self.version}'


class TermsAgreement(models.Model):
    SOURCE_SIGNUP = 'SIGNUP'
    SOURCE_MYPAGE = 'MYPAGE'
    SOURCE_ADMIN = 'ADMIN'

    SOURCE_CHOICES = [
        (SOURCE_SIGNUP, 'Signup'),
        (SOURCE_MYPAGE, 'Mypage'),
        (SOURCE_ADMIN, 'Admin'),
    ]

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='terms_agreements',
    )
    document = models.ForeignKey(
        TermsDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agreements',
    )
    kind = models.CharField(max_length=30, choices=TermsDocument.KIND_CHOICES)
    version = models.CharField(max_length=50)
    is_required = models.BooleanField(default=False)
    agreed = models.BooleanField(default=True)
    agreed_at = models.DateTimeField(null=True, blank=True, default=None)
    withdrawn_at = models.DateTimeField(null=True, blank=True, default=None)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True, default='')
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default=SOURCE_SIGNUP)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'terms_agreements'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['user', 'kind'], name='terms_user_kind_idx'),
            models.Index(fields=['user', 'created_at'], name='terms_user_created_idx'),
        ]

    def __str__(self):
        return f'TermsAgreement(user_id={self.user_id}, {self.kind} {self.version}, agreed={self.agreed})'


class PointHistory(models.Model):
    TRANSACTION_EARN = 'EARN'
    TRANSACTION_USE = 'USE'
    TRANSACTION_REFUND = 'REFUND'
    TRANSACTION_EXPIRE = 'EXPIRE'
    TRANSACTION_ADMIN = 'ADMIN'

    TRANSACTION_TYPE_CHOICES = [
        (TRANSACTION_EARN, 'Earn'),
        (TRANSACTION_USE, 'Use'),
        (TRANSACTION_REFUND, 'Refund'),
        (TRANSACTION_EXPIRE, 'Expire'),
        (TRANSACTION_ADMIN, 'Admin'),
    ]

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='point_histories',
    )
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    amount = models.IntegerField()
    balance_after = models.PositiveIntegerField()
    reason_code = models.CharField(max_length=80)
    reference_id = models.CharField(max_length=100, blank=True, default='')
    idempotency_key = models.CharField(max_length=120, unique=True, null=True, blank=True)
    policy_version = models.CharField(max_length=30, default='2026.06')
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_point_history'
        verbose_name = 'Point History'
        verbose_name_plural = 'Point Histories'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['user', 'created_at'], name='point_user_created_idx'),
            models.Index(fields=['reason_code'], name='point_reason_idx'),
        ]

    def __str__(self):
        return f'PointHistory(user_id={self.user_id}, amount={self.amount})'


class PointPolicy(models.Model):
    id = models.BigAutoField(primary_key=True)
    reason_code = models.CharField(max_length=80, unique=True)
    transaction_type = models.CharField(max_length=20, choices=PointHistory.TRANSACTION_TYPE_CHOICES)
    amount = models.IntegerField()
    daily_limit = models.PositiveIntegerField(null=True, blank=True, default=None)
    monthly_limit = models.PositiveIntegerField(null=True, blank=True, default=None)
    account_once = models.BooleanField(default=False)
    per_reference_once = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    policy_version = models.CharField(max_length=30, default='2026.06')
    effective_start_at = models.DateTimeField(default=timezone.now)
    effective_end_at = models.DateTimeField(null=True, blank=True, default=None)
    description = models.TextField(blank=True, default='')
    updated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='updated_point_policies',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'point_policies'
        ordering = ['reason_code']
        indexes = [
            models.Index(fields=['reason_code', 'is_active'], name='point_policy_active_idx'),
            models.Index(fields=['effective_start_at', 'effective_end_at'], name='point_policy_period_idx'),
        ]

    def __str__(self):
        return f'{self.reason_code} ({self.amount})'


class PointPolicyChangeLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    policy = models.ForeignKey(
        PointPolicy,
        on_delete=models.CASCADE,
        related_name='change_logs',
    )
    actor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='point_policy_change_logs',
    )
    before_value = models.JSONField(default=dict, blank=True)
    after_value = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'point_policy_change_logs'
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'PointPolicyChangeLog(policy_id={self.policy_id})'


class SocialAccount(models.Model):
    PROVIDER_GOOGLE = 'google'
    PROVIDER_KAKAO = 'kakao'

    PROVIDER_CHOICES = [
        (PROVIDER_GOOGLE, 'Google'),
        (PROVIDER_KAKAO, 'Kakao'),
    ]

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='social_accounts',
    )
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    provider_user_id = models.CharField(max_length=191)
    provider_email = models.EmailField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login_at = models.DateTimeField(null=True, blank=True, default=None)

    class Meta:
        db_table = 'social_accounts'
        ordering = ['provider', 'provider_user_id']
        constraints = [
            models.UniqueConstraint(fields=['provider', 'provider_user_id'], name='unique_social_provider_user'),
            models.UniqueConstraint(fields=['user', 'provider'], name='unique_user_social_provider'),
        ]
        indexes = [
            models.Index(fields=['provider', 'provider_email'], name='social_provider_email_idx'),
        ]

    def __str__(self):
        return f'{self.provider}:{self.provider_user_id}'
