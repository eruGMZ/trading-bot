# Fundamento del horizonte Swing Trading

**Identificador:** D-025
**Protocolo:** QRP-001 v1.1
**Fecha:** 2026-11-09
**Estado:** Aprobado por decisión humana
**Sustituye:** la intención previa de convertir el bot 1.0.0 (`master`) en un bot de scalping
**No sustituye:** D-004 (el horizonte Swing ya estaba decidido); este documento es el fundamento que D-004 no contenía

---

## 1. Propósito

Dejar por escrito por qué el proyecto **no** evolucionó el bot operativo 1.0.0 hacia scalping, y por qué el universo de investigación quedó restringido a **Swing Trading** (horas a días; temporalidades 1H, 4H y 1D).

Sin este documento, D-004 aparece como un dato del universo operativo, no como el cierre de un planteamiento anterior. Un auditor o un agente futuro podría reabrir scalping como si nunca se hubiera descartado.

Este texto no autoriza capital real, no reabre la 1.0.0 y no relaja D-014.

## 2. Planteamiento original (descartado)

La 1.0.0 en `master` es un bot en vivo (Bitso BTC/MXN, Telegram, RSI vía TradingView CDP, loop de ~60 s). El plan inicial era **reemplazar ese modo de operación por un bot de scalping**: alta frecuencia intradía, decisiones en minutos o segundos, presencia continua frente al mercado.

Ese plan era una conversión de producto, no una línea de investigación QRP-001. No llegó a preregistrarse como experimento. Queda descartado aquí para que no se retome por omisión.

## 3. Por qué scalping es incompatible

Tres restricciones independientes. Cualquiera basta para cerrar scalping; juntas lo hacen no negociable.

### 3.1 Modo de trabajo del operador

El responsable es **empleado de tiempo completo**. No puede:

- vigilar pantallas en horario laboral;
- reaccionar a microestructura, spreads o eventos de segundos;
- mantener un loop de ejecución que exija intervención o supervisión intradía;
- operar un stack que depende de sesión gráfica, CDP y latencia local (el diseño de la 1.0.0).

Scalping asume un operador disponible en la sesión de mercado o un sistema autónomo con supervisión continua. Ninguna de las dos condiciones se cumple.

Un backtest de scalping “que sale bien” no elimina esta restricción: el edge de scalping, si existiera, vive en la ejecución. Sin operador ni infraestructura de baja latencia, el resultado de laboratorio no es transferible.

### 3.2 Tope fiscal de frecuencia (D-014)

`MAX_TRADES_MONTH = 8` es restricción dura, no parámetro. Régimen SAT 605 (sueldos y salarios). Superar ~10 operaciones/mes de forma sostenida empuja a actividad empresarial.

Scalping, por definición, produce decenas o cientos de operaciones al mes. Una variante de scalping que “cumpla 8 ops/mes” ya no es scalping: es otra estrategia disfrazada, y no se registra como tal.

Consecuencia: scalping queda **fuera del universo** igual que derivados o cortos. No se investiga, no se preregistra, no se usa como benchmark de frecuencia.

### 3.3 Desalineación con el producto 1.0.0

La 1.0.0 no es un motor de scalping (RSI H1-like, 3 trades/día tope de código, Bitso, sin libro de órdenes). Forzarla a scalping sería reescribir el sistema, no un cambio de parámetros. Ese esfuerzo no se justifica si el horizonte viable es Swing.

La 1.0.0 se descarta como producto operativo. El trabajo posterior a `1.0.0` vive en `develop` como laboratorio QRP-001, no como parche del bot en vivo.

## 4. Por qué Swing es el horizonte residual viable

Swing (posiciones de horas a días) es el único horizonte que satisface a la vez:

| Restricción | Encaje |
|---|---|
| Empleo de tiempo completo | Las decisiones caben fuera de horario o en un ciclo automático de velas cerradas (H1/H4/1D), sin microgestión |
| Máx. 8 ops/mes | Frecuencia natural de Swing; el tope fiscal deja de ser un recorte artificial |
| Spot long-only BTC/USDT | Hold de horas/días es el uso canónico de spot sin margen |
| Evidencia de Fase 0 | Mean Reversion H1 (más cercano a intradía) fue rechazado; H-001 apunta a H4 de forma coherente con este horizonte |

Temporalidades permitidas (D-004, protocolo §5): **1H, 4H, 1D**. 1H es señal o entrada, no licencia para scalping: una hipótesis cuya frecuencia esperada exceda 8 ops/mes, o cuya ventaja dependa de ticks/minutos, queda fuera de alcance aunque use velas de 1H.

## 5. Qué queda fuera de alcance

No se investiga ni se propone:

- scalping, market making, o cualquier estrategia cuya tesis requiera más de 8 operaciones/mes;
- reconvertir la 1.0.0 (Bitso, Telegram, CDP) en el vehículo de una estrategia QRP-001;
- relajar D-014 “solo para probar”;
- intradía de alta frecuencia con otra etiqueta (p. ej. “mean reversion M1/M5”).

Una solicitud de volver a scalping es un cambio de universo: aprobación humana nueva, experimento independiente, y choque explícito con D-014. El agente no puede reabrirla por iniciativa propia.

## 6. Relación con decisiones ya tomadas

| ID | Relación |
|---|---|
| D-004 | Fija el horizonte Swing. Este documento es su fundamento retrospectivo. |
| D-014 | El tope de 8 ops/mes hace a scalping estructuralmente ilegal en este proyecto. |
| D-001 a D-003, D-005 | Universo Binance Spot BTC/USDT Long Only: compatible con Swing, no con scalping de libro. |
| D-007 | Capital real no autorizado. El cambio de horizonte no implica operar. |
| D-000 / H-000 | Fase 0 (H1 mean reversion) cerrada; no se reinterpreta como “casi scalping” ni se reabre. |
| H-001 / EXP-0001 | Primera familia viva (Trend Following H4) nace ya dentro de este horizonte. |

## 7. Consecuencias

1. El bot 1.0.0 no es la base del siguiente sistema en producción. Un bot futuro, si existe, se diseña después de un candidato que pase Train, lockbox y prospectiva, con horizonte Swing.
2. Toda hipótesis nueva debe declarar frecuencia esperada y máxima. Si la máxima supera 8 ops/mes, se rechaza en preregistro, sin backtest.
3. `develop` conserva el laboratorio (`backtest/`). El código de la 1.0.0 en la raíz es legado, no línea de producto.

## 8. Qué no cambia

- No autoriza Train de EXP-0001 por sí solo (sigue D-024 y revisión humana del runner).
- No autoriza el lockbox ni capital.
- No modifica umbrales de `CRITERIOS_APROBACION.md`.
- No amplia temporalidades ni familias.
