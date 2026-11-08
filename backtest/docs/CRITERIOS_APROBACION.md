# Criterios de aprobación — QRP-001

**Estado:** BORRADOR. Ningún umbral de este documento está aprobado (P-008 en `REGISTRO_DECISIONES.md`).
**Última actualización:** 2026-11-08

Este documento fijará los mínimos comunes que todo preregistro debe respetar. Un preregistro puede endurecerlos, nunca relajarlos. Los umbrales no pueden cambiarse después de conocer resultados.

## 1. Mínimos propuestos para la confirmación (LOCKBOX y prospectiva)

Tomados de Fase 0 como punto de partida. Están sin aprobar.

| Métrica | Umbral propuesto | Estado |
|---|---|---|
| Expectancy neta por operación | > 0 | Propuesto |
| Profit Factor neto | > 1.2 | Propuesto |
| Maximum Drawdown | < 10% del capital | Propuesto (P-003) |
| IC 95% de la expectancy (bootstrap por bloques) | Límite inferior > 0 | Propuesto |
| Escenario de costos adverso | Expectancy neta > 0 | Propuesto |
| Benchmarks | Valor ajustado por riesgo frente a Buy & Hold BTC, argumentado con métricas | Propuesto; métrica concreta por definir |
| Número mínimo de operaciones | Por definir | Pendiente |

## 2. Puertas por etapa

| Etapa | Puerta para avanzar | Estado |
|---|---|---|
| C — Train | Criterios del preregistro, no inferiores a §1 | Propuesto |
| D — Validación interna | Estabilidad en Walk-Forward y sensibilidad a parámetros, definidas en el preregistro | Pendiente |
| E1 — LOCKBOX | Criterios de §1, ejecución única | Propuesto |
| E2 — Prospectiva | Por definir (P-007) | Pendiente |
| F — Paper Trading | Por definir (P-007) | Pendiente |
| G/H — Revisión y autorización | Decisión humana | Fijo |

## 3. Pendientes

- Número mínimo de operaciones independientes.
- Métrica concreta de comparación con benchmarks (Sharpe, Calmar u otra).
- Criterio de estabilidad en Walk-Forward.
- Presupuesto global de pruebas (P-006), del que depende el Deflated Sharpe.
