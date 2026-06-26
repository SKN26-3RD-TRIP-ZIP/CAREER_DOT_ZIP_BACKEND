import os

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError


TTS_MODEL = 'gpt-4o-mini-tts'
MAX_TTS_TEXT_LENGTH = 1200

# 면접관 페르소나별로 다른 목소리를 매핑한다.
# 실제 음성 합성 요청에서는 normalized persona를 기준으로 이 값을 사용한다.
PERSONA_TTS_VOICES = {
    'coach': 'shimmer',
    'practical': 'alloy',
    'verifier': 'onyx',
    'pressure': 'onyx',
}


# OpenAI TTS 호출 자체가 실패했을 때 클라이언트에 502로 알려주기 위한 예외.
class TTSException(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = 'TTS request failed.'
    default_code = 'tts_failed'


# OpenAI TTS 요청이 제한 시간 안에 끝나지 않았을 때 504로 분리해서 응답한다.
class TTSTimeout(APIException):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    default_detail = 'TTS request timed out.'
    default_code = 'tts_timeout'


def synthesize_interview_question(text, *, persona='practical'):
    # API 호출 전에 입력 텍스트와 페르소나를 서비스 내부 기준으로 정규화한다.
    normalized_text = validate_tts_text(text)
    normalized_persona = normalize_persona(persona)

    # settings 값을 우선 사용하고, 로컬 실행/배포 환경 차이를 위해 환경 변수도 fallback으로 확인한다.
    api_key = getattr(settings, 'OPENAI_API_KEY', None) or os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise APIException('OPENAI_API_KEY is not configured.')

    # OpenAI SDK가 없는 환경에서도 서버가 바로 죽지 않도록 함수 실행 시점에 지연 import한다.
    try:
        from openai import APITimeoutError, OpenAI, OpenAIError
    except ImportError as exc:
        raise TTSException('OpenAI SDK is not installed.') from exc

    # 모델은 설정/환경 변수로 교체 가능하게 두고, 기본값은 gpt-4o-mini-tts를 사용한다.
    model = getattr(settings, 'OPENAI_TTS_MODEL', None) or os.environ.get('OPENAI_TTS_MODEL') or TTS_MODEL
    voice = PERSONA_TTS_VOICES[normalized_persona]

    try:
        # 질문 텍스트를 mp3 음성 바이너리로 합성한다.
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

    # SDK 응답 형태가 바뀌어도 bytes를 안정적으로 꺼낼 수 있도록 별도 함수로 분리했다.
    audio_bytes = extract_audio_bytes(response)
    if not audio_bytes:
        raise TTSException('OpenAI TTS response was empty.')

    # View에서는 audio_bytes를 HttpResponse 본문으로 보내고, 나머지 값은 응답 헤더/디버깅에 사용한다.
    return {
        'audio_bytes': audio_bytes,
        'model': model,
        'voice': voice,
        'persona': normalized_persona,
        'content_type': 'audio/mpeg',
    }


def validate_tts_text(text):
    # 빈 질문이나 지나치게 긴 질문은 TTS 비용/지연을 만들 수 있어 사전에 차단한다.
    normalized_text = str(text or '').strip()
    if not normalized_text:
        raise ValidationError({'text': 'Text is required.'})
    if len(normalized_text) > MAX_TTS_TEXT_LENGTH:
        raise ValidationError({'text': f'Text must be {MAX_TTS_TEXT_LENGTH} characters or fewer.'})
    return normalized_text


def normalize_persona(persona):
    # 과거/다른 코드에서 verify로 넘어오는 값을 현재 표준 이름인 verifier로 보정한다.
    normalized = str(persona or 'practical').strip().lower()
    if normalized == 'verify':
        normalized = 'verifier'

    # 알 수 없는 페르소나는 실전형 면접관(practical)으로 안전하게 fallback한다.
    return normalized if normalized in PERSONA_TTS_VOICES else 'practical'


def extract_audio_bytes(response):
    # OpenAI SDK 응답 객체가 content 속성을 제공하는 경우.
    content = getattr(response, 'content', None)
    if content:
        return bytes(content)

    # 스트림/파일 유사 객체처럼 read()로 본문을 읽어야 하는 경우.
    read = getattr(response, 'read', None)
    if callable(read):
        return read()

    # 테스트나 SDK 버전 차이로 이미 bytes 형태가 넘어오는 경우.
    if isinstance(response, (bytes, bytearray)):
        return bytes(response)

    return b''
