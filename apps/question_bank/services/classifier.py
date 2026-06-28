TECHNICAL_KEYWORDS = (
    '개발', '구현', '코드', '알고리즘', '데이터베이스', 'db', 'sql', 'api', '서버',
    '백엔드', '프론트엔드', 'react', 'django', 'spring', 'java', 'python', '보안',
    '네트워크', '운영체제', 'cs', '자료구조', '성능', '장애', '배포', 'docker',
    'aws', 'git', 'github', '아키텍처', '트랜잭션', '인덱스', '캐시',
)
PERSONALITY_KEYWORDS = (
    '강점', '단점', '협업', '갈등', '실패', '성격', '커뮤니케이션', '문제 해결 경험',
    '리더십', '팀원', '스트레스', '가치관', '성장', '소통', '역할', '책임', '배운 점',
)
JOB_KEYWORDS = (
    '지원동기', '직무', '회사', '부서', '입사', '커리어', '목표', '포부', '관심',
    '지원', '희망', '지원한 이유',
)

EASY_KEYWORDS = ('자기소개', '강점', '단점', '지원동기', '간단히 설명')
HARD_KEYWORDS = (
    '장애 해결', '성능 개선', '보안 이슈', '대안 비교', '트레이드오프', '아키텍처 설계',
    '인덱스', '트랜잭션', '캐시', '동시성', '스케일링',
)


def classify_question_type(question_text: str, answer_text: str = '') -> str:
    text = f'{question_text} {answer_text}'.lower()
    for question_type, keywords in (
        ('technical', TECHNICAL_KEYWORDS),
        ('personality', PERSONALITY_KEYWORDS),
        ('job', JOB_KEYWORDS),
    ):
        if any(keyword.lower() in text for keyword in keywords):
            return question_type
    return 'job'


def classify_difficulty(
    question_text: str,
    question_type: str,
    metadata: dict | None = None,
) -> str:
    del question_type, metadata
    text = (question_text or '').lower()
    if any(keyword.lower() in text for keyword in HARD_KEYWORDS):
        return 'hard'
    if any(keyword.lower() in text for keyword in EASY_KEYWORDS):
        return 'easy'
    return 'medium'
