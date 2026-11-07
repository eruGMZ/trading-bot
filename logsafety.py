"""Evita que secretos (tokens, API keys) aparezcan en los logs."""

import logging

REDACTED = "***"


def redact(text, secrets):
    """Sustituye cada secreto no vacío dentro de ``text`` por ``***``."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    return text


class RedactFilter(logging.Filter):
    def __init__(self, secrets):
        super().__init__()
        self._secrets = [s for s in secrets if s]

    def filter(self, record):
        message = record.getMessage()
        record.msg = redact(message, self._secrets)
        record.args = ()
        return True
