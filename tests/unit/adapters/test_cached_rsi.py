"""Unit tests for atomic RSI cache persistence and signal provider."""

from decimal import Decimal
from pathlib import Path

from trading_bot.adapters.indicators.cached_rsi import (
    CachedRsiSignalProvider,
    save_rsi_cache,
)


def test_save_and_read_rsi_cache(tmp_path: Path) -> None:
    """Verify save_rsi_cache atomically creates valid JSON readable by provider."""
    cache_file = tmp_path / "rsi_cache.json"
    save_rsi_cache(cache_file, rsi=Decimal("29.86"), timestamp=1000.0)

    provider = CachedRsiSignalProvider(cache_file, max_age_seconds=120)
    result = provider.get_latest_rsi(now=1050.0)

    assert result is not None
    rsi_val, ts = result
    assert rsi_val == Decimal("29.86")
    assert ts == 1000.0


def test_cached_rsi_missing_file(tmp_path: Path) -> None:
    """Verify provider returns None if cache file does not exist."""
    cache_file = tmp_path / "nonexistent.json"
    provider = CachedRsiSignalProvider(cache_file)
    assert provider.get_latest_rsi() is None


def test_cached_rsi_expired(tmp_path: Path) -> None:
    """Verify provider returns None when cache exceeds max_age_seconds."""
    cache_file = tmp_path / "rsi_cache.json"
    save_rsi_cache(cache_file, rsi=Decimal("50.00"), timestamp=1000.0)

    provider = CachedRsiSignalProvider(cache_file, max_age_seconds=60)
    assert provider.get_latest_rsi(now=1061.0) is None


def test_cached_rsi_future_timestamp(tmp_path: Path) -> None:
    """Verify provider returns None when timestamp is in the future."""
    cache_file = tmp_path / "rsi_cache.json"
    save_rsi_cache(cache_file, rsi=Decimal("50.00"), timestamp=2000.0)

    provider = CachedRsiSignalProvider(cache_file, max_age_seconds=60)
    assert provider.get_latest_rsi(now=1000.0) is None


def test_cached_rsi_out_of_bounds(tmp_path: Path) -> None:
    """Verify provider returns None when RSI is invalid or out of [0, 100]."""
    cache_file = tmp_path / "rsi_cache.json"
    cache_file.write_text('{"rsi": "105.0", "timestamp": 1000.0}', encoding="utf-8")

    provider = CachedRsiSignalProvider(cache_file)
    assert provider.get_latest_rsi(now=1010.0) is None


def test_cached_rsi_corrupted_json(tmp_path: Path) -> None:
    """Verify provider handles corrupted JSON gracefully."""
    cache_file = tmp_path / "rsi_cache.json"
    cache_file.write_text('{broken json', encoding="utf-8")

    provider = CachedRsiSignalProvider(cache_file)
    assert provider.get_latest_rsi(now=1010.0) is None
