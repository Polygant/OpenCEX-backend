class EVMHandlerManager:
    def __init__(self):
        self._registry = {}

    def register(self, evm_handler_class, **options):
        self._registry[evm_handler_class.CURRENCY.code] = evm_handler_class
        # print(f'Success register {evm_handler_class}')

    def get_handler(self, currency_code):
        return self._registry[currency_code]


evm_handlers_manager = EVMHandlerManager()


def register_evm_handler(cls):
    evm_handlers_manager.register(cls)
    return cls
