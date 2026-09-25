# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""Ownership de task_id (Celery) por tenant.

Cierra el hueco de control de acceso documentado en websocket.py y
montecarlo.py desde la sesión anterior: antes de este módulo, cualquier
usuario autenticado -- de CUALQUIER tenant -- podía consultar o
suscribirse al progreso de un task_id ajeno con solo conocer el UUID.
No había ninguna verificación de que la tarea le perteneciera a su
tenant; solo se exigía *estar* autenticado, no *ser el dueño*.

Mecanismo: cada endpoint que encola una tarea Celery (`.delay()` /
`send_task`) llama a `register_task_owner()` justo después de encolar,
guardando `task_id -> tenant_id` en Redis con un TTL. Los puntos de
consulta (GET .../status, WS /ws/progreso) llaman a
`verify_task_owner()` antes de devolver cualquier dato de la tarea, y
niegan el acceso si el tenant no coincide.

Política de fallo -- distinta a propósito de token_revocation.py y
rate_limit.py:
- Si Redis no está disponible del todo, se respeta
  `settings.security_protection_fail_closed` igual que el resto de
  controles de seguridad del sistema (para no introducir una postura
  de fallo inconsistente según el módulo).
- PERO si Redis SÍ responde y simplemente no hay un registro para ese
  task_id (tarea inexistente, expirada, o creada antes de este
  control), la respuesta es SIEMPRE denegar -- eso no es "no se pudo
  verificar", es "se verificó y no es tuya/no existe". No hay
  excepción de política fail-open para ese caso, porque fail-open ahí
  reabriría exactamente el IDOR que este módulo existe para cerrar.
"""
from __future__ import annotations

from typing import Optional

import structlog

from app.core.redis_client import get_redis

logger = structlog.get_logger()

_PREFIX = "task_owner:"
# TTL generoso: mayor al tiempo máximo razonable de cualquier tarea
# soportada hoy (OCR, Monte Carlo). Si en el futuro alguna tarea legítima
# puede tardar más que esto, subir el valor -- no eliminar el TTL.
_DEFAULT_TTL_SECONDS = 6 * 60 * 60  # 6 horas


def _key(task_id: str) -> str:
    return f"{_PREFIX}{task_id}"


async def register_task_owner(
    task_id: str,
    *,
    tenant_id,
    user_id,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> bool:
    """Registra el dueño de una tarea recién encolada.

    Fail-open deliberado aquí (no en la verificación): si Redis falla en
    este punto, preferimos que la tarea se encole igual -- el cliente ya
    recibió (o está por recibir) un task_id y la operación de negocio no
    debe abortarse por esto. El hueco se cierra del lado de la consulta:
    `verify_task_owner` niega el acceso si no encuentra el registro,
    así que un fallo de registro nunca se traduce en fuga de datos, en
    el peor caso el propio dueño no podrá consultar su tarea (y deberá
    reintentar), lo cual es un problema de disponibilidad, no de fuga.
    """
    redis = get_redis()
    if redis is None:
        logger.warning(
            "task_owner_register_skipped_no_redis",
            task_id=task_id,
            tenant_id=str(tenant_id),
        )
        return False

    try:
        key = _key(task_id)
        await redis.hset(key, mapping={"tenant_id": str(tenant_id), "user_id": str(user_id)})
        await redis.expire(key, ttl_seconds)
        logger.debug(
            "task_owner_registered",
            task_id=task_id,
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            ttl_seconds=ttl_seconds,
        )
        return True
    except Exception as exc:  # pragma: no cover - backend failure path
        logger.warning(
            "task_owner_register_failed",
            task_id=task_id,
            tenant_id=str(tenant_id),
            error=str(exc),
        )
        return False


async def verify_task_owner(task_id: str, *, tenant_id) -> bool:
    """Devuelve True solo si la tarea está registrada Y pertenece al
    tenant dado. Ver la nota de política de fallo en el docstring del
    módulo: la ausencia de registro nunca se resuelve como "permitir",
    solo la indisponibilidad total de Redis respeta
    `security_protection_fail_closed`.
    """
    redis = get_redis()
    if redis is None:
        logger.warning("task_owner_verify_unavailable", task_id=task_id)
        return False

    try:
        owner_tenant: Optional[str] = await redis.hget(_key(task_id), "tenant_id")
    except Exception as exc:  # pragma: no cover - backend failure path
        logger.warning("task_owner_verify_error", task_id=task_id, error=str(exc))
        return False

    if owner_tenant is None:
        logger.info("task_owner_not_found", task_id=task_id, tenant_id=str(tenant_id))
        return False

    return owner_tenant == str(tenant_id)
