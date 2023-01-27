import logging

from django.core.management.base import BaseCommand
from core.models import UserRestrictions
from core.models import WithdrawalRequest

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Disables withdrawals for users and cancel created withrawals'

    def add_arguments(self, parser):
        parser.add_argument('-e', '--exclude', help="list of excluded emails separated by comma", type=str)

    def handle(self, *args, **options):
        exclude = options.get('exclude')
        if exclude:
            exclude = exclude.split(',')

        restrictions_qs = UserRestrictions.objects.all()
        if exclude:
            restrictions_qs = restrictions_qs.exclude(
                user__email__in=exclude
            )
        restrictions_qs.update(disable_withdrawals=True)

        withdrawals_qs = WithdrawalRequest.objects.filter(
            state__in=[WithdrawalRequest.STATE_CREATED, WithdrawalRequest.STATE_VERIFYING]
        )
        if exclude:
            withdrawals_qs = withdrawals_qs.exclude(
                user__email__in=exclude,
            )

        for wd in withdrawals_qs:
            if wd.state == WithdrawalRequest.STATE_VERIFYING:
                wd.state = WithdrawalRequest.STATE_CREATED
                wd.save()
            wd.cancel()
