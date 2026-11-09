"""
Cálculo de EMA200, ATR14 y ADX14 con suavizado Wilder (§3.2, §3.4).

- EMA200: α = 2/201. Inicialización con SMA de las primeras 200 velas H4.
- ATR14: α = 1/14 (Wilder). Inicialización con media de los primeros 14 TR.
- ADX14: Wilder para TR, +DM, -DM; primer ADX = media de 14 DX.
- Se reinician completamente en cada discontinuidad (§2.1 regla 5).
- Los valores son NaN hasta completar el calentamiento de 200 velas.
"""
import math
import numpy as np
import pandas as pd
from .constants import EMA_PERIOD, EMA_ALPHA, ATR_PERIOD, ADX_PERIOD


def compute_indicators(h4_df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega columnas ema200, atr14, adx14 a h4_df.
    NaN durante el calentamiento y tras cada reinicio.
    """
    n = len(h4_df)
    ema200_arr = np.full(n, np.nan)
    atr14_arr  = np.full(n, np.nan)
    adx14_arr  = np.full(n, np.nan)

    # --- estado EMA200 ---
    close_buf = []          # buffer para SMA inicial (hasta 200 cierres)
    ema_val   = None

    # --- estado ATR14 / ADX14 ---
    tr_buf        = []      # buffer 14 TR para SMA inicial
    plus_dm_buf   = []
    minus_dm_buf  = []
    smooth_tr     = None    # suma suavizada Wilder de TR
    smooth_pdm    = None
    smooth_mdm    = None
    dx_buf        = []      # buffer 14 DX para SMA inicial de ADX
    adx_val       = None

    # --- barra anterior ---
    prev_close = None
    prev_high  = None
    prev_low   = None

    rows = h4_df.to_dict("records")

    for i, row in enumerate(rows):
        if row["discontinuity_before"]:
            close_buf   = []
            ema_val     = None
            tr_buf      = []
            plus_dm_buf = []
            minus_dm_buf= []
            smooth_tr   = None
            smooth_pdm  = None
            smooth_mdm  = None
            dx_buf      = []
            adx_val     = None
            prev_close  = None
            prev_high   = None
            prev_low    = None

        # --- EMA200 ---
        if ema_val is None:
            close_buf.append(row["close"])
            if len(close_buf) == EMA_PERIOD:
                ema_val = sum(close_buf) / EMA_PERIOD
                ema200_arr[i] = ema_val
        else:
            ema_val = ema_val * (1.0 - EMA_ALPHA) + row["close"] * EMA_ALPHA
            ema200_arr[i] = ema_val

        # --- ATR14 y ADX14 (requieren barra anterior) ---
        if prev_close is not None:
            hi, lo, cl = row["high"], row["low"], row["close"]

            tr = max(hi - lo, abs(hi - prev_close), abs(lo - prev_close))

            up   = hi - prev_high
            down = prev_low - lo
            plus_dm  = up   if (up > down and up > 0)   else 0.0
            minus_dm = down if (down > up and down > 0) else 0.0

            # ATR14
            if smooth_tr is None:
                tr_buf.append(tr)
                if len(tr_buf) == ATR_PERIOD:
                    smooth_tr = sum(tr_buf)
                    atr14_arr[i] = smooth_tr / ATR_PERIOD
            else:
                smooth_tr = smooth_tr - smooth_tr / ATR_PERIOD + tr
                atr14_arr[i] = smooth_tr / ATR_PERIOD

            # +DM14 / -DM14 suavizados
            if smooth_pdm is None:
                plus_dm_buf.append(plus_dm)
                minus_dm_buf.append(minus_dm)
                if len(plus_dm_buf) == ADX_PERIOD:
                    smooth_pdm = sum(plus_dm_buf)
                    smooth_mdm = sum(minus_dm_buf)
            else:
                smooth_pdm = smooth_pdm - smooth_pdm / ADX_PERIOD + plus_dm
                smooth_mdm = smooth_mdm - smooth_mdm / ADX_PERIOD + minus_dm

            # DX → ADX14
            if smooth_tr is not None and smooth_pdm is not None and smooth_tr > 0:
                atr_now  = smooth_tr / ATR_PERIOD
                plus_di  = 100.0 * (smooth_pdm / ADX_PERIOD) / atr_now if atr_now > 0 else 0.0
                minus_di = 100.0 * (smooth_mdm / ADX_PERIOD) / atr_now if atr_now > 0 else 0.0
                di_sum = plus_di + minus_di
                dx = 100.0 * abs(plus_di - minus_di) / di_sum if di_sum > 0 else 0.0

                if adx_val is None:
                    dx_buf.append(dx)
                    if len(dx_buf) == ADX_PERIOD:
                        adx_val = sum(dx_buf) / ADX_PERIOD
                        adx14_arr[i] = adx_val
                else:
                    adx_val = (adx_val * (ADX_PERIOD - 1) + dx) / ADX_PERIOD
                    adx14_arr[i] = adx_val

        prev_close = row["close"]
        prev_high  = row["high"]
        prev_low   = row["low"]

    out = h4_df.copy()
    out["ema200"] = ema200_arr
    out["atr14"]  = atr14_arr
    out["adx14"]  = adx14_arr
    return out
