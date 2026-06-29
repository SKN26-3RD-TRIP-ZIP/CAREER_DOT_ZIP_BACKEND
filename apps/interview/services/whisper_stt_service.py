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
MIN_STT_TEXT_CHARS = 5
MIN_STT_WORD_COUNT = 2
MIN_STT_SPEECH_DURATION_SEC = 1.0
MIN_PAUSE_SEC = 0.5
LONG_PAUSE_SEC = 3.0
FILLER_WORDS = ('음', '어', '아')
KOREAN_PUNCTUATION = '，。！？、…“”‘’'


# Whisper API 호출 실패를 클라이언트에 502로 전달하기 위한 서비스 예외.
class WhisperSTTException(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = 'Whisper STT request failed.'
    default_code = 'whisper_stt_failed'


# STT 응답 지연은 일반 실패와 구분해 504로 내려준다.
class WhisperSTTTimeout(APIException):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    default_detail = 'Whisper STT request timed out.'
    default_code = 'whisper_stt_timeout'


# 업로드 용량 초과는 클라이언트 입력 문제이므로 413으로 분리한다.
class AudioTooLarge(APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = 'Audio file is too large.'
    default_code = 'audio_too_large'


class STTAnswerQualityError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Recorded answer is too short.'
    default_code = 'stt_answer_too_short'


@dataclass
class WhisperTranscription:
    text: str
    words: list
    duration: Optional[float] = None


def transcribe_uploaded_audio(uploaded_file, *, language='ko'):
    # 업로드 파일을 먼저 검증한 뒤 임시 파일로 저장해 Whisper SDK에 넘긴다.
    validate_uploaded_audio(uploaded_file)
    started_at = time.perf_counter()
    temp_path = write_upload_to_tempfile(uploaded_file)

    try:
        transcription = call_whisper(temp_path, language=language)
        stats = build_stt_stats(transcription.words, transcription.duration)
        validate_stt_answer_quality(
            transcription.text,
            speech_duration=stats['speech_duration'],
        )
        processing_time_ms = round((time.perf_counter() - started_at) * 1000)

        # 프론트는 stt_text를 답변 저장에 쓰고, pause 지표는 평가/리포트 보조 데이터로 사용한다.
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
        # 사용자 음성 원본은 현재 저장하지 않으므로 Whisper 호출 후 임시 파일을 즉시 제거한다.
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def validate_uploaded_audio(uploaded_file):
    # 현재 프론트 MediaRecorder가 webm/opus로 보내기 때문에 허용 타입도 여기에 맞춘다.
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


def count_stt_words(text):
    return len([word for word in str(text or '').split() if word.strip()])


def validate_stt_answer_quality(stt_text, *, speech_duration=None):
    normalized_text = str(stt_text or '').strip()
    text_length = len(normalized_text)
    word_count = count_stt_words(normalized_text)
    reasons = []

    if not normalized_text:
        reasons.append('empty_text')
    if text_length < MIN_STT_TEXT_CHARS:
        reasons.append('text_too_short')
    if word_count < MIN_STT_WORD_COUNT:
        reasons.append('word_count_too_low')

    duration_value = None
    if speech_duration is not None:
        try:
            duration_value = float(speech_duration)
        except (TypeError, ValueError):
            duration_value = None
        if duration_value is not None and duration_value < MIN_STT_SPEECH_DURATION_SEC:
            reasons.append('speech_duration_too_short')

    if reasons:
        raise STTAnswerQualityError(
            {
                'detail': '답변이 너무 짧아 다시 녹음이 필요합니다.',
                'code': 'stt_answer_too_short',
                'retryable': True,
                'reasons': reasons,
                'metrics': {
                    'text_length': text_length,
                    'word_count': word_count,
                    'speech_duration': duration_value,
                },
                'minimums': {
                    'text_length': MIN_STT_TEXT_CHARS,
                    'word_count': MIN_STT_WORD_COUNT,
                    'speech_duration': MIN_STT_SPEECH_DURATION_SEC,
                },
            }
        )

    return normalized_text


def write_upload_to_tempfile(uploaded_file):
    # Django UploadedFile은 chunks()로 읽어야 큰 파일도 메모리를 덜 사용한다.
    with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_file:
        for chunk in uploaded_file.chunks():
            temp_file.write(chunk)
        return temp_file.name


def call_whisper(temp_path, *, language):
    # settings 값을 우선 사용하고, 로컬 실행 환경을 위해 환경 변수도 fallback으로 확인한다.
    api_key = getattr(settings, 'OPENAI_API_KEY', None) or os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise APIException('OPENAI_API_KEY is not configured.')

    # OpenAI SDK가 없는 환경에서도 함수 호출 시점에 명확한 STT 예외로 응답한다.
    try:
        from openai import APITimeoutError, OpenAI, OpenAIError
    except ImportError as exc:
        raise WhisperSTTException('OpenAI SDK is not installed.') from exc

    try:
        # verbose_json과 word timestamp를 요청해야 답변 텍스트뿐 아니라 pause 분석까지 계산할 수 있다.
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
    # SDK 응답과 테스트용 dict/mock 모두 처리할 수 있게 get_response_value로 접근한다.
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

    # 이후 통계 계산에서 사용할 수 있도록 단어별 시작/끝 시간을 float 초 단위로 정리한다.
    return WhisperTranscription(
        text=text.strip(),
        words=words,
        duration=round(float(duration), 3) if duration is not None else None,
    )


def get_response_value(response, key):
    # OpenAI SDK 객체와 dict mock을 같은 방식으로 다루기 위한 작은 어댑터.
    if isinstance(response, dict):
        return response.get(key)
    return getattr(response, key, None)


def build_stt_stats(words, duration=None):
    # 단어 타임스탬프 사이의 gap을 사용해 침묵 시간, 긴 침묵 횟수, 말한 시간만 분리한다.
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
        # filler count는 디버그/향후 말버릇 분석용으로 함께 반환한다.
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
