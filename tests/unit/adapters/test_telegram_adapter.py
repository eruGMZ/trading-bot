"""Unit tests for Telegram adapter and command dispatcher."""

from decimal import Decimal
from typing import Any
from unittest import mock

import requests

from trading_bot.adapters.telegram.client import TelegramAdapter
from trading_bot.adapters.telegram.dispatcher import (
    TelegramCommandDispatcher,
    is_authorized_chat,
)
from trading_bot.domain.models import BotSnapshot, TradeMetrics


def _mock_res(
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


def test_is_authorized_chat() -> None:
    """Verify authorization checks string and int chat IDs accurately."""
    assert is_authorized_chat("123", "123") is True
    assert is_authorized_chat(123, "123") is True
    assert is_authorized_chat("123", 123) is True
    assert is_authorized_chat("999", "123") is False
    assert is_authorized_chat("123", "") is False
    assert is_authorized_chat("123", None) is False
    assert is_authorized_chat(None, "123") is False


def test_telegram_adapter_send_and_notify() -> None:
    """Verify TelegramAdapter sends HTTP POST to sendMessage."""
    mock_session = mock.Mock(spec=requests.Session)
    mock_session.post.return_value = _mock_res(
        200,
        json_data={"ok": True, "result": {"message_id": 1}},
    )

    adapter = TelegramAdapter(token="BOT_TOKEN", chat_id="12345", session=mock_session)
    assert adapter.is_configured is True

    adapter.notify("Test alert message")
    mock_session.post.assert_called_once()
    args, kwargs = mock_session.post.call_args
    assert "sendMessage" in args[0]
    assert kwargs["json"] == {"chat_id": "12345", "text": "Test alert message"}


def test_telegram_adapter_get_updates() -> None:
    """Verify TelegramAdapter parses incoming updates into validated dictionaries."""
    mock_session = mock.Mock(spec=requests.Session)
    mock_session.get.return_value = _mock_res(
        200,
        json_data={
            "ok": True,
            "result": [
                {
                    "update_id": 101,
                    "message": {
                        "message_id": 1,
                        "chat": {"id": 12345, "type": "private"},
                        "text": "/status",
                        "date": 1700000000,
                    },
                }
            ],
        },
    )

    adapter = TelegramAdapter(token="BOT_TOKEN", chat_id="12345", session=mock_session)
    updates = adapter.get_updates(offset=100)

    assert len(updates) == 1
    assert updates[0]["update_id"] == 101
    assert updates[0]["message"]["text"] == "/status"


def test_telegram_dispatcher_commands() -> None:
    """Verify TelegramCommandDispatcher handles standard commands."""
    dispatcher = TelegramCommandDispatcher(
        allowed_chat_id="12345",
        capital_ref_mxn=Decimal("5000"),
        daily_loss_pct=Decimal("0.03"),
        is_dry_run=True,
        mode_label="dry_run",
    )
    assert dispatcher.is_authorized("12345") is True
    assert dispatcher.is_authorized("99999") is False

    snap = BotSnapshot(
        running=True,
        mode="dry_run",
        position=None,
        pnl_total=Decimal("100"),
        pnl_today=Decimal("50"),
        trades_today=2,
        losses_today=0,
        peak_equity=Decimal("5100"),
    )

    # /status
    status_resp = dispatcher.dispatch("/status", snap)
    assert "DRY-RUN" in status_resp
    assert "Activo" in status_resp
    assert "2 trades hoy" in status_resp

    # /pnl
    pnl_resp = dispatcher.dispatch("/pnl", snap)
    assert "PnL hoy: +50 MXN" in pnl_resp

    # /stop and /start with state_controller mock
    mock_ctrl = mock.Mock()
    stop_resp = dispatcher.dispatch("/stop", snap, state_controller=mock_ctrl)
    assert "Bot detenido" in stop_resp
    mock_ctrl.set.assert_called_with(running=False)

    start_resp = dispatcher.dispatch("/start", snap, state_controller=mock_ctrl)
    assert "Bot reactivado" in start_resp
    mock_ctrl.set.assert_called_with(running=True)

    # /start blocked when halted
    halted_snap = BotSnapshot(
        running=False,
        mode="dry_run",
        position=None,
        pnl_total=Decimal("0"),
        pnl_today=Decimal("0"),
        trades_today=0,
        losses_today=0,
        peak_equity=Decimal("5000"),
        halt_reason="critical test halt",
    )
    blocked_resp = dispatcher.dispatch("/start", halted_snap, state_controller=mock_ctrl)
    assert "No puedo reactivar: bot bloqueado" in blocked_resp


def test_telegram_dispatcher_metrics() -> None:
    """Verify /metrics command retrieves performance metrics from repository."""
    dispatcher = TelegramCommandDispatcher(allowed_chat_id="12345")
    mock_repo = mock.Mock()
    mock_repo.get_metrics.return_value = TradeMetrics(
        total=5,
        win_rate=Decimal("80.00"),
        expectancy=Decimal("45.50"),
        profit_factor=Decimal("3.20"),
        max_drawdown_mxn=Decimal("60.00"),
        gross_profit=Decimal("250.00"),
        gross_loss=Decimal("-50.00"),
    )

    snap = BotSnapshot(
        running=True,
        mode="dry_run",
        position=None,
        pnl_total=Decimal("0"),
        pnl_today=Decimal("0"),
        trades_today=0,
        losses_today=0,
        peak_equity=Decimal("5000"),
    )

    resp = dispatcher.dispatch("/metrics", snap, trade_repo=mock_repo)
    assert "Win rate: 80%" in resp
    assert "Profit factor: 3.20" in resp
    assert "Max drawdown: -60 MXN" in resp
