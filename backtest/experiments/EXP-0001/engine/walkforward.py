"""
Walk-Forward con parámetros fijos para EXP-0001 (§8.1).

4 ventanas: IS 18 meses, paso 3 meses.
Cada ventana incluye 200 barras H4 de calentamiento previas al inicio del IS.
Los parámetros NO se reoptimilan entre ventanas.
Criterio de estabilidad: todas las 4 OOS con expectancy > 0.
"""
from __future__ import annotations
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional
from .constants import Config, WARMUP_BARS
from .simulator import simulate, SimulationResult
from .metrics import compute_metrics, compute_train_months


@dataclass
class WFWindow:
    window_id:     int
    is_start:      pd.Timestamp
    is_end:        pd.Timestamp
    oos_start:     pd.Timestamp
    oos_end:       pd.Timestamp
    oos_n_trades:  int
    oos_expectancy: float
    oos_result:    Optional[SimulationResult]


@dataclass
class WalkForwardResult:
    config:   Config
    windows:  List[WFWindow]
    all_oos_positive: bool    # todas las ventanas OOS con expectancy > 0
    is_valid: bool


def run_walk_forward(
    h4_ind: pd.DataFrame,
    config: Config,
    train_effective_start: pd.Timestamp,
) -> WalkForwardResult:
    """
    Ejecuta Walk-Forward con 4 ventanas (§8.1).

    h4_ind: DataFrame H4 con indicadores, cubre todo el período Train.
    train_effective_start: inicio del Train efectivo (primera barra después del calentamiento global).
    """
    IS_MONTHS  = 18
    OOS_MONTHS = 3
    N_WINDOWS  = 4

    windows: List[WFWindow] = []

    for w in range(N_WINDOWS):
        # Calcular límites de IS y OOS para esta ventana
        is_start_approx  = train_effective_start + pd.DateOffset(months=w * OOS_MONTHS)
        is_end_approx    = is_start_approx + pd.DateOffset(months=IS_MONTHS)
        oos_start_approx = is_end_approx
        oos_end_approx   = oos_start_approx + pd.DateOffset(months=OOS_MONTHS)

        # Filtrar barras OOS
        oos_mask = (h4_ind["open_time"] >= oos_start_approx) & (h4_ind["open_time"] < oos_end_approx)
        oos_df   = h4_ind[oos_mask].reset_index(drop=True)
        if len(oos_df) == 0:
            break

        # Incluir 200 barras de calentamiento antes del inicio del IS
        is_mask = h4_ind["open_time"] < oos_start_approx
        pre_df  = h4_ind[is_mask].reset_index(drop=True)

        if len(pre_df) < WARMUP_BARS:
            # No hay suficientes barras de calentamiento: ventana inválida
            break

        # Tomar las últimas WARMUP_BARS como calentamiento + todo el IS
        warmup_start_idx = max(0, len(pre_df) - WARMUP_BARS)
        wf_window_df = pd.concat([pre_df.iloc[warmup_start_idx:], oos_df]).reset_index(drop=True)

        # Simular: el calentamiento inicializa indicadores; solo OOS genera métricas
        result = simulate(wf_window_df, config)

        # Filtrar trades del OOS
        if result.is_valid:
            oos_times   = set(oos_df["open_time"].tolist())
            oos_trades  = [t for t in result.trades if t.open_time_entrada in oos_times]
            oos_pnls    = [t.pnl_neto_usdt for t in oos_trades]
            oos_expect  = sum(oos_pnls) / len(oos_pnls) if oos_pnls else 0.0
        else:
            oos_trades = []
            oos_expect = 0.0

        actual_is_start  = pre_df["open_time"].iloc[0] if len(pre_df) > 0 else is_start_approx
        actual_oos_start = oos_df["open_time"].iloc[0]
        actual_oos_end   = oos_df["open_time"].iloc[-1]

        windows.append(WFWindow(
            window_id=w + 1,
            is_start=actual_is_start,
            is_end=oos_start_approx,
            oos_start=actual_oos_start,
            oos_end=actual_oos_end,
            oos_n_trades=len(oos_trades),
            oos_expectancy=oos_expect,
            oos_result=result if result.is_valid else None,
        ))

    all_positive = (
        len(windows) == N_WINDOWS
        and all(w.oos_expectancy > 0 for w in windows)
    )

    return WalkForwardResult(
        config=config,
        windows=windows,
        all_oos_positive=all_positive,
        is_valid=len(windows) > 0,
    )
