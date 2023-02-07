from django.contrib.auth import get_user_model
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework import permissions
from rest_framework import viewsets, status
from rest_framework.response import Response

from notifications.serializers import NotificationsSerializer

User = get_user_model()

from notifications.helpers import get_order_notifications


class NotificationView(viewsets.ViewSet):
    @extend_schema(
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value={
                    'data': {
                        'id',
                        'state',
                        'pair',
                        'operation',
                        'type',
                        'quantity',
                        'price',
                    },
                    'date': "<str>",
                    'type': "<str: ORDER_OPEN|ORDER_CANCEL|ORDER_CLOSE>",
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
    def list(self, request):
        data = []

        if not request.user.is_anonymous:
            data = get_order_notifications(request.user.id, destroy=True)

        return Response(data, status=status.HTTP_200_OK)


class UserNotificationView(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]
    http_method_names = ['get', 'delete']

    @extend_schema(
        responses=NotificationsSerializer,
    )
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
