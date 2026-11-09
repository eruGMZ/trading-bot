# Reporte de auditoría — Preregistro EXP-0001 v3

**Fecha:** 2026-11-08
**Versión auditada:** v3
**Auditor:** Research Agent (Claude Code)
**Estado:** Para revisión humana — no es una aprobación

---

## 1. Hallazgos y correcciones aplicadas

### 1.1 Críticos (corregidos en v3)

| # | Hallazgo | Corrección |
|---|---|---|
| C-1 | Fórmula de dimensionamiento mezclaba unidades (multiplicar distancia_SL por tipo_cambio no produce tamaño correcto en BTC) | Fórmula reescrita en USDT puro: `tamaño_BTC = riesgo_USDT / (distancia_stop_USDT + costo_unitario_USDT)`. Verificada algebraicamente: pérdida al stop exacto = riesgo_USDT = equity × 0.5%. |
| C-2 | No quedaba claro cuándo se evalúa el stop intravela vs. cuándo se actualiza el trailing | Regla de vigencia explícita: el stop del cierre de `t+k` entra en vigor en `t+k+1`. Solo el stop del inicio de la vela puede ejecutarse durante esa vela. |
| C-3 | IC bootstrap aparecía como "informativo" en §5 pero como obligatorio en §8 | Criterio unificado en §5: límite inferior IC 95% > 0 es criterio de aprobación obligatorio. Eliminada la ambigüedad. |

### 1.2 Alta prioridad (corregidos en v3)

| # | Hallazgo | Corrección |
|---|---|---|
| A-1 | Sensibilidad ±20% ATR y ±5 ADX podía leerse como configuraciones adicionales que consumen presupuesto | Declarado explícitamente en §6 y §8.2: la sensibilidad es análisis de robustez, no consume presupuesto de B-3 ni modifica la selección. |
| A-2 | Capital de 150 USDT era aproximado con tipo de cambio no fijado | Capital exacto 150.00 USDT, tipo de cambio 20.00 MXN/USDT declarado como referencia; ajuste si difiere ±10% antes de congelar. |
| A-3 | 0.5% no especificaba si incluía costos o solo distancia al stop | Definido como pérdida máxima estimada incluyendo costos adversos. La fórmula usa `riesgo_bruto = distancia_stop + costo_unitario`. |
| A-4 | Conteo de frecuencia mensual no aclaraba posiciones que cruzan mes ni si contaban aperturas o cierres | Aclarado en §3.7: conteo por fecha de apertura; una posición puede cruzar el mes sin restricción. |

### 1.3 Observaciones adicionales (corregidas en v3)

| # | Hallazgo | Corrección |
|---|---|---|
| O-1 | No se definía qué hacer con un bloque H4 con H1 faltante | §2: bloque incompleto se descarta; no genera indicadores ni señales. |
| O-2 | No se aclaraba que la entrada usa el `open` real si hay gap | §3.2: se usa `open[t+1]` sin ajuste, nunca el close anterior. |
| O-3 | No se mencionaba que el stop puede ejecutarse en la vela de entrada | §3.4: documentado explícitamente. |
| O-4 | Spread y slippage no aclaraban si eran porcentajes por lado o round-trip | §4: declarados como round-trip agregado sobre notional; no por lado. |
| O-5 | Walk-Forward no especificaba número de ventanas ni separación temporal | §8.1: 4 ventanas detalladas con sus rangos exactos; verificadas con 29 meses de Train. |
| O-6 | Bootstrap no especificaba unidad de remuestreo (velas vs. operaciones) | §8.3: unidad = retornos de operaciones individuales; justificación metodológica incluida. |

### 1.4 Punto no modificado

| # | Punto | Decisión |
|---|---|---|
| P-1 | Comisión Binance 0.10%/0.10% | Mantenida como **provisional** hasta verificación en panel. No congelada. |

---

## 2. Verificaciones numéricas realizadas

### 2.1 Dimensionamiento (precio referencia 65,000 USDT/BTC, ATR14 = 1,200 USDT, equity 150 USDT)

| Escenario | Pérdida | % del equity |
|---|---|---|
| Stop ejecuta exactamente | 0.750000 USDT | **0.5000%** ✅ |
| Gap bajista de 1% en el precio del stop | 0.930925 USDT | 0.6206% (exceso: +0.12 pp) |

El exceso en gaps es el riesgo residual declarado en §3.6. BTC/USDT es un par líquido y los gaps en H4 son poco frecuentes, pero no eliminables.

### 2.2 Walk-Forward (29 meses Train efectivo, ventana 18m, paso 3m)

4 ventanas cubren el Train completo. La última ventana OOS tiene 2 meses en lugar de 3 (por el límite del Train). Esto es aceptable y se declara en §8.1.

---

## 3. Riesgos metodológicos residuales

| Riesgo | Severidad | Mitigación declarada |
|---|---|---|
| **Gaps bajistas pueden exceder el 0.5% de riesgo** | Media | Declarado en §3.6; inherente a datos OHLC. Paper Trading medirá la frecuencia real. |
| **Comisión no verificada en panel de cuenta** | Alta (bloquea congelamiento) | §4 y §11 marcan el parámetro como provisional. |
| **Bootstrap válido solo con ≥ 50 ops** | Media | Coincide con el criterio mínimo de §5; si no hay 50 ops, tampoco hay aprobación. |
| **Train limitado a ~29 meses efectivos** | Media | Declarado; Walk-Forward tiene solo 4 ventanas OOS (~11 meses de test total). |
| **Conocimiento del mercado en el periodo del lockbox** | Declarado | `POLITICA_DATOS_OOS.md` §4.3 y `REGISTRO_HIPOTESIS.md` H-001. |
| **EMA200 requiere 200 velas H4 de calentamiento** | Baja | §2 excluye el calentamiento del Train; el Train efectivo comienza ~2023-06-03. |

---

## 4. Decisiones que requieren aprobación humana antes de congelar

| # | Decisión | Bloquea |
|---|---|---|
| **D-H1** | Verificar comisiones reales en panel Binance (Maker/Taker; ¿BNB activo?) | Congelamiento del preregistro |
| **D-H2** | Confirmar capital exacto de 150.00 USDT (o actualizar si tipo de cambio difirió) | Congelamiento |
| **D-H3** | Aprobar el preregistro v3 en su totalidad | Inicio del backtest |

---

## 5. Lo que el preregistro v3 no resuelve (fuera de su alcance)

- El código del backtest aún no existe. La consistencia entre el preregistro y el código se verifica antes de ejecutar (Etapa B → C).
- A-4 (script confirmatorio del lockbox) no es necesario para Train; solo para E1.
- La duración mínima de E2 (N operaciones) se define en este preregistro solo como "pendiente por preregistro", conforme a D-019.

---

## 6. Conclusión de la auditoría

El preregistro v3 no contiene contradicciones metodológicas detectables. Las siete correcciones obligatorias y las seis observaciones adicionales de la revisión anterior quedan resueltas. El único bloqueador activo es la verificación de comisiones en el panel Binance.

**El preregistro está metodológicamente listo para congelamiento**, sujeto a las tres decisiones humanas de §4.
