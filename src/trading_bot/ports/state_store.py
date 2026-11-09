"""State persistence store port interface."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StateStorePort(Protocol):
    """Port interface for persisting and loading bot state."""

    def load(self) -> dict[str, Any]:
        """Load state data from the persistent store."""
        ...

    def save(self, state_data: dict[str, Any]) -> None:
        """Atomically persist state data."""
        ...
