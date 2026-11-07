"""Lectura y validación de señales RSI desde el caché local."""

import json
import math
import time

from config import CACHE_FILE, CACHE_MAX_AGE_SECONDS


def read_cached_rsi(
    cache_file=CACHE_FILE,
    max_age_seconds=CACHE_MAX_AGE_SECONDS,
    now=None,
):
    """Devuelve un RSI válido y reciente, o ``None`` si no está disponible."""
    try:
        with open(cache_file, encoding="utf-8") as cache:
            data = json.load(cache)

        if not isinstance(data, dict):
            return None

        rsi = data.get("rsi")
        timestamp = data.get("timestamp")
        if (
            isinstance(rsi, bool)
            or not isinstance(rsi, (int, float))
            or isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
        ):
            return None

        rsi = float(rsi)
        timestamp = float(timestamp)
        current_time = time.time() if now is None else float(now)
        if not all(math.isfinite(value) for value in (rsi, timestamp, current_time)):
            return None
        if not 0 <= rsi <= 100:
            return None

        age_seconds = current_time - timestamp
        if age_seconds < 0 or age_seconds > max_age_seconds:
            return None

        return rsi
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None