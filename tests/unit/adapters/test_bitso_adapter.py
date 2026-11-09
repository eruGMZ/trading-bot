"""Unit tests for Bitso REST and Paper trading exchange adapters."""

from decimal import Decimal
from typing import Any
from unittest import mock

import pytest
import requests

from trading_bot.adapters.bitso.client import LiveBitsoAdapter
from trading_bot.adapters.bitso.paper import PaperTradingAdapter
from trading_bot.adapters.bitso.schemas import BitsoTickerPayload
from trading_bot.core.exceptions import ExchangeError
from trading_bot.domain.models import Quote


def _mock_response(
    status_code: int = 200,
    json_data: dict[str, Any] | None = None,
    text: str = "",
) -> mock.Mock:
    res = mock.Mock(spec=requests.Response)
    res.status_code = status_code
    if json_data is not None:
        res.json.return_value = json_data
        res.text = str(json_data)
    else:
        res.json.side_effect = ValueError("No JSON")
        res.text = text
    return res


def test_bitso_ticker_schema_and_spread() -> None:
    """Verify BitsoTickerPayload calculates spread_pct automatically."""
    data = {
        "book": "btc_mxn",
        "last": "1000000.00",
        "bid": "995000.00",
        "ask": "1005000.00",
    }
    ticker = BitsoTickerPayload.model_validate(data)
    assert ticker.last == Decimal("1000000.00")
    # spread = (1005000 - 995000) / 1005000 = 10000 / 1005000
    expected_spread = Decimal("10000") / Decimal("1005000")
    assert ticker.spread_pct == expected_spread


def test_live_bitso_get_quote() -> None:
    """Verify LiveBitsoAdapter.get_quote returns a Quote with Decimal fields."""
    mock_session = mock.Mock(spec=requests.Session)
    mock_session.request.return_value = _mock_response(
        status_code=200,
        json_data={
            "success": True,
            "payload": {
                "book": "btc_mxn",
                "last": "1200000.50",
                "bid": "1199000.00",
                "ask": "1201000.00",
            },
        },
    )

    client = LiveBitsoAdapter("test_key", "test_secret", session=mock_session)
    quote = client.get_quote("btc_mxn")

    assert isinstance(quote, Quote)
    assert quote.symbol == "btc_mxn"
    assert quote.last == Decimal("1200000.50")
    assert quote.bid == Decimal("1199000.00")
    assert quote.ask == Decimal("1201000.00")
    assert quote.spread_pct > Decimal("0")


def test_live_bitso_get_available_balance() -> None:
    """Verify LiveBitsoAdapter.get_available_balance parses currencies accurately."""
    mock_session = mock.Mock(spec=requests.Session)
    mock_session.request.return_value = _mock_response(
        status_code=200,
        json_data={
            "success": True,
            "payload": {
                "balances": [
                    {"currency": "btc", "available": "0.12345678", "locked": "0.0"},
                    {"currency": "mxn", "available": "5000.50", "locked": "0.0"},
                ]
            },
        },
    )

    client = LiveBitsoAdapter("test_key", "test_secret", session=mock_session)
    btc_bal = client.get_available_balance("btc")
    mxn_bal = client.get_available_balance("mxn")
    eth_bal = client.get_available_balance("eth")

    assert btc_bal == Decimal("0.12345678")
    assert mxn_bal == Decimal("5000.50")
    assert eth_bal == Decimal("0")


def test_live_bitso_place_order_buy_and_sell() -> None:
    """Verify LiveBitsoAdapter.place_order creates expected payload and returns oid."""
    mock_session = mock.Mock(spec=requests.Session)
    mock_session.request.return_value = _mock_response(
        status_code=200,
        json_data={"success": True, "payload": {"oid": "ord_12345"}},
    )

    client = LiveBitsoAdapter("test_key", "test_secret", session=mock_session)

    # Buy order
    buy_oid = client.place_order("btc_mxn", "buy", amount_mxn=Decimal("500.00"))
    assert buy_oid == "ord_12345"

    # Sell order
    sell_oid = client.place_order("btc_mxn", "sell", amount_btc=Decimal("0.0005"))
    assert sell_oid == "ord_12345"

    # Validation errors
    with pytest.raises(ValueError, match="Buy order requires amount_mxn > 0"):
        client.place_order("btc_mxn", "buy", amount_mxn=Decimal("0"))

    with pytest.raises(ValueError, match="Sell order requires amount_btc > 0"):
        client.place_order("btc_mxn", "sell", amount_btc=Decimal("0"))

    with pytest.raises(ValueError, match="Invalid order side"):
        client.place_order("btc_mxn", "invalid", amount_mxn=Decimal("500"))


def test_live_bitso_non_json_error() -> None:
    """Verify Cloudflare HTML 502/503 responses raise custom ExchangeError gracefully."""
    mock_session = mock.Mock(spec=requests.Session)
    mock_session.request.return_value = _mock_response(
        status_code=502,
        json_data=None,
        text="<html><body>502 Bad Gateway</body></html>",
    )

    client = LiveBitsoAdapter("test_key", "test_secret", session=mock_session)
    with pytest.raises(ExchangeError, match="Invalid non-JSON response from Bitso"):
        client.get_quote("btc_mxn")


def test_live_bitso_api_error_response() -> None:
    """Verify Bitso error payload raises ExchangeError."""
    mock_session = mock.Mock(spec=requests.Session)
    mock_session.request.return_value = _mock_response(
        status_code=400,
        json_data={
            "success": False,
            "error": {"code": "0101", "message": "Insufficient balance"},
        },
    )

    client = LiveBitsoAdapter("test_key", "test_secret", session=mock_session)
    with pytest.raises(ExchangeError, match="Bitso API error"):
        client.place_order("btc_mxn", "buy", amount_mxn=Decimal("500"))


def test_paper_trading_adapter() -> None:
    """Verify PaperTradingAdapter simulates orders and maintains in-memory balances."""
    paper = PaperTradingAdapter(
        initial_mxn=Decimal("5000.00"),
        initial_btc=Decimal("0.00000000"),
    )

    quote = paper.get_quote("btc_mxn")
    assert quote.last == Decimal("1000000.00")
    assert paper.get_available_balance("mxn") == Decimal("5000.00")
    assert paper.get_available_balance("btc") == Decimal("0.00000000")

    # Buy 1000 MXN -> should decrease MXN and increase BTC
    buy_oid = paper.place_order("btc_mxn", "buy", amount_mxn=Decimal("1000.00"))
    assert buy_oid.startswith("sim_ord_")
    assert paper.get_available_balance("mxn") == Decimal("4000.00")
    assert paper.get_available_balance("btc") > Decimal("0")

    # Sell all BTC
    btc_to_sell = paper.get_available_balance("btc")
    sell_oid = paper.place_order("btc_mxn", "sell", amount_btc=btc_to_sell)
    assert sell_oid.startswith("sim_ord_")
    assert paper.get_available_balance("btc") == Decimal("0.00000000")
    assert paper.get_available_balance("mxn") > Decimal("4000.00")
