# Megalodon — P1 Structural Source Extraction / Provenance Audit

## 1. Corrección respecto de V2
La implementación anterior era conservadora pero todavía estaba cerca de scaffolding: extracción por encabezados y líneas enumeradas. Eso no alcanza el estándar de una máquina de ingeniería documental.

Esta revisión sustituye esa limitación por extracción estructural determinista real.

## 2. Principio de producto
Megalodon es mecánico. No usa IA para decidir, inferir o inventar requisitos.

El motor puede:
- leer estructura física/documental;
- localizar texto;
- identificar claves explícitas;
- mapear columnas/campos configurados;
- reconstruir filas de tablas;
- extraer páginas y coordenadas lógicas;
- OCRizar páginas escaneadas;
- detectar relaciones explícitamente declaradas;
- transformar los datos en estructuras de trabajo.

No puede convertir una obligación normativa del corpus en un requisito efectivo de la propuesta.

## 3. Fuentes que pueden originar requisitos efectivos
### Fuente oficial cargada
Convocatoria, anexos, formatos, aclaraciones y modificaciones proporcionados por el cliente/usuario.

Ruta:
`documento -> extracción estructural -> candidate -> confirmación -> TenderRequirement`

### Workspace editable
La ruta manual sigue siendo válida cuando el cliente/usuario está trabajando en el Workspace editable. El requisito queda trazado a la versión del documento del Workspace, su tenant y su revisión. No se exige una fuente normativa para permitir esa edición humana.

### Corpus normativo
Solo referencia normativa, validación, advertencia, fundamento o comparación. No materializa por sí mismo un TenderRequirement.

## 4. Extracción estructural implementada
### PDF
- extracción de texto con referencia de página;
- extracción de tablas con página/tabla/fila/celda;
- detección de páginas sin capa de texto;
- OCR mecánico con `pdf2image` + `pytesseract` para páginas escaneadas;
- registro de que OCR fue utilizado.

### DOCX
- párrafos;
- tablas;
- fila/celda;
- referencia del campo estructural.

### XLSX
- hoja;
- fila;
- coordenada de celda;
- valor de campo.

### Requisitos
Se preserva el identificador oficial cuando existe explícitamente, en lugar de reemplazarlo por un identificador interno. Si no existe, se usa un identificador técnico de extracción y permanece sujeto a revisión.

`mandatory` no se inventa. Solo se obtiene si existe un campo/valor explícito configurado; en caso contrario permanece `null` hasta la decisión del usuario.

## 5. Relaciones documentales
El extractor reconoce de forma determinista:
- `MODIFICA`
- `SUSTITUYE`
- `ACLARA`

Una relación solo queda resuelta automáticamente cuando contiene un identificador explícito del objeto que modifica/sustituye/aclara. Si no existe, queda `REVIEW_REQUIRED`; no se intenta adivinar el destino por similitud semántica.

La relación conserva documento, versión, revisión, página, tabla, fila, celda, campo y texto original.

## 6. Dependencias / flujos
La configuración existente ya distingue perfiles para:
- CONAGUA;
- SICT;
- CFE;
- FEDERAL;
- estatal;
- municipal;
- adquisiciones/servicios federales;
- privada;
- remodelación/construcción privada.

Los perfiles contienen flujos y formatos. La nueva capa agrega contratos estructurales de tabla y relación.

La calibración final de cada formato debe hacerse contra archivos oficiales representativos de cada dependencia. No se deben inventar nombres de columnas o claves oficiales que no aparezcan en la documentación real.

## 7. Call graph de TenderRequirement
Las únicas construcciones productivas detectadas son:
- `ProcurementService.derive_requirements()` — consume candidatos confirmados de fuentes oficiales;
- `ProcurementService.add_requirement()` — consume candidato confirmado o edición explícita del Workspace.

Los motores jurídicos no construyen `TenderRequirement`.

`TenderOrchestrator` puede actualizar el estado de evaluación (`PASS/FAIL/UNKNOWN`) de un requisito existente y generar definiciones de regla para evaluación. Eso es ejecución/validación sobre un requisito ya existente, no creación normativa silenciosa.

## 8. Validación ejecutada
- `compileall`: PASS para extractor, servicio y migración.
- smoke test de extracción de tabla con identificador, descripción, obligatorio y coordenadas: PASS.
- smoke test de relaciones explícitas/no explícitas: PASS.
- comprobación de ausencia de proveedores LLM en el extractor: PASS.
- pytest completo: no arrancó en este entorno porque falta `structlog` al cargar `tests/conftest.py`.

## 9. Qué NO se debe declarar terminado todavía
No es correcto afirmar que CONAGUA/SICT/CFE están ya al 100% de cobertura de todos sus formatos oficiales solo por tener el motor estructural.

Lo que ya existe es el motor real y el contrato de configuración. La siguiente etapa de excelencia es alimentar cada perfil con layouts reales: tablas, encabezados, claves, campos, variantes de formato y reglas de relación observadas en documentos oficiales de cada flujo.
