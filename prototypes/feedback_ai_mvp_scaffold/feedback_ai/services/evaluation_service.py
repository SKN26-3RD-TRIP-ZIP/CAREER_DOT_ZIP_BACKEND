# prototypes/feedback_ai_mvp_scaffold/feedback_ai/services/evaluation_service.py

import asyncio
import re
import logging  # 💡 로깅 모듈 추가
import time     # 💡 레이턴시 측정을 위한 time 모듈 추가
from datetime import datetime
from kiwipiepy import Kiwi
from chains.evaluation_chains import eval_grounding_chain, eval_competency_chain
from schemas.evaluation import EvaluationMasterResult
from prototypes.feedback_ai_mvp_scaffold.feedback_ai.utils.tag_router import route_deterministic_tags
from prototypes.feedback_ai_mvp_scaffold.feedback_ai.config import SPEECH_CONFIG  # 설정 파일 반입

# 로거 정의
logger = logging.getLogger("feedback_ai.evaluation_service")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")

kiwi = Kiwi()
FILLER_WORDS = [["어", "음", "그니까", "사실", "이제", "저기"]]

def analyze_dysfluency_local(stt_text: str, long_pause_count: int = 0) -> dict:
    """[Task A] 로컬 비유창성 분석"""
    logger.info("=== [Task A] 로컬 비유창성 분석 시작 ===")
    start_time = time.time()
    
    filler_counts = {}
    total_filler = 0
    for word in FILLER_WORDS[0]:
        count = len(re.findall(rf'\\b{word}\\b|{word}\\.+', stt_text))
        if count > 0:
            filler_counts[word] = count
            total_filler += count

    tokens = [t.form for t in kiwi.tokenize(stt_text)]
    repetition_scans = []
    for i in range(len(tokens) - 1):
        if tokens[i] == tokens[i+1] and len(tokens[i]) > 1:
            repetition_scans.append(tokens[i])

    duration = time.time() - start_time
    logger.info(f"[Task A 완료] 필러워드: {total_filler}회, 중복 발화: {len(repetition_scans)}건 검출")
    
    return {
        "filler_word_counts": filler_counts,
        "total_filler_count": total_filler,
        "long_pause_count": long_pause_count,
        "repetitions": repetition_scans
    }


class EvaluationService:

    @staticmethod
    def calculate_final_scores(metrics: dict, question_type: str) -> tuple:
        """답변 구조 및 기술 분석 - 가중치 분배 사유서(ADR) 기준 매트릭스 연산 처리 레이어"""
        logger.info(f"=== 결정론적 가중치 스코어링 연산 (인풋 카테고리: '{question_type}') ===")
        
        bei = metrics.get("bei_logic_score", 0.0)
        cbi = metrics.get("cbi_competency_score", 0.0)
        tech = metrics.get("technical_depth_score")
        speech = metrics.get("speech_delivery_score", 0.0)

        # 1. 인성 및 직무 적합성 질문일 때 (Technical 축 완전 배제 후 2:2:1 밸런싱 확장)
        if question_type in ["personality", "job"]:
            metrics["technical_depth_score"] = None
            # BEI(40%) + CBI(40%) + Speech(20%)
            overall_score = (bei * 0.4) + (cbi * 0.4) + (speech * 0.2)
            logger.info(f"[가중치 분기 수식 가동]: (BEI:{bei} * 0.4) + (CBI:{cbi} * 0.4) + (Speech:{speech} * 0.2)")
            
        # 2. 기술 관련 질문일 때 (4개 지표 가중치 가동 반영)
        elif question_type in ["technical"]:
            tech_val = tech if tech is not None else 40.0
            # BEI(30%) + CBI(30%) + Tech(25%) + Speech(15%)
            overall_score = (bei * 0.3) + (cbi * 0.3) + (tech_val * 0.25) + (speech * 0.15)
            logger.info(f"[가중치 분기 수식 가동]: (BEI:{bei} * 0.3) + (CBI:{cbi} * 0.3) + (Tech:{tech_val} * 0.25) + (Speech:{speech} * 0.15)")
        
        else:
            logger.warning(f"정의되지 않은 question_type('{question_type}') 진입. 기본 단순 평균 스케일로 우회합니다.")
            overall_score = (bei + cbi + speech) / 3.0

        final_score = round(overall_score, 1)
        logger.info(f"▶ 최종 가중 평균 종합 점수(overall_score): {final_score}점")
        return final_score, metrics


    @staticmethod
    async def run_pipeline(
        answer_text: str, 
        question_type: str, 
        long_pause_count: int = 0, # 👈 정식 인터페이스로 격상
        llm_weakness_tags: list = None
    ) -> EvaluationMasterResult:
        """하이브리드 비동기 분기 병렬 처리 통합 파이프라인 마스터 매니저"""
        logger.info(f"==================== 🚀 EVALUATION PIPELINE RUN (타입: {question_type}) ====================")
        pipeline_start_time = time.time()

        # 1. 텍스트 기본 전처리 검증 규칙
        char_count = len(answer_text)
        raw_word_count = len(answer_text.split())
        logger.info(f"[인풋 데이터 검증] 글자 수: {char_count}자, 공백 기준 단어 수: {raw_word_count}개")

        # 2. 로컬 정량 지표 가동 (외부에서 유입된 침묵 데이터 전송)
        dysfluency_res = analyze_dysfluency_local(answer_text, long_pause_count=long_pause_count)

        # 3. 비동기 LLM 오케스트레이션 가동 (Task B + Task C 병렬 쓰레드 대입)
        logger.info("📡 외부 LLM 비동기 오케스트레이션(Task B & Task C) 병렬 호출 시작...")
        llm_start_time = time.time()
        
        task_b = eval_grounding_chain(answer_text)
        task_c = eval_competency_chain(answer_text)
        
        grounding_res, competency_res = await asyncio.gather(task_b, task_c)
        
        llm_duration = time.time() - llm_start_time
        logger.info(f"📡 LLM 병렬 체인 응답 수신 완료 (소요시간: {llm_duration:.3f}s)")

        # 정성 지표 파싱 및 누산
        bei_star = competency_res.get("bei_star", {})
        bei_total = float(sum(v.get("score", 0) for v in bei_star.values()))
        cbi_level = competency_res.get("cbi_competency", {}).get("assigned_level", 1)
        cbi_score = float(cbi_level * 20.0)
        
        logger.info(f"[정성 지표 중간 정산] BEI STAR 총합: {bei_total}점, CBI 매핑 레벨: {cbi_level} (환산: {cbi_score}점)")

        # 4. MVP Grounding 수치 기반 동적 기술 점수 산출 로직
        is_grounded_flag = grounding_res.get("is_grounded", False)
        logger.info(f"[Grounding 엔진 판정] is_grounded: {is_grounded_flag}")
        
        if is_grounded_flag:
            extracted_entities = sum(
                1 for key in ["tech_stack", "before_metric", "after_metric"] 
                if grounding_res.get(key)
            )
            calculated_tech_score = float(85 + (extracted_entities * 5))
            calculated_tech_score = min(calculated_tech_score, 100.0)
            logger.info(f"-> 지표 검증 통과 완료. 유효 엔티티 개수: {extracted_entities}/3 -> 동적 매핑 기술 점수: {calculated_tech_score}점")
        else:
            calculated_tech_score = 40.0
            logger.info(f"-> ⚠️ 지표 결손 발생 (과락 Floor Penalty 적용). 매핑 기술 점수: {calculated_tech_score}점")

        # 5. 메트릭 사전 취합 (config 상수 연산으로 대체)
        # 기본 100점 - (필러워드 개수 * 5점) -> 최소 20점 보장
        calculated_speech_score = SPEECH_CONFIG["BASE_SCORE"] - (dysfluency_res["total_filler_count"] * SPEECH_CONFIG["FILLER_PENALTY_PER_COUNT"])
        speech_delivery_score = max(calculated_speech_score, SPEECH_CONFIG["FLOOR_SCORE"])

        raw_metrics = {
            "bei_logic_score": bei_total,
            "cbi_competency_score": cbi_score,
            "technical_depth_score": calculated_tech_score,
            "speech_delivery_score": speech_delivery_score
        }

        # 6. 백엔드 결정론적 계산기 레이어 작동 (가중 평균 대입)
        overall_score, final_metrics = EvaluationService.calculate_final_scores(raw_metrics, question_type)

        # 7. 규칙 엔진 가동 (정수/실수 순수 프리미티브 변수로 다이렉트 바인딩)
        logger.info("🔧 마스터 규칙 엔진 가동 (Deterministic Tag Routing)...")
        
        total_filler_count = dysfluency_res.get("total_filler_count", 0)
        long_pause_count = dysfluency_res.get("long_pause_count", 0)

        deterministic_tags = route_deterministic_tags(
            question_type=question_type,
            bei_star=bei_star,
            cbi_res=competency_res,
            grounding_res=grounding_res,
            total_filler=total_filler_count,
            long_pause_count=long_pause_count,
            raw_word_count=raw_word_count,
            tech_score=calculated_tech_score,
            stt_text=answer_text,
            llm_weakness_tags=llm_weakness_tags
        )
        logger.info(f"🔧 강점 태그 {len(deterministic_tags['strengths'])}개 / 약점 태그 {len(deterministic_tags['weaknesses'])}개 트리거 완료.")

        # 8. 필러워드 검출량에 따른 동적 코멘트 스위칭 핸들러
        total_fillers = dysfluency_res.get("total_filler_count", 0)
        if total_fillers <= 2:
            speech_comment = f"발화 대비 필러워드 비율이 매우 안정적입니다. (총 {total_fillers}회 포착)"
        elif total_fillers <= 6:
            speech_comment = f"발화 대비 필러워드 사용이 무난한 편이나 다소 정돈이 필요합니다. (총 {total_fillers}회 포착)"
        else:
            speech_comment = f"발화 중 무의식적인 간투사가 자주 반복되어 전달력이 저하될 우려가 있습니다. (총 {total_fillers}회 포착)"

        pipeline_duration = time.time() - pipeline_start_time
        logger.info(f"==================== 🎉 PIPELINE SUCCESS (총 소요시간: {pipeline_duration:.3f}s) ====================")

        # 9. 최종 데이터 패널 마샬링 리턴
        return EvaluationMasterResult(
            score_summary={
                "overall_score": overall_score,
                "metrics": final_metrics
            },
            score_detail={
                "bei_logic": {
                    "regex_filter_passed": char_count >= 150,
                    "raw_word_count": raw_word_count,
                    "star_segmentation": {k: v.get("desc", "") for k, v in bei_star.items()}
                },
                "cbi_competency": competency_res.get("cbi_competency", {}),
                "speech_delivery": {
                    "filler_word_analysis": speech_comment
                }
            },
            dynamically_triggered_tags=deterministic_tags
        )