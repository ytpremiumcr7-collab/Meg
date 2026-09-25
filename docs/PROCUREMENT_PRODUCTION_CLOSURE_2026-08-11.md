# Megalodon — Procurement Production Closure Status — 2026-08-11

## Alcance de este corte

Este corte continúa la reingeniería del dominio de automatización de licitaciones sobre el árbol existente de Megalodon. No elimina de forma destructiva los módulos heredados; introduce contratos y un dominio canónico para sustituirlos progresivamente.

## Implementado y conectado

- `TenderPackage` como raíz del agregado y versionado por `TenderRevision`.
- `Requirement`, `Evidence`, `EvidenceLink`, `Artifact`, `Dependency`, `ValidationRun`, `Approval` y `SubmissionPackage`.
- `JurisdictionProfile`, `LegalSource` y `LegalRule` con resolución desde DB tenant-scoped; no existe lista universal hardcoded para decidir jurisdicción.
- Ingesta documental real: hash SHA-256, almacenamiento Supabase, extracción determinista de PDF/DOCX/XLSX/text/JSON/XML/CSV/MD y persistencia de la evidencia.
- Límite de tamaño configurable para fuentes (`TENDER_SOURCE_MAX_FILE_SIZE_MB`).
- Runtime de reglas deterministas.
- Integración real de `MotorCosteo` con `Presupuesto -> Partida -> Concepto -> Insumo`.
- Integración real de `MotorCPM` con `ProgramaObra -> ActividadPrograma`.
- Consulta de fuentes BIM reales y cálculos topográficos reales, limitados al expediente asociado.
- Materialización del resultado calculado de costos al modelo canónico.
- Compilación real de `AE-02`, `APU`, `PROGRAMA` y `QA-REPORT` sólo cuando existe información fuente suficiente.
- Trazabilidad de artefactos mediante evidencias de cálculo y `TenderDependency`.
- Empaquetado real `SUBMISSION-vN.zip` con `MANIFEST.json`, hashes y verificación del contenido almacenado.
- Invalidación explícita de artefactos y submissions previos al crear una nueva revisión.
- Cálculo de impacto de revisión por rutas cambiadas en el modelo canónico.
- Firma real PAdES a través del `FirmaService` existente, preservando original y firmado, con hash de ambos.
- Submission bloqueado si existen PDFs activos sin firma.
- Registro real de comprobante de presentación externo: archivo, portal, referencia y SHA-256; el sistema sólo marca `SUBMITTED` al registrar evidencia real.
- Aislamiento tenant en las consultas del dominio nuevo.
- Compatibilidad con `CostOS`, CPM, BIM, Topografía y Monte Carlo sin convertir Tezcatlipoca en dependencia del dominio.

## Componentes existentes preservados

Se mantienen en el árbol para migración segura:

- `app/engines/licitacion/*`
- `app/engines/costos/*`
- `app/engines/programacion/*`
- BIM
- Topografía
- Firma
- Monte Carlo
- módulos heredados de licitaciones y Fallo/PreFall
- integración de Tezcatlipoca

No se declaró ninguno de estos módulos "eliminado" hasta disponer de sustituto y pruebas de regresión.

## ProductionQuant

Decisión de integración:

- Rule Engine: absorbible en el runtime determinista de procurement.
- Monte Carlo: conectado como riesgo/escenarios cuando el modelo lo especifica de forma completa.
- Dempster-Shafer: reservado a fusión de evidencia/analytics; no decide compliance jurídico obligatorio.
- Bayesian/Isolation Forest: fuera del camino crítico actual.
- SPRT/Q-Learning/MDP/Game Theory/PBFT: fuera del core de procurement en este corte.

## Tezcatlipoca

Procurement no depende estructuralmente de Tezcatlipoca. La integración futura debe entrar por puertos/adapters de evidencia, geoespacial o contexto de sitio. El dominio de licitaciones puede operar sin arrancar Tezcatlipoca.

## Validación ejecutada en este corte

- `python -m compileall -q backend/app` — PASS.
- `py_compile` de los módulos modificados — PASS.
- Smoke real de `ProcurementArtifactCompiler`: XLSX económico, XLSX APU, XLSX programa, PDF QA y ZIP con `MANIFEST.json` — PASS.
- Escaneo del dominio nuevo por `pass`, `TODO`, `FIXME`, `mock`, `stub`, `placeholder`, `demo`, `scaffold` — sin coincidencias.

## Gates que NO se declaran cerrados sin infraestructura real

No se marca "Production PASS" hasta ejecutar sobre infraestructura de despliegue real:

1. Alembic `upgrade/downgrade` contra PostgreSQL soportado.
2. Pruebas contra Redis real, workers Celery y colas/reintentos/idempotencia.
3. E2E HTTP con autenticación real y almacenamiento Supabase real.
4. Firma PAdES/TSA con certificados de prueba controlados y validación criptográfica completa.
5. Carga/concurrencia y pruebas de grandes expedientes/BIM/PDF.
6. Backup/restore y DR con medición de RPO/RTO.
7. Pruebas adversariales completas de aislamiento multi-tenant en API/DB/cache/worker/storage.
8. CI/CD staging -> production con rollback probado.
9. Prueba vertical de los casos de oro de guías (CONAGUA/PTAR, obra civil y remodelación) con datos completos reales.
10. Conectores de portales gubernamentales concretos: sólo pueden marcar `SUBMITTED` después de una interacción/receipt real; no se inventaron adapters falsos.

## Criterio de cierre final

El dominio se considera industrializado sólo cuando una convocatoria real puede atravesar:

`ingest -> jurisdiction -> requirements -> evidence -> bidder -> engineering -> quantities -> cost -> schedule -> documents -> cross-validation -> approval -> signature -> submission package -> external receipt -> archive`

y cada resultado crítico tiene origen, versión, hash, regla/motor y evidencia de auditoría.
