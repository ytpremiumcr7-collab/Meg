# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Audit Ledger / Bitácora inmutable.
Registro de acciones: quién hizo qué, cuándo, sobre qué expediente.
"""
from enum import Enum
from uuid import uuid4

from sqlalchemy import String, Text, ForeignKey, Index, DateTime
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, TenantMixin


class TipoAccion(str, Enum):
    CREAR = "CREAR"
    MODIFICAR = "MODIFICAR"
    ELIMINAR = "ELIMINAR"
    CONSULTAR = "CONSULTAR"
    APROBAR = "APROBAR"
    RECHAZAR = "RECHAZAR"
    FIRMAR = "FIRMAR"
    PUBLICAR = "PUBLICAR"
    ARCHIVAR = "ARCHIVAR"
    EXPORTAR = "EXPORTAR"


class AuditLedger(Base, UUIDMixin, TenantMixin):
    """Registro inmutable de acciones sobre el sistema."""
    __tablename__ = "audit_ledger"

    user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_role: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Entidad afectada
    entidad_tipo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # EXPEDIENTE, DOCUMENTO, etc.
    entidad_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Acción
    accion: Mapped[TipoAccion] = mapped_column(String(50), nullable=False, index=True)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Datos de trazabilidad
    datos_anteriores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    datos_nuevos: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Evidencia criptográfica
    hash_registro: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    hash_previo: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Contexto
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        Index("ix_audit_entidad_accion", "entidad_tipo", "entidad_id", "accion"),
        Index("ix_audit_fecha", "created_at"),
    )
