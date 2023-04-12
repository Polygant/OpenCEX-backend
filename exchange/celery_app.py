import os

from tblib import pickling_support

from exchange.settings import env

pickling_support.install()

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'exchange.settings')
django.setup()

from lib.cryptointegrator.tasks import generate_crypto_schedule
from kombu import Queue
from django.conf import settings
from celery.schedules import crontab
from celery import Celery
from celery.signals import worker_ready


# @worker_ready.connect
# def at_start(sender, **k):
#     with sender.app.connection() as conn:
#          sender.app.send_task('inouts.tasks.sync_currencies_with_db', (), connection=conn)


def is_section_enabled(name):
    return env(f'COMMON_TASKS_{name.upper()}', default=True)

backend_url = f"redis://:{settings.REDIS['pwd']}@{settings.REDIS['host']}:{settings.REDIS['port']}" \
    if settings.REDIS['pwd'] else \
    f"redis://{settings.REDIS['host']}:{settings.REDIS['port']}"

app = Celery(
    'exchange',
    backend=backend_url,
    broker=settings.BROKER_URL,
    include=['bots.tasks']
)

app.config_from_object('django.conf:settings', namespace='CELERY')
app.conf.worker_log_format = "[%(asctime)s: %(processName)s %(levelname)s] %(name)s %(message)s"

app.conf.beat_schedule = {}
app.conf.task_routes = {}
app.conf.task_default_queue = 'default'

app.conf.task_queues = (
    Queue('default'),
    Queue('mailing'),
)

app.conf.beat_schedule.update(generate_crypto_schedule(settings.CRYPTO_AUTO_SCHEDULE_CONF))

generated_queues = []
for item in settings.CRYPTO_AUTO_SCHEDULE_CONF:
    currency_symbol = item.get('currency').lower()
    generated_queues.append(Queue(currency_symbol))

app.conf.task_queues += tuple(generated_queues)

if is_section_enabled('payout_withdraw'):
    app.conf.beat_schedule.update({
        'sci_process_withdrawals': {
            'task': 'core.tasks.inouts.process_withdrawal_requests',
            'schedule': crontab(minute='*/15'),
            'args': (),
            'options': {
                'expires': 10,
                'queue': 'payout_withdraw',
            }

        },
        'cancel_expired_withdrawals': {
            'task': 'core.tasks.inouts.cancel_expired_withdrawals',
            'schedule': crontab(minute='*/15'),
            'args': (),
            'options': {
                'expires': 10,
                'queue': 'payout_withdraw',
            }
        },
    })
    app.conf.task_queues += (Queue('payout_withdraw'),)

if is_section_enabled('cryptocoins_commons'):
    app.conf.beat_schedule.update({
        'check_accumulations': {
            'task': 'cryptocoins.tasks.commons.check_accumulations',
            'schedule': 20,
            'options': {
                'queue': 'cryptocoins_commons',
            }
        },
        'mark_accumulated_topups': {
            'task': 'cryptocoins.tasks.commons.mark_accumulated_topups',
            'schedule': 60,
            'options': {
                'queue': 'cryptocoins_commons',
            }
        },
    })
    app.conf.task_routes.update({
        'core.tasks.orders.stop_limit_processor': {
            'queue': 'cryptocoins_commons',
        },
    }),
    app.conf.task_routes.update({
        'cryptocoins.tasks.commons.mark_accumulated_topups_for_currency': {
            'queue': 'cryptocoins_commons',
        },
    }),
    app.conf.task_queues += (Queue('cryptocoins_commons'),)

if is_section_enabled('ethereum'):
    app.conf.beat_schedule.update({
        'eth_process_new_blocks': {
            'task': 'cryptocoins.tasks.eth.eth_process_new_blocks',
            'schedule': settings.ETH_BLOCK_GENERATION_TIME,
        },
        'eth_check_balances': {
            'task': 'cryptocoins.tasks.eth.check_balances',
            'schedule': settings.ETH_ERC20_ACCUMULATION_PERIOD,
            'options': {
                'expires': 20,
            }
        },
        # 'process_payouts': {
        #     'task': 'cryptocoins.tasks.eth.process_payouts',
        #     'schedule': settings.ETH_ERC20_ACCUMULATION_PERIOD,
        #     'options': {
        #         'expires': 20,
        #     }
        # },
    })
    app.conf.task_routes.update({
        'cryptocoins.tasks.eth.eth_process_new_blocks': {
            'queue': 'eth_new_blocks',
        },
        'cryptocoins.tasks.eth.eth_process_block': {
            'queue': 'eth_new_blocks',
        },
    }),
    app.conf.task_routes.update({
        'cryptocoins.tasks.eth.eth_process_eth_deposit': {
            'queue': 'eth_deposits',
        },
        'cryptocoins.tasks.eth.eth_process_erc20_deposit': {
            'queue': 'eth_deposits',
        },
    }),
    app.conf.task_routes.update({
        'cryptocoins.tasks.eth.process_payouts': {
            'queue': 'eth_payouts',
        },
        'cryptocoins.tasks.eth.withdraw_eth': {
            'queue': 'eth_payouts',
        },
        'cryptocoins.tasks.eth.withdraw_erc20': {
            'queue': 'eth_payouts',
        },
    }),
    app.conf.task_routes.update({
        'cryptocoins.tasks.eth.check_balances': {
            'queue': 'eth_check_balances',
        },
        'cryptocoins.tasks.eth.check_balance': {
            'queue': 'eth_check_balances',
        },
        'cryptocoins.tasks.eth.check_tx_withdrawal': {
            'queue': 'eth_check_balances',
        },
        'cryptocoins.tasks.eth.check_deposit_scoring': {
            'queue': 'eth_check_balances',
        },
    }),
    app.conf.task_routes.update({
        'cryptocoins.tasks.eth.accumulate_eth': {
            'queue': 'eth_accumulations',
        },
    }),
    app.conf.task_routes.update({
        'cryptocoins.tasks.eth.accumulate_erc20': {
            'queue': 'erc20_accumulations',
        },
    }),
    app.conf.task_routes.update({
        'cryptocoins.tasks.eth.send_gas': {
            'queue': 'eth_send_gas',
        },
    }),

    app.conf.task_queues += (
        Queue('eth_new_blocks'),
        Queue('eth_deposits'),
        Queue('eth_payouts'),
        Queue('eth_check_balances'),
        Queue('eth_accumulations'),
        Queue('erc20_accumulations'),
        Queue('eth_send_gas'),
    )

if is_section_enabled('bnb'):
    app.conf.beat_schedule.update({
        'bnb_process_new_blocks': {
            'task': 'cryptocoins.tasks.bnb.bnb_process_new_blocks',
            'schedule': settings.BNB_BLOCK_GENERATION_TIME,
        },
        'bnb_check_balances': {
            'task': 'cryptocoins.tasks.bnb.check_balances',
            'schedule': settings.BNB_BEP20_ACCUMULATION_PERIOD,
            'options': {
                'expires': 20,
            }
        },
        # 'cryptocoins.tasks.bnb.accumulate_bnb_dust': {
        #     'task': 'cryptocoins.tasks.bnb.accumulate_bnb_dust',
        #     'schedule': crontab(minute='5', hour='0'),
        #     'options': {
        #         'queue': 'bnb_accumulations',
        #     }
        # },
        # 'process_payouts': {
        #     'task': 'cryptocoins.tasks.bnb.process_payouts',
        #     'schedule': settings.BNB_BEP20_ACCUMULATION_PERIOD,
        #     'options': {
        #         'expires': 20,
        #     }
        # },
    })
    app.conf.task_routes.update({
        'cryptocoins.tasks.bnb.bnb_process_new_blocks': {
            'queue': 'bnb_new_blocks',
        },
        'cryptocoins.tasks.bnb.bnb_process_block': {
            'queue': 'bnb_new_blocks',
        },
    }),
    app.conf.task_routes.update({
        'cryptocoins.tasks.bnb.bnb_process_bnb_deposit': {
            'queue': 'bnb_deposits',
        },
        'cryptocoins.tasks.bnb.bnb_process_bep20_deposit': {
            'queue': 'bnb_deposits',
        },
    }),
    app.conf.task_routes.update({
        'cryptocoins.tasks.bnb.process_payouts': {
            'queue': 'bnb_payouts',
        },
        'cryptocoins.tasks.bnb.withdraw_bnb': {
            'queue': 'bnb_payouts',
        },
        'cryptocoins.tasks.bnb.withdraw_bep20': {
            'queue': 'bnb_payouts',
        },
    }),
    app.conf.task_routes.update({
        'cryptocoins.tasks.bnb.check_balances': {
            'queue': 'bnb_check_balances',
        },
        'cryptocoins.tasks.bnb.check_balance': {
            'queue': 'bnb_check_balances',
        },
        'cryptocoins.tasks.bnb.check_tx_withdrawal': {
            'queue': 'bnb_check_balances',
        },
        'cryptocoins.tasks.bnb.check_deposit_scoring': {
            'queue': 'bnb_check_balances',
        },
    }),
    app.conf.task_routes.update({
        'cryptocoins.tasks.bnb.accumulate_bnb': {
            'queue': 'bnb_accumulations',
        },
    }),
    app.conf.task_routes.update({
        'cryptocoins.tasks.bnb.accumulate_bep20': {
            'queue': 'bep20_accumulations',
        },
    }),
    app.conf.task_routes.update({
        'cryptocoins.tasks.bnb.send_gas': {
            'queue': 'bnb_send_gas',
        },
    }),

    app.conf.task_queues += (
        Queue('bnb_new_blocks'),
        Queue('bnb_deposits'),
        Queue('bnb_payouts'),
        Queue('bnb_check_balances'),
        Queue('bnb_accumulations'),
        Queue('bep20_accumulations'),
        Queue('bnb_send_gas'),
    )

if is_section_enabled('tron'):
    app.conf.beat_schedule.update({
        'trx_process_new_blocks': {
            'task': 'cryptocoins.tasks.trx.trx_process_new_blocks',
            'schedule': settings.TRX_BLOCK_GENERATION_TIME,
        },
        'trx_check_balances': {
            'task': 'cryptocoins.tasks.trx.check_balances',
            'schedule': settings.TRX_TRC20_ACCUMULATION_PERIOD,
            'options': {
                'expires': 20,
            }
        },
        # 'cryptocoins.tasks.trx.accumulate_trx_dust': {
        #     'task': 'cryptocoins.tasks.trx.accumulate_trx_dust',
        #     'schedule': crontab(minute='10', hour='0'),
        #     'options': {
        #         'queue': 'trx_accumulations',
        #     }
        # },
    })
    app.conf.task_routes.update({
        'cryptocoins.tasks.trx.trx_process_new_blocks': {
            'queue': 'trx_new_blocks',
        },
        'cryptocoins.tasks.trx.trx_process_block': {
            'queue': 'trx_new_blocks',
        },
    }),
    app.conf.task_routes.update({
        'cryptocoins.tasks.trx.trx_process_trx_deposit': {
            'queue': 'trx_deposits',
        },
        'cryptocoins.tasks.trx.trx_process_trc20_deposit': {
            'queue': 'trx_deposits',
        },
    }),
    app.conf.task_routes.update({
        'cryptocoins.tasks.trx.process_payouts': {
            'queue': 'trx_payouts',
        },
        'cryptocoins.tasks.trx.withdraw_trx': {
            'queue': 'trx_payouts',
        },
        'cryptocoins.tasks.trx.withdraw_trc20': {
            'queue': 'trx_payouts',
        },
    }),
    app.conf.task_routes.update({
        'cryptocoins.tasks.trx.check_balances': {
            'queue': 'trx_check_balances',
        },
        'cryptocoins.tasks.trx.check_balance': {
            'queue': 'trx_check_balances',
        },
        'cryptocoins.tasks.trx.check_tx_withdrawal': {
            'queue': 'trx_check_balances',
        },
        'cryptocoins.tasks.trx.check_deposit_scoring': {
            'queue': 'trx_check_balances',
        },
    }),
    app.conf.task_routes.update({
        'cryptocoins.tasks.trx.accumulate_trx': {
            'queue': 'trx_accumulations',
        },
    }),
    app.conf.task_routes.update({
        'cryptocoins.tasks.trx.accumulate_trc20': {
            'queue': 'trc20_accumulations',
        },
    }),

    app.conf.task_queues += (
        Queue('trx_new_blocks'),
        Queue('trx_deposits'),
        Queue('trx_payouts'),
        Queue('trx_check_balances'),
        Queue('trx_accumulations'),
        Queue('trc20_accumulations'),
    )

if is_section_enabled('notifications'):
    app.conf.task_routes.update({
        'core.tasks.facade.pong': {
            'queue': 'notifications',
        },
    })
    app.conf.task_routes.update({
        'core.tasks.facade.notify_sof_*': {
            'queue': 'notifications',
        },
    })
    app.conf.task_routes.update({
        'core.tasks.orders.send_exchange_completed_message': {
            'queue': 'notifications',
        },
    })
    app.conf.task_routes.update({
        'core.tasks.orders.send_exchange_expired_message': {
            'queue': 'notifications',
        },
    })
    app.conf.task_routes.update({
        'core.tasks.orders.send_order_changed_api_callback_request': {
            'queue': 'notifications',
        }
    })
    app.conf.task_routes.update({
        'core.tasks.inouts.withdrawal_failed_email': {
            'queue': 'notifications',
        },
    })
    app.conf.task_routes.update({
        'core.tasks.inouts.send_sepa_details_email*': {
            'queue': 'notifications',
        },
    })
    app.conf.task_routes.update({
        'core.tasks.facade.notify_user_ip_changed': {
            'queue': 'notifications',
        },
    })
    app.conf.task_routes.update({
        'core.tasks.facade.notify_failed_login': {
            'queue': 'notifications',
        },
    })
    app.conf.task_routes.update({
        'core.tasks.inouts.send_withdrawal_confirmation_email': {
            'queue': 'notifications',
        },
    })

    app.conf.task_queues += (Queue('notifications'),)

if is_section_enabled('utils'):
    @worker_ready.connect
    def at_start(sender, **k):
        with sender.app.connection() as conn:
            sender.app.send_task('core.tasks.inouts.sync_currencies_with_db',
                                 (), connection=conn, queue='utils')
            sender.app.send_task('core.tasks.settings.initialize_settings',
                                 (), connection=conn, queue='utils')


    app.conf.beat_schedule.update({
        # 'cryptocoins.tasks.eth.accumulate_eth_dust': {
        #     'task': 'cryptocoins.tasks.eth.accumulate_eth_dust',
        #     'schedule': crontab(minute='0', hour='0'),
        #     'options': {
        #         'queue': 'utils',
        #     }
        # },
        'cryptocoins.tasks.commons.check_crypto_workers': {
            'task': 'cryptocoins.tasks.commons.check_crypto_workers',
            'schedule': crontab(minute=0),  # every hour
            'options': {
                'queue': 'utils',
            }
        },
    })
    app.conf.task_queues += (Queue('utils'),)

if is_section_enabled('kyc'):
    app.conf.beat_schedule.update({
        'plan_kyc_data_update': {
            'task': 'core.tasks.facade.plan_kyc_data_updates',
            'schedule': crontab(minute='*/10'),
            'options': {
                'queue': 'kyc',
            }
        },
    })
    app.conf.task_queues += (Queue('kyc'),)

if is_section_enabled('cleanup'):
    app.conf.beat_schedule.update({
        'bot_matches_cleanup': {
            'task': 'core.tasks.orders.bot_matches_cleanup',
            'schedule': crontab(minute='30', hour='0'),
            'options': {
                'queue': 'cleanup',
            },
        },
        'auto_transactions_cleanup': {
            'task': 'core.tasks.orders.cleanup_extra_transactions',
            'schedule': crontab(minute='20', hour='0'),
            'options': {
                'queue': 'cleanup',
            },
        },
        'clear_sessions': {
            'task': 'core.tasks.facade.clear_sessions',
            'schedule': crontab(minute='10', hour='0'),
            'options': {
                'queue': 'cleanup',
            },
        },
        'clear_old_logs': {
            'task': 'core.tasks.facade.clear_old_logs',
            'schedule': crontab(minute='11', hour='0'),
            'options': {
                'queue': 'cleanup',
            },
        },
        'clear_login_history': {
            'task': 'core.tasks.facade.clear_login_history',
            'schedule': crontab(minute='12', hour='0'),
            'options': {
                'queue': 'cleanup',
            },
        },
        'order_changes_cleanup': {
            'task': 'core.tasks.orders.cleanup_old_order_changes',
            'schedule': crontab(minute='13', hour='0'),
            'options': {
                'queue': 'cleanup',
            },
        },
        'external_prices_history_cleanup': {
            'task': 'core.tasks.stats.cleanup_old_prices_history',
            'schedule': crontab(minute='13', hour='0'),
            'options': {
                'queue': 'cleanup',
            },
        },
        'trades_aggregated_cleanup': {
            'task': 'core.tasks.stats.trades_aggregated_cleanup',
            'schedule': crontab(minute='14', hour='0'),
            'options': {
                'queue': 'cleanup',
            },
        },
        'clean_old_difbalances': {
            'task': 'core.tasks.inouts.clean_old_difbalances',
            'schedule': crontab(minute='15', hour='0'),
            'options': {
                'queue': 'cleanup',
            },
        },
        # 'vacuum_database': {
        #     'task': 'core.tasks.stats.vacuum_database',
        #     'schedule': crontab(minute='0', hour='1', day_of_week='1'),
        #     'options': {
        #         'queue': 'cleanup',
        #     },
        # },
    })
    app.conf.task_queues += (Queue('cleanup'),)

if is_section_enabled('bots'):
    app.conf.beat_schedule.update({
        'run_bots': {
            'task': 'bots.tasks.check_bots',
            'schedule': 5.0,
            'options': {
                'queue': 'bots',
            }
        }
    })
    app.conf.task_queues += (Queue('bots'),)

if is_section_enabled('otc'):
    app.conf.beat_schedule.update({
        'otc_orders_price_update': {
            'task': 'core.tasks.orders.otc_orders_price_update',
            'schedule': crontab(minute='*'),
            'options': {
                # ensure we don't accumulate a huge backlog of these if the workers are down
                'expires': 20,
                'queue': 'otc'
            }
        },
        'update_crypto_external_prices': {
            'task': 'cryptocoins.tasks.datasources.update_crypto_external_prices',
            'schedule': 15.0,
            'options': {
                'queue': 'otc',
            }
        },
        'update_cryptocompare_pairs_price_cache': {
            'task': 'core.tasks.stats.update_cryptocompare_pairs_price_cache',
            'schedule': crontab(minute='*'),
            'options': {
                'queue': 'otc',
            }
        },
    })
    app.conf.task_queues += (Queue('otc'),)

if is_section_enabled('stats'):
    app.conf.task_routes.update({
        'core.tasks.stats.do_trades_aggregation_for_pair': {
            'queue': 'stats',
        }
    })
    app.conf.beat_schedule.update({
        'make_user_stats': {
            'task': 'core.tasks.stats.make_user_stats',
            'schedule': crontab(minute='1', hour='5'),
            'args': (),
            'options': {
                'queue': 'stats',
            }
        },
        'aggregate_fee': {
            'task': 'core.tasks.orders.aggregate_fee',
            'schedule': crontab(minute='1', hour='4'),
            'args': (),
            'options': {
                'queue': 'stats',
            }
        },
        'pairs_24h_stats_cache_update': {
            'task': 'core.tasks.orders.pairs_24h_stats_cache_update',
            'schedule': crontab(minute='*'),
            'args': (),
            'options': {
                'queue': 'stats',
            }
        },
        'trades_agg_minute': {
            'task': 'core.tasks.stats.plan_trades_aggregation',
            'schedule': crontab(minute='*'),
            'args': ('minute',),
            'options': {
                'queue': 'stats',
            }
        },
        'trades_agg_hour': {
            'task': 'core.tasks.stats.plan_trades_aggregation',
            'schedule': crontab(minute='1'),
            'args': ('hour',),
            'options': {
                'queue': 'stats',
            }
        },
        'trades_agg_day': {
            'task': 'core.tasks.stats.plan_trades_aggregation',
            'schedule': crontab(minute='1', hour='0'),
            'args': ('day',),
            'options': {
                'queue': 'stats',
            }
        },
        'cache_bitcoin_sat_per_byte': {
            'task': 'cryptocoins.tasks.btc.cache_bitcoin_sat_per_byte',
            'schedule': settings.SAT_PER_BYTES_UPDATE_PERIOD,
            'options': {
                'queue': 'stats',
            }
        },
        'calculate_topups_and_withdrawals': {
            'task': 'cryptocoins.tasks.stats.calculate_topups_and_withdrawals',
            'schedule': crontab(minute='0', hour='0'),
            'options': {
                'queue': 'stats',
            }
        },
        'calculate_dif_balances': {
            'task': 'core.tasks.inouts.calculate_dif_balances',
            'schedule': crontab(minute='0', hour='0'),
            'options': {
                'queue': 'stats',
            },
        },
        'calculate_dif_balances_1m': {
            'task': 'core.tasks.inouts.calculate_dif_balances',
            'schedule': crontab(minute='0', hour='1', day_of_month='*/10'),
            'args': ('1m',),
            'options': {
                'queue': 'stats',
            },
        },
        'fill_inout_coin_stats': {
            'task': 'core.tasks.stats.fill_inout_coin_stats',
            'schedule': crontab(minute='5', hour='0'),
            'options': {
                'queue': 'stats',
            },
        }
    })
    app.conf.task_queues += (Queue('stats'),)

if is_section_enabled('stop_limits'):
    app.conf.task_routes.update({
        'core.tasks.orders.stop_limit_processor': {
            'queue': 'stop_limits',
        },
    }),
    app.conf.task_queues += (Queue('stop_limits'),)
