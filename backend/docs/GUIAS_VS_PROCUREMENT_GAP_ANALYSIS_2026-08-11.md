# Guías 2026 vs Procurement Domain — auditoría de cierre de diseño

Fecha: 2026-08-11

## Conclusión ejecutiva

El dominio Procurement anterior no podía declararse capaz de automatizar cualquier licitación de cualquier entidad. La causa principal era arquitectónica: la selección de jurisdicción era texto libre, no existía un catálogo jurídico global/tenant con herencia de reglas, los artículos no eran entidades enlazadas a las reglas y el frontend no seleccionaba el régimen completo antes de crear el expediente.

Este corte corrige esa parte crítica:

- `JurisdictionProfile` puede ser global o específico del tenant.
- `LegalSource` puede ser global o específico del tenant.
- `LegalArticle` es una entidad persistida.
- `LegalRule.article_id` enlaza regla → artículo → fuente.
- Los perfiles pueden declarar `inherits_from` para reutilizar un régimen base sin duplicar reglas.
- El frontend obtiene un catálogo real y obliga a seleccionar perfil, procedimiento, tipo de contrato y criterio de evaluación.
- El backend rechaza perfiles sin RuleSet/fuentes suficientes para operar.
- La derivación de requisitos usa el perfil y sus herencias y evalúa condiciones declarativas reales.

## Lo que las guías exigen y cómo queda

| Requisito de las guías | Estado del dominio en este corte |
|---|---|
| TenderPackage como aggregate root | Implementado |
| Versionado de convocatoria | Implementado |
| Fuente original + hash | Implementado |
| JurisdictionProfile | Implementado |
| Catálogo global + override tenant | Implementado |
| Selección dependencia/entidad desde frontend | Implementado |
| Selección procedimiento | Implementado |
| Selección tipo de contrato | Implementado |
| Selección criterio de evaluación | Implementado |
| LegalSourceRegistry | Implementado |
| LegalArticle | Implementado |
| Rule → Article → Source | Implementado |
| RuleSet inheritance | Implementado |
| Requirement matrix | Implementado como entidades derivadas |
| EvidenceGraph | Implementado como entidades y enlaces |
| BIM/IFC → cantidades | Integración existente, falta cerrar contrato vertical completo |
| Topografía → cantidades | Integración existente, falta cerrar contrato vertical completo |
| APU/CostOS | Integrado al modelo canónico |
| FASAR/FSR reproducible | Motor existente reutilizable; todavía requiere cerrar extracción de datos empresariales y fuente/versionado completo por expediente |
| Financiamiento por flujo de efectivo | Motor específico debe cerrarse sobre el modelo de bases/anticipo |
| Programa/CPM | Integrado al modelo canónico |
| Curva S/recursos | Parcial: requiere cierre vertical con datos físicos/económicos del expediente |
| Document compiler | Implementado para artefactos base; no cubre todavía todos los anexos posibles de todas las convocantes |
| Cross-consistency | Implementado como motor base |
| Firma | Integrada al servicio existente |
| Submission package | Implementado |
| Portal adapters | No universalizados todavía |
| CONAGUA/SICT | Perfiles heredables preparados; requisitos particulares deben derivarse de bases/anexos del procedimiento, no inventarse globalmente |
| 32 entidades federativas/municipios | Arquitectura preparada, pero no se deben sembrar leyes locales inventadas. Cada perfil requiere su fuente oficial y RuleSet vigente |
| CFE/PEMEX/régimen especial | No se debe declarar READY hasta registrar la fuente jurídica y reglas específicas aplicables al procedimiento |

## Artículos que quedaron amarrados

Se registran bloques y artículos de la guía para LOPSRM: 1–4, 15–24, 27–30, 31–35, 36–40, 41–44, 45–47, 48–51, 52–58, 59–63, 64–69, 74–80, 83+, y artículos específicos 24, 36 y 46. Para RLOPSRM se registran 58–68, 191 y 213.

Los cinco artículos que gobiernan directamente reglas iniciales del flujo tienen binding de `LegalRule.article_id`: modalidad (24), evaluación (36), tipo de contrato (46), FSR (191) y seguros/fianzas (213).

## La regla importante para "cualquier entidad"

La plataforma no debe inventar una ley estatal, municipal o régimen especial para aparentar cobertura. El catálogo permite registrar cualquier dependencia/entidad y cargar su legislación, reglamento, lineamientos, manuales, portal y reglas de evaluación. Un perfil sin fuentes y RuleSet suficientes se marca como no operable y el backend rechaza crear el expediente para producción.

## Casos y formatos contrastados

La guía general exige convocatoria → junta → presentación → evaluación → fallo → contrato y además construcción de propuesta técnica/económica.

El manual exige, entre otros, catálogo, APU, explosión, curva S, programas de recursos, financiamiento, firmas y reconciliación total.

El caso CONAGUA/PTAR agrega AT-1 a AT-13, AE-1 a AE-12, experiencia hidráulica, maquinaria, capacidad financiera, contenido nacional, PACMA y anexos específicos.

Las plantillas XLSX confirman que el modelo de negocio tiene que producir FASAR, APU, catálogo, indirectos, programa de ejecución, curva S, suministro de materiales, programa de mano de obra, equipo y explosión de insumos.

## Dictamen

Este corte cierra correctamente la **selección jurisdiccional y el amarre jurídico estructural**, pero todavía no permite afirmar que Megalodon pueda recibir una convocatoria arbitraria de cualquier municipio/dependencia y generar automáticamente todo el expediente final sin configurar previamente el RuleSet de esa jurisdicción y sus plantillas/anexos.

Eso no es una debilidad del diseño: es una condición necesaria para no fabricar requisitos legales. La siguiente fase de implementación debe completar la biblioteca de jurisdicciones reales y después cerrar verticalmente los pipelines técnicos/económicos/documentales por tipo de procedimiento y contrato.
