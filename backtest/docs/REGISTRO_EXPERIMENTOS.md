# Registro de experimentos — QRP-001

Todos los experimentos y configuraciones evaluadas, incluidos los rechazados. El contador global alimenta el control de pruebas múltiples (QRP-001 v1.1 §13).

## Contador global

| Concepto | Valor |
|---|---|
| Familias evaluadas | 2 de 5 (FASE-0: Mean Reversion; EXP-0001: Trend Following) |
| Familias disponibles | **3** |
| Configuraciones preregistradas (aún sin ejecutar) | 4 de 20 (EXP-0001: A, B, C, D) |
| Configuraciones evaluadas sobre Train | 4 de 20 (A, B, E1, E2 — FASE-0) |
| Configuraciones disponibles (tras EXP-0001) | **12** |
| Presupuesto global | **Aprobado** (D-016, 2026-11-08) — 5 familias, 4 configs/familia, 20 configs total |
| LOCKBOX_OOS_001 | **No consumido** |

## Regla de contabilización (D-016)

Toda **configuración** evaluada sobre Train cuenta contra el presupuesto, independientemente de su resultado.

| Tipo de prueba | Cuenta como |
|---|---|
| Configuración preregistrada | 1 configuración |
| Variante de parámetros preregistrada | 1 configuración adicional |
| Prueba repetida sobre los mismos datos con distintos parámetros no preregistrados | **Prohibida** |
| Ajuste posterior a ver resultados (no preregistrado) | **Prohibido** |
| Escenarios de costo (base y adverso) sobre la misma configuración | No cuentan — son análisis de sensibilidad, no configuraciones independientes |
| Configuraciones descartadas antes de completar el backtest | Cuentan igual |

**Grid search libre:** prohibido. Toda variante de parámetros debe estar preregistrada antes de ejecutarse.

**Deflated Sharpe Ratio:** se calcula con `N = número total de configuraciones evaluadas` en ese momento. Cada configuración nueva reduce el umbral de Sharpe efectivo que debe superar la siguiente. Ver `CRITERIOS_APROBACION.md` §2.

## Experimentos

| ID | Fecha | Hipótesis | Configuraciones | Segmentos | Dictamen | Referencia |
|---|---|---|---|---|---|---|
| FASE-0 | 2026-11-08 | H-000 (Mean Reversion H1) | 4 (A, B, E1, E2) | Train | RECHAZADO | `backtest/REPORTE_FASE0.md`, `25f0e3f` |
| EXP-0001 | 2026-11-09 | H-001 (Trend Following H4) | 4 (A primaria, B/C/D exploratorias) — **preregistradas** | Train (pendiente) | PREREGISTRO CONGELADO — Train autorizado (D-024) | `EXP-0001/preregistration.md` v4 |

## Uso del lockbox

| Lockbox | Candidato | Fecha | Hashes | Resultado |
|---|---|---|---|---|
| LOCKBOX_OOS_001 | — | — | — | No consumido |
