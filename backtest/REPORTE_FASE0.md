# Reporte Fase 0 — Backtest Mean Reversion H1 BTC/USDT

**Especificación:** Documento_Implementación_Final v1.1 (2026-11-08)
**Fecha del reporte:** 2026-11-08
**Para:** revisión humana (paso 9 de §12)

## 1. Conclusión

**No existe fundamento para avanzar a Fase 1.** Las cuatro configuraciones evaluadas (A, B y las dos experimentales E1, E2) tienen expectancy neta negativa y Profit Factor < 1.0 sobre Train, en ambos escenarios de costo. Según la regla única de §2 corresponde ❌ **Rechazar: no hay edge demostrable**.

- La expectancy **bruta** (antes de costos) también es negativa en todas las variantes (A: −0.149R, B: −0.133R, E1: −0.083R, E2: −0.207R). Los costos agravan el resultado, pero no lo causan.
- El presupuesto de 2 variantes experimentales está agotado.
- **OOS no se ejecutó** (`oos_executed: false`). No hay candidata que validar; ejecutarlo consumiría el único segmento independiente sin aportar decisión.

## 2. Datos y verificación

| Elemento | Valor |
|---|---|
| Fuente | Binance API pública, klines H1 BTCUSDT |
| Rango del CSV | 2023-05-01 00:00 → 2026-10-31 23:00 UTC (ventana fija de `fetch_klines.py`) |
| Velas | 30,720 |
| Duplicados | 0 |
| Gaps (≠ 1h entre velas) | 0 |
| Velas OHLC inválidas | 0 |
| SHA-256 del CSV | `e88a8403c0cc30fde45fd9b492a7c60a0aa43a2d1e157b8bb3ec5663e6195598` |
| Calentamiento | 2023-05-01 → 2023-10-31 (4,415 velas H1, ~1,103 H4; no se opera) |
| Train | 2023-10-31 → 2025-10-31 (24 meses, 17,544 velas) |
| OOS (no ejecutado) | 2025-10-31 → 2026-10-31 (12 meses, 8,761 velas) |

### Reproducción

La primera ejecución usó un CSV descargado con una versión anterior de `fetch_klines.py`, cuya ventana era relativa a `now()` (2023-05-10 → 2026-11-08, SHA-256 `4c7417d3…`). Para cerrar Fase 0 con evidencia reproducible:

1. Se volvió a descargar con la ventana fija actual y se validaron continuidad, duplicados, gaps e integridad OHLC.
2. Las 30,492 velas comunes a ambos CSV tienen OHLC idénticos.
3. Se reejecutaron A, B, E1 y E2, solo sobre Train, con parámetros idénticos.
4. **Las 8 combinaciones variante × escenario reproducen exactamente la ejecución anterior**: las mismas operaciones una a una, las mismas métricas y el mismo IC. Las ventanas difieren en unos 8 días en cada extremo, pero ninguna operación cae ahí (primera entrada 2023-11-14, última salida 2025-10-10).
5. La ejecución previa se conserva en `runs/2026-11-08_csv_previo/` como comparación.

Entorno: Python 3.12.3, pandas 2.1.4, numpy 1.26.4 (fijadas en `requirements.txt`). El bootstrap usa una semilla fija (20261108).

**Nota sobre la integridad del OOS:** el nuevo OOS empieza el 2025-10-31, y la ejecución previa usó como Train datos hasta el 2025-11-08. Los primeros ~8 días del OOS actual ya se vieron, por tanto, como Train. Ninguna operación cayó en ese tramo y no se tomó ninguna decisión con él. Aun así, si en el futuro se usara este OOS, conviene excluir ese tramo o declararlo.

## 3. Metodología aplicada

- RSI(14) y ATR(14) con suavizado Wilder; EMA200 sobre velas H4 UTC **cerradas** (sin look-ahead).
- Señal al cierre de vela H1; entrada simulada al open de la siguiente; SL/TP anclados al precio de entrada con el ATR de la vela de señal.
- Misma vela toca SL y TP → se asume SL primero (aplicada igual a todas las variantes). Ocurrió 1 vez en A y 1 en E2.
- Límites 1 operación/día y 8/mes (UTC) aplicados.
- Costos descontados del resultado en R antes de calcular todas las métricas. Base 0.22% round-trip; adverso 0.30%.
- Max DD como % de capital con riesgo 1% por operación.
- IC 95%: bootstrap de bloques circulares (bloque 10, 2,000 remuestreos, semilla fija).

## 4. Resultados Train

| Variante | Escenario | n | Expectancy (R) | PF | Max DD | Win rate | IC 95% |
|---|---|---|---|---|---|---|---|
| A | base | 74 | −0.3847 | 0.513 | 30.72% | 36.5% | [−0.635, −0.144] |
| A | adverso | 74 | −0.4705 | 0.444 | 36.92% | 36.5% | [−0.729, −0.224] |
| B | base | 70 | −0.3600 | 0.532 | 31.09% | 37.1% | [−0.586, −0.118] |
| B | adverso | 70 | −0.4425 | 0.460 | 35.36% | 37.1% | [−0.668, −0.200] |
| E1 (RSI<25) | base | 28 | −0.3018 | 0.597 | 13.93% | 39.3% | [−0.893, +0.206] |
| E1 | adverso | 28 | −0.3812 | 0.523 | 15.23% | 39.3% | [−0.975, +0.129] |
| E2 (SL 1.2×ATR) | base | 74 | −0.5027 | 0.452 | 40.01% | 29.7% | [−0.766, −0.247] |
| E2 | adverso | 74 | −0.6101 | 0.387 | 47.77% | 29.7% | [−0.881, −0.343] |

Salidas (escenario base): A 46 SL / 27 TP / 1 SL misma vela; B 44 / 26; E1 17 / 11; E2 51 / 22 / 1.

## 5. Variantes experimentales

Ambas se preregistraron antes de ejecutarse (ver `variants_register.json`), tomadas de los ejemplos que el propio §2 plantea (RSI 25/35, ATR 1.2/2.0), con hipótesis y condición de falsación escritas de antemano.

- **E1 — refutada.** Win rate 36.5% → 39.3%, aún bajo el breakeven (~43% con payoff 1.33:1). Las operaciones cayeron de 74 a 28; el IC se ensanchó hasta cruzar cero, pero el punto estimado sigue negativo. Es incertidumbre, no evidencia de edge.
- **E2 — refutada.** Win rate 36.5% → 29.7% (breakeven ~37.5%). El stop ceñido es alcanzado por ruido antes de que la reversión se desarrolle.

## 6. Análisis por régimen (complementario, no criterio de aprobación)

Clasificación: pendiente de la EMA200 H4 cerrada (10 velas H4) normalizada por ATR H1; umbral 0.5, sin información futura.

| Variante (base) | Régimen | n | Expectancy (R) | PF | Max DD |
|---|---|---|---|---|---|
| A | trending | 65 | −0.337 | 0.559 | 24.13% |
| A | ranging | 9 | −0.732 | 0.259 | 8.90% |
| B | trending | 57 | −0.364 | 0.528 | 26.44% |
| B | ranging | 13 | −0.342 | 0.547 | 5.93% |
| E1 | trending | 25 | −0.290 | 0.609 | 12.37% |
| E1 | ranging | 3 | −0.401 | 0.503 | 2.42% |
| E2 | trending | 66 | −0.485 | 0.465 | 34.84% |
| E2 | ranging | 8 | −0.647 | 0.358 | 8.06% |

Hallazgo: pierde en ambos regímenes. El filtro EMA200 H4 concentra ~88% de las entradas de A en régimen *trending*. Las muestras *ranging* (3–13 operaciones) son demasiado pequeñas para concluir nada por sí solas.

## 7. Limitaciones

- Tamaños de muestra pequeños (28–74 operaciones por configuración); los IC lo reflejan.
- El buffer de ejecución es una aproximación de sensibilidad, no slippage medido (§2).
- La regla SL-primero es conservadora; su efecto es mínimo aquí (1 caso por variante afectada).
- La clasificación de régimen es una heurística propia dentro de lo que §2 deja abierto ("objetiva, sin información futura").
## 8. Cierre de Fase 0

**Dictamen (revisión humana, 2026-11-08): no avanzar a Fase 1. No ejecutar OOS.** La reproducción confirmó el resultado, por lo que la Fase 0 queda **cerrada como no aprobada**.

- La hipótesis Mean Reversion H1 en BTC/USDT (variantes A, B, E1, E2) queda **cerrada**. No se ajustarán RSI, ATR ni temporalidades para rescatarla: eso sería una búsqueda retrospectiva de parámetros.
- Fase 1, capital real e infraestructura de producción siguen **no autorizados**. La validación OCO (§6) no aplica mientras Fase 1 esté bloqueada.
- El OOS (2025-10-31 → 2026-10-31) sigue sin consumir; ver la nota de integridad en la sección 2.
- Toda hipótesis nueva se abrirá como experimento independiente, con su propio preregistro y un periodo histórico no usado en ninguna decisión previa.
