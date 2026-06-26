from django.urls import path

from .views_points import MyPointBalanceView, MyPointHistoryView


urlpatterns = [
    path("users/me/points", MyPointBalanceView.as_view(), name="my-point-balance"),
    path("users/me/points/history", MyPointHistoryView.as_view(), name="my-point-history"),
]
