"""Unit tests for pure risk engine logic and financial calculations."""

from datetime import datetime, timedelta
from decimal import Decimal

from trading_bot.domain.models import BotSnapshot, Position, RiskLimits
from trading_bot.domain.risk_engine import (
    can_trade,
    compute_pnl,
    drawdown_exceeded,
    needs_stop_loss,
    position_size_mxn,
    signal_buy,
    signal_sell,
    spread_too_wide,
)


def _create_snapshot(
    running: bool = True,
    position: Position | None = None,
    trades_today: int = 0,
    losses_today: int = 0,
    pnl_today: Decimal = Decimal("0"),
    pnl_total: Decimal = Decimal("0"),
    peak_equity: Decimal = Decimal("5000"),
    halt_reason: str | None = None,
    last_trade_time: datetime | None = None,
) -> BotSnapshot:
    return BotSnapshot(
        running=running,
        mode="dry_run",
        position=position,
        pnl_total=pnl_total,
        pnl_today=pnl_today,
        trades_today=trades_today,
        losses_today=losses_today,
        peak_equity=peak_equity,
        halt_reason=halt_reason,
        last_trade_time=last_trade_time,
    )


# ── can_trade tests ──────────────────────────────────────────────────────────


def test_can_trade_fresh_state_authorized() -> None:
    """Verify fresh state without positions or trades is authorized."""
    snap = _create_snapshot()
    ok, reason = can_trade(snap)
    assert ok is True
    assert reason == "ok"


def test_can_trade_blocks_when_halted() -> None:
    """Verify can_trade blocks when halt_reason is set."""
    snap = _create_snapshot(halt_reason="critical error")
    ok, reason = can_trade(snap)
    assert ok is False
    assert "bot halted" in reason


def test_can_trade_blocks_when_stopped() -> None:
    """Verify can_trade blocks when bot is not running."""
    snap = _create_snapshot(running=False)
    ok, reason = can_trade(snap)
    assert ok is False
    assert "bot stopped" in reason


def test_can_trade_blocks_when_position_open() -> None:
    """Verify can_trade blocks when position is already open."""
    pos = Position(
        entry_price=Decimal("1000000"),
        amount_btc=Decimal("0.001"),
        entry_time=datetime.now(),
        high_since_entry=Decimal("1000000"),
    )
    snap = _create_snapshot(position=pos)
    ok, reason = can_trade(snap)
    assert ok is False
    assert "position already open" in reason


def test_can_trade_blocks_at_daily_trade_limits() -> None:
    """Verify can_trade blocks at max_trades or max_losses limits."""
    snap_trades = _create_snapshot(trades_today=3)
    ok, reason = can_trade(snap_trades)
    assert ok is False
    assert "daily trades limit reached" in reason

    snap_losses = _create_snapshot(losses_today=2)
    ok, reason = can_trade(snap_losses)
    assert ok is False
    assert "daily losses limit reached" in reason


def test_can_trade_daily_loss_cutoff() -> None:
    """Verify can_trade blocks when daily loss exceeds configured percentage."""
    limits = RiskLimits(capital_ref_mxn=Decimal("5000"), daily_loss_pct=Decimal("0.03"))
    # 3% of 5000 = -150 MXN limit

    snap_ok = _create_snapshot(pnl_today=Decimal("-100"))
    assert can_trade(snap_ok, limits=limits)[0] is True

    snap_breach = _create_snapshot(pnl_today=Decimal("-150.01"))
    ok, reason = can_trade(snap_breach, limits=limits)
    assert ok is False
    assert "daily loss limit breached" in reason


def test_can_trade_trading_hours_window() -> None:
    """Verify can_trade respects trading_hours restrictions."""
    limits = RiskLimits(trading_hours="9-22")
    inside_time = datetime(2026, 1, 1, 14, 0, 0)
    outside_time = datetime(2026, 1, 1, 3, 0, 0)

    snap = _create_snapshot()
    assert can_trade(snap, limits=limits, now=inside_time)[0] is True
    ok, reason = can_trade(snap, limits=limits, now=outside_time)
    assert ok is False
    assert "outside trading hours" in reason


def test_can_trade_minimum_trade_interval() -> None:
    """Verify can_trade enforces minimum delay between trades."""
    limits = RiskLimits(min_hours_between_trades=Decimal("1"))
    now = datetime(2026, 1, 1, 12, 0, 0)

    # 30 minutes ago -> should block
    snap_recent = _create_snapshot(last_trade_time=now - timedelta(minutes=30))
    ok, reason = can_trade(snap_recent, limits=limits, now=now)
    assert ok is False
    assert "waiting for minimum trade interval" in reason

    # 2 hours ago -> should allow
    snap_ready = _create_snapshot(last_trade_time=now - timedelta(hours=2))
    assert can_trade(snap_ready, limits=limits, now=now)[0] is True


def test_can_trade_with_dict_snapshot() -> None:
    """Verify backwards compatibility of can_trade with raw dictionary snapshots."""
    dict_snap = {
        "running": True,
        "halt_reason": None,
        "position": None,
        "trades_today": 0,
        "losses_today": 0,
        "pnl_today": Decimal("0"),
        "capital_ref": Decimal("5000"),
        "daily_loss_pct": Decimal("0.03"),
    }
    assert can_trade(dict_snap)[0] is True


# ── Position sizing tests ────────────────────────────────────────────────────


def test_position_sizing_calculation() -> None:
    """Verify position sizing uses (capital * risk_pct) / stop_loss_pct capped at max_mxn."""
    # capital=5000, risk=1% (50 MXN), stop=2% -> 50 / 0.02 = 2500 MXN -> capped at 500 MXN
    size = position_size_mxn(
        capital_ref=Decimal("5000"),
        risk_pct=Decimal("0.01"),
        stop_loss_pct=Decimal("0.02"),
        max_mxn=Decimal("500"),
    )
    assert size == Decimal("500.00")


def test_position_sizing_uncapped_when_below_max() -> None:
    """Verify position sizing is not capped when computed size is below max_mxn."""
    # capital=1000, risk=1% (10 MXN), stop=10% -> 10 / 0.10 = 100 MXN (max 500)
    size = position_size_mxn(
        capital_ref=Decimal("1000"),
        risk_pct=Decimal("0.01"),
        stop_loss_pct=Decimal("0.10"),
        max_mxn=Decimal("500"),
    )
    assert size == Decimal("100.00")


def test_position_sizing_minimum_floor() -> None:
    """Verify position sizing returns at least 1.00 MXN on zero/negative capital."""
    size = position_size_mxn(
        capital_ref=Decimal("0"),
        risk_pct=Decimal("0.01"),
        stop_loss_pct=Decimal("0.02"),
        max_mxn=Decimal("500"),
    )
    assert size == Decimal("1.00")


# ── Stop-loss & Drawdown tests ───────────────────────────────────────────────


def test_needs_stop_loss() -> None:
    """Verify stop-loss triggers when price drop meets or exceeds threshold."""
    # 2% drop from 100,000 is 98,000
    assert needs_stop_loss(Decimal("100000"), Decimal("98000"), Decimal("0.02")) is True
    assert needs_stop_loss(Decimal("100000"), Decimal("97000"), Decimal("0.02")) is True
    assert needs_stop_loss(Decimal("100000"), Decimal("99000"), Decimal("0.02")) is False
    assert needs_stop_loss(Decimal("0"), Decimal("90000"), Decimal("0.02")) is False


def test_drawdown_exceeded() -> None:
    """Verify drawdown kill-switch triggers at or above threshold."""
    assert drawdown_exceeded(Decimal("9000"), Decimal("10000"), Decimal("0.10")) is True
    assert drawdown_exceeded(Decimal("8000"), Decimal("10000"), Decimal("0.10")) is True
    assert drawdown_exceeded(Decimal("9500"), Decimal("10000"), Decimal("0.10")) is False
    assert drawdown_exceeded(Decimal("0"), Decimal("0"), Decimal("0.10")) is False


def test_spread_too_wide() -> None:
    """Verify spread filter blocks when spread exceeds maximum."""
    assert spread_too_wide(Decimal("0.006"), Decimal("0.005")) is True
    assert spread_too_wide(Decimal("0.004"), Decimal("0.005")) is False
    assert spread_too_wide(Decimal("0.005"), Decimal("0.005")) is False


def test_signals_basic() -> None:
    """Verify signal_buy and signal_sell evaluation."""
    assert signal_buy(Decimal("28"), Decimal("30")) is True
    assert signal_buy(Decimal("30"), Decimal("30")) is False
    assert signal_buy(None, Decimal("30")) is False

    assert signal_sell(Decimal("72"), Decimal("70")) is True
    assert signal_sell(Decimal("70"), Decimal("70")) is False
    assert signal_sell(None, Decimal("70")) is False


# ── PnL computation tests ────────────────────────────────────────────────────


def test_compute_pnl_gain_and_loss() -> None:
    """Verify PnL computation for positive and negative trades without fees."""
    # Gain: bought at 1,000,000, sold at 1,020,000 (+2%)
    pnl_mxn, pnl_pct = compute_pnl(
        entry_price=Decimal("1000000"),
        sell_price=Decimal("1020000"),
        sold_btc=Decimal("0.0005"),
    )
    assert pnl_mxn == Decimal("10.00")
    assert pnl_pct == Decimal("2.00")

    # Loss: bought at 1,000,000, sold at 980,000 (-2%)
    pnl_mxn, pnl_pct = compute_pnl(
        entry_price=Decimal("1000000"),
        sell_price=Decimal("980000"),
        sold_btc=Decimal("0.0005"),
    )
    assert pnl_mxn == Decimal("-10.00")
    assert pnl_pct == Decimal("-2.00")


def test_compute_pnl_with_taker_fees() -> None:
    """Verify Bitso taker fee deduction turns breakeven price movement into a loss."""
    # Round-trip with 0.0078 fee per side
    pnl_mxn, pnl_pct = compute_pnl(
        entry_price=Decimal("1000000"),
        sell_price=Decimal("1000000"),
        sold_btc=Decimal("0.001"),
        fee_rate=Decimal("0.0078"),
    )
    # Entry cost = 1000 * 1.0078 = 1007.80
    # Proceeds = 1000 * 0.9922 = 992.20
    # PnL = 992.20 - 1007.80 = -15.60 MXN
    assert pnl_mxn == Decimal("-15.60")
    assert pnl_pct == Decimal("-1.55")
