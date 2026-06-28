# Report Summary Format

## 1. 개요

`FeedbackReport.summary`는 세션 전체 평가 결과를 집약한 JSONB 필드이다.
`generate_final_report()` 가 반환하는 구조와 1:1 대응한다.

최상위 키는 4개이다.

| 키 | 설명 |
|---|---|
| `evaluation_metadata` | 세션 기본 정보 및 평가 집계 현황 |
| `score_summary` | 전체 점수 요약 (overall + 5개 지표) |
| `score_detail` | 강약점·개선안·질문별 상세 + 통계 진단 |
| `dynamically_triggered_tags` | 동적 생성된 강점/약점 태그 |

---

## 2. evaluation_metadata

```json
"evaluation_metadata": {
  "session_id": 42,
  "persona_type": "backend_developer",
  "interview_mode": "text",
  "interview_type": "technical",
  "question_count": 5,
  "answer_count": 5,
  "evaluated_answer_count": 5,
  "calculated_at": "2025-08-01T14:23:00+09:00",
  "summary_text": "전반적으로 STAR 구조가 잘 갖춰진 답변이 많았으며..."
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `session_id` | int | 면접 세션 PK |
| `persona_type` | string | 면접 페르소나 유형 (e.g. `backend_developer`) |
| `interview_mode` | string | `text` / `voice` |
| `interview_type` | string | `technical` / `behavioral` 등 — grounding premium 적용 여부에 영향 |
| `question_count` | int | 세션 내 전체 질문 수 |
| `answer_count` | int | 실제 제출된 답변 수 |
| `evaluated_answer_count` | int | 평가 완료된 답변 수 |
| `calculated_at` | ISO 8601 | 리포트 생성 시각 (KST) |
| `summary_text` | string | LLM이 생성한 세션 전체 총평 |

---

## 3. score_summary

```json
"score_summary": {
  "overall_score": 74,
  "metrics": {
    "bei_logic_score": 78.5,
    "cbi_competency_score": 72.0,
    "grounding_score": 60.0,
    "speech_delivery_score": 85.0,
    "technical_score": 76.2
  }
}
```

| 필드 | 설명 |
|---|---|
| `overall_score` | 모든 평가 답변의 `answer_score` 평균 |
| `metrics.bei_logic_score` | 답변별 BEI total 평균 |
| `metrics.cbi_competency_score` | 답변별 CBI score 평균 |
| `metrics.grounding_score` | 답변별 grounding 반영 점수 평균 |
| `metrics.speech_delivery_score` | 답변별 speech_score 평균 |
| `metrics.technical_score` | 답변별 answer_score 평균 (overall_score와 동일 계열) |

---

## 4. score_detail

```json
"score_detail": {
  "strength": ["..."],
  "weakness": ["..."],
  "improvement": ["..."],
  "questions": [...],
  "statistics": {
    "bei_metrics": {
      "averages": {
        "situation": 18.2,
        "task": 17.4,
        "action": 22.6,
        "result": 14.8
      },
      "element_total_avg": 73.0
    },
    "cbi_metrics": {
      "average_level": 3.2,
      "average_score": 64.0
    }
  },
  "speech_diagnostics": {
    "total_filler_count": 18,
    "avg_fillers_per_answer": 3.6,
    "filler_word_distribution": { "어": 8, "음": 5, "이제": 3, "그니까": 2 }
  }
}
```

### 4-1. 서술형 피드백

| 필드 | 설명 |
|---|---|
| `strength` | 세션 전반의 강점 요약 (string 배열) |
| `weakness` | 세션 전반의 약점 요약 (string 배열) |
| `improvement` | 개선 방향 제안 (string 배열) |

### 4-2. questions (답변별 상세)

```json
"questions": [
  {
    "question_id": 101,
    "question_text": "가장 어려웠던 기술적 도전을 설명해주세요.",
    "answer_text": "...",
    "bei_score": {
      "situation": { "score": 20, "evidence": "..." },
      "task":      { "score": 18, "evidence": "..." },
      "action":    { "score": 25, "evidence": "..." },
      "result":    { "score": 15, "evidence": "..." },
      "total": 78
    },
    "cbi_score": {
      "assigned_level": 3,
      "score": 60.0,
      "evidence_sentence": "..."
    },
    "filler_words": {
      "counts": { "어": 2, "음": 1 },
      "total": 3,
      "comment": "..."
    },
    "answer_score": 76,
    "score_detail": { ... }
  }
]
```

각 항목의 필드 상세는 `evaluation_score_guide.md` 참고.

### 4-3. statistics

| 경로 | 설명 |
|---|---|
| `bei_metrics.averages.{situation\|task\|action\|result}` | STAR 요소별 세션 평균 점수 |
| `bei_metrics.element_total_avg` | BEI total의 세션 평균 |
| `cbi_metrics.average_level` | CBI 레벨 세션 평균 |
| `cbi_metrics.average_score` | CBI 환산 점수 세션 평균 |

### 4-4. speech_diagnostics

| 필드 | 설명 |
|---|---|
| `total_filler_count` | 세션 전체 습관어 누적 횟수 |
| `avg_fillers_per_answer` | 답변당 평균 습관어 횟수 |
| `filler_word_distribution` | 습관어 종류별 총 횟수 |

---

## 5. dynamically_triggered_tags

```json
"dynamically_triggered_tags": {
  "strength_tags": [
    {
      "tag_name": "수치 기반 근거 제시",
      "description": "구체적인 지표를 활용하여 결과를 설명하는 능력이 두드러집니다.",
      "trigger_signal": "is_grounded == true (3회 이상)"
    }
  ],
  "weakness_tags": [
    {
      "tag_name": "결과 진술 부족",
      "description": "행동 이후의 성과나 결과를 수치화하거나 구체화하는 서술이 미흡합니다.",
      "trigger_signal": "bei_score.result < 15 (2회 이상)"
    }
  ]
}
```

| 필드 | 설명 |
|---|---|
| `strength_tags` | 강점 태그 배열 (상위 최대 5개) |
| `weakness_tags` | 약점 태그 배열 (상위 최대 5개) |
| `tag_name` | 태그 제목 |
| `description` | 태그 상세 설명 |
| `trigger_signal` | 해당 태그가 발동된 조건 (로깅 및 디버깅용) |

---

## 6. 전체 스키마 요약

```
FeedbackReport.summary
├── evaluation_metadata
│   ├── session_id
│   ├── persona_type
│   ├── interview_mode / interview_type
│   ├── question_count / answer_count / evaluated_answer_count
│   ├── calculated_at
│   └── summary_text
├── score_summary
│   ├── overall_score
│   └── metrics
│       ├── bei_logic_score
│       ├── cbi_competency_score
│       ├── grounding_score
│       ├── speech_delivery_score
│       └── technical_score
├── score_detail
│   ├── strength / weakness / improvement
│   ├── questions[]
│   │   ├── question_id / question_text / answer_text
│   │   ├── bei_score (situation, task, action, result, total)
│   │   ├── cbi_score (assigned_level, score, evidence_sentence)
│   │   ├── filler_words (counts, total, comment)
│   │   ├── answer_score
│   │   └── score_detail (→ evaluation_score_guide.md)
│   ├── statistics
│   │   ├── bei_metrics (averages, element_total_avg)
│   │   └── cbi_metrics (average_level, average_score)
│   └── speech_diagnostics
│       ├── total_filler_count
│       ├── avg_fillers_per_answer
│       └── filler_word_distribution
└── dynamically_triggered_tags
    ├── strength_tags[] (tag_name, description, trigger_signal)
    └── weakness_tags[] (tag_name, description, trigger_signal)
```
