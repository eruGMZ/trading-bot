"""Pure risk management rules and position sizing calculations.

All functions are deterministic, mathematical, and free of I/O or side effects.
Arithmetic is strictly executed using Decimal precision to preserve accounting accuracy.
"""

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

from trading_bot.core.money import quantize_mxn, quantize_percent, to_decimal
from trading_bot.domain.models import BotSnapshot, RiskLimits


def can_trade(
    snapshot: BotSnapshot | Mapping[str, Any],
    limits: RiskLimits | None = None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Evaluate whether the bot is authorized to open a new position.

    Args:
        snapshot: Current immutable bot snapshot or dictionary.
        limits: Optional RiskLimits overriding defaults or dictionary values.
        now: Timestamp used for evaluation (defaults to datetime.now()).

    Returns:
        (authorized, reason) tuple.
    """
    if isinstance(snapshot, BotSnapshot):
        halt_reason = snapshot.halt_reason
        running = snapshot.running
        has_position = snapshot.position is not None
        trades_today = snapshot.trades_today
        losses_today = snapshot.losses_today
        pnl_today = snapshot.pnl_today
        last_trade_time = snapshot.last_trade_time

        risk_cfg = limits if limits is not None else RiskLimits()
        max_trades = risk_cfg.max_trades_day
        max_losses = risk_cfg.max_losses_day
        capital_ref = risk_cfg.capital_ref_mxn
        daily_loss_pct = risk_cfg.daily_loss_pct
        trading_hours = risk_cfg.trading_hours
        min_hours = risk_cfg.min_hours_between_trades
    else:
        halt_reason = snapshot.get("halt_reason")
        running = bool(snapshot.get("running", True))
        has_position = snapshot.get("position") is not None
        trades_today = int(snapshot.get("trades_today", 0))
        losses_today = int(snapshot.get("losses_today", 0))
        pnl_today = to_decimal(snapshot.get("pnl_today", Decimal("0")))

        raw_last = snapshot.get("last_trade_time")
        if isinstance(raw_last, datetime):
            last_trade_time = raw_last
        elif isinstance(raw_last, str) and raw_last:
            last_trade_time = datetime.fromisoformat(raw_last)
        else:
            last_trade_time = None

        max_trades = (
            limits.max_trades_day
            if limits is not None
            else int(snapshot.get("max_trades", 3))
        )
        max_losses = (
            limits.max_losses_day
            if limits is not None
            else int(snapshot.get("max_losses", 2))
        )
        capital_ref = (
            limits.capital_ref_mxn
            if limits is not None
            else to_decimal(snapshot.get("capital_ref", Decimal("5000")))
        )
        daily_loss_pct = (
            limits.daily_loss_pct
            if limits is not None
            else to_decimal(snapshot.get("daily_loss_pct", Decimal("0.03")))
        )
        trading_hours = (
            limits.trading_hours
            if limits is not None
            else str(snapshot.get("trading_hours", ""))
        )
        min_hours = (
            limits.min_hours_between_trades
            if limits is not None
            else to_decimal(snapshot.get("min_hours", Decimal("1")))
        )

    if halt_reason:
        return False, f"bot halted: {halt_reason}"
    if not running:
        return False, "bot stopped"
    if has_position:
        return False, "position already open"
    if trades_today >= max_trades:
        return False, "daily trades limit reached"
    if losses_today >= max_losses:
        return False, "daily losses limit reached"

    # Daily loss cut in fiat (e.g. 3% of capital_ref)
    limit_mxn = -(capital_ref * daily_loss_pct)
    if pnl_today < limit_mxn:
        return False, f"daily loss limit breached ({pnl_today:+.2f} MXN, limit {limit_mxn:.2f} MXN)"

    current_dt = now if now is not None else datetime.now()

    if trading_hours:
        try:
            start_str, end_str = trading_hours.split("-")
            start_h, end_h = int(start_str), int(end_str)
            if not (start_h <= current_dt.hour < end_h):
                return (
                    False,
                    f"outside trading hours ({current_dt.hour}h, window {start_h}-{end_h}h)",
                )
        except (ValueError, TypeError):
            pass  # Malformed string bypassed safely in runtime check

    if last_trade_time is not None:
        elapsed_seconds = Decimal(str((current_dt - last_trade_time).total_seconds()))
        elapsed_hours = elapsed_seconds / Decimal("3600")
        if elapsed_hours < min_hours:
            return (
                False,
                f"waiting for minimum trade interval ({elapsed_hours:.1f}h < {min_hours:.1f}h)",
            )

    return True, "ok"


def needs_stop_loss(entry_price: Decimal, current_price: Decimal, stop_loss_pct: Decimal) -> bool:
    """Return True if price drop from entry exceeds or matches stop-loss threshold."""
    if entry_price <= Decimal("0"):
        return False
    drop = (entry_price - current_price) / entry_price
    return drop >= stop_loss_pct


def signal_buy(rsi: Decimal | None, rsi_buy: Decimal) -> bool:
    """Return True if RSI indicates oversold condition."""
    return rsi is not None and rsi < rsi_buy


def signal_sell(rsi: Decimal | None, rsi_sell: Decimal) -> bool:
    """Return True if RSI indicates overbought condition."""
    return rsi is not None and rsi > rsi_sell


def spread_too_wide(spread_pct: Decimal, max_spread_pct: Decimal) -> bool:
    """Return True if relative bid/ask spread exceeds allowed threshold."""
    return spread_pct > max_spread_pct


def drawdown_exceeded(current_equity: Decimal, peak_equity: Decimal, kill_pct: Decimal) -> bool:
    """Return True if drawdown from historical peak equity reaches kill-switch threshold."""
    if peak_equity <= Decimal("0"):
        return False
    drawdown = (peak_equity - current_equity) / peak_equity
    return drawdown >= kill_pct


def position_size_mxn(
    capital_ref: Decimal,
    risk_pct: Decimal,
    stop_loss_pct: Decimal,
    max_mxn: Decimal,
) -> Decimal:
    """Calculate target position size in MXN based on fixed fractional risk sizing.

    Formula: Position Size = (Capital Ref * Risk Pct) / Stop Loss Pct
    Clamped to [1.00 MXN, max_mxn].

    Args:
        capital_ref: Reference capital in MXN.
        risk_pct: Fraction of capital to risk per trade (e.g. 0.01 for 1%).
        stop_loss_pct: Expected stop loss percentage (e.g. 0.02 for 2%).
        max_mxn: Hard ceiling limit for position size in MXN.

    Returns:
        Quantized position size in MXN.
    """
    min_size = Decimal("1.00")
    if stop_loss_pct <= Decimal("0") or capital_ref <= Decimal("0"):
        return quantize_mxn(max(min_size, min(max_mxn, min_size)))

    computed = (capital_ref * risk_pct) / stop_loss_pct
    return quantize_mxn(max(min_size, min(computed, max_mxn)))


def compute_pnl(
    entry_price: Decimal,
    sell_price: Decimal,
    sold_btc: Decimal,
    fee_rate: Decimal = Decimal("0"),
) -> tuple[Decimal, Decimal]:
    """Compute realized profit and loss in fiat and percentage net of round-trip fees.

    Args:
        entry_price: Asset price at position entry.
        sell_price: Asset price at position exit.
        sold_btc: Quantity of BTC sold.
        fee_rate: Taker fee per side (e.g. 0.0078 for 0.78%).

    Returns:
        (pnl_mxn, pnl_pct) tuple quantized to fiat and percent precision.
    """
    one = Decimal("1")
    entry_cost = entry_price * sold_btc * (one + fee_rate)
    sell_proceeds = sell_price * sold_btc * (one - fee_rate)
    pnl_mxn = sell_proceeds - entry_cost

    pnl_pct = (
        (pnl_mxn / entry_cost) * Decimal("100")
        if entry_cost > Decimal("0")
        else Decimal("0")
    )

    return quantize_mxn(pnl_mxn), quantize_percent(pnl_pct)
