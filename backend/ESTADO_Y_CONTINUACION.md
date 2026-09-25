<!--
Copyright © 2026 Cristian Rodriguez
All rights reserved.
Unauthorized copying, modification, distribution, or use is prohibited
without prior written permission.
-->

# MEGALODON — Estado y plan de continuación
(generado porque la conversación llegó al límite de contexto)

## Qué es esto
Sistema de gestión de obra pública mexicana (expedientes, presupuestos,
BIM, topografía, jurídico, firma electrónica) para licitaciones/obra
pública. Dos entregables:

1. **Backend** (`megalodon-backend-corregido.zip`) — Python/FastAPI,
   PostgreSQL+PostGIS (vía Supabase), Supabase Storage.
2. **Frontend** (`weblinuxmegalodon-conectado.zip`) — React/Vite,
   simulación de escritorio tipo OS ("MegalodonOS"), cada app es una
   mini-app dentro del escritorio.

## Decisión de arquitectura (ya tomada, no reabrir)
Un solo backend canónico (Python/FastAPI), un solo frontend
(`weblinuxmegalodon`), Supabase para DB+Storage. Se evaluó un segundo
backend en Node/Drizzle (`app_quitar_a_kimi`) y se decidió NO usarlo como
runtime -- solo se minaron ideas de su modelo de datos. Ver
`AUDITORIA_KIMI_Y_3D.md` dentro del zip del backend para el detalle
completo de esa decisión y por qué.

## Cómo hemos estado trabajando (seguir el mismo patrón)
1. **Nunca portar código a ciegas**: antes de traer lógica de los .py
   originales de Cristian (que son blueprints/boceto de arquitectura, NO
   código de producción listo -- él mismo lo aclaró), se lee el original
   completo, se compara contra lo que ya existe, y se identifican bugs
   reales antes de decidir qué portar.
2. **Verificación real, no confianza ciega**: Python se verifica con
   `python3 -m py_compile` sobre TODO el árbol `app/` después de cada
   cambio. TypeScript se verifica con `tsc --noEmit` real (hay tsc
   instalado en el sandbox) sobre el cliente completo. Esto ya atrapó
   bugs reales varias veces (ver CAMBIOS_SESION.md).
3. **Honestidad sobre límites del sandbox**: no hay red en el bash_tool,
   así que no se pudo instalar `ifcopenshell`/`supabase-py`/etc. para
   probar en runtime real -- todo se verificó por lectura cuidadosa +
   sintaxis, y se documentó explícitamente qué no se pudo probar (ver
   notas de "esto no se pudo verificar" en STORAGE_SUPABASE.md).
4. **Siempre entregar zip + documentación del cambio** al terminar un
   bloque de trabajo, nunca solo código sin explicación.
5. **Preguntar antes de over-engineer**: cuando una tarea tenía un fork
   de alcance grande (ej. portar todo `megalodon_efirma_core.py` de 988
   líneas vs. solo lo que aporta), se preguntó a Cristian en vez de
   asumir. Él prefiere decisiones deliberadas, no scope creep.

## Qué ya quedó hecho (real, verificado, no mockeado)
Ver el detalle completo dentro del zip del backend, en estos archivos
(léelos en este orden si retomas):
- `CAMBIOS_SESION.md` -- bugs del backend original + costeo corregidos
- `STORAGE_SUPABASE.md` -- integración de Supabase Storage
- `BIM_IFC_IMPLEMENTADO.md` -- motor BIM/IFC real con ifcopenshell
- `AUDITORIA_KIMI_Y_3D.md` -- por qué no se usó Kimi/portar_3D completos
- `TOPOGRAFIA_IMPLEMENTADO.md` -- motor de topografía real (TIN, volúmenes, geodesia)
- `ROADMAP.md` -- lista completa de hecho/pendiente, ESTE es el más importante

Resumen ultra-corto:
- Backend arranca de verdad (antes tenía ImportError garantizado)
- Auth real (JWT, login/register/me)
- Motor de costos con bugs de cálculo corregidos (multi-concepto,
  recalcular, Excel, sobrecostos)
- BIM real con ifcopenshell (cuantificación + malla 3D + nivel/bbox)
- Storage real con Supabase (antes `firmar_documento`/`subir_documento`
  eran placeholders que no hacían nada real)
- Validadores reales (10 validadores de licitación portados)
- Firma electrónica con TSA real + CFDI 4.0
- Topografía real de cero (TIN, volúmenes corte/terraplén, geodesia)
- Frontend conectado: auth real, store de expediente activo, app de
  Proyectos, megalodon-costos (guarda en backend real), bim-calculator
  (visor 3D real), app de Topografía (visor 3D real)

## Qué falta (por prioridad, según ROADMAP.md)
1. Conectar el resto de mini-apps del escritorio al backend (la mayoría
   siguen con datos de demo)
2. Mover procesamiento IFC pesado a Celery async (ya hay storage real,
   falta esta pieza)
3. Clash detection real portando partes de `portar_3D` (broad_phase/
   dynamic_tree) -- NO todo el archivo, solo detección de colisiones
4. Migraciones de Alembic (no se pudieron generar sin una BD real
   corriendo) y tests (cero todavía)
5. **Pendiente que Cristian mencionó y no se ha empezado**: herramienta
   para panel admin de usuarios, y otra para su panel super-admin. Iba a
   mandar una propuesta -- retomar eso si él la manda.
6. Nombres de producto mezclados (Cornstone / Megalodon OS /
   WebLinuxMegalodon) -- se dijo que se iría corrigiendo sobre la marcha,
   no se ha hecho una limpieza dedicada.

## Cómo continuar en el chat nuevo
1. Sube `megalodon-backend-corregido.zip` y `weblinuxmegalodon-conectado.zip`.
2. Sube este archivo (`ESTADO_Y_CONTINUACION.md`).
3. Dile a Claude: "Lee ESTADO_Y_CONTINUACION.md y ROADMAP.md dentro del
   zip del backend, y seguimos con [lo que decidas]."
4. No hace falta volver a explicar el contexto del proyecto ni la
   arquitectura -- ya está toda documentada.
