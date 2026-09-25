# Nota importante primero: la auditoría de este turno parece haber revisado un ZIP viejo

Antes de los hallazgos: la auditoría recibida en esta ronda afirma que
`app/utils/upload_limits.py` "no existe" y que "no existe una migración que
cree las ocho tablas [Tez]". Ambas cosas ya estaban hechas y verificadas en
el ZIP entregado inmediatamente antes de esa auditoría
(`MEGALODON_V7_2026-08-30_infra_hardening.zip`) -- confirmado de nuevo aquí
mismo con `unzip -l` sobre ese archivo exacto:

    megalodon_audit/backend/app/utils/upload_limits.py           2816 bytes
    megalodon_audit/backend/alembic/versions/20260829_tezcatlipoca_tables.py  11140 bytes

Ambos presentes, tamaños no-cero, con contenido real. La conclusión más
probable es que esa sesión de auditoría recibió un ZIP anterior (el de
`2026-08-27`, antes de la ronda de infraestructura) en vez del más
reciente. No se repitió el trabajo ya hecho por esta razón -- se verificó
que sigue presente y se continuó con los hallazgos genuinamente nuevos de
esa misma auditoría.

## Hallazgos nuevos de esta ronda, verificados contra el código real

### Token de acceso en localStorage -- NO tan grave como se reportó

Verificado: `frontend/app/src/lib/api-client.ts` sí intenta LEER
`localStorage.getItem('megalodon-auth')` al cargar. Pero
`frontend/app/src/stores/useAuthStore.ts` usa `create<AuthState>(...)` de
Zustand SIN el middleware `persist()` -- no hay `partialize`, no hay
`name:`, no hay nada que escriba a localStorage. Confirmé además con
`grep -rn "localStorage.setItem"` sobre todo `frontend/app/src` -- cero
resultados en todo el árbol. El código de lectura es real pero está
leyendo una llave que el propio proyecto nunca escribe -- no hay una
fuga activa por este camino tal como está el código hoy. Sí queda una
duda legítima: el comentario en `api-client.ts` asume que `useAuthStore`
persiste, lo cual sugiere que la sesión no sobrevive un refresh de
página en absoluto (ni por localStorage ni por otro medio) -- un bug de
UX, no de seguridad. No se tocó código por esto todavía; falta confirmar
si existe un flujo de refresh vía cookie httpOnly antes de decidir qué
hacer con este bloque muerto.

### `/sanciones-publicas` -- CONFIRMADO, cross-tenant real, CERRADO

Verificado exacto: sin auth, `select(Sancion).where(Sancion.estado ==
"VIGENTE")` sin `tenant_id`. `Sancion` tiene `TenantMixin` y CERO campo de
clasificación/publicación -- a diferencia de `ExpedienteObra`, que sí
tiene `clasificacion` y gatea correctamente su propio endpoint público
(`/expedientes-publicos`, que además es intencionalmente cross-tenant por
diseño, como un portal de transparencia nacional -- ese no es el bug).
`estado == "VIGENTE"` es un estado del expediente sancionador (vigente
vs. concluida/suspendida/apelada), no una decisión de publicación. El
endpoint mezclaba sanciones de todos los tenants, con `motivo` y
`monto_multa`, sin login.

**Corregido:** columna nueva `sanciones.publicada` (boolean, default
`false` -- migración `20260830_sancion_publicada_flag.py`), y el endpoint
ahora exige `Sancion.publicada.is_(True)` además del estado. Con el
default en false y ningún registro marcado, el endpoint queda vacío hasta
que cada tenant decida explícitamente qué sanciones sí van al portal
público -- mismo principio que "ninguna LegalRule activa sin fundamento
verificado" aplicado aquí a publicación de datos.

### Duplicados exactos en el corpus legado -- CONFIRMADO, no tocado

Verificado por sha256: `reglamento_lopsrm_completo_auto.yaml` y
`reglamento_lopsrm_general_auto.yaml` en
`backend/app/data/legal_corpus/reglas_yaml_generadas/` son
byte-idénticos (mismo hash, mismo tamaño). Esto vive en el corpus LEGADO
(el que consume `motor_busqueda_legal.py`, uno de los tres motores
paralelos identificados al inicio de este trabajo), no en el nuevo
`legal_sources`/`legal_articles` que se ha venido poblando esta sesión.
No se tocó -- baja prioridad frente a la decisión pendiente de retirar o
convertir en fachada los motores viejos.

### Licencia MIT vs. "All rights reserved" -- CONFIRMADO Y CERRADO

Verificado: `pyproject.toml` decía `license = {text = "MIT"}`, mientras
`LICENSE` y los headers de cada archivo dicen software propietario
("Copyright... All rights reserved... No license, express or implied, is
granted..."). Corregido `pyproject.toml` a `"Proprietary"` para que
coincida con lo que el proyecto dice en todos los demás lugares -- no se
tocó `LICENSE` ni los headers, porque cambiarlos a MIT habría sido de
facto abrir el código, una decisión que no me corresponde tomar por
cuenta propia.

## Actualización 2026-08-30c — bug real de materializer.materialize() + primer contrato de dominio formal

Se recibió una propuesta arquitectónica (otra sesión) sobre no fusionar
los módulos de Megalodon y conectar por contratos de dominio explícitos
en vez de un mega-servicio. Se verificó el hallazgo concreto que traía
antes de aceptar la recomendación general.

**Confirmado y cerrado: `ProcurementMaterializer.materialize()` exige
`tenant_id` como keyword-only (`materializer.py:29`), pero
`orchestrator.py:332` lo llamaba sin pasarlo.** `TypeError` garantizado en
cualquier ejecución real que llegara a la etapa MATERIALIZATION. Corregido
con `tenant_id=tender.tenant_id`.

**Confirmado el mismo patrón de siempre en los tests:**
`test_materializer_requires_tenant_context()` en
`tests/procurement/test_stage_trace_static.py` solo comprobaba que el
string `"tenant_id: UUID"` aparece en el texto de `materializer.py` --
nunca cruzaba eso contra la llamada real del orquestador, por eso pasaba
en verde con el bug presente. Se agregó
`test_orchestrator_passes_tenant_id_to_materialize()` que sí ata ambos
lados.

**Sobre la recomendación general (no fusionar, formalizar contratos de
dominio con snapshot + provenance):** de acuerdo con el principio -- es la
misma disciplina que ya se venía aplicando toda la sesión al corpus legal
(`LegalArticle.content_hash`, `LegalSource.version`, ninguna `LegalRule`
activa sin fundamento verificado). No se intentó construir las cinco
abstracciones propuestas (`DomainReference`, `DomainSnapshot`,
`ProcurementIntegrationPort`, `MaterializationPolicy`, `TenantContext`
transversal) de un jalón -- eso es varias semanas tocando una docena de
engines. Se implementaron las primeras dos (`DomainReference`,
`DomainSnapshot`, en `app/engines/procurement/domain_contracts.py`) y se
aplicaron como plantilla a UN flujo -- BIM/Topografía → 
`technical.snapshots` en `materializer.py`, el que la propuesta señalaba
como ya mejor patronado -- en vez de a los cinco a la vez.

`canonical["technical"]["snapshots"]` ahora convive con
`quantification_sources` (que no se tocó -- verificado con grep que nada
más lo consume hoy, cero riesgo de romper algo). Cada snapshot trae:

    source: {resource_type, resource_id, tenant_id, revision, content_hash}
    snapshot: <datos congelados>
    engine_version
    captured_at
    output_hash  # sha256 determinista de lo que se congeló, verificado con prueba de determinismo

`content_hash` del recurso origen queda en `None` para BIM/Topografía a
propósito -- ni `ModeloBIM` ni `CalculoVolumen` calculan un hash de
contenido propio todavía; inventarlo habría sido el mismo error que ya
corregimos varias veces en el corpus legal (una cifra que aparenta
verificación pero no lo es).

**No se tocó en esta ronda** (confirmado que ya existe, no hace falta
construirlo): `ContractPolicy`
(`app/engines/procurement/contract_policy.py`) ya cumple buena parte del
rol de la `MaterializationPolicy` propuesta, con otro nombre.

**Pendiente si se quiere seguir el mismo patrón:** replicar
`DomainReference`/`DomainSnapshot` a económico (`_materialize_budget`) y
programación (`_materialize_schedule`) cuando se decida seguir esa ruta --
no se apuró en esta ronda. `licitacion_id` en `TenderPackage` (propuesto
en la ronda anterior) tampoco se agregó todavía -- no se pidió
explícitamente en esta ronda.

| Hallazgo | Estado |
|---|---|
| Auditoría corrió contra ZIP viejo (upload_limits/Tez tables ya existían) | Aclarado, sin retrabajo |
| Token en localStorage | Corregido el diagnóstico: no hay escritura activa, solo lectura muerta |
| `/sanciones-publicas` cross-tenant | ✅ Cerrado (columna `publicada` + filtro) |
| Duplicados YAML en corpus legado | Confirmado, sin tocar (baja prioridad) |
| Licencia MIT vs. propietario | ✅ Cerrado |
