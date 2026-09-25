# Megalodon Procurement v5 — mapa de alcance, entorno y ejecución

Fecha de corte: 11 de agosto de 2026.

## 1. Fuentes revisadas

La especificación funcional de esta fase se derivó de todos los documentos de la carpeta de guías:

- Guia_Completa_Licitaciones_Obra_Publica_Mexico_2026.md
- Guia_Exhaustiva_Megalodon_Automatizacion_Licitaciones_Publicas_Mexico_2026.docx
- Manual_Exhaustivo_Elaboracion_Licitaciones_Publicas_Obra_2026.docx
- Propuesta_Licitacion_LOPSRM_2026.xlsx
- Plantilla_APU_FASAR_Licitacion_Obra_Publica_2026.xlsx
- Caso_Practico_CONAGUA_PTAR_Completo_2026.md
- Ingeniería de Sistemas Cuantitativos...
- Megalodon_ProductionQuant_Industrialized_v1.zip

La guía general cubre LOPSRM/RLOPSRM, LAASSP/RLAASSP, Compras MX, etapas del procedimiento, documentación legal/administrativa, propuesta técnica/económica, APU/FASAR, indirectos, financiamiento, utilidad, programas, evaluación, garantías, particularidades CFE/SICT/CONAGUA/PEMEX/secretarías, contratos por precios unitarios/precio alzado/mixto, remodelación y ruta de estados/municipios.

El manual exige una regla adicional: antes de producir una proposición se debe clasificar convocante, objeto jurídico, fuente de recursos, ley, modalidad, tipo de contrato, anexos y régimen especial; una inferencia nunca puede convertirse en hecho sin aprobación/evidencia.

## 2. Arquitectura objetivo de esta fase

```text
IDENTITY / TENANT
        |
        v
JURISDICTION PROFILE
        |
        +--> LegalSource -> LegalArticle -> LegalRule
        |
        +--> Procedure / Contract / Evaluation Policy
        |
        +--> CasePack / Entity Template Pack
        |
        v
TenderPackage
  |
  +--> TenderRevision
  +--> SourceDocument / Evidence
  +--> RequirementGraph
  +--> BidderModel
  +--> TechnicalModel
  +--> QuantityModel
  +--> CostModel
  +--> ScheduleModel
  +--> RiskModel
  +--> ArtifactGraph
  +--> QA / Cross-Consistency
  +--> Approval
  +--> Signature
  +--> Submission
```

## 3. Entorno real que se conserva

Se mantienen como módulos existentes y proveedores especializados:

- `MotorCosteo` / CostOS
- `MotorCPM`
- BIM/IFC y cuantificación
- Topografía
- Presupuesto / Partida / Concepto / Insumo
- Firma/PAdES
- Supabase Storage
- PostgreSQL/PostGIS
- Redis/Celery
- OpenTelemetry
- Tezcatlipoca únicamente a través de ports/adapters, nunca como dependencia del Procurement Core

No se reemplazan de forma destructiva.

## 4. Variabilidad de negocio que ahora se hace explícita

### Jurisdicción

- `MX-FED-OBRA`
- `MX-FED-ADQ`
- `MX-FED-SERV`
- `MX-FED-CONAGUA-OBRA`
- `MX-FED-SICT-OBRA`
- `MX-FED-CFE-OBRA`
- `MX-FED-PEMEX-OBRA`
- `MX-FED-SECRETARIAS-OBRA`
- perfil estatal configurable
- perfil municipal configurable

Los perfiles estatales/municipales no se marcan como listos mientras no exista su RuleSet/fuente oficial. No se inventa legislación local.

### Procedimiento

- Licitación pública
- Invitación
- Adjudicación

La lista efectiva viene del perfil jurídico y puede ser ampliada mediante un perfil tenant-owned gobernado por administración.

### Tipo de contrato

- Precios unitarios
- Precio alzado
- Mixto

El dominio bloquea un contrato mixto sin identificación de componentes unit-price/lump-sum y bloquea precios unitarios sin APU/estructura económica trazable.

### Criterio de evaluación

- Binario
- Puntos y porcentajes
- Costo-beneficio cuando el régimen lo habilite

Nunca se fija un 70/30 u otro porcentaje global como regla universal.

### Tipo de proyecto

- construcción nueva
- remodelación
- rehabilitación
- mantenimiento/conservación
- ampliación
- infraestructura
- servicios relacionados

Para remodelación se exige evidencia de condiciones existentes y, si se declara una adquisición separada, fundamento de clasificación jurídica antes de cerrar el expediente.

### Escala

El sistema no fija un tope artificial. La clasificación pequeña/media/grande/industrial es metadato operativo y no un límite del motor.

## 5. Caso CONAGUA/PTAR

El `REFERENCE_CONAGUA_PTAR_2026` reproduce la estructura de aceptación de la guía:

- AT-01 ... AT-13
- AE-01 ... AE-12

Los requisitos se generan por `LegalRule` condicionado al `case_pack_code`. No se convierten en obligaciones universales de CONAGUA; sólo se activan en el paquete explícito o cuando la convocatoria real contenga los marcadores/requisitos correspondientes.

El compilador genera artefactos deterministas cuando existe información canónica suficiente. Si falta un dato requerido, se bloquea; no se escribe texto de relleno.

## 6. CFE / SICT

La guía aporta particularidades de CFE (DCPROTER, F1-F8) y SICT (DT-1..DT-13). El sistema conoce esas familias y su selección desde el perfil. Los formatos oficiales externos se marcan como `requires_uploaded_template` cuando corresponde: no se fabrica un formulario oficial inexistente.

## 7. Artículos y fuentes

Las reglas se enlazan estructuralmente:

`LegalRule -> LegalArticle -> LegalSource`

Las fuentes federales se anclan a URLs oficiales de Cámara de Diputados/DOF y Compras MX. En producción no se toma el texto de una URL como verdad silenciosa: se conserva versión, hash y vigencia.

## 8. Prueba vertical que debe cerrar el dominio

```text
convocatoria + anexos + expediente de empresa
          |
          v
ingesta / hash / extracción
          |
          v
jurisdicción + procedimiento + contrato + evaluación
          |
          v
RequirementGraph + EvidenceGraph
          |
          +--> bidder
          +--> BIM/CAD/topografía/manual -> quantities
          |
          v
CostOS / APU / FASAR / indirectos / financing / profit
          |
          v
CPM / WBS / curva S / materiales / MO / equipo
          |
          v
document compiler
          |
          v
cross-consistency + legal/compliance QA
          |
          v
approval -> signature -> submission -> receipt -> archive
```

## 9. Regla de producción

No se marca un perfil, caso o artefacto como listo sólo porque existe el código. Requiere:

- fuente jurídica y versión identificables;
- RuleSet aplicable;
- requisitos trazables;
- evidencia real;
- modelo técnico/económico completo;
- artefactos reproducibles;
- QA sin BLOCKER;
- aprobación correspondiente;
- firma cuando aplica;
- hash de submission y comprobante cuando se presenta.

## 10. Estado de la fase v5

Implementado en código:

- selector frontend de jurisdicción, procedimiento, contrato, evaluación, tipo de proyecto, escala y case pack;
- catálogo jurisdiccional con herencia de reglas;
- perfiles CFE/SICT/CONAGUA/PEMEX/secretarías y perfiles locales no habilitados sin fuente oficial;
- case pack CONAGUA AT/AE;
- estructura CFE F1-F8 y SICT DT-1..DT-13;
- políticas deterministas para unit-price/lump-sum/mixed;
- validación específica para remodelación;
- nuevos campos SaaS persistentes para evaluación/proyecto/escala/case pack;
- artefactos de anexos con bloqueo ante información ausente;
- migración Alembic explícita para estos cambios.

Bloqueos que correctamente siguen fuera de “PASS” hasta probar infraestructura real:

- migración sobre PostgreSQL productivo;
- E2E HTTP contra Redis/Celery/Storage real;
- prueba multi-tenant adversarial;
- firma PAdES/TSA con certificados reales de operación;
- carga/DR/restore;
- conectores reales de cada portal estatal/municipal;
- adquisición y verificación de las fuentes normativas locales no incluidas en la guía.

No son placeholders: son gates de infraestructura y gobernanza que requieren sistemas/fuentes externas reales.


## V6 — clasificación de régimen y recursos
La selección del procedimiento ya no depende sólo de la entidad. El paquete canónico también conserva fuente de recursos, clase de objeto y régimen jurídico. Esto evita asumir que una obra ejecutada por un estado/municipio con recursos federales queda automáticamente bajo un único régimen; el expediente debe aportar el fundamento aplicable. Para remodelaciones con adquisiciones/servicios separados, el flujo puede cambiar a LAASSP/local según el componente y sus fuentes.

La versión vigente consultada de LOPSRM ubica los tipos de contrato en el artículo 45 (última reforma DOF 14-11-2025); cualquier referencia interna al artículo 46 se considera histórica y no se usa para nuevas reglas.
