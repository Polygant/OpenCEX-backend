import json
import os
from datetime import datetime

from core.enums.profile import UserTypeEnum

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'exchange.settings')
import django

django.setup()

from allauth.account.models import EmailAddress

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.db.models import QuerySet
from django.db.transaction import atomic
from django_otp.plugins.otp_totp.models import TOTPDevice

from cryptocoins.coins.btc.service import BTCCoinService
from cryptocoins.models import Keeper, GasKeeper, LastProcessedBlock
from cryptocoins.utils.commons import create_keeper

from core.consts.currencies import CRYPTO_WALLET_CREATORS
from core.currency import Currency
from core.utils.wallet_history import create_or_update_wallet_history_item_from_transaction
from core.models import UserWallet, UserFee, Profile, DisabledCoin
from core.models import Transaction
from core.models import FeesAndLimits
from core.models import PairSettings
from core.models import WithdrawalFee
from core.models.facade import CoinInfo
from core.models.inouts.transaction import REASON_MANUAL_TOPUP
from core.pairs import Pair
from cryptocoins.coins.btc import BTC, BTC_CURRENCY
from cryptocoins.coins.eth import ETH
from cryptocoins.coins.usdt import USDT
from cryptocoins.coins.bnb import BNB
from cryptocoins.coins.trx import TRX

from cryptocoins.utils.btc import generate_btc_multisig_keeper

from exchange.settings import env
from bots.models import BotConfig
from lib.cipher import AESCoderDecoder

User = get_user_model()

BACKUP_PATH = os.path.join(settings.BASE_DIR, 'backup')


def main():

    IS_TRON = True if env('COMMON_TASKS_TRON', default=True) else False
    IS_BSC = True if env('COMMON_TASKS_BNB', default=True) else False

    coin_list = [
        ETH,
        BTC,
        USDT,
        BNB,
        TRX,
    ]
    coin_info = {
        ETH: [
            {
                'model': CoinInfo,
                'find': {'currency': ETH},
                'attributes': {
                    'name': 'Ethereum',
                    'decimals': 8,
                    'index': 3,
                    'tx_explorer': 'https://etherscan.io/tx/',
                    'links': {
                        "bt": {
                            "href": "https://bitcointalk.org/index.php?topic=428589.0",
                            "title": "BitcoinTalk"
                        },
                        "cmc": {
                            "href": "https://coinmarketcap.com/currencies/ethereum/",
                            "title": "CoinMarketCap"
                        },
                        "exp": {
                            "href": "https://etherscan.io/",
                            "title": "Explorer"
                        },
                        "official": {
                            "href": "http://ethereum.org",
                            "title": "ethereum.org"
                        }
                    }
                }
            },
            {
                'model': FeesAndLimits,
                'find': {'currency': ETH},
                    'attributes': {
                    'limits_deposit_min': 0.00500000,
                    'limits_deposit_max': 1000.00000000,
                    'limits_withdrawal_min': 0.00500000,
                    'limits_withdrawal_max': 15.00000000,
                    'limits_order_min': 0.00100000,
                    'limits_order_max': 15.00000000,
                    'limits_code_max': 100.00000000,
                    'limits_accumulation_min': 0.00500000,
                    'fee_deposit_address': 0.00000010,
                    'fee_deposit_code': 0,
                    'fee_withdrawal_code': 0,
                    'fee_order_limits': 0.00100000,
                    'fee_order_market': 0.00200000,
                    'fee_exchange_value': 0.00200000,

                },
            },
            {
                'model': WithdrawalFee,
                'find': {'currency': ETH},
                'attributes': {
                    'blockchain_currency': ETH,
                    'address_fee': 0.00000010
                }
            },
        ],
        BTC: [
            {
                'model': CoinInfo,
                'find': {'currency': BTC},
                'attributes': {
                    'name': 'Bitcoin',
                    'decimals': 8,
                    'index': 2,
                    'tx_explorer': 'https://www.blockchain.com/btc/tx/',
                    'links': {
                        "bt": {
                            "href": "https://bitcointalk.org/index.php",
                            "title": "BitcoinTalk"
                        },
                        "cmc": {
                            "href": "https://coinmarketcap.com/currencies/bitcoin/",
                            "title": "CoinMarketCap"
                        },
                        "exp": {
                            "href": "https://www.blockchain.com/en/explorer",
                            "title": "Explorer"
                        },
                        "official": {
                            "href": "https://bitcoin.org",
                            "title": "bitcoin"
                        }
                    }
                },
            },
            {
                'model': FeesAndLimits,
                'find': {'currency': BTC},
                'attributes': {
                    'limits_deposit_min': 0.00020000,
                    'limits_deposit_max': 100,
                    'limits_withdrawal_min': 0.00020000,
                    'limits_withdrawal_max': 5,
                    'limits_order_min': 0.00030000,
                    'limits_order_max': 5.00000000,
                    'limits_code_max': 100.00000000,
                    'limits_accumulation_min': 0.00020000,
                    'fee_deposit_address': 0,
                    'fee_deposit_code': 0,
                    'fee_withdrawal_code': 0,
                    'fee_order_limits': 0.00100000,
                    'fee_order_market': 0.00200000,
                    'fee_exchange_value': 0.00200000,

                },
            },
            {
                'model': WithdrawalFee,
                'find': {'currency': BTC},
                'attributes': {
                    'blockchain_currency': BTC,
                    'address_fee': 0.00000001
                },
            },
        ],
        USDT: [
            {
                'model': CoinInfo,
                'find': {'currency': USDT},
                'attributes': {
                    'name': 'Tether USDT',
                    'decimals': 2,
                    'index': 1,
                    'links': {
                        "cmc": {
                            "href": "https://coinmarketcap.com/currencies/tether/",
                            "title": "CoinMarketCap"
                        },
                        "exp": {
                            "href": "https://coin-cap.pro/en/contract/tether/",
                            "title": "Explorer"
                        },
                        "official": {
                            "href": "https://tether.to/",
                            "title": "tether.to"
                        }
                    }
                },
            },
            {
                'model': FeesAndLimits,
                'find': {'currency': USDT},
                'attributes': {
                    'limits_deposit_min': 1.00000000,
                    'limits_deposit_max': 1000000.00000000,
                    'limits_withdrawal_min': 2.00000000,
                    'limits_withdrawal_max': 10000.00000000,
                    'limits_order_min': 1.00000000,
                    'limits_order_max': 100000.00000000,
                    'limits_code_max': 100000.00000000,
                    'limits_accumulation_min': 1.00000000,
                    'fee_deposit_address': 0,
                    'fee_deposit_code': 0,
                    'fee_withdrawal_code': 0,
                    'fee_order_limits': 0.00100000,
                    'fee_order_market': 0.00200000,
                    'fee_exchange_value': 0.00200000,
                },
            },
            {
                'model': WithdrawalFee,
                'find': {'currency': USDT, 'blockchain_currency': ETH},
                'attributes': {
                    'blockchain_currency': ETH,
                    'address_fee': 5.00000000
                },
            },
            {
                'model': WithdrawalFee,
                'find': {'currency': USDT, 'blockchain_currency': BNB},
                'attributes': {
                    'blockchain_currency': BNB,
                    'address_fee': 0.00010000
                },
            },
            {
                'model': WithdrawalFee,
                'find': {'currency': USDT, 'blockchain_currency': TRX},
                'attributes': {
                    'blockchain_currency': TRX,
                    'address_fee': 1.00000000
                },
            },
        ],
        TRX: [
            {
                'model': CoinInfo,
                'find': {'currency': TRX},
                'attributes': {
                    'name': 'Tron',
                    'decimals': 8,
                    'index': 5,
                    'tx_explorer': 'https://tronscan.org/#/transaction/',
                    'links': {
                        "cmc": {
                            "href": "https://coinmarketcap.com/currencies/tron/",
                            "title": "CoinMarketCap"
                        },
                        "exp": {
                            "href": "https://coin-cap.pro/en/coin/tron/",
                            "title": "Explorer"
                        },
                        "official": {
                            "href": "https://tron.network/",
                            "title": "tron.network"
                        }
                    }
                },
            },
            {
                'model': FeesAndLimits,
                'find': {'currency': TRX},
                'attributes': {
                    'limits_deposit_min': 1.00000000,
                    'limits_deposit_max': 100000000.00000000,
                    'limits_withdrawal_min': 1.00000000,
                    'limits_withdrawal_max': 10000000.00000000,
                    'limits_order_min': 1.00000000,
                    'limits_order_max': 1000000.00000000,
                    'limits_code_max': 1000000.00000000,
                    'limits_accumulation_min': 1.00000000,
                    'fee_deposit_address': 0,
                    'fee_deposit_code': 0,
                    'fee_withdrawal_code': 0,
                    'fee_order_limits': 0.00100000,
                    'fee_order_market': 0.00200000,
                    'fee_exchange_value': 0.00200000,
                },
            },
            {
                'model': WithdrawalFee,
                'find': {'currency': TRX},
                'attributes': {
                    'blockchain_currency': TRX,
                    'address_fee': 1.00000000
                },
            },
        ],
        BNB: [
            {
                'model': CoinInfo,
                'find': {'currency': BNB},
                'attributes': {
                    'name': 'Binance Coin',
                    'decimals': 8,
                    'index': 6,
                    'tx_explorer': 'https://bscscan.com/tx/',
                    'links': {
                        "cmc": {
                            "href": "https://coinmarketcap.com/currencies/bnb/",
                            "title": "CoinMarketCap"
                        },
                        "exp": {
                            "href": "https://bscscan.com/",
                            "title": "Explorer"
                        },
                        "official": {
                            "href": "https://www.binance.com/",
                            "title": "www.binance.com"
                        }
                    }
                },
            },
            {
                'model': FeesAndLimits,
                'find': {'currency': BNB},
                'attributes': {
                    'limits_deposit_min': 0.00010000,
                    'limits_deposit_max': 1000000.00000000,
                    'limits_withdrawal_min': 0.00100000,
                    'limits_withdrawal_max': 1000000.00000000,
                    'limits_order_min': 0.01000000,
                    'limits_order_max': 1000000.00000000,
                    'limits_code_max': 1000000.00000000,
                    'limits_accumulation_min': 0.00100000,
                    'fee_deposit_address': 0,
                    'fee_deposit_code': 0,
                    'fee_withdrawal_code': 0,
                    'fee_order_limits': 0.00100000,
                    'fee_order_market': 0.00200000,
                    'fee_exchange_value': 0.00200000,
                },
            },
            {
                'model': WithdrawalFee,
                'find': {'currency': BNB},
                'attributes': {
                    'blockchain_currency': BNB,
                    'address_fee': 0.00010000
                },
            },
        ],
    }

    if not IS_BSC:
        coin_info[BNB].append(
            {
                'model': DisabledCoin,
                'find': {'currency': BNB},
                'attributes': {
                    'disable_all': True,
                    'disable_stack': True,
                    'disable_pairs': True,
                    'disable_exchange': True,
                    'disable_withdrawals': True,
                    'disable_topups': True,
                },
            },
        )

    if not IS_TRON:
        coin_info[TRX].append(
            {
                'model': DisabledCoin,
                'find': {'currency': TRX},
                'attributes': {
                    'disable_all': True,
                    'disable_stack': True,
                    'disable_pairs': True,
                    'disable_exchange': True,
                    'disable_withdrawals': True,
                    'disable_topups': True,
                },
            },
        )

    with atomic():
        to_write = []

        def get_or_create(model_inst, curr, get_attrs, set_attrs: dict):
            item, is_created = model_inst.objects.get_or_create(
                **get_attrs,
                defaults={
                    'currency': curr,
                    **set_attrs,
                }
            )

            if not is_created:
                for key, attr in set_attrs.items():
                    setattr(item, key, attr)
                item.save()

        for coin, to_create_list in coin_info.items():
            for data in to_create_list:
                model = data['model']
                find = data['find']
                attributes = data['attributes']
                get_or_create(model, coin, find,  attributes)

        # create user for bot
        name = 'bot1@bot.com'
        bot = User.objects.filter(username=name).first()
        to_write.append('Bot info:')
        if not bot:
            bot = User.objects.create_user(name, name, settings.BOT_PASSWORD)
            to_write.append('Bot created.')
            EmailAddress.objects.create(
                user=bot,
                email=bot.email,
                verified=True,
                primary=True,
            )

            UserFee.objects.create(
                user=bot,
                fee_rate=0,
            )

            # top up bot
            topup_list = {
                BTC: 3,
                ETH: 100,
                USDT: 100_000,
                BNB: 10,
                TRX: 100_000,
            }

            for currency_id, amount in topup_list.items():
                currency = Currency.get(currency_id)
                tx = Transaction.topup(bot.id, currency, amount, {'1': 1}, reason=REASON_MANUAL_TOPUP)
                create_or_update_wallet_history_item_from_transaction(tx)
                to_write.append(f'Bot TopUp: {amount} {currency.code}')

        if bot.profile:
            bot.profile.user_type = UserTypeEnum.bot.value
            bot.profile.save()

        to_write.append(f'Email: {name}  Password: {settings.BOT_PASSWORD}')
        to_write.append('='*10)

        # create pairs
        pair_list = {
            Pair.get('BTC-USDT'): {
                PairSettings: {
                    'is_enabled': True,
                    'is_autoorders_enabled': True,
                    'price_source': PairSettings.PRICE_SOURCE_EXTERNAL,
                    'custom_price': 0,
                    'deviation': 0.99000000,
                    'precisions': ['100', '10', '1', '0.1', '0.01']
                },
                BotConfig: {
                    'name': 'BTC-USDT',
                    'user': bot,
                    'strategy': BotConfig.TRADE_STRATEGY_DRAW,
                    'instant_match': True,
                    'ohlc_period': 5,
                    'loop_period_random': True,
                    'min_period': 75,
                    'max_period': 280,
                    'ext_price_delta': 0,
                    'min_order_quantity': 0.001,
                    'max_order_quantity': 0.05,
                    'low_orders_max_match_size': 0.0029,
                    'low_orders_spread_size': 200,
                    'low_orders_min_order_size': 0.0003,
                    'enabled': True,
                }
            },
            Pair.get('ETH-USDT'): {
                PairSettings: {
                    'is_enabled': True,
                    'is_autoorders_enabled': True,
                    'price_source': PairSettings.PRICE_SOURCE_EXTERNAL,
                    'custom_price': 0,
                    'deviation': 0.99000000,
                    'precisions': ['100', '10', '1', '0.1', '0.01']
                },
                BotConfig: {
                    'name': 'ETH-USDT',
                    'user': bot,
                    'strategy': BotConfig.TRADE_STRATEGY_DRAW,
                    'instant_match': True,
                    'ohlc_period': 5,
                    'loop_period_random': True,
                    'min_period': 61,
                    'max_period': 208,
                    'ext_price_delta': 0.001,
                    'min_order_quantity': 0.03,
                    'max_order_quantity': 2.02,
                    'low_orders_max_match_size': 1,
                    'low_orders_spread_size': 1,
                    'low_orders_min_order_size': 1,
                    'enabled': True,
                }
            },
            Pair.get('TRX-USDT'): {
                PairSettings: {
                    'is_enabled': IS_TRON,
                    'is_autoorders_enabled': True,
                    'price_source': PairSettings.PRICE_SOURCE_EXTERNAL,
                    'custom_price': 0,
                    'deviation': 0.0,
                    'precisions': ['0.01', '0.001', '0.0001', '0.00001', '0.000001']
                },
                BotConfig: {
                    'name': 'TRX-USDT',
                    'user': bot,
                    'strategy': BotConfig.TRADE_STRATEGY_DRAW,
                    'instant_match': True,
                    'ohlc_period': 60,
                    'loop_period_random': False,
                    'min_period': 60,
                    'max_period': 180,
                    'ext_price_delta': 0.001,
                    'min_order_quantity': 100,
                    'max_order_quantity': 10_000,
                    'low_orders_max_match_size': 1,
                    'low_orders_spread_size': 1,
                    'low_orders_min_order_size': 1,
                    'enabled': IS_TRON,
                }
            },
            Pair.get('BNB-USDT'): {
                PairSettings: {
                    'is_enabled': IS_BSC,
                    'is_autoorders_enabled': True,
                    'price_source': PairSettings.PRICE_SOURCE_EXTERNAL,
                    'custom_price': 0,
                    'deviation': 0.0,
                    'precisions': ['100', '10', '1', '0.1', '0.01'],
                },
                BotConfig: {
                    'name': 'BNB-USDT',
                    'user': bot,
                    'strategy': BotConfig.TRADE_STRATEGY_DRAW,
                    'instant_match': True,
                    'ohlc_period': 60,
                    'loop_period_random': False,
                    'min_period': 60,
                    'max_period': 180,
                    'ext_price_delta': 0.001,
                    'min_order_quantity': 0.01,
                    'max_order_quantity': 0.5,
                    'low_orders_max_match_size': 1,
                    'low_orders_spread_size': 1,
                    'low_orders_min_order_size': 1,
                    'enabled': IS_BSC,
                }
            },
        }

        for pair, model_list in pair_list.items():
            for model, kwargs in model_list.items():
                model.objects.get_or_create(
                    pair=pair,
                    defaults={
                        'pair': pair,
                        **kwargs,
                    }
                )

        # create user for super admin
        name = env('ADMIN_USER', default='admin@exchange.net')
        password = User.objects.make_random_password()
        user = User.objects.filter(username=name).first()
        if not user:
            user = User.objects.create_superuser(name, name, password)
            EmailAddress.objects.create(
                user=user,
                email=user.email,
                verified=True,
                primary=True,
            )
        else:
            user.set_password(password)
            user.save()

        Profile.objects.filter(user=user).update(is_auto_orders_enabled=True)

        to_write.append('Admin Info:')
        to_write.append(f'Email: {name}  Password: {password}')
        to_write.append(f'Master Pass: {settings.ADMIN_MASTERPASS}')
        print(f"password: {password}")

        totp, is_new_totp = TOTPDevice.objects.get_or_create(
            user=user,
            defaults={
                'name': user.email,
            }
        )
        to_write.append(f'2fa token: {totp.config_url}')
        to_write.append('='*10)

        site, site_is_new = Site.objects.get_or_create(
            pk=1,
            defaults={
                'domain': settings.DOMAIN,
                'name': settings.PROJECT_NAME,
            }
        )
        if not site_is_new:
            site.domain = settings.DOMAIN
            site.name = settings.PROJECT_NAME
            site.save()

        service = BTCCoinService()
        last_processed_block_instance, _ = LastProcessedBlock.objects.get_or_create(
            currency=BTC_CURRENCY
        )
        last_processed_block_instance.block_id = service.get_last_network_block_id()
        last_processed_block_instance.save()

        # btc
        if not Keeper.objects.filter(currency=BTC_CURRENCY).exists():
            btc_info, btc_keeper = generate_btc_multisig_keeper()
            to_write.append('BTC Info')
            to_write.append(f'Keeper address: {btc_keeper.user_wallet.address}')
            to_write.append('private data:')
            to_write.append(json.dumps(btc_info, indent=4))
            to_write.append('='*10)
        else:
            to_write.append('BTC Info')
            to_write.append('Keeper exists, see previous file')
            to_write.append('='*10)

        for currency_id in coin_list:
            if currency_id in [USDT, BTC]:
                continue

            currency = Currency.get(currency_id)
            if not Keeper.objects.filter(currency=currency).exists():
                k_password, keeper = keeper_create(currency)
                gas_password, gas_keeper = keeper_create(currency, True)
                to_write.append(f'{currency.code} Info')
                to_write.append(f'Keeper address: {keeper.user_wallet.address}, Password: {k_password}')
                to_write.append(f'GasKeeper address: {gas_keeper.user_wallet.address}, Password: {gas_password}')
                to_write.append('='*10)
            else:
                to_write.append(f'{currency.code} Info')
                to_write.append('Keeper and GasKeeper exists, see previous file')
                to_write.append('=' * 10)

        filename = f'save_to_self_and_delete_{int(datetime.now().timestamp())}.txt'
        filename_path = os.path.join(settings.BASE_DIR, filename)
        with open(filename_path, 'a+') as file:
            for line in to_write:
                file.write(line + '\r\n')

        print(
            f'the file {filename} was created, it contains private information, '
            f'please save the file to yourself and delete it from the server'
        )


def keeper_create(currency, is_gas_keeper=False):

    wallet_create_fn = CRYPTO_WALLET_CREATORS[currency]
    kwargs = {'user_id': None, 'is_new': True, 'currency': currency}

    new_keeper_wallet: UserWallet = wallet_create_fn(**kwargs)
    if isinstance(new_keeper_wallet, QuerySet):
        new_keeper_wallet = new_keeper_wallet.first()

    if not new_keeper_wallet:
        raise Exception('New wallet was not created')

    password = None
    if not is_gas_keeper:
        password = User.objects.make_random_password()
        private_key = AESCoderDecoder(settings.CRYPTO_KEY).decrypt(new_keeper_wallet.private_key)
        encrypted_key = AESCoderDecoder(password).encrypt(private_key)
        dbl_encrypted_key = AESCoderDecoder(settings.CRYPTO_KEY).encrypt(encrypted_key)
        new_keeper_wallet.private_key = dbl_encrypted_key
        new_keeper_wallet.save()

    KeeperModel = Keeper
    if is_gas_keeper:
        # if currency not in [ETH_CURRENCY, TRX_CURRENCY]:
        #     raise Exception('Only ETH and TRX GasKeeper can be created')
        KeeperModel = GasKeeper

    keeper = create_keeper(new_keeper_wallet, KeeperModel)
    return password, keeper



if __name__ == '__main__':
    print('Start')
    main()
    print('Stop')
