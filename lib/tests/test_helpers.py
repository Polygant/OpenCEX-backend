import pytest

from decimal import Decimal

from lib.helpers import to_decimal, normalize_data


class TestToDecimal:

    def test_float_to_decimal(self):
        assert to_decimal('1.020304050607', decimal_places=8) == Decimal('1.02030405')
        assert to_decimal('1.020304050607', decimal_places=10) == Decimal('1.0203040506')
        assert to_decimal(0.001) == Decimal('0.001')
        assert to_decimal(1) == Decimal('1')
        assert to_decimal(Decimal('1.020304050607'), decimal_places=8) == Decimal('1.02030405')
        assert to_decimal(0.00000001) == Decimal('0.00000001')
        assert to_decimal(1.00000001) == Decimal('1.00000001')
        assert to_decimal(0.1) * to_decimal(0.1) == to_decimal(0.01)
        assert to_decimal(10.01) * to_decimal(10.01) == to_decimal(100.2001)

        with pytest.raises(ValueError):
            assert to_decimal('some string') == Decimal('0')


class TestNormalizeDataTest:

    def test_normalize_data(self):
        test_data = {
            'key': {
                'subkey': Decimal('0.666'),
            },
            'second_key': 'some str',
        }

        result_data = normalize_data(test_data)
        assert 'key' in test_data
        assert 'subkey' in test_data['key']
        assert result_data['key']['subkey'] == 0.666

        assert 'second_key' in test_data
        assert isinstance(test_data['second_key'], str)

        test_data = {
            'key': [
                Decimal(0),
                Decimal(1),
                {
                    'subkey': Decimal(2)
                }
            ]
        }
        result_data = normalize_data(test_data)
        assert result_data['key'][2]['subkey'] == 2.0
