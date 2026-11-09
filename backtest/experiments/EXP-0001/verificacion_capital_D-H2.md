# Verificación de capital inicial — D.H2

**Experimento:** EXP-0001
**Decisión que desbloquea:** congelamiento del preregistro v3
**Estado:** CERRADO — aprobación humana recibida (2026-11-08)
**Fecha de apertura:** 2026-11-08
**Fecha de cierre:** 2026-11-08

---

## 1. Capital aprobado

| Parámetro | Valor |
|---|---|
| Capital inicial simulado | **150.00 USDT** (exacto) |
| Equivalencia de referencia | 3,000 MXN ÷ 20.00 MXN/USDT = 150.00 USDT |
| Tipo de cambio de referencia | 20.00 MXN/USDT (declarado en el preregistro; no usado en la simulación) |
| Moneda operativa del backtest | **USDT** |
| Conversiones cambiarias durante la simulación | **Ninguna** |

El tipo de cambio 20.00 MXN/USDT es únicamente una referencia para contextualizar el capital en moneda local. La simulación opera íntegramente en USDT y no realiza conversiones.

---

## 2. Alcance de esta aprobación

Esta decisión autoriza el uso de 150.00 USDT como capital inicial en la **simulación histórica** de EXP-0001.

**No constituye:**
- Autorización para operar fondos reales.
- Autorización para transferir, depositar ni retirar capital en ninguna cuenta.
- Autorización para ejecutar ninguna operación en mercado real.

La aprobación de capital real es una decisión independiente que sigue el proceso establecido en QRP-001 §18 y queda fuera del alcance de este preregistro.

---

## 3. Consistencia con otros parámetros del preregistro

El valor de 150.00 USDT es coherente con:

| Parámetro | Relación |
|---|---|
| Riesgo por operación (§3.6) | 0.5% × 150.00 = 0.75 USDT máximo por trade |
| Kill switch de DD (D-018) | 10% × 150.00 = 15.00 USDT de drawdown máximo |
| Notional mínimo Binance Spot | 10 USDT — verificar antes de E2 que el tamaño_BTC × precio_entrada ≥ 10 USDT en el primer trade |

El notional mínimo de Binance no bloquea el Train (simulación), pero deberá verificarse antes de la validación prospectiva (E2).

---

## 4. Qué permanece sin cambios

- Preregistro v3 §3.6: capital declarado como 150.00 USDT — **ya correcto, sin modificación**.
- Parámetros de sizing, criterios de aprobación (§5) y configuraciones (§6): sin cambios.
- Estado del preregistro: BORRADOR — pendiente D-H3.

**D-H2 está cerrado.** Ver entrada D-022 en `REGISTRO_DECISIONES.md`.
