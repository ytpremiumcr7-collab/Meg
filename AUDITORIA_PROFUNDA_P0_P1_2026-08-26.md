# Auditoría profunda Megalodón V7 — P0/P1 — 2026-08-26

## Alcance

Se auditó el árbol de código del ZIP recibido, priorizando:

- continuidad Alembic y coherencia modelo ↔ migración;
- autenticación/cookies/JWT y WebSockets;
- aislamiento tenant y rutas críticas;
- notificaciones y conexiones de transporte;
- exposición de módulos opcionales de Tezcatlipoca;
- dependencias Python/Node y reproducibilidad;
- compilación sintáctica y build verificable sin inventar resultados;
- búsquedas de TODO/FIXME/mocks/placeholders en código operativo.

No se usó README como fuente de verdad. Las decisiones de corrección se tomaron contra el código ejecutable, modelos y migraciones.

## Arquitectura observada

**Backend**

`FastAPI main` → `/api/v1` router → routers de dominio → servicios/módulos → motores deterministas → SQLAlchemy/async DB/Redis/storage.

Puntos de dominio relevantes: procurement/expedientes/documentos, validación/compliance, firma, BIM, topografía, notificaciones, jobs/workers y observabilidad.

**Tezcatlipoca** está integrado como sidecar namespaceado bajo `/api/tezcatlipoca/*`. Su router AI queda detrás de `FEATURE_AI_ASSISTANT`.

**Frontend**

`Vite + React + TypeScript` → apps/hubs → hooks/lib cliente API → cookies de sesión y REST/WS. Se observaron 15 apps frontend de primer nivel, 2 hooks TS y un cliente de dominio compartido.

## Conteo estructural

- Python bajo `backend/app`: 397 archivos.
- Routers/API: 32 archivos Python.
- Servicios/módulos: 58 archivos Python.
- Motores: 66 archivos Python.
- Modelos: 28 archivos Python.
- Frontend apps: 15 directorios de primer nivel.
- Hooks frontend: 2 archivos TS/TSX.
- La cadena Alembic reporta un único `head`: `20260826_rule_execution_tenant_hardening`.

## P0 corregido: migración `requirement_id`

### Problema

`20260826_rule_execution_tenant_hardening.py` consultaba y creaba FK contra `tender_rule_executions.requirement_id`, pero la migración padre `20260826_tender_rule_execution_provenance.py` no creaba esa columna. Una base nueva podía fallar antes de completar el hardening.

### Implementación

Se agregó en la migración de hardening:

1. detección de la columna en `information_schema`;
2. creación nullable sólo si falta;
3. backfill desde `tender_rule_definitions.requirement_id` por `rule_definition_id`;
4. validación explícita de filas sin `requirement_id`;
5. cambio a `NOT NULL`;
6. posteriormente, FK compuesto tenant-aware y el índice correspondiente.

La ruta de downgrade **no recrea** una FK histórica sobre `requirement_id`, porque esa columna no existía en la revisión padre. La columna se elimina al final del downgrade, después de quitar las estructuras que sí fueron añadidas por el hardening.

## P1 corregido: WebSocket

### Problema 1 — token obligatorio

El endpoint de notificaciones aceptaba cookies dentro del cuerpo de la función, pero la firma exigía `token: str`, por lo que una conexión cookie-only podía ser rechazada por validación antes de ejecutar el código.

### Corrección

`token` pasó a `Optional[str] = None`. La prioridad de autenticación queda cookie → query token.

### Problema 2 — fugas de conexiones

`disconnect()` eliminaba la conexión del índice por usuario, pero podía dejar el mismo WebSocket retenido en índices por tarea/capa.

### Corrección

Se limpia la conexión de los tres índices y se eliminan sets vacíos.

### Problema 3 — notificaciones globales

El servicio de notificaciones usaba `broadcast()` y además serializaba el payload antes de entregarlo a un manager cuyo contrato era `send_json(dict)`. Eso podía convertir el mensaje en string y ampliaba innecesariamente el ámbito del envío.

### Corrección

Las notificaciones se envían con `manager.send_to_user(destinatario, payload)` y el payload permanece como objeto.

## P1 corregido: AI opt-in real

`FEATURE_AI_ASSISTANT` ya existía con default `False`, pero el router AI de Tezcatlipoca se montaba siempre. Se cambió el montaje para ocurrir sólo cuando el flag es `True`.

Esto conserva el diseño actual: Tezcatlipoca puede existir sin convertir el asistente AI en dependencia obligatoria.

## Dependencias / build — resultado honesto

### Python

- Python del entorno: 3.13.5.
- El proyecto declara Python >=3.12 y Docker usa Python 3.12.
- `structlog` está declarado en `backend/pyproject.toml`, pero **no está instalado en este runtime**.
- Se intentó instalar las dependencias y el entorno no tuvo conectividad DNS/red hacia los repositorios. No se creó una instalación falsa ni se introdujeron wheels improvisados.
- `python3 -m compileall` del backend y migraciones: **OK**.
- Import de `app.main`: bloqueado por `ModuleNotFoundError: structlog`.
- `pytest --collect-only`: bloqueado en `conftest.py` por el mismo faltante, por lo que no se debe marcar la suite como verde.

### Node

- Node: 22.16.0.
- npm: 10.9.2.
- Frontend: no existe `package-lock.json`, `npm-shrinkwrap.json`, `yarn.lock` ni `pnpm-lock.yaml` en el árbol inspeccionado.
- El intento de instalación quedó impedido por falta de red y no produjo un `node_modules` utilizable.
- `tsc -b` no pudo ejecutarse realmente porque faltan `vite/client` y `node` en `node_modules`.
- Parseo sintáctico de los archivos TS/TSX/JS con el parser de TypeScript: **0 errores de parseo en 149 archivos inspeccionados**.

### Conclusión de build

**No existe evidencia suficiente para declarar build verde.** La fuente del bloqueo es reproducibilidad/dependencias del entorno, no un error de sintaxis detectado en el código fuente.

## Riesgos que quedan fuera de esta reparación

### P1/P2 — lockfiles

La ausencia de lockfile impide reproducir exactamente el árbol Node. Antes de cerrar release, en un entorno con red debe generarse y versionarse `frontend/app/package-lock.json` y cualquier lockfile que use el cliente TypeScript, y entonces el CI debe usar `npm ci`.

### P1/P2 — migraciones al arranque

El backend integrado intenta inicialización/migración desde el ciclo de vida de la aplicación mientras el compose también contempla un servicio dedicado de migración. Debe decidirse una única autoridad de migración para producción para evitar carreras entre workers.

### P2 — BaseService y tenant_id opcional

Existe una API genérica donde `tenant_id` puede ser opcional. Esto es un footgun arquitectónico para modelos tenantizados: futuras rutas podrían olvidar el scope. No se cambió globalmente porque hacerlo sin auditar todos los callers podría romper flujos de administración/globales legítimos.

### P2 — query-token WebSocket

Se conserva como compatibilidad. El camino preferido debe ser cookie/httpOnly; el query token puede aparecer en logs de proxies. Una siguiente iteración puede retirar el fallback cuando todos los consumidores hayan migrado.

## Validación posterior a los cambios

- `compileall`: OK.
- `alembic heads`: único head, OK.
- invariantes estáticas del downgrade sobre `requirement_id`: OK.
- parser TypeScript sobre fuente: 0 errores de parseo.
- `app.main` y `pytest` quedan bloqueados exclusivamente por `structlog` ausente.
- build Vite queda bloqueado por dependencias Node ausentes.

## Cierre

La implementación realizada es deliberadamente pequeña y localizada. No se reescribieron módulos de dominio ni se cambiaron contratos ajenos a los hallazgos P0/P1.

El ZIP entregable contiene el código corregido y este informe. No contiene un `node_modules` falso ni un entorno Python incompleto.
