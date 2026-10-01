from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from app.models.user import User
from app.schemas.indices_costos import (
    AcreditacionMonedaCreate,
    ActualizacionPrecioInput,
    ObservacionIndiceCreate,
    RetiroIndiceCreate,
    SerieIndiceCreate,
    VinculoIndiceCreate,
)
from app.services.indices_costos_service import IndicesCostosService

router = APIRouter(dependencies=[Depends(get_current_user)])


def servicio(db: Annotated[AsyncSession, Depends(get_db)], usuario: Annotated[User, Depends(get_current_user)]):
    return IndicesCostosService(db, usuario)


@router.post('/series', status_code=201, dependencies=[Depends(rate_limit_strict)])
async def crear_serie(data: SerieIndiceCreate, service: Annotated[IndicesCostosService, Depends(servicio)]):
    return await service.crear_serie(data)


@router.get('/series', dependencies=[Depends(rate_limit_standard)])
async def listar_series(service: Annotated[IndicesCostosService, Depends(servicio)], skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    return await service.listar_series(skip, limit)


@router.post('/observaciones', status_code=201, dependencies=[Depends(rate_limit_strict)])
async def crear_observacion(data: ObservacionIndiceCreate, service: Annotated[IndicesCostosService, Depends(servicio)]):
    return await service.crear_observacion(data)


@router.get('/observaciones', dependencies=[Depends(rate_limit_standard)])
async def listar_observaciones(serie_id: UUID, service: Annotated[IndicesCostosService, Depends(servicio)], skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    return await service.listar_observaciones(serie_id, skip, limit)


@router.post('/vinculos', status_code=201, dependencies=[Depends(rate_limit_strict)])
async def crear_vinculo(data: VinculoIndiceCreate, service: Annotated[IndicesCostosService, Depends(servicio)]):
    return await service.crear_vinculo(data)


@router.get('/vinculos', dependencies=[Depends(rate_limit_standard)])
async def listar_vinculos(service: Annotated[IndicesCostosService, Depends(servicio)], skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    return await service.listar_vinculos(skip, limit)


@router.post('/calcular', dependencies=[Depends(rate_limit_standard)])
async def calcular(data: ActualizacionPrecioInput, service: Annotated[IndicesCostosService, Depends(servicio)]):
    return await service.resolver(data)


@router.post('/retiros', status_code=201, dependencies=[Depends(rate_limit_strict)])
async def retirar(data: RetiroIndiceCreate, service: Annotated[IndicesCostosService, Depends(servicio)]):
    return await service.retirar(data)


@router.post('/acreditaciones-moneda', status_code=201, dependencies=[Depends(rate_limit_strict)])
async def acreditar_moneda(data: AcreditacionMonedaCreate, service: Annotated[IndicesCostosService, Depends(servicio)]):
    return await service.acreditar_moneda(data)
