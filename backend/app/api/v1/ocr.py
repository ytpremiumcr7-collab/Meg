# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
API de OCR para extracción de metrados.
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.errors import TareaNoEncontradaException
from app.core.task_ownership import register_task_owner, verify_task_owner
from app.services.ocr_service import OCRService
from app.config import settings
from app.utils.upload_limits import read_upload_with_limit
from app.models.user import User
from app.workers.celery_app import celery_app
import base64

router = APIRouter()


@router.post("/extraer")
async def extraer_metrados(
    file: UploadFile = File(...),
    presupuesto_id: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """
    Extrae metrados de un documento (imagen o PDF) mediante OCR.
    Si se proporciona presupuesto_id, crea partidas sugeridas.
    """
    content = await read_upload_with_limit(file, settings.TENDER_SOURCE_MAX_FILE_SIZE_MB)

    # Encolar en Celery para procesamiento async
    content_b64 = base64.b64encode(content).decode()

    task = celery_app.send_task(
        "app.workers.ocr_tasks.extraer_metrados_ocr",
        args=[str(current_user.id), file.filename, content_b64, presupuesto_id, str(current_user.tenant_id)],
    )
    await register_task_owner(task.id, tenant_id=current_user.tenant_id, user_id=current_user.id)

    return {
        "task_id": task.id,
        "status": "PENDING",
        "message": "Procesamiento OCR encolado",
        "filename": file.filename,
    }


@router.get("/extraer/{task_id}/status")
async def consultar_ocr(task_id: str, current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard)):
    # MISMO IDOR que /riesgo/simular/{task_id}/status (ver ESTADO_Y_PLAN):
    # este endpoint no estaba explícitamente listado en el comentario de
    # websocket.py, pero tiene idéntico patrón -- get_current_user solo
    # exige estar autenticado, nunca verificaba que el task_id fuera del
    # mismo tenant. Se cierra igual, con el mismo registro compartido.
    if not await verify_task_owner(task_id, tenant_id=current_user.tenant_id):
        raise TareaNoEncontradaException()

    task = celery_app.AsyncResult(task_id)

    if task.ready():
        return {"task_id": task_id, "status": "SUCCESS", "result": task.result}

    return {"task_id": task_id, "status": task.status}


@router.post("/validar")
async def validar_metrados(
    metrados: list,
    umbral_confianza: float = 60.0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Valida metrados extraídos por OCR."""
    from app.engines.ia.ocr_metrados import MetradoExtraido

    service = OCRService(db)

    # Convertir dicts a objetos MetradoExtraido
    metrados_objs = []
    for m in metrados:
        metrados_objs.append(MetradoExtraido(**m))

    resultado = await service.validar_metrados(metrados_objs, umbral_confianza)
    return resultado
