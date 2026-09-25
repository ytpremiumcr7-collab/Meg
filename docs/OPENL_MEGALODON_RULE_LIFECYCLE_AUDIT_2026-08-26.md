# Megalodon v7 — OpenL-inspired Rule Lifecycle Audit
Fecha: 2026-08-26

## 1. Regla de preservación

Fuente base: ZIP `MEGALODON_V7_STAGE_EVIDENCE_TENANT_AB_2026-08-26.zip` recuperado antes de esta fase.

No se modificó `backend/tezcatlipoca/**`.
No se eliminaron archivos del baseline.
No se sustituyeron dominios de negocio por un modelo canónico.
No se introdujo IA/LLM.

## 2. Qué estudiamos de OpenL

La documentación oficial describe un BRMS donde las tablas de negocio son reglas ejecutables y se validan sintáctica y tipadamente antes del runtime. OpenL Studio permite crear/modificar reglas, explicación de cálculos y tablas de pruebas; el motor soporta decision tables, lookup tables, decision trees, spreadsheet calculations y algoritmos/flows. También existe versionado de reglas mediante propiedades de contexto y versionado de proyectos.

Fuentes consultadas:
- OpenL Getting Started: https://openl-tablets.org/documentation/getting-started
- OpenL Features: https://openl-tablets.org/features
- OpenL Reference Guide: https://openl-tablets.org/files/openl-tablets/5.27.5/OpenL%20Tablets%20-%20Reference%20Guide.pdf
- OpenL repository: https://github.com/openl-tablets/openl-tablets

La lección trasladada a Megalodon es el ciclo, no Excel ni Java:

RULE SOURCE → VALIDATE/COMPILE → VERSION → TEST → ACTIVATE → EXECUTE → EXPLAIN.

## 3. Auditoría previa: superficie realmente afectada

Se revisaron:
- `backend/app/engines/procurement/rules.py`
- `backend/app/engines/procurement/orchestrator.py`
- `backend/app/services/procurement/service.py`
- `backend/app/models/procurement.py`
- `backend/app/models/__init__.py`
- `backend/app/api/v1/procurement.py`
- migraciones de procurement existentes
- tests de procurement

Conclusión previa: Megalodon ya tenía `TenderRequirement.condition` y `DeterministicRuleRuntime`, pero no separaba fuente de regla/versionado/runtime. La evaluación no tenía una fase formal de compilación/validación y el resultado no exponía una explicación estructurada por condición.

## 4. Implementación aplicada

### 4.1 `DeterministicRuleCompiler`

Nuevo comportamiento:

1. valida estructura;
2. valida operadores;
3. valida tipos de parámetros específicos (`between`, `in`, `count_*`);
4. normaliza la definición;
5. agrega versión al artefacto ejecutable;
6. genera `compiled_hash` determinista;
7. puede ejecutar casos de prueba sin mutar datos de negocio.

No se usa `eval`, `exec`, SQL dinámico ni código arbitrario del usuario.

### 4.2 `TenderRuleDefinition`

Se agregó una entidad separada del `TenderRequirement`.

Responsabilidad:
- versión de regla;
- definición ejecutable;
- estado (`ACTIVE`, `RETIRED`, `DRAFT` cuando los tests fallan);
- casos de prueba;
- hash compilado;
- referencia a la fuente;
- activación/retirada.

`TenderRequirement` sigue siendo dueño del requisito de negocio. La nueva entidad no lo sustituye.

### 4.3 Integración con `TenderRequirement`

Se agregó `rule_definition_id` como referencia opcional.

Los requisitos sin condiciones declarativas siguen siendo válidos y no se fuerzan a convertirse en reglas.

Los requisitos con condiciones se convierten en una definición versionada antes de entrar al runtime.

### 4.4 Versionado

Nuevo método de servicio:
`create_requirement_rule_version(...)`

Cada nueva versión:
- compila;
- valida;
- ejecuta sus test cases si existen;
- retira la versión activa anterior;
- crea nueva versión;
- enlaza `TenderRequirement.rule_definition_id` a la nueva versión;
- actualiza la condición del requisito a la definición activa.

### 4.5 Testing de reglas

Nuevo método:
`validate_requirement_rule(...)`

Los casos tienen la forma conceptual:

```json
{
  "facts": { ... },
  "expected": true
}
```

Una prueba fallida no activa la regla y deja la definición en `DRAFT`.

### 4.6 Explicación de ejecución

`RuleResult` ahora devuelve:
- `rule_id`
- `rule_version`
- `matched`
- `message`
- `severity`
- `evaluated_conditions[]`

Cada condición expone:
- field
- operator
- expected
- observed
- present
- matched

Esto permite construir evidencia/provenance sin convertir el runtime en un motor opaco.

### 4.7 Orchestrator

El `TenderOrchestrator` ahora:
- compila/recupera la definición versionada antes de evaluarla;
- detecta hash compilado inconsistente;
- bloquea reglas no activas;
- registra la versión de regla ejecutada;
- conserva el pipeline existente;
- corrige el tránsito `QA_READY -> READY_FOR_HUMAN_REVIEW` cuando no hay findings.

No se sustituyó el orquestador ni el dominio de Procurement.

### 4.8 API

Se agregaron rutas para:
- validar casos de prueba de una regla;
- crear una nueva versión de regla.

Las rutas utilizan el `tender_id` autenticado y el servicio valida `tenant_id` junto con la entidad.

## 5. Migración

Nueva migración:
`backend/alembic/versions/20260826_tender_rule_lifecycle.py`

Crea:
`tender_rule_definitions`

y agrega:
`tender_requirements.rule_definition_id`

La cadena Alembic comprobada termina en:
`20260826_tender_rule_lifecycle (head)`

## 6. Auditoría posterior

### Archivos modificados

```text
backend/app/api/v1/procurement.py
backend/app/engines/procurement/orchestrator.py
backend/app/engines/procurement/rules.py
backend/app/models/__init__.py
backend/app/models/procurement.py
backend/app/services/procurement/service.py
```

### Archivos nuevos

```text
backend/alembic/versions/20260826_tender_rule_lifecycle.py
backend/tests/procurement/test_rule_lifecycle_openl.py
```

### Archivos eliminados

Ninguno.

### Tezcatlipoca

Archivos baseline: 89
Archivos finales: 89
Diferencias SHA-256: 0

## 7. Validación ejecutada

PASS:
- `python -m py_compile` sobre todos los archivos Python modificados.
- `python -m compileall` sobre `backend/app`.
- tests directos de compilación/ejecución de reglas:
  - hash determinista;
  - rechazo de operador inválido;
  - rechazo de `between` malformado;
  - explicación de condiciones;
  - versión de regla.
- AST parse de archivos críticos.
- revisión de Alembic heads.
- comparación SHA-256 de `backend/tezcatlipoca`.
- búsqueda dirigida de `eval(` / `exec(` en `backend/app/engines/procurement`.

## 8. Limitación honesta

El pytest de toda la aplicación y el runtime PostgreSQL no se pudieron ejecutar en este sandbox porque faltan dependencias/runtime del entorno (`structlog` y, en otro intento de carga directa de modelos, `aiosqlite`) y no hay PostgreSQL operacional disponible.

Por ello NO se marca como PASS el E2E de base de datos.

## 9. Veredicto

Código de la nueva capacidad: PASS.
Regresión estática: PASS.
Preservación de Tezcatlipoca: PASS.
Archivos eliminados: 0.
Runtime PostgreSQL: PENDIENTE.

No se requiere rehacer desde el baseline porque la auditoría posterior no encontró un defecto funcional determinista en la nueva implementación. El siguiente gate debe ejecutarse con el stack real y demostrar persistencia, tenant A/B y ejecución del rule lifecycle dentro del `TenderOrchestrator`.
