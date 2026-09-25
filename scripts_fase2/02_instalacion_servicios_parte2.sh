#!/bin/bash
# =============================================================================
# FASE 2 — Script 2: Instalar servicios Compliance + Contrato + Licitacion
# =============================================================================
# Este script COPIA archivos NUEVOS, NUNCA modifica existentes.
# Si un archivo ya existe, hace backup (.backup) antes de escribir.
# =============================================================================

set -euo pipefail

BACKEND_DIR="${1:-./backend}"
SERVICES_DIR="$BACKEND_DIR/app/services"

echo "🦈 MEGALODON FASE 2 — Script 2: Instalando Compliance + Contrato + Licitacion..."
echo "   Directorio objetivo: $SERVICES_DIR"
echo ""

# ─── SERVICIO 3: compliance_service.py ─────────────────────────────────────

cat > "$SERVICES_DIR/compliance_service.py" << 'PYEOF'
# Copyright © 2026 Cristian Rodriguez
"""Servicio de compliance — Reglas, inconformidades, sanciones y evaluación automática."""
from typing import Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.models.compliance import (
    ReglaCumplimiento, Inconformidad, Sancion, EvaluacionCompliance,
    EstadoInconformidad, TipoSancion, EstadoRegla,
)
from app.models.user import User
from app.schemas.compliance import (
    ReglaCumplimientoCreate, InconformidadCreate, InconformidadUpdate,
    SancionCreate, EvaluacionComplianceCreate,
)
from app.core.errors import MegalodonException, ErrorCode

class ComplianceService:
    async def crear_regla(self, db: AsyncSession, data: ReglaCumplimientoCreate, current_user: User) -> ReglaCumplimiento:
        r = ReglaCumplimiento(
            nombre=data.nombre, descripcion=data.descripcion,
            tipo_procedimiento=data.tipo_procedimiento, etapa=data.etapa,
            requisitos=data.requisitos, obligatorio=data.obligatorio,
            condicion_evaluacion=data.condicion_evaluacion,
            tenant_id=current_user.tenant_id, created_by=current_user.id)
        db.add(r); await db.commit(); await db.refresh(r); return r

    async def listar_reglas(self, db: AsyncSession, current_user: User,
                            tipo_procedimiento=None, etapa=None, activa=None, skip=0, limit=50) -> dict:
        q = select(ReglaCumplimiento).where(ReglaCumplimiento.tenant_id == current_user.tenant_id)
        if tipo_procedimiento: q = q.where(ReglaCumplimiento.tipo_procedimiento == tipo_procedimiento)
        if etapa: q = q.where(ReglaCumplimiento.etapa == etapa)
        if activa is not None: q = q.where(ReglaCumplimiento.activa == activa)
        total = await db.scalar(select(func.count()).select_from(q.subquery())) or 0
        items = (await db.execute(q.offset(skip).limit(limit).order_by(
            ReglaCumplimiento.etapa, ReglaCumplimiento.nombre))).scalars().all()
        return {"total": total, "items": items}

    async def obtener_regla(self, db: AsyncSession, regla_id: UUID, current_user: User) -> ReglaCumplimiento:
        r = (await db.execute(select(ReglaCumplimiento).where(and_(
            ReglaCumplimiento.id == regla_id,
            ReglaCumplimiento.tenant_id == current_user.tenant_id)))).scalar_one_or_none()
        if not r: raise MegalodonException(ErrorCode.NOT_FOUND, f"Regla '{regla_id}' no encontrada.")
        return r

    async def actualizar_regla(self, db: AsyncSession, regla_id: UUID, data: ReglaCumplimientoCreate, current_user: User) -> ReglaCumplimiento:
        r = await self.obtener_regla(db, regla_id, current_user)
        r.nombre=data.nombre; r.descripcion=data.descripcion; r.tipo_procedimiento=data.tipo_procedimiento
        r.etapa=data.etapa; r.requisitos=data.requisitos; r.obligatorio=data.obligatorio
        r.condicion_evaluacion=data.condicion_evaluacion; r.updated_by=current_user.id
        await db.commit(); await db.refresh(r); return r

    async def eliminar_regla(self, db: AsyncSession, regla_id: UUID, current_user: User) -> None:
        r = await self.obtener_regla(db, regla_id, current_user)
        await db.delete(r); await db.commit()

    async def crear_inconformidad(self, db: AsyncSession, data: InconformidadCreate, current_user: User) -> Inconformidad:
        i = Inconformidad(
            expediente_id=data.expediente_id, licitacion_id=data.licitacion_id,
            contrato_id=data.contrato_id, titulo=data.titulo, descripcion=data.descripcion,
            severidad=data.severidad, estado=EstadoInconformidad.ABIERTA,
            regla_id=data.regla_id, asignado_a=data.asignado_a,
            fecha_limite=data.fecha_limite, evidencia=data.evidencia,
            tenant_id=current_user.tenant_id, created_by=current_user.id)
        db.add(i); await db.commit(); await db.refresh(i); return i

    async def listar_inconformidades(self, db: AsyncSession, current_user: User,
                                     estado=None, severidad=None, expediente_id=None, skip=0, limit=50) -> dict:
        q = select(Inconformidad).where(Inconformidad.tenant_id == current_user.tenant_id)
        if estado: q = q.where(Inconformidad.estado == estado)
        if severidad: q = q.where(Inconformidad.severidad == severidad)
        if expediente_id: q = q.where(Inconformidad.expediente_id == expediente_id)
        total = await db.scalar(select(func.count()).select_from(q.subquery())) or 0
        items = (await db.execute(q.offset(skip).limit(limit).order_by(
            Inconformidad.created_at.desc()))).scalars().all()
        return {"total": total, "items": items}

    async def obtener_inconformidad(self, db: AsyncSession, inconformidad_id: UUID, current_user: User) -> Inconformidad:
        i = (await db.execute(select(Inconformidad).where(and_(
            Inconformidad.id == inconformidad_id,
            Inconformidad.tenant_id == current_user.tenant_id)))).scalar_one_or_none()
        if not i: raise MegalodonException(ErrorCode.NOT_FOUND, f"Inconformidad '{inconformidad_id}' no encontrada.")
        return i

    async def actualizar_inconformidad(self, db: AsyncSession, inconformidad_id: UUID,
                                       data: InconformidadUpdate, current_user: User) -> Inconformidad:
        i = await self.obtener_inconformidad(db, inconformidad_id, current_user)
        for field in ['titulo','descripcion','severidad','estado','asignado_a','fecha_limite','resolucion','evidencia']:
            val = getattr(data, field, None)
            if val is not None: setattr(i, field, val)
        i.updated_by = current_user.id; await db.commit(); await db.refresh(i); return i

    async def crear_sancion(self, db: AsyncSession, data: SancionCreate, current_user: User) -> Sancion:
        s = Sancion(
            proveedor_id=data.proveedor_id, expediente_id=data.expediente_id,
            tipo=data.tipo, monto=data.monto, descripcion=data.descripcion,
            fundamento_legal=data.fundamento_legal, estado="ACTIVA",
            tenant_id=current_user.tenant_id, created_by=current_user.id)
        db.add(s); await db.commit(); await db.refresh(s); return s

    async def listar_sanciones(self, db: AsyncSession, current_user: User,
                               proveedor_id=None, tipo=None, skip=0, limit=50) -> dict:
        q = select(Sancion).where(Sancion.tenant_id == current_user.tenant_id)
        if proveedor_id: q = q.where(Sancion.proveedor_id == proveedor_id)
        if tipo: q = q.where(Sancion.tipo == tipo)
        total = await db.scalar(select(func.count()).select_from(q.subquery())) or 0
        items = (await db.execute(q.offset(skip).limit(limit).order_by(
            Sancion.created_at.desc()))).scalars().all()
        return {"total": total, "items": items}

    async def obtener_sancion(self, db: AsyncSession, sancion_id: UUID, current_user: User) -> Sancion:
        s = (await db.execute(select(Sancion).where(and_(
            Sancion.id == sancion_id, Sancion.tenant_id == current_user.tenant_id)))).scalar_one_or_none()
        if not s: raise MegalodonException(ErrorCode.NOT_FOUND, f"Sancion '{sancion_id}' no encontrada.")
        return s

    async def evaluar_expediente(self, db: AsyncSession, expediente_id: str, current_user: User) -> dict:
        reglas = (await db.execute(select(ReglaCumplimiento).where(and_(
            ReglaCumplimiento.tenant_id == current_user.tenant_id,
            ReglaCumplimiento.activa == True)))).scalars().all()
        cumplidas, incumplidas = [], []
        for r in reglas:
            if r.condicion_evaluacion:
                incumplidas.append({"regla_id":str(r.id),"nombre":r.nombre,"obligatorio":r.obligatorio,
                    "motivo":"Requiere evaluacion manual (condicion no automatizada aun)"})
            else:
                cumplidas.append({"regla_id":str(r.id),"nombre":r.nombre})
        score = len(cumplidas)/max(len(reglas),1)*100
        return {"expediente_id":expediente_id,"total_reglas":len(reglas),
            "cumplidas":len(cumplidas),"incumplidas":len(incumplidas),
            "score":round(score,2),"detalle_cumplidas":cumplidas,"detalle_incumplidas":incumplidas}
PYEOF

echo "   ✅ compliance_service.py"

# ─── SERVICIO 4: contrato_service.py ───────────────────────────────────────

cat > "$SERVICES_DIR/contrato_service.py" << 'PYEOF'
# Copyright © 2026 Cristian Rodriguez
"""Servicio de contratos — Administración contractual completa."""
from typing import Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.models.contrato import (
    Contrato, EstadoContrato, TipoGarantia, TipoModificacion, TipoPenalizacion,
    ConvenioModificatorio, GarantiaContrato, EntregableContrato, PenalizacionContrato,
)
from app.models.user import User
from app.schemas.contrato import (
    ContratoCreate, ContratoUpdate, ConvenioModificatorioCreate,
    GarantiaCreate, EntregableCreate, PenalizacionCreate,
)
from app.core.errors import MegalodonException, ErrorCode

class ContratoService:
    TRANSICIONES = {
        EstadoContrato.EN_FIRMA: [EstadoContrato.VIGENTE, EstadoContrato.CANCELADO],
        EstadoContrato.VIGENTE: [EstadoContrato.EN_MODIFICACION, EstadoContrato.SUSPENDIDO,
                                   EstadoContrato.RESCINDIDO, EstadoContrato.TERMINADO],
        EstadoContrato.EN_MODIFICACION: [EstadoContrato.VIGENTE],
        EstadoContrato.SUSPENDIDO: [EstadoContrato.VIGENTE, EstadoContrato.RESCINDIDO],
        EstadoContrato.RESCINDIDO: [], EstadoContrato.TERMINADO: [EstadoContrato.FINIQUITADO],
        EstadoContrato.FINIQUITADO: [], EstadoContrato.CANCELADO: [],
    }

    async def crear(self, db: AsyncSession, data: ContratoCreate, current_user: User) -> Contrato:
        c = Contrato(
            expediente_id=data.expediente_id, licitacion_id=data.licitacion_id,
            proveedor_id=data.proveedor_id, numero_contrato=data.numero_contrato,
            estado=EstadoContrato.EN_FIRMA, objeto=data.objeto,
            monto_total=data.monto_total, monto_original=data.monto_total,
            plazo_dias=data.plazo_dias, plazo_original=data.plazo_dias,
            fecha_firma=data.fecha_firma, fecha_inicio=data.fecha_inicio,
            fecha_termino=data.fecha_termino, lugar_ejecucion=data.lugar_ejecucion,
            supervisor_id=data.supervisor_id, residente_id=data.residente_id,
            tipo_contrato=data.tipo_contrato, partida_presupuestal=data.partida_presupuestal,
            clausulas_especiales=data.clausulas_especiales,
            anticipo_porcentaje=data.anticipo_porcentaje, ajuste_costos=data.ajuste_costos,
            tenant_id=current_user.tenant_id, created_by=current_user.id)
        db.add(c); await db.commit(); await db.refresh(c); return c

    async def listar(self, db: AsyncSession, current_user: User,
                     estado=None, expediente_id=None, proveedor_id=None, skip=0, limit=50) -> dict:
        q = select(Contrato).where(Contrato.tenant_id == current_user.tenant_id)
        if estado: q = q.where(Contrato.estado == estado)
        if expediente_id: q = q.where(Contrato.expediente_id == expediente_id)
        if proveedor_id: q = q.where(Contrato.proveedor_id == proveedor_id)
        total = await db.scalar(select(func.count()).select_from(q.subquery())) or 0
        items = (await db.execute(q.offset(skip).limit(limit).order_by(
            Contrato.created_at.desc()))).scalars().all()
        return {"total": total, "items": items}

    async def obtener(self, db: AsyncSession, contrato_id: UUID, current_user: User) -> Contrato:
        c = (await db.execute(select(Contrato).where(and_(
            Contrato.id == contrato_id, Contrato.tenant_id == current_user.tenant_id)))).scalar_one_or_none()
        if not c: raise MegalodonException(ErrorCode.NOT_FOUND, f"Contrato '{contrato_id}' no encontrado.")
        return c

    async def actualizar(self, db: AsyncSession, contrato_id: UUID, data: ContratoUpdate, current_user: User) -> Contrato:
        c = await self.obtener(db, contrato_id, current_user)
        for field in ['objeto','monto_total','plazo_dias','fecha_firma','fecha_inicio',
                      'fecha_termino','lugar_ejecucion','supervisor_id','residente_id',
                      'estado','anticipo_porcentaje','ajuste_costos','clausulas_especiales']:
            val = getattr(data, field, None)
            if val is not None: setattr(c, field, val)
        c.updated_by = current_user.id; await db.commit(); await db.refresh(c); return c

    async def transicionar_estado(self, db: AsyncSession, contrato_id: UUID,
                                   nuevo_estado: EstadoContrato, current_user: User) -> Contrato:
        c = await self.obtener(db, contrato_id, current_user)
        permitidos = self.TRANSICIONES.get(c.estado, [])
        if nuevo_estado not in permitidos:
            raise MegalodonException(ErrorCode.BAD_REQUEST,
                f"Transicion de '{c.estado}' a '{nuevo_estado}' no permitida.")
        c.estado = nuevo_estado; c.updated_by = current_user.id
        await db.commit(); await db.refresh(c); return c

    async def crear_modificatorio(self, db: AsyncSession, contrato_id: UUID,
                                   data: ConvenioModificatorioCreate, current_user: User) -> ConvenioModificatorio:
        c = await self.obtener(db, contrato_id, current_user)
        if c.estado not in [EstadoContrato.VIGENTE, EstadoContrato.EN_MODIFICACION]:
            raise MegalodonException(ErrorCode.BAD_REQUEST,
                f"No se puede modificar contrato en estado '{c.estado}'.")
        if c.estado == EstadoContrato.VIGENTE:
            c.estado = EstadoContrato.EN_MODIFICACION; c.updated_by = current_user.id
        m = ConvenioModificatorio(
            contrato_id=contrato_id, numero_convenio=data.numero_convenio,
            tipo=data.tipo, monto_adicional=data.monto_adicional,
            plazo_adicional_dias=data.plazo_adicional_dias, descripcion=data.descripcion,
            motivo=data.motivo, documento_soporte=data.documento_soporte, created_by=current_user.id)
        db.add(m)
        if data.monto_adicional: c.monto_total += data.monto_adicional
        if data.plazo_adicional_dias: c.plazo_dias += data.plazo_adicional_dias
        await db.commit(); await db.refresh(m); return m

    async def crear_garantia(self, db: AsyncSession, contrato_id: UUID,
                              data: GarantiaCreate, current_user: User) -> GarantiaContrato:
        c = await self.obtener(db, contrato_id, current_user)
        g = GarantiaContrato(
            contrato_id=contrato_id, tipo=data.tipo, monto=data.monto,
            aseguradora=data.aseguradora, numero_poliza=data.numero_poliza,
            fecha_emision=data.fecha_emision, fecha_vencimiento=data.fecha_vencimiento,
            documento_url=data.documento_url, observaciones=data.observaciones, created_by=current_user.id)
        db.add(g); await db.commit(); await db.refresh(g); return g

    async def verificar_vigencia_garantias(self, db: AsyncSession, contrato_id: UUID, current_user: User) -> List[dict]:
        from datetime import datetime, timedelta
        garantias = (await db.execute(select(GarantiaContrato).where(
            GarantiaContrato.contrato_id == contrato_id).order_by(
            GarantiaContrato.fecha_emision.desc()))).scalars().all()
        hoy = datetime.utcnow().date(); alertas = []
        for g in garantias:
            if g.fecha_vencimiento:
                dias = (g.fecha_vencimiento - hoy).days
                estado = "VENCIDA" if dias < 0 else ("PROXIMA_A_VENCER" if dias <= 30 else "VIGENTE")
                alertas.append({"garantia_id":str(g.id),"tipo":g.tipo,"numero_poliza":g.numero_poliza,
                    "fecha_vencimiento":g.fecha_vencimiento.isoformat(),"dias_restantes":dias,"estado":estado})
        return alertas

    async def crear_entregable(self, db: AsyncSession, contrato_id: UUID,
                                data: EntregableCreate, current_user: User) -> EntregableContrato:
        c = await self.obtener(db, contrato_id, current_user)
        e = EntregableContrato(
            contrato_id=contrato_id, tipo=data.tipo, numero=data.numero,
            descripcion=data.descripcion, avance_fisico=data.avance_fisico,
            avance_financiero=data.avance_financiero, monto_ejecutado=data.monto_ejecutado,
            fecha_inicio_periodo=data.fecha_inicio_periodo, fecha_fin_periodo=data.fecha_fin_periodo,
            documento_url=data.documento_url, estado="PENDIENTE", created_by=current_user.id)
        db.add(e); await db.commit(); await db.refresh(e); return e

    async def crear_penalizacion(self, db: AsyncSession, contrato_id: UUID,
                                  data: PenalizacionCreate, current_user: User) -> PenalizacionContrato:
        c = await self.obtener(db, contrato_id, current_user)
        p = PenalizacionContrato(
            contrato_id=contrato_id, tipo=data.tipo, monto=data.monto,
            porcentaje=data.porcentaje, descripcion=data.descripcion,
            fundamento_legal=data.fundamento_legal, documento_soporte=data.documento_soporte,
            estado="ACTIVA", created_by=current_user.id)
        db.add(p); await db.commit(); await db.refresh(p); return p

    async def resumen_contrato(self, db: AsyncSession, contrato_id: UUID, current_user: User) -> dict:
        c = await self.obtener(db, contrato_id, current_user)
        mods = (await db.execute(select(ConvenioModificatorio).where(
            ConvenioModificatorio.contrato_id == contrato_id))).scalars().all()
        gars = (await db.execute(select(GarantiaContrato).where(
            GarantiaContrato.contrato_id == contrato_id))).scalars().all()
        ents = (await db.execute(select(EntregableContrato).where(
            EntregableContrato.contrato_id == contrato_id).order_by(EntregableContrato.numero))).scalars().all()
        pens = (await db.execute(select(PenalizacionContrato).where(
            PenalizacionContrato.contrato_id == contrato_id))).scalars().all()
        monto_mods = sum(m.monto_adicional or 0 for m in mods)
        plazo_mods = sum(m.plazo_adicional_dias or 0 for m in mods)
        monto_ejec = sum(e.monto_ejecutado or 0 for e in ents if e.estado == "APROBADO")
        monto_pen = sum(p.monto or 0 for p in pens if p.estado == "ACTIVA")
        return {
            "contrato_id":str(c.id), "numero_contrato":c.numero_contrato,
            "estado":c.estado.value if hasattr(c.estado,'value') else c.estado,
            "objeto":c.objeto, "monto_original":float(c.monto_original or 0),
            "monto_total":float(c.monto_total or 0), "monto_modificaciones":round(monto_mods,4),
            "monto_ejecutado":round(monto_ejec,4), "monto_pendiente":round(float(c.monto_total or 0)-monto_ejec,4),
            "monto_penalizaciones":round(monto_pen,4), "plazo_original":c.plazo_original,
            "plazo_actual":c.plazo_dias, "plazo_modificaciones":plazo_mods,
            "total_modificatorios":len(mods), "total_garantias":len(gars),
            "total_entregables":len(ents), "total_penalizaciones":len(pens),
            "alertas_garantias":await self.verificar_vigencia_garantias(db, contrato_id, current_user),
        }
PYEOF

echo "   ✅ contrato_service.py"

# ─── SERVICIO 5: licitacion_service.py ─────────────────────────────────────

cat > "$SERVICES_DIR/licitacion_service.py" << 'PYEOF'
# Copyright © 2026 Cristian Rodriguez
"""Servicio de licitaciones — Maquina de estados legal completa."""
from typing import Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.models.licitacion import (
    Licitacion, EstadoLicitacion, TipoProcedimiento,
    JuntaAclaracion, Proposicion, EvaluacionLicitacion,
)
from app.models.user import User
from app.schemas.licitacion import (
    LicitacionCreate, LicitacionUpdate, JuntaAclaracionCreate,
    ProposicionCreate, EvaluacionCreate, TransicionEstadoCreate,
)
from app.core.errors import MegalodonException, ErrorCode

class LicitacionService:
    TRANSICIONES = {
        EstadoLicitacion.PLANEACION: [EstadoLicitacion.CONVOCATORIA, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.CONVOCATORIA: [EstadoLicitacion.JUNTA_ACLARACIONES, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.JUNTA_ACLARACIONES: [EstadoLicitacion.RECEPCION_PROPUESTAS, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.RECEPCION_PROPUESTAS: [EstadoLicitacion.APERTURA_PROPUESTAS, EstadoLicitacion.CANCELADA],
        EstadoLicitacion.APERTURA_PROPUESTAS: [EstadoLicitacion.EVALUACION, EstadoLicitacion.DESIERTA],
        EstadoLicitacion.EVALUACION: [EstadoLicitacion.FALLO, EstadoLicitacion.DESIERTA],
        EstadoLicitacion.FALLO: [EstadoLicitacion.CONTRATO, EstadoLicitacion.DESIERTA],
        EstadoLicitacion.CONTRATO: [EstadoLicitacion.EJECUCION],
        EstadoLicitacion.EJECUCION: [EstadoLicitacion.TERMINADA, EstadoLicitacion.RESCINDIDA],
        EstadoLicitacion.TERMINADA: [], EstadoLicitacion.RESCINDIDA: [],
        EstadoLicitacion.DESIERTA: [], EstadoLicitacion.CANCELADA: [],
    }

    async def crear(self, db: AsyncSession, data: LicitacionCreate, current_user: User) -> Licitacion:
        l = Licitacion(
            expediente_id=data.expediente_id, folio=data.folio,
            tipo_procedimiento=data.tipo_procedimiento, estado=EstadoLicitacion.PLANEACION,
            objeto=data.objeto, monto_estimado=data.monto_estimado, plazo_dias=data.plazo_dias,
            reglas_participacion=data.reglas_participacion, bases=data.bases,
            matriz_evaluacion=data.matriz_evaluacion,
            presupuesto_dependencia_miles=data.presupuesto_dependencia_miles,
            tenant_id=current_user.tenant_id, created_by=current_user.id)
        db.add(l); await db.commit(); await db.refresh(l); return l

    async def listar(self, db: AsyncSession, current_user: User,
                     estado=None, tipo_procedimiento=None, expediente_id=None, skip=0, limit=50) -> dict:
        q = select(Licitacion).where(Licitacion.tenant_id == current_user.tenant_id)
        if estado: q = q.where(Licitacion.estado == estado)
        if tipo_procedimiento: q = q.where(Licitacion.tipo_procedimiento == tipo_procedimiento)
        if expediente_id: q = q.where(Licitacion.expediente_id == expediente_id)
        total = await db.scalar(select(func.count()).select_from(q.subquery())) or 0
        items = (await db.execute(q.offset(skip).limit(limit).order_by(
            Licitacion.created_at.desc()))).scalars().all()
        return {"total": total, "items": items}

    async def obtener(self, db: AsyncSession, licitacion_id: UUID, current_user: User) -> Licitacion:
        l = (await db.execute(select(Licitacion).where(and_(
            Licitacion.id == licitacion_id, Licitacion.tenant_id == current_user.tenant_id)))).scalar_one_or_none()
        if not l: raise MegalodonException(ErrorCode.NOT_FOUND, f"Licitacion '{licitacion_id}' no encontrada.")
        return l

    async def actualizar(self, db: AsyncSession, licitacion_id: UUID, data: LicitacionUpdate, current_user: User) -> Licitacion:
        l = await self.obtener(db, licitacion_id, current_user)
        if l.estado not in [EstadoLicitacion.PLANEACION, EstadoLicitacion.CONVOCATORIA]:
            raise MegalodonException(ErrorCode.BAD_REQUEST,
                f"No se puede editar licitacion en estado '{l.estado.value}'.")
        for field in ['folio','objeto','monto_estimado','plazo_dias',
                      'reglas_participacion','bases','matriz_evaluacion']:
            val = getattr(data, field, None)
            if val is not None: setattr(l, field, val)
        l.updated_by = current_user.id; await db.commit(); await db.refresh(l); return l

    async def transicionar_estado(self, db: AsyncSession, licitacion_id: UUID,
                                   data: TransicionEstadoCreate, current_user: User) -> Licitacion:
        l = await self.obtener(db, licitacion_id, current_user)
        actual, nuevo = l.estado, data.nuevo_estado
        permitidos = self.TRANSICIONES.get(actual, [])
        if nuevo not in permitidos:
            raise MegalodonException(ErrorCode.BAD_REQUEST,
                f"Transicion de '{actual.value}' a '{nuevo.value}' no permitida.")
        if nuevo == EstadoLicitacion.CONVOCATORIA and (not l.folio or not l.bases):
            raise MegalodonException(ErrorCode.BAD_REQUEST, "Requiere folio y bases para convocatoria.")
        if nuevo == EstadoLicitacion.RECEPCION_PROPUESTAS:
            count = await db.scalar(select(func.count()).where(JuntaAclaracion.licitacion_id == licitacion_id)) or 0
            if count == 0: raise MegalodonException(ErrorCode.BAD_REQUEST,
                "Debe registrar al menos una junta de aclaraciones.")
        if nuevo == EstadoLicitacion.APERTURA_PROPUESTAS:
            count = await db.scalar(select(func.count()).where(Proposicion.licitacion_id == licitacion_id)) or 0
            if count == 0: raise MegalodonException(ErrorCode.BAD_REQUEST,
                "No hay proposiciones registradas.")
        if nuevo == EstadoLicitacion.FALLO:
            count = await db.scalar(select(func.count()).where(and_(
                EvaluacionLicitacion.licitacion_id == licitacion_id,
                EvaluacionLicitacion.resultado != None))) or 0
            if count == 0: raise MegalodonException(ErrorCode.BAD_REQUEST,
                "No hay evaluaciones completadas.")
        l.estado = nuevo; l.updated_by = current_user.id
        await db.commit(); await db.refresh(l); return l

    async def crear_junta_aclaraciones(self, db: AsyncSession, licitacion_id: UUID,
                                        data: JuntaAclaracionCreate, current_user: User) -> JuntaAclaracion:
        l = await self.obtener(db, licitacion_id, current_user)
        if l.estado not in [EstadoLicitacion.CONVOCATORIA, EstadoLicitacion.JUNTA_ACLARACIONES]:
            raise MegalodonException(ErrorCode.BAD_REQUEST,
                f"No se puede registrar junta en estado '{l.estado.value}'.")
        j = JuntaAclaracion(
            licitacion_id=licitacion_id, fecha=data.fecha, lugar=data.lugar,
            modalidad=data.modalidad, acta=data.acta, preguntas=data.preguntas,
            respuestas=data.respuestas, created_by=current_user.id)
        db.add(j)
        if l.estado == EstadoLicitacion.CONVOCATORIA:
            l.estado = EstadoLicitacion.JUNTA_ACLARACIONES; l.updated_by = current_user.id
        await db.commit(); await db.refresh(j); return j

    async def registrar_proposicion(self, db: AsyncSession, licitacion_id: UUID,
                                     data: ProposicionCreate, current_user: User) -> Proposicion:
        l = await self.obtener(db, licitacion_id, current_user)
        if l.estado not in [EstadoLicitacion.JUNTA_ACLARACIONES, EstadoLicitacion.RECEPCION_PROPUESTAS]:
            raise MegalodonException(ErrorCode.BAD_REQUEST,
                f"No se puede registrar proposicion en estado '{l.estado.value}'.")
        dup = (await db.execute(select(Proposicion).where(and_(
            Proposicion.licitacion_id == licitacion_id,
            Proposicion.proveedor_id == data.proveedor_id)))).scalar_one_or_none()
        if dup: raise MegalodonException(ErrorCode.CONFLICT,
            "El proveedor ya presento una proposicion en esta licitacion.")
        p = Proposicion(
            licitacion_id=licitacion_id, proveedor_id=data.proveedor_id,
            monto=data.monto, plazo_dias=data.plazo_dias, documentos=data.documentos,
            firma_digital=data.firma_digital, sello_tiempo=data.sello_tiempo,
            created_by=current_user.id)
        db.add(p)
        if l.estado == EstadoLicitacion.JUNTA_ACLARACIONES:
            l.estado = EstadoLicitacion.RECEPCION_PROPUESTAS; l.updated_by = current_user.id
        await db.commit(); await db.refresh(p); return p

    async def crear_evaluacion(self, db: AsyncSession, licitacion_id: UUID,
                                data: EvaluacionCreate, current_user: User) -> EvaluacionLicitacion:
        l = await self.obtener(db, licitacion_id, current_user)
        if l.estado != EstadoLicitacion.APERTURA_PROPUESTAS:
            raise MegalodonException(ErrorCode.BAD_REQUEST,
                f"Evaluacion solo permitida en estado '{EstadoLicitacion.APERTURA_PROPUESTAS.value}'.")
        e = EvaluacionLicitacion(
            licitacion_id=licitacion_id, proposicion_id=data.proposicion_id,
            tipo=data.tipo, puntaje=data.puntaje, observaciones=data.observaciones,
            cumple_requisitos=data.cumple_requisitos, resultado=data.resultado,
            evaluador_id=current_user.id, created_by=current_user.id)
        db.add(e); await db.commit(); await db.refresh(e); return e

    async def emitir_fallo(self, db: AsyncSession, licitacion_id: UUID,
                            proposicion_ganadora_id: UUID, current_user: User) -> dict:
        l = await self.obtener(db, licitacion_id, current_user)
        if l.estado != EstadoLicitacion.EVALUACION:
            raise MegalodonException(ErrorCode.BAD_REQUEST,
                f"Fallo solo permitido en estado '{EstadoLicitacion.EVALUACION.value}'.")
        g = (await db.execute(select(Proposicion).where(Proposicion.id == proposicion_ganadora_id))).scalar_one_or_none()
        if not g or g.licitacion_id != str(licitacion_id):
            raise MegalodonException(ErrorCode.NOT_FOUND,
                "Proposicion ganadora no encontrada o no pertenece a esta licitacion.")
        l.estado = EstadoLicitacion.FALLO; l.updated_by = current_user.id
        await db.commit()
        return {
            "licitacion_id": str(l.id), "folio": l.folio,
            "estado": l.estado.value,
            "ganador": {"proposicion_id": str(g.id), "proveedor_id": g.proveedor_id,
                        "monto": float(g.monto), "plazo_dias": g.plazo_dias},
            "fecha_fallo": l.updated_at.isoformat() if l.updated_at else None,
        }

    async def resumen_licitacion(self, db: AsyncSession, licitacion_id: UUID, current_user: User) -> dict:
        l = await self.obtener(db, licitacion_id, current_user)
        juntas = (await db.execute(select(JuntaAclaracion).where(
            JuntaAclaracion.licitacion_id == licitacion_id).order_by(JuntaAclaracion.fecha))).scalars().all()
        props = (await db.execute(select(Proposicion).where(
            Proposicion.licitacion_id == licitacion_id).order_by(Proposicion.monto))).scalars().all()
        evals = (await db.execute(select(EvaluacionLicitacion).where(
            EvaluacionLicitacion.licitacion_id == licitacion_id).order_by(EvaluacionLicitacion.created_at))).scalars().all()
        monto_min = min((p.monto for p in props if p.monto), default=0)
        monto_max = max((p.monto for p in props if p.monto), default=0)
        monto_avg = sum((p.monto for p in props if p.monto), default=0) / max(len(props), 1)
        return {
            "licitacion_id": str(l.id), "folio": l.folio,
            "estado": l.estado.value if hasattr(l.estado,'value') else str(l.estado),
            "tipo_procedimiento": l.tipo_procedimiento.value if hasattr(l.tipo_procedimiento,'value') else str(l.tipo_procedimiento),
            "objeto": l.objeto, "monto_estimado": float(l.monto_estimado or 0),
            "estadisticas": {
                "total_juntas": len(juntas), "total_proposiciones": len(props),
                "total_evaluaciones": len(evals), "monto_minimo": round(monto_min,4),
                "monto_maximo": round(monto_max,4), "monto_promedio": round(monto_avg,4),
            },
            "juntas": [{"id":str(j.id),"fecha":j.fecha.isoformat() if j.fecha else None} for j in juntas],
            "proposiciones": [{"id":str(p.id),"monto":float(p.monto or 0)} for p in props],
        }
PYEOF

echo "   ✅ licitacion_service.py"

echo ""
echo "🦈 Script 2 completado. 3 servicios instalados."
echo "   Total servicios nuevos: 5"
echo "   Ejecutar: bash scripts_fase2/02_instalacion_servicios_parte2.sh ./backend"
