import re
from django import template

numeric_test = re.compile("^\d+$")
register = template.Library()


def getattribute(value, arg: str):
    """Gets an attribute of an object dynamically from a string name"""
    result = '---'  # settings.TEMPLATE_STRING_IF_INVALID

    args = arg.split('.')

    arg = args.pop(0)

    if hasattr(value, str(arg)):
        result = getattr(value, arg)
    elif arg in value:
        result = value[arg]
    elif numeric_test.match(str(arg)) and len(value) > int(arg):
        result = value[int(arg)]
    return getattribute(result, '.'.join(args)) if len(args) > 0 else result


register.filter('getattribute', getattribute)


def get_type(value):
    return type(value)


register.filter('get_type', get_type)


def bool_to_icon(value):
    if isinstance(value, bool):
        if value:
            return '<img src="/staticfiles/admin/img/icon-yes.svg" alt="True">'
        else:
            return '<img src="/staticfiles/admin/img/icon-no.svg" alt="False">'
    return value


register.filter('bool_to_icon', bool_to_icon)
