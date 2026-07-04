import sys
import os
import json
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.normalizer import TransactionNormalizer
from core.repository import InMemoryTransactionRepository, InMemoryErrorRepository


class TestNormalizerIntegration(unittest.TestCase):
    def setUp(self):
        sample_path = os.path.join(os.path.dirname(__file__), "..", "sample_data", "transactions.json")
        with open(sample_path, encoding="utf-8") as f:
            self.raw_records = json.load(f)
        self.normalizer = TransactionNormalizer()

    def test_batch_produces_expected_valid_invalid_split(self):
        valid, errors, metrics = self.normalizer.process_batch(self.raw_records)
        self.assertEqual(metrics.total_processed, len(self.raw_records))
        self.assertEqual(len(valid), metrics.total_valid)
        self.assertEqual(len(errors.errors), metrics.total_invalid)
        self.assertEqual(metrics.total_valid + metrics.total_invalid, metrics.total_processed)

    def test_all_three_variants_represented_in_valid_output(self):
        valid, _, _ = self.normalizer.process_batch(self.raw_records)
        sources = {tx.source for tx in valid}
        self.assertEqual(sources, {"variant_1", "variant_2", "variant_3"})

    def test_no_negative_amounts_in_valid_output(self):
        valid, _, _ = self.normalizer.process_batch(self.raw_records)
        for tx in valid:
            self.assertGreaterEqual(tx.amount, 0)

    def test_unknown_variant_is_captured_as_error_not_raised(self):
        raw = [{"foo": "bar", "baz": 123}]
        valid, errors, metrics = self.normalizer.process_batch(raw)
        self.assertEqual(len(valid), 0)
        self.assertEqual(metrics.total_invalid, 1)
        self.assertEqual(errors.errors[0].source, "unknown")

    def test_repository_persists_and_filters(self):
        valid, errors, metrics = self.normalizer.process_batch(self.raw_records)
        tx_repo = InMemoryTransactionRepository()
        err_repo = InMemoryErrorRepository()
        tx_repo.save_many(valid)
        err_repo.save_many(errors.errors)

        self.assertEqual(len(tx_repo.list()), len(valid))
        success_only = tx_repo.list({"status": "SUCCESS"})
        self.assertTrue(all(tx.status == "SUCCESS" for tx in success_only))
        self.assertEqual(len(err_repo.list()), len(errors.errors))


if __name__ == "__main__":
    unittest.main()
