from django.urls import path

from .views import AuditLogListView, MemberListView, MemberStatusView
from .views_member_detail import MemberDetailView


urlpatterns = [
    path('members', MemberListView.as_view(), name='admin-member-list'),
    path('members/<int:member_id>', MemberDetailView.as_view(), name='admin-member-detail'),
    path(
        'members/<int:member_id>/status',
        MemberStatusView.as_view(),
        name='admin-member-status',
    ),
    path('audit-logs', AuditLogListView.as_view(), name='admin-audit-log-list'),
]
