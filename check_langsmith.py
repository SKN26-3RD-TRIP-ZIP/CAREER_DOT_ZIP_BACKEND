import os
import sys
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.analysis.services.utils import get_client

print("=== LangSmith 설정 확인 ===")
print(f"LANGCHAIN_TRACING_V2 : {os.environ.get('LANGCHAIN_TRACING_V2')}")
print(f"LANGCHAIN_PROJECT    : {os.environ.get('LANGCHAIN_PROJECT')}")
print(f"LANGCHAIN_API_KEY    : {os.environ.get('LANGCHAIN_API_KEY', '')[:20]}...")

print("\n=== 테스트 LLM 호출 (LangSmith 트레이스 확인용) ===")
client = get_client()
resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "ping, reply with pong only"}],
    max_tokens=5,
)
print(f"응답: {resp.choices[0].message.content}")
print("\n위 호출이 LangSmith에 기록됐는지 확인하세요.")
print("→ https://smith.langchain.com  프로젝트: career-dot-zip")
