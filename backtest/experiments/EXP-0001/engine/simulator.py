"""
Máquina de estados FLAT/LONG para EXP-0001 (§3).

Reglas clave implementadas:
- Señal en cierre de t → entrada en open[t+1] (§3.5)
- stop_inicial = open[t+1] − atr_mult × ATR14[t] (§3.4)
- Stop vigente en inicio de barra; nuevo nivel entra en vigor en la siguiente (§3.3)
- Tres casos de salida: stop_normal, gap_bajista, stop_entrada (§3.3)
- Trailing stop: max(stop_vigente, close[t] − atr_mult × ATR14[t]) (§3.4)
- Señal anterior a discontinuidad no ejecutable tras ella (§2.1 regla 6)
- Discontinuidad con posición abierta → resultado inválido (§2.1 regla 4)
- end_of_data: cierre al close de la última vela H4 completa (§3.3)
- Control de frecuencia: max 8 aperturas por mes calendario UTC (D-014)
- Dimensionamiento: tamano = riesgo_USDT / (distancia + precio × fee) (§3.6)
- Redondeo hacia abajo al múltiplo de STEP_SIZE más cercano (§9)
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd
import numpy as np

from .constants import (
    CAPITAL_INICIAL, RISK_PER_TRADE, FEE_ADVERSO,
    MAX_TRADES_MONTH, STEP_SIZE, Config,
)


@dataclass
class Trade:
    open_time_entrada:  pd.Timestamp
    open_time_salida:   pd.Timestamp
    precio_entrada:     float
    precio_salida:      float
    exit_type:          str          # stop_normal | gap_bajista | stop_entrada | end_of_data
    stop_inicial:       float
    stop_salida:        float        # nivel stop vigente en la barra de salida
    tamano_btc:         float
    pnl_bruto_usdt:     float
    costo_usdt:         float
    pnl_neto_usdt:      float
    equity_pre_usdt:    float
    equity_post_usdt:   float
    config_name:        str


@dataclass
class SimulationResult:
    config:          Config
    is_valid:        bool
    invalid_reason:  Optional[str]
    trades:          list[Trade]
    equity_curve:    pd.Series       # index=open_time, values=equity mark-to-market
    capital_inicial: float


def _floor_step(value: float, step: float) -> float:
    """Redondeo hacia abajo al múltiplo de step más cercano."""
    return math.floor(value / step) * step


def simulate(
    h4_ind: pd.DataFrame,
    config: Config,
    capital_inicial: float = CAPITAL_INICIAL,
    fee: float = FEE_ADVERSO,
    max_trades_month: int = MAX_TRADES_MONTH,
) -> SimulationResult:
    """
    Ejecuta la simulación completa sobre h4_ind (H4 con indicadores).

    h4_ind debe tener columnas:
      open_time, open, high, low, close, discontinuity_before,
      ema200, atr14, adx14

    Devuelve SimulationResult con trades y curva de equity mark-to-market.
    """
    trades: list[Trade] = []
    equity_times = []
    equity_vals  = []

    realized_equity = capital_inicial
    state = "FLAT"

    # Señal pendiente
    pending_entry = False
    prev_atr14    = None

    # Estado de posición abierta
    pos_entry_price  = None
    pos_stop         = None
    pos_size_btc     = None
    pos_entry_time   = None
    pos_equity_pre   = None
    pos_stop_inicial = None

    ops_per_month: dict = {}

    rows = h4_ind.to_dict("records")

    for i, row in enumerate(rows):
        open_time = row["open_time"]

        # ── 1. Discontinuidad ──────────────────────────────────────────────
        if row["discontinuity_before"]:
            if state == "LONG":
                # §2.1 regla 4: resultado inválido
                return SimulationResult(
                    config=config, is_valid=False,
                    invalid_reason=f"Discontinuidad con posición abierta en {open_time}",
                    trades=trades,
                    equity_curve=pd.Series(equity_vals, index=equity_times, name="equity"),
                    capital_inicial=capital_inicial,
                )
            # §2.1 regla 6: señal anterior no ejecutable
            pending_entry = False
            prev_atr14    = None

        ema200 = row["ema200"]
        atr14  = row["atr14"]
        adx14  = row["adx14"]
        bar_open  = row["open"]
        bar_high  = row["high"]
        bar_low   = row["low"]
        bar_close = row["close"]

        # ── 2. Entrada pendiente o verificación de stop ────────────────────
        if pending_entry and state == "FLAT":
            month_key = (open_time.year, open_time.month)
            if ops_per_month.get(month_key, 0) >= max_trades_month:
                # Límite fiscal alcanzado: descarta señal
                pending_entry = False
            else:
                entry_price  = bar_open
                stop_inicial = entry_price - config.atr_mult * prev_atr14
                distancia    = entry_price - stop_inicial          # > 0 siempre
                costo_unit   = entry_price * fee
                tamano_btc   = _floor_step(
                    (realized_equity * RISK_PER_TRADE) / (distancia + costo_unit),
                    STEP_SIZE,
                )
                ops_per_month[month_key] = ops_per_month.get(month_key, 0) + 1

                if bar_low <= stop_inicial:
                    # stop_entrada: posición se abre y cierra en la misma barra
                    exit_price  = stop_inicial
                    pnl_bruto   = tamano_btc * (exit_price - entry_price)
                    costo_usdt  = tamano_btc * entry_price * fee
                    pnl_neto    = pnl_bruto - costo_usdt
                    eq_pre      = realized_equity
                    realized_equity += pnl_neto
                    trades.append(Trade(
                        open_time_entrada=open_time, open_time_salida=open_time,
                        precio_entrada=entry_price, precio_salida=exit_price,
                        exit_type="stop_entrada",
                        stop_inicial=stop_inicial, stop_salida=stop_inicial,
                        tamano_btc=tamano_btc,
                        pnl_bruto_usdt=pnl_bruto, costo_usdt=costo_usdt,
                        pnl_neto_usdt=pnl_neto,
                        equity_pre_usdt=eq_pre, equity_post_usdt=realized_equity,
                        config_name=config.name,
                    ))
                else:
                    state            = "LONG"
                    pos_entry_price  = entry_price
                    pos_stop         = stop_inicial
                    pos_stop_inicial = stop_inicial
                    pos_size_btc     = tamano_btc
                    pos_entry_time   = open_time
                    pos_equity_pre   = realized_equity

                pending_entry = False

        elif state == "LONG":
            # Verificar stop con el nivel vigente del inicio de la barra
            if bar_open <= pos_stop:
                exit_price = bar_open
                _record_exit(
                    exit_type="gap_bajista", exit_price=exit_price, exit_time=open_time,
                    pos_entry_price=pos_entry_price, pos_stop_inicial=pos_stop_inicial,
                    pos_stop=pos_stop, pos_size_btc=pos_size_btc,
                    pos_entry_time=pos_entry_time, pos_equity_pre=pos_equity_pre,
                    fee=fee, config=config, trades=trades,
                )
                realized_equity = trades[-1].equity_post_usdt
                state = "FLAT"
            elif bar_low <= pos_stop:
                exit_price = pos_stop
                _record_exit(
                    exit_type="stop_normal", exit_price=exit_price, exit_time=open_time,
                    pos_entry_price=pos_entry_price, pos_stop_inicial=pos_stop_inicial,
                    pos_stop=pos_stop, pos_size_btc=pos_size_btc,
                    pos_entry_time=pos_entry_time, pos_equity_pre=pos_equity_pre,
                    fee=fee, config=config, trades=trades,
                )
                realized_equity = trades[-1].equity_post_usdt
                state = "FLAT"

        # ── 3. Curva de equity mark-to-market ─────────────────────────────
        if state == "LONG":
            unrealized = pos_size_btc * (bar_close - pos_entry_price)
            mtm = realized_equity + unrealized
        else:
            mtm = realized_equity
        equity_times.append(open_time)
        equity_vals.append(mtm)

        # ── 4. Actualizar trailing stop (vigencia diferida: próxima barra) ─
        if state == "LONG" and not np.isnan(atr14):
            new_stop = bar_close - config.atr_mult * atr14
            pos_stop = max(pos_stop, new_stop)

        # ── 5. Generar señal de entrada (para open[t+1]) ───────────────────
        if (state == "FLAT" and not pending_entry
                and not np.isnan(ema200) and not np.isnan(adx14) and not np.isnan(atr14)):
            if bar_close > ema200 and adx14 > config.adx_threshold:
                pending_entry = True
                prev_atr14    = atr14

    # ── end_of_data: cerrar posición abierta al close de la última vela ───
    if state == "LONG" and rows:
        last = rows[-1]
        exit_price = last["close"]
        exit_time  = last["open_time"]
        _record_exit(
            exit_type="end_of_data", exit_price=exit_price, exit_time=exit_time,
            pos_entry_price=pos_entry_price, pos_stop_inicial=pos_stop_inicial,
            pos_stop=pos_stop, pos_size_btc=pos_size_btc,
            pos_entry_time=pos_entry_time, pos_equity_pre=pos_equity_pre,
            fee=fee, config=config, trades=trades,
        )
        realized_equity = trades[-1].equity_post_usdt
        # Actualizar último punto de la curva con equity realizado
        if equity_vals:
            equity_vals[-1] = realized_equity

    return SimulationResult(
        config=config, is_valid=True, invalid_reason=None,
        trades=trades,
        equity_curve=pd.Series(equity_vals, index=equity_times, name="equity"),
        capital_inicial=capital_inicial,
    )


def _record_exit(
    *,
    exit_type: str,
    exit_price: float,
    exit_time,
    pos_entry_price: float,
    pos_stop_inicial: float,
    pos_stop: float,
    pos_size_btc: float,
    pos_entry_time,
    pos_equity_pre: float,
    fee: float,
    config: Config,
    trades: list,
) -> None:
    pnl_bruto  = pos_size_btc * (exit_price - pos_entry_price)
    costo_usdt = pos_size_btc * pos_entry_price * fee
    pnl_neto   = pnl_bruto - costo_usdt
    trades.append(Trade(
        open_time_entrada=pos_entry_time, open_time_salida=exit_time,
        precio_entrada=pos_entry_price, precio_salida=exit_price,
        exit_type=exit_type,
        stop_inicial=pos_stop_inicial, stop_salida=pos_stop,
        tamano_btc=pos_size_btc,
        pnl_bruto_usdt=pnl_bruto, costo_usdt=costo_usdt,
        pnl_neto_usdt=pnl_neto,
        equity_pre_usdt=pos_equity_pre,
        equity_post_usdt=pos_equity_pre + pnl_neto,
        config_name=config.name,
    ))
