from django.urls import path

from .views import (
    AdminPointAdjustView,
    AdminPointHistoryView,
    AdminPointPolicyListView,
    AdminPointPolicyUpdateView,
    AuditLogListView,
    DashboardStatsView,
    MemberDetailView,
    MemberInviteView,
    MemberListView,
    MemberStatsView,
    MemberStatusView,
)


urlpatterns = [
    path('dashboard', DashboardStatsView.as_view(), name='admin-dashboard'),
    path('members/stats', MemberStatsView.as_view(), name='admin-member-stats'),
    path('members/invite', MemberInviteView.as_view(), name='admin-member-invite'),
    path('members', MemberListView.as_view(), name='admin-member-list'),
    path('members/<int:member_id>/points/adjust', AdminPointAdjustView.as_view(), name='admin-member-points-adjust'),
    path('members/<int:member_id>/status', MemberStatusView.as_view(), name='admin-member-status'),
    path('members/<int:member_id>', MemberDetailView.as_view(), name='admin-member-detail'),
    path('points/history', AdminPointHistoryView.as_view(), name='admin-points-history'),
    path('points/policies', AdminPointPolicyListView.as_view(), name='admin-points-policies'),
    path('points/policies/<int:policy_id>', AdminPointPolicyUpdateView.as_view(), name='admin-points-policy-update'),
    path('audit-logs', AuditLogListView.as_view(), name='admin-audit-log-list'),
]
