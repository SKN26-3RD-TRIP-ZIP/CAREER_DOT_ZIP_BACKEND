"""
JD/이력서 파일 업로드 + 마이페이지 요약 테스트.

- /jds/upload, /resumes/upload : PDF/DOCX 업로드 → 텍스트 추출 → original_text 저장
- 확장자/빈파일/크기/추출실패/소유자 격리 예외
- /users/me/summary 집계

실행: python manage.py test apps.input.tests_upload
"""
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.input.models import (
    JobDescription,
    ResumeMaster,
    CoverLetter,
    ProjectExperience,
)
from apps.interview.models import InterviewSession
from apps.report.models import FinalReport

PASSWORD = "QaTestPw!234"


def _pdf_bytes(text="Job posting backend developer recruitment responsibilities include Django REST API development. Requirements include Python database design. Preferred qualifications include AWS monitoring."):
    import fitz  # PyMuPDF

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _docx_bytes(text="Resume email up@example.com github portfolio backend engineer career project Django Python REST API PostgreSQL AWS deployment monitoring education certificate."):
    from docx import Document

    document = Document()
    document.add_paragraph(text)
    buf = BytesIO()
    document.save(buf)
    return buf.getvalue()


class _AuthMixin:
    def _auth(self, email="up@example.com"):
        user = User.objects.create_user(email=email, name="up", password=PASSWORD)
        user.is_verified = True
        user.save(update_fields=["is_verified"])
        token = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return user


class JDUploadTests(_AuthMixin, APITestCase):
    url = "/api/v1/jds/upload"

    def test_pdf_upload_creates_jd_with_text(self):
        self._auth()
        f = SimpleUploadedFile("jd.pdf", _pdf_bytes(), content_type="application/pdf")
        res = self.client.post(self.url, {"file": f, "company_name": "테스트테크", "position": "백엔드"}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn("jd_id", res.data)
        self.assertEqual(res.data["company_name"], "테스트테크")
        self.assertEqual(res.data["position"], "백엔드")
        self.assertEqual(res.data["input_method"], "PDF")
        self.assertIn("created_at", res.data)
        jd = JobDescription.objects.get()
        self.assertEqual(jd.input_method, "PDF")
        self.assertIn("Job posting", jd.original_text)
        self.assertEqual(jd.company_name, "테스트테크")

    def test_reject_non_pdf_extension(self):
        self._auth()
        f = SimpleUploadedFile("img.png", b"\x89PNG\r\n", content_type="image/png")
        res = self.client.post(self.url, {"file": f}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_docx_upload_creates_jd_with_text(self):
        self._auth()
        f = SimpleUploadedFile(
            "jd.docx",
            _docx_bytes("Job posting backend developer recruitment responsibilities requirements qualifications preferred hiring process working conditions."),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        res = self.client.post(self.url, {"file": f}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn("jd_id", res.data)

    def test_reject_empty_file(self):
        self._auth()
        f = SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf")
        res = self.client.post(self.url, {"file": f}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reject_oversize(self):
        self._auth()
        big = b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024 + 1)
        f = SimpleUploadedFile("big.pdf", big, content_type="application/pdf")
        res = self.client.post(self.url, {"file": f}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        self.assertEqual(res.data["error_code"], "FILE_TOO_LARGE")

    def test_extraction_failure_returns_422(self):
        self._auth()
        # .pdf 확장자지만 내용은 PDF가 아님 → 파서 실패
        f = SimpleUploadedFile("broken.pdf", b"this is not a real pdf", content_type="application/pdf")
        res = self.client.post(self.url, {"file": f}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["error_code"], "INVALID_FILE_SIGNATURE")

    def test_requires_auth(self):
        f = SimpleUploadedFile("jd.pdf", _pdf_bytes(), content_type="application/pdf")
        res = self.client.post(self.url, {"file": f}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class ResumeUploadTests(_AuthMixin, APITestCase):
    url = "/api/v1/resumes/upload"

    def test_docx_upload_creates_resume_with_text(self):
        user = self._auth()
        f = SimpleUploadedFile(
            "resume.docx",
            _docx_bytes(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        res = self.client.post(self.url, {"file": f}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn("resume_id", res.data)
        self.assertIn("created_at", res.data)
        self.assertIn("updated_at", res.data)
        resume = ResumeMaster.objects.get()
        self.assertIn("Resume", resume.original_text)
        self.assertEqual(resume.email, user.email)

    def test_pdf_upload_ok(self):
        self._auth()
        f = SimpleUploadedFile("resume.pdf", _pdf_bytes("Resume email up@example.com github portfolio backend engineer career project Django Python REST API PostgreSQL AWS deployment monitoring education certificate."), content_type="application/pdf")
        res = self.client.post(self.url, {"file": f}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        resume = ResumeMaster.objects.get()
        self.assertIn("Resume", resume.original_text)

    def test_reject_unsupported_extension(self):
        self._auth()
        f = SimpleUploadedFile("resume.hwp", b"content", content_type="application/octet-stream")
        res = self.client.post(self.url, {"file": f}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reject_oversize(self):
        self._auth()
        big = b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024 + 1)
        f = SimpleUploadedFile("resume.pdf", big, content_type="application/pdf")
        res = self.client.post(self.url, {"file": f}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        self.assertEqual(res.data["error_code"], "FILE_TOO_LARGE")

    def test_list_only_own_resumes(self):
        self._auth("a@example.com")
        self.client.post(
            self.url,
            {"file": SimpleUploadedFile("r.pdf", _pdf_bytes(), content_type="application/pdf")},
            format="multipart",
        )
        # 다른 사용자로 전환 → 목록 비어 있어야 함
        self._auth("b@example.com")
        res = self.client.get("/api/v1/resumes")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["total"], 0)

    def test_detail_only_own_resume(self):
        user = self._auth("owner@example.com")
        resume = ResumeMaster.objects.create(user=user, name="owned", email=user.email, original_text="owned")
        self._auth("other@example.com")
        res = self.client.get(f"/api/v1/resumes/{resume.id}")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class UserSummaryTests(_AuthMixin, APITestCase):
    url = "/api/v1/users/me/summary"

    def test_summary_counts(self):
        user = self._auth()
        JobDescription.objects.create(user=user, company_name="c", position="p", original_text="t")
        ResumeMaster.objects.create(user=user, name="n", email=user.email, original_text="t")
        ResumeMaster.objects.create(user=user, name="n2", email=user.email)
        CoverLetter.objects.create(user=user, title="cl")
        ProjectExperience.objects.create(user=user, project_name="proj", description="d")
        session = InterviewSession.objects.create(
            user=user,
            interview_type="technical",
            persona="practical",
            status="completed",
        )
        report = FinalReport.objects.create(
            session=session,
            summary={"score_summary": {"overall_score": 88}},
        )

        res = self.client.get(self.url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["jd_count"], 1)
        self.assertEqual(res.data["resume_count"], 2)
        self.assertEqual(res.data["cover_letter_count"], 1)
        self.assertEqual(res.data["project_count"], 1)
        self.assertEqual(res.data["latest_jd"]["company_name"], "c")
        self.assertEqual(res.data["latest_jd"]["position"], "p")
        self.assertEqual(res.data["latest_jd"]["analysis_status"], "PENDING")
        self.assertIn("created_at", res.data["latest_jd"])
        self.assertEqual(res.data["latest_resume"]["name"], "n2")
        self.assertIsNotNone(res.data["latest_resume_updated_at"])
        self.assertEqual(res.data["interview_count"], 1)
        self.assertEqual(res.data["latest_interview"]["session_id"], str(session.id))
        self.assertEqual(res.data["latest_report"]["report_id"], str(report.id))
        self.assertEqual(res.data["latest_report"]["overall_score"], 88)

    def test_summary_only_counts_own_data(self):
        user = self._auth("summary-owner@example.com")
        other = User.objects.create_user(email="summary-other@example.com", name="other", password=PASSWORD)
        JobDescription.objects.create(user=user, company_name="own", position="p", original_text="t")
        ResumeMaster.objects.create(user=user, name="own", email=user.email, original_text="t")
        CoverLetter.objects.create(user=other, title="other")
        ProjectExperience.objects.create(user=other, project_name="other", description="d")
        JobDescription.objects.create(user=other, company_name="other", position="p", original_text="t")
        ResumeMaster.objects.create(user=other, name="other", email=other.email, original_text="t")
        other_session = InterviewSession.objects.create(
            user=other,
            interview_type="technical",
            persona="practical",
            status="completed",
        )
        FinalReport.objects.create(
            session=other_session,
            summary={"score_summary": {"overall_score": 91}},
        )

        res = self.client.get(self.url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["jd_count"], 1)
        self.assertEqual(res.data["resume_count"], 1)
        self.assertEqual(res.data["cover_letter_count"], 0)
        self.assertEqual(res.data["project_count"], 0)
        self.assertEqual(res.data["interview_count"], 0)
        self.assertEqual(res.data["latest_jd"]["company_name"], "own")
        self.assertEqual(res.data["latest_resume"]["name"], "own")
        self.assertIsNone(res.data["latest_interview"])
        self.assertIsNone(res.data["latest_report"])

    def test_summary_empty_state(self):
        self._auth("empty-summary@example.com")
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["jd_count"], 0)
        self.assertEqual(res.data["resume_count"], 0)
        self.assertIsNone(res.data["latest_jd"])
        self.assertIsNone(res.data["latest_resume"])
        self.assertEqual(res.data["interview_count"], 0)
        self.assertIsNone(res.data["latest_interview"])
        self.assertIsNone(res.data["latest_report"])

    def test_summary_requires_auth(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class UserProfileTests(_AuthMixin, APITestCase):
    url = "/api/v1/users/me/profile"

    def test_profile_create_get_and_patch_with_frontend_values(self):
        self._auth("profile@example.com")

        create = self.client.post(
            self.url,
            {
                "career_type": "new",
                "major_type": "major",
                "desired_job": "backend",
                "career_year": 0,
            },
            format="json",
        )
        self.assertEqual(create.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create.data["career_type"], "new")

        detail = self.client.get(self.url)
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["major_type"], "major")
        self.assertEqual(detail.data["desired_job"], "backend")

        patch = self.client.patch(
            self.url,
            {
                "career_type": "career",
                "major_type": "non_major",
                "career_year": 3,
            },
            format="json",
        )
        self.assertEqual(patch.status_code, status.HTTP_200_OK)

        detail = self.client.get(self.url)
        self.assertEqual(detail.data["career_type"], "career")
        self.assertEqual(detail.data["major_type"], "non_major")
        self.assertEqual(detail.data["career_year"], 3)
