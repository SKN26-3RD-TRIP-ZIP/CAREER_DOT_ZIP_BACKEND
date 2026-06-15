from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import AuditLog


User = get_user_model()


class PageQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(required=False, default=1, min_value=1)
    size = serializers.IntegerField(required=False, default=20, min_value=1, max_value=100)


class MemberListQuerySerializer(PageQuerySerializer):
    status = serializers.ChoiceField(choices=User.STATUS_CHOICES, required=False)
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
    status = serializers.ChoiceField(choices=User.STATUS_CHOICES)


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
