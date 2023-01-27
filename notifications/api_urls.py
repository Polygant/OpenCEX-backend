from rest_framework.routers import DefaultRouter

from notifications.views import NotificationView
from notifications.views import UserNotificationView

router = DefaultRouter()
router.register(r'notifications', NotificationView, basename='notifications')
router.register(r'user_notifications', UserNotificationView, basename='user_notifications')

urlpatterns = []

urlpatterns.extend(router.urls)
