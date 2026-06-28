from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.services.oauth import (
    OAuthAccountBlocked,
    OAuthEmailRequired,
    OAuthError,
    OAuthProviderNotConfigured,
    OAuthStateInvalid,
    build_authorization_url,
    exchange_code_for_profile,
    get_or_create_social_user,
    get_provider_config,
    validate_oauth_state,
)
from apps.accounts.views import REFRESH_COOKIE_MAX_AGE, REFRESH_COOKIE_NAME
from django.conf import settings
from django.contrib.auth.models import update_last_login


class OAuthStartQuerySerializer(serializers.Serializer):
    next = serializers.CharField(required=False, allow_blank=True, max_length=255)


class OAuthCallbackSerializer(serializers.Serializer):
    code = serializers.CharField(required=False, allow_blank=True)
    state = serializers.CharField(required=False, allow_blank=True)
    error = serializers.CharField(required=False, allow_blank=True)
    error_description = serializers.CharField(required=False, allow_blank=True)


def _provider_not_configured_response(provider):
    config = get_provider_config(provider)
    return Response(
        {
            'detail': 'OAuth provider credentials are not configured.',
            'code': 'OAUTH_PROVIDER_NOT_CONFIGURED',
            'status': 'ENV_REQUIRED',
            'provider': config.provider,
            'required_env': config.required_env,
        },
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _set_refresh_cookie(response, refresh):
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=str(refresh),
        httponly=True,
        secure=getattr(settings, 'REFRESH_COOKIE_SECURE', False),
        samesite=getattr(settings, 'REFRESH_COOKIE_SAMESITE', 'Lax'),
        path=getattr(settings, 'REFRESH_COOKIE_PATH', '/'),
        domain=getattr(settings, 'REFRESH_COOKIE_DOMAIN', None),
        max_age=REFRESH_COOKIE_MAX_AGE,
    )


class OAuthStartView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, provider):
        serializer = OAuthStartQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            data = build_authorization_url(
                provider,
                next_path=serializer.validated_data.get('next') or '/',
            )
        except OAuthProviderNotConfigured:
            return _provider_not_configured_response(provider)
        except OAuthError as exc:
            return Response({'detail': str(exc), 'code': exc.code}, status=status.HTTP_400_BAD_REQUEST)
        return Response(data, status=status.HTTP_200_OK)


class OAuthCallbackView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, provider):
        return self._handle(request, provider, request.query_params)

    def post(self, request, provider):
        return self._handle(request, provider, request.data)

    def _handle(self, request, provider, data):
        serializer = OAuthCallbackSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        if payload.get('error'):
            return Response(
                {
                    'detail': payload.get('error_description') or payload['error'],
                    'code': 'OAUTH_PROVIDER_ERROR',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not payload.get('code') or not payload.get('state'):
            return Response(
                {'detail': 'code and state are required.', 'code': 'OAUTH_CALLBACK_INVALID'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            state_payload = validate_oauth_state(provider, payload['state'])
            profile = exchange_code_for_profile(provider, code=payload['code'])
            user, social, created = get_or_create_social_user(provider, profile)
        except OAuthProviderNotConfigured:
            return _provider_not_configured_response(provider)
        except OAuthStateInvalid as exc:
            return Response({'detail': str(exc), 'code': exc.code}, status=status.HTTP_400_BAD_REQUEST)
        except OAuthEmailRequired as exc:
            return Response({'detail': str(exc), 'code': exc.code}, status=status.HTTP_409_CONFLICT)
        except OAuthAccountBlocked as exc:
            return Response({'detail': str(exc), 'code': exc.code}, status=status.HTTP_403_FORBIDDEN)
        except OAuthError as exc:
            return Response({'detail': str(exc), 'code': exc.code}, status=status.HTTP_400_BAD_REQUEST)

        update_last_login(None, user)
        refresh = RefreshToken.for_user(user)
        response = Response(
            {
                'access_token': str(refresh.access_token),
                'token_type': 'Bearer',
                'provider': social.provider,
                'created': created,
                'next_path': state_payload.get('next_path') or '/mypage',
            },
            status=status.HTTP_200_OK,
        )
        _set_refresh_cookie(response, refresh)
        return response
