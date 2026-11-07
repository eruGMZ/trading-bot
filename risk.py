"""Reglas de negocio puras: sin I/O, sin efectos secundarios.

Todas las funciones son deterministas dado el mismo input.
Se pueden testear sin Bitso, Telegram ni disco.
"""
from datetime import datetime


def can_trade(snapshot, now=None):
    """Evalúa si se puede abrir una nueva posición.

    Args:
        snapshot: copia inmutable del estado (dict).
        now: datetime para pruebas; None = datetime.now().

    Returns:
        (bool, str) — (autorizado, razón).
    """
    if snapshot.get("halt_reason"):
        return False, f"bot bloqueado: {snapshot['halt_reason']}"
    if not snapshot.get("running", True):
        return False, "bot detenido"
    if snapshot.get("position"):
        return False, "ya hay posición abierta"
    if snapshot.get("trades_today", 0) >= snapshot.get("max_trades", 3):
        return False, "máximo de trades diarios alcanzado"
    if snapshot.get("losses_today", 0) >= snapshot.get("max_losses", 2):
        return False, "máximo de pérdidas diarias alcanzado"

    # Corte de pérdida diaria en MXN (p. ej. 3% de capital_ref).
    pnl_today = snapshot.get("pnl_today", 0.0)
    capital_ref = snapshot.get("capital_ref", 5000.0)
    daily_loss_pct = snapshot.get("daily_loss_pct", 0.03)
    limit_mxn = -(capital_ref * daily_loss_pct)
    if pnl_today < limit_mxn:
        return False, f"corte de pérdida diaria ({pnl_today:+.0f} MXN, límite {limit_mxn:.0f} MXN)"

    last = snapshot.get("last_trade_time")
    if last:
        t = now if now is not None else datetime.now()
        elapsed_h = (t - datetime.fromisoformat(last)).total_seconds() / 3600
        min_h = snapshot.get("min_hours", 1)
        if elapsed_h < min_h:
            return False, f"esperando intervalo mínimo ({elapsed_h:.1f}h < {min_h}h)"

    return True, "ok"


def needs_stop_loss(entry_price, current_price, stop_loss_pct):
    """True si el precio cayó lo suficiente para activar el stop-loss."""
    if entry_price <= 0:
        return False
    return (entry_price - current_price) / entry_price >= stop_loss_pct


def signal_buy(rsi, rsi_buy):
    """True si el RSI señala compra (sobreventa)."""
    return rsi is not None and rsi < rsi_buy


def signal_sell(rsi, rsi_sell):
    """True si el RSI señala venta (sobrecompra)."""
    return rsi is not None and rsi > rsi_sell


def spread_too_wide(spread_pct, max_spread_pct):
    """True si el spread bid/ask supera el umbral permitido.

    Un spread ancho indica baja liquidez o spike de volatilidad.
    Bloquea entradas; no afecta salidas ni stop-loss.
    """
    return spread_pct > max_spread_pct


def drawdown_exceeded(current_equity, peak_equity, kill_pct):
    """True si el drawdown desde el máximo supera el umbral del kill switch.

    Args:
        current_equity: equity actual en MXN.
        peak_equity: equity máximo histórico en MXN.
        kill_pct: umbral (p. ej. 0.10 = 10%).
    """
    if peak_equity <= 0:
        return False
    drawdown = (peak_equity - current_equity) / peak_equity
    return drawdown >= kill_pct


def position_size_mxn(capital_ref, risk_pct, stop_loss_pct, max_mxn):
    """Calcula el tamaño de posición usando la fórmula riesgo / stop-loss.

    Ejemplo: capital_ref=5000, risk_pct=0.01, stop_loss_pct=0.02, max_mxn=500
      → riesgo = 5000 * 0.01 = 50 MXN
      → posición = 50 / 0.02 = 2500 MXN  → limitado a 500 MXN

    Args:
        capital_ref: capital de referencia en MXN.
        risk_pct: fracción de capital a arriesgar por operación (0.01 = 1%).
        stop_loss_pct: porcentaje de caída que activa el stop (0.02 = 2%).
        max_mxn: tope duro sobre el tamaño de posición.

    Returns:
        float — MXN a invertir, como mínimo 1 MXN.
    """
    if stop_loss_pct <= 0 or capital_ref <= 0:
        return max(1.0, min(max_mxn, 1.0))
    computed = (capital_ref * risk_pct) / stop_loss_pct
    return max(1.0, min(computed, max_mxn))


def compute_pnl(entry_price, sell_price, sold_btc, fee_rate=0.0):
    """Calcula el PnL en MXN y en porcentaje, descontando comisiones de ida y vuelta.

    Args:
        fee_rate: comisión por lado (ej. 0.0078 para taker de Bitso → ~1.56% round-trip).
                  0.0 para simulaciones sin comisiones.

    Returns:
        (pnl_mxn, pnl_pct) — positivo = ganancia, negativo = pérdida.
    """
    entry_cost    = entry_price * sold_btc * (1 + fee_rate)
    sell_proceeds = sell_price  * sold_btc * (1 - fee_rate)
    pnl_mxn = sell_proceeds - entry_cost
    pnl_pct = pnl_mxn / entry_cost * 100 if entry_cost > 0 else 0.0
    return pnl_mxn, pnl_pct
