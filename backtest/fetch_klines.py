"""Descarga klines H1 de BTC/USDT desde la API pública de Binance.

Uso:
    python fetch_klines.py

Salida: btcusdt_h1.csv con columnas open_time,open,high,low,close,volume
Los timestamps están en UTC. No requiere API key.
"""

import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

SYMBOL   = "BTCUSDT"
INTERVAL = "1h"
LIMIT    = 1000  # máximo por request en Binance
OUTPUT   = Path(__file__).parent / "btcusdt_h1.csv"

# Ventana FIJA, no relativa a la fecha de ejecución.
# El documento exige un script reproducible: con `now()` cada ejecución produce
# un dataset distinto y, por tanto, resultados que no se pueden auditar.
# 3.5 años = 36 meses de backtest + ~6 meses de calentamiento para la EMA200 H4.
START_UTC = datetime(2023, 5, 1,  0, 0, tzinfo=timezone.utc)
END_UTC   = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)

START_MS = int(START_UTC.timestamp() * 1000)
END_MS   = int(END_UTC.timestamp() * 1000)

BASE_URL = "https://api.binance.com/api/v3/klines"


def fetch_batch(start_ms: int, end_ms: int) -> list:
    params = {
        "symbol":    SYMBOL,
        "interval":  INTERVAL,
        "startTime": start_ms,
        "endTime":   end_ms,
        "limit":     LIMIT,
    }
    r = requests.get(BASE_URL, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def main():
    all_rows = []
    cursor   = START_MS
    seen_ts  = set()

    print(f"Descargando {SYMBOL} {INTERVAL} desde "
          f"{datetime.fromtimestamp(START_MS/1000, tz=timezone.utc).date()} "
          f"hasta {datetime.fromtimestamp(END_MS/1000, tz=timezone.utc).date()}")

    while cursor < END_MS:
        batch = fetch_batch(cursor, END_MS)
        if not batch:
            break
        for row in batch:
            ts = int(row[0])
            if ts in seen_ts or ts >= END_MS:
                continue
            seen_ts.add(ts)
            all_rows.append({
                "open_time": ts,
                "open":      float(row[1]),
                "high":      float(row[2]),
                "low":       float(row[3]),
                "close":     float(row[4]),
                "volume":    float(row[5]),
            })
        last_ts = int(batch[-1][0])
        if last_ts <= cursor:
            break
        cursor = last_ts + 1
        print(f"  {len(all_rows):>6} velas  ({datetime.fromtimestamp(last_ts/1000, tz=timezone.utc).date()})",
              end="\r")
        time.sleep(0.12)  # respetar rate limit Binance (1200 req/min)

    all_rows.sort(key=lambda r: r["open_time"])

    # Validar continuidad: no debe haber gaps de más de 1 vela H1
    gaps = 0
    for i in range(1, len(all_rows)):
        diff_h = (all_rows[i]["open_time"] - all_rows[i-1]["open_time"]) / 3_600_000
        if diff_h > 1.5:
            gaps += 1
            print(f"\n  GAP detectado: {diff_h:.1f}h en "
                  f"{datetime.fromtimestamp(all_rows[i]['open_time']/1000, tz=timezone.utc)}")

    with open(OUTPUT, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["open_time","open","high","low","close","volume"])
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nTotal: {len(all_rows)} velas  |  Gaps: {gaps}  |  Guardado en {OUTPUT}")
    if gaps > 0:
        print("ADVERTENCIA: hay gaps. Revisar antes de ejecutar el backtest.")
        sys.exit(1)


if __name__ == "__main__":
    main()
