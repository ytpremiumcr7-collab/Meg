from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
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
from app.models.documento import DocumentoCDE, TipoDocumento
from app.models.topografia import Levantamiento, SuperficieTIN
from app.models.licitacion import Licitacion, EstadoLicitacion, TipoProcedimiento
from app.models.contrato import Contrato, EstadoContrato, EntregableContrato, TipoModificacion
from app.models.proveedor import Proveedor, TipoPersona
from app.models.montecarlo import MonteCarloRun, EstadoMonteCarlo
from app.models.audit_ledger import TipoAccion
from app.models.user import User, UserRole
from app.schemas.contrato import ContratoUpdate, ConvenioModificatorioCreate, EntregableCreate
from app.schemas.licitacion import LicitacionUpdate
from app.schemas.compliance import InconformidadCreate, SancionCreate
from app.schemas.procurement.schemas import ApprovalCreate
from app.services.procurement.jobs import ProcurementJobService
from app.services.procurement.service import ProcurementService
from app.services.programacion_service import ProgramacionService
from app.modules.documentos.service import DocumentoModuleService
from app.modules.search.service import SearchService
from app.services.topografia_service import TopografiaService
from app.services.documento_service import DocumentoService
from app.services.licitacion_service import LicitacionService
from app.services.contrato_service import ContratoService
from app.services.compliance_service import ComplianceService
from app.services.montecarlo_service import MonteCarloService
from app.modules.audit.service import AuditService
from app.services.expediente_service import ExpedienteService
from app.workers.procurement_tasks import _execute as execute_procurement_job
from app.services.firma_service import FirmaService


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


@pytest.mark.xfail(reason="RED confirmado: duracion_total usa la actividad mas larga", strict=False)
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


@pytest.mark.xfail(reason="RED confirmado: SS se ejecuta como FS", strict=False)
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


@pytest.mark.xfail(reason="RED confirmado: IDs duplicados se sobrescriben", strict=False)
def test_cpm_rejects_duplicate_activity_identifiers_instead_of_overwriting():
    motor = MotorCPM()
    motor.agregar_actividad(Actividad(id="A", nombre="primera", duracion=1))

    with pytest.raises(MegalodonException):
        motor.agregar_actividad(Actividad(id="A", nombre="segunda", duracion=9))


@pytest.mark.xfail(reason="RED confirmado: PERT descarta predecesores deterministas", strict=False)
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


@pytest.mark.xfail(reason="RED confirmado: crear_programa persiste antes de validar CPM", strict=False)
@pytest.mark.asyncio
async def test_crear_programa_rolls_back_persisted_rows_when_cpm_rejects_cycle(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    expediente = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="CPM-ATOMIC")
    db_session.add(expediente)
    await db_session.commit()
    await db_session.refresh(expediente)

    service = ProgramacionService(db_session, tenant.id)

    with pytest.raises(MegalodonException):
        await service.crear_programa(
            expediente_id=expediente.id,
            nombre="Programa ciclico",
            fecha_inicio=datetime(2026, 10, 7, 8, 0, 0),
            actividades_data=[
                {"id": "A", "nombre": "A", "duracion": 2, "predecesoras": ["B"]},
                {"id": "B", "nombre": "B", "duracion": 3, "predecesoras": ["A"]},
            ],
            creado_por_id=user.id,
            tenant_id=tenant.id,
        )

    persisted = (
        await db_session.execute(
            select(ProgramaObra).where(
                ProgramaObra.expediente_id == expediente.id,
                ProgramaObra.tenant_id == tenant.id,
            )
        )
    ).scalars().all()
    assert persisted == []


@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: un revisor satisface multiples roles logicos", strict=False)
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


@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: ventana commit QUEUED antes de broker", strict=False)
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


@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: contratos aceptan dinero/plazos negativos", strict=False)
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



@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: CDE valida documentos_cde pero servicio consulta Documento legacy", strict=False)
@pytest.mark.asyncio
async def test_cde_classification_operates_on_documentos_cde_not_legacy_documentos(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    expediente = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="CDE-TABLE")
    db_session.add(expediente)
    await db_session.flush()
    cde = DocumentoCDE(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        expediente_id=expediente.id,
        nombre="anexo-tecnico.pdf",
        descripcion="Documento CDE de auditoria",
        tipo=TipoDocumento.OTRO,
        version=1,
        metadatos={},
    )
    db_session.add(cde)
    await db_session.commit()
    await db_session.refresh(cde)

    result = await DocumentoModuleService(db_session).clasificar_documento(
        cde.id,
        tipo_sugerido=TipoDocumento.ANEXO_TECNICO,
        confianza=0.99,
    )

    assert result.id == cde.id
    assert result.tipo == TipoDocumento.ANEXO_TECNICO


@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: volumen topografico acepta superficies de expedientes distintos", strict=False)
@pytest.mark.asyncio
async def test_topography_rejects_volume_between_surfaces_from_different_expedientes(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    exp_a = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="TOPO-A")
    exp_b = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="TOPO-B")
    db_session.add_all([exp_a, exp_b])
    await db_session.flush()

    lev_a = Levantamiento(
        expediente_id=exp_a.id,
        identificador=f"LEV-A-{uuid4().hex[:6]}",
        nombre="Levantamiento A",
        creado_por_id=user.id,
        actualizado_por_id=user.id,
    )
    lev_b = Levantamiento(
        expediente_id=exp_b.id,
        identificador=f"LEV-B-{uuid4().hex[:6]}",
        nombre="Levantamiento B",
        creado_por_id=user.id,
        actualizado_por_id=user.id,
    )
    db_session.add_all([lev_a, lev_b])
    await db_session.flush()

    def surface(expediente_id, levantamiento_id, nombre, z):
        return SuperficieTIN(
            expediente_id=expediente_id,
            levantamiento_id=levantamiento_id,
            nombre=nombre,
            tipo="EXISTENTE",
            malla_vertices=[0.0, 0.0, z, 10.0, 0.0, z, 0.0, 10.0, z],
            malla_caras=[0, 1, 2],
            area_plan_m2=50,
            area_superficie_m2=50,
            elevacion_min=z,
            elevacion_max=z,
            elevacion_media=z,
            pendiente_media_pct=0,
            num_puntos=3,
            num_triangulos=1,
            creado_por_id=user.id,
            actualizado_por_id=user.id,
        )

    sup_a = surface(exp_a.id, lev_a.id, "Terreno expediente A", 0.0)
    sup_b = surface(exp_b.id, lev_b.id, "Proyecto expediente B", 1.0)
    db_session.add_all([sup_a, sup_b])
    await db_session.commit()
    await db_session.refresh(sup_a)
    await db_session.refresh(sup_b)

    service = TopografiaService(db_session, tenant.id)
    with pytest.raises(MegalodonException):
        await service.calcular_volumen(
            superficie_existente_id=sup_a.id,
            superficie_proyecto_id=sup_b.id,
            creado_por_id=user.id,
        )



@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: busqueda usa Licitacion.numero_licitacion inexistente", strict=False)
@pytest.mark.asyncio
async def test_global_search_uses_real_licitacion_folio_field(db_session, tenant_a_user):
    tenant, _user = tenant_a_user

    result = await SearchService(db_session).busqueda_global(
        "sin-resultados-audit",
        dominios=["licitaciones"],
        tenant_id=tenant.id,
    )

    assert result["total"] == 0
    assert result["total_por_dominio"]["licitaciones"] == 0


@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: Documento legacy recibe tenant_id inexistente", strict=False)
@pytest.mark.asyncio
async def test_legacy_document_upload_persists_without_passing_unknown_tenant_field(
    db_session, tenant_a_user, monkeypatch
):
    tenant, user = tenant_a_user
    expediente = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="DOC-UPLOAD")
    db_session.add(expediente)
    await db_session.commit()
    await db_session.refresh(expediente)

    fake_storage = SimpleNamespace(
        bucket="audit-documents",
        subir=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.documento_service.storage_documentos",
        lambda: fake_storage,
    )

    documento = await DocumentoService(db_session, tenant.id).subir_documento(
        expediente_id=expediente.id,
        file_content=b"contenido-auditoria",
        filename="evidencia.txt",
        tipo_documental="OTRO",
        cifrar=False,
        tenant_id=str(tenant.id),
        creado_por_id=user.id,
    )

    assert documento.expediente_id == expediente.id



@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: PATCH licitacion evita la maquina de estados", strict=False)
@pytest.mark.asyncio
async def test_licitacion_patch_cannot_bypass_lifecycle_machine(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    expediente = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="LIC-STATE")
    db_session.add(expediente)
    await db_session.flush()
    lic = Licitacion(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        expediente_id=expediente.id,
        folio=f"AUD-LIC-{uuid4().hex[:8]}",
        jurisdiction_code="AUDIT",
        tipo_procedimiento=TipoProcedimiento.LICITACION_PUBLICA,
        estado=EstadoLicitacion.PLANEACION,
        objeto="Auditoria de maquina de estados",
    )
    db_session.add(lic)
    await db_session.commit()
    await db_session.refresh(lic)

    with pytest.raises(MegalodonException):
        await LicitacionService().actualizar(
            db_session,
            lic.id,
            LicitacionUpdate(
                estado=EstadoLicitacion.FALLO,
                jurisdiction_code="AUDIT",
            ),
            user,
        )

    await db_session.refresh(lic)
    assert lic.estado == EstadoLicitacion.PLANEACION


@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: PATCH contrato evita la maquina de estados", strict=False)
@pytest.mark.asyncio
async def test_contract_patch_cannot_bypass_lifecycle_machine(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    expediente = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="CONTRACT-STATE")
    proveedor = Proveedor(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        tipo_persona=TipoPersona.MORAL,
        rfc=f"AUD{uuid4().hex[:10].upper()}"[:13],
        razon_social="Proveedor Auditoria",
    )
    db_session.add_all([expediente, proveedor])
    await db_session.flush()
    contrato = Contrato(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        expediente_id=expediente.id,
        proveedor_id=proveedor.id,
        numero_contrato=f"AUD-C-{uuid4().hex[:8]}",
        estado=EstadoContrato.EN_FIRMA,
        objeto="Contrato auditoria",
        monto_total=1000,
        monto_original=1000,
        plazo_dias=10,
        plazo_original=10,
    )
    db_session.add(contrato)
    await db_session.commit()
    await db_session.refresh(contrato)

    with pytest.raises(MegalodonException):
        await ContratoService().actualizar(
            db_session,
            contrato.id,
            ContratoUpdate(estado=EstadoContrato.TERMINADO),
            user,
        )

    await db_session.refresh(contrato)
    assert contrato.estado == EstadoContrato.EN_FIRMA


@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: compliance permite referencia cross-tenant", strict=False)
@pytest.mark.asyncio
async def test_compliance_inconformidad_rejects_cross_tenant_expediente_reference(
    db_session, tenant_a_user, tenant_b_user
):
    tenant_a, user_a = tenant_a_user
    tenant_b, user_b = tenant_b_user
    expediente_b = _expediente(
        tenant_id=tenant_b.id,
        user_id=user_b.id,
        suffix="COMPLIANCE-XTENANT",
    )
    db_session.add(expediente_b)
    await db_session.commit()
    await db_session.refresh(expediente_b)

    with pytest.raises(MegalodonException):
        await ComplianceService().crear_inconformidad(
            db_session,
            InconformidadCreate(
                expediente_id=str(expediente_b.id),
                titulo="Referencia cruzada",
                descripcion="Tenant A no debe poder apuntar a expediente de tenant B",
            ),
            user_a,
        )



@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: marcar_encolado reactiva COMPLETADO", strict=False)
@pytest.mark.asyncio
async def test_montecarlo_late_mark_queued_cannot_reactivate_completed_run(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    run = MonteCarloRun(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        task_id=f"audit-mc-{uuid4().hex[:16]}",
        request_hash="a" * 64,
        estado=EstadoMonteCarlo.COMPLETADO.value,
        progreso=100,
        iteraciones=100,
        seed=42,
        presupuesto_base=1000,
        presupuesto_maximo=1500,
        variables=[],
        configuracion={},
        resultado={"ok": True},
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    await MonteCarloService(db_session, tenant.id).marcar_encolado(run.id)

    await db_session.refresh(run)
    assert run.estado == EstadoMonteCarlo.COMPLETADO.value
    assert run.progreso == 100


@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: fallo tardio pisa CANCELADO con ERROR", strict=False)
@pytest.mark.asyncio
async def test_montecarlo_late_failure_cannot_overwrite_cancelled_run(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    run = MonteCarloRun(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        task_id=f"audit-mc-{uuid4().hex[:16]}",
        request_hash="b" * 64,
        estado=EstadoMonteCarlo.CANCELADO.value,
        progreso=40,
        iteraciones=100,
        seed=43,
        presupuesto_base=1000,
        presupuesto_maximo=1500,
        variables=[],
        configuracion={},
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    await MonteCarloService(db_session, tenant.id).fallar(
        run.task_id,
        RuntimeError("late worker failure"),
        execution_ms=50,
    )

    await db_session.refresh(run)
    assert run.estado == EstadoMonteCarlo.CANCELADO.value


@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: bases congeladas siguen mutables por PATCH", strict=False)
@pytest.mark.asyncio
async def test_frozen_licitacion_bases_cannot_be_mutated_by_generic_patch(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    expediente = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="BASES-FROZEN")
    db_session.add(expediente)
    await db_session.flush()
    lic = Licitacion(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        expediente_id=expediente.id,
        folio=f"AUD-BASE-{uuid4().hex[:8]}",
        jurisdiction_code="AUDIT",
        tipo_procedimiento=TipoProcedimiento.LICITACION_PUBLICA,
        estado=EstadoLicitacion.CONVOCATORIA,
        objeto="Bases congeladas",
        bases="BASE ORIGINAL",
        bases_version=7,
        bases_congeladas=True,
        matriz_evaluacion={"criterios": [{"id": "A"}]},
    )
    db_session.add(lic)
    await db_session.commit()
    await db_session.refresh(lic)

    with pytest.raises(MegalodonException):
        await LicitacionService().actualizar(
            db_session,
            lic.id,
            LicitacionUpdate(
                jurisdiction_code="AUDIT",
                bases="BASE MUTADA DESPUES DE CONGELAR",
                matriz_evaluacion={"criterios": [{"id": "B"}]},
                bases_congeladas=True,
            ),
            user,
        )

    await db_session.refresh(lic)
    assert lic.bases == "BASE ORIGINAL"
    assert lic.bases_version == 7
    assert lic.matriz_evaluacion == {"criterios": [{"id": "A"}]}



@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: sancion compliance acepta proveedor de otro tenant", strict=False)
@pytest.mark.asyncio
async def test_compliance_sanction_rejects_cross_tenant_provider_reference(
    db_session, tenant_a_user, tenant_b_user
):
    _tenant_a, user_a = tenant_a_user
    tenant_b, user_b = tenant_b_user
    proveedor_b = Proveedor(
        tenant_id=tenant_b.id,
        creado_por_id=user_b.id,
        actualizado_por_id=user_b.id,
        tipo_persona=TipoPersona.MORAL,
        rfc=f"SAN{uuid4().hex[:10].upper()}"[:13],
        razon_social="Proveedor Tenant B",
    )
    db_session.add(proveedor_b)
    await db_session.commit()
    await db_session.refresh(proveedor_b)

    with pytest.raises(MegalodonException):
        await ComplianceService().crear_sancion(
            db_session,
            SancionCreate(
                proveedor_id=str(proveedor_b.id),
                tipo="MULTA",
                motivo="Tenant A no debe sancionar una entidad de tenant B",
                monto_multa=1000,
            ),
            user_a,
        )


@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: LECTOR puede aprobar estimacion contractual", strict=False)
@pytest.mark.asyncio
async def test_lector_cannot_approve_contract_estimate(db_session, tenant_a_user):
    tenant, owner = tenant_a_user
    lector = User(
        email=f"audit-lector-{uuid4().hex[:8]}@example.mx",
        hashed_password="not-used",
        full_name="Audit Lector",
        role=UserRole.LECTOR,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    expediente = _expediente(tenant_id=tenant.id, user_id=owner.id, suffix="LECTOR-EST")
    proveedor = Proveedor(
        tenant_id=tenant.id,
        creado_por_id=owner.id,
        actualizado_por_id=owner.id,
        tipo_persona=TipoPersona.MORAL,
        rfc=f"LEC{uuid4().hex[:10].upper()}"[:13],
        razon_social="Proveedor Lector Audit",
    )
    db_session.add_all([lector, expediente, proveedor])
    await db_session.flush()
    contrato = Contrato(
        tenant_id=tenant.id,
        creado_por_id=owner.id,
        actualizado_por_id=owner.id,
        expediente_id=expediente.id,
        proveedor_id=proveedor.id,
        numero_contrato=f"AUD-LECT-{uuid4().hex[:8]}",
        estado=EstadoContrato.VIGENTE,
        objeto="Contrato para probar RBAC",
        monto_total=10000,
        monto_original=10000,
        plazo_dias=100,
        plazo_original=100,
    )
    db_session.add(contrato)
    await db_session.flush()
    estimacion = EntregableContrato(
        tenant_id=tenant.id,
        creado_por_id=owner.id,
        actualizado_por_id=owner.id,
        contrato_id=contrato.id,
        numero_estimacion=1,
        monto_ejecutado=1000,
        avance_fisico=10,
        avance_financiero=10,
        aprobado=False,
    )
    db_session.add(estimacion)
    await db_session.commit()
    await db_session.refresh(estimacion)

    with pytest.raises(MegalodonException):
        await ContratoService().aprobar_entregable(
            db_session,
            contrato.id,
            estimacion.id,
            lector,
        )

    await db_session.refresh(estimacion)
    assert estimacion.aprobado is False


@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: convenio acepta antecedentes que no coinciden con contrato", strict=False)
@pytest.mark.asyncio
async def test_contract_amendment_previous_values_must_match_current_contract(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    expediente = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="AMEND-TRACE")
    proveedor = Proveedor(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        tipo_persona=TipoPersona.MORAL,
        rfc=f"AMD{uuid4().hex[:10].upper()}"[:13],
        razon_social="Proveedor Amendment Audit",
    )
    db_session.add_all([expediente, proveedor])
    await db_session.flush()
    contrato = Contrato(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        expediente_id=expediente.id,
        proveedor_id=proveedor.id,
        numero_contrato=f"AUD-AMD-{uuid4().hex[:8]}",
        estado=EstadoContrato.VIGENTE,
        objeto="Contrato trazabilidad",
        monto_total=5000,
        monto_original=5000,
        plazo_dias=100,
        plazo_original=100,
    )
    db_session.add(contrato)
    await db_session.commit()
    await db_session.refresh(contrato)

    with pytest.raises(MegalodonException):
        await ContratoService().crear_modificatorio(
            db_session,
            contrato.id,
            ConvenioModificatorioCreate(
                numero="CM-01",
                tipo=TipoModificacion.MONTO,
                descripcion="Convenio con antecedente falso",
                monto_anterior=1,
                monto_nuevo=6000,
                plazo_anterior=2,
                plazo_nuevo=110,
                justificacion="Auditoria de trazabilidad",
            ),
            user,
        )



@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: estimaciones aprobadas pueden exceder monto contractual", strict=False)
@pytest.mark.asyncio
async def test_contract_rejects_approved_estimates_above_contract_total(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    expediente = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="OVERBILL")
    proveedor = Proveedor(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        tipo_persona=TipoPersona.MORAL,
        rfc=f"OVR{uuid4().hex[:10].upper()}"[:13],
        razon_social="Proveedor Overbilling Audit",
    )
    db_session.add_all([expediente, proveedor])
    await db_session.flush()
    contrato = Contrato(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        expediente_id=expediente.id,
        proveedor_id=proveedor.id,
        numero_contrato=f"AUD-OVR-{uuid4().hex[:8]}",
        estado=EstadoContrato.VIGENTE,
        objeto="Contrato limite de estimaciones",
        monto_total=1000,
        monto_original=1000,
        plazo_dias=100,
        plazo_original=100,
    )
    db_session.add(contrato)
    await db_session.flush()
    e1 = EntregableContrato(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        contrato_id=contrato.id,
        numero_estimacion=1,
        monto_ejecutado=700,
        avance_fisico=50,
        avance_financiero=70,
        aprobado=False,
    )
    e2 = EntregableContrato(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        contrato_id=contrato.id,
        numero_estimacion=2,
        monto_ejecutado=700,
        avance_fisico=100,
        avance_financiero=100,
        aprobado=False,
    )
    db_session.add_all([e1, e2])
    await db_session.commit()

    service = ContratoService()
    await service.aprobar_entregable(db_session, contrato.id, e1.id, user)
    with pytest.raises(MegalodonException):
        await service.aprobar_entregable(db_session, contrato.id, e2.id, user)


@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: autoflush=False deja avance contractual atrasado", strict=False)
@pytest.mark.asyncio
async def test_contract_progress_includes_newly_approved_estimate_with_production_autoflush(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    expediente = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="AUTOFLUSH")
    proveedor = Proveedor(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        tipo_persona=TipoPersona.MORAL,
        rfc=f"AFL{uuid4().hex[:10].upper()}"[:13],
        razon_social="Proveedor Autoflush Audit",
    )
    db_session.add_all([expediente, proveedor])
    await db_session.flush()
    contrato = Contrato(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        expediente_id=expediente.id,
        proveedor_id=proveedor.id,
        numero_contrato=f"AUD-AFL-{uuid4().hex[:8]}",
        estado=EstadoContrato.VIGENTE,
        objeto="Contrato progreso",
        monto_total=1000,
        monto_original=1000,
        plazo_dias=100,
        plazo_original=100,
        avance_fisico=0,
        avance_financiero=0,
    )
    db_session.add(contrato)
    await db_session.flush()
    estimacion = EntregableContrato(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        contrato_id=contrato.id,
        numero_estimacion=1,
        monto_ejecutado=250,
        avance_fisico=25,
        avance_financiero=25,
        aprobado=False,
    )
    db_session.add(estimacion)
    await db_session.commit()

    old_autoflush = db_session.sync_session.autoflush
    db_session.sync_session.autoflush = False
    try:
        await ContratoService().aprobar_entregable(
            db_session,
            contrato.id,
            estimacion.id,
            user,
        )
    finally:
        db_session.sync_session.autoflush = old_autoflush

    await db_session.refresh(contrato)
    assert float(contrato.avance_fisico) == 25.0
    assert float(contrato.avance_financiero) == 25.0


@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: AuditService no enlaza hash_previo automaticamente", strict=False)
@pytest.mark.asyncio
async def test_audit_service_builds_a_valid_hash_chain_without_manual_hash_plumbing(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    entity_id = str(uuid4())
    audit = AuditService(db_session)

    await audit.registrar_accion(
        user_id=user.id,
        user_email=user.email,
        user_role=str(user.role),
        entidad_tipo="EXPEDIENTE",
        entidad_id=entity_id,
        accion=TipoAccion.CREAR,
        descripcion="primera accion",
        datos_nuevos={"v": 1},
        tenant_id=tenant.id,
    )
    await audit.registrar_accion(
        user_id=user.id,
        user_email=user.email,
        user_role=str(user.role),
        entidad_tipo="EXPEDIENTE",
        entidad_id=entity_id,
        accion=TipoAccion.MODIFICAR,
        descripcion="segunda accion",
        datos_anteriores={"v": 1},
        datos_nuevos={"v": 2},
        tenant_id=tenant.id,
    )

    verification = await audit.verificar_integridad_cadena(
        "EXPEDIENTE",
        entity_id,
        tenant_id=tenant.id,
    )

    assert verification["valido"] is True
    assert verification["errores"] == []



@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: Merkle ignora DocumentoCDE", strict=False)
@pytest.mark.asyncio
async def test_expediente_merkle_includes_cde_document_hashes(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    expediente = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="MERKLE-CDE")
    db_session.add(expediente)
    await db_session.flush()
    cde = DocumentoCDE(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        expediente_id=expediente.id,
        nombre="documento-cde-integridad.pdf",
        descripcion="Debe estar cubierto por Merkle",
        tipo=TipoDocumento.ANEXO_TECNICO,
        version=1,
        hash_sha256="c" * 64,
        metadatos={},
    )
    db_session.add(cde)
    await db_session.commit()

    root = await ExpedienteService(db_session, tenant.id).calcular_merkle_root(
        expediente.id,
        tenant_id=tenant.id,
    )

    assert root != ""


@pytest.mark.xfail(reason="RED confirmado en PostgreSQL: FirmaService usa descifrado legacy sin key", strict=False)
@pytest.mark.asyncio
async def test_signature_reads_current_envelope_encrypted_documents(monkeypatch, db_session):
    encrypted_document = SimpleNamespace(
        storage_path="audit/encrypted.pdf",
        cifrado=True,
        nonce_cifrado=("01" * 12),
        tag_cifrado=("02" * 16),
        encryption_key_enc=("03" * 60),
    )
    fake_storage = SimpleNamespace(
        descargar=AsyncMock(return_value=b"ciphertext"),
    )
    monkeypatch.setattr(
        "app.services.firma_service.storage_documentos",
        lambda: fake_storage,
    )

    # The current document encryption contract carries encryption_key_enc.
    # FirmaService must use descifrar_sobre(...), not the legacy primitive
    # that requires an external raw key which it never supplies.
    result = await FirmaService(db_session)._contenido_real(encrypted_document)

    assert isinstance(result, bytes)



@pytest.mark.asyncio
async def test_procurement_worker_rejects_job_when_tender_revision_changed_after_enqueue(
    db_session, tenant_a_user, monkeypatch
):
    tenant, user = tenant_a_user
    expediente = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="JOB-SNAPSHOT")
    db_session.add(expediente)
    await db_session.flush()

    model_v1 = {"facts": {"version": 1}}
    tender = TenderPackage(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        expediente_id=expediente.id,
        identifier=f"AUD-SNAPSHOT-{uuid4().hex[:8]}",
        title="Procurement snapshot audit",
        state=TenderState.QA_READY.value,
        canonical_model=model_v1,
        current_revision=1,
    )
    db_session.add(tender)
    await db_session.flush()

    model_hash_v1 = sha256(
        json.dumps(model_v1, sort_keys=True, default=str).encode()
    ).hexdigest()
    job = ProcurementJob(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        tender_id=tender.id,
        kind="RUN",
        status="QUEUED",
        request_hash=ProcurementJobService.request_hash(
            tender_id=tender.id,
            kind="RUN",
            revision=1,
            model_hash=model_hash_v1,
        ),
        progress=0,
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    tender.current_revision = 2
    tender.canonical_model = {"facts": {"version": 2}}
    await db_session.commit()

    run_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(ProcurementService, "run", run_mock)

    with pytest.raises(MegalodonException):
        await execute_procurement_job(
            str(job.id),
            str(user.id),
            str(tenant.id),
            str(tender.id),
        )

    assert run_mock.await_count == 0
