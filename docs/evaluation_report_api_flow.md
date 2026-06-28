# 평가 및 최종 리포트 API 프론트 연동 가이드

## 1. 목적

면접 완료 후 평가(Evaluation)와 최종 리포트(FinalReport)를 프론트에서 조회하는 API 호출 순서와 주요 응답 필드를 정리한다.

MVP 기준 프론트 메인 흐름은 아래와 같다.

```text
세션 완료 (PATCH /sessions/{session_id}/complete)
→ 리포트 조회/자동생성 (GET /sessions/{session_id}/report)
→ 답변별 평가 상세 조회 (GET /evaluations/{answer_id})
→ 강점/약점 태그 조회 (GET /evaluations/{answer_id}/strength-tags | weakness-tags)
```

> 아래 API 경로는 각 앱의 `urls.py` 기준 상대 경로이다.  
> 실제 호출 시에는 프로젝트 라우팅 prefix를 앞에 붙여 사용한다.  
> 예: `/api/v1/interview/sessions/{session_id}/report` 등 프로젝트 설정에 맞게 조정

---

## 2. 전체 호출 순서

| 순서 | 목적 | Method | Path |
| --- | --- | --- | --- |
| 1 | 리포트 조회 / 자동생성 | GET | `/sessions/{session_id}/report` |
| 2 | 답변별 평가 상세 조회 | GET | `/evaluations/{answer_id}` |
| 3 | 강점 태그 조회 | GET | `/evaluations/{answer_id}/strength-tags` |
| 4 | 약점 태그 조회 | GET | `/evaluations/{answer_id}/weakness-tags` |
| 5 | (선택) 리포트 목록 조회 | GET | `/reports` |
| 6 | (선택) 리포트 재생성 | POST | `/reports/sessions/{session_id}/generate` |

---

## 3. 리포트 조회 / 자동생성

프론트 기준 핵심 API이다. 세션 완료 후 이 엔드포인트 하나로 리포트를 조회하거나 자동생성할 수 있다.

- 리포트가 없으면 자동으로 생성해 반환한다.
- 리포트가 있더라도 이전에 AI 평가가 전부 실패한 상태라면 재시도 후 반환한다.
- 세션이 `completed` 상태가 아니면 404를 반환한다.

### Request

```http
GET /sessions/{session_id}/report
```

### 주요 응답 필드

```json
{
  "report_id": "uuid",
  "session_id": "uuid",
  "status": "completed",
  "generated_at": "2025-01-01T00:00:00Z",
  "summary": {
    "score_summary": {
      "overall_score": 72,
      "average_bei_score": 68.5,
      "average_cbi_level": 2.4,
      "average_speech_score": 80.0,
      "average_sbert_score": 0.74
    },
    "score_detail": [...],
    "dynamically_triggered_tags": {
      "strengths": [
        {
          "tag_name": "논리적 구조화",
          "description": "...",
          "trigger_signal": "..."
        }
      ],
      "weaknesses": [
        {
          "tag_name": "구체성 부족",
          "description": "...",
          "trigger_signal": "..."
        }
      ]
    },
    "evaluation_metadata": {
      "answer_count": 3,
      "evaluated_answer_count": 3,
      "summary_text": "전반적으로 논리적인 답변 구조를 갖추고 있으나 구체적인 수치 근거가 부족합니다.",
      "generated_at": "2025-01-01T00:00:00Z"
    }
  }
}
```

### 에러 케이스: AI 평가 실패

OpenAI 호출이 실패해 평가가 전혀 생성되지 않은 경우 503을 반환한다.

```json
HTTP 503

{
  "error": "evaluation_failed",
  "detail": "AI 평가 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
}
```

프론트에서는 503 응답 시 재시도 안내 UI를 표시하고 동일 엔드포인트를 다시 호출한다.

### 참고

- 세션이 `completed` 상태가 아닌 경우 404를 반환한다.
- `overall_score`는 `summary.score_summary.overall_score`에 있다.  
  `null`일 경우 평가가 아직 없거나 전부 실패한 상태다.

---

## 4. 답변별 평가 상세 조회

### Request

```http
GET /evaluations/{answer_id}
```

### 주요 응답 필드

```json
{
  "evaluation_id": "uuid",
  "answer_id": "uuid",
  "bei_score": {
    "score": 70,
    "situation": 18,
    "task": 17,
    "action": 20,
    "result": 15
  },
  "cbi_score": {
    "score": 3,
    "level": "중"
  },
  "filler_words": {
    "count": 4,
    "penalty": -2
  },
  "sbert_db_similarity": 0.78,
  "sbert_readme_similarity": 0.65,
  "llm_concept_score": 8,
  "answer_score": 74,
  "score_detail": {
    "bei_weight": 0.4,
    "cbi_weight": 0.3,
    "speech_weight": 0.15,
    "sbert_weight": 0.15
  },
  "evaluated_at": "2025-01-01T00:00:00Z"
}
```

### 주요 점수 필드 설명

| 필드 | 설명 |
| --- | --- |
| `bei_score` | STAR 구조 기반 답변 구성 점수. `situation / task / action / result` 세부 포함 |
| `cbi_score` | 역량 행동 지표 점수. `level`은 하/중/상 |
| `filler_words` | 습관어 감지 결과. `count`는 감지 횟수, `penalty`는 감점 |
| `sbert_db_similarity` | DB 직무 레퍼런스와의 의미 유사도 (0~1) |
| `sbert_readme_similarity` | README 레퍼런스와의 의미 유사도 (0~1) |
| `llm_concept_score` | LLM이 평가한 개념 이해도 점수 (0~10) |
| `answer_score` | 위 항목을 종합한 최종 기술 점수 (0~100) |

---

## 5. 강점 태그 조회

### Request

```http
GET /evaluations/{answer_id}/strength-tags
```

### 주요 응답 필드

```json
{
  "answer_id": "uuid",
  "strength_tags": [
    {
      "id": "uuid",
      "tag_name": "논리적 구조화",
      "reason": "[communication] 답변이 STAR 흐름에 맞게 구성되어 있음",
      "priority_rank": 1,
      "trigger_signal_log": "situation → task → action → result 순서로 명확히 서술함"
    }
  ]
}
```

---

## 6. 약점 태그 조회

### Request

```http
GET /evaluations/{answer_id}/weakness-tags
```

### 주요 응답 필드

```json
{
  "answer_id": "uuid",
  "weakness_tags": [
    {
      "id": "uuid",
      "tag_name": "구체성 부족",
      "reason": "수치나 구체적 결과 언급이 없음",
      "priority_rank": 1,
      "is_selected_for_followup": true,
      "used_for": "follow_up",
      "followup_question_id": "uuid"
    }
  ]
}
```

### 참고

- `is_selected_for_followup: true`인 태그는 꼬리질문 생성에 사용된 약점이다.
- `followup_question_id`는 해당 약점에서 생성된 꼬리질문 ID이다. null이면 아직 꼬리질문이 없다.

---

## 7. 리포트 목록 조회

마이페이지 등 지난 면접 이력을 보여줄 때 사용한다.

### Request

```http
GET /reports
```

### 주요 응답 필드

```json
{
  "total": 2,
  "results": [
    {
      "report_id": "uuid",
      "session_id": "uuid",
      "interview_type": "technical",
      "persona": "practical",
      "overall_score": 72,
      "summary_text": "전반적으로 논리적인 답변 구조를 갖추고 있으나 구체적인 수치 근거가 부족합니다.",
      "generated_at": "2025-01-01T00:00:00Z"
    }
  ]
}
```

---

## 8. 리포트 재생성

기존 리포트를 강제로 재생성할 때 사용한다. 일반적인 프론트 흐름에서는 사용하지 않으며, AI 평가 실패 후 관리자 또는 서비스 레벨에서 재시도할 때 활용한다.

### Request

```http
POST /reports/sessions/{session_id}/generate
```

### Body

```json
{
  "force_regenerate": true
}
```

- `force_regenerate`를 생략하거나 `false`로 보내면 기존 리포트가 있을 경우 그대로 반환한다.
- `true`로 보내면 기존 리포트의 `summary`를 덮어쓴다.

### 응답

- 신규 생성 시 `201 Created`, 기존 리포트가 있고 `force_regenerate: false`인 경우 `200 OK`를 반환한다.
- 응답 body 구조는 `GET /reports/sessions/{session_id}`와 동일하다.

---

## 9. 평가 수동 생성 (선택적)

MVP에서는 리포트 생성 시 미평가 답변이 자동 백필되므로 프론트에서 직접 호출할 필요가 없다.  
특정 답변에 대해 즉시 평가를 트리거해야 하는 경우에만 사용한다.

### Request

```http
POST /evaluations
```

### Body

```json
{
  "answer_id": "uuid"
}
```

### 주요 응답 필드

```json
{
  "evaluation_id": "uuid",
  "answer_id": "uuid",
  "evaluated_at": "2025-01-01T00:00:00Z",
  "answer_score": 74
}
```

### 참고

- 동일 `answer_id`로 평가가 이미 존재하면 400을 반환한다.
- 타인의 답변 ID를 전달해도 400을 반환한다 (소유권 검증 포함).

---

## 10. 프론트 구현 시 권장 흐름

```text
1. 면접 완료 (PATCH /sessions/{session_id}/complete)
2. 결과 화면 진입 시 GET /sessions/{session_id}/report 호출
   → 503 응답이면 재시도 안내 UI 표시 후 동일 엔드포인트 재호출
3. summary.score_summary.overall_score로 종합 점수 표시
4. summary.dynamically_triggered_tags로 세션 전체 강점/약점 태그 표시
5. 답변별 상세 탭에서 GET /evaluations/{answer_id} 로 세부 점수 표시
6. 강점/약점 태그 패널에서 GET /evaluations/{answer_id}/strength-tags
   및 GET /evaluations/{answer_id}/weakness-tags 호출
```

---

## 11. BE 검증 상태

아래 흐름은 E2E 테스트로 검증 완료되었다.

```text
세션 완료
→ GET /sessions/{session_id}/report (자동 평가 백필 + 리포트 생성)
→ GET /evaluations/{answer_id}
→ GET /evaluations/{answer_id}/strength-tags
→ GET /evaluations/{answer_id}/weakness-tags
```

---

## 12. 참고 사항

- 모든 API는 인증된 사용자 기준으로 동작하며, 타인의 세션/답변에는 접근할 수 없다.
- 프론트는 JWT 인증 헤더를 포함해야 한다.
- 평가는 멱등하다: 동일 `answer_id`에 대해 중복 생성을 시도하면 기존 평가를 그대로 반환하거나 400을 반환한다.
- OpenAI 실제 호출은 BE 설정값에 따라 mock 또는 real engine으로 동작한다.
