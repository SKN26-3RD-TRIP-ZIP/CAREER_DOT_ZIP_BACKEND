"""
회원가입 관련 메일 발송 모듈.

발송 메일:
1) 사용자 환영 메일 (이메일 인증 링크 포함)
2) 관리자 신규가입 알림 메일

보안 원칙:
- 비밀번호 / access token / refresh token / cookie / 이메일 인증 토큰 원문 /
  OAuth 인증코드 등 민감정보는 메일 본문·로그에 절대 포함하지 않는다.
- 관리자 알림에는 인증 토큰을 넣지 않는다(가입 사실/이름/이메일/시각/방식만).

발송 실패 정책(MVP):
- 호출부(SignupView)에서 try/except 로 감싸고 logger.exception 으로 기록한다.
- 메일/관리자 알림 실패가 회원가입 실패로 이어지지 않게 한다.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from .tokens import generate_email_verification_token

logger = logging.getLogger("apps.accounts")

SUPPORT_EMAIL = "support@career.zip"


def build_verification_url(user) -> str:
    """FE 기준 이메일 인증 URL 을 구성한다."""
    token = generate_email_verification_token(user)
    frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173").rstrip("/")
    return f"{frontend_base}/verify-email?token={token}"


def send_welcome_email(user) -> None:
    """가입 사용자에게 환영 메일(인증 링크 포함)을 발송한다."""
    verify_url = build_verification_url(user)
    subject = "[Career.zip] 가입을 환영합니다"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@career.zip")

    text_body = (
        f"{user.name}님, Career.zip 가입을 환영합니다!\n\n"
        f"아래 링크를 눌러 이메일 인증을 완료해 주세요 (24시간 이내):\n{verify_url}\n\n"
        f"인증 완료 후 프로필을 등록하면 AI 모의면접을 시작할 수 있습니다.\n\n"
        f"문의: {SUPPORT_EMAIL}\n"
    )

    html_body = f"""\
<div style="font-family:Apple SD Gothic Neo,Malgun Gothic,sans-serif;max-width:560px;margin:0 auto;color:#1f2937">
  <h2 style="color:#253900">Career.zip 가입을 환영합니다 🎉</h2>
  <p><strong>{user.name}</strong>님, AI 모의면접 서비스 Career.zip 에 가입해 주셔서 감사합니다.</p>
  <p>아래 버튼을 눌러 <strong>이메일 인증</strong>을 완료해 주세요. (링크는 24시간 동안 유효합니다.)</p>
  <p style="margin:24px 0">
    <a href="{verify_url}"
       style="background:#08CB00;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600">
       이메일 인증하기
    </a>
  </p>
  <p style="font-size:13px;color:#6b7280">버튼이 동작하지 않으면 아래 주소를 복사해 접속하세요:<br>{verify_url}</p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0"/>
  <p>인증을 마치면 프로필을 등록하고 바로 모의면접을 시작할 수 있습니다.</p>
  <p style="font-size:13px;color:#6b7280">문의: <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a></p>
</div>
"""

    msg = EmailMultiAlternatives(subject, text_body, from_email, [user.email])
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)
    logger.info("welcome email sent to user_id=%s", user.id)


def send_verification_code_email(user, code: str) -> None:
    """6자리 이메일 인증번호를 발송한다. (코드 방식) 코드는 로그에 남기지 않는다."""
    subject = "[Career.zip] 이메일 인증번호 안내"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@career.zip")
    # 유효시간은 settings.EMAIL_CODE_TTL_SECONDS 와 동기화한다(현재 10분).
    ttl_min = max(1, int(getattr(settings, "EMAIL_CODE_TTL_SECONDS", 600)) // 60)

    text_body = (
        f"{user.name}님, Career.zip 이메일 인증번호를 안내드립니다.\n\n"
        f"인증번호: {code}\n\n"
        f"인증 화면에 위 6자리 번호를 입력해 주세요. (유효시간 {ttl_min}분)\n"
        f"메일이 보이지 않으면 스팸함을 확인하거나 인증 화면에서 인증번호를 재전송해 주세요.\n"
        f"본인이 요청하지 않았다면 이 메일을 무시하셔도 됩니다.\n\n"
        f"문의: {SUPPORT_EMAIL}\n"
    )

    html_body = f"""\
<div style="font-family:Apple SD Gothic Neo,Malgun Gothic,sans-serif;max-width:560px;margin:0 auto;color:#1f2937">
  <h2 style="color:#253900">이메일 인증번호 안내</h2>
  <p><strong>{user.name}</strong>님, 아래 6자리 인증번호를 인증 화면에 입력해 주세요. (유효시간 {ttl_min}분)</p>
  <p style="margin:24px 0;text-align:center">
    <span style="display:inline-block;background:#EEEEEE;color:#253900;font-size:32px;font-weight:700;letter-spacing:8px;padding:16px 24px;border-radius:12px">{code}</span>
  </p>
  <p style="font-size:13px;color:#6b7280">본인이 요청하지 않았다면 이 메일을 무시하셔도 됩니다.</p>
  <p style="font-size:13px;color:#6b7280">문의: <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a></p>
</div>
"""

    msg = EmailMultiAlternatives(subject, text_body, from_email, [user.email])
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)
    logger.info("verification code email sent to user_id=%s", user.id)


def send_verification_email(user) -> None:
    """[deprecated] 링크 방식 인증 메일. 코드 방식(send_verification_code_email)으로 대체됨."""
    verify_url = build_verification_url(user)
    subject = "[Career.zip] 이메일 인증을 완료해 주세요"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@career.zip")

    text_body = (
        f"{user.name}님, 이메일 인증 링크를 다시 보내드립니다.\n\n"
        f"아래 링크를 눌러 이메일 인증을 완료해 주세요 (24시간 이내):\n{verify_url}\n\n"
        f"본인이 요청하지 않았다면 이 메일을 무시하셔도 됩니다.\n\n"
        f"문의: {SUPPORT_EMAIL}\n"
    )

    html_body = f"""\
<div style="font-family:Apple SD Gothic Neo,Malgun Gothic,sans-serif;max-width:560px;margin:0 auto;color:#1f2937">
  <h2 style="color:#253900">이메일 인증을 완료해 주세요</h2>
  <p><strong>{user.name}</strong>님, 이메일 인증 링크를 다시 보내드립니다.</p>
  <p>아래 버튼을 눌러 <strong>이메일 인증</strong>을 완료해 주세요. (링크는 24시간 동안 유효합니다.)</p>
  <p style="margin:24px 0">
    <a href="{verify_url}"
       style="background:#08CB00;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600">
       이메일 인증하기
    </a>
  </p>
  <p style="font-size:13px;color:#6b7280">버튼이 동작하지 않으면 아래 주소를 복사해 접속하세요:<br>{verify_url}</p>
  <p style="font-size:13px;color:#6b7280">본인이 요청하지 않았다면 이 메일을 무시하셔도 됩니다.</p>
  <p style="font-size:13px;color:#6b7280">문의: <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a></p>
</div>
"""

    msg = EmailMultiAlternatives(subject, text_body, from_email, [user.email])
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)
    logger.info("verification email resent to user_id=%s", user.id)


def send_dormancy_warning_email(user) -> None:
    """30일 후 휴면 전환 예정 안내 메일을 발송한다. (150일 미접속 시점)"""
    subject = "[Career.zip] 장기 미이용 안내 - 30일 후 휴면 전환 예정"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@career.zip")
    frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173").rstrip("/")
    login_url = f"{frontend_base}/login"

    text_body = (
        f"{user.name}님, Career.zip을 오랫동안 이용하지 않으셨습니다.\n\n"
        f"마지막 접속으로부터 150일이 지났으며, 30일 후(총 180일 미접속 시) 계정이 자동으로 휴면 상태로 전환됩니다.\n\n"
        f"계속 이용하시려면 아래 링크에서 로그인해 주세요:\n{login_url}\n\n"
        f"휴면 전환 후에도 로그인하면 즉시 계정을 복구할 수 있습니다.\n\n"
        f"문의: {SUPPORT_EMAIL}\n"
    )

    html_body = f"""\
<div style="font-family:Apple SD Gothic Neo,Malgun Gothic,sans-serif;max-width:560px;margin:0 auto;color:#1f2937">
  <h2 style="color:#253900">장기 미이용 안내</h2>
  <p><strong>{user.name}</strong>님, Career.zip을 오랫동안 이용하지 않으셨습니다.</p>
  <p>마지막 접속으로부터 <strong>150일</strong>이 지났으며,<br>
     <strong>30일 후(총 180일 미접속 시) 계정이 자동으로 휴면 상태로 전환됩니다.</strong></p>
  <p>계속 이용하시려면 아래 버튼을 눌러 로그인해 주세요.</p>
  <p style="margin:24px 0">
    <a href="{login_url}"
       style="background:#08CB00;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600">
       로그인하기
    </a>
  </p>
  <p style="font-size:13px;color:#6b7280">휴면 전환 후에도 로그인하면 즉시 계정을 복구할 수 있습니다.</p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0"/>
  <p style="font-size:13px;color:#6b7280">문의: <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a></p>
</div>
"""

    msg = EmailMultiAlternatives(subject, text_body, from_email, [user.email])
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)
    logger.info("dormancy warning email sent to user_id=%s", user.id)


def send_dormancy_email(user) -> None:
    """계정이 휴면 상태로 전환될 때 발송하는 알림 메일."""
    subject = "[Career.zip] 계정이 휴면 상태로 전환되었습니다"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@career.zip")
    frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173").rstrip("/")
    login_url = f"{frontend_base}/login"

    text_body = (
        f"{user.name}님, Career.zip 계정이 휴면 상태로 전환되었습니다.\n\n"
        f"마지막 접속으로부터 180일이 경과하여 계정이 휴면 처리되었습니다.\n\n"
        f"다시 이용하시려면 아래 링크에서 로그인하면 계정이 즉시 복구됩니다:\n{login_url}\n\n"
        f"문의: {SUPPORT_EMAIL}\n"
    )

    html_body = f"""\
<div style="font-family:Apple SD Gothic Neo,Malgun Gothic,sans-serif;max-width:560px;margin:0 auto;color:#1f2937">
  <h2 style="color:#253900">계정 휴면 안내</h2>
  <p><strong>{user.name}</strong>님, Career.zip 계정이 <strong>휴면 상태</strong>로 전환되었습니다.</p>
  <p>마지막 접속으로부터 <strong>180일</strong>이 경과하여 계정이 자동으로 휴면 처리되었습니다.</p>
  <p>다시 이용하시려면 아래 버튼을 눌러 로그인해 주세요. 로그인 즉시 계정이 복구됩니다.</p>
  <p style="margin:24px 0">
    <a href="{login_url}"
       style="background:#08CB00;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600">
       로그인하여 계정 복구
    </a>
  </p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0"/>
  <p style="font-size:13px;color:#6b7280">문의: <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a></p>
</div>
"""

    msg = EmailMultiAlternatives(subject, text_body, from_email, [user.email])
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)
    logger.info("dormancy email sent to user_id=%s", user.id)


def send_admin_signup_notification(user, signup_method: str = "email") -> None:
    """관리자에게 신규 가입 알림 메일을 발송한다. (민감정보 미포함)"""
    admin_email = getattr(settings, "ADMIN_NOTIFICATION_EMAIL", "")
    if not admin_email:
        logger.warning("ADMIN_NOTIFICATION_EMAIL 미설정 — 관리자 알림 메일 생략")
        return

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@career.zip")
    signed_up_at = timezone.localtime(user.created_at) if user.created_at else timezone.localtime()
    frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173").rstrip("/")
    member_detail_url = f"{frontend_base}/admin/members?user_id={user.id}"

    subject = "[Career.zip Admin] 신규 회원가입 알림"
    text_body = (
        "신규 회원이 가입했습니다.\n\n"
        f"- 이메일: {user.email}\n"
        f"- 이름: {user.name}\n"
        f"- 가입 시각: {signed_up_at:%Y-%m-%d %H:%M:%S}\n"
        f"- 가입 방식: {signup_method}\n"
        f"- 회원 상세: {member_detail_url}\n"
    )
    html_body = f"""\
<div style="font-family:Apple SD Gothic Neo,Malgun Gothic,sans-serif;max-width:560px;margin:0 auto;color:#1f2937">
  <h3 style="color:#253900">신규 회원가입 알림</h3>
  <table style="border-collapse:collapse;font-size:14px">
    <tr><td style="padding:4px 12px;color:#6b7280">이메일</td><td style="padding:4px 12px">{user.email}</td></tr>
    <tr><td style="padding:4px 12px;color:#6b7280">이름</td><td style="padding:4px 12px">{user.name}</td></tr>
    <tr><td style="padding:4px 12px;color:#6b7280">가입 시각</td><td style="padding:4px 12px">{signed_up_at:%Y-%m-%d %H:%M:%S}</td></tr>
    <tr><td style="padding:4px 12px;color:#6b7280">가입 방식</td><td style="padding:4px 12px">{signup_method}</td></tr>
  </table>
  <p style="margin-top:16px"><a href="{member_detail_url}">회원 상세 페이지 열기</a></p>
</div>
"""
    msg = EmailMultiAlternatives(subject, text_body, from_email, [admin_email])
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)
    logger.info("admin signup notification sent for user_id=%s", user.id)
