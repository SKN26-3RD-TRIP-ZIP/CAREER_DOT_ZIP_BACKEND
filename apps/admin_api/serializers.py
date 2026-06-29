from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import AuditLog
from apps.accounts.models import PointHistory, PointPolicy
from apps.interview.models import GuardrailEvent


User = get_user_model()
ADMIN_MEMBER_STATUS_CHOICES = tuple(User.STATUS_CHOICES) + (('suspended', 'Suspended'),)


class PageQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(required=False, default=1, min_value=1)
    size = serializers.IntegerField(required=False, default=20, min_value=1, max_value=100)


class MemberListQuerySerializer(PageQuerySerializer):
    status = serializers.ChoiceField(choices=ADMIN_MEMBER_STATUS_CHOICES, required=False)
    search = serializers.CharField(required=False, max_length=255, allow_blank=True)


class MemberListSerializer(serializers.ModelSerializer):
    practice_count = serializers.IntegerField(read_only=True)
    monthly_session_count = serializers.IntegerField(read_only=True)
    report_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'name',
            'is_staff',
            'status',
            'practice_count',
            'monthly_session_count',
            'report_count',
            'last_login',
            'created_at',
        )


class MemberStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ADMIN_MEMBER_STATUS_CHOICES)


class MemberInviteSerializer(serializers.Serializer):
    email = serializers.EmailField()


class AuditLogQuerySerializer(PageQuerySerializer):
    action_type = serializers.CharField(required=False, max_length=50)
    actor_id = serializers.IntegerField(required=False, min_value=1)


class AuditLogSerializer(serializers.ModelSerializer):
    audit_log_id = serializers.IntegerField(source='id', read_only=True)
    actor_id = serializers.IntegerField(read_only=True, allow_null=True)
    actor_name = serializers.CharField(source='actor.name', read_only=True, allow_null=True)
    target_name = serializers.SerializerMethodField()

    def get_target_name(self, obj):
        if obj.target_type == User._meta.db_table:
            user = User.objects.filter(id=obj.target_id).first()
            return user.name if user else None
        return None

    class Meta:
        model = AuditLog
        fields = (
            'audit_log_id',
            'actor_id',
            'actor_name',
            'action_type',
            'target_type',
            'target_id',
            'target_name',
            'before_value',
            'after_value',
            'created_at',
        )


class AdminPointAdjustSerializer(serializers.Serializer):
    amount = serializers.IntegerField()
    reason = serializers.CharField(max_length=500)
    idempotency_key = serializers.CharField(required=False, allow_blank=True, max_length=120)


class AdminPointHistoryQuerySerializer(PageQuerySerializer):
    user_id = serializers.IntegerField(required=False, min_value=1)
    transaction_type = serializers.ChoiceField(choices=PointHistory.TRANSACTION_TYPE_CHOICES, required=False)
    search = serializers.CharField(required=False, max_length=255, allow_blank=True)


class AdminPointHistorySerializer(serializers.ModelSerializer):
    point_history_id = serializers.IntegerField(source='id', read_only=True)
    user_id = serializers.IntegerField(read_only=True)
    user_name = serializers.CharField(source='user.name', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = PointHistory
        fields = (
            'point_history_id',
            'user_id',
            'user_name',
            'user_email',
            'transaction_type',
            'amount',
            'balance_after',
            'reason_code',
            'reference_id',
            'policy_version',
            'description',
            'created_at',
        )


class AdminPointPolicySerializer(serializers.ModelSerializer):
    policy_id = serializers.IntegerField(source='id', read_only=True)

    class Meta:
        model = PointPolicy
        fields = (
            'policy_id',
            'reason_code',
            'transaction_type',
            'amount',
            'daily_limit',
            'monthly_limit',
            'is_active',
            'policy_version',
            'description',
            'updated_at',
        )


class AdminPointPolicyUpdateSerializer(serializers.Serializer):
    amount = serializers.IntegerField(required=False)
    is_active = serializers.BooleanField(required=False)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate(self, attrs):
        if 'amount' not in attrs and 'is_active' not in attrs:
            raise serializers.ValidationError('수정할 항목(amount 또는 is_active)이 없습니다.')
        return attrs


class AdminGuardrailEventQuerySerializer(PageQuerySerializer):
    category = serializers.ChoiceField(choices=GuardrailEvent.CATEGORY_CHOICES, required=False)
    action = serializers.ChoiceField(choices=GuardrailEvent.ACTION_CHOICES, required=False)
    stage = serializers.ChoiceField(choices=GuardrailEvent.STAGE_CHOICES, required=False)
    direction = serializers.ChoiceField(choices=GuardrailEvent.DIRECTION_CHOICES, required=False)
    user_id = serializers.IntegerField(required=False, min_value=1)


class AdminGuardrailEventSerializer(serializers.ModelSerializer):
    guardrail_event_id = serializers.IntegerField(source='id', read_only=True)
    user_id = serializers.IntegerField(read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    session_id = serializers.UUIDField(read_only=True)
    question_id = serializers.UUIDField(read_only=True)
    answer_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = GuardrailEvent
        fields = (
            'guardrail_event_id',
            'user_id',
            'user_email',
            'session_id',
            'question_id',
            'answer_id',
            'category',
            'action',
            'stage',
            'direction',
            'rule_source',
            'reason_code',
            'masked_excerpt',
            'endpoint',
            'retention_until',
            'created_at',
        )
