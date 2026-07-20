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
