# llm/client.py
import os
from openai import OpenAI
from dotenv import load_dotenv  # <-- dotenv 모듈 가져오기

# 1. 현재 디렉토리 및 상위 디렉토리의 .env 파일을 자동으로 탐색하여 로드
load_dotenv()

# 2. os.getenv를 통해 시스템 환경 변수에 등록된 값을 안전하게 매핑
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# 3. 만약 키 값이 제대로 로드되지 않았다면 사전에 밸리데이션 에러 발생 (디버깅 용이)
if not OPENAI_API_KEY:
    raise ValueError(
        "❌ [에러] .env 파일에서 'OPENAI_API_KEY'를 찾을 수 없습니다.\n"
        "파일 이름이 정확히 '.env'인지, 혹은 프로젝트 루트 경로에 위치해 있는지 확인하세요."
    )

# 4. 검증된 키로 OpenAI 클라이언트 초기화
client = OpenAI(api_key=OPENAI_API_KEY)