# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
AuditService - Servicio de auditoría y bitácora inmutable.
Consultas, reportes y verificación de integridad del audit ledger.
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_ledger import AuditLedger, TipoAccion
from app.services.base import BaseService
from app.core.errors import MegalodonException, ErrorCode


class AuditService(BaseService[AuditLedger]):
    """Servicio de auditoría con consultas avanzadas y reportes."""

    def __init__(self, db: AsyncSession):
        super().__init__(AuditLedger, db)

    async def registrar_accion(
        self,
        *,
        user_id: Optional[UUID],
        user_email: Optional[str],
        user_role: Optional[str],
        entidad_tipo: str,
        entidad_id: str,
        accion: TipoAccion,
        descripcion: Optional[str] = None,
        datos_anteriores: Optional[Dict] = None,
        datos_nuevos: Optional[Dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        hash_previo: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
    ) -> AuditLedger:
        import hashlib
        import json

        payload = {
            "user_id": str(user_id) if user_id else None,
            "entidad_tipo": entidad_tipo,
            "entidad_id": entidad_id,
            "accion": accion.value,
            "descripcion": descripcion,
            "datos_nuevos": datos_nuevos,
            "timestamp": datetime.utcnow().isoformat(),
            "hash_previo": hash_previo,
        }
        hash_registro = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()

        registro = await self.create({
            "tenant_id": tenant_id,
            "user_id": user_id,
            "user_email": user_email,
            "user_role": user_role,
            "entidad_tipo": entidad_tipo,
            "entidad_id": entidad_id,
            "accion": accion,
            "descripcion": descripcion,
            "datos_anteriores": datos_anteriores,
            "datos_nuevos": datos_nuevos,
            "hash_registro": hash_registro,
            "hash_previo": hash_previo,
            "ip_address": ip_address,
            "user_agent": user_agent,
        })
        return registro

    async def obtener_historial_expediente(
        self,
        expediente_id: str,
        *,
        skip: int = 0,
        limit: int = 100,
        tenant_id: Optional[UUID] = None,
    ) -> List[AuditLedger]:
        query = select(AuditLedger).where(
            and_(
                AuditLedger.entidad_tipo == "EXPEDIENTE",
                AuditLedger.entidad_id == str(expediente_id),
            )
        )
        if tenant_id is not None:
            query = query.where(AuditLedger.tenant_id == tenant_id)
        result = await self.db.execute(
            query.order_by(desc(AuditLedger.created_at)).offset(skip).limit(limit)
        )
        return result.scalars().all()

    async def obtener_historial_documento(
        self,
        documento_id: str,
        *,
        skip: int = 0,
        limit: int = 100,
        tenant_id: Optional[UUID] = None,
    ) -> List[AuditLedger]:
        query = select(AuditLedger).where(
            and_(
                AuditLedger.entidad_tipo == "DOCUMENTO",
                AuditLedger.entidad_id == str(documento_id),
            )
        )
        if tenant_id is not None:
            query = query.where(AuditLedger.tenant_id == tenant_id)
        result = await self.db.execute(
            query.order_by(desc(AuditLedger.created_at)).offset(skip).limit(limit)
        )
        return result.scalars().all()

    async def verificar_integridad_cadena(
        self,
        entidad_tipo: str,
        entidad_id: str,
        tenant_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        import hashlib
        import json

        query = select(AuditLedger).where(
            and_(
                AuditLedger.entidad_tipo == entidad_tipo,
                AuditLedger.entidad_id == str(entidad_id),
            )
        )
        if tenant_id is not None:
            query = query.where(AuditLedger.tenant_id == tenant_id)
        result = await self.db.execute(query.order_by(AuditLedger.created_at))
        registros = result.scalars().all()

        if not registros:
            return {"valido": True, "registros": 0, "errores": []}

        errores = []
        hash_previo_esperado = None
        for i, reg in enumerate(registros):
            payload = {
                "user_id": str(reg.user_id) if reg.user_id else None,
                "entidad_tipo": reg.entidad_tipo,
                "entidad_id": reg.entidad_id,
                "accion": reg.accion.value if hasattr(reg.accion, 'value') else reg.accion,
                "descripcion": reg.descripcion,
                "datos_nuevos": reg.datos_nuevos,
                "timestamp": reg.created_at.isoformat() if reg.created_at else None,
                "hash_previo": reg.hash_previo,
            }
            hash_recomputado = hashlib.sha256(
                json.dumps(payload, sort_keys=True, default=str).encode()
            ).hexdigest()
            if hash_recomputado != reg.hash_registro:
                errores.append({
                    "indice": i,
                    "registro_id": str(reg.id),
                    "hash_almacenado": reg.hash_registro,
                    "hash_recomputado": hash_recomputado,
                    "tipo_error": "HASH_NO_COINCIDE",
                })
            if hash_previo_esperado is not None and reg.hash_previo != hash_previo_esperado:
                errores.append({
                    "indice": i,
                    "registro_id": str(reg.id),
                    "hash_previo_almacenado": reg.hash_previo,
                    "hash_previo_esperado": hash_previo_esperado,
                    "tipo_error": "CADENA_ROTA",
                })
            hash_previo_esperado = reg.hash_registro

        return {
            "valido": len(errores) == 0,
            "registros": len(registros),
            "errores": errores,
        }

    async def reporte_actividad_usuario(
        self,
        user_id: UUID,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
        tenant_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        query = select(AuditLedger).where(AuditLedger.user_id == user_id)
        if tenant_id is not None:
            query = query.where(AuditLedger.tenant_id == tenant_id)
        if fecha_inicio:
            query = query.where(AuditLedger.created_at >= fecha_inicio)
        if fecha_fin:
            query = query.where(AuditLedger.created_at <= fecha_fin)

        result = await self.db.execute(query)
        registros = result.scalars().all()

        acciones = {}
        entidades = {}
        for r in registros:
            accion_key = r.accion.value if hasattr(r.accion, 'value') else str(r.accion)
            acciones[accion_key] = acciones.get(accion_key, 0) + 1
            entidades[r.entidad_tipo] = entidades.get(r.entidad_tipo, 0) + 1

        return {
            "user_id": str(user_id),
            "total_registros": len(registros),
            "periodo": {
                "inicio": fecha_inicio.isoformat() if fecha_inicio else None,
                "fin": fecha_fin.isoformat() if fecha_fin else None,
            },
            "acciones": acciones,
            "entidades_afectadas": entidades,
            "registros": [
                {
                    "id": str(r.id),
                    "accion": r.accion.value if hasattr(r.accion, 'value') else str(r.accion),
                    "entidad_tipo": r.entidad_tipo,
                    "entidad_id": r.entidad_id,
                    "descripcion": r.descripcion,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in registros
            ],
        }

    async def reporte_actividad_sistema(
        self,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
        tenant_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        query = select(AuditLedger)
        if tenant_id is not None:
            query = query.where(AuditLedger.tenant_id == tenant_id)
        if fecha_inicio:
            query = query.where(AuditLedger.created_at >= fecha_inicio)
        if fecha_fin:
            query = query.where(AuditLedger.created_at <= fecha_fin)

        result = await self.db.execute(query)
        registros = result.scalars().all()

        usuarios = {}
        acciones = {}
        for r in registros:
            if r.user_email:
                usuarios[r.user_email] = usuarios.get(r.user_email, 0) + 1
            accion_key = r.accion.value if hasattr(r.accion, 'value') else str(r.accion)
            acciones[accion_key] = acciones.get(accion_key, 0) + 1

        return {
            "total_registros": len(registros),
            "periodo": {
                "inicio": fecha_inicio.isoformat() if fecha_inicio else None,
                "fin": fecha_fin.isoformat() if fecha_fin else None,
            },
            "top_usuarios": sorted(usuarios.items(), key=lambda x: x[1], reverse=True)[:10],
            "acciones": acciones,
        }
