# Registro de decisiones — QRP-001

**Protocolo:** QRP-001 v1.1
**Estado del protocolo:** Pendiente de aprobación integral. No hay autorización para iniciar investigación de estrategias.
**Última actualización:** 2026-11-08 (resolución de revisión de QRP-001 v1.1)

Las decisiones aprobadas delimitan el universo de investigación. No autorizan a iniciar experimentos ni a operar.

## 1. Decisiones aprobadas

| ID | Decisión | Resultado | Fecha |
|---|---|---|---|
| D-000 | Fase 0 (Mean Reversion H1) | Cerrada, no aprobada; hipótesis cerrada permanentemente (`25f0e3f`) | 2026-11-08 |
| D-001 | Exchange | Binance | 2026-11-08 |
| D-002 | Mercado | Spot | 2026-11-08 |
| D-003 | Par | BTC/USDT | 2026-11-08 |
| D-004 | Horizonte | Swing Trading (horas a días); temporalidades 1H, 4H y 1D | 2026-11-08 |
| D-005 | Dirección | Long Only (FLAT → LONG → FLAT); sin cortos, margen, apalancamiento ni derivados | 2026-11-08 |
| D-006 | Holdout | LOCKBOX_OOS_001, un único uso confirmatorio global | 2026-11-08 |
| D-007 | Capital real | No autorizado | 2026-11-08 |
| D-008 | P-009: dataset derivado de investigación | **Autorizado** con aislamiento técnico. Implementado: `backtest/research/data/btcusdt_h1_research_v1.csv` | 2026-11-08 |
| D-009 | P-012: limpieza del lockbox | LOCKBOX_OOS_001 **no se certifica como plenamente ciego**. Se conserva como evaluación histórica restringida. La validación prospectiva es la evidencia confirmatoria principal. | 2026-11-08 |
| D-010 | P-013: uso del holdout | **Confirmado**: un único candidato y un único intento global. Si falla, el lockbox queda consumido; ningún candidato posterior lo usa. | 2026-11-08 |
| D-011 | P-010: ampliar histórico | **No autorizado** por ahora. Las limitaciones de muestra para 1D se declaran en cada experimento y no se compensan relajando criterios. | 2026-11-08 |
| D-012 | Costos no observables (antes P-011) | Comisión documentada con fuente y fecha; spread y slippage como **supuestos explícitos** con escenarios base y adverso; limitaciones de liquidez declaradas. Ninguna estimación se presenta como observación histórica. El Paper Trading servirá para calibrarlos. | 2026-11-08 |
| D-013 | CSV original de Fase 0 perdido | Registrado como incidencia permanente de trazabilidad (`INCIDENCIAS.md`, INC-001). No se reconstruye ni se sustituye. | 2026-11-08 |
| D-014 | Restricción fiscal de frecuencia | `MAX_TRADES_MONTH = 8` es **restricción dura no optimizable**. Régimen SAT 605 (asalariado). >10 ops/mes sostenido activa actividad empresarial. Escalado solo por capital (500→10,000 MXN), nunca por frecuencia. Ver `CRITERIOS_APROBACION.md` §1. | 2026-11-08 |
| D-015 | Criterios de aprobación (B-2) | **Aprobados.** Train: ≥50 ops, Sharpe >1.0, DD <10%, PF >1.5 (escenario adverso). LOCKBOX/Prospectiva: PF >1.2, DD <10%, expectancy >0, IC no cruza 0. Ver `CRITERIOS_APROBACION.md`. | 2026-11-08 |
| D-016 | Presupuesto global de experimentos (B-3) | **Aprobado.** Máx. 5 familias, 4 configs/familia, 20 configs total. Grid search libre prohibido. Toda variante preregistrada antes de ejecutarse. FASE-0 consume 1 familia y 4 configs. Escenarios de costo no cuentan como configs. Ver `REGISTRO_EXPERIMENTOS.md`. | 2026-11-08 |
| D-017 | Capital simulado y riesgo por operación (P-001, P-002) | Capital inicial simulado: **$3,000 MXN** (sujeto a que coincida con el capital real asignado). Riesgo: **0.5% del equity actualizado** por operación. | 2026-11-08 |
| D-018 | Kill switch de drawdown (P-003) | **10% DD sobre el equity inicial de cada fase.** Detiene nuevas operaciones al alcanzar el umbral. Sin reanudación automática. Requiere decisión humana para reiniciar. | 2026-11-08 |
| D-019 | Duración de E2 y Paper Trading (P-007) | **E2 (prospectiva):** mínimo 3 meses **y** mínimo de operaciones cerradas (definido por preregistro antes de iniciar). **Paper Trading (F):** mínimo 2 meses **y** mínimo de operaciones (ídem). La duración sola no es suficiente; ambas condiciones deben cumplirse. | 2026-11-08 |

## 2. Pendientes que bloquean la aprobación integral de QRP-001

Señalados en la resolución de revisión como prioritarios. Mientras sigan abiertos, no se inicia investigación.

| ID | Asunto | Estado |
|---|---|---|
| B-1 | Arquitectura del Quant Agent | Redactada: `ARQUITECTURA_QUANT_AGENT_v1.0.md`. Pendiente de revisión. |
| B-2 | Criterios de aprobación | **Cerrado** 2026-11-08 — D-015, `CRITERIOS_APROBACION.md` |
| B-3 | Control de experimentación | **Cerrado** 2026-11-08 — D-016, `REGISTRO_EXPERIMENTOS.md` |
| B-4 | Gestión del riesgo simulado | **Cerrado** 2026-11-08 — D-017, D-018, D-019 |
| B-5 | Capa 3 de aislamiento (sandbox) | **Cerrado** 2026-11-08. Las 4 vías verificadas. Ver `EVIDENCIA_AISLAMIENTO_LOCKBOX.md` §6. |

## 3. Otros pendientes

| ID | Asunto | Estado | Notas |
|---|---|---|---|
| P-001 | Capital inicial de simulación | Pendiente | Debe ser coherente con el notional mínimo de Binance. |
| P-002 | Riesgo máximo por operación | Pendiente | |
| P-003 | Drawdown máximo admisible | Propuesta: 10%, por aprobar | Comparar contra el DD de Buy & Hold del mismo periodo. |
| P-004 | Horizonte máximo de una posición | Por definir en cada preregistro | Puede fijarse un tope global. |
| P-005 | Comisión efectiva de Binance | Por documentar | Fuente y fecha de consulta; nivel VIP y descuento BNB (D-012). |
| P-006 | Presupuesto global de experimentos y configuraciones | Por aprobar | Necesario para el control de pruebas múltiples y el Deflated Sharpe. |
| P-007 | Duración de validación prospectiva y Paper Trading | Por aprobar | Con D-009, la prospectiva es la evidencia principal: su duración determina la potencia de la confirmación. |
| P-008 | Umbrales mínimos comunes de aprobación | Borrador | `CRITERIOS_APROBACION.md` |
| A-1 | Instalar `socat` y verificar la capa 3 | **Cerrado** 2026-11-08 | `socat` instalado; capa 3 verificada en sesión real (vía residual bloqueada). Ver `EVIDENCIA_AISLAMIENTO_LOCKBOX.md` §5. |
| A-2 | Perfil de permisos del Audit Agent | Pendiente | `ARQUITECTURA_QUANT_AGENT_v1.0.md` §10 |
| A-3 | Cargador de datos fail-closed (capa 4) | Pendiente | Con el primer experimento |
| A-4 | Script confirmatorio del lockbox | Pendiente | Cuando exista un candidato |

## 4. Historial de resoluciones

| Fecha | Resolución | Cierra |
|---|---|---|
| 2026-11-08 | Decisiones estratégicas QRP-001 v1.1 | D-001 a D-007 |
| 2026-11-08 | Resolución de revisión de QRP-001 v1.1 | P-009, P-010, P-011, P-012, P-013; registra INC-001 |

La incompatibilidad "un candidato por ciclo frente a uso único global" (antigua §3.1) queda resuelta por D-010. Las incompatibilidades de spread (§3.2), dataset con lockbox (§3.3) y muestra 1D (§3.4) quedan resueltas por D-012, D-008 y D-011 respectivamente.
