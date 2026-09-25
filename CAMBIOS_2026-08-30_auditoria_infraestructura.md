# Cambios 2026-08-30 — Auditoría de infraestructura (Tezcatlipoca / storage / uploads)

Contexto: se recibió una auditoría externa completa del ZIP
`MEGALODON_V7_2026-08-27_legal_corpus_integrado`. La parte jurídica de esa
auditoría ya se verificó y quedó documentada en
`CAMBIOS_2026-08-27_legal_corpus_integracion.md`. Este archivo cubre la
verificación y corrección de los hallazgos de infraestructura/despliegue
(P0 de esa auditoría), cada uno confirmado leyendo el código real antes de
tocar nada -- no se aceptó ningún hallazgo solo porque el reporte lo dijera.

## 1. Tablas de Tezcatlipoca ausentes de Alembic — CONFIRMADO Y CERRADO

Verificado: `tezcatlipoca/db/models.py` declara su propio
`Base = declarative_base()`, separado de `app.models.base.Base`.
`alembic/env.py` construye `target_metadata` solo a partir de
`app.models.base.Base` (`import app.models` puebla ese metadata;
`tezcatlipoca.db.models` nunca se importa ahí). Ninguna migración en
`alembic/versions/` crea `tezcatlipoca_users`, `user_sessions`,
`snapshots`, `tunnels`, `dead_drops`, `api_logs`, `token_blacklist` ni
`system_settings` -- confirmado con grep sobre las 14 migraciones
existentes, cero resultados.

La única migración relacionada
(`f4c2d7e9a1b6_tez_audit_tenant_scope.py`) hace `ALTER TABLE api_logs`
condicional a que la columna no exista -- asume que la tabla podría
existir de una instalación vieja con el `create_all()` en runtime que el
propio código de Tez documenta como abandonado (comentario en
`db/models.py` línea ~220), pero no la crea.

**Corregido:** `alembic/versions/20260829_tezcatlipoca_tables.py` -- crea
las 8 tablas con el esquema exacto de `tezcatlipoca/db/models.py`
(columna por columna, verificado por lectura directa, no regenerado de
memoria), con guard `if tabla not in existing` para no romper
instalaciones viejas que sí tengan alguna de estas tablas ya creada por el
`create_all()` legacy. Head único verificado tras integrarla.

**No resuelto, a propósito:** la fractura de fondo sigue -- Tez tiene un
`Base` separado del resto del proyecto. Un cambio futuro a
`tezcatlipoca/db/models.py` NO se reflejará en `alembic revision
--autogenerate` a menos que alguien lo escriba a mano, como se hizo aquí.
La forma correcta de cerrar esto de raíz es que `alembic/env.py` importe
también `tezcatlipoca.db.models` y una ambos metadata en un solo
`target_metadata` -- no se hizo en esta ronda porque cambia el
comportamiento de autogenerate para *todo* el proyecto, no solo para Tez,
y eso merece decidirse aparte, no colarse dentro de un fix de tablas
faltantes.

## 2. Migraciones concurrentes al arrancar — CONFIRMADO, NO RESUELTO

Verificado: `docker-compose.prod.yml` ya tiene un servicio `migrate`
dedicado (`command: alembic upgrade head`), y `api`/`worker`/`scheduler`
declaran `depends_on: migrate: condition: service_completed_successfully`.
Pero `app/main.py` línea 146, dentro del `lifespan` de FastAPI, también
llama `await init_db_async()` → `tezcatlipoca/db/models.py:
_upgrade_database_sync()` → `command.upgrade(config, "head")` -- en cada
proceso. El `api` service corre `uvicorn ... --workers 4`: cuatro
procesos, cada uno reintentando `alembic upgrade head` al arrancar,
encima del `migrate` que ya corrió.

**No se cambió el comportamiento todavía.** El fix obvio es que
`_iniciar_tezcatlipoca()` verifique la revisión actual contra head en vez
de intentar aplicarla, y falle explícito si no coinciden -- pero esto
depende de cómo se despliega realmente en producción. Si el `migrate`
job de `docker-compose.prod.yml` es el camino real, verificar-no-aplicar
es estrictamente mejor. Si el despliegue real es Railway (sin ese
`migrate` job separado -- no confirmado si el compose productivo
efectivamente se usa o es aspiracional), este `init_db_async()` podría
ser hoy el ÚNICO mecanismo de migración, y cambiarlo a "solo verificar"
rompería el único camino que aplica el esquema. No se tocó hasta
confirmar cuál es el despliegue real.

## 3. Storage: MinIO declarado, Supabase usado — CONFIRMADO Y PARCIALMENTE CERRADO

Verificado: `docker-compose.prod.yml` declara un servicio `minio` con
`MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`, pero el bloque `environment` del
servicio `api` no incluye `SUPABASE_URL` ni `SUPABASE_SERVICE_KEY`.
`app/integrations/supabase_storage.py` -- consumido por `bim_service.py`,
`documento_service.py`, `firma_service.py`,
`services/procurement/service.py` y los workers de PDF/Excel/BIM -- no
tiene ningún camino alterno a Supabase: si faltan esas variables, hoy
sólo truena `MegalodonException` en el primer upload real, no al
arrancar. El servicio `minio` del compose no lo consume ningún módulo de
la app -- es infraestructura declarada sin código que la use.

**Corregido:** `app/config.py`, dentro de `_reject_insecure_production_runtime`
(mismo validador que ya falla el arranque por SECRET_KEY/DEBUG/SQLite en
producción), se agregó: si `ENVIRONMENT=production` y falta
`SUPABASE_URL` o `SUPABASE_SERVICE_KEY`, el arranque falla explícito con
un mensaje que señala la incoherencia MinIO-declarado/Supabase-usado. Esto
convierte una falla silenciosa en el primer upload real en una falla
inmediata y visible al desplegar -- no resuelve cuál debe ser la
autoridad de storage, solo evita que el sistema pase el health check y
falle después con un usuario real en medio.

**No resuelto, a propósito:** decidir Supabase vs. MinIO/S3-compatible
como autoridad real de storage, y si se elige MinIO, escribir el cliente
correspondiente y quitar `supabase_storage.py` de los flujos que lo usan
hoy. No se tomó esa decisión por el usuario.

## 4. Uploads sin límite antes de leer completo — CONFIRMADO, 1 DE 5 CERRADO

Verificado con `grep -rn "await file.read()\|await archivo.read()" app/api`:
5 puntos con este patrón --
`bim.py:206`, `expedientes.py:194`, `ocr.py:40`, `topografia.py:233` y
`topografia.py:393`. Ninguno aplicaba `IFC_MAX_FILE_SIZE_MB` ni
`TENDER_SOURCE_MAX_FILE_SIZE_MB` antes de leer -- el archivo completo
entraba a RAM sin importar su tamaño, y el límite (si acaso) se
comprobaba después, ya con todo cargado.

**Corregido:** `app/utils/upload_limits.py` -- helper
`read_upload_with_limit()` que lee en bloques de 1 MiB y aborta apenas se
cruza el límite (`MegalodonException`, HTTP 413), sin materializar el
resto del archivo en memoria. Aplicado en `bim.py` (la ruta que nombró la
auditoría explícitamente), usando `settings.IFC_MAX_FILE_SIZE_MB`.
`compileall` completo del backend: OK después del cambio.

**No resuelto, a propósito:** `expedientes.py:194`, `ocr.py:40`,
`topografia.py:233` y `topografia.py:393` siguen con el patrón viejo.
Cada uno necesita revisar qué límite de configuración le corresponde
(¿`TENDER_SOURCE_MAX_FILE_SIZE_MB` para expedientes? ¿existe un límite
específico para OCR y para los archivos de topografía, o hay que agregar
uno?) antes de aplicar el mismo helper -- no se apuró ese mapeo bajo
presión de tiempo en esta ronda.

## 5. Frontend sin lockfile — CONFIRMADO, NO RESUELTO (fuera del alcance de este entorno)

Verificado: no existe `package-lock.json` en `frontend/app/`, solo
`NOTICE_PACKAGE_LOCK.txt`. `package.json` tiene 73 dependencias con rango
`^` y 1 con `~` -- prácticamente todo el árbol de dependencias flota.

**No se pudo generar aquí:** este entorno no tiene acceso a red para
correr `npm install`. Hay que correrlo en un entorno con red (local o
CI), commitear el `package-lock.json` resultante, y desde ahí usar
`npm ci` en el pipeline de build -- no `npm install` -- para que el build
sea reproducible.

## Resumen de lo cerrado esta ronda

| Hallazgo | Estado |
|---|---|
| Tablas Tez ausentes de Alembic | ✅ Cerrado (migración nueva) |
| Migraciones concurrentes al arrancar | 🟡 Confirmado, sin tocar (depende de topología real de despliegue) |
| MinIO declarado / Supabase usado | 🟡 Fail-fast agregado; decisión de autoridad de storage sigue pendiente |
| Uploads sin límite antes de leer | 🟡 1 de 5 rutas corregidas (BIM); patrón replicable en las otras 4 |
| Frontend sin lockfile | 🔴 Confirmado, requiere entorno con red |
