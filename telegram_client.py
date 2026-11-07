"""Transporte HTTP de Telegram Bot API."""

import logging

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger(__name__)


def telegram_is_configured():
    return bool(TELEGRAM_BOT_TOKEN)


def is_authorized_chat(chat_id, allowed_chat_id):
    """Solo el chat configurado puede dar órdenes. Si no hay chat configurado, nadie puede."""
    if allowed_chat_id in (None, ""):
        return False
    return str(chat_id) == str(allowed_chat_id)


def send_message(chat_id, text):
    return requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )


def get_updates(offset):
    response = requests.get(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
        params={"offset": offset, "timeout": 3},
        timeout=10,
    )
    return response.json().get("result", [])


def telegram_notify(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram no configurado — mensaje omitido: %s", message)
        return
    try:
        send_message(TELEGRAM_CHAT_ID, message)
        log.info("Telegram: %s", message)
    except Exception as error:
        log.error("Error enviando Telegram: %s", error)
