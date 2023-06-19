from django.db import migrations
from django.db import connection, transaction
from django.db.models import Max

from core.models import Pair
from core.pairs import PAIRS_LIST


def transfer_data(apps, schema_editor):
    from cryptocoins.tokens_manager import register_tokens_and_pairs
    register_tokens_and_pairs()
    for pair in PAIRS_LIST:
        pair_id = pair[0]
        base, quote = pair[1].split('-')
        Pair.objects.get_or_create(id=pair_id, base=base, quote=quote)


def auto_increment_start(apps, schema_editor):
    with connection.cursor() as cursor:
        Pair = apps.get_model('core', 'Pair')
        pairs = Pair.objects.all()
        max_id = pairs.aggregate(Max('id'))['id__max']
        if max_id:
            cursor.execute(f"""
                SELECT setval(pg_get_serial_sequence('"core_pair"','id'), coalesce(max("id"), {max_id}), max("id") IS NOT null) FROM "core_pair";
            """)
        transaction.atomic()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_auto_20230606_1047'),
    ]

    operations = [
        migrations.RunPython(transfer_data, lambda *args: None),
        migrations.RunPython(auto_increment_start, lambda *args: None)
    ]
