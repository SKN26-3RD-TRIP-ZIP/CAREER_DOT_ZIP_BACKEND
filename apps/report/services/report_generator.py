def generate_final_report(session):
    """Generate a rule-based final report summary for a session."""
    questions = list(session.questions.all())
    answers = list(session.answers.all())
    evaluated_answers = [answer for answer in answers if hasattr(answer, 'evaluation')]

    overall_score = 0
    final_scores = [answer.evaluation.final_tech_score for answer in evaluated_answers if getattr(answer.evaluation, 'final_tech_score', None) is not None]
    if final_scores:
        overall_score = round(sum(final_scores) / len(final_scores))
    else:
        llm_scores = [answer.evaluation.llm_concept_score for answer in evaluated_answers if getattr(answer.evaluation, 'llm_concept_score', None) is not None]
        if llm_scores:
            overall_score = round(sum(llm_scores) / len(llm_scores))

    strengths = []
    weaknesses = []
    recommendations = []
    summary_parts = []

    if evaluated_answers:
        strengths.append('평가된 답변이 있어 결과가 보다 신뢰성 있게 도출되었습니다.')
        summary_parts.append('평가된 답변 기반으로 리포트가 생성되었습니다.')
    else:
        summary_parts.append('평가된 답변이 없어 기본적인 결과만 제공됩니다.')

    if answers:
        strengths.append('답변이 모두 작성되어 세션 분석이 가능합니다.')
    if questions and not answers:
        weaknesses.append('답변이 아직 작성되지 않은 질문이 있습니다.')

    if overall_score >= 80:
        strengths.append('전반적으로 강점이 돋보입니다.')
    elif overall_score >= 60:
        weaknesses.append('일부 답변에서 개선 여지가 있습니다.')
        recommendations.append('핵심 문항에 대한 답변을 조금 더 구체화하세요.')
    else:
        weaknesses.append('전반적인 답변 완성도가 낮습니다.')
        recommendations.append('핵심 질문에 대해 사례 중심으로 답변을 다시 구성해 보세요.')

    if evaluated_answers and any(getattr(answer.evaluation, 'final_tech_score', 0) < 60 for answer in evaluated_answers):
        recommendations.append('기술적 세부 사항을 보완해 주세요.')

    if not strengths:
        strengths.append('리포트 생성 기준을 충족했습니다.')
    if not recommendations:
        recommendations.append('추가적으로 답변 요약을 점검해 보세요.')

    summary = ' '.join(summary_parts)
    if not summary:
        summary = '세션 데이터 기반으로 최종 리포트가 생성되었습니다.'

    raw_data = {
        'question_count': len(questions),
        'answer_count': len(answers),
        'evaluated_answer_count': len(evaluated_answers),
        'supported_scores': {
            'final_tech_scores': final_scores,
            'llm_concept_scores': [answer.evaluation.llm_concept_score for answer in evaluated_answers if getattr(answer.evaluation, 'llm_concept_score', None) is not None],
        },
    }

    return {
        'overall_score': overall_score,
        'summary': summary,
        'strengths': strengths,
        'weaknesses': weaknesses,
        'recommendations': recommendations,
        'question_count': len(questions),
        'answer_count': len(answers),
        'evaluated_answer_count': len(evaluated_answers),
        'raw_data': raw_data,
    }
