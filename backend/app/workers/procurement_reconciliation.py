from __future__ import annotations
import asyncio
from app.workers.celery_app import celery_app
from app.services.procurement.storage_guard import ProcurementStorageGuard

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300, retry_kwargs={"max_retries": 5}, acks_late=True)
def reconcile_procurement_storage(self):
    return asyncio.run(ProcurementStorageGuard().reconcile(max_rows=250))
