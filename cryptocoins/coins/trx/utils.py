from tronpy import Tron


def is_valid_tron_address(address):
    try:
        res = Tron.is_address(address)
        return res
    except:
        return False


def get_latest_tron_block_num(*args):
    client = Tron()
    return client.get_latest_block_number()

