"""Pruebas del agregador H1 → H4."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import numpy as np
import pytest
from engine.aggregator import aggregate_h1_to_h4


def _make_h1(start: str, n_hours: int, prices: list = None) -> pd.DataFrame:
    """Genera n_hours velas H1 consecutivas desde start."""
    times = pd.date_range(start=start, periods=n_hours, freq="1h", tz="UTC")
    p = prices if prices else [100.0] * n_hours
    return pd.DataFrame({
        "open_time": times,
        "open":  p,
        "high":  [x + 1 for x in p],
        "low":   [x - 1 for x in p],
        "close": p,
        "volume": [1.0] * n_hours,
    })


class TestAggregatorBasic:
    def test_complete_blocks(self):
        h1 = _make_h1("2023-01-01 00:00:00", 24)
        h4 = aggregate_h1_to_h4(h1)
        assert len(h4) == 6  # 24h / 4h = 6 bloques

    def test_ohlc_aggregation(self):
        h1 = _make_h1("2023-01-01 00:00:00", 4)
        h1["open"]  = [100.0, 101.0, 99.0, 102.0]
        h1["high"]  = [103.0, 104.0, 100.0, 105.0]
        h1["low"]   = [98.0,  99.0,  97.0,  101.0]
        h1["close"] = [101.0, 99.0, 102.0, 103.0]
        h4 = aggregate_h1_to_h4(h1)
        assert len(h4) == 1
        row = h4.iloc[0]
        assert row["open"]  == 100.0   # primer open
        assert row["high"]  == 105.0   # máximo de los 4 high
        assert row["low"]   == 97.0    # mínimo de los 4 low
        assert row["close"] == 103.0   # último close
        assert row["volume"] == 4.0    # suma de volúmenes

    def test_incomplete_block_discarded(self):
        # 7 H1: bloque 00-03 completo (4), bloque 04-07 incompleto (3) → solo 1 H4
        h1 = _make_h1("2023-01-01 00:00:00", 7)
        h4 = aggregate_h1_to_h4(h1)
        assert len(h4) == 1
        assert h4.iloc[0]["open_time"] == pd.Timestamp("2023-01-01 00:00:00", tz="UTC")

    def test_first_bar_no_discontinuity(self):
        h1 = _make_h1("2023-01-01 00:00:00", 8)
        h4 = aggregate_h1_to_h4(h1)
        assert h4.iloc[0]["discontinuity_before"] == False

    def test_continuous_blocks_no_discontinuity(self):
        h1 = _make_h1("2023-01-01 00:00:00", 24)
        h4 = aggregate_h1_to_h4(h1)
        assert all(~h4["discontinuity_before"])

    def test_gap_detected_as_discontinuity(self):
        # Bloque 00:00 y luego salta a 12:00 (gap de 8h = 2 bloques faltantes)
        h1a = _make_h1("2023-01-01 00:00:00", 4)
        h1b = _make_h1("2023-01-01 12:00:00", 4)
        h1  = pd.concat([h1a, h1b]).reset_index(drop=True)
        h4  = aggregate_h1_to_h4(h1)
        assert len(h4) == 2
        assert h4.iloc[0]["discontinuity_before"] == False
        assert h4.iloc[1]["discontinuity_before"] == True

    def test_empty_input(self):
        empty = pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])
        h4 = aggregate_h1_to_h4(empty)
        assert len(h4) == 0

    def test_volume_sum(self):
        h1 = _make_h1("2023-01-01 00:00:00", 4)
        h1["volume"] = [1.0, 2.0, 3.0, 4.0]
        h4 = aggregate_h1_to_h4(h1)
        assert h4.iloc[0]["volume"] == 10.0
