from __future__ import annotations

from hashlib import sha256
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, MegalodonException
from app.models.procurement import TenderPackage
from app.models.procurement_jobs import ProcurementIdempotency, ProcurementJob
from app.models.user import User
from app.workers.celery_app import celery_app


class ProcurementJobService:
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user

    @staticmethod
    def request_hash(*, tender_id: UUID, kind: str, revision: int, model_hash: str) -> str:
        payload = {"tender_id": str(tender_id), "kind": kind, "revision": revision, "model_hash": model_hash}
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    async def create_or_replay(self, tender: TenderPackage, kind: str, idempotency_key: str | None = None) -> tuple[ProcurementJob, bool]:
        effective_key = (idempotency_key or f"derived:{kind}:{tender.id}:r{tender.current_revision}:{sha256(json.dumps(tender.canonical_model, sort_keys=True, default=str).encode()).hexdigest()}")[:128]
        request_hash = self.request_hash(
            tender_id=tender.id,
            kind=kind,
            revision=tender.current_revision,
            model_hash=sha256(json.dumps(tender.canonical_model, sort_keys=True, default=str).encode()).hexdigest(),
        )
        existing = await self.db.scalar(select(ProcurementIdempotency).where(
            ProcurementIdempotency.tenant_id == self.user.tenant_id,
            ProcurementIdempotency.key == effective_key,
        ))
        if existing is not None:
            if existing.request_hash != request_hash:
                raise MegalodonException(ErrorCode.CONFLICT, "La Idempotency-Key ya fue utilizada para otra operación.", 409)
            job = await self.db.get(ProcurementJob, existing.job_id)
            if job is None:
                raise MegalodonException(ErrorCode.ARCHIVO_ERROR, "Registro de idempotencia huérfano; requiere reconciliación administrativa.", 500)
            return job, True

        job = ProcurementJob(
            tenant_id=self.user.tenant_id,
            creado_por_id=self.user.id,
            actualizado_por_id=self.user.id,
            tender_id=tender.id,
            kind=kind,
            status="PENDING",
            idempotency_key=effective_key,
            request_hash=request_hash,
            progress=0,
        )
        self.db.add(job)
        try:
            await self.db.flush()
            idem = ProcurementIdempotency(
                tenant_id=self.user.tenant_id,
                key=effective_key,
                request_hash=request_hash,
                job_id=job.id,
            )
            self.db.add(idem)
            job.status = "QUEUED"
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            existing = await self.db.scalar(select(ProcurementIdempotency).where(
                ProcurementIdempotency.tenant_id == self.user.tenant_id,
                ProcurementIdempotency.key == effective_key,
            ))
            if existing is not None:
                job = await self.db.get(ProcurementJob, existing.job_id)
                if job is not None:
                    return job, True
            raise
        except Exception:
            await self.db.rollback()
            raise
        try:
            task = celery_app.send_task(
                "app.workers.procurement_tasks.execute_job",
                args=[str(job.id), str(self.user.id), str(self.user.tenant_id), str(tender.id)],
                task_id=str(uuid4()),
            )
            job.task_id = task.id
            await self.db.commit()
        except Exception as exc:
            job.status = "FAILED"
            job.error_code = "ENQUEUE_FAILED"
            job.error_message = str(exc)[:4000]
            await self.db.commit()
            raise MegalodonException(ErrorCode.ARCHIVO_ERROR, "No se pudo encolar el job de Procurement.", 503) from exc
        await self.db.refresh(job)
        return job, False

    async def get(self, job_id: UUID) -> ProcurementJob:
        job = await self.db.scalar(select(ProcurementJob).where(
            ProcurementJob.id == job_id,
            ProcurementJob.tenant_id == self.user.tenant_id,
        ))
        if job is None:
            raise MegalodonException(ErrorCode.TAREA_NO_ENCONTRADA, "Job de Procurement no encontrado.", 404)
        return job
