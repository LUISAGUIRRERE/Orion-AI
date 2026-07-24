# Experience Engine v1

## Que es

`orion/experience/` convierte cada mision terminada en dos cosas
durables: un `ExperienceReport` (evidencia estructurada de lo que esa
mision logro, costo y revelo) y cero o mas `KnowledgeItem` en el
Knowledge Store (`Pattern`, `Decision`, `Lesson`, `Risk`,
`Opportunity`, `Best Practice`). No es una base de datos de logs: cada
entrada es pequena, estructurada, con proposito, y siempre trazable a
la mision que la produjo.

```
Mission
  |
  v
Experience Engine  (lee Mission + PromptPackage + ExecutionResult +
  |                  outcome del Pipeline + eventos, todo ya persistido)
  v
ExperienceReport + KnowledgeItem(s)
  |
  v
Knowledge Store  ->  The Window
```

## Desacoplamiento total

`orion/experience/` nunca modifica ni importa lo interno de
`orion.prompt_composer`, `orion.executor`, ni
`orion.execution.git_manager` -- solo lee lo que esos modulos ya
persistieron, exactamente por sus propias funciones publicas de
lectura (`prompt_storage.load()`, `executor_storage.load_result()`,
`execution_pipeline.get_outcome()`, `bridge_services.get_events()`).
Es el mismo patron que `orion.projects.services` ya establecio en
Sprint 009 para leer estado de otros modulos sin acoplarse a ellos.

## Clasificacion: deterministica, no IA

Cada regla en `rules.py` es una funcion pura sobre datos ya conocidos.
Ninguna llama a un proveedor de IA, ninguna adivina. Ejemplos reales:

- **Patterns:** "Mision tipo 'code_generation' completada sin errores
  de validacion", o "Grupo de N archivos relacionados generados juntos
  en 'components/home/'" (cuando una mision produce varios archivos en
  el mismo directorio).
- **Best Practice / Opportunity:** cada recomendacion generada se
  clasifica como Oportunidad si senala un vacio real (ej. "no se
  encontro documentacion de arquitectura para este proyecto") o como
  Buena Practica si describe un enfoque que funciono.
- **Lesson / Risk:** cada error real registrado en la linea de tiempo
  de la mision se convierte en una Leccion ("Evitar: <error>"); si
  hubo al menos un error, tambien se registra un Riesgo agregando
  todos los errores de esa mision.
- **Decision:** si la mision selecciono un adaptador explicitamente
  (tag `adapter:<nombre>`, ver `docs/EXECUTOR.md`), se registra como
  una decision tomada.

Los ejemplos de la especificacion de este Sprint ("Crear un Hero
reutilizable", "Tailwind requiere actualizar tokens antes del build")
son el tipo de conocimiento mas profundo, especifico del dominio, que
esta v1 **no** genera todavia -- necesitaria juicio real, no solo
lectura de senales estructuradas. Eso es trabajo futuro, explicitamente
fuera de alcance: "Lo importante es definir el contrato."

## Contrato de ExperienceReport

Estructura minima exigida por este Sprint, implementada 1:1 en
`orion/experience/models.py`: Mission Summary, Objectives Achieved,
Files Modified, Artifacts Generated, Execution Metrics, Errors
Encountered, Fixes Applied, Patterns Detected, Reusable Components,
Recommendations, Confidence Score.

`fixes_applied` queda siempre vacio en v1: ORION no tiene todavia un
mecanismo de reintento automatico, asi que no hay nada que esta
funcion pueda detectar honestamente. Documentado, no ocultado.

## Persistencia

Cada mision, tras terminar (REVIEW o FAILED -- un fallo tambien es
evidencia real), deja bajo `workspace/missions/<id>/`:
`experience_report.yaml` (siempre) y `experience_summary.md`
(renderizado legible, opcional pero siempre generado en v1). El
Knowledge Store vive en `workspace/knowledge/<item-id>.yaml`, un
archivo por item -- mismo patron de directorio-plano-de-YAML que ya
usan `orion.bridge.storage` y `orion.projects.storage`.

## Integracion con el Builder

Minima: `orion/agents/builder/agent.py` gana un solo helper,
`_record_experience_safely()`, llamado en los tres puntos de salida de
`process_next()` (exito, fallo del pipeline, excepcion) -- nunca puede
dejar una mision en un estado inconsistente ni interrumpir al Builder,
mismo patron defensivo que ya usan la integracion de Prompt Composer y
Executor.

## Integracion con The Window

- `GET /api/experience/{mission_id}` -- el ExperienceReport completo.
- `GET /api/knowledge` (filtros opcionales `type`, `project_id`, `tag`)
  y `GET /api/knowledge/{item_id}`.
- La pagina de detalle de una mision (`/missions/{id}`) ahora muestra,
  si existen, un resumen del Experience Report y una tabla del
  conocimiento generado por esa mision especifica.

## Eventos

`experience_generated` (siempre), `pattern_detected`,
`lesson_recorded`, `recommendation_created` (uno por cada
`KnowledgeItem` de tipo Pattern/Lesson/Best Practice/Opportunity
respectivamente). `Decision` y `Risk` se persisten en el Knowledge
Store y quedan enlazados en el reporte igual que los demas, pero esta
Sprint especifica exactamente cuatro tipos de evento -- ninguno de los
dos tiene uno propio, y no se inventa uno.

## Tests

`tests/test_experience.py`, `unittest` de la libreria estandar, sin
llamadas externas. Redirige `bridge_storage.MISSIONS_DIR` y
`knowledge_store.KNOWLEDGE_DIR` a un directorio temporal por test
(restaurado en `tearDown`), asi que nunca toca el `workspace/` real de
Orion-AI. Corre con:

```
python3 -m unittest tests.test_experience -v
```
