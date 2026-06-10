from apps.interview.services.ai_chain_service import InterviewAIChainService
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


def _build_user_profile(session):
    profile = getattr(session.user, 'profile', None)
    if not profile:
        return {}

    return {
        'career_type': getattr(profile, 'career_type', None),
        'major_type': getattr(profile, 'major_type', None),
        'desired_job': getattr(profile, 'desired_job', None),
    }


def _build_job_description_source(session):
    jd = session.jd
    if not jd:
        return None

    return {
        'source_table': 'job_descriptions',
        'jd_id': str(jd.id),
        'company_name': jd.company_name,
        'position': jd.position,
        'original_text': jd.original_text,
        'company_summary': jd.company_summary,
        'talent_profile': jd.talent_profile,
        'job_requirements': jd.job_requirements,
        'keywords': jd.keywords,
    }


def _build_resume_source(session):
    resume = session.resume
    if not resume:
        return None

    skills = [
        {
            'skill_name': skill.name,
            'category': None,
            'level': None,
        }
        for skill in resume.skills.all()
    ]

    careers = [
        {
            'company_name': career.company_name,
            'position': career.position,
            'description': career.description,
        }
        for career in resume.careers.all()
    ]

    certificates = [
        {
            'name': certificate.name,
            'issued_by': certificate.issued_by,
            'issued_at': certificate.issued_at,
        }
        for certificate in resume.certificates.all()
    ]

    return {
        'source_table': 'resume_master',
        'resume_id': str(resume.id),
        'original_text': resume.original_text,
        'extracted_keywords': resume.extracted_keywords,
        'skills': skills,
        'projects': [],
        'careers': careers,
        'certificates': certificates,
    }


def _build_cover_letter_source(session):
    cover_letter = session.cover_letter
    if not cover_letter:
        return None

    return {
        'source_table': 'cover_letters',
        'cover_letter_id': str(cover_letter.id),
        'items': [
            {
                'source_table': 'cover_letter_items',
                'cover_letter_item_id': str(item.id),
                'question': item.question,
                'answer_text': item.answer_text,
            }
            for item in cover_letter.items.all()
        ],
    }


def _build_project_experience_sources(session):
    return [
        {
            'source_table': 'project_experiences',
            'project_id': str(project.id),
            'project_name': project.project_name,
            'description': project.description,
            'contribution': project.contribution,
            'tech_stack': project.tech_stack,
            'github_url': project.github_url,
        }
        for project in session.user.projects.all()
    ]


def _build_ai_input_sources(session):
    input_sources = {}

    job_description = _build_job_description_source(session)
    if job_description:
        input_sources['job_description'] = job_description

    resume = _build_resume_source(session)
    if resume:
        input_sources['resume'] = resume

    cover_letter = _build_cover_letter_source(session)
    if cover_letter:
        input_sources['cover_letter'] = cover_letter

    project_experiences = _build_project_experience_sources(session)
    if project_experiences:
        input_sources['project_experiences'] = project_experiences

    return input_sources


def _build_ai_generation_payload(session, question_count):
    return {
        'session_id': str(session.id),
        'user_context': {
            'user_id': session.user_id,
            'source': 'server',
        },
        'persona': {
            'persona_id': None,
            'persona_type': _map_persona_type(session.persona),
            'name': session.persona,
            'description': '',
        },
        'prompt_version_id': None,
        'user_profile': _build_user_profile(session),
        'input_sources': _build_ai_input_sources(session),
        'generation_options': {
            'question_count': question_count,
            'allow_multiple_source_tags': True,
            'include_source_text_excerpt': True,
        },
    }


def _map_persona_type(persona):
    if persona == 'verifier':
        return 'verify'
    if persona in {'coach', 'practical', 'verify'}:
        return persona
    return 'practical'


def _convert_ai_questions(ai_questions, excluded_texts=None):
    excluded = {text.casefold() for text in (excluded_texts or [])}
    converted = []

    for question in ai_questions:
        question_text = (question.get('question_text') or '').strip()
        if not question_text:
            continue
        if question_text.casefold() in excluded:
            continue

        source_tags = question.get('source_tags') or []
        first_source = source_tags[0] if source_tags else {}
        source_type = first_source.get('source_type') or 'general'
        source_reference = _build_ai_source_reference(question, source_tags)

        converted.append(
            {
                'question_text': question_text,
                'source_type': source_type,
                'source_reference': source_reference,
            }
        )
        excluded.add(question_text.casefold())

    return converted


def _build_ai_source_reference(question, source_tags):
    client_key = question.get('client_question_key') or 'unknown'
    source_types = [
        tag.get('source_type')
        for tag in source_tags
        if tag.get('source_type')
    ]
    source_type_part = ','.join(source_types) if source_types else 'unknown'
    return f'ai_chain_mock:{client_key}:{source_type_part}'


def _ai_chain_questions(session, count, excluded_texts=None):
    if count <= 0:
        return []

    service = InterviewAIChainService()
    payload = _build_ai_generation_payload(session, count)
    result = service.generate_questions(payload)
    return _convert_ai_questions(
        result.get('questions') or [],
        excluded_texts=excluded_texts,
    )[:count]


def generate_interview_questions(session):
    question_count = int(session.total_question_count or 3)

    selected = select_questions_for_session(session, question_count)
    selected_texts = [question['question_text'] for question in selected]

    if len(selected) < question_count:
        ai_questions = _ai_chain_questions(
            session,
            question_count - len(selected),
            excluded_texts=selected_texts,
        )
        selected.extend(ai_questions)
        selected_texts.extend(question['question_text'] for question in ai_questions)

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
