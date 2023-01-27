from django.dispatch import Signal

order_changed = Signal(providing_args=['order'])

market_order_closed = Signal(providing_args=['order'])
