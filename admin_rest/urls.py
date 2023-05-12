from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

from admin_rest import restful_admin
from admin_rest import views

urlpatterns = [
    path('login/', views.login),
    path('user/', views.me),
    path('permissions/', views.permissions),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('models/', views.models),
    path('resources/', views.resources),
    path('navigation/', views.navigation),
    path('upload/image/', views.upload_image),
    path('browser/image/', views.image_browser),
]

urlpatterns += restful_admin.site.urls