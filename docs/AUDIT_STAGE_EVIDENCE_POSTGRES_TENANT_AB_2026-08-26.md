# Megalodon v7 — Auditoría + implementación + reauditoría
## StageRun + Validation Evidence + Tenant A/B

Fecha: 2026-08-26
Baseline: `MEGALODON_V7_AUDIT_IMPLEMENTACION_QUIRURGICA_2026-08-26.zip`

## 1. Objetivo

Instrumentar el flujo real del `TenderOrchestrator` para que cada etapa deje un `StageRun` durable, enlazar cada `TenderValidationRun` a evidencia concreta y preparar una prueba E2E PostgreSQL con Tenant A/B usando el fixture INBAL, sin modificar Tezcatlipoca ni fusionar dominios de negocio.

La arquitectura conserva:

- Expediente
- Planeación
- Topografía
- BIM
- Costos/APU
- Presupuesto
- Programación
- Jurídico
- Licitaciones
- Licitaciones de Obra
- Documentos
- Firma
- Validación
- Auditoría

El orquestador sólo coordina; no posee los datos de esos dominios.

## 2. Auditoría previa

Se localizaron estas condiciones antes de tocar el código:

1. `PreparationRunTracker` existía, pero guardaba el trace en la misma `AsyncSession` que el flujo de negocio. Un rollback del negocio podía borrar la traza.
2. Sólo existía una etapa visible (`ORCHESTRATION`); no había evidencia persistida del recorrido interno del `TenderOrchestrator`.
3. `TenderValidationRun` guardaba un JSON `evidence`, pero no existía relación normalizada `validation -> evidence`.
4. El materializador consultaba `ExpedienteObra`, y los caminos BIM/Topografía no tenían una defensa tenant explícita en todas las consultas.
5. `ProcurementService.run()` iniciaba el trace, pero algunas excepciones podían dejar el `PreparationRun` en `RUNNING`.
6. No había endpoint para inspeccionar el historial persistido del pipeline.

## 3. Cambios aplicados

### 3.1 `PreparationRunTracker`

Archivo:
`backend/app/services/procurement/preparation_runs.py`

Se cambió a sesiones independientes usando `AsyncSessionLocal`.

Consecuencia:

```text
BUSINESS TRANSACTION
       │
       ├── cambia TenderPackage / requisitos / resultados
       │
       └── puede rollbackearse

TRACE TRANSACTION
       │
       ├── PreparationRun
       └── StageRun
```

Si el negocio falla, la evidencia de la etapa no desaparece.

Pipeline version:
`procurement-preparation-v2`

### 3.2 Etapas reales del `TenderOrchestrator`

Cada etapa hace `BEGIN → PASS/FAILED` y guarda inputs/outputs/versiones:

```text
CONTRACT_POLICY
      ↓
LOAD_RULE_INPUTS
      ↓
REQUIREMENT_EVALUATION
      ↓
MATERIALIZATION
      ↓
RISK_ANALYSIS
      ↓
CROSS_CONSISTENCY
      ↓
VALIDATION_EVIDENCE
      ↓
LIFECYCLE_GATE
```

`engine_version`:
`tender-orchestrator-v2`

`rule_version`:
`procurement-rules-v2`

### 3.3 Evidencia de validación

Nuevo modelo:

`TenderValidationEvidenceLink`

Tabla:

`tender_validation_evidence_links`

Relación:

```text
TenderValidationRun
       │
       └── TenderValidationEvidenceLink
                │
                └── TenderEvidence
```

Cada `TenderValidationRun.evidence` también conserva:

```json
{
  "revision": 1,
  "model_hash": "...",
  "evidence_ids": ["..."]
}
```

Cuando un finding no trae evidencia previa de un requisito, el orquestador crea una evidencia de cálculo determinista identificada por:

`VALIDATION:<codigo>@r<revision>`

y utiliza el hash del modelo como `source_hash`.

### 3.4 Tenant hardening

`ProcurementMaterializer` ahora exige `tenant_id` explícito.

Se cerraron estas rutas:

```text
ExpedienteObra
ModeloBIM
CalculoVolumen
Presupuesto vía ExpedienteObra
ProgramaObra vía ExpedienteObra
```

La regla es:

```text
ID funcional
+
tenant del expediente/tender
```

No se confía en un ID proveniente del modelo sin verificar su pertenencia.

También se endurecieron consultas de artículos/fuentes jurídicos para impedir que un `article_id` de otro tenant sea aceptado por una regla local.

### 3.5 Error handling del run

`ProcurementService.run()` ahora termina el `PreparationRun` como:

```text
BLOCKED
FAILED
RUNNING
READY_FOR_HUMAN_REVIEW
```

según corresponda.

No se permite dejar una ejecución en `RUNNING` de forma silenciosa cuando una excepción sale del pipeline.

### 3.6 Historial API

Nuevo endpoint:

`GET /api/v1/procurement/tenders/{tender_id}/preparation-runs`

Siempre scoped por:

```text
tenant_id + tender_id
```

Permite reconstruir:

```text
run
 ├── correlation_id
 ├── pipeline_version
 ├── status
 └── stages[]
       ├── input_refs
       ├── output_refs
       ├── rule_version
       ├── engine_version
       ├── status
       └── errors
```

## 4. Migración

Nueva revisión:

`20260826_procurement_validation_evidence`

Down revision:

`20260826_procurement_preparation_runs`

El árbol Alembic tiene un único head:

`20260826_procurement_validation_evidence`

## 5. Prueba permanente PostgreSQL

Nuevo archivo:

`backend/tests/e2e/test_procurement_stage_trace_postgres.py`

La prueba exige PostgreSQL real y crea:

```text
Tenant A
  └── User A
      └── Expediente A
          └── Tender A

Tenant B
  └── User B
      └── Expediente B
          └── Tender B
```

Ambos tenants pueden reutilizar el mismo identificador externo de licitación porque el identificador de negocio pertenece al tenant.

La prueba comprueba:

1. `PreparationRun` persistido.
2. Todos los `StageRun` esperados persistidos.
3. `READY_FOR_HUMAN_REVIEW` del flujo válido.
4. acceso cross-tenant rechazado.
5. requirements/evidence tenant-scoped.
6. la misma lógica opera independientemente para A y B.

## 6. Lo que no se pudo ejecutar en este sandbox

El gate PostgreSQL real NO se marca PASS en este entorno.

El entorno actual no dispone de:

- `asyncpg`
- servidor PostgreSQL operativo
- Redis/Celery operativo

Se intentó instalar `aiosqlite`, pero el entorno no tiene acceso de red y no dispone del paquete localmente.

Por lo tanto no se afirma falsamente que el E2E PostgreSQL haya corrido aquí.

La prueba queda preparada para ejecución en el stack real.

## 7. Reauditoría posterior

### Compilación de archivos críticos

PASS:

- `orchestrator.py`
- `materializer.py`
- `preparation_runs.py`
- `service.py`
- `models/procurement.py`
- `api/v1/procurement.py`
- migración
- test estático
- test E2E PostgreSQL

### Contratos estáticos

PASS:

- 8 etapas del orchestrator presentes.
- `PreparationRunTracker` usa sesión independiente.
- cada búsqueda de StageRun verifica tenant.
- `TenderValidationEvidenceLink` existe y se persiste.
- `TenderValidationRun` guarda `evidence_ids`.
- Materializer requiere tenant.
- API de historial exige tender scoped al usuario.

### Alembic

PASS:

- un solo head.

### Tezcatlipoca

PASS:

`backend/tezcatlipoca`:

- archivos base: 89
- archivos resultantes: 89
- añadidos: 0
- eliminados: 0
- modificados: 0

**Resultado: byte-for-byte idéntico al baseline.**

## 8. Cambios de fuente deliberados

Sólo se modificaron:

```text
backend/app/models/procurement.py
backend/app/models/__init__.py
backend/app/services/procurement/preparation_runs.py
backend/app/services/procurement/service.py
backend/app/engines/procurement/orchestrator.py
backend/app/engines/procurement/materializer.py
backend/app/api/v1/procurement.py
```

Se añadieron:

```text
backend/alembic/versions/20260826_procurement_validation_evidence.py
backend/tests/procurement/test_stage_trace_static.py
backend/tests/e2e/test_procurement_stage_trace_postgres.py
```

No se eliminó ningún archivo original.

## 9. Veredicto

**IMPLEMENTACIÓN CORRECTA A NIVEL DE CÓDIGO Y CONTRATO.**

**NO-GO DE RUNTIME POSTGRESQL todavía**, exclusivamente porque este entorno no tiene la dependencia/infraestructura necesaria para ejecutar el gate real.

El siguiente gate real debe arrancar directamente con:

```text
PostgreSQL
↓
Tenant A/B
↓
INBAL
↓
PreparationRun
↓
StageRuns
↓
ValidationEvidenceLinks
↓
READY_FOR_HUMAN_REVIEW
↓
cross-tenant denial
```

y después provocarse un fallo/rollback para demostrar que la traza permanece.
