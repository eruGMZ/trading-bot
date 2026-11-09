# BTC/MXN Quantitative Trading Daemon

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Type Checking: Mypy Strict](https://img.shields.io/badge/mypy-strict-brightgreen.svg)](https://mypy.readthedocs.io/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-black.svg)](https://github.com/astral-sh/ruff)
[![Architecture: Hexagonal](https://img.shields.io/badge/architecture-Hexagonal%20(Ports%20%26%20Adapters)-orange.svg)](docs/ARCHITECTURE.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

An institutional-grade, strictly typed spot trading daemon engineered for the **Bitso BTC/MXN** market. Built with modern Python 3.11+, standard library immutability, Hexagonal (`src-layout`) architecture, exact Decimal financial arithmetic, and robust capital-preservation guardrails.

---

## Key Highlights

- **Exact Financial Precision:** 100% `decimal.Decimal` precision for all currency balances, trade sizes, PnL, fees, and percentages. Zero floating-point drift (`ROUND_DOWN` for Bitcoin satoshis, `ROUND_HALF_EVEN` for fiat accounting).
- **Hexagonal Architecture (`src-layout`):** Total decoupling between pure domain logic, abstract boundary ports (`typing.Protocol`), infrastructure adapters (`pydantic` DTO boundaries), and application orchestration.
- **Resilient Concurrency & Lifecycle:** Thread-safe state coordination (`StateManager`), atomic POSIX file persistence (`tempfile` + `os.replace`), SQLite Write-Ahead Logging (`WAL`), and cooperative graceful shutdown (`SIGTERM`/`SIGINT` via `threading.Event`).
- **Comprehensive Risk Controls:** Dynamic volatility position sizing, high-watermark trailing stops, daily loss cutoff caps, global equity drawdown kill switch, and automated startup/daily balance reconciliation.
- **Telegram Control Plane:** Dedicated bi-directional Telegram polling listener for real-time trade alerts and operator remote control (`/status`, `/pause`, `/resume`, `/metrics`, `/close`).

---

## Architecture Overview

The daemon is structured following a strict **Hexagonal Architecture (Ports & Adapters)** pattern within a modular `src-layout`. For in-depth architectural contracts, component boundaries, and decoupling rules, please refer to [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Installation & Setup

### Prerequisites
- Linux / macOS
- Python 3.11 or higher
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/your-org/trading-bot.git
cd trading-bot
```

### 2. Configure Virtual Environment
```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### 3. Install Package with Development Tooling
Install the daemon in editable mode along with `pytest`, `mypy`, `ruff`, and testing dependencies:
```bash
pip install --upgrade pip
pip install -e ".[dev]"
```

---

## Configuration Guide

The daemon loads configuration from environment variables or a local `.env` file via `pydantic-settings`.

```bash
cp .env.example .env
chmod 600 .env
```

### Core Configuration Variables

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `BOT_MODE` | `str` | `dry_run` | Operating mode: `dry_run` (simulated execution) or `operational` (live capital). |
| `BITSO_API_KEY` | `SecretStr` | `""` | Bitso REST API key (requires *View balances* and *Place orders*). |
| `BITSO_API_SECRET` | `SecretStr` | `""` | Bitso HMAC-SHA256 API secret. |
| `TELEGRAM_BOT_TOKEN` | `SecretStr` | `""` | Telegram Bot API token obtained from `@BotFather`. |
| `TELEGRAM_CHAT_ID` | `str` | `""` | Authorized operator chat ID (commands from other IDs are rejected). |
| `CAPITAL_REF_MXN` | `Decimal` | `5000.00` | Reference capital in MXN used for position sizing and drawdown calculation. |
| `RISK_PCT_PER_TRADE` | `Decimal` | `0.01` | Risk fraction per trade (e.g. `0.01` = 1% capital risk). |
| `MAX_TRADE_MXN` | `Decimal` | `500.00` | Hard ceiling on individual order allocation size in MXN. |
| `STOP_LOSS_PCT` | `Decimal` | `0.02` | Stop-loss distance from entry (or high watermark for trailing stop). |
| `DAILY_LOSS_PCT` | `Decimal` | `0.03` | Maximum daily loss fraction (e.g. 3% cutoff halting new entries until tomorrow). |
| `DRAWDOWN_KILL_PCT` | `Decimal` | `0.10` | Global equity drawdown kill-switch threshold (e.g. 10% emergency exit & halt). |
| `MAX_SPREAD_PCT` | `Decimal` | `0.005` | Maximum bid/ask spread permitted (0.5% filter avoiding illiquid spikes). |
| `RSI_BUY` | `Decimal` | `30.0` | Oversold entry threshold. |
| `RSI_SELL` | `Decimal` | `70.0` | Overbought exit threshold. |
| `LOOP_SECONDS` | `int` | `60` | Market loop evaluation tick interval. |
| `RECONCILE_DUST_MXN` | `Decimal` | `10.0` | Allowable reconciliation balance variance before warning or halting. |

---

## Running the Application

### 1. Launch Trading Daemon
Run the main daemon using the installed console script:
```bash
# Using CLI script entrypoint
trading-bot

# Or directly via Python module
python -m trading_bot.application.runner
```

### 2. Launch RSI Indicator Cache Updater
When pairing with TradingView Desktop or an external market streamer:
```bash
# Using CLI script entrypoint
rsi-updater

# Or directly via Python module
python -m trading_bot.adapters.indicators.cached_rsi
```

### 3. Graceful Shutdown
The daemon cooperatively listens for `SIGINT` (Ctrl+C) and `SIGTERM` signals. Upon receipt, background worker threads cleanly finish their current operation, close database connections, persist state to disk, and notify the operator via Telegram before terminating.

---

## Remote Control Plane (Telegram)

When configured with an authorized `TELEGRAM_CHAT_ID`, the daemon supports operator commands:

- `/status` — View current operational state, open position, PnL today/total, and equity.
- `/pause` — Suspend new market entries without closing existing positions.
- `/resume` — Re-enable automated order execution.
- `/metrics` — Display historical performance (win rate, profit factor, expectancy, max drawdown).
- `/close` — Manually market-sell open position and update accounting records.
- `/help` — List available operator commands.

---

## Testing & Quality Gates

The project maintains 100% strict typing and a comprehensive automated test suite. Before any commit or deployment, the verification loop must pass with zero errors:

### Run Full Test Suite with Coverage
```bash
pytest -v --cov=src/trading_bot tests/
```

### Strict Type Checking
```bash
mypy --strict src/ tests/
```

### Fast Linting & Formatting Check
```bash
ruff check src/ tests/
```

---

## Special Thanks

Special thanks to [Aries Allen](https://github.com/Ariiies) for his key contributions, architectural guidance, and dedicated engineering efforts during the production-readiness refactoring and core system hardening.

---

## License

This project is licensed under the terms of the [MIT License](LICENSE).