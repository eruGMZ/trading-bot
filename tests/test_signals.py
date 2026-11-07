import json
import tempfile
import unittest
from pathlib import Path

from signals import read_cached_rsi


class ReadCachedRsiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_file = Path(self.temp_dir.name) / "rsi_cache.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_cache(self, data):
        self.cache_file.write_text(json.dumps(data), encoding="utf-8")

    def read_rsi(self, now=1_000, max_age_seconds=120):
        return read_cached_rsi(
            cache_file=self.cache_file,
            max_age_seconds=max_age_seconds,
            now=now,
        )

    def test_returns_recent_rsi(self):
        self.write_cache({"rsi": 29.86, "timestamp": 950})

        self.assertEqual(self.read_rsi(), 29.86)

    def test_accepts_rsi_range_boundaries(self):
        for value in (0, 100):
            with self.subTest(value=value):
                self.write_cache({"rsi": value, "timestamp": 1_000})
                self.assertEqual(self.read_rsi(), float(value))

    def test_accepts_cache_at_maximum_age(self):
        self.write_cache({"rsi": 50, "timestamp": 880})

        self.assertEqual(self.read_rsi(), 50.0)

    def test_returns_none_for_missing_file(self):
        self.assertIsNone(self.read_rsi())

    def test_returns_none_for_expired_cache(self):
        self.write_cache({"rsi": 50, "timestamp": 879})

        self.assertIsNone(self.read_rsi())

    def test_returns_none_for_future_timestamp(self):
        self.write_cache({"rsi": 50, "timestamp": 1_001})

        self.assertIsNone(self.read_rsi())

    def test_returns_none_for_malformed_json(self):
        self.cache_file.write_text("{invalid", encoding="utf-8")

        self.assertIsNone(self.read_rsi())

    def test_returns_none_for_invalid_rsi_or_timestamp(self):
        invalid_entries = (
            {"timestamp": 1_000},
            {"rsi": 50},
            {"rsi": -0.1, "timestamp": 1_000},
            {"rsi": 100.1, "timestamp": 1_000},
            {"rsi": "50", "timestamp": 1_000},
            {"rsi": True, "timestamp": 1_000},
            {"rsi": float("nan"), "timestamp": 1_000},
            {"rsi": 50, "timestamp": float("inf")},
        )

        for entry in invalid_entries:
            with self.subTest(entry=entry):
                self.write_cache(entry)
                self.assertIsNone(self.read_rsi())


if __name__ == "__main__":
    unittest.main()