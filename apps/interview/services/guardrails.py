import re
from dataclasses import dataclass


BLOCKING_ACTIONS = {'BLOCK_INPUT', 'END_SESSION'}

_SECRET_PATTERNS = [
    re.compile(r'\b(?:api[_-]?key|token|secret|access[_-]?token)\b\s*[:=]\s*["\']?[A-Za-z0-9_\-]{16,}', re.I),
    re.compile(r'\b(?:db[_-]?password|database[_-]?password|passwd|password|pwd)\b\s*[:=]\s*["\']?[^"\';\s]{8,}', re.I),
    re.compile(r'\b(?:aws[_-]?secret[_-]?access[_-]?key)\b\s*[:=]\s*["\']?[A-Za-z0-9/+=]{32,}', re.I),
    re.compile(r'\bsk-[A-Za-z0-9]{20,}\b'),
    re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
]
_RRN_PATTERN = re.compile(r'\b\d{6}[- ]?[1-4]\d{6}\b')
_EMAIL_PATTERN = re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.I)
_PHONE_PATTERN = re.compile(r'(?<!\d)(?:01[016789][- ]?\d{3,4}[- ]?\d{4}|0\d{1,2}[- ]?\d{3,4}[- ]?\d{4})(?!\d)')
_ACCOUNT_PATTERN = re.compile(
    r'(?:계좌|account|acct|bank|은행)[^\n\r]{0,24}(?<!\d)(?:\d{2,6}[- ]?){2,5}\d{2,6}(?!\d)',
    re.I,
)
_PII_PATTERNS = [
    (_EMAIL_PATTERN, '[EMAIL_MASKED]'),
    (_PHONE_PATTERN, '[PHONE_MASKED]'),
    (_ACCOUNT_PATTERN, '[ACCOUNT_MASKED]'),
]
_PROMPT_INJECTION_PATTERN = re.compile(
    r'(ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|system\s+prompt|developer\s+message|'
    r'지금부터\s*너는|이전\s*지시|시스템\s*프롬프트|프롬프트\s*무시)',
    re.I,
)
_XSS_PATTERN = re.compile(r'(<\s*script\b|javascript\s*:|onerror\s*=|onload\s*=)', re.I)
_SQLI_PATTERN = re.compile(r"(\bunion\s+select\b|\bdrop\s+table\b|--\s|/\*|\bor\s+1\s*=\s*1\b)", re.I)
_HARMFUL_PATTERN = re.compile(
    r'(kill|bomb|terror|폭탄|살해|테러|협박|불법\s*제조|마약\s*제조)',
    re.I,
)
_AUTOMATION_ABUSE_PATTERN = re.compile(
    r'(bypass\s+(?:auth|permission)|privilege\s+escalation|brute\s*force|권한\s*우회|자동화\s*공격)',
    re.I,
)


@dataclass(frozen=True)
class GuardrailResult:
    category: str
    action: str
    reason_code: str
    masked_excerpt: str = ''

    @property
    def should_block(self):
        return self.action in BLOCKING_ACTIONS

    def as_response(self):
        return {
            'category': self.category,
            'action': self.action,
            'reason_code': self.reason_code,
            'masked_excerpt': self.masked_excerpt,
        }


def mask_sensitive_text(text, *, limit=240):
    masked = text or ''
    for pattern in _SECRET_PATTERNS:
        masked = pattern.sub('[SECRET_MASKED]', masked)
    masked = _RRN_PATTERN.sub('[RRN_MASKED]', masked)
    for pattern, replacement in _PII_PATTERNS:
        masked = pattern.sub(replacement, masked)
    masked = _XSS_PATTERN.sub('[XSS_MASKED]', masked)
    masked = _SQLI_PATTERN.sub('[SQLI_MASKED]', masked)
    return masked if limit is None else masked[:limit]


def mask_text_for_llm(text):
    return mask_sensitive_text(text, limit=None)


def _first_match(patterns, text):
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return ''


def _normalize_answer(text):
    return re.sub(r'\s+', ' ', (text or '').strip().lower())


def scan_user_input(text, *, previous_answers=None, min_answer_length=15):
    value = text or ''
    normalized = _normalize_answer(value)

    if _first_match(_SECRET_PATTERNS, value):
        return GuardrailResult('G3', 'BLOCK_INPUT', 'SECRET_PATTERN', mask_sensitive_text(value))
    if _RRN_PATTERN.search(value):
        return GuardrailResult('G3', 'BLOCK_INPUT', 'RRN_PATTERN', mask_sensitive_text(value))
    if _XSS_PATTERN.search(value):
        return GuardrailResult('G3', 'BLOCK_INPUT', 'XSS_PATTERN', mask_sensitive_text(value))
    if _SQLI_PATTERN.search(value):
        return GuardrailResult('G3', 'BLOCK_INPUT', 'SQL_INJECTION_PATTERN', mask_sensitive_text(value))
    if _PROMPT_INJECTION_PATTERN.search(value):
        return GuardrailResult('G3', 'BLOCK_INPUT', 'PROMPT_INJECTION_PATTERN', mask_sensitive_text(value))
    if _AUTOMATION_ABUSE_PATTERN.search(value):
        return GuardrailResult('G5', 'REQUIRE_ADMIN_REVIEW', 'AUTOMATION_OR_PRIVILEGE_ABUSE', mask_sensitive_text(value))
    if _HARMFUL_PATTERN.search(value):
        return GuardrailResult('G4', 'BLOCK_INPUT', 'HARMFUL_OR_ILLEGAL_REQUEST', mask_sensitive_text(value))
    if _first_match([pattern for pattern, _replacement in _PII_PATTERNS], value):
        return GuardrailResult('G3', 'WARN', 'PII_PATTERN', mask_sensitive_text(value))

    if len(normalized) < min_answer_length:
        return GuardrailResult('G1', 'GUIDE', 'ANSWER_TOO_SHORT', mask_sensitive_text(value))

    previous = {_normalize_answer(item) for item in (previous_answers or []) if item}
    if normalized and normalized in previous:
        return GuardrailResult('G2', 'WARN', 'REPEATED_ANSWER', mask_sensitive_text(value))

    return GuardrailResult('G0', 'ALLOW', 'NO_ISSUE', '')
