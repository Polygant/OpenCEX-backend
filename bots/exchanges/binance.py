from binance.client import Client
from django.conf import settings

from bots.exchanges.base_exchange import BaseExchange
from bots.structs import OrderSide, OrderType, OrderBookEntryStruct, OrderStruct, AmountPriceStruct
from lib.cipher import AESCoderDecoder
from lib.helpers import pretty_decimal, to_decimal


class BinanceExchange(BaseExchange):
    NAME = 'Binance Exchange'
    BASE_URL = 'https://api.binance.com/'

    def get_pair(self):
        return f'{self.config.pair.base.CODE}{self.config.pair.quote.CODE}'

    def login(self):
        binance_api_key = AESCoderDecoder(settings.CRYPTO_KEY).decrypt(self.config.binance_api_key)
        binance_secret_key = AESCoderDecoder(settings.CRYPTO_KEY).decrypt(self.config.binance_secret_key)
        self._client = Client(binance_api_key, binance_secret_key)
        self.log.info('Successfully login to Binance Exchange')

        data = self._client.get_symbol_info(symbol=self.get_pair())
        for fltr in data['filters']:
            if fltr['filterType'] == 'PRICE_FILTER':
                self.quote_symbol_precision = abs(to_decimal(fltr['tickSize']).adjusted())
            elif fltr['filterType'] == 'LOT_SIZE':
                self.base_symbol_precision = abs(to_decimal(fltr['stepSize']).adjusted())

        self.log.info(f'Base precision={self.base_symbol_precision}, Quote precision={self.quote_symbol_precision}')

    def make_order(self, order):
        self.log.info(f'Make order: {order}')

        side = 'BUY' if order.side == OrderSide.BUY else 'SELL'
        data = {
            'quantity': pretty_decimal(order.quantity, self.base_symbol_precision),
            'side': side,
            'symbol': self.get_pair()
        }

        if order.order_type == OrderType.LIMIT:
            data['price'] = pretty_decimal(order.price, self.quote_symbol_precision)
            result = self._client.order_limit(**data)
        else:
            self.log.info(f'Binance counter data: {data}')
            result = self._client.order_market(**data)

        price = sum([to_decimal(r['price']) * to_decimal(r['qty']) / to_decimal(result['origQty'])
                     for r in result['fills']])

        res_order = OrderStruct(
            id=result['orderId'],
            quantity=to_decimal(result['origQty']),
            quantity_left=to_decimal(result['origQty']) - to_decimal(result['executedQty']),
            price=price,
            side=OrderSide.BUY if result['side'] == 'BUY' else OrderSide.SELL,
            order_type=OrderType.LIMIT if result['type'] == 'LIMIT' else OrderType.AUTO
        )
        self.log.info(f'Order res: {res_order}')
        return res_order

    def cancel_order(self, order_id):
        self.log.info(f'Cancelling order: {order_id}')
        data = {'symbol': self.get_pair(), 'orderId': order_id}
        result = self._client.cancel_order(**data)
        # self.remove_order_from_cache(order_id)

    def cancel_all_orders(self):
        self.log.info(f'Cancelling all orders')
        for order_id in self.orders_ids:
            self.cancel_order(order_id)

    def balance(self):
        self.log.info(f'Checking Binance balance')
        result = self._client.get_account()
        balances = {bal['asset']: (float(bal['free']) + float(bal['locked'])) for bal in result['balances']}
        return balances

    def opened_orders(self):
        data = {'symbol': self.get_pair()}

        result = self._client.get_open_orders(**data)

        orders = [OrderStruct(
            price=to_decimal(o['price']),
            quantity=to_decimal(o['origQty']),
            quantity_left=to_decimal(o['origQty']) - to_decimal(o['executedQty']),
            side=OrderSide.BUY if o['side'] == 'BUY' else OrderSide.SELL,
            order_type=OrderType.LIMIT if o['type'] == 'LIMIT' else OrderType.AUTO,
            id=o['orderId']
        ) for o in result]

        return list(orders)

    def price(self) -> float:
        """
        {
          "symbol": "BNBBTC",
          "priceChange": "-94.99999800",
          "priceChangePercent": "-95.960",
          "weightedAvgPrice": "0.29628482",
          "prevClosePrice": "0.10002000",
          "lastPrice": "4.00000200",
          "lastQty": "200.00000000",
          "bidPrice": "4.00000000",
          "askPrice": "4.00000200",
          "openPrice": "99.00000000",
          "highPrice": "100.00000000",
          "lowPrice": "0.10000000",
          "volume": "8913.30000000",
          "quoteVolume": "15.30000000",
          "openTime": 1499783499040,
          "closeTime": 1499869899040,
          "firstId": 28385,   // First tradeId
          "lastId": 28460,    // Last tradeId
          "count": 76         // Trade count
        }
        """

        data = {'symbol': self.get_pair()}
        result = self._client.get_ticker(**data)

        price = float(result['lastPrice'])
        self.log.info(f'Binance ticker price: {price}')
        return price

    def orderbook(self) -> OrderBookEntryStruct:
        data = {'symbol': self.get_pair()}
        result = self._client.get_orderbook_ticker(**data)

        return OrderBookEntryStruct(
            highest_buy=AmountPriceStruct(
                price=float(result['bidPrice']),
                amount=float(result['bidQty'])
            ),
            lowest_sell=AmountPriceStruct(
                price=float(result['askPrice']),
                amount=float(result['askQty'])
            )
        )
