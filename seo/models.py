from django.db import models
from django.utils.timezone import now

from core.currency import CurrencyModelField
from lib.fields import RichTextField
from seo.validators import upload_to, validate_extension


class Tag(models.Model):
    slug = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255, default='')
    title = models.CharField(max_length=255)
    meta_title = models.TextField(blank=True, null=True, default=None)
    meta_description = models.TextField(blank=True, null=True, default=None)

    def __str__(self):
        return self.slug


class Post(models.Model):
    created = models.DateTimeField(default=now)
    slug = models.CharField(max_length=255, blank=True, null=True)
    title = models.TextField(null=True, blank=True)
    text = RichTextField(null=True, blank=True)
    preview_image = models.ImageField(upload_to='uploads/preview/',
                                      blank=True, null=True, default=None)
    views_count = models.PositiveIntegerField(blank=True, default=0)
    meta_title = models.TextField(blank=True, null=True)
    meta_description = models.TextField(blank=True, null=True)
    tags = models.ManyToManyField(Tag)

    def __str__(self):
        title = self.title
        if not title:
            title = self.title_ru
        return f'{self.created.date()} {title}'

    @classmethod
    def get_slugs_list(cls):
        return list(cls.objects.all().values_list('slug_ru', flat=True)) + \
            list(cls.objects.all().values_list('slug_en', flat=True))

    class Meta:
        ordering = (
            '-created',
        )


class ContentPhoto(models.Model):
    title = models.CharField(max_length=255)
    announce_image = models.ImageField(upload_to=upload_to, validators=[validate_extension])

    def __str__(self):
        return self.title


class CoinStaticPage(models.Model):
    """
    Static coin SEO pages content
    """
    # symbol
    currency = CurrencyModelField(unique=True)
    # page title
    title = models.CharField(verbose_name='Page title', max_length=511, blank=True, default='')
    # text name
    name = models.CharField(verbose_name='Currency name (e.g. Bitcoin)', max_length=255)
    trade_button_text = models.CharField(verbose_name='Header trade button text',
                                         max_length=511, blank=True, default='')

    meta_description = models.TextField(blank=True, default='')
    header_text = RichTextField()
    usd_block_text = RichTextField(blank=True, default='')
    eur_block_text = RichTextField(blank=True, default='')
    rub_block_text = RichTextField(blank=True, default='')
    footer_text = RichTextField()

    def __str__(self):
        return f'{self.currency}'


class CoinStaticSubPage(models.Model):
    currency = CurrencyModelField()
    slug = models.CharField(max_length=255, blank=True, default='')
    title = models.CharField(max_length=255, blank=True, default='')
    content = RichTextField(blank=True, default='')
    meta_title = models.TextField(blank=True, default='')
    meta_description = models.TextField(blank=True, default='')
