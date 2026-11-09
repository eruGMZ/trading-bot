# Auditoría integral — Preregistro EXP-0001 v3

**Documento auditado:** `backtest/experiments/EXP-0001/preregistration.md` (versión 3)
**Fecha de auditoría:** 2026-11-08
**Auditor:** Research Agent (Claude Code) — no es una aprobación humana
**Propósito:** determinar si el preregistro está metodológicamente completo, es internamente consistente y puede congelarse sin introducir ambigüedades en la implementación

---

## Resultado general

**APTO CON OBSERVACIONES**

No se detectan contradicciones metodológicas que invaliden el experimento. Los hallazgos de severidad ALTA son inconsistencias documentales corregibles antes del congelamiento. No se identifican fallas críticas de diseño. Se requiere resolución de los hallazgos A-1 a A-5 antes de congelar.

---

## Verificación de decisiones de referencia

### D-021 (Comisiones Binance)
- **REGISTRO_DECISIONES.md:** VIP 0, Maker 0.10%, Taker 0.10%, round-trip base 0.20%, adverso 0.30%. ✅
- **Preregistro §4:** valores coinciden numéricamente. ✅
- **Inconsistencia:** §4 todavía incluye el texto "Provisional. No congelado hasta verificación en panel de cuenta." — ver hallazgo A-1.
- **Preregistro §11:** fila de comisión aún muestra ⏳ Provisional — ver hallazgo A-1.

### D-022 (Capital inicial)
- **REGISTRO_DECISIONES.md:** 150.00 USDT aprobado; sin autorización de fondos reales. ✅
- **Preregistro §3.6:** 150.00 USDT declarado como exacto. ✅
- **Inconsistencia menor:** §3.6 incluye cláusula "si antes de congelar el preregistro el tipo de cambio difiere en más de ±10%, se revisa el capital" — ver hallazgo M-1.

---

## Hallazgos

### ALTA

---

**A-1 — §4 y §11: lenguaje "Provisional" no retirado tras cierre de D-021**

| Campo | Detalle |
|---|---|
| Sección | §4 (tabla de costos), §11 (tabla de aprobación) |
| Evidencia | §4: "Provisional. VIP 0 asumido… No congelado hasta verificación en panel de cuenta." §11: "⏳ Provisional (Maker 0.10% / Taker 0.10% sin BNB)" |
| Riesgo | El texto contradice la decisión D-021 ya registrada. Un lector del preregistro podría interpretar que las comisiones siguen sin confirmar, creando ambigüedad sobre si el congelamiento sigue bloqueado. |
| Corrección requerida | Reemplazar el texto de §4 (columna Naturaleza, fila Comisión) por: "Confirmado. VIP 0 verificado. Maker 0.10% + Taker 0.10%, sin BNB (decisión conservadora del modelo). Ver D-021." Actualizar §11: marcar la fila de comisión como ✅ con fecha 2026-11-08. |

---

**A-2 — §9: tipo de salida `end_of_data` ausente del registro de operaciones**

| Campo | Detalle |
|---|---|
| Sección | §9 (Registro de operaciones) |
| Evidencia | §9 lista los tipos de salida: `stop_normal`, `gap_bajista`, `stop_entrada`. §3.3 define un cuarto tipo: `end_of_data`. No está en el registro. |
| Riesgo | El código que implemente §9 no incluirá `end_of_data` como valor válido. Las operaciones de cierre administrativo quedarán sin tipo o provocarán un error en el registro. Las métricas de §5 calculadas sobre el registro incompleto serán incorrectas. |
| Corrección requerida | Agregar `end_of_data` a la lista de tipos de salida en §9. Especificar que las operaciones con `exit_type = end_of_data` se incluyen en las métricas (como declara §3.3) y que queda prohibido excluirlas. |

---

**A-3 — §5: método de anualización del Sharpe Ratio no especificado**

| Campo | Detalle |
|---|---|
| Sección | §5 (Criterios de aprobación de Train) |
| Evidencia | El criterio dice "Sharpe neto anualizado > 1.0" sin definir el factor de anualización. Para retornos H4 el factor es √(365×6) ≈ 46.8, para retornos de operaciones individuales depende de la frecuencia real, para escala diaria es √252. |
| Riesgo | Dos implementaciones del mismo backtest pueden producir Sharpe anualizados muy diferentes usando factores distintos. El criterio umbral de 1.0 no es comparable entre implementaciones sin fijar el factor. |
| Corrección requerida | Especificar: (a) base del retorno que entra al Sharpe (retorno por operación, diario, o por barra H4); (b) factor de anualización exacto; (c) si el Sharpe es Sharpe estándar (desviación de retornos) o Sharpe de Sortino (semidesviación). |

---

**A-4 — §8.1: calentamiento EMA200 dentro de ventanas Walk-Forward no especificado**

| Campo | Detalle |
|---|---|
| Sección | §8.1 (Walk-Forward) |
| Evidencia | §8.1 dice "los indicadores de cada ventana IS se calculan únicamente con datos anteriores al inicio de esa ventana IS." Pero la EMA200 requiere 200 velas H4 de calentamiento. Si la ventana IS de WF-02 comienza en el mes 3 del Train efectivo (~2023-09-03), y los primeros 200 bares H4 de calentamiento global van hasta ~2023-06-03, la ventana IS de WF-02 comienza antes de que la EMA200 sea válida. El preregistro no dice si cada ventana WF realiza su propio calentamiento de 200 barras (reduciendo el IS efectivo) o si reutiliza el calentamiento global. |
| Riesgo | Dos implementaciones pueden interpretar el límite de IS de forma diferente, produciendo ventanas OOS distintas y haciendo el Walk-Forward no reproducible. |
| Corrección requerida | Especificar: ¿las 200 barras de calentamiento de EMA200 en cada ventana WF consumen los primeros 200 bares del IS window, o se usa el calentamiento global del Train completo como contexto para todos los IS windows? |

---

**A-5 — §6: regla de selección cuando A falla pero otra configuración pasa**

| Campo | Detalle |
|---|---|
| Sección | §6 (Configuraciones) |
| Evidencia | §6 dice: "No se selecciona la que 'mejor funciona': se selecciona la que supera los criterios de §5. Si más de una los supera, se toma la base (A)." No especifica qué ocurre si A falla y solo B, C o D pasan los criterios. |
| Riesgo | Si A falla pero B pasa, el texto actual permite interpretar que B se selecciona (porque "supera los criterios de §5") o que ninguna se selecciona (porque la base no pasó). Esta ambigüedad permite una decisión discrecional post-resultados, que viola el propósito del preregistro. |
| Corrección requerida | Agregar explícitamente: "Si A no supera los criterios de §5 pero alguna otra configuración sí lo hace, [¿se selecciona esa configuración o se declara EXP-0001 fallido?]". Una de las dos reglas debe estar preregistrada. |

---

### MEDIA

---

**M-1 — §3.6: cláusula de revisión de capital por tipo de cambio es redundante post D-022**

| Campo | Detalle |
|---|---|
| Sección | §3.6 (Capital simulado) |
| Evidencia | "Si antes de congelar el preregistro el tipo de cambio difiere en más de ±10%, se revisa el capital y se documenta la actualización." D-022 aprobó explícitamente 150.00 USDT como capital exacto. |
| Riesgo | La cláusula sugiere que el capital aún puede cambiar tras D-022, creando una ventana de modificación post-decisión. Si el tipo de cambio cambia, un lector del preregistro podría modificar el capital sin nueva aprobación humana explícita. |
| Corrección requerida | Reemplazar la cláusula por: "Capital aprobado por decisión humana D-022 (2026-11-08). No se modifica." |

---

**M-2 — §8.3: CBB con mínimo 50 operaciones y bloques de 20 produce muy pocos bloques**

| Campo | Detalle |
|---|---|
| Sección | §8.3 (Bootstrap CBB) |
| Evidencia | Con 50 operaciones (mínimo permitido) y bloques de 20, el bootstrap dispone de ~2.5 bloques no solapados. Con bloques circulares hay más solapamiento pero la varianza del estimador es alta con tan pocos bloques. |
| Riesgo | El IC 95% con 2–3 bloques efectivos no es estadísticamente robusto. El criterio obligatorio de §5 (límite inferior IC > 0) podría aprobarse o rechazarse con alta sensibilidad a un puñado de operaciones. |
| Corrección requerida | Declarar explícitamente el comportamiento esperado: "Con el mínimo de 50 operaciones el bootstrap es válido pero la varianza del IC es alta; el resultado se reporta con esta advertencia." O elevar el mínimo de operaciones para bootstrap válido. No se requiere cambio numérico, pero la limitación debe quedar documentada en §8.3. |

---

**M-3 — §5 y CRITERIOS_APROBACION.md §2: IC bootstrap tiene diferente carácter en ambos documentos**

| Campo | Detalle |
|---|---|
| Sección | §5 del preregistro vs. §2 de CRITERIOS_APROBACION.md |
| Evidencia | CRITERIOS_APROBACION.md §2 marca el IC bootstrap como "Informativo". El preregistro §5 lo marca como obligatorio ("IC 95% bootstrap — límite inferior de expectancy neta > 0, Obligatorio: Sí"). |
| Riesgo | No es un error — el preregistro puede endurecer criterios (permitido por CRITERIOS_APROBACION.md). Pero la discrepancia puede confundir a un auditor futuro. |
| Corrección requerida | Agregar nota en §5: "Este preregistro endurece el criterio de IC bootstrap a obligatorio, en aplicación de CRITERIOS_APROBACION.md §2 que autoriza al preregistro a endurecerlo. Decisión preregistrada antes de ver resultados." |

---

**M-4 — §7: "Buy & Hold escalado al tiempo invertido" sin definición operacional**

| Campo | Detalle |
|---|---|
| Sección | §7 (Benchmarks) |
| Evidencia | El tercer benchmark es "Buy & Hold escalado al tiempo invertido (exposición equivalente a la estrategia)" sin especificar cómo se calcula la exposición ni el método de escalado. |
| Riesgo | Dos implementaciones pueden calcular el benchmark de forma diferente, haciendo la comparación no replicable. |
| Corrección requerida | Definir: "tiempo invertido = suma de bares H4 en posición / total de bares H4 del Train; retorno escalado = retorno Buy & Hold total × fracción de tiempo en posición." O la fórmula equivalente que se prefiera. |

---

**M-5 — Notional mínimo de Binance no declarado en el preregistro**

| Campo | Detalle |
|---|---|
| Sección | No existe sección |
| Evidencia | El notional mínimo de Binance Spot para BTC/USDT es 10 USDT por orden. Con 150 USDT de capital, 0.5% de riesgo = 0.75 USDT de riesgo. Si el ATR es muy elevado (p.ej., ATR14 = 5,000 USDT con precio 65,000 USDT), el tamaño calculado podría ser tan pequeño que el notional (`tamaño_BTC × precio_entrada`) sea menor de 10 USDT. Esta restricción no existe para la simulación, pero tampoco se declara. |
| Riesgo | Si el backtest de Train produce operaciones válidas pero con notional < 10 USDT, esas operaciones no podrían ejecutarse en Binance en validación prospectiva. No invalida el backtest pero crea una discrepancia entre Train y E2. |
| Corrección requerida | Agregar nota en §3.6 o §9: "El backtest no aplica el notional mínimo de Binance (10 USDT). Antes de E2, verificar que los tamaños calculados producen notional ≥ 10 USDT en las condiciones de capital esperadas." |

---

### BAJA

---

**B-1 — §3.4: especificación de suavizado del EMA200**

| Campo | Detalle |
|---|---|
| Sección | §3.2 y §3.4 |
| Evidencia | "EMA200" sin especificar el factor de suavizado. El estándar de la industria es α = 2/(N+1) = 2/201 ≈ 0.00995. El ATR sí especifica "Wilder smoothing" (α = 1/N). La EMA no especifica su variante. |
| Corrección requerida | Agregar: "EMA200 calculada con factor de suavizado α = 2/(200+1) (EMA exponencial estándar)." |

---

**B-2 — §3.4: especificación de suavizado del ADX14**

| Campo | Detalle |
|---|---|
| Sección | §3.2 |
| Evidencia | "ADX14" sin especificar que usa Wilder smoothing para DX, +DI y −DI, igual que el ATR. ADX tiene variantes (Wilder original vs. EMA exponencial). |
| Corrección requerida | Agregar: "ADX14 calculado con el método de Wilder (smoothing α = 1/14) para +DI, −DI y el suavizado final del DX." |

---

**B-3 — §5: definición de Maximum Drawdown (peak vs. capital inicial)**

| Campo | Detalle |
|---|---|
| Sección | §5 |
| Evidencia | "Maximum Drawdown < 10% del capital inicial" especifica el denominador como capital inicial, lo cual es más conservador que usar el equity máximo. Pero no especifica si el DD se calcula sobre la curva de equity continua o solo en los momentos de cierre de operaciones. |
| Corrección requerida | Agregar: "DD calculado sobre la curva de equity al cierre de cada operación (trade-by-trade), con denominador igual al capital inicial de 150.00 USDT." |

---

**B-4 — §2.1 regla 4: "su resultado" es ambiguo (¿configuración o experimento completo?)**

| Campo | Detalle |
|---|---|
| Sección | §2.1 |
| Evidencia | "su resultado de Train se declara inválido" — "su" podría referirse a la configuración específica que tenía la posición abierta, o al experimento EXP-0001 completo. Si las 4 configuraciones comparten el mismo backtest y la misma discontinuidad, todas podrían verse afectadas. |
| Corrección requerida | Aclarar: "el resultado de Train de esa configuración se declara inválido. Las demás configuraciones se evalúan de forma independiente." |

---

## Verificaciones adicionales

**¿Se usan resultados de Fase 0 como evidencia de EXP-0001?**
No. El preregistro referencia H-001 y el rechazo de H-000 solo como motivación económica (§ de REGISTRO_HIPOTESIS.md), no como datos de Train ni como criterio de aprobación. ✅

**¿Hay modificaciones post-v3 que alteren decisiones aprobadas?**
§2.1 y §3.3 fueron agregados en esta sesión (D.H2 de la auditoría del agente) con aprobación humana explícita. Las modificaciones son aditivas y no alteran parámetros de §3–§6. ✅

**¿Hay parámetros que permitan decisiones discrecionales después de ver resultados?**
Hallazgo A-5 (regla de selección cuando A falla). Los demás parámetros están completamente fijados. ✅ con excepción de A-5.

**¿Hay supuestos implícitos no declarados?**
- Wilder smoothing para ADX (hallazgo B-2).
- Factor de anualización del Sharpe (hallazgo A-3).
- Calentamiento dentro de ventanas WF (hallazgo A-4).

**Coherencia con QRP-001 y políticas de datos:**
- Dataset derivado y SHA-256 coinciden con MANIFEST.json. ✅
- Cargador fail-closed referenciado. ✅
- Segmento Train no cruza el lockbox. ✅
- Declaración de conocimiento del lockbox presente (vía REGISTRO_HIPOTESIS.md). ✅
- Presupuesto: 4/20 configs consumidas, total acumulado 8/20. ✅
- Restricción fiscal MAX_TRADES_MONTH = 8 declarada (§3.7). ✅

---

## Tabla resumen

| ID | Sección | Severidad | Descripción breve | Bloquea congelamiento |
|---|---|---|---|---|
| A-1 | §4, §11 | ALTA | Lenguaje "Provisional" no retirado tras D-021 | Sí |
| A-2 | §9 | ALTA | `end_of_data` ausente del registro de operaciones | Sí |
| A-3 | §5 | ALTA | Método de anualización del Sharpe no especificado | Sí |
| A-4 | §8.1 | ALTA | Calentamiento EMA200 en ventanas WF no especificado | Sí |
| A-5 | §6 | ALTA | Regla de selección ambigua cuando A falla | Sí |
| M-1 | §3.6 | MEDIA | Cláusula de revisión de capital redundante post D-022 | No |
| M-2 | §8.3 | MEDIA | CBB con 50 ops y bloques de 20 produce muy pocos bloques | No |
| M-3 | §5 | MEDIA | IC obligatorio en preregistro vs. informativo en CRITERIOS | No |
| M-4 | §7 | MEDIA | Benchmark escalado sin definición operacional | No |
| M-5 | §3.6 | MEDIA | Notional mínimo Binance no declarado | No |
| B-1 | §3.2 | BAJA | Factor de suavizado EMA200 no especificado | No |
| B-2 | §3.2 | BAJA | Suavizado ADX14 no especificado | No |
| B-3 | §5 | BAJA | DD trade-by-trade vs. continuo no especificado | No |
| B-4 | §2.1 | BAJA | "su resultado" ambiguo: ¿configuración o experimento? | No |

**Bloqueadores del congelamiento:** A-1, A-2, A-3, A-4, A-5 (5 hallazgos ALTA).
**Observaciones sin bloqueo:** M-1 a M-5, B-1 a B-4 (9 hallazgos MEDIA/BAJA).

---

## Lo que este reporte no hace

- No modifica el preregistro.
- No cierra D-H3.
- No congela ningún documento.
- No ejecuta backtests ni cálculos.
- No aprueba el preregistro — la aprobación corresponde exclusivamente al humano.

La aprobación final es D-H3 y requiere resolución de los 5 hallazgos ALTA descritos arriba.
