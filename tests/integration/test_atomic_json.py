"""Integration tests verifying atomic JSON state replacement under concurrency."""

import concurrent.futures
from decimal import Decimal
from pathlib import Path

from trading_bot.adapters.persistence.json_state import JsonStateStore


def test_atomic_json_concurrent_reads_and_writes(tmp_path: Path) -> None:
    """Verify concurrent reads never encounter 0-byte or truncated files during atomic writes."""
    state_file = tmp_path / "state_concurrent.json"
    store = JsonStateStore(state_file)
    initial_state = store.load()

    iterations = 50
    errors: list[Exception] = []

    def writer() -> None:
        for i in range(iterations):
            try:
                state_copy = dict(initial_state)
                state_copy["trades_today"] = i
                state_copy["pnl_today"] = Decimal(str(i * 10))
                store.save(state_copy)
            except Exception as e:
                errors.append(e)

    def reader() -> None:
        for _ in range(iterations):
            try:
                loaded = store.load()
                assert isinstance(loaded, dict)
                assert "trades_today" in loaded
                assert "pnl_today" in loaded
            except Exception as e:
                errors.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        f_writers = [executor.submit(writer) for _ in range(2)]
        f_readers = [executor.submit(reader) for _ in range(4)]
        concurrent.futures.wait(f_writers + f_readers)

    assert not errors, f"Encountered concurrency errors: {errors}"
    final_state = store.load()
    assert isinstance(final_state, dict)
    assert final_state["running"] is True
