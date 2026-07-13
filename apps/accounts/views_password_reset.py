import hashlib
import logging

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .emails import send_password_reset_email
from .models import User


logger = logging.getLogger("apps.accounts")

GENERIC_REQUEST_RESPONSE = {
    "detail": "가입된 계정이라면 비밀번호 재설정 링크를 이메일로 보내드렸습니다.",
    "code": "PASSWORD_RESET_REQUEST_ACCEPTED",
}


def _cache_key(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"password-reset:{prefix}:{digest}"


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=128)
    token = serializers.CharField(max_length=256)
    password = serializers.CharField(write_only=True, min_length=8, max_length=128)
    password_confirm = serializers.CharField(write_only=True, min_length=8, max_length=128)

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "비밀번호 확인이 일치하지 않습니다."}
            )

        try:
            user_id = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError(
                {"token": "유효하지 않거나 만료된 재설정 링크입니다."}
            )

        if not user.is_active or user.status in {"banned", "withdrawn"}:
            raise serializers.ValidationError(
                {"token": "유효하지 않거나 만료된 재설정 링크입니다."}
            )
        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError(
                {"token": "유효하지 않거나 만료된 재설정 링크입니다."}
            )

        try:
            validate_password(attrs["password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})

        attrs["user"] = user
        return attrs


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        cooldown = getattr(settings, "PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS", 60)

        email_allowed = cache.add(_cache_key("email", email), "1", cooldown)
        if not email_allowed:
            return Response(GENERIC_REQUEST_RESPONSE, status=status.HTTP_200_OK)

        user = User.objects.filter(email__iexact=email).first()
        if (
            user is not None
            and user.is_active
            and user.is_verified
            and user.has_usable_password()
            and user.status not in {"banned", "withdrawn"}
        ):
            try:
                send_password_reset_email(user)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "password reset email failed user_id=%s exc=%s",
                    user.id,
                    exc.__class__.__name__,
                )

        return Response(GENERIC_REQUEST_RESPONSE, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=["password", "updated_at"])
        logger.info("password reset completed user_id=%s", user.id)
        return Response(
            {
                "detail": "비밀번호가 변경되었습니다. 새 비밀번호로 로그인해주세요.",
                "code": "PASSWORD_RESET_COMPLETED",
            },
            status=status.HTTP_200_OK,
        )
