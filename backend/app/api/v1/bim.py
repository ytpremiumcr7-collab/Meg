# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
API BIM/IFC — cuantificación real conectada a BIMService.

BUG ORIGINAL (histórico): subir_ifc() encolaba una tarea de Celery
pasando solo filename/content_type (nunca los bytes del archivo), y el
worker (bim_tasks.py) tenía un TODO sin implementar -- nada se procesaba
nunca, la tarea siempre regresaba elementos_count=0 hardcodeado. Se
resolvió haciendo el procesamiento SÍNCRONO mientras no hubiera storage
real de donde el worker pudiera leer el archivo de forma asíncrona.

Storage real (Supabase, ver STORAGE_SUPABASE.md) y el worker
(workers/bim_tasks.py:procesar_ifc) ya existen y están probados -- este
endpoint ahora sí encola en vez de procesar en el request. Un IFC grande
ya no bloquea el request completo; el frontend hace polling a
GET /modelos/{id} hasta que estado_procesamiento sea COMPLETADO o ERROR.
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, verificar_expediente_tenant
from app.core.errors import MegalodonException, ErrorCode
from app.config import settings
from app.models.base import EstadoProceso
from app.services.bim_service import BIMService
from app.services.clash_service import ClashService
from app.models.user import User
from app.schemas.costos import ParametrosCosteoInput
from app.utils.upload_limits import read_upload_with_limit

# BUG ORIGINAL: ningún endpoint de este router verificaba que
# expediente_id perteneciera al tenant del usuario autenticado -- ver
# nota completa en app.core.deps.verificar_expediente_tenant. Todas las
# rutas de este archivo cuelgan de /{expediente_id}/..., así que se
# aplica una sola vez a nivel router.
router = APIRouter(dependencies=[Depends(verificar_expediente_tenant)])


class ModeloBIMOut(BaseModel):
    id: UUID
    identificador: str
    nombre: str
    descripcion: Optional[str] = None
    expediente_id: UUID
    estado_procesamiento: str
    num_elementos: int
    niveles: Optional[List[str]] = None
    version_ifc: Optional[str] = None
    error_procesamiento: Optional[str] = None

    class Config:
        from_attributes = True


class ElementoBIMOut(BaseModel):
    id: UUID
    modelo_id: UUID
    global_id: str
    tipo: str
    nombre: Optional[str] = None
    volumen: Optional[float] = None
    area: Optional[float] = None
    longitud: Optional[float] = None
    fuente_volumen: str
    fuente_area: str
    nivel: Optional[str] = None
    bbox: Optional[List[float]] = None
    partida_id: Optional[UUID] = None
    malla_vertices: Optional[list] = None
    malla_caras: Optional[list] = None

    class Config:
        from_attributes = True


class MapeoPartida(BaseModel):
    elemento_id: UUID
    partida_id: UUID


class GenerarPresupuestoRequest(BaseModel):
    nombre: str = "Presupuesto desde BIM"
    parametros_costeo: ParametrosCosteoInput
    # 5D real: {tipo_ifc: catalogo_apu_id}. Los tipos incluidos aquí se
    # presupuestan con precio real del catálogo (y su desglose de
    # insumos si lo trae); los que no, quedan como antes -- solo
    # cantidades, pendientes de costeo manual.
    mapeo_catalogo: Optional[Dict[str, UUID]] = None


class AsignarZona4D(BaseModel):
    elemento_id: UUID
    zona_4d: str


class GenerarActividades4DRequest(BaseModel):
    fecha_inicio: datetime
    # Duración base configurable; la estimación final la ajusta el
    # servicio BIM con el tamaño y la complejidad geométrica del grupo.
    dias_por_defecto: float = 5.0
    nombre_programa: Optional[str] = None


class GeneracionBIM4D5DOut(BaseModel):
    id: UUID
    modelo_id: UUID
    expediente_id: UUID
    programa_id: Optional[UUID] = None
    estado: str
    error: Optional[str] = None
    agrupar_por: str
    dias_por_defecto: float
    num_actividades_generadas: Optional[int] = None

    class Config:
        from_attributes = True


class EjecutarClashRequest(BaseModel):
    # 0 = solo traslape real ("clash duro"). >0 = también marca pares que
    # están más cerca que esta distancia sin llegar a tocarse ("clash
    # blando" -- típico para reglas de clearance MEP vs estructura).
    tolerancia_m: float = 0.0
    tipos_incluidos: Optional[List[str]] = None
    tipos_excluidos: Optional[List[str]] = None


class AnalisisClashOut(BaseModel):
    id: UUID
    modelo_id: UUID
    tolerancia_m: float
    estado: str
    num_pares_evaluados: int
    num_clashes_duros: int
    num_clashes_blandos: int
    tiempo_calculo_ms: Optional[int] = None
    error: Optional[str] = None

    class Config:
        from_attributes = True


class ClashResultOut(BaseModel):
    id: UUID
    analisis_id: UUID
    elemento_a_id: UUID
    elemento_b_id: UUID
    tipo_a: str
    tipo_b: str
    severidad: str
    distancia_m: float
    volumen_aproximado_m3: Optional[float] = None
    punto_cercano_a: List[float]
    punto_cercano_b: List[float]
    triangulos_a: Optional[list] = None
    triangulos_b: Optional[list] = None
    estado: str

    class Config:
        from_attributes = True


class ActualizarEstadoClashRequest(BaseModel):
    estado: str  # NUEVO | REVISADO | RESUELTO | IGNORADO


@router.get("/{expediente_id}/modelos", response_model=List[ModeloBIMOut])
async def listar_modelos_bim(
    expediente_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista los modelos BIM de un expediente (más reciente primero)."""
    service = BIMService(db, tenant_id=current_user.tenant_id)
    return await service.listar_modelos(expediente_id)


@router.post("/{expediente_id}/modelos", response_model=ModeloBIMOut)
async def subir_modelo_bim(
    expediente_id: UUID,
    file: UploadFile = File(...),
    nombre: str = Form(...),
    descripcion: Optional[str] = Form(None),
    tipos_elementos: Optional[str] = Form(None),  # coma-separado, ej "IfcWall,IfcSlab"
    extraer_malla: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Registra el modelo (sube el IFC a Supabase Storage de una vez) y
    encola la extracción de cantidades (Qto del IFC, con respaldo
    geométrico) y la malla para renderizar en el frontend.

    Devuelve con estado_procesamiento=EN_PROCESO; el frontend hace
    polling a GET /modelos/{id} hasta COMPLETADO o ERROR."""
    service = BIMService(db, tenant_id=current_user.tenant_id)
    contenido = await read_upload_with_limit(file, settings.IFC_MAX_FILE_SIZE_MB)

    modelo = await service.crear_modelo(
        expediente_id=expediente_id,
        nombre=nombre,
        descripcion=descripcion,
        file_content=contenido,
        filename=file.filename or "modelo.ifc",
        creado_por_id=current_user.id,
    )

    tipos = [t.strip() for t in tipos_elementos.split(",")] if tipos_elementos else None

    modelo.estado_procesamiento = EstadoProceso.EN_PROCESO.value
    await db.commit()
    await db.refresh(modelo)

    from app.workers.bim_tasks import procesar_ifc
    procesar_ifc.delay(
        modelo_id=str(modelo.id),
        expediente_id=str(expediente_id),
        tenant_id=str(current_user.tenant_id),
        tipos_elementos=tipos,
        extraer_malla=extraer_malla,
    )
    return modelo


@router.get("/{expediente_id}/modelos/{modelo_id}/descarga")
async def descargar_modelo_bim(
    expediente_id: UUID,
    modelo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """URL firmada temporal para descargar el IFC original desde
    Supabase Storage directamente (no pasa por el backend)."""
    service = BIMService(db, tenant_id=current_user.tenant_id)
    url = await service.url_descarga_modelo(modelo_id, expediente_id=expediente_id)
    return {"url": url, "expira_en_segundos": 3600}


@router.get("/{expediente_id}/modelos/{modelo_id}", response_model=ModeloBIMOut)
async def obtener_modelo_bim(
    expediente_id: UUID,
    modelo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    service = BIMService(db, tenant_id=current_user.tenant_id)
    modelo = await service._validar_modelo_en_expediente(modelo_id, expediente_id)
    return modelo


@router.get("/{expediente_id}/modelos/{modelo_id}/elementos", response_model=List[ElementoBIMOut])
async def listar_elementos_bim(
    expediente_id: UUID,
    modelo_id: UUID,
    tipo: Optional[str] = None,
    nivel: Optional[str] = None,
    incluir_malla: bool = False,
    limit: int = 200,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista elementos cuantificados. `incluir_malla=true` para pedir la
    geometría (más pesado) cuando el frontend va a renderizar en 3D.
    `nivel` filtra por piso/planta (ver ModeloBIM.niveles)."""
    service = BIMService(db, tenant_id=current_user.tenant_id)
    return await service.listar_elementos(
        modelo_id, expediente_id=expediente_id, tipo=tipo, nivel=nivel, incluir_malla=incluir_malla, limit=limit, offset=offset
    )


@router.post("/{expediente_id}/modelos/{modelo_id}/mapear-partidas")
async def mapear_elementos_a_partidas(
    expediente_id: UUID,
    modelo_id: UUID,
    mapeos: List[MapeoPartida],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = BIMService(db, tenant_id=current_user.tenant_id)
    count = await service.mapear_a_partidas(modelo_id, expediente_id=expediente_id, mapeos=[m.model_dump() for m in mapeos])
    return {"elementos_actualizados": count}


@router.post("/{expediente_id}/modelos/{modelo_id}/generar-presupuesto")
async def generar_presupuesto_desde_bim(
    expediente_id: UUID,
    modelo_id: UUID,
    data: GenerarPresupuestoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Crea un presupuesto (solo cantidades, sin precio unitario todavía)
    a partir de los elementos ya cuantificados de un modelo BIM."""
    from app.api.v1.presupuestos import PresupuestoOut

    service = BIMService(db, tenant_id=current_user.tenant_id)
    presupuesto = await service.crear_presupuesto_desde_bim(
        modelo_id=modelo_id,
        expediente_id=expediente_id,
        nombre=data.nombre,
        parametros_costeo=data.parametros_costeo.to_domain(),
        mapeo_catalogo=data.mapeo_catalogo,
    )
    return PresupuestoOut.model_validate(presupuesto)


@router.post("/{expediente_id}/modelos/{modelo_id}/zonas-4d")
async def asignar_zonas_4d(
    expediente_id: UUID,
    modelo_id: UUID,
    asignaciones: List[AsignarZona4D],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Asigna zona_4d a elementos en lote -- agrupación de trabajo
    editable para el cronograma 4D, independiente de `nivel` (ver
    ElementoBIM.zona_4d). Sin esto, generar-4d5d agrupa por `nivel`."""
    service = BIMService(db, tenant_id=current_user.tenant_id)
    count = await service.asignar_zonas_4d(
        modelo_id, expediente_id=expediente_id,
        asignaciones=[a.model_dump() for a in asignaciones],
    )
    return {"elementos_actualizados": count}


@router.post("/{expediente_id}/modelos/{modelo_id}/generar-4d5d", response_model=GeneracionBIM4D5DOut)
async def generar_4d5d(
    expediente_id: UUID,
    modelo_id: UUID,
    data: GenerarActividades4DRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Encola la generación de un ProgramaObra 4D desde el modelo BIM
    (una actividad por zona×tipo, sin predecesoras -- ver nota en
    BIMService.generar_actividades_4d). Devuelve de inmediato el
    registro de seguimiento; el frontend hace polling a
    GET .../generaciones-4d5d/{id} hasta COMPLETADO o ERROR."""
    service = BIMService(db, tenant_id=current_user.tenant_id)
    generacion = await service.crear_generacion_4d5d(
        modelo_id=modelo_id,
        expediente_id=expediente_id,
        dias_por_defecto=data.dias_por_defecto,
        creado_por_id=current_user.id,
    )

    from app.workers.bim_tasks import generar_4d5d_desde_bim
    generar_4d5d_desde_bim.delay(
        generacion_id=str(generacion.id),
        modelo_id=str(modelo_id),
        expediente_id=str(expediente_id),
        tenant_id=str(current_user.tenant_id),
        fecha_inicio_iso=data.fecha_inicio.isoformat(),
        dias_por_defecto=data.dias_por_defecto,
        creado_por_id=str(current_user.id),
    )
    return generacion


@router.get("/{expediente_id}/generaciones-4d5d/{generacion_id}", response_model=GeneracionBIM4D5DOut)
async def obtener_generacion_4d5d(
    expediente_id: UUID,
    generacion_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Poll de estado de una generación 4D en curso."""
    from app.models.bim import GeneracionBIM4D5D

    result = await db.execute(
        select(GeneracionBIM4D5D).where(
            GeneracionBIM4D5D.id == generacion_id,
            GeneracionBIM4D5D.expediente_id == expediente_id,
        )
    )
    generacion = result.scalar_one_or_none()
    if not generacion:
        raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Generación {generacion_id} no encontrada")
    return generacion


@router.post("/{expediente_id}/modelos/{modelo_id}/clash-detection", response_model=AnalisisClashOut)
async def ejecutar_clash_detection(
    expediente_id: UUID,
    modelo_id: UUID,
    data: EjecutarClashRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Registra el análisis (rápido, PENDIENTE) y encola el cómputo real
    (broad phase AABB + narrow phase Möller-Trumbore triángulo-triángulo)
    en un worker Celery -- ver ClashService/bim_tasks.analizar_clash sobre
    por qué esto ya no corre síncrono dentro del request. El frontend hace
    polling a GET /clash-detection/{analisis_id} hasta COMPLETADO/ERROR,
    igual que con la carga del modelo."""
    service = ClashService(db, current_user.tenant_id)
    analisis = await service.crear_analisis_pendiente(
        modelo_id=modelo_id,
        expediente_id=expediente_id,
        tolerancia_m=data.tolerancia_m,
        tipos_incluidos=data.tipos_incluidos,
        tipos_excluidos=data.tipos_excluidos,
        creado_por_id=current_user.id,
    )

    from app.workers.bim_tasks import analizar_clash
    analizar_clash.delay(analisis_id=str(analisis.id), tenant_id=str(current_user.tenant_id))

    return analisis


@router.get("/{expediente_id}/modelos/{modelo_id}/clash-detection/{analisis_id}", response_model=AnalisisClashOut)
async def obtener_analisis_clash(
    expediente_id: UUID,
    modelo_id: UUID,
    analisis_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    service = ClashService(db, current_user.tenant_id)
    return await service.obtener_analisis(analisis_id, modelo_id=modelo_id)


@router.get(
    "/{expediente_id}/modelos/{modelo_id}/clash-detection/{analisis_id}/resultados",
    response_model=List[ClashResultOut],
)
async def listar_resultados_clash(
    expediente_id: UUID,
    modelo_id: UUID,
    analisis_id: UUID,
    severidad: Optional[str] = None,
    estado: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """`severidad`: DURO | BLANDO. `estado`: NUEVO | REVISADO | RESUELTO
    | IGNORADO. Ordenado DURO primero, luego por fecha."""
    service = ClashService(db, current_user.tenant_id)
    return await service.listar_resultados(
        analisis_id, modelo_id=modelo_id, severidad=severidad, estado=estado, limit=limit, offset=offset
    )


@router.patch("/{expediente_id}/clash-resultados/{resultado_id}/estado", response_model=ClashResultOut)
async def actualizar_estado_clash(
    expediente_id: UUID,
    resultado_id: UUID,
    data: ActualizarEstadoClashRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Marca un clash como revisado/resuelto/ignorado -- seguimiento de
    equipo, no vuelve a correr el análisis geométrico."""
    service = ClashService(db, current_user.tenant_id)
    return await service.actualizar_estado_resultado(resultado_id, data.estado)
