# interview_ai MVP Scaffold

AI 모의면접 시스템의 질문 생성/꼬리질문 생성 파트를 독립적으로 테스트하기 위한 미니 프로젝트입니다.

## 목적

- DB/API 연동 전 mock data로 AI 흐름 검증
- 질문 생성 결과 JSON 구조 검증
- 꼬리질문 결과 JSON 구조 검증
- mock 모드와 실제 LLM 모드를 같은 interface로 실행
- FE/BE 공유용 응답 예시 정리

## 폴더 구조

```text
interview_ai_mvp_scaffold/
├── interview_ai/
│   ├── schemas/
│   │   ├── question_schema.py
│   │   ├── followup_schema.py
│   │   └── evaluation_schema.py
│   ├── data/
│   │   ├── mock_interview_data.py
│   │   ├── personas.py
│   │   ├── weakness_tags.py
│   │   └── fallback_questions.py
│   ├── prompts/
│   │   ├── question_generation_prompt.py
│   │   └── followup_generation_prompt.py
│   ├── chains/
│   │   ├── question_generation_chain.py
│   │   └── followup_generation_chain.py
│   ├── validators/
│   │   └── quality_rules.py
│   ├── llm/
│   │   └── openai_client.py
│   ├── utils/
│   │   └── json_parser.py
│   └── config.py
├── docs/
│   └── sample_api_response.md
├── tests/
│   └── test_schemas.py
├── run_mock_test.py
├── run_llm_test.py
├── requirements.txt
├── .env.example
└── README.md
```

## 1. Mock 모드 실행

API 키 없이 바로 실행 가능합니다.

```bash
pip install -r requirements.txt
python run_mock_test.py
pytest
```

## 2. 실제 LLM 모드 실행

`.env.example`을 복사해서 `.env` 파일을 만듭니다.

```bash
cp .env.example .env
```

`.env`에 API 키를 입력합니다.

```text
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
```

실행합니다.

```bash
python run_llm_test.py
```

## 현재 구현 범위

- Pydantic schema 검증
- mock 기반 질문 생성 A안
- mock 기반 꼬리질문 생성 A안
- 실제 OpenAI LLM 연결 구조
- LLM 응답 JSON 파싱
- missing_fields fallback 질문 생성
- 간단한 rule-based 품질 검증

## 다음 구현 후보

- 질문 생성 실패 시 retry
- Pydantic 검증 실패 시 fallback
- 핵심 정보 추출 Chain 추가
- 평가 결과 weakness_tags 기반 꼬리질문 고도화
- Django API view 연결
