# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Proveedor Stripe -- OPCIONAL a propósito.

El arranque real de negocio es con Mercado Pago. Stripe queda
implementado con la misma interfaz para cuando haga falta expandir,
pero:
  1. El paquete `stripe` NO es una dependencia obligatoria del proyecto
     (vive en el extra opcional `pip install .[stripe]`, ver
     pyproject.toml). El import de acá está protegido: si el paquete no
     está instalado, este módulo se importa igual (no truena el
     arranque del backend), solo que `disponible` queda en False.
  2. Sin STRIPE_SECRET_KEY en el entorno, `disponible` también es False,
     aunque el paquete SÍ esté instalado.
  3. app.services.suscripcion_service solo usa este proveedor si
     `disponible` es True; si no, cae a Mercado Pago (o reporta
     "proveedor no disponible" si el que se pidió explícitamente fue
     Stripe).
"""
from typing import Any, Dict, Optional

import structlog

from app.config import settings
from app.integrations.payments.base import PaymentProvider, ResultadoCheckout, ResultadoWebhook

logger = structlog.get_logger()

try:
    import stripe as _stripe_sdk
    _STRIPE_SDK_DISPONIBLE = True
except ImportError:
    _stripe_sdk = None
    _STRIPE_SDK_DISPONIBLE = False


_ESTADO_STRIPE_A_INTERNO = {
    "trialing": "ACTIVA",
    "active": "ACTIVA",
    "past_due": "VENCIDA",
    "unpaid": "VENCIDA",
    "canceled": "CANCELADA",
    "incomplete": "PENDIENTE_PAGO",
    "incomplete_expired": "CANCELADA",
}


class StripeProvider(PaymentProvider):
    nombre = "STRIPE"

    def __init__(self) -> None:
        if _STRIPE_SDK_DISPONIBLE and settings.STRIPE_SECRET_KEY:
            _stripe_sdk.api_key = settings.STRIPE_SECRET_KEY

    @property
    def disponible(self) -> bool:
        return _STRIPE_SDK_DISPONIBLE and bool(settings.STRIPE_SECRET_KEY)

    async def crear_checkout(
        self,
        *,
        tenant_id: str,
        plan: str,
        precio: float,
        moneda: str,
        email_cliente: str,
        url_retorno_exito: str,
        url_retorno_fallo: str,
    ) -> ResultadoCheckout:
        if not self.disponible:
            return ResultadoCheckout(
                disponible=False,
                mensaje=(
                    "Stripe no está configurado (falta el paquete `stripe` -- "
                    "`pip install .[stripe]` -- o STRIPE_SECRET_KEY). "
                    "Usa Mercado Pago mientras tanto."
                ),
            )

        try:
            sesion = _stripe_sdk.checkout.Session.create(
                mode="subscription",
                customer_email=email_cliente,
                line_items=[{
                    "price_data": {
                        "currency": moneda.lower(),
                        "unit_amount": int(round(precio * 100)),
                        "recurring": {"interval": "month"},
                        "product_data": {"name": f"Megalodon CostOS -- Plan {plan}"},
                    },
                    "quantity": 1,
                }],
                success_url=url_retorno_exito,
                cancel_url=url_retorno_fallo,
                client_reference_id=f"{tenant_id}:{plan}",
            )
        except Exception as exc:  # noqa: BLE001 - SDK externo, cualquier error de red/API cae aquí
            logger.error("stripe_crear_checkout_error", error=str(exc))
            return ResultadoCheckout(disponible=True, mensaje=f"Stripe rechazó la solicitud: {exc}")

        return ResultadoCheckout(disponible=True, url_pago=sesion.url, external_id=sesion.id)

    def verificar_firma_webhook(self, payload: bytes, headers: Dict[str, str]) -> bool:
        if not self.disponible or not settings.STRIPE_WEBHOOK_SECRET:
            logger.warning("stripe_webhook_sin_secreto_configurado")
            return not self.disponible  # si Stripe ni siquiera está activo, no debería llegar tráfico real aquí
        try:
            _stripe_sdk.Webhook.construct_event(
                payload, headers.get("stripe-signature", ""), settings.STRIPE_WEBHOOK_SECRET,
            )
            return True
        except Exception:  # noqa: BLE001
            return False

    async def procesar_webhook(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> ResultadoWebhook:
        tipo = payload.get("type", "")
        obj = (payload.get("data") or {}).get("object") or {}

        if not tipo.startswith("customer.subscription."):
            return ResultadoWebhook(valido=True, mensaje="Evento ignorado (no es de suscripción).")

        estado_stripe = obj.get("status", "")
        return ResultadoWebhook(
            valido=True,
            external_id=obj.get("id"),
            estado=_ESTADO_STRIPE_A_INTERNO.get(estado_stripe, "PENDIENTE_PAGO"),
            datos_crudos=obj,
        )

    async def cancelar_suscripcion(self, external_id: str) -> bool:
        if not self.disponible:
            return False
        try:
            _stripe_sdk.Subscription.cancel(external_id)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("stripe_cancelar_error", error=str(exc))
            return False
