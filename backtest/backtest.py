"""Backtester Mean Reversion H1 — BTC/USDT — Variantes A y B.

Especificación: Documento_Implementación_Final v1.1 (2026-11-08)

Uso:
    python backtest.py               # ejecuta ambas variantes sobre TRAIN
    python backtest.py --oos         # incluye segmento OOS (una sola vez)

ADVERTENCIA: no correr con --oos hasta haber preregistrado las variantes
y congelado los parámetros Train. Ver protocolo OOS en el documento.

Decisiones metodológicas explícitas (trazabilidad con el documento):

  §2 "Regla de resolución SL/TP en la misma vela": si una vela H1 toca el nivel
      de SL y el de TP, se asume SIEMPRE que el SL se ejecutó primero. Se aplica
      de forma idéntica a las variantes A y B. Ver `_resolve_exit`.

  §2 "Especificación de indicadores": RSI(14) y ATR(14) con suavizado Wilder
      (α = 1/14, seed = media aritmética de las primeras n observaciones
      válidas). Velas H4 con límites horarios UTC. EMA200 H4 calculada
      exclusivamente sobre velas H4 CERRADAS (shift(1) antes de mapear a H1).

  §2 "Costos simulados": la comisión + buffer se descuenta del resultado de cada
      operación ANTES de calcular expectancy, profit factor, drawdown e IC. El
      resultado en R es NETO. Un escenario de costo distinto debe producir
      métricas distintas; si no lo hace, el descuento no se está aplicando.

  §2 "Split de datos": el periodo de calentamiento (velas iniciales necesarias
      para estabilizar la EMA200 H4) NO forma parte de Train. Train son los
      meses 1–24 del periodo de backtest y OOS son los ÚLTIMOS 12 meses.

  §2 "Métricas requeridas": Max Drawdown se reporta como % del capital,
      asumiendo el riesgo de 1% por operación de §6. El umbral de aceptación
      (< 10%) es un umbral de capital, no de R.

  §2 "Bootstrap por bloques": bloques circulares de tamaño fijo, con semilla
      fija para reproducibilidad.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ── Parámetros congelados (§1 del documento) ──────────────────────────────────
RSI_PERIOD   = 14
ATR_PERIOD   = 14
EMA_PERIOD   = 200
SL_MULT      = 1.5
TP_MULT      = 2.0
RSI_OVERSOLD = 30

# Costos por lado (§2): comisión 0.10% + buffer de ejecución
FEE_BASE     = 0.0011   # 0.10% + 0.01%
FEE_ADVERSE  = 0.0015   # 0.10% + 0.05%

MAX_PER_DAY  = 1
MAX_PER_MON  = 8

# Riesgo por trade (§6), usado para expresar el drawdown en % de capital
RISK_PER_TRADE = 0.01

# Umbrales de aceptación OOS (§2)
MIN_PROFIT_FACTOR = 1.2
MAX_DD_PCT        = 10.0

# Protocolo de backtest
BACKTEST_MONTHS = 36
OOS_MONTHS      = 12

# Bootstrap
BOOTSTRAP_N     = 2000
BOOTSTRAP_BLOCK = 10
BOOTSTRAP_SEED  = 20261108

# Clasificación de régimen (análisis complementario, §2).
# Pendiente de la EMA200 H4 cerrada sobre las últimas N velas H4, normalizada
# por el ATR H1. Umbral fijo, sin información futura.
REGIME_LOOKBACK_H4 = 10
REGIME_THRESHOLD   = 0.5

DATA_FILE    = Path(__file__).parent / "btcusdt_h1.csv"
VARIANTS_LOG = Path(__file__).parent / "variants_register.json"


# ── Variantes ─────────────────────────────────────────────────────────────────
# A y B son la estrategia base inmutable (§1). Las experimentales están
# limitadas a 2 por el documento (§2) y SOLO pueden ejecutarse sobre Train:
# `run_backtest` lo impide por construcción, no por convención.

VARIANT_SPECS = {
    "A": {
        "rule": "A", "rsi_oversold": 30, "sl_mult": 1.5, "tp_mult": 2.0,
        "experimental": False,
    },
    "B": {
        "rule": "B", "rsi_oversold": 30, "sl_mult": 1.5, "tp_mult": 2.0,
        "experimental": False,
    },
    # E1: RSI 25 — entradas más extremas. Hipótesis: un oversold más profundo
    # eleva la probabilidad de rebote y con ella la win rate, que es lo que
    # falla (36.5% frente a un breakeven de ~43% con el payoff 1.33:1).
    "E1": {
        "rule": "A", "rsi_oversold": 25, "sl_mult": 1.5, "tp_mult": 2.0,
        "experimental": True,
    },
    # E2: ATR mult 1.2/2.0 — stop más ceñido, payoff 1.67:1. Hipótesis: baja el
    # breakeven de win rate a ~37.5%, al alcance de la WR observada.
    "E2": {
        "rule": "A", "rsi_oversold": 30, "sl_mult": 1.2, "tp_mult": 2.0,
        "experimental": True,
    },
}

BASE_VARIANTS         = [v for v, s in VARIANT_SPECS.items() if not s["experimental"]]
EXPERIMENTAL_VARIANTS = [v for v, s in VARIANT_SPECS.items() if s["experimental"]]
MAX_EXPERIMENTAL      = 2   # §2 del documento


# ── Indicadores (suavizado Wilder = EMA α=1/n) ────────────────────────────────

def wilder_smooth(series: pd.Series, n: int) -> pd.Series:
    """Suavizado Wilder: seed = media aritmética de las primeras n observaciones
    válidas, luego recursión con α = 1/n.

    Las observaciones iniciales NaN (p. ej. el primer valor de un diff) se
    descartan antes de construir el seed, para no promediar sobre menos de n
    valores reales.
    """
    values = series.to_numpy(dtype=float)
    result = np.full(len(values), np.nan)

    valid = np.flatnonzero(~np.isnan(values))
    if len(valid) < n:
        return pd.Series(result, index=series.index)

    start = valid[n - 1]
    result[start] = values[valid[:n]].mean()

    alpha = 1.0 / n
    for i in range(start + 1, len(values)):
        if np.isnan(values[i]):
            result[i] = result[i - 1]
        else:
            result[i] = result[i - 1] * (1 - alpha) + values[i] * alpha
    return pd.Series(result, index=series.index)


def calc_rsi(close: pd.Series, n: int = RSI_PERIOD) -> pd.Series:
    delta  = close.diff()
    gain   = delta.clip(lower=0)
    loss   = (-delta).clip(lower=0)
    avg_g  = wilder_smooth(gain, n)
    avg_l  = wilder_smooth(loss, n)

    # avg_l == 0 → RSI = 100 por definición (no NaN: un NaN bloquearía la señal
    # de la variante B de forma silenciosa).
    rsi = np.full(len(close), np.nan)
    g   = avg_g.to_numpy(dtype=float)
    l   = avg_l.to_numpy(dtype=float)

    ready      = ~np.isnan(g) & ~np.isnan(l)
    zero_loss  = ready & (l == 0)
    zero_gain  = ready & (l != 0) & (g == 0)
    normal     = ready & (l != 0) & (g != 0)

    rsi[zero_loss] = 100.0
    rsi[zero_gain] = 0.0
    rs = g[normal] / l[normal]
    rsi[normal] = 100 - (100 / (1 + rs))
    return pd.Series(rsi, index=close.index)


def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series,
             n: int = ATR_PERIOD) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return wilder_smooth(tr, n)


def build_h4_features(df_h1: pd.DataFrame) -> tuple:
    """EMA200 sobre velas H4 (límites UTC 00/04/08/12/16/20h) y su pendiente,
    mapeadas al índice H1.

    Cada vela H1 recibe la última EMA200-H4 de una vela H4 YA CERRADA. La vela
    H4 en curso nunca se usa: `shift(1)` sobre la serie H4 antes del reindex
    garantiza que para una vela H1 dentro del bloque H4 que empieza en T, la
    EMA empleada es la del bloque que cerró en T.

    Retorna (ema200_h4, slope_h4) como arrays alineados con df_h1.
    """
    df = df_h1.copy()
    df.index = pd.to_datetime(df["open_time"], unit="ms", utc=True)

    # origin="epoch" fija los límites en múltiplos exactos de 4h desde epoch,
    # que en UTC son 00/04/08/12/16/20h.
    h4 = df["close"].resample("4h", closed="left", label="left",
                              origin="epoch").last().dropna()

    ema_h4 = h4.ewm(span=EMA_PERIOD, adjust=False).mean()

    # Pendiente absoluta de la EMA200 H4 sobre REGIME_LOOKBACK_H4 velas.
    slope_h4 = ema_h4.diff(REGIME_LOOKBACK_H4)

    h1_index = df.index
    ema_lagged   = ema_h4.shift(1).reindex(h1_index, method="ffill")
    slope_lagged = slope_h4.shift(1).reindex(h1_index, method="ffill")
    return ema_lagged.to_numpy(dtype=float), slope_lagged.to_numpy(dtype=float)


# ── Simulador ─────────────────────────────────────────────────────────────────

def _resolve_exit(high: float, low: float, sl: float, tp: float):
    """Resuelve la salida dentro de una vela H1.

    REGLA OBLIGATORIA (§2 del documento): si la vela toca ambos niveles y no se
    dispone de datos de menor temporalidad para determinar el orden real, se
    asume que el SL se ejecutó PRIMERO (resultado desfavorable). Se aplica de
    forma idéntica a todas las variantes, sin excepción y sin depender del
    resultado que convenga.
    """
    hit_sl = low  <= sl
    hit_tp = high >= tp
    if hit_sl and hit_tp:
        return sl, "SL_same_candle"
    if hit_sl:
        return sl, "SL"
    if hit_tp:
        return tp, "TP"
    return None, None


def simulate(df: pd.DataFrame, variant: str, fee_per_side: float) -> pd.DataFrame:
    """Simula operaciones sobre el DataFrame con indicadores precalculados.

    variant: clave de VARIANT_SPECS. La regla de entrada es 'A' (RSI por debajo
    del umbral al cierre) o 'B' (cruce al alza del umbral); el umbral de RSI y
    los múltiplos de ATR provienen de la especificación de la variante.

    El resultado en R de cada operación es NETO de comisiones:
        pnl_bruto_pct = exit/entry - 1
        pnl_neto_pct  = pnl_bruto_pct - 2 * fee_per_side
        pnl_r_neto    = pnl_neto_pct / (distancia_SL / entry)

    Una posición todavía abierta al final del segmento se registra con
    exit_type="OPEN_AT_END" y se excluye de las métricas.
    """
    if variant not in VARIANT_SPECS:
        raise ValueError(f"variante desconocida: {variant}")

    spec         = VARIANT_SPECS[variant]
    rule         = spec["rule"]
    rsi_oversold = spec["rsi_oversold"]
    sl_mult      = spec["sl_mult"]
    tp_mult      = spec["tp_mult"]

    trades       = []
    in_position  = False
    entry_price  = 0.0
    sl_price     = 0.0
    tp_price     = 0.0
    entry_time   = None
    entry_regime = None
    trades_today = 0
    trades_month = 0
    last_day     = None
    last_month   = None

    open_  = df["open"].to_numpy(dtype=float)
    high   = df["high"].to_numpy(dtype=float)
    low    = df["low"].to_numpy(dtype=float)
    close  = df["close"].to_numpy(dtype=float)
    rsi    = df["rsi"].to_numpy(dtype=float)
    atr    = df["atr"].to_numpy(dtype=float)
    ema200 = df["ema200"].to_numpy(dtype=float)
    slope  = df["ema200_slope"].to_numpy(dtype=float)
    times  = df["open_time"].to_numpy()

    def _record(exit_time, exit_price, exit_type):
        risk_pct = (entry_price - sl_price) / entry_price
        gross    = (exit_price / entry_price) - 1.0
        net      = gross - 2.0 * fee_per_side
        trades.append({
            "entry_time":  entry_time.isoformat(),
            "exit_time":   exit_time.isoformat() if exit_time else None,
            "entry_price": entry_price,
            "exit_price":  exit_price,
            "exit_type":   exit_type,
            "regime":      entry_regime,
            "pnl_r_gross": round(gross / risk_pct, 4),
            "pnl_r":       round(net / risk_pct, 4),   # NETO — base de métricas
            "pnl_pct":     round(net * 100, 4),
        })

    for i in range(1, len(df) - 1):
        ts  = datetime.fromtimestamp(int(times[i]) / 1000, tz=timezone.utc)
        day = ts.date()
        mon = (ts.year, ts.month)

        if day != last_day:
            trades_today = 0
            last_day     = day
        if mon != last_month:
            trades_month = 0
            last_month   = mon

        # ── Gestión de posición abierta ───────────────────────────────────────
        # La entrada ocurrió al open de esta vela o de una anterior, por lo que
        # la vela actual sí puede resolver el SL/TP.
        if in_position:
            exit_price, exit_type = _resolve_exit(high[i], low[i],
                                                  sl_price, tp_price)
            if exit_price is None:
                continue
            _record(ts, exit_price, exit_type)
            in_position = False
            continue

        # ── Señal de entrada (vela i = señal, entrada al open de i+1) ─────────
        if trades_today >= MAX_PER_DAY or trades_month >= MAX_PER_MON:
            continue
        if np.isnan(rsi[i]) or np.isnan(atr[i]) or np.isnan(ema200[i]):
            continue
        if atr[i] <= 0:
            continue
        # Filtro de tendencia: cierre H1 vs. última EMA200 H4 cerrada.
        if close[i] <= ema200[i]:
            continue

        if rule == "A":
            signal = rsi[i] < rsi_oversold
        else:  # "B": cruce al alza
            signal = (not np.isnan(rsi[i - 1])
                      and rsi[i - 1] < rsi_oversold
                      and rsi[i] >= rsi_oversold)
        if not signal:
            continue

        entry_price = open_[i + 1]
        atr_val     = atr[i]                       # ATR conocido al cierre de i
        sl_price    = entry_price - sl_mult * atr_val
        tp_price    = entry_price + tp_mult * atr_val
        if sl_price <= 0:
            continue

        # Régimen en la vela de señal (sin información futura).
        if np.isnan(slope[i]):
            entry_regime = "unknown"
        else:
            norm = abs(slope[i]) / atr_val
            entry_regime = "trending" if norm >= REGIME_THRESHOLD else "ranging"

        in_position   = True
        entry_time    = datetime.fromtimestamp(int(times[i + 1]) / 1000,
                                               tz=timezone.utc)
        trades_today += 1
        trades_month += 1

    # Posición abierta al final del segmento: se registra, no se inventa salida.
    if in_position:
        _record(None, close[-1], "OPEN_AT_END")

    return pd.DataFrame(trades)


# ── Métricas ──────────────────────────────────────────────────────────────────

EMPTY_METRICS = {
    "n": 0, "expectancy_r": 0.0, "profit_factor": 0.0,
    "max_dd_r": 0.0, "max_dd_pct": 0.0, "win_rate": 0.0,
    "open_at_end": 0,
}


def closed_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades
    return trades[trades["exit_type"] != "OPEN_AT_END"]


def metrics(trades: pd.DataFrame) -> dict:
    """Métricas sobre el resultado NETO en R de las operaciones cerradas."""
    n_open = 0 if trades.empty else int((trades["exit_type"] == "OPEN_AT_END").sum())
    closed = closed_trades(trades)
    if closed.empty:
        return {**EMPTY_METRICS, "open_at_end": n_open}

    r     = closed["pnl_r"].to_numpy(dtype=float)
    wins  = r[r > 0]
    loses = r[r <= 0]
    pf    = wins.sum() / abs(loses.sum()) if loses.sum() != 0 else float("inf")

    # Drawdown en R y en % de capital (riesgo 1% por operación, §6).
    equity = np.cumsum(r)
    peak   = np.maximum.accumulate(equity)
    max_dd_r = float((peak - equity).max())

    equity_pct = np.cumsum(r * RISK_PER_TRADE * 100.0)
    peak_pct   = np.maximum.accumulate(np.concatenate([[0.0], equity_pct]))[1:]
    peak_pct   = np.maximum(peak_pct, 0.0)
    max_dd_pct = float((peak_pct - equity_pct).max())

    return {
        "n":             int(len(r)),
        "expectancy_r":  round(float(r.mean()), 4),
        "profit_factor": round(pf, 4) if np.isfinite(pf) else None,
        "max_dd_r":      round(max_dd_r, 4),
        "max_dd_pct":    round(max_dd_pct, 4),
        "win_rate":      round(float((r > 0).mean()) * 100, 1),
        "open_at_end":   n_open,
    }


def bootstrap_ci(trades: pd.DataFrame, n_boot: int = BOOTSTRAP_N,
                 block_size: int = BOOTSTRAP_BLOCK, ci: float = 0.95) -> tuple:
    """IC de la expectancy neta por bootstrap de bloques circulares.

    Bloques circulares de tamaño fijo: preservan la dependencia temporal entre
    operaciones consecutivas y evitan el sesgo de truncar el último bloque.
    Semilla fija → reproducible.
    """
    closed = closed_trades(trades)
    if closed.empty:
        return (None, None)

    r = closed["pnl_r"].to_numpy(dtype=float)
    n = len(r)
    if n < 2:
        return (None, None)

    block = min(block_size, n)
    rng   = np.random.default_rng(BOOTSTRAP_SEED)
    n_blocks = int(np.ceil(n / block))

    starts  = rng.integers(0, n, size=(n_boot, n_blocks))
    offsets = np.arange(block)
    idx     = (starts[:, :, None] + offsets[None, None, :]) % n   # circular
    samples = r[idx.reshape(n_boot, -1)[:, :n]]
    means   = samples.mean(axis=1)

    alpha = (1 - ci) / 2
    return (round(float(np.quantile(means, alpha)), 4),
            round(float(np.quantile(means, 1 - alpha)), 4))


def regime_breakdown(trades: pd.DataFrame) -> dict:
    """Análisis complementario por régimen (§2). No es criterio de aprobación."""
    closed = closed_trades(trades)
    if closed.empty:
        return {}
    out = {}
    for regime, group in closed.groupby("regime"):
        out[str(regime)] = metrics(group)
    return out


# ── Criterios de decisión (§2) ─────────────────────────────────────────────────

def evaluate(m: dict, ci: tuple) -> tuple:
    """Aplica la regla única de decisión del documento.

    Todas las condiciones deben cumplirse simultáneamente:
      expectancy > 0  Y  PF > 1.2  Y  DD < 10% del capital  Y  IC95% > 0.

    - IC que cruza cero, o PF en (1.0, 1.2]: evidencia insuficiente, no avanzar.
    - PF <= 1.0 o expectancy <= 0: rechazar.
    - DD >= 10%: rechazar, independientemente de las demás métricas.
    """
    e     = m["expectancy_r"]
    pf    = m["profit_factor"]
    dd    = m["max_dd_pct"]
    ci_lo = ci[0]

    if m["n"] == 0:
        return "NO_DATA", "Sin operaciones cerradas en el segmento."

    pf_val = float("inf") if pf is None else pf

    # El DD excesivo rechaza por sí solo.
    if dd >= MAX_DD_PCT:
        return "REJECT", f"Max DD {dd:.2f}% ≥ {MAX_DD_PCT}% del capital."
    if e <= 0:
        return "REJECT", f"Expectancy neta {e}R ≤ 0: sin edge demostrable."
    if pf_val <= 1.0:
        return "REJECT", f"Profit Factor {pf} ≤ 1.0: sin edge demostrable."
    if pf_val <= MIN_PROFIT_FACTOR:
        return "INSUFFICIENT", (f"Profit Factor {pf} en (1.0, {MIN_PROFIT_FACTOR}]: "
                                "evidencia insuficiente.")
    if ci_lo is None:
        return "INSUFFICIENT", "IC 95% no calculable."
    if ci_lo <= 0:
        return "INSUFFICIENT", (f"IC 95% de expectancy cruza cero "
                                f"(límite inferior {ci_lo}).")
    return "CANDIDATE", (f"E={e}R, PF={pf}, DD={dd:.2f}%, IC95% inferior={ci_lo}.")


VERDICT_LABEL = {
    "CANDIDATE":    "✅ CANDIDATO A FASE 1",
    "INSUFFICIENT": "⚠️  Evidencia insuficiente. No avanzar.",
    "REJECT":       "❌ Rechazar.",
    "NO_DATA":      "— Sin datos.",
}


# ── Split de datos ─────────────────────────────────────────────────────────────

def split_segments(df: pd.DataFrame) -> tuple:
    """Separa calentamiento / Train / OOS según §2.

    El calentamiento (velas iniciales que estabilizan la EMA200 H4) queda FUERA
    de Train: solo alimenta los indicadores, que se precalculan sobre el dataset
    completo. Train son los meses 1–24 del periodo de backtest; OOS son los
    ÚLTIMOS 12 meses.
    """
    end       = df["dt"].max()
    oos_start = end - pd.DateOffset(months=OOS_MONTHS)
    bt_start  = end - pd.DateOffset(months=BACKTEST_MONTHS)

    if df["dt"].min() > bt_start:
        print(f"ERROR: los datos empiezan en {df['dt'].min().date()} y el periodo "
              f"de backtest de {BACKTEST_MONTHS} meses requiere datos desde "
              f"{bt_start.date()}, más el calentamiento previo.")
        sys.exit(1)

    warmup = df[df["dt"] < bt_start]
    train  = df[(df["dt"] >= bt_start) & (df["dt"] < oos_start)].copy()
    oos    = df[df["dt"] >= oos_start].copy()
    return warmup, train, oos


# ── Runner principal ───────────────────────────────────────────────────────────

def run_backtest(include_oos: bool = False, include_experimental: bool = False):
    if not DATA_FILE.exists():
        print(f"ERROR: {DATA_FILE} no encontrado. Ejecuta fetch_klines.py primero.")
        sys.exit(1)

    if len(EXPERIMENTAL_VARIANTS) > MAX_EXPERIMENTAL:
        print(f"ERROR: {len(EXPERIMENTAL_VARIANTS)} variantes experimentales "
              f"definidas; el documento permite un máximo de {MAX_EXPERIMENTAL}.")
        sys.exit(1)

    if include_oos:
        _guard_oos()

    variants = list(BASE_VARIANTS)
    if include_experimental:
        variants += EXPERIMENTAL_VARIANTS
        _guard_experimental()

    df = pd.read_csv(DATA_FILE)
    df = df.sort_values("open_time").drop_duplicates("open_time").reset_index(drop=True)

    # Indicadores sobre el dataset completo (el calentamiento los alimenta).
    df["rsi"] = calc_rsi(df["close"])
    df["atr"] = calc_atr(df["high"], df["low"], df["close"])
    ema, slope = build_h4_features(df)
    df["ema200"]       = ema
    df["ema200_slope"] = slope
    df["dt"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)

    warmup, df_train, df_oos = split_segments(df)

    print(f"\nCalentamiento : {warmup['dt'].min().date()} → {warmup['dt'].max().date()}"
          f"  ({len(warmup)} velas H1, ~{len(warmup)//4} H4) — no se operan")
    print(f"Train         : {df_train['dt'].min().date()} → {df_train['dt'].max().date()}"
          f"  ({len(df_train)} velas)")
    print(f"OOS           : {df_oos['dt'].min().date()} → {df_oos['dt'].max().date()}"
          f"  ({len(df_oos)} velas)"
          f"{'' if include_oos else '  [NO EJECUTADO]'}\n")

    results = {
        "_spec":  "Documento_Implementación_Final v1.1",
        "_run_at": datetime.now(timezone.utc).isoformat(),
        "_config": {
            "fee_per_side": {"base": FEE_BASE, "adverse": FEE_ADVERSE},
            "risk_per_trade": RISK_PER_TRADE,
            "max_per_day": MAX_PER_DAY, "max_per_month": MAX_PER_MON,
            "same_candle_rule": "SL_first",
            "variants": {v: VARIANT_SPECS[v] for v in variants},
            "bootstrap": {"n": BOOTSTRAP_N, "block": BOOTSTRAP_BLOCK,
                          "seed": BOOTSTRAP_SEED, "type": "circular_block"},
            "segments": {
                "train": [str(df_train["dt"].min()), str(df_train["dt"].max())],
                "oos":   [str(df_oos["dt"].min()), str(df_oos["dt"].max())],
            },
        },
        "segments": {},
    }

    for variant in variants:
        spec = VARIANT_SPECS[variant]
        tag  = "  [EXPERIMENTAL — solo Train]" if spec["experimental"] else ""
        print("=" * 72)
        print(f"Variante {variant}{tag}")
        print(f"  regla={spec['rule']}  RSI<{spec['rsi_oversold']}  "
              f"SL={spec['sl_mult']}×ATR  TP={spec['tp_mult']}×ATR")
        print("=" * 72)
        for scenario, fee in (("base", FEE_BASE), ("adverso", FEE_ADVERSE)):
            segments = [("train", df_train)]
            # Las variantes experimentales se evalúan EXCLUSIVAMENTE sobre Train
            # (§2). OOS está reservado a las variantes base preregistradas.
            if include_oos and not spec["experimental"]:
                segments.append(("oos", df_oos))

            for seg_name, seg_df in segments:
                trades = simulate(seg_df, variant, fee)
                m      = metrics(trades)
                ci     = bootstrap_ci(trades)
                print(f"  [{scenario:7}] {seg_name.upper():5} → "
                      f"n={m['n']:<4} E={m['expectancy_r']:>8}R  "
                      f"PF={str(m['profit_factor']):>7}  "
                      f"DD={m['max_dd_pct']:>6.2f}%  "
                      f"WR={m['win_rate']:>5}%  "
                      f"IC95%=[{ci[0]}, {ci[1]}]"
                      + (f"  (+{m['open_at_end']} abierta)" if m["open_at_end"] else ""))
                results["segments"][f"{variant}_{scenario}_{seg_name}"] = {
                    "metrics": m,
                    "ci95":    list(ci),
                    "regimes": regime_breakdown(trades),
                    "trades":  trades.to_dict(orient="records"),
                }
        print()

    out_file = Path(__file__).parent / ("results_full.json" if include_oos
                                        else "results_train.json")
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Resultados guardados en {out_file}")

    _print_regimes(results)
    _print_decision(results, variants, "oos" if include_oos else "train", include_oos)

    if include_oos:
        _mark_oos_executed()


def _print_regimes(results: dict):
    print(f"\n{'='*72}")
    print("ANÁLISIS POR RÉGIMEN (complementario — no es criterio de aprobación)")
    print("=" * 72)
    for key, data in results["segments"].items():
        if not data["regimes"]:
            continue
        print(f"  {key}")
        for regime, m in sorted(data["regimes"].items()):
            print(f"    {regime:9} n={m['n']:<4} E={m['expectancy_r']:>8}R  "
                  f"PF={str(m['profit_factor']):>7}  DD={m['max_dd_pct']:>6.2f}%")


def _print_decision(results: dict, variants: list, segment: str, is_oos: bool):
    print(f"\n{'='*72}")
    print(f"CRITERIOS DE DECISIÓN — segmento {segment.upper()} (§2 del documento)")
    if not is_oos:
        print("NOTA: los criterios de aceptación aplican al segmento OOS. Esta")
        print("      evaluación sobre Train es orientativa.")
    print("=" * 72)
    for variant in variants:
        for scenario in ("base", "adverso"):
            key = f"{variant}_{scenario}_{segment}"
            if key not in results["segments"]:
                continue
            data = results["segments"][key]
            verdict, reason = evaluate(data["metrics"], data["ci95"])
            print(f"  Variante {variant} [{scenario:7}] → "
                  f"{VERDICT_LABEL[verdict]}\n      {reason}")


# ── Protocolo OOS ──────────────────────────────────────────────────────────────

def _guard_oos():
    """OOS se ejecuta UNA SOLA VEZ sobre variantes preregistradas (§2)."""
    if not VARIANTS_LOG.exists():
        print(f"ERROR: {VARIANTS_LOG} no existe. Las variantes deben registrarse "
              "y congelarse ANTES de ejecutar OOS.")
        sys.exit(1)
    with open(VARIANTS_LOG) as f:
        reg = json.load(f)
    if not reg.get("variants"):
        print("ERROR: el registro de variantes está vacío.")
        sys.exit(1)
    if reg.get("oos_executed"):
        print(f"ERROR: OOS ya fue ejecutado el {reg.get('oos_executed_at')}.")
        print("El documento prohíbe re-ejecutar OOS o modificar parámetros tras")
        print("verlo. Una nueva hipótesis requiere un periodo histórico nuevo.")
        sys.exit(1)


def _guard_experimental():
    """Las variantes experimentales deben estar registradas ANTES de ejecutarse,
    y no pueden añadirse después de haber visto OOS (§2)."""
    if not VARIANTS_LOG.exists():
        print(f"ERROR: {VARIANTS_LOG} no existe.")
        sys.exit(1)
    with open(VARIANTS_LOG) as f:
        reg = json.load(f)

    if reg.get("oos_executed"):
        print("ERROR: OOS ya fue ejecutado. El documento prohíbe añadir o")
        print("evaluar variantes nuevas después de ver resultados OOS; una")
        print("hipótesis nueva requiere un periodo histórico no utilizado.")
        sys.exit(1)

    registered = {v["id"] for v in reg.get("experimental_variants", [])}
    missing    = set(EXPERIMENTAL_VARIANTS) - registered
    if missing:
        print(f"ERROR: variantes experimentales sin preregistrar: {sorted(missing)}.")
        print(f"Deben constar en {VARIANTS_LOG} antes de ejecutarse.")
        sys.exit(1)

    # El registro y el código deben describir los mismos parámetros.
    for entry in reg.get("experimental_variants", []):
        vid = entry["id"]
        if vid not in VARIANT_SPECS:
            continue
        spec = VARIANT_SPECS[vid]
        for key in ("rule", "rsi_oversold", "sl_mult", "tp_mult"):
            if entry["parameters"].get(key) != spec[key]:
                print(f"ERROR: la variante {vid} difiere entre el registro y el "
                      f"código en '{key}': registro={entry['parameters'].get(key)} "
                      f"vs código={spec[key]}.")
                sys.exit(1)


def _mark_oos_executed():
    with open(VARIANTS_LOG) as f:
        reg = json.load(f)
    reg["oos_executed"]    = True
    reg["oos_executed_at"] = datetime.now(timezone.utc).isoformat()
    with open(VARIANTS_LOG, "w") as f:
        json.dump(reg, f, indent=2, ensure_ascii=False)
    print(f"\nRegistro actualizado: OOS marcado como ejecutado en {VARIANTS_LOG}.")
    print("No se puede re-ejecutar OOS ni ajustar parámetros a partir de aquí.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--oos", action="store_true",
                        help="Incluir segmento OOS. Una sola ejecución permitida.")
    parser.add_argument("--experimental", action="store_true",
                        help="Incluir las variantes experimentales preregistradas. "
                             "Se evalúan exclusivamente sobre Train.")
    args = parser.parse_args()
    run_backtest(include_oos=args.oos, include_experimental=args.experimental)
