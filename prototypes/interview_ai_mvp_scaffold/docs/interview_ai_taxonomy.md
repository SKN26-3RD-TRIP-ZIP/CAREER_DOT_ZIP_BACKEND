# AI 면접관 파트 공통 분류 기준

## 목적

질문 생성, 답변 평가, 꼬리질문 생성, 최종 리포트에서 공통으로 사용할 분류 기준을 정의한다.

이 문서는 평가 담당자, 리포트 담당자, 백엔드 담당자와 필드명을 맞추기 위한 기준표이다.

---

## 1. Question Type

| 값 | 이름 | 설명 | 예시 |
|---|---|---|---|
| `project_experience` | 프로젝트 경험 | 프로젝트 전체 맥락, 목표, 진행 과정, 본인 경험 확인 | 해당 프로젝트를 진행하게 된 배경과 본인이 맡은 역할을 설명해 주세요. |
| `technical_reasoning` | 기술 선택/이해 | 기술 선택 이유, 대안 비교, 트레이드오프, 기술 원리 확인 | Django를 선택한 이유와 FastAPI와 비교했을 때의 장단점을 설명해 주세요. |
| `contribution_check` | 본인 기여도 | 팀 프로젝트에서 본인이 직접 수행한 역할과 기여 범위 확인 | 이 기능 구현에서 본인이 직접 담당한 부분은 어디까지였나요? |
| `problem_solving` | 문제 해결 | 문제 상황, 원인 분석, 해결 과정, 결과 확인 | 프로젝트 중 가장 어려웠던 문제와 이를 해결한 과정을 설명해 주세요. |
| `job_fit` | 직무 적합성 | JD 요구사항과 사용자 경험의 연결성 확인 | JD에서 요구하는 SQL 역량과 관련해 수행한 경험을 설명해 주세요. |
| `collaboration` | 협업/커뮤니케이션 | 팀 협업, 역할 분담, 소통 방식, 갈등 해결 경험 확인 | 프론트엔드 팀원과 API 명세를 맞추는 과정에서 어떻게 소통했나요? |
| `growth_learning` | 학습/성장 | 학습 과정, 회고, 개선점, 성장 가능성 확인 | 이 프로젝트를 통해 배운 점과 다음에 보완하고 싶은 점은 무엇인가요? |
| `fallback` | 보완 질문 | 입력 자료에서 핵심 정보가 부족할 때 생성하는 보완 질문 | 프로젝트 결과나 개선 효과를 구체적으로 설명해 주실 수 있나요? |

---

## 2. Follow-up Type

| 값 | 이름 | 설명 | 예시 |
|---|---|---|---|
| `specificity_check` | 구체성 확인 | 답변이 추상적일 때 구체적인 사례, 근거, 상황 확인 | 방금 말씀하신 문제 상황을 조금 더 구체적인 사례로 설명해 주실 수 있나요? |
| `technical_reasoning` | 기술 근거 확인 | 기술 선택 이유, 대안 비교, 트레이드오프 확인 | FastAPI와 비교했을 때 Django를 선택한 기준은 무엇이었나요? |
| `contribution_check` | 기여도 확인 | 본인이 직접 수행한 작업 범위와 책임 확인 | 그 과정에서 본인이 직접 구현한 부분은 어디까지였나요? |
| `result_check` | 성과 확인 | 결과, 개선 효과, 정량 지표, 피드백 확인 | 그 개선 결과를 수치나 사용자 피드백으로 설명할 수 있나요? |
| `job_fit_check` | 직무 연결 확인 | 답변을 지원 직무/JD 요구사항과 연결 | 이 경험이 지원한 백엔드 개발자 직무와 어떻게 연결된다고 생각하나요? |
| `problem_solving_deepening` | 문제 해결 심화 | 문제 원인 분석, 해결 과정, 선택 기준 심화 확인 | 그 문제의 원인을 어떻게 파악했고, 왜 그 해결 방식을 선택했나요? |
| `answer_structure` | 답변 구조 보완 | 답변 흐름이 정리되지 않았을 때 구조화된 답변 유도 | 상황, 역할, 행동, 결과 순서로 다시 정리해서 설명해 주실 수 있나요? |

---

## 3. Weakness Tag

| 값 | 이름 | 설명 | 권장 꼬리질문 유형 | 리포트 활용 |
|---|---|---|---|---|
| `lack_of_specificity` | 구체성 부족 | 상황, 역할, 행동, 결과가 구체적으로 드러나지 않음 | `specificity_check` | 답변에 구체적인 사례와 근거를 추가하도록 안내 |
| `weak_technical_reasoning` | 기술적 근거 부족 | 기술 선택 이유, 대안 비교, 트레이드오프 설명이 부족함 | `technical_reasoning` | 기술 선택 기준과 비교 대안을 설명하도록 안내 |
| `unclear_contribution` | 본인 기여도 불명확 | 팀 프로젝트에서 본인이 직접 수행한 역할이 명확하지 않음 | `contribution_check` | 본인이 직접 맡은 작업과 책임 범위를 구체화하도록 안내 |
| `missing_result` | 성과 설명 부족 | 프로젝트 결과나 개선 효과가 구체적으로 제시되지 않음 | `result_check` | 정량 지표, 결과, 피드백을 포함하도록 안내 |
| `weak_job_fit` | 직무 연관성 부족 | 답변이 지원 직무의 요구 역량과 충분히 연결되지 않음 | `job_fit_check` | 경험과 JD 요구사항의 연결성을 보완하도록 안내 |
| `shallow_problem_solving` | 문제 해결 과정 부족 | 문제 상황, 원인 분석, 해결 과정이 얕게 설명됨 | `problem_solving_deepening` | 문제 원인, 해결 과정, 선택 이유를 단계적으로 설명하도록 안내 |
| `missing_keywords` | 핵심 키워드 누락 | 질문 의도상 포함되어야 할 핵심 개념이나 용어가 빠짐 | `specificity_check` | 누락된 핵심 키워드를 보완하도록 안내 |
| `unstructured_answer` | 답변 구조 부족 | 답변 흐름이 정리되어 있지 않아 핵심이 잘 전달되지 않음 | `answer_structure` | STAR 구조 등으로 답변을 재구성하도록 안내 |

---

## 4. Evaluation Result 연동 기준

평가 담당 파트는 최소 아래 필드를 반환한다.

```json
{
  "evaluation_id": "eval_001",
  "question_id": "q_001",
  "answer": "사용자 답변",
  "score": 3,
  "strengths": ["잘한 점"],
  "weaknesses": ["보완할 점"],
  "missing_keywords": ["누락 키워드"],
  "weakness_tags": ["weak_technical_reasoning", "lack_of_specificity"]
}
```

꼬리질문 생성 파트는 이 중 아래 필드를 사용한다.

```text
- weaknesses
- missing_keywords
- weakness_tags
```

최종 리포트 파트는 아래 필드를 집계할 수 있다.

```text
- score
- strengths
- weaknesses
- weakness_tags
- missing_keywords
```

---

## 5. 현재 MVP 기준

MVP에서는 `weakness_tags`를 너무 세분화하지 않고, 아래 8개를 우선 사용한다.

```text
lack_of_specificity
weak_technical_reasoning
unclear_contribution
missing_result
weak_job_fit
shallow_problem_solving
missing_keywords
unstructured_answer
```

최종 고도화 단계에서 직무별/질문 유형별 태그를 추가할 수 있다.
