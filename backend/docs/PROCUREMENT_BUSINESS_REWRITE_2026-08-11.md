# Procurement Domain — Business Logic Rewrite / Regression Control — 2026-08-11

## Baseline

Se parte de `Megalodon_PRR_P0P1_Closed_2026-08-11.zip`. El objetivo de este corte no es reemplazar infraestructura existente, sino corregir lógica de negocio del dominio Procurement sin cambiar los motores maduros ni sus contratos legacy.

## Cambios de negocio aplicados

1. Validación server-side de la configuración de licitación antes de persistir `TenderPackage`:
   - jurisdicción activa y resoluble;
   - procedimientos permitidos;
   - tipos de contrato permitidos;
   - criterios de evaluación permitidos;
   - fuentes de recursos y regímenes permitidos cuando el perfil los restringe;
   - tipo/escala/clase del objeto válidos;
   - paquete documental compatible;
   - existencia de RuleSet, fuentes, artículos y bindings artículo↔regla para la jurisdicción efectiva.

2. Readiness operativo por expediente:
   - fuente documental presente;
   - requisitos obligatorios pendientes;
   - configuración jurídica pendiente;
   - estado actual del expediente.
   Esto se expone en `/tenders/{tender_id}/readiness` y el frontend muestra los gates de negocio reales.

3. Los paquetes/casos de referencia no se consideran automáticamente documentos oficiales. Los artefactos derivados de un `CasePack` quedan marcados como `reference_only` cuando no existe una plantilla oficial aportada por la entidad. El submission queda bloqueado ante dichos artefactos.

4. Idempotencia del frontend alineada con la revisión del expediente. Repetir la ejecución del mismo `TenderPackage`/revisión reutiliza la misma operación en vez de generar una llave diferente por timestamp.

## Protección contra regresiones

No se modifican los motores legacy de:
- CostOS
- CPM
- BIM
- Topografía
- Monte Carlo
- Firma
- Fallo / PreFall

Los cambios quedan confinados al servicio/API/frontend de Procurement y a una prueba estática de regresión del dominio.

## Evidencia ejecutada en este entorno

- `python -m compileall backend/app` — PASS.
- Guards estáticos de negocio — PASS.
- No se empaquetan `__pycache__` ni `.pyc`.
- El suite pytest completo no puede ejecutarse en este sandbox por dependencias externas ausentes (`structlog`); no se marca como PASS ficticio.

## Decisión de producción

Este corte mejora la lógica real de negocio y elimina comportamientos engañosos del dominio, pero no certifica infraestructura externa ni E2E productivo sin PostgreSQL/Redis/Celery/Supabase y build frontend limpios. Es una mejora sobre el baseline, no una afirmación falsa de certificación final.
