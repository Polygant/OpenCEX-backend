import logging

from core.currency import Currency
from cryptocoins.exceptions import ScoringClientError
from cryptocoins.models.scoring import TransactionInputScore, ScoringSettings
from cryptocoins.scoring.scorechain_client.bitcoin import scorechain_bitcoin_client
from cryptocoins.scoring.scorechain_client.bnb import scorechain_bnb_client
from cryptocoins.scoring.scorechain_client.ethereum import scorechain_ethereum_client
from cryptocoins.scoring.scorechain_client.tron import scorechain_tron_client
from lib.helpers import to_decimal
from lib.notifications import send_telegram_message

log = logging.getLogger(__name__)


class ScoreManager:
    """
    Score parsing, storing and calculating
    """

    @classmethod
    def get_client(cls, currency):
        currency = str(currency)
        if currency in ['BTC']:
            return scorechain_bitcoin_client
        elif currency in ['ETH']:
            return scorechain_ethereum_client
        elif currency in ['TRX']:
            return scorechain_tron_client
        elif currency in ['BNB']:
            return scorechain_bnb_client
        raise Exception(f'Scorechain client for {currency} not found')

    @classmethod
    def get_address_score_info(cls, address, currency_code, token_currency=None):
        """
        Get scoring info from provider, update
        related data, etc
        """
        scorechain_client = cls.get_client(currency_code)
        address_data = scorechain_client.get_address_summary(address, scorechain_client.TYPE_INPUT, token_currency)
        return address_data

    @classmethod
    def is_address_scoring_ok(cls, tx_id, address, amount, currency_code, token_currency=None):
        from cryptocoins.models.scoring import TransactionInputScore
        from cryptocoins.models.scoring import ScoringSettings
        from core.models import UserWallet

        if isinstance(currency_code, Currency):
            currency_code = currency_code.code

        # check target addresses scoring
        is_address_scoring_ok = True
        try:
            addr_risk_data = ScoreManager.get_address_score_info(address, currency_code, token_currency)
        except:
            raise ScoringClientError()
        addr_score = addr_risk_data.get('riskscore', {}).get('value', 0) or 0

        amount = to_decimal(amount)

        #  log new tx and address with scoring
        tis = TransactionInputScore.objects.filter(hash=tx_id).first()
        if tis:
            tis.score = addr_score
            tis.data = addr_risk_data
        else:
            tis = TransactionInputScore(
                hash=tx_id,
                address=address,
                score=addr_score,
                data=addr_risk_data,
                currency=currency_code,
                token_currency=token_currency,
            )

        if addr_score < ScoringSettings.get_accumulation_min_score(currency_code):
            msg = f'Score of {currency_code} address {address} too low for deposit: {addr_score}'
            send_telegram_message(msg)
            log.error(msg)

            is_address_scoring_ok = False

            user_wallet = UserWallet.objects.filter(
                currency=currency_code,
                address=address,
            ).first()
            tis.scoring_state = TransactionInputScore.SCORING_STATE_FAILED

            if user_wallet:
                user_wallet.block_type = UserWallet.BLOCK_TYPE_DEPOSIT_AND_ACCUMULATION
                user_wallet.save()
            else:
                log.error(f'UserWallet with address {address} does not exists')
        else:
            # make_deposit(tx_id, currency_code, address, amount)
            tis.deposit_made = True
            tis.scoring_state = TransactionInputScore.SCORING_STATE_OK
        tis.save()

        return is_address_scoring_ok

    @classmethod
    def need_to_check_score(cls, tx_hash, address, amount, currency_code):
        res = True
        tis = TransactionInputScore.objects.filter(
            hash=tx_hash,
            address=address,
            currency=currency_code,
        ).first()

        if not tis:
            tis = TransactionInputScore(
                hash=tx_hash,
                address=address,
                score=0,
                currency=currency_code,
            )

        settings = ScoringSettings.get_settings(currency_code)

        if not settings:
            res = False

        if settings and amount < settings['min_tx_amount']:
            tis.scoring_state = TransactionInputScore.SCORING_STATE_SMALL_AMOUNT
            res = False
        tis.save()

        return res
