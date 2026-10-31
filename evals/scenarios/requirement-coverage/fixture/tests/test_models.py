import unittest

from billing.models import Customer


class CustomerTest(unittest.TestCase):
    def test_name_prefers_trade_name(self):
        self.assertEqual(Customer(1, "Northwind Holdings SL", "Northwind").name, "Northwind")
