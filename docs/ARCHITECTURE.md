# ARCHITECTURE.md — System Design & Architectural Invariants

> **Note for AI Agents:** This document is governed by root `AGENTS.md`. Check `docs/PROGRESS.md` for current implementation status.

## 1. System Overview & Tech Stack
- **Runtime:** Python 3.11+
- **Architecture Pattern:** Hexagonal Architecture (Ports & Adapters) with `src-layout`.
- **Purpose:** Automated spot trading daemon for **BTC/MXN** on Bitso, driven by RSI-14 signals, multi-tiered risk controls, balance reconciliation, and Telegram command/alert integration.

## 2. Repository & Package Layout (`src-layout`)

```text
trading-bot/
├── pyproject.toml
├── AGENTS.md                        # Root AI Router & Core Guardrails
├── docs/
│   ├── ARCHITECTURE.md              # System topology & invariants (this file)
│   ├── PROGRESS.md                  # Phase-by-phase refactoring tracker
│   └── analisis_bot.md              # Initial architectural audit
├── src/
│   └── trading_bot/
│       ├── __init__.py
│       ├── py.typed
│       ├── config/
│       │   └── settings.py          # Pydantic BaseSettings (env/file boundary)
│       ├── core/
│       │   ├── exceptions.py        # DomainError, ExchangeError, ReconciliationError
│       │   ├── money.py             # Decimal quantization helpers
│       │   └── logging.py           # Structured logging + RedactFilter
│       ├── domain/                  # Pure Business Logic (Standard Lib ONLY)
│       │   ├── models.py            # @dataclass(frozen=True, slots=True) entities
│       │   ├── risk_engine.py       # Pure functions: sizing, PnL, stops, drawdown
│       │   └── signals.py           # Pure RSI threshold evaluation
│       ├── ports/                   # Abstract Interfaces (typing.Protocol)
│       │   ├── exchange.py          # ExchangePort
│       │   ├── notifier.py          # NotifierPort
│       │   ├── state_store.py       # StateStorePort
│       │   ├── signal_provider.py   # SignalProviderPort
│       │   └── trade_repository.py  # TradeRepositoryPort
│       ├── adapters/                # External I/O & Pydantic Payload Schemas
│       │   ├── bitso/
│       │   │   ├── schemas.py       # Pydantic models for Bitso JSON payloads
│       │   │   ├── client.py        # LiveBitsoAdapter (HTTP + HMAC)
│       │   │   └── paper.py         # PaperTradingAdapter (Dry-run simulation)
│       │   ├── telegram/
│       │   │   ├── schemas.py       # Pydantic models for Telegram updates
│       │   │   ├── client.py        # Telegram HTTP client
│       │   │   └── dispatcher.py    # Command router (/status, /stop, /resume)
│       │   ├── persistence/
│       │   │   ├── schemas.py       # Pydantic disk schemas for state.json
│       │   │   ├── json_state.py    # Atomic POSIX file persistence (os.replace)
│       │   │   └── sqlite_trades.py # SQLite WAL repository (TEXT Decimal storage)
│       │   └── indicators/
│       │       └── cached_rsi.py    # Pydantic-validated atomic RSI cache reader
│       └── application/             # Orchestration & Lifecycle
│           ├── state_manager.py     # Thread-safe coordinator returning frozen snapshots
│           ├── use_cases/
│           │   ├── reconcile.py     # Startup & daily balance reconciliation
│           │   └── process_tick.py  # Market tick evaluation & order execution flow
│           └── runner.py            # Entrypoint, SIGTERM/SIGINT handlers, thread loop
└── tests/
    ├── unit/                        # Fast, isolated domain & schema tests
    └── integration/                 # End-to-end tick flows, SQLite WAL, fault injection