"""Unit tests for credential redaction filter and logging configuration."""

import logging
from pathlib import Path

from pydantic import SecretStr

from trading_bot.core.logging import REDACTED, RedactFilter, configure_logging, redact


def test_redact_masks_secrets() -> None:
    """Verify secrets are replaced with the REDACTED placeholder."""
    text = "Connecting to https://api.bitso.com with key BITSO_KEY_123 and secret SECRET_456"
    secrets: list[str | SecretStr | None] = ["BITSO_KEY_123", SecretStr("SECRET_456")]

    result = redact(text, secrets)
    expected = f"Connecting to https://api.bitso.com with key {REDACTED} and secret {REDACTED}"
    assert result == expected


def test_redact_ignores_empty_and_none_secrets() -> None:
    """Verify empty strings and None values in secrets do not corrupt text."""
    text = "Regular message without secrets"
    result = redact(text, ["", None, SecretStr("")])
    assert result == text


def test_redact_empty_text() -> None:
    """Verify empty text passes through untouched."""
    assert redact("", ["secret"]) == ""


def test_redact_filter_masks_message_args() -> None:
    """Verify RedactFilter scrubs formatted log messages and arguments."""
    secret = "SUPER_SECRET_TOKEN"
    filter_ = RedactFilter([secret])

    logger = logging.getLogger("test_redact_args")
    logger.setLevel(logging.INFO)

    record = logger.makeRecord(
        name="test_logger",
        level=logging.INFO,
        fn="test_file.py",
        lno=10,
        msg="Error calling endpoint with token %s",
        args=(secret,),
        exc_info=None,
    )

    allowed = filter_.filter(record)
    assert allowed is True
    assert record.args == ()
    assert record.msg == f"Error calling endpoint with token {REDACTED}"


def test_redact_filter_masks_tracebacks() -> None:
    """Verify RedactFilter scrubs exceptions containing sensitive tokens."""
    secret_token = "TELEGRAM_BOT_TOKEN_XYZ"
    filter_ = RedactFilter([secret_token])

    logger = logging.getLogger("test_redact_traceback")

    try:
        raise ValueError(f"Failed to authenticate with token: {secret_token}")
    except ValueError:
        import sys

        exc_info = sys.exc_info()

    record = logger.makeRecord(
        name="test_logger",
        level=logging.ERROR,
        fn="test_file.py",
        lno=25,
        msg="Operation failed",
        args=(),
        exc_info=exc_info,
    )

    filter_.filter(record)
    assert record.exc_info is None
    assert record.exc_text is not None
    assert secret_token not in record.exc_text
    assert REDACTED in record.exc_text


def test_configure_logging_integration(tmp_path: Path) -> None:
    """Verify configure_logging properly creates log file and redacts sensitive data."""
    log_file = tmp_path / "logs" / "test_bot.log"
    secret_key = "MY_PRIVATE_API_KEY"

    configure_logging(log_file=log_file, secrets=[secret_key], level=logging.INFO)

    test_logger = logging.getLogger("integration_test")
    test_logger.info("Initializing exchange with key: %s", secret_key)

    # Flush all handlers
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert log_file.is_file()
    content = log_file.read_text(encoding="utf-8")
    assert secret_key not in content
    assert f"key: {REDACTED}" in content


def test_redact_filter_without_secrets() -> None:
    """Verify RedactFilter with empty secrets list does not alter records."""
    filter_ = RedactFilter([])
    logger = logging.getLogger("test_no_secrets")
    record = logger.makeRecord("test", logging.INFO, "f.py", 1, "test message", (), None)

    assert filter_.filter(record) is True
    assert record.msg == "test message"


def test_configure_logging_replaces_duplicate_handler(tmp_path: Path) -> None:
    """Verify calling configure_logging repeatedly updates handler without duplicating."""
    log_file = tmp_path / "dedup.log"
    configure_logging(log_file=log_file, secrets=["SEC1"])
    configure_logging(log_file=log_file, secrets=["SEC2"])

    matching = [
        h
        for h in logging.getLogger().handlers
        if isinstance(h, logging.FileHandler) and h.baseFilename == str(log_file.resolve())
    ]
    assert len(matching) == 1
