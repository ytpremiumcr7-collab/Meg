"""Regressions through independent DB sessions, never same-session token edits."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models.montecarlo import EstadoMonteCarlo, MonteCarloRun
from app.models.presupuesto import Presupuesto
from app.models.ocr_job import OCRJob
from app.services.montecarlo_service import MonteCarloService
from app.services.ocr_jobs import OCRJobService
from app.engines.ia.ocr_metrados import ResultadoOCR
from tests.conftest import AsyncSessionLocalTest
from tests.test_prr_reproductions_20261007 import _montecarlo_run, _expediente


def empty_ocr(job_id):
    return ResultadoOCR(documento_id=str(job_id), total_metrados=0,
                        confianza_promedio=0, metrados=[], texto_completo="",
                        paginas_procesadas=1, errores=[])


@pytest.mark.asyncio
async def test_montecarlo_cached_attempt_cannot_overwrite_cancellation(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    run = _montecarlo_run(tenant_id=tenant.id, user_id=user.id,
                         estado=EstadoMonteCarlo.PENDIENTE.value)
    db_session.add(run)
    await db_session.commit()
    run_id, task_id, tenant_id = run.id, run.task_id, tenant.id
    service = MonteCarloService(db_session, tenant_id)
    token = await service.marcar_en_proceso(str(run_id))
    # run stays strongly referenced in the old worker's identity map.
    async with AsyncSessionLocalTest() as other:
        await MonteCarloService(other, tenant_id).cancelar(task_id, tenant_id)
    assert not await service.completar(task_id, {"obsolete": True}, 1, token=token)
    async with AsyncSessionLocalTest() as fresh:
        persisted = await fresh.get(MonteCarloRun, run_id)
        assert persisted.estado == EstadoMonteCarlo.CANCELADO.value
        assert persisted.resultado is None


@pytest.mark.asyncio
async def test_ocr_cached_attempt_cannot_overwrite_new_claim(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    job_id, tenant_id = uuid4(), tenant.id
    service = OCRJobService(db_session, tenant_id)
    job, _ = await service.crear(user=user, job_id=job_id, filename="x.png",
        content_type="image/png", storage_path=f"tenant/{tenant_id}/{job_id}",
        source_bytes=b"source", presupuesto_id=None)
    job, old_token = await service.claim(job_id)
    await db_session.commit()  # release the refresh read transaction
    async with AsyncSessionLocalTest() as other:
        row = await other.get(OCRJob, job_id)
        row.status, row.claim_token, row.started_at = "PENDING", None, None
        await other.commit()
        _, new_token = await OCRJobService(other, tenant_id).claim(job_id)
    assert new_token != old_token
    assert not await service.completar(job_id, old_token, empty_ocr(job_id))
    async with AsyncSessionLocalTest() as fresh:
        persisted = await fresh.get(OCRJob, job_id)
        assert persisted.status == "RUNNING"
        assert persisted.claim_token == new_token
        assert persisted.attempts == 2


@pytest.mark.asyncio
async def test_montecarlo_budget_write_failure_reverts_both_rows(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="ATOMIC-DB")
    db_session.add(exp)
    await db_session.flush()
    budget = Presupuesto(tenant_id=tenant.id, expediente_id=exp.id,
        identificador=f"AT-{uuid4().hex[:8]}", nombre="Atomic DB failure",
        factor_indirecto=0, factor_utilidad=0, factor_impuesto=0.16)
    db_session.add(budget)
    await db_session.flush()
    run = _montecarlo_run(tenant_id=tenant.id, user_id=user.id,
                         estado=EstadoMonteCarlo.PENDIENTE.value)
    run.presupuesto_id, run.expediente_id = budget.id, exp.id
    db_session.add(run)
    await db_session.commit()
    run_id, budget_id = run.id, budget.id
    service = MonteCarloService(db_session, tenant.id)
    token = await service.marcar_en_proceso(str(run_id))
    # Actual DB rejection of the projection UPDATE, after completion assigns both rows.
    sqlite = db_session.bind.dialect.name == "sqlite"
    if sqlite:
        ddl = """CREATE TRIGGER reject_mc_projection BEFORE UPDATE OF resultado_montecarlo
                 ON presupuestos WHEN NEW.resultado_montecarlo IS NOT NULL
                 BEGIN SELECT RAISE(ABORT, 'projection_rejected'); END"""
    else:
        await db_session.execute(text("""CREATE FUNCTION reject_mc_projection() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'projection_rejected'; END $$"""))
        ddl = """CREATE TRIGGER reject_mc_projection BEFORE UPDATE OF resultado_montecarlo
                 ON presupuestos FOR EACH ROW EXECUTE FUNCTION reject_mc_projection()"""
    await db_session.execute(text(ddl))
    await db_session.commit()
    try:
        with pytest.raises(DBAPIError, match="projection_rejected"):
            await service.completar(run.task_id, {"p80": 1190}, 5, token=token)
        async with AsyncSessionLocalTest() as fresh:
            saved_run = await fresh.get(MonteCarloRun, run_id)
            saved_budget = await fresh.get(Presupuesto, budget_id)
            assert saved_run.estado == EstadoMonteCarlo.EN_PROCESO.value
            assert saved_run.execution_token == token
            assert saved_run.resultado is None
            assert saved_budget.resultado_montecarlo is None
    finally:
        await db_session.rollback()
        await db_session.execute(text("DROP TRIGGER reject_mc_projection" +
                                      (" ON presupuestos" if not sqlite else "")))
        if not sqlite:
            await db_session.execute(text("DROP FUNCTION reject_mc_projection()"))
        await db_session.commit()
