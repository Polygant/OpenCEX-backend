import os.path
import json

from django.conf import settings

from core.currency import TokenParams
from core.pairs import PAIRS_LIST, pairs_ids_values, Pair
from cryptocoins.utils.register import register_token
from dataclasses import dataclass

tokens_config_fp = os.path.join(settings.BASE_DIR, 'tokens.json')


@dataclass
class Difference:
    token: str
    blockchain: str = None


def restore_backup_file():
    os.remove(tokens_config_fp)
    os.rename(tokens_config_fp + '.bak', tokens_config_fp)
    print('[+] Backup file restored')


def write_tokens_file(content):
    if os.path.exists(tokens_config_fp):
        os.rename(tokens_config_fp, tokens_config_fp + '.bak')  # make backup
    with open(tokens_config_fp, 'w') as f:
        f.write(content)


def read_tokens_file():
    if not os.path.exists(tokens_config_fp):
        write_tokens_file('{}')

    with open(tokens_config_fp, 'r') as f:
        data = json.load(f)
    return data


def get_tokens_backup_diffs():
    if not os.path.exists(tokens_config_fp) or not os.path.exists(tokens_config_fp + '.bak'):
        print('[-] tokens.json or tokens.json.bak not exists')
        return None

    with open(tokens_config_fp, 'r') as f:
        current = json.load(f)
    with open(tokens_config_fp + '.bak', 'r') as f:
        backup = json.load(f)

    # if token was newly added, then delete all info including DB entries
    token_diffs = set(current).difference(set(backup))
    if token_diffs:
        return Difference(token_diffs.pop())

    # check for blockchains differences
    for token, token_data in current.items():
        orig_bc = token_data["blockchains"]
        backup_bc = backup[token]["blockchains"]
        blochchain_diffs = set(orig_bc).difference(set(backup_bc))
        if blochchain_diffs:
            return Difference(token, blochchain_diffs.pop())


def register_tokens_and_pairs():
    """
    Basic stucture of tokens.json
    {
        "USDC": {
            "id": 100,
            "blockchains": {
                "ETH": {
                    "contract": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                    "decimals": 6
                }
            },
            "pairs": [
                [
                100, # pair id
                "USDC-USDT", # pair symbol
                ]
            ]
       }
    }
    """
    data = read_tokens_file()

    for token_symbol, token_data in data.items():
        # register token
        blockchains = {}
        token_currency_id = token_data['id']
        for bc_symbol, bc_data in token_data['blockchains'].items():
            blockchains[bc_symbol] = TokenParams(
                symbol=token_symbol,
                contract_address=bc_data['contract'],
                decimal_places=bc_data['decimals']
            )

        register_token(token_currency_id, token_symbol, blockchains)

        # register pairs
        for pair_data in token_data['pairs']:
            PAIRS_LIST.append(tuple(pair_data))
            pairs_ids_values.append((pair_data[0], pair_data[1]))
            _ = Pair(*pair_data)

