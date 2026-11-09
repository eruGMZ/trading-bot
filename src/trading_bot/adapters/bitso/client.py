"""Live Bitso HTTP client implementing ExchangePort."""

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Any

import requests
from pydantic import SecretStr
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from trading_bot.adapters.bitso.bitso_dto import (
    BitsoApiResponseDTO,
    BitsoBalanceDTO,
    BitsoOrderDTO,
    BitsoTickerDTO,
)
from trading_bot.core.exceptions import ExchangeError
from trading_bot.core.money import format_btc, format_mxn
from trading_bot.domain.models import Quote
from trading_bot.ports.exchange import ExchangePort

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.bitso.com"
DEFAULT_TIMEOUT = 10.0


class LiveBitsoAdapter(ExchangePort):
    """Production Bitso exchange adapter communicating via REST API with HMAC auth."""

    def __init__(
        self,
        api_key: str | SecretStr,
        api_secret: str | SecretStr,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
    ) -> None:
        self._key = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        self._secret = (
            api_secret.get_secret_value() if isinstance(api_secret, SecretStr) else api_secret
        )
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

        if session is not None:
            self._session = session
        else:
            self._session = requests.Session()
            retries = Retry(
                total=3,
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
                raise_on_status=False,
            )
            adapter = HTTPAdapter(max_retries=retries)
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)

    def _sign(self, method: str, path: str, payload: str = "") -> dict[str, str]:
        """Generate Bitso HMAC-SHA256 signature headers."""
        nonce = str(int(time.time() * 1000))
        message = nonce + method.upper() + path + payload
        signature = hmac.new(
            self._secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return {
            "Authorization": f"Bitso {self._key}:{nonce}:{signature}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        auth_required: bool = True,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute HTTP request with error handling and non-JSON resilience."""
        url = f"{self._base_url}{path}"
        body = json.dumps(payload) if payload is not None else ""
        headers = self._sign(method, path, body) if auth_required else {}
        if not auth_required and payload is not None:
            headers["Content-Type"] = "application/json"

        try:
            response = self._session.request(
                method=method,
                url=url,
                headers=headers,
                data=body if body else None,
                timeout=self._timeout,
            )
        except requests.RequestException as err:
            raise ExchangeError(f"Network error contacting Bitso ({url}): {err}") from err

        # Handle non-JSON responses (e.g. Cloudflare 502/503 HTML pages)
        try:
            data = response.json()
        except ValueError as err:
            snippet = response.text[:250].replace("\n", " ").strip()
            raise ExchangeError(
                f"Invalid non-JSON response from Bitso (HTTP {response.status_code}): {snippet}"
            ) from err

        if response.status_code >= 400 or not data.get("success"):
            err_detail = data.get("error", {})
            msg = err_detail.get("message") if isinstance(err_detail, dict) else str(err_detail)
            code = err_detail.get("code") if isinstance(err_detail, dict) else "unknown"
            raise ExchangeError(
                f"Bitso API error [code={code}] (HTTP {response.status_code}): {msg or data}"
            )

        return data  # type: ignore[no-any-return]

    def get_quote(self, book: str = "btc_mxn") -> Quote:
        """Fetch and parse current ticker into domain Quote."""
        path = f"/v3/ticker/?book={book}"
        raw_data = self._request("GET", path, auth_required=False)
        envelope = BitsoApiResponseDTO[BitsoTickerDTO].model_validate(raw_data)

        if envelope.payload is None:
            raise ExchangeError(f"Ticker response missing payload: {raw_data}")

        p = envelope.payload
        return Quote(
            symbol=p.book,
            last=p.last,
            bid=p.bid,
            ask=p.ask,
            spread_pct=p.spread_pct,
            timestamp=datetime.now(),
        )

    def get_available_balance(self, asset: str) -> Decimal:
        """Fetch available balance for currency asset (e.g. 'btc' or 'mxn')."""
        path = "/v3/balance/"
        raw_data = self._request("GET", path, auth_required=True)
        envelope = BitsoApiResponseDTO[BitsoBalanceDTO].model_validate(raw_data)

        if envelope.payload is None:
            raise ExchangeError(f"Balance response missing payload: {raw_data}")

        target = asset.lower()
        for item in envelope.payload.balances:
            if item.currency.lower() == target:
                return item.available

        return Decimal("0")

    def place_order(
        self,
        book: str,
        side: str,
        amount_btc: Decimal | None = None,
        amount_mxn: Decimal | None = None,
    ) -> str:
        """Place a market order on Bitso and return order ID."""
        order_side = side.lower().strip()
        order_body: dict[str, Any] = {
            "book": book,
            "side": order_side,
            "type": "market",
        }

        if order_side == "buy":
            if amount_mxn is None or amount_mxn <= Decimal("0"):
                raise ValueError("Buy order requires amount_mxn > 0")
            order_body["minor"] = format_mxn(amount_mxn)
        elif order_side == "sell":
            if amount_btc is None or amount_btc <= Decimal("0"):
                raise ValueError("Sell order requires amount_btc > 0")
            order_body["major"] = format_btc(amount_btc)
        else:
            raise ValueError(f"Invalid order side: {side!r}")

        path = "/v3/orders/"
        raw_data = self._request("POST", path, auth_required=True, payload=order_body)
        envelope = BitsoApiResponseDTO[BitsoOrderDTO].model_validate(raw_data)

        if envelope.payload is None or not envelope.payload.oid:
            raise ExchangeError(f"Bitso accepted order but returned no order ID: {raw_data}")

        oid = envelope.payload.oid
        log.info("Bitso order accepted oid=%s [%s on %s]", oid, order_side, book)
        return oid
