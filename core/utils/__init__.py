import random


def get_rand_code(length=16):
    return "{number:0{precision}d}".format(
        number=random.randrange(10 ** (length - 1), 10 ** length - 1),
        precision=length,
    )