from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.models.base import AsyncSessionLocal
from app.models.procurement_jobs import ProcurementJob
from app.models.user import User
from app.services.procurement.service import ProcurementService
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, acks_late=True, reject_on_worker_lost=True, track_started=True)
def execute_job(self, job_id: str, user_id: str, tenant_id: str, tender_id: str):
    return asyncio.run(_execute(job_id, user_id, tenant_id, tender_id))


async def _execute(job_id: str, user_id: str, tenant_id: str, tender_id: str):
    async with AsyncSessionLocal() as db:
        job = await db.scalar(select(ProcurementJob).where(
            ProcurementJob.id == UUID(job_id), ProcurementJob.tenant_id == UUID(tenant_id)
        ).with_for_update())
        if job is None:
            raise RuntimeError("Procurement job no encontrado")
        if job.status == "SUCCEEDED":
            return job.result
        job.status = "RUNNING"
        job.progress = 5
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        user = await db.get(User, UUID(user_id))
        if user is None or user.tenant_id != UUID(tenant_id):
            job.status = "FAILED"
            job.error_code = "TENANT_CONTEXT_INVALID"
            job.error_message = "El usuario del job no pertenece al tenant esperado."
            job.finished_at = datetime.now(timezone.utc)
            await db.commit()
            raise RuntimeError(job.error_message)

        service = ProcurementService(db, user)
        try:
            if job.kind == "RUN":
                result = await service.run(UUID(tender_id))
            elif job.kind == "COMPILE":
                rows = await service.compile_artifacts(UUID(tender_id))
                result = {"artifacts": [{"id": str(r.id), "code": r.artifact_code, "version": r.version, "storage_path": r.storage_path, "content_hash": r.content_hash} for r in rows]}
            else:
                raise RuntimeError(f"Tipo de job no soportado: {job.kind}")
            job.result = result
            job.status = "SUCCEEDED"
            job.progress = 100
            job.finished_at = datetime.now(timezone.utc)
            job.error_code = None
            job.error_message = None
            await db.commit()
            return result
        except Exception as exc:
            await db.rollback()
            job = await db.scalar(select(ProcurementJob).where(ProcurementJob.id == UUID(job_id), ProcurementJob.tenant_id == UUID(tenant_id)).with_for_update())
            if job is not None:
                job.status = "FAILED"
                job.progress = 100
                job.error_code = type(exc).__name__
                job.error_message = str(exc)[:4000]
                job.finished_at = datetime.now(timezone.utc)
                await db.commit()
            raise
