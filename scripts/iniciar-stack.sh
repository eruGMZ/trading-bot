#!/bin/bash
# Inicia el stack de trading en orden: bot → rsi-updater → TradingView
# Muestra una ventana de terminal con el progreso.

VERDE='\033[0;32m'
ROJO='\033[0;31m'
AMARILLO='\033[1;33m'
NC='\033[0m'

ok()  { echo -e "${VERDE}✅ $1${NC}"; }
err() { echo -e "${ROJO}❌ $1${NC}"; }
info(){ echo -e "${AMARILLO}⏳ $1${NC}"; }

echo "======================================"
echo "   🤖 TRADING BOT — INICIO DE STACK"
echo "======================================"
echo ""

# 1. trading-bot
info "Iniciando trading-bot..."
if systemctl is-active --quiet trading-bot; then
    ok "trading-bot ya estaba activo"
else
    sudo systemctl start trading-bot
    sleep 2
    if systemctl is-active --quiet trading-bot; then
        ok "trading-bot iniciado"
    else
        err "trading-bot falló — revisa: journalctl -u trading-bot -n 20"
    fi
fi

# 2. rsi-updater
info "Iniciando rsi-updater..."
if systemctl is-active --quiet rsi-updater; then
    ok "rsi-updater ya estaba activo"
else
    sudo systemctl start rsi-updater
    sleep 2
    if systemctl is-active --quiet rsi-updater; then
        ok "rsi-updater iniciado"
    else
        err "rsi-updater falló — revisa: journalctl -u rsi-updater -n 20"
    fi
fi

# 3. TradingView
info "Iniciando TradingView (espera display)..."
if systemctl is-active --quiet tradingview; then
    ok "TradingView ya estaba activo"
else
    sudo systemctl start tradingview
    sleep 5
    if systemctl is-active --quiet tradingview; then
        ok "TradingView iniciado"
    else
        err "TradingView falló — intenta: tv-start manualmente"
    fi
fi

echo ""
echo "======================================"

# 4. Verificar RSI cache
sleep 3
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
RSI_FILE="${RSI_CACHE_FILE:-"$PROJECT_ROOT/rsi_cache.json"}"
if [ ! -f "$RSI_FILE" ] && [ -f "$HOME/trading-bot/rsi_cache.json" ]; then
    RSI_FILE="$HOME/trading-bot/rsi_cache.json"
fi
if [ -f "$RSI_FILE" ]; then
    RSI=$(python3 -c "
import json,time
d=json.load(open('$RSI_FILE'))
age=int(time.time()-d['timestamp'])
print(f'RSI: {d[\"rsi\"]:.1f} (hace {age}s)')
" 2>/dev/null)
    ok "Señal activa — $RSI"
else
    info "RSI aún no disponible (TradingView arrancando)"
fi

echo ""
echo "   Estado final:"
echo -n "   trading-bot:  "; systemctl is-active trading-bot
echo -n "   rsi-updater:  "; systemctl is-active rsi-updater
echo -n "   tradingview:  "; systemctl is-active tradingview
echo ""
echo "   Monitorea con: bot-log | rsi-now"
echo "   Desde Telegram: /status"
echo "======================================"
echo ""
echo "Presiona ENTER para cerrar..."
read
