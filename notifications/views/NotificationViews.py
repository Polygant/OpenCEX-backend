from django.contrib.auth import get_user_model
from rest_framework import permissions
from rest_framework import viewsets, status
from rest_framework.response import Response

from notifications.serializers import NotificationsSerializer

User = get_user_model()

from notifications.helpers import get_order_notifications


class NotificationView(viewsets.ViewSet):
    """
    Список
    """
    def list(self, request):
        data = []

        if not request.user.is_anonymous:
            data = get_order_notifications(request.user.id, destroy=True)

        return Response(data, status=status.HTTP_200_OK)


class UserNotificationView(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]
    http_method_names = ['get', 'delete']

    def list(self, request):
        data = []
        if not request.user.is_anonymous:
            queryset = request.user.notifications.all()
            serializer = NotificationsSerializer(queryset, many=True)
            data = serializer.data
        return Response(data)

    def destroy(self, request, pk):
        if not request.user.is_anonymous:
            request.user.notifications.remove(pk)
        return Response({})
