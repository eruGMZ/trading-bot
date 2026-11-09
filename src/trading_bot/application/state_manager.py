"""Thread-safe application state manager providing immutable domain snapshots."""

import threading
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from trading_bot.core.exceptions import StateError
from trading_bot.core.money import quantize_btc, to_decimal
from trading_bot.domain.models import BotSnapshot, Position
from trading_bot.domain.risk_engine import compute_pnl
from trading_bot.ports.state_store import StateStorePort


class StateManager:
    """Thread-safe coordinator for bot state management, returning frozen BotSnapshots."""

    def __init__(
        self,
        store: StateStorePort,
        mode: str = "dry_run",
        initial_capital: Decimal = Decimal("5000.00"),
    ) -> None:
        self._store = store
        self._lock = threading.Lock()
        self._mode = mode
        self._initial_capital = initial_capital

        with self._lock:
            raw_state = self._store.load()
            self._state = dict(raw_state)
            self._state["mode"] = mode
            if self._state.get("peak_equity") is None:
                self._state["peak_equity"] = initial_capital
            self._persist_locked()

    def _persist_locked(self) -> None:
        """Persist state holding the lock."""
        self._store.save(self._state)

    def snapshot(self) -> BotSnapshot:
        """Return an immutable, frozen domain snapshot of current in-memory state."""
        with self._lock:
            raw_pos = self._state.get("position")
            pos: Position | None = None
            if isinstance(raw_pos, dict):
                raw_time = raw_pos.get("entry_time")
                if isinstance(raw_time, datetime):
                    entry_dt = raw_time
                elif isinstance(raw_time, str) and raw_time:
                    entry_dt = datetime.fromisoformat(raw_time)
                else:
                    entry_dt = datetime.now()

                high_val = raw_pos.get("high_since_entry")
                if high_val is None:
                    high_val = raw_pos["entry_price"]

                pos = Position(
                    entry_price=to_decimal(raw_pos["entry_price"]),
                    amount_btc=to_decimal(raw_pos["amount_btc"]),
                    entry_time=entry_dt,
                    high_since_entry=to_decimal(high_val),
                )

            raw_trade_time = self._state.get("last_trade_time")
            trade_dt: datetime | None = None
            if isinstance(raw_trade_time, datetime):
                trade_dt = raw_trade_time
            elif isinstance(raw_trade_time, str) and raw_trade_time:
                trade_dt = datetime.fromisoformat(raw_trade_time)

            raw_tick_ok = self._state.get("last_tick_ok")
            tick_dt: datetime | None = None
            if isinstance(raw_tick_ok, datetime):
                tick_dt = raw_tick_ok
            elif isinstance(raw_tick_ok, str) and raw_tick_ok:
                tick_dt = datetime.fromisoformat(raw_tick_ok)

            return BotSnapshot(
                running=bool(self._state.get("running", True)),
                mode=str(self._state.get("mode", self._mode)),
                position=pos,
                pnl_total=to_decimal(self._state.get("pnl_total", Decimal("0"))),
                pnl_today=to_decimal(self._state.get("pnl_today", Decimal("0"))),
                trades_today=int(self._state.get("trades_today", 0)),
                losses_today=int(self._state.get("losses_today", 0)),
                peak_equity=to_decimal(self._state.get("peak_equity", self._initial_capital)),
                halt_reason=self._state.get("halt_reason"),
                last_trade_time=trade_dt,
                last_tick_ok=tick_dt,
                last_daily_report_date=self._state.get("last_daily_report_date"),
                last_update_id=int(self._state.get("last_update_id", 0)),
            )

    def set(self, **kwargs: Any) -> None:
        """Update state fields and persist."""
        with self._lock:
            self._state.update(kwargs)
            self._persist_locked()

    def halt(self, reason: str) -> None:
        """Halt bot execution until explicit manual operator intervention."""
        with self._lock:
            self._state["running"] = False
            self._state["halt_reason"] = reason
            self._persist_locked()

    def roll_day(self, today: str | None = None) -> bool:
        """Reset daily counters if calendar date has rolled over."""
        current_day = today or date.today().isoformat()
        with self._lock:
            if self._state.get("day") == current_day:
                return False
            self._state["day"] = current_day
            self._state["trades_today"] = 0
            self._state["losses_today"] = 0
            self._state["pnl_today"] = Decimal("0")
            self._persist_locked()
            return True

    def open_position(
        self,
        price: Decimal,
        amount_mxn: Decimal,
        entry_time: datetime | None = None,
    ) -> None:
        """Open a position, update trade counter, and atomically persist."""
        now_dt = entry_time or datetime.now()
        now_str = now_dt.isoformat(timespec="seconds")
        amount_btc = quantize_btc(amount_mxn / price)

        with self._lock:
            if self._state.get("position") is not None:
                raise StateError("Cannot open position when a position is already open")

            self._state["position"] = {
                "entry_price": str(price),
                "amount_btc": str(amount_btc),
                "entry_time": now_str,
                "high_since_entry": str(price),
            }
            self._state["trades_today"] = int(self._state.get("trades_today", 0)) + 1
            self._state["last_trade_time"] = now_str
            self._persist_locked()

    def close_position(
        self,
        sell_price: Decimal,
        sold_btc: Decimal,
        fee_rate: Decimal = Decimal("0"),
    ) -> tuple[Decimal, Decimal]:
        """Close current position, update realized PnL, and atomically persist."""
        with self._lock:
            pos_dict = self._state.get("position")
            if not isinstance(pos_dict, dict):
                return Decimal("0.00"), Decimal("0.00")

            entry_price = to_decimal(pos_dict["entry_price"])
            pnl_mxn, pnl_pct = compute_pnl(entry_price, sell_price, sold_btc, fee_rate)

            cur_pnl_today = to_decimal(self._state.get("pnl_today", Decimal("0")))
            cur_pnl_total = to_decimal(self._state.get("pnl_total", Decimal("0")))
            self._state["pnl_today"] = cur_pnl_today + pnl_mxn
            self._state["pnl_total"] = cur_pnl_total + pnl_mxn

            if pnl_mxn < Decimal("0"):
                self._state["losses_today"] = int(self._state.get("losses_today", 0)) + 1

            self._state["position"] = None
            self._persist_locked()
            return pnl_mxn, pnl_pct

    def update_position_high(self, price: Decimal) -> None:
        """Update highest price observed since position entry (trailing stop watermark)."""
        with self._lock:
            pos = self._state.get("position")
            if isinstance(pos, dict):
                high_val = pos.get("high_since_entry")
                if high_val is None:
                    high_val = pos["entry_price"]
                current_high = to_decimal(high_val)
                if price > current_high:
                    pos["high_since_entry"] = str(price)
                    self._persist_locked()

    def update_peak_equity(self, current_equity: Decimal) -> None:
        """Update historical high-watermark peak equity."""
        with self._lock:
            cur_peak = to_decimal(self._state.get("peak_equity", Decimal("0")))
            if current_equity > cur_peak:
                self._state["peak_equity"] = current_equity
                self._persist_locked()

    def mark_daily_report_sent(self, today: str) -> None:
        """Record date of the last daily summary report sent."""
        with self._lock:
            self._state["last_daily_report_date"] = today
            self._persist_locked()

    def bump_update_id(self, update_id: int) -> None:
        """Advance the highest processed Telegram update ID."""
        with self._lock:
            self._state["last_update_id"] = update_id
            self._persist_locked()
