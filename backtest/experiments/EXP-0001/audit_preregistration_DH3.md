# Resolución de auditoría D-H3 — EXP-0001

**Documento auditado:** `preregistration.md` v3
**Documento corregido:** `preregistration.md` v4
**Fecha:** 2026-11-09
**Auditoría de referencia:** `audit_preregistration_final.md`

---

## Matriz de resolución

| ID | Hallazgo | Resolución aplicada | Sección modificada | Evidencia | Estado |
|---|---|---|---|---|---|
| **A-1** | §4 y §11: lenguaje "Provisional" no retirado tras cierre de D-021 | §4 columna Naturaleza reemplaza "Provisional / No congelado" por "Confirmado (D-021, 2026-11-08) / Ver verificacion_comisiones_D-H1.md". §11 actualiza la fila de comisión a ✅ con decisión D-021; agrega fila de capital D-022. | §4, §11 | Texto de D-021: VIP 0, Maker 0.10%, Taker 0.10%, sin BNB. Coincide con §4 actualizado. | **RESUELTO** |
| **A-2** | `end_of_data` ausente del registro de operaciones §9 | §9 reescrito como tabla con todos los campos. `exit_type` lista explícitamente `end_of_data` como cuarto tipo. Se agrega nota: "Todas las operaciones con `exit_type` definido se incluyen en las métricas, incluidas `end_of_data`." | §9 | El campo `exit_type` incluye los cuatro tipos; la nota prohíbe excluir `end_of_data` de métricas. Coherente con §3.3. | **RESUELTO** |
| **A-3** | Sharpe "anualizado" sin especificar el factor de anualización ni la base del retorno | Nuevo §5.1 con la definición completa: retorno H4 mark-to-market, factor √2190, tasa libre de riesgo = 0, desviación estándar muestral. Fórmula explícita. | §5 (nuevo §5.1) | Fórmula: `Sharpe = (μ_H4 / σ_H4) × √2190`. Factor justificado: 6 H4/día × 365 días = 2,190. | **RESUELTO** |
| **A-4** | Calentamiento EMA200 dentro de ventanas WF no especificado | §8.1 reescrito: cada ventana IS realiza su propio calentamiento de 200 bares H4 anteriores a su inicio. Distinción explícita entre reutilización histórica (no es look-ahead) y uso de resultados para modificar parámetros (prohibido). | §8.1 | Regla documentada: warmup cronológicamente anterior al IS de cada ventana; no genera señales ni métricas. | **RESUELTO** |
| **A-5** | Regla de selección ambigua cuando A falla pero otra configuración pasa | §6 reescrito: A es primaria confirmatoria; H-001 se aprueba si y solo si A supera los criterios. Si A falla, EXP-0001 cierra sin candidato. B/C/D son exploratorias; sus resultados quedan documentados pero no rescatan la hipótesis primaria ni autorizan etapas posteriores. | §6 | La regla preregistrada elimina la ambigüedad post-resultados. | **RESUELTO** |
| **M-1** | Cláusula de revisión de capital redundante post D-022 | La cláusula "si el tipo de cambio difiere en ±10%, se revisa el capital" fue eliminada. Reemplazada por: "Capital aprobado por D-022. No se modifica." | §3.6 | D-022 fija 150.00 USDT de forma definitiva. La cláusula de tipo de cambio ya no aplica. | **RESUELTO** |
| **M-2** | CBB con 50 ops y bloques de 20 produce muy pocos bloques | Agregada advertencia explícita: con 50 ops y bloques de 20, ~2.5 bloques no solapados, varianza alta. Agregado análisis de sensibilidad informativo con bloques de 10. Se prohíbe elegir el tamaño que produzca el resultado más favorable. | §8.3 | Advertencia documentada. Tamaño oficial sigue siendo 20. | **RESUELTO** |
| **M-3** | IC obligatorio en preregistro vs. informativo en CRITERIOS_APROBACION.md | Decisión humana D-023 (2026-11-09): IC 95% es criterio obligatorio para EXP-0001 / H-001. §5.3 actualizado con la regla definitiva. CRITERIOS_APROBACION.md §2 mantiene IC como informativo para el protocolo general; EXP-0001 lo endurece por cláusula expresa. D-023 no modifica D-015 ni ninguna decisión anterior. | §5 (§5.3 actualizado), §11 | D-023 en REGISTRO_DECISIONES.md. §5 tabla: IC marcado como obligatorio. §11: fila actualizada a ✅ D-023. | **RESUELTO** |
| **M-4** | Benchmark "escalado al tiempo invertido" sin definición operacional | §7 reescrito con tres subsecciones (§7.1, §7.2, §7.3), cada una con fórmulas explícitas, fechas y capital inicial. §7.3 define exposición como fracción de velas H4 en posición y el retorno escalado como `fraccion_expuesta × retorno_BH_total`. | §7 | Las tres fórmulas son replicables. El benchmark escalado responde a la pregunta de valor añadido sobre la mera exposición. | **RESUELTO** |
| **M-5** | Notional mínimo Binance no declarado en el preregistro | §9 agrega nota sobre notional mínimo (~10 USDT referencial, verificar antes de E2) y stepSize (~0.00001 BTC referencial). Se declara que son valores aproximados a fecha del preregistro y deben verificarse en la API de Binance antes de E2. El backtest de Train no aplica el filtro. | §9 | Los valores se declaran expresamente como aproximados. No invalidan Train. Bloquean E2 si no se verifican. | **RESUELTO** |
| **B-1** | Benchmarks sin fórmulas consistentes en todos los reportes | §7 define las tres fórmulas con variables nombradas. Los futuros reportes de Train deberán usar exactamente estas definiciones. No hay otros lugares del preregistro donde se mencionen benchmarks. | §7 | Las fórmulas de §7.1, §7.2 y §7.3 son la referencia canónica. | **RESUELTO** |
| **B-2** | Restricciones de ejecución (notional, rounding) no verificadas | §9 documenta la regla de redondeo: `tamano_btc` se redondea hacia abajo al múltiplo de stepSize más cercano. Los valores exactos de stepSize y notional mínimo se verifican antes de E2. | §9 | "Redondeo hacia abajo al múltiplo de stepSize más cercano antes de calcular el PnL." | **RESUELTO** |
| **B-3** | Suavizado EMA200 y ADX14 no especificados | §3.2 agrega: EMA200 con α = 2/(200+1); ADX14 con método Wilder para TR, +DM, −DM, +DI14, −DI14, DX, ADX14. §3.4 agrega: ATR14 con α = 1/14, inicialización con media simple de primeros 14 TR. | §3.2, §3.4 | Especificaciones completas. No hay ambigüedad de implementación. | **RESUELTO** |
| **B-4** | DD trade-by-trade vs. continuo y expresiones "su resultado" ambiguas | §5.2 define DD mark-to-market sobre curva H4 continua como criterio obligatorio. DD sobre operaciones cerradas se declara métrica complementaria informativa. §2.1 regla 4 sustituye "su resultado" por "el resultado de Train de esa configuración". | §5 (nuevo §5.2), §2.1 | DD obligatorio = mark-to-market H4; DD complementario = sobre ops cerradas. Expresión ambigua eliminada. | **RESUELTO** |

---

## Decisiones que requieren aprobación humana

| ID | Decisión | Sección | Estado |
|---|---|---|---|
| **P-DH3-01** | IC bootstrap obligatorio para EXP-0001 | §5.3 | ✅ Resuelto — D-023 (2026-11-09) |

**No quedan decisiones pendientes de aprobación humana en esta auditoría.**

---

## Verificación de consistencia documental

| Verificación | Resultado |
|---|---|
| §3, §4, §5, §6, §8, §9 y §11 sin contradicciones internas | ✅ Verificado |
| Coherencia con QRP-001 (D-004, D-005, D-014) | ✅ Long Only, H4, MAX_TRADES_MONTH=8 declarados |
| Coherencia con D-015 (criterios de aprobación) | ✅ Umbrales coinciden; IC pendiente de confirmación |
| Coherencia con D-021 (comisiones) | ✅ §4 y §11 actualizados |
| Coherencia con D-022 (capital) | ✅ §3.6 y §11 actualizados |
| Sin parámetros nuevos no preregistrados | ✅ No se introdujeron variantes ni parámetros de estrategia |
| Presupuesto experimental sin cambios | ✅ 4 unidades EXP-0001, total acumulado 8/20 |
| Regla de selección no permite modificar hipótesis primaria post-resultados | ✅ A es primaria; fallo de A cierra EXP-0001 |
| Ningún texto autoriza el backtest antes de aprobación humana | ✅ §11 mantiene "Bloqueado hasta aprobación" |
| Fase 0 no usada como evidencia de EXP-0001 | ✅ No hay referencias a resultados de Fase 0 |

---

## Confirmación

No se ejecutó ningún backtest.
No se consultaron datos OOS ni el lockbox.
No se modificaron parámetros de la estrategia ni configuraciones A/B/C/D.
No se alteró el presupuesto experimental.
No se declaró el preregistro aprobado ni congelado.

**El preregistro v4 está en estado BORRADOR.** El único bloqueador activo para el congelamiento es P-DH3-01 (decisión humana sobre IC bootstrap).
