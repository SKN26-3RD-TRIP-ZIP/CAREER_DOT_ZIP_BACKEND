import uuid
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class AnalysisSession(models.Model):
    """
    비동기 분석 파이프라인의 처리 상태를 추적하는 세션.
    분석이 완료되면 JdAnalysis가 생성
    """
    user          = models.ForeignKey(User, on_delete=models.CASCADE, related_name="analysis_sessions")

    # 입력 문서 FK (input 앱 참조)
    jd            = models.ForeignKey('input.JobDescription', on_delete=models.SET_NULL, null=True, blank=True, related_name="analysis_sessions")
    resume        = models.ForeignKey('input.ResumeMaster', on_delete=models.SET_NULL, null=True, blank=True, related_name="analysis_sessions")
    cover_letter  = models.ForeignKey('input.CoverLetter', on_delete=models.SET_NULL, null=True, blank=True, related_name="analysis_sessions")

    # 분석 완료 후 생성된 JdAnalysis 참조
    jd_analysis   = models.OneToOneField('JdAnalysis', on_delete=models.SET_NULL, null=True, blank=True, related_name="session")

    job_role          = models.CharField(max_length=100)
    company_name      = models.CharField(max_length=100, blank=True)
    jd_text           = models.TextField()
    resume_text       = models.TextField(blank=True)
    cover_letter_text = models.TextField(blank=True)

    # 중간 분석 결과 (파이프라인 내부용)
    jd_keywords     = models.JSONField(default=dict)   # {"tech_keywords": [], "trait_keywords": []}
    resume_analysis = models.JSONField(default=dict)

    CAREER_LEVEL_CHOICES = [
        ("entry",       "신입"),
        ("experienced", "경력"),
    ]
    career_level = models.CharField(
        max_length=20, choices=CAREER_LEVEL_CHOICES, default="entry"
    )

    STATUS_CHOICES = [
        ("pending",   "분석 대기"),
        ("analyzing", "분석 중"),
        ("ready",     "완료"),
        ("failed",    "실패"),
    ]
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'analysis_session'
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.user}] {self.job_role} @ {self.company_name} ({self.status})"


class JdAnalysis(models.Model):
    """
    JD + 이력서 + 자소서 매핑 분석 결과.
    분석 완료 후 생성되며, 면접 세션(InterviewSession)이 이 테이블을 참조해 질문을 가져간다.
    """
    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user          = models.ForeignKey(User, on_delete=models.CASCADE, related_name="jd_analyses")
    jd            = models.ForeignKey('input.JobDescription', on_delete=models.CASCADE, related_name="jd_analyses")
    resume        = models.ForeignKey('input.ResumeMaster', on_delete=models.CASCADE, related_name="jd_analyses")
    cover_letter  = models.ForeignKey('input.CoverLetter', on_delete=models.SET_NULL, null=True, blank=True, related_name="jd_analyses")

    # 분석 결과
    match_score         = models.FloatField(default=0.0)    # 최종 가중 합산 점수 (0.0 ~ 100.0)
    tech_score          = models.FloatField(default=0.0)    # 기술 스택 집합 연산 점수
    trait_score         = models.FloatField(default=0.0)    # 인재상 임베딩 유사도 점수
    matched_keywords    = models.JSONField(default=list)    # 매칭된 기술 키워드
    unmatched_keywords  = models.JSONField(default=list)    # 부족한 기술 키워드
    jd_keywords         = models.JSONField(default=dict)    # {"tech_keywords": [], "trait_keywords": []}
    resume_analysis     = models.JSONField(default=dict)    # 이력서 구조화 분석 결과
    strengths           = models.JSONField(default=list)    # 강점 리스트
    weaknesses          = models.JSONField(default=list)    # 약점 리스트
    cl_points           = models.JSONField(default=list)    # 자소서 반영 포인트

    # 예상 질문 생성 횟수 (최초 생성 + 재생성 누적). 무료 상한 관리에 사용.
    generation_count    = models.IntegerField(default=0)

    analyzed_at   = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'jd_analysis'
        ordering = ["-analyzed_at"]

    def __str__(self):
        return f"[{self.user}] JD:{self.jd_id} × Resume:{self.resume_id} ({self.match_score:.1f}%)"


class GeneratedQuestion(models.Model):
    """
    JdAnalysis 기반으로 생성된 면접 질문 + STAR 모범 답안.
    interview 앱의 InterviewSession이 jd_analysis_id로 이 테이블을 조회한다.
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    jd_analysis = models.ForeignKey(JdAnalysis, on_delete=models.CASCADE, related_name="questions")

    QUESTION_TYPES = [
        ("personality", "인성"),
        ("technical",   "기술·직무"),
        ("experience",  "경험 기반"),
    ]
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES)
    question_text = models.TextField()
    order         = models.IntegerField(default=0)
    is_used       = models.BooleanField(default=False)

    # 질문 출처 (어떤 문서를 근거로 생성됐는지)
    SOURCE_CHOICES = [
        ("jd",            "채용공고(JD)"),
        ("resume",        "이력서"),
        ("cover_letter",  "자기소개서"),
        ("project",       "프로젝트 경험"),
        ("combined",      "복합 출처"),
    ]
    source     = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="jd")
    source_ref = models.TextField(blank=True, default="")
    # source_ref 예시:
    #   source="jd"           → "Python, Django, Docker"  (사용된 JD 키워드)
    #   source="resume"       → "핵심 경험: 백엔드 API 설계 및 운영"
    #   source="cover_letter" → "자소서 키워드: 문제 해결 중심 사고"
    #   source="project"      → "프로젝트명: 배달 플랫폼 서버 개발"
    #   source="combined"     → "JD(Python) + 프로젝트(배달 플랫폼)"

    # STAR 모범 답안
    answer = models.JSONField(default=dict)
    # {
    #   "summary":   "두괄식 오프닝",
    #   "situation": "상황 설명",
    #   "task":      "역할·과제",
    #   "action":    "구체적 행동",
    #   "result":    "결과 및 배운 점"
    # }

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'analysis_generated_question'
        ordering = ["order"]

    def __str__(self):
        return f"[{self.question_type}] {self.question_text[:40]}"


class QuestionFeedback(models.Model):
    """
    예상 질문/답변에 대한 사용자 만족도 신호.
    - 명시 신호: 👍/👎 (rating)
    - 암묵 신호: generation_count (몇 번째 생성 결과에 피드백했는지 — 재생성이 많을수록 불만족)
    품질 모니터링·관리자 대시보드의 기초 데이터.
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    jd_analysis = models.ForeignKey(JdAnalysis, on_delete=models.CASCADE, related_name="feedbacks")

    RATING_CHOICES = [
        ("up",   "만족"),
        ("down", "불만족"),
    ]
    rating           = models.CharField(max_length=10, choices=RATING_CHOICES)
    generation_count = models.IntegerField(default=0)   # 피드백 시점의 생성 횟수
    comment          = models.TextField(blank=True, default="")
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'analysis_question_feedback'
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.rating}] analysis:{self.jd_analysis_id} (gen {self.generation_count})"
