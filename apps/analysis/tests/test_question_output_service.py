"""
question_output_service 단위 테스트

테스트 대상:
  build_question_output()  내부 포맷 → API 응답 포맷 변환
  to_db_records()          내부 포맷 → DB 저장 포맷 변환

실행:
  pytest apps/analysis/tests/test_question_output_service.py -v -s
"""

import pytest
from apps.analysis.services.question_output_service import (
    build_question_output,
    to_db_records,
)

STAR_ANSWER = {
    "summary":      "Redis 캐싱으로 응답 속도를 40% 개선했습니다.",
    "situation":    "트래픽 증가로 API 지연이 발생했습니다.",
    "task":         "캐싱 전략 설계 및 적용을 담당했습니다.",
    "action":       "Redis TTL 전략을 도입해 반복 조회를 캐싱했습니다.",
    "result":       "응답 속도 40% 개선, 서버 부하 30% 감소.",
    "basis_source": "project:배달플랫폼",
}

SAMPLE_QUESTIONS = [
    {"type": "technical",   "text": "Redis 캐싱 전략을 설명해주세요.",     "source": "jd",          "basis": "Redis 필수", "answer": STAR_ANSWER},
    {"type": "personality", "text": "팀 갈등을 해결한 경험이 있나요?",    "source": "coverletter",  "basis": "팀워크 강조", "answer": STAR_ANSWER},
    {"type": "experience",  "text": "배달플랫폼 프로젝트에서 역할은?",    "source": "project",      "basis": "배달플랫폼",  "answer": STAR_ANSWER},
]


# ══════════════════════════════════════════════════════════════
# build_question_output
# ══════════════════════════════════════════════════════════════

class TestBuildQuestionOutput:

    def test_text_renamed_to_question(self):
        """내부 'text' 키가 API 응답에서 'question'으로 변환"""
        result = build_question_output(SAMPLE_QUESTIONS)
        for item in result:
            assert "question" in item, "'question' 키 없음"
            assert "text"     not in item, "'text' 키가 남아있음"
        print(f"\n키 변환 확인: {list(result[0].keys())}")

    def test_output_count(self):
        """입력과 출력 개수 일치"""
        result = build_question_output(SAMPLE_QUESTIONS)
        assert len(result) == len(SAMPLE_QUESTIONS)

    def test_required_fields(self):
        """필수 필드 5개 모두 존재"""
        result = build_question_output(SAMPLE_QUESTIONS)
        required = {"question", "type", "source", "basis", "star"}
        for i, item in enumerate(result):
            missing = required - set(item.keys())
            assert not missing, f"항목 {i}에서 필드 누락: {missing}"

    def test_star_fields(self):
        """star 내부에 STAR 5개 키 존재"""
        result = build_question_output(SAMPLE_QUESTIONS)
        star_keys = {"summary", "situation", "task", "action", "result"}
        for item in result:
            assert star_keys.issubset(set(item["star"].keys()))

    def test_empty_input(self):
        """빈 입력 → 빈 출력"""
        result = build_question_output([])
        assert result == []

    @pytest.mark.parametrize("q_type", ["technical", "personality", "experience"])
    def test_question_types_preserved(self, q_type):
        """question type이 그대로 유지"""
        questions = [{"type": q_type, "text": "질문", "source": "jd", "basis": "", "answer": STAR_ANSWER}]
        result = build_question_output(questions)
        assert result[0]["type"] == q_type

    def test_no_answer_question(self):
        """answer 없는 질문도 처리 (star 키 없어도 에러 없음)"""
        questions = [{"type": "technical", "text": "질문", "source": "jd", "basis": ""}]
        result = build_question_output(questions)
        assert len(result) == 1
        assert "star" not in result[0]

    def test_question_text_matches(self):
        """text → question 값이 원본과 동일"""
        result = build_question_output(SAMPLE_QUESTIONS)
        for original, output in zip(SAMPLE_QUESTIONS, result):
            assert output["question"] == original["text"]

    @pytest.mark.parametrize("source", ["jd", "resume", "coverletter", "project", "combined"])
    def test_source_values(self, source):
        """모든 source 값이 그대로 전달"""
        questions = [{"type": "technical", "text": "질문", "source": source, "basis": "", "answer": STAR_ANSWER}]
        result = build_question_output(questions)
        assert result[0]["source"] == source


# ══════════════════════════════════════════════════════════════
# to_db_records
# ══════════════════════════════════════════════════════════════

class TestToDbRecords:

    JD_ANALYSIS_ID = "test-uuid-1234"

    def test_record_count(self):
        """입력 질문 수 = 반환 레코드 수"""
        records = to_db_records(SAMPLE_QUESTIONS, self.JD_ANALYSIS_ID)
        assert len(records) == len(SAMPLE_QUESTIONS)

    def test_required_db_fields(self):
        """DB 레코드 필수 필드 존재"""
        records = to_db_records(SAMPLE_QUESTIONS, self.JD_ANALYSIS_ID)
        required = {"jd_analysis_id", "question_type", "question_text", "source", "source_ref", "order", "answer"}
        for i, rec in enumerate(records):
            missing = required - set(rec.keys())
            assert not missing, f"레코드 {i}에서 필드 누락: {missing}"
        print(f"\nDB 필드: {list(records[0].keys())}")

    def test_order_sequential(self):
        """order 필드가 0부터 순차 증가"""
        records = to_db_records(SAMPLE_QUESTIONS, self.JD_ANALYSIS_ID)
        orders = [r["order"] for r in records]
        print(f"\norder: {orders}")
        assert orders == list(range(len(SAMPLE_QUESTIONS)))

    def test_jd_analysis_id_set(self):
        """모든 레코드에 jd_analysis_id 주입"""
        records = to_db_records(SAMPLE_QUESTIONS, self.JD_ANALYSIS_ID)
        for rec in records:
            assert rec["jd_analysis_id"] == self.JD_ANALYSIS_ID

    def test_text_mapped_to_question_text(self):
        """내부 'text' 키가 'question_text'로 매핑"""
        records = to_db_records(SAMPLE_QUESTIONS, self.JD_ANALYSIS_ID)
        for original, rec in zip(SAMPLE_QUESTIONS, records):
            assert rec["question_text"] == original["text"]

    def test_basis_mapped_to_source_ref(self):
        """내부 'basis' 키가 'source_ref'로 매핑"""
        records = to_db_records(SAMPLE_QUESTIONS, self.JD_ANALYSIS_ID)
        for original, rec in zip(SAMPLE_QUESTIONS, records):
            assert rec["source_ref"] == original.get("basis", "")

    def test_answer_preserved(self):
        """answer(STAR) 딕셔너리가 그대로 저장"""
        records = to_db_records(SAMPLE_QUESTIONS, self.JD_ANALYSIS_ID)
        for original, rec in zip(SAMPLE_QUESTIONS, records):
            assert rec["answer"] == original.get("answer", {})

    def test_empty_input(self):
        """빈 입력 → 빈 레코드"""
        records = to_db_records([], self.JD_ANALYSIS_ID)
        assert records == []

    def test_question_type_field(self):
        """'type' → 'question_type' 매핑"""
        records = to_db_records(SAMPLE_QUESTIONS, self.JD_ANALYSIS_ID)
        types = [r["question_type"] for r in records]
        print(f"\nquestion_type: {types}")
        assert "technical"   in types
        assert "personality" in types
        assert "experience"  in types
