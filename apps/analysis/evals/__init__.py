"""
질문·답변 품질 평가 (LLM-as-judge + 결정적 가드레일).

모델·프롬프트를 바꿀 때 품질이 오르는지 내리는지 수치로 추적하기 위한 도구.
운영 코드가 아니라 품질 회귀 방지용 측정 도구다.

실행:
  python manage.py run_quality_eval        # OPENAI_API_KEY 필요
"""
