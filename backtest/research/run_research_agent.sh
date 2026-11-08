#!/usr/bin/env bash
# Lanza el Research Agent con el perfil de aislamiento de QRP-001.
#
# Capa 3 (sandbox del sistema operativo): los comandos Bash del agente se
# ejecutan dentro de bubblewrap sin poder leer el dataset completo ni .git,
# sin red y sin opción de salir del sandbox. Las capas 1 y 2 (reglas deny y
# hook de .claude/) se aplican además, porque son configuración del proyecto.
#
# Requisitos: bubblewrap y socat instalados. Si el sandbox no puede iniciarse,
# Claude Code se niega a arrancar (failIfUnavailable): falla cerrado.
#
# Nota: WebFetch y WebSearch quedan denegados en este perfil. La investigación
# bibliográfica (QRP-001 §6) se hace en una sesión separada, sin acceso al
# repositorio de datos, o la aporta el humano.
set -euo pipefail

REPO="/home/erick-pc/trading-bot"
PROFILE="$REPO/backtest/research/agent-profile.settings.json"

for bin in bwrap socat; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "ERROR: falta '$bin'. El sandbox del Research Agent no puede iniciarse." >&2
    echo "Instalación (Linux Mint/Ubuntu): sudo apt install bubblewrap socat" >&2
    exit 1
  fi
done

cd "$REPO"
exec claude --settings "$PROFILE" "$@"
