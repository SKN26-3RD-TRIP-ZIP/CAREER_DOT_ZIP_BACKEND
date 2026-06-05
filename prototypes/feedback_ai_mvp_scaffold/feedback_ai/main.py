# prototypes/feedback_ai_mvp_scaffold/feedback_ai/main.py

import sys
from pathlib import Path

# 💡 현재 파일(main.py)의 위치를 기준으로 CAREER_DOT_ZIP_BACKEND 폴더 경로를 찾아 sys.path에 주입
# main.py에서 위로 3번 올라가면 CAREER_DOT_ZIP_BACKEND 폴더가 나옵니다.
backend_root = str(Path(__file__).resolve().parents[3])
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

import asyncio
import json
import logging
from services.evaluation_service import EvaluationService

# 로깅 설정
logger = logging.getLogger("feedback_ai.main")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")

# 현재 main.py 파일의 위치를 기준으로 data 폴더 경로 추적
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

async def run_session_test(file_name: str):
    """지정한 JSON 파일을 읽어와 파이프라인 시뮬레이션을 수행합니다."""
    file_path = DATA_DIR / file_name
    
    # 1. JSON 파일 존재 여부 팩트 체크
    if not file_path.exists():
        logger.error(f"❌ Mock 데이터 파일을 찾을 수 없습니다: {file_path}")
        return

    # 2. JSON 데이터 파일 로드
    with open(file_path, "r", encoding="utf-8") as f:
        session_data = json.load(f)
        
    session_id = session_data["session_id"]
    target_role = session_data["evaluation_target"]
    
    print("\n" + "=" * 70)
    print(f"🎬 [SESSION START] {session_id} ({target_role} 직무) - 파일명: {file_name}")
    print("=" * 70)

    # 3. 세션 내부의 면접 질문-답변 플로우(interview_flow) 순회 처리
    for block in session_data["interview_flow"]:
        answer_id = block.get("answer_id") or block.get("client_question_key")
        answer_text = block["stt_text"]
        
        # 💡 evaluation_service.py 규격 스펙에 맞게 데이터 추출 및 매핑
        question_type = block.get("question_type", "technical") # 스펙 상의 question_type 추출
        sufficiency_data = block.get("answer_sufficiency", {})
        llm_weakness_tags = sufficiency_data.get("answer_weakness_tags", []) # 약점 태그 리스트 추출
        
        logger.info(f"▶️ [파이프라인 구동] session: {session_id} | answer_id: {answer_id}")

        # 4. evaluation_service 엔진 가동 (엔진의 실제 파라미터 스펙과 100% 동기화)
        result_jsonb = await EvaluationService.run_pipeline(
            answer_text=answer_text,
            question_type=question_type,
            long_pause_count=0, # 기본값 세팅
            llm_weakness_tags=llm_weakness_tags
        )
        
        # 5. 각 문항별 규칙 라우터 최종 산출 결과 모니터링
        print(f"\n✅ [PostgreSQL 테이블 적재 완료] answer_id: {answer_id}")
        print(f"   - 최종 산출 점수 (overall_score): {result_jsonb.score_summary['overall_score']}점")
        print(f"   - 강점 태그 수: {len(result_jsonb.dynamically_triggered_tags.strengths)}개")
        print(f"   - 약점 태그 수: {len(result_jsonb.dynamically_triggered_tags.weaknesses)}개")
        print("-" * 70)

    print(f"🏁 [SESSION END] {session_id} 모든 문항 순회 및 시뮬레이션 종료\n")


async def main():
    print("\n==========================================================")
    print("🚀 data/ 폴더 내 JSON Mock 파일 기반 자동화 파이프라인 테스트")
    print("==========================================================")

    # 테스트를 돌리고 싶은 json 파일 목록 정의
    target_files = ["sess_001.json", "sess_002.json", "sess_003.json"]
    
    for file_name in target_files:
        await run_session_test(file_name)

if __name__ == "__main__":
    asyncio.run(main())