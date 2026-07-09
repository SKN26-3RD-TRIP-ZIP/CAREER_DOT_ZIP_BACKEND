# Interview Voice Flow Enhancement Priorities

작성일: 2026-06-23

## 범위

현재 면접 MVP 음성 플로우 기준으로 고도화할 항목을 정리한다. 확인한 주요 흐름은 다음과 같다.

- `InterviewAnswer`에는 이미 `stt_text`, `audio_url`, `speech_duration`, `total_pause_duration`, `long_pause_count`가 있다.
- 프론트는 녹음 파일을 `/stt/transcribe`로 보내고, STT 결과를 `/answers/{answer_id}/stt`로 patch한다.
- 현재 patch payload의 `audio_url`은 프론트에서 `null`로 보내고 있어 실제 음성 원본은 저장되지 않는다.
- S3/django-storages 설정은 아직 없고, 미디어는 로컬 `MEDIA_ROOT` 중심이다.
- 포인트/지갑 전용 앱이나 잔액 모델은 현재 앱 목록에서 확인되지 않았다.

## P0. 먼저 해야 할 것

### 1. 사용자 답변 음성 파일 S3 저장 + `InterviewAnswer.audio_url` 저장

현재 `audio_url` 필드는 이미 있으므로 DB 컬럼 추가보다 업로드 파이프를 붙이는 것이 우선이다.

구현 방향:

- 백엔드에서 STT 요청을 받을 때 `audio` 파일을 S3에 업로드한다.
- 저장 키는 `interview/{user_id}/{session_id}/{answer_id or temp_uuid}.webm`처럼 소유자와 세션을 포함한다.
- STT 변환 결과 응답에 `audio_url` 또는 `audio_key`를 포함한다.
- 프론트는 기존 `patchSttResult` payload의 `audio_url: null` 대신 백엔드가 반환한 URL을 전달한다.
- 더 안전한 방향은 `/answers/{answer_id}/stt`에서 파일 업로드와 STT 저장까지 한 번에 처리해 `answer_id`와 음성 파일 저장을 같은 트랜잭션 경계로 묶는 것이다.

주의점:

- 공개 URL보다 `audio_key` 저장 + 다운로드 시 presigned URL 발급이 안전하다.
- S3 업로드는 STT 성공 여부와 별개로 정리 정책이 필요하다. STT 실패 파일은 삭제하거나 `failed` 상태로 추적한다.
- `django-storages`, `boto3`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` 설정이 필요하다.

완료 기준:

- 답변 저장 후 `interview_answers.audio_url` 또는 `audio_key`가 비어 있지 않다.
- 리포트/관리자에서 어떤 답변의 원본 음성인지 추적 가능하다.
- STT 실패, S3 실패, patch 실패 케이스에서 재시도 UX가 깨지지 않는다.

### 2. STT 답변 욕설/혐오 발언 감지 및 세션 누적 중단 + 상태 전이 차단

현재 STT 결과가 `MVPSTTResultUpdateView`에서 `answer_text`와 `stt_text`에 동기화되므로 이 지점이 감지 로직을 넣기 가장 좋다. 다만 욕설/혐오 누적으로 세션을 종료하는 기능은 상태 전이 검증과 한 묶음으로 처리해야 한다. 세션을 `failed` 또는 `cancelled`로 바꿔도 이후 답변 저장, 꼬리질문 생성, `in_progress` 복귀가 가능하면 강제 종료 정책이 쉽게 우회되기 때문이다.

구현 방향:

- `apps/interview/services/content_moderation_service.py`를 추가한다.
- 1차는 금칙어 사전 기반으로 빠르게 감지하고, 추후 OpenAI Moderation 또는 별도 모델을 붙일 수 있게 인터페이스를 분리한다.
- `InterviewAnswer`에 답변별 감지 결과를 저장한다.
  - 예: `moderation_payload = models.JSONField(default=dict, blank=True)`
  - 예: `abuse_count = models.PositiveIntegerField(default=0)`
- `InterviewSession`에 세션 누적치를 저장한다.
  - 예: `abuse_count = models.PositiveIntegerField(default=0)`
  - 예: `terminated_reason = models.CharField(max_length=50, blank=True)`
- 누적 기준은 정책값으로 둔다.
  - 기본 제안: 3회 이상이면 자동 종료
  - 5회는 경고를 여러 번 허용하는 느슨한 모드
  - 발표/운영 안정성을 생각하면 `settings.INTERVIEW_ABUSE_LIMIT = 3` 추천
- 누적 초과 시 세션 상태를 `failed` 또는 `cancelled`로 바꾸고 `ended_at`을 기록한다.
- 세션 상태 전이 규칙을 함께 강화한다.
  - `created -> in_progress -> completed`
  - `created/in_progress -> cancelled`
  - `created/in_progress -> failed`
  - `completed/failed/cancelled` 이후에는 일반 status patch를 차단한다.
  - 강제 종료된 세션에서는 답변 저장, STT patch, 꼬리질문 생성을 차단한다.
- 종료 사유 필드 추가를 검토한다.
  - 예: `ended_reason = models.CharField(max_length=50, blank=True)`

API 응답 제안:

```json
{
  "answer_id": "...",
  "stt_text": "...",
  "moderation": {
    "flagged": true,
    "count": 1,
    "session_count": 3,
    "limit": 3
  },
  "session_status": "failed",
  "next_action": "SESSION_TERMINATED"
}
```

완료 기준:

- 같은 세션에서 감지 횟수가 누적된다.
- 기준 초과 시 프론트가 다음 질문으로 넘어가지 않고 종료 화면 또는 안내 화면으로 이동한다.
- 종료된 세션을 다시 진행 중으로 바꿀 수 없다.
- 강제 종료된 세션에서 답변 저장/꼬리질문 생성이 막힌다.
- 단순 경고 케이스와 강제 종료 케이스가 테스트로 분리된다.

### 3. 면접 준비 단계 포인트 차감/차단

현재 포인트 도메인 모델이 확인되지 않았으므로, 면접 세션 생성 전에 최소한의 지갑 모델을 먼저 정의해야 한다.

구현 방향:

- `accounts` 또는 별도 `billing`/`points` 앱에 모델을 둔다.
- 추천 모델:
  - `UserPointBalance(user, balance)`
  - `PointTransaction(user, amount, reason, ref_type, ref_id, created_at)`
- 세션 생성 API `POST /sessions`에서 트랜잭션으로 포인트를 검사하고 차감한다.
- 포인트 부족 시 `402 Payment Required` 또는 `400` + 명확한 error code를 반환한다.
  - 예: `INSUFFICIENT_POINTS`
- 세션 생성 실패 시 포인트 차감이 남지 않게 반드시 `transaction.atomic()`으로 묶는다.
- 사용자가 세션을 생성만 하고 질문 생성 전에 이탈하는 정책을 정해야 한다.
  - 단순 정책: 세션 생성 시 차감, 취소 환불 없음
  - 사용자 친화 정책: 질문 생성 성공 시 차감
  - 추천: 질문 생성 성공 시 차감. AI 질문 생성 실패와 포인트 차감이 엮이지 않아 민원 가능성이 낮다.

완료 기준:

- 포인트 부족 사용자는 면접 준비 완료 또는 질문 생성 단계에 진입하지 못한다.
- 차감 이력이 남고 중복 차감이 방지된다.
- 질문 생성 실패 시 포인트가 차감되지 않거나 자동 환불된다.

## P1. 바로 이어서 하면 좋은 것

### 4. STT 전체 분석 payload 저장

현재 백엔드는 `stt_text`, `speech_duration`, `total_pause_duration`, `long_pause_count`만 저장한다. 하지만 STT 응답에는 `processing_time_ms`, `debug.words`, `filler_words`, `pause_count`, `first_speech_start_sec` 같은 분석 원천 데이터가 있다.

구현 방향:

- `InterviewAnswer.stt_payload = models.JSONField(default=dict, blank=True)` 추가.
- `/answers/{answer_id}/stt` serializer에 `stt_payload` 또는 `debug` 저장을 허용한다.
- 평가/리포트는 파생 데이터, `stt_payload`는 원천 데이터로 역할을 분리한다.

효과:

- 리포트 고도화, 음성 습관 분석, 디버깅, 재평가에 사용할 수 있다.
- 나중에 STT 엔진을 바꿔도 원본 응답 비교가 가능하다.

### 5. TTS 결과 캐싱 또는 질문별 음성 URL 저장

현재 TTS는 요청마다 OpenAI TTS를 호출하고 mp3 blob을 바로 반환한다. 같은 질문을 다시 재생하면 비용과 지연이 반복될 수 있다.

구현 방향:

- 질문 단위로 `tts_audio_url` 또는 `tts_audio_key`를 저장한다.
- 같은 `question_id`, `persona`, `voice`, `model` 조합이면 기존 S3 음성을 재사용한다.
- TTS 합성 실패 시 기존 브라우저 TTS fallback은 유지한다.

우선순위가 P1인 이유:

- 답변 원본 저장은 사용자 데이터 보존과 리포트 근거에 직접 연결된다.
- TTS 캐싱은 비용/UX 개선 성격이 강해서 그 다음 순서가 적절하다.

## P2. 품질/운영 고도화

### 6. STT/TTS 서비스 파일 주석 인코딩 복구

`tts_service.py`, `whisper_stt_service.py`, `answer_service.py`에 한글 주석이 깨져 있어 유지보수성이 떨어진다.

구현 방향:

- 파일 인코딩을 UTF-8로 정리한다.
- 깨진 주석은 짧은 한국어 또는 영어 주석으로 복구한다.
- 기능 변경 없이 주석만 정리하는 PR로 분리하는 편이 안전하다.

### 7. 음성 파일 보존 정책과 개인정보 정책 명시

면접 답변 음성은 민감한 개인 데이터에 가깝다. S3 저장을 붙이면 보존 기간과 삭제 정책이 필요하다.

정책 제안:

- 기본 보존 기간: 30일 또는 리포트 생성 후 7일
- 사용자가 리포트에서 원본 음성 삭제 가능
- 회원 탈퇴 시 S3 객체 삭제 대상에 포함
- 관리자 접근은 presigned URL + 감사 로그로 제한

### 8. 리포트/성장 분석과 STT 지표 연결

프론트 `useReport`에는 성장 추이와 로드맵 훅이 보류 상태다. STT 전체 payload와 답변별 음성 지표를 저장하면 다음 리포트 고도화로 연결할 수 있다.

구현 방향:

- 세션별 평균 답변 길이, 침묵 비율, 필러워드 추이를 집계한다.
- `GET /mypage/growth`에서 면접 점수 + 음성 습관 지표를 함께 반환한다.
- `GET /sessions/{id}/roadmap`에서 개선 과제를 생성한다.

## 추천 실행 순서

1. `InterviewAnswer.audio_url`을 실제로 채우는 S3 업로드 파이프 구현
2. STT payload 저장 필드 추가
3. 욕설/혐오 감지, 세션 누적 종료, 종료 세션 진행 차단
4. 포인트 모델/트랜잭션 설계 후 질문 생성 성공 시 차감
5. TTS 캐싱 또는 질문별 TTS URL 저장
6. 리포트 성장 분석 API 연결
7. 깨진 주석/문서 인코딩 정리

## 이번 스프린트 권장 작업 묶음

가장 현실적인 1차 범위:

- S3 업로드 설정과 답변 음성 저장
- `stt_payload` JSONField 추가
- `/answers/{answer_id}/stt`에서 `audio_url`, `stt_payload`, pause 지표를 함께 저장
- 욕설/혐오 감지는 사전 기반 MVP로 시작하고 `INTERVIEW_ABUSE_LIMIT=3` 적용, 종료 세션의 추가 진행 차단까지 함께 구현
- 포인트는 모델 설계 문서와 API error contract까지만 먼저 확정

이렇게 끊으면 현재 음성 면접 플로우의 데이터 보존, 안전장치, 평가 확장성이 한 번에 좋아지고, 포인트 결제 정책처럼 팀 합의가 필요한 항목은 설계 충돌을 줄인 뒤 구현할 수 있다.
