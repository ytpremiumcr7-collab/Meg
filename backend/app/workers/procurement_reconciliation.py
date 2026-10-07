from __future__ import annotations

import asyncio

from app.models.base import AsyncSessionLocal
from app.services.procurement.jobs import ProcurementJobService
from app.services.procurement.storage_guard import ProcurementStorageGuard
from app.workers.celery_app import celery_app


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_kwargs={"max_retries": 5},
    acks_late=True,
)
def reconcile_procurement_storage(self):
    return asyncio.run(ProcurementStorageGuard().reconcile(max_rows=250))


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_kwargs={"max_retries": 5},
    acks_late=True,
)
def reconcile_procurement_jobs(self):
    return asyncio.run(_reconcile_procurement_jobs())


async def _reconcile_procurement_jobs() -> int:
    async with AsyncSessionLocal() as db:
        return await ProcurementJobService.reconcile_pending(db, limit=100)
