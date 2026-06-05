from apps.question_bank.models import QuestionBankItem


def get_question_candidates(
    jd_keywords: list[str] | None = None,
    resume_skills: list[str] | None = None,
    question_types: list[str] | None = None,
    difficulty: str | None = None,
    limit: int = 20,
) -> list[dict]:
    queryset = QuestionBankItem.objects.filter(is_active=True, job_category='ICT')
    if question_types:
        queryset = queryset.filter(question_type__in=question_types)
    if difficulty:
        queryset = queryset.filter(difficulty=difficulty)

    match_keywords = {
        str(keyword).strip().lower()
        for keyword in (jd_keywords or []) + (resume_skills or [])
        if str(keyword).strip()
    }
    scored_items = []
    for item in queryset:
        item_keywords = {
            str(keyword).strip().lower()
            for keyword in item.keywords
            if str(keyword).strip()
        }
        scored_items.append((len(match_keywords & item_keywords), item))

    scored_items.sort(
        key=lambda entry: (
            -entry[0],
            -entry[1].created_at.timestamp(),
            str(entry[1].id),
        )
    )
    safe_limit = max(int(limit), 0)

    # TODO: Connect InterviewSession -> JD keywords -> resume skills -> candidates
    # and pass candidates with JD/resume context to GPT before saving questions.
    return [
        {
            'question_bank_id': str(item.id),
            'question_text': item.question_text,
            'answer_example': item.answer_example,
            'question_type': item.question_type,
            'difficulty': item.difficulty,
            'keywords': item.keywords,
            'source': item.source,
            'match_score': score,
        }
        for score, item in scored_items[:safe_limit]
    ]
