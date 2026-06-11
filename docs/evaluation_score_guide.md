# Evaluation Score Guide

## 1. 개요

면접 답변 하나(InterviewAnswer)에 대해 생성되는 Evaluation의 점수 체계를 정의한다.

평가는 **4개 축**으로 구성된다.

| 축 | 측정 대상 | 처리 방식 |
|---|---|---|
| BEI (STAR 구조) | 답변의 행동 서술 구조 | LLM 평가 |
| CBI (역량 수준) | 역량 행동 지표 레벨 | LLM 평가 |
| Speech Delivery | 발화 유창성 (습관어·반복) | 로컬 분석 |
| Technical Grounding | 수치/기술스택 기반 근거 | LLM 평가 |

---

## 2. BEI Score (STAR 구조 평가)

STAR(Situation-Task-Action-Result) 프레임워크 기반 답변 구조 평가.

```json
"bei_score": {
  "situation": { "score": 20, "evidence": "..." },
  "task":      { "score": 18, "evidence": "..." },
  "action":    { "score": 25, "evidence": "..." },
  "result":    { "score": 15, "evidence": "..." },
  "total":     78
}
```

| 요소 | 설명 |
|---|---|
| `situation` | 상황 설명의 구체성과 맥락 전달력 |
| `task` | 자신이 맡은 역할과 목표 명확성 |
| `action` | 실제 행동의 구체성·주도성 |
| `result` | 결과 수치화·마무리 완결성 |
| `total` | 4개 요소 합산 (각 최대 25점, 합계 최대 100점 이론치) |

> `total`은 `final_tech_score` 산출 시 가중치 적용 전 원점수로 사용된다.

---

## 3. CBI Score (역량 행동 지표)

역량 수준을 1~5 레벨로 분류하고 점수로 환산.

```json
"cbi_score": {
  "assigned_level": 3,
  "score": 60.0,
  "evidence_sentence": "팀 리더로서 일정 조율을 주도했습니다."
}
```

| 필드 | 설명 |
|---|---|
| `assigned_level` | LLM이 판단한 역량 레벨 (1~5 정수) |
| `score` | `assigned_level × 20`으로 환산된 점수 (20~100) |
| `evidence_sentence` | LLM이 레벨 판단 근거로 추출한 답변 문장 |

**레벨 기준:**

| 레벨 | 환산 점수 | 의미 |
|---|---|---|
| 1 | 20 | 역량 발휘 증거 없음 |
| 2 | 40 | 단순 업무 수행 수준 |
| 3 | 60 | 자율적 업무 수행 |
| 4 | 80 | 팀/조직에 영향을 주는 수준 |
| 5 | 100 | 조직 전략/방향에 기여하는 수준 |

---

## 4. Filler Words (발화 유창성)

로컬 형태소 분석(kiwipiepy) 기반 비유창성 감지.

```json
"filler_words": {
  "counts": { "어": 3, "음": 2, "이제": 1 },
  "total": 6,
  "repetitions": ["정말", "사실"],
  "comment": "발화 중 무의식적인 간투사가 자주 반복되어 전달력이 저하될 우려가 있습니다. (총 6회 포착)"
}
```

| 필드 | 설명 |
|---|---|
| `counts` | 단어별 감지 횟수 |
| `total` | 전체 습관어 감지 횟수 |
| `repetitions` | 연속 반복 발화 감지 목록 |
| `comment` | 총 횟수 기반 자동 생성 코멘트 |

**감지 대상 습관어:** 어, 음, 그니까, 그러니까, 사실, 이제, 저기

**speech_score 산출 공식:**

```
speech_score = 100 - (total_filler_count × 5.0)
speech_score = max(speech_score, 20)  # 최저 20점 보정
```

| total 범위 | speech_score | 코멘트 분류 |
|---|---|---|
| 0~2 | 90~100 | 안정적 |
| 3~6 | 70~85 | 무난하나 정돈 필요 |
| 7+ | 20~65 | 전달력 저하 우려 |

---

## 5. SBERT Similarity (의미 유사도)

DB/README 레퍼런스와의 의미 유사도 (0.0~1.0 범위 float).

```json
"sbert_db_similarity": 0.78,
"sbert_readme_similarity": 0.65
```

| 필드 | 설명 |
|---|---|
| `sbert_db_similarity` | 직무 레퍼런스 DB와의 의미 유사도 |
| `sbert_readme_similarity` | 프로젝트 README 레퍼런스와의 의미 유사도 |

> null이면 SBERT 평가가 적용되지 않은 상태. 현재 MVP에서는 고도화 예정 축.

---

## 6. LLM Concept Score

LLM이 평가한 개념 이해도 점수 (0~10 정수).

> 현재 `score_detail.technical_depth.is_grounded`로 활용되며, `final_tech_score` 산출 시 grounding_premium으로 반영.

---

## 7. final_tech_score (최종 종합 점수)

**기술 면접 (interview_type = "technical"):**

```
raw = (bei_total × 0.4) + (cbi_score × 0.4) + (speech_score × 0.2) + grounding_premium
final_tech_score = min(raw, 100)
```

**인성/기타 면접:**

```
raw = (bei_total × 0.5) + (cbi_score × 0.3) + (speech_score × 0.2)
final_tech_score = min(raw, 100)
```

| 항목 | 기술면접 가중치 | 인성면접 가중치 |
|---|---|---|
| BEI (STAR 총합) | 40% | 50% |
| CBI (역량 점수) | 40% | 30% |
| Speech Delivery | 20% | 20% |
| Grounding Premium | +15점 (조건부) | 없음 |

**Grounding Premium 조건:**

`score_detail.technical_depth.is_grounded == true` 일 때 +15점 가산.
수치/기술스택 근거가 명확한 답변에 적용.

---

## 8. score_detail (상세 산출 내역)

```json
"score_detail": {
  "bei_logic": {
    "total": 78,
    "weights": { "bei": 0.4 }
  },
  "cbi_competency": {
    "assigned_level": 3,
    "score": 60.0,
    "evidence_sentence": "..."
  },
  "technical_depth": {
    "tech_stack": "Django, PostgreSQL",
    "before_metric": "응답속도 3초",
    "after_metric": "응답속도 0.8초",
    "is_grounded": true
  },
  "speech_delivery": {
    "total_filler_count": 4,
    "long_pause_count": 1,
    "speech_score": 80.0
  },
  "meta_cognition": {}
}
```

| 섹션 | 설명 |
|---|---|
| `bei_logic` | BEI 총점 및 적용 가중치 |
| `cbi_competency` | CBI 레벨, 환산 점수, 근거 문장 |
| `technical_depth` | 기술스택·수치 근거 추출 결과 및 grounding 여부 |
| `speech_delivery` | 습관어 횟수, 묵음 횟수, speech_score |
| `meta_cognition` | 현재 미사용 (향후 확장 예정) |
