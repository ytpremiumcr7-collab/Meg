# Verificación Structlog + Alembic/PostgreSQL + FKs compuestas + npm build
**Fecha:** 2026-08-26  
**Baseline:** MEGALODON_V7_P0P1_HARDENED_CORREGIDO_2026-08-26

## 1. Structlog

| Item | Estado | Evidencia |
|------|--------|-----------|
| Declarado en `backend/pyproject.toml` | **VERIFICADO** | `"structlog>=24.4.0"` línea ~97 |
| Uso en código | **VERIFICADO** | `backend/app/utils/logging.py` importa y configura `structlog` con processors JSON + contextvars |
| Instalación runtime en sandbox | **PARCIAL** | Se instaló `structlog==26.1.0` vía `pip install --user` en sesión efímera. En entrega: dependencia declarada; el usuario debe `pip install -e ".[dev]"` o `pip install structlog` en su entorno. |

**Acción requerida en destino:**  
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -c "import structlog; print(structlog.__version__)"
```

## 2. PostgreSQL + alembic upgrade head

| Item | Estado | Evidencia |
|------|--------|-----------|
| `alembic.ini` + `alembic/env.py` | **VERIFICADO** | Usa `app.config.settings`, importa `app.models` completo, async engine |
| Cadena de migraciones | **VERIFICADO** | Incluye `20260826_rule_execution_tenant_hardening` con FKs compuestas |
| Ejecución real `alembic upgrade head` en sandbox | **ROT O / INCOMPLETO** | Sandbox: 1.2 GiB RAM, sin Docker, servicios no persistentes entre resets de sesión. Se instaló PostgreSQL 16, se creó rol/db `megalodon`, se inició `alembic upgrade head` (Context impl PostgresqlImpl, transactional DDL). Proceso no completó antes de reset de sesión. |

**Script de verificación local (cuando haya PG real):** ver `scripts/verify_alembic_and_composite_fks.sh`

## 3. FKs compuestas (tenant integrity)

**VERIFICADO en código** (migración `20260826_rule_execution_tenant_hardening.py`):

```python
op.create_unique_constraint("uq_tender_packages_tenant_id", "tender_packages", ["tenant_id", "id"])
# ... similar para requirements, evidence, validation_runs, rule_definitions

op.create_foreign_key(
    "fk_tender_rule_def_tenant_tender", "tender_rule_definitions", "tender_packages",
    ["tenant_id", "tender_id"], ["tenant_id", "id"], ondelete="CASCADE",
)
# + fk_tender_rule_def_tenant_requirement
# + fk_validation_run_tenant_tender
# + fk_validation_evidence_link_tenant_validation
# + fk_validation_evidence_link_tenant_evidence
# + fk_rule_execution_tenant_tender
# + fk_rule_execution_tenant_requirement
# + fk_rule_execution_tenant_definition
# + fk_rule_execution_tenant_validation
```

**Prueba real en PostgreSQL:** **NO EJECUTADA** en este sandbox (sin DB persistente post-migración).  
El script `scripts/verify_composite_fks_postgres.sql` + shell permite validar en destino:

1. Existencia de constraints multi-columna.
2. Rechazo de INSERT con `tenant_id` inconsistente (cross-tenant).
3. Cascade / RESTRICT según definición.

## 4. Frontend: node_modules + npm run build

| Item | Estado |
|------|--------|
| `package.json` | **VERIFICADO** (React 19, Vite, etc.) |
| `npm install` | **PARCIAL** en sandbox (~350 paquetes al corte; memoria limitada) |
| `npm run build` | **NO EJECUTADO** (depende de install completo) |

**En destino:**
```bash
cd frontend/app
npm ci   # o npm install
npm run build
```

## 5. Limitaciones del entorno de verificación

- RAM ~1.2 GiB, sin swap → builds pesados (opencv, geopandas, ifcopenshell, full node_modules) fallan o matan sesión.
- Sin Docker disponible de forma estable.
- Sesiones de sandbox se reinician → paquetes y servicios no persisten.
- Por tanto: **código y dependencias declaradas VERIFICADOS**; **runtime completo de alembic upgrade + tests FK + npm build** debe ejecutarse en máquina del usuario / CI / VPS con ≥4–8 GiB y PostgreSQL 16 + PostGIS.

## 6. Criterio de éxito para la siguiente ronda

1. `pip install -e ".[dev]"` sin error y `import structlog` OK.
2. `alembic upgrade head` contra PostgreSQL 16 real → head = última revisión 20260826_*.
3. Query `pg_constraint` muestra los 9 FKs compuestas.
4. Test SQL: INSERT cross-tenant fallan con FK violation.
5. `npm run build` exit 0 y `dist/` generado.

