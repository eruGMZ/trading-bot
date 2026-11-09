# PROGRESS.md — Refactoring & Production-Readiness Tracker

**Branch:** `refactor/production-readiness`  
**Router:** See root `AGENTS.md` and `docs/ARCHITECTURE.md` before executing any task.

---

## Phase 0: Governance & Harness Setup
- [x] Complete architectural and code quality audit (`docs/analisis_bot.md`).
- [x] Create root `AGENTS.md` router with Python 3.11+ stack, Decimal rules, and `@dataclass` vs `Pydantic` boundaries.
- [x] Create `docs/ARCHITECTURE.md` defining the Hexagonal `src-layout`.
- [x] Create `docs/PROGRESS.md` for phase tracking.

## Phase 1: Packaging, Scaffolding & Config Boundary
- [x] Create `pyproject.toml` (`hatchling`, `pydantic`, `pydantic-settings`, `mypy --strict`, `ruff`, `pytest`).
- [x] Create directory tree under `src/trading_bot/` and `tests/{unit,integration}/`.
- [x] Implement `src/trading_bot/config/settings.py` using `pydantic-settings` (remove import-time `load_dotenv()` side effects and hardcoded user paths).
- [x] Migrate `logsafety.py` $\rightarrow$ `src/trading_bot/core/logging.py` with strict typing.

## Phase 2: Pure Domain Layer (`@dataclass` + `Decimal`)
- [x] Implement `src/trading_bot/core/money.py` and `src/trading_bot/core/exceptions.py`.
- [x] Define `@dataclass(frozen=True, slots=True)` models in `src/trading_bot/domain/models.py` (`Quote`, `Position`, `BotSnapshot`, `TradeMetrics`).
- [x] Refactor `risk.py` $\rightarrow$ `src/trading_bot/domain/risk_engine.py` (100% `Decimal`, English docstrings, zero I/O).
- [x] Refactor `signals.py` threshold logic $\rightarrow$ `src/trading_bot/domain/signals.py`.

## Phase 3: Ports & Infrastructure Adapters (`Pydantic` Boundaries)
- [x] Define `typing.Protocol` interfaces in `src/trading_bot/ports/`.
- [x] Implement `adapters/bitso/` (`schemas.py` with Pydantic, `LiveBitsoAdapter`, and `PaperTradingAdapter`).
- [x] Implement `adapters/persistence/json_state.py` (Pydantic disk validation + atomic `os.replace`) and `application/state_manager.py`.
- [x] Implement `adapters/persistence/sqlite_trades.py` (SQLite WAL mode + `TEXT` Decimal persistence).
- [x] Implement `adapters/indicators/cached_rsi.py` and update `rsi_updater` for atomic file writes.
- [x] Implement `adapters/telegram/` (`schemas.py`, `client.py`, `dispatcher.py`).

## Phase 4: Application Orchestration & Lifecycle
- [x] Extract `reconcile.py` and `process_tick.py` use cases with Dependency Injection.
- [x] Implement `runner.py` with `SIGTERM`/`SIGINT` handlers and `threading.Event` graceful shutdown.
- [x] Sanitize `scripts/` (`systemd` unit and shell scripts) to remove hardcoded paths.

## Phase 5: Verification & Test Suite Overhaul
- [x] Migrate and split `test_phase1.py` / `test_phase3.py` into `tests/unit/` and `tests/integration/`.
- [x] Add fault-injection tests (network timeouts mid-order, non-JSON 502 responses, atomic file contention).
- [x] Pass `ruff check`, `mypy --strict`, and `pytest -v` with zero warnings.
- [x] Prune all legacy monolithic root `.py` files and supersede with `src-layout` package.

---

## Status: COMPLETE 🎉
All 5 phases of the production-readiness refactoring roadmap are fully executed and verified:
- Clean Hexagonal Architecture (`src/trading_bot/`)
- 100% Strict Typing with `mypy --strict`
- Zero Linting Warnings with `ruff`
- 105 Automated Unit & Integration Tests (91% Package Coverage)
- Strict Financial Precision with `Decimal` arithmetic exclusively
- Concurrency Safety (POSIX atomic swaps, SQLite WAL mode)
- Zero Global Mutable State and Full Dependency Injection
