# Megalodon — Auditoría de impacto + implementación quirúrgica

Fecha: 2026-08-26
Baseline: `MEGALODON_V7_RECONSTRUIDO_NO_MUTILADO_2026-08-26.zip`
Fuente de verdad: código del baseline recuperado. README/histórico no usados como fuente de comportamiento.

## 1. Regla de no mutilación

- No se elimina ningún dominio existente.
- `backend/tezcatlipoca/` no fue modificado.
- `backend/app/api/v1/licitaciones_obra.py` no fue reescrito ni reemplazado.
- No se crea un agregado universal/canónico.
- La implementación se concentra en `backend/app/engines/procurement`, `services/procurement`, modelos/migraciones y tests del dominio.

## 2. Inventario baseline

El ZIP recuperado contiene 1013 archivos en el árbol de trabajo antes de la compilación posterior.
El backend tiene 563 archivos bajo `backend/app`.
`backend/tezcatlipoca` contiene 89 archivos.

## 3. Hallazgos que cambian la estrategia

### H1 — `licitaciones_obra.py` del baseline recuperado NO coincide con el router fixture auditado en otro baseline

El archivo recuperado es un router MPPL de 937 líneas y 18 endpoints, con acceso real a SQLAlchemy y servicios/motores de pre-evaluación. El propio módulo declara que Megalodon no sustituye Compras MX ni adjudica/publica; su responsabilidad es parsing, validación, pre-fallo, correcciones y trazabilidad.

Decisión: NO reescribirlo en esta fase. La reconstrucción segura es trabajar sobre el dominio `procurement` que ya actúa como flujo estructurado persistente.

### H2 — El dominio procurement ya tiene la mayor parte de la arquitectura que necesitamos

Existe:
- `TenderPackage` tenant-owned.
- `TenderRequirement` con `condition`, `evidence_required`, `artifact_required`, `source_reference`, `legal_rule_id`, `legal_article_id`.
- `TenderEvidence` + `TenderEvidenceLink`.
- `TenderArtifact` + hashes/versiones.
- `TenderValidationRun`.
- `TenderRevision`.
- `SubmissionPackage`.
- `ProcurementJob`, idempotencia y storage intents.
- `TenderLifecycle`.
- `DeterministicRuleRuntime`.
- `ProcurementConsistencyEngine`.
- `TenderOrchestrator`.
- compilador real de artefactos.

Decisión: no duplicar estas capacidades con nuevos modelos paralelos.

### H3 — Falta trazabilidad durable de ejecución del pipeline

El estado del tender existe, pero no existía una entidad para responder, por ejecución:

`qué entró -> qué etapa corrió -> qué regla/engine/version usó -> qué produjo -> cuándo -> con qué error`.

Decisión: agregar `TenderPreparationRun` y `TenderPreparationStageRun`, tenant-scoped, sin absorber ningún dato de dominio.

### H4 — `READY_FOR_HUMAN_REVIEW` no existía como estado explícito

El flujo terminaba en `QA_READY` y después saltaba a `HUMAN_APPROVAL`.

Decisión: agregar `READY_FOR_HUMAN_REVIEW` como gate explícito entre QA y aprobación humana, manteniendo compatibilidad con `QA_READY`.

### H5 — El runtime de reglas estaba limitado a campos planos

`DeterministicRuleRuntime` sólo resolvía `facts[field]` y tenía un conjunto pequeño de operadores.

Decisión: extenderlo de forma compatible para paths anidados (`bidder.capital`) y operadores deterministas de uso directo en requisitos (`not_empty`, `count_gte`, `count_lte`, `between`). No se introduce `eval`, código del usuario, SQL ni red.

### H6 — Se detectaron consultas tenant-scope incompletas en operaciones de requisitos/evidencias/artefactos

Se corrigieron consultas en `ProcurementService` que dependían sólo de `tender_id` o `artifact_code` y no repetían el tenant explícitamente.

Decisión: endurecer en el mismo dominio, sin convertir `BaseService` global en cambio transversal en esta fase.

## 4. Archivos que SÍ fueron tocados

### Existentes modificados

1. `backend/app/api/v1/procurement.py`
   - expone `review_state` en respuestas de tender/listado.

2. `backend/app/engines/procurement/lifecycle.py`
   - agrega `QA_READY -> READY_FOR_HUMAN_REVIEW -> HUMAN_APPROVAL`.

3. `backend/app/engines/procurement/rules.py`
   - resolución de paths anidados y nuevos operadores deterministas.

4. `backend/app/models/__init__.py`
   - export de los nuevos modelos/estados de preparation run.

5. `backend/app/models/procurement.py`
   - `TenderState.READY_FOR_HUMAN_REVIEW`.
   - `TenderPackage.review_state`.
   - `PreparationRunStatus`.
   - `PreparationStageStatus`.
   - `TenderPreparationRun`.
   - `TenderPreparationStageRun`.

6. `backend/app/services/procurement/service.py`
   - instrumentación de `run()` con execution tracking.
   - gate explícito `READY_FOR_HUMAN_REVIEW`.
   - `review_state` persistido.
   - readiness actualizado.
   - aprobación humana acepta el nuevo gate.
   - refuerzo tenant de requisitos/evidencias/artefactos.

### Nuevos

7. `backend/app/services/procurement/preparation_runs.py`
   - tracker durable tenant-scoped.

8. `backend/alembic/versions/20260826_procurement_preparation_runs.py`
   - migración para `review_state`, `tender_preparation_runs` y `tender_preparation_stage_runs`.

9. `backend/tests/procurement/test_preparation_gate.py`
   - pruebas del nuevo estado y del runtime de reglas.

## 5. Archivos que deliberadamente NO se tocaron

- `backend/app/api/v1/licitaciones_obra.py`
- `frontend/**`
- `backend/tezcatlipoca/**`
- motores Topografía/BIM/Costos/Programación/Jurídico existentes
- `BaseService` transversal

Estos quedan para gates posteriores, una vez que el contrato de preparation run esté probado.

## 6. Contrato nuevo del flujo

```text
TenderPackage
   |
   +--> PreparationRun
           |
           +--> StageRun: ORCHESTRATION
           |
           +--> resultado/fallo persistido

QA_READY
   |
   v
READY_FOR_HUMAN_REVIEW
   |
   v
HUMAN_APPROVAL
```

`READY_FOR_HUMAN_REVIEW` no equivale a publicación. Compras MX sigue siendo el sistema externo oficial de contratación/publicación; el código del proyecto no debe simular esa publicación. Compras MX está actualmente en operación como Plataforma Digital de Contrataciones Públicas. 

## 7. Tenant hardening realizado

Se reforzaron queries de:
- `TenderRequirement` por `tenant_id`.
- `TenderEvidence` por `tenant_id`.
- `TenderRequirement` vinculado por `tenant_id`.
- `TenderArtifact` vinculado por `tenant_id`.
- cálculo de versión de artefactos por `tenant_id`.
- resolución de artículos jurídicos mediante fuente jurídica visible para el tenant.

El objetivo es que un ID ajeno nunca se convierta en una segunda vía de acceso sólo porque el `tender_id` coincide.

## 8. Validación ejecutada

- `python -m compileall -q app`: PASS.
- pruebas directas del lifecycle/reglas: PASS.
- integridad de `backend/tezcatlipoca`: sin diferencias respecto al baseline.
- comparación de código fuente: sólo los 6 archivos existentes listados arriba fueron modificados; 3 archivos nuevos fueron añadidos.

La suite Pytest completa sigue condicionada por las dependencias del entorno de ejecución (por ejemplo `structlog` no está instalado en este sandbox). Por eso este gate no se presenta como PRR de runtime PostgreSQL/Redis/Celery.

## 9. Pendientes, no mezclados en esta fase

P0/P1 siguientes:

1. instrumentar todas las etapas reales del `TenderOrchestrator`, no sólo `ORCHESTRATION`.
2. enlazar cada `TenderValidationRun` con referencias de evidencia concretas.
3. añadir endpoint de historial de `PreparationRun`/`StageRun`.
4. convertir la UI de procurement en visor de estado real.
5. integrar tenant A/B con PostgreSQL real.
6. crash/restart, idempotencia concurrente, storage failure, outbox/requeue/DLQ.
7. fixture INBAL contra el pipeline persistente real.
8. hardening transversal de `BaseService` después de auditar todos sus callers.

## Veredicto de esta fase

PASS CON ALCANCE CONTROLADO.

Se implementó la columna vertebral de trazabilidad y el gate explícito de revisión humana sin mutilar dominios existentes. No es todavía GO de producción.
