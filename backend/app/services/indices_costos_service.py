"""Registro revisado y resolución de precios con versiones explícitas."""
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, MegalodonException
from app.engines.costos.indices import actualizar_precio, sellar_snapshot
from app.engines.costos.ingesta_inegi import revisar_archivo
from app.models.catalogo_conceptos import CatalogoFuente, InsumoCatalogo
from app.models.indices_costos import (
    ObservacionIndiceCosto,
    CargaIndiceCosto,
    RetiroIndiceCosto,
    SerieIndiceCosto,
    VinculoIndiceInsumo,
)
from app.models.user import User, UserRole
from app.schemas.indices_costos import (
    AcreditacionMonedaCreate,
    ActualizacionPrecioInput,
    ObservacionIndiceCreate,
    RetiroIndiceCreate,
    SerieIndiceCreate,
    CargaINEGIInput,
    ContratoINEGI,
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

    async def cargar_inegi(self, data: CargaINEGIInput, archivo: bytes, *, confirmar: bool):
        self._autorizar(global_=True)
        # All imports for the same immutable contract serialize in PostgreSQL.
        serie = await self.db.scalar(select(SerieIndiceCosto).where(
            SerieIndiceCosto.id == data.serie_id).with_for_update())
        if not serie:
            raise _error(ErrorCode.NOT_FOUND, 'Serie no encontrada')
        if not serie.contrato_inegi:
            raise _error(ErrorCode.BAD_REQUEST, 'La serie no tiene contrato de metadatos INEGI revisado')
        try:
            niveles = revisar_archivo(archivo, ContratoINEGI.model_validate(serie.contrato_inegi), data)
        except ValueError as exc:
            raise _error(ErrorCode.BAD_REQUEST, str(exc)) from exc
        anterior = await self.db.scalar(select(CargaIndiceCosto).where(
            CargaIndiceCosto.serie_id == serie.id, CargaIndiceCosto.documento_sha256 == data.evidencia.sha256))
        if anterior and (anterior.publicado_el != data.publicado_el or anterior.mes_inicio != data.mes_inicio
                         or anterior.mes_fin != data.mes_fin or anterior.ultima_actualizacion != data.ultima_actualizacion
                         or anterior.evidencia != data.evidencia.model_dump(mode='json')):
            raise _error(ErrorCode.CONFLICT, 'El mismo archivo ya tiene otra revisión; no cambiar sus fechas o intervalo')
        carga = anterior
        if confirmar and not anterior:
            carga = CargaIndiceCosto(serie_id=serie.id, documento_sha256=data.evidencia.sha256,
                publicado_el=data.publicado_el, mes_inicio=data.mes_inicio, mes_fin=data.mes_fin,
                ultima_actualizacion=data.ultima_actualizacion, evidencia=data.evidencia.model_dump(mode='json'),
                archivo=archivo, registrado_por=str(self.usuario.id))
            self.db.add(carga)
            try:
                await self.db.flush()
                self.db.add_all([ObservacionIndiceCosto(serie_id=serie.id, mes=n.mes, valor=n.valor,
                    publicado_el=n.publicado_el, documento_sha256=data.evidencia.sha256,
                    evidencia=n.evidencia.model_dump(mode='json'), carga_id=carga.id,
                    registrado_por=str(self.usuario.id)) for n in niveles])
                await self.db.commit()
            except IntegrityError as exc:
                await self.db.rollback()
                raise _error(ErrorCode.CONFLICT, 'Archivo o niveles ya registrados; la carga completa se revirtió') from exc
        retiradas = 0
        if carga:
            retiradas = len((await self.db.scalars(select(RetiroIndiceCosto.id).join(
                ObservacionIndiceCosto, RetiroIndiceCosto.observacion_id == ObservacionIndiceCosto.id
            ).where(ObservacionIndiceCosto.carga_id == carga.id))).all())
        return {'estado': ('REGISTRADO_CON_RETIROS' if retiradas else 'REGISTRADO') if confirmar else 'VALIDADO_SIN_REGISTRAR',
                'carga_id': str(carga.id) if carga else None,
                'repetida': anterior is not None, 'sha256': data.evidencia.sha256,
                'serie_id': str(serie.id), 'mes_inicio': data.mes_inicio.isoformat(),
                'mes_fin': data.mes_fin.isoformat(), 'observaciones': len(niveles),
                'observaciones_retiradas': retiradas,
                'niveles': [{'mes': n.mes.isoformat(), 'valor': str(n.valor)} for n in niveles]}

    async def archivo_carga(self, id: UUID):
        self._autorizar(global_=True)
        carga = await self.db.get(CargaIndiceCosto, id)
        if not carga:
            raise _error(ErrorCode.NOT_FOUND, 'Carga no encontrada')
        return carga.archivo

    async def crear_observacion(self, data: ObservacionIndiceCreate):
        self._autorizar(global_=True)
        await self._serie(data.serie_id)
        if data.sustituye_id:
            anterior = await self.db.scalar(select(ObservacionIndiceCosto).where(
                ObservacionIndiceCosto.id == data.sustituye_id).with_for_update())
            if not anterior:
                raise _error(ErrorCode.NOT_FOUND, 'Captura anterior no encontrada')
            retirado = await self.db.scalar(select(RetiroIndiceCosto.id).where(
                RetiroIndiceCosto.observacion_id == anterior.id))
            if not retirado or (anterior.serie_id, anterior.mes, anterior.documento_sha256,
                                anterior.revision_captura + 1) != (data.serie_id, data.mes,
                                data.evidencia.sha256, data.revision_captura):
                raise _error(ErrorCode.BAD_REQUEST,
                             'La corrección requiere retirar la captura anterior y conservar serie, mes y documento')
        return await self._guardar(ObservacionIndiceCosto(
            serie_id=data.serie_id, mes=data.mes, valor=data.valor, publicado_el=data.publicado_el,
            documento_sha256=data.evidencia.sha256, evidencia=data.evidencia.model_dump(mode='json'),
            revision_captura=data.revision_captura, sustituye_id=data.sustituye_id,
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
        if fuente.moneda != 'MXN':
            raise _error(ErrorCode.BAD_REQUEST, 'Moneda original desconocida o distinta de MXN; acreditar la fuente antes de indexar')
        if insumo.tipo != 'MATERIAL' or insumo.incluye_iva or data.region != serie.region:
            raise _error(ErrorCode.BAD_REQUEST,
                'Se requiere material sin IVA y revisión del ámbito de la serie; salarios/equipo necesitan su propio modelo')
        if not Decimal(insumo.precio_unitario).is_finite() or insumo.precio_unitario <= 0:
            raise _error(ErrorCode.BAD_REQUEST, 'Precio original inválido')
        original = serializar(insumo)
        original['fuente'] = serializar(fuente)
        original['moneda'] = fuente.moneda
        return await self._guardar(VinculoIndiceInsumo(
            tenant_id=self.usuario.tenant_id, insumo_id=insumo.id, serie_id=serie.id,
            mes_base=data.mes_base, precio_original=insumo.precio_unitario,
            insumo_original=original, fundamento=data.fundamento,
            evidencia=data.evidencia.model_dump(mode='json'), revisado_por=str(self.usuario.id),
        ))

    async def acreditar_moneda(self, data: AcreditacionMonedaCreate):
        from datetime import UTC, datetime
        self._autorizar(global_=True)
        fuente = await self.db.scalar(select(CatalogoFuente).where(
            CatalogoFuente.id == data.fuente_id).with_for_update())
        if not fuente:
            raise _error(ErrorCode.NOT_FOUND, 'Fuente de catálogo no encontrada')
        if fuente.moneda is not None:
            raise _error(ErrorCode.CONFLICT, 'La fuente ya tiene moneda; una corrección requiere revisar y retirar sus correspondencias')
        fuente.moneda = data.moneda
        fuente.moneda_evidencia = {**data.evidencia.model_dump(mode='json'),
                                  'revisado_por': str(self.usuario.id),
                                  'registrado_el': datetime.now(UTC).isoformat()}
        fuente.actualizado_por_id = self.usuario.id
        return await self._guardar(fuente)

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
