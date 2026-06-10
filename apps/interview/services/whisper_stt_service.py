import os
import string
import tempfile
import time
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError


MAX_AUDIO_BYTES = 25 * 1024 * 1024
SUPPORTED_AUDIO_TYPES = {
    'audio/webm',
    'audio/webm;codecs=opus',
}
MIN_PAUSE_SEC = 0.5
LONG_PAUSE_SEC = 3.0
FILLER_WORDS = ('음', '어', '아')
KOREAN_PUNCTUATION = '，。！？、…“”‘’'


class WhisperSTTException(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = 'Whisper STT request failed.'
    default_code = 'whisper_stt_failed'


class WhisperSTTTimeout(APIException):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    default_detail = 'Whisper STT request timed out.'
    default_code = 'whisper_stt_timeout'


class AudioTooLarge(APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = 'Audio file is too large.'
    default_code = 'audio_too_large'


@dataclass
class WhisperTranscription:
    text: str
    words: list
    duration: Optional[float] = None


def transcribe_uploaded_audio(uploaded_file, *, language='ko'):
    validate_uploaded_audio(uploaded_file)
    started_at = time.perf_counter()
    temp_path = write_upload_to_tempfile(uploaded_file)

    try:
        transcription = call_whisper(temp_path, language=language)
        stats = build_stt_stats(transcription.words, transcription.duration)
        processing_time_ms = round((time.perf_counter() - started_at) * 1000)

        return {
            'stt_text': transcription.text,
            'speech_duration': stats['speech_duration'],
            'total_pause_duration': stats['total_pause_duration'],
            'long_pause_count': stats['long_pause_count'],
            'processing_time_ms': processing_time_ms,
            'debug': {
                'audio_duration': stats['audio_duration'],
                'pause_count': stats['pause_count'],
                'first_speech_start_sec': stats['first_speech_start_sec'],
                'filler_words': stats['filler_words'],
                'words': stats['words'],
            },
        }
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def validate_uploaded_audio(uploaded_file):
    if uploaded_file is None:
        raise ValidationError({'audio': 'Audio file is required.'})

    content_type = (getattr(uploaded_file, 'content_type', '') or '').lower()
    if content_type not in SUPPORTED_AUDIO_TYPES:
        raise ValidationError({'audio': 'Only webm audio is supported.'})

    size = getattr(uploaded_file, 'size', 0) or 0
    if size <= 0:
        raise ValidationError({'audio': 'Audio file is empty.'})
    if size > MAX_AUDIO_BYTES:
        raise AudioTooLarge()


def write_upload_to_tempfile(uploaded_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_file:
        for chunk in uploaded_file.chunks():
            temp_file.write(chunk)
        return temp_file.name


def call_whisper(temp_path, *, language):
    api_key = getattr(settings, 'OPENAI_API_KEY', None) or os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise APIException('OPENAI_API_KEY is not configured.')

    try:
        from openai import APITimeoutError, OpenAI, OpenAIError
    except ImportError as exc:
        raise WhisperSTTException('OpenAI SDK is not installed.') from exc

    try:
        client = OpenAI(api_key=api_key, timeout=30)
        with open(temp_path, 'rb') as audio_file:
            response = client.audio.transcriptions.create(
                model='whisper-1',
                file=audio_file,
                language=language,
                response_format='verbose_json',
                timestamp_granularities=['word'],
            )
    except APITimeoutError as exc:
        raise WhisperSTTTimeout() from exc
    except OpenAIError as exc:
        raise WhisperSTTException('Whisper STT API call failed.') from exc

    return normalize_whisper_response(response)


def normalize_whisper_response(response):
    text = get_response_value(response, 'text') or ''
    raw_words = get_response_value(response, 'words') or []
    duration = get_response_value(response, 'duration')

    words = []
    for item in raw_words:
        word = get_response_value(item, 'word')
        start = get_response_value(item, 'start')
        end = get_response_value(item, 'end')
        if word is None or start is None or end is None:
            continue
        words.append(
            {
                'word': str(word),
                'start': round(float(start), 3),
                'end': round(float(end), 3),
            }
        )

    if not words:
        raise WhisperSTTException('Whisper word timestamps are unavailable.')

    return WhisperTranscription(
        text=text.strip(),
        words=words,
        duration=round(float(duration), 3) if duration is not None else None,
    )


def get_response_value(response, key):
    if isinstance(response, dict):
        return response.get(key)
    return getattr(response, key, None)


def build_stt_stats(words, duration=None):
    normalized_words = []
    pauses = []
    filler_counts = {word: 0 for word in FILLER_WORDS}

    for index, item in enumerate(words):
        start = float(item['start'])
        end = float(item['end'])
        next_word = words[index + 1] if index + 1 < len(words) else None
        gap = max(0.0, float(next_word['start']) - end) if next_word else 0.0

        clean_word = str(item['word']).strip()
        normalized_for_count = clean_word.strip(string.punctuation + KOREAN_PUNCTUATION)
        for filler_word in FILLER_WORDS:
            if normalized_for_count == filler_word:
                filler_counts[filler_word] += 1

        normalized_words.append(
            {
                'word': clean_word,
                'start': round(start, 3),
                'end': round(end, 3),
                'gap': round(gap, 3),
            }
        )

        if next_word and gap >= MIN_PAUSE_SEC:
            pauses.append(gap)

    first_start = float(words[0]['start']) if words else 0.0
    last_end = float(words[-1]['end']) if words else 0.0
    inferred_duration = duration if duration is not None else last_end
    speech_duration = sum(
        max(0.0, float(item['end']) - float(item['start']))
        for item in words
    )

    return {
        'audio_duration': round(float(inferred_duration), 3),
        'first_speech_start_sec': round(first_start, 3),
        'speech_duration': round(speech_duration, 3),
        'total_pause_duration': round(sum(pauses), 3),
        'pause_count': len(pauses),
        'long_pause_count': sum(1 for pause in pauses if pause >= LONG_PAUSE_SEC),
        'filler_words': filler_counts,
        'words': normalized_words,
    }
