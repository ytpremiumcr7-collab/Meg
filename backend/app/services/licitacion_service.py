# Copyright © 2026 Cristian Rodriguez
"""Servicio de licitaciones — Máquina de estados legal completa."""
from __future__ import annotations

from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.core.errors import MegalodonException, ErrorCode
from app.models.expediente import ExpedienteObra
from app.models.proveedor import Proveedor
from app.models.licitacion import (
    Licitacion,
    EstadoLicitacion,
    TipoProcedimiento,
    JuntaAclaracion,
    Proposicion,
    EvaluacionLicitacion,
)
from app.models.user import User
from app.schemas.licitacion import (
    LicitacionCreate, LicitacionUpdate, JuntaAclaracionCreate,
    ProposicionCreate, EvaluacionCreate, EvaluacionAutomaticaCreate, TransicionEstadoCreate,
)
from app.engines.juridico.motor_evaluacion import MotorEvaluacion


class LicitacionService:
    TRANSICIONES = {
        EstadoLicitacion.PLANEACION: [EstadoLicitacion.INVESTIGACION_MERCADO, EstadoLicitacion.SELECCION_PROCEDIMIENTO, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.INVESTIGACION_MERCADO: [EstadoLicitacion.SELECCION_PROCEDIMIENTO, EstadoLicitacion.CONVOCATORIA, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.SELECCION_PROCEDIMIENTO: [EstadoLicitacion.CONVOCATORIA, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.CONVOCATORIA: [EstadoLicitacion.JUNTA_ACLARACIONES, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.JUNTA_ACLARACIONES: [EstadoLicitacion.RECEPCION_PROPUESTAS, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.RECEPCION_PROPUESTAS: [EstadoLicitacion.APERTURA, EstadoLicitacion.DESIERTA, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.APERTURA: [EstadoLicitacion.EVALUACION, EstadoLicitacion.DESIERTA, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.EVALUACION: [EstadoLicitacion.FALLO, EstadoLicitacion.DESIERTA, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.FALLO: [EstadoLicitacion.ADJUDICACION, EstadoLicitacion.DESIERTA],
        EstadoLicitacion.ADJUDICACION: [EstadoLicitacion.CONTRATO],
        EstadoLicitacion.CONTRATO: [EstadoLicitacion.CERRADA],
        EstadoLicitacion.DESIERTA: [],
        EstadoLicitacion.CANCELADA: [],
        EstadoLicitacion.CERRADA: [],
    }

    async def _obtener_licitacion(self, db: AsyncSession, licitacion_id: UUID, current_user: User) -> Licitacion:
        result = await db.execute(
            select(Licitacion)
            .join(ExpedienteObra, Licitacion.expediente_id == ExpedienteObra.id)
            .where(Licitacion.id == licitacion_id)
            .where(ExpedienteObra.tenant_id == current_user.tenant_id)
        )
        lic = result.scalar_one_or_none()
        if not lic:
            raise MegalodonException(ErrorCode.NOT_FOUND, f"Licitación '{licitacion_id}' no encontrada.")
        return lic

    async def _obtener_proposicion_en_licitacion(self, db: AsyncSession, proposicion_id: UUID, licitacion_id: UUID, current_user: User) -> Proposicion:
        result = await db.execute(
            select(Proposicion)
            .join(Licitacion, Proposicion.licitacion_id == Licitacion.id)
            .join(ExpedienteObra, Licitacion.expediente_id == ExpedienteObra.id)
            .where(Proposicion.id == proposicion_id)
            .where(Proposicion.licitacion_id == licitacion_id)
            .where(ExpedienteObra.tenant_id == current_user.tenant_id)
        )
        proposicion = result.scalar_one_or_none()
        if not proposicion:
            raise MegalodonException(ErrorCode.NOT_FOUND, "Proposición no encontrada")
        return proposicion

    async def crear(self, db: AsyncSession, data: LicitacionCreate, current_user: User) -> Licitacion:
        expediente = await db.execute(
            select(ExpedienteObra)
            .where(ExpedienteObra.id == data.expediente_id)
            .where(ExpedienteObra.tenant_id == current_user.tenant_id)
        )
        if expediente.scalar_one_or_none() is None:
            raise MegalodonException(ErrorCode.NOT_FOUND, f"Expediente '{data.expediente_id}' no encontrado")

        jurisdiction_code = data.jurisdiction_code.strip().upper()
        if not jurisdiction_code:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "Debe seleccionar la dependencia convocante.", 422)
        lic = Licitacion(
            expediente_id=data.expediente_id,
            folio=data.folio,
            jurisdiction_code=jurisdiction_code,
            tipo_procedimiento=data.tipo_procedimiento,
            estado=EstadoLicitacion.PLANEACION,
            objeto=data.objeto,
            monto_estimado=data.monto_estimado,
            plazo_dias=data.plazo_dias,
            fecha_convocatoria=data.fecha_convocatoria,
            reglas_participacion=data.reglas_participacion,
            bases=data.bases,
            matriz_evaluacion=data.matriz_evaluacion,
            presupuesto_dependencia_miles=data.presupuesto_dependencia_miles,
            tenant_id=current_user.tenant_id,
            creado_por_id=current_user.id,
            actualizado_por_id=current_user.id,
        )
        db.add(lic)
        await db.commit()
        await db.refresh(lic)
        return lic

    async def listar(
        self,
        db: AsyncSession,
        current_user: User,
        estado=None,
        tipo_procedimiento=None,
        expediente_id=None,
        skip: int = 0,
        limit: int = 50,
    ) -> dict:
        query = select(Licitacion).where(Licitacion.tenant_id == current_user.tenant_id)
        if estado is not None:
            query = query.where(Licitacion.estado == estado)
        if tipo_procedimiento is not None:
            query = query.where(Licitacion.tipo_procedimiento == tipo_procedimiento)
        if expediente_id is not None:
            query = query.where(Licitacion.expediente_id == expediente_id)
        total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = (await db.execute(query.order_by(Licitacion.created_at.desc()).offset(skip).limit(limit))).scalars().all()
        return {"total": total, "items": items}

    async def obtener(self, db: AsyncSession, licitacion_id: UUID, current_user: User) -> Licitacion:
        return await self._obtener_licitacion(db, licitacion_id, current_user)

    async def actualizar(self, db: AsyncSession, licitacion_id: UUID, data: LicitacionUpdate, current_user: User) -> Licitacion:
        lic = await self._obtener_licitacion(db, licitacion_id, current_user)
        if lic.estado not in [EstadoLicitacion.PLANEACION, EstadoLicitacion.INVESTIGACION_MERCADO, EstadoLicitacion.SELECCION_PROCEDIMIENTO, EstadoLicitacion.CONVOCATORIA]:
            raise MegalodonException(ErrorCode.BAD_REQUEST, f"No se puede editar licitación en estado '{lic.estado.value}'.")
        for field in [
            'estado', 'jurisdiction_code', 'monto_estimado', 'plazo_dias', 'fecha_convocatoria', 'fecha_junta_aclaraciones',
            'fecha_apertura', 'fecha_fallo', 'fecha_adjudicacion', 'matriz_evaluacion', 'dictamen',
            'bases', 'bases_congeladas', 'justificacion_procedimiento', 'investigacion_mercado',
        ]:
            val = getattr(data, field, None)
            if val is not None:
                setattr(lic, field, val)
        lic.actualizado_por_id = current_user.id
        await db.commit()
        await db.refresh(lic)
        return lic

    async def transicionar_estado(self, db: AsyncSession, licitacion_id: UUID, data: TransicionEstadoCreate, current_user: User) -> Licitacion:
        lic = await self._obtener_licitacion(db, licitacion_id, current_user)
        nuevo = data.nuevo_estado
        permitidos = self.TRANSICIONES.get(lic.estado, [])
        if nuevo not in permitidos:
            raise MegalodonException(ErrorCode.BAD_REQUEST, f"Transición de '{lic.estado.value}' a '{nuevo.value}' no permitida.")
        if nuevo == EstadoLicitacion.CONVOCATORIA and (not lic.folio or not lic.bases):
            raise MegalodonException(ErrorCode.BAD_REQUEST, "Requiere folio y bases para convocatoria.")
        # La junta de aclaraciones ocurre fuera de Megalodon.
        # El usuario incorpora sus actas/modificaciones como documentación oficial
        # del expediente; Megalodon no exige ni crea una junta para avanzar.
        if nuevo == EstadoLicitacion.APERTURA:
            count = await db.scalar(select(func.count()).where(Proposicion.licitacion_id == licitacion_id)) or 0
            if count == 0:
                raise MegalodonException(ErrorCode.BAD_REQUEST, "No hay proposiciones registradas.")
        if nuevo == EstadoLicitacion.EVALUACION:
            count = await db.scalar(select(func.count()).where(EvaluacionLicitacion.licitacion_id == licitacion_id)) or 0
            if count == 0:
                raise MegalodonException(ErrorCode.BAD_REQUEST, "No hay evaluaciones registradas.")
        if nuevo == EstadoLicitacion.FALLO:
            count = await db.scalar(select(func.count()).where(EvaluacionLicitacion.licitacion_id == licitacion_id).where(EvaluacionLicitacion.resultado.isnot(None))) or 0
            if count == 0:
                raise MegalodonException(ErrorCode.BAD_REQUEST, "No hay evaluaciones completadas.")
        lic.estado = nuevo
        if data.justificacion:
            lic.justificacion_procedimiento = data.justificacion
        lic.actualizado_por_id = current_user.id
        await db.commit()
        await db.refresh(lic)
        return lic

    async def listar_juntas(self, db: AsyncSession, licitacion_id: UUID, current_user: User) -> List[JuntaAclaracion]:
        await self._obtener_licitacion(db, licitacion_id, current_user)
        result = await db.execute(
            select(JuntaAclaracion)
            .join(Licitacion, JuntaAclaracion.licitacion_id == Licitacion.id)
            .where(JuntaAclaracion.licitacion_id == licitacion_id)
            .where(Licitacion.tenant_id == current_user.tenant_id)
            .order_by(JuntaAclaracion.created_at.desc())
        )
        return result.scalars().all()

    async def registrar_proposicion(self, db: AsyncSession, licitacion_id: UUID, data: ProposicionCreate, current_user: User) -> Proposicion:
        lic = await self._obtener_licitacion(db, licitacion_id, current_user)
        if lic.estado not in [EstadoLicitacion.JUNTA_ACLARACIONES, EstadoLicitacion.RECEPCION_PROPUESTAS]:
            raise MegalodonException(ErrorCode.BAD_REQUEST, f"No se puede registrar proposición en estado '{lic.estado.value}'.")
        proveedor = await db.execute(
            select(Proveedor)
            .where(Proveedor.id == data.proveedor_id)
            .where(Proveedor.tenant_id == current_user.tenant_id)
        )
        if proveedor.scalar_one_or_none() is None:
            raise MegalodonException(ErrorCode.NOT_FOUND, f"Proveedor '{data.proveedor_id}' no encontrado")
        dup = await db.execute(
            select(Proposicion)
            .where(Proposicion.licitacion_id == licitacion_id)
            .where(Proposicion.proveedor_id == data.proveedor_id)
        )
        if dup.scalar_one_or_none() is not None:
            raise MegalodonException(ErrorCode.CONFLICT, "El proveedor ya presentó una proposición en esta licitación.")
        proposicion = Proposicion(
            licitacion_id=licitacion_id,
            proveedor_id=data.proveedor_id,
            monto=data.monto,
            plazo_dias=data.plazo_dias,
            sobres_digitales=data.sobres_digitales,
            tenant_id=current_user.tenant_id,
            creado_por_id=current_user.id,
            actualizado_por_id=current_user.id,
        )
        db.add(proposicion)
        if lic.estado == EstadoLicitacion.JUNTA_ACLARACIONES:
            lic.estado = EstadoLicitacion.RECEPCION_PROPUESTAS
            lic.actualizado_por_id = current_user.id
        await db.commit()
        await db.refresh(proposicion)
        return proposicion

    async def listar_proposiciones(self, db: AsyncSession, licitacion_id: UUID, current_user: User) -> List[Proposicion]:
        await self._obtener_licitacion(db, licitacion_id, current_user)
        result = await db.execute(
            select(Proposicion)
            .join(Licitacion, Proposicion.licitacion_id == Licitacion.id)
            .where(Proposicion.licitacion_id == licitacion_id)
            .where(Licitacion.tenant_id == current_user.tenant_id)
            .order_by(Proposicion.created_at.desc())
        )
        return result.scalars().all()

    async def crear_evaluacion(self, db: AsyncSession, licitacion_id: UUID, data: EvaluacionCreate, current_user: User) -> EvaluacionLicitacion:
        lic = await self._obtener_licitacion(db, licitacion_id, current_user)
        if lic.estado != EstadoLicitacion.APERTURA:
            raise MegalodonException(ErrorCode.BAD_REQUEST, f"Evaluación solo permitida en estado '{EstadoLicitacion.APERTURA.value}'.")
        await self._obtener_proposicion_en_licitacion(db, UUID(str(data.proposicion_id)), licitacion_id, current_user)
        evaluacion = EvaluacionLicitacion(
            licitacion_id=licitacion_id,
            proposicion_id=data.proposicion_id,
            tipo=data.tipo,
            resultado=data.resultado,
            puntaje=data.puntaje,
            dictamen=data.dictamen,
            criterios={**(data.criterios or {}), "jurisdiction_code": lic.jurisdiction_code, "evaluation_matrix": lic.matriz_evaluacion or {}},
            evaluador_id=current_user.id,
            tenant_id=current_user.tenant_id,
            creado_por_id=current_user.id,
            actualizado_por_id=current_user.id,
        )
        db.add(evaluacion)
        await db.commit()
        await db.refresh(evaluacion)
        return evaluacion

    async def evaluar_proposicion_automatica(
        self, db: AsyncSession, licitacion_id: UUID, data: EvaluacionAutomaticaCreate, current_user: User,
    ) -> EvaluacionLicitacion:
        """Evalúa una proposición con MotorEvaluacion en vez de recibir el
        veredicto ya decidido por un humano fuera del sistema.

        CONECTADO (pedido explícito 2026-09-07): MotorEvaluacion ya
        implementaba la evaluación por capas Legal/Técnica/Económica
        (legal como veto, técnica y económica ponderadas por criterio con
        pesos reales, validación de consistencia contra precio de
        mercado) desde antes de esta sesión, pero ningún servicio lo
        llamaba -- crear_evaluacion() de arriba exige que el CLIENTE ya
        traiga resultado/puntaje calculados, es decir, hasta ahora la
        evaluación real la hacía un humano por fuera y solo se registraba
        el veredicto. Esto automatiza el cálculo con el motor real, para
        el propósito declarado del sistema (automatizar la elaboración de
        licitaciones). crear_evaluacion() sigue existiendo para registrar
        un veredicto manual cuando haga falta (p. ej. un ajuste editorial
        sobre el dictamen); esto no lo reemplaza, lo complementa.
        """
        lic = await self._obtener_licitacion(db, licitacion_id, current_user)
        if lic.estado != EstadoLicitacion.APERTURA:
            raise MegalodonException(ErrorCode.BAD_REQUEST, f"Evaluación solo permitida en estado '{EstadoLicitacion.APERTURA.value}'.")
        await self._obtener_proposicion_en_licitacion(db, UUID(str(data.proposicion_id)), licitacion_id, current_user)

        matriz = lic.matriz_evaluacion or {}
        if not isinstance(matriz, dict) or not matriz:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "No existe una matriz de evaluación versionada en el expediente.", 409)
        if not lic.bases_congeladas:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "La evaluación requiere las bases/matriz congeladas.", 409)
        motor = MotorEvaluacion(matriz)
        if data.tipo == TipoEvaluacion.LEGAL:
            capa = motor.evaluar_legal(str(data.proposicion_id), data.datos)
        elif data.tipo == TipoEvaluacion.TECNICA:
            capa = motor.evaluar_tecnica(str(data.proposicion_id), data.datos)
        elif data.tipo == TipoEvaluacion.ECONOMICA:
            capa = motor.evaluar_economica(str(data.proposicion_id), data.datos, precio_referencia=data.precio_referencia)
        else:
            raise MegalodonException(ErrorCode.BAD_REQUEST, f"Tipo de evaluación no soportado: {data.tipo}")

        criterios_snapshot = {"detalle": [
            {"criterio": c.criterio, "cumple": c.cumple, "observacion": c.observacion, "puntaje": c.puntaje}
            for c in capa.criterios
        ], "jurisdiction_code": lic.jurisdiction_code, "evaluation_matrix": matriz}
        evaluacion = EvaluacionLicitacion(
            licitacion_id=licitacion_id,
            proposicion_id=data.proposicion_id,
            tipo=capa.tipo,
            resultado=capa.resultado,
            puntaje=capa.puntaje_total,
            dictamen=capa.dictamen,
            criterios=criterios_snapshot,
            evaluador_id=current_user.id,
            tenant_id=current_user.tenant_id,
            creado_por_id=current_user.id,
            actualizado_por_id=current_user.id,
        )
        db.add(evaluacion)
        await db.commit()
        await db.refresh(evaluacion)
        return evaluacion

    async def emitir_fallo(self, db: AsyncSession, licitacion_id: UUID, proposicion_ganadora_id: UUID, current_user: User) -> Licitacion:
        lic = await self._obtener_licitacion(db, licitacion_id, current_user)
        await self._obtener_proposicion_en_licitacion(db, proposicion_ganadora_id, licitacion_id, current_user)
        if not lic.jurisdiction_code:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "El expediente no tiene dependencia convocante fijada.", 409)
        evals = (await db.execute(select(EvaluacionLicitacion).where(
            EvaluacionLicitacion.licitacion_id == licitacion_id,
            EvaluacionLicitacion.proposicion_id == proposicion_ganadora_id,
            EvaluacionLicitacion.tenant_id == current_user.tenant_id,
        ))).scalars().all()
        if not evals:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "No existe evaluación trazable para la proposición seleccionada.", 409)
        for evaluation in evals:
            snapshot = evaluation.criterios or {}
            if snapshot.get("jurisdiction_code") != lic.jurisdiction_code:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "La evaluación pertenece a otra dependencia o carece de contexto de dependencia.", 409)
        if lic.estado not in [EstadoLicitacion.APERTURA, EstadoLicitacion.EVALUACION, EstadoLicitacion.FALLO]:
            raise MegalodonException(ErrorCode.BAD_REQUEST, f"No se puede emitir fallo en estado '{lic.estado.value}'.")
        lic.estado = EstadoLicitacion.FALLO
        lic.dictamen = f"Proposición ganadora: {proposicion_ganadora_id}"
        lic.fecha_fallo = lic.fecha_fallo or datetime.utcnow().date().isoformat()
        lic.actualizado_por_id = current_user.id
        await db.commit()
        await db.refresh(lic)
        return lic

    async def resumen_licitacion(self, db: AsyncSession, licitacion_id: UUID, current_user: User) -> Dict[str, Any]:
        lic = await self._obtener_licitacion(db, licitacion_id, current_user)
        juntas = await db.scalar(select(func.count()).where(JuntaAclaracion.licitacion_id == licitacion_id)) or 0
        proposiciones = await db.scalar(select(func.count()).where(Proposicion.licitacion_id == licitacion_id)) or 0
        evaluaciones = await db.scalar(select(func.count()).where(EvaluacionLicitacion.licitacion_id == licitacion_id)) or 0
        return {
            "licitacion_id": str(lic.id),
            "folio": lic.folio,
            "estado": lic.estado.value if hasattr(lic.estado, 'value') else str(lic.estado),
            "tipo_procedimiento": lic.tipo_procedimiento.value if hasattr(lic.tipo_procedimiento, 'value') else str(lic.tipo_procedimiento),
            "objeto": lic.objeto,
            "monto_estimado": float(lic.monto_estimado or 0),
            "plazo_dias": lic.plazo_dias,
            "juntas_aclaraciones": int(juntas),
            "proposiciones": int(proposiciones),
            "evaluaciones": int(evaluaciones),
            "bases_congeladas": bool(lic.bases_congeladas),
        }
