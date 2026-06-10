# apps/evaluation/evaluation_chains.py
import json
from concurrent.futures import ThreadPoolExecutor
from django.conf import settings
from openai import OpenAI
from .evaluation_prompts import (
    EVAL_GROUNDING_SYSTEM_PROMPT,
    EVAL_COMPETENCY_SYSTEM_PROMPT,
    EVAL_COMPETENCY_FORMAT_PROMPT
)

# 💡 4번 요구사항 반영: Django settings 중심의 안전한 초기화
openai_key = getattr(settings, "OPENAI_API_KEY", None)
client = OpenAI(api_key=openai_key)

# evaluation_chains.py 예시
def fetch_grounding(answer_text: str) -> dict:
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": EVAL_GROUNDING_SYSTEM_PROMPT},
                {"role": "user", "content": answer_text}
            ],
            timeout=15.0 # 무한 대기 방지 타임아웃 설정 추천
        )
        return json.loads(res.choices[0].message.content)
    except Exception as e:
        # 서비스 정책에 따른 Fallback 데이터 반환 혹은 raise
        return {
            "tech_stack": "확인 불가",
            "before_metric": "확인 불가",
            "after_metric": "확인 불가",
            "is_grounded": False
        }

import json
import logging

logger = logging.getLogger("feedback_ai.evaluation_chains")

def fetch_competency(answer_text: str) -> dict:
    full_system = f"{EVAL_COMPETENCY_SYSTEM_PROMPT}\n\n{EVAL_COMPETENCY_FORMAT_PROMPT}"
    
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": full_system},
                {"role": "user", "content": answer_text}
            ],
            timeout=15.0  # 외부 API 무한 대기 방지를 위한 타임아웃 설정 권장
        )
        return json.loads(res.choices[0].message.content)
        
    except Exception as e:
        # 에러 로그를 남겨 추적할 수 있도록 합니다.
        logger.error(f"OpenAI fetch_competency failed: {str(e)}", exc_info=True)
        
        # 💡 Fallback 처리: 서비스가 터지지 않도록 기본 규격의 딕셔너리를 반환합니다.
        return {
            "bei_star": {
                "situation": {
                    "desc": "OpenAI 연결 실패로 상황 평가를 진행하지 못했습니다.",
                    "score": 0,
                },
                "task": {
                    "desc": "OpenAI 연결 실패로 과제 평가를 진행하지 못했습니다.",
                    "score": 0,
                },
                "action": {
                    "desc": "OpenAI 연결 실패로 행동 평가를 진행하지 못했습니다.",
                    "score": 0,
                },
                "result": {
                    "desc": "OpenAI 연결 실패로 결과 평가를 진행하지 못했습니다.",
                    "score": 0,
                },
            },
            "cbi_competency": {
                "assigned_level": 0,
                "score": 0,
                "evidence_sentence": "OpenAI 연결 실패로 역량 평가를 진행하지 못했습니다.",
            },
            "llm_weakness_tags": [],
        }

def eval_grounding_chain(answer_text: str) -> dict:
    """뷰가 동기식이므로 내부 유선 풀에서 안전하게 스레드 병열 구동하여 대기 단축"""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fetch_grounding, answer_text)
        return future.result()

def eval_competency_chain(answer_text: str) -> dict:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fetch_competency, answer_text)
        return future.result()