# Interview AI MVP Scaffold

AI 모의면접 시스템의 **질문 생성 / 꼬리질문 생성 / 평가 결과 연동** 흐름을 본격 구현 전에 독립적으로 검증하기 위한 POC 스캐폴드입니다.

현재 코드는 최종 서비스 코드가 아니라, 핵심 기능의 동작 가능성과 출력 구조를 검증하기 위한 실험용 코드입니다.

---

## 1. 목적

이 POC의 목적은 다음과 같습니다.

- 이력서 / 자소서 / JD 기반 면접 질문 생성 가능성 검증
- 면접관 페르소나별 질문 생성 차이 확인
- 사용자 답변 기반 꼬리질문 생성 검증
- 평가 결과 기반 꼬리질문 생성 구조 검증
- Pydantic schema를 활용한 LLM 출력 검증
- mock mode / 실제 LLM mode 동시 지원
- 추후 Django backend 통합 전 AI 로직 구조 사전 검증

---

## 2. 현재 구현 범위

### 질문 생성

- 문서 직접 입력형 A안 구현
- 이력서 / 자소서 / JD 기반 질문 생성
- 신입 / 이직자 조건 반영
- 전공자 / 비전공자 조건 반영
- 면접관 페르소나 조건 반영
- JD 연결 질문 생성 강화
- question_type, source_type, expected_keywords 포함

### 꼬리질문 생성

- 질문 + 답변 기반 꼬리질문 생성
- weakness_tags / missing_keywords 기반 꼬리질문 생성
- 페르소나별 꼬리질문 스타일 반영
- 최대 꼬리질문 개수 제한

### 평가 결과 연동

- evaluation_result 기반 꼬리질문 생성
- AnswerEvaluationResult schema 검증
- weaknesses / missing_keywords / weakness_tags 추출
- evaluation_link 포함

### 테스트 및 검증

- mock mode 테스트
- 실제 LLM mode 테스트
- 사용자 mock 3종 테스트
- 페르소나 3종 비교 테스트
- JD 연결성 강화 테스트
- 평가 결과 기반 꼬리질문 테스트

---

## 3. 폴더 구조

```text
interview_ai_mvp_scaffold/
├─interview_ai/
│  ├─chains/
│  │  ├─question_generation_chain.py
│  │  └─followup_generation_chain.py
│  │
│  ├─data/
│  │  ├─mock_interview_data.py
│  │  ├─personas.py
│  │  ├─weakness_tags.py
│  │  ├─fallback_questions.py
│  │  └─interview_taxonomy.py
│  │
│  ├─llm/
│  │  └─openai_client.py
│  │
│  ├─prompts/
│  │  ├─question_generation_prompt.py
│  │  └─followup_generation_prompt.py
│  │
│  ├─schemas/
│  │  ├─question_schema.py
│  │  ├─followup_schema.py
│  │  └─evaluation_schema.py
│  │
│  ├─services/
│  │  └─interview_service.py
│  │
│  ├─utils/
│  │  └─json_parser.py
│  │
│  └─validators/
│     └─quality_rules.py
│
├─docs/
│  ├─sample_api_response.md
│  └─interview_ai_taxonomy.md
│
├─tests/
│  └─test_schemas.py
│
├─run_mock_test.py
├─run_llm_test.py
├─run_service_test.py
├─run_llm_quality_check.py
├─run_persona_quality_check.py
├─run_evaluation_followup_test.py
├─requirements.txt
├─.env.example
└─README.md
```

---

## 4. 실행 전 준비

### 패키지 설치

```bash
pip install -r requirements.txt
```

### 환경 변수 설정

`.env.example`을 참고하여 `.env` 파일을 생성합니다.

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
```

주의: `.env` 파일은 GitHub에 올리지 않습니다.

---

## 5. 실행 방법

### 5-1. mock mode 기본 테스트

API 키 없이 질문 생성 / 꼬리질문 생성 흐름을 확인합니다.

```bash
python run_mock_test.py
```

### 5-2. 실제 LLM 단일 테스트

OpenAI API를 사용해 질문 생성 / 꼬리질문 생성을 테스트합니다.

```bash
python run_llm_test.py
```

### 5-3. service layer 테스트

Django View에서 호출할 service 함수 형태로 동작하는지 확인합니다.

```bash
python run_service_test.py
```

### 5-4. LLM 품질 점검

user_001, user_002, user_003 세 케이스에 대해 실제 LLM 질문 생성 품질을 확인합니다.

```bash
python run_llm_quality_check.py
```

결과는 `outputs/` 폴더에 저장됩니다.

### 5-5. 페르소나 비교 테스트

동일 사용자 입력에 대해 coach / practical / critical 페르소나별 질문 차이를 확인합니다.

```bash
python run_persona_quality_check.py
```

기본값은 `user_001`입니다.

다른 사용자로 테스트하려면 PowerShell 기준:

```powershell
$env:PERSONA_TEST_USER_ID="user_003"
python run_persona_quality_check.py
```

### 5-6. 평가 결과 기반 꼬리질문 테스트

평가 결과의 weakness_tags / missing_keywords가 꼬리질문 생성에 연결되는지 확인합니다.

mock mode:

```bash
python run_evaluation_followup_test.py
```

LLM mode:

```powershell
$env:EVALUATION_FOLLOWUP_MODE="llm"
python run_evaluation_followup_test.py
```

---

## 6. 주요 데이터 구조

### QuestionGenerationResult

```json
{
  "session_id": "session_001",
  "user_id": "user_001",
  "persona_id": "practical",
  "questions": [
    {
      "question_id": "q_001",
      "question": "Django를 선택한 이유와 프로젝트에 기여한 점을 설명해 주세요.",
      "question_type": "technical_reasoning",
      "source_type": "resume_jd",
      "source_summary": "이력서 경험과 JD 요구사항을 연결한 질문",
      "difficulty": "medium",
      "intent": "기술 선택 이유와 직무 적합성을 확인",
      "expected_keywords": ["Django", "API", "기술 선택"]
    }
  ]
}
```

### FollowUpGenerationResult

```json
{
  "question_id": "q_001",
  "follow_ups": [
    {
      "follow_up_id": "fu_001",
      "question_id": "q_001",
      "follow_up_question": "FastAPI와 비교했을 때 Django를 선택한 기준은 무엇이었나요?",
      "follow_up_type": "technical_reasoning",
      "trigger_reason": "기술 선택 이유와 대안 비교가 부족했기 때문에",
      "based_on_weakness_tags": ["weak_technical_reasoning"]
    }
  ]
}
```

### Evaluation Result 연동

```json
{
  "evaluation_id": "eval_001",
  "question_id": "q_001",
  "answer": "사용자 답변",
  "score": 3,
  "strengths": ["잘한 점"],
  "weaknesses": ["보완할 점"],
  "missing_keywords": ["대안 비교", "트레이드오프"],
  "weakness_tags": ["weak_technical_reasoning", "lack_of_specificity"]
}
```

---

## 7. 공통 분류 기준

공통 분류 기준은 아래 파일에 정리되어 있습니다.

```text
interview_ai/data/interview_taxonomy.py
docs/interview_ai_taxonomy.md
```

현재 MVP 기준 주요 분류는 다음과 같습니다.

### Question Type

- `project_experience`
- `technical_reasoning`
- `contribution_check`
- `problem_solving`
- `job_fit`
- `collaboration`
- `growth_learning`
- `fallback`

### Follow-up Type

- `specificity_check`
- `technical_reasoning`
- `contribution_check`
- `result_check`
- `job_fit_check`
- `problem_solving_deepening`
- `answer_structure`

### Weakness Tag

- `lack_of_specificity`
- `weak_technical_reasoning`
- `unclear_contribution`
- `missing_result`
- `weak_job_fit`
- `shallow_problem_solving`
- `missing_keywords`
- `unstructured_answer`

---

## 8. 현재 검증 결과 요약

현재까지의 테스트 결과는 다음과 같습니다.

- mock 기반 질문 생성 성공
- 실제 LLM 기반 질문 생성 성공
- JD 연결성 강화 후 `resume_jd`, `jd` 기반 질문 생성 확인
- 페르소나별 질문 차이 확인
- 페르소나별 꼬리질문 차이 일부 확인
- 평가 결과 기반 꼬리질문 생성 mock / LLM mode 성공
- Pydantic schema 검증 통과
- 한국어 요청형 질문 문장 처리 개선

---

## 9. 현재 판단

A안인 **문서 직접 입력형 질문 생성 방식**은 MVP 기준으로 유지 가능합니다.

다만 최종 고도화 단계에서는 아래 개선을 고려합니다.

- 핵심 정보 추출 Chain 추가
- JD 요구 역량 추출 Chain 추가
- 질문 유형 비율 제어
- 페르소나별 질문 비율 관리
- 평가 결과와 최종 리포트 연동 강화
- weakness_tags 기반 약점 분석 고도화

---

## 10. Git 관리 주의사항

아래 파일 및 폴더는 GitHub에 올리지 않습니다.

```gitignore
.env
**/.env
__pycache__/
**/__pycache__/
*.pyc
.pytest_cache/
outputs/
**/outputs/
```

`outputs/`에는 LLM 실행 결과 JSON이 저장되므로, 원본 파일은 GitHub에 올리지 않고 Notion 또는 문서로 요약해서 관리합니다.

---

## 11. 추후 통합 방향

현재 코드는 POC 스캐폴드이므로 본 구현 단계에서 Django backend 구조에 맞게 통합합니다.

예상 통합 위치:

```text
interview_ai/chains      → backend/apps/interview/services 또는 backend/apps/analysis/services
interview_ai/services    → backend/apps/interview/services
interview_ai/prompts     → backend/prompts/interview
interview_ai/schemas     → backend/apps/interview/schemas 또는 DRF serializer로 변환
interview_ai/data        → backend/fixtures 또는 constants
```

---

## 12. 참고

이 POC는 AI 면접관 파트의 핵심 기능을 빠르게 검증하기 위한 실험 코드입니다.

본 서비스 구현 시에는 팀의 Django API 구조, DB 모델, 프론트엔드 요청/응답 구조에 맞춰 리팩토링이 필요합니다.
