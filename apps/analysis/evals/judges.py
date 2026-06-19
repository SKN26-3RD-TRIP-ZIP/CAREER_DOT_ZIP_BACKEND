"""
LLM-as-judge 평가기.

judge_question()  질문을 specificity / relevance / non_generic (각 1~5)로 채점
judge_answer()    STAR 답변을 star_completeness / groundedness / actionability로 채점

get_client()에 LangSmith 트레이싱이 걸려 있어 평가 실행도 LangSmith에 기록된다.
"""

import json

from ..services.utils import get_client, clean_json
from ..services.answer_guardrail import check_answer


def judge_question(question_text: str, context: str, model: str = "gpt-4o-mini") -> dict:
    """질문 1개를 루브릭으로 채점. 반환: {specificity, relevance, non_generic, reason, overall}"""
    client = get_client()
    res = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": (
                "당신은 면접 질문 품질 평가자입니다. 질문을 1~5점으로 엄격히 채점하세요.\n"
                "- specificity: 지원자 자료(JD/이력서/코드)에 구체적으로 들어맞는가 (1 일반론 ~ 5 매우 구체)\n"
                "- relevance:   직무·맥락과 관련 있는가\n"
                "- non_generic: 누구에게나 통하는 뻔한 질문이 아닌가 (1 뻔함 ~ 5 차별적)\n"
                "JSON만 출력: {\"specificity\":n,\"relevance\":n,\"non_generic\":n,\"reason\":\"...\"}"
            )},
            {"role": "user", "content": f"[맥락]\n{context}\n\n[평가할 질문]\n{question_text}"},
        ],
    )
    data = json.loads(clean_json(res.choices[0].message.content))
    data["overall"] = round(
        (data["specificity"] + data["relevance"] + data["non_generic"]) / 3, 2
    )
    return data


def judge_answer(answer: dict, source_text: str, model: str = "gpt-4o-mini") -> dict:
    """
    STAR 답변을 루브릭으로 채점.
    ★ 결정적 가드레일(check_answer)이 지어낸 수치를 잡으면 groundedness 점수에
      상한(2점)을 강제로 걸어 LLM 심판이 관대해지는 것을 막는다.
    """
    hard = check_answer(answer, source_text)   # 결정적 수치 검증

    client = get_client()
    res = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": (
                "당신은 면접 답변 품질 평가자입니다. STAR 답변을 1~5점으로 엄격히 채점하세요.\n"
                "- star_completeness: 상황/과제/행동/결과가 충실하고 논리적인가\n"
                "- groundedness:      원본 자료에 근거하며 지어낸 사실이 없는가 (1 창작 많음 ~ 5 완전 근거)\n"
                "- actionability:     지원자가 그대로 활용·각색하기 좋은가\n"
                "JSON만 출력: {\"star_completeness\":n,\"groundedness\":n,\"actionability\":n,\"reason\":\"...\"}"
            )},
            {"role": "user", "content": (
                f"[원본 자료]\n{source_text}\n\n"
                f"[평가할 답변]\n{json.dumps(answer, ensure_ascii=False)}\n\n"
                f"[참고: 자동 수치검증] 원본에 없는 수치 = {hard['unsupported'] or '없음'}"
            )},
        ],
    )
    data = json.loads(clean_json(res.choices[0].message.content))

    # 결정적으로 지어낸 수치가 있으면 groundedness 상한을 2로 강제
    if not hard["grounded"]:
        data["groundedness"] = min(data.get("groundedness", 5), 2)
    data["hard_unsupported"] = hard["unsupported"]
    data["overall"] = round(
        (data["star_completeness"] + data["groundedness"] + data["actionability"]) / 3, 2
    )
    return data
