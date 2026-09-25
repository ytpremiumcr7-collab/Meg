#!/bin/bash
# =============================================================================
# FASE 2 — Script 6: Frontend conectado — megalodon-client.ts actualizado
# =============================================================================
# Agrega métodos al cliente TypeScript para consumir los nuevos endpoints.
# Hace backup del archivo original antes de modificar.
# =============================================================================

set -euo pipefail

FRONTEND_DIR="${1:-./frontend/app}"
CLIENT_FILE="$FRONTEND_DIR/src/lib/megalodon-client.ts"

echo "🦈 MEGALODON FASE 2 — Script 6: Conectando frontend..."
echo "   Archivo objetivo: $CLIENT_FILE"
echo ""

if [ ! -f "$CLIENT_FILE" ]; then
    echo "❌ No se encontró $CLIENT_FILE"
    exit 1
fi

# Backup
if [ ! -f "${CLIENT_FILE}.backup.original" ]; then
    cp "$CLIENT_FILE" "${CLIENT_FILE}.backup.original"
    echo "   💾 Backup: ${CLIENT_FILE}.backup.original"
fi

# Extraer la parte antes del cierre de la clase
# Vamos a insertar los nuevos métodos antes del último }

# Crear archivo temporal con los nuevos métodos
NEW_METHODS=$(cat << 'METHODEOF'

  // ═══════════════════════════════════════════════════════════════════════
  // FASE 2 — CATÁLOGO APU
  // ═══════════════════════════════════════════════════════════════════════

  catalogoAPU = {
    crear: async (data: any) => {
      return this.request("/api/v1/catalogo-apu", { method: "POST", body: JSON.stringify(data) });
    },
    listar: async (params?: { skip?: number; limit?: number; fuente?: string; zona?: string; tipo?: string; q?: string }) => {
      const query = new URLSearchParams(params as any).toString();
      return this.request(`/api/v1/catalogo-apu?${query}`);
    },
    obtener: async (id: string) => {
      return this.request(`/api/v1/catalogo-apu/${id}`);
    },
    actualizar: async (id: string, data: any) => {
      return this.request(`/api/v1/catalogo-apu/${id}`, { method: "PATCH", body: JSON.stringify(data) });
    },
    eliminar: async (id: string) => {
      return this.request(`/api/v1/catalogo-apu/${id}`, { method: "DELETE" });
    },
    precioConIVA: async (id: string, tasaIVA: number = 0.16) => {
      return this.request(`/api/v1/catalogo-apu/${id}/precio-con-iva?tasa_iva=${tasaIVA}`);
    },
  };

  // ═══════════════════════════════════════════════════════════════════════
  // FASE 2 — CATÁLOGO CONCEPTOS
  // ═══════════════════════════════════════════════════════════════════════

  catalogoConceptos = {
    fuentes: {
      crear: async (data: any) => {
        return this.request("/api/v1/catalogo-conceptos/fuentes", { method: "POST", body: JSON.stringify(data) });
      },
      listar: async (activo?: boolean) => {
        const query = activo !== undefined ? `?activo=${activo}` : "";
        return this.request(`/api/v1/catalogo-conceptos/fuentes${query}`);
      },
    },
    conceptos: {
      crear: async (data: any) => {
        return this.request("/api/v1/catalogo-conceptos/conceptos", { method: "POST", body: JSON.stringify(data) });
      },
      listar: async (params?: { skip?: number; limit?: number; fuente_id?: string; zona?: string; estado?: string; q?: string }) => {
        const query = new URLSearchParams(params as any).toString();
        return this.request(`/api/v1/catalogo-conceptos/conceptos?${query}`);
      },
      obtener: async (id: string) => {
        return this.request(`/api/v1/catalogo-conceptos/conceptos/${id}`);
      },
      actualizar: async (id: string, data: any) => {
        return this.request(`/api/v1/catalogo-conceptos/conceptos/${id}`, { method: "PATCH", body: JSON.stringify(data) });
      },
      costoDesglosado: async (id: string, cantidad: number = 1, tasaIVA: number = 0.16) => {
        return this.request(`/api/v1/catalogo-conceptos/conceptos/${id}/costo-desglosado?cantidad=${cantidad}&tasa_iva=${tasaIVA}`);
      },
    },
    insumos: {
      crear: async (data: any) => {
        return this.request("/api/v1/catalogo-conceptos/insumos", { method: "POST", body: JSON.stringify(data) });
      },
      listar: async (params?: { skip?: number; limit?: number; fuente_id?: string; tipo?: string; categoria?: string }) => {
        const query = new URLSearchParams(params as any).toString();
        return this.request(`/api/v1/catalogo-conceptos/insumos?${query}`);
      },
    },
  };

  // ═══════════════════════════════════════════════════════════════════════
  // FASE 2 — COMPLIANCE
  // ═══════════════════════════════════════════════════════════════════════

  compliance = {
    reglas: {
      crear: async (data: any) => {
        return this.request("/api/v1/compliance/reglas", { method: "POST", body: JSON.stringify(data) });
      },
      listar: async (params?: { tipo_procedimiento?: string; etapa?: string; activa?: boolean; skip?: number; limit?: number }) => {
        const query = new URLSearchParams(params as any).toString();
        return this.request(`/api/v1/compliance/reglas?${query}`);
      },
      obtener: async (id: string) => {
        return this.request(`/api/v1/compliance/reglas/${id}`);
      },
      actualizar: async (id: string, data: any) => {
        return this.request(`/api/v1/compliance/reglas/${id}`, { method: "PATCH", body: JSON.stringify(data) });
      },
      eliminar: async (id: string) => {
        return this.request(`/api/v1/compliance/reglas/${id}`, { method: "DELETE" });
      },
    },
    inconformidades: {
      crear: async (data: any) => {
        return this.request("/api/v1/compliance/inconformidades", { method: "POST", body: JSON.stringify(data) });
      },
      listar: async (params?: { estado?: string; severidad?: string; expediente_id?: string; skip?: number; limit?: number }) => {
        const query = new URLSearchParams(params as any).toString();
        return this.request(`/api/v1/compliance/inconformidades?${query}`);
      },
      obtener: async (id: string) => {
        return this.request(`/api/v1/compliance/inconformidades/${id}`);
      },
      actualizar: async (id: string, data: any) => {
        return this.request(`/api/v1/compliance/inconformidades/${id}`, { method: "PATCH", body: JSON.stringify(data) });
      },
    },
    sanciones: {
      crear: async (data: any) => {
        return this.request("/api/v1/compliance/sanciones", { method: "POST", body: JSON.stringify(data) });
      },
      listar: async (params?: { proveedor_id?: string; tipo?: string; skip?: number; limit?: number }) => {
        const query = new URLSearchParams(params as any).toString();
        return this.request(`/api/v1/compliance/sanciones?${query}`);
      },
      obtener: async (id: string) => {
        return this.request(`/api/v1/compliance/sanciones/${id}`);
      },
    },
    evaluar: async (expedienteId: string) => {
      return this.request(`/api/v1/compliance/evaluar/${expedienteId}`, { method: "POST" });
    },
  };

  // ═══════════════════════════════════════════════════════════════════════
  // FASE 2 — CONTRATOS
  // ═══════════════════════════════════════════════════════════════════════

  contratos = {
    crear: async (data: any) => {
      return this.request("/api/v1/contratos", { method: "POST", body: JSON.stringify(data) });
    },
    listar: async (params?: { estado?: string; expediente_id?: string; proveedor_id?: string; skip?: number; limit?: number }) => {
      const query = new URLSearchParams(params as any).toString();
      return this.request(`/api/v1/contratos?${query}`);
    },
    obtener: async (id: string) => {
      return this.request(`/api/v1/contratos/${id}`);
    },
    actualizar: async (id: string, data: any) => {
      return this.request(`/api/v1/contratos/${id}`, { method: "PATCH", body: JSON.stringify(data) });
    },
    transicionar: async (id: string, nuevoEstado: string) => {
      return this.request(`/api/v1/contratos/${id}/transicionar?nuevo_estado=${nuevoEstado}`, { method: "POST" });
    },
    resumen: async (id: string) => {
      return this.request(`/api/v1/contratos/${id}/resumen`);
    },
    modificatorios: {
      crear: async (contratoId: string, data: any) => {
        return this.request(`/api/v1/contratos/${contratoId}/modificatorios`, { method: "POST", body: JSON.stringify(data) });
      },
      listar: async (contratoId: string) => {
        return this.request(`/api/v1/contratos/${contratoId}/modificatorios`);
      },
    },
    garantias: {
      crear: async (contratoId: string, data: any) => {
        return this.request(`/api/v1/contratos/${contratoId}/garantias`, { method: "POST", body: JSON.stringify(data) });
      },
      listar: async (contratoId: string) => {
        return this.request(`/api/v1/contratos/${contratoId}/garantias`);
      },
      vigencia: async (contratoId: string) => {
        return this.request(`/api/v1/contratos/${contratoId}/garantias/vigencia`);
      },
    },
    entregables: {
      crear: async (contratoId: string, data: any) => {
        return this.request(`/api/v1/contratos/${contratoId}/entregables`, { method: "POST", body: JSON.stringify(data) });
      },
      listar: async (contratoId: string) => {
        return this.request(`/api/v1/contratos/${contratoId}/entregables`);
      },
    },
    penalizaciones: {
      crear: async (contratoId: string, data: any) => {
        return this.request(`/api/v1/contratos/${contratoId}/penalizaciones`, { method: "POST", body: JSON.stringify(data) });
      },
    },
  };

  // ═══════════════════════════════════════════════════════════════════════
  // FASE 2 — LICITACIONES
  // ═══════════════════════════════════════════════════════════════════════

  licitaciones = {
    crear: async (data: any) => {
      return this.request("/api/v1/licitaciones", { method: "POST", body: JSON.stringify(data) });
    },
    listar: async (params?: { estado?: string; tipo_procedimiento?: string; expediente_id?: string; skip?: number; limit?: number }) => {
      const query = new URLSearchParams(params as any).toString();
      return this.request(`/api/v1/licitaciones?${query}`);
    },
    obtener: async (id: string) => {
      return this.request(`/api/v1/licitaciones/${id}`);
    },
    actualizar: async (id: string, data: any) => {
      return this.request(`/api/v1/licitaciones/${id}`, { method: "PATCH", body: JSON.stringify(data) });
    },
    transicionar: async (id: string, data: { nuevo_estado: string }) => {
      return this.request(`/api/v1/licitaciones/${id}/transicionar`, { method: "POST", body: JSON.stringify(data) });
    },
    resumen: async (id: string) => {
      return this.request(`/api/v1/licitaciones/${id}/resumen`);
    },
    juntas: {
      crear: async (licitacionId: string, data: any) => {
        return this.request(`/api/v1/licitaciones/${licitacionId}/junta-aclaraciones`, { method: "POST", body: JSON.stringify(data) });
      },
      listar: async (licitacionId: string) => {
        return this.request(`/api/v1/licitaciones/${licitacionId}/junta-aclaraciones`);
      },
    },
    proposiciones: {
      registrar: async (licitacionId: string, data: any) => {
        return this.request(`/api/v1/licitaciones/${licitacionId}/proposiciones`, { method: "POST", body: JSON.stringify(data) });
      },
      listar: async (licitacionId: string) => {
        return this.request(`/api/v1/licitaciones/${licitacionId}/proposiciones`);
      },
    },
    evaluaciones: {
      crear: async (licitacionId: string, data: any) => {
        return this.request(`/api/v1/licitaciones/${licitacionId}/evaluaciones`, { method: "POST", body: JSON.stringify(data) });
      },
    },
    fallo: {
      emitir: async (licitacionId: string, proposicionGanadoraId: string) => {
        return this.request(`/api/v1/licitaciones/${licitacionId}/fallo?proposicion_ganadora_id=${proposicionGanadoraId}`, { method: "POST" });
      },
    },
  };

METHODEOF
)

# Insertar antes del último } del archivo
# Usar Python para hacer la inserción de forma segura
python3 << PYTHONEOF
import re

with open("$CLIENT_FILE", 'r') as f:
    content = f.read()

# Buscar el último } que cierra la clase
# Insertar los métodos antes del último }
last_brace = content.rfind('}')
if last_brace == -1:
    print("❌ No se encontró el cierre de la clase")
    exit(1)

new_content = content[:last_brace] + """$NEW_METHODS""" + content[last_brace:]

with open("$CLIENT_FILE", 'w') as f:
    f.write(new_content)

print("   ✅ megalodon-client.ts actualizado con 5 módulos nuevos")
PYTHONEOF

echo ""
echo "🦈 Script 6 completado. Frontend conectado."
echo "   Ejecutar: bash scripts_fase2/06_frontend_conectado.sh ./frontend/app"
