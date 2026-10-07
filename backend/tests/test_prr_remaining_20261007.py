from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.errors import MegalodonException
from app.models.expediente import ExpedienteObra
from app.models.procurement import TenderPackage, TenderState
from app.models.procurement_jobs import ProcurementJob
from app.models.user import User, UserRole
from app.schemas.contrato import ContratoUpdate, ConvenioModificatorioCreate, EntregableCreate
from app.schemas.procurement.schemas import ApprovalCreate
from app.services.procurement.jobs import ProcurementJobService
from app.services.procurement.service import ProcurementService


def _expediente(*, tenant_id, user_id, suffix: str) -> ExpedienteObra:
    return ExpedienteObra(
        tenant_id=tenant_id,
        creado_por_id=user_id,
        actualizado_por_id=user_id,
        identificador=f"AUDIT-{suffix}-{uuid4().hex[:8]}",
        titulo=f"Auditoria {suffix}",
        organo="ORG TEST",
        unidad_administrativa="UA TEST",
        serie_documental="OBRA_PUBLICA",
        subserie_documental="LICITACION",
        responsable_id=user_id,
    )


@pytest.mark.asyncio
async def test_one_reviewer_cannot_satisfy_two_distinct_procurement_approval_roles(
    db_session, tenant_a_user
):
    tenant, creator = tenant_a_user
    reviewer = User(
        email=f"audit-reviewer-{uuid4().hex[:8]}@example.mx",
        hashed_password="not-used",
        full_name="Audit Reviewer",
        role=UserRole.REVISOR,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    db_session.add(reviewer)
    expediente = _expediente(tenant_id=tenant.id, user_id=creator.id, suffix="APPROVAL")
    db_session.add(expediente)
    await db_session.flush()
    tender = TenderPackage(
        tenant_id=tenant.id,
        creado_por_id=creator.id,
        actualizado_por_id=creator.id,
        expediente_id=expediente.id,
        identifier=f"AUD-APP-{uuid4().hex[:8]}",
        title="Approval segregation audit",
        state=TenderState.QA_READY.value,
        canonical_model={"approvals": {"required_roles": ["LEGAL", "FINANCE"]}},
        current_revision=1,
    )
    db_session.add(tender)
    await db_session.commit()
    await db_session.refresh(reviewer)
    await db_session.refresh(tender)

    service = ProcurementService(db_session, reviewer)
    await service.approval(
        tender.id,
        ApprovalCreate(role="LEGAL", decision="APPROVED"),
    )

    with pytest.raises(MegalodonException):
        await service.approval(
            tender.id,
            ApprovalCreate(role="FINANCE", decision="APPROVED"),
        )


@pytest.mark.asyncio
async def test_procurement_job_cannot_remain_queued_without_broker_publication(
    db_session, tenant_a_user, monkeypatch
):
    tenant, user = tenant_a_user
    expediente = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="OUTBOX")
    db_session.add(expediente)
    await db_session.flush()
    tender = TenderPackage(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        expediente_id=expediente.id,
        identifier=f"AUD-JOB-{uuid4().hex[:8]}",
        title="Durable publication audit",
        state=TenderState.QA_READY.value,
        canonical_model={"facts": {"audit": True}},
        current_revision=1,
    )
    db_session.add(tender)
    await db_session.commit()
    await db_session.refresh(tender)

    def crash_after_database_commit(*_args, **_kwargs):
        raise SystemExit("simulated process death before broker publication")

    monkeypatch.setattr(
        "app.services.procurement.jobs.celery_app.send_task",
        crash_after_database_commit,
    )

    with pytest.raises(SystemExit):
        await ProcurementJobService(db_session, user).create_or_replay(
            tender,
            "RUN",
            "audit-crash-window",
        )

    job = await db_session.scalar(
        select(ProcurementJob).where(
            ProcurementJob.tender_id == tender.id,
            ProcurementJob.tenant_id == tenant.id,
        )
    )
    assert job is not None
    assert not (job.status == "QUEUED" and job.task_id is None)


def test_contract_update_rejects_negative_total_and_duration():
    with pytest.raises(ValidationError):
        ContratoUpdate(monto_total=-1, plazo_dias=-1)


def test_contract_amendment_rejects_negative_total_and_duration():
    with pytest.raises(ValidationError):
        ConvenioModificatorioCreate(
            numero="AUD-1",
            tipo="MONTO",
            monto_nuevo=-1,
            plazo_nuevo=-1,
        )


def test_contract_estimate_rejects_negative_executed_amount():
    with pytest.raises(ValidationError):
        EntregableCreate(
            numero_estimacion=1,
            monto_ejecutado=-1,
            avance_fisico=1,
            avance_financiero=1,
        )
