import hashlib
import os
import sys


def main(name):
    with open(name, 'rb') as fl:
        hash_str = hashlib.md5(fl.read()).hexdigest()

    hash_file_name = f'{name}.hash'
    if not os.path.exists(hash_file_name):
        with open(hash_file_name, 'w') as fl:
            fl.write(hash_str)
            print('updated')

    else:
        with open(hash_file_name, 'r') as fl:
            stored_hash = fl.read()

        if stored_hash == hash_str:
            exit(0)

        else:
            with open(hash_file_name, 'w') as fl:
                fl.write(hash_str)
                print('updated')
                exit(0)


if __name__ == '__main__':
    main(sys.argv[1])
