from cryptos import Bitcoin
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from cryptocoins.tasks.bnb import bnb_manager
from cryptocoins.tasks.eth import ethereum_manager
from cryptocoins.tasks.trx import tron_manager
from lib.cipher import AESCoderDecoder

CryptoBitcoin = Bitcoin()


class BaseKeySerializer(serializers.Serializer):
    key = serializers.CharField(max_length=255)

    def get_encrypted_string(self):
        raise NotImplementedError

    def validate_key(self, key):
        if not key:
            raise ValidationError("Bad password!")

        try:
            to_check_string = self.get_encrypted_string()
            res = AESCoderDecoder(key).decrypt(to_check_string)
            if not res:
                raise ValidationError("Bad private key")
        except Exception as e:
            raise ValidationError("Bad password!")

        return key


class BTCKeySerializer(BaseKeySerializer):
    def validate_key(self, key):
        if len(key) != 52:
            raise ValidationError("Bad format private key!")

        if key[0] not in ['K', 'L']:
            raise ValidationError("Bad format private key.")

        try:
            CryptoBitcoin.privtopub(key)
        except AssertionError as e:
            raise ValidationError("Bad format private key")

        return key


class ETHKeySerializer(BaseKeySerializer):
    def get_encrypted_string(self):
        return ethereum_manager.get_keeper_wallet().private_key


class TRXKeySerializer(BaseKeySerializer):
    def get_encrypted_string(self):
        return tron_manager.get_keeper_wallet().private_key


class BNBKeySerializer(BaseKeySerializer):
    def get_encrypted_string(self):
        return bnb_manager.get_keeper_wallet().private_key
