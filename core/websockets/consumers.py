import logging
from asyncio.futures import Future
from typing import Dict, Any

from asgiref.sync import sync_to_async
from cached_property import asyncio
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser, User

from core.auth.api_hmac_auth import HMACAuthentication
from core.utils.auth import get_user_from_token
from exchange.notifications import balance_notificator, executed_order_notificator, wallet_history_endpoint, \
    opened_orders_endpoint, closed_orders_endpoint, opened_orders_by_pair_endpoint, closed_orders_by_pair_endpoint
from exchange.notifications import chart_notificator
from exchange.notifications import closed_orders_by_pair_notificator
from exchange.notifications import closed_orders_notificator
from exchange.notifications import coins_status_notificator
from exchange.notifications import fees_limits_notificator
from exchange.notifications import opened_orders_by_pair_notificator
from exchange.notifications import opened_orders_notificator
from exchange.notifications import pairs_notificator
from exchange.notifications import pairs_volume_notificator
from exchange.notifications import stack_notificator
from exchange.notifications import trades_notificator
from exchange.notifications import user_notificator
from exchange.notifications import wallet_history_notificator
from exchange.notifications import wallet_history_ticker_notificator
from exchange.notifications import wallet_topups_history_notificator
from exchange.notifications import wallet_withdrawals_history_notificator
from exchange.notifications import wallets_notificator

logger = logging.getLogger(__name__)

class LiveNotificationsConsumer(AsyncJsonWebsocketConsumer):
    AUTH_TIMEOUT = 10

    async def connect(self):
        self.authed = Future()
        await self.accept()
        # self.task = ensure_future(self.wait_auth())
        self.groups = set()

    async def wait_auth(self):
        logger.debug('Wait_auth')
        try:
            await asyncio.wait_for(self.authed, self.AUTH_TIMEOUT)
        except Exception as e:
            await self.close()

    async def do_auth(self, msg):
        logger.debug('do_auth')
        try:
            token = msg.get('token', None)
            assert token
            user, token = await sync_to_async(get_user_from_token)(token)
            await self._set_user(user)
        except Exception as e:
            self.authed.set_exception(e)

    async def do_auth_api_key(self, msg: Dict[str, Any]) -> None:
        logger.debug('do_auth_api_key')
        try:
            authenticator = HMACAuthentication()
            api_key = msg.get('api_key')
            signature = msg.get('signature')
            nonce = msg.get('nonce')
            user, _ = await sync_to_async(
                authenticator.authenticate_values
            )(
                api_key, signature, nonce
            )
            await self._set_user(user)
        except Exception as e:
            self.authed.set_exception(e)

    async def _set_user(self, user: User) -> None:
        logger.debug('set_user')
        self.scope['user'] = user
        await self.join_group(user_notificator.gen_channel(user_id=self.scope['user'].id))
        data = user_notificator.prepare_data({'hello': self.scope['user'].username})
        await self.send_json(data)
        self.authed.set_result(user)

    async def join_group(self, grp_name):
        await self.channel_layer.group_add(grp_name, self.channel_name)
        self.groups.add(grp_name)

    async def leave_group(self, grp_name):
        await self.channel_layer.group_discard(grp_name, self.channel_name)
        if grp_name in self.groups:
            self.groups.remove(grp_name)

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        logger.debug('receive')
        await AsyncJsonWebsocketConsumer.receive(self, text_data=text_data, bytes_data=bytes_data, **kwargs)

    async def receive_json(self, content, **kwargs):
        logger.debug('receive')
        # if not self.authed.done():
        #     return await self.do_auth(content)

        if ('token' in content and content.get('token', None) is None) or \
           ('api_key' in content and content.get('api_key', None) is None):
            await self.leave_group(user_notificator.gen_channel(user_id=self.scope['user'].id))
            self.authed = Future()
            self.scope['user'] = AnonymousUser()

        if not self.authed.done() and 'token' in content and content.get('token', None) is not None:
            return await self.do_auth(content)

        if not self.authed.done() and 'api_key' in content and content.get('api_key', None) is not None:
            return await self.do_auth_api_key(content)

        command = content.get('command', None)
        params = content.get('params', {})
        if not command:
            return

        params['user_id'] = self.scope['user'] and getattr(self.scope['user'], 'id')

        if command == 'add_stack':
            await self.join_group(stack_notificator.gen_channel(**params))
            data = await sync_to_async(stack_notificator.get_data)(**params)
            data = stack_notificator.prepare_data(data, **params)
            await self.send_json(data)
        elif command == 'del_stack':
            await self.leave_group(stack_notificator.gen_channel(**params))

        elif command == 'add_trades':
            await self.join_group(trades_notificator.gen_channel(**params))
            data = await sync_to_async(trades_notificator.get_paginated_data)(**params)
            data = trades_notificator.prepare_data(data)
            await self.send_json(data)
        elif command == 'del_trades':
            await self.leave_group(trades_notificator.gen_channel(**params))

        elif command == 'add_pairs_volume':
            await self.join_group(pairs_volume_notificator.gen_channel(**params))
            data = await sync_to_async(pairs_volume_notificator.get_data)(**params)
            data = pairs_volume_notificator.prepare_data(data)
            await self.send_json(data)
        elif command == 'del_pairs_volume':
            await self.leave_group(pairs_volume_notificator.gen_channel(**params))

        elif command == 'get_trades':
            data = await sync_to_async(trades_notificator.get_paginated_data)(**params)
            data = trades_notificator.prepare_data(data)
            await self.send_json(data)

        elif command == 'get_chart':
            data = chart_notificator.get_data(**params)
            await self.send_json(chart_notificator.prepare_data(data))

        elif command == 'get_coins_status':
            data = await sync_to_async(coins_status_notificator.get_data)(**params)
            data = coins_status_notificator.prepare_data(data)
            await self.send_json(data)

        elif command == 'get_limits':
            data = await sync_to_async(fees_limits_notificator.get_data)(**params)
            data = fees_limits_notificator.prepare_data(data)
            await self.send_json(data)
        elif command == 'get_pairs':
            data = await sync_to_async(pairs_notificator.get_data)(**params)
            data = pairs_notificator.prepare_data(data)
            await self.send_json(data)
        elif command == "ping":
            data = {'data': 'pong'}
            await self.send_json(data)

        # for authorized users
        user = self.scope['user']
        if user and getattr(user, 'id'):
            # if command == 'add_profile':
            #     await self.join_group(profile_notificator.gen_channel(**params))
            #     data = await sync_to_async(profile_notificator.get_data)(**params)
            #     data = profile_notificator.prepare_data(data)
            #     await self.send_json(data)
            # elif command == 'del_profile':
            #     await self.leave_group(profile_notificator.gen_channel(**params))

            if command == 'add_balance':
                await self.join_group(balance_notificator.gen_channel(**params))
                data = await sync_to_async(balance_notificator.get_data)(**params)
                data = balance_notificator.prepare_data(data)
                await self.send_json(data)
            elif command == 'del_balance':
                await self.leave_group(balance_notificator.gen_channel(**params))

            elif command == 'add_opened_orders':
                await self.join_group(opened_orders_notificator.gen_channel(**params))
                data = await sync_to_async(opened_orders_notificator.get_paginated_data)(**params)
                data = opened_orders_notificator.prepare_data(data)
                await self.send_json(data)
            elif command == 'del_opened_orders':
                await self.leave_group(opened_orders_notificator.gen_channel(**params))

            elif command == 'add_closed_orders':
                await self.join_group(closed_orders_notificator.gen_channel(**params))
                data = await sync_to_async(closed_orders_notificator.get_paginated_data)(**params)
                data = closed_orders_notificator.prepare_data(data)
                await self.send_json(data)
            elif command == 'del_closed_orders':
                await self.leave_group(closed_orders_notificator.gen_channel(**params))

            elif command == 'add_opened_orders_by_pair':
                await self.join_group(opened_orders_by_pair_notificator.gen_channel(**params))
                data = await sync_to_async(opened_orders_by_pair_notificator.get_paginated_data)(**params)
                data = opened_orders_by_pair_notificator.prepare_data(data)
                await self.send_json(data)
            elif command == 'del_opened_orders_by_pair':
                await self.leave_group(opened_orders_by_pair_notificator.gen_channel(**params))

            elif command == 'add_closed_orders_by_pair':
                await self.join_group(closed_orders_by_pair_notificator.gen_channel(**params))
                data = await sync_to_async(closed_orders_by_pair_notificator.get_paginated_data)(**params)
                data = closed_orders_by_pair_notificator.prepare_data(data)
                await self.send_json(data)
            elif command == 'del_closed_orders_by_pair':
                await self.leave_group(closed_orders_by_pair_notificator.gen_channel(**params))

            elif command == 'add_executed_orders':
                await self.join_group(executed_order_notificator.gen_channel(**params))
            elif command == 'del_executed_orders':
                await self.leave_group(executed_order_notificator.gen_channel(**params))

            elif command == 'add_wallet_history':
                await self.join_group(wallet_history_notificator.gen_channel(**params))
                data = await sync_to_async(wallet_history_notificator.get_paginated_data)(**params)
                data = wallet_history_notificator.prepare_data(data)
                await self.send_json(data)
            elif command == 'del_wallet_history':
                await self.leave_group(wallet_history_notificator.gen_channel(**params))

            elif command == 'add_wallet_topups_history':
                await self.join_group(wallet_topups_history_notificator.gen_channel(**params))
                data = await sync_to_async(wallet_topups_history_notificator.get_paginated_data)(**params)
                data = wallet_topups_history_notificator.prepare_data(data)
                await self.send_json(data)
            elif command == 'del_wallet_topups_history':
                await self.leave_group(wallet_topups_history_notificator.gen_channel(**params))

            elif command == 'add_wallet_withdrawals_history':
                await self.join_group(wallet_withdrawals_history_notificator.gen_channel(**params))
                data = await sync_to_async(wallet_withdrawals_history_notificator.get_paginated_data)(**params)
                data = wallet_withdrawals_history_notificator.prepare_data(data)
                await self.send_json(data)
            elif command == 'del_wallet_withdrawals_history':
                await self.leave_group(wallet_withdrawals_history_notificator.gen_channel(**params))

            elif command == 'add_wallet_ticker_history':
                await self.join_group(wallet_history_ticker_notificator.gen_channel(**params))
                data = await sync_to_async(wallet_history_ticker_notificator.get_paginated_data)(**params)
                data = wallet_history_ticker_notificator.prepare_data(data)
                await self.send_json(data)
            elif command == 'del_wallet_ticker_history':
                await self.leave_group(wallet_history_ticker_notificator.gen_channel(**params))

            elif command == 'get_opened_orders':
                data = await sync_to_async(opened_orders_endpoint.get_data)(**params)
                data = opened_orders_endpoint.prepare_data(data)
                await self.send_json(data)

            elif command == 'get_closed_orders':
                data = await sync_to_async(closed_orders_endpoint.get_data)(**params)
                data = closed_orders_endpoint.prepare_data(data)
                await self.send_json(data)

            elif command == 'get_opened_orders_by_pair':
                data = await sync_to_async(opened_orders_by_pair_endpoint.get_data)(**params)
                data = opened_orders_by_pair_endpoint.prepare_data(data)
                await self.send_json(data)

            elif command == 'get_closed_orders_by_pair':
                data = await sync_to_async(closed_orders_by_pair_endpoint.get_data)(**params)
                data = closed_orders_by_pair_endpoint.prepare_data(data)
                await self.send_json(data)

            elif command == 'get_wallets':
                data = await sync_to_async(wallets_notificator.get_data)(**params)
                data = wallets_notificator.prepare_data(data)
                await self.send_json(data)

            elif command == 'get_wallet_history':
                data = await sync_to_async(wallet_history_endpoint.get_data)(**params)
                data = wallet_history_endpoint.prepare_data(data)
                await self.send_json(data)

            # elif command == 'get_profile':
            #     data = await sync_to_async(profile_notificator.get_data)(**params)
            #     data = profile_notificator.prepare_data(data)
            #     await self.send_json(data)

    async def disconnect(self, code):
        logger.debug('receive')
        for i in list(self.groups):
            await self.leave_group(i)

    async def exchange_message(self, event):
        data = event['data']
        user_id = self.scope['user'] and getattr(self.scope['user'], 'id')

        if data['kind'] == stack_notificator.MSG_KIND:
            stack = data['stack']
            data = stack_notificator.prepare_data(
                stack,
                pair_name=data['pair'],
                precision=data['precision'],
                user_id=user_id,
            )

        await self.send_json(data)
