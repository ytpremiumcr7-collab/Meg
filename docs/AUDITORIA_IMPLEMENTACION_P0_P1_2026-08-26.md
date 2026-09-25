# Auditoría de implementación P0/P1 — Megalodon V7

Fecha: 2026-08-26
Baseline: `MEGALODON_V7_OPENL_DECISIONTABLE_RUNTIME_2026-08-26.zip`

## Alcance

Se auditó el ZIP original antes de modificarlo y, después, la copia de trabajo completa. La comparación se hizo por contenido/hash de archivos, AST/parseo Python, búsqueda de referencias, trazabilidad del pipeline Procurement, runtime de reglas/DecisionTable, migraciones y tests.

No se tomó README ni documentación histórica como fuente de verdad para los hallazgos de código.

## Delta de código

Archivos base: 785

Archivos finales: 787

Python base: 398

Python final: 400

Python `backend/app`: 241

Python `backend/tezcatlipoca`: 84

El delta contiene exactamente:

### Archivos nuevos

- `backend/alembic/versions/20260826_rule_execution_tenant_hardening.py`
- `backend/tests/procurement/test_p0_p1_hardening.py`

### Archivos modificados

- `backend/app/engines/juridico/motor_juridico.py`
- `backend/app/engines/procurement/orchestrator.py`
- `backend/app/engines/procurement/requirements.py`
- `backend/app/engines/procurement/rules.py`
- `backend/app/models/procurement.py`
- `backend/app/services/procurement/service.py`

No se eliminaron archivos existentes.

## P0 atacados

### P0-01 — Regla ACTIVE sin tests

Antes: `add_requirement()` y `_ensure_rule_definition()` podían crear `TenderRuleDefinition` con `status=ACTIVE` y `test_cases=[]`.

Implementado:

- auto-creación ahora produce `DRAFT`;
- activación exige casos de prueba no vacíos;
- las versiones no-DRAFT no pueden volver a editarse mediante `validate_requirement_rule()`;
- la migración convierte filas históricas `ACTIVE` sin tests/hash a `DRAFT`;
- PostgreSQL agrega checks para impedir `ACTIVE` sin tests o sin `compiled_hash`.

Resultado: **cerrado a nivel de servicio + base de datos**.

### P0-02 — Matcher fail-open

Antes: una condición sin `field` retornaba `True`.

Implementado:

- condición malformada sin `field` retorna `False`;
- la regla deja de producir un match implícito.

Resultado: **fail-closed implementado**.

### P0-03 — DecisionTable NO_MATCH tratado como error de test

Implementado:

- `DECISION_MISS` queda distinguido de `DECISION_CONFLICT`/errores de runtime;
- un caso de prueba con `expected=None` puede validar explícitamente `NO_MATCH`;
- se agregó prueba de regresión.

Resultado: **cerrado en el contrato del Testmethod-like runtime**.

### P0-04 — Ejecución DecisionTable no preservada correctamente por el orchestrator

Antes: el pipeline podía volver a pasar una definición de tabla por `compile()` de regla simple.

Implementado:

- `_compile_rule_definition()` selecciona `compile_decision_table()` cuando existe `rows`;
- el runtime ejecuta el artefacto correcto;
- los resultados serializados preservan filas seleccionadas, acciones y diagnósticos.

Resultado: **corregido**.

### P0-05 — Resultado `None` interpretado como PASS

Antes: `result=None` podía producir `result_matched=True`.

Implementado:

- ausencia de resultado ahora es `False`;
- errores de hash, regla no activa o runtime son bloqueantes;
- el requisito termina en `FAIL/UNKNOWN` y no en PASS falso.

Resultado: **corregido**.

### P0-06 — Provenance incompleta

Implementado nuevo `TenderRuleExecution` con:

- tenant/tender/requirement;
- rule definition, versión y `compiled_hash`;
- `source_reference`;
- versión del engine;
- estado/matched;
- hash y snapshot de facts;
- hit policy;
- filas seleccionadas;
- condiciones evaluadas;
- acciones;
- payload del resultado;
- error;
- revisión y timestamp;
- enlace opcional al `TenderValidationRun`.

Resultado: **la trazabilidad de ejecución ahora tiene un registro persistente dedicado**.

## P1 atacados

### P1-01 — Versiones realmente mutables

Implementado:

- sólo estados `DRAFT` se pueden validar/modificar en `validate_requirement_rule()`;
- una versión activa/retirada obliga a crear una nueva versión;
- la promoción a ACTIVE ocurre sólo después de tests exitosos;
- el artefacto fuente/hash de una versión activa deja de ser editable por esta ruta.

La transición de estado `ACTIVE -> RETIRED` sigue siendo mutable por diseño de lifecycle; eso no altera la definición/hash del artefacto.

### P1-02 — Integridad tenant en relaciones críticas

Implementado en PostgreSQL:

- claves únicas `(tenant_id,id)` para entidades del pipeline;
- FK compuestas para `TenderRuleDefinition -> TenderPackage/TenderRequirement`;
- FK compuesta para `TenderValidationRun -> TenderPackage`;
- FK compuestas para `TenderValidationEvidenceLink -> ValidationRun/Evidence`;
- FK compuestas en `TenderRuleExecution` hacia tender, requirement, rule definition y validation run.

Resultado: se reduce la posibilidad de representar una relación cross-tenant incluso si se saltan los servicios de aplicación.

### P1-03 — Umbrales jurídicos CANDIDATE usados como base decisoria

Implementado:

- un umbral `CANDIDATE` ya no puede producir procedimiento jurídico válido;
- retorna `SIN_DETERMINAR`, `valido=False`, `datos_verificados=False` y `es_candidato=True`;
- la observación se convierte en bloqueo explícito.

Resultado: **fail-closed para datos jurídicos no verificados**.

### P1-04 — Deuda de tests del runtime nuevo

Implementado:

- 5 regresiones nuevas para los P0/P1;
- suite Procurement completa: **28 passed** en un modo de ejecución aislado del `conftest` global.

## Verificación final

### PASS

- `python -m compileall` sobre `backend/app` y `backend/alembic/versions`.
- Parseo AST de todos los Python: **sin errores**.
- Tests nuevos P0/P1: **5 passed**.
- Suite `backend/tests/procurement`: **28 passed**.
- No hubo archivos borrados.
- El cambio final contiene sólo los 6 archivos modificados + 2 nuevos indicados arriba.

### LIMITACIÓN REAL

La suite completa del repositorio **no pudo colectarse** en este entorno porque falta el driver `aiosqlite`, que es necesario para que `app.models.base` cree el engine SQLite de pruebas. También el entorno no tenía `asyncpg` ni `structlog` instalados inicialmente.

No se afirmó que la suite completa estuviera verde.

Tampoco se ejecutó una migración real contra PostgreSQL de producción porque no hay una instancia PostgreSQL accesible en este entorno. Las migraciones fueron parseadas/compiladas y su cadena fue revisada estáticamente.

## Deuda que deliberadamente NO se fusionó a la fuerza

### Motores jurídicos legacy

Siguen existiendo y están huérfanos por referencias directas:

- `MotorEvaluacion`
- `SelectorProcedimiento`
- `MotorGarantiasPenalizaciones`

No se borraron ni se fusionaron artificialmente porque no existe evidencia suficiente para afirmar equivalencia funcional con el nuevo Rule Platform.

### Tezcatlipoca

No se refactorizó su arquitectura interna en esta ronda. El objetivo fue cerrar los P0/P1 del runtime Procurement sin crear una regresión masiva en el dominio Tezcatlipoca.

### RLS

No se añadió RLS de PostgreSQL en esta ronda. El aislamiento quedó reforzado con filtros de aplicación y FK compuestas. Activar RLS requiere además definir y establecer un contexto de tenant por conexión/transacción y contemplar el camino admin/system/worker; hacerlo sin ese contexto sería un cambio inseguro.

## Dictamen

Los P0 críticos identificados en la auditoría previa quedaron atacados a nivel de código y, cuando era razonable, a nivel de base de datos.

Los P1 de lifecycle, provenance, integridad tenant y datos jurídicos no verificados también quedaron atacados.

Lo que **no** queda certificado todavía es producción industrial completa: falta ejecutar la migración en PostgreSQL real, ejecutar la suite completa con todas las dependencias, y resolver de forma controlada los motores jurídicos legacy/Tezcatlipoca y RLS.

No se recomienda declarar este ZIP "production-ready" sólo con esta auditoría.
