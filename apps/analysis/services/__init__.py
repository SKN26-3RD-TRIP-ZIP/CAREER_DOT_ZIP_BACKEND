"""
analysis/services 패키지

Pipeline 1. 매칭 점수 산출
  jd_service.py       ① JD 분석
  resume_service.py   ② 사용자 문서 분석 (이력서·자소서)
  project_service.py  ② 프로젝트 경험 추출·채점 (ProjectProfile, ProjectScorer)
  match_service.py    ③ 비교 & 점수 산출 (기술/역량/룰베이스)
  result_service.py   ④ 결과 포맷팅 / CI

Pipeline 2. 갭 분석
  gap_service.py      ③④ 갭 계산 + 신입/경력 분기 출력

Pipeline 3. 예상 질문 & STAR 답변
  question_rag_service.py     ② 질문 은행 RAG (Pinecone)
  question_gen_service.py     ③ LLM 예상 질문 생성
  question_merge_service.py   ④ 질문 통합 & 중복 제거
  star_service.py             ⑤ STAR 답변 생성
  question_output_service.py  ⑥ 최종 출력 조립
  question_service.py         오케스트레이터 (②~⑥ 조율)

공통
  utils.py   get_client, clean_json, get_embeddings, cosine_similarity
"""

# views.py에서 직접 import하는 공개 인터페이스
from .jd_service       import extract_jd_keywords
from .resume_service   import analyze_resume
from .match_service    import calculate_match_score
from .question_service import generate_all_questions
