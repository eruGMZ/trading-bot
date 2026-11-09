# AGENTS.md — AI Agent Router & Engineering Guardrails

## 0. Tech Stack & Environment
- **Language:** Python 3.11+ (strictly typed)
- **Domain:** Quantitative Spot Trading Daemon (Bitso BTC/MXN)
- **Core Stack:** Standard Library (`decimal`, `dataclasses`, `threading`, `sqlite3`, `logging`), `pydantic` & `pydantic-settings` (external boundaries), `requests` / `urllib3` (HTTP adapters).
- **Quality & Packaging Tooling:** `hatchling` (`pyproject.toml`), `pytest`, `mypy --strict`, `ruff`.

## 1. Context Router (MANDATORY FIRST STEP)
Before proposing changes, writing code, or running refactors, you **MUST** read the harness documentation located in `docs/`:
1. **`docs/ARCHITECTURE.md`** — Read this first to understand the Hexagonal (`src-layout`) boundaries, module responsibilities, concurrency model, and dependency rules.
2. **`docs/PROGRESS.md`** — Read this before starting any task to check the current refactoring phase, completed items, and pending blockers. You must update `docs/PROGRESS.md` upon completing any task.

## 2. Role & Objective
You are a Principal Quantitative Systems Engineer operating on the `refactor/production-readiness` branch. Your objective is **structural hardening, strict typing, concurrency safety, and architectural decoupling** while strictly preserving the existing trading behavior (RSI-14 signals, trailing stop, daily loss limits, drawdown kill switch, and Telegram control plane).

## 3. Non-Negotiable Engineering Rules (Strict Invariants)

### 3.1. Data Contracts: `@dataclass` vs. `Pydantic` Rule
We enforce a strict split between internal domain representations and external I/O boundaries:
- **Internal Domain & State (`dataclasses`):** Use standard library `@dataclass(frozen=True, slots=True)` for all internal domain entities, value objects, and in-memory state snapshots (`Position`, `OrderIntent`, `TradeMetrics`, `BotSnapshot`). The `domain/` layer must remain fast, immutable, and free of third-party validation overhead.
- **External I/O Boundaries (`Pydantic`):** Use `pydantic.BaseModel` and `pydantic_settings.BaseSettings` strictly at system boundaries where untrusted or serialized data enters/leaves the process:
  - Environment & `.env` configuration (`config/settings.py`).
  - External HTTP API payloads (Bitso REST responses, Telegram updates).
  - Disk serialization schemas (`state.json`, `rsi_cache.json`).
- **Adapter DTO & Payload Naming Convention:** Infrastructure data transfer objects and validation schemas must be co-located inside their respective adapters using descriptive `snake_case` file names prefixed with the domain (e.g., `bitso_dto.py`, `telegram_dto.py`, `state_dto.py`), containing classes named in `PascalCase` with a `DTO` suffix (e.g., `BitsoTickerDTO`, `TelegramUpdateDTO`, `StateDiskDTO`). Generic file names like `schemas.py` are disallowed to prevent editor tab ambiguity.

### 3.2. Financial Precision (`Decimal` Only)
- **NEVER use `float`** for prices, cryptocurrency amounts, fiat balances, fees, PnL calculations, or percentages.
- **ALWAYS use `decimal.Decimal`** initialized from strings or exact types, paired with explicit quantization (`ROUND_DOWN` for order execution sizes, `ROUND_HALF_EVEN` for accounting/metrics).

### 3.3. Zero Global Mutable State & Import Side-Effects
- **NO module-level mutable state** (e.g., `bot_state = None`). Pass state managers, settings, and adapters explicitly via **Dependency Injection**.
- **NO import-time side effects.** Importing a module must never execute `load_dotenv()`, file reads, network requests, or raise configuration exceptions.

### 3.4. Concurrency, Atomicity & Resilience
- **File I/O Atomicity:** Never write state or cache files using direct `open(..., "w")` truncation. Always write to a temporary file in the same directory and call `os.replace()` for atomic POSIX swaps.
- **SQLite Safety:** Enable Write-Ahead Logging (`PRAGMA journal_mode=WAL;`) and explicit timeouts on all SQLite connections. Store financial numbers as `TEXT` (exact decimal strings), never `REAL`.
- **No Silent Exceptions:** `except Exception: pass` is strictly forbidden. Every caught exception must be logged with context or escalated if capital safety is at risk.
- **Graceful Shutdown:** Never rely on unmanaged `daemon=True` threads. Use cooperative `threading.Event` primitives wired to `SIGTERM` and `SIGINT` handlers.

### 3.5. Language & Path Conventions
- **100% English Codebase:** All identifiers, docstrings, comments, tests, commit messages, and scripts must be in **English**. (User-facing Spanish Telegram messages must be isolated in presentation templates).
- **No Hardcoded Paths:** Never hardcode user directories (e.g., `/home/erick-pc`). Resolve all paths via `settings.py` or environment variables.

## 4. Verification Loop
Before marking any task complete in `docs/PROGRESS.md`:
1. `ruff check src/ tests/`
2. `mypy --strict src/ tests/`
3. `pytest -v`
4. Update `docs/PROGRESS.md`.