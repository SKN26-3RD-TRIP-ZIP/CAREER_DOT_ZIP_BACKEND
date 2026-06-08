"""
input API 단위 테스트

테스트 대상 흐름:
  1. JD 등록      POST /api/v1/jds
  2. 이력서 등록   POST /api/v1/resumes
     ├── 학력      POST /api/v1/resumes/{resume_id}/education
     ├── 경력      POST /api/v1/resumes/{resume_id}/careers
     ├── 기술      POST /api/v1/resumes/{resume_id}/skills
     └── 자격증    POST /api/v1/resumes/{resume_id}/certificates
  3. 자소서 등록   POST /api/v1/cover-letters
"""
import pprint

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    CoverLetter,
    JobDescription,
    ResumeMaster,
    ResumeCareer,
    ResumeEducation,
    ResumeSkill,
    ResumeCertificate,
)

User = get_user_model()


# ──────────────────────────────────────────────
# Mock 데이터
# ──────────────────────────────────────────────

MOCK_JD = {
    "company_name": "커리어닷집",
    "position":     "백엔드 개발자",
    "original_text": (
        "Python/Django 기반 백엔드 개발자를 모집합니다.\n"
        "[필수]\n"
        "- Python, Django 개발 경험 2년 이상\n"
        "- REST API 설계 및 구현 경험\n"
        "- MySQL 또는 PostgreSQL 사용 경험\n"
        "[우대]\n"
        "- Docker, Kubernetes 경험\n"
        "- AWS 클라우드 서비스 경험\n"
        "- 대용량 트래픽 처리 경험"
    ),
    "input_method": "TEXT",
}

MOCK_RESUME = {
    "name":     "홍길동",
    "phone":    "010-1234-5678",
    "email":    "hong@example.com",
    "address":  "서울시 강남구",
    "github_url": "https://github.com/honggildong",
}

MOCK_EDUCATION = {
    "school_name": "한국대학교",
    "major":       "컴퓨터공학",
    "degree":      "bachelor",
    "start_date":  "2018-03",
    "end_date":    "2022-02",
    "status":      "graduated",
}

MOCK_CAREER = {
    "company_name": "스타트업A",
    "position":     "백엔드 개발자",
    "start_date":   "2022-03",
    "end_date":     "2024-02",
    "is_current":   False,
    "description":  "Django 기반 REST API 개발 및 운영, MySQL DB 설계",
}

MOCK_SKILLS = {
    "names": ["Python", "Django", "MySQL", "Docker", "REST API"],
}

MOCK_CERTIFICATE = {
    "name":      "정보처리기사",
    "issued_by": "한국산업인력공단",
    "issued_at": "2022-06",
}

MOCK_COVER_LETTER = {
    "title":        "커리어닷집 백엔드 개발자 지원",
    "company_name": "커리어닷집",
    "items": [
        {
            "question":    "지원 동기를 작성해주세요.",
            "answer_text": "저는 AI 기반 서비스에 관심이 많아 커리어닷집에 지원했습니다.",
            "order_index": 1,
        },
        {
            "question":    "본인의 강점을 작성해주세요.",
            "answer_text": "문제를 끝까지 파고드는 집요함이 강점입니다.",
            "order_index": 2,
        },
    ],
}


# ──────────────────────────────────────────────
# 1. JD 등록 테스트
# ──────────────────────────────────────────────

class JDAPITest(APITestCase):
    """
    [JD 등록]

    REQUEST:
        POST /api/v1/jds
        {
            "company_name":  "커리어닷집",
            "position":      "백엔드 개발자",
            "original_text": "Python/Django 기반...",
            "input_method":  "TEXT"
        }

    RESPONSE (201):
        {
            "id":           "uuid",
            "company_name": "커리어닷집",
            "position":     "백엔드 개발자",
            "created_at":   "2026-06-08T..."
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="jd-test@example.com",
            password="password123",
            name="테스트유저",
        )
        self.other_user = User.objects.create_user(
            email="jd-other@example.com",
            password="password123",
            name="다른유저",
        )
        self.client.force_authenticate(self.user)

    def test_JD_등록_성공(self):
        response = self.client.post(
            reverse("jd-list-create"),
            MOCK_JD,
            format="json",
        )

        print("\n[JD 등록] REQUEST :", MOCK_JD)
        print("[JD 등록] RESPONSE:", response.data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
        self.assertEqual(response.data["company_name"], "커리어닷집")
        self.assertEqual(response.data["position"], "백엔드 개발자")

        # DB 저장 확인
        jd = JobDescription.objects.get(id=response.data["id"])
        self.assertEqual(jd.user, self.user)
        self.assertEqual(jd.original_text, MOCK_JD["original_text"])

    def test_JD_목록_조회_본인것만_반환(self):
        # 본인 JD 2개, 타인 JD 1개
        JobDescription.objects.create(user=self.user, **{k: v for k, v in MOCK_JD.items()})
        JobDescription.objects.create(user=self.user, company_name="회사B", position="프론트엔드", original_text="React 개발자")
        JobDescription.objects.create(user=self.other_user, company_name="회사C", position="기획자", original_text="기획자 모집")

        response = self.client.get(reverse("jd-list-create"))

        print("\n[JD 목록] RESPONSE:", response.data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 2)

    def test_JD_상세_조회(self):
        jd = JobDescription.objects.create(user=self.user, **{k: v for k, v in MOCK_JD.items()})

        response = self.client.get(reverse("jd-detail", kwargs={"jd_id": jd.id}))

        print("\n[JD 상세] RESPONSE:", response.data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["company_name"], "커리어닷집")

    def test_JD_삭제(self):
        jd = JobDescription.objects.create(user=self.user, **{k: v for k, v in MOCK_JD.items()})

        response = self.client.delete(reverse("jd-detail", kwargs={"jd_id": jd.id}))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(JobDescription.objects.filter(id=jd.id).exists())

    def test_타인_JD_조회시_404(self):
        other_jd = JobDescription.objects.create(
            user=self.other_user,
            company_name="타인회사",
            position="개발자",
            original_text="타인 JD",
        )

        response = self.client.get(reverse("jd-detail", kwargs={"jd_id": other_jd.id}))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_미인증_요청시_401(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(reverse("jd-list-create"), MOCK_JD, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ──────────────────────────────────────────────
# 2. 이력서 등록 테스트
# ──────────────────────────────────────────────

class ResumeAPITest(APITestCase):
    """
    [이력서 등록]

    REQUEST:
        POST /api/v1/resumes
        {
            "name":       "홍길동",
            "phone":      "010-1234-5678",
            "email":      "hong@example.com",
            "address":    "서울시 강남구",
            "github_url": "https://github.com/honggildong"
        }

    RESPONSE (201):
        {
            "resume_id":  "uuid",
            "is_active":  true,
            "created_at": "2026-06-08T..."
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="resume-test@example.com",
            password="password123",
            name="테스트유저",
        )
        self.client.force_authenticate(self.user)

    def _create_resume(self):
        """테스트용 이력서 생성 헬퍼"""
        return ResumeMaster.objects.create(user=self.user, **MOCK_RESUME)

    def test_이력서_생성_성공(self):
        response = self.client.post(
            reverse("resume-create"),
            MOCK_RESUME,
            format="json",
        )

        print("\n[이력서 생성] REQUEST :", MOCK_RESUME)
        print("[이력서 생성] RESPONSE:", response.data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("resume_id", response.data)
        self.assertTrue(response.data["is_active"])

        resume = ResumeMaster.objects.get(id=response.data["resume_id"])
        self.assertEqual(resume.user, self.user)
        self.assertEqual(resume.name, "홍길동")

    def test_이력서_상세_조회(self):
        resume = self._create_resume()

        response = self.client.get(
            reverse("resume-detail", kwargs={"resume_id": resume.id})
        )

        print("\n[이력서 상세] RESPONSE:")
        pprint.pprint(dict(response.data))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "홍길동")
        self.assertEqual(response.data["email"], "hong@example.com")

    def test_학력_등록(self):
        resume = self._create_resume()

        response = self.client.post(
            reverse("resume-education-create", kwargs={"resume_id": resume.id}),
            MOCK_EDUCATION,
            format="json",
        )

        print("\n[학력 등록] REQUEST :", MOCK_EDUCATION)
        print("[학력 등록] RESPONSE:", response.data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("resume_edu_id", response.data)
        self.assertEqual(response.data["school_name"], "한국대학교")

        self.assertEqual(ResumeEducation.objects.filter(resume=resume).count(), 1)

    def test_경력_등록(self):
        resume = self._create_resume()

        response = self.client.post(
            reverse("resume-career-create", kwargs={"resume_id": resume.id}),
            MOCK_CAREER,
            format="json",
        )

        print("\n[경력 등록] REQUEST :", MOCK_CAREER)
        print("[경력 등록] RESPONSE:", response.data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("resume_career_id", response.data)
        self.assertEqual(response.data["company_name"], "스타트업A")

        self.assertEqual(ResumeCareer.objects.filter(resume=resume).count(), 1)

    def test_기술스택_등록(self):
        resume = self._create_resume()

        response = self.client.post(
            reverse("resume-skill-create", kwargs={"resume_id": resume.id}),
            MOCK_SKILLS,
            format="json",
        )

        print("\n[기술 등록] REQUEST :", MOCK_SKILLS)
        print("[기술 등록] RESPONSE:", response.data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("resume_skill_ids", response.data)
        self.assertEqual(len(response.data["resume_skill_ids"]), 5)

        self.assertEqual(ResumeSkill.objects.filter(resume=resume).count(), 5)

    def test_자격증_등록(self):
        resume = self._create_resume()

        response = self.client.post(
            reverse("resume-certificate-create", kwargs={"resume_id": resume.id}),
            MOCK_CERTIFICATE,
            format="json",
        )

        print("\n[자격증 등록] REQUEST :", MOCK_CERTIFICATE)
        print("[자격증 등록] RESPONSE:", response.data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("resume_certificate_id", response.data)
        self.assertEqual(response.data["name"], "정보처리기사")

        self.assertEqual(ResumeCertificate.objects.filter(resume=resume).count(), 1)

    def test_없는_이력서에_학력등록시_404(self):
        import uuid
        fake_id = uuid.uuid4()

        response = self.client.post(
            reverse("resume-education-create", kwargs={"resume_id": fake_id}),
            MOCK_EDUCATION,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_이력서_삭제(self):
        resume = self._create_resume()

        response = self.client.delete(
            reverse("resume-detail", kwargs={"resume_id": resume.id})
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ResumeMaster.objects.filter(id=resume.id).exists())


# ──────────────────────────────────────────────
# 3. 자소서 등록 테스트
# ──────────────────────────────────────────────

class CoverLetterAPITest(APITestCase):
    """
    [자소서 등록]

    REQUEST:
        POST /api/v1/cover-letters
        {
            "title":        "커리어닷집 백엔드 개발자 지원",
            "company_name": "커리어닷집",
            "jd_id":        "uuid",  (선택)
            "items": [
                {"question": "지원 동기", "answer_text": "...", "order_index": 1},
                {"question": "강점",     "answer_text": "...", "order_index": 2}
            ]
        }

    RESPONSE (201):
        {
            "cover_letter_id": "uuid",
            "title":           "커리어닷집 백엔드 개발자 지원",
            "is_active":       true,
            "created_at":      "2026-06-08T..."
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="cl-test@example.com",
            password="password123",
            name="테스트유저",
        )
        self.other_user = User.objects.create_user(
            email="cl-other@example.com",
            password="password123",
            name="다른유저",
        )
        self.client.force_authenticate(self.user)

    def test_자소서_등록_성공(self):
        response = self.client.post(
            reverse("cover-letter-list-create"),
            MOCK_COVER_LETTER,
            format="json",
        )

        print("\n[자소서 등록] REQUEST :", MOCK_COVER_LETTER)
        print("[자소서 등록] RESPONSE:", response.data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("cover_letter_id", response.data)
        self.assertEqual(response.data["title"], "커리어닷집 백엔드 개발자 지원")
        self.assertTrue(response.data["is_active"])

        cl = CoverLetter.objects.get(id=response.data["cover_letter_id"])
        self.assertEqual(cl.user, self.user)
        self.assertEqual(cl.items.count(), 2)

    def test_자소서_목록_조회_본인것만_반환(self):
        CoverLetter.objects.create(user=self.user, title="내 자소서1", company_name="회사A")
        CoverLetter.objects.create(user=self.user, title="내 자소서2", company_name="회사B")
        CoverLetter.objects.create(user=self.other_user, title="타인 자소서", company_name="회사C")

        response = self.client.get(reverse("cover-letter-list-create"))

        print("\n[자소서 목록] RESPONSE:", response.data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 2)

    def test_자소서_상세_조회(self):
        cl = CoverLetter.objects.create(
            user=self.user,
            title="커리어닷집 백엔드 개발자 지원",
            company_name="커리어닷집",
        )

        response = self.client.get(
            reverse("cover-letter-detail", kwargs={"cover_letter_id": cl.id})
        )

        print("\n[자소서 상세] RESPONSE:")
        pprint.pprint(dict(response.data))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "커리어닷집 백엔드 개발자 지원")

    def test_자소서_삭제(self):
        cl = CoverLetter.objects.create(
            user=self.user,
            title="삭제할 자소서",
            company_name="회사A",
        )

        response = self.client.delete(
            reverse("cover-letter-detail", kwargs={"cover_letter_id": cl.id})
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(CoverLetter.objects.filter(id=cl.id).exists())

    def test_타인_자소서_조회시_404(self):
        other_cl = CoverLetter.objects.create(
            user=self.other_user,
            title="타인 자소서",
            company_name="회사C",
        )

        response = self.client.get(
            reverse("cover-letter-detail", kwargs={"cover_letter_id": other_cl.id})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_미인증_요청시_401(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            reverse("cover-letter-list-create"),
            MOCK_COVER_LETTER,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
