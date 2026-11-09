"""Agregación H1 → H4 con detección de discontinuidades (§2, §2.1)."""
import pandas as pd


def aggregate_h1_to_h4(h1_df: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte DataFrame H1 en H4.

    Reglas:
    - Solo bloques completos con exactamente 4 H1 consecutivas (horas 0-3, 4-7, …, 20-23 UTC).
    - Bloques incompletos se descartan.
    - discontinuity_before=True cuando hay un bloque H4 faltante entre dos bloques consecutivos.

    Columnas de entrada: open_time (datetime UTC), open, high, low, close, volume
    Columnas de salida:  open_time, open, high, low, close, volume, discontinuity_before
    """
    df = h1_df.copy()
    if len(df) == 0:
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close",
                                     "volume", "discontinuity_before"])
    df = df.sort_values("open_time").reset_index(drop=True)

    # Asignar cada H1 a su bloque H4 (floor a 4h UTC)
    df["h4_block"] = df["open_time"].dt.floor("4h")

    records = []
    for block_time, group in df.groupby("h4_block"):
        group = group.sort_values("open_time").reset_index(drop=True)

        if len(group) != 4:
            continue

        hours = group["open_time"].dt.hour.values.tolist()
        start_h = block_time.hour
        expected = [start_h + i for i in range(4)]
        if hours != expected:
            continue

        records.append({
            "open_time": block_time,
            "open":  group["open"].iloc[0],
            "high":  group["high"].max(),
            "low":   group["low"].min(),
            "close": group["close"].iloc[-1],
            "volume": group["volume"].sum(),
        })

    if not records:
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close",
                                     "volume", "discontinuity_before"])

    h4 = pd.DataFrame(records).sort_values("open_time").reset_index(drop=True)

    step = pd.Timedelta("4h")
    disc = [False]
    for i in range(1, len(h4)):
        disc.append(h4["open_time"].iloc[i] - h4["open_time"].iloc[i - 1] != step)
    h4["discontinuity_before"] = disc

    return h4
