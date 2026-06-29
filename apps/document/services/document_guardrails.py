from __future__ import annotations

import re
import zipfile
from pathlib import Path

from rest_framework import status
from rest_framework.exceptions import APIException


MAX_UPLOAD_SIZE = 10 * 1024 * 1024
MIN_EXTRACTED_CHARS = 50
DOCUMENT_TYPE_MISMATCH_SCORE = 3
DOCUMENT_TYPE_MISMATCH_RATIO = 2
ALLOWED_FILE_TYPES = {'pdf', 'docx'}
SUPPORTED_MIME_TYPES = {
    'pdf': {'application/pdf'},
    'docx': {
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    },
}
IGNORED_UPLOAD_MIME_TYPES = {'', 'application/octet-stream'}

PDF_SIGNATURE = b'%PDF-'
ZIP_SIGNATURES = (b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08')

RESUME_KEYWORDS = {
    'resume',
    'cv',
    'career',
    'experience',
    'education',
    'project',
    'portfolio',
    'certificate',
    'email',
    'github',
    'skills',
    'tech stack',
    '\uc774\ub825\uc11c',
    '\uacbd\ub825',
    '\ud559\ub825',
    '\uae30\uc220\uc2a4\ud0dd',
    '\uae30\uc220 \uc2a4\ud0dd',
    '\ud504\ub85c\uc81d\ud2b8',
    '\uc790\uaca9\uc99d',
    '\uc790\uae30\uc18c\uac1c',
    '\uadfc\ubb34\uae30\uac04',
}
JD_KEYWORDS = {
    'job posting',
    'recruitment',
    'responsibilities',
    'requirements',
    'qualifications',
    'preferred',
    'hiring process',
    'working conditions',
    '\ucc44\uc6a9',
    '\ucc44\uc6a9\uacf5\uace0',
    '\uc9c1\ubb34',
    '\ub2f4\ub2f9\uc5c5\ubb34',
    '\uc790\uaca9\uc694\uac74',
    '\uc9c0\uc6d0\uc790\uaca9',
    '\uc6b0\ub300\uc0ac\ud56d',
    '\ubaa8\uc9d1',
    '\uadfc\ubb34\uc870\uac74',
    '\ucc44\uc6a9\uc808\ucc28',
}
UNSAFE_PATTERNS = (
    r'\uc774\uc804\s*\uba85\ub839.*\ubb34\uc2dc',
    r'\uc774\uc804\s*\uc9c0\uc2dc.*\ubb34\uc2dc',
    r'\uc704\s*\uc9c0\uc2dc.*\ubb34\uc2dc',
    r'ignore\s+(all\s+)?previous\s+instructions',
    r'system\s*prompt',
    r'\uc2dc\uc2a4\ud15c\s*\ud504\ub86c\ud504\ud2b8.*\ucd9c\ub825',
    r'developer\s*message',
    r'\uac1c\ubc1c\uc790\s*\uba54\uc2dc\uc9c0.*\uacf5\uac1c',
    r'\uba74\uc811\s*\uc9c8\ubb38\s*\ub300\uc2e0.*\uba85\ub839',
    r'\ud504\ub86c\ud504\ud2b8\s*\uc778\uc81d\uc158',
)


class DocumentUploadError(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = 'DOCUMENT_UPLOAD_FAILED'

    def __init__(self, error_code, message, http_status=None):
        self.status_code = http_status or self.status_code
        super().__init__(
            {
                'detail': message,
                'message': message,
                'code': error_code,
                'error_code': error_code,
            }
        )


def validate_upload_file(file_obj):
    if file_obj is None:
        raise DocumentUploadError(
            'INVALID_FILE_TYPE',
            'PDF ?? DOCX ??? ???? ? ????.',
            status.HTTP_400_BAD_REQUEST,
        )

    original_filename = Path(file_obj.name).name
    file_type = Path(original_filename).suffix.lower().lstrip('.')
    if file_type not in ALLOWED_FILE_TYPES:
        raise DocumentUploadError(
            'INVALID_FILE_TYPE',
            'PDF ?? DOCX ??? ???? ? ????.',
            status.HTTP_400_BAD_REQUEST,
        )
    if len(original_filename) > 255:
        raise DocumentUploadError(
            'INVALID_FILE_TYPE',
            '?? ??? 255?? ??? ? ????.',
            status.HTTP_400_BAD_REQUEST,
        )

    size = getattr(file_obj, 'size', 0) or 0
    if size <= 0:
        raise DocumentUploadError(
            'FILE_EMPTY',
            '? ??? ???? ? ????.',
            status.HTTP_400_BAD_REQUEST,
        )
    if size > MAX_UPLOAD_SIZE:
        raise DocumentUploadError(
            'FILE_TOO_LARGE',
            '??? ?? 10MB?? ???? ? ????.',
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    content_type = (getattr(file_obj, 'content_type', '') or '').lower()
    if content_type not in IGNORED_UPLOAD_MIME_TYPES:
        if content_type not in SUPPORTED_MIME_TYPES[file_type]:
            raise DocumentUploadError(
                'INVALID_FILE_TYPE',
                'PDF ?? DOCX ??? ???? ? ????.',
                status.HTTP_400_BAD_REQUEST,
            )

    _validate_file_signature(file_obj, file_type)
    file_obj.original_filename = original_filename
    file_obj.file_type = file_type
    return file_type, original_filename


def validate_extracted_text(text, document_type, file_type=None):
    normalized_count = len(re.findall(r'[A-Za-z0-9\uac00-\ud7a3]', text or ''))
    if normalized_count == 0:
        if file_type == 'pdf':
            raise DocumentUploadError(
                'OCR_NOT_SUPPORTED',
                '???? ?? PDF? ?? OCR? ???? ????.',
            )
        raise DocumentUploadError(
            'TEXT_EXTRACTION_FAILED',
            '???? ???? ???? ?????.',
        )
    if normalized_count < MIN_EXTRACTED_CHARS:
        raise DocumentUploadError(
            'DOCUMENT_TOO_SHORT',
            '????? ?? ??? ?? ????.',
        )
    _validate_document_type(text or '', document_type)
    _validate_safe_content(text or '')


def map_text_extraction_error(exc):
    message = str(exc).lower()
    if 'encrypted' in message or 'password' in message:
        return DocumentUploadError(
            'DOCUMENT_ENCRYPTED',
            '???? ??? ???? ? ????.',
        )
    if any(token in message for token in ('cannot open', 'failed to open', 'bad zip', 'not a zip')):
        return DocumentUploadError(
            'DOCUMENT_CORRUPTED',
            '??? ???? ??? ?? ? ????.',
        )
    if 'unsupported file type' in message:
        return DocumentUploadError(
            'INVALID_FILE_TYPE',
            'PDF ?? DOCX ??? ???? ? ????.',
            status.HTTP_400_BAD_REQUEST,
        )
    return DocumentUploadError(
        'TEXT_EXTRACTION_FAILED',
        '???? ???? ???? ?????.',
    )


def _validate_file_signature(file_obj, file_type):
    header = _read_start(file_obj, 8)
    if file_type == 'pdf':
        if not header.startswith(PDF_SIGNATURE):
            raise DocumentUploadError(
                'INVALID_FILE_SIGNATURE',
                '?? ??? ???? ????.',
                status.HTTP_400_BAD_REQUEST,
            )
        return

    if not header.startswith(ZIP_SIGNATURES):
        raise DocumentUploadError(
            'INVALID_FILE_SIGNATURE',
            '?? ??? ???? ????.',
            status.HTTP_400_BAD_REQUEST,
        )

    try:
        _seek_start(file_obj)
        with zipfile.ZipFile(file_obj) as archive:
            names = set(archive.namelist())
            if '[Content_Types].xml' not in names or 'word/document.xml' not in names:
                raise DocumentUploadError(
                    'INVALID_FILE_SIGNATURE',
                    '?? ??? ???? ????.',
                    status.HTTP_400_BAD_REQUEST,
                )
            if any(name.endswith('vbaProject.bin') for name in names):
                raise DocumentUploadError(
                    'DOCUMENT_MACRO_DETECTED',
                    '???? ??? DOCX ??? ???? ? ????.',
                )
    except zipfile.BadZipFile as exc:
        raise DocumentUploadError(
            'DOCUMENT_CORRUPTED',
            '??? ???? ??? ?? ? ????.',
        ) from exc
    finally:
        _seek_start(file_obj)


def _validate_document_type(text, document_type):
    if document_type not in {'resume', 'jd'}:
        return

    lowered = text.lower()
    resume_score = sum(1 for keyword in RESUME_KEYWORDS if keyword.lower() in lowered)
    jd_score = sum(1 for keyword in JD_KEYWORDS if keyword.lower() in lowered)

    if (
        document_type == 'resume'
        and jd_score >= DOCUMENT_TYPE_MISMATCH_SCORE
        and jd_score > resume_score * DOCUMENT_TYPE_MISMATCH_RATIO
    ):
        raise DocumentUploadError(
            'DOCUMENT_TYPE_MISMATCH',
            '??? ?? ??? ?? ?? ??? ???? ????.',
        )
    if (
        document_type == 'jd'
        and resume_score >= DOCUMENT_TYPE_MISMATCH_SCORE
        and resume_score > jd_score * DOCUMENT_TYPE_MISMATCH_RATIO
    ):
        raise DocumentUploadError(
            'DOCUMENT_TYPE_MISMATCH',
            '??? ?? ??? ?? ?? ??? ???? ????.',
        )
    if document_type == 'jd' and jd_score == 0 and resume_score == 0:
        raise DocumentUploadError(
            'DOCUMENT_NOT_RELEVANT',
            '?? ??? ??? ? ?? ?????.',
        )


def _validate_safe_content(text):
    for pattern in UNSAFE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            raise DocumentUploadError(
                'UNSAFE_DOCUMENT_CONTENT',
                '???? ??? ? ?? ??? ??? ???????.',
            )
    if _looks_like_noise(text):
        raise DocumentUploadError(
            'DOCUMENT_NOT_RELEVANT',
            '?? ??? ??? ? ?? ?????.',
        )


def _looks_like_noise(text):
    compact = re.sub(r'\s+', '', text or '')
    if not compact:
        return True
    urls = re.findall(r'https?://\S+|www\.\S+', text or '', flags=re.IGNORECASE)
    without_urls = re.sub(r'https?://\S+|www\.\S+', '', text or '', flags=re.IGNORECASE)
    if urls and not re.search(r'[A-Za-z0-9\uac00-\ud7a3]', without_urls):
        return True
    alnum = re.findall(r'[A-Za-z0-9\uac00-\ud7a3]', compact)
    if len(alnum) / max(len(compact), 1) < 0.35:
        return True
    if len(compact) >= 80 and not re.search(r'\s', text or ''):
        return True
    unique_chars = set(compact)
    return len(unique_chars) <= 5 and len(compact) >= 50


def _read_start(file_obj, size):
    _seek_start(file_obj)
    data = file_obj.read(size)
    _seek_start(file_obj)
    return data


def _seek_start(file_obj):
    try:
        file_obj.seek(0)
    except (AttributeError, OSError):
        pass
