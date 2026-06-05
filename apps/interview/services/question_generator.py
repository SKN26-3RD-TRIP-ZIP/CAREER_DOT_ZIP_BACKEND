from apps.question_bank.services.question_selector import select_questions_for_session


RULE_QUESTIONS = {
    'technical': [
        ('TECH_PROJECT_ROLE', 'Describe your role and main contribution in a recent project.'),
        ('TECH_STACK_DECISION', 'Why did you choose the main technology stack used in your project?'),
        ('TECH_JD_REQUIREMENT', 'Which job requirement best matches your experience, and why?'),
    ],
    'personality': [
        ('PERSONALITY_CONFLICT', 'Describe a conflict within a team and how you resolved it.'),
        ('PERSONALITY_STRENGTH', 'Explain your main strength with a concrete example.'),
        ('PERSONALITY_MOTIVATION', 'Why are you interested in this company and role?'),
    ],
    'comprehensive': [
        ('COMPREHENSIVE_PROJECT', 'Describe your role and main contribution in a recent project.'),
        ('COMPREHENSIVE_TEAMWORK', 'Describe a conflict within a team and how you resolved it.'),
        ('COMPREHENSIVE_ROLE', 'Which competency is most important for this role, and why?'),
    ],
}


def _rule_based_questions(session, count, excluded_texts=None):
    templates = RULE_QUESTIONS.get(session.interview_type, RULE_QUESTIONS['comprehensive'])
    excluded = {text.casefold() for text in (excluded_texts or [])}
    questions = []
    template_index = 0

    while len(questions) < count:
        cycle, template_offset = divmod(template_index, len(templates))
        reference, text = templates[template_offset]
        template_index += 1
        if cycle:
            text = f'{text} Use a different example or perspective ({cycle + 1}).'
            reference = f'{reference}_{cycle + 1}'
        if text.casefold() in excluded:
            continue
        questions.append(
            {
                'question_text': text,
                'source_type': 'rule',
                'source_reference': reference,
            }
        )
        excluded.add(text.casefold())
    return questions


def generate_interview_questions(session):
    question_count = int(session.total_question_count or 3)
    selected = select_questions_for_session(session, question_count)
    selected_texts = [question['question_text'] for question in selected]

    if len(selected) < question_count:
        selected.extend(
            _rule_based_questions(
                session,
                question_count - len(selected),
                excluded_texts=selected_texts,
            )
        )

    return [
        {
            **question,
            'order_index': index,
            'question_type': 'main',
        }
        for index, question in enumerate(selected[:question_count], start=1)
    ]
