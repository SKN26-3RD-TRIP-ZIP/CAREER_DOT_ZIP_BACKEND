import json

from django.db.models import Q

from apps.input.services.talent_profile_service import resolve_effective_talent_profile
from apps.interview.services.ai_chain_service import InterviewAIChainService
from apps.interview.services.ai_chain_persona_prompts import (
    get_persona_policy,
    normalize_persona_type,
)
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


QUESTION_SOURCE_TYPE_ALIASES = {
    'jd': 'jd',
    'job_description': 'jd',
    'jobdescription': 'jd',
    'resume': 'resume',
    'cv': 'resume',
    'cover_letter': 'cover_letter',
    'coverletter': 'cover_letter',
    'self_introduction': 'cover_letter',
    'self_intro': 'cover_letter',
    'project': 'project_experience',
    'project_experience': 'project_experience',
    'combined': 'combined',
    'prepared': 'prepared_question',
    'prepared_question': 'prepared_question',
    'generated_question': 'prepared_question',
    'analysis_generated_question': 'prepared_question',
    'profile': 'profile',
    'question_bank': 'question_bank',
    'bank': 'question_bank',
    'rule': 'rule',
    'general': 'general',
}

QUESTION_CATEGORY_ALIASES = {
    'technical': 'technical',
    'tech': 'technical',
    'coding': 'technical',
    'personality': 'personality',
    'behavioral': 'personality',
    'behavioural': 'personality',
    'experience': 'personality',
    'culture': 'personality',
    'job': 'general',
    'general': 'general',
    'other': 'general',
    'main': 'general',
    'follow_up': 'general',
}

EXPECTED_TECHNICAL_KEYWORDS_LABEL = 'expected_technical_keywords'


def _normalize_question_source_type(source_type):
    normalized = str(source_type or 'general').strip().lower()
    return QUESTION_SOURCE_TYPE_ALIASES.get(normalized, 'general')


def _normalize_question_category(question_category):
    normalized = str(question_category or 'general').strip().lower()
    return QUESTION_CATEGORY_ALIASES.get(normalized, 'general')


def _question_category_plan(interview_type, question_count):
    count = max(int(question_count or 0), 0)
    if count == 0:
        return []

    if interview_type == 'technical':
        return ['technical'] * count
    if interview_type == 'personality':
        return ['personality'] * count

    technical_count = int(round(count * 0.6))
    if count > 1:
        technical_count = min(max(technical_count, 1), count - 1)
    return ['technical'] * technical_count + ['personality'] * (count - technical_count)


def _apply_question_category_plan(questions, interview_type, question_count):
    plan = _question_category_plan(interview_type, question_count)
    categorized = []

    for index, question in enumerate(questions[:question_count]):
        planned_category = plan[index] if index < len(plan) else 'general'
        categorized.append(
            {
                **question,
                'question_category': planned_category,
            }
        )

    return categorized


def _candidate_key(question_text):
    return (question_text or '').strip().casefold()


def _question_texts(questions):
    return [question.get('question_text', '') for question in questions]


def _normalize_expected_technical_keywords(value):
    if value is None:
        return ''
    if isinstance(value, (list, tuple, set)):
        return ', '.join(
            str(item).strip()
            for item in value
            if str(item).strip()
        )
    return str(value).strip()


def _extract_expected_technical_keywords(question):
    if not isinstance(question, dict):
        return ''

    for key in (
        'expected_technical_keywords',
        'technical_keywords',
        'expected_keywords',
    ):
        keywords = _normalize_expected_technical_keywords(question.get(key))
        if keywords:
            return keywords

    return ''


def _extract_analysis_expected_technical_keywords(question):
    answer = getattr(question, 'answer', None) or {}
    if not isinstance(answer, dict):
        return ''

    for key in (
        'expected_technical_keywords',
        'technical_keywords',
        'expected_keywords',
        'keywords',
    ):
        keywords = _normalize_expected_technical_keywords(answer.get(key))
        if keywords:
            return keywords

    return ''


def _with_expected_technical_keyword_tag(question):
    question_category = _normalize_question_category(question.get('question_category'))
    keywords = _normalize_expected_technical_keywords(
        question.get('expected_technical_keywords')
    )
    source_tags = list(question.get('source_tags') or [])

    if question_category != 'technical' or not keywords:
        return {
            **question,
            'source_tags': [
                tag
                for tag in source_tags
                if not (
                    isinstance(tag, dict)
                    and tag.get('source_label') == EXPECTED_TECHNICAL_KEYWORDS_LABEL
                )
            ],
        }

    has_keyword_tag = any(
        isinstance(tag, dict)
        and tag.get('source_label') == EXPECTED_TECHNICAL_KEYWORDS_LABEL
        for tag in source_tags
    )
    if has_keyword_tag:
        return {
            **question,
            'source_tags': source_tags,
        }

    return {
        **question,
        'source_tags': [
            *source_tags,
            {
                'source_type': question.get('source_type') or 'general',
                'source_label': EXPECTED_TECHNICAL_KEYWORDS_LABEL,
                'source_text_excerpt': keywords,
                'source_reference': question.get('source_reference') or '',
            },
        ],
    }


def _normalize_source_tags(source_tags, fallback_source_type='general', fallback_reference=''):
    normalized = []

    for tag in source_tags or []:
        if not isinstance(tag, dict):
            continue

        source_type = _normalize_question_source_type(tag.get('source_type') or tag.get('source'))
        source_label = tag.get('source_label') or tag.get('label') or source_type
        source_text_excerpt = tag.get('source_text_excerpt') or tag.get('basis') or ''
        source_reference = tag.get('source_reference') or tag.get('source_ref') or fallback_reference

        normalized.append(
            {
                'source_type': source_type,
                'source_label': source_label,
                'source_text_excerpt': source_text_excerpt,
                'source_reference': source_reference,
            }
        )

    if normalized:
        return normalized

    source_type = _normalize_question_source_type(fallback_source_type)
    return [
        {
            'source_type': source_type,
            'source_label': source_type,
            'source_text_excerpt': '',
            'source_reference': fallback_reference,
        }
    ]


def _metadata_text(metadata):
    return json.dumps(
        {
            key: value
            for key, value in metadata.items()
            if value not in (None, '', [], {})
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _generation_metadata_tag(generation_source, *, prompt_metadata=None, source_reference=''):
    metadata = {
        **(prompt_metadata or {}),
        'generation_source': generation_source,
    }
    return {
        'source_type': 'general',
        'source_label': 'generation_metadata',
        'source_text_excerpt': _metadata_text(metadata),
        'source_reference': source_reference,
    }


def _prompt_metadata_from_result(result):
    return {
        'generation_source': result.get('generation_source'),
        'prompt_type': result.get('prompt_type'),
        'prompt_source': result.get('prompt_source'),
        'prompt_template_id': result.get('prompt_template_id'),
        'prompt_template_name': result.get('prompt_template_name'),
        'prompt_version_id': result.get('prompt_version_id'),
        'prompt_version_label': result.get('prompt_version_label'),
        'is_active_prompt_version': result.get('is_active_prompt_version'),
    }


def _attach_generation_metadata(question, generation_source, *, prompt_metadata=None):
    source_reference = question.get('source_reference') or ''
    return {
        **question,
        'source_tags': [
            *(question.get('source_tags') or []),
            _generation_metadata_tag(
                generation_source,
                prompt_metadata=prompt_metadata,
                source_reference=source_reference,
            ),
        ],
    }


def _append_unique_questions(target, candidates, *, limit, excluded_texts=None):
    excluded = {_candidate_key(text) for text in (excluded_texts or [])}

    for question in candidates:
        if len(target) >= limit:
            break

        question_text = (question.get('question_text') or '').strip()
        key = _candidate_key(question_text)

        if not question_text or key in excluded:
            continue

        source_type = _normalize_question_source_type(question.get('source_type'))
        source_reference = question.get('source_reference') or ''
        source_tags = _normalize_source_tags(
            question.get('source_tags'),
            fallback_source_type=source_type,
            fallback_reference=source_reference,
        )

        target.append(
            {
                'question_text': question_text,
                'question_category': _normalize_question_category(
                    question.get('question_category') or question.get('question_type')
                ),
                'expected_technical_keywords': _normalize_expected_technical_keywords(
                    question.get('expected_technical_keywords')
                ),
                'source_type': source_type,
                'source_reference': source_reference,
                'difficulty': question.get('difficulty') or 'medium',
                'source_tags': source_tags,
            }
        )
        excluded.add(key)

    return target


def _rule_based_questions(session, count, excluded_texts=None):
    templates = RULE_QUESTIONS.get(session.interview_type, RULE_QUESTIONS['comprehensive'])
    excluded = {_candidate_key(text) for text in (excluded_texts or [])}
    questions = []
    template_index = 0

    while len(questions) < count:
        cycle, template_offset = divmod(template_index, len(templates))
        reference, text = templates[template_offset]
        template_index += 1

        if cycle:
            text = f'{text} Use a different example or perspective ({cycle + 1}).'
            reference = f'{reference}_{cycle + 1}'

        if _candidate_key(text) in excluded:
            continue

        questions.append(
            _attach_generation_metadata(
                {
                    'question_text': text,
                    'question_category': _normalize_question_category(session.interview_type),
                    'source_type': 'rule',
                    'source_reference': reference,
                    'difficulty': 'medium',
                    'source_tags': [
                        {
                            'source_type': 'rule',
                            'source_label': 'Rule fallback',
                            'source_text_excerpt': reference,
                            'source_reference': reference,
                        }
                    ],
                },
                'rule_fallback',
            )
        )
        excluded.add(_candidate_key(text))

    return questions


def _build_user_profile(session):
    profile = getattr(session.user, 'profile', None)
    if not profile:
        return {}

    return {
        'career_type': getattr(profile, 'career_type', None),
        'major_type': getattr(profile, 'major_type', None),
        'desired_job': getattr(profile, 'desired_job', None),
        'career_year': getattr(profile, 'career_year', None),
        'github_url': getattr(profile, 'github_url', None),
    }


def _build_job_description_source(session):
    jd = session.jd
    if not jd:
        return None
    effective_talent_profile = resolve_effective_talent_profile(jd)

    return {
        'source_table': 'job_descriptions',
        'jd_id': str(jd.id),
        'company_name': jd.company_name,
        'position': jd.position,
        'original_text': jd.original_text,
        'company_summary': jd.company_summary,
        'talent_profile': jd.talent_profile,
        'effective_talent_profile': effective_talent_profile,
        'talent_profile_prompt_notice': effective_talent_profile.get('prompt_notice', ''),
        'job_requirements': jd.job_requirements,
        'keywords': jd.keywords,
    }


def _build_resume_source(session):
    resume = session.resume
    if not resume:
        return None

    return {
        'source_table': 'resume_master',
        'resume_id': str(resume.id),
        'name': resume.name,
        'email': resume.email,
        'github_url': resume.github_url,
        'original_text': resume.original_text,
        'extracted_keywords': resume.extracted_keywords,
        'skills': [
            {
                'skill_name': skill.name,
                'category': None,
                'level': None,
            }
            for skill in resume.skills.all()
        ],
        'careers': [
            {
                'company_name': career.company_name,
                'position': career.position,
                'start_date': career.start_date,
                'end_date': career.end_date,
                'is_current': career.is_current,
                'description': career.description,
            }
            for career in resume.careers.all()
        ],
        'education': [
            {
                'school_name': education.school_name,
                'major': education.major,
                'degree': education.degree,
                'status': education.status,
                'start_date': education.start_date,
                'end_date': education.end_date,
            }
            for education in resume.education.all()
        ],
        'certificates': [
            {
                'name': certificate.name,
                'issued_by': certificate.issued_by,
                'issued_at': certificate.issued_at,
            }
            for certificate in resume.certificates.all()
        ],
    }


def _build_cover_letter_source(session):
    cover_letter = session.cover_letter
    if not cover_letter:
        return None

    return {
        'source_table': 'cover_letters',
        'cover_letter_id': str(cover_letter.id),
        'title': cover_letter.title,
        'company_name': cover_letter.company_name,
        'items': [
            {
                'source_table': 'cover_letter_items',
                'cover_letter_item_id': str(item.id),
                'question': item.question,
                'answer_text': item.answer_text,
                'order_index': item.order_index,
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
            'start_date': project.start_date,
            'end_date': project.end_date,
        }
        for project in session.user.projects.all()
    ]


def _get_latest_jd_analysis(session):
    requested_jd_analysis_id = getattr(session, '_jd_analysis_id', None)

    if not session.jd_id or not session.resume_id:
        if not requested_jd_analysis_id:
            return None

    try:
        from apps.analysis.models import JdAnalysis
    except Exception:
        return None

    if requested_jd_analysis_id:
        return (
            JdAnalysis.objects.filter(
                id=requested_jd_analysis_id,
                user=session.user,
            )
            .select_related('jd', 'resume', 'cover_letter')
            .first()
        )

    queryset = JdAnalysis.objects.filter(
        user=session.user,
        jd=session.jd,
        resume=session.resume,
    )

    if session.cover_letter_id:
        cover_letter_matched = queryset.filter(cover_letter=session.cover_letter).order_by('-analyzed_at').first()
        if cover_letter_matched:
            return cover_letter_matched

    return queryset.order_by('-analyzed_at').first()


def _get_prepared_questions(session):
    jd_analysis = _get_latest_jd_analysis(session)
    if not jd_analysis:
        return []

    return list(jd_analysis.questions.all().order_by('order', 'created_at'))


def _build_prepared_question_sources(session):
    prepared_questions = _get_prepared_questions(session)

    return [
        {
            'source_table': 'analysis_generated_question',
            'generated_question_id': str(question.id),
            'question_type': question.question_type,
            'question_category': _normalize_question_category(question.question_type),
            'question_text': question.question_text,
            'source': question.source,
            'source_ref': question.source_ref,
            'answer': question.answer,
            'expected_technical_keywords': _extract_analysis_expected_technical_keywords(question),
            'order': question.order,
        }
        for question in prepared_questions
    ]


def _build_jd_analysis_source(session):
    jd_analysis = _get_latest_jd_analysis(session)
    if not jd_analysis:
        return None

    return {
        'source_table': 'jd_analysis',
        'jd_analysis_id': str(jd_analysis.id),
        'match_score': jd_analysis.match_score,
        'tech_score': jd_analysis.tech_score,
        'trait_score': jd_analysis.trait_score,
        'matched_keywords': jd_analysis.matched_keywords,
        'unmatched_keywords': jd_analysis.unmatched_keywords,
        'jd_keywords': jd_analysis.jd_keywords,
        'resume_analysis': jd_analysis.resume_analysis,
        'strengths': jd_analysis.strengths,
        'weaknesses': jd_analysis.weaknesses,
        'cl_points': jd_analysis.cl_points,
        'analyzed_at': jd_analysis.analyzed_at.isoformat() if jd_analysis.analyzed_at else None,
    }


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

    jd_analysis = _build_jd_analysis_source(session)
    if jd_analysis:
        input_sources['jd_analysis'] = jd_analysis

    prepared_questions = _build_prepared_question_sources(session)
    if prepared_questions:
        input_sources['prepared_questions'] = prepared_questions

    return input_sources


def _build_ai_generation_payload(session, question_count, prompt_version_id=None):
    input_sources = _build_ai_input_sources(session)

    return {
        'session_id': str(session.id),
        'user_context': {
            'user_id': str(session.user_id),
            'source': 'server',
        },
        'persona': {
            'persona_id': None,
            'persona_type': _map_persona_type(session.persona),
            'name': session.persona,
            'description': '',
            'policy': get_persona_policy(session.persona),
        },
        'prompt_version_id': prompt_version_id,
        'user_profile': _build_user_profile(session),
        'input_sources': input_sources,
        'generation_options': {
            'question_count': question_count,
            'interview_type': session.interview_type,
            'question_category_plan': _question_category_plan(
                session.interview_type,
                question_count,
            ),
            'allow_multiple_source_tags': True,
            'include_source_text_excerpt': True,
            'prefer_input_sources': bool(input_sources),
            'use_prepared_questions_as_reference': bool(input_sources.get('prepared_questions')),
        },
    }


def _map_persona_type(persona):
    return normalize_persona_type(persona)


def _convert_ai_questions(ai_questions, excluded_texts=None, result_metadata=None):
    excluded = {_candidate_key(text) for text in (excluded_texts or [])}
    converted = []

    for question in ai_questions:
        question_text = (question.get('question_text') or '').strip()
        key = _candidate_key(question_text)

        if not question_text or key in excluded:
            continue

        source_tags = _normalize_source_tags(question.get('source_tags'))
        first_source = source_tags[0] if source_tags else {}
        source_type = _normalize_question_source_type(first_source.get('source_type') or 'general')
        source_reference = _build_ai_source_reference(question, source_tags)

        generation_source = (result_metadata or {}).get('generation_source') or 'unknown_ai'
        converted.append(
            {
                'question_text': question_text,
                'question_category': _normalize_question_category(
                    question.get('question_category') or question.get('question_type')
                ),
                'expected_technical_keywords': _extract_expected_technical_keywords(question),
                'source_type': source_type,
                'source_reference': source_reference,
                'difficulty': question.get('difficulty') or 'medium',
                'source_tags': [
                    *source_tags,
                    _generation_metadata_tag(
                        generation_source,
                        prompt_metadata=result_metadata,
                        source_reference=source_reference,
                    ),
                ],
            }
        )
        excluded.add(key)

    return converted


def _build_ai_source_reference(question, source_tags):
    client_key = question.get('client_question_key') or 'unknown'
    source_types = [
        _normalize_question_source_type(tag.get('source_type'))
        for tag in source_tags
        if isinstance(tag, dict) and tag.get('source_type')
    ]
    source_type_part = ','.join(source_types) if source_types else 'unknown'
    return f'ai_chain:{client_key}:{source_type_part}'


def _ai_chain_questions(session, count, excluded_texts=None, prompt_version_id=None):
    if count <= 0:
        return []

    service = InterviewAIChainService()
    payload = _build_ai_generation_payload(session, count, prompt_version_id)
    result = service.generate_questions(payload)
    result_metadata = {
        **_prompt_metadata_from_result(result),
        'persona': payload.get('persona', {}).get('persona_type'),
    }

    return _convert_ai_questions(
        result.get('questions') or [],
        excluded_texts=excluded_texts,
        result_metadata=result_metadata,
    )[:count]


def _prepared_questions(session, count, excluded_texts=None):
    if count <= 0:
        return []

    converted = []
    for question in _get_prepared_questions(session):
        source_type = _normalize_question_source_type(question.source)
        source_reference = f'analysis_generated_question:{question.id}'
        converted.append(
            _attach_generation_metadata(
                {
                    'question_text': question.question_text,
                    'question_category': _normalize_question_category(question.question_type),
                    'expected_technical_keywords': _extract_analysis_expected_technical_keywords(question),
                    'source_type': source_type,
                    'source_reference': source_reference,
                    'difficulty': 'medium',
                    'source_tags': [
                        {
                            'source_type': source_type,
                            'source_label': '준비 질문 근거',
                            'source_text_excerpt': question.source_ref,
                            'source_reference': source_reference,
                        },
                        {
                            'source_type': 'prepared_question',
                            'source_label': '분석 단계 생성 질문',
                            'source_text_excerpt': question.question_text,
                            'source_reference': source_reference,
                        },
                    ],
                },
                'prepared_question',
            )
        )

    selected = []
    _append_unique_questions(
        selected,
        converted,
        limit=count,
        excluded_texts=excluded_texts,
    )
    return selected


def _question_bank_questions(session, count, excluded_texts=None):
    if count <= 0:
        return []

    selected = select_questions_for_session(session, count)
    normalized = []

    _append_unique_questions(
        normalized,
        selected,
        limit=count,
        excluded_texts=excluded_texts,
    )
    return [
        _attach_generation_metadata(question, 'question_bank')
        for question in normalized
    ]


def generate_interview_questions(session, prompt_version_id=None):
    question_count = int(session.total_question_count or 3)
    input_sources = _build_ai_input_sources(session)

    selected = []

    if input_sources:
        ai_questions = _ai_chain_questions(
            session,
            question_count,
            prompt_version_id=prompt_version_id,
        )
        _append_unique_questions(
            selected,
            ai_questions,
            limit=question_count,
        )

    if len(selected) < question_count:
        prepared = _prepared_questions(
            session,
            question_count - len(selected),
            excluded_texts=_question_texts(selected),
        )
        _append_unique_questions(
            selected,
            prepared,
            limit=question_count,
            excluded_texts=_question_texts(selected),
        )

    if len(selected) < question_count:
        bank_questions = _question_bank_questions(
            session,
            question_count - len(selected),
            excluded_texts=_question_texts(selected),
        )
        _append_unique_questions(
            selected,
            bank_questions,
            limit=question_count,
            excluded_texts=_question_texts(selected),
        )

    if len(selected) < question_count and not input_sources:
        ai_questions = _ai_chain_questions(
            session,
            question_count - len(selected),
            excluded_texts=_question_texts(selected),
            prompt_version_id=prompt_version_id,
        )
        _append_unique_questions(
            selected,
            ai_questions,
            limit=question_count,
            excluded_texts=_question_texts(selected),
        )

    if len(selected) < question_count:
        rule_questions = _rule_based_questions(
            session,
            question_count - len(selected),
            excluded_texts=_question_texts(selected),
        )
        _append_unique_questions(
            selected,
            rule_questions,
            limit=question_count,
            excluded_texts=_question_texts(selected),
        )

    categorized = _apply_question_category_plan(
        selected,
        session.interview_type,
        question_count,
    )

    return [
        _with_expected_technical_keyword_tag({
            **question,
            'source_type': _normalize_question_source_type(question.get('source_type')),
            'order_index': index,
            'question_type': 'main',
            'question_category': _normalize_question_category(question.get('question_category')),
        })
        for index, question in enumerate(categorized, start=1)
    ]
