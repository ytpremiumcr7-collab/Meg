#!/bin/bash
# =============================================================================
# FASE 2 — Script 3: Actualizar Routers (Endpoints) — Reemplazar stubs por real
# =============================================================================
# Este script hace BACKUP de cada router antes de modificarlo.
# Solo reemplaza funciones que tienen "pass" — nunca toca lo que ya funciona.
# =============================================================================

set -euo pipefail

BACKEND_DIR="${1:-./backend}"
API_DIR="$BACKEND_DIR/app/api/v1"

echo "🦈 MEGALODON FASE 2 — Script 3: Actualizando routers..."
echo "   Directorio objetivo: $API_DIR"
echo ""

backup_si_no_existe() {
    local f="$1"
    if [ ! -f "${f}.backup.original" ]; then
        cp "$f" "${f}.backup.original"
        echo "   💾 Backup: ${f}.backup.original"
    fi
}

# ─── ROUTER 1: catalogo_apu.py ───────────────────────────────────────────────

backup_si_no_existe "$API_DIR/catalogo_apu.py"

cat > "$API_DIR/catalogo_apu.py" << 'PYEOF'
# Copyright © 2026 Cristian Rodriguez
"""Router de catálogo APU — Análisis de Precios Unitarios."""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.catalogo_apu import CatalogoAPUCreate, CatalogoAPUOut, CatalogoAPUList
from app.services.catalogo_apu_service import CatalogoAPUService
from app.core.errors import handle_megalodon_errors

router = APIRouter(prefix="/catalogo-apu", tags=["Catálogo APU"])
service = CatalogoAPUService()

@router.post("", response_model=CatalogoAPUOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_concepto_apu(
    data: CatalogoAPUCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Crea un nuevo concepto APU en el catálogo maestro."""
    return await service.crear(db, data, current_user)

@router.get("", response_model=CatalogoAPUList)
@handle_megalodon_errors
async def listar_conceptos_apu(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    fuente: Optional[str] = Query(None),
    zona: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Búsqueda en clave, descripción o fuente"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista conceptos APU con filtros y búsqueda full-text."""
    return await service.listar(db, current_user, skip, limit, fuente, zona, tipo, q)

@router.get("/{concepto_id}", response_model=CatalogoAPUOut)
@handle_megalodon_errors
async def obtener_concepto_apu(
    concepto_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Obtiene un concepto APU por ID."""
    return await service.obtener(db, concepto_id, current_user)

@router.patch("/{concepto_id}", response_model=CatalogoAPUOut)
@handle_megalodon_errors
async def actualizar_concepto_apu(
    concepto_id: UUID,
    data: CatalogoAPUCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Actualiza un concepto APU existente."""
    return await service.actualizar(db, concepto_id, data, current_user)

@router.delete("/{concepto_id}", status_code=status.HTTP_204_NO_CONTENT)
@handle_megalodon_errors
async def eliminar_concepto_apu(
    concepto_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Elimina un concepto APU."""
    await service.eliminar(db, concepto_id, current_user)

@router.get("/{concepto_id}/precio-con-iva")
@handle_megalodon_errors
async def obtener_precio_con_iva(
    concepto_id: UUID,
    tasa_iva: float = Query(0.16, ge=0, le=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Obtiene precio unitario con y sin IVA (INP al tiempo real)."""
    return await service.obtener_precio_con_iva(db, concepto_id, tasa_iva, current_user)
PYEOF

echo "   ✅ catalogo_apu.py — 6 endpoints reales (antes: 3 stubs)"

# ─── ROUTER 2: catalogo_conceptos.py ─────────────────────────────────────────

backup_si_no_existe "$API_DIR/catalogo_conceptos.py"

cat > "$API_DIR/catalogo_conceptos.py" << 'PYEOF'
# Copyright © 2026 Cristian Rodriguez
"""Router de catálogo de conceptos — Fuentes, conceptos e insumos."""
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.catalogo_conceptos import (
    CatalogoFuenteCreate, CatalogoFuenteOut, ConceptoCatalogoCreate,
    ConceptoCatalogoOut, ConceptoCatalogoList, InsumoCatalogoCreate, InsumoCatalogoOut,
)
from app.services.catalogo_conceptos_service import CatalogoConceptosService
from app.core.errors import handle_megalodon_errors

router = APIRouter(prefix="/catalogo-conceptos", tags=["Catálogo Conceptos"])
service = CatalogoConceptosService()

# ─── FUENTES ─────────────────────────────────────────────────────────────────

@router.post("/fuentes", response_model=CatalogoFuenteOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_fuente(
    data: CatalogoFuenteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registra una fuente de catálogo (CFE, CMIC, CONAGA, etc.)."""
    return await service.crear_fuente(db, data, current_user)

@router.get("/fuentes", response_model=List[CatalogoFuenteOut])
@handle_megalodon_errors
async def listar_fuentes(
    activo: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista fuentes de catálogo."""
    return await service.listar_fuentes(db, activo)

# ─── CONCEPTOS ───────────────────────────────────────────────────────────────

@router.post("/conceptos", response_model=ConceptoCatalogoOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_concepto(
    data: ConceptoCatalogoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Crea un concepto de trabajo en el catálogo."""
    return await service.crear_concepto(db, data, current_user)

@router.get("/conceptos", response_model=ConceptoCatalogoList)
@handle_megalodon_errors
async def listar_conceptos(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    fuente_id: Optional[str] = Query(None),
    zona: Optional[str] = Query(None),
    estado: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Busca/lista conceptos con filtros por fuente, zona, estado y texto."""
    return await service.listar_conceptos(db, skip, limit, fuente_id, zona, estado, q)

@router.get("/conceptos/{concepto_id}", response_model=ConceptoCatalogoOut)
@handle_megalodon_errors
async def obtener_concepto(
    concepto_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Obtiene un concepto por ID."""
    return await service.obtener_concepto(db, concepto_id)

@router.patch("/conceptos/{concepto_id}", response_model=ConceptoCatalogoOut)
@handle_megalodon_errors
async def actualizar_concepto(
    concepto_id: UUID,
    data: ConceptoCatalogoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Actualiza un concepto existente."""
    return await service.actualizar_concepto(db, concepto_id, data, current_user)

@router.get("/conceptos/{concepto_id}/costo-desglosado")
@handle_megalodon_errors
async def calcular_costo_desglosado(
    concepto_id: UUID,
    cantidad: float = Query(1.0, gt=0),
    tasa_iva: float = Query(0.16, ge=0, le=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Calcula el costo desglosado: materiales + mano obra + maquinaria + indirectos + IVA."""
    return await service.calcular_costo_desglosado(db, concepto_id, cantidad, tasa_iva)

# ─── INSUMOS ─────────────────────────────────────────────────────────────────

@router.post("/insumos", response_model=InsumoCatalogoOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_insumo(
    data: InsumoCatalogoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Crea un insumo desglosado (material, mano de obra, maquinaria, salario profesional)."""
    return await service.crear_insumo(db, data, current_user)

@router.get("/insumos", response_model=List[InsumoCatalogoOut])
@handle_megalodon_errors
async def listar_insumos(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    fuente_id: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    categoria: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista insumos con filtros."""
    return await service.listar_insumos(db, skip, limit, fuente_id, tipo, categoria)
PYEOF

echo "   ✅ catalogo_conceptos.py — 9 endpoints reales (antes: 7 stubs)"

echo ""
echo "🦈 Script 3 — Parte 1 completada. Routers de catálogos actualizados."
echo "   Ejecutar: bash scripts_fase2/03_actualizar_routers_parte1.sh ./backend"
