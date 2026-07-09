# 음성 면접 기능 코드리뷰 발표 정리

이 문서는 음성 면접 기능을 팀원에게 설명하기 위한 코드리뷰용 요약입니다.  
전체 흐름은 `면접 세션 생성 -> 질문 TTS 재생 -> 답변 녹음 -> Whisper STT 변환 -> 답변 저장 -> STT 지표 저장 -> 꼬리질문 생성 -> 리포트/평가 연결` 순서입니다.

## 1. TTS 백엔드: 질문을 음성으로 들려주는 기능

### 관련 파일

- `CAREER_DOT_ZIP_BACKEND/apps/interview/services/tts_service.py`
- `CAREER_DOT_ZIP_BACKEND/apps/interview/mvp_views.py`
- `CAREER_DOT_ZIP_BACKEND/apps/interview/mvp_urls.py`
- `CAREER_DOT_ZIP_FRONTEND/src/hooks/useTTS.js`
- `CAREER_DOT_ZIP_FRONTEND/src/api/interviewApi.js`

### 기능 설명

면접 질문 텍스트를 OpenAI TTS API로 mp3 음성으로 변환하는 기능입니다.  
프론트에서 질문 화면에 진입하면 현재 질문 텍스트와 `session_id`를 백엔드로 보내고, 백엔드는 해당 세션의 `persona`에 맞는 목소리를 선택해서 음성을 생성합니다.

`tts_service.py`의 핵심 함수는 `synthesize_interview_question()`입니다.

이 함수는 다음 역할을 합니다.

1. 질문 텍스트가 비어 있지 않은지, 너무 길지 않은지 검증합니다.
2. 면접관 페르소나 값을 정규화합니다.
3. `OPENAI_API_KEY`를 settings 또는 환경 변수에서 가져옵니다.
4. OpenAI SDK를 사용해 TTS mp3를 생성합니다.
5. SDK 응답에서 실제 mp3 bytes를 추출합니다.
6. View가 사용할 수 있도록 audio bytes와 모델/voice/persona 정보를 함께 반환합니다.

### View에서 활용하는 방식

`MVPTTSSpeechView`는 `synthesize_interview_question()`의 반환값을 받아서 HTTP 응답을 만듭니다.

```python
response = HttpResponse(result['audio_bytes'], content_type=result['content_type'])
response['X-TTS-Model'] = result['model']
response['X-TTS-Voice'] = result['voice']
response['X-TTS-Persona'] = result['persona']
return response
```

- `audio_bytes`: 실제 mp3 파일 내용입니다. 응답 body로 내려갑니다.
- `content_type`: `audio/mpeg`입니다. 프론트가 오디오 응답으로 인식합니다.
- `model`: 어떤 TTS 모델을 썼는지 헤더로 내려갑니다.
- `voice`: 어떤 목소리를 썼는지 헤더로 내려갑니다.
- `persona`: 어떤 면접관 페르소나 기준인지 헤더로 내려갑니다.

### 코드리뷰 발표 멘트

> 질문을 실제 면접처럼 들려주기 위해 백엔드 TTS API를 만들었습니다. View는 세션 소유권을 확인하고, 서비스 계층은 텍스트 검증, persona별 voice 선택, OpenAI TTS 호출, mp3 bytes 추출을 담당합니다. 프론트는 이 mp3 blob을 받아 재생하고, 실패하면 브라우저 기본 TTS로 fallback합니다.

## 2. Whisper STT 백엔드: 음성 답변을 텍스트와 분석 지표로 변환

### 관련 파일

- `CAREER_DOT_ZIP_BACKEND/apps/interview/services/whisper_stt_service.py`
- `CAREER_DOT_ZIP_BACKEND/apps/interview/mvp_views.py`
- `CAREER_DOT_ZIP_BACKEND/apps/interview/mvp_urls.py`
- `CAREER_DOT_ZIP_FRONTEND/src/api/interviewApi.js`
- `CAREER_DOT_ZIP_FRONTEND/src/pages/interview/InterviewQuestionCheckPage.jsx`

### 기능 설명

프론트에서 녹음한 `webm` 음성 파일을 Whisper STT API로 보내 텍스트로 변환하고, 단어별 timestamp를 이용해서 말하기 지표를 계산하는 기능입니다.

`whisper_stt_service.py`의 핵심 함수는 `transcribe_uploaded_audio()`입니다.

이 함수는 다음 역할을 합니다.

1. 업로드된 오디오 파일이 존재하는지 확인합니다.
2. `audio/webm` 또는 `audio/webm;codecs=opus` 타입인지 검증합니다.
3. 파일 크기가 25MB 이하인지 확인합니다.
4. Django `UploadedFile`을 임시 `.webm` 파일로 저장합니다.
5. OpenAI Whisper API를 호출합니다.
6. `verbose_json`과 `word timestamp`를 받아옵니다.
7. 단어별 시작/끝 시간을 정리합니다.
8. 단어 사이의 gap을 계산해 침묵 시간과 긴 침묵 횟수를 산출합니다.
9. STT 텍스트와 분석 지표를 JSON으로 반환합니다.
10. 임시 오디오 파일은 저장하지 않고 즉시 삭제합니다.

### 반환 데이터

```json
{
  "stt_text": "사용자의 답변 텍스트",
  "speech_duration": 12.3,
  "total_pause_duration": 2.1,
  "long_pause_count": 1,
  "processing_time_ms": 1240,
  "debug": {
    "audio_duration": 15.0,
    "pause_count": 3,
    "first_speech_start_sec": 0.4,
    "filler_words": {},
    "words": []
  }
}
```

### 코드리뷰 발표 멘트

> 음성 답변을 단순히 텍스트로 바꾸는 데서 끝내지 않고, Whisper의 word timestamp를 이용해 speech duration, pause duration, long pause count 같은 말하기 지표를 함께 계산했습니다. 이 값들은 이후 평가와 리포트에서 음성 답변 품질을 판단하는 보조 데이터로 사용할 수 있습니다.

## 3. 답변 저장과 평가 연결

### 관련 파일

- `CAREER_DOT_ZIP_BACKEND/apps/interview/models.py`
- `CAREER_DOT_ZIP_BACKEND/apps/interview/mvp_serializers.py`
- `CAREER_DOT_ZIP_BACKEND/apps/interview/mvp_views.py`
- `CAREER_DOT_ZIP_BACKEND/apps/interview/services/answer_service.py`
- `CAREER_DOT_ZIP_BACKEND/apps/evaluation/services/sufficiency_bridge.py`
- `CAREER_DOT_ZIP_BACKEND/apps/evaluation/services/session_evaluation.py`
- `CAREER_DOT_ZIP_FRONTEND/src/api/interviewApi.js`
- `CAREER_DOT_ZIP_FRONTEND/src/pages/interview/InterviewQuestionCheckPage.jsx`

### 기능 설명

음성 답변도 기존 `InterviewAnswer` 모델에 저장되도록 연결했습니다.  
기존 평가/리포트 로직은 `answer_text`를 기준으로 동작하기 때문에, STT 결과 텍스트를 `answer_text`에도 넣고, STT 원본 보존용으로 `stt_text`에도 저장합니다.

현재 저장 흐름은 두 단계입니다.

1. `/answers` API로 기본 답변을 생성합니다.
2. `/answers/{answer_id}/stt` API로 STT 원문과 음성 분석 지표를 patch합니다.

### 저장되는 주요 필드

- `answer_text`: 기존 평가/리포트 호환용 답변 텍스트
- `answer_source`: `text` 또는 `stt`
- `stt_text`: Whisper STT 원본 텍스트
- `speech_duration`: 실제 말한 시간
- `total_pause_duration`: 침묵 구간 총합
- `long_pause_count`: 긴 침묵 횟수
- `audio_url`: 현재는 `null`, 원본 음성 저장은 아직 구현되지 않음

### 소유권 검증

STT patch API에서는 `answer_id`만으로 답변을 수정하지 않고, 다음 조건으로 현재 로그인 사용자의 답변인지 확인합니다.

```python
answer = get_object_or_404(
    InterviewAnswer.objects.select_related('session', 'question'),
    id=answer_id,
    session__user=request.user,
)
```

즉, 본인 세션에 속한 답변만 STT 결과를 patch할 수 있습니다.

### 평가 연결

평가 쪽에서는 음성 면접이면 `stt_text`를 우선 사용하고, 일반 텍스트 면접이면 `answer_text`를 사용하도록 bridge를 둡니다.

```python
if answer.session.interview_mode == 'voice' and answer.stt_text:
    return answer.stt_text
return answer.answer_text or ''
```

### 코드리뷰 발표 멘트

> 음성 답변은 기존 답변 테이블을 그대로 활용했습니다. `answer_text`는 기존 평가/리포트 호환을 위해 유지하고, `stt_text`는 STT 원본 보존용으로 저장했습니다. STT patch API는 answer 소유권을 `session__user` 조건으로 검증하고, 평가 bridge에서는 voice 면접일 때 `stt_text`를 우선 사용하도록 연결했습니다.

## 4. 마이크 점검과 세션 준비 화면

### 관련 파일

- `CAREER_DOT_ZIP_FRONTEND/src/hooks/useMicrophoneSetupCheck.js`
- `CAREER_DOT_ZIP_FRONTEND/src/pages/input/SessionSetupPage.jsx`
- `CAREER_DOT_ZIP_FRONTEND/src/pages/interview/InterviewSetupCheckPage.jsx`

### 기능 설명

음성 면접을 시작하기 전에 브라우저에서 실제 마이크 권한, 입력 장치, 음성 레벨을 확인하는 기능입니다.  
마이크 확인이 완료되지 않으면 음성 면접 세션 생성을 막습니다.

핵심 훅은 `useMicrophoneSetupCheck()`입니다.

이 훅은 다음 역할을 합니다.

1. 브라우저가 `getUserMedia`와 `AudioContext`를 지원하는지 확인합니다.
2. `navigator.mediaDevices.enumerateDevices()`로 마이크 장치 목록을 가져옵니다.
3. 사용자가 특정 마이크를 선택할 수 있게 합니다.
4. `getUserMedia()`로 마이크 권한을 요청합니다.
5. Web Audio API로 입력 파형을 분석합니다.
6. RMS 기반으로 입력 음량을 계산합니다.
7. 무음, 너무 작음, 정상 입력 상태를 구분합니다.
8. 정상 입력이 일정 시간 유지되면 `isVerified=true`로 바꿉니다.
9. 스트림, AudioContext, animation frame을 cleanup합니다.

### 세션 생성 조건

`SessionSetupPage.jsx`에서는 음성 면접일 때 마이크 검증 완료 여부를 세션 생성 조건으로 사용합니다.

```js
const requiresMicrophone = interviewMode === 'voice';
```

```js
if (requiresMicrophone && !micCheck.isVerified) {
  setError('음성 면접을 시작하려면 마이크 점검을 먼저 완료해 주세요.');
  return;
}
```

### 실제 세션 준비 흐름

```text
JD 선택
-> 이력서 선택
-> 자소서/프로젝트 선택
-> 면접 유형/페르소나/질문 수 선택
-> 마이크 점검
-> 세션 생성
-> 질문 생성
-> 질문 목록 조회
-> /interview/question 이동
```

### 코드리뷰 발표 멘트

> 음성 면접은 마이크 입력이 핵심이기 때문에 세션 생성 전에 마이크 권한과 실제 입력 상태를 검증하도록 했습니다. 단순히 권한만 확인하는 것이 아니라 Web Audio API로 입력 레벨을 분석하고, 일정 시간 정상 입력이 유지되어야 면접 시작 버튼이 활성화되도록 만들었습니다.

## 5. 실제 음성 면접 진행 화면

### 관련 파일

- `CAREER_DOT_ZIP_FRONTEND/src/pages/interview/InterviewQuestionCheckPage.jsx`
- `CAREER_DOT_ZIP_FRONTEND/src/hooks/useTTS.js`
- `CAREER_DOT_ZIP_FRONTEND/src/api/interviewApi.js`

### 기능 설명

이 화면은 음성 면접의 메인 진행 화면입니다.  
앞에서 만든 TTS, STT, 답변 저장, 꼬리질문 생성 기능이 모두 여기서 연결됩니다.

### 화면 진입 후 흐름

1. 현재 질문을 store에서 가져옵니다.
2. 질문 텍스트를 TTS로 재생합니다.
3. 사용자가 녹음을 시작하면 TTS를 멈춥니다.
4. 브라우저 `MediaRecorder`로 `webm/opus` 음성을 녹음합니다.
5. 녹음 종료 시 blob을 생성합니다.
6. blob을 `/stt/transcribe`로 업로드합니다.
7. Whisper STT 결과를 받습니다.
8. STT 텍스트로 `/answers` API에 답변을 생성합니다.
9. `/answers/{answer_id}/stt` API로 STT 지표를 patch합니다.
10. `/answers/{answer_id}/followup` API로 꼬리질문 생성 여부를 확인합니다.
11. 필요하면 현재 질문 바로 뒤에 꼬리질문을 삽입합니다.
12. 마지막 질문이면 세션 상태를 `completed`로 변경합니다.

### 핵심 함수

`processAndSave()`가 가장 중요한 파이프라인입니다.

이 함수는 다음을 한 번에 이어줍니다.

```text
webm blob
-> Whisper STT
-> answer 생성
-> STT 분석값 patch
-> 꼬리질문 생성
-> 저장 완료 상태 처리
```

### 재시도 처리

실패 단계에 따라 재시도 방식이 다릅니다.

- STT 단계 실패: 원본 blob으로 STT부터 다시 처리합니다.
- 답변 저장 이후 실패: 기존 STT 결과를 재사용해 중복 STT 호출을 줄입니다.

### 코드리뷰 발표 멘트

> `InterviewQuestionCheckPage`는 음성 면접의 실제 진행 화면입니다. 질문이 바뀌면 TTS로 질문을 재생하고, 사용자가 답변을 녹음하면 MediaRecorder로 webm 파일을 만든 뒤 Whisper STT에 업로드합니다. 이후 STT 텍스트로 답변을 생성하고, pause 지표를 patch 저장한 뒤, 답변 충분성에 따라 꼬리질문을 생성합니다. 마지막 질문까지 끝나면 세션을 completed로 바꿔 리포트 흐름으로 넘깁니다.

## 6. API 라우트 구조

### 관련 파일

- `CAREER_DOT_ZIP_BACKEND/apps/interview/mvp_urls.py`

### 역할

`mvp_urls.py`는 MVP 음성 면접 플로우에서 프론트가 호출하는 API endpoint를 모아둔 라우팅 파일입니다.

주요 라우트는 다음과 같습니다.

```text
POST   /sessions
GET    /sessions/{session_id}
PATCH  /sessions/{session_id}/status

POST   /sessions/{session_id}/questions/generate
GET    /sessions/{session_id}/questions

POST   /answers
PATCH  /answers/{answer_id}/stt
POST   /answers/{answer_id}/followup

POST   /stt/transcribe
POST   /stt/transcribe/dev
POST   /tts/speech
```

### 코드리뷰 발표 멘트

> URL 파일은 음성 면접 플로우의 API 지도를 담당합니다. 세션, 질문, 답변, STT, TTS, 꼬리질문 endpoint가 한 곳에 모여 있어서 프론트 흐름과 백엔드 View를 연결하는 기준점 역할을 합니다.

## 7. 현재 보완 포인트

### 1. 깨진 한글 문자열 정리 필요

일부 파일에 한글 문자열이 인코딩 깨진 상태로 남아 있습니다.  
기능 로직과는 별개지만, 코드리뷰 전에 UI 문구와 기존 주석 문자열은 정리하는 것이 좋습니다.

대상 예시:

- `whisper_stt_service.py`의 `FILLER_WORDS`, `KOREAN_PUNCTUATION`
- 일부 프론트 에러 메시지/안내 문구
- 일부 기존 한글 주석

### 2. dev STT endpoint 정리 필요

`/stt/transcribe/dev`는 `AllowAny` 기반 테스트 endpoint입니다.  
현재 `DEBUG`가 아니면 차단되지만, 운영 배포 전에는 제거하거나 더 명확히 dev-only로 분리하는 것이 좋습니다.

### 3. 답변 저장이 create + patch 두 단계

현재 음성 답변 저장은 다음 두 단계입니다.

```text
POST /answers
PATCH /answers/{answer_id}/stt
```

이 구조는 기존 API와 호환성이 좋지만, 중간에 patch가 실패하면 답변만 저장되고 STT 지표가 누락될 수 있습니다.  
장기적으로는 STT 결과 포함 답변 생성 API를 별도로 만들 수도 있습니다.

### 4. 원본 음성 파일 저장은 아직 없음

현재 `audio_url`은 `null`로 저장됩니다.  
즉, STT 텍스트와 분석 지표는 저장하지만 원본 음성 파일은 보관하지 않습니다.

### 5. TTS fallback 개선 가능

OpenAI TTS mp3 재생 실패 시 브라우저 TTS fallback이 있습니다.  
다만 API 요청 자체가 실패하는 경우에도 fallback 동작을 더 명확하게 보장하도록 개선할 수 있습니다.

### 6. 사용하지 않는 화면 정리 필요

`InterviewSetupCheckPage.jsx`는 이전/대체 준비 화면 성격이 강합니다.  
현재 메인 흐름은 `SessionSetupPage.jsx -> InterviewQuestionCheckPage.jsx`로 보는 것이 자연스럽습니다.  
라우팅 기준으로 어떤 화면이 실제 메인 플로우인지 팀 내에서 정리하면 좋습니다.

## 8. 전체 발표용 요약

> 이번 작업은 텍스트 기반 면접 흐름에 음성 면접 기능을 붙인 것입니다.  
> 세션 준비 화면에서는 JD/이력서/프로젝트를 선택하고 마이크 입력을 검증한 뒤 세션과 질문을 생성합니다.  
> 실제 면접 화면에서는 질문을 TTS로 들려주고, 사용자의 답변을 브라우저 MediaRecorder로 녹음합니다.  
> 녹음된 webm 파일은 Whisper STT로 변환하고, STT 텍스트는 기존 답변 저장 구조와 호환되도록 `answer_text`에 저장합니다.  
> 동시에 `stt_text`, `speech_duration`, `total_pause_duration`, `long_pause_count` 같은 음성 분석 지표도 답변에 patch 저장합니다.  
> 이후 답변 충분성 판단에 따라 꼬리질문을 생성하고, 마지막 질문까지 끝나면 세션을 completed 상태로 바꿔 리포트 흐름으로 넘깁니다.

## 9. 아주 짧은 한 줄 요약

> 음성 면접 기능은 TTS로 질문을 들려주고, MediaRecorder로 답변을 녹음한 뒤, Whisper STT와 기존 평가 파이프라인을 연결해서 음성 답변도 평가 가능한 데이터로 저장하는 흐름입니다.
