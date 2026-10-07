from __future__ import annotations

from uuid import uuid4

import pytest

from app.engines.ia.ocr_metrados import ResultadoOCR
from app.models.ocr_job import OCRJob, OCRJobStatus
from app.services.ocr_jobs import OCRJobService


@pytest.mark.asyncio
async def test_ocr_broker_message_contains_only_durable_job_id(
    db_session, tenant_a_user, monkeypatch
):
    tenant, user = tenant_a_user
    service = OCRJobService(db_session, tenant.id)
    job_id = uuid4()
    source = b"not-the-broker-payload"
    job = await service.crear(
        user=user,
        job_id=job_id,
        filename="plano.png",
        content_type="image/png",
        storage_path=f"tenant/{tenant.id}/ocr/{job_id}/source.png",
        source_bytes=source,
        presupuesto_id=None,
    )

    sent = []

    def accept(*args, **kwargs):
        sent.append((args, kwargs))
        return object()

    monkeypatch.setattr(
        "app.services.ocr_jobs.celery_app.send_task",
        accept,
    )

    published = await service.publicar(job_id)

    assert published.status == OCRJobStatus.QUEUED.value
    assert len(sent) == 1
    task_name, = sent[0][0]
    assert task_name == "app.workers.ocr_tasks.extraer_metrados_ocr"
    assert sent[0][1]["args"] == [str(job_id)]
    assert sent[0][1]["task_id"] == str(job_id)
    assert source not in repr(sent[0]).encode()


@pytest.mark.asyncio
async def test_ocr_stale_attempt_cannot_complete_after_new_claim(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    service = OCRJobService(db_session, tenant.id)
    job_id = uuid4()
    await service.crear(
        user=user,
        job_id=job_id,
        filename="plano.png",
        content_type="image/png",
        storage_path=f"tenant/{tenant.id}/ocr/{job_id}/source.png",
        source_bytes=b"source",
        presupuesto_id=None,
    )

    first, token1 = await service.claim(job_id)
    assert first is not None and token1

    # Simula que la lease venció y el reconciliador habilitó un nuevo intento.
    row = await db_session.get(OCRJob, job_id)
    row.status = OCRJobStatus.PENDING.value
    row.claim_token = None
    row.started_at = None
    await db_session.commit()

    second, token2 = await service.claim(job_id)
    assert second is not None and token2 and token2 != token1

    empty_result = ResultadoOCR(
        documento_id=str(job_id),
        total_metrados=0,
        confianza_promedio=0.0,
        metrados=[],
        texto_completo="",
        paginas_procesadas=1,
        errores=[],
    )

    assert await service.completar(job_id, token1, empty_result) is False
    assert await service.completar(job_id, token2, empty_result) is True

    await db_session.refresh(second)
    assert second.status == OCRJobStatus.SUCCEEDED.value
    assert second.attempts == 2


@pytest.mark.asyncio
async def test_ocr_publish_failure_keeps_durable_pending_intent(
    db_session, tenant_a_user, monkeypatch
):
    tenant, user = tenant_a_user
    service = OCRJobService(db_session, tenant.id)
    job_id = uuid4()
    await service.crear(
        user=user,
        job_id=job_id,
        filename="plano.pdf",
        content_type="application/pdf",
        storage_path=f"tenant/{tenant.id}/ocr/{job_id}/source.pdf",
        source_bytes=b"%PDF-audit",
        presupuesto_id=None,
    )

    def unavailable(*_args, **_kwargs):
        raise ConnectionError("broker down")

    monkeypatch.setattr(
        "app.services.ocr_jobs.celery_app.send_task",
        unavailable,
    )

    with pytest.raises(Exception):
        await service.publicar(job_id)

    row = await db_session.get(OCRJob, job_id)
    await db_session.refresh(row)
    assert row.status == OCRJobStatus.PENDING.value
    assert row.task_id == str(job_id)
    assert row.error_code == "ENQUEUE_FAILED"
