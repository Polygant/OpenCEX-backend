import hmac
from binascii import hexlify
from hashlib import sha512

from pywallet import wallet
from pywallet.utils.utils import ensure_bytes
from pywallet.utils.utils import long_or_int


class PolyWallet(wallet.Wallet):
    """ cause author is anasshole """
    @classmethod
    def from_master_secret(cls, seed, network="bitcoin_testnet"):
        """Generate a new PrivateKey from a secret key.

        :param seed: The key to use to generate this wallet. It may be a long
            string. Do not use a phrase from a book or song, as that will
            be guessed and is not secure. My advice is to not supply this
            argument and let me generate a new random key for you.

        See https://github.com/bitcoin/bips/blob/master/bip-0032.mediawiki#Serialization_format  # nopep8
        """
        network = cls.get_network(network)
        seed = ensure_bytes(seed)
        # Given a seed S of at least 128 bits, but 256 is advised
        # Calculate I = HMAC-SHA512(key="Bitcoin seed", msg=S)
        I_ = hmac.new(b"Bitcoin seed", msg=seed, digestmod=sha512).digest()
        # Split I into two 32-byte sequences, IL and IR.
        I_L, I_R = I_[:32], I_[32:]
        # Use IL as master secret key, and IR as master chain code.
        return cls(private_exponent=long_or_int(hexlify(I_L), 16),
                   chain_code=long_or_int(hexlify(I_R), 16),
                   network=network)

    @classmethod
    def child_from_seed(cls, network, seed, id):
        w = cls.from_master_secret(network=network, seed=seed).get_child(id, is_prime=False)
        return (w.to_address(), w.export_to_wif())
