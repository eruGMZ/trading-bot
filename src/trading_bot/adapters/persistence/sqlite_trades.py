"""SQLite trade repository implementing TradeRepositoryPort with WAL mode and exact TEXT storage."""

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from trading_bot.core.money import quantize_mxn, quantize_percent, to_decimal
from trading_bot.domain.models import TradeMetrics
from trading_bot.ports.trade_repository import TradeRepositoryPort

_DDL = """
CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    event       TEXT    NOT NULL,
    book        TEXT    NOT NULL,
    price       TEXT    NOT NULL,
    amount_btc  TEXT    NOT NULL,
    amount_mxn  TEXT,
    pnl_mxn     TEXT,
    pnl_pct     TEXT,
    entry_price TEXT,
    reason      TEXT,
    mode        TEXT    NOT NULL
);
"""


class SqliteTradeRepository(TradeRepositoryPort):
    """Auditable SQLite trade log repository storing financial figures as exact Decimal TEXT."""

    def __init__(self, db_path: Path, timeout: float = 30.0) -> None:
        self._path = db_path.resolve()
        self._timeout = timeout

    def _connect(self) -> sqlite3.Connection:
        """Create a connection with WAL mode enabled and explicit timeout."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._path), timeout=self._timeout)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def init_db(self) -> None:
        """Initialize database tables idempotently."""
        with self._connect() as conn:
            conn.execute(_DDL)

    def log_open(
        self,
        price: Decimal,
        amount_btc: Decimal,
        amount_mxn: Decimal,
        reason: str,
        mode: str,
        book: str = "btc_mxn",
    ) -> None:
        """Record the opening of a position."""
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO trades
                   (ts, event, book, price, amount_btc, amount_mxn,
                    pnl_mxn, pnl_pct, entry_price, reason, mode)
                   VALUES (?, 'open', ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)""",
                (
                    datetime.now().isoformat(timespec="seconds"),
                    book,
                    str(price),
                    str(amount_btc),
                    str(amount_mxn),
                    reason,
                    mode,
                ),
            )

    def log_close(
        self,
        event: str,
        entry_price: Decimal,
        exit_price: Decimal,
        amount_btc: Decimal,
        pnl_mxn: Decimal,
        pnl_pct: Decimal,
        reason: str,
        mode: str,
        book: str = "btc_mxn",
    ) -> None:
        """Record the closing or stop of a position."""
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO trades
                   (ts, event, book, price, amount_btc, amount_mxn,
                    pnl_mxn, pnl_pct, entry_price, reason, mode)
                   VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)""",
                (
                    datetime.now().isoformat(timespec="seconds"),
                    event,
                    book,
                    str(exit_price),
                    str(amount_btc),
                    str(pnl_mxn),
                    str(pnl_pct),
                    str(entry_price),
                    reason,
                    mode,
                ),
            )

    def get_metrics(self) -> TradeMetrics:
        """Compute performance metrics from historical closed operations."""
        with self._connect() as conn:
            rows = [
                to_decimal(r[0])
                for r in conn.execute(
                    "SELECT pnl_mxn FROM trades "
                    "WHERE event IN ('close','stop_loss','trailing_stop','kill_switch') "
                    "AND pnl_mxn IS NOT NULL ORDER BY id"
                )
            ]

        if not rows:
            return TradeMetrics(
                total=0,
                win_rate=Decimal("0.00"),
                expectancy=Decimal("0.00"),
                profit_factor=Decimal("0.00"),
                max_drawdown_mxn=Decimal("0.00"),
                gross_profit=Decimal("0.00"),
                gross_loss=Decimal("0.00"),
            )

        wins = [p for p in rows if p > Decimal("0")]
        losses = [p for p in rows if p <= Decimal("0")]
        total = len(rows)

        gross_profit = sum(wins, Decimal("0"))
        gross_loss_abs = abs(sum(losses, Decimal("0")))

        if gross_loss_abs > Decimal("0"):
            profit_factor = quantize_mxn(gross_profit / gross_loss_abs)
        else:
            profit_factor = Decimal("Infinity")

        win_rate = quantize_percent((Decimal(len(wins)) / Decimal(total)) * Decimal("100"))
        expectancy = quantize_mxn(sum(rows, Decimal("0")) / Decimal(total))

        # Max drawdown calculation
        cum = peak = max_dd = Decimal("0")
        for p in rows:
            cum += p
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd

        return TradeMetrics(
            total=total,
            win_rate=win_rate,
            expectancy=expectancy,
            profit_factor=profit_factor,
            max_drawdown_mxn=quantize_mxn(max_dd),
            gross_profit=quantize_mxn(gross_profit),
            gross_loss=quantize_mxn(-gross_loss_abs),
        )
