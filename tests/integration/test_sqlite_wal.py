"""Integration tests for SQLite WAL mode persistence under concurrency."""

import concurrent.futures
from decimal import Decimal
from pathlib import Path

from trading_bot.adapters.persistence.sqlite_trades import SqliteTradeRepository


def test_sqlite_wal_concurrent_inserts(tmp_path: Path) -> None:
    """Verify concurrent inserts into SQLite with WAL mode complete without locking errors."""
    db_file = tmp_path / "concurrent_trades.db"
    repo = SqliteTradeRepository(db_file)
    repo.init_db()

    def worker(worker_id: int) -> None:
        for i in range(15):
            repo.log_open(
                price=Decimal("1000000.00") + Decimal(i),
                amount_btc=Decimal("0.001"),
                amount_mxn=Decimal("1000.00"),
                reason=f"worker_{worker_id}",
                mode="dry_run",
            )
            repo.log_close(
                event="close",
                entry_price=Decimal("1000000.00"),
                exit_price=Decimal("1050000.00"),
                amount_btc=Decimal("0.001"),
                pnl_mxn=Decimal("50.00"),
                pnl_pct=Decimal("5.00"),
                reason="rsi_sell",
                mode="dry_run",
            )

    threads = 4
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(worker, tid) for tid in range(threads)]
        for fut in concurrent.futures.as_completed(futures):
            fut.result()

    metrics = repo.get_metrics()
    assert metrics.total == threads * 15
    assert metrics.win_rate == Decimal("100.00")
    assert metrics.gross_profit == Decimal(str(threads * 15 * 50))
