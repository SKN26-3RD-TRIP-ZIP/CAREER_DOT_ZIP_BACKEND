from schemas.evaluation import AnswerSufficiencyInput

mock_sufficiency_response = AnswerSufficiencyInput(
    answer_id="ans_00001",
    is_sufficient=False,
    sufficiency_reason="프로젝트에서 수행한 역할은 언급했지만 기술 선택 이유가 구체적이지 않음",
    answer_weakness_tags=[
        {
            "weakness_tag_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "tag_name": "weak_technical_reasoning",
            "reason": "장고나 슬로우 쿼리 추적 시의 인덱스 설정 기준이 설명되지 않음",
            "priority_rank": 1,
            "is_selected_for_followup": True
        }
    ],
    selected_weakness_tag={
        "weakness_tag_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
        "tag_name": "weak_technical_reasoning",
        "reason": "기술 선택 기준 보완 필요"
    },
    should_generate_followup=True,
    next_action="generate_followup"
)

mock_stt_text = """부트캠프 당시에 올림픽 호스트 국가 효과 분석 서비스를 장고로 개발했습니다. 
마이그레이션 중에 속도가 엄청 느려지는 장애가 터졌습니다. 어... 팀원들이랑 코드를 열어서 슬로우 쿼리를 추적했고 쿼리를 최적화했습니다. 
음... 그 결과 프로젝트 배포를 무사히 완료했습니다."""