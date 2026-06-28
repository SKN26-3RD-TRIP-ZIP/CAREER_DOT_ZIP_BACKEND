from __future__ import annotations

from django.utils import timezone

from apps.accounts.models import PendingRegistration, TermsAgreement, TermsDocument, User


def client_ip_from_request(request) -> str | None:
    if request is None:
        return None
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip() or None
    return request.META.get('REMOTE_ADDR') or None


def user_agent_from_request(request) -> str:
    if request is None:
        return ''
    return (request.META.get('HTTP_USER_AGENT') or '')[:255]


def get_active_terms_document(kind: str, version: str | None = None) -> TermsDocument | None:
    queryset = TermsDocument.objects.filter(kind=kind)
    if version:
        queryset = queryset.filter(version=version)
    else:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by('-effective_at', '-id').first()


def record_terms_agreement(
    *,
    user: User,
    kind: str,
    version: str,
    agreed: bool,
    is_required: bool,
    source: str,
    request=None,
    withdrawn_at=None,
) -> TermsAgreement:
    now = timezone.now()
    return TermsAgreement.objects.create(
        user=user,
        document=get_active_terms_document(kind, version),
        kind=kind,
        version=version,
        is_required=is_required,
        agreed=bool(agreed),
        agreed_at=now if agreed else None,
        withdrawn_at=withdrawn_at,
        ip_address=client_ip_from_request(request),
        user_agent=user_agent_from_request(request),
        source=source,
    )


def record_signup_terms(user: User, pending: PendingRegistration, request=None) -> list[TermsAgreement]:
    agreements = [
        record_terms_agreement(
            user=user,
            kind=TermsDocument.KIND_TERMS,
            version=pending.terms_version or 'v1',
            agreed=pending.terms_agreed,
            is_required=True,
            source=TermsAgreement.SOURCE_SIGNUP,
            request=request,
        ),
        record_terms_agreement(
            user=user,
            kind=TermsDocument.KIND_PRIVACY,
            version=pending.privacy_version or 'v1',
            agreed=pending.privacy_agreed,
            is_required=True,
            source=TermsAgreement.SOURCE_SIGNUP,
            request=request,
        ),
        record_terms_agreement(
            user=user,
            kind=TermsDocument.KIND_MARKETING,
            version=pending.terms_version or 'v1',
            agreed=pending.marketing_agreed,
            is_required=False,
            source=TermsAgreement.SOURCE_SIGNUP,
            request=request,
        ),
    ]
    return agreements


def record_social_signup_terms(
    *,
    user: User,
    terms_agreed: bool,
    privacy_agreed: bool,
    marketing_agreed: bool,
    request=None,
) -> list[TermsAgreement]:
    """소셜 간편가입 사용자의 약관 동의 이력을 기록한다.

    기존 TermsDocument/TermsAgreement 구조를 재사용하며, 활성 문서의 버전을 사용한다.
    """

    def _version(kind: str) -> str:
        document = get_active_terms_document(kind)
        return document.version if document else 'v1'

    return [
        record_terms_agreement(
            user=user,
            kind=TermsDocument.KIND_TERMS,
            version=_version(TermsDocument.KIND_TERMS),
            agreed=terms_agreed,
            is_required=True,
            source=TermsAgreement.SOURCE_SIGNUP,
            request=request,
        ),
        record_terms_agreement(
            user=user,
            kind=TermsDocument.KIND_PRIVACY,
            version=_version(TermsDocument.KIND_PRIVACY),
            agreed=privacy_agreed,
            is_required=True,
            source=TermsAgreement.SOURCE_SIGNUP,
            request=request,
        ),
        record_terms_agreement(
            user=user,
            kind=TermsDocument.KIND_MARKETING,
            version=_version(TermsDocument.KIND_MARKETING),
            agreed=marketing_agreed,
            is_required=False,
            source=TermsAgreement.SOURCE_SIGNUP,
            request=request,
        ),
    ]


def set_marketing_consent(
    *,
    user: User,
    agreed: bool,
    version: str | None = None,
    request=None,
) -> TermsAgreement:
    active_doc = get_active_terms_document(TermsDocument.KIND_MARKETING, version)
    resolved_version = version or (active_doc.version if active_doc else 'v1')
    return record_terms_agreement(
        user=user,
        kind=TermsDocument.KIND_MARKETING,
        version=resolved_version,
        agreed=agreed,
        is_required=False,
        source=TermsAgreement.SOURCE_MYPAGE,
        request=request,
        withdrawn_at=timezone.now() if not agreed else None,
    )


def required_terms_reconsent_status(user: User) -> list[dict]:
    required_documents = TermsDocument.objects.filter(is_active=True, is_required=True)
    missing = []
    for document in required_documents:
        has_agreed = TermsAgreement.objects.filter(
            user=user,
            kind=document.kind,
            version=document.version,
            agreed=True,
            withdrawn_at__isnull=True,
        ).exists()
        if not has_agreed:
            missing.append(
                {
                    'kind': document.kind,
                    'version': document.version,
                    'title': document.title,
                    'required': document.is_required,
                }
            )
    return missing
