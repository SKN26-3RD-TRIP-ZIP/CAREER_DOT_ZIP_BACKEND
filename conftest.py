import os
from pathlib import Path
from dotenv import load_dotenv

# 루트의 .env.local → .env 순으로 로드 (테스트 실행 전 환경변수 세팅)
_base = Path(__file__).parent
load_dotenv(_base / ".env.local", override=False)
load_dotenv(_base / ".env", override=False)
