# Cambios 2026-08-27 — Integración inicial legal_corpus → LegalRule

Contexto: sesión de trabajo sobre el motor jurídico/procurement, cruzando
`app/engines/juridico/*` (motor viejo, hardcodeado) contra
`app/models/procurement.py` (LegalSource/LegalArticle/LegalRule, motor nuevo
ya wireado en `app/engines/procurement/requirements.py` y `rules.py`) y
contra los paquetes de corpus jurídico (LOPSRM/LAASSP federal verificados).

## Agregado

- `alembic/versions/20260827_legal_rule_active_requires_fundamento.py`
  Constraint a nivel de DB: ninguna fila de `legal_rules` puede quedar
  `active=true` sin `source_id` Y `article_id`. Antes solo lo validaba
  `ProcurementService.create_legal_rule()` en la capa de servicio -- nada
  a nivel de esquema lo impedía. Desactiva primero cualquier fila
  existente que ya lo violaría (no la borra). Head único verificado tras
  integrarla.

- `backend/scripts/load_legal_corpus_articles.py`
  Loader real (reemplaza conceptualmente al skeleton con `print()` del
  paquete `MEGALODON_CORPUS_COBERTURA_TOTAL_HARDENED`). Carga 131
  artículos de LOPSRM + 120 de LAASSP (filtrando por `estado_dato`
  verificado en el CSV origen) a `legal_sources`/`legal_articles`, más
  RLOPSRM Art. 91 a mano (no viene segmentado en el CSV). Siembra 5
  `LegalRule` con fundamento verificado por lectura directa del texto,
  no copiado de un README:
  - `GARANTIA-CUMPLIMIENTO-OBRA-MIN10` → RLOPSRM Art. 91
  - `GARANTIA-ANTICIPO-OBRA-100` → LOPSRM Art. 48, fracción I
  - `GARANTIA-ANTICIPO-ADQ-100` → LAASSP Art. 69, fracción I
  - `TOPE-PENAS-CONVENCIONALES-OBRA` → LOPSRM Art. 46 Bis
  - `TOPE-PENAS-CONVENCIONALES-ADQ` → LAASSP Art. 75

  No ejecutado contra una base real todavía (sin acceso a red/DB en la
  sesión donde se escribió). Correr `alembic upgrade head` y luego este
  script en un entorno real antes de confiar en que aplica limpio.

## Corregido

- `app/engines/juridico/motor_garantias.py` —
  `calcular_garantia_cumplimiento()` regresaba 5% del monto del contrato
  para obra pública. RLOPSRM Art. 91 (verificado, texto completo leído)
  fija un **mínimo legal de 10%**. El método quedó en 5% -- por debajo del
  piso legal -- desde que se escribió. Si se usó para calcular una
  garantía en una propuesta real, esa propuesta salió sub-garantizada.
  Corregido a 10% con la cita exacta en comentario. Sigue siendo un valor
  hardcodeado en Python (no una consulta a `legal_rules`) -- eso queda
  pendiente como refactor propio, porque requiere que el método deje de
  ser síncrono y reciba sesión de DB.

## Actualización 2026-08-27 (segunda ronda) — CFF/LSS/INFONAVIT aportados

El usuario trajo `docs_faltantes_vigentes_oficiales.zip`: CFF, LSS, Ley del
INFONAVIT (oficiales, Cámara de Diputados, hashes verificados contra su
propio manifest) + un refresco de LOPSRM. Con eso se verificó el texto real
de las 5 citas hardcodeadas de REQ-001 a REQ-005. **Las 5 estaban mal.**
Tres se corrigieron (código + `LegalRule` sembrada); dos siguen sin
fundamento real disponible:

- **REQ-001 (SAT) — CORREGIDO.** La cita era CFF Art. 29-A (que es sobre
  requisitos de CFDI, no sobre impedimento de contratar). El artículo
  correcto es **CFF Art. 32-D** ("...en ningún caso contratarán
  adquisiciones, arrendamientos, servicios u obra pública con las personas
  ... que tengan a su cargo créditos fiscales firmes..."). Ya está en
  `motor_juridico.py` y sembrado como `LegalRule OPINION-CUMPLIMIENTO-SAT`.

- **REQ-004/005 (aviso / bases) — CORREGIDOS.** Las citas eran LOPSRM
  Art. 33/34 y LAASSP Art. 48/49 (plazos y adjudicación, no aviso ni
  bases). Los artículos correctos, verificados leyendo el texto completo:
  - Bases de licitación: **LOPSRM Art. 31** / **LAASSP Art. 40**
  - Publicación/aviso (vía "la Plataforma", nombre actual de CompraNet):
    **LOPSRM Art. 32** / **LAASSP Art. 41**
  Ya están en `motor_juridico.py` y sembrados como 4 `LegalRule`
  (`BASES-LICITACION-OBRA/ADQ`, `AVISO-PUBLICACION-OBRA/ADQ`).

- **REQ-002 (IMSS) — SIGUE PENDIENTE.** LSS Art. 15-A real es sobre
  registro/responsabilidad solidaria en subcontratación (REPSE), no sobre
  "opinión de cumplimiento". La frase "opinión de cumplimiento" no aparece
  en ninguna parte de la LSS. El mecanismo probablemente vive en un
  reglamento (RACERF u otro) no aportado todavía.

- **REQ-003 (INFONAVIT) — SIGUE PENDIENTE.** "Artículo 136" aparece una
  sola vez en toda la Ley del INFONAVIT, y es una referencia cruzada al
  Art. 136 de la Ley Federal del Trabajo (reparto de utilidades) -- no un
  artículo propio de la ley de INFONAVIT. La cita hardcodeada está
  confundiendo dos leyes distintas. Falta la normativa secundaria real de
  INFONAVIT.

`docs_faltantes_vigentes_oficiales/` (en la raíz de este repo) trae los 4
PDF oficiales + manifest para que quien retome esto no tenga que
re-descargarlos.

## Actualización 2026-08-27 (tercera ronda) — REQ-002/003 cerrados

El usuario trajo `opiniones_cumplimiento_IMSS_INFONAVIT_vigentes.zip` con la
normativa secundaria real. Verificados los 3 documentos por lectura directa
(no solo por el resumen que los acompañaba) y por sha256 contra su propio
manifest -- coinciden exacto.

- **IMSS (REQ-002) — RESUELTO, con una corrección importante.** Fundamento
  real: Reglas de carácter general para la obtención de la opinión del
  cumplimiento (Acuerdo ACDO.AS2.HCT.270422/107.P.DIR, DOF 22-09-2022),
  ancladas expresamente al **CFF Art. 32-D** (confirmado en el texto).
  Modificadas por Acuerdo ACDO.AS2.HCT.300925/288.P.DIR (DOF 06-10-2025):
  desde el 01-10-2025 la única vía de obtención es Buzón IMSS (Regla
  Quinta modificada, confirmado).

  **Corrección:** el resumen que acompañaba el zip decía "validez 15 días
  hábiles (LAASSP) / 15 días naturales (LOPSRM)". Ese dato **no aparece en
  ninguno de los dos documentos** -- ni "LAASSP" ni "LOPSRM" se mencionan
  ahí. Lo que la Regla Novena dice, literal: *"La opinión... gozará de
  vigencia durante el día de la fecha en que haya sido generada."* Es
  decir, la opinión IMSS vale solo el día en que se genera, no 15 días.
  El loader y `motor_juridico.py` quedaron con la vigencia real (mismo
  día), no con la cifra de 15 días que no se pudo verificar en el texto.
  Esto es operacionalmente importante: si el validador de evidencia de
  Megalodón solo checa "el documento existe" sin checar que la fecha de
  generación coincida con la fecha de presentación de la propuesta, va a
  dejar pasar exactamente el tipo de defecto que se supone debe prevenir.

- **INFONAVIT (REQ-003) — RESUELTO.** Fundamento real: Reglas para la
  obtención de la constancia de situación fiscal, modificadas por
  Resolución RCA-13138-01/24 (DOF 22-04-2024), también ancladas al CFF
  Art. 32-D (confirmado). Regla Sexta: vigencia de 30 días naturales
  desde emisión -- esta cifra sí se confirmó literal en el texto.

Ambas ya están sembradas como `LegalRule` (`OPINION-CUMPLIMIENTO-IMSS`,
`OPINION-CUMPLIMIENTO-INFONAVIT`) y reflejadas en `motor_juridico.py`.
`opiniones_cumplimiento_IMSS_INFONAVIT_vigentes/` en la raíz de este repo
trae los 3 documentos + manifest.

Con esto, de los 5 requisitos hardcodeados originales (REQ-001 a REQ-005):
las 5 citas resultaron incorrectas al verificarlas, y las 5 ya están
corregidas con fundamento real cargado a `legal_articles`/`legal_rules`.

## Actualización 2026-08-27 (cuarta ronda) — auditoría externa + legal_consultor.py

Se recibió una auditoría completa del ZIP anterior (otra sesión de IA). Se
verificaron los hallazgos más conectados a este trabajo antes de aceptarlos:

**Confirmado con evidencia propia — `legal_consultor.py` tenía SU PROPIO
tercer conjunto de umbrales hardcodeados**, duplicado dos veces en el mismo
archivo (`/procedimiento` y dentro de `chat_legal()`), con las mismas seis
citas -- LOPSRM Art. 42/43/40, LAASSP Art. 41/42/40 -- y las seis
resultaron mal al verificar el texto real:
- LOPSRM Art. 42 = cláusula general de excepción (no fija montos)
- LOPSRM Art. 40 = declarar una licitación desierta
- LAASSP Art. 41 = publicación de convocatoria (nuestro REQ-004)
- LAASSP Art. 42 = plazos de licitaciones internacionales
- El artículo que SÍ delega el umbral es **LOPSRM Art. 43** (obra) /
  **LAASSP Art. 55** (adquisiciones) -- y ninguno de los dos estaba citado.

Más importante: **LOPSRM Art. 43 dice literal que el monto "se
establecerá en el Presupuesto de Egresos de la Federación"** -- la ley
misma no fija un número. La tabla real es el Anexo 9 del PEF (ya cargado
en `umbrales_pef_2026_anexo9.csv`), escalonada por presupuesto autorizado
de la dependencia contratante, no un umbral único. Por tanto
`UMBRAL_AD = 1_000_000` / `UMBRAL_IR = 50_000_000` no eran solo números
poco precisos -- estaban modelando algo que la ley no modela así.
`UMA_2026 = 108.62` estaba definida pero no se usaba en ningún lado
(código muerto).

**Hallazgo adicional que la auditoría externa no reportó:** existe un
*cuarto* lugar con umbrales -- `app/config.py` y `app/core/constants.py`
tienen `UMBRAL_ADJUDICACION_DIRECTA_OBRA = 2_200_000` y
`_ADQUISICION = 1_400_000` (coinciden entre sí, pero no con los de
`legal_consultor.py`). Verifiqué que hoy no los consume ningún otro
módulo -- son configuración muerta, no una disputa activa en runtime --
pero son una trampa para quien los conecte después asumiendo que son la
autoridad.

**Corregido en esta ronda:**
- Duplicación eliminada: una sola función `_determinar_procedimiento_umbral()`
  en `legal_consultor.py`, usada por ambos puntos de llamada.
- Citas corregidas a LOPSRM Art. 43 / LAASSP Art. 55, dejando explícito en
  el propio valor de retorno que el monto real vive en el PEF, no en la ley.
- `UMA_2026` (muerta) eliminada.
- Flag agregado sobre `"seriedad": 5%` en `garantias_requeridas` -- no
  verificado todavía contra el corpus (a diferencia de `"cumplimiento": 10%`,
  que sí coincide con RLOPSRM Art. 91 ya verificado).

**NO resuelto todavía, a propósito:** implementar la tabla real del Anexo 9
requiere saber el presupuesto autorizado de la dependencia contratante para
el ejercicio -- un dato que ningún endpoint de este archivo recibe hoy.
Inventar un número fijo "correcto" habría sido repetir el mismo error con
un valor distinto. `UMBRAL_AD_PLACEHOLDER`/`UMBRAL_IR_PLACEHOLDER` quedan
marcados explícitamente como provisionales en el código.

### Resto de la auditoría externa (Tezcatlipoca, storage, uploads,
### frontend lockfile, service-layer tenant checks) -- pendiente de
### verificación propia

No se auditó código de Tezcatlipoca, `docker-compose.prod.yml`, las rutas
de upload, ni el frontend en esta sesión -- son áreas que esta conversación
no había tocado todavía. Los hallazgos de esa auditoría en esas áreas
(migraciones Tez faltantes, MinIO vs Supabase, `await file.read()` sin
límite antes de aplicarlo, falta de `package-lock.json`) suenan plausibles
por el nivel de detalle y porque el resto de esa misma auditoría se
verificó como certero en la parte jurídica -- pero no se confirmaron línea
por línea todavía. Antes de tocar código ahí hace falta una revisión
dedicada, igual que se hizo aquí.

## Pendiente (bloqueadores reales, no builtin ambition)

1. **Tabla real de umbrales PEF Anexo 9** en `determinar_procedimiento`:
   requiere decidir de dónde sale el presupuesto autorizado de la
   dependencia por convocatoria (¿lo extrae Megalodón de la convocatoria
   subida? ¿lo captura el usuario? ¿un catálogo de dependencias
   precargado?) antes de poder reemplazar el placeholder.

2. **P0 de la auditoría externa** (fuera del alcance jurídico de esta
   sesión, sin verificar todavía): migraciones de Tezcatlipoca, storage
   MinIO vs Supabase, streaming de uploads, lockfile de frontend, startup
   de migraciones concurrente con `uvicorn --workers 4`.

3. **`jurisdiction_code="MX-FED-ADQ"`** usado en las LegalRule de
   adquisiciones no existe todavía como `JurisdictionProfile` en
   `app/engines/procurement/catalog.py` (hoy solo hay perfiles de obra:
   `MX-FED-OBRA`, `MX-FED-CONAGUA-OBRA`, `MX-FED-CFE-OBRA`,
   `MX-FED-SICT-OBRA`). Sin ese perfil, la herencia de jurisdicción para
   el lado LAASSP no va a resolver bien.

4. **Extracción de `facts` desde la convocatoria subida.** Las reglas
   sembradas condicionan sobre `contract_type` y `has_anticipo` (vía
   `LegalRule.condition`, consumido por
   `ProcurementRequirementMapper._matches()`), pero nada en el código
   todavía llena esos campos en `tender.canonical_model["facts"]` a
   partir del documento que sube el usuario. Sin ese paso, las reglas
   nunca disparan aunque estén bien cargadas en la base.

## No tocado en esta sesión

Los tres motores paralelos (`/juridico`, `/legal`, `/procurement`) siguen
los tres montados. `legal_consultor.py` sigue con su patrón de chatbot.
Nada de esto se retiró todavía -- decisión pendiente de cuándo convertir
`/juridico` y `/legal` en fachadas de compatibilidad sobre `/procurement`.
