import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.exceptions import (
    AmountConversionError,
    CurrencyNormalizationError,
    DateParsingError,
    FieldMappingError,
    StatusMappingError,
)
from core.schema import SourceVariant
from core.transformers import TransformerFactory


class TestVariant1Transformer(unittest.TestCase):
    def setUp(self):
        self.transformer = TransformerFactory.create(SourceVariant.VARIANT_1)

    def test_happy_path(self):
        raw = {
            "id": "tx_001",
            "amount": "100.50",
            "currency": "USD",
            "timestamp": "2025-03-10 14:22:00",
            "status": "completed",
        }
        result = self.transformer.transform(raw)
        self.assertEqual(result["id"], "tx_001")
        self.assertEqual(result["amount"], 100.50)
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["timestamp"], "2025-03-10T14:22:00Z")
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["source"], "variant_1")

    def test_invalid_amount_raises(self):
        raw = {"id": "tx_x", "amount": "abc", "currency": "USD", "timestamp": "2025-03-10 14:22:00", "status": "completed"}
        with self.assertRaises(AmountConversionError):
            self.transformer.transform(raw)

    def test_missing_id_raises(self):
        raw = {"amount": "10.0", "currency": "USD", "timestamp": "2025-03-10 14:22:00", "status": "completed"}
        with self.assertRaises(FieldMappingError):
            self.transformer.transform(raw)

    def test_bad_date_format_raises(self):
        raw = {"id": "tx_x", "amount": "10.0", "currency": "USD", "timestamp": "10-03-2025", "status": "completed"}
        with self.assertRaises(DateParsingError):
            self.transformer.transform(raw)

    def test_unknown_status_raises(self):
        raw = {"id": "tx_x", "amount": "10.0", "currency": "USD", "timestamp": "2025-03-10 14:22:00", "status": "weird"}
        with self.assertRaises(StatusMappingError):
            self.transformer.transform(raw)


class TestVariant2Transformer(unittest.TestCase):
    def setUp(self):
        self.transformer = TransformerFactory.create(SourceVariant.VARIANT_2)

    def test_happy_path_cents_conversion(self):
        raw = {
            "transaction_id": 204,
            "total": 10050,
            "currency_code": "usd",
            "created_at": "10/03/2025 14:22",
            "state": "OK",
        }
        result = self.transformer.transform(raw)
        self.assertEqual(result["id"], "204")
        self.assertEqual(result["amount"], 100.50)
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["timestamp"], "2025-03-10T14:22:00Z")
        self.assertEqual(result["status"], "SUCCESS")

    def test_unknown_currency_raises(self):
        raw = {"transaction_id": 1, "total": 100, "currency_code": "xxx", "created_at": "10/03/2025 14:22", "state": "OK"}
        with self.assertRaises(CurrencyNormalizationError):
            self.transformer.transform(raw)

    def test_bad_date_raises(self):
        raw = {"transaction_id": 1, "total": 100, "currency_code": "usd", "created_at": "2025-03-10", "state": "OK"}
        with self.assertRaises(DateParsingError):
            self.transformer.transform(raw)


class TestVariant3Transformer(unittest.TestCase):
    def setUp(self):
        self.transformer = TransformerFactory.create(SourceVariant.VARIANT_3)

    def test_happy_path_symbol_comma(self):
        raw = {"ref": "A-77", "amount": "\u20ac99,99", "date": "2025-03-10T14:22:00Z", "result": "success"}
        result = self.transformer.transform(raw)
        self.assertEqual(result["id"], "A-77")
        self.assertEqual(result["amount"], 99.99)
        self.assertEqual(result["currency"], "EUR")
        self.assertEqual(result["timestamp"], "2025-03-10T14:22:00Z")
        self.assertEqual(result["status"], "SUCCESS")

    def test_gbp_symbol(self):
        raw = {"ref": "A-78", "amount": "\u00a375,50", "date": "2025-03-11T10:00:00Z", "result": "pending"}
        result = self.transformer.transform(raw)
        self.assertEqual(result["currency"], "GBP")
        self.assertEqual(result["amount"], 75.50)

    def test_invalid_date_raises(self):
        raw = {"ref": "A-79", "amount": "\u20ac10,00", "date": "not-a-date", "result": "success"}
        with self.assertRaises(DateParsingError):
            self.transformer.transform(raw)


if __name__ == "__main__":
    unittest.main()
