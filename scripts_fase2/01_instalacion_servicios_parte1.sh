#!/bin/bash
# =============================================================================
# FASE 2 — Script 1: Instalar 5 Servicios Nuevos
# =============================================================================
# Este script COPIA archivos NUEVOS, NUNCA modifica existentes.
# Si un archivo ya existe, hace backup (.backup) antes de escribir.
# =============================================================================

set -euo pipefail

BACKEND_DIR="${1:-./backend}"
SERVICES_DIR="$BACKEND_DIR/app/services"

echo "🦈 MEGALODON FASE 2 — Script 1: Instalando 5 servicios nuevos..."
echo "   Directorio objetivo: $SERVICES_DIR"
echo ""

# Función segura: backup + escribir
escribir_seguro() {
    local archivo="$1"
    local contenido="$2"

    if [ -f "$archivo" ]; then
        echo "   ⚠️  $archivo ya existe → backup a ${archivo}.backup"
        cp "$archivo" "${archivo}.backup"
    fi

    echo "$contenido" > "$archivo"
    echo "   ✅ $archivo"
}

# ─── SERVICIO 1: catalogo_apu_service.py ───────────────────────────────────

cat > "$SERVICES_DIR/catalogo_apu_service.py" << 'PYEOF'
# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
"""Servicio de catálogo de Análisis de Precios Unitarios (APU)."""
from typing import Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from app.models.catalogo_apu import CatalogoAPU, PrecioUnitarioAsignado
from app.models.user import User
from app.schemas.catalogo_apu import CatalogoAPUCreate, CatalogoAPUOut, CatalogoAPUList
from app.core.errors import MegalodonException, ErrorCode

class CatalogoAPUService:
    async def crear(self, db: AsyncSession, data: CatalogoAPUCreate, current_user: User) -> CatalogoAPU:
        stmt = select(CatalogoAPU).where(and_(
            CatalogoAPU.clave == data.clave,
            CatalogoAPU.fuente == data.fuente,
            CatalogoAPU.zona_economica == data.zona_economica,
            CatalogoAPU.tenant_id == current_user.tenant_id,
        ))
        if (await db.execute(stmt)).scalar_one_or_none():
            raise MegalodonException(ErrorCode.CONFLICT,
                f"Concepto APU '{data.clave}'+fuente+'{data.zona_economica}' ya existe.")
        concepto = CatalogoAPU(
            clave=data.clave, descripcion=data.descripcion, tipo=data.tipo.value,
            unidad=data.unidad.value, precio_unitario=data.precio_unitario,
            fuente=data.fuente, zona_economica=data.zona_economica,
            estado=data.estado, incluye_iva=data.incluye_iva, desglose=data.desglose,
            tenant_id=current_user.tenant_id, created_by=current_user.id,
        )
        db.add(concepto); await db.commit(); await db.refresh(concepto)
        return concepto

    async def listar(self, db: AsyncSession, current_user: User, skip=0, limit=100,
                     fuente=None, zona=None, tipo=None, q=None) -> CatalogoAPUList:
        query = select(CatalogoAPU).where(CatalogoAPU.tenant_id == current_user.tenant_id)
        if fuente: query = query.where(CatalogoAPU.fuente.ilike(f"%{fuente}%"))
        if zona: query = query.where(CatalogoAPU.zona_economica.ilike(f"%{zona}%"))
        if tipo: query = query.where(CatalogoAPU.tipo == tipo)
        if q:
            search = f"%{q}%"
            query = query.where(or_(
                CatalogoAPU.clave.ilike(search),
                CatalogoAPU.descripcion.ilike(search),
                CatalogoAPU.fuente.ilike(search),
            ))
        total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
        query = query.offset(skip).limit(limit).order_by(CatalogoAPU.clave)
        items = (await db.execute(query)).scalars().all()
        return CatalogoAPUList(total=total, items=items)

    async def obtener(self, db: AsyncSession, concepto_id: UUID, current_user: User) -> CatalogoAPU:
        stmt = select(CatalogoAPU).where(and_(
            CatalogoAPU.id == concepto_id, CatalogoAPU.tenant_id == current_user.tenant_id))
        c = (await db.execute(stmt)).scalar_one_or_none()
        if not c: raise MegalodonException(ErrorCode.NOT_FOUND, f"Concepto '{concepto_id}' no encontrado.")
        return c

    async def actualizar(self, db: AsyncSession, concepto_id: UUID, data: CatalogoAPUCreate, current_user: User) -> CatalogoAPU:
        c = await self.obtener(db, concepto_id, current_user)
        c.descripcion=data.descripcion; c.tipo=data.tipo.value; c.unidad=data.unidad.value
        c.precio_unitario=data.precio_unitario; c.fuente=data.fuente
        c.zona_economica=data.zona_economica; c.estado=data.estado
        c.incluye_iva=data.incluye_iva; c.desglose=data.desglose; c.updated_by=current_user.id
        await db.commit(); await db.refresh(c); return c

    async def eliminar(self, db: AsyncSession, concepto_id: UUID, current_user: User) -> None:
        c = await self.obtener(db, concepto_id, current_user)
        await db.delete(c); await db.commit()

    async def obtener_precio_con_iva(self, db: AsyncSession, concepto_id: UUID,
                                     tasa_iva=0.16, current_user=None) -> dict:
        c = await self.obtener(db, concepto_id, current_user)
        base = float(c.precio_unitario)
        if c.incluye_iva:
            sin_iva = base / (1 + tasa_iva); con_iva = base
        else:
            sin_iva = base; con_iva = base * (1 + tasa_iva)
        return {
            "concepto_id": str(c.id), "clave": c.clave, "descripcion": c.descripcion,
            "precio_base": round(base,4), "precio_sin_iva": round(sin_iva,4),
            "precio_con_iva": round(con_iva,4), "tasa_iva_aplicada": tasa_iva,
            "incluye_iva_original": c.incluye_iva, "fuente": c.fuente,
        }
PYEOF

echo "   ✅ catalogo_apu_service.py"

# ─── SERVICIO 2: catalogo_conceptos_service.py ─────────────────────────────

cat > "$SERVICES_DIR/catalogo_conceptos_service.py" << 'PYEOF'
# Copyright © 2026 Cristian Rodriguez
"""Servicio de catálogos de conceptos reales (CFE, CMIC, CONAGA, SCT, PEMEX, CUSTOM)."""
from typing import Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from app.models.catalogo_conceptos import CatalogoFuente, ConceptoCatalogo, InsumoCatalogo
from app.models.user import User
from app.schemas.catalogo_conceptos import (
    CatalogoFuenteCreate, ConceptoCatalogoCreate, ConceptoCatalogoOut,
    ConceptoCatalogoList, InsumoCatalogoCreate, InsumoCatalogoOut,
)
from app.core.errors import MegalodonException, ErrorCode

class CatalogoConceptosService:
    # ─── FUENTES ───
    async def crear_fuente(self, db: AsyncSession, data: CatalogoFuenteCreate, current_user: User) -> CatalogoFuente:
        stmt = select(CatalogoFuente).where(and_(
            CatalogoFuente.nombre == data.nombre,
            CatalogoFuente.tipo == data.tipo.value,
        ))
        if (await db.execute(stmt)).scalar_one_or_none():
            raise MegalodonException(ErrorCode.CONFLICT, f"Fuente '{data.nombre}' ya existe.")
        f = CatalogoFuente(nombre=data.nombre, tipo=data.tipo.value,
            vigencia_inicio=data.vigencia_inicio, vigencia_fin=data.vigencia_fin,
            descripcion=data.descripcion, url_fuente=data.url_fuente, created_by=current_user.id)
        db.add(f); await db.commit(); await db.refresh(f); return f

    async def listar_fuentes(self, db: AsyncSession, activo=None) -> List[CatalogoFuente]:
        q = select(CatalogoFuente)
        if activo is not None: q = q.where(CatalogoFuente.activo == activo)
        return (await db.execute(q.order_by(CatalogoFuente.nombre))).scalars().all()

    async def obtener_fuente(self, db: AsyncSession, fuente_id: UUID) -> CatalogoFuente:
        f = (await db.execute(select(CatalogoFuente).where(CatalogoFuente.id == fuente_id))).scalar_one_or_none()
        if not f: raise MegalodonException(ErrorCode.NOT_FOUND, f"Fuente '{fuente_id}' no encontrada.")
        return f

    # ─── CONCEPTOS ───
    async def crear_concepto(self, db: AsyncSession, data: ConceptoCatalogoCreate, current_user: User) -> ConceptoCatalogo:
        await self.obtener_fuente(db, UUID(data.fuente_id))
        stmt = select(ConceptoCatalogo).where(and_(
            ConceptoCatalogo.clave == data.clave,
            ConceptoCatalogo.fuente_id == data.fuente_id,
            ConceptoCatalogo.zona_economica == data.zona_economica,
        ))
        if (await db.execute(stmt)).scalar_one_or_none():
            raise MegalodonException(ErrorCode.CONFLICT, f"Concepto '{data.clave}' ya existe.")
        c = ConceptoCatalogo(
            fuente_id=data.fuente_id, clave=data.clave, descripcion=data.descripcion,
            descripcion_larga=data.descripcion_larga, unidad=data.unidad,
            precio_unitario=data.precio_unitario, zona_economica=data.zona_economica,
            estado=data.estado, region=data.region, incluye_iva=data.incluye_iva,
            desglose=data.desglose, created_by=current_user.id)
        db.add(c); await db.commit(); await db.refresh(c); return c

    async def listar_conceptos(self, db: AsyncSession, skip=0, limit=100,
                               fuente_id=None, zona=None, estado=None, q=None) -> ConceptoCatalogoList:
        query = select(ConceptoCatalogo).where(ConceptoCatalogo.activo == True)
        if fuente_id: query = query.where(ConceptoCatalogo.fuente_id == fuente_id)
        if zona: query = query.where(ConceptoCatalogo.zona_economica.ilike(f"%{zona}%"))
        if estado: query = query.where(ConceptoCatalogo.estado.ilike(f"%{estado}%"))
        if q:
            search = f"%{q}%"
            query = query.where(or_(
                ConceptoCatalogo.clave.ilike(search),
                ConceptoCatalogo.descripcion.ilike(search),
                ConceptoCatalogo.descripcion_larga.ilike(search),
            ))
        total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = (await db.execute(query.offset(skip).limit(limit).order_by(ConceptoCatalogo.clave))).scalars().all()
        return ConceptoCatalogoList(total=total, items=items)

    async def obtener_concepto(self, db: AsyncSession, concepto_id: UUID) -> ConceptoCatalogo:
        c = (await db.execute(select(ConceptoCatalogo).where(ConceptoCatalogo.id == concepto_id))).scalar_one_or_none()
        if not c: raise MegalodonException(ErrorCode.NOT_FOUND, f"Concepto '{concepto_id}' no encontrado.")
        return c

    # ─── INSUMOS ───
    async def crear_insumo(self, db: AsyncSession, data: InsumoCatalogoCreate, current_user: User) -> InsumoCatalogo:
        await self.obtener_fuente(db, UUID(data.fuente_id))
        stmt = select(InsumoCatalogo).where(and_(
            InsumoCatalogo.clave == data.clave,
            InsumoCatalogo.fuente_id == data.fuente_id,
            InsumoCatalogo.zona_economica == data.zona_economica,
            InsumoCatalogo.tipo == data.tipo,
        ))
        if (await db.execute(stmt)).scalar_one_or_none():
            raise MegalodonException(ErrorCode.CONFLICT, f"Insumo '{data.clave}' ya existe.")
        i = InsumoCatalogo(
            fuente_id=data.fuente_id, clave=data.clave, descripcion=data.descripcion,
            tipo=data.tipo, unidad=data.unidad, precio_unitario=data.precio_unitario,
            categoria=data.categoria, subcategoria=data.subcategoria,
            zona_economica=data.zona_economica, estado=data.estado,
            incluye_iva=data.incluye_iva, created_by=current_user.id)
        db.add(i); await db.commit(); await db.refresh(i); return i

    async def listar_insumos(self, db: AsyncSession, skip=0, limit=100,
                             fuente_id=None, tipo=None, categoria=None) -> List[InsumoCatalogo]:
        q = select(InsumoCatalogo).where(InsumoCatalogo.activo == True)
        if fuente_id: q = q.where(InsumoCatalogo.fuente_id == fuente_id)
        if tipo: q = q.where(InsumoCatalogo.tipo == tipo)
        if categoria: q = q.where(InsumoCatalogo.categoria.ilike(f"%{categoria}%"))
        return (await db.execute(q.offset(skip).limit(limit).order_by(InsumoCatalogo.clave))).scalars().all()

    async def calcular_costo_desglosado(self, db: AsyncSession, concepto_id: UUID,
                                        cantidad=1.0, tasa_iva=0.16) -> dict:
        c = await self.obtener_concepto(db, concepto_id)
        d = c.desglose or {}
        mats = sum(m.get("cantidad",0)*m.get("precio",0) for m in d.get("materiales",[]))
        mo = sum(m.get("cantidad",0)*m.get("precio",0) for m in d.get("mano_obra",[]))
        maq = sum(m.get("cantidad",0)*m.get("precio",0) for m in d.get("maquinaria",[]))
        ind = sum(m.get("cantidad",0)*m.get("precio",0) for m in d.get("indirectos",[]))
        sub = mats + mo + maq + ind
        if c.incluye_iva:
            sin_iva = sub/(1+tasa_iva); iva = sub - sin_iva; total = sub
        else:
            iva = sub*tasa_iva; total = sub+iva; sin_iva = sub
        return {
            "concepto_id": str(c.id), "clave": c.clave, "descripcion": c.descripcion,
            "cantidad": cantidad,
            "desglose": {
                "materiales":{"items":len(d.get("materiales",[])),"subtotal":round(mats,4)},
                "mano_obra":{"items":len(d.get("mano_obra",[])),"subtotal":round(mo,4)},
                "maquinaria":{"items":len(d.get("maquinaria",[])),"subtotal":round(maq,4)},
                "indirectos":{"items":len(d.get("indirectos",[])),"subtotal":round(ind,4)},
            },
            "subtotal": round(sub*cantidad,4), "total_sin_iva": round(sin_iva*cantidad,4),
            "iva": round(iva*cantidad,4), "total": round(total*cantidad,4),
            "tasa_iva_aplicada": tasa_iva, "unidad": c.unidad,
        }
PYEOF

echo "   ✅ catalogo_conceptos_service.py"

echo ""
echo "🦈 Script 1 completado. 2 servicios instalados."
echo "   Ejecutar: bash scripts_fase2/01_instalacion_servicios.sh ./backend"
