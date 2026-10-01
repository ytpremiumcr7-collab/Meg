from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

Mes = Annotated[date, Field(description='Primer día del mes observado')]


def validar_mes(value: date) -> date:
    if value.day != 1:
        raise ValueError('El mes se representa con el primer día')
    if value >= datetime.now(UTC).date().replace(day=1):
        raise ValueError('Se requiere un mes observado y cerrado')
    return value


class Estricto(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class EvidenciaIndice(Estricto):
    url: HttpUrl
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    localizador: str = Field(min_length=3, max_length=1000)

    @field_validator('url')
    @classmethod
    def sin_credenciales(cls, value):
        if value.username or value.password or value.query or value.fragment:
            raise ValueError('URL de evidencia sin credenciales, parámetros ni fragmentos')
        return value


class SerieIndiceCreate(Estricto):
    codigo: str = Field(min_length=1, max_length=120)
    version_metodologia: str = Field(min_length=1, max_length=120)
    nombre: str = Field(min_length=1, max_length=300)
    alcance: Literal['MATERIAL']
    region: str = Field(min_length=1, max_length=120)
    moneda: Literal['MXN']
    incluye_iva: Literal[False]
    condiciones_precio: str = Field(min_length=10, max_length=5000)
    periodo_referencia: str = Field(min_length=3, max_length=100)
    evidencia: EvidenciaIndice


class ObservacionIndiceCreate(Estricto):
    serie_id: UUID
    medida: Literal['NIVEL']
    mes: Mes
    valor: Decimal = Field(gt=0, max_digits=18, decimal_places=8, allow_inf_nan=False)
    publicado_el: date
    evidencia: EvidenciaIndice
    revision_captura: int = Field(1, ge=1)
    sustituye_id: UUID | None = None
    _mes = field_validator('mes')(validar_mes)

    @model_validator(mode='after')
    def publicacion_observada(self):
        if (self.revision_captura == 1) != (self.sustituye_id is None):
            raise ValueError('Una corrección requiere revisión de captura y observación sustituida')
        if self.publicado_el <= self.mes or self.publicado_el > datetime.now(UTC).date():
            raise ValueError('Fecha de publicación incompatible o futura')
        next_month = self.mes.replace(year=self.mes.year + (self.mes.month == 12), month=self.mes.month % 12 + 1)
        if self.publicado_el < next_month:
            raise ValueError('La publicación debe corresponder a un mes cerrado')
        return self


class VinculoIndiceCreate(Estricto):
    insumo_id: UUID
    serie_id: UUID
    mes_base: Mes
    region: str = Field(min_length=1, max_length=120)
    fundamento: str = Field(min_length=20, max_length=5000)
    evidencia: EvidenciaIndice
    _mes = field_validator('mes_base')(validar_mes)


class AcreditacionMonedaCreate(Estricto):
    fuente_id: UUID
    moneda: str = Field(pattern=r'^[A-Z]{3}$')
    evidencia: EvidenciaIndice


class ActualizacionPrecioInput(Estricto):
    vinculo_id: UUID
    observacion_base_id: UUID
    observacion_destino_id: UUID


class RetiroIndiceCreate(Estricto):
    observacion_id: UUID | None = None
    vinculo_id: UUID | None = None
    motivo: str = Field(min_length=20, max_length=5000)

    @model_validator(mode='after')
    def un_recurso(self):
        if (self.observacion_id is None) == (self.vinculo_id is None):
            raise ValueError('Indicar una observación o una correspondencia')
        return self
