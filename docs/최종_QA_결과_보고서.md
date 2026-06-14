# 최종 QA 결과 보고서

> 기준: BE develop `d1f8d17` / FE develop `918f771` · 작성일 2026-06-14

## 1. QA 목적
최종 발표/시연 전 현재 develop 기준 전체 사용자 흐름의 동작 여부와 운영 준비 상태를 점검한다. 새 기능 추가 없이 검증·문서화하며, 명확한 버그만 최소 수정한다.

## 2. QA 환경
| 항목 | 결과 |
|---|---|
| Backend branch | develop (`d1f8d17`) |
| Frontend branch | develop (`918f771`) |
| Backend DB | SQLite fallback(로컬) / MySQL(운영 `DATABASE_URL`) |
| Backend 자동 테스트 | **BLOCKED** (실행 환경에 Django/deps 미설치 — `.venv`는 Windows) |
| Frontend build | **BLOCKED** (`node_modules` 가 Windows 네이티브 — Linux rollup 바이너리 부재) |
| Browser QA | **코드 레벨 검증** (브라우저 실행 환경 부재 → 런타임은 로컬 재확인 권장) |
| OpenAI real call | disabled 기본(`INTERVIEW_AI_CHAIN_ENGINE`/`..._ENABLE_REAL_CALL` env로 제어, 미설정 시 mock) |
| API Key 노출 | 없음 (코드/문서 모두 키 이름만) |

> 참고: 본 환경(코워크 샌드박스)은 마운트된 Windows 의존성을 실행할 수 없어 자동 테스트/빌드/브라우저 실행이 제약됩니다. 아래 결과는 **코드 정적 검증** 기준이며, 실행 결과는 개발자 PC에서 재확인이 필요합니다.

## 3. 테스트 범위
- 인증(회원가입/6자리 인증/로그인/재발송/세션만료/로그아웃)
- 프로필, JD(직접/Mock/PDF), 이력서(PDF/DOCX), 자소서/프로젝트
- 세션 생성 payload(jd_id/resume_id/cover_letter_id/persona/mode)
- 면접(진행률/저장상태/짧은답변 경고/꼬리질문/이탈방지)
- 리포트(점수/강약점/추천/레이더/PDF)
- 마이페이지(summary/최근 리포트/성장추이/약점TOP3/추천질문)

## 4. Backend 자동 테스트 결과
| 명령 | 결과 | 비고 |
|---|---|---|
| `manage.py check` | BLOCKED | 샌드박스에 Django 미설치(`ModuleNotFoundError: django`) |
| `test apps.accounts` | BLOCKED | 동일 |
| `test apps.input` | BLOCKED | 동일 |
| `test apps.interview` | BLOCKED | 동일 |
| `test apps.report` | BLOCKED | 동일 |
| `test apps.document` | BLOCKED | 동일 |
| `test apps.external` | BLOCKED | 동일 |

- 대체 방안: 개발자 PC(Windows `.venv`)에서 동일 명령 실행. `config/settings.py` 는 `DATABASE_URL` 미설정 시 **SQLite fallback** 이므로 MySQL 없이도 테스트 가능.
- 외부 호출: 면접 엔진 기본 mock(`INTERVIEW_AI_CHAIN_ENGINE=mock` 또는 real call 비활성)으로 실제 OpenAI 호출 미발생 확인 권장.
- 참고: 직전 작업들에서 `apps.accounts`(이메일 인증/last_login/6자리코드) 테스트는 코드상 추가/갱신되어 있음(`tests/test_email_code.py`, `test_email_last_login.py`, `test_auth_recovery.py`).

## 5. Frontend build 결과
| 항목 | 결과 | 비고 |
|---|---|---|
| `npm run build` | BLOCKED | `Cannot find module @rollup/rollup-linux-x64-gnu` (Windows에서 설치된 node_modules) |
| 정적 검증 | PASS | 신규 util `node --check` 통과, import 경로 전부 존재, DemoLayout export 일치, React hook 배치 정상 |

- 대체 방안: 개발자 PC에서 `npm run build` 실행. (필요 시 `node_modules` 재설치)

## 6. 브라우저 수동 QA 결과 (코드 레벨 검증)
> 상태 범례: **PASS(코드)** = 구현·연결 확인됨(런타임 재확인 권장) · **BLOCKED** = 환경상 런타임 확인 불가 · FAIL/DEFERRED 해당 없음

| 번호 | 화면 | 테스트 시나리오 | 기대 결과 | 상태 | 비고(근거) |
|--|--|--|--|--|--|
| 1 | 회원가입 | 가입 제출 | 201 + 인증 안내 | PASS(코드) | `SignupView`+`SignupPage` |
| 2 | 인증 | 6자리 입력 | 인증 완료 | PASS(코드) | `VerifyEmailView`(POST), `VerifyEmailPage` |
| 3 | 인증 | 재발송 | 60초 카운트다운 | PASS(코드) | `VerifyEmailPage` cooldown |
| 4 | 인증 | 미인증 로그인 | 403 + 안내 | PASS(코드) | `LoginSerializer.is_verified`, `getLoginError` |
| 5 | 인증 | 로그인 성공 | `/profile` 이동 | PASS(코드) | `LoginPage` |
| 6 | 인증 | 로그아웃 | 안내 문구 | PASS(코드) | `?logout=1` + LoginPage notice |
| 7 | 인증 | 401/만료 | 로그인 안내 | PASS(코드) | axios `?session=expired` |
| 8 | 프로필 | 등록/수정 | 저장 | PASS(코드) | `profileApi` create/update |
| 9 | JD | 직접 입력 저장 | 생성 | PASS(코드) | `jdApi.createJd` |
| 10 | JD | Mock 공고 저장 | JD 저장 | PASS(코드) | `jobsApi.searchJobs/saveJobAsJd` |
| 11 | JD | PDF 업로드 | 추출/저장 | PASS(코드) | `jdApi.uploadJdPdf` |
| 12 | 이력서 | PDF 업로드 | 추출/저장 | PASS(코드) | `resumeApi.uploadResumeFile` |
| 13 | 이력서 | DOCX 업로드 | 추출/저장 | PASS(코드) | document parser docx 지원 |
| 14 | 문서 | 자소서/프로젝트 선택 | 선택 흐름 | PASS(코드) | `coverLetterApi`, 입력 API |
| 15 | 세션 | jd_id 전달 | payload 포함 | PASS(코드) | `SessionSetupPage` selectedJdId |
| 16 | 세션 | resume_id 전달 | payload 포함 | PASS(코드) | selectedResumeId |
| 17 | 세션 | persona_type 전달 | payload 포함 | PASS(코드) | PERSONA_OPTIONS |
| 18 | 세션 | text/voice 전달 | payload 포함 | PASS(코드) | INTERVIEW_MODE_OPTIONS |
| 19 | 면접 | 질문번호/진행률 | N/M + % 바 | PASS(코드) | VoiceInterviewPage 진행률 바 |
| 20 | 면접 | 답변 저장 상태 | 저장중/완료 | PASS(코드) | `저장 중...`/성공 메시지 |
| 21 | 면접 | 짧은 답변 경고 | 경고(저장 허용) | PASS(코드) | <20자 경고 |
| 22 | 면접 | 꼬리질문 표시 | 표시+안내 | PASS(코드) | follow-up + 안내 문구 |
| 23 | 면접 | 이탈 방지 | 확인창 | PASS(코드) | `beforeunload` |
| 24 | 리포트 | 종합 점수 | 표시 | PASS(코드) | `getOverallScore` fallback |
| 25 | 리포트 | 강/약점/추천 | 표시 | PASS(코드) | FinalReportPage |
| 26 | 리포트 | 역량 레이더 | 표시 | PASS(코드) | RadarChart(카드 유지) |
| 27 | 리포트 | PDF 저장 | 인쇄 버튼 | PASS(코드) | `window.print()` + print CSS |
| 28 | 마이페이지 | summary 카드 | 표시 | PASS(코드) | `getMySummary` |
| 29 | 마이페이지 | 최근 리포트 이동 | 이동 | PASS(코드) | `/report/:sessionId` |
| 30 | 마이페이지 | 성장/약점/추천 | 표시 | PASS(코드) | reports 집계 + 최근 리포트 detail |

- 런타임 한정 항목(실제 메일 수신, STT/TTS 브라우저 동작, 실제 파일 추출 결과)은 개발자 PC 브라우저에서 최종 확인 권장.

## 7. 발견 이슈
| 번호 | 이슈 | 심각도 | 상태 |
|--|--|--|--|
| I-1 | 프로덕션 settings 불일치(`settings.py` DEBUG=True / orphan `settings/base.py` 앱 누락) | 배포(중) | 보류(설정 리팩터링, DB변경 아님) |
| I-2 | `docker-compose*.yml` 부재 + FE `Dockerfile.prod`/`nginx.conf`/CI/CD 주석 | 배포(중) | 보류(인프라 작업) |
| I-3 | BE Dockerfile `runserver`(prod gunicorn 미적용) | 배포(중) | 보류(인프라 작업) |
| I-4 | 미디어 로컬 저장(S3 미적용) | 운영(하) | 추후 확장 |
| I-5 | `SECRET_KEY` 기본값 하드코딩 | 보안(중) | prod env 주입으로 해소(보류) |

> QA 중 **앱 기능(인증/JD/이력서/세션/면접/리포트/마이페이지)에서의 FAIL 버그는 발견되지 않음**(코드 검증 기준). 발견 이슈는 모두 배포/인프라/설정 영역이며 DB 변경 불필요.

## 8. 수정 완료 이슈
- 없음 (코드 변경 없음 — 기능 버그 미발견, 인프라/설정 이슈는 보류로 분류).

## 9. 보류 이슈
- I-1 ~ I-5 (위). + 추후 확장 기능은 `docs/추후_확장_기능_정리.md` 참조. DB/마이그레이션 필요 항목 없음(이번 범위).

## 10. 최종 판단
**READY_WITH_NOTES** — 앱 전체 흐름은 코드 검증상 정상이며 발표/시연 가능.
단, ① 자동 테스트/빌드/브라우저 런타임은 개발자 PC에서 1회 재확인 필요(샌드박스 환경 제약), ② 실제 AWS 자동 배포는 인프라 보완(§I-1~I-3) 후 가능.
