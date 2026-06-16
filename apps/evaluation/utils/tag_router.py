# apps/evaluation/utils/tag_router.py
import re


def _to_korean(text: str, fallback: str) -> str:
    """텍스트에 영어 비중이 높으면 fallback 한국어 문자열을 반환한다.

    sufficiency 체인이 영어로 reason을 반환하는 경우를 방어.
    ASCII 비율이 50% 초과 시 영어로 판정.
    """
    if not text:
        return fallback
    ascii_count = sum(1 for c in text if c.isascii() and c.isalpha())
    alpha_count = sum(1 for c in text if c.isalpha())
    if alpha_count > 0 and ascii_count / alpha_count > 0.5:
        return fallback
    return text

def route_deterministic_tags(
    question_type: str,
    bei_star: dict,
    cbi_res: dict,
    grounding_res: dict,
    total_filler: int,
    long_pause_count: int,
    raw_word_count: int,
    tech_score: float,
    stt_text: str = "",               
    llm_weakness_tags: list = None    
) -> dict:
    
    triggered_strengths = []
    triggered_weaknesses = []

    # 0. 파일 내부 실제 정량 지표 데이터 가공 및 방어 코드 구축
    is_excessive_fillers = total_filler > 6 

    # 점수 키 유실에 대비한 데이터 무결성 방어 조치 (기본값 0)
    bei_situation_score = bei_star.get("situation", {}).get("score", 0) if bei_star else 0
    bei_task_score = bei_star.get("task", {}).get("score", 0) if bei_star else 0
    bei_action_score = bei_star.get("action", {}).get("score", 0) if bei_star else 0
    bei_result_score = bei_star.get("result", {}).get("score", 0) if bei_star else 0
    
    # cbi_res 구조 유연화 (호환성 방어)
    cbi_competency_root = cbi_res.get("cbi_competency", {}) if cbi_res else {}
    cbi_level = cbi_competency_root.get("assigned_level", cbi_res.get("cbi_competency_level", {}).get("level", 1) if cbi_res else 1)
    is_grounded = grounding_res.get("is_grounded", False) if grounding_res else False

    # P0-4 기획 구현을 위한 아키텍처 트레이드오프 마스터 사전
    TRADEOFF_DICTIONARY = ["장점", "단점", "비용", "대안", "트레이드오프", "반면에", "리스크", "비교", "tradeoff"]
    matched_tradeoff_words = [w for w in TRADEOFF_DICTIONARY if w in stt_text]
    tradeoff_match_ratio = len(matched_tradeoff_words) / len(TRADEOFF_DICTIONARY) if TRADEOFF_DICTIONARY else 0


    # ----------------------------------------------------
    # 🌪️ [약점 태그] 수정 및 동기화 (P0-1 ~ P0-13)
    # ----------------------------------------------------
    
    # P0-1. weak_question_relevance
    if llm_weakness_tags and any(t.get("tag_name") == "weak_question_relevance" for t in llm_weakness_tags):
        triggered_weaknesses.append({
            "tag_name": "weak_question_relevance",
            "category": "answer_relevance",
            "description": "질문의 의도와 다르게 답변하거나 핵심 질문에 직접 답하지 못하고 겉도는 경향이 있음",
            "trigger_signal": "실시간 LLM 컨텍스트 파인딩 결과 주제 이탈 태그 중복 포착"
        })

    # P0-2. weak_specificity
    if bei_action_score < 15 or bei_result_score < 12:
        triggered_weaknesses.append({
            "tag_name": "weak_specificity",
            "category": "answer_quality",
            "description": "답변이 추상적이고 구체적인 상황, 행동, 결과가 부족함",
            "trigger_signal": f"BEI STAR 과락 임계치 도달 (Action: {bei_action_score}/25, Result: {bei_result_score}/25)"
        })

    # P0-3. weak_technical_understanding
    if question_type == "technical" and tech_score < 40:
        triggered_weaknesses.append({
            "tag_name": "weak_technical_understanding",
            "category": "technical",
            "description": "사용한 기술이나 개념에 대한 이해 설명이 부족하여 기초 스킬셋 신뢰도가 낮음",
            "trigger_signal": f"기술 Grounding 엔진 팩트 실증 실패 패널티 수치 도달 (Score: {tech_score})"
        })

    # P0-4. weak_technical_reasoning
    if question_type == "technical" and tradeoff_match_ratio < 0.20:
        triggered_weaknesses.append({
            "tag_name": "weak_technical_reasoning",
            "category": "technical",
            "description": "기술을 왜 선택했는지, 다른 대안과 비교한 의사결정 이유가 부족함",
            "trigger_signal": f"트레이드오프 사전 검사 결과 기획 임계치 미달 (매칭률: {tradeoff_match_ratio * 100:.1f}%)"
        })

    # P0-5. weak_personal_contribution
    if llm_weakness_tags and any(t.get("tag_name") == "weak_personal_contribution" for t in llm_weakness_tags):
        llm_tag_meta = next(t for t in llm_weakness_tags if t.get("tag_name") == "weak_personal_contribution")
        custom_reason = llm_tag_meta.get("reason", llm_tag_meta.get("description", ""))
        triggered_weaknesses.append({
            "tag_name": "weak_personal_contribution",
            "category": "experience",
            "description": "프로젝트나 경험에서 본인의 역할과 구체적인 기여도가 불명확하여 주도성 확인이 어려움",
            "trigger_signal": f"실시간 LLM 컨텍스트 파인딩 결과 본인 기여도 부족 포착" + (f" ({custom_reason})" if custom_reason else "")
        })

    # P0-6. weak_evidence
    if not is_grounded:
        triggered_weaknesses.append({
            "tag_name": "weak_evidence",
            "category": "answer_quality",
            "description": "주장에 대한 근거, 사례, 수치, 결과가 부족하여 객관성이 떨어짐",
            "trigger_signal": "실무 수치 정규식 팩트 필터링 결과 누락 (is_grounded: False)"
        })

    # P0-7. weak_jd_fit
    if llm_weakness_tags and any(t.get("tag_name") == "weak_jd_fit" for t in llm_weakness_tags):
        llm_tag_meta = next(t for t in llm_weakness_tags if t.get("tag_name") == "weak_jd_fit")
        custom_reason = llm_tag_meta.get("reason", llm_tag_meta.get("description", ""))
        triggered_weaknesses.append({
            "tag_name": "weak_jd_fit",
            "category": "job_fit",
            "description": "답변이 JD 요구사항이나 지원 직무의 핵심 기술/경험 요건과 잘 연결되지 않음",
            "trigger_signal": f"실시간 LLM 컨텍스트 파인딩 결과 JD 불일치 태그 포착" + (f" ({custom_reason})" if custom_reason else "")
        })

    # P0-8. weak_problem_solving_process
    if cbi_level <= 2:
        triggered_weaknesses.append({
            "tag_name": "weak_problem_solving_process",
            "category": "experience",
            "description": "문제를 어떻게 발견하고 해결했는지 논리적 과정 설명이 장황하거나 부족함",
            "trigger_signal": f"CBI 문제해결 성숙도 분석 결과 하위 시퀀스 안착 (CBI 레벨: {cbi_level})"
        })

    # P0-9. weak_result_impact
    result_desc = bei_star.get("result", {}).get("desc", "") if bei_star else ""
    result_keywords = ["개선", "단축", "확보", "달성", "해결", "성과"]
    if bei_result_score <= 12 and not any(rk in result_desc for rk in result_keywords):
        triggered_weaknesses.append({
            "tag_name": "weak_result_impact",
            "category": "experience",
            "description": "결과, 성과, 개선 효과, 배운 점이 부족함",
            "trigger_signal": "BEI Result 점수 미달 및 성과 어휘 탐지 불가능"
        })

    # P0-10. weak_answer_structure
    if raw_word_count >= 120 and (bei_situation_score < 15 or bei_task_score < 15 or bei_action_score < 15):
        triggered_weaknesses.append({
            "tag_name": "weak_answer_structure",
            "category": "communication",
            "description": "답변의 흐름이 정리되지 않아 핵심이 잘 드러나지 않음",
            "trigger_signal": f"발화량({raw_word_count}단어) 대비 논리 뼈대 구조 점수 붕괴 현상 확인"
        })

    # P0-11. excessive_filler_words
    if is_excessive_fillers:
        triggered_weaknesses.append({
            "tag_name": "excessive_filler_words",
            "category": "speech_delivery",
            "description": "'어, 음, 그니까, 약간' 등 무의미한 필러 워드 및 추임새 빈도가 임계치를 초과함",
            "trigger_signal": f"전달력 저하 위험 임계값 포착 (필러워드 검출: {total_filler}회)"
        })

    # P0-12. frequent_long_pauses
    if long_pause_count >= 4:
        triggered_weaknesses.append({
            "tag_name": "frequent_long_pauses",
            "category": "speech_delivery",
            "description": "답변 도중 생각이 막히거나 긴장하여 3초 이상의 긴 침묵이 빈번하게 발생함",
            "trigger_signal": f"장기 휴지 빈도 초과 (건수: {long_pause_count}회)"
        })

    # P0-13. unbalanced_speech_pace
    if long_pause_count >= 2 and is_excessive_fillers:
        triggered_weaknesses.append({
            "tag_name": "unbalanced_speech_pace",
            "category": "speech_delivery",
            "description": "전체 답변 시간 대비 실제 발화하지 않은 휴지 시간 비율이 높아 답변 페이스가 무너짐",
            "trigger_signal": f"필러워드({total_filler}회) 및 침묵({long_pause_count}회) 복합 중첩 발생"
        })


    # ----------------------------------------------------
    # 🌟 [강점 태그] 안정화 루프 (★ 내부 명세 완전 고정 요구사항 충족)
    # ----------------------------------------------------
    
    # P0-1. sharp_problem_definition
    if cbi_level >= 4:
        triggered_strengths.append({
            "tag_name": "sharp_problem_definition",
            "category": "experience",
            "description": "문제 상황의 표면적 현상에 그치지 않고, 근본적인 원인을 정확히 짚어내고 가설을 세우는 역량이 탁월함",
            "trigger_signal": f"CBI 직무 역량 표준 만족 (Level: {cbi_level})"
        })

    # P0-2. data_driven_achievement
    if is_grounded and (bei_result_score >= 20):
        triggered_strengths.append({
            "tag_name": "data_driven_achievement",
            "category": "answer_quality",
            "description": "본인의 성과와 액션을 모호한 표현 없이 명확한 정량적 수치와 구체적인 지표로 입증함",
            "trigger_signal": f"Result 단락 정량 메트릭 확인 완료 (Result 스코어: {bei_result_score})"
        })

    # P0-3. deep_tech_insight
    if question_type == "technical" and tech_score >= 90:
        triggered_strengths.append({
            "tag_name": "deep_tech_insight",
            "category": "technical",
            "description": "단순 라이브러/툴 사용법을 넘어 프레임워크나 아키텍처의 내부 동작 원리까지 깊이 있게 파악하고 설명함",
            "trigger_signal": f"기술 스택 스코어 최상위 도달 (Score: {tech_score})"
        })

    # P0-4. clear_ownership_leadership
    ownership_keywords = ["내가", "제가", "주도하여", "직접", "기획하여", "책임지고", "제안해"]
    if any(kw in stt_text for kw in ownership_keywords) and bei_action_score >= 20:
        triggered_strengths.append({
            "tag_name": "clear_ownership_leadership",
            "category": "attitude",
            "description": "프로젝트 과정에서 수동적인 수행에 그치지 않고, 문제를 스스로 발굴하여 주도적으로 오너십을 발휘함",
            "trigger_signal": "오너십 액션 키워드 검출 및 BEI Action 상위권 도달"
        })

    # P0-5. top_down_delivery
    sentences = [s.strip() for s in re.split(r'[.\n]', stt_text) if s.strip()]
    intro_text = " ".join(sentences[:3]) if sentences else ""
    top_down_markers = ["결과적으로", "핵심은", "달성했습니다", "구축했습니다", "해결했습니다", "구현했습니다"]
    if any(m in intro_text for m in top_down_markers) and bei_situation_score >= 22:
        triggered_strengths.append({
            "tag_name": "top_down_delivery",
            "category": "communication",
            "description": "결론(핵심 성과나 기술 선택 결과)을 먼저 던지고 상세 근거를 붙이는 두괄식 구조를 완벽하게 구사함",
            "trigger_signal": "초반 발화 문장 구조 내 핵심 결론 선배치 구조 포착"
        })

    # P0-6. well_balanced_tradeoff
    if question_type == "technical" and (tradeoff_match_ratio >= 0.20 or bei_action_score >= 22):
        triggered_strengths.append({
            "tag_name": "well_balanced_tradeoff",
            "category": "technical",
            "description": "특정 기술이나 솔루션을 선택할 때 장점만 보지 않고, 비용이나 한계점(Trade-off)을 명확히 인지하고 조율한 경험이 드러남",
            "trigger_signal": f"의사결정 트레이드오프 어휘 사전식 분석 조건 만족 (매칭 단어수: {len(matched_tradeoff_words)}종)"
        })

    # P0-7. high_jd_alignment
    if llm_weakness_tags and any(t.get("tag_name") == "high_jd_alignment" for t in llm_weakness_tags):
        llm_tag_meta = next(t for t in llm_weakness_tags if t.get("tag_name") == "high_jd_alignment")
        custom_reason = llm_tag_meta.get("reason", llm_tag_meta.get("description", ""))
        triggered_strengths.append({
            "tag_name": "high_jd_alignment",
            "category": "job_fit",
            "description": "본인의 핵심 프로젝트 경험과 사용 스킬셋이 지원 직무(JD)에서 요구하는 요건과 매우 긴밀함",
            "trigger_signal": f"실시간 LLM 컨텍스트 파인딩 결과 JD 최적합 매칭 포착" + (f" ({custom_reason})" if custom_reason else "")
        })

    # P0-8. agile_growth_mindset
    growth_dictionary = ["배운", "깨달았습니다", "보완", "피드백", "성장", "개선점", "회고", "이후에는"]
    growth_match_count = sum(1 for word in growth_dictionary if word in stt_text)
    if growth_match_count >= 2 and bei_result_score > 20:
        triggered_strengths.append({
            "tag_name": "agile_growth_mindset",
            "category": "growth",
            "description": "실패 경험이나 프로젝트의 기술적 한계 상황에서도 배운 점을 명확히 정리하여 발전적 자산으로 삼는 태도가 보임",
            "trigger_signal": f"발전적 회고 키워드 충족 및 BEI 성과 지표 고득점 (Result: {bei_result_score}/25)"
        })

    # P0-9. fluent_speech_delivery
    if long_pause_count <= 1 and not is_excessive_fillers:
        triggered_strengths.append({
            "tag_name": "fluent_speech_delivery",
            "category": "speech_delivery",
            "description": "불필요한 필러워드 없이 차분하고 정돈된 어조와 일정한 호흡으로 말하여 청자에게 높은 신뢰감을 줌",
            "trigger_signal": f"필러워드 및 침묵 클린 패스 (Total Filler: {total_filler}회)"
        })

    # P0-10. collaborative_problem_solver
    collaboration_dictionary = ["팀원", "동료", "의견 조율", "합의점", "공유", "문서화", "싱크", "설득", "소통", "협력", "갈등"]
    collab_match_count = sum(1 for word in collaboration_dictionary if word in stt_text)
    if question_type in ["personality", "job"] and collab_match_count >= 2 and cbi_level >= 3:
        triggered_strengths.append({
            "tag_name": "collaborative_problem_solver",
            "category": "collaboration",
            "description": "팀 내 갈등이나 협업 병목 현상이 생겼을 때, 감정적 대립 대신 논리적 소통과 조율로 팀의 생산성을 이끌어냄",
            "trigger_signal": f"협업 행동 패턴 지표 다수 포착 (키워드 매칭: {collab_match_count}건)"
        })

    # P0-11. rich_context_setting
    situation_desc = bei_star.get("situation", {}).get("desc", "") if bei_star else ""
    if bei_situation_score > 20 and len(situation_desc) >= 100:
        triggered_strengths.append({
            "tag_name": "rich_context_setting",
            "category": "experience",
            "description": "프로젝트의 비즈니스적 배경, 초기 기획 목표, 당면 과제를 명확히 제시하여 답변의 몰입도를 높임",
            "trigger_signal": "Situation 컨텍스트 상세 서술 확인 완료"
        })

    # P0-12. elaborate_action_detail
    action_desc_str = bei_star.get("action", {}).get("desc", "") if bei_star else ""
    action_keywords = ["리팩토링", "구축", "구현", "최적화", "설계", "마이그레이션", "도입"]
    if bei_action_score > 20 and any(ak in action_desc_str for ak in action_keywords):
        triggered_strengths.append({
            "tag_name": "elaborate_action_detail",
            "category": "experience",
            "description": "문제 해결을 위해 자신이 직접 실행한 엔지니어링/기획적 액션을 단계별로 세밀하게 묘사함",
            "trigger_signal": "BEI Action 기술 행동 묘사 검증 통과"
        })

    # P0-13. macro_business_perspective
    business_impact_tokens = ["비용 절감", "효율성", "지연 시간", "레이턴시", "유저 피드백", "매출", "전환율"]
    if any(bit in stt_text for bit in business_impact_tokens) and bei_result_score > 20:
        triggered_strengths.append({
            "tag_name": "macro_business_perspective",
            "category": "job_fit",
            "description": "본인의 기술적 성과가 유저 지표 향상, 비용 절감 등 비즈니스적 가치(Impact)로 어떻게 연결되는지 이해하고 있음",
            "trigger_signal": "엔지니어링 결과물의 비즈니스 가치 얼라인먼트 확인"
        })

    # P0-14. solid_answer_consistency
    if not triggered_weaknesses and bei_situation_score > 20 and bei_action_score > 20:
        triggered_strengths.append({
            "tag_name": "solid_answer_consistency",
            "category": "answer_quality",
            "description": "면접 전반에 걸쳐 본인의 이력서 정보 및 이전 답변의 기술 기조와 상충되지 않는 일관된 신뢰성을 유지함",
            "trigger_signal": f"약점 제로 및 구조화 균형 통과 (Situation: {bei_situation_score}/25, Action: {bei_action_score}/25)"
        })

    # ----------------------------------------------------
    # 🤝 [중요] 실시간 꼬리질문 레이어 병합 알고리즘 유지
    # ----------------------------------------------------
    if llm_weakness_tags:
        local_tag_names = {tw["tag_name"] for tw in triggered_weaknesses}
        for l_tag in llm_weakness_tags:
            name = l_tag.get("tag_name")
            if name not in local_tag_names:
                raw_desc = l_tag.get("reason", l_tag.get("description", ""))
                triggered_weaknesses.append({
                    "tag_name": name,
                    "category": l_tag.get("category", "general"),
                    # sufficiency 체인이 영어로 반환한 경우 한국어 fallback으로 대체
                    "description": _to_korean(raw_desc, "답변에서 추가 보완이 필요한 영역이 감지되었습니다."),
                    "trigger_signal": "LLM 실시간 피드백 루프 수집"
                })

    # 💡 [핵심 패치] evaluation_services.py의 로그 파싱 및 후속 로직이 깨지지 않도록
    # 'strengths'와 'weaknesses' 키에는 기획 원안의 순수 Array 오브젝트를 100% 그대로 내려줍니다.
    return {
        "strengths": triggered_strengths,
        "weaknesses": triggered_weaknesses
    }