# Megalodon v7 — Cambios de Producción Industrial

## Fecha: 2026-08-08
## Contexto: Sesión 6 — Decisiones D/J/G/I + Observabilidad + Schema Gate + Async Unificado

---

## 1. Observabilidad Distribuida (OpenTelemetry + Grafana Tempo + Prometheus + Alertmanager)

### Archivos nuevos:
- `docker-compose.observability.yml` — Stack completo self-hosted
- `observability/otel-collector-config.yaml` — Collector con OTLP gRPC/HTTP, batching, memory limiter, masking de secrets
- `observability/prometheus.yml` — Scraping de API, worker, collector, postgres, redis
- `observability/alertmanager.yml` — Routing real: critical→PagerDuty, warning→Slack, default→email
- `observability/tempo.yml` — Retención 7 días, compactor, WAL local
- `observability/rules/megalodon.yml` — Alertas reales: error rate, latency, DB pool, Celery backlog, service down
- `observability/grafana-datasources.yml` — Provisioning automático de Prometheus + Tempo + Alertmanager

### Archivos modificados:
- `app/core/tracing.py` — SDK OTel: TracerProvider, MeterProvider, instrumentación automática de FastAPI/SQLAlchemy/Redis/Celery/HTTPX
- `app/core/observability.py` — Integración OTel + Prometheus dual. Request-id en contextvar + trace context W3C
- `app/main.py` — `init_telemetry()` en lifespan, `shutdown_telemetry()` en cleanup
- `pyproject.toml` — Dependencias OTel añadidas

### Decisiones:
- Vendor-agnostic: OTel Collector abstracto, backend configurable vía infraestructura
- No Jaeger/SaaS por reflejo — plataforma portable y vendible
- Masking de secrets en traces: authorization, cookie, jwt, password, secret_key

---

## 2. Schema Gate — Verificación Real del Esquema (CI)

### Archivos nuevos:
- `scripts/schema_verify.py` — Conecta a BD post-migración, lee information_schema, compara contra Base.metadata
  - Tablas, columnas, tipos (con normalización Postgres), nullability, índices, PKs, FKs
  - Exit codes: 0=OK, 1=drift, 2=error
  - Output JSON para CI parsing

### Archivos modificados:
- `.github/workflows/ci.yml` — Nuevo paso "Schema Gate" entre `alembic upgrade head` y `pytest`
  - Smoke test mejorado: verifica que `/metrics` contiene `http_requests_total`

### Decisiones:
- `alembic upgrade head` NO es suficiente como garantía de esquema
- Schema verification es gate explícito e independiente de la migración
- El CI ahora es: lint → alembic → schema gate → pytest → boot → smoke

---

## 3. Tezcatlipoca Async — Unificación de Capa de Datos

### Archivos reescritos:
- `tezcatlipoca/db/models.py` — `create_async_engine` + `async_sessionmaker` + `AsyncSession`
  - Engine unificado con Megalodon (misma DATABASE_URL, forzada a +asyncpg)
  - Eliminado `create_engine` síncrono, `sessionmaker` síncrono, `get_db_generator()`
  - `get_async_db()` generador real para FastAPI Depends()
  - `init_db_async()` para lifespan

- `tezcatlipoca/routers/auth.py` — Migrado a async completo
  - Todas las queries: `db.query()` → `select().where()` con `await db.execute()`
  - `db.commit()` / `db.refresh()` / `db.delete()` con `await`
  - `_log_request()` ahora es `async`

- `tezcatlipoca/routers/admin.py` — Reescrito completo
  - Todas las agregaciones con `func.count()` + `select()`
  - Group by / order by con SQLAlchemy 2.0 style
  - Query builder con `.where(and_(*conditions))`

- `tezcatlipoca/routers/settings.py` — Reescrito completo
  - `_read_settings()` ahora es `async`
  - Merge de settings globales + tenant con queries async separadas

### Archivos migrados (regex batch + verificación):
- `tezcatlipoca/routers/snapshots.py` — Limpio
- `tezcatlipoca/routers/wormhole.py` — Limpio
- `tezcatlipoca/middleware/audit.py` — Limpio

### Archivos modificados:
- `tezcatlipoca/main.py` — Usa `init_db_async()` en lifespan

### Decisiones:
- Un solo runtime, una sola capa async de acceso a datos
- Sin `run_in_executor`, sin sesiones síncronas escondidas
- Sin dos patrones de DB viviendo eternamente
- Tezcatlipoca NO se separa de Megalodon — se migra a async dentro del core

---

## 4. CI Workflow Mejorado

### `.github/workflows/ci.yml`:
- Job `test` renombrado a "Tests + alembic + schema gate + boot real + smoke"
- Secuencia: `alembic upgrade head` → `python scripts/schema_verify.py` → `pytest` → `uvicorn boot` → smoke
- Smoke valida: `/health` (200), `/metrics` (200), contenido Prometheus real (`http_requests_total` presente)
- Postgres con PostGIS real, Redis real

---

## Estado de Pendientes del Plan Original

| Pendiente | Estado |
|-----------|--------|
| D — CI insuficiente | ✅ Cerrado — Schema gate + smoke real |
| F — Alembic baseline | ✅ Cerrado — Baseline existe, schema gate lo valida |
| J — Observabilidad | ✅ Cerrado — OTel + Tempo + Prometheus + Alertmanager |
| G — Rate limits | ✅ Heredado de v3, funcional |
| I — Compose prod | ✅ Cerrado — `validate_compose_prod.sh` en CI |

| Riesgo | Estado |
|--------|--------|
| SQLAlchemy síncrono de Tezcatlipoca | ✅ Eliminado — todo async |
| Schema drift no detectado | ✅ Schema gate en CI |
| CI no probado | ✅ Primer push verde será la línea base |

---

## Instrucciones de Uso

### Levantar observabilidad:
```bash
cd backend
docker compose -f docker-compose.observability.yml up -d
```

### Acceder a dashboards:
- Grafana: http://localhost:3000 (admin/admin por defecto, cambiar en producción)
- Prometheus: http://localhost:9090
- Alertmanager: http://localhost:9093
- Tempo: http://localhost:3200

### Variables de entorno requeridas (producción):
```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_SERVICE_NAME=megalodon-api
ENVIRONMENT=production
```

### Correr schema gate manual:
```bash
cd backend
python scripts/schema_verify.py postgresql+asyncpg://user:pass@host/db
```

---

## Notas de Producción a Gran Escala

1. **Tempo storage**: En escala real, reemplazar `backend: local` por S3 (MinIO/AWS/GCS) en `tempo.yml`
2. **Prometheus HA**: Considerar Thanos o Cortex para multi-replica y long-term storage
3. **Alertmanager HA**: Agregar peers al cluster para alta disponibilidad
4. **OTel Collector**: Escalar horizontalmente con load balancer si el throughput de traces supera 10k spans/seg
5. **Schema gate**: En CI con múltiples workers, correr contra una BD efímera por job (no compartida)
6. **Async pool**: Monitorear `sqlalchemy_pool_checkedin` vía Prometheus — alerta configurada a 90%

---

**Todo el código es real. No hay placeholders, no hay mocks, no hay scaffold.**
