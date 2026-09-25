# Megalodon — Procurement SaaS Production State — 2026-08-11

## Alcance de este corte

Este corte endurece el dominio `Procurement` para que opere como software SaaS real sobre el estado persistido de Megalodon, evitando registros virtuales o artefactos declarativos sin contenido.

## Integraciones cerradas en código

- `TenderPackage` es el aggregate root del dominio de automatización.
- El modelo canónico es validado por Pydantic con campos estructurados y `extra=forbid` en el contrato principal.
- Las fuentes documentales se almacenan en Object Storage con SHA-256 y extracción de texto separada; la ingesta es idempotente por hash.
- Las reglas jurídicas son tenant-owned y deben existir como configuración antes de derivar requisitos; el sistema no inventa requisitos legales.
- `RequirementEngine` deriva requisitos sólo a partir de reglas configuradas y contexto del procedimiento.
- `EvidenceGraph` enlaza evidencia con requisitos y artefactos.
- Los artefactos agregados manualmente sólo se aceptan si existe objeto real en storage y el SHA-256 declarado coincide con su contenido.
- `MotorCosteo` se utiliza mediante el materializador real y proyecta `Presupuesto -> Partida -> Concepto -> Insumo`.
- `MotorCPM` se utiliza mediante el materializador real y proyecta `ProgramaObra -> ActividadPrograma`.
- Al crear un `TenderPackage`, si el usuario no proporciona partidas/programa en el modelo canónico, el servicio intenta reutilizar los presupuestos y programas reales asociados al `ExpedienteObra` del mismo tenant.
- `CrossConsistencyEngine` verifica sumas, APU, cantidades, correspondencia presupuesto/programa y artefactos requeridos.
- Los documentos se compilan desde el modelo canónico; XLSX/PDF/ZIP son reproducibles y hashables.
- La firma PAdES reutiliza `FirmaService` existente y conserva el artefacto original separado del firmado.
- El paquete de submission mantiene manifest y hash; un comprobante de recepción se almacena y se asocia al paquete y a su hash.
- La UI de Convocatoria ya no llama a un endpoint inexistente ni presenta datos ficticios de publicación; gestiona la ingestión de fuentes reales.
- El módulo antiguo de Pre-Fallo sigue separado del nuevo dominio de preparación de propuestas y conserva su función de evaluación preliminar, sin adjudicar.
- El ranking de Pre-Fallo ya no necesita construir una convocatoria vacía para ordenar resultados.
- Se eliminaron defaults de IVA en el cliente y reglas económicas implícitas en el motor antiguo; una regla económica debe provenir de configuración del procedimiento.

## Criterios explícitos de no-fabricación

El dominio no considera `PASS` sólo por crear filas de base de datos. Un artefacto requiere contenido persistido y hash verificable. Una regla jurídica requiere configuración. Una firma requiere ejecución de `FirmaService`. Una presentación sólo se considera documentada cuando existe comprobante almacenado.

## Validaciones ejecutadas en este entorno

- `python -m compileall -q backend/app backend/tests/procurement`: PASS.
- `PYTHONPATH=backend pytest -q backend/tests/procurement --confcutdir=backend/tests/procurement`: PASS (5 tests).
- `npx tsc --noEmit -p tsconfig.json`: PASS.

## Gates que requieren infraestructura real y no deben marcarse PASS aquí

Este entorno de análisis no tiene las dependencias/runtime ni los recursos operativos de la plataforma (por ejemplo PostgreSQL/Redis/Supabase y todos los paquetes de producción), por lo que aún requieren ejecución en CI/staging real:

1. Migración Alembic contra PostgreSQL real.
2. E2E HTTP con autenticación/RBAC y aislamiento multi-tenant.
3. Ejecución de workers/Redis para trabajos pesados de ingestión, BIM, cuantificación, costeo y compilación.
4. Firma PAdES con certificados operativos y TSA real cuando el procedimiento la exija.
5. Integraciones efectivas con portales de convocantes; no se inventan adapters vacíos.
6. Pruebas de carga, recuperación, backup/restore y DR.
7. Golden cases completos con datos reales: CONAGUA/PTAR, obra civil y remodelación.

Estas pruebas son gates de infraestructura/operación y no se sustituyen con mocks.
