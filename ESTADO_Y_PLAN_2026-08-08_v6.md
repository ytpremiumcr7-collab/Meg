# Megalodon — Estado del trabajo y plan de continuación (v6)
_Generado 2026-08-08, sexta sesión (misma fecha, continuación inmediata de v5)._

## Restricción del entorno (igual que siempre)
Sandbox sin red, sin `fastapi`/`sqlalchemy`/`alembic`/`pytest`/`structlog`/
`prometheus_client`/`docker` instalados. Todo verificado con `py_compile`
(árbol completo `backend/`, 301 archivos, 0 errores) + `bash -n` en los
scripts nuevos + un test funcional standalone del algoritmo de
detección de ciclos (sí se pudo correr, es Python puro sin deps
externas — ver sección G). **No** se levantó un server real ni se
corrió Docker. Antes de confiar esto en producción: dejar que el CI
nuevo (pendiente D) corra de verdad contra su Postgres/Redis/Docker
reales — eso era justo lo que faltaba y es exactamente lo que este
CI ahora hace en cada push.

## ✅ Hecho en esta sesión — D, J, G, I los cuatro cerrados

### D — CI insuficiente — CERRADO
El ZIP no traía ningún workflow. Se creó `.github/workflows/ci.yml`
desde cero, con 5 jobs independientes entre sí:
- **lint-and-compile**: `ruff check` + smoke test de *import real*
  (`python -c "import app.main"`, no solo `py_compile`) — ejecuta
  código de import-time de verdad, incluyendo el `sys.path.insert`
  hack de tezcatlipoca.
- **test**: Postgres real como service de GitHub Actions (imagen
  `postgis/postgis:16-3.4`, no `postgres` a secas — la migración
  `06d589924524` hace `CREATE EXTENSION postgis`) + Redis real,
  `alembic upgrade head` contra ese Postgres, `pytest -q`, y un
  arranque real de `uvicorn app.main:app` con smoke test HTTP contra
  `/health` y el `/metrics` nuevo (pendiente J). Las cuatro cosas que
  v5 marcaba explícitamente como "no se pudo ejecutar en este sandbox".
- **docker-build**: build real de `backend/Dockerfile` (sin push).
- **compose-validate**: corre el script nuevo del pendiente I contra
  un Docker real.
- **frontend**: `npm ci` + `npm run lint` + `npm run build` en
  `frontend/app`.

Verificado en este sandbox: YAML parseado con `pyyaml` (5 jobs, sin
errores de sintaxis). **No verificado**: que los jobs realmente pasen
en GitHub Actions — la primera corrida real será el primer push.

### J — Observabilidad — CERRADO (base: métricas + request-id; tracing/alerting quedan fuera, ver abajo)
`tezcatlipoca/core/observability.py::correlate_request` ya existía
pero nunca se conectaba a `app/main.py` (v5 lo señalaba como "punto de
partida natural"). Se creó `app/core/observability.py`, que:

- Genera/propaga `X-Request-ID` end-to-end vía un `ContextVar` (no
  thread-local — correcto bajo asyncio con requests concurrentes).
- Instala un `logging.LogRecordFactory` global (`install_request_id_log_factory`)
  que inyecta `request_id` en **todo** `LogRecord` del proceso, venga
  de `app.*` (structlog) o de `tezcatlipoca.*` (stdlib `logging` puro).
  Esto es clave: `tezcatlipoca/main.py::JSONFormatter` YA tenía
  `if hasattr(record, "request_id")` escrito, esperando que alguien lo
  conectara — nunca se llenaba. Se eligió un `LogRecordFactory` y no un
  `logging.Filter` porque un Filter atado a un logger no corre para los
  handlers de loggers ancestros (no cubriría la propagación entre
  `app.*` y `tezcatlipoca.*`), mientras que el factory corre una vez
  por cada record sin importar el logger/handler.
- `RequestContextMiddleware` (Starlette `BaseHTTPMiddleware`): agregado
  en `app/main.py` como el middleware MÁS externo (después de
  CORS/GZip), liga el request-id a `structlog.contextvars`, mide
  latencia y cuenta requests con Prometheus (`Counter`, `Histogram`,
  `Gauge` de en-curso, `Counter` de excepciones no manejadas), y
  regresa el id en el header de respuesta.
- `/metrics` en `app/main.py` (Prometheus text exposition format,
  scrape-able por cualquier Prometheus/Grafana estándar).
- `app/utils/logging.py`: se agregó `structlog.contextvars.merge_contextvars`
  como primer processor (para que `request_id` aparezca en el JSON de
  cada log de `app.*` sin pasarlo a mano) y se llama a
  `install_request_id_log_factory()` dentro de `configure_logging()`.
- `prometheus-client>=0.21.0` agregado a `pyproject.toml`.

**Fuera de alcance de esta sesión (documentado, no mock ni intento a
medias)**: tracing distribuido con OpenTelemetry (requiere decidir un
backend de infraestructura — Jaeger/Tempo/SaaS — antes de escribir
código, no es una decisión de código) y reglas de alerting (viven en el
Prometheus/Alertmanager del entorno de despliegue). Si se retoma J,
esto es lo que falta.

### G — TODOs de negocio — CERRADO
- **`firma_electronica.py:generar_sello_tiempo`** (el TODO original de
  RFC 3161/TSA): implementado de verdad con
  `pyhanko.sign.timestamps.HTTPTimeStamper` (mismo cliente que ya usa
  `PAdESLTSigner` para firmar PDFs, pero aquí opera sobre un hash
  arbitrario en vez de un PDF completo — útil para sellar artefactos
  no-PDF). Antes devolvía `None` siempre (documentado como
  deliberadamente más seguro que un timestamp falso); ahora intenta
  contra `DEFAULT_TSA_URLS` en orden y devuelve el `TimeStampToken`
  real en base64, o `None` con el motivo en logs si ninguna TSA
  respondió — mismo contrato, pero el caso positivo ya no es un
  placeholder. Nota honesta: se confirmó que este método no lo llama
  nadie hoy (`firma_service.py` usa su propio camino de TSA vía
  `PAdESLTSigner` para firmar PDFs) — quedó implementado como API
  pública correcta y disponible, no forzado a un call site que no le
  corresponde.
- **`cpm.py` — ciclos indirectos en predecesoras** (el TODO
  referenciado desde `programacion_service.py`, nunca cerrado ahí a
  propósito porque arreglarlo solo en el service daría falsa
  seguridad): se agregó `MotorCPM._detectar_ciclos()`, DFS iterativo
  (no recursivo — un programa de obra real puede tener miles de
  actividades encadenadas, y una versión recursiva reventaría el
  límite de recursión de Python), llamado al inicio de `calcular_cpm()`
  antes del forward pass. Si hay ciclo, `MegalodonException` con el
  ciclo completo (lista de ids). Antes: el `max_iter` del forward pass
  simplemente dejaba de iterar sin avisar, y las actividades atrapadas
  quedaban con fechas `None` silenciosamente. Verificado con un test
  standalone (Python puro, sin deps del proyecto — sí se pudo correr en
  este sandbox): ciclo directo, indirecto A→B→C→A, auto-referencia,
  predecesor inexistente (no debe marcarse como ciclo), y un grafo
  lineal de 2000 nodos sin ciclo (confirma que la versión iterativa no
  revienta con `RecursionError` a esa escala) — los 7 casos pasaron.
- **`documento_service.py:100`**: revisado — es un comentario
  histórico ("BUG ORIGINAL... nunca subía") documentando un bug YA
  arreglado en una sesión anterior, no un TODO vivo. Sin cambios (falso
  positivo del grep original).
- **`bim_service.py` líneas 183/529, `firma_service.py:13`**: falsos
  positivos — "TODO" ahí es parte de la palabra "TODOS" (español) o de
  prosa narrativa sobre un bug ya cerrado, no un marcador de pendiente.
  Sin cambios.

### I — validar `docker-compose.prod.yml` — CERRADO
Antes era una nota "SIN VERIFICAR" en un comentario, que no falla nada
si el entorno real no soporta los tags de merge. Ahora hay
`backend/scripts/validate_compose_prod.sh`, que:
1. Confirma `docker compose version >= 2.24.4` (versión exacta en la
   que Compose agregó los tags `!override`/`!reset`, confirmado contra
   el changelog/issues de `docker/compose` — la nota de v5 decía
   "≥2.24 aprox", ahora es la versión exacta).
2. Corre `docker compose -f docker-compose.yml -f docker-compose.prod.yml config --format json`
   con variables dummy para los `${VAR:?...}` requeridos, y parsea el
   JSON resultante (un script embebido de Python, no un `grep` frágil
   sobre YAML) para confirmar que `db`, `redis` y `minio` efectivamente
   quedan sin `ports` tras el merge.
3. Falla con `exit 1` y mensaje claro si cualquiera de las dos cosas no
   se cumple.
Conectado a D: corre como job `compose-validate` en el CI nuevo, en
cada push, contra un Docker real (GitHub Actions trae Docker
preinstalado). Ya no depende de que alguien se acuerde de correrlo a
mano antes de un deploy.

## Archivos tocados en esta sesión
```
.github/workflows/ci.yml                                      (nuevo — D)
backend/app/core/observability.py                              (nuevo — J)
backend/app/main.py                                            (+middleware, +/metrics — J)
backend/app/utils/logging.py                                   (+contextvars, +log factory — J)
backend/pyproject.toml                                         (+prometheus-client — J)
backend/app/modules/firma/firma_electronica.py                 (TSA real — G)
backend/app/engines/programacion/cpm.py                        (detección de ciclos — G)
backend/scripts/validate_compose_prod.sh                       (nuevo — I)
backend/docker-compose.prod.yml                                (comentario actualizado — I)
```

## 🔴 Pendiente — sin tocar en esta sesión
1. **Tracing distribuido + alerting** (la parte de J que quedó fuera a
   propósito, ver arriba — requiere decisiones de infraestructura antes
   de escribir código).
2. **No verificado, riesgo latente** (heredado desde v3, sin cambios):
   `tezcatlipoca/db/models.py` usa SQLAlchemy síncrono dentro del mismo
   proceso async de `app/main.py`. Vale la pena confirmarlo con un test
   de carga real antes de producción.
3. **Solo existe UNA migración de Alembic** (`06d589924524`, las
   extensiones de Postgres) — se notó al armar el job `test` del CI
   nuevo. Si el esquema completo (~30 tablas) se maneja hoy fuera de
   Alembic (autogenerate pendiente, o se aplica por otro medio), el CI
   nuevo NO lo va a detectar corriendo solo `alembic upgrade head` — es
   un hallazgo nuevo, no estaba en ningún audit previo, y no se tocó
   en esta sesión (fuera de alcance de D/J/G/I). Vale la pena
   confirmarlo antes de depender de este CI como garantía de esquema.
4. **CI nuevo, nunca corrido de verdad**: el primer push que dispare
   este workflow es la primera vez que se prueba contra dependencias
   reales — es posible que aparezcan ajustes menores (versiones de
   actions, timeouts, etc.) en esa primera corrida.

## Cómo retomar en el próximo chat
1. Sube este ZIP.
2. C (v3), IDOR de task_id (v4), F (v5), y D→J→G→I (v6) ya están
   cerrados.
3. Prioridad sugerida para la próxima sesión: punto 3 de arriba
   (confirmar si falta una migración baseline de Alembic) antes de
   confiar el CI en producción, y/o la parte de tracing/alerting de J
   si se decide ya la infraestructura.
4. Antes de dar por buena esta sesión en producción: dejar correr el
   CI nuevo de verdad en GitHub Actions (eso reemplaza el
   `pytest -q`/`alembic upgrade head`/`uvicorn` manual que pedían las
   sesiones anteriores — ahora es automático en cada push) y confirmar
   que `/metrics` y el `request_id` en logs se ven como se espera en un
   despliegue real.
