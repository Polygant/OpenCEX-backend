from rest_framework import serializers
from notifications.models import Notification


class NotificationsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('id', 'title', 'text', 'type')


class NotificationDetailSerializer(serializers.ModelSerializer):

    class Meta:
        model = Notification
        fields = ('data', 'date', 'type')

    def create(self, validated_data):
        return Notification.objects.create(**validated_data)
