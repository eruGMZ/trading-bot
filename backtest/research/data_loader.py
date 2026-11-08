"""
Cargador de datos fail-closed — QRP-001 Capa 4 (A-3)

Solo acepta el dataset derivado de investigación, identificado por su SHA-256.
Rechaza explícitamente:
  - Cualquier archivo que no sea el derivado registrado.
  - Cualquier fila con open_time >= LOCKBOX_START (2025-11-08T00:00:00Z).
  - Datasets con filas duplicadas o gaps de 1h.

Si algo falla, lanza una excepción — nunca devuelve datos parciales en silencio.

Uso:
    from backtest.research.data_loader import load_research_data
    df = load_research_data()          # usa la ruta y hash del MANIFEST
    df = load_research_data(path)      # ruta explícita, hash verificado igual
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Constantes del dataset derivado de investigación (D-008)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR  = _REPO_ROOT / "backtest" / "research" / "data"
_MANIFEST  = _DATA_DIR / "MANIFEST.json"

# open_time estrictamente menor que este valor — ninguna fila del lockbox.
_LOCKBOX_START = pd.Timestamp("2025-11-08T00:00:00Z")

# Columnas mínimas requeridas.
_REQUIRED_COLS = {"open_time", "open", "high", "low", "close", "volume"}


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def load_research_data(path: str | Path | None = None) -> pd.DataFrame:
    """
    Carga y valida el dataset derivado de investigación.

    Parameters
    ----------
    path : opcional
        Ruta al CSV. Si se omite, se toma del MANIFEST.

    Returns
    -------
    pd.DataFrame
        Columnas: open_time (DatetimeTZAware UTC), open, high, low, close,
        volume (float64). Ordenado por open_time, índice 0..N-1.

    Raises
    ------
    DataLoaderError
        En cualquier condición de fallo: hash incorrecto, filas del lockbox,
        duplicados, gaps, columnas faltantes o incoherencia OHLC.
    """
    manifest = _load_manifest()
    csv_path, expected_sha = _resolve_path(path, manifest)
    _verify_sha256(csv_path, expected_sha)
    df = _read_csv(csv_path)
    _validate(df, csv_path)
    return df


# ---------------------------------------------------------------------------
# Implementación interna
# ---------------------------------------------------------------------------

class DataLoaderError(RuntimeError):
    """Error irrecuperable del cargador. No continuar con datos parciales."""


def _load_manifest() -> dict:
    if not _MANIFEST.exists():
        raise DataLoaderError(
            f"MANIFEST no encontrado: {_MANIFEST}. "
            "El dataset derivado no ha sido generado o está en una ubicación inesperada."
        )
    with _MANIFEST.open(encoding="utf-8") as fh:
        return json.load(fh)


def _resolve_path(
    path: str | Path | None, manifest: dict
) -> tuple[Path, str]:
    if path is None:
        rel = manifest.get("dataset")
        if not rel:
            raise DataLoaderError("MANIFEST no contiene el campo 'dataset'.")
        csv_path = (_DATA_DIR / rel).resolve()
    else:
        csv_path = Path(path).resolve()

    expected_sha = manifest.get("sha256")
    if not expected_sha:
        raise DataLoaderError("MANIFEST no contiene el campo 'sha256'.")

    # Protección extra: rechazar explícitamente el dataset completo por nombre.
    if csv_path.name == "btcusdt_h1.csv" and "research" not in str(csv_path):
        raise DataLoaderError(
            "Se intentó cargar el dataset completo (btcusdt_h1.csv) que contiene "
            "LOCKBOX_OOS_001. Usa el dataset derivado de investigación. "
            "QRP-001 / D-008."
        )

    if not csv_path.exists():
        raise DataLoaderError(f"Dataset no encontrado: {csv_path}")

    return csv_path, expected_sha


def _verify_sha256(path: Path, expected: str) -> None:
    """Calcula SHA-256 del archivo y lo compara con el esperado."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual != expected:
        raise DataLoaderError(
            f"SHA-256 incorrecto para {path.name}.\n"
            f"  Esperado : {expected}\n"
            f"  Calculado: {actual}\n"
            "El archivo fue modificado o no es el dataset derivado registrado (D-008)."
        )


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(
            path,
            dtype={
                "open_time": "int64",
                "open": "float64",
                "high": "float64",
                "low": "float64",
                "close": "float64",
                "volume": "float64",
            },
        )
    except Exception as exc:
        raise DataLoaderError(f"Error al leer {path}: {exc}") from exc

    missing = _REQUIRED_COLS - set(df.columns)
    if missing:
        raise DataLoaderError(
            f"Columnas faltantes en el dataset: {sorted(missing)}"
        )

    # open_time es Unix ms → DatetimeTZAware UTC.
    try:
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    except Exception as exc:
        raise DataLoaderError(f"Error al convertir open_time: {exc}") from exc

    return df.sort_values("open_time").reset_index(drop=True)


def _validate(df: pd.DataFrame, path: Path) -> None:
    """Validaciones fail-closed. Lanza DataLoaderError ante cualquier anomalía."""

    # 1. Sin filas del lockbox.
    lockbox_rows = df[df["open_time"] >= _LOCKBOX_START]
    if not lockbox_rows.empty:
        first = lockbox_rows["open_time"].iloc[0]
        raise DataLoaderError(
            f"{len(lockbox_rows)} fila(s) con open_time >= {_LOCKBOX_START} "
            f"(primera: {first}). "
            "El dataset contiene datos del LOCKBOX_OOS_001. QRP-001 / D-008."
        )

    # 2. Sin duplicados.
    dupes = df["open_time"].duplicated().sum()
    if dupes:
        raise DataLoaderError(
            f"{dupes} open_time duplicado(s) en {path.name}."
        )

    # 3. Sin gaps de 1h (tolerancia de 1 segundo por DST o microsegundos).
    if len(df) > 1:
        deltas = df["open_time"].diff().dropna()
        expected = pd.Timedelta("1h")
        tol = pd.Timedelta("1s")
        gaps = deltas[abs(deltas - expected) > tol]
        if not gaps.empty:
            idx = gaps.index[0]
            raise DataLoaderError(
                f"{len(gaps)} gap(s) detectado(s). Primero en fila {idx}: "
                f"{df['open_time'].iloc[idx-1]} → {df['open_time'].iloc[idx]} "
                f"(delta={gaps.iloc[0]})."
            )

    # 4. Coherencia OHLC básica.
    bad_ohlc = df[
        (df["low"] > df["open"]) |
        (df["low"] > df["close"]) |
        (df["high"] < df["open"]) |
        (df["high"] < df["close"]) |
        (df["low"] <= 0) |
        (df["high"] <= 0)
    ]
    if not bad_ohlc.empty:
        raise DataLoaderError(
            f"{len(bad_ohlc)} fila(s) con OHLC inválido. "
            f"Primera fila: {bad_ohlc.iloc[0].to_dict()}"
        )

    # 5. Al menos una fila.
    if df.empty:
        raise DataLoaderError(f"El dataset {path.name} está vacío.")
