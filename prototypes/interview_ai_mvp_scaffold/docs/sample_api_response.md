# Sample API Response

## 질문 생성 응답 예시

```json
{
  "session_id": "session_abcd1234",
  "user_id": "user_001",
  "persona_id": "practical",
  "questions": [
    {
      "question_id": "q_001",
      "question": "프로젝트에서 사용한 핵심 기술을 선택한 이유와 다른 대안과 비교했을 때의 장단점은 무엇인가요?",
      "question_type": "technical_reasoning",
      "source_type": "resume_jd",
      "source_summary": "이력서/자소서에 작성된 프로젝트 기술 경험과 JD 요구 역량을 기반으로 생성한 질문",
      "difficulty": "medium",
      "intent": "기술 선택 이유와 트레이드오프 설명 능력을 확인하기 위한 질문",
      "expected_keywords": ["기술 선택 이유", "대안 비교", "트레이드오프", "프로젝트 요구사항"]
    }
  ]
}
```

## 꼬리질문 응답 예시

```json
{
  "question_id": "q_001",
  "follow_ups": [
    {
      "follow_up_id": "fu_abcd1234",
      "question_id": "q_001",
      "follow_up_question": "방금 답변에서 언급한 기술 선택을 다른 대안과 비교했을 때, 가장 중요한 판단 기준은 무엇이었나요?",
      "follow_up_type": "technical_reasoning",
      "trigger_reason": "기술 선택 이유는 언급했지만 대안 비교와 판단 기준이 부족함",
      "based_on_weakness_tags": ["weak_technical_reasoning"]
    }
  ]
}
```
