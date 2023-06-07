from django.db import migrations
from django.db import connection, transaction

from core.pairs import Pair


def transfer_data(apps, schema_editor):
    NewPair = apps.get_model('core', 'Pair')
    with connection.cursor() as cursor:
        cursor.execute("SELECT pair FROM core_pairsettings")
        for row in cursor.fetchall():
            old_pair = Pair.get(row[0])
            pair = NewPair(id=old_pair.id, base=old_pair.base, quote=old_pair.quote)
            pair.save()


def auto_increment_start(apps, schema_editor):
    with connection.cursor() as cursor:
        cursor.execute("SELECT max(id) FROM core_pair")
        max_id = cursor.fetchone()[0]
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
