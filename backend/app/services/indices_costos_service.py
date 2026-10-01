"""Registro revisado y resolución de precios con versiones explícitas."""
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, MegalodonException
from app.engines.costos.indices import actualizar_precio, sellar_snapshot
from app.models.catalogo_conceptos import CatalogoFuente, InsumoCatalogo
from app.models.indices_costos import (
    ObservacionIndiceCosto,
    RetiroIndiceCosto,
    SerieIndiceCosto,
    VinculoIndiceInsumo,
)
from app.models.user import User, UserRole
from app.schemas.indices_costos import (
    ActualizacionPrecioInput,
    ObservacionIndiceCreate,
    RetiroIndiceCreate,
    SerieIndiceCreate,
    VinculoIndiceCreate,
)


def serializar(row) -> dict:
    from datetime import date, datetime
    return {column.name: str(value) if isinstance(value, (UUID, Decimal)) else
            value.isoformat() if isinstance(value, (date, datetime)) else value
            for column in row.__table__.columns
            for value in [getattr(row, column.name)]}


def _error(code: ErrorCode, message: str) -> MegalodonException:
    status = {ErrorCode.NOT_FOUND: 404, ErrorCode.CONFLICT: 409,
              ErrorCode.PERMISO_DENEGADO: 403}.get(code, 400)
    return MegalodonException(code, message, status_code=status)


class IndicesCostosService:
    def __init__(self, db: AsyncSession, usuario: User):
        self.db, self.usuario = db, usuario

    def _autorizar(self, global_: bool = False):
        roles = {UserRole.SUPERADMIN.value} if global_ else {UserRole.ADMIN.value, UserRole.SUPERADMIN.value}
        if self.usuario.role not in roles:
            raise _error(ErrorCode.PERMISO_DENEGADO, 'Sin permiso para registrar esta evidencia')

    async def _guardar(self, row):
        self.db.add(row)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise _error(ErrorCode.CONFLICT, 'La versión o retiro ya existe, o su referencia no es válida') from exc
        await self.db.refresh(row)
        return serializar(row)

    async def _serie(self, id: UUID):
        row = await self.db.get(SerieIndiceCosto, id)
        if row is None:
            raise _error(ErrorCode.NOT_FOUND, 'Serie no encontrada')
        return row

    async def crear_serie(self, data: SerieIndiceCreate):
        self._autorizar(global_=True)
        values = data.model_dump(mode='json', exclude={'alcance', 'moneda', 'incluye_iva'})
        return await self._guardar(SerieIndiceCosto(**values, registrado_por=str(self.usuario.id)))

    async def crear_observacion(self, data: ObservacionIndiceCreate):
        self._autorizar(global_=True)
        await self._serie(data.serie_id)
        return await self._guardar(ObservacionIndiceCosto(
            serie_id=data.serie_id, mes=data.mes, valor=data.valor, publicado_el=data.publicado_el,
            documento_sha256=data.evidencia.sha256, evidencia=data.evidencia.model_dump(mode='json'),
            registrado_por=str(self.usuario.id),
        ))

    async def crear_vinculo(self, data: VinculoIndiceCreate):
        self._autorizar()
        serie = await self._serie(data.serie_id)
        insumo = await self.db.get(InsumoCatalogo, data.insumo_id)
        if insumo is None or not insumo.activo:
            raise _error(ErrorCode.NOT_FOUND, 'Insumo activo no encontrado')
        fuente = await self.db.get(CatalogoFuente, insumo.fuente_id)
        if not fuente or not fuente.activo:
            raise _error(ErrorCode.BAD_REQUEST, 'Fuente de catálogo inactiva')
        if insumo.tipo != 'MATERIAL' or insumo.incluye_iva or data.region != serie.region:
            raise _error(ErrorCode.BAD_REQUEST,
                'Se requiere material sin IVA y revisión del ámbito de la serie; salarios/equipo necesitan su propio modelo')
        if not Decimal(insumo.precio_unitario).is_finite() or insumo.precio_unitario <= 0:
            raise _error(ErrorCode.BAD_REQUEST, 'Precio original inválido')
        original = serializar(insumo)
        original['fuente'] = serializar(fuente)
        original['moneda'] = 'MXN'
        return await self._guardar(VinculoIndiceInsumo(
            tenant_id=self.usuario.tenant_id, insumo_id=insumo.id, serie_id=serie.id,
            mes_base=data.mes_base, precio_original=insumo.precio_unitario,
            insumo_original=original, fundamento=data.fundamento,
            evidencia=data.evidencia.model_dump(mode='json'), revisado_por=str(self.usuario.id),
        ))

    async def listar_series(self, skip: int, limit: int):
        rows = await self.db.scalars(select(SerieIndiceCosto).order_by(SerieIndiceCosto.codigo, SerieIndiceCosto.id).offset(skip).limit(limit))
        return [serializar(row) for row in rows]

    async def listar_observaciones(self, serie_id: UUID, skip: int, limit: int):
        await self._serie(serie_id)
        retired = select(RetiroIndiceCosto.observacion_id).where(RetiroIndiceCosto.observacion_id.is_not(None))
        rows = await self.db.scalars(select(ObservacionIndiceCosto).where(
            ObservacionIndiceCosto.serie_id == serie_id, ObservacionIndiceCosto.id.not_in(retired)
        ).order_by(ObservacionIndiceCosto.mes, ObservacionIndiceCosto.publicado_el, ObservacionIndiceCosto.id).offset(skip).limit(limit))
        return [serializar(row) for row in rows]

    async def listar_vinculos(self, skip: int, limit: int):
        retired = select(RetiroIndiceCosto.vinculo_id).where(RetiroIndiceCosto.vinculo_id.is_not(None))
        rows = await self.db.scalars(select(VinculoIndiceInsumo).where(
            VinculoIndiceInsumo.tenant_id == self.usuario.tenant_id, VinculoIndiceInsumo.id.not_in(retired)
        ).order_by(VinculoIndiceInsumo.created_at, VinculoIndiceInsumo.id).offset(skip).limit(limit))
        return [serializar(row) for row in rows]

    async def _vinculo(self, id: UUID, *, exclusivo=False):
        row = await self.db.scalar(select(VinculoIndiceInsumo).where(
            VinculoIndiceInsumo.id == id, VinculoIndiceInsumo.tenant_id == self.usuario.tenant_id,
        ).with_for_update(read=not exclusivo))
        if row is None:
            raise _error(ErrorCode.NOT_FOUND, 'Correspondencia no encontrada')
        return row

    async def retirar(self, data: RetiroIndiceCreate):
        self._autorizar(global_=data.observacion_id is not None)
        if data.vinculo_id:
            await self._vinculo(data.vinculo_id, exclusivo=True)
        else:
            row = await self.db.scalar(select(ObservacionIndiceCosto).where(
                ObservacionIndiceCosto.id == data.observacion_id).with_for_update())
            if row is None:
                raise _error(ErrorCode.NOT_FOUND, 'Observación no encontrada')
        return await self._guardar(RetiroIndiceCosto(**data.model_dump(), registrado_por=str(self.usuario.id)))

    async def resolver(self, data: ActualizacionPrecioInput) -> dict:
        vinculo = await self._vinculo(data.vinculo_id)
        ids = {data.observacion_base_id, data.observacion_destino_id}
        rows = await self.db.scalars(select(ObservacionIndiceCosto).where(
            ObservacionIndiceCosto.id.in_(ids)).order_by(ObservacionIndiceCosto.id).with_for_update(read=True))
        niveles = {row.id: row for row in rows}
        if set(niveles) != ids:
            raise _error(ErrorCode.NOT_FOUND, 'Falta un nivel publicado; no se sustituye por inflación global')
        base, destino = niveles[data.observacion_base_id], niveles[data.observacion_destino_id]
        retiro = await self.db.scalar(select(RetiroIndiceCosto.id).where(or_(
            RetiroIndiceCosto.observacion_id.in_(ids), RetiroIndiceCosto.vinculo_id == vinculo.id)))
        if retiro:
            raise _error(ErrorCode.CONFLICT, 'La correspondencia o una observación fue retirada')
        if base.serie_id != vinculo.serie_id or destino.serie_id != vinculo.serie_id or base.mes != vinculo.mes_base or destino.mes < base.mes:
            raise _error(ErrorCode.BAD_REQUEST, 'Serie, mes base o mes destino incompatibles')
        serie = await self._serie(vinculo.serie_id)
        try:
            precio = actualizar_precio(Decimal(vinculo.precio_original), Decimal(base.valor), Decimal(destino.valor))
        except ValueError as exc:
            raise _error(ErrorCode.BAD_REQUEST, str(exc)) from exc
        return sellar_snapshot({
            'version': 1, 'metodo': 'COCIENTE_NIVELES', 'redondeo': 'DECIMAL_50_HALF_UP_0.01',
            'tipo': 'ESTIMACION_OBSERVADA', 'moneda': 'MXN', 'incluye_iva': False,
            'precio_original': str(vinculo.precio_original), 'precio_actualizado': str(precio),
            'serie': serializar(serie), 'vinculo': serializar(vinculo),
            'base': serializar(base), 'destino': serializar(destino),
        })
