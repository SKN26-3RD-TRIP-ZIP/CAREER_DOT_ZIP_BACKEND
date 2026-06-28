# Interview llm chain에서 받아올 값들

## 1. QuestionGenerationChain
- 질문 (타입과 내용) 및 기반 문서 정보 수집
- 주요 키 값: questions 하위 question_text, question_type, source_type, source_text_excerpt

{
  "session_id": "uuid",
  "questions": [
    {
      "client_question_key": "q_001",
      "question_text": "금융 데이터 분석 프로젝트에서 본인이 맡은 역할과 기술 선택 이유를 설명해주세요.",
      "question_type": "technical",
      "difficulty": null,
      "order_index": 1,
      "generation_reason": "이력서의 프로젝트 경험과 JD의 Python, SQL 역량 요구사항이 연결됨",
      "source_tags": [
        {
          "source_type": "resume",
          "source_label": "이력서 기반",
          "source_text_excerpt": "금융 데이터 분석 프로젝트에서 AI 체인 설계 및 리포트 생성을 담당"
        },
        {
          "source_type": "jd",
          "source_label": "JD 기반",
          "source_text_excerpt": "Python, SQL 기반 데이터 분석 역량 요구"
        }
      ]
    }
  ]
}

## 2. AnswerSufficiencyChain
- 약점 태그 전부 수집
- 주요 키 값: sufficiency_reason, answer_weakness_tags 하위 모든 내용

{
  "answer_id": "uuid",
  "is_sufficient": false,
  "sufficiency_reason": "프로젝트에서 수행한 역할은 언급했지만, 본인 기여도와 기술 선택 이유가 구체적으로 드러나지 않음",
  "answer_weakness_tags": [
    {
      "weakness_tag_id": "uuid",
      "tag_name": "본인 기여도 불명확",
      "reason": "사용자가 프로젝트에서 어떤 역할을 주도했는지 구체적으로 설명하지 않음",
      "priority_rank": 1,
      "is_selected_for_followup": true
    },
    {
      "weakness_tag_id": "uuid",
      "tag_name": "기술 선택 이유 부족",
      "reason": "LangChain이나 OpenDART를 선택한 기준이 설명되지 않음",
      "priority_rank": 2,
      "is_selected_for_followup": false
    }
  ],
  "selected_weakness_tag": {
    "weakness_tag_id": "uuid",
    "tag_name": "본인 기여도 불명확",
    "reason": "프로젝트에서 본인이 맡은 역할과 기여도를 우선 확인할 필요가 있음"
  },
  "should_generate_followup": true,
  "next_action": "GENERATE_FOLLOWUP"
}

## 3. FollowUpQuestionChain
- 꼬리질문과 꼬리질문의 기반이 된 약점태그 수집
- 주요 키 값: followup_question 하위 parent_question_id, answer_weakness_tag_id, question_text, question_type, generation_reason

{
  "session_id": "uuid",
  "followup_question": {
    "parent_question_id": "uuid",
    "generated_from_answer_id": "uuid",
    "answer_weakness_tag_id": "uuid",
    "question_text": "방금 답변에서 데이터 수집과 분석을 했다고 말씀하셨는데, 그중 본인이 직접 설계하거나 주도한 부분은 무엇이었나요?",
    "question_type": "technical",
    "difficulty": null,
    "order_index": 2,
    "generation_reason": "본인 기여도가 불명확하다는 트리거 태그를 기준으로 생성됨"
  }
}