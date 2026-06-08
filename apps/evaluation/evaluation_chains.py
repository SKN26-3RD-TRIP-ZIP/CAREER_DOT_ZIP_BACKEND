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

def fetch_grounding(answer_text: str) -> dict:
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": EVAL_GROUNDING_SYSTEM_PROMPT},
            {"role": "user", "content": answer_text}
        ]
    )
    return json.loads(res.choices[0].message.content)

def fetch_competency(answer_text: str) -> dict:
    full_system = f"{EVAL_COMPETENCY_SYSTEM_PROMPT}\n\n{EVAL_COMPETENCY_FORMAT_PROMPT}"
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": full_system},
            {"role": "user", "content": answer_text}
        ]
    )
    return json.loads(res.choices[0].message.content)

def eval_grounding_chain(answer_text: str) -> dict:
    """뷰가 동기식이므로 내부 유선 풀에서 안전하게 스레드 병열 구동하여 대기 단축"""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fetch_grounding, answer_text)
        return future.result()

def eval_competency_chain(answer_text: str) -> dict:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fetch_competency, answer_text)
        return future.result()