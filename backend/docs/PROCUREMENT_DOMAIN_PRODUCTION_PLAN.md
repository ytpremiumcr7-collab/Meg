# Megalodon — Tender Automation Domain: Production Closure Plan

## Objetivo

Construir un dominio de automatización de licitaciones de obra pública orientado a preparación de proposiciones, determinista, source-backed, multi-tenant, versionado y auditable. El archivo final (XLSX/DOCX/PDF) es un artefacto materializado del modelo canónico y no la fuente de verdad.

## Núcleo

`TenderPackage + TenderRevision + RuleSet + RequirementGraph + EvidenceGraph + BidModel + DependencyGraph + Workflow + SubmissionPackage`.

## Componentes existentes reutilizables

- CostOS / `MotorCosteo`: cálculo determinista de costos.
- CPM: programación.
- BIM / cuantificación: fuentes de cantidades.
- Topografía: cantidades derivadas de levantamientos/superficies.
- Monte Carlo: riesgo/escenarios, aislado del cumplimiento jurídico.
- `CompletenessEngine`, `TechnicalEvaluationEngine`, `EconomicEvaluationEngine`: validación/evaluación.
- `PreFallEngine` y módulo de fallo: conservar como evaluación/adjudicación, no como núcleo de preparación.
- Firma PAdES/e.firma: conservar detrás de un gate explícito.

## Cuantificación ProductionQuant

- Rule Engine: fusionar conceptualmente con `DeterministicRuleRuntime`.
- Dempster-Shafer: evidencia incierta/analítica, nunca decisión de compliance obligatoria.
- Monte Carlo: integrar desde el motor existente de riesgo.
- Bayesian / Isolation Forest / SPRT: fuera del core; únicamente analítica posterior cuando exista evidencia y gobierno de modelo.
- Q-Learning / MDP / Game Theory: fuera del core de contratación.
- PBFT: no introducir; integridad mediante hashes, versionado, firmas, transacciones y ledger append-only.

## Tezcatlipoca

Tezcatlipoca no es dependencia del dominio de Procurement. La integración futura se realiza por ports/adapters (`EvidencePort`, `GeoEvidenceProvider`, `SiteContextProvider`). La ausencia de Tezcatlipoca no invalida un expediente de licitación.

## Fases de cierre

### F0 — Baseline
Congelar rama, respaldar DB/storage, inventariar endpoints/modelos/engines y clasificar KEEP/ADAPT/WRAP/REWRITE/DELETE.

### F1 — Identity boundary
Megalodon mantiene auth/tenant/RBAC; Tezcatlipoca permanece desacoplado.

### F2 — Canonical procurement model
Activar TenderPackage/TenderRevision/Requirement/Evidence/Artifact/Dependency/Validation/Submission.

### F3 — Jurisdiction + legal rules
Resolver jurisdicción de forma explícita y cargar RuleSets versionados; eliminar reglas jurídicas hardcoded del core.

### F4 — Tender ingestion
Ingresar convocatoria, bases, anexos, juntas, especificaciones y planos con hash, revisión y procedencia.

### F5 — Requirements + Evidence Graph
Convertir requisitos en objetos verificables y enlazar cada requisito con fuente, evidencia, artefacto y validación.

### F6 — Bidder master data
Unificar identidad, poderes, capacidad, experiencia, personal, equipo y documentos reutilizables.

### F7 — Quantity Engine
Unificar BIM/CAD/topografía/manual/especificaciones mediante `QuantityProvider` y producir cantidades source-backed.

### F8 — Cost Engine
Conectar APU/FSR/equipo/indirectos/financiamiento/utilidad/impuestos mediante `CostModel`.

### F9 — Schedule Engine
Conectar WBS/activities/dependencies/resources/calendars/erogaciones/curva S.

### F10 — Risk/Monte Carlo
Simulación reproducible por `seed + inputs + engine_version` sin alterar decisiones jurídicas.

### F11 — Document Compiler
Materializar artefactos desde modelos canónicos y templates versionados; no sincronizar manualmente archivos de regreso a DB.

### F12 — Cross-consistency
Validar fechas, cantidades, APU, catálogo, presupuesto, programa, recursos, documentos, firmas y totales.

### F13 — Autonomous orchestrator
Orquestar ingest → jurisdiction → requirements → bidder → engineering → quantities → cost → schedule → documents → QA → repair → revalidate → freeze.

### F14 — Human gates
Mantener intervención humana únicamente en interpretación jurídica novedosa, excepciones, estrategia/margen, aprobación, firma y presentación.

### F15 — Submission
Construir manifest, hash, paquete, firma, adapter de portal y recibo. No marcar `SUBMITTED` hasta disponer de evidencia real de recepción.

### F16 — Security / concurrency / workers
Cerrar aislamiento tenant en API/DB/cache/workers/storage/websocket y mover tareas pesadas a workers idempotentes.

### F17 — Observability
OpenTelemetry + métricas + logs estructurados + correlación por tenant/tender/job.

### F18 — CI/CD / DR / scale
Lint, type-check, unit, integration, migrations, security, build, E2E, staging, production, rollback; backups y restore verificados; pruebas de carga y concurrencia.

### F19 — Golden cases
CONAGUA/PTAR, obra civil tradicional y remodelación/obra pequeña, con variantes federal/estatal/municipal/organismo.

### F20 — PRR
No se considera producción industrializada hasta demostrar arquitectura, seguridad, tenant isolation, migraciones, E2E, integridad documental, firma, observabilidad, performance y DR.

## Definition of Done

Una convocatoria real y su conjunto documental deben poder convertirse en un expediente/proposición versionado, reproducible, trazable, validado y materializado, con intervención humana limitada a gates de responsabilidad. Ningún estado `SUBMITTED` se permite sin recibo real y hash del paquete presentado.
