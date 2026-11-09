"""Unit tests for JSON state store and SQLite trade repository."""

from decimal import Decimal
from pathlib import Path

import pytest

from trading_bot.adapters.persistence.json_state import JsonStateStore
from trading_bot.adapters.persistence.sqlite_trades import SqliteTradeRepository
from trading_bot.adapters.persistence.state_dto import PositionDiskDTO, StateDiskDTO
from trading_bot.core.exceptions import StateError


def test_state_disk_schemas() -> None:
    """Verify validation and serialization of state DTOs."""
    pos = PositionDiskDTO(
        entry_price=Decimal("1000000.50"),
        amount_btc=Decimal("0.00500000"),
        entry_time="2026-11-09T10:00:00",
        high_since_entry=Decimal("1050000.00"),
    )
    assert pos.entry_price == Decimal("1000000.50")

    state = StateDiskDTO(
        day="2026-11-09",
        mode="operational",
        position=pos,
        pnl_today=Decimal("150.25"),
    )
    assert state.position is not None
    assert state.position.amount_btc == Decimal("0.00500000")
    assert state.pnl_today == Decimal("150.25")


def test_json_state_store_lifecycle(tmp_path: Path) -> None:
    """Verify JsonStateStore creates default state, saves updates, and loads accurately."""
    state_file = tmp_path / "state.json"
    store = JsonStateStore(state_file, default_mode="dry_run")

    # Load non-existent file -> initializes default state
    initial = store.load()
    assert initial["running"] is True
    assert initial["mode"] == "dry_run"
    assert initial["position"] is None
    assert state_file.is_file()

    # Modify and save state
    initial["position"] = {
        "entry_price": "1100000.00",
        "amount_btc": "0.002",
        "entry_time": "2026-11-09T12:00:00",
        "high_since_entry": "1100000.00",
    }
    initial["pnl_today"] = "250.50"
    store.save(initial)

    # Reload and verify
    reloaded = store.load()
    assert reloaded["position"] is not None
    assert reloaded["position"]["entry_price"] == Decimal("1100000.00")
    assert reloaded["pnl_today"] == Decimal("250.50")


def test_json_state_store_corrupted_file(tmp_path: Path) -> None:
    """Verify JsonStateStore raises StateError on corrupted file content."""
    state_file = tmp_path / "corrupt_state.json"
    state_file.write_text("{invalid json", encoding="utf-8")

    store = JsonStateStore(state_file)
    with pytest.raises(StateError, match="Corrupted state file"):
        store.load()


def test_json_state_store_invalid_schema(tmp_path: Path) -> None:
    """Verify JsonStateStore raises StateError on invalid schema structure."""
    state_file = tmp_path / "invalid_schema.json"
    state_file.write_text('{"unknown_key": 123}', encoding="utf-8")  # missing required "day"

    store = JsonStateStore(state_file)
    with pytest.raises(StateError, match="State schema validation failed"):
        store.load()


def test_sqlite_trade_repository_lifecycle(tmp_path: Path) -> None:
    """Verify SqliteTradeRepository records opens, closes, and calculates metrics."""
    db_file = tmp_path / "trades.db"
    repo = SqliteTradeRepository(db_file)
    repo.init_db()

    # Empty metrics
    empty_m = repo.get_metrics()
    assert empty_m.total == 0

    # Log open
    repo.log_open(
        price=Decimal("1000000.00"),
        amount_btc=Decimal("0.001"),
        amount_mxn=Decimal("1000.00"),
        reason="rsi_buy",
        mode="dry_run",
    )

    # Log two closed trades: 1 win (+100 MXN), 1 loss (-40 MXN)
    repo.log_close(
        event="close",
        entry_price=Decimal("1000000.00"),
        exit_price=Decimal("1100000.00"),
        amount_btc=Decimal("0.001"),
        pnl_mxn=Decimal("100.00"),
        pnl_pct=Decimal("10.00"),
        reason="rsi_sell",
        mode="dry_run",
    )
    repo.log_close(
        event="stop_loss",
        entry_price=Decimal("1000000.00"),
        exit_price=Decimal("960000.00"),
        amount_btc=Decimal("0.001"),
        pnl_mxn=Decimal("-40.00"),
        pnl_pct=Decimal("-4.00"),
        reason="stop_loss",
        mode="dry_run",
    )

    # Compute metrics
    m = repo.get_metrics()
    assert m.total == 2
    assert m.win_rate == Decimal("50.00")
    assert m.gross_profit == Decimal("100.00")
    assert m.gross_loss == Decimal("-40.00")
    assert m.expectancy == Decimal("30.00")  # (100 - 40) / 2 = 30
    assert m.profit_factor == Decimal("2.50")  # 100 / 40 = 2.5
