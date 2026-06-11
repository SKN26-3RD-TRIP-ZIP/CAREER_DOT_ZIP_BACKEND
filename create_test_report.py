"""
E2E 리포트 테스트용 픽스처 생성 스크립트.

실행법 (Git Bash, career_project 환경 / CAREER_DOT_ZIP_BACKEND 디렉토리에서):
    python create_test_report.py
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.contrib.auth import get_user_model
from apps.interview.models import InterviewSession, InterviewQuestion, InterviewAnswer

User = get_user_model()

# ── 1. 유저 ────────────────────────────────────────────────────────────────
TEST_EMAIL = 'test_report@career.zip'
TEST_PW    = 'Test1234!'
TEST_NAME  = '테스트유저'

user, created = User.objects.get_or_create(
    email=TEST_EMAIL,
    defaults={'name': TEST_NAME, 'is_active': True, 'is_verified': True},
)
if created:
    user.set_password(TEST_PW)
    user.save()
    print(f'[유저 생성] {TEST_EMAIL} / {TEST_PW}')
else:
    print(f'[유저 재사용] {TEST_EMAIL}')

# ── 2. 세션 ────────────────────────────────────────────────────────────────
session = InterviewSession.objects.create(
    user=user,
    status='completed',
    interview_type='technical',
    persona='practical',
    interview_mode='text',
)
print(f'[세션 생성] id={session.id}  status={session.status}')

# ── 3. 질문 3개 ────────────────────────────────────────────────────────────
questions_data = [
    ('Django ORM의 select_related와 prefetch_related 차이를 설명하세요.', 'main'),
    ('N+1 문제를 실무에서 어떻게 해결했나요?', 'follow_up'),
    ('REST API 설계 시 버저닝 전략을 어떻게 잡으시나요?', 'main'),
]
questions = []
for i, (text, qtype) in enumerate(questions_data, start=1):
    q = InterviewQuestion.objects.create(
        session=session,
        question_text=text,
        question_type=qtype,
        order_index=i,
    )
    questions.append(q)

print(f'[질문 생성] {len(questions)}개')

# ── 4. 답변 3개 ────────────────────────────────────────────────────────────
answers_data = [
    ('select_related는 SQL JOIN으로 단일 쿼리에서 FK/OneToOne 관계를 가져오고, '
     'prefetch_related는 별도 쿼리로 M2M이나 역참조 관계를 가져옵니다. '
     '전자는 단일 row가 커지는 단점이 있고, 후자는 쿼리 2번이지만 메모리 효율이 높습니다.'),
    ('이전 프로젝트에서 게시글 목록 API가 댓글 수를 계산하면서 게시글당 1개씩 추가 쿼리가 나갔습니다. '
     'annotate(comment_count=Count("comments"))로 한 쿼리로 해결했고 응답시간이 800ms에서 90ms로 줄었습니다.'),
    ('URL에 /v1/, /v2/ prefix를 넣는 방식을 주로 씁니다. 헤더 버저닝도 있지만 '
     '디버깅과 캐싱 측면에서 URL 방식이 명확하다고 생각합니다. '
     '하위 호환이 필요한 경우 구버전은 6개월 deprecation 기간을 둡니다.'),
]
for q, ans_text in zip(questions, answers_data):
    InterviewAnswer.objects.create(
        session=session,
        question=q,
        answer_text=ans_text,
        stt_text=ans_text,
    )

print(f'[답변 생성] {len(answers_data)}개')

# ── 5. 결과 출력 ───────────────────────────────────────────────────────────
print()
print('=' * 60)
print(f'  테스트 계정  : {TEST_EMAIL}')
print(f'  비밀번호     : {TEST_PW}')
print(f'  세션 UUID   : {session.id}')
print()
print(f'  FE 접속 URL :')
print(f'  http://localhost:5175/report/{session.id}')
print('=' * 60)
