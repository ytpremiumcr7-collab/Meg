<!--
Copyright © 2026 Cristian Rodriguez
All rights reserved.
Unauthorized copying, modification, distribution, or use is prohibited
without prior written permission.
-->

# Clash Detection — implementación real

## Qué se construyó

1. **`app/engines/bim/clash/`** (nuevo) — motor geométrico puro, sin
   dependencia de BD, para poder probarlo aislado:
   - `aabb_tree.py` — árbol AABB estático (broad phase). Construcción
     única por partición de mediana + consulta de traslape por pila.
   - `mesh_bvh.py` — BVH por-triángulo dentro de cada malla, para que el
     narrow phase no compare todos los triángulos de A contra todos los
     de B a fuerza bruta.
   - `triangle_intersect.py` — test triángulo-triángulo: intersección
     exacta (Möller-Trumbore por arista) + distancia mínima cuando se
     pide tolerancia > 0 (segmento-segmento + punto-triángulo,
     Ericson *Real-Time Collision Detection* 5.1.5/5.1.9).
   - `motor_clash.py` — orquesta broad → narrow phase y arma
     `ResultadoClash` (severidad, distancia, volumen aproximado, puntos
     y triángulos involucrados).
2. **`app/models/bim.py`** — `AnalisisClash` (header de una corrida:
   tolerancia usada, conteos, tiempo) + `ClashResult` (un par en
   conflicto, con ciclo de vida propio `NUEVO/REVISADO/RESUELTO/
   IGNORADO`, a diferencia de `ValidacionPropuesta` que guarda su
   bitácora en un solo JSON — aquí cada resultado se actualiza
   independientemente con el tiempo).
3. **`app/services/clash_service.py`** (nuevo) — traduce `ElementoBIM`
   (SQLAlchemy) ↔ `ElementoParaClash` (dataclass del motor), corre el
   análisis y persiste. Síncrono por ahora, mismo criterio que
   `procesar_ifc()`.
4. **`app/api/v1/bim.py`** — 4 endpoints nuevos: correr análisis, leer
   header, listar resultados (filtrable por severidad/estado), marcar
   estado de un resultado.
5. **Cliente TS**: `client.bim.correrClashDetection` /
   `obtenerAnalisisClash` / `listarResultadosClash` /
   `actualizarEstadoClash`, verificado con `tsc --noEmit` (compila sin
   errores).

## Por qué NO es un port directo de `portar_3D` (hallazgo de la lectura completa)

Se leyó completo `broad_phase.c`/`.h` (534+77 líneas), `dynamic_tree.c`
(2188 líneas), `mesh.c` (2408 líneas) y `mesh_contact.c` (1184 líneas)
antes de escribir nada, siguiendo el mismo criterio que el resto del
proyecto (nunca portar a ciegas). Dos hallazgos cambiaron el plan
original del ROADMAP:

- **`dynamic_tree.c` es un árbol dinámico para cuerpos que se mueven
  cada frame**: inserción incremental con selección de hermano por SAH,
  rotaciones de rebalanceo, proxies con margen inflado para no
  reconstruir en cada movimiento, múltiples árboles por tipo de cuerpo.
  Los elementos BIM son estáticos durante un análisis — no hay nada que
  mover — así que `aabb_tree.py` solo toma lo que aplica: build masivo
  de una sola vez (equivalente conceptual a `b3PartitionMid`/
  `b3BuildTree`) y consulta por pila (`b3DynamicTree_Query`). Todo lo
  incremental (~1200 de las 2188 líneas) quedó fuera a propósito.
- **`mesh_contact.c` nunca colisiona malla-contra-malla**: `shapeA`
  siempre es Mesh/HeightField pero `shapeB` siempre es una primitiva
  convexa (esfera, cápsula, hull) — confirmado en el switch de tipos y
  el assert de entrada. Tiene sentido para un motor de físicas en tiempo
  real (cóncavo-contra-cóncavo casi no se simula, es carísimo), pero es
  exactamente lo que un clash BIM necesita (pared cóncava contra ducto
  cóncavo). No había función de "malla-contra-malla" para portar tal
  cual, así que `triangle_intersect.py` se escribió con algoritmos
  públicos estándar de geometría computacional (Möller-Trumbore,
  Ericson), no específicos de `portar_3D`.

De `mesh.c` sí se reusó el patrón (no el código línea por línea) de que
cada malla tenga su propio BVH de triángulos para acelerar consultas
espaciales — eso es `mesh_bvh.py`.

## Verificación real (no solo `py_compile`)

El álgebra de intersección de triángulos es el tipo de código donde un
bug sutil no se nota leyendo, así que se armaron 3 suites de prueba que
sí se corrieron (no solo se revisaron):

- `test_triangle_intersect.py`: 16 casos, incluido un caso degenerado
  real que se encontró en el camino (un vértice cae exactamente sobre el
  plano del otro triángulo) — la primera versión con fórmula de
  intervalos fallaba ahí; se cambió a Möller-Trumbore por arista, que
  resuelve el caso límite sin ramas especiales. Documentado en los
  comentarios del módulo.
- `test_aabb_tree.py`: incluye 8 corridas con cajas aleatorias
  comparadas contra fuerza bruta O(n²), más casos límite (árbol vacío,
  cajas apiladas idénticas).
- `test_motor_clash.py`: 14 casos end-to-end con elementos tipo caja
  (mallas de 12 triángulos reales, no mocks) — viga que atraviesa una
  losa, elementos sin malla, tolerancia blanda vs dura, volumen
  aproximado.
- Prueba de estrés: dos mallas de ~7,000 triángulos cada una,
  cruzándose de verdad → detecta el clash correcto en 0.7s.

## Volumen aproximado — qué significa exactamente

`volumen_aproximado_m3` es el volumen de la **intersección de los dos
AABB** de los elementos, no un booleano exacto de las mallas (eso
necesitaría una librería de CSG que el proyecto no trae, ej.
`manifold3d`). Es una cota superior simple y honesta: siempre ≥ el
traslape real, sirve para priorizar severidad pero no para cubicar un
volumen de conflicto exacto. Está documentado así en el docstring de
`motor_clash.py` y en el modelo de BD.

## Limitación documentada

Dos triángulos que se tocan justo en un vértice compartido (sin
cruzarse de verdad) pueden reportarse como clash con distancia 0 —
técnicamente correcto (sí se tocan en ese punto) pero puede generar
ruido en geometría donde eso es intencional (ej. una esquina donde tres
muros comparten un vértice). No hay reglas de exclusión por tipo de
elemento todavía (ej. "no marcar Wall-vs-Slab como clash, se espera que
se toquen") — se dejó fuera de este bloque, es el siguiente paso lógico
si el ruido resulta ser un problema en modelos reales.

## Pendiente

- **Reglas de exclusión por par de tipos** (ej. columna-cimentación
  esperado tocarse) — mencionado arriba.
- **Async con Celery**: mismo criterio que IFC — corre síncrono
  mientras el volumen de modelos no lo justifique.
- **Migraciones**: `AnalisisClash`/`ClashResult` ya están en
  `app/models/__init__.py` y en `alembic/env.py` (que además no traía
  `bim.py`/`validador.py` importados — se corrigió de paso). Sigue sin
  existir ninguna migración generada en `alembic/versions/` para NADA
  del proyecto todavía; sigue siendo el pendiente marcado en el
  ROADMAP.
- **Frontend**: no se tocó en este bloque (conectar mini-apps es un
  ítem aparte del ROADMAP). El visor 3D ya tiene todo lo que necesita
  para resaltar clashes (`triangulos_a`/`triangulos_b` vienen listos
  para `BufferGeometry`, igual que `malla_vertices`/`malla_caras`).
