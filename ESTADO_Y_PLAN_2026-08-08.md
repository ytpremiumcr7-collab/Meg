# Megalodon — Estado del trabajo y plan de continuación
_Generado 2026-08-08, sesión de corrección post-auditoría._

## Qué es esto
Este ZIP es `megalodon_v4_fixed_security_flow_1_.zip` con las correcciones
aplicadas sobre `megalodon_v4_fixed_security_flow_audit.md` (la auditoría
que también mandaste). Es un backend FastAPI multi-tenant para gestión de
obra (expedientes, presupuestos, BIM, licitaciones, firma electrónica...)
más un módulo separado, **Tezcatlipoca** (`backend/tezcatlipoca/`), que es
una plataforma OSINT geoespacial (agrega 60+ fuentes públicas: ADS-B,
AIS, USGS, Shodan/CISA-KEV, KiwiSDR, Copernicus, etc.) con su propia base
de datos/esquema, expuesta bajo `/api/tezcatlipoca/*` en el mismo FastAPI.
Frontend en `frontend/app/` (React + Vite + Three.js).

**Restricción del entorno donde se hizo este trabajo:** sandbox sin red y
sin `alembic`/`sqlalchemy`/`fastapi`/`pytest` instalados (no se pudo hacer
`pip install`). Todo lo de abajo se verificó con `py_compile` + análisis
AST + inspección manual línea por línea, **no** con `pytest` real ni
`alembic upgrade head` contra una Postgres real. Es la misma limitación
que ya reconocían los tests preexistentes del propio proyecto
(`tests/integration/test_auth_flow.py` lo dice explícitamente en su
docstring). Antes de confiar en esto en producción: correr `pytest -q` y
`alembic upgrade head` de verdad, con Postgres/Redis arriba.

## Cómo estábamos trabajando
1. Yo (Claude) leo la auditoría (`.md`) + descomprimo el ZIP en un sandbox.
2. Verifico cada hallazgo del audit contra el código real (no confío
   ciegamente en el reporte ni en el código: leo ambos).
3. Ataco los bloqueadores en el orden de "Bloqueos reales" del audit,
   priorizando lo que rompe en runtime o es un hueco de seguridad real
   sobre lo que es deuda técnica/cosmética.
4. Cada fix se compila (`py_compile`) y, cuando aplica, se valida con un
   script Python que parsea el AST (para cosas como "¿quedaron las 8
   clases del modelo bien formadas?" o "¿la cadena de migraciones es
   lineal, sin huérfanos?") ya que no hay intérprete completo con las
   dependencias reales disponible aquí.
5. Cuando toco un endpoint/servicio con tests existentes, reviso si mi
   cambio de contrato rompe esos tests y actualizo o agrego tests nuevos
   en el mismo estilo que ya usa el repo (`tests/integration/conftest.py`).
6. Documento cada fix con el mismo estilo que ya usa el proyecto:
   docstrings tipo "BUG ORIGINAL: ... / AHORA: ..." directamente en el
   código, no solo en un changelog aparte. Así el próximo chat (o el
   próximo dev humano) entiende el porqué sin tener que preguntar.

## Hecho en esta sesión (verificado por compilación/AST, no por pytest real)

### ✅ Bloqueador A — `ApiLog` no existía
`backend/tezcatlipoca/db/models.py`
- No era solo un import roto: `class ApiLog(Base):` había desaparecido y
  su cuerpo (`__tablename__`, columnas) había quedado pegado dentro de
  `DeadDrop`, corrompiendo también esa clase (tabla/`id` sobreescritos).
- Separado limpiamente. Verificado con AST que las 8 clases
  (`User, UserSession, Snapshot, Tunnel, DeadDrop, ApiLog,
  TokenBlacklist, SystemSetting`) quedan bien formadas y con los campos
  correctos, coincidiendo exactamente con lo que usan
  `routers/admin.py`, `routers/auth.py`, `middleware/audit.py` y
  `core/bootstrap.py`.

### ✅ Bloqueador B — Registro público abierto por tenant/rol
`backend/app/api/v1/auth.py`, `backend/app/services/auth_service.py`,
`backend/app/models/user.py`, `backend/app/core/errors.py`
- `POST /auth/register` ya NO acepta `tenant_id` ni `role` del cliente.
  Ahora solo puede crear una organización (tenant) **nueva**, usando
  `AuthService.create_tenant()` — que ya existía en el código pero
  **nunca estaba conectado a ningún endpoint** (código muerto que
  resultó ser justo la pieza que faltaba).
- Nuevo modelo `Invitation` (`app/models/user.py`): para sumar gente a
  un tenant que YA existe, un ADMIN/SUPERADMIN de ese tenant crea una
  invitación (`POST /auth/invitations`) con email+rol fijos; la persona
  invitada canjea el token en `POST /auth/register/invite`. El
  tenant_id y el rol del usuario resultante salen SIEMPRE de la
  invitación guardada en DB, nunca de lo que mande el cliente.
- `SUPERADMIN` (rol "god admin" de plataforma, ver
  `app/core/entitlements.py: requiere_godadmin`) no se puede otorgar ni
  por `/register` ni por invitación — solo por acción directa de
  plataforma.
- Solo se guarda el hash SHA-256 del token de invitación (igual que ya
  hacían los refresh tokens legacy en el mismo archivo).
- 6 tests nuevos en
  `backend/tests/integration/test_registration_and_invitations.py`
  (happy path, rol ignorado del payload viejo, no-admin no puede
  invitar, no se puede invitar con superadmin, canje crea con
  tenant/rol de la invitación, invitación no se puede canjear 2 veces).
  **No ejecutados de verdad** (ver restricción de entorno arriba).

### ✅ Bloqueador E — Baseline de migraciones no existía
`backend/alembic/versions/`
- No había ninguna migración que creara el esquema base (~30 tablas:
  users, tenants, expedientes_obra, licitaciones, contratos, bim,
  presupuestos...). `alembic upgrade head` sobre una DB nueva fallaba
  en la migración de BIM 4D/5D porque asumía tablas que nadie creaba.
- Nueva migración `55225d1e7443` (encadenada entre `06d589924524` y
  `9f3a1c7d2b4e`): crea el esquema completo delegando en
  `Base.metadata.create_all(checkfirst=True)` sobre `app.models`
  (mismo mecanismo que ya usa `env.py` para autogenerate). Incluye la
  tabla `invitations` nueva.
- La migración de BIM 4D/5D (`9f3a1c7d2b4e`) se reescribió para ser
  **idempotente** (usa `sqlalchemy.inspect` antes de crear cada
  columna/tabla/índice), porque sus tablas (`zona_4d`,
  `generaciones_bim_4d5d`, `elemento_bim_actividad`) ya están
  declaradas en `app/models/bim.py` y por lo tanto la baseline nueva
  también las crea — así funciona sin importar el orden real de
  ejecución contra una DB parcialmente parchada.
- Cadena de revisiones validada estáticamente (parseo regex de
  `revision`/`down_revision`, sin depender del paquete `alembic` que no
  está instalado aquí): lineal, 3 migraciones, sin huérfanos, sin ramas.
  **Falta correr `alembic upgrade head` de verdad contra Postgres.**

### ✅ Bug extra encontrado (no estaba en el audit original)
`backend/.gitignore` tenía:
```
alembic/versions/*.py
!alembic/versions/.gitkeep
```
Es decir: **ninguna migración se versiona en git nunca**, ni las que ya
existían antes de esta sesión. Corregido (regla eliminada, con
docstring explicando el porqué). Si el repo real ya tiene historial de
git con esta regla, vale la pena revisar si además de mi baseline nueva
hacen falta las migraciones viejas que quizás nunca se comitearon.

### ✅ Limpieza
574 archivos `.pyc` + 70 carpetas `__pycache__` eliminados del árbol
(bloqueador H del audit — contaminaba el artefacto).

## Pendiente — orden de prioridad sugerido para el próximo chat

1. **C — Rate limit y revocación solo cubren `/auth`.**
   `rate_limit_standard`, `rate_limit_strict`, `is_jti_revoked`,
   `revoke_jti` (en `app/core/rate_limit.py` y
   `app/core/token_revocation.py`) existen y funcionan, pero no están
   conectados en el resto de los ~25 routers de `app/api/v1/` ni en los
   ~20 de `tezcatlipoca/routers/`. Tarea mecánica pero grande: revisar
   router por router, decidir `standard` vs `strict` según sensibilidad,
   añadir el `Depends(...)`.

2. **D — CI insuficiente.**
   `.github/workflows/` corre `compileall` + `pytest -q`, nada más. Le
   falta: `alembic upgrade head` contra una Postgres de servicio real
   (esto habría podido atrapar el bloqueador E antes de este audit),
   build de la imagen Docker, lint (`ruff`/`mypy`), y — esto es clave —
   un **smoke test de import real** (`python -c "from app.main import
   app"` y lo mismo para tezcatlipoca), porque `compileall` NO atrapa
   bugs cross-módulo como el de `ApiLog`: solo valida sintaxis por
   archivo, no que los símbolos importados existan.

3. **F — `except:`/`pass` silenciosos.**
   4 `except:` desnudos + 15 `pass` en: `tezcatlipoca/main.py`,
   `tezcatlipoca/services/osint_recon/osint_engine.py`,
   `tezcatlipoca/services/snapshot_store.py`,
   `tezcatlipoca/services/data_fetcher.py`,
   `app/workers/bim_tasks.py`, `app/services/bim_service.py`.
   Requiere criterio caso por caso (no es mecánico): decidir si cada
   uno debe loguear+re-lanzar, loguear+continuar, o de verdad ignorarse.

4. **J — Observabilidad.**
   Falta métricas exportables (Prometheus), tracing distribuido,
   correlación de request ID end-to-end (ya hay algo en
   `tezcatlipoca/core/observability.py: correlate_request` — ver si se
   puede extender/reusar en el backend principal), dashboard/alerting.

5. **G — TODOs de negocio** (menor prioridad, es deuda conocida y
   documentada, no bloqueador de seguridad/runtime): TSA/RFC 3161 en
   `firma_electronica.py:356`, y pendientes en
   `programacion_service.py`, `documento_service.py`, `bim_service.py`,
   `firma_service.py`.

6. **I — `docker-compose.prod.yml`** usa `ports: !override []`; validar
   que la versión de Docker Compose del entorno real de despliegue
   soporta ese merge tag (nota ya la deja el propio archivo).

## Archivos tocados en esta sesión (para ubicar rápido en el próximo chat)
```
backend/tezcatlipoca/db/models.py                                  (fix ApiLog/DeadDrop)
backend/app/api/v1/auth.py                                          (register + invitations)
backend/app/services/auth_service.py                                (create_invitation, register_user_via_invite)
backend/app/models/user.py                                          (modelo Invitation)
backend/app/core/errors.py                                          (3 códigos de error nuevos)
backend/tests/integration/test_registration_and_invitations.py     (nuevo)
backend/alembic/versions/55225d1e7443_baseline_esquema_completo.py (nuevo)
backend/alembic/versions/9f3a1c7d2b4e_bim_4d_5d.py                  (idempotente + re-encadenada)
backend/.gitignore                                                  (fix regla que ignoraba migraciones)
```

## Cómo retomar en un chat nuevo
1. Sube este ZIP.
2. Pega o referencia este archivo (`ESTADO_Y_PLAN_2026-08-08.md`, va
   incluido dentro del ZIP en la raíz).
3. Dile a Claude en qué punto de la lista "Pendiente" quieres seguir
   (por defecto, seguiría en orden: C → D → F → J → G → I).
