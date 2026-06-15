from django.urls import path

from .views import AuditLogListView, DashboardStatsView, MemberInviteView, MemberListView, MemberStatsView, MemberStatusView
from .views_member_detail import MemberDetailView


urlpatterns = [
    path('dashboard', DashboardStatsView.as_view(), name='admin-dashboard'),
    path('members/stats', MemberStatsView.as_view(), name='admin-member-stats'),
    path('members/invite', MemberInviteView.as_view(), name='admin-member-invite'),
    path('members', MemberListView.as_view(), name='admin-member-list'),
    path('members/<int:member_id>/status', MemberStatusView.as_view(), name='admin-member-status'),
    path('members/<int:member_id>', MemberDetailView.as_view(), name='admin-member-detail'),
    path('audit-logs', AuditLogListView.as_view(), name='admin-audit-log-list'),
]
