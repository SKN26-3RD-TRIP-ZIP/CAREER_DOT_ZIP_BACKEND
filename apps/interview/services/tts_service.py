import os

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError


TTS_MODEL = 'gpt-4o-mini-tts'
MAX_TTS_TEXT_LENGTH = 1200

PERSONA_TTS_VOICES = {
    'coach': 'shimmer',
    'practical': 'alloy',
    'verifier': 'onyx',
    'pressure': 'onyx',
}

class TTSException(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = 'TTS request failed.'
    default_code = 'tts_failed'


class TTSTimeout(APIException):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    default_detail = 'TTS request timed out.'
    default_code = 'tts_timeout'


def synthesize_interview_question(text, *, persona='practical'):
    normalized_text = validate_tts_text(text)
    normalized_persona = normalize_persona(persona)
    api_key = getattr(settings, 'OPENAI_API_KEY', None) or os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise APIException('OPENAI_API_KEY is not configured.')

    try:
        from openai import APITimeoutError, OpenAI, OpenAIError
    except ImportError as exc:
        raise TTSException('OpenAI SDK is not installed.') from exc

    model = getattr(settings, 'OPENAI_TTS_MODEL', None) or os.environ.get('OPENAI_TTS_MODEL') or TTS_MODEL
    voice = PERSONA_TTS_VOICES[normalized_persona]

    try:
        client = OpenAI(api_key=api_key, timeout=30)
        response = client.audio.speech.create(
            model=model,
            voice=voice,
            input=normalized_text,
            response_format='mp3',
        )
    except APITimeoutError as exc:
        raise TTSTimeout() from exc
    except OpenAIError as exc:
        raise TTSException('OpenAI TTS API call failed.') from exc

    audio_bytes = extract_audio_bytes(response)
    if not audio_bytes:
        raise TTSException('OpenAI TTS response was empty.')

    return {
        'audio_bytes': audio_bytes,
        'model': model,
        'voice': voice,
        'persona': normalized_persona,
        'content_type': 'audio/mpeg',
    }


def validate_tts_text(text):
    normalized_text = str(text or '').strip()
    if not normalized_text:
        raise ValidationError({'text': 'Text is required.'})
    if len(normalized_text) > MAX_TTS_TEXT_LENGTH:
        raise ValidationError({'text': f'Text must be {MAX_TTS_TEXT_LENGTH} characters or fewer.'})
    return normalized_text


def normalize_persona(persona):
    normalized = str(persona or 'practical').strip().lower()
    if normalized == 'verify':
        normalized = 'verifier'
    return normalized if normalized in PERSONA_TTS_VOICES else 'practical'


def extract_audio_bytes(response):
    content = getattr(response, 'content', None)
    if content:
        return bytes(content)

    read = getattr(response, 'read', None)
    if callable(read):
        return read()

    if isinstance(response, (bytes, bytearray)):
        return bytes(response)

    return b''
