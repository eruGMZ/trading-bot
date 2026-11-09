"""
Cálculo de métricas para EXP-0001 (§5).

Sharpe:     (μ_H4 / σ_H4) × √2190, retornos mark-to-market H4, rfr=0, std muestral.
DD:         mark-to-market H4, denominador = capital_inicial (§5.2).
PF:         sum(pnl_neto > 0) / |sum(pnl_neto < 0)|.
Expectancy: media de pnl_neto sobre ops cerradas.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List
from .constants import SQRT_H4_PER_YEAR, CAPITAL_INICIAL
from .simulator import Trade


@dataclass
class Metrics:
    n_trades:    int
    sharpe:      float
    max_dd:      float          # fracción, e.g. 0.07 = 7%
    profit_factor: float
    expectancy:  float          # USDT por operación
    ops_per_month: float
    total_return: float         # fracción


def compute_metrics(
    trades: List[Trade],
    equity_curve: pd.Series,
    capital_inicial: float = CAPITAL_INICIAL,
    train_months: float = None,
) -> Metrics:
    """
    Calcula todas las métricas de Train.

    equity_curve: pd.Series indexado por open_time, valores en USDT (mark-to-market H4).
    train_months: duración del Train en meses calendario (para ops/mes).
    """
    eq = equity_curve.values.astype(float)

    # Sharpe sobre retornos H4
    if len(eq) < 2:
        sharpe = 0.0
    else:
        rets = np.diff(eq) / eq[:-1]
        mu   = rets.mean()
        sig  = rets.std(ddof=1) if len(rets) > 1 else 0.0
        sharpe = (mu / sig * SQRT_H4_PER_YEAR) if sig > 0 else 0.0

    # Max Drawdown mark-to-market (§5.2)
    peak = np.maximum.accumulate(eq)
    dd_series = (peak - eq) / capital_inicial
    max_dd = float(dd_series.max()) if len(dd_series) > 0 else 0.0

    # Métricas sobre trades
    n_trades = len(trades)
    pnls = [t.pnl_neto_usdt for t in trades]

    if n_trades == 0:
        pf         = 0.0
        expectancy = 0.0
    else:
        wins  = sum(p for p in pnls if p > 0)
        losses= abs(sum(p for p in pnls if p < 0))
        pf    = wins / losses if losses > 0 else float("inf")
        expectancy = sum(pnls) / n_trades

    # Total return
    total_return = (eq[-1] - capital_inicial) / capital_inicial if len(eq) > 0 else 0.0

    # Ops/mes
    if train_months is None or train_months <= 0:
        ops_per_month = float("nan")
    else:
        ops_per_month = n_trades / train_months

    return Metrics(
        n_trades=n_trades,
        sharpe=sharpe,
        max_dd=max_dd,
        profit_factor=pf,
        expectancy=expectancy,
        ops_per_month=ops_per_month,
        total_return=total_return,
    )


def compute_train_months(equity_curve: pd.Series) -> float:
    """Duración del Train en meses calendario a partir de la curva de equity."""
    if len(equity_curve) < 2:
        return 0.0
    delta = equity_curve.index[-1] - equity_curve.index[0]
    return delta.total_seconds() / (30.4375 * 24 * 3600)
