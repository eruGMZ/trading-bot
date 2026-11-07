"""Evita que secretos (tokens, API keys) aparezcan en los logs."""

import logging
import traceback

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

    def _scrub(self, text):
        return redact(text, self._secrets) if text else text

    def filter(self, record):
        # Cubre mensajes donde el token aparece via %s (ej: str(urllib3_exception))
        record.msg = self._scrub(record.getMessage())
        record.args = ()
        # Cubre tracebacks ya formateados
        if record.exc_text:
            record.exc_text = self._scrub(record.exc_text)
        # Pre-formatea y redacta tracebacks pendientes antes de que el Formatter los escriba
        if record.exc_info:
            record.exc_text = self._scrub(
                "".join(traceback.format_exception(*record.exc_info))
            )
            record.exc_info = None
        return True
