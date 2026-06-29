# 사용자 설정 인재상 평가·리포트 연동 계약안

## 1. 평가 파트 입력 데이터

질문 생성과 평가 파트는 `resolve_effective_talent_profile(jd)` 결과를 참고 데이터로 받을 수 있다.

```json
{
  "source_type": "USER_DEFINED",
  "is_official": false,
  "confirmed_by_user": true,
  "summary": "빠르게 실행하고 결과를 기반으로 개선하는 문화를 중요하게 생각합니다.",
  "items": [
    {
      "trait_code": "OWNERSHIP",
      "trait_name": "주도성",
      "category_code": "EXECUTION_RESPONSIBILITY",
      "category_name": "실행과 책임",
      "priority_order": 1,
      "description": "문제를 먼저 발견하고 해결 방법을 제안하는 사람"
    }
  ],
  "prompt_notice": "아래 인재상은 사용자가 면접 연습을 위해 설정한 기준이며 회사의 공식 인재상으로 단정하지 마세요."
}
```

`confirmed_by_user=false`인 사용자 설정값은 평가 기준으로 사용하지 않는다.

## 2. 인재상별 평가 결과 필드 제안

기존 평가 API Response는 유지하고, 후속 합의 후 `score_detail` 또는 별도 확장 필드에 아래 구조를 추가하는 방안을 제안한다.

```json
{
  "talent_profile_evidence": [
    {
      "trait_code": "OWNERSHIP",
      "trait_name": "주도성",
      "score_0_4": 3,
      "evidence_summary": "문제를 직접 발견하고 해결한 행동 근거가 확인됨",
      "missing_evidence": "트레이드오프 설명은 부족함"
    }
  ]
}
```

## 3. 0~4 공통 평가 기준

| 점수 | 기준 |
| --- | --- |
| 0 | 관련 근거 없음 |
| 1 | 성향이나 의지만 있고 행동 근거 없음 |
| 2 | 관련 경험은 있으나 역할·행동·결과가 불명확 |
| 3 | 상황·행동·결과가 구체적 |
| 4 | 판단 근거·트레이드오프·결과·회고까지 명확 |

공통 평가 차원은 `상황 적합성`, `본인 행동의 구체성`, `결과 또는 변화`, `회고와 재적용 가능성`이다.

## 4. 리포트 Response 필드 제안

FinalReport DB 스키마는 변경하지 않는다. 후속 구현 시 `summary` JSON 내부에 아래 블록을 추가하는 방안을 제안한다.

```json
{
  "talent_profile_summary": {
    "source_type": "USER_DEFINED",
    "is_official": false,
    "notice": "사용자가 면접 연습을 위해 설정한 인재상 기준",
    "high_evidence_traits": ["OWNERSHIP", "COLLABORATION"],
    "summary_text": "사용자가 설정한 인재상 기준으로 주도성과 협업 관련 행동 근거가 확인되었습니다."
  }
}
```

## 5. 출처 표시 방식

사용자 설정값은 항상 다음 의미로 표시한다.

```text
사용자가 면접 연습을 위해 설정한 인재상 기준
```

회사 공식 인재상으로 단정하지 않는다.

## 6. 금지 표현

```text
이 회사 인재상에 85% 적합합니다.
```

권장 표현:

```text
사용자가 설정한 인재상 기준으로
주도성과 협업 관련 행동 근거가 확인되었습니다.
```

## 7. 기존 Response 호환 방안

- `EvaluationSerializer`의 기존 필드는 유지한다.
- `FinalReport.summary`의 기존 `score_summary`, `evaluation_metadata`, `dynamically_triggered_tags` 구조는 유지한다.
- 신규 인재상 결과는 optional 필드로 추가해 기존 프론트가 무시할 수 있게 한다.
- 점수 산식에는 반영하지 않고, 먼저 근거 요약과 피드백 보조 정보로 사용한다.

## 8. 담당자 합의 필요 항목

- 인재상별 0~4 점수를 `Evaluation.score_detail`에 넣을지 `FinalReport.summary`에만 넣을지
- 인재상 평가를 질문별로 할지 세션 전체 집계로 할지
- 리포트 화면에서 인재상 근거를 별도 섹션으로 노출할지
- USER_DEFINED 외 `OFFICIAL`, `HYBRID`, `JOB_DEFAULT`를 언제 활성화할지
- 사용자 설정 인재상이 없는 경우 리포트 문구를 생략할지 기본 안내를 표시할지
