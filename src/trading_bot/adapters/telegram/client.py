"""Telegram HTTP adapter implementing NotifierPort."""

import logging
from typing import Any

import requests
from pydantic import SecretStr

from trading_bot.adapters.telegram.telegram_dto import TelegramResponseDTO, TelegramUpdateDTO
from trading_bot.ports.notifier import NotifierPort

log = logging.getLogger(__name__)

DEFAULT_TELEGRAM_BASE = "https://api.telegram.org"
DEFAULT_TIMEOUT = 10.0


class TelegramAdapter(NotifierPort):
    """Production Telegram client implementing NotifierPort."""

    def __init__(
        self,
        token: str | SecretStr,
        chat_id: str | int,
        base_url: str = DEFAULT_TELEGRAM_BASE,
        timeout: float = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
    ) -> None:
        self._token = token.get_secret_value() if isinstance(token, SecretStr) else str(token)
        self._chat_id = str(chat_id).strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = session or requests.Session()

    @property
    def is_configured(self) -> bool:
        """Return True if bot token and chat ID are configured."""
        return bool(self._token and self._chat_id)

    def _endpoint(self, method: str) -> str:
        return f"{self._base_url}/bot{self._token}/{method}"

    def send_message(self, chat_id: int | str, text: str) -> None:
        """Send a plain text message to a specified Telegram chat."""
        if not self._token:
            log.warning("Telegram token missing; message omitted: %s", text)
            return

        url = self._endpoint("sendMessage")
        payload = {"chat_id": str(chat_id), "text": text}

        try:
            response = self._session.post(url, json=payload, timeout=self._timeout)
            try:
                data = response.json()
            except ValueError:
                snippet = response.text[:200].replace("\n", " ").strip()
                log.error("Telegram API returned non-JSON (%d): %s", response.status_code, snippet)
                return

            if response.status_code >= 400 or not data.get("ok"):
                log.error(
                    "Telegram error sending message (%d): %s",
                    response.status_code,
                    data.get("description", data),
                )
        except requests.RequestException as err:
            log.error("Network error sending Telegram message: %s", err)

    def notify(self, message: str) -> None:
        """Send notification to the configured operator chat."""
        if not self.is_configured:
            log.warning("Telegram not fully configured; notification omitted: %s", message)
            return
        self.send_message(self._chat_id, message)

    def get_updates(self, offset: int) -> list[dict[str, Any]]:
        """Fetch pending Telegram updates starting from offset."""
        if not self._token:
            return []

        url = self._endpoint("getUpdates")
        params = {"offset": offset, "timeout": 3}

        try:
            response = self._session.get(url, params=params, timeout=self._timeout)
            try:
                data = response.json()
            except ValueError:
                snippet = response.text[:200].replace("\n", " ").strip()
                log.error(
                    "Telegram getUpdates returned non-JSON (%d): %s",
                    response.status_code,
                    snippet,
                )
                return []

            if not data.get("ok"):
                log.error("Telegram getUpdates failed: %s", data.get("description", data))
                return []

            envelope = TelegramResponseDTO[list[TelegramUpdateDTO]].model_validate(data)
            if not envelope.result:
                return []

            return [
                u.model_dump(mode="python", by_alias=True)
                for u in envelope.result
            ]
        except requests.RequestException as err:
            log.error("Network error fetching Telegram updates: %s", err)
            return []
