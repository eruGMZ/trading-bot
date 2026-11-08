# Arquitectura del Quant Research Agent

**Identificador:** QRA-001
**Versión:** 1.0
**Estado:** **Operativamente habilitado para Train** (2026-11-08). A-2 y A-3 completados. Lockbox bloqueado hasta completar A-4 y obtener autorización humana.
**Protocolo de referencia:** `PROTOCOLO_INVESTIGACION_ESTRATEGIAS_v1.1.md`
**Última actualización:** 2026-11-08

QRP-001 define qué se investiga y con qué reglas. Este documento define quién hace cada cosa, qué puede ver cada uno y qué controles técnicos lo impiden cuando no debe.

## 1. Principio de diseño

Una regla escrita no impide que un proceso lea un archivo. Cada restricción crítica de QRP-001 debe tener un control técnico, y donde no exista se declara como riesgo residual, no se presume cubierta.

## 2. Roles

| Rol | Quién | Responsabilidad | Nunca hace |
|---|---|---|---|
| **Responsable humano** | Humano | Aprueba el protocolo, los preregistros que avanzan de etapa, las excepciones y el uso del lockbox | Delegar la aprobación de producción o capital |
| **Custodio de datos** | Humano (puede coincidir con el responsable) | Descarga datos, genera datasets derivados, conserva originales, ejecuta la evaluación confirmatoria en el lockbox | Compartir con los agentes resultados del lockbox antes de cerrarlos y registrarlos |
| **Research Agent** | Sesión de Claude Code lanzada con `run_research_agent.sh` | Hipótesis, preregistros, código de estrategias, backtests sobre el dataset derivado, reportes | Leer el dataset completo o el lockbox, descargar datos, modificar controles, experimentos cerrados o producción |
| **Audit Agent** | Sesión de Claude Code separada, sin el contexto del Research Agent | Revisar preregistros, código y resultados en busca de look-ahead, leakage, pruebas no contabilizadas y errores | Modificar experimentos; diseñar estrategias; aprobar |

El Research Agent y el Audit Agent son sesiones distintas: el auditor no hereda la conversación ni el razonamiento del investigador, solo los artefactos escritos. Ver la limitación de §8.

## 3. Matriz de acceso

| Recurso | Responsable | Custodio | Research Agent | Audit Agent |
|---|---|---|---|---|
| `backtest/btcusdt_h1.csv` (completo, contiene lockbox) | Sí | Sí | **No** (capas 1–3) | **No** (capas 1–2) |
| Historial de git (contiene el completo en `25f0e3f`) | Sí | Sí | **No** (capas 2–3) | **No** (capa 2) |
| `backtest/research/data/` (derivado, sin lockbox) | Sí | Escritura | Solo lectura | Solo lectura |
| `backtest/research/tools/` (custodia) | Sí | Ejecuta | **No ejecuta ni edita** | No |
| `backtest/experiments/EXP-XXXX/` abiertos | Sí | — | Escritura | Lectura |
| Experimentos cerrados y Fase 0 | Sí | — | Solo lectura | Solo lectura |
| `backtest/docs/` | Sí | — | Escritura en registros; propuestas de cambio | Lectura; escribe auditorías |
| `.claude/` (controles) | Sí | — | **No edita** (capa 1) | **No edita** (capa 1) |
| Código y configuración de producción | Sí | — | No (QRP-001 §18) | No |
| Red / descarga de datos | Sí | Sí | **No** (capas 2–3) | — |

## 4. Estructura de directorios

```
backtest/
├── btcusdt_h1.csv              # completo — custodia, acceso denegado a agentes
├── backtest.py, fetch_klines.py, REPORTE_FASE0.md, ...   # Fase 0, cerrada
├── docs/                       # protocolo, políticas, registros
├── research/
│   ├── data/
│   │   ├── btcusdt_h1_research_v1.csv   # derivado, sin lockbox
│   │   └── MANIFEST.json               # hash, rango, procedencia
│   ├── tools/
│   │   └── make_research_dataset.py    # custodia
│   ├── agent-profile.settings.json      # perfil con sandbox
│   └── run_research_agent.sh            # lanzador del Research Agent
└── experiments/
    └── EXP-XXXX/               # uno por experimento (QRP-001 §17)
.claude/
├── settings.json               # capa 1 (deny) y registro de la capa 2
└── hooks/lockbox_guard.py      # capa 2
```

## 5. Capas de control del lockbox

| Capa | Mecanismo | Qué cubre | Qué no cubre | Estado |
|---|---|---|---|---|
| 1 | Reglas `permissions.deny` en `.claude/settings.json` | Read del dataset completo y de `.git/objects`; edición de controles, datos derivados y herramientas de custodia | Comandos Bash arbitrarios | **Activa y verificada** |
| 2 | Hook `PreToolUse` `lockbox_guard.py` (fail-closed) | Read, Grep, Glob y Bash que nombran el dataset completo, rutas ofuscadas y enlaces simbólicos (Read/Grep), `backtest.py`, `--oos`, descargas, herramienta de custodia, lectura del historial de git | Programas que construyen la ruta en tiempo de ejecución | **Activa y verificada** |
| 3 | Sandbox del SO (bubblewrap) vía `run_research_agent.sh` | Todo acceso de los comandos Bash al dataset completo y a `.git`, sin importar cómo se escriba la ruta; sin red | Herramientas internas de Claude Code, cubiertas por las capas 1–2 | **Activa y verificada** (2026-11-08) |
| 4 | Cargador de datos de investigación fail-closed | Que el código de los experimentos solo acepte el derivado con su hash y rechace cualquier vela ≥ 2025-11-08 | — | **Activa y verificada** (2026-11-08) — `backtest/research/data_loader.py` |

Evidencia de las pruebas: `EVIDENCIA_AISLAMIENTO_LOCKBOX.md`.

**Capas 1–3 activas y verificadas.** La vía residual (programas que construyen la ruta en runtime) queda bloqueada por la capa 3 (verificado 2026-11-08, `EVIDENCIA_AISLAMIENTO_LOCKBOX.md` §5).

**Riesgo residual permanente:** los agentes se ejecutan con el mismo usuario del sistema que el custodio. El sandbox restringe sus comandos, pero las capas 1 y 2 dependen de la configuración de Claude Code. El aislamiento completo frente a cualquier proceso requeriría un usuario del sistema o una máquina distintos para la custodia; no se propone por ahora.

## 6. Evaluación en LOCKBOX_OOS_001

Ningún agente ejecuta la evaluación confirmatoria ni ve sus datos antes de que el resultado quede registrado.

1. El Research Agent entrega un candidato único congelado: código, configuración y reglas con sus hashes, y un script confirmatorio que solo recibe la ruta del dataset como argumento.
2. El Audit Agent revisa el paquete congelado.
3. El responsable humano autoriza la ejecución.
4. El custodio ejecuta el script fuera de cualquier sesión de agente, una sola vez, y registra el resultado en `REGISTRO_EXPERIMENTOS.md`.
5. Solo entonces el resultado se comparte con los agentes.

Por decisión D-009 (P-012), el resultado se reporta como **evaluación histórica restringida**, no como confirmación plenamente independiente. LOCKBOX_OOS_001 no se certifica como plenamente ciego; la validación prospectiva (Etapa E2) es la evidencia confirmatoria principal. Ningún agente puede autorizar el uso del lockbox: la autorización es exclusivamente humana.

## 7. Memoria y continuidad entre sesiones

Ningún estado de investigación vive en la memoria de una conversación. Todo lo que debe sobrevivir entre sesiones se escribe en archivos versionados:

| Necesidad | Dónde |
|---|---|
| Reglas y decisiones | `PROTOCOLO_…_v1.1.md`, `REGISTRO_DECISIONES.md` |
| Hipótesis | `REGISTRO_HIPOTESIS.md` |
| Experimentos, contador global y estado del lockbox | `REGISTRO_EXPERIMENTOS.md` |
| Incidencias | `INCIDENCIAS.md` |
| Estado de cada experimento | `backtest/experiments/EXP-XXXX/` |

Al iniciar, cada sesión de agente lee el protocolo y los registros antes de actuar. La memoria automática de Claude Code solo guarda punteros a estos documentos, nunca resultados ni decisiones que no consten en ellos.

## 8. Independencia de la auditoría: límites

Separar investigador y auditor en sesiones distintas evita que el auditor herede el razonamiento del investigador. Pero si ambos son el mismo modelo, comparten sesgos y puntos ciegos, por lo que la auditoría automática no es independiente en sentido estricto. La revisión humana de la Etapa G de QRP-001 sigue siendo el control independiente real.

## 9. Cambios en los controles

- `.claude/` y `backtest/research/tools/` no pueden editarse desde una sesión de agente (capa 1). Los cambios los hace el responsable humano directamente.
- Todo cambio de un control se registra en `REGISTRO_DECISIONES.md` con fecha y motivo.
- Un control no se relaja para desbloquear un experimento. Si un experimento lo necesita, se plantea como solicitud de aprobación.

## 10. Pendientes

| ID | Pendiente | Responsable |
|---|---|---|
| A-1 | ~~Instalar `socat` y verificar la capa 3~~ | **Cerrado** 2026-11-08 |
| A-2 | Perfil de permisos del Audit Agent | **Cerrado** 2026-11-08 — `audit-profile.settings.json`, `run_audit_agent.sh` |
| A-3 | Cargador de datos fail-closed (capa 4) | **Cerrado** 2026-11-08 — `data_loader.py`; 3/3 tests pasados |
| A-4 | Script confirmatorio del lockbox: sin red, dataset de solo lectura, acceso limitado al sistema de archivos, verificación de hashes antes de ejecutar — **obligatorio antes de cualquier ejecución del lockbox**, aunque todavía no exista un candidato | Agente — bloquea Etapa E1 (no bloquea investigación sobre Train) |
