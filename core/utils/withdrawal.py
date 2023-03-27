from django.db.models import Q

from core.consts.currencies import BEP20_CURRENCIES
from core.consts.currencies import ERC20_CURRENCIES
from core.consts.currencies import TRC20_CURRENCIES
from core.models.inouts.withdrawal import WithdrawalRequest, CREATED, PENDING


def get_withdrawal_requests_to_process(currencies: list, blockchain_currency=''):
    tokens = []
    coins = []
    for cur in currencies:
        if cur in ERC20_CURRENCIES or cur in TRC20_CURRENCIES or cur in BEP20_CURRENCIES:
            tokens.append(cur)
        else:
            coins.append(cur)

    if tokens and not blockchain_currency:
        raise Exception('Blockchain currency not set')

    qs = WithdrawalRequest.objects.filter(
        (Q(currency__in=tokens) & Q(data__blockchain_currency=blockchain_currency)) | Q(currency__in=coins),
        state=CREATED,
        approved=True,
        confirmed=True,
    ).order_by(
        'created',
    ).only(
        'id',
    )

    return qs


def get_withdrawal_requests_pending(currencies: list, blockchain_currency=''):
    # TODO REFACTOR
    common_currencies = []
    not_common_currencies = []
    common_qs = None
    for cur in currencies:
        if cur in ERC20_CURRENCIES or cur in TRC20_CURRENCIES or cur in BEP20_CURRENCIES:
            common_currencies.append(cur)
        else:
            not_common_currencies.append(cur)

    if common_currencies and not blockchain_currency:
        raise Exception('Blockchain currency not set')

    if common_currencies:
        common_qs = WithdrawalRequest.objects.filter(
            currency__in=common_currencies,
            state=PENDING,
            approved=True,
            confirmed=True,
            data__blockchain_currency=blockchain_currency
        ).only(
            'id',
            'txid',
        )

    qs = WithdrawalRequest.objects.filter(
        currency__in=not_common_currencies,
        state=PENDING,
        approved=True,
        confirmed=True,
    ).only(
        'id',
        'txid',
    )

    if common_qs:
        qs = qs.union(common_qs)

    return qs