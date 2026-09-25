#!/bin/bash
# =============================================================================
# FASE 2 — Script 4: Actualizar Routers Compliance + Contratos + Licitaciones
# =============================================================================

set -euo pipefail

BACKEND_DIR="${1:-./backend}"
API_DIR="$BACKEND_DIR/app/api/v1"

echo "🦈 MEGALODON FASE 2 — Script 4: Actualizando routers restantes..."
echo ""

backup_si_no_existe() {
    local f="$1"
    if [ ! -f "${f}.backup.original" ]; then
        cp "$f" "${f}.backup.original"
        echo "   💾 Backup: ${f}.backup.original"
    fi
}

# ─── ROUTER 3: compliance.py ─────────────────────────────────────────────────

backup_si_no_existe "$API_DIR/compliance.py"

cat > "$API_DIR/compliance.py" << 'PYEOF'
# Copyright © 2026 Cristian Rodriguez
"""Router de compliance — Reglas, inconformidades, sanciones y evaluación."""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.compliance import (
    ReglaCumplimientoCreate, ReglaCumplimientoOut,
    InconformidadCreate, InconformidadUpdate, InconformidadOut,
    SancionCreate, SancionOut,
)
from app.services.compliance_service import ComplianceService
from app.core.errors import handle_megalodon_errors

router = APIRouter(prefix="/compliance", tags=["Compliance"])
service = ComplianceService()

# ─── REGLAS ──────────────────────────────────────────────────────────────────

@router.post("/reglas", response_model=ReglaCumplimientoOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_regla(
    data: ReglaCumplimientoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Crea una regla de cumplimiento."""
    return await service.crear_regla(db, data, current_user)

@router.get("/reglas", response_model=dict)
@handle_megalodon_errors
async def listar_reglas(
    tipo_procedimiento: Optional[str] = Query(None),
    etapa: Optional[str] = Query(None),
    activa: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista reglas de cumplimiento con filtros."""
    return await service.listar_reglas(db, current_user, tipo_procedimiento, etapa, activa, skip, limit)

@router.get("/reglas/{regla_id}", response_model=ReglaCumplimientoOut)
@handle_megalodon_errors
async def obtener_regla(
    regla_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Obtiene una regla por ID."""
    return await service.obtener_regla(db, regla_id, current_user)

@router.patch("/reglas/{regla_id}", response_model=ReglaCumplimientoOut)
@handle_megalodon_errors
async def actualizar_regla(
    regla_id: UUID,
    data: ReglaCumplimientoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Actualiza una regla de cumplimiento."""
    return await service.actualizar_regla(db, regla_id, data, current_user)

@router.delete("/reglas/{regla_id}", status_code=status.HTTP_204_NO_CONTENT)
@handle_megalodon_errors
async def eliminar_regla(
    regla_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Elimina una regla."""
    await service.eliminar_regla(db, regla_id, current_user)

# ─── INCONFORMIDADES ───────────────────────────────────────────────────────

@router.post("/inconformidades", response_model=InconformidadOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_inconformidad(
    data: InconformidadCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registra una inconformidad."""
    return await service.crear_inconformidad(db, data, current_user)

@router.get("/inconformidades", response_model=dict)
@handle_megalodon_errors
async def listar_inconformidades(
    estado: Optional[str] = Query(None),
    severidad: Optional[str] = Query(None),
    expediente_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista inconformidades con filtros."""
    return await service.listar_inconformidades(db, current_user, estado, severidad, expediente_id, skip, limit)

@router.get("/inconformidades/{inconformidad_id}", response_model=InconformidadOut)
@handle_megalodon_errors
async def obtener_inconformidad(
    inconformidad_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Obtiene una inconformidad por ID."""
    return await service.obtener_inconformidad(db, inconformidad_id, current_user)

@router.patch("/inconformidades/{inconformidad_id}", response_model=InconformidadOut)
@handle_megalodon_errors
async def actualizar_inconformidad(
    inconformidad_id: UUID,
    data: InconformidadUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Actualiza una inconformidad."""
    return await service.actualizar_inconformidad(db, inconformidad_id, data, current_user)

# ─── SANCIONES ───────────────────────────────────────────────────────────────

@router.post("/sanciones", response_model=SancionOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_sancion(
    data: SancionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registra una sanción."""
    return await service.crear_sancion(db, data, current_user)

@router.get("/sanciones", response_model=dict)
@handle_megalodon_errors
async def listar_sanciones(
    proveedor_id: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista sanciones con filtros."""
    return await service.listar_sanciones(db, current_user, proveedor_id, tipo, skip, limit)

@router.get("/sanciones/{sancion_id}", response_model=SancionOut)
@handle_megalodon_errors
async def obtener_sancion(
    sancion_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Obtiene una sanción por ID."""
    return await service.obtener_sancion(db, sancion_id, current_user)

# ─── EVALUACIÓN ──────────────────────────────────────────────────────────────

@router.post("/evaluar/{expediente_id}")
@handle_megalodon_errors
async def evaluar_expediente(
    expediente_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Evalúa un expediente contra todas las reglas de cumplimiento activas."""
    return await service.evaluar_expediente(db, expediente_id, current_user)
PYEOF

echo "   ✅ compliance.py — 11 endpoints reales (antes: 5 stubs)"

# ─── ROUTER 4: contratos.py ──────────────────────────────────────────────────

backup_si_no_existe "$API_DIR/contratos.py"

cat > "$API_DIR/contratos.py" << 'PYEOF'
# Copyright © 2026 Cristian Rodriguez
"""Router de contratos — Ciclo contractual completo."""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.contrato import (
    ContratoCreate, ContratoOut, ContratoUpdate, ContratoList,
    ConvenioModificatorioCreate, ConvenioModificatorioOut,
    GarantiaCreate, GarantiaOut,
    EntregableCreate, EntregableOut,
    PenalizacionCreate, PenalizacionOut,
)
from app.services.contrato_service import ContratoService
from app.core.errors import handle_megalodon_errors

router = APIRouter(prefix="/contratos", tags=["Contratos"])
service = ContratoService()

# ─── CONTRATOS CRUD ────────────────────────────────────────────────────────

@router.post("", response_model=ContratoOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_contrato(
    data: ContratoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Crea un nuevo contrato en estado EN_FIRMA."""
    return await service.crear(db, data, current_user)

@router.get("", response_model=ContratoList)
@handle_megalodon_errors
async def listar_contratos(
    estado: Optional[str] = Query(None),
    expediente_id: Optional[str] = Query(None),
    proveedor_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista contratos con filtros."""
    return await service.listar(db, current_user, estado, expediente_id, proveedor_id, skip, limit)

@router.get("/{contrato_id}", response_model=ContratoOut)
@handle_megalodon_errors
async def obtener_contrato(
    contrato_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Obtiene un contrato por ID."""
    return await service.obtener(db, contrato_id, current_user)

@router.patch("/{contrato_id}", response_model=ContratoOut)
@handle_megalodon_errors
async def actualizar_contrato(
    contrato_id: UUID,
    data: ContratoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Actualiza un contrato (solo en estados tempranos)."""
    return await service.actualizar(db, contrato_id, data, current_user)

@router.post("/{contrato_id}/transicionar")
@handle_megalodon_errors
async def transicionar_estado_contrato(
    contrato_id: UUID,
    nuevo_estado: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transiciona el estado del contrato con validación de máquina de estados."""
    from app.models.contrato import EstadoContrato
    return await service.transicionar_estado(db, contrato_id, EstadoContrato(nuevo_estado), current_user)

# ─── CONVENIOS MODIFICATORIOS ────────────────────────────────────────────────

@router.post("/{contrato_id}/modificatorios", response_model=ConvenioModificatorioOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_modificatorio(
    contrato_id: UUID,
    data: ConvenioModificatorioCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Crea un convenio modificatorio."""
    return await service.crear_modificatorio(db, contrato_id, data, current_user)

@router.get("/{contrato_id}/modificatorios", response_model=list[ConvenioModificatorioOut])
@handle_megalodon_errors
async def listar_modificatorios(
    contrato_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista convenios modificatorios."""
    return await service.listar_modificatorios(db, contrato_id, current_user)

# ─── GARANTÍAS ───────────────────────────────────────────────────────────────

@router.post("/{contrato_id}/garantias", response_model=GarantiaOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_garantia(
    contrato_id: UUID,
    data: GarantiaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registra una garantía de contrato."""
    return await service.crear_garantia(db, contrato_id, data, current_user)

@router.get("/{contrato_id}/garantias", response_model=list[GarantiaOut])
@handle_megalodon_errors
async def listar_garantias(
    contrato_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista garantías de un contrato."""
    return await service.listar_garantias(db, contrato_id, current_user)

@router.get("/{contrato_id}/garantias/vigencia")
@handle_megalodon_errors
async def verificar_vigencia_garantias(
    contrato_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verifica vigencia de garantías y alerta por vencimiento próximo."""
    return await service.verificar_vigencia_garantias(db, contrato_id, current_user)

# ─── ENTREGABLES / ESTIMACIONES ────────────────────────────────────────────

@router.post("/{contrato_id}/entregables", response_model=EntregableOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_entregable(
    contrato_id: UUID,
    data: EntregableCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registra un entregable o estimación."""
    return await service.crear_entregable(db, contrato_id, data, current_user)

@router.get("/{contrato_id}/entregables", response_model=list[EntregableOut])
@handle_megalodon_errors
async def listar_entregables(
    contrato_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista entregables de un contrato."""
    return await service.listar_entregables(db, contrato_id, current_user)

# ─── PENALIZACIONES ──────────────────────────────────────────────────────────

@router.post("/{contrato_id}/penalizaciones", response_model=PenalizacionOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_penalizacion(
    contrato_id: UUID,
    data: PenalizacionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registra una penalización."""
    return await service.crear_penalizacion(db, contrato_id, data, current_user)

# ─── RESUMEN CONTRACTUAL ─────────────────────────────────────────────────────

@router.get("/{contrato_id}/resumen")
@handle_megalodon_errors
async def resumen_contrato(
    contrato_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Genera resumen completo: montos, plazos, garantías, alertas."""
    return await service.resumen_contrato(db, contrato_id, current_user)
PYEOF

echo "   ✅ contratos.py — 14 endpoints reales (antes: 7 stubs)"

# ─── ROUTER 5: licitaciones.py ───────────────────────────────────────────────

backup_si_no_existe "$API_DIR/licitaciones.py"

cat > "$API_DIR/licitaciones.py" << 'PYEOF'
# Copyright © 2026 Cristian Rodriguez
"""Router de licitaciones — Máquina de estados legal completa."""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.licitacion import (
    LicitacionCreate, LicitacionOut, LicitacionUpdate, LicitacionList,
    JuntaAclaracionCreate, JuntaAclaracionOut,
    ProposicionCreate, ProposicionOut,
    EvaluacionCreate, EvaluacionOut,
    TransicionEstadoCreate,
)
from app.services.licitacion_service import LicitacionService
from app.core.errors import handle_megalodon_errors

router = APIRouter(prefix="/licitaciones", tags=["Licitaciones"])
service = LicitacionService()

# ─── CRUD BÁSICO ───────────────────────────────────────────────────────────

@router.post("", response_model=LicitacionOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_licitacion(
    data: LicitacionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Crea una nueva licitación en estado PLANEACION."""
    return await service.crear(db, data, current_user)

@router.get("", response_model=LicitacionList)
@handle_megalodon_errors
async def listar_licitaciones(
    estado: Optional[str] = Query(None),
    tipo_procedimiento: Optional[str] = Query(None),
    expediente_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista licitaciones con filtros."""
    from app.models.licitacion import EstadoLicitacion, TipoProcedimiento
    est = EstadoLicitacion(estado) if estado else None
    tp = TipoProcedimiento(tipo_procedimiento) if tipo_procedimiento else None
    return await service.listar(db, current_user, est, tp, expediente_id, skip, limit)

@router.get("/{licitacion_id}", response_model=LicitacionOut)
@handle_megalodon_errors
async def obtener_licitacion(
    licitacion_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Obtiene una licitación por ID."""
    return await service.obtener(db, licitacion_id, current_user)

@router.patch("/{licitacion_id}", response_model=LicitacionOut)
@handle_megalodon_errors
async def actualizar_licitacion(
    licitacion_id: UUID,
    data: LicitacionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Actualiza una licitación (solo en estados tempranos)."""
    return await service.actualizar(db, licitacion_id, data, current_user)

# ─── TRANSICIÓN DE ESTADO ────────────────────────────────────────────────────

@router.post("/{licitacion_id}/transicionar", response_model=LicitacionOut)
@handle_megalodon_errors
async def transicionar_estado_licitacion(
    licitacion_id: UUID,
    data: TransicionEstadoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transiciona el estado con validación de máquina de estados legal."""
    return await service.transicionar_estado(db, licitacion_id, data, current_user)

# ─── JUNTA DE ACLARACIONES ─────────────────────────────────────────────────

@router.post("/{licitacion_id}/junta-aclaraciones", response_model=JuntaAclaracionOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_junta_aclaraciones(
    licitacion_id: UUID,
    data: JuntaAclaracionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registra una junta de aclaraciones."""
    return await service.crear_junta_aclaraciones(db, licitacion_id, data, current_user)

@router.get("/{licitacion_id}/junta-aclaraciones", response_model=list[JuntaAclaracionOut])
@handle_megalodon_errors
async def listar_juntas_aclaraciones(
    licitacion_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista juntas de aclaraciones."""
    return await service.listar_juntas(db, licitacion_id, current_user)

# ─── PROPOSICIONES ─────────────────────────────────────────────────────────

@router.post("/{licitacion_id}/proposiciones", response_model=ProposicionOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def registrar_proposicion(
    licitacion_id: UUID,
    data: ProposicionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registra una proposición u oferta."""
    return await service.registrar_proposicion(db, licitacion_id, data, current_user)

@router.get("/{licitacion_id}/proposiciones", response_model=list[ProposicionOut])
@handle_megalodon_errors
async def listar_proposiciones(
    licitacion_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista proposiciones de una licitación."""
    return await service.listar_proposiciones(db, licitacion_id, current_user)

# ─── EVALUACIÓN ────────────────────────────────────────────────────────────

@router.post("/{licitacion_id}/evaluaciones", response_model=EvaluacionOut, status_code=status.HTTP_201_CREATED)
@handle_megalodon_errors
async def crear_evaluacion(
    licitacion_id: UUID,
    data: EvaluacionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registra una evaluación de proposición."""
    return await service.crear_evaluacion(db, licitacion_id, data, current_user)

# ─── FALLO ─────────────────────────────────────────────────────────────────

@router.post("/{licitacion_id}/fallo")
@handle_megalodon_errors
async def emitir_fallo(
    licitacion_id: UUID,
    proposicion_ganadora_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Emite el fallo de la licitación."""
    return await service.emitir_fallo(db, licitacion_id, proposicion_ganadora_id, current_user)

# ─── RESUMEN ─────────────────────────────────────────────────────────────────

@router.get("/{licitacion_id}/resumen")
@handle_megalodon_errors
async def resumen_licitacion(
    licitacion_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Genera resumen completo del proceso de licitación."""
    return await service.resumen_licitacion(db, licitacion_id, current_user)
PYEOF

echo "   ✅ licitaciones.py — 13 endpoints reales (antes: 6 stubs)"

echo ""
echo "🦈 Script 4 completado. Routers compliance + contratos + licitaciones actualizados."
echo "   Total endpoints nuevos/reales: 38"
echo "   Ejecutar: bash scripts_fase2/04_actualizar_routers_parte2.sh ./backend"
