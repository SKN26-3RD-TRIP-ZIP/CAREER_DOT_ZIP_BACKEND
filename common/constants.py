# accounts_user.status
ACCOUNT_STATUS = {
    "active":    "정상 이용 가능",
    "suspended": "관리자 정지",
    "dormant":   "장기 미이용 휴면",
    "withdrawn": "회원 탈퇴",
}

# accounts_user.role
USER_ROLE = {
    "user":  "일반 사용자",
    "admin": "관리자",
}

# interviews_interviewsession.status
INTERVIEW_SESSION_STATUS = {
    "ready":       "대기 중",
    "in_progress": "진행 중",
    "completed":   "완료",
    "canceled":    "취소",
    "failed":      "실패",
}

# interviews_interviewsession.mode
INTERVIEW_MODE = {
    "text":  "텍스트 모드",
    "voice": "음성 모드",
}

# prompts_personaconfig.persona_type
PERSONA_TYPE = {
    "coach":     "코치형",
    "practical": "실전형",
    "verify":    "검증형",
}

# resumes_jobdescription.input_method
JD_INPUT_METHOD = {
    "TEXT": "직접 입력",
    "PDF":  "PDF 업로드",
    "URL":  "URL 입력",
    "OCR":  "이미지 OCR",
}

# interviews_question.question_type
QUESTION_TYPE = {
    "technical":   "기술 질문",
    "personality": "인성 질문",
    "job":         "직무 질문",
    "experience":  "경험 질문",
}

# interviews_question.difficulty
DIFFICULTY = {
    "low":  "하",
    "mid":  "중",
    "high": "상",
}

# prompts_basequestion.question_type
BASE_QUESTION_TYPE = {
    "bank":     "질문 뱅크",
    "template": "템플릿",
}

# prompts_basequestion.category
BASE_QUESTION_CATEGORY = {
    "personality": "인성",
    "technical":   "기술",
    "cs":          "CS",
}

# prompts_basequestion.cs_domain
CS_DOMAIN = {
    "data_structure":   "자료구조",
    "algorithm":        "알고리즘",
    "operating_system": "운영체제",
    "network":          "네트워크",
    "database":         "데이터베이스",
    "object_oriented":  "객체지향",
}

# interviews_question.source_type
QUESTION_SOURCE_TYPE = {
    "resume":            "이력서",
    "cover_letter":      "자기소개서",
    "jd":                "직무기술서",
    "question_bank":     "질문 뱅크",
    "project_experience": "프로젝트 경험",
}

# weakness_tags.category / strength_tags.category (공통)
TAG_CATEGORY = {
    "experience":       "경험",
    "answer_quality":   "답변 품질",
    "technical":        "기술",
    "attitude":         "태도",
    "communication":    "커뮤니케이션",
    "job_fit":          "직무 적합성",
    "growth":           "성장 가능성",
    "speech_delivery":  "전달력",
    "collaboration":    "협업",
}

# evaluations_expertreview.expert_type
EXPERT_TYPE = {
    "HUMAN": "사람 전문가",
    "GPT4o": "GPT-4o AI",
}

# audits_auditlog.action_type
AUDIT_ACTION_TYPE = {
    "template_activate":      "템플릿 활성화",
    "version_default_change": "버전 기본값 변경",
    "template_create":        "템플릿 생성",
    "template_delete":        "템플릿 삭제",
    "version_create":         "버전 생성",
    "member_status_change":   "회원 상태 변경",
}

# audits_auditlog.target_type
AUDIT_TARGET_TYPE = {
    "accounts_user":              "사용자",
    "prompts_personaconfig":      "페르소나 설정",
    "prompts_prompttemplate":     "프롬프트 템플릿",
    "prompts_promptversion":      "프롬프트 버전",
}

# resumes_userresume.career_type
CAREER_TYPE = {
    "junior":     "신입",
    "experienced": "경력",
}

# resumes_education.major_type
MAJOR_TYPE = {
    "major":     "전공자",
    "non_major": "비전공자",
}

# resumes_education.status
EDUCATION_STATUS = {
    "graduated":       "졸업",
    "enrolled":        "재학",
    "leave_of_absence": "휴학",
    "dropped_out":     "중퇴",
}

# resumes_education.degree
DEGREE = {
    "고졸":   "고등학교 졸업",
    "전문학사": "전문대 졸업",
    "학사":   "대학교 졸업",
    "석사":   "대학원 석사",
    "박사":   "대학원 박사",
}

# resumes_skill.level
SKILL_LEVEL = {
    "high":   "상",
    "medium": "중",
    "low":    "하",
}

# resumes_skill.category
SKILL_CATEGORY = {
    "언어":    "프로그래밍 언어",
    "프레임워크": "프레임워크 / 라이브러리",
    "DB":     "데이터베이스",
    "인프라":   "인프라 / DevOps",
    "협업도구":  "협업 도구",
}

# interviews_question.technical_domain (또는 관련 도메인 분류)
TECHNICAL_DOMAIN = {
    "CS":           "컴퓨터 과학",
    "DB":           "데이터베이스",
    "Network":      "네트워크",
    "OS":           "운영체제",
    "Architecture": "소프트웨어 아키텍처",
    "Frontend":     "프론트엔드",
    "Backend":      "백엔드",
    "AI":           "인공지능 / ML",
    "Data":         "데이터 엔지니어링",
}
