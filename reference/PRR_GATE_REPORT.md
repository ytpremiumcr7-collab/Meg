# PRR Gate — Megalodon v7 — Expediente federal de referencia

## Alcance

Prueba adversarial del flujo principal de automatización de licitación:

Expediente → Planeación → Topografía/BIM → Costos → Presupuesto → Investigación de mercado → Selector jurídico → Requisitos → Calendario → Bases/Convocatoria → Validadores → Consistency → paquete documental.

No se usaron README ni documentación histórica como fuente de verdad. La evidencia primaria del comportamiento proviene del código actual del ZIP. La normativa se contrastó contra fuentes oficiales vigentes.

## Expediente de referencia

Procedimiento federal real tomado del aviso SIDOF/DOF:

- Procedimiento: LO-48-E00-048E00994-N-3-2026
- Entidad: Instituto Nacional de Bellas Artes y Literatura
- Tipo: Licitación Pública Nacional
- Publicación: 2026-03-03
- Visita al sitio: 2026-03-05 12:00
- Junta de aclaraciones: 2026-03-06 13:00
- Apertura de proposiciones: 2026-03-13 17:00
- Fallo: 2026-03-19 17:00
- Objeto: Trabajos de conservación y mantenimiento de los muros colindantes del atrio del templo y del lucernario, así como mantenimiento a módulos sanitarios en el Museo Laboratorio Arte Alameda.
- Fuente primaria: https://sidof.segob.gob.mx/notas/docFuente/5781605

El contenedor de ejecución no tiene salida de red/DNS, por lo que no fue posible descargar el PDF binario desde SIDOF/Compras MX. Para no inventar ni sustituir la fuente, se preservó en `INBAL_N3_2026_OFICIAL_extract.txt` el contenido oficial disponible en el resultado de SIDOF. El expediente operacional es sintético y está marcado como tal.

## Casos

`expediente_inbal_n3_2026_CONTROL.json` contiene un caso estructuralmente realista consistente.

`expediente_inbal_n3_2026_INCONSISTENTE.json` contiene inconsistencias controladas para verificar que un futuro motor de consistencia las detecte.

## Evidencia de runtime

El runtime FastAPI completo no pudo arrancarse en el contenedor porque el entorno no tiene instaladas varias dependencias que sí están declaradas por el proyecto y tampoco hay Docker disponible. `pytest` falla al importar configuración por variables obligatorias ausentes (`DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `SECRET_KEY`). Además, el entorno no tiene `asyncpg`, `structlog`, `redis`, `celery` y otras dependencias del backend.

Para no confundir un bloqueo ambiental con comportamiento del producto, se ejecutaron directamente los cuerpos actuales de las funciones del router `licitaciones_obra.py` mediante un harness AST. Eso sí ejecuta el código fuente actual de las funciones, eliminando sólo decoradores/dependencies de FastAPI y sustituyendo UUID/dependencias por stubs mínimos.

## Resultado del replay

Las ocho funciones del flujo principal analizado (`crear_planeacion`, `obtener_planeacion`, `publicar_convocatoria`, `obtener_convocatoria`, `registrar_proposicion`, `listar_proposiciones`, `evaluar_proposiciones`, `emitir_fallo`) no usan `db` ni `current_user` para producir el resultado.

Hechos observados directamente:

- `backend/app/api/v1/licitaciones_obra.py:27-43`: `crear_planeacion` devuelve siempre `plan-000...` y declara fases como completadas sin persistirlas.
- `:45-61`: `obtener_planeacion` devuelve `$5,000,000`, 180 días, fecha `2026-08-01` y folio fijo `DT-2026-001`.
- `:67-89`: `publicar_convocatoria` devuelve fechas `2026-07-20`/`2026-08-10`, plazo fijo y base legal concatenada de LOPSRM/LAASSP; no publica nada.
- `:91-120`: `obtener_convocatoria` devuelve nuevamente `$5,000,000`, 180 días, requisitos y garantías prefabricadas.
- `:126-145`: `registrar_proposicion` crea un UUID fijo y una fecha fija.
- `:147-184`: `listar_proposiciones` devuelve tres empresas ficticias y montos/fechas fijas.
- `:190-227`: `evaluar_proposiciones` evalúa IDs fijos y no consulta propuestas almacenadas.
- `:606-626`: `publicar_compranet` reporta `PUBLICADA_COMPRANET` y devuelve una URL ficticia sin una llamada a la plataforma.
- `:632-659`: `resumen_ciclo_completo` vuelve a reportar un ciclo completo hardcodeado, incluyendo contrato, ejecución y finiquito.

Contradicciones contra el expediente de prueba:

- Monto esperado: 12,850,000; la ruta devuelve 5,000,000.
- Plazo esperado: 60 días; la ruta devuelve 180.
- Publicación oficial: 2026-03-03; la ruta devuelve 2026-07-20.
- Apertura oficial: 2026-03-13 17:00; la ruta devuelve 2026-08-10 10:00.
- Planeación esperada: presupuesto 12,850,000 / 60 días; ruta: 5,000,000 / 180 días.

Conclusión: `licitaciones_obra.py` no es una capa de cableado que falte conectar; su implementación actual es un fixture/vertical demostrativa. Es P0 y requiere reescritura interna conservando la responsabilidad de cada endpoint.

## Prueba de consistencia independiente

El caso CONTROL pasa las comprobaciones mínimas de monto/plazo/mercado.

El caso INCONSISTENTE produce tres hallazgos P0:

1. presupuesto total 12,851,200 vs expediente 9,900,000.
2. plazo de planeación 175 vs expediente 120 días.
3. referencia de mercado 12,850,000 vs expediente 9,900,000.

Esto demuestra que el dataset puede actuar como oráculo de una futura `CrossConsistencyEngine`, pero el backend actual no tiene ese motor: no aparece implementación backend de `CrossConsistency`, `DocumentCompiler`, `Outbox` ni `Idempotency` en las referencias analizadas.

## Clasificación de los 15 huecos del PRR anterior

### Requieren código nuevo o reescritura: 10

1. PlaneacionService y su integración persistente.
2. InvestigacionMercadoService con evidencia/versionado.
3. ProcurementCalendarEngine.
4. DocumentCompiler.
5. CrossConsistencyEngine backend.
6. EvidenceGraph/provenance.
7. publicación externa verificable.
8. reescritura de `licitaciones_obra.py` para persistencia real.
9. Outbox.
10. Idempotency.

### Código existente pero roto o semánticamente insuficiente: 4

11. Selector jurídico: excepción legal reducida indebidamente a una justificación de 50 caracteres.
12. Validadores que aceptan afirmaciones/flags como si fueran evidencia primaria.
13. `LicitacionService`: transiciones referencian estados no declarados y usa `created_by`/`updated_by` frente al modelo de auditoría `creado_por_id`/`actualizado_por_id`.
14. BaseService permite `get/update/delete` sin tenant.

### Dato/configuración jurídica pendiente: 1

15. Umbrales/reglas jurídicas críticas no están todos en estado VERIFIED con fuente primaria, vigencia y jurisdicción.

No son 15 simples tareas de cableado. El replay demuestra que el componente principal de `licitaciones_obra.py` requiere reescritura; los motores de topografía/BIM/costos son mayormente reales y el problema ahí es cerrar su orquestación hacia el expediente/licto, no inventar nuevamente esos motores.

## Flujo que debe quedar operativo

Expediente → Planeación → Estudios técnicos → Topografía/BIM → Cantidades → Costos/APU → Presupuesto congelado → Investigación de mercado → Selector jurídico → Requisitos → Calendario jurídico → Convocatoria/Bases estructuradas → Compilación documental → Validación técnica/económica/jurídica → CrossConsistency → Evidence/Provenance → Human Review → paquete publicable.

## Normativa oficial usada para contraste

- LOPSRM vigente, Cámara de Diputados, última reforma 14-nov-2025: https://www.diputados.gob.mx/LeyesBiblio/pdf/LOPSRM.pdf
- Art. 24 Bis / investigación de mercado: misma ley vigente.
- Arts. 27, 28, 30 y 31: procedimientos, proposiciones digitales, plataforma y contenido mínimo de convocatoria: misma ley vigente.
- Plataforma Compras MX / transición de CompraNet: https://comprasmx.buengobierno.gob.mx/mejoras

## Veredicto del gate

**NO-GO.**

El bloqueador principal no es falta de más features. Es que el núcleo de automatización aún no compila un expediente real en un paquete licitatorio persistente, verificable y cruzado contra evidencia.

La próxima ejecución debe hacerse en un entorno que levante Postgres/Redis/Celery y todas las dependencias declaradas. El harness AST no sustituye ese gate; sirve para demostrar que la ruta fixture actual falla incluso antes de llegar a infraestructura.
