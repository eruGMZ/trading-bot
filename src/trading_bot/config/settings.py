"""Application settings and environment configuration.

Provides an immutable, strictly typed BotSettings model using pydantic-settings.
All financial, risk, and fee thresholds are enforced as Decimal types with zero
import-time side effects (no automatic file reads or network calls on import).
"""

from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BotMode = Literal["dry_run", "operational"]


class BotSettings(BaseSettings):
    """Immutable application settings loaded from environment or .env file."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    # ── Credentials & External Endpoints ─────────────────────────────────────
    bitso_api_key: SecretStr = Field(default=SecretStr(""))
    bitso_api_secret: SecretStr = Field(default=SecretStr(""))
    telegram_bot_token: SecretStr = Field(default=SecretStr(""))
    telegram_chat_id: str = Field(default="")
    cdp_port: str = Field(
        default="9222",
        validation_alias=AliasChoices("cdp_port", "tradingview_cdp_port"),
    )

    # ── Operating Mode & Market Pair ─────────────────────────────────────────
    bot_mode: BotMode = Field(default="dry_run")
    book: str = Field(default="btc_mxn")

    # ── Base Directory & Persistence Paths ───────────────────────────────────
    base_dir: Path = Field(default_factory=lambda: Path.cwd() / "data")
    log_file: Path | None = Field(default=None)
    state_file: Path | None = Field(default=None)
    cache_file: Path | None = Field(default=None)
    trade_log_file: Path | None = Field(default=None)

    # ── Financial Precision & Risk Limits (Decimal Only) ─────────────────────
    capital_ref_mxn: Decimal = Field(default=Decimal("5000"), gt=Decimal("0"))
    risk_pct_per_trade: Decimal = Field(default=Decimal("0.01"), gt=Decimal("0"), le=Decimal("1"))
    max_trade_mxn: Decimal = Field(default=Decimal("500"), gt=Decimal("0"))
    daily_loss_pct: Decimal = Field(default=Decimal("0.03"), gt=Decimal("0"), le=Decimal("1"))
    drawdown_kill_pct: Decimal = Field(default=Decimal("0.10"), gt=Decimal("0"), le=Decimal("1"))
    max_spread_pct: Decimal = Field(default=Decimal("0.005"), gt=Decimal("0"), le=Decimal("1"))
    min_hours_between_trades: Decimal = Field(default=Decimal("1"), ge=Decimal("0"))
    stop_loss_pct: Decimal = Field(default=Decimal("0.02"), gt=Decimal("0"), le=Decimal("1"))
    rsi_buy: Decimal = Field(default=Decimal("30"), ge=Decimal("0"), le=Decimal("100"))
    rsi_sell: Decimal = Field(default=Decimal("70"), ge=Decimal("0"), le=Decimal("100"))
    bitso_taker_fee: Decimal = Field(default=Decimal("0.0078"), ge=Decimal("0"), le=Decimal("1"))
    reconcile_dust_mxn: Decimal = Field(default=Decimal("10.0"), ge=Decimal("0"))

    # ── Operational Guardrails & Daily Windows ───────────────────────────────
    max_trades_day: int = Field(default=3, ge=1)
    max_losses_day: int = Field(default=2, ge=1)
    daily_report_hour: int = Field(default=23, ge=0, le=23)
    trading_hours: str = Field(default="")
    connection_timeout_min: int = Field(default=10, ge=1)

    # ── Polling & Cache Intervals ────────────────────────────────────────────
    cache_max_age_seconds: int = Field(default=120, ge=1)
    rsi_update_interval: int = Field(default=60, ge=1)
    loop_seconds: int = Field(default=60, ge=1)

    @field_validator("bot_mode", mode="before")
    @classmethod
    def _normalize_bot_mode(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("trading_hours")
    @classmethod
    def _validate_trading_hours(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            return ""
        parts = cleaned.split("-")
        if len(parts) != 2:
            raise ValueError(
                f"Invalid trading_hours format: {value!r}. Expected format 'HH-HH' (e.g. '9-22')."
            )
        try:
            start_h, end_h = int(parts[0]), int(parts[1])
        except ValueError as err:
            raise ValueError(f"Invalid integer in trading_hours: {value!r}.") from err
        if not (0 <= start_h <= 24 and 0 <= end_h <= 24 and start_h < end_h):
            raise ValueError(
                f"Invalid trading_hours range: {value!r}. "
                "Hours must be within 0-24 with start < end."
            )
        return cleaned

    @model_validator(mode="after")
    def _resolve_paths(self) -> Self:
        base = self.base_dir
        updates: dict[str, Path] = {}

        if self.log_file is None:
            updates["log_file"] = base / "bot.log"
        elif not self.log_file.is_absolute():
            updates["log_file"] = base / self.log_file

        if self.state_file is None:
            updates["state_file"] = base / "state.json"
        elif not self.state_file.is_absolute():
            updates["state_file"] = base / self.state_file

        if self.cache_file is None:
            updates["cache_file"] = base / "rsi_cache.json"
        elif not self.cache_file.is_absolute():
            updates["cache_file"] = base / self.cache_file

        if self.trade_log_file is None:
            updates["trade_log_file"] = base / "trades.db"
        elif not self.trade_log_file.is_absolute():
            updates["trade_log_file"] = base / self.trade_log_file

        for key, val in updates.items():
            object.__setattr__(self, key, val)
        return self

    @property
    def is_dry_run(self) -> bool:
        """Return True if running in simulated dry-run mode."""
        return self.bot_mode != "operational"

    @property
    def mode_tag(self) -> str:
        """Return log/notification prefix indicating operational mode."""
        return "[SIMULADO] " if self.is_dry_run else "[REAL] "


def load_settings(
    env_file: Path | str | None = None,
    **overrides: Any,
) -> BotSettings:
    """Factory to construct BotSettings with optional .env loading and explicit overrides.

    Args:
        env_file: Path to a .env file. If None, only environment variables are read.
        **overrides: Keyword arguments overriding any environment or .env values.

    Returns:
        An immutable, fully validated BotSettings instance.
    """
    effective_env_file: Path | str | None = env_file
    if effective_env_file is not None:
        path = Path(effective_env_file)
        if not path.is_file():
            effective_env_file = None

    init_kwargs: dict[str, Any] = dict(overrides)
    if effective_env_file is not None:
        init_kwargs["_env_file"] = effective_env_file

    return BotSettings(**init_kwargs)
