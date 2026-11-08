"""Genera el dataset derivado de investigación (P-009, QRP-001 v1.1).

Lee el dataset completo SOLO para filtrar filas por marca de tiempo y escribe
un archivo derivado que contiene exclusivamente velas anteriores al corte de
investigación. No calcula indicadores, estadísticas ni resultados sobre ningún
precio: el único criterio de selección es `open_time`.

Esta herramienta es de CUSTODIA. Es la única pieza del flujo de investigación
que lee el archivo completo, y debe ejecutarla el custodio de datos (humano),
no el Research Agent. Tras su ejecución, los controles de acceso de
`.claude/` impiden al agente leer el archivo de origen.

Uso (desde la raíz del repositorio):
    python3 -I backtest/research/tools/make_research_dataset.py

Es idempotente: si el derivado ya existe y su hash coincide con el manifiesto,
no lo reescribe. Si existe con otro contenido, aborta sin sobrescribir.
"""

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

SOURCE = ROOT / "backtest" / "btcusdt_h1.csv"
SOURCE_SHA256 = "e88a8403c0cc30fde45fd9b492a7c60a0aa43a2d1e157b8bb3ec5663e6195598"

OUT_DIR  = ROOT / "backtest" / "research" / "data"
OUT_FILE = OUT_DIR / "btcusdt_h1_research_v1.csv"
MANIFEST = OUT_DIR / "MANIFEST.json"

HOUR_MS = 3_600_000


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


# Corte de investigación (POLITICA_DATOS_OOS.md §3, regla 1): la última vela
# incluida es la que abre 2025-11-07T23:00Z, para que ninguna vela 1D de
# investigación toque el 2025-11-08, día que contiene el inicio del lockbox.
RESEARCH_END_EXCLUSIVE = _ms(datetime(2025, 11, 8, 0, 0, tzinfo=timezone.utc))

# Límites de LOCKBOX_OOS_001, solo para verificar que ninguna fila se filtra.
LOCKBOX_START = _ms(datetime(2025, 11, 8, 20, 0, tzinfo=timezone.utc))
LOCKBOX_END_EXCLUSIVE = _ms(datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc))

FIELDS = ["open_time", "open", "high", "low", "close", "volume"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fail(msg: str):
    print(f"ERROR: {msg}")
    sys.exit(1)


def main():
    if not SOURCE.exists():
        fail(f"no existe el dataset de origen {SOURCE}")

    src_hash = sha256(SOURCE)
    if src_hash != SOURCE_SHA256:
        fail(f"el SHA-256 del origen no coincide.\n  esperado {SOURCE_SHA256}\n  obtenido {src_hash}")

    # ── Filtrado por marca de tiempo (sin tocar los precios) ──────────────────
    # Las líneas se copian en crudo (bytes, incluido el fin de línea \r\n del
    # origen), sin convertir los precios a número, para que el derivado sea
    # byte a byte un prefijo del origen. Solo se interpreta el primer campo.
    raw_lines, kept, dropped = [], [], 0
    with open(SOURCE, "rb") as f:
        header_raw = f.readline()
        header = next(csv.reader([header_raw.decode()]))
        if header != FIELDS:
            fail(f"cabecera inesperada: {header}")
        for line in f:
            open_time = int(line.split(b",", 1)[0])
            if open_time < RESEARCH_END_EXCLUSIVE:
                raw_lines.append(line)
                kept.append([str(open_time)])
            else:
                dropped += 1

    # ── Verificaciones ────────────────────────────────────────────────────────
    times = [int(r[0]) for r in kept]
    if not times:
        fail("el derivado quedaría vacío")
    if times != sorted(times):
        fail("las filas no están ordenadas por open_time")
    if len(set(times)) != len(times):
        fail("hay open_time duplicados")
    gaps = sum(1 for a, b in zip(times, times[1:]) if b - a != HOUR_MS)
    if gaps:
        fail(f"{gaps} discontinuidades de 1h en el derivado")
    in_lockbox = sum(1 for t in times if LOCKBOX_START <= t < LOCKBOX_END_EXCLUSIVE)
    if in_lockbox:
        fail(f"{in_lockbox} filas del derivado pertenecen al lockbox")
    if max(times) >= RESEARCH_END_EXCLUSIVE:
        fail("el derivado contiene filas posteriores al corte")

    # ── Escritura sin sobrescribir ────────────────────────────────────────────
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT_FILE.with_suffix(".csv.tmp")
    with open(tmp, "wb") as f:
        f.write(header_raw)
        f.writelines(raw_lines)
    out_hash = sha256(tmp)

    if OUT_FILE.exists():
        existing = sha256(OUT_FILE)
        tmp.unlink()
        if existing != out_hash:
            fail(f"{OUT_FILE.name} ya existe con otro contenido; no se sobrescribe")
        print(f"{OUT_FILE.name} ya existe y coincide; sin cambios.")
    else:
        tmp.rename(OUT_FILE)

    manifest = {
        "dataset": OUT_FILE.name,
        "kind": "derivado",
        "is_original_phase0_dataset": False,
        "protocol": "QRP-001 v1.1 — decisión P-009",
        "description": ("Subconjunto por marca de tiempo del dataset completo, "
                        "sin velas de LOCKBOX_OOS_001 ni del 2025-11-08."),
        "sha256": out_hash,
        "rows": len(kept),
        "columns": FIELDS,
        "timezone": "UTC",
        "frequency": "1h",
        "first_open_time": iso(times[0]),
        "last_open_time": iso(times[-1]),
        "selection_rule": "open_time < 2025-11-08T00:00:00Z",
        "source": {
            "file": "backtest/btcusdt_h1.csv",
            "sha256": SOURCE_SHA256,
            "origin": "Binance API pública /api/v3/klines, BTCUSDT 1h, descargado 2026-11-08 con backtest/fetch_klines.py",
            "rows_dropped": dropped,
        },
        "verification": {
            "duplicates": 0,
            "hourly_gaps": 0,
            "rows_in_lockbox": 0,
            "prices_inspected": False,
        },
        "generator": "backtest/research/tools/make_research_dataset.py",
        "generator_sha256": sha256(Path(__file__)),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if MANIFEST.exists():
        old = json.loads(MANIFEST.read_text())
        if old.get("sha256") == out_hash:
            manifest["generated_at"] = old.get("generated_at", manifest["generated_at"])
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    print(f"Derivado: {OUT_FILE}")
    print(f"  filas {len(kept)}  ({manifest['first_open_time']} → {manifest['last_open_time']})")
    print(f"  descartadas del origen: {dropped}")
    print(f"  sha256 {out_hash}")
    print("  duplicados 0 · gaps 0 · filas del lockbox 0")


if __name__ == "__main__":
    main()
