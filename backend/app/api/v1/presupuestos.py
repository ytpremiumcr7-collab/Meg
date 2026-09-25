# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
API de presupuestos programables conectada a PresupuestoService.
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, verificar_expediente_tenant
from app.services.presupuesto_service import PresupuestoService
from app.services.entitlements_service import EntitlementsService
from app.models.user import User, Tenant
from app.schemas.costos import ParametrosCosteoInput

# BUG ORIGINAL: ningún endpoint verificaba que expediente_id perteneciera
# al tenant del usuario -- ver app.core.deps.verificar_expediente_tenant.
router = APIRouter(dependencies=[Depends(verificar_expediente_tenant)])


class PartidaCreate(BaseModel):
    numero: int
    descripcion: str
    unidad: str
    cantidad: float = Field(..., gt=0)
    # BUG ORIGINAL: era requerido (Field(..., gt=0)) SIEMPRE, incluso para
    # partidas con APU (conceptos/insumos) donde el precio se calcula solo.
    # Ahora solo es obligatorio para partidas tipo tabulador (sin
    # conceptos), donde el precio ya viene resuelto de un catálogo oficial.
    precio_unitario: Optional[float] = Field(None, gt=0)
    insumos: Optional[List[dict]] = Field(default_factory=list)
    conceptos: Optional[List[dict]] = Field(default_factory=list)


class PresupuestoCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    partidas: List[PartidaCreate]
    parametros_costeo: ParametrosCosteoInput
    zona_economica: str = "CENTRO"


class ActualizarParametrosCosteoRequest(BaseModel):
    parametros_costeo: ParametrosCosteoInput


class InsumoOut(BaseModel):
    id: UUID
    clave: str
    descripcion: str
    tipo: str
    unidad: str
    cantidad: float
    precio_unitario: float
    importe: float
    rendimiento: float

    class Config:
        from_attributes = True


class ConceptoOut(BaseModel):
    id: UUID
    clave: str
    descripcion: str
    unidad: str
    cantidad: float
    costo_directo_unitario: float
    insumos: List[InsumoOut] = Field(default_factory=list)

    class Config:
        from_attributes = True


class PartidaOut(BaseModel):
    id: UUID
    numero: int
    descripcion: str
    unidad: str
    cantidad: float
    precio_unitario: float
    importe: float
    conceptos: List[ConceptoOut] = Field(default_factory=list)

    class Config:
        from_attributes = True


class AgregarPartidaCatalogoRequest(BaseModel):
    catalogo_apu_id: UUID
    cantidad: float = Field(..., gt=0)


class ActualizarCantidadPartidaRequest(BaseModel):
    cantidad: float = Field(..., gt=0)


class PresupuestoOut(BaseModel):
    """Response model explícito: evita serializar el ORM crudo
    (riesgo de DetachedInstanceError si se accede a relaciones no
    cargadas después de que get_db cierra la sesión)."""
    id: UUID
    identificador: str
    nombre: str
    descripcion: Optional[str] = None
    expediente_id: UUID
    monto_directo: float
    monto_indirecto: float
    monto_utilidad: float
    monto_riesgo: Optional[float] = None
    monto_impuesto: float
    monto_total: float
    moneda: str
    factor_indirecto: float
    factor_utilidad: float
    factor_impuesto: float
    factor_riesgo: Optional[float] = None
    metadatos: Optional[dict] = None
    zona_economica: str
    estado: Optional[str] = None
    # BUG ORIGINAL: no se exponían las partidas -- no había forma de ver
    # los conceptos reales de un presupuesto a través de esta API, solo
    # los montos agregados.
    partidas: List[PartidaOut] = Field(default_factory=list)
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


@router.post("/{expediente_id}/presupuestos", response_model=PresupuestoOut)
async def crear_presupuesto(
    expediente_id: UUID,
    data: PresupuestoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = PresupuestoService(db, current_user.tenant_id)

    partidas_data = []
    for p in data.partidas:
        partidas_data.append({
            "numero": p.numero,
            "descripcion": p.descripcion,
            "unidad": p.unidad,
            "cantidad": p.cantidad,
            # BUG ORIGINAL: precio_unitario nunca se incluía aquí, así que
            # el caso "partida de tabulador con precio ya conocido" jamás
            # llegaba al servicio (siempre se recalculaba en 0.00).
            "precio_unitario": p.precio_unitario,
            "insumos": p.insumos or [],
            "conceptos": p.conceptos or [],
        })

    presupuesto = await service.crear_desde_costeo(
        expediente_id=expediente_id,
        nombre=data.nombre,
        descripcion=data.descripcion,
        partidas_data=partidas_data,
        parametros_costeo=data.parametros_costeo.to_domain(),
        zona_economica=data.zona_economica,
        creado_por_id=current_user.id,
    )

    return presupuesto


@router.put(
    "/{expediente_id}/presupuestos/{presupuesto_id}/parametros-costeo",
    response_model=PresupuestoOut,
)
async def actualizar_parametros_costeo(
    expediente_id: UUID,
    presupuesto_id: UUID,
    data: ActualizarParametrosCosteoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    service = PresupuestoService(db, current_user.tenant_id)
    return await service.actualizar_parametros_costeo(
        presupuesto_id,
        expediente_id,
        data.parametros_costeo.to_domain(),
        actualizado_por_id=current_user.id,
    )


@router.get("/{expediente_id}/presupuestos", response_model=List[PresupuestoOut])
async def listar_presupuestos(
    expediente_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    service = PresupuestoService(db, current_user.tenant_id)
    presupuestos = await service.listar_por_expediente(expediente_id, skip=skip, limit=limit)
    return presupuestos


@router.post(
    "/{expediente_id}/presupuestos/{presupuesto_id}/partidas/desde-catalogo",
    response_model=PresupuestoOut,
)
async def agregar_partida_desde_catalogo(
    expediente_id: UUID,
    presupuesto_id: UUID,
    data: AgregarPartidaCatalogoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Agrega una partida al presupuesto tomando el precio (y desglose de
    insumos si lo tiene) de un concepto real del catálogo maestro
    (CatalogoAPU: CMIC, CFE, Pemex, investigación de mercado, etc.).
    Antes solo se podían cargar partidas todas de golpe al crear el
    presupuesto -- no había forma de ir agregando una por una después."""
    service = PresupuestoService(db, current_user.tenant_id)
    return await service.agregar_partida_desde_catalogo(
        presupuesto_id, expediente_id=expediente_id,
        catalogo_apu_id=data.catalogo_apu_id, cantidad=data.cantidad,
        actualizado_por_id=current_user.id,
    )


@router.patch(
    "/{expediente_id}/presupuestos/{presupuesto_id}/partidas/{partida_id}",
    response_model=PresupuestoOut,
)
async def actualizar_cantidad_partida(
    expediente_id: UUID,
    presupuesto_id: UUID,
    partida_id: UUID,
    data: ActualizarCantidadPartidaRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = PresupuestoService(db, current_user.tenant_id)
    return await service.actualizar_cantidad_partida(
        presupuesto_id, expediente_id=expediente_id, partida_id=partida_id,
        nueva_cantidad=data.cantidad, actualizado_por_id=current_user.id,
    )


@router.delete(
    "/{expediente_id}/presupuestos/{presupuesto_id}/partidas/{partida_id}",
    response_model=PresupuestoOut,
)
async def eliminar_partida(
    expediente_id: UUID,
    presupuesto_id: UUID,
    partida_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = PresupuestoService(db, current_user.tenant_id)
    return await service.eliminar_partida(
        presupuesto_id, expediente_id=expediente_id, partida_id=partida_id,
        actualizado_por_id=current_user.id,
    )


@router.post("/{expediente_id}/presupuestos/{presupuesto_id}/recalcular", response_model=PresupuestoOut)
async def recalcular_presupuesto(
    expediente_id: UUID,
    presupuesto_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    # BUG ORIGINAL: max_corridas_costeo_mes existía en PlanLimite pero
    # nada lo hacía cumplir -- esta es la "corrida de costeo" que el plan
    # limita (3/mes en Free, 25 en Intermedio, etc.), así que se cuenta
    # aquí antes de recalcular.
    tenant = await db.get(Tenant, current_user.tenant_id)
    await EntitlementsService(db).verificar_y_registrar_uso(tenant, "corridas_costeo")

    service = PresupuestoService(db, current_user.tenant_id)
    presupuesto = await service.recalcular(
        presupuesto_id, expediente_id=expediente_id, actualizado_por_id=current_user.id,
    )
    return presupuesto


class CambiarEstadoPresupuestoRequest(BaseModel):
    estado: str  # BORRADOR | CALCULADO | VALIDADO | RECHAZADO | APROBADO


@router.patch("/{expediente_id}/presupuestos/{presupuesto_id}/estado", response_model=PresupuestoOut)
async def cambiar_estado_presupuesto(
    expediente_id: UUID,
    presupuesto_id: UUID,
    data: CambiarEstadoPresupuestoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """No existía ningún mecanismo para marcar un presupuesto como
    validado/aprobado/rechazado -- el campo `estado` tampoco existía
    antes de esta ronda de unificación del modelo de datos."""
    service = PresupuestoService(db, current_user.tenant_id)
    return await service.cambiar_estado(
        presupuesto_id, expediente_id=expediente_id, nuevo_estado=data.estado,
        actualizado_por_id=current_user.id,
    )


@router.get("/{expediente_id}/presupuestos/{presupuesto_id}/excel")
async def exportar_excel(
    expediente_id: UUID,
    presupuesto_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    from fastapi.responses import StreamingResponse
    import io

    service = PresupuestoService(db, current_user.tenant_id)
    excel_bytes = await service.generar_excel(presupuesto_id, expediente_id=expediente_id)

    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=presupuesto_{presupuesto_id}.xlsx"},
    )


@router.get("/{expediente_id}/presupuestos/{presupuesto_id}/pdf")
async def exportar_pdf(
    expediente_id: UUID,
    presupuesto_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Versión síncrona -- para presupuestos grandes usar el worker
    async (app/workers/pdf_tasks.py) vía el endpoint de exportaciones."""
    from fastapi.responses import StreamingResponse
    import io

    service = PresupuestoService(db, current_user.tenant_id)
    pdf_bytes = await service.generar_pdf(presupuesto_id, expediente_id=expediente_id)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=presupuesto_{presupuesto_id}.pdf"},
    )


@router.post("/{expediente_id}/presupuestos/{presupuesto_id}/validar-sobrecostos")
async def validar_sobrecostos(
    expediente_id: UUID,
    presupuesto_id: UUID,
    presupuesto_base_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = PresupuestoService(db, current_user.tenant_id)
    resultado = await service.validar_sobrecostos(presupuesto_id, expediente_id=expediente_id, presupuesto_base_id=presupuesto_base_id)
    return resultado
