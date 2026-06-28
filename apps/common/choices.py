INTERVIEW_TYPE_CHOICES = [
    ("technical", "기술 면접"),
    ("personality", "인성 면접"),
    ("comprehensive", "종합 면접"),
]

INTERVIEW_PERSONA_CHOICES = [
    ("coach", "코치형"),
    ("practical", "실무형"),
    ("verifier", "검증형"),
]

INTERVIEW_SESSION_STATUS_COMPLETED = "completed"
INTERVIEW_SESSION_STATUS_CANCELLED = "cancelled"

INTERVIEW_SESSION_STATUS_CHOICES = [
    ("created", "생성됨"),
    ("in_progress", "진행 중"),
    (INTERVIEW_SESSION_STATUS_COMPLETED, "완료"),
    (INTERVIEW_SESSION_STATUS_CANCELLED, "취소"),
]

QUESTION_TYPE_CHOICES = [
    ("main", "기본 질문"),
    ("follow_up", "꼬리질문"),
]

QUESTION_CATEGORY_CHOICES = [
    ("technical", "Technical"),
    ("personality", "Personality"),
    ("general", "General"),
]

ANSWER_SOURCE_CHOICES = [
    ("text", "텍스트"),
    ("stt", "음성 인식"),
]

ANALYSIS_STATUS_CHOICES = [
    ("pending", "대기"),
    ("processing", "처리 중"),
    ("completed", "완료"),
    ("failed", "실패"),
]

INPUT_METHOD_CHOICES = [
    ("TEXT", "직접 입력"),
    ("FILE", "파일 업로드"),
    ("URL", "URL 입력"),
]

EXTERNAL_SOURCE_CHOICES = [
    ("manual", "직접 입력"),
    ("worknet", "워크넷"),
]

CAREER_TYPE_CHOICES = [
    ("new", "신입"),
    ("experienced", "경력"),
]

MAJOR_TYPE_CHOICES = [
    ("major", "전공"),
    ("non_major", "비전공"),
]
