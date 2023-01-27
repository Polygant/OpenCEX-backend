from django.urls import path, re_path

from rest_framework.routers import DefaultRouter

from core.views.withdrawal import (WithdrawalRequestView, ConfirmWithdrawalRequestView,
                                   WithdrawalRequestInfoView, CancelWithdrawalRequestView,
                                   ResendWithdrawalRequestConfirmationEmailView, WithdrawalUserLimitView)


router = DefaultRouter()
router.register(r'', WithdrawalRequestView, basename='withdrawal')

urlpatterns = [
    path('confirm-withdrawal-request', ConfirmWithdrawalRequestView.as_view(),
         name='confirm-withdrawal-request'),
    path('cancel-withdrawal-request', CancelWithdrawalRequestView.as_view(),
         name='cancel-withdrawal-request'),
    re_path(r'withdrawal-request-info/(?P<token>[\w]{64})', WithdrawalRequestInfoView.as_view(),
            name='withdrawal-request-info'),
    path('resend-withdrawal-request', ResendWithdrawalRequestConfirmationEmailView.as_view(),
         name='resend-withdrawal-request'),
    path('limits-withdrawal-request', WithdrawalUserLimitView.as_view(),
         name='limits-withdrawal-request'),
]

urlpatterns += router.urls
