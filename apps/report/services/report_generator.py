from collections import Counter
from django.db.models import Prefetch

def get_score(value):
    if isinstance(value, dict):
        return value.get("score", 0)
    return value or 0

def generate_final_report(session):
    """
    Generate a data-driven final report summary for a session
    by aggregating evaluated answer tags (Top 5 & Most Common) 
    AND performing Filler Words diagnostics & Detailed Statistics.
    """
    # 💡 N+1 쿼리 방지 최적화: evaluation 데이터 및 매핑 태그 미리 로드
    answers = session.answers.all().select_related('evaluation').prefetch_related(
        'strength_mappings__strength_tag',
        'weakness_mappings__weakness_tag'
    )
    
    questions = list(session.questions.all())
    answers_list = list(answers)
    evaluated_answers = [ans for ans in answers_list if hasattr(ans, 'evaluation') and ans.evaluation is not None]

    # 1. 종합 점수(Overall Score) 산출
    overall_score = 0
    final_scores = [
        ans.evaluation.final_tech_score 
        for ans in evaluated_answers 
        if getattr(ans.evaluation, 'final_tech_score', None) is not None
    ]
    if final_scores:
        overall_score = round(sum(final_scores) / len(final_scores))
    else:
        llm_scores = [
            ans.evaluation.llm_concept_score 
            for ans in evaluated_answers 
            if getattr(ans.evaluation, 'llm_concept_score', None) is not None
        ]
        if llm_scores:
            overall_score = round(sum(llm_scores) / len(llm_scores))

    strengths = []
    weaknesses = []
    recommendations = []
    summary_parts = []

    # 2. 강점/약점 태그 집계 및 빈도수 추출
    strength_counter = Counter()
    weakness_counter = Counter()

    # 💡 통계 계산용 변수 초기화 (BEI, CBI)
    bei_situations = []
    bei_tasks = []
    bei_actions = []
    bei_results = []
    cbi_levels = []
    cbi_scores = []

    for ans in evaluated_answers:
        eval_obj = ans.evaluation
        
        # 태그 카운트 수집
        for sm in ans.strength_mappings.all():
            strength_counter[sm.strength_tag.tag_name] += 1
        for wm in ans.weakness_mappings.all():
            weakness_counter[wm.weakness_tag.tag_name] += 1

        # BEI 상세 데이터 추출
        bei = eval_obj.bei_score if isinstance(eval_obj.bei_score, dict) else {}
        bei_situations.append(get_score(bei.get("situation")))
        bei_tasks.append(get_score(bei.get("task")))
        bei_actions.append(get_score(bei.get("action")))
        bei_results.append(get_score(bei.get("result")))

        # CBI 상세 데이터 추출
        cbi = eval_obj.cbi_score if isinstance(eval_obj.cbi_score, dict) else {}
        if "assigned_level" in cbi:
            cbi_levels.append(cbi["assigned_level"])
        elif "level" in cbi:
            cbi_levels.append(cbi["level"])

        if "score" in cbi:
            cbi_scores.append(cbi["score"])

    # 상위 최대 5개 태그 추출 및 최상위 1개 강조 분석 로직
    top_5_strengths = [item[0] for item in strength_counter.most_common(5)]
    top_5_weaknesses = [item[0] for item in weakness_counter.most_common(5)]

    # 리스트 변수에 상위 5개 태그 기본 주입 (Serializers 및 DB 저장용)
    strengths = top_5_strengths if top_5_strengths else []
    weaknesses = top_5_weaknesses if top_5_weaknesses else []

    # 요약 및 분석 코멘트에 최상위(Most Common) 1개 태그 반영
    if strength_counter:
        most_common_strength = strength_counter.most_common(1)[0][0]
        summary_parts.append(f"이번 세션에서 가장 강력하게 발휘된 역량은 [{most_common_strength}] 입니다.")
    if weakness_counter:
        most_common_weakness = weakness_counter.most_common(1)[0][0]
        summary_parts.append(f"가장 빈번하게 노출된 보완점은 [{most_common_weakness}] 항목으로 확인됩니다.")

    # 3. 비유창성(Filler Words) 종합 진단 및 동적 추천사 레이어
    total_filler_count = 0
    global_filler_words_counter = Counter()
    
    for ans in evaluated_answers:
        filler_data = getattr(ans.evaluation, 'filler_words', {})
        if filler_data and isinstance(filler_data, dict):
            total_filler_count += filler_data.get('total', 0)
            counts = filler_data.get('counts', {})
            if isinstance(counts, dict):
                for word, cnt in counts.items():
                    global_filler_words_counter[word] += cnt

    avg_fillers_per_answer = 0
    if evaluated_answers:
        avg_fillers_per_answer = total_filler_count / len(evaluated_answers)

    if total_filler_count > 0:
        most_common_fillers = [word for word, count in global_filler_words_counter.most_common(2)]
        filler_str = ", ".join([f"'{w}'" for w in most_common_fillers])
        
        summary_parts.append(f"전체 면접 중 총 {total_filler_count}회의 습관어가 감지되었습니다.")
        
        if avg_fillers_per_answer >= 3.0:
            recommendations.append(
                f"현재 답변 과정에서 {filler_str} 등의 비유창성 표현을 과도하게 반복하는 경향이 있습니다. "
                f"문장을 음성으로 억지로 이어 붙이기보다는, 생각을 정리할 때 1~2초간 의도적인 침묵(Pause)을 두는 연습을 권장합니다."
            )
        else:
            summary_parts.append("전반적으로 불필요한 추임새 없이 깔끔한 톤으로 답변을 전개했습니다.")
            recommendations.append(
                f"주로 감지되는 표현은 {filler_str} 입니다. 안정적인 발화를 유지하고 있으나 실전 긴장 상황에서도 이 페이스를 유지하도록 유의하세요."
            )
    else:
        summary_parts.append("비유창성 언어가 전혀 발견되지 않은 정제된 발화 습관을 보여주었습니다.")

    # 4. 방어 코드 (데이터가 아예 비어있을 경우 프론트엔드 UI 깨짐 방지)
    if not strengths:
        strengths.append('리포트 생성 기본 요건을 충족했습니다.')
    if not weaknesses and len(answers_list) < 3:
        weaknesses.append('전반적인 답변 구조의 일관성 확인이 필요합니다.')
    if not recommendations:
        recommendations.append('추가적으로 세션 상세 답변의 꼬리질문 분석 내용을 점검해 보세요.')

    summary = ' '.join(summary_parts)
    if not summary:
        summary = '세션 데이터 기반으로 최종 리포트가 생성되었습니다.'

    # 5. BEI / CBI 통계 집계 및 계산 처리
    n = len(evaluated_answers)
    detailed_stats = {}
    if n > 0:
        avg_sit = round(sum(bei_situations) / n, 1)
        avg_tsk = round(sum(bei_tasks) / n, 1)
        avg_act = round(sum(bei_actions) / n, 1)
        avg_res = round(sum(bei_results) / n, 1)
        
        detailed_stats = {
            "bei_metrics": {
                "averages": {
                    "situation": avg_sit,
                    "task": avg_tsk,
                    "action": avg_act,
                    "result": avg_res
                },
                "element_total_avg": round((avg_sit + avg_tsk + avg_act + avg_res), 1),
                "raw_scores": {
                    "situation": bei_situations,
                    "task": bei_tasks,
                    "action": bei_actions,
                    "result": bei_results
                }
            },
            "cbi_metrics": {
                "average_level": round(sum(cbi_levels) / len(cbi_levels), 1) if cbi_levels else 0,
                "average_score": round(sum(cbi_scores) / len(cbi_scores), 1) if cbi_scores else 0,
                "raw_levels": cbi_levels,
                "raw_scores": cbi_scores
            }
        }

    tech_avg = round(sum(final_scores) / len(final_scores), 1) if final_scores else 0

    standard_summary = {
        "evaluation_metadata": {
            "session_id": str(session.id),
            "persona_type": session.persona,
            "interview_mode": session.interview_mode,
            "question_count": len(questions),
            "answer_count": len(answers_list),
            "evaluated_answer_count": n,
        },
        "score_summary": {
            "overall_score": overall_score,
            "bei_avg": detailed_stats.get("bei_metrics", {}).get("element_total_avg", 0),
            "cbi_avg": detailed_stats.get("cbi_metrics", {}).get("average_score", 0),
            "tech_avg": tech_avg,
        },
        "score_detail": {
            "strength": strengths,
            "weakness": weaknesses,
            "improvement": recommendations,
            "statistics": detailed_stats,
            "speech_diagnostics": {
                "total_filler_count": total_filler_count,
                "avg_fillers_per_answer": round(avg_fillers_per_answer, 2),
                "filler_word_distribution": dict(global_filler_words_counter),
            },
        },
        "dynamically_triggered_tags": {
            "weakness_tags": top_5_weaknesses,
            "strength_tags": top_5_strengths,
        },
    }

    # 6. 최종 차트 및 프론트엔드 연동을 위한 raw_data 명세 결합
    raw_data = {
        "question_count": len(questions),
        "answer_count": len(answers_list),
        "evaluated_answer_count": n,
        "supported_scores": {
            "final_tech_scores": final_scores,
            "llm_concept_scores": [
                ans.evaluation.llm_concept_score
                for ans in evaluated_answers
                if getattr(ans.evaluation, "llm_concept_score", None) is not None
            ],
        },
        "tag_distribution": {
            "strengths": dict(strength_counter),
            "weaknesses": dict(weakness_counter),
        },
        "speech_diagnostics": {
            "total_filler_count": total_filler_count,
            "avg_fillers_per_answer": round(avg_fillers_per_answer, 2),
            "filler_word_distribution": dict(global_filler_words_counter),
        },
        "detailed_statistics": detailed_stats,
        "summary": standard_summary,
    }

    return {
        "overall_score": overall_score,
        "summary": summary,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "recommendations": recommendations,
        "question_count": len(questions),
        "answer_count": len(answers_list),
        "evaluated_answer_count": n,
        "raw_data": raw_data,
    }