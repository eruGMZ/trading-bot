# Registro de hipótesis — QRP-001

Historial de todas las hipótesis formuladas, incluidas las descartadas antes de experimentar. Una entrada no se borra; solo cambia de estado.

| ID | Fecha | Familia | Hipótesis | Experimento | Estado |
|---|---|---|---|---|---|
| H-000 | 2026-11-08 | Mean Reversion | RSI(14) H1 sobrevendido con filtro EMA200 H4 genera rebotes explotables en BTC/USDT | Fase 0 (`25f0e3f`) | Cerrada: rechazada |
| H-001 | 2026-11-08 | Trend Following | BTC/USDT exhibe tendencias direccionales persistentes en H4, impulsadas por momentum y ciclos de adopción institucional/minorista, que pueden explotarse de forma sistemática en dirección larga cuando el precio confirma una tendencia alcista, generando retornos positivos ajustados por riesgo netos de costos de ejecución en el segmento Train | EXP-0001 | Abierta: preregistro congelado (D-024, 2026-11-09) — Train autorizado |

---

## H-001 — Fundamento económico y falsabilidad

### Fundamento económico

BTC/USDT presenta condiciones estructurales que favorecen el seguimiento de tendencias en marcos de tiempo medianos (H4):

1. **Momentum institucional.** Las entradas y salidas de capital institucional (ETFs spot, tesorerías corporativas, fondos macro) se ejecutan en bloques grandes y sobre períodos de días a semanas. Esto genera presión sostenida en una dirección antes de que el precio se equilibre.

2. **FOMO y retroalimentación minorista.** Una vez establecida una tendencia visible, la participación minorista la amplifica. Este mecanismo es más pronunciado en BTC que en mercados de renta variable tradicional.

3. **Ausencia de reversión a la media en horizontes medios.** La hipótesis H-000 (Mean Reversion H1) fue rechazada con evidencia: las desviaciones del precio respecto a su media no se revierten consistentemente en H1. Esto es compatible con la existencia de autocorrelación positiva de retornos en horizontes más largos (H4/1D).

4. **Asimetría estructural long-only.** BTC tiene un sesgo histórico alcista de largo plazo derivado de la reducción programática de la oferta (halvings). Una estrategia long-only captura ese sesgo sin incurrir en el riesgo de posiciones cortas en un activo con volatilidad extrema al alza.

5. **Marco H4 y frecuencia.** H4 reduce el ruido intradía, produce menos señales que H1 (compatible con el límite fiscal de 8 ops/mes) y alinea el horizonte de operación con ciclos de acumulación/distribución observables en el precio.

### Predicción concreta y falsable

> En el segmento Train (2023-05-01 → 2025-11-07), una estrategia long-only de Trend Following en H4 sobre BTC/USDT, con señal de entrada basada en la confirmación de tendencia alcista y salida por reversión de señal o stop loss por ATR, generará:
> - Profit Factor neto > 1.5 (escenario adverso)
> - Sharpe Ratio neto anualizado > 1.0 (escenario adverso)
> - Maximum Drawdown < 10%
> - ≥ 50 operaciones cerradas
> - ≤ 8 operaciones promedio por mes

La hipótesis queda **refutada** si alguno de estos criterios no se cumple en el escenario adverso, o si el resultado no es distinguible del Buy & Hold ajustado por exposición.

### Influencia del conocimiento del lockbox

El periodo del lockbox (2025-11-08 → 2026-10-31) corresponde a un periodo ya transcurrido. La elección de Trend Following H4 no se basa en observaciones de ese periodo, sino en el rechazo empírico de Mean Reversion (H-000) y en el razonamiento económico anterior. Se declara que el agente puede tener conocimiento general del comportamiento de BTC durante ese periodo a través de sus datos de entrenamiento, conforme a `POLITICA_DATOS_OOS.md` §4.3.

### Lo que NO especifica esta hipótesis

Los siguientes elementos se definen en el preregistro de EXP-0001, no aquí, para evitar optimización previa:

- Indicador(es) concreto(s) de tendencia y sus períodos.
- Umbral(es) de entrada y salida.
- Mecanismo exacto de dimensionamiento de posición.
- Número de configuraciones a evaluar (máx. 4, del presupuesto global).
