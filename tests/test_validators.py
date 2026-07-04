import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.exceptions import TransactionValidationError
from core.validators import TransactionValidator


class TestTransactionValidator(unittest.TestCase):
    def setUp(self):
        self.validator = TransactionValidator()
        self.base = {
            "id": "tx1",
            "amount": 10.0,
            "currency": "USD",
            "timestamp": "2025-03-10T14:22:00Z",
            "status": "SUCCESS",
            "source": "variant_1",
        }

    def test_valid_transaction_passes(self):
        self.validator.validate(self.base, "variant_1")  # no exception

    def test_negative_amount_fails(self):
        tx = dict(self.base, amount=-5.0)
        with self.assertRaises(TransactionValidationError):
            self.validator.validate(tx, "variant_1")

    def test_missing_field_fails(self):
        tx = dict(self.base)
        del tx["currency"]
        with self.assertRaises(TransactionValidationError):
            self.validator.validate(tx, "variant_1")

    def test_bad_timestamp_fails(self):
        tx = dict(self.base, timestamp="not-a-date")
        with self.assertRaises(TransactionValidationError):
            self.validator.validate(tx, "variant_1")

    def test_bad_status_fails(self):
        tx = dict(self.base, status="WEIRD")
        with self.assertRaises(TransactionValidationError):
            self.validator.validate(tx, "variant_1")

    def test_non_numeric_amount_fails(self):
        tx = dict(self.base, amount="10.0")
        with self.assertRaises(TransactionValidationError):
            self.validator.validate(tx, "variant_1")


if __name__ == "__main__":
    unittest.main()
