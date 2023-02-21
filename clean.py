import os
import random
import time



os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'exchange.settings')
import django

django.setup()

from django.db.transaction import atomic
from bots.models import BotConfig
from cryptocoins.models import AccumulationTransaction

from core.models import Balance, UserWallet, UserFee, UserExchangeFee
from django.contrib.auth import get_user_model
from django.db.models import Q


# todo needs to repair
def main():
    with atomic():
        users = get_user_model().objects.filter(~Q(is_staff=True) & ~Q(username__iregex="^bot[0-9]+@bot.com$")).all()

        wallets = UserWallet.objects.filter(user__in=users)
        accumulation_state = AccumulationState.objects.filter(wallet__in=wallets.all())
        AccumulationTransaction.objects.filter(accumulation_state__in=accumulation_state.all()).delete()
        accumulation_state.delete()

        BotConfig.objects.filter(user__in=users).delete()
        # MarketTradeRequest.objects.filter(user__in=users).delete()
        UserFee.objects.filter(user__in=users).delete()
        UserExchangeFee.objects.filter(user__in=users).delete()

        for user in users:
            user.delete()

        Balance.objects.update(amount=0, amount_in_orders=0)
        wallets2 = UserWallet.objects.filter(~Q(user__isnull=True) & ~Q(user__username__iregex="^bot[0-9]+@bot.com$"))
        accumulation_state = AccumulationState.objects.filter(wallet__in=wallets2.all())
        AccumulationTransaction.objects.filter(accumulation_state__in=accumulation_state.all()).delete()
        accumulation_state.delete()
        wallets2.delete()


if __name__ == '__main__':
    print('Start')
    main()
    print('Stop')

