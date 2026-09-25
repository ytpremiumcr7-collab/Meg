# Megalodon Procurement — Mapa de cierre vertical 2026-08-11

## Alcance verificado

Las guías y casos se convierten en ejes de configuración y no en lógica hardcoded:

- Jurisdicción: federal, estatal, municipal y entidad/dependencia.
- Régimen jurídico: LOPSRM/RLOPSRM, LAASSP/RLAASSP cuando el objeto así lo exija, y regímenes locales/especiales cargados por tenant.
- Dependencia/entidad: CONAGUA, SICT, CFE, PEMEX, secretarías federales y perfiles locales configurables.
- Procedimiento: licitación pública, invitación y adjudicación cuando el perfil lo habilita.
- Tipo de contrato: precios unitarios, precio alzado y mixto.
- Criterio de evaluación: binario, puntos/porcentajes y costo-beneficio cuando la jurisdicción lo habilita.
- Tipo de proyecto: obra nueva, infraestructura, ampliación, rehabilitación, mantenimiento y remodelación.
- Escala: pequeña, media, grande, industrial y sin límite artificial.
- Fuente de recursos: federal, estatal, municipal, convenio y mixto, gobernado por el perfil.
- Clase del objeto: obra pública, servicio relacionado y adquisiciones/mixto cuando el régimen lo permita.

## Cadena canónica

TenderPackage
→ TenderRevision
→ JurisdictionProfile
→ LegalSource
→ LegalArticle
→ LegalRule
→ Requirement
→ Evidence
→ BidModel
→ QuantityModel
→ CostModel
→ ScheduleModel
→ Artifact
→ Cross-Consistency
→ QA
→ Approval
→ Signature
→ Submission
→ Receipt
→ Archive

## Casos de aceptación de las guías

### CONAGUA/PTAR

`REFERENCE_CONAGUA_PTAR_2026` conserva los 25 anexos estructurales `AT-01..AT-13` y `AE-01..AE-12` y ahora existe un parser determinista que extrae del caso documental:

- 27 conceptos de catálogo.
- APU del concepto 2.01.006 con materiales, mano de obra, equipo y herramienta.
- indirectos.
- financiamiento y curva de desembolsos.
- utilidad.
- programas de materiales, mano de obra y equipo.
- explosión de insumos.
- 25 secciones de anexos.

La prueba de aceptación reproduce también una contradicción presente en el caso: el monto global de la propuesta no coincide con la suma del catálogo de conceptos. Megalodon la identifica como `BLOCKER`; no la corrige ni la oculta.

### CFE

`CFE_DCPROTER` exige F1..F8 y bloquea la compilación si la convocatoria no aporta las plantillas oficiales de la entidad. El núcleo no inventa esos formatos.

### SICT

`SICT_DT_2026` exige DT-01..DT-13 y sigue el mismo contrato: las plantillas oficiales de la convocatoria deben estar disponibles antes de marcar el expediente como presentable.

### PEMEX y perfiles especiales

Los perfiles de régimen especial no se consideran operables por tener un nombre. Requieren su `LegalSource + LegalArticle + LegalRule + templates` cargados y vigentes.

### Estados y municipios

Se ofrecen perfiles de base para onboarding, pero permanecen `NO OPERABLE` hasta que el tenant cargue la ley, reglamento, lineamientos, fuentes y reglas de esa entidad. Esto evita generar una proposición con una ley incorrecta.

## Contratos

### Precios unitarios

Exige:

- catálogo cuantificado;
- APU;
- costo directo;
- memoria de indirectos;
- financiamiento basado en flujo;
- utilidad trazable;
- programa.

### Precio alzado

Exige:

- actividades principales;
- monto total determinable;
- memoria de integración económica;
- WBS/programa.

### Mixto

Exige explícitamente componentes a precios unitarios y a precio alzado, con sus respectivas estructuras.

## Artículos jurídicos

El contrato actual se enlaza a `LegalRule.article_id` y `LegalRule.source_id`. Para la regla vigente de tipos de contrato se creó la versión basada en el artículo 45 vigente de la LOPSRM. El registro anterior asociado a la numeración histórica queda inactivo para ejecución y se conserva como historia.

## Operación SaaS

El frontend permite seleccionar:

- dependencia/entidad;
- procedimiento;
- tipo de contrato;
- criterio de evaluación;
- tipo de proyecto;
- escala;
- fuente de recursos;
- clase del objeto;
- régimen jurídico;
- paquete documental de entidad.

El backend vuelve a validar las mismas elecciones y además verifica la disponibilidad de reglas, fuentes y artículos para el tenant.

## Integración existente preservada

No se eliminan los motores maduros. El nuevo dominio se conecta por contratos a:

- CostOS/costeo;
- presupuesto/partidas/conceptos/insumos;
- CPM/programación;
- BIM;
- topografía;
- Monte Carlo/riesgo;
- firma;
- documento/storage;
- Tezcatlipoca sólo mediante adapters futuros y sin dependencia estructural.

## Gates que todavía requieren infraestructura de ejecución real

El código está preparado para los gates finales, pero no se marca como producción certificada sin ejecutarlos contra infraestructura real:

- PostgreSQL y Alembic reales.
- Redis/Celery reales.
- Supabase Storage/Auth real.
- E2E HTTP multi-tenant.
- firma PAdES/TSA operativa.
- carga/concurrencia.
- backup/restore y DR.
- observabilidad exportada.
- conectores de portales de presentación donde exista API/flujo autorizado.

Estos gates no se sustituyen por implementaciones ficticias.
