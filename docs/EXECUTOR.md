# Executor v1

## Que es

`orion/executor/` recibe un `PromptPackage` (compuesto enteramente por
`orion.prompt_composer` -- el Executor nunca construye contexto propio)
y delega el trabajo real a un adaptador configurable. Con este Sprint,
el flujo objetivo queda completo:

```
Mission
  |
  v
Prompt Composer  ->  PromptPackage
  |
  v
Executor  ->  Provider Adapter  ->  Workspace Changes
  |
  v
Validation  ->  Git Manager (commit / push / PR)
```

## Independencia de proveedor

Ninguna linea de `orion/executor/` (fuera de los adaptadores mismos)
menciona un proveedor de IA especifico ni una tecnologia especifica.
La interfaz `ProviderAdapter` (`adapters/base.py`) es el unico
contrato: recibe un `ExecutionRequest`, devuelve un `ExecutionResult`.
Un adaptador real para Claude Code, Codex CLI, Gemini CLI o Jules se
agrega implementando esa interfaz y llamando a
`orion.executor.registry.register_adapter(...)` -- nunca modificando
`orion/executor/services.py` ni `orion/execution/task_runner.py`.

## Limites explicitos (por diseno, no por omision)

- **El Executor no hace git.** Solo escribe archivos en `repo_root`
  (`Path.write_text`); el commit/push/PR siguen siendo exclusivamente
  de `orion.execution.git_manager`, sin cambios.
- **El Executor no descubre contexto.** `run_for_mission` carga el
  `PromptPackage` que `orion.prompt_composer` ya persistio para esa
  mision (`prompt_storage.load(mission.id)`) y falla explicitamente
  (`ExecutorError`) si no existe uno -- nunca intenta componerlo el
  mismo.
- **El Executor no decide arquitectura.** Un adaptador solo ve lo que
  el `PromptPackage.execution_prompt` ya contiene; no tiene acceso a
  descubrir mas archivos, mas commits, ni mas historia por su cuenta.
- **Sin logica de stack especifico.** Ni `orion/executor/` ni el
  adaptador determinista mencionan React, Next.js, WordPress o
  Flutter en ningun punto.

## El adaptador determinista (`deterministic_local`)

Existe unicamente para validar el contrato completo del Executor, no
para hacer trabajo real. Dado el mismo `ExecutionRequest`, siempre
produce el mismo `ExecutionResult`: sin red, sin credenciales, sin
aleatoriedad. Cada archivo que genera dice explicitamente, en texto
plano, que no proviene de un proveedor real -- ver
`orion/executor/adapters/deterministic.py`.

## Seleccion de adaptador

v1 usa una convencion simple sobre las tags ya existentes de una
Mission: una tag `adapter:<nombre>` selecciona ese adaptador
explicitamente; si no hay ninguna, se usa `deterministic_local` (el
unico adaptador real que existe todavia). Un campo estructurado propio
en `Mission` es una mejora futura razonable una vez exista un segundo
adaptador real que la justifique -- no se invento antes de tiempo.

## Timeouts y captura de errores

`run_for_mission` corre `adapter.execute(request)` en un solo hilo
(`concurrent.futures.ThreadPoolExecutor`) y aplica
`future.result(timeout=request.timeout_seconds)`: si el adaptador no
responde a tiempo, el Executor recupera el control igual (el hilo
bloqueado queda abandonado, pero nunca cuelga al Builder) y registra
`ExecutionStatus.TIMEOUT`. Cualquier excepcion que lance un adaptador
se captura y se convierte en `ExecutionStatus.FAILED` con el error
exacto -- nunca se propaga cruda. En ambos casos se persiste un
`ExecutionResult` estructurado antes de que `ExecutorError` se levante
hacia `orion.execution.task_runner` / `pipeline.py`, que ya sabian
manejar una excepcion de ejecucion (igual que ya hacian con
`GitManagerError`) sin ningun cambio adicional.

## Integracion con el Builder

Minima, y en un solo punto: `orion.execution.task_runner.execute()`
ahora revisa si `mission.mission_type == "executor"` antes de
consultar el registro de handlers legado
(`orion.agents.builder.registry`); si lo es, delega enteramente a
`orion.executor.services.run_for_mission`. `orion/agents/builder/agent.py`
no cambio en absoluto en este Sprint: la integracion de Prompt Composer
del Sprint anterior ya garantiza que un `PromptPackage` existe antes de
que `task_runner.execute()` corra, para toda mision, sin excepcion --
el Executor simplemente lo consume.

Las misiones existentes (`documentation`, `research`, `scaffold`,
`code_generation`) siguen exactamente igual: `mission_type == "executor"`
es un valor nuevo que las demas nunca usan.

## Persistencia y eventos

Cada mision `executor` deja, junto a su `prompt_package.yaml` (Sprint
anterior), dos archivos mas bajo `workspace/missions/<id>/`:
`execution_request.yaml` y `execution_result.yaml`. Cuatro eventos
nuevos en la linea de tiempo de la mision, con autor `Executor`:
`execution_requested`, `execution_started`, `execution_completed`,
`execution_failed`.

## Bug latente corregido de paso

`orion.execution.validation.run()` nunca recibio un `repo_root`: para
proyectos externos siempre revisaba
`bridge_storage.REPO_ROOT / archivo` en vez del repositorio real. Nunca
se noto porque solo valida archivos `.py`, y ninguna mision contra un
proyecto externo habia producido uno todavia. Corregido aqui (parametro
`repo_root` con el mismo valor por defecto de siempre) porque el
Executor es el primer camino que podria producir un `.py` real contra
un proyecto externo.

## Tests

`tests/test_executor.py`, `unittest` de la libreria estandar, sin
llamadas externas de ningun tipo -- ni siquiera al adaptador
determinista real en los casos de timeout/crash, que usan sus propios
adaptadores de prueba (`_SlowAdapter`, `_CrashingAdapter`, `_EchoAdapter`)
registrados solo dentro del modulo de test. Corre con:

```
python3 -m unittest tests.test_executor tests.test_prompt_composer -v
```
