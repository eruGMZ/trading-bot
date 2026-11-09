"""Pruebas de EMA200, ATR14 y ADX14."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import numpy as np
import pytest
from engine.indicators import compute_indicators
from engine.constants import EMA_PERIOD, ATR_PERIOD, ADX_PERIOD


def _make_h4(n: int, close: float = 100.0, discontinuity_at: int = None) -> pd.DataFrame:
    times  = pd.date_range("2022-01-01", periods=n, freq="4h", tz="UTC")
    closes = np.full(n, close)
    # Ligeras variaciones para que ATR > 0
    highs  = closes + 1.0
    lows   = closes - 1.0
    disc   = [False] * n
    if discontinuity_at is not None:
        disc[discontinuity_at] = True
    return pd.DataFrame({
        "open_time": times,
        "open":  closes,
        "high":  highs,
        "low":   lows,
        "close": closes,
        "volume": np.ones(n),
        "discontinuity_before": disc,
    })


class TestEMA200:
    def test_nan_before_warmup(self):
        df = _make_h4(199)
        out = compute_indicators(df)
        assert out["ema200"].isna().all()

    def test_valid_at_warmup_bar(self):
        # Con cierre constante 100, EMA200 inicializa en 100.0
        df  = _make_h4(200)
        out = compute_indicators(df)
        assert not np.isnan(out["ema200"].iloc[-1])
        assert abs(out["ema200"].iloc[-1] - 100.0) < 1e-9

    def test_ema_initialization_matches_sma(self):
        # Cierre variable: primera EMA debe ser la SMA de las primeras 200 barras
        rng    = np.random.default_rng(42)
        closes = rng.uniform(90, 110, 220)
        times  = pd.date_range("2022-01-01", periods=220, freq="4h", tz="UTC")
        df     = pd.DataFrame({
            "open_time": times,
            "open":  closes, "high": closes + 1, "low": closes - 1, "close": closes,
            "volume": np.ones(220), "discontinuity_before": [False] * 220,
        })
        out     = compute_indicators(df)
        sma200  = closes[:200].mean()
        ema_200 = out["ema200"].iloc[199]
        assert abs(ema_200 - sma200) < 1e-9

    def test_ema_updates_correctly(self):
        rng    = np.random.default_rng(7)
        closes = rng.uniform(90, 110, 202)
        times  = pd.date_range("2022-01-01", periods=202, freq="4h", tz="UTC")
        df     = pd.DataFrame({
            "open_time": times,
            "open": closes, "high": closes + 1, "low": closes - 1, "close": closes,
            "volume": np.ones(202), "discontinuity_before": [False] * 202,
        })
        out  = compute_indicators(df)
        alpha = 2.0 / 201
        sma   = closes[:200].mean()
        ema_200 = sma
        ema_201 = ema_200 * (1 - alpha) + closes[200] * alpha
        ema_202 = ema_201 * (1 - alpha) + closes[201] * alpha
        assert abs(out["ema200"].iloc[200] - ema_201) < 1e-9
        assert abs(out["ema200"].iloc[201] - ema_202) < 1e-9

    def test_reset_after_discontinuity(self):
        df = _make_h4(300, discontinuity_at=250)
        out = compute_indicators(df)
        # Justo antes de discontinuidad: EMA válida
        assert not np.isnan(out["ema200"].iloc[249])
        # Justo después del reinicio: NaN (menos de 200 barras)
        assert np.isnan(out["ema200"].iloc[250])
        assert np.isnan(out["ema200"].iloc[299])


class TestATR14:
    def test_nan_before_14_bars(self):
        df  = _make_h4(14)
        out = compute_indicators(df)
        # Primera fila válida: bar índice 14 (15ª barra, primero con 14 TRs)
        assert out["atr14"].iloc[:14].isna().all()

    def test_atr_initialization(self):
        # Con close constante 100, high=101, low=99 → TR=2 siempre
        df  = _make_h4(16)
        out = compute_indicators(df)
        # ATR14 en barra 14 = media de primeros 14 TR = 2.0
        assert abs(out["atr14"].iloc[14] - 2.0) < 1e-9

    def test_atr_reset_after_discontinuity(self):
        df  = _make_h4(50, discontinuity_at=30)
        out = compute_indicators(df)
        assert not np.isnan(out["atr14"].iloc[25])
        assert np.isnan(out["atr14"].iloc[30])


class TestADX14:
    def test_adx_needs_at_least_28_bars(self):
        # Con barras suficientes, ADX debe ser válido a partir de barra 27
        df  = _make_h4(60)
        out = compute_indicators(df)
        # Barras 0-26 no tienen ADX; barra 27 en adelante tiene ADX
        # (bar 1 = primer TR, bar 14 = primer smooth, bar 27 = primer ADX)
        assert out["adx14"].iloc[:27].isna().all()
        assert not np.isnan(out["adx14"].iloc[27])

    def test_adx_range(self):
        # ADX debe estar en [0, 100]
        rng    = np.random.default_rng(99)
        closes = rng.uniform(90, 110, 100)
        times  = pd.date_range("2022-01-01", periods=100, freq="4h", tz="UTC")
        df     = pd.DataFrame({
            "open_time": times,
            "open": closes, "high": closes + rng.uniform(0.5, 2, 100),
            "low": closes - rng.uniform(0.5, 2, 100), "close": closes,
            "volume": np.ones(100), "discontinuity_before": [False] * 100,
        })
        out = compute_indicators(df)
        valid = out["adx14"].dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()
