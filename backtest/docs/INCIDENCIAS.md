# Registro de incidencias — QRP-001

Las incidencias no se borran ni se reescriben. Una corrección posterior se añade como actualización con fecha.

---

## INC-001 — Pérdida del CSV original de la primera ejecución de Fase 0

| Campo | Valor |
|---|---|
| Fecha de la pérdida | 2026-11-08 |
| Fecha de registro | 2026-11-08 |
| Tipo | Trazabilidad de datos |
| Severidad | Permanente; no invalida el dictamen de Fase 0 |
| Estado | Cerrada como pérdida registrada (no recuperable) |

### Qué se perdió

El CSV usado en la primera ejecución de Fase 0:

| Atributo | Valor |
|---|---|
| Rango (`open_time`) | 2023-05-10T12:00Z → 2026-11-08T20:00Z |
| Filas | 30,681 |
| SHA-256 | `4c7417d335af8ff499d8fd421063ac5573227b6d9935e36c0bdcd401caab0f61` |
| Origen | `fetch_klines.py` con una ventana relativa a `now()` (versión previa a la ventana fija) |

### Cómo ocurrió

Durante la reproducción de Fase 0, el agente copió el CSV a `backtest/runs/2026-11-08_csv_previo/` y lo borró antes del commit `25f0e3f` para no versionar datos duplicados. Conservó solo su hash en `SHA256SUMS`. El archivo nunca estuvo en git ni existe otra copia.

### Qué se conserva

- El SHA-256, que permite identificar el archivo si apareciera una copia, pero no reconstruirlo.
- Los resultados de la primera ejecución (`runs/2026-11-08_csv_previo/results_train.json`).
- La comparación hecha antes de borrarlo: sus 30,492 velas comunes con el CSV actual tenían OHLC idénticos, y la reejecución produjo exactamente las mismas operaciones y métricas.

### Consecuencias

- La reproducción **exacta** de la primera ejecución con su dataset original ya no es posible.
- Coincidir en las velas comunes no prueba que el CSV actual sea una reproducción del original: difieren en rango, número de filas y hash.
- El dictamen de Fase 0 no queda invalidado, porque se reprodujo con el dataset actual, que sí está versionado. Lo que queda limitada es la reproducibilidad integral de la evidencia original.

### Acciones

- No se regenera ni se etiqueta ningún archivo como original.
- No se modifican el reporte, los resultados ni el código cerrado de Fase 0.
- Regla aplicada desde ahora (`POLITICA_DATOS_OOS.md` §1): los datasets originales se conservan siempre, aunque estén duplicados, y ningún dataset se borra sin registrar antes la decisión.
