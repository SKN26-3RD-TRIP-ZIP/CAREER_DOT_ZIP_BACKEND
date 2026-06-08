import re
import logging
import time
from datetime import datetime
from kiwipiepy import Kiwi

# 💡 동기식으로 매핑된 기존 파일 및 외부 유틸 반입
from evaluation_chains import eval_grounding_chain, eval_competency_chain
from apps.evaluation.utils.tag_router import route_deterministic_tags
from apps.evaluation.models import StrengthTag, WeaknessTag, AnswerStrengthTag, AnswerWeaknessTag
from .config import SPEECH_CONFIG  # 설정 파일 반입 (팀원 환경 경로에 맞게 상대 참조)

# 로거 정의
logger = logging.getLogger("feedback_ai.evaluation_service")

kiwi = Kiwi()
FILLER_WORDS = [["어", "음", "그니까", "사실", "이제", "저기"]]


class EvaluationService:

    @staticmethod
    def analyze_dysfluency_local(stt_text: str, long_pause_count: int = 0) -> dict:
        """[Task A] 로컬 비유창성 분석 (원본 알고리즘 100% 보존)"""
        logger.info("=== [Task A] 로컬 비유창성 분석 시작 ===")
        start_time = time.time()
        
        filler_counts = {}
        total_filler = 0
        for word in FILLER_WORDS[0]:
            count = len(re.findall(rf'\b{word}\b|{word}\.+', stt_text))
            if count > 0:
                filler_counts[word] = count
                total_filler += count

        tokens = [t.form for t in kiwi.tokenize(stt_text)]
        repetition_scans = []
        for i in range(len(tokens) - 1):
            if tokens[i] == tokens[i+1] and len(tokens[i]) > 1:
                repetition_scans.append(tokens[i])

        duration = time.time() - start_time
        logger.info(f"[Task A 완료] 필러워드: {total_filler}회, 중복 발화: {len(repetition_scans)}건 검출 (소요시간: {duration:.3f}s)")
        
        return {
            "filler_word_counts": filler_counts,
            "total_filler_count": total_filler,
            "long_pause_count": long_pause_count,
            "repetitions": repetition_scans,
            "is_sentence_incomplete": False
        }

    @staticmethod
    def run_pipeline(answer_text: str, question_type: str = "technical", long_pause_count: int = 0, llm_weakness_tags: list = None) -> dict:
        """
        하이브리드 비동기 분기 병렬 처리 통합 파이프라인 마스터 매니저
        """
        pipeline_start_time = time.time()
        logger.info(f"==================== 🚀 EVALUATION PIPELINE RUN (타입: {question_type}) ====================")

        # 1. 인풋 데이터 기초 밸리데이션 검사
        char_count = len(answer_text)
        word_count = len(answer_text.split())
        logger.info(f"[인풋 데이터 검증] 글자 수: {char_count}자, 공백 기준 단어 수: {word_count}개")

        # 2. [Task A] 로컬 비유창성 언어분석 엔진 구동
        dysfluency_res = EvaluationService.analyze_dysfluency_local(answer_text, long_pause_count)

        # 3. [Django 동기화 개편]: 아키텍처 흐름에 맞춰 LLM 체인을 순차적으로 동기 호출 실행
        logger.info("📡 외부 LLM 동기 오케스트레이션(Task B & Task C) 순차 호출 시작...")
        
        # [Task B] 구체성 검증 체인 동기 호출
        grounding_res = eval_grounding_chain(answer_text)
        
        # [Task C] 역량 채점 루브릭 체인 동기 호출
        cbi_res = eval_competency_chain(answer_text)
        
        logger.info("📡 LLM 체인 응답 수신 완료")

        # 4. [정성 지표 정산 레이어] (원본 스코어링 공식 완벽 유지)
        bei_star = cbi_res.get("bei_star_rating", {})
        situation_score = bei_star.get("situation", {}).get("score", 0)
        task_score = bei_star.get("task", {}).get("score", 0)
        action_score = bei_star.get("action", {}).get("score", 0)
        result_score = bei_star.get("result", {}).get("score", 0)
        
        bei_total = situation_score + task_score + action_score + result_score
        
        cbi_level = cbi_res.get("cbi_competency_level", {}).get("assigned_level", 1)
        cbi_mapped_score = float(cbi_level * 20)

        logger.info(f"[정성 지표 중간 정산] BEI STAR 총합: {bei_total}점, CBI 매핑 레벨: {cbi_level} (환산: {cbi_mapped_score}점)")

        # 5. [정량 지표 감점산 레이어] (Config 상수 결합)
        base_speech_score = SPEECH_CONFIG.get("BASE_SCORE", 100.0)
        penalty_per_count = SPEECH_CONFIG.get("FILLER_PENALTY_PER_COUNT", 5.0)
        floor_score = SPEECH_CONFIG.get("FLOOR_SCORE", 20.0)
        
        total_fillers = dysfluency_res.get("total_filler_count", 0)
        calculated_speech_score = base_speech_score - (total_fillers * penalty_per_count)
        final_speech_score = max(calculated_speech_score, floor_score)

        # 6. [최종 통합 스코어링 라우터] 분기 처리
        if question_type == "technical":
            is_grounded_flag = grounding_res.get("is_grounded", False)
            grounding_premium = 15.0 if is_grounded_flag else 0.0
            
            raw_calc = (bei_total * 0.4) + (cbi_mapped_score * 0.4) + (final_speech_score * 0.2) + grounding_premium
            overall_score = min(round(raw_calc, 1), 100.0)
            logger.info(f"⚙️ [기술면접 스코어링] Premium 가산점 여부: {is_grounded_flag} (+{grounding_premium}점)")
        else:
            raw_calc = (bei_total * 0.5) + (cbi_mapped_score * 0.3) + (final_speech_score * 0.2)
            overall_score = min(round(raw_calc, 1), 100.0)
            logger.info("⚙️ [인성/기타면접 스코어링] 정성 지표 비중 가중치 체계 가동")

        # 7. [규칙 기반 하이브리드 태그 라우팅 엔진]
        deterministic_tags = route_deterministic_tags(
            question_type=question_type,
            bei_star=bei_star,
            cbi_res=cbi_res,
            grounding_res=grounding_res,
            total_filler=total_fillers,
            long_pause_count=long_pause_count,
            raw_word_count=word_count,
            tech_score=overall_score,
            stt_text=answer_text,
            llm_weakness_tags=llm_weakness_tags
        )
        logger.info(f"✨ [태그 라우터 완료] 강점 {len(deterministic_tags['strengths'])}개 / 약점 {len(deterministic_tags['weaknesses'])}개 매핑")

        # 8. 필러워드 빈도에 따른 대시보드 코멘트 서술 핸들러
        if total_fillers <= 2:
            speech_comment = f"발화 대비 필러워드 비율이 매우 안정적입니다. (총 {total_fillers}회 포착)"
        elif total_fillers <= 6:
            speech_comment = f"발화 대비 필러워드 사용이 무난한 편이나 다소 정돈이 필요합니다. (총 {total_fillers}회 포착)"
        else:
            speech_comment = f"발화 중 무의식적인 간투사가 자주 반복되어 전달력이 저하될 우려가 있습니다. (총 {total_fillers}회 포착)"

        pipeline_duration = time.time() - pipeline_start_time
        logger.info(f"==================== 🎉 PIPELINE SUCCESS (소요시간: {pipeline_duration:.3f}s) ====================")

        # 9. [Django DB 맞춤형 마샬링]: Pydantic 스키마 대신 순수 딕셔너리로 마샬링하여 리턴
        return {
            "bei_score": {
                "situation": situation_score,
                "task": task_score,
                "action": action_score,
                "result": result_score,
                "total": bei_total
            },
            "cbi_score": {
                "level": cbi_level,
                "score": cbi_mapped_score,
                "evidence": cbi_res.get("cbi_competency_level", {}).get("evidence_sentence", "")
            },
            "filler_words": {
                "counts": dysfluency_res["filler_word_counts"],
                "total": total_fillers,
                "repetitions": dysfluency_res["repetitions"],
                "comment": speech_comment
            },
            "final_tech_score": int(overall_score),
            "score_detail": {
                "tech_grounding": {
                    "tech_stack": grounding_res.get("tech_stack", "없음"),
                    "before_metric": grounding_res.get("before_metric", "없음"),
                    "after_metric": grounding_res.get("after_metric", "없음"),
                    "is_grounded": grounding_res.get("is_grounded", False)
                },
                "meta": {
                    "char_count": char_count,
                    "word_count": word_count,
                    "evaluated_at": datetime.now().isoformat()
                }
            },
            # 💡 views.py의 트랜잭션 내부에서 루프를 돌며 관계 테이블을 생성하도록 태그 패키징 리스트 첨부
            "pipeline_tags": deterministic_tags
        }