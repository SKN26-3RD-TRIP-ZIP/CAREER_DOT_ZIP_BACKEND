# Career.zip 실제 데이터 기반 통합 E2E QA 결과 보고서 (템플릿)

> 실행 회차: ___회차 · 실행일: ____-__-__ · 실행자: ______ · 대상 커밋: `________`
> AI 엔진 모드: [ ] mock  [ ] openai(real)  ·  평가 OpenAI 키: [ ] 사용가능 [ ] 없음
> ⚠️ 비밀번호/토큰/쿠키/인증코드 값 기록 금지

## 0. 요약 스코어보드

| 분류 | 개수 | 비고 |
|---|---|---|
| PASS | | |
| FAIL | | |
| BLOCKED | | |
| NEEDS_CONFIRMATION | | |
| NOT_IMPLEMENTED | | |
| MOCK_ONLY | | |

## 1. 현재 실행 가능 여부 요약
- 서버 기동:
- 마이그레이션:
- 인증 흐름 진입 가능 여부(verify-email 블로커 포함):
- 실제 AI 호출 가능 여부:

## 2. 실제 데이터 연결 상태
| 영역 | 상태(real/mock/NI) | 근거 | 비고 |
|---|---|---|---|
| 질문 생성 | | 기본 mock 엔진 | env 전환 시 real |
| 꼬리질문/적절성 | | mock | |
| 평가/태그 | | OpenAI 직접 호출 | 키/쿼터 |
| 리포트 | | 평가 기반 | |
| 문서 업로드 파싱 | | extract_text_from_document | |
| JD 분석/매칭 | | 임베딩+Pinecone | project_service 일부 미구현 |
| STT 적재 | | 클라 텍스트 저장 | 음성엔진 없음 |
| Worknet 채용 | | Open API | |

## 3. 계정별 QA 시나리오 결과 요약
| 계정 | 사용자 | 핵심 흐름 | PASS | FAIL | BLOCKED/기타 | 메모 |
|---|---|---|---|---|---|---|
| parksoyun9084 | 박소윤 | 가입~리포트~마이페이지 | | | | |
| jykim4169 | 김지윤 | OAuth/voice/STT/꼬리질문 | | | | |
| h2yoon423 | 홍지윤 | 분석/매칭/리포트/관리자대조 | | | | |
| tripdotzip | 관리자 | 회원/프롬프트/audit/권한 | | | | |

## 4. 발견한 mock 잔존 지점
| 위치 | 내용 | real 전환 조건 | 상태 |
|---|---|---|---|
| `apps/interview/services/ai_chain_mock_engine.py` | 질문/꼬리질문/적절성 mock | env openai+real_call | MOCK_ONLY |
| `ai_chain_openai_engine.py` | 실패 시 mock fallback | - | 확인 |
| | | | |

## 5. API 명세 불일치
| 명세 경로 | 실제 경로 | 차이 | 상태 |
|---|---|---|---|
| `POST /jds/upload` | `POST /documents/upload` | 전용 업로드 경로 부재 | NEEDS_CONFIRMATION |
| `POST /jds/{id}/analyze` | `POST /analysis/analyze/` | 분석 경로 분리 | NEEDS_CONFIRMATION |
| `POST /jds/{id}/match` | `POST /analysis/match/` | 명세 미확정 | NEEDS_CONFIRMATION |
| `POST /resumes/upload` | `POST /documents/upload` | 전용 업로드 경로 부재 | NEEDS_CONFIRMATION |
| `GET /auth/verify-email` | (없음) | 미구현 | NOT_IMPLEMENTED |
| `POST /auth/logout` | (없음) | 미구현 | NOT_IMPLEMENTED |
| 구글 로그인 | (없음) | 백엔드 OAuth 미구현 | NOT_IMPLEMENTED |
| 면접 세션 API | 중첩형/MVP 평면형 2벌 | 정식 표면 미확정 | NEEDS_CONFIRMATION |
| 타 사용자 자원 접근 | 404 반환 | 명세가 403이면 불일치 | 확인 |

## 6. 프론트/백엔드 오류
| ID | 위치 | 증상 | 재현 | 심각도 | 비고 |
|---|---|---|---|---|---|
| | | | | | |

## 7. 보안 / 개인정보 위험
| 항목 | 위험도 | 내용 | 조치 |
|---|---|---|---|
| 원격 공유 MySQL 사용 | 중 | 로컬 QA가 Aiven 공유 DB에 쓰기 | QA 식별자/별도 스키마 검토 |
| `.env` 커밋 여부 | ? | .gitignore 확인 필요 | 점검 |
| refresh cookie `secure=False` | 중 | prod 전 True 전환 필요 | 배포 전 수정 |
| | | | |

## 8. 수정 필요 우선순위
| 순위 | 항목 | 분류 | 사유 |
|---|---|---|---|
| P0 | verify-email 또는 가입 후 verified 처리 | NI | 미해결 시 로그인 불가 |
| P0 | 면접 세션 API 표면(중첩 vs MVP) 확정 | NC | E2E 기준 결정 필요 |
| P1 | JD upload/analyze/match 경로 명세 정합 | NC | 프론트 연동 영향 |
| P1 | 구글 OAuth 처리 주체 명확화 | NI | 시나리오 전제 |
| P2 | refresh cookie secure 배포 설정 | 보안 | 배포 전 |
| P2 | analysis project_service 미구현 | NI | 매칭 정확도 |

## 9. 테스트 실행 명령어
```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
pytest
pytest apps/interview apps/evaluation apps/input
```

## 10. PR에 넣을 작업 내용 / 11. 팀 공유 메시지
(qa-plan / PR 설명 참조)

---

# 📌 v2.0 — 차단 해제 전 스코어보드 (현시점 사전판정)

## 0b. 현시점 분류 (실행 전, 코드 분석 기준)
| 분류 | 대표 항목 |
|---|---|
| PASS(실행필요) | signup, login(seed후), token/refresh, 입력/세션/리포트 라우트 존재 |
| FAIL | (실행 전 미확정) |
| BLOCKED | 로그인 이후 전 기능(토큰·사용자 데이터 부재): 프로필~면접~평가~리포트~마이페이지~관리자 |
| NEEDS_CONFIRMATION | 면접 API 이중표면, JD analyze/match·upload 경로, 원격 vs QA DB, AWS/Actions |
| NOT_IMPLEMENTED | verify-email, logout, 비번재설정, Google OAuth, 가입환영/관리자알림/인증 메일, Swagger, 회원탈퇴(확인) |
| MOCK_ONLY | 질문/꼬리질문/적절성(mock 엔진 기본), FE 사용자 흐름 대부분(SaaSPrototype), TTS(브라우저) |

## 12. 메일 검증 결과 (신규)
| 메일 | 발송됨 | 수신확인 | 민감정보 미포함 | 비고 |
|---|---|---|---|---|
| 가입 환영 | | | | |
| 관리자 신규가입 알림 | | | | |
| 이메일 인증 | | | | |
| 비밀번호 재설정 | | | | |
