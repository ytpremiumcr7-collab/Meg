# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Configuración de Celery para workers asíncronos.
"""
from celery import Celery
from app.config import settings

celery_app = Celery(
    "megalodon",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.bim_tasks",
        "app.workers.montecarlo_tasks",
        "app.workers.ocr_tasks",
        "app.workers.pdf_tasks",
        "app.workers.excel_tasks",
        "app.workers.procurement_tasks",
        "app.workers.procurement_reconciliation",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Mexico_City",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,  # 30 minutos máximo
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    beat_schedule={
        "procurement-storage-reconciliation": {
            "task": "app.workers.procurement_reconciliation.reconcile_procurement_storage",
            "schedule": 300.0,
        },
    },
)
