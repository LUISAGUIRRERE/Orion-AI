# Prompt Composer v1

## Qué es

`orion/prompt_composer/` es el nuevo modulo que traduce una Mission en
el mejor contexto posible para ejecutarla, sin saber nada sobre que
proveedor de IA o que stack tecnologico va a usar ese contexto.

Antes de este Sprint, el Builder no construia prompts en absoluto (sus
handlers son plantillas deterministas, Sprint 006/BETA 001) — no habia
nada que desacoplar todavia. Este Sprint introduce esa capa ahora,
antes de que exista un Executor real que la necesite, para que cuando
ese Executor llegue (proximo Sprint), el Builder ya no tenga que saber
como construir contexto: solo pasa la Mission al Prompt Composer y el
PromptPackage resultante al Executor.

## Independencia de proveedor

Ninguna linea de `orion/prompt_composer/` menciona Claude, Codex,
Gemini, ni ningun otro proveedor. Tampoco menciona Next.js, React,
WordPress, Flutter ni ningun stack tecnologico especifico: las
convenciones de archivos que reconoce (`TEAM.md`, `docs/ARCHITECTURE.md`,
`design-tokens/`, `docs/adr/`, ...) son las propias convenciones de
documentacion de ORION, establecidas en ORION ALPHA 001 / BETA 001 —
no un supuesto sobre la tecnologia del proyecto. Un repositorio que no
siga ninguna de esas convenciones simplemente produce menos contexto
descubierto; nunca falla una mision por eso.

`PromptPackage.execution_prompt` es texto neutral (`instructions` +
`constraints`). Traducirlo al formato especifico de Claude Code, Codex
CLI, Gemini CLI, Jules o cualquier otro agente es trabajo de un
adaptador futuro y separado — explicitamente fuera de este Sprint.

## Flujo

```
Mission
  |
  v
Prompt Composer (orion.prompt_composer.services.compose_for_mission)
  |  resuelve project + repo_root igual que el Execution Pipeline
  |  descubre contexto real del repositorio y del Mission Framework
  v
PromptPackage (persistido en workspace/missions/<id>/prompt_package.yaml)
  |
  v
Builder -> Execution Pipeline (sin cambios: sigue usando los
           handlers deterministas de Sprint 006 / BETA 001)
```

El Builder invoca al Prompt Composer una vez por mision, justo antes
de correr el Execution Pipeline, y registra un evento `prompt_composed`
en la linea de tiempo de la mision (o `prompt_composer_failed` si algo
sale mal — nunca deja la mision atascada). El PromptPackage se guarda
como evidencia y como base para el Executor futuro; hoy no reemplaza
todavia a los handlers existentes.

## Que descubre automaticamente

Sin que la mision tenga que indicarlo:

| Categoria | Como se descubre |
|---|---|
| TEAM.md, CLAUDE.md/AGENTS.md, README.md, ARCHITECTURE.md, DESIGN_SYSTEM.md, CONTENT_GUIDE.md | Nombres de archivo conocidos en la raiz o en `docs/` del repositorio del proyecto |
| ADRs | `docs/adr/`, `docs/decisions/` o `adr/`, todos los `.md` dentro |
| Design Tokens | `design-tokens/` o `tokens/`, archivos `.json`/`.css` |
| Misiones relacionadas | Mismo `project_id` y/o tags compartidos, via el Mission Framework existente |
| Archivos afectados | `artifact_path` / `artifact_files` que la propia mision ya declara |
| Commits recientes | `git log` sobre el `repo_root` real del proyecto, via GitManager (nunca git directo) |
| Pull Requests relacionados | Mejor esfuerzo: ramas remotas locales con prefijo `mission/`, distintas a la propia — ORION no tiene acceso a la API de GitHub en este entorno, asi que el estado siempre se marca como inferido, nunca confirmado |
| Estado del proyecto | Reutiliza `orion.projects.services.describe_project()` (Sprint 009) — nunca lo recalcula por separado |

## Limites explicitos de esta v1

- No llama a ningun modelo de IA. Es deterministico y basado en
  plantillas: `suggested_plan` y `execution_prompt` son estructura,
  no razonamiento. Generar un plan realmente inteligente es trabajo
  futuro, una vez que este v1 se haya probado contra misiones reales
  variadas.
- `acceptance_criteria` se extrae con una heuristica simple (busca un
  marcador de texto como "criterio de aceptacion" en la descripcion
  de la mision). Una mejora futura razonable: un campo estructurado
  propio en `Mission`, siguiendo el mismo patron aditivo que
  `artifact_path`/`artifact_files`.
- `related_files` solo lee lo que la propia mision ya declara
  (`artifact_path`/`artifact_files`); no intenta adivinar rutas de
  archivo a partir de texto libre.
- El PromptPackage generado no se conecta todavia a ningun Executor
  real: los handlers de `orion.agents.builder.registry` (Sprint 006 /
  BETA 001) siguen siendo los que efectivamente producen el
  entregable de una mision. Conectar un Executor real que consuma
  `PromptPackage.execution_prompt` es la continuacion natural de este
  Sprint, no parte de el.

## Tests

`tests/test_prompt_composer.py`, con `unittest` de la libreria
estandar (sin nuevas dependencias). Cada test que necesita un
"repositorio" crea uno real y desechable bajo un directorio temporal
— nunca toca el propio repositorio de Orion-AI ni ningun proyecto
real. Correr con:

```
python3 -m unittest tests.test_prompt_composer -v
```
