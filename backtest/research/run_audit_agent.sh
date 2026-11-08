#!/usr/bin/env bash
# Lanza el Audit Agent con perfil de solo lectura (QRA-001 A-2).
#
# El Audit Agent puede leer todo el repositorio excepto:
#   - backtest/btcusdt_h1.csv (dataset completo con lockbox)
#   - .git (historial git)
# Solo puede escribir en archivos audit*.md dentro de experiments/EXP-XXXX/.
# Sin red. Sin operaciones destructivas de git ni del sistema de archivos.
#
# Uso: bash backtest/research/run_audit_agent.sh [args para claude]
set -euo pipefail

REPO="/home/erick-pc/trading-bot"
PROFILE="$REPO/backtest/research/audit-profile.settings.json"

for bin in bwrap socat; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "ERROR: falta '$bin'. El sandbox del Audit Agent no puede iniciarse." >&2
    echo "Instalación (Linux Mint/Ubuntu): sudo apt install bubblewrap socat" >&2
    exit 1
  fi
done

cd "$REPO"
exec claude --settings "$PROFILE" "$@"
