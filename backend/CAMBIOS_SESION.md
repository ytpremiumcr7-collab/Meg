<!--
Copyright © 2026 Cristian Rodriguez
All rights reserved.
Unauthorized copying, modification, distribution, or use is prohibited
without prior written permission.
-->

# Megalodon Backend — Cambios de esta sesión

Base usada: `megalodon-backend--programacion4` (la iteración más completa y
reciente de los 4 backends encontrados en el zip; ver comparación al final).

## 1. Bugs que impedían que el backend arrancara

| Archivo | Bug | Fix |
|---|---|---|
| `app/models/base.py` | Nunca se creaba el `engine`/sesión de SQLAlchemy, pero 7 routers hacían `from app.models.base import engine` → **ImportError inmediato al iniciar la app** | Se creó `engine`, `AsyncSessionLocal` y `get_session()` en `base.py`, fuente única de verdad |
| `app/models/base.py` (`TenantMixin`) | `tenant_id` no tenía `ForeignKey`, rompía las relaciones `User.tenant` y `ExpedienteObra.tenant` (`NoForeignKeysError` en la primera request) | Se agregó `ForeignKey("tenants.id")` |
| `app/main.py` | `conn.execute("CREATE EXTENSION...")` con string crudo — SQLAlchemy 2.0 async lo rechaza | Envuelto con `text(...)` |
| `app/api/v1/*.py` (7 archivos) | Cada router duplicaba su propio `get_db()` + `sessionmaker()` en vez de reusar una sesión centralizada | Se creó `app/core/deps.py` con `get_db`/`get_current_user` únicos; todos los routers lo importan de ahí |
| `app/api/v1/auth.py` | `POST /auth/refresh` recibía `refresh_token: str` suelto → FastAPI lo trataba como **query param**, pero el cliente TS lo manda como JSON body → 422 siempre | Se creó `RefreshRequest` (Pydantic) como body real |

## 2. Bugs de cálculo en el motor de costeo (los más importantes)

Comparé `app/engines/costos/motor_costeo.py` (219 líneas) contra tu script
original `megalodon_costos_v3_1.py` (3,678 líneas, el único de tus 5
archivos fuente que compila sin errores — `v3_3.py` viene con wrapper de
markdown pegado y errores de sintaxis reales, ver sección 4).

| Bug | Efecto | Fix |
|---|---|---|
| `PartidaCosteo.precio_unitario` solo leía `conceptos[0]` | Cualquier partida con **más de un concepto** (ej. "muro" = block + acero + aplanado) perdía silenciosamente el costo de todos los conceptos menos el primero | Ahora suma `costo_directo_unitario * cantidad` de **todos** los conceptos |
| `crear_desde_costeo` compartía la misma lista de insumos entre todos los conceptos de una partida, y solo el primero se quedaba con ellos | Presupuestos con APU multi-concepto salían mal calculados desde la creación | Cada concepto ahora lee **sus propios** insumos anidados (`concepto.insumos`) |
| Router `presupuestos.py` nunca reenviaba `precio_unitario` al servicio | El caso "partida de tabulador con precio ya conocido" (tu flujo real con el tabulador CDMX importado) **nunca podía funcionar** — siempre se recalculaba a $0.00 | Se agregó `precio_unitario_manual` en el motor: si la partida no trae conceptos, se respeta el precio dado, sin pasar por indirectos/utilidad a nivel de concepto (mismo principio que ya corregiste en Piedra Angular para no aplicar doble indirecto) |
| `recalcular()` y `generar_excel()` reconstruían las partidas con `conceptos=[]` (nunca recargaban de la BD) | **Cada vez que alguien daba clic en "Recalcular" o exportaba a Excel, el presupuesto completo se ponía en $0.00**, pisando los montos reales guardados | Nuevo helper `_reconstruir_partidas_desde_db()` con `selectinload` completo (partida → conceptos → insumos) |
| `validar_sobrecostos()` reconstruía ambos presupuestos con `partidas=[]` en vez de usar los montos ya guardados | La validación de sobrecostos **siempre decía "dentro de tolerancia"**, sin importar los datos reales — grave para cumplimiento en obra pública | Ahora usa directamente `monto_total` ya calculado y guardado en BD |
| Faltaba `factor_riesgo` (existe en tu `MotorPreciosBIM` original) | Presupuestos de obra pública con componente de riesgo no tenían dónde aplicarlo | Se agregó `factor_riesgo`/`monto_riesgo` opcional (default 0, no rompe presupuestos existentes) |

## 3. Bugs en el cliente TypeScript (`client-typescript/megalodon-client.ts`)

| Bug | Efecto | Fix |
|---|---|---|
| `auth.login()` arma un `URLSearchParams`, pero `request()` solo reconocía `FormData` como cuerpo especial | `URLSearchParams` caía en la rama de `JSON.stringify()`, que lo serializa como `"{}"` (no tiene propiedades enumerables propias) → **el login siempre mandaba un body vacío y nunca podía autenticar a nadie** | `request()` ahora también reconoce `URLSearchParams` y lo manda tal cual |
| `ocr.validar()` mandaba `umbral_confianza` como **header** | El backend lo espera como query param (`umbral_confianza: float = 60.0` sin anotación) → nunca se leía, siempre usaba el default 60.0 | Ahora va en la query string |
| `websocket.onProgress()` / `onComplete()` llamaban `this.subscribe(...)` / `this.unsubscribe(...)` | Dentro de un object literal (`websocket = {...}`), `this` apunta a `MegalodonClient`, no al propio objeto `websocket` → **`this.subscribe is not a function` en cuanto se usaba `client.websocket.onProgress(...)`** | Cambiado a `this.websocket.subscribe(...)` |
| `Presupuesto`/`PartidaCreate`/`PresupuestoCreate` no reflejaban el esquema real ni el nuevo `factor_riesgo` | Autocompletado y validación de tipos incorrectos | Interfaces actualizadas, `precio_unitario` ahora opcional (solo aplica a partidas tipo tabulador) |

Verificado con `tsc --noEmit` (TypeScript 6.0.3, sin red): **compila limpio,
0 errores**, tras los fixes.

## 4. Hallazgo importante sobre tus archivos fuente

De tus 5 scripts originales, verifiqué cuáles compilan como Python válido:

| Archivo | ¿Compila? | Nota |
|---|---|---|
| `megalodon_costos_v3_1.py` (3,678 líneas) | ✅ Sí | El más confiable; base de los fixes de esta sesión |
| `megalodon_costos_v3(1).py` (3,011 líneas) | ✅ Sí | |
| `megalodon_costos_v3_3.py` (1,744 líneas) | ❌ **No** | Viene con texto de chat pegado al inicio/final ("Perfecto, te entrego el archivo...") y errores de sintaxis reales (mezcla de one-liners `def f(): ...` con bloques `if`/`with` indentados después, lo cual no es Python válido). A pesar de tener MÁS funcionalidad en papel (repositorio Postgres real, vínculo programación↔presupuesto), **nunca se pudo haber ejecutado tal cual**. Recuperar esa lógica requiere repararlo línea por línea, no copiarlo directo. |
| `sistema_unificado_megalodon_costos_v2(3).py` (3,033 líneas) | ✅ Sí | |
| `sistema_expediente_electronico_mexico_real_end_to_end_v2(1).py` (2,312 líneas) | ✅ Sí | |

## 5. Qué falta (pausado a tu pedido para enfocar en costos)

Ver `ROADMAP.md` para el detalle completo priorizado. En resumen, lo
siguiente son los engines que siguen "delgados" comparados con tu lógica
original y el frontend aún sin cablear a ningún endpoint real:

- BIM: falta portar `MotorPreciosBIM` completo (cuantificación desde
  elementos → costeo). Existe completo y probado en `v3_1`.
- Topografía: 0 líneas reales, puro scaffolding vacío.
- Jurídico: 143 líneas vs `MotorJuridico` completo con jurisdicciones.
- Validadores: 85 líneas vs 9 validadores reales (SAT, IMSS, INFONAVIT, etc.)
- Frontend (MegalodonOS): sigue sin conectarse a ningún endpoint — sesión
  pausada aquí para enfocar en dejar bien el motor de costos primero.
