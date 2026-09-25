# PRR — OpenL DecisionTable → AlgorithmBuilder → evaluator → runtime → Testmethod → Megalodon

Fecha: 2026-08-26
Base comparada: `MEGALODON_V7_OPENL_RULE_LIFECYCLE_2026-08-26.zip` recuperado antes de esta fase.

## 1. Qué se estudió de OpenL

La implementación oficial actual de OpenL muestra que `DecisionTable.bindTable()` prepara la tabla y delega en `DecisionTableAlgorithmBuilder`; éste prepara parámetros, construye evaluadores de condiciones, prepara acciones y construye un algoritmo de ejecución. El runtime invoca el algoritmo preparado en vez de interpretar la tabla completa desde cero en cada llamada. citeturn23file0turn24file0

Las tablas `Testmethod` ejecutan la regla real por cada fila de prueba y comparan la salida con el resultado esperado; la documentación oficial describe explícitamente ese contrato. citeturn479426search20turn479426search24

OpenL soporta distintas representaciones de reglas y versionado; esta fase tomó únicamente las ideas útiles para Megalodon, no Excel ni Java como dependencias. citeturn479426search5turn479426search2

## 2. Auditoría previa de Megalodon

El runtime previo de `backend/app/engines/procurement/rules.py` tenía reglas simples con `conditions` + operadores y hash determinista, pero no tenía una representación de `DecisionTable` con filas/acciones, ni una etapa de preparación de un plan de ejecución, ni un test equivalente a Testmethod sobre decisiones multi-fila.

`TenderRuleDefinition` ya era la fuente persistente correcta: su `definition` es JSON versionado y existe `compiled_hash`. Por eso NO se creó una nueva tabla ni un nuevo agregado para las tablas de decisión.

`TenderOrchestrator` ya tenía el punto correcto de integración (`REQUIREMENT_EVALUATION`) y la responsabilidad de ejecutar reglas. Por eso se amplió ese punto en lugar de añadir otro motor paralelo.

## 3. Implementación aplicada

### `backend/app/engines/procurement/rules.py`

Se añadió una capa de ejecución de `DecisionTable` compatible con el runtime existente:

- `CompiledDecisionRow` almacena path predividido, operador, valor, acción y orden.
- `CompiledDecisionTable` almacena filas inmutables, política de hit, índice opcional y hash de la fuente normalizada.
- `DecisionTableResult` devuelve filas seleccionadas, acciones, condiciones evaluadas, mensaje y error determinista.
- `compile_decision_table()` valida toda la tabla antes de permitir ejecución.
- `test_decision_table()` es el equivalente funcional de Testmethod y utiliza el mismo runtime productivo.
- `evaluate_decision_table()` ejecuta las filas precompiladas.

### Semántica

- `FIRST`: selecciona la primera fila coincidente; su precedencia es explícita.
- `UNIQUE`: exige exactamente una fila coincidente y devuelve `DECISION_CONFLICT` si varias coinciden. Es la política por defecto para evitar ambigüedad silenciosa.
- `ALL`: devuelve todas las filas coincidentes.

### Preparación/optimización

Los paths (`a.b.c`) se separan durante compilación, no por evaluación. Cuando todas las filas comparten la misma primera condición `eq` sobre el mismo campo, se construye un índice seguro por valor. Si no existe esa invariante, se usa el recorrido completo de filas para no alterar semántica.

No se genera Python, SQL ni código arbitrario a partir de la definición del usuario.

### `backend/app/engines/procurement/orchestrator.py`

- Las reglas existentes siguen usando `DeterministicRuleCompiler.compile()` y `DeterministicRuleRuntime.evaluate()`.
- Una definición con `rows` usa el nuevo `compile_decision_table()`.
- Se introdujo una cache acotada de planes ejecutables por `compiled_hash`, con máximo 256 planes. La DB sigue siendo la fuente de verdad.
- El `TenderOrchestrator` no adquiere propiedad sobre `TenderRequirement` ni `TenderRuleDefinition`.

## 4. Lo que NO se hizo

No se tocó `backend/tezcatlipoca`.

No se añadió un modelo canónico.

No se creó una nueva tabla SQL.

No se reemplazó el runtime de reglas simple.

No se introdujo Excel.

No se usó `eval`.

No se mezcló el motor de reglas con el workflow durable.

No se cambió `Licitaciones de Obra`.

## 5. Tests creados

`backend/tests/procurement/test_decision_table_runtime.py`

Casos:

- selección FIRST;
- orden determinista en solapamientos;
- conflicto UNIQUE;
- índice de igualdad seguro;
- Testmethod contra el mismo runtime productivo;
- rechazo de IDs duplicados.

Más las pruebas existentes de `test_rules.py` y `test_rule_lifecycle_openl.py`.

Resultado ejecutado con `pytest --noconftest`:

**10 passed.**

`compileall backend/app`:

**PASS.**

## 6. Auditoría posterior

Comparación fuente contra el base, excluyendo bytecode generado y caches:

Los únicos cambios de código son:

1. `backend/app/engines/procurement/rules.py`
2. `backend/app/engines/procurement/orchestrator.py`
3. `backend/tests/procurement/test_decision_table_runtime.py`

No hay eliminaciones de archivos del baseline.

`backend/tezcatlipoca`: comparación byte a byte = **0 diferencias**.

Los archivos modificados compilan con AST válido.

## 7. Limitación honesta

No se pudo ejecutar `pytest` completo ni el flujo HTTP/PostgreSQL completo en este sandbox porque las dependencias de aplicación/servicios no están disponibles (por ejemplo `structlog` y PostgreSQL). Por eso el resultado de esta fase no se presenta como GO de runtime productivo.

Sí se demostró la parte que se pretendía implementar: preparación, validación, compilación, ejecución determinista, resolución de filas, conflicto de reglas, cache de plan y Testmethod sobre el mismo runtime.

## 8. Veredicto

**PASS — implementación correcta para el alcance de esta fase.**

**PASS — compatibilidad con reglas simples existentes.**

**PASS — comportamiento determinista de DecisionTable.**

**PASS — pruebas Testmethod equivalentes.**

**PASS — integridad del árbol y ausencia de mutilación.**

**PASS — Tezcatlipoca intacto.**

**PENDIENTE — runtime PostgreSQL/HTTP completo.**
