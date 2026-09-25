<!--
Copyright © 2026 Cristian Rodriguez
All rights reserved.
Unauthorized copying, modification, distribution, or use is prohibited
without prior written permission.
-->

# Motor BIM/IFC — implementación real

## Qué se construyó

1. **`app/models/bim.py`** (nuevo) — `ModeloBIM` + `ElementoBIM`, con el
   puente `ElementoBIM.partida_id` hacia presupuestos. Inspirado en el
   schema de Kimi, adaptado a SQLAlchemy 2.0.
2. **`app/engines/bim/motor_bim.py`** (reescrito) — cuantificación real
   con `ifcopenshell`:
   - Cantidades: primero el Quantity Set del IFC (`Qto_*`, tiene
     significado de dominio), con respaldo calculado desde la geometría
     real cuando el IFC no trae Qto. Cada cantidad queda marcada con su
     `fuente` (`QTO_IFC` / `GEOMETRIA_CALCULADA` / `NO_DISPONIBLE`) para
     que costeo sepa qué tan confiable es.
   - Corrige el factor de unidades del IFC (muchos exportadores, sobre
     todo Revit, usan milímetros — sin corregir esto los volúmenes salen
     ~1,000,000,000x mal).
   - Extrae la malla triangulada (vértices/caras) de cada elemento, en
     metros y coordenadas de mundo, lista para `THREE.BufferGeometry`.
3. **`app/services/bim_service.py`** (reescrito) — ahora sí persiste
   `ModeloBIM`/`ElementoBIM` en BD (antes se perdía todo), agrupa
   elementos por tipo para generar partidas de presupuesto, y enlaza cada
   elemento a su partida real.
4. **`app/api/v1/bim.py`** (reescrito) — endpoints reales: subir+procesar
   IFC, listar elementos (con o sin malla), mapear a partidas, generar
   presupuesto desde BIM.
5. **Cliente TS**: namespace `bim` completo.

## Bugs reales que tenía la versión anterior (nunca funcionaba)

- Buscaba las cantidades por la llave exacta `"Volume"`/`"Area"`/`"Length"`,
  que casi ningún exportador IFC usa (lo normal es `NetVolume`,
  `NetSideArea`, etc.) — nunca encontraba nada.
- Usaba `ifcopenshell.util.element.get_psets(...)` sin el import
  explícito (`import ifcopenshell.util.element`) — los submódulos de
  ifcopenshell no se auto-importan, esto tronaba con `AttributeError`.
- No calculaba nada desde geometría real — solo dependía de Qtos, que
  muchos archivos IFC simplemente no traen.
- No corregía la unidad de longitud del IFC.
- `procesar_ifc()` no guardaba nada en BD.
- El endpoint de subida encolaba una tarea de Celery sin mandarle los
  bytes del archivo, y el worker tenía un TODO sin implementar.

## Cómo renderizar en el frontend (weblinuxmegalodon)

El backend nunca dibuja píxeles — prepara la malla, el navegador la
renderiza con Three.js/WebGL. Ejemplo mínimo con React Three Fiber:

```tsx
const elementos = await client.bim.listarElementos(expedienteId, modeloId, {
  incluirMalla: true,
});

function ElementoMesh({ elemento }: { elemento: ElementoBIM }) {
  if (!elemento.malla_vertices || !elemento.malla_caras) return null;
  return (
    <mesh>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={elemento.malla_vertices.length / 3}
          array={new Float32Array(elemento.malla_vertices)}
          itemSize={3}
        />
        <bufferAttribute
          attach="index"
          array={new Uint32Array(elemento.malla_caras)}
          count={elemento.malla_caras.length}
          itemSize={1}
        />
      </bufferGeometry>
      <meshStandardMaterial color="#8899aa" />
    </mesh>
  );
}
```

## Pendiente (a propósito, no se improvisó)

- **Storage real**: `ModeloBIM.ruta_archivo` hoy solo guarda el nombre del
  archivo. Falta subir el IFC a Supabase Storage/S3 y procesar desde ahí.
  Mientras no exista, el procesamiento es síncrono en el request.
- **Async con Celery**: la plomería ya existe en el repo, pero necesita la
  pieza de storage de arriba para poder reencolar el trabajo pesado en
  archivos IFC grandes.
- **Clash detection real**: portar `broad_phase`/`dynamic_tree` de
  `portar_3D` para detectar colisiones entre elementos, cuando el pipeline
  básico ya esté probado con modelos reales (ver AUDITORIA_KIMI_Y_3D.md).
- **Migraciones**: `ModeloBIM`/`ElementoBIM` ya están en
  `app/models/__init__.py`, listos para que `alembic revision
  --autogenerate` los detecte cuando haya una BD real conectada.

## Actualización: nivel, bounding box y visor 2D/3D mejorado

**Backend** (`motor_bim.py`, `models/bim.py`, `bim_service.py`, router,
cliente):
- Cada elemento ahora trae `nivel` (nombre del `IfcBuildingStorey` que lo
  contiene, vía `ifcopenshell.util.element.get_container`) y `bbox`
  (`[minX,minY,minZ,maxX,maxY,maxZ]` en metros, calculado de la malla).
- `ModeloBIM.niveles`: lista de nombres de nivel ordenados de abajo hacia
  arriba (por `Elevation`, no alfabético) -- lista para armar un selector
  de piso sin tener que traer todos los elementos primero.
- `GET /elementos` acepta `?nivel=` para filtrar server-side también.

**Frontend** (`bim-calculator`, modo "Modelo IFC"):
- **Selector de nivel**: filtra el visor 3D y el resumen por tipo a un
  piso a la vez (filtrado en cliente sobre lo ya descargado, para no
  re-bajar la malla cada vez que cambias de piso).
- **Color por tipo de elemento**: antes todo era gris plano; ahora muros,
  losas, columnas, vigas, puertas, ventanas, etc. tienen su propio color.
- **Selección de elemento**: clic en cualquier pieza del modelo 3D
  resalta esa pieza y muestra un panel con nombre, tipo, nivel, volumen,
  área y de dónde salió cada dato.
- **Vista 2D (planta)**: toggle que cambia la cámara a ortográfica
  top-down sobre la MISMA malla 3D (no es un plano arquitectónico
  dibujado con achurados/cotas -- se avisa explícitamente en la UI para
  no sobre-vender qué tan "2D profesional" es esto todavía).
- **Alambre (wireframe)** y **auto-encuadre de cámara** (`<Bounds fit
  clip observe>` de drei, en vez de una posición de cámara fija que
  quedaba mal según el tamaño real del modelo).
