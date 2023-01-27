from lib.cache import PrefixedRedisCache


class TestPrefixedRedisCache:

    def test_cache(self):
        cache = PrefixedRedisCache.get_cache('app1')

        cache.set('key', 'value')
        assert cache.get('key') == 'value'
