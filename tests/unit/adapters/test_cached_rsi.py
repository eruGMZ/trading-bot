"""Unit tests for atomic RSI cache persistence, provider, and CLI updater."""

import threading
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest import mock

import requests
import websocket

from trading_bot.adapters.indicators.cached_rsi import (
    CachedRsiSignalProvider,
    eval_js_runtime,
    fetch_tradingview_rsi,
    get_chart_ws_url,
    main,
    run_rsi_updater,
    save_rsi_cache,
)


def _mock_http_response(
    status_code: int = 200,
    json_data: Any = None,
) -> mock.Mock:
    res = mock.Mock(spec=requests.Response)
    res.status_code = status_code
    if json_data is not None:
        res.json.return_value = json_data
    else:
        res.json.side_effect = ValueError("No JSON")
    return res


def test_save_and_read_rsi_cache(tmp_path: Path) -> None:
    """Verify save_rsi_cache atomically creates valid JSON readable by provider."""
    cache_file = tmp_path / "rsi_cache.json"
    save_rsi_cache(cache_file, rsi=Decimal("29.86"), timestamp=1000.0)

    provider = CachedRsiSignalProvider(cache_file, max_age_seconds=120)
    result = provider.get_latest_rsi(now=1050.0)

    assert result is not None
    rsi_val, ts = result
    assert rsi_val == Decimal("29.86")
    assert ts == 1000.0


def test_cached_rsi_missing_file(tmp_path: Path) -> None:
    """Verify provider returns None if cache file does not exist."""
    cache_file = tmp_path / "nonexistent.json"
    provider = CachedRsiSignalProvider(cache_file)
    assert provider.get_latest_rsi() is None


def test_cached_rsi_expired(tmp_path: Path) -> None:
    """Verify provider returns None when cache exceeds max_age_seconds."""
    cache_file = tmp_path / "rsi_cache.json"
    save_rsi_cache(cache_file, rsi=Decimal("50.00"), timestamp=1000.0)

    provider = CachedRsiSignalProvider(cache_file, max_age_seconds=60)
    assert provider.get_latest_rsi(now=1061.0) is None


def test_cached_rsi_future_timestamp(tmp_path: Path) -> None:
    """Verify provider returns None when timestamp is in the future."""
    cache_file = tmp_path / "rsi_cache.json"
    save_rsi_cache(cache_file, rsi=Decimal("50.00"), timestamp=2000.0)

    provider = CachedRsiSignalProvider(cache_file, max_age_seconds=60)
    assert provider.get_latest_rsi(now=1000.0) is None


def test_cached_rsi_out_of_bounds(tmp_path: Path) -> None:
    """Verify provider returns None when RSI is invalid or out of [0, 100]."""
    cache_file = tmp_path / "rsi_cache.json"
    cache_file.write_text('{"rsi": "105.0", "timestamp": 1000.0}', encoding="utf-8")

    provider = CachedRsiSignalProvider(cache_file)
    assert provider.get_latest_rsi(now=1010.0) is None


def test_cached_rsi_corrupted_json(tmp_path: Path) -> None:
    """Verify provider handles corrupted JSON gracefully."""
    cache_file = tmp_path / "rsi_cache.json"
    cache_file.write_text('{broken json', encoding="utf-8")

    provider = CachedRsiSignalProvider(cache_file)
    assert provider.get_latest_rsi(now=1010.0) is None


def test_get_chart_ws_url_success() -> None:
    """Verify get_chart_ws_url extracts debugger URL from TradingView tab."""
    mock_pages = [
        {"url": "https://www.google.com", "webSocketDebuggerUrl": "ws://other"},
        {
            "url": "https://www.tradingview.com/chart/abcd/",
            "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/123",
        },
    ]
    with mock.patch("requests.get", return_value=_mock_http_response(200, mock_pages)):
        ws_url = get_chart_ws_url(cdp_port="9222")
        assert ws_url == "ws://localhost:9222/devtools/page/123"


def test_get_chart_ws_url_not_found_or_error() -> None:
    """Verify get_chart_ws_url returns None on missing chart tab or HTTP error."""
    mock_pages = [{"url": "https://www.google.com", "webSocketDebuggerUrl": "ws://other"}]
    with mock.patch("requests.get", return_value=_mock_http_response(200, mock_pages)):
        assert get_chart_ws_url(cdp_port="9222") is None

    with mock.patch("requests.get", return_value=_mock_http_response(500, [])):
        assert get_chart_ws_url(cdp_port="9222") is None

    with mock.patch("requests.get", side_effect=requests.RequestException("Unreachable")):
        assert get_chart_ws_url(cdp_port="9222") is None


def test_eval_js_runtime_success() -> None:
    """Verify eval_js_runtime sends command and parses result value."""
    mock_ws = mock.Mock()
    mock_ws.recv.return_value = '{"id": 1, "result": {"result": {"value": "{\\"rsi\\": 33.5}"}}}'

    with mock.patch("websocket.create_connection", return_value=mock_ws):
        res = eval_js_runtime("ws://localhost:9222", expression="console.log(1)")
        assert res == '{"rsi": 33.5}'
        mock_ws.close.assert_called_once()


def test_eval_js_runtime_timeout_or_error() -> None:
    """Verify eval_js_runtime returns None when websocket times out or errors."""
    mock_ws = mock.Mock()
    mock_ws.recv.side_effect = websocket.WebSocketTimeoutException("Timeout")

    with mock.patch("websocket.create_connection", return_value=mock_ws):
        assert eval_js_runtime("ws://localhost:9222", expression="test()") is None
        mock_ws.close.assert_called_once()

    with mock.patch("websocket.create_connection", side_effect=Exception("WS connect failed")):
        assert eval_js_runtime("ws://localhost:9222", expression="test()") is None


def test_fetch_tradingview_rsi_success() -> None:
    """Verify fetch_tradingview_rsi orchestrates discovery, evaluation, and Decimal validation."""
    with (
        mock.patch(
            "trading_bot.adapters.indicators.cached_rsi.get_chart_ws_url",
            return_value="ws://localhost:9222/page",
        ),
        mock.patch(
            "trading_bot.adapters.indicators.cached_rsi.eval_js_runtime",
            return_value='{"rsi": 41.75}',
        ),
    ):
        val = fetch_tradingview_rsi(cdp_port="9222")
        assert val == Decimal("41.75")


def test_fetch_tradingview_rsi_invalid_payloads() -> None:
    """Verify fetch_tradingview_rsi rejects out-of-bounds, null, or corrupted RSI."""
    with (
        mock.patch(
            "trading_bot.adapters.indicators.cached_rsi.get_chart_ws_url",
            return_value="ws://localhost:9222/page",
        ),
        mock.patch(
            "trading_bot.adapters.indicators.cached_rsi.eval_js_runtime",
            return_value='{"rsi": 125.0}',
        ),
    ):
        assert fetch_tradingview_rsi(cdp_port="9222") is None

    with (
        mock.patch(
            "trading_bot.adapters.indicators.cached_rsi.get_chart_ws_url",
            return_value=None,
        ),
    ):
        assert fetch_tradingview_rsi(cdp_port="9222") is None


def test_main_runs_single_iteration_and_saves_cache(tmp_path: Path) -> None:
    """Verify main() entrypoint with --once flag persists RSI and exits cleanly with 0."""
    target_cache = tmp_path / "rsi_cache.json"

    with mock.patch(
        "trading_bot.adapters.indicators.cached_rsi.fetch_tradingview_rsi",
        return_value=Decimal("31.25"),
    ):
        exit_code = main(["--once", "--port", "9222", "--cache-file", str(target_cache)])
        assert exit_code == 0

    assert target_cache.is_file()
    provider = CachedRsiSignalProvider(target_cache, max_age_seconds=60)
    data = provider.get_latest_rsi()
    assert data is not None
    assert data[0] == Decimal("31.25")


def test_main_single_iteration_indicator_unavailable(tmp_path: Path) -> None:
    """Verify main() handles indicator absence gracefully without crash."""
    target_cache = tmp_path / "rsi_cache.json"

    with mock.patch(
        "trading_bot.adapters.indicators.cached_rsi.fetch_tradingview_rsi",
        return_value=None,
    ):
        exit_code = main(["--once", "--cache-file", str(target_cache)])
        assert exit_code == 0

    assert not target_cache.exists()


def test_main_handles_keyboard_interrupt() -> None:
    """Verify main() catches KeyboardInterrupt and exits cleanly with code 0."""
    with mock.patch(
        "trading_bot.adapters.indicators.cached_rsi.run_rsi_updater",
        side_effect=KeyboardInterrupt,
    ):
        assert main(["--once"]) == 0


def test_main_handles_fatal_exception() -> None:
    """Verify main() catches unexpected exceptions and returns code 1."""
    with mock.patch(
        "trading_bot.adapters.indicators.cached_rsi.run_rsi_updater",
        side_effect=RuntimeError("Fatal error"),
    ):
        assert main(["--once"]) == 1


def test_main_cli_help() -> None:
    """Verify main() handles --help by exiting cleanly with code 0."""
    assert main(["--help"]) == 0


def test_main_cli_invalid_arg() -> None:
    """Verify main() handles unrecognized flags by returning code 2."""
    assert main(["--unknown-flag-xyz"]) == 2


def test_run_rsi_updater_cooperative_shutdown(tmp_path: Path) -> None:
    """Verify run_rsi_updater stops immediately when stop_event is set."""
    stop_ev = threading.Event()
    stop_ev.set()
    exit_code = run_rsi_updater(
        cache_file=tmp_path / "cache.json",
        stop_event=stop_ev,
    )
    assert exit_code == 0
