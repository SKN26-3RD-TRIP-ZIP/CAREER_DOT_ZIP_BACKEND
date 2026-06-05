import json
import asyncio
from llm.client import client
from prompts.evaluation_prompts import (
    EVAL_GROUNDING_SYSTEM_PROMPT,
    EVAL_COMPETENCY_SYSTEM_PROMPT,
    EVAL_COMPETENCY_FORMAT_PROMPT
)

async def eval_grounding_chain(answer_text: str) -> dict:
    """[Task B] Fast LLM Chain - 외부 프롬프트를 참조하여 실무 경험 구체성 지표 추출"""
    
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": EVAL_GROUNDING_SYSTEM_PROMPT}, 
            {"role": "user", "content": answer_text}
        ]
    ))
    return json.loads(res.choices[0].message.content)


async def eval_competency_chain(answer_text: str) -> dict:
    """[Task C] Deep LLM Chain - 외부 마스터 가이드라인과 포맷 프롬프트를 조립하여 분석"""
    
    # 시스템 가이드라인과 JSON 출력 형식을 유기적으로 결합
    full_system_prompt = f"{EVAL_COMPETENCY_SYSTEM_PROMPT}\n\n{EVAL_COMPETENCY_FORMAT_PROMPT}"

    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: client.chat.completions.create(
        model="gpt-4o",  # 심층 분석용 고성능 모델 유지
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": full_system_prompt},
            {"role": "user", "content": answer_text}
        ]
    ))
    return json.loads(res.choices[0].message.content)