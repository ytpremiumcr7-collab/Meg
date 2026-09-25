# Megalodon — Estado del trabajo y plan de continuación (v2)
_Generado 2026-08-08, segunda sesión — continuación de C→D→F→J→G→I._

## Restricción del entorno (igual que la sesión anterior)
Sandbox sin red, sin `fastapi`/`sqlalchemy`/`alembic`/`pytest` instalados.
Todo verificado con `py_compile` (árbol completo, 0 errores) + análisis
AST propio, **no** con un servidor real levantado ni Postgres/Redis
reales. Antes de confiar esto en producción: `pytest -q`,
`alembic upgrade head`, y levantar `uvicorn app.main:app` de verdad.

## Contexto: por qué esta sesión no siguió el plan al pie de la letra
El plan anterior decía que la tarea **C** era "conectar rate limit y
revocación, que ya existen, en el resto de los routers" — un trabajo
mecánico. Al auditar el código real (no el plan) para hacer C, encontré
que el problema era más grave de lo descrito: **66 endpoints de
Tezcatlipoca no tenían NINGÚN mecanismo de autenticación**, no solo les
faltaba rate limit. Verificado con un script AST propio (no me fié del
primer grep, que daba falsos positivos/negativos — ver
`inventory_v2.py`, corrido dos veces con resultados consistentes).
Corregir eso pasó a ser prerequisito de C, no C mismo.

## ✅ Hecho en esta sesión (verificado por compilación + AST)

### Bloqueador nuevo, no estaba en ningún audit anterior — CERRADO
**64 endpoints de Tezcatlipoca sin autenticación**, en 11 routers:
`ai_channel.py` (18), `aviation.py` (6), `sar.py` (6), `transport.py`
(7), `scm.py` (6), `geo.py` (3), `telemetry.py` (3), `photogrammetry.py`
(3), `geo_threats.py` (2), `entity_graph.py` (2), `layers.py` (2), más
huecos puntuales en `malware.py` (4) y `osint.py` (1).

De estos, los que SÍ pegan a servicios reales (no son stubs) son los
más serios: `aviation.py` (incluye `/military` y detección de GPS
jamming), `sar.py` (NASA/Copernicus/GEE), `photogrammetry.py` (creaba
proyectos WebODM sin auth). `ai_channel.py` (18 endpoints) y `scm.py`
son stubs — no tocan DB ni ningún engine, solo hacen echo del input —
pero se protegieron igual, documentado el porqué en cada archivo.

Política aplicada (documentada en cada archivo tocado):
- `malware.py`/`osint.py`: ya usaban `Depends(get_current_user)` en
  parte de sus endpoints → se completaron los que faltaban con el
  MISMO mecanismo (consistencia intra-archivo).
- Todo el resto: `Depends(require_role(["full", "admin"]))` — el mismo
  nivel que ya usa `cyber.py` (el módulo hermano más parecido:
  agregación de fuentes OSINT/threat-intel externas), para que un
  usuario tier "restricted" no pueda tocar ninguna fuente OSINT sensible
  sin importar el nombre del router.
- `wormhole.py: /health` se dejó público a propósito (su propio
  docstring dice "Public health check endpoint"; mismo criterio que ya
  usa el middleware de rate limit para excluir `/health`).

Verificado: re-corrí el inventario AST después del fix → 0 huecos
reales restantes (los 3 que aparecen son falsos positivos esperados:
los 2 WebSocket usan otro mecanismo, ver abajo, y `/health` es público
a propósito).

Herramienta usada: `fix_auth_gaps.py` (codemod AST, inserta el
parámetro en la posición exacta post-firma, no regex a ciegas) —
**dejo el script en el ZIP** por si hace falta re-auditar o extender el
patrón a futuros routers.

**Bug propio detectado y corregido en el codemod**: en 3 archivos con
docstring de módulo multilínea (`geo.py`, `geo_threats.py`, `scm.py`)
el primer intento del script insertó los imports nuevos DENTRO del
docstring (compilaba igual, porque sigue siendo un string válido, pero
quedaba mal). Se corrigió a mano en los 3 antes de dar la tarea por
cerrada — lo dejo anotado porque es exactamente el tipo de "parece que
funcionó pero está mal" que hay que verificar leyendo el resultado, no
solo confiando en que `py_compile` no truene.

### Rate limiting de Tezcatlipoca — reemplazado, no solo completado
Encontré DOS rate limiters caseros en memoria, independientes entre sí:
1. `tezcatlipoca/middleware/rate_limit.py` (middleware global,
   `dict` de proceso). Confirmé que **no se usa en el deploy real** —
   `app/main.py` monta los routers de tezcatlipoca directamente y nunca
   ejecuta `tezcatlipoca/main.py` (donde vive este middleware) — así
   que hoy es código muerto que aparenta proteger algo y no protege
   nada. Además, aunque se usara, tiene fuga de memoria (nunca evictea
   IPs que no vuelven) y no funciona bien con más de un worker.
2. `geo_threats.py` tenía su propio `_check_rate_limit` duplicado, con
   los mismos problemas.

Reemplazados ambos por `tezcatlipoca/core/rate_limit.py`, nuevo módulo
que reusa `tezcatlipoca/services/redis_client.py` (que YA existía con
un sliding-window correcto en Redis, pero ningún router lo llamaba) y
replica el diseño de `app/core/rate_limit.py` (mismo algoritmo,
`rate_limit_standard`=100/60s, `rate_limit_strict`=10/60s) sin fusionar
ambos módulos — a propósito, porque el propio código de integración
(`app/main.py`, sección "INTEGRACIÓN ZIP 4") deja explícito que unificar
tezcatlipoca con Megalodon es una decisión de producto pendiente, y
rate limiting es infraestructura pura que no necesita esperar a esa
decisión. Conexión a Redis perezosa (no depende de que un
`@router.on_event("startup")` se dispare en el proceso mergeado — no
pude confirmar empíricamente en este sandbox si eso ocurre cuando el
app padre define su propio `lifespan=`, así que se optó por no
depender de eso).

`geo_threats.py` ya quedó reconectado a este mecanismo (sus 2
endpoints). **El resto de Tezcatlipoca (y todo `app/api/v1/`) todavía
NO tiene `Depends(rate_limit_...)` conectado** — ver pendientes.

### WebSocket — revocación de tokens conectada
`app/api/v1/websocket.py`: los dos endpoints (`/ws/progreso`,
`/ws/notificaciones`) decodificaban el JWT a mano y nunca llamaban a
`is_jti_revoked` — a diferencia de TODO el resto de la API, que pasa
por `get_current_user` (que sí la revisa). Un logout no invalidaba una
conexión WebSocket ya autenticada con ese token hasta que expirara por
tiempo. Corregido con `_validar_token_ws()`, que centraliza decode +
chequeo de revocación para ambos endpoints.

## 🔴 Hallazgo crítico NUEVO, sin corregir — prioridad #1 del próximo chat
**`app/main.py` (el entrypoint real) nunca inicializa los engines de
Tezcatlipoca.** Confirmé con grep que `app/main.py` no tiene ninguna
ocurrencia de `app.state.data_fetcher`, `app.state.faa_notams`, ni
llama a `set_data_fetcher()`/`set_malware_agg()`/`set_osint_engine()`.
Todo eso solo se instancia en el `lifespan` de `tezcatlipoca/main.py`
propio, que **no se ejecuta** en el proceso real (solo se importan los
`router` objects, no el `main.py` completo).

Consecuencia: ahora mismo, en el deploy real (`uvicorn app.main:app`),
la mayoría de los endpoints de Tezcatlipoca que dependen de
`req.app.state.X` (aviation, sar, transport, photogrammetry — los que
SÍ son integraciones reales) devolverían 500 (AttributeError no
capturado específicamente, cae al handler genérico). Es un bug de
disponibilidad, no de seguridad — pero es más grave que cualquier cosa
de esta sesión en cuanto a "¿funciona el producto en absoluto".

No lo arreglé en esta sesión por precaución: mover/replicar la
inicialización de ~15 clientes de servicio dentro del lifespan de
`app/main.py` es un cambio de más alcance (¿debe fallar el arranque si
falta una API key? ¿debe ser perezoso por servicio?) que no quise
improvisar con el poco tiempo que quedaba en el turno. Es la tarea
número 1 recomendada para el próximo chat, antes incluso de seguir con
C.

## Pendiente — replanificado

0. **[NUEVO, prioridad más alta] Inicializar los engines de Tezcatlipoca
   en `app/main.py`.** Sin esto, Tezcatlipoca no funciona en el deploy
   real sin importar qué tan bien esté protegido o rate-limiteado.

1. **C (continúa) — Rate limit por endpoint.** Ya está el mecanismo
   correcto en ambos módulos (`app.core.rate_limit` y
   `tezcatlipoca.core.rate_limit`, este último nuevo). Falta conectarlo
   vía `Depends(...)` en:
   - Los ~275 endpoints de `app/api/v1/` que aún no lo tienen (auth.py
     ya lo tiene).
   - Los ~62 endpoints restantes de Tezcatlipoca que ya tienen auth
     pero no rate limit (todos menos `geo_threats.py`, que se dejó
     conectado en esta sesión como ejemplo del patrón a replicar).
   Política sugerida (misma idea del plan original): GET → standard,
   mutaciones (POST/PUT/PATCH/DELETE) → strict, con excepciones para
   endpoints admin/pagos/firma (strict siempre) y webhooks de pago
   (standard generoso, para no tirar reintentos legítimos de
   Mercado Pago/Stripe).

2. **IDOR de `task_id` en WebSocket y en
   `GET /riesgo/simular/{task_id}/status`** (hallazgo nuevo, documentado
   con comentario en el código pero NO arreglado): cualquier usuario
   autenticado de cualquier tenant puede consultar/suscribirse al
   progreso de un `task_id` ajeno si lo conoce (son UUID4, así que
   adivinarlos a ciegas es inviable, pero sigue siendo un control de
   acceso ausente). Arreglarlo bien requiere una tabla o hash en Redis
   `task_id -> (tenant_id, user_id)`, poblada en cada endpoint que hace
   `.delay()`/`send_task` (OCR, BIM, Monte Carlo, PDF/Excel) — toca
   varios archivos, no se improvisó a medias.

3. **D — CI insuficiente.** Sin tocar en esta sesión.

4. **F — `except:`/`pass` silenciosos.** Sin tocar.

5. **J — Observabilidad.** Sin tocar.

6. **G — TODOs de negocio.** Sin tocar.

7. **I — `docker-compose.prod.yml`.** Sin tocar.

## Archivos tocados en esta sesión
```
tezcatlipoca/routers/ai_channel.py       (+auth en 18 endpoints, docstring de stub)
tezcatlipoca/routers/aviation.py         (+auth en 6 endpoints)
tezcatlipoca/routers/entity_graph.py     (+auth en 2 endpoints)
tezcatlipoca/routers/geo.py              (+auth en 3 endpoints; fix bug de docstring)
tezcatlipoca/routers/geo_threats.py      (+auth en 2; rate limit Redis conectado; fix bug de docstring)
tezcatlipoca/routers/layers.py           (+auth en 2 endpoints)
tezcatlipoca/routers/malware.py          (+auth en 4 endpoints)
tezcatlipoca/routers/osint.py            (+auth en 1 endpoint)
tezcatlipoca/routers/photogrammetry.py   (+auth en 3 endpoints)
tezcatlipoca/routers/sar.py              (+auth en 6 endpoints)
tezcatlipoca/routers/scm.py              (+auth en 6 endpoints; fix bug de docstring; nota de stub)
tezcatlipoca/routers/telemetry.py        (+auth en 3 endpoints)
tezcatlipoca/routers/transport.py        (+auth en 7 endpoints)
tezcatlipoca/routers/wormhole.py         (+auth en 1; revertido a público en /health)
tezcatlipoca/core/rate_limit.py          (NUEVO — Redis sliding window)
tezcatlipoca/middleware/rate_limit.py    (reescrito: delega en core.rate_limit)
app/api/v1/websocket.py                  (revocación de tokens conectada)
```
Scripts de apoyo (quedan en el ZIP, no son parte del backend):
`inventory_v2.py` (inventario AST de auth), `fix_auth_gaps.py` (codemod).

## Cómo retomar en el próximo chat
1. Sube este ZIP.
2. Empezar por el punto 0 (inicializar engines de Tezcatlipoca en
   `app/main.py`) antes de seguir con C — sin eso, todo lo demás
   protege un módulo que no responde.
3. Seguir con C (rate limit mecánico en los endpoints restantes),
   después D → F → J → G → I como se venía planeando.
