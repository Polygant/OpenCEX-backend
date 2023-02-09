from django.urls import path
from django.urls.conf import include

from core.views.facade import MessagesView
from core.views.facade import RegenerateApiKey
from core.views.facade import SourceOfFundsViewSet
from core.views.facade import UserProfileView
from core.views.facade import check_kyc_verification
from core.views.facade import check_otp
from core.views.facade import check_user_2fa_is_on
from core.views.facade import coins_api_view
from core.views.facade import generate_secret
from core.views.facade import kyc_callback_url
from core.views.facade import kyc_get_access_token
from core.views.facade import mark_message_as_read, CountryList, PhoneVerification, CodePhoneVerification, CaptchaCheck
from core.views.facade import remove_user_2fa
from core.views.facade import resend_email_confirmation_mail
from core.views.facade import save_user_language
from core.views.facade import set_user_2fa

urlpatterns = [
    path(r'auth/registration/', include('dj_rest_auth.registration.urls')),
    path(r'auth/', include('dj_rest_auth.urls')),
    path(r'check2fa/', check_user_2fa_is_on),
    path(r'check_captcha/', CaptchaCheck.as_view()),
    path(r'gen_secret/', generate_secret),
    path(r'checkotp/', check_otp),
    path(r'set2fa/', set_user_2fa),
    path(r'remove2fa/', remove_user_2fa),
    path(r'kyc_get_access_token/', kyc_get_access_token),
    path(r'kyc_callback/', kyc_callback_url),
    path(r'check_kyc/', check_kyc_verification),
    path(r'countries/', CountryList.as_view()),
    path(r'messages/mark_read/', mark_message_as_read),
    path(r'messages/', MessagesView.as_view({'get': 'list'})),
    path(r'profile/', UserProfileView.as_view(actions={'get': 'retrieve', 'post': 'update', 'put': 'update'})),
    path(r'regenerate-api-key/', RegenerateApiKey.as_view()),
    path(r'phone-verify/check/', CodePhoneVerification.as_view()),
    path(r'phone-verify/', PhoneVerification.as_view()),
    path(r'sof', SourceOfFundsViewSet.as_view(actions={'get': 'retrieve', 'post': 'create'})),
    path(r'language/', save_user_language),
    path(r'coins/', coins_api_view),
    path(r'resend-email-confirmation/', resend_email_confirmation_mail),
]
