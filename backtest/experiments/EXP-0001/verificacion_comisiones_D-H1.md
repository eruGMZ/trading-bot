# Verificación de comisiones — D.H1

**Experimento:** EXP-0001
**Decisión que desbloquea:** congelamiento del preregistro v3
**Estado:** CERRADO — evidencia registrada; decisión de modelo adoptada (2026-11-08)
**Fecha de apertura:** 2026-11-08
**Fecha de cierre:** 2026-11-08

---

## 1. Qué debe verificarse

La comisión declarada en el preregistro v3 §4 es **provisional**:

| Parámetro | Valor provisional | Fuente |
|---|---|---|
| Maker fee (Spot) | 0.10% | Tabla oficial Binance Spot, VIP 0 |
| Taker fee (Spot) | 0.10% | Tabla oficial Binance Spot, VIP 0 |
| Descuento BNB | No activo | Asumido |
| Round-trip base | 0.20% | Maker + Taker |
| Round-trip adverso | 0.30% | Base + spread 0.05% + slippage 0.05% |

Estos valores deben confirmarse contra la cuenta real antes de congelar.

---

## 2. Checklist de verificación

Verificar **en el panel de la cuenta Binance**, no en la tabla pública:

- [ ] **Fee tier actual** — ir a *Cuenta → Nivel de comisión* (o *Fee Rate*). Confirmar que es VIP 0.
- [ ] **Maker fee efectivo** — anotar el porcentaje que muestra el panel para operaciones Spot Maker.
- [ ] **Taker fee efectivo** — anotar el porcentaje para Spot Taker.
- [ ] **BNB discount** — ¿está activada la opción "Usar BNB para pagar comisiones"? Si sí, anotar el descuento vigente (actualmente 25% para VIP 0, es decir 0.075%/0.075%).
- [ ] **Volumen 30 días** — verificar que el volumen Spot de los últimos 30 días no supera el umbral de VIP 1 (1,000,000 USDT), que reduciría las fees a 0.09%/0.10%.

---

## 3. Escenarios y su impacto en el modelo de costos

Dependiendo del resultado, el parámetro `fee_round_trip` del preregistro cambia:

| Escenario | Maker | Taker | Round-trip base | Adverso | Acción requerida |
|---|---|---|---|---|---|
| **A — VIP 0, sin BNB** (supuesto actual) | 0.10% | 0.10% | 0.20% | 0.30% | Ninguna; confirmar y congelar. |
| **B — VIP 0, con BNB** | 0.075% | 0.075% | 0.15% | 0.25% | Actualizar §4 antes de congelar; recalcular dimensionamiento en §3.6. |
| **C — VIP 1, sin BNB** | 0.09% | 0.10% | 0.19% | 0.29% | Actualizar §4; diferencia marginal, revisar si afecta criterios de aprobación. |
| **D — VIP 1, con BNB** | 0.0675% | 0.075% | 0.1425% | ~0.24% | Actualizar §4; recalcular dimensionamiento. |

**Regla de decisión:** si el escenario real difiere del supuesto (A), el preregistro se actualiza en §4 antes de congelar. No es necesario cambiar la fórmula de dimensionamiento (§3.6), solo el valor de `fee_round_trip_adverso` que entra en `costo_unitario`.

---

## 4. Impacto en el dimensionamiento de posición

La fórmula de §3.6 es:

```
costo_unitario = precio_entrada × fee_round_trip_adverso
riesgo_bruto   = distancia_stop + costo_unitario
tamaño_BTC     = riesgo_USDT / riesgo_bruto
```

Un cambio en `fee_round_trip_adverso` modifica `tamaño_BTC` levemente. Ejemplo con precio de entrada = 65,000 USDT/BTC, ATR14 = 1,200 USDT, equity = 150 USDT:

| Escenario | fee adverso | costo_unitario | riesgo_bruto | tamaño_BTC | variación vs A |
|---|---|---|---|---|---|
| A (0.30%) | 0.0030 | 195.00 USDT | 1,395.00 USDT | 0.0005376 BTC | — |
| B (0.25%) | 0.0025 | 162.50 USDT | 1,362.50 USDT | 0.0005505 BTC | +2.4% |
| D (0.24%) | 0.0024 | 156.00 USDT | 1,356.00 USDT | 0.0005531 BTC | +2.9% |

La variación es menor al 3% en el caso más favorable. No cambia el comportamiento cualitativo del sistema.

---

## 5. Resultado registrado

**Fuente:** IA integrada de Binance, consultada 2026-11-08.

```
Fecha de verificación: 2026-11-08
Fee tier verificado:   VIP 0 (Regular)
Maker fee efectivo:    0.10%
Taker fee efectivo:    0.10%
Volumen Spot 30 días:  0 USD (cuenta sin historial operativo)
Actualización de nivel: diaria a las 08:00 UTC
BNB discount (cuenta): NO VERIFICADO — no confirmado ni descartado
  — Descuento BNB aplicado al modelo: 0% (decisión conservadora)
Round-trip base real:  0.20%
Escenario adoptado:    A (VIP 0, sin descuento BNB en el modelo)
Acción tomada:         Confirmar sin cambios en §4 del preregistro
```

**Decisión de modelo sobre BNB (2026-11-08):**
El estado real del descuento BNB en la cuenta no fue verificado. Se adopta escenario A (sin descuento BNB) como **decisión conservadora del modelo**, no como afirmación sobre la configuración real de la cuenta. Si en el futuro se activa BNB, el modelo resulta conservador (sobreestima costos); no es una sobreoptimización, es un margen de seguridad.

**Parámetros del preregistro §4 — sin cambios:**

| Componente | Base | Adverso |
|---|---|---|
| Comisión Binance round-trip | 0.20% | 0.20% |
| Spread estimado | 0.02% | 0.05% |
| Slippage | 0.00% | 0.05% |
| **Total round-trip** | **0.22%** | **0.30%** |

---

## 6. Qué no hace este documento

- No modifica ningún parámetro del preregistro (los valores §4 ya eran correctos).
- No congela el preregistro (requiere además D.H2 y D.H3).
- No ejecuta backtests ni cálculos con datos reales.

**D.H1 está cerrado.** Ver entrada en `REGISTRO_DECISIONES.md`.
