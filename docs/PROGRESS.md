# PROGRESS.md — Project Status & Roadmap

**Branch:** `refactor/production-readiness`  
**Router:** See root `AGENTS.md` and `docs/ARCHITECTURE.md` before executing any task.

---

## Current Status

The core production-readiness refactoring and post-audit hardening are complete: the daemon operates under a decoupled Hexagonal architecture with strict static typing (`mypy --strict`), zero lint warnings (`ruff`), 100% `Decimal` financial precision, and a fully passing test suite (118 unit and integration tests), establishing a hardened, production-ready baseline that is ready for deployment but awaiting further feature development.

---

## Next Steps & Future Development

While the core trading engine, safety invariants, and execution infrastructure are fully operational and verified, the platform is staged for the following future developments:

- **Strategy Expansion & Multi-Indicator Signals:** Incorporate multi-timeframe momentum filters, trend indicators (e.g., MACD, EMA ribbons), and modular strategy pipelines beyond the baseline RSI-14 threshold model.
- **Backtesting & Simulation Pipeline:** Wire historical market replays and parameter grid search directly into the decoupled domain risk engine.
- **Multi-Pair & Multi-Exchange Support:** Extend port adapters to support additional currency pairs and alternative liquidity providers beyond Bitso BTC/MXN.
- **Advanced Order Execution:** Implement dynamic order slicing, slippage mitigation, and taker fee optimization algorithms.
- **Telemetry & Operational Monitoring:** Add structured Prometheus metrics scraping, health probe endpoints, and enhanced remote administration commands via Telegram.
