import asyncio
import re
import json
from kiwipiepy import Kiwi
from llm.client import client  # 기존 config 상의 비동기 client 또는 wrapper 가정

# 형태소 분석기 초기화 (비유창성 분석용)
kiwi = Kiwi()
FILLER_WORDS = ["어", "음", "그니까", "사실", "이제", "저기"]

# ==========================================
# 1. 독립 연산 레이어 (비동기 Task)
# ==========================================

def analyze_dysfluency_local(stt_text: str) -> dict:
    """
    [Task A] Python 로컬 연산: 형태소 분석 기반 비유창성(간투사/반복) 통계 추출
    LLM 비용이 들지 않으며 즉시 실행됨
    """
    filler_counts = {}
    total_filler = 0
    
    # 간투사(필러워드) 정규식 및 패턴 카운팅
    for word in FILLER_WORDS:
        count = len(re.findall(rf'\b{word}\b|{word}\.+', stt_text))
        if count > 0:
            filler_counts[word] = count
            total_filler += count

    # 말더듬 및 단어 반복 스캔 (조사 제외 2글자 이상 연속 중복)
    tokens = [t.form for t in kiwi.tokenize(stt_text)]
    repetition_scans = []
    for i in range(len(tokens) - 1):
        if tokens[i] == tokens[i+1] and len(tokens[i]) > 1:
            repetition_scans.append(tokens[i])

    # 문장 미완성 여부 판별 (흐리는 어미 체킹)
    is_incomplete = stt_text.endswith("...") or any(t.tag in ["EC", "XSV"] for t in kiwi.tokenize(stt_text)[-1:])

    return {
        "filler_word_counts": filler_counts,
        "total_filler_count": total_filler,
        "repetition_words": repetition_scans,
        "is_sentence_incomplete": is_incomplete
    }


async def eval_grounding_async(answer: str) -> dict:
    """
    [Task B] Fast LLM: 실무 경험 구체성 지표 추출 (poc_grounding 기반 비동기화)
    """
    prompt = """지원자 답변에서 다음 3대 실무 객관성 지표를 찾아 JSON으로 추출하십시오.
    1. 사용한 구체적 기술명 (tech_stack)
    2. 직면했던 정량적 제약/한계 수치 (before_metric)
    3. 개선 후 도출된 정량적 성과 수치 (after_metric)
    세 개가 모두 존재하면 'is_grounded': true, 하나라도 결손되면 false로 지정하십시오.
    반드시 마크다운 래퍼 없이 순수 JSON 오브젝트만 반환하세요."""

    # 프로독션 환경에서는 오버헤드를 줄이기 위해 gpt-4o-mini 비동기 호출
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": prompt}, {"role": "user", "content": answer}]
    ))
    return json.loads(res.choices[0].message.content)


async def eval_competency_async(answer: str) -> dict:
    """
    [Task C] Deep LLM: BEI(STAR) 구조화 및 CBI 역량 루브릭 통합 채점 (poc_bei + poc_cbi 통합)
    """
    system_prompt = system_prompt = """당신은 대기업 최고 실무진 및 직무 역량 평가 위원입니다.
제공된 지원자의 면접 답변(STT 텍스트)을 바탕으로 [BEI 구조화] 및 [CBI 역량 루브릭 채점]을 엄격하게 수행하십시오.

======================================================================
[RULE 1] BEI (행동사건면접) STAR 구조화 및 채점 가이드라인
======================================================================
지원자의 발화 맥락을 파악하여 다음 4가지 요소로 분리하고 정성적 점수(요소별 25점 만점, 총 100점)를 산출하십시오.

1. Situation (상황 - 만점 25점):
   - 평가 기준: 본인이 처했던 문제 상황, 배경, 타임라인이 얼마나 명확하게 제시되었는가?
   - 감점 요인: 단순히 "프로젝트를 했습니다" 수준으로 배경 맥락이 아예 모호한 경우 10점 이하 부여.
2. Task (과제 - 만점 25점):
   - 평가 기준: 해결해야 하는 과제나 목표, 당시 직면한 한계점 및 목표 달성의 난이도가 구체적이었는가?
   - 감점 요인: 문제 정의가 모호하고 본인이 무엇을 달성해야 했는지 목적 의식이 안 보일 경우 감점.
3. Action (행동 - 만점 25점):
   - 평가 기준: 문제 해결을 위해 지원자 '본인'이 취한 구체적인 기술적 노력, 논리적 접근 방식, 대안 검토 과정이 잘 기술되었는가? (가장 중요)
   - 감점 요인: '우리가 했다'식의 묻어가는 설명이거나, 구체적 기술 컴포넌트 제어 내용 없이 "열심히 해결했다" 식의 정성적 서술은 10점 이하 부여.
4. Result (결과 - 만점 25점):
   - 평가 기준: 행동을 통해 도출된 성과와 성공 여부가 명확한가?
   - 감점 요인: "무사히 끝냈다", "좋은 성과를 얻었다" 등 추상적인 회고에 그치면 12점 이하 부여.

======================================================================
[RULE 2] CBI (역량면접) '문제해결 및 주도성' 루브릭 매뉴얼
======================================================================
다음 대기업 표준 직무 역량 사전 가이드를 기반으로 지원자의 역량 레벨(Lv.1 ~ Lv.5)을 단 하나만 확정하고, 해당 레벨의 충족 여부를 입증하는 발화 원문("evidence_sentence")을 텍스트 내에서 정확히 추출하십시오.

- [Lv.1] 단순 수동적 수행 (Passive Execution)
  - 정의: 주어진 지시사항을 단순 이행하거나, 장애 발생 시 스스로 해결하지 못하고 포기/방관한 수준.
- [Lv.2] 외부 의존 및 회피 (Dependency & Escape)
  - 정의: 문제를 인지했으나 스스로 해결하려는 분석적 노력이 부족하여 멘토, 팀장 등 외부 리소스에 온전히 해결을 위탁하거나 책임 소지가 불명확한 수준.
- [Lv.3] 원인 분석 및 주도적 대안 제시 (Problem Analysis & Action)
  - 정의: 장애나 한계 상황의 근본 원인을 추적(로그 분석, 트래픽 추적 등)하고, 기술적 대안을 스스로 도출하여 직접적인 개선 Action을 실행한 수준. (신입 MVP의 정상 기준선)
- [Lv.4] 전파 및 정량적 최적화 (Optimization & Knowledge Sharing)
  - 정의: 본인의 Action을 통해 아키텍처 부하 완화 등 시스템을 정량적으로 최적화 완료하고, 프로세스 개선 과정을 매뉴얼화하여 팀 내에 공유/전파한 수준.
- [Lv.5] 시스템적 조직 혁신 및 제도화 (Organizational Impact)
  - 정의: 일회성 해결을 넘어 향후 다른 기수나 조직 전체가 반복적인 시행착오를 줄이도록 공용 매뉴얼/위키 시스템을 구축하거나 장기적 인프라 개선 구조를 제도화한 수준.

======================================================================
[RULE 3] 출력 포맷 제약 조건 (JSON Output Only)
======================================================================
- 마크다운 래퍼(```json ... ```)나 기타 텍스트 설명 없이 반드시 하단 스키마와 100% 일치하는 순수 JSON 오브젝트 하나만 반환하십시오.
- "desc" 필드에는 해당 단락에 대한 요약과 평가 사유를 국문(Korean)으로 상세히 적으십시오.

{
  "bei_star": {
    "situation": { "desc": "string", "score": "integer" },
    "task": { "desc": "string", "score": "integer" },
    "action": { "desc": "string", "score": "integer" },
    "result": { "desc": "string", "score": "integer" }
  },
  "cbi_competency": {
    "assigned_level": "integer (1 to 5)",
    "evidence_sentence": "string (실제 STT 원문에서 그대로 추출한 문장)"
  }
}"""

    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: client.chat.completions.create(
        model="gpt-4o",  # 심층 역량 평가를 위해 상위 모델 활용
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": answer}]
    ))
    return json.loads(res.choices[0].message.content)


# ==========================================
# 2. 비동기 오케스트레이션 및 인텔리전스 융합 레이어
# ==========================================

async def run_total_evaluation_pipeline(answer_id: str, answer_text: str) -> dict:
    """
    모든 분석 태스크를 병렬로 실행하고 백엔드 비즈니스 로직으로 결합하여 
    최종 PostgreSQL 적재용 JSONB 스키마를 완성하는 마스터 파이프라인
    """
    print(f"🚀 [답변 ID: {answer_id}] 통합 평가 파이프라인 가동 시작...")

    # [선행 필터] poc_bei.py의 정량 밸리데이션 규칙 선적용
    char_count = len(re.sub(r'\s+', '', answer_text))
    if char_count < 150:
        print("⚠️ 발화 글자 수 부족(150자 미만)으로 인한 정량 필터 폴백 적용")
        # 폴백용 로직 또는 패널티 결과 즉시 리턴 가능
    
    # 3개 태스크 비동기 병렬 기동 (가장 느린 Task C 시간으로 전체 레이턴시가 수렴됨)
    task_a = asyncio.to_thread(analyze_dysfluency_local, answer_text) # 블로킹 함수 쓰레드 격리
    task_b = eval_grounding_async(answer_text)
    task_c = eval_competency_async(answer_text)
    
    # 동시 취합
    dysfluency_res, grounding_res, competency_res = await asyncio.gather(task_a, task_b, task_c)
    
    # ==========================================
    # 🔥 핵심: 백엔드 정형 레이어 인텔리전스 융합 로직 (Cross-Referencing)
    # ==========================================
    
    # 융합 포인트 1: 실무 구체성(is_grounded) 결손 시, BEI Result 스코어에 감점 감쇄(Attenuation) 적용
    bei_star = competency_res.get("bei_star", {})
    if not grounding_res.get("is_grounded", False):
        # 수치 지표가 누락되었다면 Result 점수를 강제로 40% 차감하는 백엔드 규칙 가중치 연동
        original_result_score = bei_star.get("result", {}).get("score", 0)
        bei_star["result"]["score"] = round(original_result_score * 0.6, 1)
        bei_star["result"]["desc"] += " (연구소 평가: 구체적인 기술 스택 및 정량 수치 미비로 인한 신뢰도 감점 반영)"

    # 융합 포인트 2: 정량 통계를 기반으로 강점/약점 태그 엔진 트리거 시그널 계산
    triggered_strengths = []
    triggered_weaknesses = []
    
    # 강점 조건 체킹 (예시: 필러워드가 없고 페이스가 유창할 때)
    if dysfluency_res["total_filler_count"] <= 3 and not dysfluency_res["is_sentence_incomplete"]:
        triggered_strengths.append({
            "tag_name": "fluent_speech_delivery",
            "reason": f"전체 답변 중 필러워드가 단 {dysfluency_res['total_filler_count']}회 검출되었으며, 말끝 흐림이 없어 전달력이 우수함"
        })
        
    # 약점 조건 체킹 (예시: Grounding 수치 결손 및 특정 단어 반복 포착 시)
    if not grounding_res.get("is_grounded", False):
        triggered_weaknesses.append({
            "tag_name": "weak_specificity",
            "reason": f"성과를 기술하는 단락에서 전/후 대비 정량 지표(Metric)가 결손되어 실무 구체성이 떨어짐"
        })
    if len(dysfluency_res["repetition_words"]) >= 2:
         triggered_weaknesses.append({
            "tag_name": "habitual_repetition",
            "reason": f"답변 과정에서 [{', '.join(dysfluency_res['repetition_words'])}] 등의 단어를 연속해서 말더듬는 습관 포착"
        })

    # 종합 가중치 점수 계산 (BEI 합산 + CBI 가중치)
    total_bei_score = sum(factor.get("score", 0) for factor in bei_star.values())
    cbi_level = competency_res.get("cbi_competency", {}).get("assigned_level", 1)
    
    # 하이브리드 수식 적용 예시 (최종 스코어 산출)
    overall_score = round((total_bei_score * 0.7) + (cbi_level * 6.0), 1)

    # ==========================================
    # 3. PostgreSQL 적재용 JSONB 구조화 마샬링
    # ==========================================
    master_evaluation_jsonb = {
        "score_summary": {
            "overall_score": overall_score,
            "bei_total": total_bei_score,
            "cbi_level": cbi_level
        },
        "score_detail": {
            "bei_logic": bei_star,
            "cbi_competency": competency_res.get("cbi_competency", {}),
            "technical_grounding": grounding_res,
            "speech_delivery": dysfluency_res
        },
        "pipeline_tags": {
            "strengths": triggered_strengths,
            "weaknesses": triggered_weaknesses
        }
    }
    
    print(f"✅ [답변 ID: {answer_id}] 파이프라인 처리 완료.")
    return master_evaluation_jsonb

# ==========================================
# 4. 테스트 런처 구동
# ==========================================
if __name__ == "__main__":
    # 부트캠프 프로젝트 당시 작성된 Kafka 기반 실제 모의 답변 데이터 케이스
    mock_user_answer = """부트캠프 당시 올림픽 호스트 국가 효과 분석 웹 서비스를 장고로 개발했습니다. 
    대용량 데이터를 마이그레이션하는 과정에서 DB 부하로 인해 로딩 속도가 엄청 느려지는 장애가 터졌습니다. 어... 
    팀원들과 코드를 열어 슬로우 쿼리를 추적했고 쿼리를 최적화했습니다. 그 결과 프로젝트 속도를 대폭 개선 시켰습니다. 
    음... 그래서 무사히 배포 완료했습니다."""

    async def main():
        result = await run_total_evaluation_pipeline(
            answer_id="ans_00001", 
            answer_text=mock_user_answer
        )
        print("\n=== [PostgreSQL 적재용 최종 JSONB 출력 결과] ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))

    asyncio.run(main())


# ==========================================
# 2. 테스트 결과

# 🚀 [답변 ID: ans_00001] 통합 평가 파이프라인 가동 시작...
# ✅ [답변 ID: ans_00001] 파이프라인 처리 완료.

# === [PostgreSQL 적재용 최종 JSONB 출력 결과] ===
# {
#   "score_summary": {
#     "overall_score": 61.4,
#     "bei_total": 62.0,
#     "cbi_level": 3
#   },
#   "score_detail": {
#     "bei_logic": {
#       "situation": {
#         "desc": "지원자는 부트캠프에서 올림픽 호스트 국가 효과 분석 웹 서비스를 개발하면서 대용량 데이터 마이그레이션 과정 중 DB 부하 문제를 경험했습니다. 그러나 상황 자체의 맥락 설명이 구체적이지 않습니다.",
#         "score": 15
#       },
#       "task": {
#         "desc": "DB 부하로 인해 로딩 속도가 느려지는 문제가 발생했으며 이를 해결하기 위해 쿼리 최적화가 필요했습니다. 그러나 과제의 구체성이 부족합니다.",
#         "score": 18
#       },
#       "action": {
#         "desc": "팀원들과 함께 슬로우 쿼리를 추적하여 이를 최적화하는 구체적 행동을 취했습니다. 하지만 개인의 기술적 노력과 논리적 접근 방식이 충분히 서술되지 않았습니다.",
#         "score": 20
#       },
#       "result": {
#         "desc": "프로젝트의 속도가 개선되어 무사히 배포 완료했으나 결과에 대한 구체적인 정량적 성공 지표가 부족합니다. (연구소 평가: 구체적인 기술 스택 및 정량 수치 미비로 인한 신뢰도 감점 반영)",
#         "score": 9.0
#       }
#     },
#     "cbi_competency": {
#       "assigned_level": 3,
#       "evidence_sentence": "팀원들과 코드를 열어 슬로우 쿼리를 추적했고 쿼리를 최적화했습니다."
#     },
#     "technical_grounding": {
#       "tech_stack": "장고",
#       "before_metric": "로딩 속도 느림",
#       "after_metric": "프로젝트 속도 대폭 개선",
#       "is_grounded": false
#     },
#     "speech_delivery": {
#       "filler_word_counts": {
#         "어": 1,
#         "음": 1
#       },
#       "total_filler_count": 2,
#       "repetition_words": [],
#       "is_sentence_incomplete": false
#     }
#   },
#   "pipeline_tags": {
#     "strengths": [
#       {
#         "tag_name": "fluent_speech_delivery",
#         "reason": "전체 답변 중 필러워드가 단 2회 검출되었으며, 말끝 흐림이 없어 전달력이 우수함"
#       }
#     ],
#     "weaknesses": [
#       {
#         "tag_name": "weak_specificity",
#         "reason": "성과를 기술하는 단락에서 전/후 대비 정량 지표(Metric)가 결손되어 실무 구체성이 떨어짐"
#       }
#     ]
#   }
# }