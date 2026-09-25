<!--
Copyright © 2026 Cristian Rodriguez
All rights reserved.
Unauthorized copying, modification, distribution, or use is prohibited
without prior written permission.
-->

# Topografía — implementación real (de 0 a nivel BIM)

## Estado anterior

5 carpetas de motor (`levantamientos/`, `coordenadas/`, `volumenes/`,
`triangulacion/`, `geodesia/`) con solo un `__init__.py` vacío cada una.
Modelos `Levantamiento`/`PuntoTopografico` existían pero `Levantamiento`
no tenía `expediente_id` -- quedaba huérfano, sin relación con el resto
del sistema. Sin service, sin router, sin cliente, sin frontend.

## Qué se construyó

**Motores** (sin dependencias nuevas -- `scipy`, `pyproj`, `shapely`,
`geoalchemy2` ya estaban en `pyproject.toml`):

- **`triangulacion/`**: TIN real con `scipy.spatial.Delaunay`. Calcula
  área en planta Y área de superficie real (distintas en terreno
  inclinado), pendiente media, y genera curvas de nivel reales
  ("marching triangles": corta cada triángulo al nivel buscado e
  interpola el punto de cruce en cada arista).
- **`volumenes/`**: corte/terraplén real entre dos superficies TIN
  (método de área promedio por triángulo, el mismo que usa Civil 3D) o
  contra una elevación de referencia plana. No asume que ambas
  superficies comparten los mismos puntos (x,y) -- interpola cada una
  por separado sobre una triangulación de referencia construida con la
  unión de ambos conjuntos de puntos.
- **`geodesia/`**: transformación de coordenadas entre CRS (pyproj,
  ej. GPS WGS84 -> UTM/ITRF2014 del proyecto), distancia/azimut entre
  puntos, y cierre de poligonal (traverse) -- el chequeo de campo
  estándar antes de aceptar un levantamiento.
- **`coordenadas/`**: importador de puntos desde CSV en formato PENZD
  (Punto,Este,Norte,Elevación,Descripción -- el estándar que exportan
  estaciones totales y GPS RTK) o CSV genérico con encabezados.
- **`levantamientos/`**: perfiles longitudinales de terreno a lo largo de
  un eje (muestrea la superficie TIN ya triangulada) -- insumo real para
  diseño de rasante de camino.

**Modelos nuevos**: `SuperficieTIN` (malla + estadísticas, mismo formato
`malla_vertices`/`malla_caras` que `ElementoBIM` para reusar el visor 3D)
y `CalculoVolumen` (con `partida_id` -- mismo puente hacia costeo que ya
tiene BIM). Se corrigió `Levantamiento.expediente_id` que no existía.

**Servicio + router + cliente**: CRUD de levantamientos, importar CSV,
triangular, calcular volumen, curvas de nivel, perfil, geodesia
(transformar coordenadas, cierre de poligonal), y
`generar_partida_movimiento_tierras` (bridge a presupuesto, mismo patrón
que `crear_presupuesto_desde_bim`).

**Frontend**: app nueva "Topografía" -- sube CSV, triangula, visor 3D con
la superficie coloreada por rampa de elevación (verde=bajo, café=alto,
en vez de gris plano o color por tipo como BIM, porque aquí es una sola
superficie continua), calculadora de volumen entre dos superficies o
contra una elevación de referencia, botón para generar presupuesto de
movimiento de tierras.

## Decisiones de diseño

- **CRS por default: EPSG:6362** (México ITRF2014 / UTM zona 14N,
  centro del país). México cruza varias zonas UTM (11N-16N) -- si tu
  proyecto está fuera de la zona 14N, pásale el `crs`/`srid` correcto al
  crear el levantamiento; no se fuerza un solo CRS.
- **Volumen por "área promedio por triángulo"**, no por diferencia de
  grids regulares -- es el método real que usa software de topografía
  profesional, no una aproximación de coarse-grid.
- El listado de superficies viene SIN la malla (`SuperficieResumenOut`) a
  propósito -- la malla completa se pide aparte por superficie
  (`GET /superficies/{id}`), igual que BIM separa listar de incluir_malla.

## Pendiente (a propósito)

- **Poligonales con ajuste real**: `cierre_poligonal` hoy solo reporta el
  error de cierre, no hace compensación tipo Bowditch/Crandall
  (redistribuir el error entre los vértices) -- es el siguiente nivel de
  rigor si se necesita.
- **Exportación a formatos CAD** (DXF de curvas de nivel, por ejemplo) --
  no se pidió todavía, no se construyó.
- **Vista de curvas de nivel en el visor 3D**: el endpoint ya genera las
  curvas reales, pero el frontend todavía no las dibuja superpuestas en
  el visor (quedó como el siguiente paso natural de UI).
