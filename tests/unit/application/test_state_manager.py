"""Unit tests for StateManager coordinating state snapshots and persistence."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from trading_bot.adapters.persistence.json_state import JsonStateStore
from trading_bot.application.state_manager import StateManager
from trading_bot.core.exceptions import StateError


def test_state_manager_lifecycle(tmp_path: Path) -> None:
    """Verify StateManager opens, tracks high, closes position, and updates PnL."""
    store = JsonStateStore(tmp_path / "state.json", default_mode="dry_run")
    mgr = StateManager(store, mode="dry_run", initial_capital=Decimal("5000.00"))

    snap = mgr.snapshot()
    assert snap.running is True
    assert snap.position is None
    assert snap.trades_today == 0
    assert snap.pnl_today == Decimal("0")
    assert snap.peak_equity == Decimal("5000.00")

    # Open position
    mgr.open_position(
        price=Decimal("1000000.00"),
        amount_mxn=Decimal("1000.00"),
        entry_time=datetime(2026, 11, 9, 10, 0, 0),
    )

    snap_pos = mgr.snapshot()
    assert snap_pos.position is not None
    assert snap_pos.position.entry_price == Decimal("1000000.00")
    assert snap_pos.position.amount_btc == Decimal("0.00100000")
    assert snap_pos.trades_today == 1

    # Double open raises StateError
    with pytest.raises(StateError, match="Cannot open position"):
        mgr.open_position(price=Decimal("1000000"), amount_mxn=Decimal("500"))

    # Update position high (trailing stop watermark)
    mgr.update_position_high(Decimal("1050000.00"))
    assert mgr.snapshot().position.high_since_entry == Decimal("1050000.00")  # type: ignore[union-attr]

    # Lower price does not decrease high
    mgr.update_position_high(Decimal("1020000.00"))
    assert mgr.snapshot().position.high_since_entry == Decimal("1050000.00")  # type: ignore[union-attr]

    # Close position with profit
    pnl_mxn, pnl_pct = mgr.close_position(
        sell_price=Decimal("1020000.00"),
        sold_btc=Decimal("0.00100000"),
    )
    assert pnl_mxn == Decimal("20.00")
    assert pnl_pct == Decimal("2.00")

    snap_closed = mgr.snapshot()
    assert snap_closed.position is None
    assert snap_closed.pnl_today == Decimal("20.00")
    assert snap_closed.losses_today == 0


def test_state_manager_roll_day_and_halt(tmp_path: Path) -> None:
    """Verify calendar day rollover resets daily counters and halt locks the bot."""
    store = JsonStateStore(tmp_path / "state.json")
    mgr = StateManager(store)

    mgr.set(trades_today=3, losses_today=2, pnl_today=Decimal("-150.00"), day="2026-11-08")
    assert mgr.roll_day("2026-11-09") is True

    snap = mgr.snapshot()
    assert snap.trades_today == 0
    assert snap.losses_today == 0
    assert snap.pnl_today == Decimal("0")

    # Halt
    mgr.halt("Critical risk trip")
    snap_halted = mgr.snapshot()
    assert snap_halted.running is False
    assert snap_halted.halt_reason == "Critical risk trip"
