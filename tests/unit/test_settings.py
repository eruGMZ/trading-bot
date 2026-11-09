"""Unit tests for BotSettings configuration and validation."""

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from trading_bot.config.settings import BotSettings, load_settings


def test_default_settings_instantiation() -> None:
    """Verify default values are correctly populated and strictly typed."""
    settings = BotSettings()

    assert settings.bot_mode == "dry_run"
    assert settings.is_dry_run is True
    assert settings.mode_tag == "[SIMULADO] "
    assert settings.book == "btc_mxn"
    assert settings.cdp_port == "9222"

    # Financial Precision: verify Decimal type
    assert isinstance(settings.capital_ref_mxn, Decimal)
    assert settings.capital_ref_mxn == Decimal("5000")
    assert isinstance(settings.risk_pct_per_trade, Decimal)
    assert settings.risk_pct_per_trade == Decimal("0.01")
    assert isinstance(settings.max_trade_mxn, Decimal)
    assert settings.max_trade_mxn == Decimal("500")
    assert isinstance(settings.daily_loss_pct, Decimal)
    assert settings.daily_loss_pct == Decimal("0.03")
    assert isinstance(settings.drawdown_kill_pct, Decimal)
    assert settings.drawdown_kill_pct == Decimal("0.10")
    assert isinstance(settings.max_spread_pct, Decimal)
    assert settings.max_spread_pct == Decimal("0.005")
    assert isinstance(settings.min_hours_between_trades, Decimal)
    assert settings.min_hours_between_trades == Decimal("1")
    assert isinstance(settings.stop_loss_pct, Decimal)
    assert settings.stop_loss_pct == Decimal("0.02")
    assert isinstance(settings.rsi_buy, Decimal)
    assert settings.rsi_buy == Decimal("30")
    assert isinstance(settings.rsi_sell, Decimal)
    assert settings.rsi_sell == Decimal("70")
    assert isinstance(settings.bitso_taker_fee, Decimal)
    assert settings.bitso_taker_fee == Decimal("0.0078")
    assert isinstance(settings.reconcile_dust_mxn, Decimal)
    assert settings.reconcile_dust_mxn == Decimal("10.0")

    # Operational guardrails
    assert settings.max_trades_day == 3
    assert settings.max_losses_day == 2
    assert settings.daily_report_hour == 23
    assert settings.trading_hours == ""
    assert settings.connection_timeout_min == 10


def test_bot_mode_normalization_and_operational() -> None:
    """Verify operational mode sets is_dry_run to False and handles case/whitespace."""
    settings = BotSettings(bot_mode=" OPERATIONAL ")
    assert settings.bot_mode == "operational"
    assert settings.is_dry_run is False
    assert settings.mode_tag == "[REAL] "


def test_invalid_bot_mode_raises_validation_error() -> None:
    """Verify invalid bot_mode values are strictly rejected."""
    with pytest.raises(ValidationError):
        BotSettings(bot_mode="sandbox")

    with pytest.raises(ValidationError):
        BotSettings(bot_mode="production")


def test_path_resolution_with_default_base_dir() -> None:
    """Verify paths resolve relative to default base_dir."""
    settings = BotSettings()
    expected_base = Path.cwd() / "data"

    assert settings.base_dir == expected_base
    assert settings.log_file == expected_base / "bot.log"
    assert settings.state_file == expected_base / "state.json"
    assert settings.cache_file == expected_base / "rsi_cache.json"
    assert settings.trade_log_file == expected_base / "trades.db"


def test_path_resolution_with_custom_base_dir(tmp_path: Path) -> None:
    """Verify paths automatically derive from a custom base_dir."""
    custom_dir = tmp_path / "custom_data"
    settings = BotSettings(base_dir=custom_dir)

    assert settings.base_dir == custom_dir
    assert settings.log_file == custom_dir / "bot.log"
    assert settings.state_file == custom_dir / "state.json"
    assert settings.cache_file == custom_dir / "rsi_cache.json"
    assert settings.trade_log_file == custom_dir / "trades.db"


def test_path_resolution_with_explicit_paths(tmp_path: Path) -> None:
    """Verify explicitly provided absolute and relative paths are preserved or resolved."""
    explicit_log = tmp_path / "custom.log"
    settings = BotSettings(
        base_dir=tmp_path,
        log_file=explicit_log,
        state_file=Path("nested/state.json"),
    )

    assert settings.log_file == explicit_log
    assert settings.state_file == tmp_path / "nested/state.json"


def test_decimal_coercion_from_string_and_float() -> None:
    """Verify numeric strings and floats are coerced to Decimal without precision loss."""
    settings = BotSettings(
        capital_ref_mxn="10000.50",
        risk_pct_per_trade="0.02",
        bitso_taker_fee="0.0065",
    )

    assert settings.capital_ref_mxn == Decimal("10000.50")
    assert settings.risk_pct_per_trade == Decimal("0.02")
    assert settings.bitso_taker_fee == Decimal("0.0065")


def test_bounds_validation_on_financial_fields() -> None:
    """Verify validation boundaries on risk and capital fields."""
    with pytest.raises(ValidationError):
        BotSettings(capital_ref_mxn=Decimal("0"))  # gt=0 required

    with pytest.raises(ValidationError):
        BotSettings(risk_pct_per_trade=Decimal("1.5"))  # le=1 required

    with pytest.raises(ValidationError):
        BotSettings(daily_loss_pct=Decimal("-0.01"))  # gt=0 required


def test_trading_hours_validation() -> None:
    """Verify trading_hours accepts valid format and rejects malformed strings."""
    # Valid formats
    assert BotSettings(trading_hours="").trading_hours == ""
    assert BotSettings(trading_hours="9-22").trading_hours == "9-22"
    assert BotSettings(trading_hours=" 0-24 ").trading_hours == "0-24"

    # Invalid formats
    with pytest.raises(ValidationError, match="Invalid trading_hours format"):
        BotSettings(trading_hours="invalid")

    with pytest.raises(ValidationError, match="Invalid trading_hours range"):
        BotSettings(trading_hours="22-9")  # start >= end

    with pytest.raises(ValidationError, match="Invalid trading_hours range"):
        BotSettings(trading_hours="9-25")  # end > 24


def test_alias_cdp_port_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify TRADINGVIEW_CDP_PORT alias works seamlessly."""
    monkeypatch.setenv("TRADINGVIEW_CDP_PORT", "9333")
    settings = BotSettings()
    assert settings.cdp_port == "9333"


def test_env_monkeypatching(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify environment variables are read by BotSettings."""
    monkeypatch.setenv("BOT_MODE", "operational")
    monkeypatch.setenv("CAPITAL_REF_MXN", "25000")
    monkeypatch.setenv("MAX_TRADE_MXN", "1500")
    monkeypatch.setenv("BITSO_API_KEY", "test_key_123")

    settings = BotSettings()
    assert settings.bot_mode == "operational"
    assert settings.capital_ref_mxn == Decimal("25000")
    assert settings.max_trade_mxn == Decimal("1500")
    assert settings.bitso_api_key.get_secret_value() == "test_key_123"


def test_load_settings_without_env_file(tmp_path: Path) -> None:
    """Verify load_settings factory functions cleanly without touching filesystem."""
    settings = load_settings(
        env_file=tmp_path / "non_existent.env",
        capital_ref_mxn=Decimal("7500"),
    )
    assert settings.capital_ref_mxn == Decimal("7500")


def test_load_settings_with_real_env_file(tmp_path: Path) -> None:
    """Verify load_settings correctly reads from an explicit .env file."""
    env_file = tmp_path / "custom.env"
    env_file.write_text("BOT_MODE=operational\nCAPITAL_REF_MXN=12345\n", encoding="utf-8")

    settings = load_settings(env_file=env_file)
    assert settings.bot_mode == "operational"
    assert settings.capital_ref_mxn == Decimal("12345")


def test_immutability() -> None:
    """Verify that settings are frozen and cannot be mutated at runtime."""
    settings = BotSettings()
    with pytest.raises(ValidationError):
        settings.bot_mode = "operational"  # type: ignore[misc]
