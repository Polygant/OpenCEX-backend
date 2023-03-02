from typing import List, Tuple

from django.conf import settings

from bots.exchanges.base_exchange import BaseExchange
from bots.helpers import BaseHttpSession
from bots.structs import OrderSide, OrderType, OrderBookEntryStruct, OrderStruct, AmountPriceStruct
from core.models.orders import Order
from lib.helpers import pretty_decimal, to_decimal
from lib.notifications import send_telegram_message


class MainExchange(BaseExchange):
    NAME = 'Main Exchange'
    BASE_URL = settings.BOTS_API_BASE_URL + '/api/v1'
    PUBLIC_API_URL = settings.BOTS_API_BASE_URL + '/api/public/v1'

    def get_pair(self):
        return f'{self.config.pair.base.CODE}-{self.config.pair.quote.CODE}'

    def login(self):
        googlecode = ''
        data = {
            "username": self.config.user.username,
            "password": settings.BOT_PASSWORD,
            'googlecode': googlecode
        }
        try:
            r = self.session.post('/auth/login/', json=data, verify=False)
            auth_token = r.json().get('access_token')
            if auth_token:
                self.log.info(f'Successfully login to {self.NAME}')
            self.session._session.headers['Authorization'] = "Token {}".format(
                auth_token)
        except Exception as e:
            if self.config.authorization_error:
                send_telegram_message(f"Bot {self.config.name} error:\n{str(e)}")
            self.log.warning(str(e))

    def make_order(self, order):
        self.log.info(f'Make order: {order}')

        url = '/orders/'
        data = {
            'pair': self.get_pair(),
            'operation': Order.OPERATION_BUY if order.side == OrderSide.BUY else Order.OPERATION_SELL,
            'quantity': pretty_decimal(order.quantity, self.base_symbol_precision)
        }
        if order.order_type == OrderType.LIMIT:
            data['type'] = Order.ORDER_TYPE_LIMIT
            data['price'] = pretty_decimal(
                order.price, self.quote_symbol_precision)
        else:
            data['type'] = Order.ORDER_TYPE_EXTERNAL
            data['otc_limit'] = 0.0001 if order.side == OrderSide.SELL else 100000
            data['otc_percent'] = order.otc_percent

        r = self.session.post(url, json=data, verify=False)
        result = r.json()
        self.log.info(f'Order res: {result}')

        self.add_order_to_cache(result['id'])

        result = OrderStruct(
            id=result['id'],
            price=to_decimal(result['price']),
            quantity=to_decimal(result['quantity']),
            quantity_left=to_decimal(result['quantity_left']),
            side=OrderSide.SELL if result['operation'] == Order.OPERATION_SELL else OrderSide.BUY,
            order_type=OrderType.LIMIT if result['type'] == Order.ORDER_TYPE_LIMIT else OrderType.AUTO,
            otc_percent=result['otc_percent']
        )
        return result

    def cancel_order(self, order_id):
        self.log.info(f'Cancelling order: {order_id}')
        try:
            self.session.delete(f'/orders/{order_id}/')
        except Exception as e:
            if self.config.cancel_order_error:
                send_telegram_message(f"Bot {self.config.name} error:\n{str(e)}")
            self.log.warning(str(e))
        self.remove_order_from_cache(order_id)

    def balance(self):
        self.log.info(f'Checking {self.NAME} balance')
        res = self.session.get(f'/balance/').json()
        balance = {key: (float(val['actual']) + float(val['orders']))
                   for key, val in res['balance'].items()}
        return balance

    def free_balance(self):
        self.log.info(f'Checking {self.NAME} free balance')
        res = self.session.get(f'/balance/').json()
        balance = {key: (float(val['actual']))
                   for key, val in res['balance'].items()}
        return balance

    def opened_orders(self):
        res = self.session.get(
            f'/orders/?limit=10&offset=0&opened=true&pair={self.get_pair()}').json()
        result = res['results']

        orders = list([OrderStruct(
            price=to_decimal(o['price']),
            quantity=to_decimal(o['quantity']),
            quantity_left=to_decimal(o['quantity_left']),
            side=OrderSide.BUY if o['operation'] == Order.OPERATION_BUY else OrderSide.SELL,
            order_type=OrderType.LIMIT if o['type'] == Order.ORDER_TYPE_LIMIT else OrderType.AUTO,
            id=o['id']
        ) for o in result if o['id'] in self.orders_ids])

        self.log.info(f'{self.NAME} opened orders: {orders}')

        return orders

    def price(self):
        res = self.session.get(f'/pairs_volume/').json()
        for pair in res:
            if pair['pair'] == self.get_pair():
                price = float(pair['price'])
                self.log.info(f'{self.NAME} ticker price: {price}')
                return price
        # self.logger.error(f'Cant fetch ticker for {self.get_pair()}')
        send_telegram_message(f'Bot {self.config.name} error:\nCant fetch ticker for {self.get_pair()}')
        raise Exception(f'Cant fetch ticker for {self.get_pair()}')

    def get_ticker(self):
        session = BaseHttpSession(self.PUBLIC_API_URL)
        res = session.get(f'/summary').json()['data']
        pair = self.get_pair().replace('-', '_')
        for pair_data in res:
            if pair == pair_data['trading_pairs']:
                return pair_data

    def orderbook(self) -> OrderBookEntryStruct:
        data = self.session.get(f'/stack/{self.get_pair()}/')
        # data = StackView.stack_limited(self.get_pair(), 1, 1)
        buys = data['buys']
        sells = sorted(data['sells'], reverse=True)

        highest_buy = AmountPriceStruct(
            price=float(buys[0]['price'] or 0) if buys else 0,
            amount=float(buys[0]['quantity'] or 0) if buys else 0,
        )
        lowest_sell = AmountPriceStruct(
            price=float(sells[0]['price'] or 0) if sells else 0,
            amount=float(sells[0]['quantity'] or 0) if sells else 0,
        )

        return OrderBookEntryStruct(
            highest_buy=highest_buy,
            lowest_sell=lowest_sell
        )

    def get_orders_stack(self) -> Tuple[List[OrderStruct], List[OrderStruct]]:
        res = self.session.get(f'/allorders/?pair={self.get_pair()}').json()
        buy_orders = []
        sell_orders = []

        for e in res:
            order_entry = OrderStruct(
                id=e['id'],
                price=e['price'],
                quantity=e['quantity_left'],
                quantity_left=e['quantity_left'],
                side=OrderSide.BUY if e['operation'] == 0 else OrderSide.SELL,
                is_bot=e['is_bot'],
            )
            if order_entry.side == OrderSide.BUY:
                buy_orders.append(order_entry)
            else:
                sell_orders.append(order_entry)

        buy_orders.sort(reverse=True)
        return buy_orders, sell_orders

    def get_latest_ohlc_candle(self, interval) -> dict:
        data = self.session.get(f'/latest_candle/?pair={self.get_pair()}&interval={interval}').json()
        return data
