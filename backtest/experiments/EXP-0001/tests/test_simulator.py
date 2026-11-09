"""
Pruebas del simulador EXP-0001.

Estrategia de test: se pasan DataFrames H4 con indicadores ya calculados,
evitando el calentamiento de 200 barras para pruebas unitarias de lógica.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import numpy as np
import pytest
from engine.simulator import simulate
from engine.constants import Config, CAPITAL_INICIAL, FEE_ADVERSO, STEP_SIZE


CONFIG_A = Config("EXP-0001-A", adx_threshold=25.0, atr_mult=2.0, is_primary=True)

BASE_TIME = pd.Timestamp("2023-06-01 00:00:00", tz="UTC")


def _bar(offset_h4: int, o, h, l, c, ema200=None, atr14=None, adx14=None, disc=False):
    return {
        "open_time": BASE_TIME + pd.Timedelta(hours=4 * offset_h4),
        "open": float(o), "high": float(h), "low": float(l), "close": float(c),
        "ema200": float(ema200) if ema200 is not None else np.nan,
        "atr14":  float(atr14)  if atr14  is not None else np.nan,
        "adx14":  float(adx14)  if adx14  is not None else np.nan,
        "discontinuity_before": disc,
        "volume": 1.0,
    }


def _df(bars):
    return pd.DataFrame(bars)


class TestNoTrades:
    def test_no_signal_flat_indicators(self):
        bars = [_bar(i, 100, 101, 99, 100) for i in range(5)]
        result = simulate(_df(bars), CONFIG_A)
        assert result.is_valid
        assert result.trades == []

    def test_signal_requires_close_above_ema(self):
        # close < ema → no señal
        bars = [
            _bar(0, 100, 101, 99, 95, ema200=100, atr14=5, adx14=30),
            _bar(1, 95,  96,  94, 95),
        ]
        result = simulate(_df(bars), CONFIG_A)
        assert result.trades == []


class TestEntryLogic:
    def test_entry_at_next_open(self):
        """Señal en t, entrada en open[t+1]."""
        bars = [
            _bar(0, 100, 101, 99, 105, ema200=100, atr14=5, adx14=30),  # señal
            _bar(1, 108, 115, 107, 112, ema200=100, atr14=5, adx14=30),  # entrada open=108
            _bar(2, 110, 120, 109, 115, ema200=100, atr14=5, adx14=30),  # sigue abierto
            _bar(3, 113, 122, 112, 118, ema200=100, atr14=5, adx14=30),  # sigue abierto
        ]
        result = simulate(_df(bars), CONFIG_A)
        # Posición abierta → end_of_data al cierre de barra 3
        assert len(result.trades) == 1
        t = result.trades[0]
        assert t.precio_entrada == 108.0  # open[t+1]
        assert t.exit_type == "end_of_data"
        assert t.precio_salida == 118.0   # close de última barra

    def test_stop_inicial_calculation(self):
        """stop_inicial = open[t+1] - atr_mult * ATR14[t]."""
        # ATR14 en señal = 5, atr_mult=2 → stop = entry_price - 10
        bars = [
            _bar(0, 100, 101, 99, 105, ema200=100, atr14=5, adx14=30),  # señal, ATR=5
            _bar(1, 108, 115, 97, 112, ema200=100, atr14=4, adx14=30),  # low=97 < 108-10=98 → no, 97 < 98 → sí
        ]
        result = simulate(_df(bars), CONFIG_A)
        assert len(result.trades) == 1
        t = result.trades[0]
        # stop_inicial = 108 - 2*5 = 98
        assert abs(t.stop_inicial - 98.0) < 1e-9
        # low=97 ≤ 98 → stop_entrada
        assert t.exit_type == "stop_entrada"
        assert abs(t.precio_salida - 98.0) < 1e-9

    def test_no_lookahead_signal_uses_bar_t_data(self):
        """Verifica que la señal usa datos de t, no t+1."""
        # Barra t: close < EMA → no señal
        # Barra t+1: close > EMA → señal (pero no debería generar entrada en t+2)
        bars = [
            _bar(0, 100, 101, 99, 95, ema200=100, atr14=5, adx14=30),  # close=95 < ema=100 → no señal
            _bar(1, 95,  96,  94, 105, ema200=100, atr14=5, adx14=30), # close=105 > ema=100 → señal
            _bar(2, 103, 115, 102, 110, ema200=100, atr14=5, adx14=30), # entrada aquí
        ]
        result = simulate(_df(bars), CONFIG_A)
        # Solo un trade que entra en barra 2 (t=1 generó señal)
        assert len(result.trades) == 1
        assert result.trades[0].precio_entrada == 103.0  # open[2]


class TestStopScenarios:
    def test_stop_normal(self):
        """low ≤ stop pero open > stop → ejecutar al nivel del stop."""
        # Entrada barra 1: open=108, atr_mult=2, prev_atr14=5 → stop_inicial=98
        # Al cierre de barra 1: close=105, atr=5 → new_stop_cand=105-10=95 < 98 → trailing queda en 98
        # Barra 2: stop_vigente=98. low=97 ≤ 98 y open=103 > 98 → stop_normal at 98
        bars = [
            _bar(0, 100, 101, 99, 105, ema200=100, atr14=5, adx14=30),  # señal, prev_atr14=5
            _bar(1, 108, 115, 100, 105, ema200=100, atr14=5, adx14=30),  # entrada 108, stop=98; close=105<108 → trailing=98
            _bar(2, 103, 104, 97,  101, ema200=100, atr14=5, adx14=30),  # low=97 ≤ 98, open=103 > 98 → stop_normal at 98
        ]
        result = simulate(_df(bars), CONFIG_A)
        assert len(result.trades) == 1
        t = result.trades[0]
        assert t.exit_type == "stop_normal"
        assert abs(t.precio_salida - 98.0) < 1e-9

    def test_gap_bajista(self):
        """open[t] ≤ stop → ejecutar al open (gap)."""
        bars = [
            _bar(0, 100, 101, 99, 105, ema200=100, atr14=5, adx14=30),
            _bar(1, 108, 115, 100, 112, ema200=100, atr14=5, adx14=30),  # stop_inicial=98
            _bar(2, 90, 95, 88, 92, ema200=100, atr14=5, adx14=30),      # open=90 ≤ 98 → gap
        ]
        result = simulate(_df(bars), CONFIG_A)
        assert len(result.trades) == 1
        t = result.trades[0]
        assert t.exit_type == "gap_bajista"
        assert abs(t.precio_salida - 90.0) < 1e-9

    def test_stop_entrada(self):
        """low ≤ stop_inicial en la barra de entrada → stop_entrada."""
        bars = [
            _bar(0, 100, 101, 99, 105, ema200=100, atr14=5, adx14=30),
            _bar(1, 108, 115, 97, 112, ema200=100, atr14=5, adx14=30),  # stop=98, low=97 ≤ 98
        ]
        result = simulate(_df(bars), CONFIG_A)
        assert len(result.trades) == 1
        t = result.trades[0]
        assert t.exit_type == "stop_entrada"
        assert abs(t.precio_salida - 98.0) < 1e-9


class TestTrailingStop:
    def test_trailing_stop_never_decreases(self):
        """El trailing stop solo puede subir, nunca bajar."""
        # Barra 0: señal (prev_atr14=5)
        # Barra 1 (entrada): open=108, stop_inicial=98; close=120, atr=5 → new_stop=max(98,110)=110
        # Barra 2: stop=110, low=112 > 110 (no stop); close=115, atr=6 → new_stop=max(110, 115-12)=max(110,103)=110 (no baja)
        # Barra 3: stop=110, low=109 ≤ 110 → stop_normal at 110
        # La barra 2 tiene close=115 < ema200=200 para evitar nueva señal y 2º trade
        bars = [
            _bar(0, 100, 101, 99, 105, ema200=100, atr14=5, adx14=30),
            _bar(1, 108, 115, 100, 120, ema200=100, atr14=5, adx14=30),
            _bar(2, 118, 125, 112, 115, ema200=200, atr14=6, adx14=30),  # low=112 > 110; ema=200 bloquea señal nueva
            _bar(3, 113, 116, 109, 112, ema200=200, atr14=5, adx14=30),
        ]
        result = simulate(_df(bars), CONFIG_A)
        assert len(result.trades) == 1
        t = result.trades[0]
        assert t.exit_type == "stop_normal"
        assert abs(t.precio_salida - 110.0) < 1e-9

    def test_trailing_stop_vigencia_diferida(self):
        """
        El nivel calculado al cierre de barra t NO es ejecutable DURANTE barra t.
        Solo entra en vigor en la barra t+1.
        """
        # Barra entrada (t=1): stop_inicial=98. close=120, ATR=5 → new_stop=max(98,110)=110
        # Barra t=2: stop_vigente=110. low=109 (que es < 110) → debería ejecutarse, NO usar un stop hipotético más alto
        bars = [
            _bar(0, 100, 101, 99, 105, ema200=100, atr14=5, adx14=30),
            _bar(1, 108, 115, 100, 120, ema200=100, atr14=5, adx14=30),  # entrada, stop_inicial=98 → trailing=110 al cierre
            _bar(2, 112, 116, 109, 115, ema200=100, atr14=5, adx14=30),  # low=109 ≤ 110 → stop_normal
        ]
        result = simulate(_df(bars), CONFIG_A)
        assert len(result.trades) == 1
        t = result.trades[0]
        assert t.exit_type == "stop_normal"
        assert abs(t.precio_salida - 110.0) < 1e-9


class TestDiscontinuity:
    def test_discontinuity_with_open_position_invalidates(self):
        """Discontinuidad con posición abierta → resultado inválido."""
        bars = [
            _bar(0, 100, 101, 99, 105, ema200=100, atr14=5, adx14=30),
            _bar(1, 108, 115, 100, 112, ema200=100, atr14=5, adx14=30),  # entrada
            _bar(2, 110, 120, 109, 115, ema200=100, atr14=5, adx14=30, disc=True),  # discontinuidad con posición
        ]
        result = simulate(_df(bars), CONFIG_A)
        assert not result.is_valid

    def test_discontinuity_without_position_clears_signal(self):
        """Señal antes de discontinuidad no ejecutable después."""
        bars = [
            _bar(0, 100, 101, 99, 105, ema200=100, atr14=5, adx14=30),  # señal
            # discontinuidad: señal descartada
            _bar(1, 108, 115, 100, 112, disc=True),    # indicadores NaN → no señal
            _bar(2, 110, 120, 109, 115),
        ]
        result = simulate(_df(bars), CONFIG_A)
        assert result.is_valid
        assert len(result.trades) == 0  # señal fue descartada


class TestFrequencyFilter:
    def test_8_trades_per_month_limit(self):
        """Máximo 8 aperturas por mes calendario."""
        # Crear 10 señales en el mismo mes
        bars = []
        # Barra 0: señal
        for i in range(20):
            if i % 2 == 0:
                # Vela de señal
                bars.append(_bar(i, 100, 101, 99, 105, ema200=100, atr14=5, adx14=30))
            else:
                # Vela de entrada + stop_entrada para cerrar rápido
                bars.append(_bar(i, 108, 115, 97, 112, ema200=100, atr14=5, adx14=30))
        result = simulate(_df(bars), CONFIG_A)
        # Todas las barras de señal están en el mismo mes (2023-06)
        # Deben ejecutarse como máximo 8
        assert len(result.trades) <= 8


class TestEndOfData:
    def test_end_of_data_uses_last_close(self):
        """Posición abierta al final → cierre al close de la última barra."""
        bars = [
            _bar(0, 100, 101, 99, 105, ema200=100, atr14=5, adx14=30),
            _bar(1, 108, 115, 100, 112, ema200=100, atr14=5, adx14=30),
            _bar(2, 110, 120, 109, 999, ema200=100, atr14=5, adx14=30),  # close=999 (último)
        ]
        result = simulate(_df(bars), CONFIG_A)
        assert len(result.trades) == 1
        t = result.trades[0]
        assert t.exit_type == "end_of_data"
        assert abs(t.precio_salida - 999.0) < 1e-9
        assert t.open_time_salida == bars[2]["open_time"]


class TestSizingAndCosts:
    def test_risk_per_trade_0_5_percent(self):
        """El riesgo nominal debe ser ≤ 0.5% del equity inicial."""
        bars = [
            _bar(0, 100, 101, 99, 105, ema200=100, atr14=5, adx14=30),
            _bar(1, 108, 115, 100, 112, ema200=100, atr14=5, adx14=30),
        ]
        result = simulate(_df(bars), CONFIG_A)
        t = result.trades[0]
        # Si el stop se ejecutara exactamente: riesgo = tamano * distancia + costo
        distancia   = t.precio_entrada - t.stop_inicial
        costo_unit  = t.precio_entrada * FEE_ADVERSO
        riesgo_real = t.tamano_btc * (distancia + costo_unit)
        riesgo_max  = CAPITAL_INICIAL * 0.005
        # Puede ser ligeramente menor por redondeo hacia abajo
        assert riesgo_real <= riesgo_max + 1e-6

    def test_btc_size_rounded_down(self):
        """El tamaño se redondea hacia abajo al múltiplo de STEP_SIZE."""
        bars = [
            _bar(0, 100, 101, 99, 105, ema200=100, atr14=5, adx14=30),
            _bar(1, 108, 115, 100, 112, ema200=100, atr14=5, adx14=30),
        ]
        result = simulate(_df(bars), CONFIG_A)
        t = result.trades[0]
        import math
        assert abs(t.tamano_btc - math.floor(t.tamano_btc / STEP_SIZE) * STEP_SIZE) < 1e-12

    def test_round_trip_cost_applied(self):
        """El costo siempre se deduce del PnL neto."""
        bars = [
            _bar(0, 100, 101, 99, 105, ema200=100, atr14=5, adx14=30),
            _bar(1, 108, 115, 100, 112, ema200=100, atr14=5, adx14=30),
        ]
        result = simulate(_df(bars), CONFIG_A)
        t = result.trades[0]
        assert t.costo_usdt > 0
        assert abs(t.pnl_neto_usdt - (t.pnl_bruto_usdt - t.costo_usdt)) < 1e-9


class TestEquityCurve:
    def test_equity_curve_length_matches_bars(self):
        bars = [_bar(i, 100, 101, 99, 100) for i in range(5)]
        result = simulate(_df(bars), CONFIG_A)
        assert len(result.equity_curve) == 5

    def test_equity_starts_at_capital_inicial_when_flat(self):
        bars = [_bar(i, 100, 101, 99, 100) for i in range(3)]
        result = simulate(_df(bars), CONFIG_A)
        assert all(v == CAPITAL_INICIAL for v in result.equity_curve)
