# Procurement V6 — Baseline Audit & SaaS Hardening

## Baseline

Source: `MEGALODON_PRODUCTION_PROCUREMENT_V6_REPACK_2026-08-11.zip`.

The ZIP is internally valid (`unzip -t` PASS) and contains 752 files before cleanup. The new procurement surface consists of:

- `backend/app/api/v1/procurement.py`
- `backend/app/services/procurement/service.py`
- `backend/app/models/procurement.py`
- `backend/app/engines/procurement/*`
- `backend/app/schemas/procurement/*`
- procurement Alembic migrations
- `frontend/app/src/apps/licitaciones-obra/components/TenderAutomationPanel.tsx`

Existing modules deliberately kept out of the refactor boundary: Licitacion/Fallo/PreFall, CostOS, CPM, BIM, Topografía, Monte Carlo, Firma and Tezcatlipoca integration.

## Findings before modification

1. The Procurement API was mounted independently at `/api/v1/procurement`; no existing route was replaced.
2. Several write endpoints lacked route-level RBAC dependencies even though the service had tenant scoping.
3. `UploadFile.read()` loaded the complete file before enforcing the configured maximum; that is unsafe for large SaaS uploads.
4. Tender listing was unbounded and had no pagination.
5. Approval creation had an application-level uniqueness check but no database uniqueness constraint, so concurrent approval requests could race.
6. Tender aggregate updates had no optimistic concurrency control.
7. The domain already had tenant predicates, but race-safe handling for version conflicts was absent.
8. The frontend Procurement panel uses the existing `megalodonClient.procurement` contract and does not replace the legacy licitaciones routes.
9. Alembic procurement chain was linear through `20260811_procurement_v6_jurisdiction_funding`.
10. The packaged baseline contained `__pycache__` artifacts; these are excluded from the production package.

## Hardening applied

### Concurrency

- Added `TenderPackage.row_version` and SQLAlchemy optimistic locking.
- Added a production migration.
- Tender approval execution acquires `FOR UPDATE` on the aggregate.
- Approval role/revision is database-unique.
- `StaleDataError` is translated into HTTP-domain conflict semantics instead of becoming a 500.

### SaaS isolation

- Existing tenant predicates remain in place.
- No cross-tenant route was introduced.
- New write endpoints preserve tenant-scoped service enforcement.

### Ingestion

- Uploads are streamed in bounded chunks and rejected at the configured limit before accumulating more data.
- Existing content hashing and storage idempotency are preserved.

### Query scalability

- Tender listing now accepts bounded `offset`/`limit` while preserving the previous list response shape.
- Maximum page size is capped at 500.

### Regression strategy

No legacy licitaciones route, engine or module is replaced by this change. Changes are limited to the Procurement domain boundary, its persistence schema, and its route authorization.

## Verification

- `python -m py_compile` on modified Python modules: PASS.
- `compileall` on Procurement/application target: PASS.
- Direct Procurement lifecycle/rule smoke test: PASS.
- Full pytest collection is blocked in this sandbox because `structlog` is not installed in the application environment.
- SQLAlchemy runtime mapper verification is blocked because `aiosqlite` is not installed in this sandbox.
- These environment limitations are not represented as production PASS.

## Production gates still requiring real infrastructure

- PostgreSQL migration execution and rollback rehearsal.
- PostgreSQL concurrency test with concurrent approvals and aggregate edits.
- Redis/Celery worker execution and retry/idempotency tests.
- Supabase Storage upload/download and signed artifact tests.
- Full HTTP E2E with real authentication/tenant/RBAC.
- Frontend production build in the repository's intended Node environment.
- Load, DR/restore and multi-tenant adversarial tests.

No mock/stub/demo replacement was introduced to mask any of these gates.
