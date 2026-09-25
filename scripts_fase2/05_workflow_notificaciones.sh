#!/bin/bash
# =============================================================================
# FASE 2 — Script 5: Workflow condiciones dinámicas + Notificaciones reales
# =============================================================================

set -euo pipefail

BACKEND_DIR="${1:-./backend}"

echo "🦈 MEGALODON FASE 2 — Script 5: Workflow + Notificaciones..."
echo ""

# ─── WORKFLOW ENGINE — Condiciones dinámicas ─────────────────────────────────

cat > "$BACKEND_DIR/app/modules/workflow/engine.py" << 'PYEOF'
# Copyright © 2026 Cristian Rodriguez
"""Motor de workflow con condiciones dinámicas evaluables."""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime, timedelta
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models.workflow import Workflow, WorkflowPaso, WorkflowTransicion, WorkflowCondicion
from app.models.user import User
from app.core.errors import MegalodonException, ErrorCode

class OperadorCondicion(str, Enum):
    IGUAL = "=="
    DIFERENTE = "!="
    MAYOR = ">"
    MAYOR_IGUAL = ">="
    MENOR = "<"
    MENOR_IGUAL = "<="
    CONTIENE = "contains"
    EMPIEZA_CON = "startswith"
    TERMINA_CON = "endswith"
    EN_LISTA = "in"
    VACIO = "is_empty"
    NO_VACIO = "is_not_empty"

class MotorWorkflow:
    """Motor de evaluación de workflow con condiciones dinámicas."""

    async def evaluar_condicion(
        self,
        condicion: WorkflowCondicion,
        contexto: Dict[str, Any],
    ) -> bool:
        """Evalúa una condición dinámica contra un contexto de datos."""
        campo = condicion.campo
        operador = condicion.operador
        valor_referencia = condicion.valor_referencia

        # Obtener valor del contexto
        valor_actual = self._obtener_valor_anidado(contexto, campo)

        if operador == OperadorCondicion.IGUAL:
            return str(valor_actual) == str(valor_referencia)
        elif operador == OperadorCondicion.DIFERENTE:
            return str(valor_actual) != str(valor_referencia)
        elif operador == OperadorCondicion.MAYOR:
            return float(valor_actual or 0) > float(valor_referencia)
        elif operador == OperadorCondicion.MAYOR_IGUAL:
            return float(valor_actual or 0) >= float(valor_referencia)
        elif operador == OperadorCondicion.MENOR:
            return float(valor_actual or 0) < float(valor_referencia)
        elif operador == OperadorCondicion.MENOR_IGUAL:
            return float(valor_actual or 0) <= float(valor_referencia)
        elif operador == OperadorCondicion.CONTIENE:
            return str(valor_referencia) in str(valor_actual or "")
        elif operador == OperadorCondicion.EMPIEZA_CON:
            return str(valor_actual or "").startswith(str(valor_referencia))
        elif operador == OperadorCondicion.TERMINA_CON:
            return str(valor_actual or "").endswith(str(valor_referencia))
        elif operador == OperadorCondicion.EN_LISTA:
            lista = valor_referencia if isinstance(valor_referencia, list) else [valor_referencia]
            return str(valor_actual) in [str(v) for v in lista]
        elif operador == OperadorCondicion.VACIO:
            return not valor_actual or str(valor_actual).strip() == ""
        elif operador == OperadorCondicion.NO_VACIO:
            return bool(valor_actual) and str(valor_actual).strip() != ""
        return False

    def _obtener_valor_anidado(self, contexto: Dict[str, Any], campo: str) -> Any:
        """Obtiene un valor anidado del contexto usando notación punto."""
        partes = campo.split(".")
        valor = contexto
        for parte in partes:
            if isinstance(valor, dict):
                valor = valor.get(parte)
            else:
                return None
            if valor is None:
                return None
        return valor

    async def validar_transicion(
        self,
        db: AsyncSession,
        workflow_id: UUID,
        paso_origen_id: UUID,
        paso_destino_id: UUID,
        contexto: Dict[str, Any],
        current_user: User,
    ) -> Dict[str, Any]:
        """Valida una transición evaluando todas las condiciones asociadas."""
        # Verificar existencia del flujo y pasos
        workflow = await db.get(Workflow, workflow_id)
        if not workflow:
            raise MegalodonException(ErrorCode.NOT_FOUND, "Workflow no encontrado.")

        paso_origen = await db.get(WorkflowPaso, paso_origen_id)
        paso_destino = await db.get(WorkflowPaso, paso_destino_id)
        if not paso_origen or not paso_destino:
            raise MegalodonException(ErrorCode.NOT_FOUND, "Paso no encontrado.")

        # Buscar transición
        stmt = select(WorkflowTransicion).where(
            and_(
                WorkflowTransicion.workflow_id == workflow_id,
                WorkflowTransicion.paso_origen_id == paso_origen_id,
                WorkflowTransicion.paso_destino_id == paso_destino_id,
            )
        )
        transicion = (await db.execute(stmt)).scalar_one_or_none()
        if not transicion:
            raise MegalodonException(ErrorCode.BAD_REQUEST, "Transición no definida.")

        # Evaluar condiciones
        condiciones = await db.execute(
            select(WorkflowCondicion).where(
                WorkflowCondicion.transicion_id == transicion.id
            ).order_by(WorkflowCondicion.orden)
        )
        condiciones = condiciones.scalars().all()

        resultados = []
        todas_cumplidas = True

        for cond in condiciones:
            cumple = await self.evaluar_condicion(cond, contexto)
            resultados.append({
                "condicion_id": str(cond.id),
                "campo": cond.campo,
                "operador": cond.operador,
                "valor_referencia": cond.valor_referencia,
                "cumple": cumple,
            })
            if not cumple and cond.obligatoria:
                todas_cumplidas = False

        return {
            "transicion_valida": todas_cumplidas,
            "transicion_id": str(transicion.id),
            "condiciones_evaluadas": len(resultados),
            "condiciones_cumplidas": sum(1 for r in resultados if r["cumple"]),
            "detalle": resultados,
        }

    async def verificar_sla_vencidos(
        self,
        db: AsyncSession,
        workflow_id: Optional[UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Detecta tareas vencidas y las escala."""
        from datetime import datetime
        ahora = datetime.utcnow()

        query = select(WorkflowPaso).where(
            and_(
                WorkflowPaso.estado == "EN_PROGRESO",
                WorkflowPaso.fecha_limite != None,
                WorkflowPaso.fecha_limite < ahora,
            )
        )
        if workflow_id:
            query = query.where(WorkflowPaso.workflow_id == workflow_id)

        pasos_vencidos = (await db.execute(query)).scalars().all()

        alertas = []
        for paso in pasos_vencidos:
            paso.estado = "VENCIDO"
            paso.updated_at = ahora
            alertas.append({
                "paso_id": str(paso.id),
                "workflow_id": str(paso.workflow_id),
                "nombre": paso.nombre,
                "fecha_limite": paso.fecha_limite.isoformat(),
                "dias_vencido": (ahora - paso.fecha_limite).days,
                "accion": "ESCALADO",
            })

        await db.commit()
        return alertas

    async def crear_condicion(
        self,
        db: AsyncSession,
        transicion_id: UUID,
        campo: str,
        operador: str,
        valor_referencia: Any,
        obligatoria: bool = True,
        orden: int = 0,
    ) -> WorkflowCondicion:
        """Crea una condición dinámica para una transición."""
        cond = WorkflowCondicion(
            transicion_id=transicion_id,
            campo=campo,
            operador=operador,
            valor_referencia=valor_referencia,
            obligatoria=obligatoria,
            orden=orden,
        )
        db.add(cond)
        await db.commit()
        await db.refresh(cond)
        return cond
PYEOF

echo "   ✅ workflow/engine.py — Condiciones dinámicas implementadas"

# ─── NOTIFICACIONES — SMTP + SMS reales ──────────────────────────────────────

cat > "$BACKEND_DIR/app/modules/notifications/service.py" << 'PYEOF'
# Copyright © 2026 Cristian Rodriguez
"""Servicio de notificaciones — SMTP + SMS + WebSocket + Panel."""
import smtplib
import json
from typing import Optional, Dict, Any, List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.config import settings
from app.core.errors import MegalodonException, ErrorCode

class NotificationService:
    """Servicio de notificaciones multi-canal."""

    def __init__(self):
        self.smtp_host = getattr(settings, 'SMTP_HOST', None)
        self.smtp_port = getattr(settings, 'SMTP_PORT', 587)
        self.smtp_user = getattr(settings, 'SMTP_USER', None)
        self.smtp_password = getattr(settings, 'SMTP_PASSWORD', None)
        self.smtp_tls = getattr(settings, 'SMTP_TLS', True)
        self.twilio_sid = getattr(settings, 'TWILIO_SID', None)
        self.twilio_token = getattr(settings, 'TWILIO_TOKEN', None)
        self.twilio_from = getattr(settings, 'TWILIO_FROM_NUMBER', None)

    async def enviar(
        self,
        db: AsyncSession,
        tipo: str,  # email, sms, websocket, panel, all
        destinatario: str,
        asunto: str,
        mensaje: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Envía notificación por el canal especificado."""
        resultados = {}

        if tipo in ("email", "all"):
            resultados["email"] = await self._enviar_email(destinatario, asunto, mensaje)
        if tipo in ("sms", "all"):
            resultados["sms"] = await self._enviar_sms(destinatario, mensaje)
        if tipo in ("websocket", "all"):
            resultados["websocket"] = await self._enviar_websocket(destinatario, asunto, mensaje, metadata)
        if tipo in ("panel", "all"):
            resultados["panel"] = await self._guardar_panel(db, destinatario, asunto, mensaje, metadata)

        return {
            "enviado": any(r.get("enviado") for r in resultados.values()),
            "canales": resultados,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _enviar_email(
        self,
        destinatario: str,
        asunto: str,
        mensaje: str,
    ) -> Dict[str, Any]:
        """Envía email vía SMTP."""
        if not all([self.smtp_host, self.smtp_user, self.smtp_password]):
            return {"enviado": False, "motivo": "SMTP no configurado"}

        try:
            msg = MIMEMultipart()
            msg["From"] = self.smtp_user
            msg["To"] = destinatario
            msg["Subject"] = asunto
            msg.attach(MIMEText(mensaje, "html" if "<" in mensaje else "plain"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_tls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            return {"enviado": True, "canal": "SMTP"}
        except Exception as e:
            return {"enviado": False, "motivo": str(e)}

    async def _enviar_sms(
        self,
        destinatario: str,
        mensaje: str,
    ) -> Dict[str, Any]:
        """Envía SMS vía Twilio."""
        if not all([self.twilio_sid, self.twilio_token, self.twilio_from]):
            return {"enviado": False, "motivo": "SMS no configurado (Twilio)"}

        try:
            from twilio.rest import Client
            client = Client(self.twilio_sid, self.twilio_token)
            message = client.messages.create(
                body=mensaje[:1600],  # Twilio limit
                from_=self.twilio_from,
                to=destinatario,
            )
            return {"enviado": True, "canal": "Twilio", "sid": message.sid}
        except ImportError:
            return {"enviado": False, "motivo": "Librería twilio no instalada"}
        except Exception as e:
            return {"enviado": False, "motivo": str(e)}

    async def _enviar_websocket(
        self,
        destinatario: str,
        asunto: str,
        mensaje: str,
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Envía notificación vía WebSocket."""
        # El WebSocket manager se inyecta desde el main app
        from app.api.v1.websocket import manager
        payload = {
            "tipo": "notificacion",
            "destinatario": destinatario,
            "asunto": asunto,
            "mensaje": mensaje,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        }
        try:
            await manager.broadcast(json.dumps(payload))
            return {"enviado": True, "canal": "WebSocket"}
        except Exception as e:
            return {"enviado": False, "motivo": str(e)}

    async def _guardar_panel(
        self,
        db: AsyncSession,
        destinatario: str,
        asunto: str,
        mensaje: str,
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Guarda notificación persistente en panel."""
        from app.models.notifications import NotificationLog
        log = NotificationLog(
            destinatario=destinatario,
            tipo="panel",
            asunto=asunto,
            mensaje=mensaje,
            metadata=metadata,
            estado="PENDIENTE",
        )
        db.add(log)
        await db.commit()
        await db.refresh(log)
        return {"enviado": True, "canal": "Panel", "log_id": str(log.id)}

    async def obtener_pendientes(
        self,
        db: AsyncSession,
        destinatario: str,
        limite: int = 50,
    ) -> List[Dict[str, Any]]:
        """Obtiene notificaciones pendientes del panel."""
        from app.models.notifications import NotificationLog
        stmt = select(NotificationLog).where(
            and_(
                NotificationLog.destinatario == destinatario,
                NotificationLog.estado == "PENDIENTE",
            )
        ).order_by(NotificationLog.created_at.desc()).limit(limite)
        logs = (await db.execute(stmt)).scalars().all()
        return [{"id": str(l.id), "asunto": l.asunto, "mensaje": l.mensaje,
                 "created_at": l.created_at.isoformat()} for l in logs]

    async def marcar_leida(
        self,
        db: AsyncSession,
        notification_id: str,
    ) -> bool:
        """Marca una notificación como leída."""
        from app.models.notifications import NotificationLog
        log = await db.get(NotificationLog, notification_id)
        if log:
            log.estado = "LEIDA"
            log.leida_at = datetime.utcnow()
            await db.commit()
            return True
        return False
PYEOF

echo "   ✅ notifications/service.py — SMTP + SMS + WebSocket + Panel"

echo ""
echo "🦈 Script 5 completado. Workflow dinámico + Notificaciones reales."
echo "   Ejecutar: bash scripts_fase2/05_workflow_notificaciones.sh ./backend"
