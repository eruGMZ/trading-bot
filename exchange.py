"""Cliente HTTP para las operaciones de Bitso usadas por el bot."""

import hashlib
import hmac
import json
import logging
import time
from decimal import ROUND_DOWN, Decimal

import requests

from config import BITSO_API_KEY, BITSO_API_SECRET, IS_DRY_RUN

log = logging.getLogger(__name__)

BASE_URL = "https://api.bitso.com"
BTC_QUANTUM = Decimal("0.00000001")


def format_btc(amount):
    """Cantidad de BTC truncada a 8 decimales. Nunca redondea hacia arriba."""
    return f"{Decimal(str(amount)).quantize(BTC_QUANTUM, rounding=ROUND_DOWN):f}"


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
        f"{BASE_URL}{path}",
        headers=bitso_headers("GET", path),
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def bitso_get_available(currency):
    """Saldo disponible de una moneda (p. ej. 'btc' o 'mxn')."""
    data = bitso_get_balance()
    if not data.get("success"):
        raise RuntimeError(f"No se pudo leer el balance: {data}")
    for balance in data["payload"]["balances"]:
        if balance["currency"] == currency:
            return float(balance["available"])
    return 0.0


def bitso_get_quote(book="btc_mxn"):
    """Retorna {last, bid, ask, spread_pct} desde el ticker de Bitso.

    spread_pct = (ask - bid) / ask — indica la amplitud relativa del spread.
    Un spread alto bloquea nuevas entradas.
    """
    response = requests.get(f"{BASE_URL}/v3/ticker/?book={book}", timeout=10)
    response.raise_for_status()
    p = response.json()["payload"]
    last = float(p["last"])
    bid  = float(p["bid"])
    ask  = float(p["ask"])
    spread_pct = (ask - bid) / ask if ask > 0 else 0.0
    return {"last": last, "bid": bid, "ask": ask, "spread_pct": spread_pct}


def bitso_get_ticker(book="btc_mxn"):
    """Alias de compatibilidad. Usa bitso_get_quote() para datos completos."""
    return bitso_get_quote(book)["last"]


def bitso_place_order(book, side, amount_mxn=None, amount_btc=None):
    """Orden de mercado. Compra por MXN (minor); venta por BTC (major).

    En dry-run no llama a Bitso.
    """
    if side == "buy":
        if not amount_mxn or amount_mxn <= 0:
            raise ValueError("la compra requiere amount_mxn > 0")
        order = {"book": book, "side": "buy", "type": "market", "minor": f"{amount_mxn:.2f}"}
        desc = f"compra {amount_mxn:.2f} MXN"
    elif side == "sell":
        qty = format_btc(amount_btc or 0)
        if float(qty) <= 0:
            raise ValueError("la venta requiere amount_btc > 0")
        order = {"book": book, "side": "sell", "type": "market", "major": qty}
        desc = f"venta {qty} BTC"
    else:
        raise ValueError(f"lado de orden inválido: {side!r}")

    if IS_DRY_RUN:
        log.info("[SIMULADO] Orden %s en %s", desc, book)
        return {"simulated": True, **order}

    path = "/v3/orders/"
    body = json.dumps(order)
    response = requests.post(
        f"{BASE_URL}{path}",
        headers=bitso_headers("POST", path, body),
        data=body,
        timeout=10,
    )
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code >= 400 or not data.get("success"):
        raise RuntimeError(f"Bitso rechazó la orden ({response.status_code}): {data}")
    oid = (data.get("payload") or {}).get("oid")
    if not oid:
        raise RuntimeError(f"Bitso no devolvió oid de orden: {data}")
    log.info("Orden aceptada oid=%s — %s", oid, desc)
    return data
