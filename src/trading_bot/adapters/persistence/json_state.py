"""Thread-safe atomic JSON state store implementing StateStorePort."""

import json
import logging
import os
import tempfile
import threading
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from trading_bot.adapters.persistence.state_dto import StateDiskDTO
from trading_bot.core.exceptions import StateError
from trading_bot.ports.state_store import StateStorePort

log = logging.getLogger(__name__)


def _decimal_default(obj: Any) -> Any:
    """JSON serializer helper for Decimal values."""
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class JsonStateStore(StateStorePort):
    """Atomic POSIX file persistence store for bot operational state."""

    def __init__(self, path: Path, default_mode: str = "dry_run") -> None:
        self._path = path.resolve()
        self._default_mode = default_mode
        self._lock = threading.Lock()

    def default_state(self, mode: str | None = None, day: str | None = None) -> dict[str, Any]:
        """Generate default valid state dictionary."""
        effective_mode = mode or self._default_mode
        effective_day = day or date.today().isoformat()
        schema = StateDiskDTO(mode=effective_mode, day=effective_day)
        return schema.model_dump(mode="python")

    def load(self) -> dict[str, Any]:
        """Load and validate state from disk, creating default if file does not exist."""
        with self._lock:
            if not self._path.exists():
                init_state = self.default_state()
                self._save_atomic(init_state)
                return init_state

            try:
                content = self._path.read_text(encoding="utf-8")
                raw = json.loads(content)
            except Exception as err:
                raise StateError(f"Corrupted state file at {self._path}: {err}") from err

            if not isinstance(raw, dict):
                raise StateError(f"State file {self._path} must contain a JSON object")

            try:
                validated = StateDiskDTO.model_validate(raw)
            except Exception as err:
                raise StateError(f"State schema validation failed for {self._path}: {err}") from err

            return validated.model_dump(mode="python")

    def save(self, state_data: dict[str, Any]) -> None:
        """Atomically persist state data to disk."""
        with self._lock:
            try:
                validated = StateDiskDTO.model_validate(state_data)
            except Exception as err:
                raise StateError(f"Cannot save invalid state data: {err}") from err

            dumped = validated.model_dump(mode="python")
            self._save_atomic(dumped)

    def _save_atomic(self, state_data: dict[str, Any]) -> None:
        """Internal atomic write using mkstemp, fsync, and POSIX os.replace."""
        parent_dir = self._path.parent
        parent_dir.mkdir(parents=True, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(
            dir=str(parent_dir),
            prefix=".state-",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2, default=_decimal_default)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_path, self._path)
        except BaseException as err:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise StateError(f"Failed atomic write to {self._path}: {err}") from err
