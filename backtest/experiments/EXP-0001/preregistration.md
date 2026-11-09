# Preregistro — EXP-0001

**Hipótesis:** H-001
**Familia:** Trend Following
**Temporalidad principal:** H4
**Fecha de preregistro:** 2026-11-08
**Versión:** 4 (resolución de hallazgos D-H3: A-1 a A-5, M-1 a M-5, B-1 a B-4)
**Estado:** ✅ CONGELADO — aprobado humanamente (D-024, 2026-11-09). No modificar sin nueva decisión registrada.
**Fecha de congelamiento:** 2026-11-09

---

## 1. Pregunta de investigación

¿Puede una estrategia long-only de Trend Following en H4 sobre BTC/USDT generar retornos positivos ajustados por riesgo, netos de costos de ejecución, en el segmento Train (2023-05-01 → 2025-11-07)?

## 2. Datos

| Atributo | Valor |
|---|---|
| Dataset | `backtest/research/data/btcusdt_h1_research_v1.csv` |
| SHA-256 | `6b4b42003db49b7abc5f8fe74391149eb64143a204cc98bd15c5c24646639c1c` |
| Cargador | `backtest/research/data_loader.py` (fail-closed, capa 4) |
| Temporalidad de trabajo | H4 — agregado de 4 velas H1; cierres UTC 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 |
| Segmento Train | `open_time` < 2025-11-08T00:00Z (limitado por el dataset derivado) |
| Calentamiento | Primeras 200 velas H4 (~33 días) reservadas para EMA200; no generan señales ni operaciones |
| Train efectivo | Aprox. 2023-06-03 → 2025-11-07 (~29 meses) |

**Agregación H4:** se usa OHLCV estándar (open de la primera H1, close de la cuarta, high/low máximo/mínimo del bloque, volume suma). Una vela H4 es válida solo cuando las cuatro H1 que la componen están presentes y cerradas. Si falta alguna H1 dentro del bloque, **el bloque completo se descarta**: no genera indicadores ni señales. Este comportamiento se verifica en el código antes del primer backtest.

### 2.1 Tratamiento de discontinuidades temporales

1. Cada bloque H4 debe contener exactamente cuatro velas H1 consecutivas, completas y válidas.
2. Los bloques incompletos se descartan íntegramente y no generan indicadores, señales ni ejecuciones.
3. Toda discontinuidad en la secuencia H4 debe detectarse explícitamente.
4. Si una configuración mantiene una posición abierta al comenzar una discontinuidad temporal, **el resultado de Train de esa configuración** se declara inválido. Las demás configuraciones se evalúan de forma independiente. No se inventan precios de ejecución ni se presume que el stop permaneció sin ejecutar.
5. Si la discontinuidad ocurre sin una posición abierta, se reinicia el calentamiento de indicadores. Se requieren 200 velas H4 consecutivas, completas y válidas antes de habilitar nuevas señales.
6. Una señal anterior a una discontinuidad no puede ejecutarse después de ella.
7. Toda invalidación debe documentar el intervalo afectado, la configuración, el estado de posición y el último stop vigente.

**Regla de cierre del segmento:** el dataset debe contener una última vela H4 completa cuyo cierre coincida con el límite temporal establecido para Train. Si no existe, debe declararse un problema de integridad del segmento antes de evaluar resultados.

## 3. Lógica de la estrategia

### 3.1 Máquina de estados

FLAT → LONG → FLAT (QRP-001 §8). Sin posiciones cortas ni simultáneas.

### 3.2 Señal de entrada (FLAT → LONG)

**Condición:** se cumplen simultáneamente en la vela H4 recién cerrada (vela `t`):

1. `close[t] > EMA200[t]` — precio de cierre por encima de la EMA de 200 períodos H4.
   - Factor de suavizado: α = 2 / (200 + 1) ≈ 0.00995 (EMA exponencial estándar).
   - Inicialización: media simple de las primeras 200 velas H4 del periodo de calentamiento.
   - Si hay una discontinuidad, el calentamiento se reinicia desde cero (§2.1 regla 5).
2. `ADX14[t] > 25` — ADX de 14 períodos H4 indica tendencia activa.
   - Calculado con el método de Wilder (smoothing α = 1/14) para +DI, −DI y el suavizado final del DX.
   - Componentes: TR (True Range), +DM, −DM, +DI14, −DI14, DX, ADX14 (suavizado Wilder de DX).
   - Se requieren al menos 14 + 14 = 28 velas H4 válidas para la primera lectura del ADX14 tras el calentamiento; en la práctica el calentamiento de 200 velas garantiza la inicialización.

**Ejecución:** entrada al `open[t+1]`, el precio de apertura real de la siguiente vela H4. Si `open[t+1]` difiere de `close[t]` por un gap, se usa `open[t+1]` sin ajuste — nunca se asume el precio del cierre anterior.

**Nota EMA200 vs EMA50:** la propuesta inicial del agente mencionó EMA50. El usuario especificó EMA200 de forma explícita. No se usa EMA50 en este preregistro.

### 3.3 Señal de salida (LONG → FLAT)

**Mecanismos de salida:**

1. **Trailing stop por ATR** (§3.4) — único mecanismo operativo. No hay salida por reversión de señal.
2. **Cierre administrativo al fin del segmento** (`end_of_data`) — si el segmento Train termina con una posición abierta, la posición se liquida al `close` de la última vela H4 completa del Train, con costos aplicados en escenario adverso (§4). Este cierre **sí se incluye en las métricas** (Sharpe, PF, DD, expectancy) y queda identificado con `exit_type = end_of_data`. No se contabiliza como señal operativa del mecanismo de trailing stop. El precio de liquidación debe corresponder a una vela H4 completa real del dataset; si no existe, se declara un problema de integridad del segmento (§2.1 regla de cierre).

### 3.4 Stop loss, trailing stop y regla de vigencia

#### Stop inicial
Calculado en el momento de la entrada con datos de la vela `t` (cerrada):

```
stop_inicial = open[t+1] − ATR_mult × ATR14[t]
```

- `ATR14[t]`: ATR calculado con Wilder smoothing (α = 1/14) sobre la vela `t`. Inicializado con la media simple de los primeros 14 TR. Requiere al menos 14 velas H4 válidas; el calentamiento de 200 velas garantiza la inicialización.
- `ATR_mult`: múltiplo según la configuración (§6).
- **El stop inicial puede ejecutarse durante la misma vela H4 en que se abre la posición** (`t+1`).

#### Trailing stop — regla de vigencia (sin look-ahead)

El stop vigente al inicio de una vela es el único que puede ejecutarse durante esa vela. El nuevo nivel calculado al cierre entra en vigor en la vela siguiente:

| Momento | Acción |
|---|---|
| Inicio de vela `t+k` | Stop vigente = nivel calculado al cierre de `t+k−1`. **Único ejecutable durante `t+k`.** |
| Cierre de vela `t+k` | Nuevo nivel = `max(stop_vigente, close[t+k] − ATR_mult × ATR14[t+k])`. |
| Inicio de vela `t+k+1` | El nuevo nivel entra en vigor. |

El stop **solo sube, nunca baja**. El cierre de una vela no puede ejecutar ni modificar el stop de esa misma vela.

### 3.5 Simulación de la ejecución del stop — todos los casos

Con esta estrategia no existe TP, por lo que el único evento de salida es el stop. Los casos posibles en una vela `t+k` son:

| Caso | Condición | Precio de ejecución | Notas |
|---|---|---|---|
| Sin ejecución | `low[t+k] > stop_vigente` | — | Posición continúa |
| Ejecución normal | `low[t+k] ≤ stop_vigente` y `open[t+k] > stop_vigente` | `stop_vigente` | Conservador: se asume ejecución en el stop, no mejor |
| Gap bajista | `open[t+k] ≤ stop_vigente` | `open[t+k]` | Peor caso real; la pérdida excede el 0.5% objetivo (ver §3.6) |

No existe ambigüedad de orden de eventos porque no hay TP. No se simula ningún precio mejor que `stop_vigente` ni que `open[t+k]`. Si `open[t+k] ≤ stop_vigente`, se usa `open[t+k]` aunque sea inferior — nunca `stop_vigente`.

**Vela de entrada con stop inmediato:** si en la vela `t+1` (vela de entrada) `low[t+1] ≤ stop_inicial` y `open[t+1] > stop_inicial`, la posición se cierra en `stop_inicial` dentro de la misma vela. Esta operación se registra con duración de una vela H4.

### 3.6 Dimensionamiento de posición

**Principio:** el 0.5% del equity es la **pérdida máxima estimada** si el stop se ejecuta exactamente al nivel previsto, en el escenario de costos adverso. Los gaps pueden exceder ese límite (declarado como riesgo residual).

#### Fórmula

```
equity_USDT     = capital actual en USDT
riesgo_USDT     = equity_USDT × 0.005

precio_entrada  = open[t+1]  en USDT/BTC
stop_inicial    = precio_entrada − ATR_mult × ATR14[t]
distancia_stop  = precio_entrada − stop_inicial   (en USDT/BTC; > 0 siempre)

costo_unitario  = precio_entrada × fee_round_trip_adverso
                  (0.003 para 0.30%; simplificación conservadora: se usa precio de entrada
                   para ambas patas, aunque la salida sea a menor precio)

riesgo_bruto    = distancia_stop + costo_unitario

tamaño_BTC      = riesgo_USDT / riesgo_bruto
```

#### Verificación algebraica de la garantía

```
pérdida_max = tamaño_BTC × (distancia_stop + costo_unitario)
            = (riesgo_USDT / riesgo_bruto) × riesgo_bruto
            = riesgo_USDT
            = equity_USDT × 0.005  ✓
```

La garantía se cumple **si y solo si** el stop ejecuta exactamente a `stop_vigente`. En caso de gap, la pérdida real es:

```
pérdida_gap = tamaño_BTC × ((precio_entrada − open[t+k]) + costo_unitario)
            > riesgo_USDT   porque (precio_entrada − open[t+k]) > distancia_stop
```

Un gap de 1% en el precio del stop equivale a ~+0.12 pp adicionales de riesgo sobre el equity (verificado numéricamente). Este exceso se declara como **riesgo residual de gaps**, inherente a cualquier estrategia con stop-loss en datos OHLC.

#### Capital simulado

**Capital inicial: 150.00 USDT** (exacto). Conversión de referencia: 3,000 MXN ÷ 20.00 MXN/USDT = 150.00 USDT. El tipo de cambio 20.00 MXN/USDT queda como referencia declarada en este preregistro. La simulación opera en USDT; no hay conversión a MXN dentro del backtest.

Capital aprobado por decisión humana D-022 (2026-11-08). No se modifica. La conversión de referencia a MXN no participa en ningún cálculo del backtest.

### 3.7 Filtro de frecuencia (D-014)

- El conteo de operaciones es **por fecha de apertura** (mes calendario UTC del `open[t+1]`).
- Si en el mes calendario ya se abrieron 8 operaciones, no se abre ninguna más ese mes.
- Una posición abierta en un mes puede cerrarse en uno diferente sin restricción.
- Una posición que atraviesa el cambio de mes se contabiliza solo en el mes de apertura.

## 4. Modelo de costos

Los porcentajes son del **notional total de la operación** (precio × tamaño en USDT), aplicados como costo round-trip agregado (ida + vuelta combinados). No son porcentajes por lado.

| Componente | Base | Adverso | Naturaleza |
|---|---|---|---|
| Comisión Binance Spot (round-trip) | 0.20% | 0.20% | **Confirmado (D-021, 2026-11-08).** VIP 0 verificado: Maker 0.10% + Taker 0.10%. Descuento BNB: 0% (decisión conservadora del modelo; estado real en cuenta no verificado). Ver `EXP-0001/verificacion_comisiones_D-H1.md`. |
| Spread estimado BTC/USDT | 0.02% | 0.05% | **Supuesto.** Round-trip agregado sobre notional. Par de alta liquidez. |
| Slippage de entrada y salida | 0.00% | 0.05% | **Supuesto.** Adverso cubre llenados parciales o gaps en el open. |
| **Total round-trip** | **0.22%** | **0.30%** | Suma de los tres componentes. |

Aplicación: `costo_operacion_USDT = tamaño_BTC × precio_entrada × fee_round_trip`. El costo se netea contra el PnL bruto de cada operación antes de calcular cualquier métrica. Ningún supuesto de spread/slippage se presenta como observación histórica.

## 5. Criterios de aprobación de Train

Según `CRITERIOS_APROBACION.md` §2 (D-015). La **configuración A** debe cumplir **todos** en escenario adverso para que EXP-0001 apruebe su hipótesis primaria. No hay criterios informativos: todos son obligatorios.

| Métrica | Umbral | Obligatorio | Definición operacional |
|---|---|---|---|
| Operaciones cerradas | ≥ 50 | Sí | Operaciones con `exit_time` definido, incluye `end_of_data` |
| Sharpe neto anualizado | > 1.0 | Sí | Ver fórmula §5.1 |
| Maximum Drawdown | < 10% del capital inicial | Sí | Ver definición §5.2 |
| Profit Factor neto | > 1.5 | Sí | Suma de PnL neto positivos / valor absoluto suma de PnL neto negativos |
| Expectancy neta por operación | > 0 USDT | Sí | Media aritmética de PnL neto de todas las operaciones cerradas |
| Ops/mes promedio (por apertura) | ≤ 8 | Sí | Total operaciones / meses de Train efectivo, contadas por fecha de apertura |
| IC 95% bootstrap — límite inferior de expectancy neta | > 0 | Sí | Ver §5.3 |

Si algún criterio no se cumple, la configuración A no aprueba aunque los demás sí.

### 5.1 Definición del Sharpe Ratio anualizado

**Base del retorno:** retorno neto por intervalo H4, calculado como:

```
retorno_H4[t] = (equity[t] − equity[t−1]) / equity[t−1]
```

donde `equity[t]` es el equity mark-to-market al cierre de la vela H4 `t` (incluye PnL no realizado de posiciones abiertas y costos ya aplicados). Los periodos FLAT tienen `retorno_H4 = 0`.

**Frecuencia:** 6 intervalos H4 por día × 365 días = 2,190 periodos anuales.

**Fórmula:**

```
Sharpe_anualizado = (μ_H4 / σ_H4) × √2190
```

donde:
- `μ_H4` = media aritmética de los retornos H4 netos del Train completo.
- `σ_H4` = desviación estándar muestral (divisor N−1) de los retornos H4 netos.
- Tasa libre de riesgo = 0.
- El factor √2190 convierte el Sharpe por-barra a anual.

### 5.2 Definición del Maximum Drawdown

**DD calculado sobre la curva de equity mark-to-market por vela H4** (criterio obligatorio):

```
DD[t] = (equity_pico[t] − equity[t]) / capital_inicial
```

donde `equity_pico[t] = max(equity[0], …, equity[t])` y `capital_inicial = 150.00 USDT`.

La curva de equity incorpora: PnL realizado, PnL no realizado (posición valorada al `close` de cada H4), costos aplicados y equity durante periodos FLAT.

**DD calculado sobre operaciones cerradas** (métrica complementaria, informativa): diferente al criterio obligatorio. No puede sustituirlo.

### 5.3 IC bootstrap — criterio obligatorio (D-023)

El IC 95% bootstrap de la expectancy neta es un **criterio obligatorio de aprobación** para EXP-0001 / H-001, por decisión humana D-023 (2026-11-09).

**Regla:** el límite inferior del IC 95% de la expectancy neta debe ser estrictamente > 0. Si el IC incluye cero, la configuración primaria A no supera el criterio estadístico.

**Método principal:** CBB, 10,000 iteraciones, bloques de 20 operaciones, confianza 95%, semilla 20261108. Este es el único método que determina la aprobación.

**Sensibilidad informativa:** se calculará adicionalmente con bloques de 10 operaciones. Este análisis es informativo y no puede rescatar un resultado desfavorable del método principal ni sustituirlo.

**Limitación muestral:** con el mínimo de 50 operaciones y bloques de 20, la varianza del estimador es alta. Las 10,000 iteraciones no eliminan esta limitación estructural. El resultado se reporta con la advertencia correspondiente cuando el número de operaciones esté cerca del mínimo.

`CRITERIOS_APROBACION.md` §2 clasifica el IC como informativo para el protocolo general. Este preregistro lo endurece a obligatorio para EXP-0001 en aplicación de la cláusula "un preregistro puede endurecerlos, nunca relajarlos". Ver D-023.

## 6. Configuraciones

Presupuesto disponible antes de EXP-0001: 16/20. Este experimento consume máximo 4 unidades.

| Config | ADX umbral | ATR múltiplo SL/Trail | Descripción |
|---|---|---|---|
| **EXP-0001-A** | 25 | 2.0 × ATR14 | Configuración base |
| **EXP-0001-B** | 20 | 2.0 × ATR14 | ADX más permisivo |
| **EXP-0001-C** | 25 | 1.5 × ATR14 | Stop más ajustado |
| **EXP-0001-D** | 25 | 3.0 × ATR14 | Stop más holgado |

Todas comparten: EMA200 H4, entrada en apertura de vela siguiente, trailing stop ATR, sin salida por reversión de señal.

**Rol de cada configuración:**
- **EXP-0001-A** es la configuración **primaria confirmatoria**. La hipótesis H-001 se aprueba si y solo si A supera todos los criterios de §5. Si A falla, EXP-0001 se declara fallido respecto de su hipótesis primaria, independientemente de los resultados de B, C y D.
- **EXP-0001-B, C y D** son configuraciones **secundarias exploratorias**. Se evalúan conforme a los mismos criterios de §5 y sus resultados se documentan. Si alguna supera los criterios pero A falla, sus resultados quedan registrados como exploratorios y **no rescatan la hipótesis primaria ni autorizan automáticamente la siguiente fase**.

**Regla de selección:** se evalúan las 4 en todos los casos; el presupuesto se consume aunque A falle. No se selecciona la que "mejor funciona". Si A supera los criterios, A es el candidato único a etapas posteriores (E1, E2). Si A falla, no hay candidato y EXP-0001 cierra sin candidato aprobado.

**Consumo del presupuesto:** EXP-0001 consume 4 unidades → total acumulado 8/20.

## 7. Benchmarks

Los tres benchmarks se calculan sobre el mismo segmento Train, con el mismo capital inicial de 150.00 USDT. No se aplican costos de transacción a los benchmarks.

### 7.1 Buy & Hold BTC

```
equity_BH[t] = 150.00 × (close_H4[t] / close_H4[t_inicio])
```

donde `t_inicio` es el primer cierre H4 del Train efectivo (~2023-06-03). Curva continua por vela H4.

### 7.2 USDT sin rendimiento

```
equity_USDT[t] = 150.00  (constante)
```

Retorno 0 en todo el periodo. Sin intereses ni rendimientos.

### 7.3 Buy & Hold escalado al tiempo invertido

Mide el retorno de BTC ponderado por la fracción del tiempo que la estrategia estuvo en posición:

```
fraccion_expuesta = (número de velas H4 con posición abierta) / (total de velas H4 del Train efectivo)

retorno_BH_total  = (close_H4[t_fin] / close_H4[t_inicio]) − 1

retorno_escalado  = fraccion_expuesta × retorno_BH_total

equity_escalado   = 150.00 × (1 + retorno_escalado)
```

Este benchmark responde a la pregunta: "¿Qué hubiera ganado si hubiera comprado BTC solo durante las velas en que la estrategia estuvo expuesta, distribuyendo la ganancia proporcionalmente?" Permite evaluar si la estrategia agrega valor sobre la mera exposición al activo.

## 8. Validación robusta (Etapa D)

Solo se ejecuta si la configuración aprobada pasa los criterios de Train (§5).

### 8.1 Walk-Forward

- **Tipo:** rolling, parámetros **fijos** (los de la configuración aprobada, sin reoptimización en ninguna ventana).
- **Ventana in-sample (IS):** 18 meses.
- **Paso (step):** 3 meses.
- **Ventanas resultantes con 29 meses de Train efectivo:** 4 ventanas.
  - WF-01: IS mes 0–18, OOS mes 18–21 (3m)
  - WF-02: IS mes 3–21, OOS mes 21–24 (3m)
  - WF-03: IS mes 6–24, OOS mes 24–27 (3m)
  - WF-04: IS mes 9–27, OOS mes 27–29 (2m)
- **Calentamiento por ventana:** cada ventana IS realiza su propio calentamiento de indicadores de forma independiente. Los 200 bares H4 anteriores al inicio del IS de cada ventana sirven de calentamiento para EMA200; los 14 + 14 bares anteriores sirven para ADX14; los 14 anteriores para ATR14. Este calentamiento usa datos cronológicamente anteriores al IS de esa ventana — no es look-ahead. Las velas de calentamiento no generan señales ni operaciones y quedan excluidas de las métricas de esa ventana.
- **Distinción entre reutilización histórica y look-ahead:** en un rolling WF, el IS de una ventana posterior solapará cronológicamente con el IS o el OOS de una ventana anterior. Esto es reutilización de datos históricos y no constituye fuga de información. Lo que sí está prohibido es usar los **resultados** (PnL, configuración elegida, métricas) de una ventana para modificar los parámetros de cualquier ventana posterior.
- **Sin fugas:** los parámetros evaluados en una ventana OOS no se usan para ajustar la configuración antes de la siguiente ventana IS.
- **Métrica de estabilidad:** los resultados de los cuatro periodos OOS deben ser todos positivos en expectancy neta. Se reporta la dispersión.

### 8.2 Sensibilidad de parámetros

- Evalúa ±20% del ATR múltiplo y ±5 unidades del umbral ADX alrededor de los valores de la configuración aprobada.
- **Esta evaluación es informativa y no consume presupuesto de B-3.** No genera configuraciones nuevas ni modifica la selección.
- No puede usarse para elegir parámetros distintos de los preregistrados.

### 8.3 Bootstrap circular por bloques (CBB)

**Unidad de remuestreo:** retornos individuales de operaciones (PnL neto por operación en USDT), no velas.

**Justificación:** las operaciones son el elemento estadístico independiente de la estrategia. Remuestrear velas no captura la autocorrelación a nivel de operación. Remuestrear operaciones individuales preserva la distribución de retornos y permite estimar la varianza del estimador de expectancy.

**Parámetros:**

| Parámetro | Valor |
|---|---|
| Método | Circular block bootstrap (CBB) |
| Iteraciones | 10,000 |
| Nivel de confianza | 95% (α = 0.05) |
| Unidad | Retorno neto de cada operación cerrada |
| Tamaño de bloque | 20 operaciones (aproximadamente 2–3 meses con 8 ops/mes; captura autocorrelación serial) |
| Semilla | 20261108 |
| Métrica | Expectancy neta media (USDT por operación) |
| IC | Percentiles 2.5 y 97.5 de la distribución bootstrap |

**Dependencia temporal:** el CBB preserva la estructura de autocorrelación dentro de cada bloque. El tamaño de 20 operaciones se elige conservadoramente para capturar correlación entre operaciones consecutivas (efecto de rachas ganadoras/perdedoras). Si el número total de operaciones es menor de 50, el bootstrap no es válido (coincide con el criterio mínimo de §5).

**Validez estadística:** el IC bootstrap es válido bajo la hipótesis de que los retornos de operaciones son aproximadamente estacionarios y que las colas de la distribución están representadas en la muestra. Con < 50 operaciones o sin superar los criterios de §5, el IC no se calcula.

**Advertencia — base limitada con 50 operaciones:** con el mínimo de 50 operaciones y bloques de 20, el CBB dispone de ~2.5 bloques no solapados. La varianza del estimador de expectancy será alta y el IC resultante debe interpretarse con cautela. Las 10,000 iteraciones no eliminan esta limitación estructural. Si el backtest produce exactamente 50 operaciones, el IC se reporta con esta advertencia explícita.

**Análisis de sensibilidad del tamaño de bloque (informativo):** se calculará adicionalmente con bloques de 10 operaciones para evaluar la estabilidad del IC. Este análisis es informativo y no modifica el criterio de aprobación. No se elige el tamaño de bloque que produzca el resultado más favorable: el tamaño oficial es 20.

## 9. Registro de operaciones

Cada operación registra los siguientes campos:

| Campo | Descripción |
|---|---|
| `open_time_entrada` | Timestamp UTC de apertura de la posición (= open de la vela `t+1`) |
| `open_time_salida` | Timestamp UTC de cierre; `None` solo si el evento es `end_of_data` sin vela H4 real (no debería ocurrir con la regla de cierre de §2.1) |
| `precio_entrada` | USDT/BTC; `open[t+1]` |
| `precio_salida` | USDT/BTC; `stop_vigente`, `open[t+k]` (gap) o `close` de última H4 completa (`end_of_data`) |
| `exit_type` | `stop_normal` / `gap_bajista` / `stop_entrada` / `end_of_data` |
| `nivel_stop_inicial` | USDT/BTC |
| `nivel_stop_salida` | Nivel del stop vigente en el momento del cierre |
| `atr_mult` | Múltiplo ATR de la configuración |
| `tamano_btc` | Tamaño de la posición en BTC |
| `pnl_bruto_usdt` | `tamano_btc × (precio_salida − precio_entrada)` |
| `costo_usdt` | `tamano_btc × precio_entrada × fee_round_trip_adverso` |
| `pnl_neto_usdt` | `pnl_bruto_usdt − costo_usdt` |
| `equity_pre_usdt` | Equity antes de abrir la posición |
| `equity_post_usdt` | Equity después del cierre |

**Inclusión en métricas:** todas las operaciones con `exit_type` definido se incluyen en las métricas de §5, incluidas las de tipo `end_of_data`. Ningún tipo de salida se excluye del cálculo de Sharpe, PF, DD ni expectancy.

**Notional mínimo de Binance (referencia para E2):** el backtest no aplica el notional mínimo de Binance Spot (aproximadamente 10 USDT para BTC/USDT en la fecha de este preregistro; verificar en la API de Binance antes de E2). Si alguna operación del Train produce `tamano_btc × precio_entrada < 10 USDT`, se registra como advertencia en el reporte pero no invalida el backtest de Train. Deberá verificarse antes de la validación prospectiva E2. El stepSize de BTC/USDT en Binance Spot es aproximadamente 0.00001 BTC; el tamaño calculado se redondea hacia abajo al múltiplo de stepSize más cercano antes de calcular el PnL (la diferencia es despreciable pero debe ser consistente). Los valores exactos de notional mínimo y stepSize deben verificarse en la API de Binance antes de E2.

## 10. Lo que invalida este preregistro

- Modificar cualquier parámetro de §3–§6 después de ver resultados de Train.
- Ejecutar backtest antes de aprobación humana y congelamiento.
- Usar datos fuera del segmento Train (incluido el lockbox).
- Agregar configuraciones no listadas en §6 después de ver resultados.
- Usar el análisis de sensibilidad de §8.2 para elegir parámetros distintos de los preregistrados.

## 11. Estado de aprobación

| Paso | Estado |
|---|---|
| H-001 formulada | ✅ 2026-11-08 |
| Señal, stop y configuraciones definidos | ✅ v3 2026-11-08 |
| Dimensionamiento verificado algebraicamente | ✅ v3 2026-11-08 |
| Ejecución intravela — todos los casos documentados | ✅ v3 2026-11-08 |
| Bootstrap — método, unidad y validez especificados | ✅ v3 2026-11-08 |
| Walk-Forward — ventanas y no-fuga verificadas | ✅ v3 2026-11-08 |
| Sensibilidad vs. presupuesto — aclarado | ✅ v3 2026-11-08 |
| Comisión Binance verificada en panel de cuenta | ✅ **Confirmado** (D-021, 2026-11-08) — Maker 0.10% / Taker 0.10% / BNB: 0% por decisión conservadora |
| Capital inicial confirmado | ✅ **Confirmado** (D-022, 2026-11-08) — 150.00 USDT |
| Hallazgos A-1 a A-5 y M-1 a M-5 y B-1 a B-4 resueltos | ✅ v4 2026-11-09 — ver `audit_preregistration_DH3.md` |
| IC bootstrap — obligatorio para EXP-0001 | ✅ **Confirmado** (D-023, 2026-11-09) — ver §5.3 |
| Revisión humana y congelamiento (D-H3) | ✅ **APROBADO Y CONGELADO** (D-024, 2026-11-09) |
| Inicio de backtest | ✅ **Autorizado** — después del congelamiento |
