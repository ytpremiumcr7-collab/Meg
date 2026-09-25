<!--
Copyright © 2026 Cristian Rodriguez
All rights reserved.
Unauthorized copying, modification, distribution, or use is prohibited
without prior written permission.
-->

# Auditoría: app_quitar_a_kimi + portar_3D

## Veredicto sobre `app_quitar_a_kimi` (Node/TS/Drizzle/tRPC)

**No se usa como runtime.** Confirmado por auditoría: el auth completo está
cableado a OAuth de la plataforma Kimi (`api/kimi/auth.ts`, `unionId` como
llave del usuario en `db/schema.ts`) — el mismo patrón que ya tuviste que
quitar en Motor Nutricional. Migrarlo tal cual implicaría repetir ese
trabajo por segunda vez.

**Sí vale la pena portar como IDEA/CONTRATO al backend Python:**

1. **`db/schema.ts` (33 tablas)** — el modelado de dominio es más completo
   que el de `programacion4` en varios puntos concretos que faltan en
   Python:
   - `constantesLegales` como **tabla editable**, no constantes hardcodeadas
     en código (permite actualizar umbrales de ley sin re-deploy)
   - `contratistas`, `catalogoInsumos`, `garantias` — no existen en Python
   - `modelosBim` + `elementosBim` (con `partidaId` como FK directa) — es
     exactamente el puente BIM→presupuesto que falta en Python
   - `reglasValidacion` + `resultadosValidacion` — patrón de **reglas
     configurables en BD**, no hardcodeadas (mejor que el `motor_validador.py`
     actual)
   - `simulacionesMonteCarlo` + `parametrosRiesgo` persistidos (Python los
     calcula pero no los guarda)
   - `vinculosPartidaActividad` — el enlace presupuesto↔programación que
     viste en tu `v3_3.py` (el archivo con errores de sintaxis)

2. **`costos-router.ts`** — ya tiene `compararPresupuestos` (versionado/
   comparación) y jerarquía de partidas (NORMAL/SUBPARTIDA/RESUMEN). El
   orden de cálculo de indirecto/utilidad/riesgo/IVA es el mismo que ya
   dejé corregido en Python — sin bug de doble indirecto.

3. **`validadores-router.ts`** — patrón reglas-en-BD + evaluadores
   (`evaluarSeguridadSocial`, `evaluarFSR`, `evaluarMaquinaria`,
   `evaluarSobrecostos`, `evaluarCompleto`) vale la pena portar la
   estructura, no el código literal.

**Importante:** `bim-router.ts` NO tiene geometría real — `cuantificarModelo`
solo agrega datos que ya vienen calculados (asume que algo más ya extrajo
volumen/área del IFC). La pieza de cómputo real tiene que salir de
`portar_3D` o del `MotorPreciosBIM` de tu `v3_1.py`.

## Veredicto sobre `portar_3D`

Es un **fork de Box2D v3** (el motor de físicas open source de Erin Catto)
extendido hacia 3D — no es un motor BIM/IFC. Evidencia: 93 archivos fuente
en C, mismos nombres de joints que Box2D (`revolute_joint.c`,
`weld_joint.c`, `wheel_joint.c`, `motor_joint.c`), prefijo `b3` (antes `b2`
en Box2D), estructura de docs idéntica a la de Box2D (`character.md`,
`compound.md`, `distance.svg`, `manifolds.svg`).

**Lo que SÍ sirve para BIM:**
- `broad_phase.c` + `dynamic_tree.c` (AABB tree) → detección de colisiones
  entre elementos, útil para *clash detection* real entre objetos BIM
- `mesh.c` + `mesh_contact.c` → colisión contra mallas triangulares
  arbitrarias (un elemento BIM exportado a triángulos podría usar esto)
- `compound.c`, `capsule.c`, `sphere.c` → primitivas geométricas y cálculo
  de centroide/volumen de formas convexas simples

**Lo que NO sirve / es peso muerto para este caso de uso:**
- Todo el solver de físicas: `contact_solver.c`, `constraint_graph.c`,
  `island.c`, joints, `scheduler.c` (paralelismo para simulación) — esto es
  para cuerpos rígidos en movimiento (videojuegos), no para cuantificar un
  edificio estático.

**Falta completamente: parsing de IFC.** Esta librería no lee archivos
`.ifc` — solo trabaja con primitivas geométricas ya cargadas en memoria
(esferas, cápsulas, mallas). Para BIM real todavía se necesita una capa de
ingesta IFC (algo tipo IfcOpenShell) que convierta el archivo IFC en mallas
antes de que `portar_3D` pueda hacer algo con ellas.

**Riesgo operativo a considerar:** es C puro con CMake — compilarlo va a
funcionar en Railway (Linux normal), pero si alguna vez necesitas
compilarlo o probarlo localmente desde Termux/proot, la cadena de build de
CMake + toolchain de C en Android tiene sus propias fricciones (aparte,
`extern/sokol` son headers de renderizado que probablemente no aplican para
un backend headless — es para los samples visuales de Box2D, no para el
cómputo).

## Sobre la especificación que compartiste

La leí completa. Es coherente con todo lo que hemos encontrado y con las
correcciones ya hechas (un solo backend, engine centralizado, dominio por
carpetas). La sigo como guía para lo que viene. Dos puntos donde la
especificación asume algo que la auditoría no confirma:

- Sección 5.10/7: espera que `portar_3D` cubra "parsing nativo" de BIM —
  como se documentó arriba, eso no está ahí. Hay que decidir: escribir un
  parser IFC en Python (más simple, más lento) o buscar/portar una librería
  de parsing IFC en C para que viva junto a `portar_3D` (más rápido, más
  trabajo).
- La especificación no menciona qué pasa con `megalodon_production`
  (e.firma) — dado que ya está terminado como servicio aparte, sugiero
  tratarlo como el mismo patrón que `portar_3D`: integrarlo como módulo
  interno (`app/modules/firma/` o `app/integrations/efirma.py`) en vez de
  reescribir `ServicioFirma` desde cero en el motor delgado actual.
