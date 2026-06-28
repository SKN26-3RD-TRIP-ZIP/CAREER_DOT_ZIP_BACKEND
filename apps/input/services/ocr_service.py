from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError

from apps.document.services.document_parser import extract_text_from_file
from apps.interview.services.guardrails import scan_user_input


MAX_OCR_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
SUPPORTED_MIME_TYPES = {
    'application/pdf',
    'image/png',
    'image/jpeg',
}


class OCRProviderNotConfigured(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = 'OCR provider is not configured.'
    default_code = 'OCR_PROVIDER_NOT_CONFIGURED'


class OCRProviderError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = 'OCR provider failed.'
    default_code = 'OCR_PROVIDER_FAILED'


def validate_ocr_upload(file_obj):
    if file_obj is None:
        raise ValidationError({'file': 'File is required.'})
    filename = Path(file_obj.name).name
    extension = Path(filename).suffix.lower().lstrip('.')
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValidationError({'file': 'Only PNG, JPG, JPEG, and PDF files are supported.'})
    content_type = (getattr(file_obj, 'content_type', '') or '').lower()
    if content_type and content_type not in SUPPORTED_MIME_TYPES:
        raise ValidationError({'file': 'Unsupported MIME type.'})
    size = getattr(file_obj, 'size', 0) or 0
    if size <= 0:
        raise ValidationError({'file': 'File is empty.'})
    if size > MAX_OCR_UPLOAD_BYTES:
        raise ValidationError({'file': 'File is too large.'})
    return extension, filename


def _provider_name():
    return (getattr(settings, 'OCR_PROVIDER', '') or os.environ.get('OCR_PROVIDER') or '').strip().lower()


def _mock_ocr(file_obj) -> str:
    name = Path(file_obj.name).stem
    return f'Mock OCR extracted text from {name}. Please review and edit before saving.'


def _call_image_ocr_provider(file_obj) -> str:
    provider = _provider_name()
    if provider == 'mock':
        return _mock_ocr(file_obj)
    raise OCRProviderNotConfigured()


def extract_job_text_from_upload(file_obj) -> dict:
    extension, filename = validate_ocr_upload(file_obj)
    if extension == 'pdf':
        text = (extract_text_from_file(file_obj, 'pdf') or '').strip()
        provider = 'pdf_text'
    else:
        text = (_call_image_ocr_provider(file_obj) or '').strip()
        provider = _provider_name() or 'unconfigured'
    if not text:
        raise OCRProviderError('OCR produced empty text.')

    guardrail = scan_user_input(text, min_answer_length=1)
    return {
        'filename': filename,
        'provider': provider,
        'raw_text': guardrail.masked_excerpt if guardrail.should_block else text,
        'masked': guardrail.should_block,
        'guardrail': guardrail.as_response(),
    }
