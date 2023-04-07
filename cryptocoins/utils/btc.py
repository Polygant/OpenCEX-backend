import json
from collections import OrderedDict
from typing import Tuple, Any

from cryptos import Bitcoin
from django.conf import settings
from pywallet.wallet import create_wallet

from core.models import UserWallet
from cryptocoins.coins.btc import BTC_CURRENCY
from cryptocoins.models import Keeper
from cryptocoins.utils.commons import create_keeper
from lib.cipher import AESCoderDecoder
from lib.helpers import to_decimal
from hashlib import sha256, new
from base58 import b58encode


def sha256d(bstr):
    return sha256(sha256(bstr).digest()).digest()


def convert_pkh_to_address(prefix, addr):
    data = prefix + addr
    return b58encode(data + sha256d(data)[:4])


def pubkey_to_address(pubkey_hex):
    pubkey = bytearray.fromhex(pubkey_hex)
    round1 = sha256(pubkey).digest()
    h = new('ripemd160')
    h.update(round1)
    pubkey_hash = h.digest()
    return convert_pkh_to_address(b'\x00', pubkey_hash).decode()


def btc2sat(btc):
    return to_decimal(btc) * 10**8


def sat2btc(sat):
    return to_decimal(sat) / to_decimal(10**8)


def generate_btc_multisig_keeper(log=None) -> Tuple[OrderedDict, Keeper]:
    from cryptocoins.coins.btc.service import BTCCoinService
    service = BTCCoinService()
    btc = Bitcoin()
    ad1 = service.create_new_wallet(addr_import=False)
    ad2 = service.create_new_wallet(addr_import=False)
    ad3 = service.create_new_wallet(addr_import=False)
    # save ad# data

    is_segwit = not getattr(settings, 'BTC_ADDRESS_LEGACY', False)

    pub_keys = [ad1.public_key, ad2.public_key, ad3.public_key]
    if is_segwit:
        script, address = btc.mk_multsig_segwit_address(*pub_keys, num_required=2)
    else:
        script, address = btc.mk_multsig_address(*pub_keys, num_required=2)

    '''
    create keeper in admin panel and add script to "keeper.extra" {"redeem_script":"script"}
    use ad3 private key in keeper
    import address to btc node 

    curl --data-binary '{"method": "addmultisigaddress", "params": [2,["ad1['public_key']", "ad2['public_key']", "ad3['public_key']"], "keeper", "legacy"], "jsonrpc": "2.0"}' -H 'content-type: text/plain;' http://user:password@host:port
    curl --data-binary '{"method": "importaddress", "params": ["multisig_address", "keeper", false], "jsonrpc": "2.0"}' -H 'content-type: text/plain;' http://user:password@host:port


    !!!!!!!!!WARNING!!!!!!!!
    the ORDER of the keys affects the RESULT

    '''
    private_key_encrypt = AESCoderDecoder(settings.CRYPTO_KEY).encrypt(
        ad3.private_key
    )

    owner = OrderedDict({
        'address': ad1.address,
        'public key': ad1.public_key,
        'private key': ad1.private_key
    })

    manager = OrderedDict({
        'address': ad2.address,
        'public key': ad2.public_key,
        'private key': ad2.private_key
    })

    site = OrderedDict({
        'address': ad3.address,
        'public key': ad3.public_key,
        'private key': ad3.private_key,
        'private key encrypted': private_key_encrypt
    })

    keeper_data = OrderedDict({
        'address': address,
        'extra: redeem_script': script
    })

    res = OrderedDict({
        'OWNER': owner,
        'MANAGER': manager,
        'SITE': site,
        'KEEPER': keeper_data
    })

    print(json.dumps(res, indent=4))

    service.rpc.addmultisigaddress(2, pub_keys, "keeper", "p2sh-segwit" if is_segwit else "legacy")
    service.rpc.importaddress(address, "keeper", False)
    if log:
        log.info('Keeper address sucessfully imported to node')

    user_wallet = UserWallet.objects.create(
        user_id=None,
        currency=BTC_CURRENCY,
        blockchain_currency=BTC_CURRENCY,
        address=address,
        private_key=private_key_encrypt,
    )

    keeper: Keeper = create_keeper(user_wallet, extra={'redeem_script': script})

    return res, keeper
