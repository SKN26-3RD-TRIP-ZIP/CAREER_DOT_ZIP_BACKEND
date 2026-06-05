import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import UploadedDocument


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class DocumentAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email='document-owner@example.com',
            password='password123',
            name='Owner',
        )
        self.other_user = user_model.objects.create_user(
            email='document-other@example.com',
            password='password123',
            name='Other',
        )
        self.client.force_authenticate(self.user)

    def test_upload_txt_extracts_text(self):
        uploaded_file = SimpleUploadedFile(
            'resume.txt',
            'Hello document'.encode('utf-8'),
            content_type='text/plain',
        )

        response = self.client.post(
            reverse('document-upload'),
            {'file': uploaded_file, 'document_type': 'resume'},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['parse_status'], 'completed')
        self.assertEqual(response.data['extracted_text'], 'Hello document')

    def test_upload_rejects_unsupported_file(self):
        uploaded_file = SimpleUploadedFile('resume.exe', b'content')

        response = self.client.post(
            reverse('document-upload'),
            {'file': uploaded_file, 'document_type': 'resume'},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_and_detail_only_return_owned_documents(self):
        owned = UploadedDocument.objects.create(
            user=self.user,
            document_type='resume',
            file=SimpleUploadedFile('owned.txt', b'owned'),
            original_filename='owned.txt',
            file_type='txt',
            file_size=5,
        )
        other = UploadedDocument.objects.create(
            user=self.other_user,
            document_type='resume',
            file=SimpleUploadedFile('other.txt', b'other'),
            original_filename='other.txt',
            file_type='txt',
            file_size=5,
        )

        list_response = self.client.get(reverse('document-list'))
        detail_response = self.client.get(
            reverse('document-detail', kwargs={'document_id': owned.id})
        )
        other_response = self.client.get(
            reverse('document-detail', kwargs={'document_id': other.id})
        )

        self.assertEqual(list_response.data['total'], 1)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(other_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_removes_database_row_and_file(self):
        document = UploadedDocument.objects.create(
            user=self.user,
            document_type='other',
            file=SimpleUploadedFile('delete.txt', b'delete'),
            original_filename='delete.txt',
            file_type='txt',
            file_size=6,
        )
        file_path = Path(document.file.path)

        response = self.client.delete(
            reverse('document-detail', kwargs={'document_id': document.id})
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(UploadedDocument.objects.filter(id=document.id).exists())
        self.assertFalse(file_path.exists())

    def test_authentication_is_required(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(reverse('document-list'))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
