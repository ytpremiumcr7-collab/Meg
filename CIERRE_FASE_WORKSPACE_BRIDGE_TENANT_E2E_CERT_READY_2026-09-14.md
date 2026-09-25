# Megalodon — verificación y endurecimiento de fase de cierre
## 2026-09-14

## 1. Verificación del ZIP entregado anteriormente

Se verificó el ZIP anterior frente al nuevo árbol de código, no solo el nombre del archivo ni su tamaño redondeado.

- ZIP anterior: `MEGALODON_V11_AUDITORIA_PRODUCTO_PROFUNDA_CORREGIDA_2026-09-14.zip`
- ZIP anterior: 850 archivos tras extracción.
- Árbol nuevo: 855 archivos.
- Diferencias binarias: 29 archivos modificados, 6 agregados, 1 sustituido/eliminado como artefacto de reporte.
- El tamaño mostrado por `ls -lh` redondea ambos a 13M; esto NO significa que sean iguales.
- SHA-256 anterior: `24f88345bb9e0883dbf731ee88071f7726251e0c06eb4f615e1d4c42dddc15f2`
- SHA-256 nuevo: `1fe1349434b113eb1a88a4775b504f35113bf7c87a4b8c5f430236c48dbd65da`

El nuevo ZIP sí contiene cambios reales de código.

## 2. Cambios reales aplicados en esta pasada

### Tenant a nivel de servicio

Endurecimiento realizado en:

- `backend/app/services/base.py`
- `bim_service.py`
- `clash_service.py`
- `programacion_service.py`
- `presupuesto_service.py`
- `topografia_service.py`
- `montecarlo_service.py`
- `procurement/service.py`
- workers BIM / Monte Carlo / PDF / Excel
- routers correspondientes

`BaseService(tenant_required=True)` ahora exige contexto tenant aunque el modelo no tenga una columna `tenant_id` propia. Esto es importante para agregados cuyo tenant se obtiene a través de `ExpedienteObra`.

Las entidades hijas sin `tenant_id` propio se validan mediante joins hacia su raíz tenant-owned, en lugar de inventar columnas inexistentes.

Ejemplo crítico corregido:

`ElementoBIM` no posee `tenant_id`; la consulta correcta es `ElementoBIM -> ModeloBIM -> tenant_id`.

Se eliminaron las consultas añadidas incorrectamente que intentaban acceder a `ElementoBIM.tenant_id`.

### Programación

Las lecturas de `ProgramaObra` y `ActividadPrograma` ahora validan el tenant a través de `ExpedienteObra`.

### Presupuesto

Las lecturas de `Presupuesto`/`Partida` se enlazan con `ExpedienteObra` para comprobar tenant.

### Topografía

`TopografiaService` ahora exige tenant y todos los objetos derivados se resuelven a través de `Levantamiento -> ExpedienteObra`.

### Clash

`ClashService` exige tenant.

`ModeloBIM` y `AnalisisClash` son las raíces tenant-owned; `ClashResult` se resuelve a través de `AnalisisClash`.

### Monte Carlo

Los workers reciben explícitamente `_tenant_id` en el payload y las operaciones de progreso, cancelación, finalización y error filtran por tenant.

Presupuesto y Programa se validan contra el expediente tenant-owned.

### Workers de exportación

PDF y Excel reciben `tenant_id`, instancian `PresupuestoService` con contexto tenant y escriben en rutas:

`tenant/{tenant_id}/presupuestos/{expediente_id}/{presupuesto_id}/...`

### BIM Storage

El IFC persistido por `BIMService` ahora usa:

`tenant/{tenant_id}/{expediente_id}/{identificador}-{filename}`

Esto alinea el storage del dominio BIM con el contrato de aislamiento por tenant.

## 3. Bridge TenderPackage ↔ Licitacion

Se reforzó `TenderWorkspaceService.sync_bridge()`.

La sincronización ya no mantiene una segunda copia hardcodeada de los campos del bridge como lógica paralela al contrato.

Ahora:

1. carga el bridge tenant-scoped;
2. exige `field_mapping`;
3. exige `FAIL_CLOSED`;
4. verifica dirección;
5. verifica autoridad declarada;
6. aplica únicamente destinos permitidos por el contrato;
7. detecta revisión obsoleta;
8. incrementa `TenderPackage.current_revision` cuando la sincronización modifica el paquete;
9. persiste la versión efectiva de `Licitacion` después del flush.

Se corrigió además el error anterior donde `last_licitacion_version` podía registrar `row_version + 1` sin que la fila realmente hubiera alcanzado esa versión.

## 4. Workspace

El agregado documental existente se conserva y se integra con:

- `TenderPackage`
- documentos versionados
- historial inmutable
- edición humana
- optimistic locking
- bloqueo
- detección de edición humana que sería sobrescrita por regeneración
- fuentes/evidencias
- requisitos relacionados
- dependencias del modelo canónico

La regla de no destrucción silenciosa permanece fail-closed.

## 5. Regression guard

Se agregó:

`scripts/tenant_isolation_gate.py`

Este gate busca regresiones obvias como `db.get()` directo sobre raíces tenant-owned en los servicios/workers críticos y comprueba que los workers críticos tengan contexto tenant explícito.

Resultado ejecutado:

`TENANT ISOLATION GATE: PASS`

Este gate es una defensa adicional, no reemplaza E2E.

## 6. Prueba de dos tenants

Se amplió:

`backend/tests/integration/test_closure_two_tenants.py`

La suite cubre:

- Tenant A / Tenant B;
- Expediente A / B;
- TenderPackage A / B;
- Licitacion A / B;
- Workspace documental;
- edición humana;
- stale write;
- regeneración destructiva bloqueada;
- bridge cruzado rechazado;
- acceso HTTP cruzado;
- BIM;
- Presupuesto;
- Programación;
- Topografía;
- Monte Carlo;
- llamadas directas a servicios sin pasar por router.

## 7. Validación ejecutada en este entorno

### PASS

- Python `compileall`: PASS
- TypeScript `tsc --noEmit --pretty false`: PASS
- `scripts/tenant_isolation_gate.py`: PASS
- comparación binaria old/new: PASS, se demostraron cambios reales

### NO CERTIFICADO

El E2E PostgreSQL real todavía NO puede declararse PASS en este runtime.

Bloqueos objetivos del entorno:

- no está instalado `asyncpg`;
- no hay servidor PostgreSQL disponible;
- no existe `docker`/contenedor PostgreSQL utilizable;
- `structlog` tampoco está instalado y el entorno no tiene red para instalarlo;
- los tests existentes usan SQLite por defecto, pero esa ruta no sustituye la certificación PostgreSQL solicitada.

No se utilizó un mock de PostgreSQL para declarar éxito.

## 8. Estado de certificación

### CERT_READY, no CERTIFIED

La implementación fue modificada y verificada estáticamente. El ZIP entregado contiene código diferente al anterior.

La certificación final requiere ejecutar el mismo árbol contra PostgreSQL real y completar:

1. migraciones Alembic reales;
2. Tenant A + Tenant B reales;
3. datos equivalentes;
4. ataques cruzados HTTP;
5. ataques cruzados a servicios;
6. workers con payload tenant-scoped;
7. storage real o emulador compatible con el contrato, preferentemente storage real;
8. pruebas de optimistic locking concurrente;
9. regeneración vs edición humana concurrente;
10. comprobación de integridad de bridge y FK compuestas;
11. invalidación/recompilación después de cambios de fuente, requisitos, BIM, presupuesto y programación;
12. suite completa sin fallos de infraestructura.

No se debe cambiar el estado a `CERTIFIED` hasta obtener ese resultado.
