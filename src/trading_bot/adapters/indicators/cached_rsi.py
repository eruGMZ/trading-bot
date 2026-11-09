"""Atomic RSI cache file writer and reader implementing SignalProviderPort.

Provides Chrome DevTools Protocol (CDP) WebSocket connectivity to extract
real-time RSI indicator values from a local TradingView instance, persisting
them atomically to JSON cache for consumption by the trading daemon.
"""

import argparse
import contextlib
import json
import logging
import os
import signal
import tempfile
import threading
import time
from decimal import Decimal
from pathlib import Path
from types import FrameType
from typing import Final

import requests
import websocket
from pydantic import BaseModel, ConfigDict

from trading_bot.config.settings import BotSettings
from trading_bot.core.logging import configure_logging
from trading_bot.core.money import to_decimal
from trading_bot.domain.signals import validate_rsi
from trading_bot.ports.signal_provider import SignalProviderPort

log = logging.getLogger(__name__)

JS_GET_RSI: Final[str] = r"""
(function(){
    var rows = document.querySelectorAll("[class*='valueItem'],[class*='value-']");
    var vals = [];
    rows.forEach(function(el){
        var t = el.textContent.trim();
        if(t) vals.push(t);
    });
    var dotNumRe = /^[0-9]{1,2}\.[0-9]+$/;
    var rsi = null;
    for(var i=0; i<vals.length; i++){
        if(!dotNumRe.test(vals[i])) continue;
        var n = parseFloat(vals[i]);
        if(n >= 1 && n <= 100){
            rsi = n;
            break;
        }
    }
    return JSON.stringify({rsi: rsi});
})()
"""


class RsiCacheDTO(BaseModel):
    """Pydantic boundary DTO for the rsi_cache.json file."""

    model_config = ConfigDict(extra="ignore")

    rsi: Decimal
    timestamp: float


def save_rsi_cache(
    cache_file: Path,
    rsi: Decimal,
    timestamp: float | None = None,
) -> None:
    """Atomically write RSI value to JSON cache file using tempfile + os.replace.

    Prevents race conditions where consumers read 0-byte truncated files.
    """
    ts = time.time() if timestamp is None else timestamp
    payload = {"rsi": str(rsi), "timestamp": ts}
    parent = cache_file.parent
    parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=str(parent), prefix=".rsi-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, cache_file)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


class CachedRsiSignalProvider(SignalProviderPort):
    """Signal provider reading validated RSI values from atomic JSON cache."""

    def __init__(self, cache_file: Path, max_age_seconds: int = 120) -> None:
        self._cache_file = cache_file
        self._max_age = max_age_seconds

    def get_latest_rsi(self, now: float | None = None) -> tuple[Decimal, float] | None:
        """Read and validate the latest RSI from cache.

        Returns:
            (rsi_decimal, timestamp) tuple, or None if expired, corrupt, or invalid.
        """
        if not self._cache_file.is_file():
            return None

        try:
            content = self._cache_file.read_text(encoding="utf-8")
            raw = json.loads(content)
            dto = RsiCacheDTO.model_validate(raw)
        except Exception:
            return None

        current_time = time.time() if now is None else now
        age = current_time - dto.timestamp
        if age < 0 or age > self._max_age:
            return None

        validated_val = validate_rsi(dto.rsi)
        if validated_val is None:
            return None

        return validated_val, dto.timestamp


def get_chart_ws_url(
    cdp_port: str = "9222",
    host: str = "localhost",
    timeout: float = 3.0,
) -> str | None:
    """Discover the WebSocket debugger URL for the TradingView chart tab via CDP.

    Args:
        cdp_port: Remote debugging port for Chrome/TradingView.
        host: Hostname running the CDP server.
        timeout: Network timeout in seconds for HTTP endpoint query.

    Returns:
        WebSocket URL string, or None if unreachable or chart tab not found.
    """
    url = f"http://{host}:{cdp_port}/json"
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code != 200:
            log.warning("CDP endpoint %s returned HTTP status %s", url, response.status_code)
            return None
        pages = response.json()
        if not isinstance(pages, list):
            log.warning("CDP endpoint %s returned non-list JSON: %s", url, type(pages))
            return None
        page = next(
            (
                p
                for p in pages
                if isinstance(p, dict) and "tradingview.com/chart" in str(p.get("url", ""))
            ),
            None,
        )
        if not page:
            log.debug("No active TradingView chart page found on %s", url)
            return None
        ws_url = page.get("webSocketDebuggerUrl")
        return str(ws_url) if ws_url else None
    except requests.RequestException as err:
        log.warning("Failed to query CDP HTTP endpoint at %s: %s", url, err)
        return None
    except Exception as err:
        log.warning("Unexpected error querying CDP endpoint %s: %s", url, err)
        return None


def eval_js_runtime(
    ws_url: str,
    expression: str,
    timeout: float = 5.0,
) -> str | None:
    """Execute JavaScript expression via CDP WebSocket Runtime.evaluate.

    Args:
        ws_url: Target WebSocket debugger URL.
        expression: JavaScript snippet to evaluate in page context.
        timeout: WebSocket connection and evaluation timeout.

    Returns:
        String result value if evaluated successfully, or None on error/timeout.
    """
    ws = None
    try:
        ws = websocket.create_connection(ws_url, timeout=timeout)
        cmd = {
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": expression, "returnByValue": True},
        }
        ws.send(json.dumps(cmd))
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                ws.settimeout(2.0)
                msg = ws.recv()
                if not isinstance(msg, str):
                    continue
                data = json.loads(msg)
                if isinstance(data, dict) and data.get("id") == 1:
                    result_node = data.get("result", {})
                    if isinstance(result_node, dict):
                        inner = result_node.get("result", {})
                        if isinstance(inner, dict):
                            val = inner.get("value")
                            return str(val) if val is not None else None
                    return None
            except websocket.WebSocketTimeoutException:
                break
            except Exception as err:
                log.debug("Error while waiting for CDP response: %s", err)
                break
        return None
    except Exception as err:
        log.warning("CDP WebSocket evaluation failed on %s: %s", ws_url, err)
        return None
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception as err:
                log.debug("Error closing CDP WebSocket: %s", err)


def fetch_tradingview_rsi(
    cdp_port: str = "9222",
    host: str = "localhost",
    timeout: float = 3.0,
) -> Decimal | None:
    """Query TradingView chart via CDP, evaluate RSI script, and return Decimal RSI.

    Args:
        cdp_port: Remote debugging port for TradingView.
        host: Host running the TradingView instance.
        timeout: Network timeout in seconds.

    Returns:
        Validated Decimal RSI in [0, 100], or None if unavailable or invalid.
    """
    ws_url = get_chart_ws_url(cdp_port=cdp_port, host=host, timeout=timeout)
    if not ws_url:
        return None

    raw_eval = eval_js_runtime(ws_url=ws_url, expression=JS_GET_RSI, timeout=timeout)
    if not raw_eval:
        return None

    try:
        parsed = json.loads(raw_eval)
        if not isinstance(parsed, dict):
            return None
        rsi_val = parsed.get("rsi")
        if rsi_val is None:
            return None
        dec_candidate = to_decimal(rsi_val)
        return validate_rsi(dec_candidate)
    except Exception as err:
        log.warning("Failed to parse RSI value from CDP output %r: %s", raw_eval, err)
        return None


def run_rsi_updater(
    cache_file: Path | None = None,
    cdp_port: str | None = None,
    interval_seconds: int | None = None,
    max_iterations: int | None = None,
    stop_event: threading.Event | None = None,
    settings: BotSettings | None = None,
) -> int:
    """Run cooperative polling loop fetching RSI and updating JSON cache file.

    Args:
        cache_file: Optional path to rsi_cache.json.
        cdp_port: Optional CDP port string.
        interval_seconds: Optional polling interval in seconds.
        max_iterations: Optional maximum loop cycles before stopping.
        stop_event: Optional threading.Event to request loop shutdown.
        settings: Optional pre-loaded BotSettings instance.

    Returns:
        0 on success or graceful exit, 1 on unhandled fatal error.
    """
    cfg: BotSettings | None = settings
    if cfg is None:
        try:
            cfg = BotSettings()
        except Exception as err:
            log.warning("Could not load BotSettings: %s. Using default fallbacks.", err)

    target_cache_file = (
        cache_file
        or (cfg.cache_file if cfg is not None else None)
        or (Path.cwd() / "data" / "rsi_cache.json")
    )
    target_port = cdp_port or (cfg.cdp_port if cfg is not None else "9222")
    interval = (
        interval_seconds
        or (cfg.rsi_update_interval if cfg is not None else 60)
    )

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    if cfg is not None and cfg.log_file is not None:
        try:
            configure_logging(cfg.log_file)
        except Exception as err:
            log.warning("Could not configure file logging to %s: %s", cfg.log_file, err)

    shutdown_ev = stop_event or threading.Event()

    def _sig_handler(signum: int, _frame: FrameType | None) -> None:
        sig_name = signal.Signals(signum).name
        log.info("Received OS signal %s. Initiating graceful stop...", sig_name)
        shutdown_ev.set()

    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(ValueError, AttributeError):
                signal.signal(sig, _sig_handler)

    log.info(
        "Starting RSI updater loop (port=%s, interval=%ss, cache=%s)",
        target_port,
        interval,
        target_cache_file,
    )

    iterations = 0
    try:
        while not shutdown_ev.is_set():
            iterations += 1
            rsi = fetch_tradingview_rsi(cdp_port=target_port)
            if rsi is not None:
                try:
                    save_rsi_cache(target_cache_file, rsi=rsi)
                    log.info("RSI updated -> %s (persisted to %s)", rsi, target_cache_file)
                except Exception as err:
                    log.error("Failed to write RSI cache to %s: %s", target_cache_file, err)
            else:
                log.warning("TradingView RSI indicator not available on CDP port %s", target_port)

            if max_iterations is not None and iterations >= max_iterations:
                break

            if shutdown_ev.wait(timeout=float(interval)):
                break
    except KeyboardInterrupt:
        log.info("RSI updater interrupted by user. Stopping...")
    except Exception as err:
        log.critical("Unexpected error in RSI updater loop: %s", err, exc_info=True)
        return 1

    log.info("RSI updater stopped cleanly.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for rsi-updater entrypoint."""
    parser = argparse.ArgumentParser(
        description="Polls TradingView via Chrome DevTools Protocol (CDP) and writes RSI to cache."
    )
    parser.add_argument(
        "--port",
        dest="cdp_port",
        type=str,
        default=None,
        help="CDP remote debugging port (default: from settings or 9222)",
    )
    parser.add_argument(
        "--interval",
        dest="interval_seconds",
        type=int,
        default=None,
        help="Polling interval in seconds (default: from settings or 60)",
    )
    parser.add_argument(
        "--cache-file",
        dest="cache_file",
        type=Path,
        default=None,
        help="Path to output rsi_cache.json file (default: from settings)",
    )
    parser.add_argument(
        "--once",
        dest="once",
        action="store_true",
        help="Execute a single fetch and exit immediately.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI script entrypoint for rsi-updater console script."""
    try:
        args = parse_args(argv)
    except SystemExit as exc:
        if exc.code is None:
            return 0
        return int(exc.code) if isinstance(exc.code, int) else 2

    try:
        return run_rsi_updater(
            cache_file=args.cache_file,
            cdp_port=args.cdp_port,
            interval_seconds=args.interval_seconds,
            max_iterations=1 if args.once else None,
        )
    except KeyboardInterrupt:
        log.info("RSI updater interrupted by user. Stopping...")
        return 0
    except Exception as err:
        log.critical("Fatal crash during RSI updater execution: %s", err, exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
