# 면접 MVP E2E API 플로우 점검 순서

## 목표

BE 기준으로 아래 흐름이 끊기지 않는지 확인한다.

1. 페르소나 목록 조회
2. 면접 세션 생성
3. 세션 진행 상태 변경
4. 질문 생성
5. 질문 목록 조회
6. turns 응답 확인
7. 답변 저장
8. 꼬리질문 생성
9. 꼬리질문 목록 조회
10. turns 응답 재확인
11. 세션 완료

## 확인 포인트

- 질문 생성 결과의 `question_type`이 `main`인지 확인
- 답변 저장 후 `answer_id`가 반환되는지 확인
- 꼬리질문 생성 후 `follow_up_questions`가 반환되는지 확인
- turns 응답에서 `persona_detail`, `progress`, `current_turn`, `next_action`이 정상 동작하는지 확인
- 완료 처리 후 session status가 `completed`로 변경되는지 확인

## 테스트 명령어

```bash
python manage.py test apps.interview.test_interview_mvp_e2e_flow
python manage.py test apps.interview
```
