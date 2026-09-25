# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Tareas asíncronas para OCR y extracción de metrados.
"""
import base64
import asyncio
from typing import Optional

from app.workers.celery_app import celery_app
from app.engines.ia.ocr_metrados import MotorOCRMetrados


@celery_app.task(bind=True, time_limit=300)
def extraer_metrados_ocr(
    self,
    usuario_id: str,
    filename: str,
    file_content_b64: str,
    presupuesto_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
):
    """Extrae metrados de planos mediante OCR y, si se proporciona
    presupuesto_id, persiste las partidas sugeridas llamando a
    OCRService (que tiene la lógica de _crear_partidas_sugeridas).
    Antes: (a) no recibía presupuesto_id, (b) tampoco lo persistía
    aunque lo hubiera recibido porque llamaba al motor directamente
    sin pasar por el servicio ni abrir sesión de BD."""
    try:
        file_bytes = base64.b64decode(file_content_b64)
        motor = MotorOCRMetrados()
        resultado = motor.procesar_documento(file_bytes, filename, usuario_id)

        # Persistir partidas si se recibió presupuesto_id -- el worker
        # delega la lógica al servicio, no la duplica aquí.
        if presupuesto_id and resultado.metrados:
            async def _persistir():
                from app.models.base import AsyncSessionLocal
                from app.services.ocr_service import OCRService
                from uuid import UUID
                async with AsyncSessionLocal() as db:
                    service = OCRService(db, tenant_id=UUID(tenant_id) if tenant_id else None)
                    await service._crear_partidas_sugeridas(UUID(presupuesto_id), resultado)

            asyncio.run(_persistir())

        return {
            "status": "SUCCESS",
            "usuario_id": usuario_id,
            "filename": filename,
            "presupuesto_id": presupuesto_id,
            "total_metrados": resultado.total_metrados,
            "confianza_promedio": resultado.confianza_promedio,
            "metrados": [m.to_dict() for m in resultado.metrados],
            "paginas_procesadas": resultado.paginas_procesadas,
            "errores": resultado.errores,
        }
    except Exception as exc:
        self.retry(countdown=60, exc=exc)
