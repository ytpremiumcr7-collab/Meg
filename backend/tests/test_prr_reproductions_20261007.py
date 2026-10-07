from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.errors import MegalodonException
from app.engines.programacion.cpm import Actividad, MotorCPM, TipoDependencia
from app.models.expediente import ExpedienteObra
from app.models.procurement import TenderPackage, TenderState
from app.models.procurement_jobs import ProcurementJob
from app.models.programacion import ProgramaObra
from app.models.user import User, UserRole
from app.schemas.contrato import ContratoUpdate, ConvenioModificatorioCreate, EntregableCreate
from app.schemas.procurement.schemas import ApprovalCreate
from app.services.procurement.jobs import ProcurementJobService
from app.services.procurement.service import ProcurementService
from app.services.programacion_service import ProgramacionService


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


def _wire_successors(*activities: Actividad) -> None:
    by_id = {a.id: a for a in activities}
    for activity in activities:
        for predecessor in activity.predecesoras:
            if predecessor in by_id:
                by_id[predecessor].sucesoras.append(activity.id)


def test_cpm_project_duration_is_full_sequential_span_not_longest_activity():
    start = datetime(2026, 10, 7, 8, 0, 0)
    a = Actividad(id="A", nombre="A", duracion=2)
    b = Actividad(id="B", nombre="B", duracion=3, predecesoras=["A"])
    _wire_successors(a, b)
    motor = MotorCPM()
    motor.agregar_actividad(a)
    motor.agregar_actividad(b)

    result = motor.calcular_cpm(start, usar_calendario=False)

    assert result.duracion_total == 5


def test_cpm_honors_start_to_start_dependency():
    start = datetime(2026, 10, 7, 8, 0, 0)
    a = Actividad(id="A", nombre="A", duracion=4)
    b = Actividad(
        id="B",
        nombre="B",
        duracion=2,
        predecesoras=["A"],
        dependencias={"A": TipoDependencia.INICIO_INICIO},
    )
    _wire_successors(a, b)
    motor = MotorCPM()
    motor.agregar_actividad(a)
    motor.agregar_actividad(b)

    result = motor.calcular_cpm(start, usar_calendario=False)

    assert result.actividades["B"].inicio_temprano == start


def test_cpm_rejects_duplicate_activity_identifiers_instead_of_overwriting():
    motor = MotorCPM()
    motor.agregar_actividad(Actividad(id="A", nombre="primera", duracion=1))

    with pytest.raises(MegalodonException):
        motor.agregar_actividad(Actividad(id="A", nombre="segunda", duracion=9))


@pytest.mark.asyncio
async def test_pert_keeps_deterministic_predecessors_in_mixed_program():
    tenant_id = uuid4()
    db = SimpleNamespace(commit=AsyncMock())
    service = ProgramacionService(db, tenant_id)

    deterministic = SimpleNamespace(
        identificador="A",
        nombre="Deterministica",
        duracion=2,
        duracion_optimista=None,
        duracion_probable=None,
        duracion_pesimista=None,
        predecesoras=[],
    )
    probabilistic = SimpleNamespace(
        identificador="B",
        nombre="PERT",
        duracion=3,
        duracion_optimista=2,
        duracion_probable=3,
        duracion_pesimista=4,
        predecesoras=["A"],
    )
    program = SimpleNamespace(
        actividades=[deterministic, probabilistic],
        fecha_inicio_plan=datetime(2026, 10, 7, 8, 0, 0),
        resultado_pert=None,
    )
    service._validar_programa_en_expediente = AsyncMock(return_value=program)
    service._get_programa_con_actividades = AsyncMock(return_value=program)

    result = await service.calcular_pert(uuid4(), uuid4(), tenant_id=tenant_id)

    assert result.duracion_esperada >= 5


@pytest.mark.asyncio
async def test_crear_programa_rolls_back_persisted_rows_when_cpm_rejects_cycle(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    expediente = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="CPM-ATOMIC")
    db_session.add(expediente)
    await db_session.commit()
    await db_session.refresh(expediente)
    expediente_id = expediente.id
    tenant_id = tenant.id
    user_id = user.id

    service = ProgramacionService(db_session, tenant_id)

    with pytest.raises(MegalodonException):
        await service.crear_programa(
            expediente_id=expediente_id,
            nombre="Programa ciclico",
            fecha_inicio=datetime(2026, 10, 7, 8, 0, 0),
            actividades_data=[
                {"id": "A", "nombre": "A", "duracion": 2, "predecesoras": ["B"]},
                {"id": "B", "nombre": "B", "duracion": 3, "predecesoras": ["A"]},
            ],
            creado_por_id=user_id,
            tenant_id=tenant_id,
        )

    persisted = (
        await db_session.execute(
            select(ProgramaObra).where(
                ProgramaObra.expediente_id == expediente_id,
                ProgramaObra.tenant_id == tenant_id,
            )
        )
    ).scalars().all()
    assert persisted == []


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
    assert job.status == "PENDING"
    assert job.task_id == str(job.id)

    published_task_ids = []

    def broker_accepts(*_args, **kwargs):
        published_task_ids.append(kwargs["task_id"])
        return SimpleNamespace(id=kwargs["task_id"])

    monkeypatch.setattr(
        "app.services.procurement.jobs.celery_app.send_task",
        broker_accepts,
    )
    replayed_job, replayed = await ProcurementJobService(
        db_session, user
    ).create_or_replay(
        tender,
        "RUN",
        "audit-crash-window",
    )

    assert replayed is True
    assert replayed_job.id == job.id
    assert replayed_job.status == "QUEUED"
    assert replayed_job.task_id == str(job.id)
    assert published_task_ids == [str(job.id)]


@pytest.mark.parametrize(
    ("factory", "payload"),
    [
        (ContratoUpdate, {"monto_total": -1, "plazo_dias": -1}),
        (
            ConvenioModificatorioCreate,
            {
                "numero": "AUD-1",
                "tipo": "MONTO",
                "monto_nuevo": -1,
                "plazo_nuevo": -1,
            },
        ),
        (
            EntregableCreate,
            {
                "numero_estimacion": 1,
                "monto_ejecutado": -1,
                "avance_fisico": 1,
                "avance_financiero": 1,
            },
        ),
    ],
)
def test_contract_domain_rejects_negative_money_and_duration(factory, payload):
    with pytest.raises(ValidationError):
        factory(**payload)
