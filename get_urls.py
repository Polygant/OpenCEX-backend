import os
import random
import time



os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'exchange.settings')
import django

django.setup()

def main():
    from django.conf import settings
    from django.urls import URLPattern, URLResolver

    urlconf = __import__(settings.ROOT_URLCONF, {}, {}, [''])

    def list_urls(lis, acc=None):
        if acc is None:
            acc = []
        if not lis:
            return
        l = lis[0]
        if isinstance(l, URLPattern):
            yield acc + [str(l.pattern)]
        elif isinstance(l, URLResolver):
            yield from list_urls(l.url_patterns, acc + [str(l.pattern)])
        yield from list_urls(lis[1:], acc)

    for p in list_urls(urlconf.urlpatterns):
        print(''.join(p))


if __name__ == '__main__':
    print('Start')
    main()
    print('Stop')

