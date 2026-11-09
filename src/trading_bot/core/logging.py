"""Logging configuration and credential redaction filter.

Ensures sensitive secrets (API keys, tokens) never appear in application logs
or exception tracebacks.
"""

import logging
import traceback
from collections.abc import Sequence
from pathlib import Path

from pydantic import SecretStr

REDACTED = "***"


def _extract_secret(secret: str | SecretStr | None) -> str:
    """Safely extract plain text from a string or SecretStr."""
    if secret is None:
        return ""
    if isinstance(secret, SecretStr):
        return secret.get_secret_value()
    return str(secret)


def redact(text: str, secrets: Sequence[str | SecretStr | None]) -> str:
    """Replace non-empty secret occurrences in text with REDACTED placeholder."""
    if not text:
        return text

    scrubbed = text
    for item in secrets:
        val = _extract_secret(item)
        if val:
            scrubbed = scrubbed.replace(val, REDACTED)
    return scrubbed


class RedactFilter(logging.Filter):
    """Logging filter that redacts credentials from messages, arguments, and tracebacks."""

    def __init__(self, secrets: Sequence[str | SecretStr | None] = ()) -> None:
        super().__init__()
        self._secrets: list[str] = [
            extracted
            for item in secrets
            if (extracted := _extract_secret(item))
        ]

    def _scrub(self, text: str) -> str:
        return redact(text, self._secrets)

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log record by scrubbing sensitive tokens from message and exception info."""
        if not self._secrets:
            return True

        # Scrub formatted message and clear args to prevent re-formatting
        try:
            record.msg = self._scrub(record.getMessage())
            record.args = ()
        except Exception:
            # Fallback if getMessage fails on non-standard formatting
            record.msg = self._scrub(str(record.msg))

        # Scrub existing formatted traceback string
        if record.exc_text:
            record.exc_text = self._scrub(record.exc_text)

        # Pre-format and scrub pending exception info before Formatter formats it
        if record.exc_info and record.exc_info[1] is not None:
            record.exc_text = self._scrub(
                "".join(traceback.format_exception(*record.exc_info))
            )
            record.exc_info = None

        return True


def configure_logging(
    log_file: Path,
    secrets: Sequence[str | SecretStr | None] = (),
    level: int = logging.INFO,
) -> None:
    """Configure root logging with a redacted UTF-8 file handler.

    Args:
        log_file: Destination file path for log entries.
        secrets: Sequence of sensitive strings or SecretStr objects to redact.
        level: Minimum log level for root logger.
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(str(log_file), encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    handler.addFilter(RedactFilter(secrets))

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers if configure_logging is called multiple times
    for existing in list(root.handlers):
        if isinstance(existing, logging.FileHandler) and existing.baseFilename == str(
            log_file.resolve()
        ):
            root.removeHandler(existing)

    root.addHandler(handler)
