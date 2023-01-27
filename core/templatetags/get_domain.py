from django import template
from django.contrib.sites.models import Site

register = template.Library()


@register.simple_tag(takes_context=True)
def get_domain(context, *args, **kwargs):
    domain = Site.objects.get_current().domain
    return 'https://' + domain
