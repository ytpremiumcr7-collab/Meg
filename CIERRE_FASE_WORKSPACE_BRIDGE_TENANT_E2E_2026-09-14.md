# FASE DE CIERRE — WORKSPACE + BRIDGE + TENANT + E2E
Fecha: 2026-09-14

## Estado
Implementación de cierre aplicada sobre `MEGALODON_V11_FLUJO_END_TO_END_TENANT_CORREGIDO_2026-09-14.zip`.

## 1. Workspace documental
Se añadió un workspace persistente y versionado sobre `TenderPackage`:
- `TenderDocument`: contenido editable, modelo estructurado, estado, versión, revisión del tender, hash del modelo generado, procedencia, requisitos relacionados, dependencias de datos, warnings, conflicto y `row_version`.
- `TenderDocumentRevision`: historial inmutable de creación, edición humana y regeneración.
- API de listar/abrir/editar/historial/regenerar/bloquear.
- Control optimista de concurrencia: `expected_row_version` obligatorio en edición/regeneración.
- Regeneración fail-closed si una edición humana quedaría sobrescrita por un cambio de modelo/revisión.
- Compilación crea/actualiza la proyección de workspace. Si existe edición humana, no la sobrescribe y registra `last_conflict`.
- Frontend incluye editor documental, guardado de versiones e indicadores de revisión/procedencia.

**Nota honesta:** la representación editable inicial de los artefactos compilados es una proyección documental (texto/modelo + referencia al artefacto binario). El binario de entrega sigue siendo el artefacto compilado. Para que una edición arbitraria de texto sustituya automáticamente cualquier PDF/XLSX de entrega, el compilador específico debe aceptar ese modelo editable como fuente; no se ha fingido que un textarea recompila mágicamente un XLSX/PDF.

## 2. Bridge TenderPackage ↔ Licitacion
Se añadió `TenderLicitacionBridge` con:
- tenant_id
- tender_package_id
- licitacion_id
- expediente_id
- relationship_type
- contract_version
- field_mapping
- last_tender_revision
- last_licitacion_version
- conflict_policy
- active

Existe contrato explícito de tres campos iniciales y sincronización bidireccional fail-closed. La creación rechaza expedientes cruzados y ambos agregados deben pertenecer al tenant del actor.

También `Licitacion` recibe `row_version` y clave única `(tenant_id,id)` para permitir integridad referencial compuesta.

## 3. Tenant isolation a nivel servicio
Se reforzó `BaseService` con contexto de tenant y modo `tenant_required`. Expediente, programación, presupuesto y documento pasan el tenant al servicio.

BIM pasó a contexto tenant-scoped y los workers IFC/4D-5D reciben `tenant_id` explícito y filtran por `(id, expediente_id, tenant_id)` antes de leer o modificar.

El job de Procurement ya propagaba tenant y mantenía idempotencia tenant-scoped.

## 4. E2E dos tenants
Se añadió `backend/tests/integration/test_closure_two_tenants.py` cubriendo:
- dos tenants y expedientes independientes;
- TenderPackage A/B;
- Licitacion A/B;
- workspace A;
- edición y control de `row_version`;
- bridge A;
- lectura HTTP cruzada A→B y B→A;
- intento de bridge hacia la licitación del otro tenant;
- rechazo de regeneración destructiva después de edición humana.

### Resultado de ejecución en este entorno
- `compileall`: PASS
- TypeScript `tsc --noEmit`: PASS
- pytest E2E: **NO CERTIFICADO** porque el entorno carece de `structlog` y no tiene PostgreSQL/stack real disponible. Se intentó instalar `structlog`, pero el entorno no tiene acceso de red.

No se declara E2E PostgreSQL real aprobado. La prueba está incorporada; la certificación requiere ejecutar el mismo suite contra PostgreSQL real con dos tenants.

## 5. Correcciones frontend
- Se eliminó el overwrite destructivo de `canonical_model/source_manifest` en `refresh` al mezclar el elemento resumido de `list`.
- El idempotency key de compile usa la revisión devuelta por la persistencia de la revisión humana, no un `current_revision` potencialmente obsoleto de React.

## 6. Migraciones
- `20260914_workspace_bridge_tenant.py`
- `20260914_workspace_bridge_versioning.py`

Orden:
`20260914_db_driven_formats_structure`
→ `20260914_workspace_bridge_tenant`
→ `20260914_workspace_bridge_versioning`

## 7. Lo que NO se declara cerrado
1. Certificación PostgreSQL E2E real no ejecutada por limitación del entorno.
2. Falta todavía completar tenant-context defense-in-depth en todo servicio BIM/Costos/Presupuesto/Programación que haga queries directas; el cierre de esta pasada elimina los puntos críticos identificados, pero la certificación final debe ejecutar un escaneo sistemático de todas las consultas directas y workers.
3. El editor documental ya existe como agregado real, pero la compilación de cada formato binario debe terminar de consumir su modelo editable para que una edición sea materializable automáticamente en todos los formatos.

## Veredicto
La fase avanzó de "panel + artefactos" a una arquitectura con workspace versionado, bridge explícito y contexto tenant en servicios críticos. **No se marca CERTIFICADA hasta ejecutar PostgreSQL E2E de dos tenants y cerrar el escaneo completo de queries/workers.**
