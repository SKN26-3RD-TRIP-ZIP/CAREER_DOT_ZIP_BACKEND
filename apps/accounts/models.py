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
                        created_at, updated_at, role
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        created_at, updated_at, role
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
