# Criterios de aprobación — QRP-001

**Estado:** APROBADO (B-2 cerrado, 2026-11-08)
**Última actualización:** 2026-11-08
**Protocolo:** QRP-001 v1.1

Estos umbrales son los mínimos comunes que todo preregistro debe respetar. Un preregistro puede endurecerlos, nunca relajarlos. Los umbrales **no pueden cambiarse después de conocer resultados**.

## 1. Restricción operativa dura — frecuencia máxima

`MAX_TRADES_MONTH = 8` es una **restricción fiscal, no un parámetro de optimización.**

- Régimen SAT: Sueldos y salarios (605). No se cambiará.
- Superar ~10 ops/mes de forma sostenida (6+ meses) activa clasificación de actividad empresarial ante SAT (RESICO, pagos provisionales, obligaciones contables).
- Si un backtest muestra mejor resultado con 12–15 ops/mes, **esa variante no es viable**. No se registra como candidato ni se propone como alternativa.
- El escalado es solo por capital (500 → 10,000 MXN), nunca por frecuencia.
- CARF 2026: Binance reporta saldo y operaciones brutas al SAT. Cada operación es visible.

## 2. Umbrales mínimos — Train (pre-filtro para usar el LOCKBOX)

Un candidato que no pase estos umbrales en Train **no llega a E1**. Se ahorra el lockbox.

| Métrica | Umbral mínimo | Escenario |
|---|---|---|
| Operaciones en Train | ≥ 50 | — |
| Sharpe Ratio neto anualizado | > 1.0 | Adverso |
| Maximum Drawdown | < 10% del capital | Adverso |
| Profit Factor neto | > 1.5 | Adverso |
| Expectancy neta por operación | > 0 | Adverso |
| IC 95% bootstrap por bloques (expectancy) | Informativo | — |

**Lógica:** Train es el filtro estricto porque ahí se selecciona el candidato único. Con 8 ops/mes × 24 meses de Train el máximo teórico es ~192 operaciones; con EMA200 y filtros de régimen se esperan 60–120 reales. 50 ops es alcanzable y estadísticamente suficiente.

## 3. Umbrales mínimos — LOCKBOX E1 y prospectiva E2 (confirmación)

E1 y E2 no son filtros de selección sino confirmaciones. El umbral es más bajo: se acepta que la estrategia "no se degrade", no que sea excepcional fuera de muestra.

| Métrica | Umbral mínimo | Escenario |
|---|---|---|
| Profit Factor neto | > 1.2 | Adverso |
| Maximum Drawdown | < 10% del capital | Adverso |
| Expectancy neta por operación | > 0 | Adverso |
| Sharpe neto anualizado | > 0.5 (informativo) | Adverso |
| IC 95% bootstrap (expectancy) | No cruza 0 | — |

**Nota sobre E1 (D-009):** el resultado de LOCKBOX_OOS_001 se reporta como evaluación histórica restringida. Un resultado positivo en E1 no es suficiente por sí solo: se requiere además E2 (validación prospectiva), que es la evidencia confirmatoria principal.

## 4. Puertas por etapa

| Etapa | Puerta para avanzar |
|---|---|
| C — Train | Criterios de §2, no inferiores; cumplir `MAX_TRADES_MONTH ≤ 8` |
| D — Validación interna | Estabilidad en Walk-Forward y sensibilidad a parámetros (definidas en el preregistro) |
| E1 — LOCKBOX | Criterios de §3, ejecución única, autorización humana |
| E2 — Prospectiva | Criterios de §3 **y** ≥ 3 meses **y** ≥ N ops cerradas (N definido en el preregistro antes de iniciar) |
| F — Paper Trading | Criterios de §3 **y** ≥ 2 meses **y** ≥ N ops cerradas (N definido en el preregistro); costos reales documentados vs. supuestos |
| G/H — Revisión y autorización | Decisión humana independiente |

## 5. Parámetros de riesgo simulado (D-017, D-018)

| Parámetro | Valor |
|---|---|
| Capital inicial simulado | $3,000 MXN (debe coincidir con el capital real asignado) |
| Riesgo máximo por operación | 0.5% del equity actualizado |
| Kill switch de drawdown | 10% del equity inicial de la fase — detiene nuevas operaciones sin reanudación automática |

## 6. Pendientes menores (no bloquean QRP-001)

| ID | Pendiente |
|---|---|
| — | N mínimo de ops para E2 y Paper Trading (se define en cada preregistro) |
| — | Criterio de estabilidad en Walk-Forward (se define en el primer preregistro) |
| — | Métrica concreta de comparación con benchmarks (Sharpe, Calmar u otra) |
| P-005 | Comisión efectiva de Binance documentada con fuente y fecha |
