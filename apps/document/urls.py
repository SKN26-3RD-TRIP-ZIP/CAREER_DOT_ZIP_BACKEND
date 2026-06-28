from django.urls import path

from .views import DocumentDetailView, DocumentListView, DocumentUploadView


urlpatterns = [
    path('documents/upload', DocumentUploadView.as_view(), name='document-upload'),
    path('documents', DocumentListView.as_view(), name='document-list'),
    path('documents/<uuid:document_id>', DocumentDetailView.as_view(), name='document-detail'),
]
