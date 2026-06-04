def generate_interview_questions(session):
    """Return list of question dicts for the given session (rule-based MVP).

    Each question dict contains: order_index, question_type, question_text, source_type, source_reference
    """
    questions = []
    interview_type = getattr(session, 'interview_type', 'technical')
    persona = getattr(session, 'persona', 'practical')
    count = int(getattr(session, 'total_question_count', 3) or 3)

    # simple templates by type
    if interview_type == 'technical':
        templates = [
            ("project", "프로젝트에서 본인이 맡은 역할과 주요 기여를 설명해주세요."),
            ("project", "프로젝트에서 사용한 기술 스택을 선택한 이유를 설명해주세요."),
            ("jd", "해당 직무의 핵심 요구사항을 충족시키기 위해 어떤 경험을 쌓았는지 설명해주세요."),
        ]
    elif interview_type == 'personality':
        templates = [
            ("profile", "팀에서 갈등을 해결한 경험을 이야기해 주세요."),
            ("profile", "자신의 강점과 약점을 구체적인 사례로 설명해주세요."),
            ("cover_letter", "회사와 직무에 지원한 동기를 말씀해주세요."),
        ]
    else:  # comprehensive
        templates = [
            ("project", "프로젝트에서 본인이 맡은 역할과 주요 기여를 설명해주세요."),
            ("profile", "팀에서 갈등을 해결한 경험을 이야기해 주세요."),
            ("jd", "해당 직무에서 가장 중요하다고 생각하는 역량은 무엇인가요? 구체적으로 설명해주세요."),
        ]

    # persona could tweak wording; for MVP we'll append a short persona note
    persona_note = {
        'coach': ' (코칭 톤으로 질문)',
        'practical': ' (실무 중심 질문)',
        'verifier': ' (검증형 질문)',
        'pressure': ' (압박형 질문)',
    }.get(persona, '')

    for i in range(count):
        tpl = templates[i % len(templates)]
        source, text = tpl
        q = {
            'order_index': i + 1,
            'question_type': 'main',
            'question_text': text + persona_note,
            'source_type': source,
            'source_reference': f'{source}_reference',
        }
        questions.append(q)

    return questions
