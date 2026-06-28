import re


KEYWORD_CANDIDATES = (
    'Python', 'Java', 'JavaScript', 'TypeScript', 'React', 'Django', 'Spring',
    'Spring Boot', 'SQL', 'MySQL', 'PostgreSQL', 'Redis', 'Docker', 'AWS', 'Git',
    'GitHub', 'API', 'REST', '서버', '백엔드', '프론트엔드', '데이터베이스', '보안',
    '네트워크', '운영체제', '알고리즘', '자료구조', '성능', '장애', '배포', '협업',
    '갈등', '문제 해결', '리더십', '커뮤니케이션', '아키텍처', '트랜잭션', '인덱스',
    '캐시', '동시성', 'MSA', 'CI/CD', '테스트', 'TDD',
)


def extract_keywords(question_text: str, answer_text: str = '') -> list[str]:
    text = f'{question_text} {answer_text}'.lower()
    return [
        keyword
        for keyword in KEYWORD_CANDIDATES
        if _contains_keyword(text, keyword)
    ]


def _contains_keyword(text, keyword):
    lowered_keyword = keyword.lower()
    if re.search(r'[a-z]', lowered_keyword):
        pattern = rf'(?<![a-z0-9]){re.escape(lowered_keyword)}(?![a-z0-9])'
        return re.search(pattern, text) is not None
    return lowered_keyword in text
