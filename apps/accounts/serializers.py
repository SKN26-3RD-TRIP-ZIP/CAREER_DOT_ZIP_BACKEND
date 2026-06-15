from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import User


class SignupSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ('email', 'name', 'password')

    def validate_email(self, value):
        """Validate email uniqueness."""
        existing = User.objects.filter(email=value).first()
        if existing:
            if existing.status == 'banned':
                raise serializers.ValidationError('This email is banned.')
            raise serializers.ValidationError('This email is already registered.')
        return value

    def create(self, validated_data):
        """Create a new user with the validated data."""
        password = validated_data.pop('password')
        user = User.objects.create_user(
            email=validated_data['email'],
            name=validated_data['name'],
            password=password,
        )
        return user


class SignupResponseSerializer(serializers.ModelSerializer):
    """Serializer for signup response."""
    user_id = serializers.SerializerMethodField()
    message = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('user_id', 'email', 'name', 'message')

    def get_user_id(self, obj):
        """Return user ID."""
        return obj.id

    def get_message(self, obj):
        """Return signup success message."""
        return '가입 완료. 이메일 인증 메일을 확인해주세요.'


class LoginSerializer(serializers.Serializer):
    """Serializer for user login."""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        """Validate credentials and user status."""
        email = data.get('email')
        password = data.get('password')

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError('Invalid email or password.')

        if not user.check_password(password):
            raise serializers.ValidationError('Invalid email or password.')

        # 이메일 인증 완료 여부로 차단한다. (이전: is_staff 로 잘못 검사하던 버그 수정)
        if not user.is_verified:
            raise serializers.ValidationError('Email not verified.')

        if user.status == 'dormant':
            raise serializers.ValidationError('Account is suspended.')

        if user.status == 'banned':
            raise serializers.ValidationError('Account is banned.')

        if not user.is_active:
            raise serializers.ValidationError('Account is inactive.')

        data['user'] = user
        return data
