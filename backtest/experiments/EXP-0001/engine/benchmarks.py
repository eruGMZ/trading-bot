"""
Benchmarks para EXP-0001 (§7).

§7.1  Buy & Hold pasivo: equity_BH[t] = 150 × close[t] / close[t0]
§7.2  USDT sin invertir: 150.00 USDT constante
§7.3  Buy & Hold escalado por exposición:
        fraccion_expuesta = barras_en_posicion / total_barras_train
        retorno_bh_total  = close[-1] / close[0] − 1
        equity_escal      = 150 × (1 + fraccion_expuesta × retorno_bh_total)
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List
from .constants import CAPITAL_INICIAL
from .simulator import Trade


@dataclass
class BenchmarkResults:
    bh_equity_final:      float    # §7.1
    usdt_equity_final:    float    # §7.2
    bh_scaled_equity:     float    # §7.3
    bh_total_return:      float
    exposure_fraction:    float
    n_bars_total:         int
    n_bars_in_position:   int


def compute_benchmarks(
    h4_ind: pd.DataFrame,
    trades: List[Trade],
    equity_curve: pd.Series,
    capital_inicial: float = CAPITAL_INICIAL,
    warmup_bars: int = 200,
) -> BenchmarkResults:
    """
    h4_ind: DataFrame H4 con indicadores. Los primeros warmup_bars no generan trades.
    trades: lista de operaciones cerradas de la simulación.
    equity_curve: curva de equity (mismo índice que h4_ind).
    """
    # Período de Train efectivo (tras calentamiento)
    train_df = h4_ind.iloc[warmup_bars:].reset_index(drop=True)
    if len(train_df) == 0:
        return BenchmarkResults(
            bh_equity_final=capital_inicial,
            usdt_equity_final=capital_inicial,
            bh_scaled_equity=capital_inicial,
            bh_total_return=0.0,
            exposure_fraction=0.0,
            n_bars_total=0,
            n_bars_in_position=0,
        )

    close0  = float(train_df["close"].iloc[0])
    close_f = float(train_df["close"].iloc[-1])

    # §7.1
    bh_total_return  = close_f / close0 - 1.0
    bh_equity_final  = capital_inicial * (1.0 + bh_total_return)

    # §7.2
    usdt_equity_final = capital_inicial

    # §7.3: contar barras H4 en posición usando los trades
    n_bars_total = len(train_df)
    n_bars_pos   = _count_bars_in_position(trades, train_df["open_time"])
    exposure_frac = n_bars_pos / n_bars_total if n_bars_total > 0 else 0.0
    bh_scaled     = capital_inicial * (1.0 + exposure_frac * bh_total_return)

    return BenchmarkResults(
        bh_equity_final=bh_equity_final,
        usdt_equity_final=usdt_equity_final,
        bh_scaled_equity=bh_scaled,
        bh_total_return=bh_total_return,
        exposure_fraction=exposure_frac,
        n_bars_total=n_bars_total,
        n_bars_in_position=n_bars_pos,
    )


def _count_bars_in_position(trades: List[Trade], bar_times: pd.Series) -> int:
    """Cuenta cuántas barras H4 del Train efectivo cayeron dentro de algún trade."""
    if not trades:
        return 0
    count = 0
    for bt in bar_times:
        for t in trades:
            if t.open_time_entrada <= bt <= t.open_time_salida:
                count += 1
                break
    return count
