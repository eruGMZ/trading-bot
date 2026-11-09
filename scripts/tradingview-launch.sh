#!/bin/bash
# Espera a que el display X11 esté disponible antes de lanzar TradingView.
# Necesario cuando el servicio systemd arranca antes de que la sesión gráfica esté lista.

DISPLAY_ID="${DISPLAY:-:0}"
MAX_WAIT=120  # segundos máximos de espera
INTERVAL=3

export DISPLAY="$DISPLAY_ID"

# Intentar obtener XAUTHORITY desde la sesión del usuario si no está definido
if [ -z "$XAUTHORITY" ]; then
    TARGET_HOME="${HOME:-/home/${USER}}"
    XAUTHORITY_CANDIDATE=$(find "$TARGET_HOME" -maxdepth 2 -name ".Xauthority" 2>/dev/null | head -1)
    if [ -n "$XAUTHORITY_CANDIDATE" ]; then
        export XAUTHORITY="$XAUTHORITY_CANDIDATE"
    fi
fi

echo "[tv-launch] Esperando display $DISPLAY_ID..."
elapsed=0
while ! xdpyinfo -display "$DISPLAY_ID" >/dev/null 2>&1; do
    if [ "$elapsed" -ge "$MAX_WAIT" ]; then
        echo "[tv-launch] Timeout esperando display $DISPLAY_ID — abortando"
        exit 1
    fi
    sleep "$INTERVAL"
    elapsed=$((elapsed + INTERVAL))
done

echo "[tv-launch] Display $DISPLAY_ID disponible (${elapsed}s). Iniciando TradingView..."
exec /opt/TradingView/tradingview \
    --remote-debugging-port=9222 \
    --remote-allow-origins=*
