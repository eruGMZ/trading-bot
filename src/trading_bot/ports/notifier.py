"""Notifier and operator communication port interface."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class NotifierPort(Protocol):
    """Port interface for outgoing notifications and inbound operator messages."""

    def notify(self, message: str) -> None:
        """Send a notification to the configured operator channel."""
        ...

    def send_message(self, chat_id: int | str, text: str) -> None:
        """Send a direct message to a specific chat identifier."""
        ...

    def get_updates(self, offset: int) -> list[dict[str, Any]]:
        """Fetch pending message updates starting from the offset."""
        ...
