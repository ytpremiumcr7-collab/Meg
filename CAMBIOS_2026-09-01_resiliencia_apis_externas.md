# Cambios 2026-09-01 — Resiliencia de fuentes externas + bugs de logging

Base: `MEGALODON_V7_2026-08-31_pending_closed_PRR.zip` (el zip subido en esta
ronda). Este documento describe lo que se verificó y lo que se cambió
al revisar ese paquete.

## 0. Verificación independiente de lo ya declarado cerrado

Antes de tocar nada, se releyó `PRR_CIERRE_PENDIENTES_2026-08-31.txt` y se
verificaron por lectura directa (no por confianza en el reporte) dos de sus
afirmaciones más fuertes:

- `DomainSnapshot` en `domain_contracts.py`: inmutabilidad real vía
  `@dataclass(frozen=True)` + `MappingProxyType`/tuplas recursivas, hash sobre
  el payload congelado. Confirmado, coincide con lo declarado.
- Bloqueo de concurrencia en `service.py`: `create_requirement_rule_version`,
  `add_artifact`, `create_revision` sí llaman `self._get(tender_id,
  for_update=True)`, y ese helper (línea ~489) sí aplica `.with_for_update()`
  condicionalmente. Confirmado.

También se verificó, corriendo comandos reales en este entorno (no
asumiendo), que los 3 pendientes que el reporte anterior dejó abiertos por
límites del sandbox **siguen bloqueados aquí también, por la misma razón**:

- Sin red de salida (`x-deny-reason: host_not_allowed` al intentar
  `pypi.org`) → no se puede generar `backend/uv.lock` ni
  `frontend/app/package-lock.json` de forma reproducible.
- Sin Docker (`docker: not found`) → no hay Postgres/Redis reales para un
  E2E de verdad.

No se inventó ningún lockfile ni se simuló un E2E. Sigue pendiente, ahora
confirmado de forma independiente en dos entornos distintos.

## 1. Hallazgo: el P0 histórico de `licitaciones_obra.py` ya estaba resuelto

`reference/PRR_GATE_REPORT.md` (26-ago) documentaba que el router de
licitaciones era un fixture/demo — sin persistencia real, adjudicaba con
valores hardcodeados. Se verificó el archivo actual línea por línea: ese
código **ya no existe**. Fue reemplazado por un router MPPL (motor de
prevención/pre-evaluación) + una sección "workspace" con persistencia real
en DB, transiciones de estado válidas, y un docstring que aclara
explícitamente que Megalodon no sustituye a Compras MX ni emite fallo
oficial. Se confirmó revisando `guardar_planeacion`, `emitir_fallo_workspace`
y `licitacion_service.py` (líneas 200-330): usan datos reales de la
request, no valores fijos, y persisten con tenant scoping correcto.

Esto **no está documentado en ningún changelog** de los que trae el zip
(ni el de 26-ago, ni 27, ni 30, ni 30b) — aparentemente se hizo en una
sesión paralela. Se deja constancia acá para que no se pierda el rastro.
No se tocó nada de esto: ya está bien.

## 2. Bugs reales encontrados y corregidos (no sólo huecos de cobertura)

Buscando cómo el sistema depende de APIs externas (Shodan, Censys,
GreyNoise, Feodo Tracker, URLhaus, CISA KEV, Open-Meteo — todo el módulo
`tezcatlipoca/services/malware/` y `weather/`), aparecieron bugs reales,
verificados por ejecución (mockeando sólo la red, no la lógica):

1. **`feodo_tracker.py` — `NameError` en el manejo de errores.** `logger`
   se usaba pero nunca se importaba. Peor: cuando la geolocalización de UNA
   IP fallaba (timeout, rate-limit de ip-api.com), la excepción se
   propagaba y tiraba el feed de C2 **completo**, aunque las otras 499 IPs
   estuvieran perfectas. Se corrigió: `logger` importado, geolocalización
   ahora degrada a "Unknown" sin tumbar nada, y se limitó a 60
   geolocalizaciones nuevas por llamada (ip-api.com es 150 req/min free
   tier — un feed grande podía chocar con eso a medio proceso).
2. **`cisa_kev.py` — URL de API incorrecta.** Usaba
   `https://api.cisa.gov/known-exploited-vulnerabilities/catalog`, que no
   aparece en ninguna fuente oficial (se verificó contra CISA, EclecticIQ,
   Elastic, y el cliente oficial en PyPI — todos coinciden en
   `https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json`,
   que es la que ya usaba `aggregator.py` en su implementación paralela).
   Con la URL vieja, este cliente probablemente nunca devolvió datos reales
   en producción, y el `except` silencioso lo ocultaba. Corregida.
3. **`aggregator.py` — CVE nunca se detectaba en modo "auto".**
   `_detect_type()` no reconocía el patrón `CVE-\d{4}-\d+`, así que cuando
   `enrich(indicator, indicator_type="auto")` recibía un CVE, caía a
   "unknown" y **CISA KEV nunca se consultaba**, sin importar si el CVE
   estaba realmente en el catálogo. Corregido y verificado con un
   `enrich("CVE-2024-12345", "auto")` de punta a punta.
4. **`main.py` (Tezcatlipoca) — 6 handlers de error de WebSocket que se
   caían solos.** Llamaban `logger.warning("evento", bounds=bounds)` sobre
   un logger `logging.getLogger` estándar, que no acepta kwargs
   arbitrarios — cada vez que un timeout/error real ocurría en
   `find_flights`/`find_ships`/`sar_focus`, el logging mismo lanzaba
   `TypeError` en vez de registrar el error. Se reformatearon esas 6
   llamadas a mensajes planos (verificado con el `logging` real de Python).
5. **`routers/auth.py` (Tezcatlipoca) — otro `NameError`,** esta vez en el
   registro forense de intentos de login fallidos (`_record_auth_attempt`).
   Como corre en una task de asyncio en segundo plano, no tumbaba el
   login, pero sí dejaba sin auditoría los intentos sospechosos —
   justo cuando más se necesita ese registro. Corregido con `structlog`
   (coincide con la firma que el código ya usaba).
6. **`modules/firma/cfdi40.py` (backend principal, sellado CFDI 4.0 SAT) —
   mismo `NameError`.** Si una `.key` de e.firma fallaba en carga DER y
   PEM, el `except` debía loguear y luego lanzar
   `ValueError("...Verifique contraseña.")` — un mensaje claro y accionable.
   En cambio, el propio `logger.debug(...)` reventaba primero con
   `NameError`, así que quien intentaba sellar un CFDI se topaba con un
   error interno sin sentido. Corregido.
7. **Ningún conector externo tenía respaldo persistente.** Todos
   cacheaban sólo en memoria del proceso (`self.cache = {}`). Si el
   proceso reinicia (deploy, crash, autoscaling) mientras la fuente externa
   está caída, arrancaba sin datos y sin forma de distinguir "0 amenazas"
   de "la fuente lleva horas caída" — ambiguo y peligroso para una
   plataforma de inteligencia. Se construyó
   `services/feed_resilience.py` (caché en disco, escritura atómica,
   estado explícito `live`/`stale_cache`/`unavailable`) y se conectó a
   `aggregator.py`, `feodo_tracker.py`, `urlhaus.py`, `cisa_kev.py` y
   `open_meteo.py`. **Probado de punta a punta simulando un reinicio de
   proceso con las 3 fuentes caídas**: antes de este cambio,
   `total_threats` hubiera dado `0`; ahora sirve el último dato bueno
   conocido y lo marca `stale_cache` en vez de mentir que está limpio.

Adicional: `urlhaus.py`, `feodo_tracker.py` y `cisa_kev.py` importaban
`sync_get`/`async_get` de `services/secure_requests.py` (que ya trae
reintento con backoff y manejo de 429) pero llamaban `requests.get/post`
directo, sin usar nada de eso. Ahora sí lo usan. Se agregó `sync_post` a
`secure_requests.py` (no existía; URLhaus lo necesita para sus tres
endpoints POST) y se probó con mocks (éxito directo, 429-luego-éxito,
falla persistente que agota reintentos y propaga).

`shodan_connector.py`, `censys.py` y `grey_noise.py` (los 3 que requieren
API key de pago) recibieron un pase más ligero: `print()` → `logger`
consistente, y se agregó logging en los `except` que antes sólo devolvían
`{"error": ...}` sin dejar rastro en ningún log. **No** se les agregó
respaldo persistente en disco todavía — ya degradan razonablemente bien
(devuelven error explícito si falta la key) y no son de "siempre
activos", así que se priorizó el tiempo en las 5 fuentes que sí corren
sin configuración.

## 3. Verificación

- `python3 -m py_compile` sobre **todo** `backend/` (app/ + tezcatlipoca/,
  no sólo los archivos tocados): 0 errores de sintaxis.
- `services/feed_resilience.py`, `secure_requests.sync_post`,
  `feodo_tracker.py`, `urlhaus.py`, `cisa_kev.py`, `aggregator.py` y
  `open_meteo.py` se probaron con **ejecución real** (mockeando sólo la
  llamada de red, nunca la lógica), incluyendo los escenarios de "proceso
  recién iniciado + fuente caída" y "fuente caída pero hay respaldo".
  Este sandbox no tiene `structlog`/`aiohttp` instalados (sin red para
  instalarlos); se usaron stubs mínimos que replican la firma real de
  ambas librerías para poder correr las pruebas — no para inventar
  resultados, sino para poder ejecutar en vez de sólo leer código.
- Los 6 call-sites corregidos en `main.py` se probaron además contra el
  `logging` real de Python (sin stub), para confirmar que el
  `TypeError` original ya no ocurre.

## 4. Lo que NO se hizo (para no prometer de más)

- No se generaron `uv.lock` ni `package-lock.json` — bloqueado por falta
  de red en este entorno, igual que en la ronda anterior.
- No se corrió un E2E real contra Postgres/Redis — no hay Docker aquí.
- No se le agregó respaldo persistente a shodan/censys/greynoise (ver
  arriba, quedó como pase ligero).
- No se consolidó la duplicación entre `aggregator.py` (fetch inline) y
  los clientes standalone (`FeodoTrackerClient`, `URLhausClient`,
  `CISAKEVClient`) — ambos caminos están vivos (montados en routers
  distintos) y unificarlos es un cambio más grande, con más superficie de
  riesgo, que no se podía verificar por ejecución real dado que
  `aggregator.py` es async/aiohttp y los clientes standalone son
  síncronos/`requests`. Se aplicó el mismo fix de resiliencia a ambos
  caminos por separado en vez de forzar una fusión sin poder probarla.
