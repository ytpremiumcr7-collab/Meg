# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Validador - Motor de validación de expedientes.
Validaciones automáticas de requisitos, documentos, montos, plazos.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4

from sqlalchemy import String, Text, ForeignKey, Index, DateTime, Boolean, Integer
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TenantMixin, AuditMixin
from enum import Enum


class TipoValidacion(str, Enum):
    """Tipos de validaciones disponibles."""
    DOCUMENTAL = "DOCUMENTAL"
    FINANCIERA = "FINANCIERA"
    TECNICA = "TECNICA"
    TEMPORAL = "TEMPORAL"
    NORMATIVA = "NORMATIVA"
    INTEGRIDAD = "INTEGRIDAD"


class EstadoValidacion(str, Enum):
    """Estados de una validación."""
    PENDIENTE = "PENDIENTE"
    EN_PROCESO = "EN_PROCESO"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"
    CON_OBSERVACIONES = "CON_OBSERVACIONES"


class ValidacionExpediente(Base, UUIDMixin, TenantMixin):
    """Validación de un expediente.

    Agrupa múltiples checks de validación aplicados a un expediente.
    """
    __tablename__ = "validaciones_expediente"

    expediente_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Tipo y descripción
    tipo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Estado
    estado: Mapped[str] = mapped_column(String(50), default="PENDIENTE", nullable=False)

    # Resultados detallados
    resultados: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # Ejemplo: [
    #   {"check": "Documentos completos", "estado": "APROBADO", "detalle": "12/12 documentos presentes"},
    #   {"check": "Monto dentro de umbral", "estado": "APROBADO", "detalle": "$45M dentro de límite"},
    #   {"check": "Plazo razonable", "estado": "RECHAZADO", "detalle": "365 días excede estándar de 180"},
    # ]

    # Observaciones
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Ejecutor
    ejecutado_por_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    fecha_ejecucion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Score de validación (0-100)
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_validacion_expediente_tipo", "expediente_id", "tipo"),
        Index("ix_validacion_estado", "estado"),
    )


class ValidacionPropuesta(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Validación determinista de una propuesta de licitación.

    Registra el resultado de correr los 10 validadores reales de
    app.engines.validadores.motor_validador.MotorDeterministaLicitaciones
    (SAT 32-D, seguridad social, firma electrónica, FSR, costos horarios
    de maquinaria, sobrecostos, congruencia temporal, garantía de
    cumplimiento, publicación SIRECO y requisitos de participación) sobre
    los datos de una propuesta. Es el registro auditable de esa corrida:
    qué se evaluó, con qué datos de entrada, bajo qué reglas y con qué
    resultado -- ver ValidadorService.evaluar_propuesta_completa().

    RESTAURADO: este modelo se había perdido al añadir ValidacionExpediente
    / CheckValidacion (un flujo distinto, para validar la completitud
    documental de un expediente en general). Los dos flujos son
    complementarios y ambos se conservan:
      - ValidacionExpediente: ¿está completo/conforme el expediente?
      - ValidacionPropuesta:  ¿es solvente esta propuesta de un licitante?
    app/services/validador_service.py, app/api/v1/validadores.py y
    app/models/__init__.py ya esperaban esta clase; sin ella el import de
    app.models fallaba en cadena para todo el backend.
    """
    __tablename__ = "validaciones_propuesta"

    expediente_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Vínculo opcional a una Proposicion concreta (app.models.licitacion).
    # Opcional porque el motor determinista también sirve como pre-chequeo
    # de cumplimiento sobre datos de propuesta que aún no se formalizan
    # como Proposicion dentro de una Licitacion (p. ej. borrador previo a
    # someter la oferta). Cuando sí corresponde a una Proposicion ya
    # existente, se enlaza aquí y el resultado se sincroniza de vuelta
    # hacia ella (firma_valida / cumplimiento_documental / integridad_valida
    # / estado) -- ver ValidadorService.evaluar_propuesta_completa().
    proposicion_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proposiciones.id", ondelete="SET NULL"), nullable=True, index=True
    )

    rfc_empresa: Mapped[Optional[str]] = mapped_column(String(13), nullable=True, index=True)

    # SOLVENTE | DESCALIFICADO (ver MotorDeterministaLicitaciones.procesar_propuesta)
    estado: Mapped[str] = mapped_column(String(30), nullable=False, default="SOLVENTE", index=True)

    # Bitácora completa devuelta por el motor: lista de
    # {"id_regla", "seccion", "estatus" (PASA/FALLA/NO_APLICA),
    #  "valor_detectado", "valor_esperado", "evidencia"}
    bitacora_evaluacion: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Payload completo recibido para esta corrida (trazabilidad/reproducibilidad).
    datos_entrada: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_validacion_propuesta_expediente", "expediente_id", "estado"),
        Index("ix_validacion_propuesta_proposicion", "proposicion_id"),
    )


class CheckValidacion(Base, UUIDMixin, TenantMixin):
    """Check individual de validación.

    Un check es una validación atómica que puede ser reutilizada
    en múltiples validaciones de expediente.
    """
    __tablename__ = "checks_validacion"

    # Identificación
    codigo: Mapped[str] = mapped_column(String(50), nullable=False, index=True, unique=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Categoría
    categoria: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # DOCUMENTAL, FINANCIERA, TECNICA, TEMPORAL, NORMATIVA

    # Lógica de validación
    logica: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Ejemplo: {
    #   "tipo": "documento_existe",
    #   "parametros": {"tipo_documento": "CONVOCATORIA", "requerido": true}
    # }
    # O:
    # {
    #   "tipo": "rango_numerico",
    #   "parametros": {"campo": "monto_contrato", "min": 0, "max": 100000000}
    # }

    # Mensajes
    mensaje_exito: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    mensaje_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Severidad
    severidad: Mapped[str] = mapped_column(String(20), default="MEDIA", nullable=False)
    # BLOQUEANTE, ALTA, MEDIA, BAJA, INFORMATIVA

    # Estado
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Orden de ejecución
    orden: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_checks_categoria_activo", "categoria", "activo"),
        Index("ix_checks_orden", "orden"),
    )