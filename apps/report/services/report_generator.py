import logging
from collections import Counter

from django.utils import timezone

from apps.evaluation.services.session_evaluation import evaluate_session_answers

logger = logging.getLogger("feedback_ai.report_generator")


def get_score(value):
  if isinstance(value, dict):
    return value.get('score', 0)
  return value or 0


def _aggregate_tag_objects(evaluated_answers, mapping_attr, tag_attr):
  """Build design-doc tag objects from answer tag mappings."""
  tag_map = {}
  for answer in evaluated_answers:
    for mapping in getattr(answer, mapping_attr).all():
      tag = getattr(mapping, tag_attr)
      name = tag.tag_name
      if name not in tag_map:
        tag_map[name] = {
          'tag_name': name,
          'description': mapping.reason or tag.description or '',
          'trigger_signal': getattr(mapping, 'trigger_signal_log', None) or mapping.reason or '',
          'count': 0,
        }
      tag_map[name]['count'] += 1
  ranked = sorted(tag_map.values(), key=lambda item: (-item['count'], item['tag_name']))
  for item in ranked:
    item.pop('count', None)
  return ranked[:5]


def generate_final_report(session):
  """
  Build the canonical feedback_reports.summary JSONB payload
  (evaluation_metadata, score_summary, score_detail, dynamically_triggered_tags).
  """
  # 미평가 답변 자동 백필: 실제 면접 플로우(MVP)에서는 답변 저장만 일어나고
  # 평가가 트리거되지 않으므로, 리포트 생성 시점에 누락된 평가를 채운다.
  # 멱등이며(이미 평가된 답변은 건너뜀) 답변별로 예외가 격리되어 실패해도 리포트는 계속 생성된다.
  try:
    evaluate_session_answers(session)
  except Exception:  # noqa: BLE001 - 백필 실패가 리포트 생성을 막지 않도록 방어
    logger.exception('evaluate_session_answers backfill failed for session %s', getattr(session, 'id', '?'))

  answers = session.answers.all().select_related('evaluation', 'question').prefetch_related(
      'strength_mappings__strength_tag',
      'weakness_mappings__weakness_tag',
  )

  questions = list(session.questions.all())
  answers_list = list(answers)
  evaluated_answers = [
      ans for ans in answers_list
      if hasattr(ans, 'evaluation') and ans.evaluation is not None
  ]

  final_scores = [
      ans.evaluation.final_tech_score
      for ans in evaluated_answers
      if getattr(ans.evaluation, 'final_tech_score', None) is not None
  ]
  overall_score = round(sum(final_scores) / len(final_scores)) if final_scores else 0

  strength_counter = Counter()
  weakness_counter = Counter()
  bei_situations, bei_tasks, bei_actions, bei_results = [], [], [], []
  cbi_levels, cbi_scores = [], []
  speech_scores = []
  sbert_scores = []

  for ans in evaluated_answers:
    eval_obj = ans.evaluation

    for sm in ans.strength_mappings.all():
      strength_counter[sm.strength_tag.tag_name] += 1
    for wm in ans.weakness_mappings.all():
      weakness_counter[wm.weakness_tag.tag_name] += 1

    # Technical 축(고도화: SBERT 유사도 기반 기술 질문 평가). 미구현 시 None -> 0 처리.
    sbert_sims = [
        s for s in (
            getattr(eval_obj, 'sbert_db_similarity', None),
            getattr(eval_obj, 'sbert_readme_similarity', None),
        )
        if s is not None
    ]
    if sbert_sims:
      sbert_scores.append(sum(sbert_sims) / len(sbert_sims))

    bei = eval_obj.bei_score if isinstance(eval_obj.bei_score, dict) else {}
    bei_situations.append(get_score(bei.get('situation')))
    bei_tasks.append(get_score(bei.get('task')))
    bei_actions.append(get_score(bei.get('action')))
    bei_results.append(get_score(bei.get('result')))

    cbi = eval_obj.cbi_score if isinstance(eval_obj.cbi_score, dict) else {}
    if 'assigned_level' in cbi:
      cbi_levels.append(cbi['assigned_level'])
    elif 'level' in cbi:
      cbi_levels.append(cbi['level'])
    if 'score' in cbi:
      cbi_scores.append(cbi['score'])

    score_detail = eval_obj.score_detail if isinstance(eval_obj.score_detail, dict) else {}
    speech_delivery = score_detail.get('speech_delivery', {})
    if speech_delivery.get('speech_score') is not None:
      speech_scores.append(speech_delivery['speech_score'])

  top_strength_names = [name for name, _ in strength_counter.most_common(5)]
  top_weakness_names = [name for name, _ in weakness_counter.most_common(5)]

  total_filler_count = 0
  global_filler_words_counter = Counter()
  for ans in evaluated_answers:
    filler_data = getattr(ans.evaluation, 'filler_words', {}) or {}
    if isinstance(filler_data, dict):
      total_filler_count += filler_data.get('total', 0)
      counts = filler_data.get('counts', {})
      if isinstance(counts, dict):
        for word, cnt in counts.items():
          global_filler_words_counter[word] += cnt

  n = len(evaluated_answers)
  avg_fillers_per_answer = round(total_filler_count / n, 2) if n else 0

  recommendations = []
  summary_text_parts = []
  if strength_counter:
    summary_text_parts.append(
        f"이번 세션에서 가장 강력하게 발휘된 역량은 [{strength_counter.most_common(1)[0][0]}] 입니다."
    )
  if weakness_counter:
    summary_text_parts.append(
        f"가장 빈번하게 노출된 보완점은 [{weakness_counter.most_common(1)[0][0]}] 항목으로 확인됩니다."
    )
  if total_filler_count > 0:
    most_common_fillers = [word for word, _ in global_filler_words_counter.most_common(2)]
    filler_str = ', '.join([f"'{w}'" for w in most_common_fillers])
    summary_text_parts.append(f"전체 면접 중 총 {total_filler_count}회의 습관어가 감지되었습니다.")
    if avg_fillers_per_answer >= 3.0:
      recommendations.append(
          f"답변 과정에서 {filler_str} 등의 추임새가 자주 반복됩니다. "
          "생각을 정리할 때 1~2초 의도적 pause 연습을 권장합니다."
      )
    else:
      recommendations.append(
          f"주로 감지되는 표현은 {filler_str} 입니다. 실전에서도 현재 발화 페이스를 유지하세요."
      )
  else:
    summary_text_parts.append("비유창성 언어가 거의 발견되지 않은 정제된 발화 습관을 보여주었습니다.")

  if not recommendations:
    recommendations.append('세션 상세 답변의 꼬리질문 분석 내용을 점검해 보세요.')

  detailed_stats = {}
  bei_avg = cbi_avg = speech_avg = 0
  if n > 0:
    avg_sit = round(sum(bei_situations) / n, 1)
    avg_tsk = round(sum(bei_tasks) / n, 1)
    avg_act = round(sum(bei_actions) / n, 1)
    avg_res = round(sum(bei_results) / n, 1)
    bei_avg = round((avg_sit + avg_tsk + avg_act + avg_res) / 4, 1)
    cbi_avg = round(sum(cbi_scores) / len(cbi_scores), 1) if cbi_scores else 0
    speech_avg = round(sum(speech_scores) / len(speech_scores), 1) if speech_scores else 0
    detailed_stats = {
      'bei_metrics': {
        'averages': {
          'situation': avg_sit,
          'task': avg_tsk,
          'action': avg_act,
          'result': avg_res,
        },
        'element_total_avg': bei_avg,
      },
      'cbi_metrics': {
        'average_level': round(sum(cbi_levels) / len(cbi_levels), 1) if cbi_levels else 0,
        'average_score': cbi_avg,
      },
    }

  # Grounding 축: 현재 기술 질문 평가방식(final_tech_score = grounding 기반 종합 점수)
  grounding_avg = round(sum(final_scores) / len(final_scores), 1) if final_scores else 0
  # Technical 축: 고도화 SBERT 유사도 평가(0~1 -> 0~100 환산). 미구현 시 0.
  technical_avg = round((sum(sbert_scores) / len(sbert_scores)) * 100, 1) if sbert_scores else 0
  strength_tags = _aggregate_tag_objects(evaluated_answers, 'strength_mappings', 'strength_tag')
  weakness_tags = _aggregate_tag_objects(evaluated_answers, 'weakness_mappings', 'weakness_tag')

  # 질문별 평가 경량 배열 (리포트 메인 '질문별 AI 평가' 테이블용 스냅샷).
  # generate 시점에 함께 집계 -> 별도 쿼리/추가 API 없이 리포트 1회 호출로 노출.
  question_breakdown = []
  for ans in evaluated_answers:
    q = ans.question
    eval_obj = ans.evaluation
    q_score = getattr(eval_obj, 'final_tech_score', None)
    wmaps = list(ans.weakness_mappings.all())
    improvement_action = ''
    if wmaps:
      top_wm = sorted(wmaps, key=lambda m: getattr(m, 'priority_rank', 99) or 99)[0]
      improvement_action = top_wm.reason or (
          top_wm.weakness_tag.description if top_wm.weakness_tag else ''
      )
    question_breakdown.append({
      'question_id': str(q.id),
      'order': q.order_index,
      'question_type': q.question_type,
      'question_text': q.question_text,
      'improvement_action': improvement_action,
      'score': q_score if q_score is not None else 0,
    })
  question_breakdown.sort(key=lambda item: item['order'])

  return {
    'evaluation_metadata': {
      'session_id': str(session.id),
      'persona_type': session.persona,
      'interview_mode': session.interview_mode,
      'interview_type': session.interview_type,
      'question_count': len(questions),
      'answer_count': len(answers_list),
      'evaluated_answer_count': n,
      'calculated_at': timezone.now().isoformat(),
      'summary_text': ' '.join(summary_text_parts) if summary_text_parts else '세션 데이터 기반으로 최종 리포트가 생성되었습니다.',
    },
    'score_summary': {
      'overall_score': overall_score,
      # 5축 레이더: BEI / CBI / Grounding / Speech / Technical(고도화 SBERT)
      'metrics': {
        'bei_logic_score': bei_avg,
        'cbi_competency_score': cbi_avg,
        'grounding_score': grounding_avg,
        'speech_delivery_score': speech_avg,
        'technical_score': technical_avg,
      },
    },
    'score_detail': {
      'strength': top_strength_names or ['리포트 생성 기본 요건을 충족했습니다.'],
      'weakness': top_weakness_names or (
          ['전반적인 답변 구조의 일관성 확인이 필요합니다.'] if len(answers_list) < 3 else []
      ),
      'improvement': recommendations,
      'questions': question_breakdown,
      'statistics': detailed_stats,
      'speech_diagnostics': {
        'total_filler_count': total_filler_count,
        'avg_fillers_per_answer': avg_fillers_per_answer,
        'filler_word_distribution': dict(global_filler_words_counter),
      },
    },
    'dynamically_triggered_tags': {
      'strength_tags': strength_tags,
      'weakness_tags': weakness_tags,
    },
  }
