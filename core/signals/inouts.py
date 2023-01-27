from django.dispatch import Signal

balance_changed = Signal(providing_args=['user_id'])
