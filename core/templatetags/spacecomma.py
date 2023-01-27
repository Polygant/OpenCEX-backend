from django import template
# from django.utils import numberformat
import re
register = template.Library()


@register.filter('spacecomma')
def spacecomma(value, arg=None):
    lte = None
    gte = None

    if not value:
        return value

    if '.' in str(value) or 'E' in str(value):
        value = float(value)
    else:
        value = int(value)
    reg = '{:,}'

    if arg and ',' in str(arg):
        gte, lte = arg.split(',')
    else:
        gte = arg

    if gte or gte == 0:
        reg = "{:,."+str(gte)+"f}"
        if not lte:
            lte = gte

    if -1 < value < 1 and lte:
        reg = "{:,."+str(lte)+"f}"

    val = reg.format(value)

    if '.' in val:
        val = val.rstrip('0').rstrip('.')

    return val.replace(",", " ")
