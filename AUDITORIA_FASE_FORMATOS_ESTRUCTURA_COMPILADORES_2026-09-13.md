# Megalodon — Fase formatos → estructura → compiladores

## Objetivo

Desacoplar del código los catálogos de formatos, la estructura de proposición y la selección de compiler, haciendo que `jurisdiction_code` sea el contexto raíz del tramo, sin convertir los algoritmos reales de BIM/costos/presupuesto/programación/workspace en stubs ni introducir fallbacks silenciosos.

## Cambios implementados

1. `backend/app/engines/procurement/format_field_map.py`
   - Eliminado el diccionario estático `FORMAT_TO_CANONICAL`.
   - El catálogo efectivo se carga desde `JurisdictionProfile.templates.format_definitions`.
   - Se respetan perfiles tenant/global e herencia de dependencia.
   - Los aliases solo normalizan nombres; no asignan una dependencia ni inventan reglas.
   - Un formato no configurado no se remapea silenciosamente a otra dependencia.

2. `backend/app/engines/procurement/proposition_structure.py`
   - Eliminada la lectura runtime de `proposition_structure.csv`.
   - La estructura se carga desde `JurisdictionProfile.templates.proposition_structure`.
   - La estructura DB se considera catálogo/configuración y no sustituye requisitos del expediente vigente.

3. Migración `20260914_db_driven_formats_structure.py`
   - Migra los catálogos existentes a DB para conservar el comportamiento existente.
   - Conserva claves `templates` ya existentes.
   - CONAGUA, SICT, federal base, CENACE y perfil estatal reciben únicamente los formatos que ya estaban presentes en los datos de referencia; no se crea un cross-map CFE/CONAGUA.

4. `compiler.py`
   - Los algoritmos reales siguen siendo código.
   - La elección de qué formato utiliza qué algoritmo pasa a DB.
   - Se añadió una allow-list de compilers ejecutables. El valor de DB nunca se ejecuta como nombre de método arbitrario.
   - Si DB apunta a un compiler inexistente/no permitido, falla de forma explícita.

5. `ProcurementService.compile_artifacts`
   - El catálogo se resuelve exclusivamente con `tender.jurisdiction_code`.
   - Prioridad de formatos: `detected_formats` → formatos de checklist que estén configurados → catálogo DB de la dependencia como modo compatible.
   - Se verifican rutas canónicas antes de compilar.
   - Formatos explícitamente detectados/required con datos faltantes bloquean; no se ocultan errores.
   - Se conserva la generación real de artefactos.

6. Case packs
   - El camino de compilación ya no usa `LegalRule.artifact_required`.
   - Se añadió `get_configured_case_pack`, que consume únicamente el case pack explícitamente configurado en el perfil seleccionado.
   - Los artefactos derivados del corpus jurídico quedan fuera del flujo primario de elaboración.

7. API
   - `/derive-proposition-structure` ahora requiere `jurisdiction_code` y lee la configuración desde DB.

8. Tests
   - Se eliminaron tests que dependían del diccionario hardcodeado.
   - Se agregaron pruebas de normalización segura, allow-list del compiler, ejecución real de XLSX y carga DB-driven mediante un perfil seleccionado.

## Integridad de motores existentes

No se reemplazaron BIM, costos, presupuesto programable, programación/CPM, Monte Carlo ni workspace por stubs. El cambio únicamente mueve la configuración de formato/estructura/selección de compiler a la capa DB y deja los algoritmos ejecutables en código.

## Validación ejecutada

- `python -m compileall` sobre backend, migración y tests: PASS.
- AST parse de archivos modificados: PASS.
- Búsqueda de `FORMAT_TO_CANONICAL` y lectura runtime de `proposition_structure.csv`: sin referencias en código de aplicación.
- Prueba de compiler real: genera XLSX válido (`PK` header).
- `pytest` intentado sobre `test_proposition_bridge_and_formats.py`: BLOQUEADO por dependencia del entorno (`structlog` faltante en `backend/tests/conftest.py`; no se falseó el resultado con stubs).
- Build frontend/E2E y PostgreSQL real no se declaran PASS porque este entorno no tiene las dependencias/servicios necesarios.

## Estado Git local

Commit creado:

`52ee876 feat: make procurement formats DB-driven`

No existe remoto GitHub configurado en el ZIP; por ello no se declara un PR remoto creado.

## Nota de seguridad arquitectónica

La dependencia seleccionada es el contexto raíz. Un expediente CONAGUA no puede resolver el catálogo de formatos de CFE por fallback. La normativa/corpus no puede introducir requisitos de elaboración a través de este tramo. El pre-fallo permanece como la capa donde se puede consultar el histórico/normativa permitido y siempre bajo el contexto de la dependencia seleccionada.
