import logging
import os
import shutil
import tarfile

from django.conf import settings
from django.db import models
from django.utils import timezone
from import_export import resources
from import_export.widgets import Widget
from tablib import Dataset

from core.currency import Currency
from core.models import Order, Transaction, ExecutionResult
from core.models.inouts.pair import Pair

log = logging.getLogger(__name__)

BACKUP_PATH = os.path.join(settings.BASE_DIR, 'cleanup_backups')
TEMP_DIR = os.path.join(BACKUP_PATH, 'tmp')
RESTORE_DIR = os.path.join(BACKUP_PATH, 'restore')


class CurrencyWidget(Widget):
    def clean(self, value, row=None, *args, **kwargs):
        return Currency.get(value)


class PairWidget(Widget):
    def clean(self, value, row=None, *args, **kwargs):
        return Pair.get(value)


resources.ModelResource.WIDGETS_MAP['CurrencyModelField'] = CurrencyWidget
resources.ModelResource.WIDGETS_MAP['PairModelField'] = PairWidget


def prepare_backup():
    log.info('Preparing cleanup backup')
    if not os.path.exists(BACKUP_PATH):
        os.mkdir(BACKUP_PATH)
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.mkdir(TEMP_DIR)


def finish_backup():
    log.info(f'Creating backup archive')
    filenames = ['transaction.csv', 'order.csv', 'executionresult.csv']
    now = timezone.now().date()
    name = f'backup_{now}'
    filepath = os.path.join(BACKUP_PATH, name)
    archive_files(filepath, filenames)
    shutil.rmtree(TEMP_DIR)
    log.info(f'Temp dir successfully deleted')


def backup_qs_to_csv(queryset):
    filename = f'{queryset.model._meta.model_name}.csv'
    filename = os.path.join(TEMP_DIR, filename)
    res = queryset_to_csv(queryset, filename)
    return res


def queryset_to_csv(queryset, filename):
    resource = create_import_export_resource(queryset.model)
    dataset = resource.export(queryset)
    csv = dataset.csv

    # delete header if file already exists
    if os.path.exists(filename):
        csv = csv.split('\r\n',1)[1]

    with open(filename, 'a') as csvfile:
        csvfile.write(csv)
    log.info(f'{len(dataset)} rows written to {filename}')
    return filename


def archive_files(arc_name, filenames):
    arc_name = f'{arc_name}.tar.gz'
    tar = tarfile.open(arc_name, 'w:gz')
    for filename in filenames:
        filepath = os.path.join(TEMP_DIR, filename)
        if not os.path.exists(filepath):
            log.info(f'File {filepath} not found')
            continue
        tar.add(filepath, arcname=filename)
    tar.close()
    log.info(f'{arc_name} successfully created')


def restore_from_backup(arch_name):
    if os.path.exists(RESTORE_DIR):
        shutil.rmtree(RESTORE_DIR)
    os.mkdir(RESTORE_DIR)
    backup_arch_name = os.path.join(BACKUP_PATH, arch_name)
    extract_archive(backup_arch_name, RESTORE_DIR)

    models = [Transaction, Order, ExecutionResult]
    # models = [ Order, ExecutionResult]
    for model in models:
        filename = f'{model._meta.model_name}.csv'
        filepath = os.path.join(RESTORE_DIR, filename)

        if not os.path.exists(filepath):
            log.warning(f'{filepath} not exists')
            continue

        restore_model_from_csv(filepath, model)
    log.info('Deleting temp restore folder')
    shutil.rmtree(RESTORE_DIR)


def extract_archive(archive_name, extraction_dirname='.'):
    tar = tarfile.open(archive_name, "r")
    tar.extractall(extraction_dirname)


def restore_model_from_csv(csv_name, model):
    log.info(f'Restoring {csv_name}')
    dataset = Dataset()
    with open(csv_name) as csvfile:
        imported_data = dataset.load(csvfile.read(), 'csv')

    resource = create_import_export_resource(model)
    res = resource.import_data(dataset=dataset, raise_errors=True)
    log.info(f'Restored {res.total_rows} entries')


def create_import_export_resource(model_cls):
    fields = model_cls._meta.get_fields()
    foreign_key_fields_dict = {f.name: f.attname for f in fields if isinstance(f, models.ForeignKey)}

    def add_method(cls, field_name, db_name):
        def inner_fn(self, obj):
            # print(obj, db_name)
            return getattr(obj, db_name, None)

        inner_fn.__name__ = f'dehydrate_{field_name}'
        inner_fn.__doc__ = f'dehydrate_{field_name}'
        setattr(cls, f'dehydrate_{field_name}', inner_fn)

    class AutoResource(resources.ModelResource):
        class Meta:
            model = model_cls
            use_bulk = True
            always_bulk_create = True

        # def get_field_name(self, field):
        #     """
        #     Returns the field name for a given field.
        #     """
        #     for field_name, f in self.fields.items():
        #         if f == field:
        #             if field_name in foreign_key_fields_dict:
        #                 return foreign_key_fields_dict[field_name]
        #             return field_name
        #     raise AttributeError("Field %s does not exists in %s resource" % (
        #         field, self.__class__))

        def save_instance(self, instance, using_transactions=True, dry_run=False):
            self.before_save_instance(instance, using_transactions, dry_run)
            if self._meta.use_bulk:
                if instance.pk and not self._meta.always_bulk_create:
                    self.update_instances.append(instance)
                else:
                    self.create_instances.append(instance)
            else:
                if not using_transactions and dry_run:
                    # we don't have transactions and we want to do a dry_run
                    pass
                else:
                    instance.save()
            self.after_save_instance(instance, using_transactions, dry_run)

    for name, db_name in foreign_key_fields_dict.items():
        add_method(AutoResource, name, db_name)

    return AutoResource()
