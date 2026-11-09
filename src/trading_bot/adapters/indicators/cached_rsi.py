"""Atomic RSI cache file writer and reader implementing SignalProviderPort."""

import json
import logging
import os
import tempfile
import time
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from trading_bot.domain.signals import validate_rsi
from trading_bot.ports.signal_provider import SignalProviderPort

log = logging.getLogger(__name__)


class RsiCachePayload(BaseModel):
    """Pydantic boundary model for the rsi_cache.json file."""

    model_config = ConfigDict(extra="ignore")

    rsi: Decimal
    timestamp: float


def save_rsi_cache(
    cache_file: Path,
    rsi: Decimal,
    timestamp: float | None = None,
) -> None:
    """Atomically write RSI value to JSON cache file using tempfile + os.replace.

    Prevents race conditions where consumers read 0-byte truncated files.
    """
    ts = time.time() if timestamp is None else timestamp
    payload = {"rsi": str(rsi), "timestamp": ts}
    parent = cache_file.parent
    parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=str(parent), prefix=".rsi-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, cache_file)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


class CachedRsiSignalProvider(SignalProviderPort):
    """Signal provider reading validated RSI values from atomic JSON cache."""

    def __init__(self, cache_file: Path, max_age_seconds: int = 120) -> None:
        self._cache_file = cache_file
        self._max_age = max_age_seconds

    def get_latest_rsi(self, now: float | None = None) -> tuple[Decimal, float] | None:
        """Read and validate the latest RSI from cache.

        Returns:
            (rsi_decimal, timestamp) tuple, or None if expired, corrupt, or invalid.
        """
        if not self._cache_file.is_file():
            return None

        try:
            content = self._cache_file.read_text(encoding="utf-8")
            raw = json.loads(content)
            payload = RsiCachePayload.model_validate(raw)
        except Exception:
            return None

        current_time = time.time() if now is None else now
        age = current_time - payload.timestamp
        if age < 0 or age > self._max_age:
            return None

        validated_val = validate_rsi(payload.rsi)
        if validated_val is None:
            return None

        return validated_val, payload.timestamp
