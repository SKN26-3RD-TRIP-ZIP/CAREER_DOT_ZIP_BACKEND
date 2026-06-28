"""
로그인 없이 JWT 토큰을 직접 생성하는 스크립트.
Usage: python generate_tokens.py [email]
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.accounts.models import User
from rest_framework_simplejwt.tokens import RefreshToken

email = sys.argv[1] if len(sys.argv) > 1 else None

if email:
    try:
        user = User.objects.get(email=email)
        print(f"유저 찾음: {user.email} (id={user.pk})")
    except User.DoesNotExist:
        print(f"유저 없음: {email}")
        sys.exit(1)
else:
    # 첫 번째 유저 사용
    user = User.objects.first()
    if not user:
        print("DB에 유저가 없습니다. 먼저 유저를 생성하세요:")
        print("  python manage.py createsuperuser")
        sys.exit(1)
    print(f"첫 번째 유저 사용: {user.email} (id={user.pk})")

refresh = RefreshToken.for_user(user)
access = str(refresh.access_token)
refresh_str = str(refresh)

print()
print("=" * 60)
print("[1] Authorization 헤더 (API 요청 시)")
print(f"Authorization: Bearer {access}")
print()
print("[2] refresh_token 쿠키값")
print(f"refresh_token={refresh_str}")
print()
print("[3] 브라우저 DevTools > Application > Cookies 에서 직접 추가:")
print(f"  이름: refresh_token")
print(f"  값:   {refresh_str}")
print(f"  HttpOnly: true, SameSite: Lax")
print("=" * 60)
