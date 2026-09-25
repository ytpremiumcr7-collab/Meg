# Megalodon — Auditoría e implementación arquitectónica
Fecha: 2026-09-13

## Alcance ejecutado
- ZIP actual auditado completo por inventario y comparación con versión anterior.
- Backend inspeccionado por módulos de procurement, licitación/pre-fallo, BIM, costos, programación, workers, modelos y migraciones.
- Se verificaron regresiones conocidas entre las versiones 2026-09-08 y 2026-09-11.
- Se implementaron correcciones de frontera de responsabilidad y aislamiento.

## Cambios implementados
1. **Fuente de verdad de requisitos**: `ProcurementRequirementMapper` dejó de consultar `LegalRule`/corpus para crear requisitos. Ahora solo acepta candidatos estructurados provenientes de la evidencia documental del expediente.
2. **Corpus normativo aislado**: el corpus ya no puede fabricar requisitos silenciosamente durante `derive_requirements`.
3. **Dependencia raíz**: `Licitacion.jurisdiction_code` se incorpora y se migra con backfill desde `reglas_participacion` cuando existe.
4. **Evaluación determinista**: `MotorEvaluacion` ya no contiene pesos, mínimos ni penalización de mercado hardcodeados; consume la matriz congelada de la licitación y falla cerrado si está incompleta.
5. **Trazabilidad de evaluación**: las evaluaciones almacenan el contexto de dependencia y snapshot de la matriz.
6. **Fallo**: una proposición no puede seleccionarse para fallo si no tiene evaluación trazable o si la evaluación no pertenece a la dependencia del expediente.
7. **Junta de aclaraciones**: se eliminó el endpoint de creación local desde el router de licitaciones y se eliminó la exigencia de que exista una junta creada en Megalodon para avanzar. Los registros históricos pueden consultarse; la junta ocurre fuera del sistema.
8. **Pre-fallo**: se añadió `jurisdiction_code` al contexto estructurado y se rechazan patrones históricos suministrados para otra dependencia.
9. **Regresión frontend**: se corrigió `/juridico/procedimiento` → `/juridico/determinar-procedimiento` en clientes TS.
10. **Release gate**: además del esquema, verifica que existan registros activos en `jurisdiction_profiles`, `procedure_thresholds` y `catalog_terms`.
11. **CI**: se restauró `.github/workflows/security-hardening.yml`, eliminado accidentalmente en la versión actual.

## BIM / costos / programación
### BIM
El motor IFC es real y no un stub: carga IFC, detecta unidades, extrae QTO y geometría, genera malla y registra errores por elemento. Los tipos IFC por defecto son una decisión técnica del extractor, no una regla jurídica/económica.

### Costos / presupuesto
Se confirmó que `MotorCosteo` calcula partidas, APU, indirectos, utilidad, riesgo, impuesto y total con `Decimal`. **Persisten valores económicos por defecto (15%, 10%, 16%) en `PresupuestoCosteo`, `PresupuestoService` y el modelo DB.** Estos son candidatos obligatorios para la siguiente migración a parámetros económicos DB-driven; no se inventó una sustitución sin conocer el régimen/fuente aplicable.

### Programación
CPM/forward-backward pass y ruta crítica están implementados. Los defaults puramente algorítmicos deben distinguirse de parámetros de negocio antes de migrarlos.

## Hallazgos que no se marcaron como “resueltos” artificialmente
- El mapa de formatos `format_field_map.py` todavía contiene un diccionario estático grande; debe migrarse a configuración versionada por expediente/dependencia antes de declarar cerrada la migración DB → Backend → Frontend.
- `proposition_structure.py` lee `proposition_structure.csv` directamente; debe pasar a repositorio DB/versionado.
- La generación de artefactos en `ProcurementService.compile_artifacts()` contiene códigos de artefacto/compiler explícitos; requiere migración a definiciones de formato versionadas antes de considerar completa la eliminación de hardcode de formatos.
- El histórico específico de motivos de desechamiento/fallos todavía no tiene un repositorio histórico por dependencia suficientemente formalizado; la guardia de contexto ya impide mezclar dependencias cuando se suministra un conjunto histórico.

## Pruebas
- `python -m compileall` sobre backend/app y tests: **PASS**.
- `git diff --check`: **PASS**.
- Pytest completo/dirigido: **BLOQUEADO POR ENTORNO**. El entorno no contiene `structlog` y tampoco `aiosqlite`; el intento de instalar dependencias falló porque el sandbox no tiene resolución de red. No se sustituyeron dependencias con stubs para falsificar el resultado.
- Frontend build: no ejecutable de forma reproducible porque el ZIP no contiene `frontend/app/package-lock.json` ni `node_modules`.
- PostgreSQL/Alembic real: no ejecutado en este sandbox; requiere infraestructura PostgreSQL/PostGIS real.

## Integridad del entregable
El ZIP entregable se reconstruyó a partir del ZIP original actual y se sobreescribieron únicamente los archivos modificados/nuevos. No se recortaron carpetas, corpus, motores, frontend, tests ni archivos no relacionados.
