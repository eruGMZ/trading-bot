"""Pruebas de cálculo de métricas (§5)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import numpy as np
import pytest
from engine.metrics import compute_metrics, compute_train_months
from engine.simulator import Trade
from engine.constants import SQRT_H4_PER_YEAR


def _make_trade(pnl_neto: float, entry_time: pd.Timestamp = None,
                capital: float = 150.0) -> Trade:
    t0 = entry_time or pd.Timestamp("2023-06-01", tz="UTC")
    return Trade(
        open_time_entrada=t0, open_time_salida=t0 + pd.Timedelta("4h"),
        precio_entrada=100.0, precio_salida=100.0 + pnl_neto,
        exit_type="stop_normal",
        stop_inicial=90.0, stop_salida=90.0,
        tamano_btc=1.0,
        pnl_bruto_usdt=pnl_neto + 0.3, costo_usdt=0.3,
        pnl_neto_usdt=pnl_neto,
        equity_pre_usdt=capital, equity_post_usdt=capital + pnl_neto,
        config_name="EXP-0001-A",
    )


def _make_equity(values: list, start: str = "2023-06-01") -> pd.Series:
    times = pd.date_range(start=start, periods=len(values), freq="4h", tz="UTC")
    return pd.Series(values, index=times, name="equity")


class TestSharpe:
    def test_zero_returns_give_zero_sharpe(self):
        eq     = _make_equity([150.0] * 50)
        result = compute_metrics([], eq, train_months=1.0)
        assert result.sharpe == 0.0

    def test_sharpe_formula(self):
        # Retorno constante → Sharpe bien definido
        eq = _make_equity([150.0 * (1.001 ** i) for i in range(100)])
        result = compute_metrics([], eq, train_months=1.0)
        rets = np.diff(eq.values) / eq.values[:-1]
        mu   = rets.mean()
        sig  = rets.std(ddof=1)
        expected = mu / sig * SQRT_H4_PER_YEAR
        assert abs(result.sharpe - expected) < 1e-9

    def test_negative_sharpe_possible(self):
        eq = _make_equity([150.0 * (0.999 ** i) for i in range(100)])
        result = compute_metrics([], eq, train_months=1.0)
        assert result.sharpe < 0


class TestMaxDD:
    def test_no_drawdown(self):
        eq     = _make_equity([150.0 + i for i in range(10)])
        result = compute_metrics([], eq, capital_inicial=150.0, train_months=1.0)
        assert result.max_dd == 0.0

    def test_dd_uses_capital_inicial_denominator(self):
        # Pico = 160, caída a 140 → DD = (160-140)/150 = 0.1333
        eq     = _make_equity([150, 155, 160, 150, 140, 145])
        result = compute_metrics([], eq, capital_inicial=150.0, train_months=1.0)
        expected = (160.0 - 140.0) / 150.0
        assert abs(result.max_dd - expected) < 1e-9

    def test_dd_starts_from_initial_capital(self):
        # Si equity cae de 150 a 130 → DD = 20/150
        eq     = _make_equity([150, 145, 140, 135, 130])
        result = compute_metrics([], eq, capital_inicial=150.0, train_months=1.0)
        assert abs(result.max_dd - 20.0 / 150.0) < 1e-9


class TestProfitFactor:
    def test_no_trades(self):
        eq     = _make_equity([150.0] * 5)
        result = compute_metrics([], eq, train_months=1.0)
        assert result.profit_factor == 0.0

    def test_all_wins(self):
        trades = [_make_trade(5.0), _make_trade(3.0)]
        eq     = _make_equity([150, 155, 158])
        result = compute_metrics(trades, eq, train_months=1.0)
        assert result.profit_factor == float("inf")

    def test_pf_calculation(self):
        trades = [_make_trade(10.0), _make_trade(10.0), _make_trade(-5.0)]
        eq     = _make_equity([150, 160, 170, 165])
        result = compute_metrics(trades, eq, train_months=1.0)
        assert abs(result.profit_factor - 20.0 / 5.0) < 1e-9


class TestExpectancy:
    def test_expectancy_mean_of_pnls(self):
        trades = [_make_trade(10.0), _make_trade(-4.0), _make_trade(2.0)]
        eq     = _make_equity([150, 160, 156, 158])
        result = compute_metrics(trades, eq, train_months=1.0)
        expected = (10 - 4 + 2) / 3.0
        assert abs(result.expectancy - expected) < 1e-9


class TestOpsPerMonth:
    def test_ops_per_month(self):
        trades = [_make_trade(1.0)] * 6
        eq     = _make_equity([150.0] * 7)
        result = compute_metrics(trades, eq, train_months=2.0)
        assert abs(result.ops_per_month - 3.0) < 1e-9
