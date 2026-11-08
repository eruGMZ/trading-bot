"""Configuración compartida por el bot y el actualizador del RSI."""

import os

from dotenv import load_dotenv

load_dotenv()

BITSO_API_KEY = os.getenv("BITSO_API_KEY", "")
BITSO_API_SECRET = os.getenv("BITSO_API_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
CDP_PORT = os.getenv("TRADINGVIEW_CDP_PORT") or "9222"

# Un valor mal escrito (p. ej. "Operational") no debe caer en silencio a dry-run.
VALID_MODES = ("dry_run", "operational")
BOT_MODE = os.getenv("BOT_MODE", "dry_run").strip()
if BOT_MODE not in VALID_MODES:
    raise ValueError(
        f"BOT_MODE inválido: {BOT_MODE!r}. Usa 'dry_run' u 'operational'."
    )
IS_DRY_RUN = BOT_MODE != "operational"
MODE_TAG = "[SIMULADO] " if IS_DRY_RUN else "[REAL] "

LOG_FILE = os.path.expanduser("~/trading-bot/bot.log")
STATE_FILE = os.path.expanduser("~/trading-bot/state.json")
CACHE_FILE = os.path.expanduser("~/trading-bot/rsi_cache.json")
TRADE_LOG_FILE = os.path.expanduser("~/trading-bot/trades.db")
CACHE_MAX_AGE_SECONDS = 120
RSI_UPDATE_INTERVAL = 60
LOOP_SECONDS = 60

# ── Gestión de riesgo ─────────────────────────────────────────────────────────
# Capital de referencia (MXN). Sirve de base para todos los cálculos de riesgo.
# No tiene que coincidir con el saldo en Bitso; es el capital que decides
# "poner en juego" para las reglas de drawdown y pérdida diaria.
CAPITAL_REF_MXN = float(os.getenv("CAPITAL_REF_MXN", "5000"))

# Riesgo máximo por operación, como fracción de CAPITAL_REF_MXN.
# Con stop-loss del 2% y riesgo del 1%: posición = 0.01*5000/0.02 = 2500 MXN
# El tope MAX_TRADE_MXN evita posiciones demasiado grandes.
RISK_PCT_PER_TRADE = float(os.getenv("RISK_PCT_PER_TRADE", "0.01"))  # 1%
MAX_TRADE_MXN     = float(os.getenv("MAX_TRADE_MXN", "500"))         # tope duro

# Límites de pérdida
MAX_TRADES_DAY         = int(os.getenv("MAX_TRADES_DAY", "3"))
MAX_LOSSES_DAY         = int(os.getenv("MAX_LOSSES_DAY", "2"))
DAILY_LOSS_PCT         = float(os.getenv("DAILY_LOSS_PCT", "0.03"))   # 3% de capital_ref
DRAWDOWN_KILL_PCT      = float(os.getenv("DRAWDOWN_KILL_PCT", "0.10"))# 10%: kill switch

# Spread máximo permitido para abrir una posición (evita entrar en picos de volatilidad).
MAX_SPREAD_PCT = float(os.getenv("MAX_SPREAD_PCT", "0.005"))  # 0.5%

MIN_HOURS_BETWEEN_TRADES = float(os.getenv("MIN_HOURS_BETWEEN_TRADES", "1"))
STOP_LOSS_PCT            = float(os.getenv("STOP_LOSS_PCT", "0.02"))  # 2%
RSI_BUY                  = float(os.getenv("RSI_BUY", "30"))
RSI_SELL                 = float(os.getenv("RSI_SELL", "70"))
DAILY_REPORT_HOUR        = int(os.getenv("DAILY_REPORT_HOUR", "23"))

# Comisión taker de Bitso (0.78%). Se aplica en compra y venta; round-trip ≈ 1.56%.
BITSO_TAKER_FEE = float(os.getenv("BITSO_TAKER_FEE", "0.0078"))

# Ventana horaria para abrir posiciones, formato "HH-HH" hora local (ej. "9-22").
# Vacío = sin restricción de horario.
TRADING_HOURS = os.getenv("TRADING_HOURS", "")

# Si al arrancar hay BTC en Bitso por encima de este valor sin posición registrada, se bloquea.
RECONCILE_DUST_MXN = 10.0
