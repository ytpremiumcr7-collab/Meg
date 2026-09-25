# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas de licitaciones con máquina de estados legal.
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.licitacion import TipoProcedimiento, EstadoLicitacion, TipoEvaluacion, ResultadoEvaluacion


# ─── Junta de Aclaraciones ─────────────────────────────────────────────

class JuntaAclaracionCreate(BaseModel):
    fecha: str
    acta: Optional[str] = None
    preguntas_respuestas: Optional[dict] = None
    cambios_bases: Optional[str] = None
    numero_junta: int = 1
    fecha_limite_solicitudes: Optional[str] = None


class JuntaAclaracionOut(BaseModel):
    id: str
    licitacion_id: str
    fecha: str
    acta: Optional[str]
    preguntas_respuestas: Optional[dict]
    cambios_bases: Optional[str]
    numero_junta: int
    fecha_limite_solicitudes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Proposición ───────────────────────────────────────────────────────

class ProposicionCreate(BaseModel):
    proveedor_id: str
    monto: float = Field(..., ge=0)
    plazo_dias: int = Field(..., gt=0)
    sobres_digitales: Optional[dict] = None


class ProposicionOut(BaseModel):
    id: str
    licitacion_id: str
    proveedor_id: str
    monto: float
    plazo_dias: int
    estado: str
    firma_valida: Optional[bool]
    integridad_valida: Optional[bool]
    cumplimiento_documental: Optional[bool]
    motivo_desecho: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Evaluación ────────────────────────────────────────────────────────

class EvaluacionCreate(BaseModel):
    proposicion_id: str
    tipo: TipoEvaluacion
    resultado: ResultadoEvaluacion
    puntaje: Optional[float] = Field(None, ge=0, le=100)
    dictamen: Optional[str] = None
    criterios: Optional[dict] = None


class EvaluacionAutomaticaCreate(BaseModel):
    """Evaluación calculada por MotorEvaluacion en vez de traer ya
    resultado/puntaje decididos por un humano fuera del sistema (eso es
    lo que hace EvaluacionCreate arriba). `datos` trae los valores crudos
    por criterio -- para LEGAL, booleanos por cada CriterioLegal
    (ver app/engines/juridico/motor_evaluacion.py); para TECNICA/ECONOMICA,
    puntajes 0-100 por cada CriterioTecnico/CriterioEconomico."""
    proposicion_id: str
    tipo: TipoEvaluacion
    datos: dict
    puntaje_minimo_tecnico: Optional[float] = None
    precio_referencia: Optional[float] = None


class EvaluacionOut(BaseModel):
    id: str
    licitacion_id: str
    proposicion_id: str
    tipo: str
    resultado: str
    puntaje: Optional[float]
    dictamen: Optional[str]
    criterios: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Licitación ────────────────────────────────────────────────────────

class LicitacionCreate(BaseModel):
    expediente_id: str
    folio: str = Field(..., max_length=100)
    tipo_procedimiento: TipoProcedimiento
    objeto: str
    monto_estimado: Optional[float] = None
    plazo_dias: Optional[int] = None
    fecha_convocatoria: Optional[str] = None
    reglas_participacion: Optional[dict] = None
    bases: Optional[str] = None
    matriz_evaluacion: Optional[dict] = None
    presupuesto_dependencia_miles: Optional[float] = None


class LicitacionUpdate(BaseModel):
    estado: Optional[EstadoLicitacion] = None
    jurisdiction_code: str = Field(..., min_length=1, max_length=120)
    monto_estimado: Optional[float] = None
    plazo_dias: Optional[int] = None
    fecha_convocatoria: Optional[str] = None
    fecha_junta_aclaraciones: Optional[str] = None
    fecha_apertura: Optional[str] = None
    fecha_fallo: Optional[str] = None
    fecha_adjudicacion: Optional[str] = None
    matriz_evaluacion: Optional[dict] = None
    dictamen: Optional[str] = None
    bases: Optional[str] = None
    bases_congeladas: Optional[bool] = None
    justificacion_procedimiento: Optional[str] = None
    investigacion_mercado: Optional[dict] = None


class LicitacionOut(BaseModel):
    id: str
    expediente_id: str
    jurisdiction_code: Optional[str]
    folio: str
    tipo_procedimiento: str
    estado: str
    objeto: str
    monto_estimado: Optional[float]
    plazo_dias: Optional[int]
    fecha_convocatoria: Optional[str]
    fecha_junta_aclaraciones: Optional[str]
    fecha_apertura: Optional[str]
    fecha_fallo: Optional[str]
    fecha_adjudicacion: Optional[str]
    bases_version: int
    bases_congeladas: bool
    justificacion_procedimiento: Optional[str]
    presupuesto_dependencia_miles: Optional[float]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LicitacionList(BaseModel):
    total: int
    items: List[LicitacionOut]


class LicitacionDetalleOut(LicitacionOut):
    juntas_aclaraciones: List[JuntaAclaracionOut] = []
    proposiciones: List[ProposicionOut] = []
    evaluaciones: List[EvaluacionOut] = []

    class Config:
        from_attributes = True


# ─── Transiciones de estado ────────────────────────────────────────────

class TransicionEstadoCreate(BaseModel):
    nuevo_estado: EstadoLicitacion
    justificacion: Optional[str] = None
    datos_adicionales: Optional[dict] = None


class InvestigacionMercadoCreate(BaseModel):
    cotizaciones: List[dict]
    proveedores_contactados: List[str]
    precios_referencia: List[dict]
    oferta_nacional: bool
    dispersion_precios: Optional[float] = None
    conclusion: str


class SelectorProcedimientoOut(BaseModel):
    procedimiento_recomendado: TipoProcedimiento
    justificacion: str
    umbrales_aplicables: dict
    datos_verificados: bool
    es_candidato: bool
    fuente_umbral: Optional[str]
    ejercicio_fiscal: int
