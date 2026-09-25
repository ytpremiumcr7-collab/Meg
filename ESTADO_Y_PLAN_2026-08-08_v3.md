# Megalodon — Estado del trabajo y plan de continuación (v3)
_Generado 2026-08-08, tercera sesión._

## Restricción del entorno (igual que siempre)
Sandbox sin red, sin `fastapi`/`sqlalchemy`/`alembic`/`pytest` instalados.
Todo verificado con `py_compile` (árbol completo, 0 errores) + AST propio.
**No** se levantó un server real. Antes de confiar esto en producción:
`pytest -q`, `alembic upgrade head`, y `uvicorn app.main:app` de verdad.

## ✅ Hecho en esta sesión

### 1. Prioridad #0 de la sesión anterior — CERRADA
`app/main.py` (el entrypoint real) ahora inicializa los ~15
engines/clientes de Tezcatlipoca (`DataFetcherEngine`, `FAANOTAMClient`,
`NASAEarthdataClient`, etc.) y los expone en `app.state`, replicando el
mismo bloque que antes solo vivía en `tezcatlipoca/main.py` (que nunca
se ejecuta en el proceso real). Antes de esta sesión, la mayoría de los
endpoints reales de Tezcatlipoca devolvían 500 en producción sin
importar auth/rate-limit. Se verificó cada constructor involucrado
(revisando su código fuente) para confirmar que ninguno revienta si
falta una API key — todos usan `os.getenv(..., "")` con default vacío y
degradan con gracia. Envuelto en `try/except` a propósito: un fallo
inicializando OSINT no debe tumbar el arranque de Megalodon completo
(ver `_iniciar_tezcatlipoca`/`_detener_tezcatlipoca` en `app/main.py`).

### 2. Tarea C — rate limiting mecánico, COMPLETADA
337 de 339 endpoints tienen ahora `Depends(rate_limit_standard)` o
`Depends(rate_limit_strict)` (los 2 restantes son los WebSocket, fuera
de este patrón por diseño — ya tienen su propio chequeo de revocación
de la sesión anterior). Política aplicada: GET/HEAD → standard
(100/60s), POST/PUT/PATCH/DELETE → strict (10/60s), con 2 excepciones
explícitas (`pagos.py` webhooks → standard, para no descartar
reintentos legítimos de Mercado Pago/Stripe que ya verifican firma
HMAC propia). Verificado con inventario AST antes/después
(`endpoint_inventory_rate_limit_FINAL.json` en el ZIP).

**Error propio cometido y corregido en esta misma sesión**: corrí el
codemod (`apply_rate_limits.py`) dos veces (la segunda para cubrir 2
endpoints de `auth.py` que se habían colado por un `SKIP_FILES` mal
puesto) sin regenerar el inventario intermedio — eso duplicó el
parámetro `_rate_limit` en 46 archivos (sintaxis inválida, no
compilaba). Lo until detecté con el compile-check de rutina de
costumbre (no asumí que "corrió sin error" == "quedó bien"), escribí
`dedup_rate_limit.py` para colapsar el patrón duplicado de forma
segura y acotada, y re-verifiqué compilación + inventario completo
después. Ambos scripts quedan en `backend/_sesion_scripts/` con una
nota explicando qué pasó, para que quede visible en vez de escondido.

## 🔴 Pendiente — sin tocar en esta sesión

1. **IDOR de `task_id`** (WebSocket y `GET
   /riesgo/simular/{task_id}/status`): documentado con comentario en el
   código desde la sesión anterior, sigue sin arreglarse. Requiere una
   tabla/hash Redis `task_id -> (tenant_id, user_id)` poblada en cada
   endpoint que crea una tarea Celery (OCR, BIM, Monte Carlo, PDF/Excel).

2. **D — CI insuficiente.** Sin tocar.
3. **F — `except:`/`pass` silenciosos.** Sin tocar.
4. **J — Observabilidad** (métricas Prometheus, tracing, request-id
   end-to-end, alerting). Sin tocar.
5. **G — TODOs de negocio** (TSA/RFC 3161 en firma electrónica y otros).
   Sin tocar.
6. **I — validar `docker-compose.prod.yml`** (`ports: !override []`
   requiere Docker Compose ≥ 2.24 aprox — falta confirmar contra el
   entorno real de despliegue). Sin tocar.

7. **No verificado, riesgo latente**: `tezcatlipoca/db/models.py` usa
   SQLAlchemy **síncrono** (`Session`, no `AsyncSession`) mientras que
   ahora corre dentro del MISMO proceso async de `app/main.py`. Cada
   request a un endpoint de Tezcatlipoca que use `Depends(get_db_generator)`
   ejecuta esa sesión síncrona dentro de un handler `async def` — FastAPI
   corre dependencias síncronas en un threadpool aparte automáticamente,
   así que no debería bloquear el loop, pero **no se verificó** que
   `get_db_generator` esté de hecho declarado de forma que FastAPI lo
   trate como sync-dependency (vs. quedar ejecutándose en el loop
   principal). Vale la pena confirmarlo con un test de carga real antes
   de producción — no es algo que se pueda verificar solo leyendo código
   en este sandbox.

## Archivos tocados en esta sesión
```
app/main.py                              (NUEVO: inicialización real de engines de tezcatlipoca)
+ los 46 archivos de routers (app/api/v1/*.py y tezcatlipoca/routers/*.py)
  con Depends(rate_limit_standard|strict) agregado -- ver
  backend/_sesion_scripts/endpoint_inventory_rate_limit_FINAL.json
  para la lista exacta endpoint por endpoint.
```

## Cómo retomar en el próximo chat
1. Sube este ZIP.
2. Recomendado seguir con el punto 1 (IDOR de task_id) ya que quedó
   documentado y acotado, o directamente D → F → J → G → I como se
   venía planeando — C ya está cerrada.
3. Antes de dar por buena esta sesión en producción: correr
   `pytest -q`, `alembic upgrade head` contra Postgres real, y
   `uvicorn app.main:app` de verdad — nada de esto se pudo ejecutar en
   este sandbox (sin red, sin dependencias instaladas).
