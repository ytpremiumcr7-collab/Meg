#!/bin/bash
# =============================================================================
# FASE 2 — MASTER SCRIPT: Instalación completa de correcciones
# =============================================================================
# Ejecuta todos los scripts en orden, con verificación de cada paso.
# Si algo falla, se detiene y reporta.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${1:-./backend}"
FRONTEND_DIR="${2:-./frontend}"

echo ""
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║           🦈 MEGALODON FASE 2 — INSTALACIÓN COMPLETA                ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""
echo "   Backend:  $BACKEND_DIR"
echo "   Frontend: $FRONTEND_DIR"
echo ""

# Verificar directorios
if [ ! -d "$BACKEND_DIR/app" ]; then
    echo "❌ ERROR: No se encontró $BACKEND_DIR/app"
    echo "   Uso: bash $0 <ruta_backend> [ruta_frontend]"
    exit 1
fi

# ─── PASO 1: Servicios Parte 1 (Catalogo APU + Conceptos) ───────────────────
echo ""
echo "▶ PASO 1/5: Instalando servicios (Catálogo APU + Conceptos)..."
bash "$SCRIPT_DIR/01_instalacion_servicios_parte1.sh" "$BACKEND_DIR"

# ─── PASO 2: Servicios Parte 2 (Compliance + Contrato + Licitacion) ─────────
echo ""
echo "▶ PASO 2/5: Instalando servicios (Compliance + Contrato + Licitación)..."
bash "$SCRIPT_DIR/02_instalacion_servicios_parte2.sh" "$BACKEND_DIR"

# ─── PASO 3: Routers Parte 1 (Catálogos) ────────────────────────────────────
echo ""
echo "▶ PASO 3/5: Actualizando routers de catálogos..."
bash "$SCRIPT_DIR/03_actualizar_routers_parte1.sh" "$BACKEND_DIR"

# ─── PASO 4: Routers Parte 2 (Compliance + Contratos + Licitaciones) ──────────
echo ""
echo "▶ PASO 4/5: Actualizando routers restantes..."
bash "$SCRIPT_DIR/04_actualizar_routers_parte2.sh" "$BACKEND_DIR"

# ─── PASO 5: Workflow + Notificaciones ──────────────────────────────────────
echo ""
echo "▶ PASO 5/5: Instalando workflow dinámico + notificaciones..."
bash "$SCRIPT_DIR/05_workflow_notificaciones.sh" "$BACKEND_DIR"

# ─── VERIFICACIÓN FINAL ─────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════════════"
echo "🔍 VERIFICACIÓN FINAL"
echo "═══════════════════════════════════════════════════════════════════════"

# Contar archivos nuevos
SERVICIOS_NUEVOS=$(find "$BACKEND_DIR/app/services" -name "*_service.py" -newer "$SCRIPT_DIR" 2>/dev/null | wc -l)
ROUTERS_ACTUALIZADOS=$(find "$BACKEND_DIR/app/api/v1" -name "*.py" -newer "$SCRIPT_DIR" 2>/dev/null | wc -l)

echo ""
echo "   📦 Servicios nuevos:     $SERVICIOS_NUEVOS"
echo "   📡 Routers actualizados: $ROUTERS_ACTUALIZADOS"
echo ""

# Verificar sintaxis Python
echo "   🔍 Verificando sintaxis Python..."
ERRORES=0
for f in "$BACKEND_DIR/app/services/catalogo_apu_service.py" \
         "$BACKEND_DIR/app/services/catalogo_conceptos_service.py" \
         "$BACKEND_DIR/app/services/compliance_service.py" \
         "$BACKEND_DIR/app/services/contrato_service.py" \
         "$BACKEND_DIR/app/services/licitacion_service.py"; do
    if [ -f "$f" ]; then
        if python3 -m py_compile "$f" 2>/dev/null; then
            echo "      ✅ $(basename $f)"
        else
            echo "      ❌ $(basename $f) — ERROR DE SINTAXIS"
            ERRORES=$((ERRORES + 1))
        fi
    fi
done

for f in "$BACKEND_DIR/app/api/v1/catalogo_apu.py" \
         "$BACKEND_DIR/app/api/v1/catalogo_conceptos.py" \
         "$BACKEND_DIR/app/api/v1/compliance.py" \
         "$BACKEND_DIR/app/api/v1/contratos.py" \
         "$BACKEND_DIR/app/api/v1/licitaciones.py"; do
    if [ -f "$f" ]; then
        if python3 -m py_compile "$f" 2>/dev/null; then
            echo "      ✅ $(basename $f)"
        else
            echo "      ❌ $(basename $f) — ERROR DE SINTAXIS"
            ERRORES=$((ERRORES + 1))
        fi
    fi
done

if [ -f "$BACKEND_DIR/app/modules/workflow/engine.py" ]; then
    if python3 -m py_compile "$BACKEND_DIR/app/modules/workflow/engine.py" 2>/dev/null; then
        echo "      ✅ workflow/engine.py"
    else
        echo "      ❌ workflow/engine.py — ERROR DE SINTAXIS"
        ERRORES=$((ERRORES + 1))
    fi
fi

if [ -f "$BACKEND_DIR/app/modules/notifications/service.py" ]; then
    if python3 -m py_compile "$BACKEND_DIR/app/modules/notifications/service.py" 2>/dev/null; then
        echo "      ✅ notifications/service.py"
    else
        echo "      ❌ notifications/service.py — ERROR DE SINTAXIS"
        ERRORES=$((ERRORES + 1))
    fi
fi

echo ""
if [ $ERRORES -eq 0 ]; then
    echo "╔══════════════════════════════════════════════════════════════════════╗"
    echo "║              ✅ FASE 2 INSTALADA CORRECTAMENTE                       ║"
    echo "╚══════════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "   📊 RESUMEN DE CAMBIOS:"
    echo "   ─────────────────────"
    echo "   • 5 servicios nuevos (APU, Conceptos, Compliance, Contrato, Licitación)"
    echo "   • 5 routers actualizados (29 stubs → código real)"
    echo "   • Workflow dinámico: campo + operador + valor"
    echo "   • Notificaciones: SMTP + SMS (Twilio) + WebSocket + Panel"
    echo "   • Máquina de estados legal: 12 pasos de contratación pública"
    echo "   • Resumen contractual: montos, plazos, garantías, alertas"
    echo "   • Resumen licitación: estadísticas, fallo, proposiciones"
    echo ""
    echo "   🗂️  Backups guardados como: *.backup.original"
    echo ""
    echo "   ▶ Próximo paso: Generar schemas Pydantic faltantes + Tests"
    echo ""
else
    echo "╔══════════════════════════════════════════════════════════════════════╗"
    echo "║              ⚠️  $ERRORES ERRORES DE SINTAXIS DETECTADOS             ║"
    echo "╚══════════════════════════════════════════════════════════════════════╝"
    echo "   Revisa los archivos marcados con ❌"
    exit 1
fi
