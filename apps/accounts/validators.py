"""
커스텀 비밀번호 검증기.

Django 기본 검증기(UserAttributeSimilarity/MinimumLength/CommonPassword/NumericPassword)에
더해, 영문/숫자/특수문자 조합과 동일문자 연속 반복을 검증한다.

settings.AUTH_PASSWORD_VALIDATORS 에 등록되어 DRF 의 validate_password() 호출 시 함께 적용된다.
- 12345678  → 숫자만(특수문자/영문 없음) → 차단
- qwer1234   → 특수문자 없음 → 차단
- aaaa1234!  → 동일문자 3연속 → 차단
- password123→ CommonPasswordValidator 가 별도 차단
"""
import re

from django.core.exceptions import ValidationError


class PasswordComplexityValidator:
    """영문 + 숫자 + 특수문자를 모두 포함하고, 동일문자 3연속을 금지한다."""

    def __init__(self, min_length: int = 8):
        self.min_length = min_length

    def validate(self, password, user=None):
        errors = []

        if len(password) < self.min_length:
            errors.append(
                ValidationError(
                    f"비밀번호는 최소 {self.min_length}자 이상이어야 합니다.",
                    code="password_too_short_custom",
                )
            )
        if not re.search(r"[A-Za-z]", password):
            errors.append(
                ValidationError("영문자를 1자 이상 포함해야 합니다.", code="password_no_letter")
            )
        if not re.search(r"\d", password):
            errors.append(
                ValidationError("숫자를 1자 이상 포함해야 합니다.", code="password_no_digit")
            )
        if not re.search(r"[^A-Za-z0-9]", password):
            errors.append(
                ValidationError("특수문자를 1자 이상 포함해야 합니다.", code="password_no_special")
            )
        if re.search(r"(.)\1\1", password):
            errors.append(
                ValidationError(
                    "같은 문자를 3번 이상 연속으로 사용할 수 없습니다.",
                    code="password_repeated_char",
                )
            )

        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return (
            f"비밀번호는 {self.min_length}자 이상이며 영문, 숫자, 특수문자를 각각 "
            "1자 이상 포함해야 합니다. (같은 문자 3연속 불가)"
        )
