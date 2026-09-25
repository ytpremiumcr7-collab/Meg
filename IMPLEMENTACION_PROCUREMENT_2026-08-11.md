# Implementación — Tender Automation Domain — 2026-08-11

## Cambios realizados

Se añadió un dominio de automatización de licitaciones alrededor de un modelo canónico `TenderPackage` y sus revisiones. El dominio incluye persistencia para requisitos, evidencias, artefactos, dependencias, validaciones, aprobaciones y paquetes de presentación.

Se incorporaron:

- `app/models/procurement.py`
- `app/engines/procurement/rules.py`
- `app/engines/procurement/jurisdiction.py`
- `app/engines/procurement/consistency.py`
- `app/engines/procurement/orchestrator.py`
- `app/engines/procurement/compiler.py`
- `app/schemas/procurement/schemas.py`
- `app/services/procurement/service.py`
- `app/api/v1/procurement.py`
- `alembic/versions/20260811_procurement_domain.py`
- `tests/unit/test_procurement_domain_core.py`
- `docs/PROCUREMENT_DOMAIN_PRODUCTION_PLAN.md`

También se cableó el router `/api/v1/procurement` y se registraron los modelos en `app.models`.

## Capacidad funcional incorporada

1. Creación multi-tenant de `TenderPackage` asociado a `ExpedienteObra`.
2. Versionado explícito mediante `TenderRevision`.
3. Ingesta de fuentes documentales reales hacia Supabase Storage con SHA-256 y creación de evidencia `SOURCE_DOCUMENT`.
4. Requisitos estructurados y versionables.
5. Grafo de evidencia mediante `TenderEvidenceLink`.
6. Resolución determinista de jurisdicción; no hay inferencia silenciosa.
7. Runtime de reglas declarativas deterministas con política fail-closed.
8. Consistencia cruzada entre presupuesto, catálogo, programa, carta, cantidades y documentos.
9. Integración directa con `MotorCosteo` para el modelo económico canónico.
10. Orquestador de ciclo de preparación/QA.
11. Compilación real de catálogo económico XLSX y reporte PDF.
12. Persistencia de artefactos con hash y revisionado.
13. Manifest de presentación con hash del modelo y artefactos.
14. Gates explícitos antes de congelar y preparar el paquete final.

## Política de integración

- CostOS, CPM, BIM, Topografía, Monte Carlo, firma y fallo existentes no fueron eliminados.
- El nuevo dominio se añade como capa orquestadora y canónica para sustituir progresivamente las piezas antiguas.
- Tezcatlipoca no se convierte en dependencia del Procurement Domain.
- El paquete ProductionQuant no se copia íntegramente al core; el Rule Engine se incorpora conceptualmente, Monte Carlo se mantiene como riesgo, y los motores adaptativos/consenso quedan fuera del núcleo.

## Verificación realizada en este entorno

- `py_compile` de los archivos nuevos y modificados: PASS.
- Pruebas puras del dominio: PASS.
- Rule runtime determinista: PASS.
- Jurisdiction resolver sin adivinanzas: PASS.
- Consistency engine: PASS.
- Generación XLSX/PDF real: PASS.
- Escaneo de stubs/placeholders en los nuevos archivos de producción: sin hallazgos.

## Verificación que NO pudo ejecutarse aquí

El sandbox de esta ejecución no contiene `asyncpg`, `aiosqlite` ni `structlog` necesarios para importar y levantar la aplicación FastAPI completa. Tampoco hay una instancia PostgreSQL/Redis/Supabase real conectada. Por tanto no se declara aquí `production PASS`, migración ejecutada, E2E PASS, carga PASS ni DR PASS.

La implementación queda lista para ejecutarse en el entorno de integración real, donde deben correr obligatoriamente las migraciones, pruebas contra PostgreSQL/Redis/Supabase, E2E, aislamiento multi-tenant, generación/descarga de artefactos, firma y los gates de producción descritos en `docs/PROCUREMENT_DOMAIN_PRODUCTION_PLAN.md`.
