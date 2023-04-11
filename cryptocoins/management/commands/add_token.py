import json

from django.core.management.base import BaseCommand

from core.models import PairSettings, FeesAndLimits, WithdrawalFee
from core.models.stats import InoutsStats
from cryptocoins.data_sources.crypto import binance_data_source, kucoin_data_source
from core.models.facade import CoinInfo
from core.pairs import PAIRS_LIST
from cryptocoins.tokens_manager import read_tokens_file, write_tokens_file, get_tokens_backup_diffs, restore_backup_file
from core.consts.currencies import BEP20_CURRENCIES, ERC20_CURRENCIES, TRC20_CURRENCIES, CURRENCIES_LIST


TOKENS_BLOCKCHAINS_MAP = {'ETH': ERC20_CURRENCIES, 'BNB': BEP20_CURRENCIES, 'TRX': TRC20_CURRENCIES}


class Command(BaseCommand):

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        all_tokens_data = read_tokens_file()

        # common token data
        token_symbol = prompt('Enter token symbol').upper()
        blockchain_symbol = prompt('Enter token blockchain symbol (ETH, BNB, TRX)', choices=['ETH', 'BNB', 'TRX'])

        if is_token_exists(token_symbol, blockchain_symbol):
            print('[!] Token with this blockchain already added')
            return

        contract = prompt('Enter token contract address')
        decimals = prompt('Enter token decimals', int)
        token_currency_id = get_available_currency_id()

        if token_symbol not in all_tokens_data:
            all_tokens_data[token_symbol] = {'id': token_currency_id, 'blockchains': {}, 'pairs': []}

        all_tokens_data[token_symbol]['blockchains'][blockchain_symbol] = {
            "contract": contract,
            "decimals": decimals
        }

        # pair data
        all_pairs_symbols = [p[1] for p in PAIRS_LIST]
        pair_to_usdt = f'{token_symbol}-USDT'

        if pair_to_usdt not in all_pairs_symbols:
            while 1:
                precisions = prompt(
                    f'Enter precisions for pair {token_symbol}-USDT from max to min, separated by comma(like 10,1,0.1,0.01)')
                precisions = precisions.split(',')
                precisions = [p.strip() for p in precisions if p.strip()]

                precisions_alright = 1
                for p in precisions:
                    if not p:
                        continue
                    if not is_float(p):
                        precisions_alright = 0
                        print(f'[!] Incorrect value element: {p}')
                        break

                if precisions_alright:
                    break
            pair_id = get_available_pair_id()
            all_tokens_data[token_symbol]["pairs"].append([pair_id, pair_to_usdt, precisions])

        write_tokens_file(json.dumps(all_tokens_data, indent=2))
        print(f'[+] Token {token_symbol} ({blockchain_symbol}) successfully added to a file')

        print('*****Coin Info*****')
        if CoinInfo.objects.filter(currency=token_symbol).exists():
            print(f'[*] CoinInfo already exists for {token_symbol}')
        else:
            token_name = prompt('Enter token name')
            display_decimals = prompt('Enter decimals for rounding', int, default=2)
            index = prompt('Enter token index')
            cmc_link = prompt('Enter CoinMarketCap link', default='')
            exp_link = prompt('Enter explorer link', default='')
            off_link = prompt('Enter official site link', default='')
            if off_link:
                off_title = prompt('Enter title for official site')

            links = {}
            if cmc_link:
                links['cmc'] = {
                    'href': cmc_link,
                    'title': 'CoinMarketCap'
                }
            if exp_link:
                links['exp'] = {
                    'href': exp_link,
                    'title': 'Explorer'
                }
            if off_link:
                links['official'] = {
                    'href': off_link,
                    'title': off_title
                }
            CoinInfo.objects.create(
                currency=token_symbol,
                defaults={
                    'name': token_name,
                    'decimals': display_decimals,
                    'index': index,
                    'links': links,
                }
            )
            print('[+] CoinInfo successfully created')

        ## PairSettings
        print('*****Pair Settings*****')

        if PairSettings.objects.filter(pair=pair_to_usdt).exists():
            print(f'[*] PairSettings already exists for {token_symbol}-USDT')
        else:
            pair_settings = {'pair': pair_to_usdt}
            if binance_data_source.is_pair_exists(pair_to_usdt) or kucoin_data_source.is_pair_exists(pair_to_usdt):
                pair_settings['price_source'] = PairSettings.PRICE_SOURCE_EXTERNAL
            else:
                print(f'Pair {pair_to_usdt} is not found in external price sources')
                pair_settings['price_source'] = PairSettings.PRICE_SOURCE_CUSTOM
                pair_settings['custom_price'] = prompt(f'Enter custom price for {pair_to_usdt}', arg_type=float)
            PairSettings.objects.create(**pair_settings)
            print('[+] PairSettings successfully created')

        print('*****Fees and Limits*****')
        if FeesAndLimits.objects.filter(currency=token_symbol).exists():
            print(f'[*] FeesAndLimits already exists')
        else:
            default_fees_and_limits = {
                'currency': token_symbol,
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
            }
            FeesAndLimits.objects.create(**default_fees_and_limits)
            print('[+] FeesAndLimits successfully created')

        print('*****Withdrawal Fee*****')
        if WithdrawalFee.objects.filter(currency=token_symbol, blockchain_currency=blockchain_symbol).exists():
            print(f'[*] WithdrawalFee already exists')
        else:
            WithdrawalFee.objects.create(
                currency=token_symbol,
                blockchain_currency=blockchain_symbol,
                address_fee=1.00000000
            )
            print('[+] WithdrawalFee successfully created')

        print('*****Inouts Stats*****')
        if InoutsStats.objects.filter(currency=token_symbol).exists():
            print(f'[*] InoutsStats already exists')
        else:
            InoutsStats.objects.create(
                currency=token_symbol,
            )
            print('[+] InoutsStats successfully created')


def revert():
    diff = get_tokens_backup_diffs()
    if not diff:
        print('[-] Revert is impossible')
    if diff.token and not diff.blockchain:
        print('[*] CoinInfo, FeesAndLimits, WithdrawalFee, InoutsStats, PairSettings entries will be deleted')
        CoinInfo.objects.filter(currency=diff.token).delete()
        FeesAndLimits.objects.filter(currency=diff.token).delete()
        WithdrawalFee.objects.filter(currency=diff.token).delete()
        InoutsStats.objects.filter(currency=diff.token).delete()
        PairSettings.objects.filter(pair=f'{diff.token}-USDT').delete()
    elif diff.token and diff.blockchain:
        print('[*] WithdrawalFee entry will be deleted')
        WithdrawalFee.objects.filter(currency=diff.token, blockchain_currency=diff.blockchain).delete()
    restore_backup_file()


def get_available_currency_id():
    return max(c[0] for c in CURRENCIES_LIST) + 1


def get_available_pair_id():
    return max(p[0] for p in PAIRS_LIST) + 1


def is_token_exists(symbol, blockchain_symbol):
    blockchain_currencies = TOKENS_BLOCKCHAINS_MAP[blockchain_symbol]
    symbols = [c.code for c in blockchain_currencies]
    return symbol in symbols


def prompt(text, arg_type=str, choices=None, default=None):
    if not choices:
        choices = []

    res = None

    while res is None:
        if default is not None:
            text = text + f' [default: {default}]'
        res = input(text + ': ')
        if not res:
            if default is not None:
                return default

            if arg_type is str:
                print('[!] Param can not be blank')
                res = None
                continue
        try:
            res = arg_type(res)
        except:
            print(f'[!] Incorrect param type. It should be {arg_type}')
            res = None
            continue

        if choices and res not in choices:
            print(f'[!] Incorrect value. Value must be in {choices}')
            res = None
            continue
    return res


def is_float(s):
    return s.replace('.', '', 1).isdigit()
