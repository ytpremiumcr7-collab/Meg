# P1 — Monte Carlo SaaS, cierre de implementación

Fecha: 2026-08-10
Base: `MEGALODON_TEZCATLIPOCA_PRODUCTION_CLOSURE_2026-08-10.zip`

## Objetivo
Cerrar Monte Carlo como capacidad SaaS de costo + plazo con lógica estadística real, ejecución asíncrona, persistencia multi-tenant, idempotencia, cuotas, cancelación, reproducibilidad, correlación entre riesgos, trazabilidad y frontend CostOS conectado al backend oficial.

## Implementación
1. Motor determinista/reproducible por seed explícito y RNG local; no usa estado global.
2. Distribuciones: normal, triangular, uniforme, lognormal y beta.
3. Impactos: `costo_pct`, `plazo_pct`, `plazo_dias`, `costo_y_plazo_pct`.
4. Monte Carlo de plazo real: P1/P5/P10/P25/P50/P75/P80/P90/P95/P99, CV, CI y probabilidad de excedencia.
5. Probabilidad conjunta de exceder presupuesto y plazo.
6. Sensibilidad de costo y plazo.
7. Matriz de correlaciones opcional mediante Gaussian copula, validada por simetría y semidefinición positiva.
8. Corridas persistentes en `monte_carlo_runs`, con estado, progreso, seed, configuración, resultado, timestamps y error.
9. Idempotency-Key por tenant + hash de solicitud.
10. Reserva de consumo SaaS transaccional; upsert concurrente de `TenantUso`; compensación si Celery no acepta la tarea.
11. Umbral de jobs pesados ligado al plan.
12. Cancelación con protección de carrera PENDIENTE/CANCELADO/EN_PROCESO.
13. Celery es ejecutor; PostgreSQL es fuente de verdad.
14. CostOS deja de hacer una simulación local como fuente autoritativa: transforma sus riesgos de componentes a impactos relativos y consulta el backend.
15. Confianza seleccionada en UI se envía al backend; el cliente TypeScript acepta correlaciones.
16. Se corrigió una inconsistencia crítica de seed: el worker utiliza el seed persistido de la corrida, no un `42` oculto.
17. Se eliminó la dependencia `passlib`; auth usa `bcrypt` y `PyJWT` oficiales.
18. WebSocket ya no tiene `pass`; registra fallos de broadcast.

## Contratos de seguridad
- Todas las corridas están scopeadas por `tenant_id`.
- Presupuesto, programa y expediente se verifican dentro del tenant.
- Corridas >100,000 iteraciones requieren plan con jobs pesados.
- `Idempotency-Key` no puede reutilizarse con un request hash distinto.
- Resultado y estado se consultan desde DB; Celery no es autoridad del historial.

## Validación ejecutada
- `compileall` de backend/app + tests P1: PASS.
- `alembic heads`: `d5e8f7a1c2b3 (head)`.
- Suite pura Monte Carlo: **12/12 PASS**.
- Validación adicional de correlación: PASS.
- Validación de seed persistido/worker: PASS (test estático).
- Barrido del product path de Monte Carlo/Auth modificado: sin `pass`, `NotImplementedError` ni placeholder de probabilidad de plazo.

## Límites de esta ejecución
No se afirma que una infraestructura externa haya sido provisionada desde este sandbox. El cierre operacional definitivo todavía requiere ejecutar: `backend/scripts/install_production_deps.sh`, `pip check`, `alembic upgrade head` contra PostgreSQL/PostGIS real, Redis/Celery real, `npm ci`, typecheck/build y E2E/load. No se utilizaron mocks para cubrir esos gates.

## Dependencias
La fuente de verdad es `backend/pyproject.toml`. `passlib` fue eliminado; `bcrypt` y `PyJWT` quedan como dependencias oficiales. `aiosqlite` se conserva por soporte explícito de tests/desarrollo local, no como sustituto de PostgreSQL de producción.

## SHA-256 del árbol de trabajo
`d3b49bcf05e68a9e565cb255c3f2c744b0b07eef1b4d20f6482dd1e1a379863a`
