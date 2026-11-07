"""Cliente HTTP para las operaciones de Bitso usadas por el bot."""

import hashlib
import hmac
import json
import logging
import time

import requests

from config import BITSO_API_KEY, BITSO_API_SECRET, IS_DRY_RUN

log = logging.getLogger(__name__)


def bitso_sign(method, path, payload=""):
    nonce = str(int(time.time() * 1000))
    msg = nonce + method.upper() + path + payload
    sig = hmac.new(
        BITSO_API_SECRET.encode(),
        msg.encode(),
        hashlib.sha256,
    ).hexdigest()
    return nonce, sig


def bitso_headers(method, path, payload=""):
    nonce, sig = bitso_sign(method, path, payload)
    return {
        "Authorization": f"Bitso {BITSO_API_KEY}:{nonce}:{sig}",
        "Content-Type": "application/json",
    }


def bitso_get_balance():
    path = "/v3/balance/"
    response = requests.get(
        f"https://api.bitso.com{path}",
        headers=bitso_headers("GET", path),
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def bitso_get_ticker(book="btc_mxn"):
    response = requests.get(
        f"https://api.bitso.com/v3/ticker/?book={book}",
        timeout=10,
    )
    response.raise_for_status()
    return float(response.json()["payload"]["last"])


def bitso_place_order(book, side, amount_mxn):
    if IS_DRY_RUN:
        log.info("[SIMULADO] Orden %s %s MXN en %s", side, amount_mxn, book)
        return {"simulated": True, "side": side, "amount_mxn": amount_mxn}

    path = "/v3/orders/"
    body = json.dumps({
        "book": book,
        "side": side,
        "type": "market",
        "minor": str(amount_mxn),
    })
    response = requests.post(
        f"https://api.bitso.com{path}",
        headers=bitso_headers("POST", path, body),
        data=body,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()