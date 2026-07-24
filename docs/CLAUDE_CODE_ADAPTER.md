# Claude Code Provider Adapter

El primer Provider Adapter real del Executor. Deja atras el modo
bootstrap: hasta este Sprint, un humano actuaba como puente entre
ORION y Claude Code, copiando prompts a mano. Ese puente desaparece
como concepto de arquitectura -- el Executor ahora entrega un
`PromptPackage` directamente a un `ProviderAdapter` y recibe un
`ExecutionResult`, sin intervencion humana en el medio.

## Flujo

```
Mission
  |
COO
  |
Prompt Composer -> PromptPackage
  |
Executor
  |
ProviderAdapter.execute(PromptPackage)   <-- unico cambio de contrato
  |
Workspace Changes
  |
Validation
  |
Git Manager
  |
The Window
```

## El unico cambio real

Antes de este Sprint, `ProviderAdapter.execute()` recibia un
`ExecutionRequest` completo (mission_id, adapter, prompt_package,
timeout, requested_at). Ahora recibe directamente el
`PromptPackage`. Es el unico cambio de contrato de todo el Sprint --
`orion.executor.services._run_with_timeout` ahora llama
`adapter.execute(request.prompt_package)` en vez de
`adapter.execute(request)`. `ExecutionRequest` sigue existiendo y
sigue persistiendose (`execution_request.yaml`): es el registro propio
del Executor de que se pidio, no lo que un adaptador recibe.

Un adaptador nunca conocera `Mission`. Solo conoce `PromptPackage`.

## Contrato extendido de `ProviderAdapter`

`orion/executor/adapters/base.py` ahora define cuatro metodos:

- `execute(package: PromptPackage) -> ExecutionResult` -- el unico
  obligatorio de sobreescribir.
- `health_check() -> AdapterHealth` -- por defecto reporta
  `healthy=True` (un adaptador de prueba local no tiene nada que
  pueda estar no saludable).
- `cancel(mission_id: str) -> bool` -- por defecto `False` (nada esta
  realmente en curso salvo que un adaptador diga lo contrario).
- `capabilities() -> AdapterCapabilities` -- por defecto
  `supports_cancel=False`, sin techo de timeout.

`DeterministicLocalAdapter` (BETA 003) sigue usando los valores por
defecto de `health_check()`/`cancel()`, y solo sobreescribe
`capabilities()` para un mensaje mas especifico -- cero cambio de
comportamiento observable para las misiones existentes.

## `ClaudeCodeAdapter`

`orion/providers/claude_code/adapter.py`. Registrado bajo el nombre
`'claude_code'`.

- `health_check()`: revisa honestamente si el binario configurado
  (`ORION_CLAUDE_CODE_CLI`, por defecto `'claude'`) esta en `PATH`.
  Reporta `healthy=False` siempre en este Sprint -- incluso si el
  binario existe -- porque `execute()` todavia no puede usarlo (ver
  `_invoke()` abajo). Reportar `healthy=True` seria mentir sobre lo
  que el adaptador puede realmente hacer.
- `execute(package)`: crea un workspace temporal real
  (`tempfile.mkdtemp`), escribe el `PromptPackage` completo ahi como
  `prompt_package.json`, llama a `_invoke()`, y limpia el workspace en
  un `finally` -- siempre, exito o fallo. Nunca lanza una excepcion:
  si `_invoke()` falla, retorna un `ExecutionResult` estructurado con
  `status=FAILED` y un `error` claro.
- `cancel(mission_id)`: `False`, honesto -- nada esta en curso todavia
  en v1 (`execute()` es sincrono).
- `capabilities()`: documenta explicitamente el limite de este Sprint
  en su campo `notes`.

### El limite deliberado: `_invoke()`

`ClaudeCodeAdapter._invoke(package, workspace)` es el unico punto no
implementado de todo el adaptador. Lanza `ClaudeCodeNotAvailableError`
con un mensaje que explica exactamente que falta. Su docstring incluye
el boceto de lo que una implementacion real haria:

```python
result = subprocess.run(
    [self._config.cli_path, "--print", package.execution_prompt.instructions,
     "--cwd", str(workspace), "--output-format", "json"],
    capture_output=True, text=True, timeout=self._config.timeout_seconds,
)
if result.returncode != 0:
    raise ClaudeCodeNotAvailableError(result.stderr)
return _parse_modified_files_from(result.stdout)
```

Por que no se implemento: este entorno sandbox no tiene el SDK/CLI de
Claude Code disponible, y este Sprint prohibe explicitamente conectar
credenciales reales ("No conectar todavia claves privadas"). Todo lo
demas alrededor de este punto -- ciclo de vida del workspace, entrega
del PromptPackage, captura estructurada de errores, recoleccion de
archivos (`_collect_modified_files`, real y probada aunque inalcanzable
hasta que `_invoke()` sea real) -- esta completo y probado.

## Configuracion

`orion/providers/claude_code/config.py` -- `ClaudeCodeConfig`, un
dataclass que solo lee *nombres* de variables de entorno, nunca un
valor secreto:

- `ORION_CLAUDE_CODE_CLI` (por defecto `'claude'`) -- el binario que
  `health_check()` busca en `PATH`.
- `ORION_CLAUDE_CODE_TIMEOUT_SECONDS` (por defecto `300`) -- el limite
  que una implementacion real de `_invoke()` pasaria a su
  subprocess/SDK.

Ninguna clave, token o secreto se lee, guarda o referencia en ningun
lugar de este modulo.

## Seleccion dinamica de proveedor

`orion/executor/services.py` gano tres piezas nuevas, todas orientadas
al criterio de exito literal del Sprint ("cambiar unicamente
`provider = 'claude_code'`"):

1. **`ORION_PROVIDER`** -- variable de entorno que reemplaza el
   `DEFAULT_ADAPTER` hardcodeado como adaptador por defecto (cuando
   una mision no trae tag `adapter:<nombre>` explicito). Sin la
   variable, el comportamiento es identico al de BETA 003
   (`deterministic_local`).
2. **Descubrimiento dinamico por convencion**: si el nombre resuelto
   no esta registrado, `_get_adapter_with_discovery()` intenta
   `importlib.import_module(f"orion.providers.{name}")` antes de
   fallar. Importar ese paquete registra el adaptador como efecto
   secundario -- `orion.executor` nunca importa
   `orion.providers.claude_code` por nombre en ningun punto de su
   propio codigo.
3. **`orion/providers/`** -- un paquete nuevo, hermano de
   `orion/executor/adapters/` (que solo contiene adaptadores de
   prueba integrados). Cada proveedor real (Claude Code hoy; Codex
   CLI, Gemini CLI, Jules manana) vive en su propio subpaquete y se
   registra sin que `orion.executor` sepa que existe.

Con esto, agregar Codex CLI el dia de manana significa: crear
`orion/providers/codex_cli/`, y cambiar `ORION_PROVIDER=codex_cli` (o
un tag `adapter:codex_cli` por mision). Cero cambios en
`orion.executor`.

## Eventos nuevos

Cuatro eventos nuevos, coexistiendo con los cuatro de BETA 003
(`execution_requested/started/completed/failed`), nunca
reemplazandolos:

| Evento              | Cuando |
|----------------------|--------|
| `provider_selected`  | Justo despues de resolver que adaptador se usara (tag o `ORION_PROVIDER`), antes de construir el `ExecutionRequest`. |
| `provider_started`   | Justo antes de invocar `adapter.execute()`. |
| `provider_finished`  | Cuando el adaptador termina con `status=SUCCEEDED`. |
| `provider_failed`    | Cuando el adaptador termina con cualquier otro status (`FAILED`/`TIMEOUT`), o lanza una excepcion. |

## Que NO cambio

- `orion.prompt_composer` -- intacto.
- `Mission` / `orion.bridge` -- intacto.
- `orion.execution.git_manager` -- intacto.
- `DeterministicLocalAdapter` -- mismo comportamiento observable,
  solo su firma interna de `execute()` cambio de `request` a
  `package` (una actualizacion mecanica, no de logica).
- Ninguna mision anterior (`documentation`/`research`/`scaffold`/
  `code_generation`/`executor` con `deterministic_local`) cambia de
  comportamiento.

## Pruebas

`tests/test_executor.py` -- 15 tests (los 10 de BETA 003 mas 5
nuevos): adaptador por defecto vias `ORION_PROVIDER`, descubrimiento
dinamico simulado (parchando `importlib.import_module` para la
duracion de un solo test, sin tocar el filesystem), y tres tests
nuevos para los valores por defecto de `health_check()`/`cancel()`/
`capabilities()` en la clase base.

`tests/test_claude_code_adapter.py` -- 13 tests nuevos: auto-registro
al importar, `health_check()` con y sin binario presente en `PATH`
(siempre `healthy=False`, con mensaje distinto en cada caso),
`execute()` alcanzando el limite de `_invoke()` y retornando un
`FAILED` estructurado sin lanzar nunca, `_invoke()` lanzando el error
documentado directamente, `_write_package()` persistiendo JSON real,
`_collect_modified_files()` leyendo archivos reales de un workspace
real, `cancel()` honesto, `capabilities()` documentando el limite, y
una prueba de guardia de que ni `adapter.py` ni `config.py` contienen
tokens de red o secretos.

```
python3 -m unittest tests.test_executor tests.test_claude_code_adapter -v
```

51/51 tests en la suite completa (`python3 -m unittest discover -s
tests`), incluyendo `test_experience.py` y `test_prompt_composer.py`
sin ninguna regresion.

Sin llamadas externas. Sin credenciales. Sin dependencias nuevas.

---

## BETA 006 -- Claude Code Live Invocation

A partir de este Sprint `ClaudeCodeAdapter._invoke()` deja de ser un
limite deliberadamente no implementado: es una llamada real a un
subproceso real. Esta seccion documenta la inspeccion del entorno que
precedio a la implementacion, las decisiones de diseno que resultaron
de esa inspeccion, y el resultado honesto de la validacion real.

### Inspeccion del entorno (hecha antes de escribir una sola linea)

Binario: instalado, en `/usr/local/bin/claude`, en `PATH` bajo el
nombre `claude`.

Version: `2.1.209 (Claude Code)` (via `claude --version`).

Autenticacion: **no autenticado**. `claude auth status --json` ->
`{"loggedIn": false, "authMethod": "none", "apiProvider": "firstParty"}`.
Metodos disponibles segun `claude auth --help`: `claude auth login`
(interactivo, requiere navegador/flujo OAuth) o `ANTHROPIC_API_KEY`
(variable de entorno, no presente en este sandbox). Ninguno de los dos
es utilizable desde este entorno no interactivo.

Ejecucion no interactiva: si, via `-p`/`--print`. Confirmado con
llamadas reales (fallidas por autenticacion, pero con parseo de flags
exitoso): `claude -p --output-format json` leyendo el prompt de stdin.

Flags confirmados via `claude --help` (nunca inventados):

| Necesidad | Flag real | Notas |
|---|---|---|
| prompt | stdin (con `-p`) | tambien acepta un argumento posicional; se eligio stdin para evitar limites de longitud de argumentos y caracteres especiales |
| directorio de trabajo | `cwd` del subproceso (no hay flag `--cwd`; `--add-dir` es solo para *agregar* directorios extra, nunca se usa) | el proceso solo puede tocar el workspace aislado que ORION le asigna como cwd |
| formato de salida | `--output-format json` | devuelve un unico objeto JSON con `type`, `is_error`, `result`, `num_turns`, `exit`-like semantics |
| permisos | `--permission-mode acceptEdits` | ver justificacion abajo |
| límite de turnos | **no existe** en esta version de la CLI | confirmado ausente en `claude --help` -- ver mas abajo |
| modelo | `--model <alias-o-nombre>` | confirmado, ej. `sonnet`, `opus` |
| timeout | **no existe** en esta version de la CLI | confirmado ausente en `claude --help` -- enforced enteramente por ORION |

Dos hallazgos honestos que el brief de este Sprint pedia explicitamente
no inventar:

- **No hay flag de timeout nativo.** `ORION_CLAUDE_CODE_TIMEOUT` se
  aplica enteramente del lado de ORION: `subprocess.Popen.wait(timeout=...)`
  mas terminacion real del grupo de procesos (`os.killpg`, SIGTERM
  primero, SIGKILL si no responde en 5s).
- **No hay flag de limite de turnos.** `ORION_CLAUDE_CODE_MAX_TURNS`
  se acepta y se guarda en `ClaudeCodeConfig` (cumpliendo la superficie
  de configuracion pedida por el Sprint), pero `_build_args()` nunca
  lo traduce a un flag inventado. Si una mision lo configura,
  `execute()` lo nota explicitamente en `ExecutionResult.summary` en
  vez de descartarlo en silencio.

### Por que `--permission-mode acceptEdits` y no `bypassPermissions`

El brief de este Sprint exige explicitamente "no permitir comandos
destructivos fuera del workspace". La propia ayuda de la CLI describe
`--dangerously-skip-permissions`/`bypassPermissions` como
"Recommended only for sandboxes with no internet access" -- lo
opuesto de la garantia que ORION quiere para una llamada real y
conectada a la red. `acceptEdits` auto-acepta ediciones de archivo
(lo unico que una mision de codigo tipo "crear hello-orion.txt"
necesita) sin conceder ese permiso total.

### Arquitectura real de `_invoke()`

```
ClaudeCodeAdapter.execute(package)
  -> health_check()                          # real: PATH + auth status --json
  -> workspace temporal aislado (tempfile.mkdtemp)
  -> _write_package()                        # prompt_package.json, provenance
  -> snapshot (sha256 por archivo)            # baseline
  -> _build_prompt_text(package)              # PromptPackage -> texto plano
  -> _invoke(args, cwd=workspace, prompt, mission_id)
       -> subprocess.Popen(args, cwd=workspace, stdin/stdout/stderr=PIPE,
                            text=True, start_new_session=True)
       -> self._active_processes[mission_id] = process   # PID registrado
       -> 2 threads de drenado (stdout/stderr), con tope MAX_CAPTURE_CHARS
       -> process.wait(timeout=ORION_CLAUDE_CODE_TIMEOUT)
       -> en timeout: os.killpg(SIGTERM, luego SIGKILL si hace falta)
       -> self._active_processes.pop(mission_id)          # limpieza real
  -> snapshot posterior -> diff (creado/modificado/eliminado)
  -> ExecutionArtifact por cada cambio, con contenido real leido de disco
  -> ExecutionResult (status, adapter, duration, stdout/stderr resumido
     via _truncate(), exit_code, artifacts, error estructurado)
```

`cancel(mission_id)` busca el proceso activo en `self._active_processes`
(protegido por un `threading.Lock`, porque `execute()` corre en el
hilo propio del Executor mientras `cancel()` puede llegar desde otro
hilo), y si existe, envia SIGTERM/SIGKILL a todo el grupo de procesos
-- cancelacion real, no cosmetica. `execute()` distingue "cancelado"
de "murio por su cuenta" via un set `self._cancel_requested`.

### Deteccion de cambios

`_snapshot(workspace)` recorre el workspace y guarda un hash sha256
por archivo (excluyendo `.git`/`.claude`, y excluyendo implicitamente
`prompt_package.json` porque el baseline se toma DESPUES de escribirlo).
`_diff(before, after)` produce tres listas (creado/modificado/eliminado)
comparando esos hashes. `ExecutionArtifact` gano un campo nuevo,
`change_type` ("created"/"modified"/"deleted", default "modified" para
retrocompatibilidad total con `DeterministicLocalAdapter` y con todos
los test doubles anteriores). `orion.executor.services.run_for_mission`
gano el unico cambio correspondiente: si `change_type == "deleted"`,
hace `target.unlink()` en vez de escribir -- GitManager sigue siendo el
unico responsable de git; esto es un simple unlink de filesystem, tan
mundano como el `write_text()` que ya existia.

### `ExecutionResult` extendido

Tres campos nuevos, aditivos y con default vacio -- ningun adaptador
anterior (`DeterministicLocalAdapter`, los test doubles de
`tests/test_executor.py`) necesita tocarlos:

- `stdout_excerpt: str` -- salida estandar, truncada a `MAX_EXCERPT_CHARS`
  (4000 caracteres).
- `stderr_excerpt: str` -- idem para error estandar.
- `exit_code: int | None` -- codigo de salida real del proceso.

`ExecutionStatus` gano `CANCELLED`, distinto de `TIMEOUT` (el adaptador
dejo de esperar) y `FAILED` (el proveedor reporto un error) --
`orion.executor.services` ya trata cualquier status distinto de
`SUCCEEDED` como fallo de mision, asi que agregar este miembro es
aditivo y no rompe ningun switch existente.

### Seguridad -- checklist del Sprint, verificado contra el codigo real

| Requisito | Cumplido como |
|---|---|
| Nunca ejecutar sobre main directamente | El adaptador nunca toca git; `cwd` es siempre un workspace temporal aislado |
| Nunca ejecutar fuera del workspace asignado | `cwd=workspace`, nunca se pasa `--add-dir` |
| Nunca exponer credenciales en logs | Ningun token/secreto se lee, construye ni interpola en ningun string del adaptador (ver `tests/test_claude_code_adapter.py::SourceGuardTests` y `test_secret_env_value_never_appears_in_result`) |
| Nunca usar shell=True | `subprocess.Popen(args, ...)` con lista explicita, jamas `shell=True` |
| Lista explicita de argumentos | `_build_args()` construye una lista, nunca un string interpolado |
| Timeout configurable | `ORION_CLAUDE_CODE_TIMEOUT`, enforced en Python via `Popen.wait(timeout=...)` |
| Capturar stdout y stderr | Threads de drenado dedicados, siempre |
| Limite maximo de salida | `MAX_CAPTURE_CHARS` (200k, retencion) + `MAX_EXCERPT_CHARS` (4k, lo que se persiste) |
| Cancelacion real del proceso | `cancel()` -> `os.killpg` real sobre el grupo de procesos |
| Registrar PID mientras este activo | `self._active_processes[mission_id]`, poblado/limpiado alrededor de cada `_invoke()` |
| Limpiar estado al terminar | `finally` limpia `_active_processes`; workspace temporal se borra con `shutil.rmtree` en el `finally` de `execute()` |
| No permitir comandos destructivos fuera del workspace | `--permission-mode acceptEdits` (nunca bypass), `cwd` aislado -- limitacion honesta: esto depende de que el propio sandboxing de herramientas de Claude Code respete su cwd; ORION no implementa una jaula de filesystem adicional propia |
| GitManager como unico responsable de git | Sin cambios: el adaptador jamas invoca git |
| El adaptador no hace commit, push ni PR | Sin cambios: `execute()` solo devuelve `ExecutionArtifact`s: `orion.executor.services.run_for_mission` los escribe, y el Pipeline/GitManager existentes hacen el resto exactamente como antes |

### Pruebas (68/68 en la suite completa, sin llamar nunca al proveedor real)

`tests/test_claude_code_adapter.py` reescrito por completo para BETA
006. Cada prueba que ejercita un subproceso real usa un **CLI falso
real** -- un script Python ejecutable y desechable escrito a un
directorio temporal en cada test, nunca el binario `claude` real. Esto
prueba mecanica real de proceso (lanzamiento, stdin/stdout/stderr,
timeouts, terminacion de grupo de procesos) sin nunca acercarse a un
proveedor de IA real:

CLI no instalado, health_check exitoso (con CLI falso autenticado),
health_check con CLI falso no autenticado, exito real (crea un archivo
real, detectado y devuelto como artifact `created`), sin cambios,
error del proveedor (`is_error=true`), exit code distinto de cero sin
`is_error` (tratado como fallo de todas formas, defensivo), salida no
parseable como JSON, timeout real (con medicion de tiempo real,
confirmando que se corta mucho antes del sleep completo), cancelacion
real (ejecutada en un hilo, cancelada desde otro, con medicion de
tiempo real), stdout excesivo (500KB, resultado acotado), stderr
excesivo (idem), corto-circuito cuando `health_check()` falla (nunca
intenta el subproceso), `ORION_CLAUDE_CODE_MAX_TURNS` configurado y
notado en el resumen sin inventar un flag, secreto en variable de
entorno nunca aparece en el resultado, deteccion de creado/modificado/
eliminado a nivel de `_snapshot`/`_diff`/`_build_artifacts` (sin
subproceso), exclusion de `.git`/`.claude` del snapshot, `_invoke()`
dejando que un proceso real borre y modifique archivos pre-existentes
en un `cwd` controlado, registro y limpieza real del PID mientras el
proceso esta activo, ausencia de `shell=True` y de tokens de red/secretos
en el codigo fuente, y valores por defecto/lectura de las cuatro
variables de entorno documentadas.

`tests/test_executor.py` gano una prueba nueva,
`test_artifact_deletion_is_written_through`, confirmando que
`orion.executor.services.run_for_mission` borra realmente un archivo
del `repo_root` cuando un adaptador devuelve `change_type="deleted"`.

```
python3 -m unittest discover -s tests -v
```

68/68 OK, incluyendo las 51 pruebas de sprints anteriores sin ninguna
regresion.

### Validacion real -- resultado honesto

Se registro una mision de bajo riesgo real ("Crear un archivo
hello-orion.txt con una descripcion breve de ORION") contra un
repositorio sandbox desechable, con `ORION_PROVIDER=claude_code`, sin
tag `adapter:<nombre>` explicito, usando el **Claude Code real**
instalado en este entorno (no un CLI falso). Resultado: ver la
seccion final de este documento / el mensaje de reporte de este
Sprint para el diagnostico exacto -- este Sprint NO se declara
completo en el sentido de "ORION invoco Claude Code real y recibio
cambios reales", porque el entorno de ejecucion no tiene una sesion
autenticada (`claude auth status` -> `loggedIn: false`) ni
`ANTHROPIC_API_KEY`, y ninguno de los dos puede resolverse desde una
herramienta no interactiva. `health_check()` detecta esto
correctamente y `execute()` falla de forma limpia y documentada,
exactamente como esta disenado para hacerlo -- la implementacion esta
completa y probada de extremo a extremo salvo por la disponibilidad
de credenciales, que es una decision operativa fuera del alcance de
este Sprint ("no conectar claves privadas").
