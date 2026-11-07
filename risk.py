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


def compute_pnl(entry_price, sell_price, sold_btc):
    """Calcula el PnL en MXN y en porcentaje.

    Returns:
        (pnl_mxn, pnl_pct) — positivo = ganancia, negativo = pérdida.
        No descuenta comisiones (eso queda para Fase 3).
    """
    pnl_mxn = (sell_price - entry_price) * sold_btc
    pnl_pct = (sell_price - entry_price) / entry_price * 100
    return pnl_mxn, pnl_pct
