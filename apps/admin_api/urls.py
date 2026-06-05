from django.urls import path

from .views import AuditLogListView, MemberListView, MemberStatusView


urlpatterns = [
    path('members', MemberListView.as_view(), name='admin-member-list'),
    path(
        'members/<int:member_id>/status',
        MemberStatusView.as_view(),
        name='admin-member-status',
    ),
    path('audit-logs', AuditLogListView.as_view(), name='admin-audit-log-list'),
]
