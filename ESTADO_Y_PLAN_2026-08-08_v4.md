# Megalodon — Estado del trabajo y plan de continuación (v4)
_Generado 2026-08-08, cuarta sesión (misma fecha, continuación inmediata de v3)._

## Restricción del entorno (igual que siempre)
Sandbox sin red, sin `fastapi`/`sqlalchemy`/`alembic`/`pytest` instalados.
Todo verificado con `py_compile` (árbol completo, 0 errores) + AST propio.
**No** se levantó un server real ni Redis real. Antes de confiar esto en
producción: `pytest -q`, `alembic upgrade head`, `uvicorn app.main:app`
de verdad, y un test de carga/integración contra Redis real para el
mecanismo nuevo de esta sesión.

## ✅ Hecho en esta sesión

### IDOR de `task_id` — CERRADO
Pendiente #1 de v3. Nuevo módulo `app/core/task_ownership.py`, mismo
patrón fail-open/fail-closed que `token_revocation.py` y `rate_limit.py`
(gobernado por `settings.security_protection_fail_closed`), con una
excepción de diseño explicada en su propio docstring: la *ausencia* de
registro para un `task_id` (no solo la caída de Redis) siempre deniega,
sin importar la política — fail-open ahí reabriría el mismo hueco.

Mecanismo: hash en Redis `task_owner:{task_id} -> {tenant_id, user_id}`,
TTL 6h, poblado en `register_task_owner()` al encolar y verificado en
`verify_task_owner()` al consultar/suscribir.

Conectado en los 3 puntos reales de exposición:
- `app/api/v1/montecarlo.py`: `POST /simular` registra, `GET
  /simular/{task_id}/status` verifica (404 `TareaNoEncontradaException`
  si no coincide — no 403, para no confirmar que el `task_id` existe).
- `app/api/v1/ocr.py`: `POST /extraer` registra, `GET
  /extraer/{task_id}/status` verifica.
- `app/api/v1/websocket.py`: acción `subscribe` de `/ws/progreso`
  verifica antes de suscribir. `_validar_token_ws` ahora también extrae
  `tenant_id` del claim del JWT (ya existía ahí desde
  `AuthService.create_access_token`, no hace falta ir a la base de datos).

**Hallazgo no documentado en v3**: `GET /extraer/{task_id}/status` de
OCR tenía el mismo IDOR exacto que Monte Carlo y WebSocket — el
comentario original en `websocket.py` no lo mencionaba. Se cerró igual,
con el mismo mecanismo compartido, y se dejó una nota en el código
explicando el hallazgo.

**BIM deliberadamente no tocado**: sus dos `.delay()`
(`app/api/v1/bim.py`) nunca devuelven el `task_id` de Celery al
cliente — el frontend hace polling sobre `modelo_id`/`generacion_id`,
ya scopeados por tenant vía la base de datos normal. No hay superficie
de ataque ahí para este mecanismo; no se le agregó `register_task_owner`
porque no hay nada que verificar del otro lado.

Nuevo código de error `ErrorCode.TAREA_NO_ENCONTRADA` (`AUT-2007`) y
excepción `TareaNoEncontradaException` (404) en `app/core/errors.py`,
manejada por el `exception_handler` global existente en `main.py` — no
requirió tocar `main.py`.

Verificado en esta sesión:
- `py_compile` del árbol completo (0 errores).
- Chequeo AST propio confirmando que `register_task_owner`/
  `verify_task_owner` se llaman exactamente donde deben en los 3
  archivos tocados.
- Lectura del inventario `endpoint_inventory_rate_limit_FINAL.json` de
  la sesión anterior para confirmar que sigue siendo 337/339 (esta
  sesión no tocó rate limiting).

**No verificado** (requiere Redis real, no se puede en este sandbox):
que `redis.asyncio` con `decode_responses=True` (config actual de
`app/core/redis_client.py`) efectivamente devuelva `str` en
`hget`/`hset` como asume el código nuevo — es consistente con cómo ya
se usa en `token_revocation.py`, pero no se ejecutó contra un servidor
real.

## 🔴 Pendiente — sin tocar en esta sesión

1. **D — CI insuficiente.** Sin tocar.
2. **F — `except:`/`pass` silenciosos.** Sin tocar.
3. **J — Observabilidad** (métricas Prometheus, tracing, request-id
   end-to-end, alerting). Sin tocar.
4. **G — TODOs de negocio** (TSA/RFC 3161 en firma electrónica y otros).
   Sin tocar.
5. **I — validar `docker-compose.prod.yml`** (`ports: !override []`
   requiere Docker Compose ≥ 2.24 aprox — falta confirmar contra el
   entorno real de despliegue). Sin tocar.
6. **No verificado, riesgo latente** (heredado de v3, sin cambios):
   `tezcatlipoca/db/models.py` usa SQLAlchemy síncrono dentro del mismo
   proceso async de `app/main.py`. Vale la pena confirmarlo con un test
   de carga real antes de producción.

## Archivos tocados en esta sesión
```
app/core/task_ownership.py               (NUEVO)
app/core/errors.py                       (+ErrorCode.TAREA_NO_ENCONTRADA, +TareaNoEncontradaException)
app/api/v1/montecarlo.py                 (register/verify en crear + status)
app/api/v1/ocr.py                        (register/verify en crear + status)
app/api/v1/websocket.py                  (tenant_id en _validar_token_ws, verify en subscribe)
```

## Cómo retomar en el próximo chat
1. Sube este ZIP.
2. C ya está cerrada (v3) y el IDOR ya está cerrado (v4). Seguir con
   D → F → J → G → I, en el orden que resulte más cómodo — ya no hay
   ningún pendiente de fuga de datos activa en la lista.
3. Antes de dar por buena esta sesión en producción: correr
   `pytest -q`, `alembic upgrade head` contra Postgres real,
   `uvicorn app.main:app` de verdad, y una prueba de integración contra
   Redis real que ejercite `task_ownership.py` end-to-end (crear tarea
   con un tenant, intentar consultarla con otro, confirmar 404) — nada
   de esto se pudo ejecutar en este sandbox (sin red, sin dependencias
   instaladas).
