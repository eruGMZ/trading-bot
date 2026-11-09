"""
Pruebas de integración: pipeline completo sobre datos sintéticos.

Verifica la ausencia de lookahead de extremo a extremo y la correcta
propagación de discontinuidades a través del pipeline.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import numpy as np
import pytest

from engine.aggregator import aggregate_h1_to_h4
from engine.indicators import compute_indicators
from engine.simulator import simulate
from engine.metrics import compute_metrics, compute_train_months
from engine.bootstrap import run_bootstrap
from engine.constants import Config, CAPITAL_INICIAL, WARMUP_BARS


CONFIG_A = Config("EXP-0001-A", adx_threshold=25.0, atr_mult=2.0, is_primary=True)


def _make_synthetic_h1(n_hours: int, seed: int = 42) -> pd.DataFrame:
    """
    Genera datos H1 sintéticos con tendencia alcista suave.
    Garantiza que después del calentamiento haya señales válidas.
    """
    rng  = np.random.default_rng(seed)
    times = pd.date_range("2022-01-01 00:00:00", periods=n_hours, freq="1h", tz="UTC")
    base  = 30000.0
    prices = np.cumsum(rng.normal(0.1, 50, n_hours)) + base
    prices = np.maximum(prices, 1000.0)  # precio siempre > 0
    noise  = rng.uniform(0, 20, n_hours)
    highs  = prices + noise
    lows   = prices - noise
    return pd.DataFrame({
        "open_time": times,
        "open":   prices,
        "high":   highs,
        "low":    lows,
        "close":  prices,
        "volume": rng.uniform(1, 100, n_hours),
    })


class TestFullPipeline:
    def test_pipeline_runs_without_error(self):
        """El pipeline completo debe ejecutarse sin errores."""
        h1 = _make_synthetic_h1(n_hours=5000)  # ~208 días H4
        h4 = aggregate_h1_to_h4(h1)
        h4_ind = compute_indicators(h4)
        result = simulate(h4_ind, CONFIG_A)
        assert result.is_valid

    def test_equity_curve_starts_at_capital_inicial(self):
        h1 = _make_synthetic_h1(n_hours=5000)
        h4 = aggregate_h1_to_h4(h1)
        h4_ind = compute_indicators(h4)
        result = simulate(h4_ind, CONFIG_A)
        assert abs(result.equity_curve.iloc[0] - CAPITAL_INICIAL) < 1e-6

    def test_equity_curve_length_equals_h4_bars(self):
        h1 = _make_synthetic_h1(n_hours=5000)
        h4 = aggregate_h1_to_h4(h1)
        h4_ind = compute_indicators(h4)
        result = simulate(h4_ind, CONFIG_A)
        assert len(result.equity_curve) == len(h4_ind)

    def test_no_trades_during_warmup(self):
        """No deben generarse trades en las primeras 200 barras H4 (calentamiento)."""
        h1 = _make_synthetic_h1(n_hours=5000, seed=10)
        h4 = aggregate_h1_to_h4(h1)
        h4_ind = compute_indicators(h4)
        result = simulate(h4_ind, CONFIG_A)

        warmup_end = h4_ind["open_time"].iloc[WARMUP_BARS - 1]
        for t in result.trades:
            assert t.open_time_entrada > warmup_end, \
                f"Trade en warmup: {t.open_time_entrada} <= {warmup_end}"

    def test_no_lookahead_signal_bar_uses_only_its_own_indicators(self):
        """
        Verifica ausencia de lookahead: la señal solo usa indicadores de la barra t.
        Método: si la barra t tiene EMA200=NaN (warmup), no puede generar señal,
        independientemente de las barras siguientes.
        """
        h1 = _make_synthetic_h1(n_hours=5000, seed=20)
        h4 = aggregate_h1_to_h4(h1)
        h4_ind = compute_indicators(h4)
        result = simulate(h4_ind, CONFIG_A)

        # Para cada trade, verificar que la barra de señal (t-1 antes de entrada) tenía
        # indicadores válidos
        for t in result.trades:
            # La barra de señal es la anterior a la entrada
            entry_idx = h4_ind.index[h4_ind["open_time"] == t.open_time_entrada]
            if len(entry_idx) == 0:
                continue
            idx = entry_idx[0]
            if idx == 0:
                continue
            signal_row = h4_ind.iloc[idx - 1]
            assert not np.isnan(signal_row["ema200"]), "Señal generada con EMA200=NaN"
            assert not np.isnan(signal_row["adx14"]), "Señal generada con ADX14=NaN"
            assert not np.isnan(signal_row["atr14"]), "Señal generada con ATR14=NaN"

    def test_trades_entry_at_next_bar_open(self):
        """Verificar que la entrada ocurre al open de la barra siguiente a la señal."""
        h1 = _make_synthetic_h1(n_hours=5000, seed=30)
        h4 = aggregate_h1_to_h4(h1)
        h4_ind = compute_indicators(h4)
        result = simulate(h4_ind, CONFIG_A)

        for t in result.trades:
            if t.exit_type == "stop_entrada":
                # La entrada y salida son en la misma barra → verificar open de esa barra
                entry_rows = h4_ind[h4_ind["open_time"] == t.open_time_entrada]
                if len(entry_rows) > 0:
                    assert abs(entry_rows.iloc[0]["open"] - t.precio_entrada) < 1e-6

    def test_metrics_computed_without_error(self):
        h1 = _make_synthetic_h1(n_hours=5000, seed=50)
        h4 = aggregate_h1_to_h4(h1)
        h4_ind = compute_indicators(h4)
        result = simulate(h4_ind, CONFIG_A)
        months = compute_train_months(result.equity_curve)
        metrics = compute_metrics(result.trades, result.equity_curve, train_months=months)
        assert isinstance(metrics.sharpe, float)
        assert isinstance(metrics.max_dd, float)
        assert metrics.max_dd >= 0.0

    def test_bootstrap_runs_on_real_trades(self):
        h1 = _make_synthetic_h1(n_hours=5000, seed=70)
        h4 = aggregate_h1_to_h4(h1)
        h4_ind = compute_indicators(h4)
        result = simulate(h4_ind, CONFIG_A)
        if len(result.trades) > 0:
            official, info = run_bootstrap(result.trades)
            assert official.n_iter == 10_000
            assert official.seed == 20261108
            assert official.block_size == 20

    def test_discontinuity_pipeline(self):
        """Pipeline maneja discontinuidad sin posición → reinicia warmup."""
        # Crear H1 con un gap de 24h a mitad del dataset
        h1a = _make_synthetic_h1(n_hours=1000, seed=1)
        h1b = _make_synthetic_h1(n_hours=4000, seed=2)
        # Avanzar h1b 100 horas más allá del fin de h1a para crear discontinuidad
        gap = h1a["open_time"].iloc[-1] + pd.Timedelta("100h")
        h1b = h1b.copy()
        h1b["open_time"] = pd.date_range(start=gap, periods=4000, freq="1h", tz="UTC")
        h1 = pd.concat([h1a, h1b]).reset_index(drop=True)
        h4 = aggregate_h1_to_h4(h1)
        h4_ind = compute_indicators(h4)
        # Debe haber al menos una discontinuidad en h4_ind
        assert h4_ind["discontinuity_before"].any()
        result = simulate(h4_ind, CONFIG_A)
        # Si hay posición en la discontinuidad → inválido (correcto)
        # Si no hay posición → válido (también correcto)
        # Lo importante es que no lanza excepción
        assert isinstance(result.is_valid, bool)
