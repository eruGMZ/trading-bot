"""PreToolUse guard: impide que un agente acceda a LOCKBOX_OOS_001.

QRP-001 v1.1 · POLITICA_DATOS_OOS.md §3 · decisión P-009.

Bloquea, para Read, Grep, Glob y Bash:
  - Cualquier acceso al dataset completo `backtest/btcusdt_h1.csv`, que
    contiene el lockbox. Se resuelven rutas reales, así que un enlace
    simbólico hacia el archivo también se bloquea en Read y Grep.
  - Búsquedas (Grep) cuyo alcance incluye ese archivo sin un filtro que lo
    excluya.
  - La ejecución del backtester de Fase 0 (`backtest.py`, que lee el dataset
    completo), la opción `--oos`, la descarga de datos (`fetch_klines`) y la
    herramienta de custodia `make_research_dataset`.
  - Lecturas del historial de git que pueden reconstruir el archivo
    (`git show <rev>:<ruta>`, `cat-file`, `archive`, `log -p`, `grep`...).

Es una capa de defensa, no una garantía completa: no puede ver lo que un
programa hace por dentro (p. ej. Python que construye la ruta en tiempo de
ejecución). Esa vía la cierra el sandbox del perfil de investigación
(`backtest/research/agent-profile.settings.json`). Ver
ARQUITECTURA_QUANT_AGENT_v1.0.md §5.

Salida: JSON con permissionDecision "deny" para bloquear; nada para permitir.
Si el propio hook falla, la configuración usa onFailure "block" (fail-closed).
"""

import fnmatch
import json
import os
import re
import sys

PROJECT = os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR")
                           or os.path.join(os.path.dirname(__file__), "..", ".."))
FULL_DATASET = os.path.join(PROJECT, "backtest", "btcusdt_h1.csv")

# Nombre del dataset completo. No coincide con el derivado
# `btcusdt_h1_research_v1.csv` porque exige `.csv` justo después de `h1`.
FULL_NAME_RE = re.compile(r"btcusdt_h1\.csv", re.IGNORECASE)

BASH_RULES = [
    (FULL_NAME_RE, "acceso al dataset completo que contiene LOCKBOX_OOS_001"),
    (re.compile(r"(^|[\s/'\"])backtest\.py\b"),
     "el backtester de Fase 0 lee el dataset completo y Fase 0 está cerrada"),
    (re.compile(r"--oos\b"), "ejecución sobre el segmento OOS / lockbox"),
    (re.compile(r"fetch_klines"), "descarga de datos no autorizada"),
    (re.compile(r"make_research_dataset"),
     "herramienta de custodia: la ejecuta el custodio humano, no el agente"),
    (re.compile(r"\.git/objects"), "lectura directa de objetos de git"),
    (re.compile(r"\bgit\s+(?:-\S+\s+)*(cat-file|archive|fast-export|bundle|grep|fsck)\b"),
     "lectura del historial de git que puede reconstruir el dataset completo"),
    (re.compile(r"\bgit\s+(?:-\S+\s+)*show\s+\S*:"),
     "lectura de un archivo desde el historial de git"),
    (re.compile(r"\bgit\s+(?:-\S+\s+)*(log|diff|show|whatchanged)\b.*\s(-p|--patch|-S|-G|--stat-full|--binary)\b"),
     "lectura de contenido del historial de git"),
    (re.compile(r"\bgit\s+(?:-\S+\s+)*(checkout|restore|switch|worktree|stash)\b.*25f0e3f"),
     "restauración de archivos de Fase 0 desde el historial"),
]


def deny(reason: str):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Bloqueado por lockbox_guard (QRP-001, LOCKBOX_OOS_001): {reason}. "
                "Usa backtest/research/data/btcusdt_h1_research_v1.csv. "
                "Cualquier excepción requiere autorización humana."
            ),
        }
    }))
    sys.exit(0)


def real(path: str, cwd: str) -> str:
    if not path:
        return ""
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    return os.path.realpath(path)


def contains_full_dataset(scope: str) -> bool:
    """True si `scope` es el dataset completo o un directorio que lo contiene."""
    if not scope:
        return False
    return scope == FULL_DATASET or FULL_DATASET.startswith(scope.rstrip(os.sep) + os.sep)


def main():
    data = json.load(sys.stdin)
    tool = data.get("tool_name", "")
    inp = data.get("tool_input") or {}
    cwd = data.get("cwd") or PROJECT

    if tool == "Read":
        if real(inp.get("file_path", ""), cwd) == FULL_DATASET:
            deny("lectura del dataset completo")
        if FULL_NAME_RE.search(inp.get("file_path", "")):
            deny("lectura del dataset completo")

    elif tool == "Grep":
        scope = real(inp.get("path") or cwd, cwd)
        if contains_full_dataset(scope):
            glob = inp.get("glob")
            ftype = inp.get("type")
            excluded = (
                (glob and not fnmatch.fnmatch("btcusdt_h1.csv", glob)
                 and not fnmatch.fnmatch("backtest/btcusdt_h1.csv", glob))
                or (ftype and ftype.lower() != "csv")
            )
            if not excluded:
                deny("la búsqueda incluiría el contenido del dataset completo; "
                     "acota `path`, o usa `glob`/`type` que lo excluyan")
        if FULL_NAME_RE.search(json.dumps(inp)):
            deny("búsqueda dirigida al dataset completo")

    elif tool == "Glob":
        # Listar nombres no expone datos; solo se bloquea si apunta al archivo.
        if FULL_NAME_RE.search(json.dumps(inp)):
            deny("referencia al dataset completo")

    elif tool == "Bash":
        cmd = inp.get("command", "")
        for pattern, reason in BASH_RULES:
            if pattern.search(cmd):
                deny(reason)

    sys.exit(0)


if __name__ == "__main__":
    main()
