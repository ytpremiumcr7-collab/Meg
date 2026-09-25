# Megalodon + Tezcatlipoca — Cierre de fase industrial 2026-08-10

## Alcance
Esta fase parte directamente de `MEGALODON_TEZCATLIPOCA_UPDATED_V3.zip`.
No se eliminó ningún archivo presente en V3.

## Cambios aplicados

### Dependencias
- `backend/pyproject.toml` queda como única fuente de dependencias del backend.
- `backend/tezcatlipoca/requirements.txt` queda como entrypoint de compatibilidad que instala el proyecto unificado; ya no mantiene un segundo universo de versiones.
- Se eliminó la dependencia directa `aioredis`, porque el código usa `redis.asyncio` del paquete `redis` unificado.
- Se eliminó la declaración duplicada de `python-multipart`.

### Runtime
- Dockerfile endurecido:
  - usuario no-root UID/GID 10001;
  - imagen runtime sin extras de desarrollo;
  - `PYTHONDONTWRITEBYTECODE`;
  - healthcheck real contra `/health`;
  - proxy headers configurados;
  - permisos explícitos de runtime.
- Compose de producción:
  - healthchecks reales para PostgreSQL, Redis y MinIO;
  - dependencias de arranque condicionadas por salud;
  - OpenTelemetry Collector integrado como servicio interno.
- Collector OTel fijado a `0.157.0`, versión documentada oficialmente por OpenTelemetry a julio de 2026.

### Observabilidad
- Se eliminó el fallback/no-op de OpenTelemetry en `app/core/tracing.py`.
- La instrumentación FastAPI, SQLAlchemy, Redis, Celery y HTTPX usa directamente los paquetes declarados.
- Collector recibe OTLP por gRPC/HTTP y reenvía mediante OTLP/HTTP al backend de observabilidad configurado.
- La configuración exige `OTEL_BACKEND_ENDPOINT` en producción.

### DR
- `backend/scripts/backup_postgres.sh`
  - dump custom de PostgreSQL;
  - permisos restrictivos;
  - checksum SHA-256.
- `backend/scripts/restore_postgres.sh`
  - verifica checksum cuando existe;
  - restaura con `pg_restore`;
  - falla ante errores.
- `backend/.env.production.example` documenta secretos y endpoints necesarios.

### Security pipeline
- `.github/workflows/security-hardening.yml`:
  - `pip check`;
  - `pip-audit --strict`;
  - CodeQL;
  - `npm audit`;
  - build frontend.
- `backend/scripts/generate_sbom.sh` genera CycloneDX con Syft.

## Verificaciones realizadas
- `compileall` de `backend/app` y `backend/tezcatlipoca`: OK.
- Comparación contra V3:
  - archivos en V3: 969;
  - archivos actuales: 1020;
  - archivos de V3 eliminados: **0**.
- Se añadió funcionalidad/configuración; no se sustituyó el árbol existente por un scaffold.
- El intento de `npm ci` no pudo completarse dentro del límite de ejecución del entorno de auditoría; por tanto NO se declara el build frontend clean-room como verificado.

## Pendientes que siguen siendo honestamente abiertos
1. Ejecutar build Docker real con Docker/BuildKit.
2. Resolver instalación limpia frontend en un entorno con red/cache suficiente.
3. Ejecutar `pip-audit`, CodeQL y SBOM en CI real.
4. Probar backup + restore contra una instancia PostgreSQL real.
5. Configurar un backend OTLP real (Tempo/Grafana Cloud/Jaeger/vendor) mediante `OTEL_BACKEND_ENDPOINT`.
6. Pruebas de carga distribuidas y HA/DR completas.
7. Vertical slice físico completo: AOI → observación → levantamiento → topografía → BIM → CostOS → evidencia → auditoría.

## Criterio
Esta fase endurece la plataforma sin convertirla en demo. Los puntos pendientes no se marcan como completados hasta haber sido ejecutados en infraestructura real.
