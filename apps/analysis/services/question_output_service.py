"""
Pipeline 3 - ⑥ 최종 출력 조립

역할:
  STAR 답변이 붙은 질문 목록을 최종 API 응답 형태로 조립한다.
  GeneratedQuestion DB 저장 형식과 API 응답 형식 모두를 책임진다.

포함 함수:
  build_question_output()   최종 API 응답 형식 조립
  to_db_records()           DB 저장용 레코드 변환
"""


def build_question_output(questions_with_star: list[dict]) -> list[dict]:
    """
    STAR 답변이 붙은 질문 목록을 최종 API 응답 형태로 조립한다.

    내부 형식(text 키) → API 형식(question 키) 변환.
    """
    output = []
    for q in questions_with_star:
        item = {
            "question": q.get("text") or q.get("question", ""),
            "type":     q.get("type", ""),
            "source":   q.get("source", "jd"),
            "basis":    q.get("basis", ""),
        }
        if "answer" in q:
            item["answer"] = q["answer"]
        output.append(item)
    return output


def to_db_records(
    questions_with_star: list[dict],
    jd_analysis_id: str,
) -> list[dict]:
    """
    최종 질문 목록을 GeneratedQuestion 모델 저장용 레코드로 변환한다.

    반환 형식 (GeneratedQuestion 필드에 맞춤):
    [
        {
            "jd_analysis_id": "uuid",
            "question_type":  "personality",
            "question_text":  "질문 내용",
            "source":         "coverletter",
            "source_ref":     "근거 원문",
            "order":          0,
            "answer":         { "summary": ..., "situation": ..., ... }
        },
        ...
    ]
    """
    records = []
    for i, q in enumerate(questions_with_star):
        records.append({
            "jd_analysis_id": jd_analysis_id,
            "question_type":  q.get("type", "personality"),
            "question_text":  q.get("text") or q.get("question", ""),
            "source":         q.get("source", "jd"),
            "source_ref":     q.get("basis", ""),
            "order":          i,
            "answer":         q.get("answer", {}),
        })
    return records
