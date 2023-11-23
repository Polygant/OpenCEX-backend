import hashlib
import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework import permissions, status, views, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core.exceptions.inouts import WithdrawalAlreadyConfirmed
from core.models.inouts.withdrawal import WithdrawalRequest, WithdrawalUserLimit
from core.serializers.withdrawal import (
    WithdrawalSerializer,
    ConfirmationTokenSerializer,
    ResendWithdrawalRequestConfirmationEmailSerializer, CancelWithdrawalRequestEmailSerializer
)
from core.tasks.inouts import send_withdrawal_confirmation_email
from core.utils import get_rand_code
from lib.filterbackend import FilterBackend


class WithdrawalRequestView(viewsets.ReadOnlyModelViewSet, viewsets.mixins.CreateModelMixin):
    serializer_class = WithdrawalSerializer
    queryset = WithdrawalRequest.objects.all()
    filter_backends = (FilterBackend,)

    def get_queryset(self):
        qs = super(WithdrawalRequestView, self).get_queryset()
        return qs.filter(user=self.request.user)

    def perform_create(self, serializer):
        with transaction.atomic():
            instance = serializer.save()
            confirmation_token = self._make_confirmation_token(instance)

            instance.confirmation_token = confirmation_token
            instance.save(update_fields=['confirmation_token'])

            # send confirmation info
            send_withdrawal_confirmation_email.apply_async([instance.id])

    @staticmethod
    def _make_confirmation_token(withdrawal_request: WithdrawalRequest) -> str:
        token = get_rand_code(6)
        while WithdrawalRequest.objects.filter(confirmation_token=token, user=withdrawal_request.user).exists():
            token = get_rand_code(6)
        return token


class ConfirmWithdrawalRequestView(views.APIView):
    """
    Email withdrawal confirmation link handler
    """
    # permission_classes = [
    #     permissions.AllowAny,
    # ]

    @extend_schema(
        request=ConfirmationTokenSerializer,
    )
    def post(self, request):
        serializer = ConfirmationTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        expiration_date = timezone.now() - timezone.timedelta(minutes=settings.WITHDRAWAL_REQUEST_EXPIRATION_M)
        withdrawal_request = WithdrawalRequest.objects.filter(
            confirmation_token__iexact=serializer.data['confirmation_token'],
            created__gt=expiration_date,
            user=request.user,
        ).only('id').first()

        if withdrawal_request is None:
            return Response(data='Withdrawal request does not exists or expired',
                            status=status.HTTP_404_NOT_FOUND)

        if withdrawal_request.confirmed:
            raise WithdrawalAlreadyConfirmed()

        withdrawal_request.confirmed = True
        withdrawal_request.save(update_fields=['confirmed'])

        return Response({})


class CancelWithdrawalRequestView(views.APIView):
    """
    Email withdrawal cancelling link handler
    """
    permission_classes = [
        permissions.AllowAny,
    ]

    @extend_schema(
        request=CancelWithdrawalRequestEmailSerializer,
    )
    def post(self, request):
        serializer = CancelWithdrawalRequestEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        expiration_date = timezone.now() - timezone.timedelta(minutes=settings.WITHDRAWAL_REQUEST_EXPIRATION_M)
        filter_data = {
            'created__gt': expiration_date,
            'confirmed': False,
        }

        if 'confirmation_token' not in serializer.data and 'withdrawal_request_id' not in serializer.data:
            raise ValidationError({
                "confirmation_token": "Incorrect data.",
                "withdrawal_request_id": "Incorrect data.",
            }, code="incorrect_data")

        if 'confirmation_token' in serializer.data:
            filter_data['confirmation_token'] = serializer.data['confirmation_token']

        if 'withdrawal_request_id' in serializer.data:
            filter_data['pk'] = serializer.data['withdrawal_request_id']

        withdrawal_request = WithdrawalRequest.objects.filter(
            **filter_data
        ).only('id').first()

        if withdrawal_request is None:
            return Response(data='Withdrawal request does not exists or expired',
                            status=status.HTTP_404_NOT_FOUND)

        if withdrawal_request.confirmed:
            raise WithdrawalAlreadyConfirmed()

        withdrawal_request.cancel()

        return Response({})


class WithdrawalRequestInfoView(views.APIView):
    """
    We can make `lookup_field = 'confirmation_token'` in WithdrawalRequestView
    but it requires authorization
    """
    permission_classes = [
        permissions.AllowAny,
    ]

    @extend_schema(
        responses=WithdrawalSerializer,
    )
    def get(self, request, token):
        expiration_date = timezone.now() - timezone.timedelta(minutes=settings.WITHDRAWAL_REQUEST_EXPIRATION_M)
        withdrawal_request = WithdrawalRequest.objects.filter(
            confirmation_token__iexact=token,
            confirmed=False,
            created__gt=expiration_date,
        ).first()

        if withdrawal_request is None:
            return Response(data='Withdrawal request does not exists or expired',
                            status=status.HTTP_404_NOT_FOUND)

        serializer = WithdrawalSerializer(instance=withdrawal_request)

        return Response(serializer.data)


class ResendWithdrawalRequestConfirmationEmailView(views.APIView):
    """
    Resend confirmation email
    """
    @extend_schema(
        request=ResendWithdrawalRequestConfirmationEmailSerializer,
    )
    def post(self, request):
        serializer = ResendWithdrawalRequestConfirmationEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        expiration_date = timezone.now() - timezone.timedelta(minutes=settings.WITHDRAWAL_REQUEST_EXPIRATION_M)

        filter_data = {
            'created__gt': expiration_date
        }

        if 'confirmation_token' not in serializer.data and 'withdrawal_request_id' not in serializer.data:
            raise ValidationError({
                "confirmation_token": "Incorrect data.",
                "withdrawal_request_id": "Incorrect data.",
            }, code="incorrect_data")

        if 'confirmation_token' in serializer.data:
            filter_data['confirmation_token'] = serializer.data['confirmation_token']

        if 'withdrawal_request_id' in serializer.data:
            filter_data['pk'] = serializer.data['withdrawal_request_id']

        withdrawal_request = WithdrawalRequest.objects.filter(
            **filter_data,
        ).only('id').first()

        if withdrawal_request is None:
            return Response(data='Withdrawal request does not exists or expired',
                            status=status.HTTP_404_NOT_FOUND)

        if withdrawal_request.confirmed:
            raise WithdrawalAlreadyConfirmed()

        send_withdrawal_confirmation_email.apply_async([withdrawal_request.id])
        return Response(status=status.HTTP_200_OK)


class WithdrawalUserLimitView(views.APIView):

    @extend_schema(
        responses={
            200: OpenApiTypes.OBJECT,
        },
        examples=[
            OpenApiExample(
                'Example',
                summary='response',
                value={
                    'current_limit_amount': 0,
                    'level': 0,
                    'level_limit': 0,
                },
                request_only=False,  # signal that example only applies to requests
                response_only=True,  # signal that example only applies to responses
            ),
        ]
    )
    def get(self, request):
        limit_data = WithdrawalUserLimit.get_limits(request.user)
        user_limit = limit_data.get('limit')

        return Response({
            'current_limit_amount': limit_data.get('amount', 0),
            'level': user_limit.level,
            'level_limit': user_limit.amount,
        })
