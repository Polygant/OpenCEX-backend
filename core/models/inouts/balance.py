from core.consts.currencies import ALL_CURRENCIES
from core.consts.orders import SELL
from core.currency import CurrencyModelField
from core.utils.stats.daily import get_filtered_pairs_24h_stats
from exchange.models import UserMixinModel
from lib.fields import MoneyField
from lib.helpers import to_decimal


class Balance(UserMixinModel):
    currency = CurrencyModelField()
    amount = MoneyField(default=0)
    amount_in_orders = MoneyField(default=0)

    class Meta:
        unique_together = (('user', 'currency'),)

    @classmethod
    def order_set(cls, order, amount=None):
        # TODO: MOVE TO TRANSACTION
        query = {'user_id': order.user_id}
        if not amount:
            amount = to_decimal(0)
        if order.operation == SELL:
            query['currency'] = order.pair.base
        else:
            query['currency'] = order.pair.quote

        cls._update(query, amount)

    @classmethod
    def _update(cls, query, amount):
        # TODO: user add_to_order instead!
        if not amount:
            amount = to_decimal(0)

        b = cls.objects.select_for_update().filter(**query).first()
        if b:
            b.amount_in_orders = to_decimal(amount)
        else:
            b = cls(amount_in_orders=amount, **query)
        b.save()

    @classmethod
    def for_user(cls, user, currency=None):
        """ if currency == None: return list of dicts """
        if currency:
            obj, _ = cls.objects.get_or_create(user=user, currency=currency, defaults={'amount': 0})
            return {'actual': obj.amount, 'orders': obj.amount_in_orders, 'currency': currency}

        result = {i.code: {'actual': 0, 'orders': 0} for i in ALL_CURRENCIES}

        for i in cls.objects.filter(user=user).all():
            result[i.currency.code] = {'actual': i.amount, 'orders': i.amount_in_orders}

        return result

    @classmethod
    def portfolio_for_user(cls, user, currency_code='USDT'):
        pairs_data = get_filtered_pairs_24h_stats()
        result = cls.for_user(user)
        pairs = {i['pair']: i for i in pairs_data['pairs']}

        factor = cls.calc_factor(pairs, currency_code)

        for key, item in result.items():
            item['actual_usd'] = 0
            item['price'] = 0
            item['price_24h'] = 0
            item['price_24h_value'] = 0

            if key+'-USDT' in pairs:
                pair_data = pairs[key+'-USDT']
                item = cls.prepare_item(item, pair_data, factor)

            elif key in ['USD', 'EUR', 'RUB']:
                if key == currency_code:
                    item['price'] = to_decimal('1')
                    item = cls.prepare_item(item, item)
                else:
                    item['price'] = 1 / cls.calc_factor(pairs, key)
                    item = cls.prepare_item(item, item, factor)

            result[key] = item

        return result

    @staticmethod
    def prepare_item(item, data, factor=1):
        if not factor:
            factor = 1
        item['actual'] = to_decimal(item['actual'] or 0) + to_decimal(item['orders'] or 0)
        item['price'] = to_decimal(data['price'] or 0) * factor
        item['price_24h'] = to_decimal(data['price_24h'] or 0) * factor
        item['price_24h_value'] = to_decimal(data['price_24h_value'] or 0) * factor
        item['actual_usd'] = to_decimal(item['price'] or 0) * to_decimal(item['actual'] or 0)

        return item

    @staticmethod
    def calc_factor(pairs, currency_code):
        factor = 1
        btc_usd_price = pairs.get('BTC-USDT', {}).get('price') or 0
        if btc_usd_price and currency_code in ['EUR', 'RUB'] and ('BTC-'+currency_code) in pairs:
            btc_currency_price = pairs['BTC-'+currency_code].get('price') or 0
            factor = btc_currency_price / btc_usd_price
        return to_decimal(factor or 1)

    def __str__(self):
        return '{} {} {}'.format(self.user.username, self.currency.code, self.amount)
