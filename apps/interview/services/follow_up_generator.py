def generate_follow_up_questions(answer):
    """Simple rule-based generator for follow-up questions (MVP).

    Returns a list of dicts with keys: question_type, question_text, source_type, source_reference
    """
    questions = []

    # Prefer weakness tags if present
    try:
        weakness_mappings = answer.weakness_mappings.all()
    except Exception:
        weakness_mappings = []

    if weakness_mappings:
        wm = weakness_mappings[0]
        tag = wm.weakness_tag.tag_name if wm.weakness_tag else 'weakness'
        question_text = f"{tag} 관련하여 구체적으로 어떤 부분에서 어려움을 겪으셨나요? 자세히 설명해 주세요."
        questions.append({
            'question_type': 'follow_up',
            'question_text': question_text,
            'source_type': 'evaluation',
            'source_reference': tag.upper(),
        })
        return questions

    # If evaluation exists, use score hints
    eval = getattr(answer, 'evaluation', None)
    if eval:
        if eval.final_tech_score is not None and eval.final_tech_score < 60:
            question_text = '기술적 깊이(technical depth)를 보완하기 위해 어떤 자료나 경험을 추가로 참고하셨나요?'
            questions.append({
                'question_type': 'follow_up',
                'question_text': question_text,
                'source_type': 'evaluation',
                'source_reference': 'TECH_DEPTH_LOW',
            })
            return questions

    # Fallback: base on answer length
    ans_text = (answer.answer_text or '').strip()
    if len(ans_text.split()) < 20:
        question_text = '답변을 조금 더 구체적으로 확장해 주실 수 있나요? 주요 상황과 결과를 포함해 설명해 주세요.'
    else:
        question_text = '설계한 접근 방식의 한계나 고려하지 못한 리스크가 있었나요? 구체적으로 알려주세요.'

    questions.append({
        'question_type': 'follow_up',
        'question_text': question_text,
        'source_type': 'evaluation' if eval else 'general',
        'source_reference': 'AUTO' if not eval else 'AUTO_EVAL',
    })

    return questions
