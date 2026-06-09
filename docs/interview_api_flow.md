# 면접 진행 API 프론트 연동 가이드

## 1. 목적

프론트 면접 진행 화면에서 사용할 BE API 호출 순서와 주요 응답 필드를 정리한다.

이 문서는 면접 MVP 흐름 기준으로 작성되었으며, 아래 흐름을 기준으로 한다.

```text
페르소나 목록 조회
→ 면접 세션 생성
→ 질문 생성
→ turns 조회
→ 답변 저장
→ 꼬리질문 생성
→ turns 재조회
→ 세션 완료
```

> 아래 API 경로는 `apps/interview/urls.py` 기준 상대 경로이다.  
> 실제 호출 시에는 프로젝트 라우팅 prefix가 있으면 앞에 붙여 사용한다.  
> 예: `/api/v1/interview/sessions`, `/api/v1/sessions` 등 프로젝트 설정에 맞게 조정

---

## 2. 전체 호출 순서

| 순서 | 목적 | Method | Path |
| --- | --- | --- | --- |
| 1 | 페르소나 목록 조회 | GET | `/personas` |
| 2 | 면접 세션 생성 | POST | `/sessions` |
| 3 | 세션 진행 상태 변경 | PATCH | `/sessions/{session_id}/status` |
| 4 | 질문 생성 | POST | `/sessions/{session_id}/questions/generate` |
| 5 | 면접 진행 상태 조회 | GET | `/sessions/{session_id}/turns` |
| 6 | 답변 저장 | POST | `/sessions/{session_id}/questions/{question_id}/answer` |
| 7 | 꼬리질문 생성 | POST | `/sessions/{session_id}/answers/{answer_id}/follow-up/generate` |
| 8 | 면접 진행 상태 재조회 | GET | `/sessions/{session_id}/turns` |
| 9 | 세션 완료 | PATCH | `/sessions/{session_id}/complete` |

---

## 3. 페르소나 목록 조회

### Request

```http
GET /personas
```

### 주요 응답 필드

```json
{
  "total": 3,
  "results": [
    {
      "persona_type": "friendly",
      "label": "친절한 코치형",
      "description": "...",
      "usage_guide": "..."
    },
    {
      "persona_type": "practical",
      "label": "실무 면접관형",
      "description": "...",
      "usage_guide": "..."
    },
    {
      "persona_type": "verify",
      "label": "검증 면접관형",
      "description": "...",
      "usage_guide": "..."
    }
  ]
}
```

### 프론트 사용 방식

- 페르소나 선택 카드에 `label`, `description`, `usage_guide`를 사용한다.
- 세션 생성 시 `persona_type` 값을 `persona`로 전달한다.

---

## 4. 면접 세션 생성

### Request

```http
POST /sessions
```

### Body 예시

```json
{
  "jd_id": "uuid",
  "resume_id": "uuid",
  "cover_letter_id": "uuid",
  "interview_type": "technical",
  "persona": "practical",
  "total_question_count": 3
}
```

### 참고

- `jd_id`, `resume_id`, `cover_letter_id`는 사용자가 입력한 문서 상태에 따라 선택적으로 전달한다.
- MVP 기준으로 `persona`는 아래 값 중 하나를 사용한다.
  - `friendly`
  - `practical`
  - `verify`
- 알 수 없는 persona 값은 BE에서 기본값 `practical`로 정규화한다.

### 주요 응답 필드

```json
{
  "session_id": "uuid",
  "interview_type": "technical",
  "persona": "practical",
  "persona_detail": {
    "persona_type": "practical",
    "label": "실무 면접관형",
    "description": "...",
    "usage_guide": "..."
  },
  "status": "created",
  "total_question_count": 3,
  "created_at": "..."
}
```

---

## 5. 세션 진행 상태 변경

### Request

```http
PATCH /sessions/{session_id}/status
```

### Body 예시

```json
{
  "status": "in_progress"
}
```

### 사용 시점

- 사용자가 실제 면접 시작 버튼을 눌렀을 때 호출한다.
- `in_progress`로 변경되면 BE에서 `started_at`이 기록된다.

---

## 6. 질문 생성

### Request

```http
POST /sessions/{session_id}/questions/generate
```

### Body 예시

```json
{}
```

필요 시 재생성 옵션을 사용할 수 있다.

```json
{
  "force_regenerate": true
}
```

### 주요 응답 필드

```json
{
  "session_id": "uuid",
  "total": 3,
  "questions": [
    {
      "question_id": "uuid",
      "order_index": 1,
      "question_type": "main",
      "question_text": "프로젝트에서 본인이 맡은 역할을 설명해주세요.",
      "source_type": "resume",
      "source_reference": "..."
    }
  ]
}
```

### 프론트 사용 방식

- 질문 생성 후 바로 `GET /sessions/{session_id}/turns`를 호출해 화면 상태를 갱신한다.
- MVP 기준 메인 질문은 `question_type: "main"`으로 저장된다.

---

## 7. 면접 진행 상태 조회: turns

### Request

```http
GET /sessions/{session_id}/turns
```

### 주요 응답 구조

```json
{
  "session_id": "uuid",
  "interview_type": "technical",
  "persona": "practical",
  "persona_detail": {
    "persona_type": "practical",
    "label": "실무 면접관형",
    "description": "...",
    "usage_guide": "..."
  },
  "status": "in_progress",
  "total": 3,
  "progress": {
    "main_question_count": 3,
    "answered_count": 1,
    "follow_up_question_count": 1,
    "total_question_count": 3,
    "current_question_index": 1,
    "completion_rate": 0.33
  },
  "current_turn": {
    "turn_index": 2,
    "question_id": "uuid",
    "answer_id": null
  },
  "next_action": {
    "type": "ANSWER_CURRENT_QUESTION",
    "question_id": "uuid",
    "answer_id": null
  },
  "turns": [
    {
      "turn_index": 1,
      "question": {
        "question_id": "uuid",
        "order_index": 1,
        "question_type": "main",
        "question_text": "..."
      },
      "answer": {
        "answer_id": "uuid",
        "answer_text": "...",
        "answer_source": "text",
        "created_at": "..."
      },
      "evaluation": null,
      "follow_up_questions": []
    }
  ]
}
```

---

## 8. `next_action.type` 기준 화면 처리

프론트는 `turns` 응답의 `next_action.type`을 기준으로 다음 화면/동작을 판단한다.

| next_action.type | 의미 | 프론트 동작 |
| --- | --- | --- |
| `ANSWER_CURRENT_QUESTION` | 현재 메인 질문에 대한 답변이 필요함 | 질문 표시 후 답변 입력/녹음 UI 표시 |
| `GENERATE_FOLLOW_UP` | 저장된 답변 기반 꼬리질문 생성이 필요함 | 꼬리질문 생성 API 호출 |
| `COMPLETE_INTERVIEW` | 모든 질문 흐름이 완료됨 | 면접 완료 버튼 또는 결과 화면 이동 |

### 처리 예시

```text
if next_action.type === "ANSWER_CURRENT_QUESTION":
    current_turn.question_id 기준으로 답변 저장 UI 표시

if next_action.type === "GENERATE_FOLLOW_UP":
    next_action.answer_id 기준으로 꼬리질문 생성 API 호출

if next_action.type === "COMPLETE_INTERVIEW":
    세션 완료 API 호출 또는 결과 화면으로 이동
```

---

## 9. 답변 저장

### Request

```http
POST /sessions/{session_id}/questions/{question_id}/answer
```

### Body 예시

```json
{
  "answer_text": "제가 Django REST Framework 기반 API 설계를 담당했습니다.",
  "answer_source": "text"
}
```

### 참고

- MVP 현재 단계에서는 `answer_text`에 텍스트 답변을 저장한다.
- STT 연동 후에는 음성 인식 결과 텍스트를 `answer_text`로 전달하면 된다.
- `answer_source`는 현재 `text`를 기본으로 사용하고, STT 연동 시 `voice` 또는 `stt` 등으로 확장 가능하다.

### 주요 응답 필드

```json
{
  "answer_id": "uuid",
  "question_id": "uuid",
  "answer_text": "...",
  "answer_source": "text",
  "created_at": "..."
}
```

---

## 10. 꼬리질문 생성

### Request

```http
POST /sessions/{session_id}/answers/{answer_id}/follow-up/generate
```

### 사용 시점

- `GET /sessions/{session_id}/turns` 응답에서 `next_action.type`이 `GENERATE_FOLLOW_UP`일 때 호출한다.

### 주요 응답 필드

```json
{
  "session_id": "uuid",
  "answer_id": "uuid",
  "total": 1,
  "follow_up_questions": [
    {
      "question_id": "uuid",
      "parent_question_id": "uuid",
      "answer_id": "uuid",
      "order_index": 4,
      "question_type": "follow_up",
      "question_text": "방금 답변에서 언급한 API 설계 기준을 더 구체적으로 설명해 주세요."
    }
  ]
}
```

### 프론트 사용 방식

- 꼬리질문 생성 후 `GET /sessions/{session_id}/turns`를 다시 호출한다.
- 재조회 결과에서 `follow_up_questions` 배열을 화면에 반영한다.

---

## 11. 세션 완료

### Request

```http
PATCH /sessions/{session_id}/complete
```

### 사용 시점

- `next_action.type`이 `COMPLETE_INTERVIEW`일 때 호출한다.
- 또는 사용자가 면접 종료 버튼을 눌렀을 때 호출한다.

### 주요 응답 필드

```json
{
  "session_id": "uuid",
  "status": "completed",
  "started_at": "...",
  "ended_at": "..."
}
```

---

## 12. 프론트 구현 시 권장 흐름

```text
1. /personas 호출
2. 사용자가 persona 선택
3. /sessions POST로 세션 생성
4. /sessions/{session_id}/status PATCH로 in_progress 변경
5. /sessions/{session_id}/questions/generate 호출
6. /sessions/{session_id}/turns 호출
7. next_action.type 확인
8. ANSWER_CURRENT_QUESTION이면 답변 저장
9. GENERATE_FOLLOW_UP이면 꼬리질문 생성 후 turns 재조회
10. COMPLETE_INTERVIEW이면 세션 완료
```

---

## 13. BE 검증 상태

BE 기준으로 아래 흐름은 E2E 테스트로 검증 완료되었다.

```text
페르소나 목록 조회
→ 세션 생성
→ 세션 상태 변경
→ 질문 생성
→ 질문 목록 조회
→ turns 조회
→ 답변 저장
→ 꼬리질문 생성
→ 꼬리질문 목록 조회
→ turns 재조회
→ 세션 완료
```

검증 테스트:

```bash
python manage.py test apps.interview.test_interview_mvp_e2e_flow
python manage.py test apps.interview
```

---

## 14. 참고 사항

- 모든 API는 인증된 사용자 기준으로 동작한다.
- 프론트는 JWT 인증 헤더를 포함해야 한다.
- OpenAI 실제 호출은 BE 설정값에 따라 mock 또는 real engine으로 동작한다.
- MVP에서는 답변 텍스트 저장 흐름을 우선 사용하고, STT는 이후 `answer_text`에 연결하면 된다.
