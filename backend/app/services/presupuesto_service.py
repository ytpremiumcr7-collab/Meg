# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
PresupuestoService - Gestión de presupuestos programables con costeo.
"""
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.presupuesto import Presupuesto, Partida, Concepto, Insumo, ZonaEconomica, EstadoPresupuesto
from app.models.expediente import ExpedienteObra
from app.models.catalogo_apu import CatalogoAPU
from app.services.base import BaseService
from app.engines.costos.motor_costeo import MotorCosteo, PresupuestoCosteo, PartidaCosteo, ConceptoCosteo, InsumoCosteo
from app.engines.costos.parametros import ParametrosCosteoSnapshot, verificar_snapshot_almacenado
from app.core.errors import MegalodonException, ErrorCode


class PresupuestoService(BaseService[Presupuesto]):
    """Servicio de presupuestos con motor de costeo integrado."""

    def __init__(self, db: AsyncSession, tenant_id: UUID | None = None):
        super().__init__(Presupuesto, db, tenant_id=tenant_id, tenant_required=True)
        self.motor_costeo = MotorCosteo()

    async def listar_por_expediente(
        self, expediente_id: UUID, skip: int = 0, limit: int = 20,
    ) -> List[Presupuesto]:
        """Lista presupuestos de un expediente con partidas/conceptos/
        insumos precargados (BaseService.get_multi() no lo hace, y
        PresupuestoOut ahora expone `partidas`)."""
        from sqlalchemy.orm import selectinload

        result = await self.db.execute(
            select(Presupuesto)
            .join(ExpedienteObra, ExpedienteObra.id == Presupuesto.expediente_id)
            .where(Presupuesto.expediente_id == expediente_id, ExpedienteObra.tenant_id == self.tenant_id)
            .options(
                selectinload(Presupuesto.partidas)
                .selectinload(Partida.conceptos)
                .selectinload(Concepto.insumos)
            )
            .order_by(Presupuesto.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def crear_desde_costeo(
        self,
        *,
        expediente_id: UUID,
        nombre: str,
        descripcion: Optional[str] = None,
        partidas_data: List[Dict[str, Any]],
        parametros_costeo: ParametrosCosteoSnapshot,
        zona_economica: str = "CENTRO",
        creado_por_id: Optional[UUID] = None,
    ) -> Presupuesto:
        """Crea presupuesto desde datos de costeo con cálculo completo.

        Dos formas válidas de mandar una partida en `partidas_data`:

        1) Tabulador / precio ya conocido (ej. tabulador CDMX importado):
           solo manda `precio_unitario` y NO manda `conceptos`. Ese precio
           se respeta tal cual, sin recalcular desde insumos.

        2) APU real (uno o más conceptos): manda `conceptos`, y cada
           concepto trae SUS PROPIOS `insumos` anidados (no se comparten
           entre conceptos). El precio_unitario de la partida se calcula
           sumando el costo de todos los conceptos.
        """

        # Validar expediente existe
        result = await self.db.execute(
            select(ExpedienteObra).where(ExpedienteObra.id == expediente_id, ExpedienteObra.tenant_id == self.tenant_id)
        )
        expediente = result.scalar_one_or_none()
        if not expediente:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Expediente {expediente_id} no encontrado",
            )

        # Generar identificador
        from datetime import datetime
        count_result = await self.db.execute(
            select(Presupuesto).join(ExpedienteObra, ExpedienteObra.id == Presupuesto.expediente_id).where(Presupuesto.expediente_id == expediente_id, ExpedienteObra.tenant_id == self.tenant_id)
        )
        count = len(count_result.scalars().all()) + 1
        identificador = f"PRE-{expediente.identificador}-{count:03d}"

        # Construir modelo de costeo
        partidas_costeo = []
        for i, p_data in enumerate(partidas_data, 1):
            conceptos_data = p_data.get("conceptos") or []
            conceptos: List[ConceptoCosteo] = []

            if conceptos_data:
                # Caso APU: cada concepto trae SUS PROPIOS insumos.
                # BUG ORIGINAL: todos los conceptos de la partida compartían
                # la misma lista de insumos del nivel partida, y encima
                # solo el primer concepto se quedaba con ellos (los demás
                # recibían insumos=[] y quedaban en costo cero).
                for c_data in conceptos_data:
                    insumos_concepto = [
                        InsumoCosteo(
                            clave=ins_data.get("clave", ""),
                            descripcion=ins_data.get("descripcion", ""),
                            tipo=ins_data.get("tipo", "MATERIAL"),
                            unidad=ins_data.get("unidad", ""),
                            cantidad=Decimal(str(ins_data.get("cantidad", 0))),
                            precio_unitario=Decimal(str(ins_data.get("precio_unitario", 0))),
                            rendimiento=Decimal(str(ins_data.get("rendimiento", 1.0))),
                        )
                        for ins_data in c_data.get("insumos", [])
                    ]
                    conceptos.append(ConceptoCosteo(
                        clave=c_data.get("clave", ""),
                        descripcion=c_data.get("descripcion", ""),
                        unidad=c_data.get("unidad", ""),
                        cantidad=Decimal(str(c_data.get("cantidad", 1.0))),
                        insumos=insumos_concepto,
                    ))
            else:
                # Sin conceptos explícitos: si vienen insumos sueltos a
                # nivel partida, se agrupan en un concepto implícito.
                insumos_partida = [
                    InsumoCosteo(
                        clave=ins_data.get("clave", ""),
                        descripcion=ins_data.get("descripcion", ""),
                        tipo=ins_data.get("tipo", "MATERIAL"),
                        unidad=ins_data.get("unidad", ""),
                        cantidad=Decimal(str(ins_data.get("cantidad", 0))),
                        precio_unitario=Decimal(str(ins_data.get("precio_unitario", 0))),
                        rendimiento=Decimal(str(ins_data.get("rendimiento", 1.0))),
                    )
                    for ins_data in p_data.get("insumos", [])
                ]
                if insumos_partida:
                    conceptos.append(ConceptoCosteo(
                        clave=f"CON-{i:03d}",
                        descripcion=p_data.get("descripcion", ""),
                        unidad=p_data.get("unidad", ""),
                        insumos=insumos_partida,
                    ))

            # Precio manual (tabulador): solo aplica si NO hay conceptos,
            # es decir, el precio ya viene resuelto de un catálogo oficial
            # y no debe recalcularse desde una APU que no existe.
            precio_manual = None
            if not conceptos and p_data.get("precio_unitario") is not None:
                precio_manual = Decimal(str(p_data["precio_unitario"]))

            partidas_costeo.append(PartidaCosteo(
                numero=i,
                descripcion=p_data.get("descripcion", ""),
                unidad=p_data.get("unidad", ""),
                cantidad=Decimal(str(p_data.get("cantidad", 0))),
                conceptos=conceptos,
                precio_unitario_manual=precio_manual,
            ))

        presupuesto_costeo = PresupuestoCosteo(
            identificador=identificador,
            nombre=nombre,
            partidas=partidas_costeo,
            parametros=parametros_costeo,
        )

        # Calcular
        presupuesto_costeo = self.motor_costeo.calcular_presupuesto(presupuesto_costeo)

        # Crear en DB
        presupuesto = await self.create({
            "id": uuid4(),
            "identificador": identificador,
            "nombre": nombre,
            "descripcion": descripcion,
            "expediente_id": expediente_id,
            "monto_directo": float(presupuesto_costeo.monto_directo),
            "monto_indirecto": float(presupuesto_costeo.monto_indirecto),
            "monto_utilidad": float(presupuesto_costeo.monto_utilidad),
            "monto_riesgo": float(presupuesto_costeo.monto_riesgo),
            "monto_impuesto": float(presupuesto_costeo.monto_impuesto),
            "monto_total": float(presupuesto_costeo.monto_total),
            "factor_indirecto": float(parametros_costeo.factor_indirecto),
            "factor_utilidad": float(parametros_costeo.factor_utilidad),
            "factor_impuesto": float(parametros_costeo.factor_impuesto),
            "factor_riesgo": float(parametros_costeo.factor_riesgo),
            "zona_economica": zona_economica,
            "metadatos": {"parametros_costeo": parametros_costeo.to_dict()},
            "estado": EstadoPresupuesto.CALCULADO.value,
        }, creado_por_id=creado_por_id)

        # Crear partidas, conceptos e insumos
        for p_costeo in presupuesto_costeo.partidas:
            partida = Partida(
                id=uuid4(),
                tenant_id=presupuesto.tenant_id,
                presupuesto_id=presupuesto.id,
                numero=p_costeo.numero,
                descripcion=p_costeo.descripcion,
                unidad=p_costeo.unidad,
                cantidad=float(p_costeo.cantidad),
                precio_unitario=float(p_costeo.precio_unitario),
                importe=float(p_costeo.importe),
            )
            self.db.add(partida)

            for c_costeo in p_costeo.conceptos:
                concepto = Concepto(
                    id=uuid4(),
                    tenant_id=presupuesto.tenant_id,
                    partida_id=partida.id,
                    clave=c_costeo.clave,
                    descripcion=c_costeo.descripcion,
                    unidad=c_costeo.unidad,
                    cantidad=float(c_costeo.cantidad),
                    costo_directo_unitario=float(c_costeo.costo_directo_unitario),
                )
                self.db.add(concepto)

                for i_costeo in c_costeo.insumos:
                    insumo = Insumo(
                        id=uuid4(),
                        tenant_id=presupuesto.tenant_id,
                        concepto_id=concepto.id,
                        clave=i_costeo.clave,
                        descripcion=i_costeo.descripcion,
                        tipo=i_costeo.tipo,
                        unidad=i_costeo.unidad,
                        cantidad=float(i_costeo.cantidad),
                        precio_unitario=float(i_costeo.precio_unitario),
                        importe=float(i_costeo.importe),
                        rendimiento=float(i_costeo.rendimiento),
                    )
                    self.db.add(insumo)

        await self.db.commit()

        # BUG EVITADO: db.refresh(presupuesto) solo recarga columnas
        # escalares, no relaciones -- si el caller (o el response_model)
        # intentara leer presupuesto.partidas después de esto, sería un
        # lazy-load implícito que en AsyncSession truena con
        # MissingGreenlet. Se re-consulta ya con todo precargado.
        return await self._reconstruir_partidas_desde_db(presupuesto.id, expediente_id)

    async def _reconstruir_partidas_desde_db(self, presupuesto_id: UUID, expediente_id: UUID) -> "Presupuesto":
        """Recarga un presupuesto con partidas → conceptos → insumos completos.
        Valida que el presupuesto pertenezca al expediente de la ruta.

        BUG ORIGINAL: recalcular() y generar_excel() reconstruían las
        partidas con conceptos=[] (sin recargar nada de la BD). Como
        PartidaCosteo.precio_unitario ahora depende de sus conceptos, eso
        significaba que CADA recálculo o exportación a Excel ponía el
        presupuesto entero en $0.00, pisando los montos reales guardados.
        """
        from sqlalchemy.orm import selectinload

        result = await self.db.execute(
            select(Presupuesto)
            .where(Presupuesto.id == presupuesto_id)
            .where(Presupuesto.expediente_id == expediente_id)
            .where(Presupuesto.tenant_id == self.tenant_id)
            .options(
                selectinload(Presupuesto.partidas)
                .selectinload(Partida.conceptos)
                .selectinload(Concepto.insumos)
            )
        )
        presupuesto = result.scalar_one_or_none()
        if not presupuesto:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Presupuesto {presupuesto_id} no encontrado en el expediente {expediente_id}",
            )
        return presupuesto

    def _partidas_costeo_desde_orm(self, presupuesto: "Presupuesto") -> List[PartidaCosteo]:
        """Convierte las partidas ORM (con conceptos e insumos ya cargados)
        a PartidaCosteo, preservando el precio manual de partidas tipo
        tabulador (las que no tienen conceptos)."""
        partidas_costeo = []
        for p in presupuesto.partidas:
            conceptos = [
                ConceptoCosteo(
                    clave=c.clave,
                    descripcion=c.descripcion,
                    unidad=c.unidad,
                    cantidad=Decimal(str(c.cantidad)),
                    insumos=[
                        InsumoCosteo(
                            clave=ins.clave,
                            descripcion=ins.descripcion,
                            tipo=ins.tipo,
                            unidad=ins.unidad,
                            cantidad=Decimal(str(ins.cantidad)),
                            precio_unitario=Decimal(str(ins.precio_unitario)),
                            rendimiento=Decimal(str(ins.rendimiento)),
                        )
                        for ins in c.insumos
                    ],
                )
                for c in p.conceptos
            ]
            # Partida tipo tabulador (sin conceptos): preserva el precio
            # unitario ya guardado en vez de recalcularlo desde cero.
            precio_manual = Decimal(str(p.precio_unitario)) if not conceptos else None
            partidas_costeo.append(PartidaCosteo(
                numero=p.numero,
                descripcion=p.descripcion,
                unidad=p.unidad,
                cantidad=Decimal(str(p.cantidad)),
                conceptos=conceptos,
                precio_unitario_manual=precio_manual,
            ))
        return partidas_costeo

    @staticmethod
    def _parametros_desde_orm(presupuesto: "Presupuesto") -> ParametrosCosteoSnapshot:
        snapshot = (presupuesto.metadatos or {}).get("parametros_costeo")
        try:
            return verificar_snapshot_almacenado(
                snapshot,
                (
                    presupuesto.factor_indirecto,
                    presupuesto.factor_utilidad,
                    presupuesto.factor_impuesto,
                    presupuesto.factor_riesgo,
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MegalodonException(
                ErrorCode.PRESUPUESTO_ERROR,
                f"Snapshot de parámetros de costeo inválido: {exc}",
                details={"presupuesto_id": str(presupuesto.id)},
            ) from exc

    async def actualizar_parametros_costeo(
        self,
        presupuesto_id: UUID,
        expediente_id: UUID,
        parametros: ParametrosCosteoSnapshot,
        actualizado_por_id: Optional[UUID] = None,
    ) -> Presupuesto:
        presupuesto = await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id)
        if presupuesto.estado in (EstadoPresupuesto.VALIDADO.value, EstadoPresupuesto.APROBADO.value):
            raise MegalodonException(
                ErrorCode.PRESUPUESTO_ERROR,
                "No se pueden sustituir parámetros de un presupuesto validado o aprobado; cree una revisión",
                details={"estado": presupuesto.estado},
            )
        metadatos = dict(presupuesto.metadatos or {})
        metadatos["parametros_costeo"] = parametros.to_dict()
        presupuesto_costeo = PresupuestoCosteo(
            identificador=presupuesto.identificador,
            nombre=presupuesto.nombre,
            partidas=self._partidas_costeo_desde_orm(presupuesto),
            parametros=parametros,
        )
        self.motor_costeo.calcular_presupuesto(presupuesto_costeo)

        for p_orm, p_costeo in zip(presupuesto.partidas, presupuesto_costeo.partidas):
            p_orm.precio_unitario = float(p_costeo.precio_unitario)
            p_orm.importe = float(p_costeo.importe)
        presupuesto.factor_indirecto = float(parametros.factor_indirecto)
        presupuesto.factor_utilidad = float(parametros.factor_utilidad)
        presupuesto.factor_impuesto = float(parametros.factor_impuesto)
        presupuesto.factor_riesgo = float(parametros.factor_riesgo)
        presupuesto.monto_directo = float(presupuesto_costeo.monto_directo)
        presupuesto.monto_indirecto = float(presupuesto_costeo.monto_indirecto)
        presupuesto.monto_utilidad = float(presupuesto_costeo.monto_utilidad)
        presupuesto.monto_riesgo = float(presupuesto_costeo.monto_riesgo)
        presupuesto.monto_impuesto = float(presupuesto_costeo.monto_impuesto)
        presupuesto.monto_total = float(presupuesto_costeo.monto_total)
        presupuesto.metadatos = metadatos
        if actualizado_por_id is not None:
            presupuesto.actualizado_por_id = actualizado_por_id
        await self.db.commit()
        return await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id)

    async def recalcular(
        self, presupuesto_id: UUID, expediente_id: UUID, actualizado_por_id: Optional[UUID] = None,
    ) -> Presupuesto:
        """Recalcula un presupuesto existente a partir de sus partidas,
        conceptos e insumos reales guardados en BD."""
        presupuesto = await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id)
        partidas_costeo = self._partidas_costeo_desde_orm(presupuesto)

        presupuesto_costeo = PresupuestoCosteo(
            identificador=presupuesto.identificador,
            nombre=presupuesto.nombre,
            partidas=partidas_costeo,
            parametros=self._parametros_desde_orm(presupuesto),
        )

        presupuesto_costeo = self.motor_costeo.calcular_presupuesto(presupuesto_costeo)

        # Actualizar también el importe/precio_unitario de cada partida,
        # por si cambiaron insumos desde la última vez.
        for p_orm, p_costeo in zip(presupuesto.partidas, presupuesto_costeo.partidas):
            p_orm.precio_unitario = float(p_costeo.precio_unitario)
            p_orm.importe = float(p_costeo.importe)

        # Si el presupuesto ya estaba VALIDADO/APROBADO, un recálculo
        # cambia los montos sobre los que se dio esa validación/
        # aprobación -- se regresa a CALCULADO para forzar que alguien
        # vuelva a validar/aprobar contra los números nuevos, en vez de
        # dejar una aprobación "vieja" apuntando a montos que ya no son
        # los que están en pantalla.
        nuevo_estado = presupuesto.estado
        if presupuesto.estado in (EstadoPresupuesto.VALIDADO.value, EstadoPresupuesto.APROBADO.value):
            nuevo_estado = EstadoPresupuesto.CALCULADO.value

        await self.update(
            presupuesto_id,
            {
                "monto_directo": float(presupuesto_costeo.monto_directo),
                "monto_indirecto": float(presupuesto_costeo.monto_indirecto),
                "monto_utilidad": float(presupuesto_costeo.monto_utilidad),
                "monto_riesgo": float(presupuesto_costeo.monto_riesgo),
                "monto_impuesto": float(presupuesto_costeo.monto_impuesto),
                "monto_total": float(presupuesto_costeo.monto_total),
                "estado": nuevo_estado,
            },
            actualizado_por_id=actualizado_por_id,
        )

        # self.update() termina en un get() plano (sin selectinload); se
        # re-consulta con las relaciones precargadas por la misma razón
        # que en crear_desde_costeo (evitar un lazy-load async al serializar).
        return await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id)

    async def generar_excel(self, presupuesto_id: UUID, expediente_id: UUID) -> bytes:
        """Genera Excel del presupuesto a partir de los datos reales en BD."""
        presupuesto = await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id)
        partidas_costeo = self._partidas_costeo_desde_orm(presupuesto)

        presupuesto_costeo = PresupuestoCosteo(
            identificador=presupuesto.identificador,
            nombre=presupuesto.nombre,
            partidas=partidas_costeo,
            parametros=self._parametros_desde_orm(presupuesto),
        )
        presupuesto_costeo = self.motor_costeo.calcular_presupuesto(presupuesto_costeo)

        return self.motor_costeo.generar_excel(presupuesto_costeo)

    _TRANSICIONES_ESTADO = {
        EstadoPresupuesto.BORRADOR.value: {EstadoPresupuesto.CALCULADO.value},
        EstadoPresupuesto.CALCULADO.value: {EstadoPresupuesto.VALIDADO.value, EstadoPresupuesto.RECHAZADO.value},
        EstadoPresupuesto.VALIDADO.value: {EstadoPresupuesto.APROBADO.value, EstadoPresupuesto.RECHAZADO.value},
        EstadoPresupuesto.RECHAZADO.value: {EstadoPresupuesto.CALCULADO.value},
        EstadoPresupuesto.APROBADO.value: set(),  # terminal -- solo un recalcular() lo regresa a CALCULADO
    }

    async def cambiar_estado(
        self, presupuesto_id: UUID, expediente_id: UUID, nuevo_estado: str,
        actualizado_por_id: Optional[UUID] = None,
    ) -> Presupuesto:
        """Transiciona el estado del presupuesto (VALIDADO/APROBADO/
        RECHAZADO) validando que la transición sea válida -- no existía
        ningún mecanismo para esto porque el campo `estado` tampoco
        existía antes de esta ronda de unificación."""
        presupuesto = await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id)
        if nuevo_estado not in {e.value for e in EstadoPresupuesto}:
            raise MegalodonException(
                ErrorCode.PRESUPUESTO_ERROR,
                f"Estado inválido: {nuevo_estado}. Válidos: {[e.value for e in EstadoPresupuesto]}",
            )
        permitidas = self._TRANSICIONES_ESTADO.get(presupuesto.estado, set())
        if nuevo_estado not in permitidas:
            raise MegalodonException(
                ErrorCode.PRESUPUESTO_ERROR,
                f"Transición de estado inválida: {presupuesto.estado} -> {nuevo_estado}",
                details={"transiciones_permitidas": sorted(permitidas)},
            )
        await self.update(
            presupuesto_id, {"estado": nuevo_estado}, actualizado_por_id=actualizado_por_id,
        )
        return await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id)

    async def generar_pdf(self, presupuesto_id: UUID, expediente_id: UUID) -> bytes:
        """Genera PDF del presupuesto a partir de los datos reales en BD.
        Mismo patrón que generar_excel()."""
        presupuesto = await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id)
        partidas_costeo = self._partidas_costeo_desde_orm(presupuesto)

        presupuesto_costeo = PresupuestoCosteo(
            identificador=presupuesto.identificador,
            nombre=presupuesto.nombre,
            partidas=partidas_costeo,
            parametros=self._parametros_desde_orm(presupuesto),
        )
        presupuesto_costeo = self.motor_costeo.calcular_presupuesto(presupuesto_costeo)

        return self.motor_costeo.generar_pdf(presupuesto_costeo)

    async def validar_sobrecostos(
        self,
        presupuesto_id: UUID,
        expediente_id: UUID,
        presupuesto_base_id: UUID,
    ) -> Dict[str, Any]:
        """Valida sobrecostos vs presupuesto base.

        BUG ORIGINAL: reconstruía ambos presupuestos con partidas=[], así
        que monto_total siempre daba $0 para los dos lados y la validación
        reportaba "dentro de tolerancia" sin importar los datos reales.
        Ahora se usan directamente los montos ya calculados y guardados
        en BD (que ya reflejan sus partidas reales).
        """
        expediente = await self.db.execute(
            select(ExpedienteObra).where(ExpedienteObra.id == expediente_id, ExpedienteObra.tenant_id == self.tenant_id)
        )
        expediente_obj = expediente.scalar_one_or_none()
        if not expediente_obj:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Expediente {expediente_id} no encontrado",
            )

        result_actual = await self.db.execute(
            select(Presupuesto)
            .join(ExpedienteObra, Presupuesto.expediente_id == ExpedienteObra.id)
            .where(Presupuesto.id == presupuesto_id)
            .where(ExpedienteObra.tenant_id == expediente_obj.tenant_id)
        )
        actual = result_actual.scalar_one_or_none()

        result_base = await self.db.execute(
            select(Presupuesto)
            .join(ExpedienteObra, Presupuesto.expediente_id == ExpedienteObra.id)
            .where(Presupuesto.id == presupuesto_base_id)
            .where(ExpedienteObra.tenant_id == expediente_obj.tenant_id)
        )
        base = result_base.scalar_one_or_none()

        if not actual or not base:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                "Presupuesto no encontrado",
            )

        monto_actual = Decimal(str(actual.monto_total))
        monto_base = Decimal(str(base.monto_total))
        sobrecosto = monto_actual - monto_base
        factor = (sobrecosto / monto_base) if monto_base else Decimal("0")
        tolerancia = Decimal(str(self.motor_costeo.constantes.TOLERANCIA_FACTOR_SOBRECOSTO))

        return {
            "presupuesto_base": float(monto_base),
            "presupuesto_actual": float(monto_actual),
            "sobrecosto": float(sobrecosto),
            "factor_sobrecosto": float(factor),
            "dentro_tolerancia": factor <= tolerancia,
            "tolerancia_permitida": self.motor_costeo.constantes.TOLERANCIA_FACTOR_SOBRECOSTO,
        }

    # ─── Gestión incremental de partidas (desde catálogo real) ─────────
    #
    # ANTES: la única forma de meter partidas era crear_desde_costeo(),
    # todas de golpe al crear el presupuesto. No había manera de ir
    # agregando/editando/quitando una partida a la vez sobre un
    # presupuesto ya existente -- justo lo que hace falta para una UI de
    # costeo real donde el usuario busca un concepto en el catálogo
    # (CatalogoAPU: CMIC, CFE, Pemex, investigación de mercado, etc.),
    # decide una cantidad, y lo agrega.

    async def agregar_partida_desde_catalogo(
        self,
        presupuesto_id: UUID,
        expediente_id: UUID,
        catalogo_apu_id: UUID,
        cantidad: float,
        actualizado_por_id: Optional[UUID] = None,
    ) -> Presupuesto:
        """Agrega una partida al presupuesto tomando su precio (y
        desglose de insumos si el concepto lo trae) del catálogo maestro
        CatalogoAPU. Si el concepto no tiene `desglose.insumos` (p. ej.
        viene de un catálogo de investigación de mercado con solo un
        precio de referencia), la partida se guarda como tipo tabulador
        con ese precio unitario tal cual, sin inventar un desglose."""
        presupuesto = await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id)

        # BUG: self.db.get(CatalogoAPU, catalogo_apu_id) no validaba tenant
        # -- cualquier usuario autenticado que supiera o adivinara un
        # catalogo_apu_id de OTRO tenant se traía su descripción, precio
        # unitario y desglose completo de insumos hacia su propio
        # presupuesto. Mismo tipo de fuga que ya se cerró en otros ~10
        # routers esta sesión; CatalogoAPUService.obtener() ya lo hacía
        # bien (filtra por tenant_id), este método no.
        expediente = await self.db.scalar(select(ExpedienteObra).where(ExpedienteObra.id == expediente_id, ExpedienteObra.tenant_id == self.tenant_id))
        if not expediente:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Expediente {expediente_id} no encontrado",
            )
        result_apu = await self.db.execute(
            select(CatalogoAPU).where(
                CatalogoAPU.id == catalogo_apu_id,
                CatalogoAPU.tenant_id == self.tenant_id,
            )
        )
        concepto_apu = result_apu.scalar_one_or_none()
        if not concepto_apu:
            # Mismo 404 exista o no exista el id, o exista bajo otro
            # tenant -- no revelar cuál de los tres casos es.
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Concepto de catálogo {catalogo_apu_id} no encontrado",
            )

        siguiente_numero = max((p.numero for p in presupuesto.partidas), default=0) + 1
        insumos_desglose = (concepto_apu.desglose or {}).get("insumos") or []

        if insumos_desglose:
            concepto_costeo = ConceptoCosteo(
                clave=concepto_apu.clave,
                descripcion=concepto_apu.descripcion,
                unidad=concepto_apu.unidad,
                cantidad=Decimal("1"),
                insumos=[
                    InsumoCosteo(
                        clave=ins.get("clave", ""),
                        descripcion=ins.get("descripcion", ""),
                        tipo=ins.get("tipo", "MATERIAL"),
                        unidad=ins.get("unidad", ""),
                        cantidad=Decimal(str(ins.get("cantidad", 0))),
                        precio_unitario=Decimal(str(ins.get("precio_unitario", 0))),
                        rendimiento=Decimal(str(ins.get("rendimiento", 1.0))),
                    )
                    for ins in insumos_desglose
                ],
            )
            partida_costeo = PartidaCosteo(
                numero=siguiente_numero, descripcion=concepto_apu.descripcion, unidad=concepto_apu.unidad,
                cantidad=Decimal(str(cantidad)), conceptos=[concepto_costeo],
            )
        else:
            concepto_costeo = None
            partida_costeo = PartidaCosteo(
                numero=siguiente_numero, descripcion=concepto_apu.descripcion, unidad=concepto_apu.unidad,
                cantidad=Decimal(str(cantidad)), conceptos=[],
                precio_unitario_manual=Decimal(str(concepto_apu.precio_unitario)),
            )

        partida = Partida(
            id=uuid4(),
            tenant_id=presupuesto.tenant_id,
            presupuesto_id=presupuesto.id,
            numero=siguiente_numero,
            descripcion=concepto_apu.descripcion,
            unidad=concepto_apu.unidad,
            cantidad=cantidad,
            precio_unitario=float(partida_costeo.precio_unitario),
            importe=float(partida_costeo.importe),
        )
        self.db.add(partida)
        await self.db.flush()  # necesitamos partida.id para los FK de concepto/insumo

        if concepto_costeo is not None:
            concepto = Concepto(
                id=uuid4(),
                tenant_id=presupuesto.tenant_id,
                partida_id=partida.id,
                clave=concepto_costeo.clave,
                descripcion=concepto_costeo.descripcion,
                unidad=concepto_costeo.unidad,
                cantidad=float(concepto_costeo.cantidad),
                costo_directo_unitario=float(concepto_costeo.costo_directo_unitario),
            )
            self.db.add(concepto)
            await self.db.flush()
            for ins_costeo in concepto_costeo.insumos:
                self.db.add(Insumo(
                    id=uuid4(),
                    tenant_id=presupuesto.tenant_id,
                    concepto_id=concepto.id,
                    clave=ins_costeo.clave,
                    descripcion=ins_costeo.descripcion,
                    tipo=ins_costeo.tipo,
                    unidad=ins_costeo.unidad,
                    cantidad=float(ins_costeo.cantidad),
                    precio_unitario=float(ins_costeo.precio_unitario),
                    importe=float(ins_costeo.importe),
                    rendimiento=float(ins_costeo.rendimiento),
                ))

        await self.db.commit()

        # Recalcula los montos agregados del presupuesto (indirectos,
        # utilidad, impuesto) sobre TODAS las partidas, incluida ésta.
        return await self.recalcular(presupuesto_id, expediente_id, actualizado_por_id)

    async def actualizar_cantidad_partida(
        self,
        presupuesto_id: UUID,
        expediente_id: UUID,
        partida_id: UUID,
        nueva_cantidad: float,
        actualizado_por_id: Optional[UUID] = None,
    ) -> Presupuesto:
        presupuesto = await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id)
        partida = next((p for p in presupuesto.partidas if str(p.id) == str(partida_id)), None)
        if not partida:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Partida {partida_id} no encontrada en el presupuesto {presupuesto_id}",
            )
        partida.cantidad = nueva_cantidad
        await self.db.commit()
        return await self.recalcular(presupuesto_id, expediente_id, actualizado_por_id)

    async def eliminar_partida(
        self,
        presupuesto_id: UUID,
        expediente_id: UUID,
        partida_id: UUID,
        actualizado_por_id: Optional[UUID] = None,
    ) -> Presupuesto:
        presupuesto = await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id)
        partida = next((p for p in presupuesto.partidas if str(p.id) == str(partida_id)), None)
        if not partida:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Partida {partida_id} no encontrada en el presupuesto {presupuesto_id}",
            )
        await self.db.delete(partida)
        await self.db.commit()
        return await self.recalcular(presupuesto_id, expediente_id, actualizado_por_id)
