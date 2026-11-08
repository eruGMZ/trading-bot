# Política de datos y aislamiento OOS

**Protocolo:** QRP-001 v1.1
**Estado:** Pendiente de aprobación integral junto con QRP-001
**Última actualización:** 2026-11-08 (resolución de revisión)

## 1. Requisitos generales de datos

Todo dataset usado en un experimento deberá:

- Registrar SHA-256, fuente de descarga y fecha de descarga.
- Registrar zona horaria (UTC) y frecuencia.
- Validar duplicados, gaps y coherencia OHLC (`low ≤ open, close ≤ high`, precios > 0).
- Conservar la versión original sin modificar. Las transformaciones (agregación a 4H o 1D, filtrados, recortes) se registran y producen archivos derivados con su propio hash.
- Usar solo información disponible en el momento de cada decisión, con velas cerradas y sin información futura.
- **Nunca borrar un dataset sin registrar antes la decisión y su motivo.** (Regla incorporada tras INC-001.)

Cada experimento declara sus datos en `data_manifest.json`.

## 2. Datasets existentes

| Dataset | Rango (`open_time`, UTC) | Velas | SHA-256 | Estado |
|---|---|---|---|---|
| `backtest/btcusdt_h1.csv` | 2023-05-01T00:00Z → 2026-10-31T23:00Z | 30,720 | `e88a8403…e6195598` | Versionado en `25f0e3f`. **Contiene el LOCKBOX.** Acceso denegado a agentes (capas 1–3). |
| `backtest/research/data/btcusdt_h1_research_v1.csv` | 2023-05-01T00:00Z → 2025-11-07T23:00Z | 22,128 | `6b4b4200…46639c1c` | **Dataset derivado de investigación** (D-008). Sin lockbox. Byte-idéntico al prefijo del original. Ver §2.1. |
| CSV previo de Fase 0 | 2023-05-10T12:00Z → 2026-11-08T20:00Z | 30,681 | `4c7417d3…caab0f61` | **No conservado** (INC-001); solo queda su hash. |

### 2.1 Dataset derivado de investigación

Generado con `backtest/research/tools/make_research_dataset.py` (herramienta de custodia; edición denegada a agentes).

| Atributo | Valor |
|---|---|
| Origen | `backtest/btcusdt_h1.csv` (verificado por SHA-256 del origen) |
| Corte | `open_time < 2025-11-08T00:00Z` (ninguna vela 1D toca el lockbox) |
| Filas descartadas | 8,592 = 8,572 del lockbox + 20 del 2025-11-08 (00:00–19:00) |
| Duplicados / gaps de 1h | 0 / 0 |
| Filas dentro del lockbox | 0 (verificado) |
| Igualdad byte a byte con el prefijo del original | Sí (`head -n 22129` + `cmp`) |
| Manifiesto | `backtest/research/data/MANIFEST.json` |

**Restricciones:** el derivado no es el dataset original de Fase 0 y no se presenta como tal. No se modifica ni se sobrescribe; cualquier nueva versión produce un archivo con otro nombre y hash.

## 3. LOCKBOX_OOS_001

### 3.1 Clasificación (D-009)

LOCKBOX_OOS_001 **no se certifica como plenamente ciego**. Se conserva como **evaluación histórica restringida**. La validación prospectiva (Etapa E2 de QRP-001) constituye la evidencia confirmatoria principal.

### 3.2 Límites exactos

| Elemento | Valor |
|---|---|
| Inicio (incluido) | `open_time` = 2025-11-08T20:00:00Z |
| Fin (excluido) | `open_time` < 2026-11-01T00:00:00Z |
| Última vela H1 incluida | `open_time` = 2026-10-31T23:00:00Z (cierra 2026-11-01T00:00:00Z) |
| Velas H1 en el dataset actual | 8,572 |

Regla de pertenencia: una vela H1 pertenece al lockbox si y solo si `2025-11-08T20:00:00Z ≤ open_time < 2026-11-01T00:00:00Z`.

**Por qué empieza a las 20:00 y no a las 00:00:** la primera ejecución de Fase 0 procesó como Train todas las velas hasta la que abre el 2025-11-08T19:00Z (cierra a las 20:00). Empezar el lockbox antes solaparía datos ya procesados por un simulador. Las velas del 2025-11-08 entre 00:00 y 19:00 quedan excluidas tanto del lockbox como de cualquier uso confirmatorio.

**Velas agregadas:** una vela 4H o 1D que contenga alguna vela H1 del lockbox pertenece al lockbox. En concreto, la vela 1D del 2025-11-08 (00:00–24:00) mezcla datos previos y datos del lockbox, por lo que no puede usarse en Train ni en validación interna. La vela 4H de 20:00–24:00 de ese día es la primera 4H íntegramente dentro del lockbox.

**Calentamiento de indicadores:** al evaluar el candidato en el lockbox, los indicadores pueden calentarse con datos anteriores al inicio. Ninguna señal, operación ni métrica se genera con velas fuera del intervalo.

### 3.3 Uso (D-010)

Un único candidato y un único intento global. Si falla, el lockbox queda consumido; ningún candidato posterior lo usa. El resultado se reporta como evaluación histórica restringida.

### 3.4 Reglas de aislamiento

1. Ningún experimento de investigación (Etapas C y D) puede leer velas del lockbox. Los datos de Train y validación interna terminan, como muy tarde, en la vela con `open_time` 2025-11-07T23:00Z.
2. El aislamiento es **técnico, no solo normativo**: los experimentos leen el dataset derivado (§2.1), que no contiene el lockbox.
3. La ejecución confirmatoria requiere: candidato único seleccionado entre todas las familias, hashes de código, configuración, reglas y dataset, y autorización humana explícita.
4. Se permite una sola ejecución. Su resultado, positivo o negativo, consume el lockbox de forma definitiva y queda registrado en `REGISTRO_EXPERIMENTOS.md`.
5. No se evalúan candidatos adicionales ni se ajusta la estrategia a partir de los resultados.
6. El lockbox no sustituye la validación prospectiva (D-009).

### 3.5 Controles técnicos

| Capa | Estado | Qué cubre |
|---|---|---|
| 1 — Reglas `permissions.deny` | **Activa y verificada** | Read del CSV completo y de `.git/objects`; edición de controles, datos y herramientas |
| 2 — Hook `lockbox_guard.py` (fail-closed) | **Activa y verificada** | Read, Grep, Glob, Bash que nombren el CSV, rutas ofuscadas, symlinks, `backtest.py`, `--oos`, git history |
| 3 — Sandbox del SO (bubblewrap) | **Configurada, no operativa** (falta `socat`) | Todo acceso Bash al CSV y `.git` sin importar cómo se construya la ruta; sin red |
| 4 — Cargador fail-closed | **Pendiente** | Que el código solo acepte el derivado con su hash y rechace velas ≥ 2025-11-08 |

Evidencia de las pruebas: `EVIDENCIA_AISLAMIENTO_LOCKBOX.md`. Arquitectura completa: `ARQUITECTURA_QUANT_AGENT_v1.0.md`.

**Riesgo residual:** un programa que construya la ruta en tiempo de ejecución puede leer el CSV (verificado). Se cierra con la capa 3 (pendiente A-1: instalar `socat`).

## 4. Auditoría de exposición previa

Requisito de QRP-001 v1.1 §15.

### 4.1 Exposición a resultados de estrategias: no detectada

Verificado el 2026-11-08 únicamente con metadatos (configuraciones de segmentos, marcas de tiempo y fechas de operaciones), sin calcular nada sobre precios del lockbox:

| Evidencia | Resultado |
|---|---|
| `backtest/results_full.json` (salida de `--oos`) | No existe: OOS nunca ejecutado |
| `variants_register.json` → `oos_executed` | `false` |
| Segmentos procesados en `runs/2026-11-08_csv_previo/results_train.json` | Solo `train`, hasta 2025-11-08T19:00Z |
| Segmentos procesados en `results_train.json` | Solo `train`, hasta 2025-10-31T22:00Z |
| Última salida de cualquier operación registrada en Fase 0 | 2025-10-10T19:00Z |

### 4.2 Contacto con el segmento sin resultados de estrategia: declarado

- **Indicadores.** `backtest.py` de Fase 0 calcula RSI, ATR y EMA200 sobre el dataset completo, incluido el lockbox, aunque solo simula operaciones sobre Train. Esos valores no se imprimieron ni se analizaron.
- **Validaciones de integridad.** Durante la reproducción de Fase 0 se ejecutaron comprobaciones sobre el CSV completo (duplicados, gaps, OHLC inválidas, igualdad de velas entre CSVs). Solo produjeron conteos agregados de errores, todos iguales a cero.
- **Esta auditoría.** Se leyeron las marcas de tiempo del CSV para contar las velas del lockbox (8,572).

Ninguno de estos contactos produjo información sobre la rentabilidad de una estrategia ni sobre el comportamiento del precio en el segmento.

### 4.3 Conocimiento general del mercado: no eliminable, debe declararse

El segmento corresponde a un periodo ya transcurrido. El responsable humano lo vivió en tiempo real, y el agente de IA puede tener conocimiento general del comportamiento de BTC en parte de ese periodo a través de sus datos de entrenamiento. Ese conocimiento puede sesgar la elección de familia de estrategia aunque nunca se haya calculado un resultado sobre el lockbox.

Mitigaciones:

- Cada hipótesis declara, en su preregistro, si su elección está influida por conocimiento del periodo del lockbox.
- La selección del candidato único se justifica exclusivamente con resultados de Train y validación interna.
- El reporte de la ejecución confirmatoria menciona esta limitación.
- La validación prospectiva (Etapa E2) es la que no tiene esta exposición, y por eso es la evidencia confirmatoria principal (D-009).

**Dictamen de la auditoría:** el lockbox está limpio respecto a resultados de estrategias y decisiones basadas en ellos. No está limpio respecto al conocimiento general del mercado, lo cual es inherente a cualquier holdout histórico. Corresponde a la revisión humana aceptar o no esta limitación.

## 5. Política de costos de ejecución (D-012)

Los costos de ejecución se documentan **por separado** en cada preregistro y en cada reporte de resultados:

### 5.1 Comisión (observable y verificable)

- Fuente: página oficial de Binance Spot.
- Se registra: nivel VIP, descuento por BNB, fecha de consulta.
- Se aplica como round-trip (ida y vuelta): base 0.20% (maker/taker 0.10%/0.10%) o el valor vigente documentado.
- Es un dato, no un supuesto.

### 5.2 Spread y slippage (supuestos explícitos)

- No son observables en datos históricos OHLC de Binance.
- Se declaran como **supuestos**, nunca como observaciones.
- Cada preregistro define dos escenarios:
  - **Base:** estimación conservadora razonable.
  - **Adverso:** estimación deliberadamente pesimista.
- Se presentan ambos resultados; la aprobación se basa en el escenario adverso.
- El Paper Trading (Etapa E2) servirá para calibrarlos con datos reales.

### 5.3 Limitaciones de liquidez

- Se declara que los backtests asumen ejecución inmediata al precio de cierre de la vela, sin impacto de mercado.
- Se documenta el tamaño de posición relativo al volumen típico del par (pendiente P-005).
- Si la posición supera un umbral razonable del volumen medio (por ejemplo, 1%), se declara como limitación.

### 5.4 Resumen de costos en los backtests de Fase 0 (referencia)

| Escenario | Round-trip | Componentes |
|---|---|---|
| Base | 0.22% | Comisión 0.20% + spread estimado 0.02% |
| Adverso | 0.30% | Comisión 0.20% + spread y slippage estimados 0.10% |

Estos valores se usaron en Fase 0 pero se neteaban como un solo parámetro (`fee_pct`). A partir de ahora, la comisión se separa de los supuestos (spread + slippage).

## 6. Incompatibilidades y riesgos — estado actual

| # | Incompatibilidad original | Estado | Resolución |
|---|---|---|---|
| 1 | El dataset versionado contiene el lockbox | **Resuelta** | Dataset derivado generado (§2.1) con controles técnicos (§3.5, D-008) |
| 2 | El backtester de Fase 0 puede ejecutar sobre el lockbox | **Mitigada** | `backtest.py` bloqueado por las capas 1–2; Fase 0 cerrada y no se modifica |
| 3 | El CSV original de Fase 0 no se conservó | **Registrada** | INC-001 en `INCIDENCIAS.md` (D-013); regla de no borrado añadida a §1 |
| 4 | Datos de Train limitados para 1D | **Aceptada** | D-011: no se amplía; se declara como limitación en cada experimento |
| 5 | Spread y slippage no observables en datos históricos | **Resuelta** | D-012: costos separados con escenarios base y adverso (§5) |

### Riesgos abiertos

- **Capa 3 no operativa:** falta instalar `socat` (A-1). Un programa que construya la ruta en runtime puede leer el CSV completo.
- **Git history:** el CSV completo está en el commit `25f0e3f`. Las capas 1–2 bloquean los comandos git que lo extraerían, pero la capa 3 es necesaria para cerrar la vía de runtime.
- **Controles edit-locked:** `.claude/settings.json`, `.claude/hooks/` y `backtest/research/tools/` no son editables por agentes. Los cambios los hace el responsable humano.
