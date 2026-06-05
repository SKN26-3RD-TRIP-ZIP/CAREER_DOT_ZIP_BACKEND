import json
import re

from apps.question_bank.services.keyword_extractor import extract_keywords
from apps.question_bank.services.question_bank_service import get_question_candidates


def _normalize_keywords(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(keyword).strip() for keyword in value if str(keyword).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(keyword).strip() for keyword in parsed if str(keyword).strip()]
        return [
            keyword.strip()
            for keyword in re.split(r'[,|;\n]+', value)
            if keyword.strip()
        ]
    return []


def select_questions_from_bank(
    jd_keywords,
    interview_type,
    question_count,
    resume_skills=None,
):
    question_types = {
        'technical': ['technical'],
        'personality': ['personality'],
        'comprehensive': ['technical', 'personality', 'job'],
    }.get(interview_type)
    candidates = get_question_candidates(
        jd_keywords=jd_keywords,
        resume_skills=resume_skills,
        question_types=question_types,
        limit=question_count,
    )

    selected = []
    seen = set()
    for candidate in candidates:
        question_text = candidate['question_text'].strip()
        normalized_text = question_text.casefold()
        if not question_text or normalized_text in seen:
            continue
        seen.add(normalized_text)
        selected.append(
            {
                'question_text': question_text,
                'source_type': 'question_bank',
                'source_reference': f"{candidate['source']}:{candidate['question_bank_id']}",
            }
        )
        if len(selected) >= question_count:
            break
    return selected


def select_questions_for_session(session, question_count):
    jd = session.jd
    if jd is None:
        return []

    jd_keywords = _normalize_keywords(jd.keywords)
    jd_context = ' '.join(
        value
        for value in (
            jd.position,
            jd.original_text,
            jd.job_requirements,
        )
        if value
    )
    jd_keywords.extend(extract_keywords(jd_context))

    resume_skills = []
    if session.resume_id:
        resume_skills.extend(
            session.resume.skills.values_list('name', flat=True)
        )
        resume_skills.extend(_normalize_keywords(session.resume.extracted_keywords))
        resume_skills.extend(extract_keywords(session.resume.original_text or ''))

    return select_questions_from_bank(
        jd_keywords=list(dict.fromkeys(jd_keywords)),
        resume_skills=list(dict.fromkeys(resume_skills)),
        interview_type=session.interview_type,
        question_count=question_count,
    )
