/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useState, useEffect } from 'react';
import { Building2, Plus, Trash2, Calculator, Download, HardHat, Upload, Loader2, AlertCircle, FolderKanban, Box, FileWarning, ShieldAlert, CheckCircle2, AlertTriangle, Layers, Search, Link2 } from 'lucide-react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Bounds } from '@react-three/drei';
import { megalodonClient } from '@/lib/api-client';
import { useExpedienteStore } from '@/stores/useExpedienteStore';
import AnimatedNumber from '@/components/AnimatedNumber';
import type { ModeloBIM, ElementoBIM, AnalisisClash, ClashResult, GeneracionBIM4D5D, CatalogoAPUOut, Presupuesto } from '@/lib/megalodon-client';

type ElementType = 'Muro' | 'Columna' | 'Viga' | 'Losa' | 'Cimentacion' | 'Escalera' | 'Ventana' | 'Puerta';
type Material = 'Concreto' | 'Acero' | 'Ladrillo' | 'Madera' | 'Vidrio';

interface BuildingElement {
  id: string;
  type: ElementType;
  length: number;
  width: number;
  height: number;
  quantity: number;
  material: Material;
}

const MATERIAL_DENSITY: Record<Material, number> = {
  Concreto: 2400,
  Acero: 7850,
  Ladrillo: 1900,
  Madera: 600,
  Vidrio: 2500,
};

const MATERIAL_COST: Record<Material, number> = {
  Concreto: 120,
  Acero: 800,
  Ladrillo: 85,
  Madera: 200,
  Vidrio: 300,
};

const ELEMENT_TYPES: ElementType[] = ['Muro', 'Columna', 'Viga', 'Losa', 'Cimentacion', 'Escalera', 'Ventana', 'Puerta'];
const MATERIALS: Material[] = ['Concreto', 'Acero', 'Ladrillo', 'Madera', 'Vidrio'];

function calcVolume(el: BuildingElement): number {
  return el.length * el.width * el.height * el.quantity;
}

function calcArea(el: BuildingElement): number {
  switch (el.type) {
    case 'Muro': return el.length * el.height * el.quantity;
    case 'Losa': return el.length * el.width * el.quantity;
    case 'Ventana':
    case 'Puerta': return el.length * el.height * el.quantity;
    default: return el.length * el.height * el.quantity;
  }
}

function calcWeight(el: BuildingElement): number {
  return calcVolume(el) * MATERIAL_DENSITY[el.material];
}

function calcCost(el: BuildingElement): number {
  return calcVolume(el) * MATERIAL_COST[el.material];
}

/* ------------------------------------------------------------------ */
/*  Modo IFC real -- conectado al motor BIM del backend (ifcopenshell)  */
/* ------------------------------------------------------------------ */

const FUENTE_LABEL: Record<string, string> = {
  QTO_IFC: 'del IFC',
  GEOMETRIA_CALCULADA: 'calculado (aprox.)',
  NO_DISPONIBLE: 'no disponible',
};

// Color por tipo de elemento -- antes todo salía gris plano, imposible
// distinguir muros de losas de columnas de un vistazo.
const COLOR_POR_TIPO: Record<string, string> = {
  IfcWall: '#c9a86c',
  IfcSlab: '#8899aa',
  IfcColumn: '#6c8ec9',
  IfcBeam: '#9e6cc9',
  IfcDoor: '#c96c6c',
  IfcWindow: '#6cc9c3',
  IfcRoof: '#c96c9e',
  IfcStair: '#c9c06c',
  IfcFooting: '#5a5a6e',
  IfcCovering: '#8ec96c',
  IfcRailing: '#c98e6c',
};
const COLOR_DEFAULT = '#8899aa';
const COLOR_SELECCIONADO = '#ffd166';

function ElementoMesh({
  elemento, seleccionado, wireframe, onSelect, enClash = false,
}: {
  elemento: ElementoBIM;
  seleccionado: boolean;
  wireframe: boolean;
  onSelect: (el: ElementoBIM) => void;
  enClash?: boolean;
}) {
  if (!elemento.malla_vertices?.length || !elemento.malla_caras?.length) return null;
  const color = seleccionado
    ? '#ffd166'
    : enClash
      ? '#ef4444'
      : (COLOR_POR_TIPO[elemento.tipo] || COLOR_DEFAULT);
  return (
    <mesh
      onClick={(e) => { e.stopPropagation(); onSelect(elemento); }}
      onPointerOver={(e) => { e.stopPropagation(); document.body.style.cursor = 'pointer'; }}
      onPointerOut={() => { document.body.style.cursor = 'auto'; }}
    >
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[new Float32Array(elemento.malla_vertices), 3]}
        />
        <bufferAttribute
          attach="index"
          args={[new Uint32Array(elemento.malla_caras), 1]}
        />
      </bufferGeometry>
      <meshStandardMaterial
        color={color}
        side={2}
        wireframe={wireframe}
        emissive={seleccionado ? '#ffd166' : enClash ? '#b91c1c' : '#000000'}
        emissiveIntensity={seleccionado ? 0.3 : enClash ? 0.2 : 0}
      />
    </mesh>
  );
}

function IFCPanel() {
  const expedienteActivo = useExpedienteStore((s) => s.expedienteActivo());
  const [modelo, setModelo] = useState<ModeloBIM | null>(null);
  const [elementos, setElementos] = useState<ElementoBIM[]>([]);
  const [procesando, setProcesando] = useState(false);
  const [error, setError] = useState('');
  const [generandoPresupuesto, setGenerandoPresupuesto] = useState(false);
  const [mensajePresupuesto, setMensajePresupuesto] = useState('');

  // Controles del visor -- antes no había filtro de nivel, ni vista 2D,
  // ni selección de elemento individual.
  const [nivelFiltro, setNivelFiltro] = useState<string>('__todos__');
  const [vista, setVista] = useState<'3d' | '2d'>('3d');
  const [wireframe, setWireframe] = useState(false);
  const [seleccionado, setSeleccionado] = useState<ElementoBIM | null>(null);
  // FIX P1 auditoría BIM 2026-09-14 (Caso 2 "mapear-partidas"): el backend
  // ya tenía POST /mapear-partidas y el cliente ya tenía
  // megalodonClient.bim.mapearAPartidas() -- ninguna pantalla lo llamaba.
  // La única forma de conectar BIM->presupuesto era generarPresupuesto()
  // (crea un presupuesto NUEVO agrupando por tipo IFC); no había forma de
  // vincular un elemento puntual a una partida de un presupuesto YA
  // EXISTENTE (ej. el que se armó desde la licitación real) para
  // trazabilidad/verificación. Esto cierra ese hueco para el elemento
  // seleccionado en el visor.
  const [presupuestosDisponibles, setPresupuestosDisponibles] = useState<Presupuesto[]>([]);
  const [presupuestoVinculoId, setPresupuestoVinculoId] = useState('');
  const [partidaVinculoId, setPartidaVinculoId] = useState('');
  const [vinculando, setVinculando] = useState(false);
  const [mensajeVinculo, setMensajeVinculo] = useState('');
  // FIX P1 auditoría BIM 2026-09-14 (Caso 1 "factores económicos"): el
  // backend acepta factor_indirecto/factor_utilidad/factor_impuesto con
  // defaults 15/10/16%, pero ningún flujo de generación de presupuesto
  // desde BIM en esta app dejaba editarlos -- siempre se generaba con el
  // default del backend, sin que el usuario pudiera saber siquiera que
  // existía esa perilla.
  const [factorIndirecto, setFactorIndirecto] = useState(0);
  const [factorUtilidad, setFactorUtilidad] = useState(0);
  const [factorImpuesto, setFactorImpuesto] = useState(0);
  const [referenciaParametros, setReferenciaParametros] = useState('');

  useEffect(() => {
    if (!expedienteActivo) { setPresupuestosDisponibles([]); return; }
    megalodonClient.presupuestos.list(expedienteActivo.id)
      .then(setPresupuestosDisponibles)
      .catch(() => setPresupuestosDisponibles([])); // sin presupuestos todavía -- no es un error que deba bloquear el visor
  }, [expedienteActivo?.id]);

  const partidasDelPresupuestoSeleccionado =
    presupuestosDisponibles.find((p) => p.id === presupuestoVinculoId)?.partidas ?? [];

  const handleVincularPartida = async () => {
    if (!expedienteActivo || !modelo || !seleccionado || !partidaVinculoId) return;
    setVinculando(true);
    setMensajeVinculo('');
    try {
      await megalodonClient.bim.mapearAPartidas(expedienteActivo.id, modelo.id, [
        { elemento_id: seleccionado.id, partida_id: partidaVinculoId },
      ]);
      setElementos((prev) => prev.map((e) => (e.id === seleccionado.id ? { ...e, partida_id: partidaVinculoId } : e)));
      setSeleccionado((prev) => (prev ? { ...prev, partida_id: partidaVinculoId } : prev));
      setMensajeVinculo('Vinculado.');
    } catch (e: any) {
      setMensajeVinculo(e?.message || 'No se pudo vincular el elemento a la partida.');
    } finally {
      setVinculando(false);
    }
  };

  const handleArchivo = async (file: File) => {
    if (!expedienteActivo) return;
    setError('');
    setProcesando(true);
    setModelo(null);
    setElementos([]);
    setSeleccionado(null);
    setNivelFiltro('__todos__');
    try {
      const modeloSubido = await megalodonClient.bim.subirModelo(expedienteActivo.id, file, {
        nombre: file.name.replace(/\.ifc$/i, ''),
        extraerMalla: true,
      });
      setModelo(modeloSubido);

      // El procesamiento del IFC ahora corre en un worker (antes era
      // síncrono en este mismo request) -- hay que esperar a que
      // termine en vez de asumir que ya quedó listo.
      const modeloListo = modeloSubido.estado_procesamiento === 'COMPLETADO'
        ? modeloSubido
        : await megalodonClient.bim.esperarProcesamiento(expedienteActivo.id, modeloSubido.id);
      setModelo(modeloListo);

      if (modeloListo.estado_procesamiento === 'COMPLETADO') {
        // FIX P0 auditoría BIM 2026-09-14: antes se pedía un único
        // limit:500 y se descartaba silenciosamente cualquier elemento
        // más allá de ese -- un IFC con 2,000+ elementos se veía
        // "completo" en el visor sin serlo, y eso también afectaba
        // tiposDelModelo (tipos que solo aparecen después del elemento
        // 500 nunca llegaban a la UI, ni al mapeo 5D). El backend ya
        // soporta limit/offset; ahora se pagina de verdad hasta traer
        // todo el modelo, con un tope de seguridad explícito (avisado,
        // no silencioso) para no colgar el navegador con modelos
        // extremos mientras no exista streaming/virtualización real del
        // visor 3D (ver auditoría: arquitectura de datos BIM pendiente).
        const PAGINA = 500;
        const TOPE_SEGURIDAD = 20000;
        let acumulado: ElementoBIM[] = [];
        let offset = 0;
        while (true) {
          const pagina = await megalodonClient.bim.listarElementos(expedienteActivo.id, modeloListo.id, {
            incluirMalla: true,
            limit: PAGINA,
            offset,
          });
          acumulado = acumulado.concat(pagina);
          if (pagina.length < PAGINA || acumulado.length >= TOPE_SEGURIDAD) break;
          offset += PAGINA;
        }
        setElementos(acumulado);
        if (acumulado.length >= TOPE_SEGURIDAD) {
          setError(`El modelo tiene más de ${TOPE_SEGURIDAD} elementos; se muestran los primeros ${acumulado.length} (visor sin streaming todavía -- ver roadmap BIM).`);
        }
      } else {
        setError(modeloListo.error_procesamiento || 'El modelo no se pudo procesar');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al procesar el IFC');
    } finally {
      setProcesando(false);
    }
  };

  const handleGenerarPresupuesto = async () => {
    if (!expedienteActivo || !modelo) return;
    if (!referenciaParametros.trim()) {
      setMensajePresupuesto('Indica la fuente o referencia de los parámetros de costeo.');
      return;
    }
    setGenerandoPresupuesto(true);
    setMensajePresupuesto('');
    try {
      const presupuesto = await megalodonClient.bim.generarPresupuesto(expedienteActivo.id, modelo.id, {
        nombre: `Presupuesto desde ${modelo.nombre}`,
        parametros_costeo: {
          factor_indirecto: factorIndirecto, factor_utilidad: factorUtilidad,
          factor_impuesto: factorImpuesto, factor_riesgo: 0,
          fuente: 'CAPTURA_USUARIO', referencia: referenciaParametros.trim(),
        },
      });
      setMensajePresupuesto(`Presupuesto ${presupuesto.identificador} creado (solo cantidades -- falta capturar precios unitarios).`);
    } catch (e) {
      setMensajePresupuesto(e instanceof Error ? e.message : 'No se pudo generar el presupuesto');
    } finally {
      setGenerandoPresupuesto(false);
    }
  };

  const [tabDerecho, setTabDerecho] = useState<'resumen' | 'clash' | 'presupuesto5d' | 'cronograma4d'>('resumen');
  const [corriendo, setCorriendo] = useState(false);
  const [analisis, setAnalisis] = useState<AnalisisClash | null>(null);
  const [clashes, setClashes] = useState<ClashResult[]>([]);
  const [errorClash, setErrorClash] = useState('');
  const [toleranciaM, setToleranciaM] = useState(0);
  const [clashesResaltados, setClashesResaltados] = useState<Set<string>>(new Set());

  // --- 5D: mapeo de tipos a catálogo real (precio real, no inventado) ---
  const [busquedaCatalogo, setBusquedaCatalogo] = useState<Record<string, string>>({});
  const [resultadosCatalogo, setResultadosCatalogo] = useState<Record<string, CatalogoAPUOut[]>>({});
  const [buscandoCatalogo, setBuscandoCatalogo] = useState<string | null>(null);
  const [mapeoCatalogo, setMapeoCatalogo] = useState<Record<string, CatalogoAPUOut>>({});
  const [generandoPresupuestoReal, setGenerandoPresupuestoReal] = useState(false);
  const [mensajePresupuestoReal, setMensajePresupuestoReal] = useState('');

  // --- 4D: zonas de trabajo y generación de cronograma ---
  const [zonaInput, setZonaInput] = useState('');
  const [asignandoZona, setAsignandoZona] = useState(false);
  const [mensajeZona, setMensajeZona] = useState('');
  const [fechaInicio4D, setFechaInicio4D] = useState('');
  const [diasPorDefecto4D, setDiasPorDefecto4D] = useState(5);
  const [generando4D, setGenerando4D] = useState(false);
  const [generacion4D, setGeneracion4D] = useState<GeneracionBIM4D5D | null>(null);
  const [error4D, setError4D] = useState('');

  const handleCorrerClash = async () => {
    if (!expedienteActivo || !modelo) return;
    setCorriendo(true);
    setErrorClash('');
    setAnalisis(null);
    setClashes([]);
    try {
      const a = await megalodonClient.bim.correrClashDetection(
        expedienteActivo.id, modelo.id,
        { toleranciaM }
      );
      setAnalisis(a);
      if (a.num_clashes_duros + a.num_clashes_blandos > 0) {
        const rs = await megalodonClient.bim.listarResultadosClash(
          expedienteActivo.id, modelo.id, a.id, { limit: 200 }
        );
        setClashes(rs);
        // Resaltar en el visor los elementos con clash
        const ids = new Set<string>();
        rs.forEach(r => { ids.add(r.elemento_a_id); ids.add(r.elemento_b_id); });
        setClashesResaltados(ids);
      }
    } catch (e) {
      setErrorClash(e instanceof Error ? e.message : 'Error al correr clash detection');
    } finally {
      setCorriendo(false);
    }
  };

  const handleMarcarEstado = async (resultadoId: string, estado: 'REVISADO' | 'RESUELTO' | 'IGNORADO') => {
    if (!expedienteActivo) return;
    try {
      const actualizado = await megalodonClient.bim.actualizarEstadoClash(
        expedienteActivo.id, resultadoId, estado
      );
      setClashes(prev => prev.map(c => c.id === resultadoId ? actualizado : c));
    } catch { /* silencioso */ }
  };

  // --- 5D: buscar en el catálogo real y mapear un tipo a un concepto ---
  const handleBuscarCatalogo = async (tipo: string) => {
    const q = busquedaCatalogo[tipo]?.trim();
    if (!q) return;
    setBuscandoCatalogo(tipo);
    try {
      const { items } = await megalodonClient.catalogoApu.listar({ q, limit: 8 });
      setResultadosCatalogo((prev) => ({ ...prev, [tipo]: items }));
    } catch {
      setResultadosCatalogo((prev) => ({ ...prev, [tipo]: [] }));
    } finally {
      setBuscandoCatalogo(null);
    }
  };

  const handleGenerarPresupuestoReal = async () => {
    if (!expedienteActivo || !modelo) return;
    if (!referenciaParametros.trim()) {
      setMensajePresupuestoReal('Indica la fuente o referencia de los parámetros de costeo.');
      return;
    }
    setGenerandoPresupuestoReal(true);
    setMensajePresupuestoReal('');
    try {
      const mapeoPayload: Record<string, string> = {};
      for (const [tipo, concepto] of Object.entries(mapeoCatalogo)) mapeoPayload[tipo] = concepto.id;

      const presupuesto = await megalodonClient.bim.generarPresupuesto(expedienteActivo.id, modelo.id, {
        nombre: `Presupuesto desde ${modelo.nombre}`,
        mapeo_catalogo: Object.keys(mapeoPayload).length > 0 ? mapeoPayload : undefined,
        parametros_costeo: {
          factor_indirecto: factorIndirecto, factor_utilidad: factorUtilidad,
          factor_impuesto: factorImpuesto, factor_riesgo: 0,
          fuente: 'CAPTURA_USUARIO', referencia: referenciaParametros.trim(),
        },
      });
      const numMapeados = Object.keys(mapeoPayload).length;
      setMensajePresupuestoReal(
        numMapeados > 0
          ? `Presupuesto ${presupuesto.identificador} creado -- ${numMapeados} tipo(s) con precio real del catálogo, el resto solo cantidades.`
          : `Presupuesto ${presupuesto.identificador} creado (solo cantidades -- mapea al menos un tipo a catálogo para precio real).`
      );
    } catch (e) {
      setMensajePresupuestoReal(e instanceof Error ? e.message : 'No se pudo generar el presupuesto');
    } finally {
      setGenerandoPresupuestoReal(false);
    }
  };

  // --- 4D: asignar zona de trabajo a los elementos del nivel filtrado ---
  const handleAsignarZona = async () => {
    if (!expedienteActivo || !modelo || !zonaInput.trim()) return;
    setAsignandoZona(true);
    setMensajeZona('');
    try {
      const objetivo = nivelFiltro === '__todos__' ? elementos : elementos.filter((el) => (el.nivel || 'Sin nivel') === nivelFiltro);
      const asignaciones = objetivo.map((el) => ({ elemento_id: el.id, zona_4d: zonaInput.trim() }));
      const { elementos_actualizados } = await megalodonClient.bim.asignarZonas4d(expedienteActivo.id, modelo.id, asignaciones);
      setElementos((prev) => prev.map((el) => (objetivo.some((o) => o.id === el.id) ? { ...el, zona_4d: zonaInput.trim() } : el)));
      setMensajeZona(`Zona "${zonaInput.trim()}" asignada a ${elementos_actualizados} elemento(s).`);
    } catch (e) {
      setMensajeZona(e instanceof Error ? e.message : 'No se pudo asignar la zona');
    } finally {
      setAsignandoZona(false);
    }
  };

  const handleGenerar4D = async () => {
    if (!expedienteActivo || !modelo || !fechaInicio4D) return;
    setGenerando4D(true);
    setError4D('');
    setGeneracion4D(null);
    try {
      const gen = await megalodonClient.bim.generar4D5D(expedienteActivo.id, modelo.id, {
        fecha_inicio: new Date(fechaInicio4D).toISOString(),
        dias_por_defecto: diasPorDefecto4D,
      });
      setGeneracion4D(gen);
      const final = await megalodonClient.bim.esperarGeneracion4D5D(expedienteActivo.id, gen.id);
      setGeneracion4D(final);
      if (final.estado === 'ERROR') setError4D(final.error || 'La generación 4D falló');
    } catch (e) {
      setError4D(e instanceof Error ? e.message : 'No se pudo generar el cronograma 4D');
    } finally {
      setGenerando4D(false);
    }
  };

  if (!expedienteActivo) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center px-6" style={{ color: 'var(--text-muted)' }}>
        <FolderKanban size={32} style={{ opacity: 0.5 }} />
        <p className="text-sm">No hay ningún expediente activo.</p>
        <p className="text-xs">Abre la app &quot;Proyectos&quot; y selecciona o crea un expediente antes de subir un IFC.</p>
      </div>
    );
  }

  // Filtro por nivel: se filtra en el cliente sobre lo ya descargado
  // (incluida la malla) en vez de volver a pedir al backend -- la malla
  // ya pesa, no tiene caso re-descargarla cada vez que cambias de piso.
  const elementosVisibles = nivelFiltro === '__todos__'
    ? elementos
    : elementos.filter((el) => (el.nivel || 'Sin nivel') === nivelFiltro);

  const resumenPorTipo = elementosVisibles.reduce<Record<string, { cantidad: number; volumen: number; area: number }>>((acc, el) => {
    const r = acc[el.tipo] || { cantidad: 0, volumen: 0, area: 0 };
    r.cantidad += 1;
    r.volumen += el.volumen || 0;
    r.area += el.area || 0;
    acc[el.tipo] = r;
    return acc;
  }, {});

  // 5D: mapeo de tipo→catálogo aplica al MODELO completo (así agrupa
  // crear_presupuesto_desde_bim), no solo al nivel filtrado en el visor.
  const tiposDelModelo = Array.from(new Set(elementos.map((el) => el.tipo))).sort();

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 gap-2" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
          <FolderKanban size={12} style={{ color: 'var(--accent-gold)' }} />
          Expediente activo: <span style={{ color: 'var(--text-primary)' }}>{expedienteActivo.titulo}</span>
        </div>
        <label className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium cursor-pointer transition-colors"
          style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}>
          {procesando ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
          {procesando ? 'Procesando...' : 'Subir IFC'}
          <input
            type="file"
            accept=".ifc"
            className="hidden"
            disabled={procesando}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleArchivo(f); }}
          />
        </label>
      </div>

      {error && (
        <div className="flex items-center gap-2 px-3 py-2 text-xs" style={{ color: 'var(--danger)' }}>
          <AlertCircle size={14} /> {error}
        </div>
      )}

      {!modelo && !procesando && !error && (
        <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center px-6" style={{ color: 'var(--text-muted)' }}>
          <Box size={32} style={{ opacity: 0.5 }} />
          <p className="text-sm">Sube un archivo .ifc para cuantificar y ver el modelo en 3D.</p>
        </div>
      )}

      {modelo && elementos.length > 0 && (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Barra de controles del visor */}
          <div className="flex items-center gap-2 px-3 py-1.5 flex-wrap" style={{ borderBottom: '1px solid var(--border-subtle)', background: 'var(--surface)' }}>
            {modelo.niveles && modelo.niveles.length > 0 && (
              <select
                value={nivelFiltro}
                onChange={(e) => { setNivelFiltro(e.target.value); setSeleccionado(null); }}
                className="text-[11px] rounded px-2 py-1"
                style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
              >
                <option value="__todos__">Todos los niveles</option>
                {modelo.niveles.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            )}

            <div className="flex rounded-md overflow-hidden" style={{ border: '1px solid var(--border-subtle)' }}>
              {(['3d', '2d'] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setVista(v)}
                  className="px-2 py-1 text-[11px] font-medium transition-colors"
                  style={{
                    background: vista === v ? 'var(--accent-gold)' : 'transparent',
                    color: vista === v ? 'var(--void)' : 'var(--text-secondary)',
                  }}
                >
                  {v === '3d' ? 'Vista 3D' : 'Planta (2D)'}
                </button>
              ))}
            </div>

            <button
              onClick={() => setWireframe(!wireframe)}
              className="flex items-center gap-1 px-2 py-1 rounded text-[11px] transition-colors"
              style={{
                background: wireframe ? 'var(--accent-gold)' : 'var(--surface-elevated)',
                color: wireframe ? 'var(--void)' : 'var(--text-secondary)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              Alambre
            </button>

            <span className="text-[10px] ml-auto" style={{ color: 'var(--text-muted)' }}>
              {elementosVisibles.length} de {elementos.length} elementos
            </span>
          </div>

          <div className="flex-1 flex overflow-hidden">
            <div className="w-1/2 h-full relative" style={{ background: '#05050a' }}>
              {/* key={vista} fuerza remount de Canvas al cambiar de
                  proyección -- cambiar de perspectiva a ortográfica en la
                  misma cámara da resultados raros con Bounds/fit. */}
              <Canvas key={vista} orthographic={vista === '2d'} camera={vista === '2d' ? { position: [0, 100, 0], zoom: 8 } : { position: [10, 10, 10], fov: 50 }}>
                <ambientLight intensity={0.7} />
                <directionalLight position={[10, 15, 10]} intensity={0.8} />
                <Bounds fit clip observe margin={1.3}>
                  {elementosVisibles.map((el) => (
                    <ElementoMesh
                      key={el.id}
                      elemento={el}
                      seleccionado={seleccionado?.id === el.id}
                      wireframe={wireframe}
                      onSelect={setSeleccionado}
                      enClash={clashesResaltados.has(el.id)}
                    />
                  ))}
                </Bounds>
                <OrbitControls enableRotate={vista === '3d'} />
                {vista === '3d' && <gridHelper args={[50, 50]} />}
              </Canvas>

              {seleccionado && (
                <div className="absolute bottom-2 left-2 right-2 rounded-md p-2 text-[11px]"
                  style={{ background: 'rgba(10,10,15,0.9)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' }}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold">{seleccionado.nombre || seleccionado.tipo}</span>
                    <button onClick={() => setSeleccionado(null)} style={{ color: 'var(--text-muted)' }}>✕</button>
                  </div>
                  <div style={{ color: 'var(--text-muted)' }}>
                    {seleccionado.tipo}{seleccionado.nivel ? ` · ${seleccionado.nivel}` : ''}
                  </div>
                  <div className="flex gap-3 mt-1">
                    {seleccionado.volumen != null && <span>Vol: {seleccionado.volumen.toFixed(3)} m³</span>}
                    {seleccionado.area != null && <span>Área: {seleccionado.area.toFixed(2)} m²</span>}
                  </div>
                  <div className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>
                    Volumen {FUENTE_LABEL[seleccionado.fuente_volumen]} · Área {FUENTE_LABEL[seleccionado.fuente_area]}
                  </div>
                  {/* FIX P1 auditoría BIM 2026-09-14 (mapear-partidas): antes
                      no había ninguna forma de vincular este elemento a una
                      partida de un presupuesto ya existente -- solo se podía
                      generar un presupuesto nuevo agrupado por tipo IFC. */}
                  <div className="mt-2 pt-2" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                    {seleccionado.partida_id ? (
                      <div className="flex items-center gap-1" style={{ color: 'var(--success, #4ade80)' }}>
                        <Link2 size={10} /> Vinculado a una partida
                      </div>
                    ) : presupuestosDisponibles.length === 0 ? (
                      <div style={{ color: 'var(--text-muted)' }}>Sin presupuestos en este expediente todavía.</div>
                    ) : (
                      <div className="flex flex-col gap-1">
                        <select
                          value={presupuestoVinculoId}
                          onChange={(e) => { setPresupuestoVinculoId(e.target.value); setPartidaVinculoId(''); }}
                          className="rounded px-1 py-0.5 text-[10px]"
                          style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                        >
                          <option value="">Presupuesto...</option>
                          {presupuestosDisponibles.map((p) => (
                            <option key={p.id} value={p.id}>{p.identificador} · {p.nombre}</option>
                          ))}
                        </select>
                        {presupuestoVinculoId && (
                          <div className="flex gap-1">
                            <select
                              value={partidaVinculoId}
                              onChange={(e) => setPartidaVinculoId(e.target.value)}
                              className="flex-1 rounded px-1 py-0.5 text-[10px]"
                              style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                            >
                              <option value="">Partida...</option>
                              {partidasDelPresupuestoSeleccionado.map((partida) => (
                                <option key={partida.id} value={partida.id}>{partida.numero} · {partida.descripcion}</option>
                              ))}
                            </select>
                            <button
                              onClick={handleVincularPartida}
                              disabled={!partidaVinculoId || vinculando}
                              className="px-2 py-0.5 rounded text-[10px] font-medium"
                              style={{ background: 'var(--accent-gold)', color: '#000' }}
                            >
                              {vinculando ? <Loader2 size={10} className="animate-spin" /> : 'Vincular'}
                            </button>
                          </div>
                        )}
                        {mensajeVinculo && <div style={{ color: 'var(--text-muted)' }}>{mensajeVinculo}</div>}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            <div className="w-1/2 h-full flex flex-col overflow-hidden">
              {/* Tabs panel derecho */}
              <div className="flex shrink-0" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                {(['resumen', 'clash', 'presupuesto5d', 'cronograma4d'] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTabDerecho(t)}
                    className="flex items-center gap-1 px-3 py-2 text-[11px] font-medium transition-colors"
                    style={{
                      borderBottom: tabDerecho === t ? '2px solid var(--accent-gold)' : '2px solid transparent',
                      color: tabDerecho === t ? 'var(--text-primary)' : 'var(--text-muted)',
                    }}
                  >
                    {t === 'resumen' && <><Calculator size={11} /> Resumen</>}
                    {t === 'clash' && <><ShieldAlert size={11} /> Clash {analisis && analisis.num_clashes_duros + analisis.num_clashes_blandos > 0 && <span className="ml-1 px-1 rounded text-[9px]" style={{ background: 'var(--danger)', color: '#fff' }}>{analisis.num_clashes_duros + analisis.num_clashes_blandos}</span>}</>}
                    {t === 'presupuesto5d' && <><Link2 size={11} /> 5D</>}
                    {t === 'cronograma4d' && <><Layers size={11} /> 4D</>}
                  </button>
                ))}
              </div>

              {/* Tab Resumen */}
              {tabDerecho === 'resumen' && (
                <div className="flex-1 overflow-y-auto p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {elementosVisibles.length} elementos
                    </span>
                    <button
                      onClick={handleGenerarPresupuesto}
                      disabled={generandoPresupuesto || !referenciaParametros.trim()}
                      className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors"
                      style={{ background: 'var(--surface-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
                    >
                      {generandoPresupuesto ? <Loader2 size={11} className="animate-spin" /> : <Calculator size={11} />}
                      Generar presupuesto
                    </button>
                  </div>
                  <div className="grid grid-cols-4 gap-1.5 mb-2 text-[10px]" style={{ color: 'var(--text-muted)' }}>
                    {[
                      ['Indirectos %', factorIndirecto, setFactorIndirecto],
                      ['Utilidad %', factorUtilidad, setFactorUtilidad],
                      ['Impuesto %', factorImpuesto, setFactorImpuesto],
                    ].map(([label, value, setter]) => (
                      <label key={String(label)}>{String(label)}
                        <input type="number" min={0} max={100} step={0.01} value={Number(value) * 100}
                          onChange={(e) => (setter as (n: number) => void)(Number(e.target.value) / 100)}
                          className="w-full rounded px-1.5 py-1"
                          style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }} />
                      </label>
                    ))}
                    <label>Fuente / referencia
                      <input value={referenciaParametros} onChange={(e) => setReferenciaParametros(e.target.value)}
                        placeholder="Contrato o análisis" className="w-full rounded px-1.5 py-1"
                        style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }} />
                    </label>
                  </div>
                  {mensajePresupuesto && (
                    <p className="text-[11px] mb-2" style={{ color: 'var(--text-muted)' }}>{mensajePresupuesto}</p>
                  )}
                  {(Object.entries(resumenPorTipo) as [string, { cantidad: number; volumen: number; area: number }][]).map(([tipo, r]) => (
                    <div
                      key={tipo}
                      className="flex items-center justify-between px-2 py-1.5 rounded text-[11px] mb-1"
                      style={{ background: 'var(--surface)' }}
                    >
                      <span className="flex items-center gap-1.5" style={{ color: 'var(--text-primary)' }}>
                        <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: COLOR_POR_TIPO[tipo] || COLOR_DEFAULT }} />
                        {tipo}
                      </span>
                      <span className="font-mono" style={{ color: 'var(--text-muted)' }}>
                        {r.cantidad} pz · {r.volumen.toFixed(2)} m³
                      </span>
                    </div>
                  ))}
                  <div className="mt-3 flex items-start gap-1.5 text-[10px]" style={{ color: 'var(--text-muted)' }}>
                    <FileWarning size={12} className="shrink-0 mt-0.5" />
                    <span>Cantidades &quot;calculadas&quot; vienen de geometría -- revísalas antes de usarlas.</span>
                  </div>
                </div>
              )}

              {/* Tab Clash Detection */}
              {tabDerecho === 'clash' && (
                <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
                  {/* Controles */}
                  <div className="flex items-center gap-2">
                    <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Tolerancia (m):</label>
                    <input
                      type="number"
                      value={toleranciaM}
                      onChange={(e) => setToleranciaM(Number(e.target.value))}
                      min={0} step={0.01}
                      className="w-16 text-[11px] px-1.5 py-0.5 rounded font-mono"
                      style={{ background: 'var(--surface)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                    />
                    <button
                      onClick={handleCorrerClash}
                      disabled={corriendo || !modelo}
                      className="flex items-center gap-1.5 px-3 py-1 rounded-md text-[11px] font-medium ml-auto transition-colors"
                      style={{ background: 'var(--accent-gold)', color: 'var(--void)', opacity: corriendo || !modelo ? 0.6 : 1 }}
                    >
                      {corriendo ? <Loader2 size={11} className="animate-spin" /> : <ShieldAlert size={11} />}
                      {corriendo ? 'Analizando...' : 'Detectar clashes'}
                    </button>
                  </div>
                  <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                    0 = solo traslape real (DURO). &gt;0 = también marca pares a menos de esa distancia sin tocarse (BLANDO — clearance MEP).
                  </p>

                  {errorClash && (
                    <div className="flex items-center gap-1.5 text-[11px] px-2 py-1.5 rounded" style={{ background: 'rgba(239,68,68,0.1)', color: 'var(--danger)' }}>
                      <AlertCircle size={12} /> {errorClash}
                    </div>
                  )}

                  {analisis && (
                    <div className="flex gap-2 text-[11px]">
                      <div className="flex-1 rounded px-2 py-1.5 text-center" style={{ background: 'rgba(239,68,68,0.1)' }}>
                        <div className="font-bold text-base" style={{ color: '#ef4444' }}>{analisis.num_clashes_duros}</div>
                        <div style={{ color: 'var(--text-muted)' }}>DURO</div>
                      </div>
                      <div className="flex-1 rounded px-2 py-1.5 text-center" style={{ background: 'rgba(245,158,11,0.1)' }}>
                        <div className="font-bold text-base" style={{ color: '#f59e0b' }}>{analisis.num_clashes_blandos}</div>
                        <div style={{ color: 'var(--text-muted)' }}>BLANDO</div>
                      </div>
                      <div className="flex-1 rounded px-2 py-1.5 text-center" style={{ background: 'var(--surface)' }}>
                        <div className="font-bold text-base" style={{ color: 'var(--text-primary)' }}>{analisis.tiempo_calculo_ms ?? '—'}ms</div>
                        <div style={{ color: 'var(--text-muted)' }}>Tiempo</div>
                      </div>
                    </div>
                  )}

                  {/* Lista de clashes */}
                  {clashes.length === 0 && analisis && (
                    <div className="flex items-center gap-2 text-[11px] mt-2" style={{ color: 'var(--success)' }}>
                      <CheckCircle2 size={14} /> Sin conflictos detectados con esta tolerancia.
                    </div>
                  )}

                  {clashes.map((c) => (
                    <div key={c.id} className="rounded-md p-2 text-[11px]" style={{
                      background: c.estado === 'RESUELTO' || c.estado === 'IGNORADO'
                        ? 'var(--surface)'
                        : c.severidad === 'DURO'
                          ? 'rgba(239,68,68,0.07)'
                          : 'rgba(245,158,11,0.07)',
                      border: '1px solid var(--border-subtle)',
                      opacity: c.estado === 'RESUELTO' || c.estado === 'IGNORADO' ? 0.5 : 1,
                    }}>
                      <div className="flex items-center justify-between gap-1 mb-1">
                        <div className="flex items-center gap-1.5">
                          {c.severidad === 'DURO'
                            ? <AlertCircle size={12} style={{ color: '#ef4444' }} />
                            : <AlertTriangle size={12} style={{ color: '#f59e0b' }} />}
                          <span className="font-medium" style={{ color: c.severidad === 'DURO' ? '#ef4444' : '#f59e0b' }}>
                            {c.severidad}
                          </span>
                          <span style={{ color: 'var(--text-muted)' }}>·</span>
                          <span style={{ color: 'var(--text-secondary)' }}>{c.tipo_a}</span>
                          <span style={{ color: 'var(--text-muted)' }}>vs</span>
                          <span style={{ color: 'var(--text-secondary)' }}>{c.tipo_b}</span>
                        </div>
                        <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
                          {c.distancia_m === 0 ? 'traslape' : `${c.distancia_m.toFixed(3)}m`}
                        </span>
                      </div>
                      {c.volumen_aproximado_m3 != null && c.volumen_aproximado_m3 > 0 && (
                        <div className="text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>
                          Vol. aprox.: {c.volumen_aproximado_m3.toFixed(4)} m³
                        </div>
                      )}
                      <div className="flex gap-1 mt-1.5">
                        {(['REVISADO', 'RESUELTO', 'IGNORADO'] as const).map((est) => (
                          <button
                            key={est}
                            onClick={() => handleMarcarEstado(c.id, est)}
                            className="px-1.5 py-0.5 rounded text-[9px] transition-colors"
                            style={{
                              background: c.estado === est ? 'var(--accent-gold)' : 'var(--surface-elevated)',
                              color: c.estado === est ? 'var(--void)' : 'var(--text-muted)',
                              border: '1px solid var(--border-subtle)',
                            }}
                          >
                            {est}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {/* Tab 5D: mapeo de tipos a catálogo real */}
              {tabDerecho === 'presupuesto5d' && (
                <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
                  <div className="flex items-start gap-1.5 text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>
                    <Link2 size={12} className="shrink-0 mt-0.5" />
                    <span>Vincula cada tipo a un concepto real del catálogo (precio de verdad) antes de generar el presupuesto. Los tipos sin vincular quedan solo con cantidades, como antes.</span>
                  </div>
                  {tiposDelModelo.length === 0 && (
                    <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Sube un modelo para ver sus tipos de elemento aquí.</p>
                  )}
                  {tiposDelModelo.map((tipo) => {
                    const seleccionado = mapeoCatalogo[tipo];
                    return (
                      <div key={tipo} className="p-2 rounded" style={{ background: 'var(--surface)', border: '1px solid var(--border-subtle)' }}>
                        <div className="flex items-center gap-1.5 mb-1.5">
                          <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: COLOR_POR_TIPO[tipo] || COLOR_DEFAULT }} />
                          <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>{tipo}</span>
                        </div>
                        {seleccionado ? (
                          <div className="flex items-center justify-between text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                            <span>{seleccionado.descripcion} · {seleccionado.unidad} · ${seleccionado.precio_unitario.toFixed(2)}</span>
                            <button
                              onClick={() => setMapeoCatalogo((prev) => { const next = { ...prev }; delete next[tipo]; return next; })}
                              className="text-[10px] shrink-0 ml-2"
                              style={{ color: 'var(--danger)' }}
                            >
                              Quitar
                            </button>
                          </div>
                        ) : (
                          <>
                            <div className="flex gap-1">
                              <input
                                value={busquedaCatalogo[tipo] || ''}
                                onChange={(e) => setBusquedaCatalogo((prev) => ({ ...prev, [tipo]: e.target.value }))}
                                onKeyDown={(e) => { if (e.key === 'Enter') handleBuscarCatalogo(tipo); }}
                                placeholder="Buscar en catálogo (ej. muro, concreto)..."
                                className="flex-1 px-1.5 py-1 rounded text-[10px]"
                                style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                              />
                              <button
                                onClick={() => handleBuscarCatalogo(tipo)}
                                disabled={buscandoCatalogo === tipo}
                                className="px-2 rounded"
                                style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}
                              >
                                {buscandoCatalogo === tipo ? <Loader2 size={11} className="animate-spin" /> : <Search size={11} />}
                              </button>
                            </div>
                            {(resultadosCatalogo[tipo] || []).length > 0 && (
                              <div className="mt-1 flex flex-col gap-0.5">
                                {resultadosCatalogo[tipo].map((c) => (
                                  <button
                                    key={c.id}
                                    onClick={() => setMapeoCatalogo((prev) => ({ ...prev, [tipo]: c }))}
                                    className="text-left px-1.5 py-1 rounded text-[10px] transition-colors"
                                    style={{ background: 'var(--surface-elevated)', color: 'var(--text-secondary)' }}
                                  >
                                    {c.descripcion} · {c.unidad} · ${c.precio_unitario.toFixed(2)} ({c.fuente})
                                  </button>
                                ))}
                              </div>
                            )}
                            {buscandoCatalogo !== tipo && busquedaCatalogo[tipo] && (resultadosCatalogo[tipo]?.length === 0) && (
                              <p className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>Sin resultados.</p>
                            )}
                          </>
                        )}
                      </div>
                    );
                  })}
                  <div className="flex items-center gap-2 mt-1 text-[10px]" style={{ color: 'var(--text-muted)' }}>
                    <label className="flex items-center gap-1">Indirectos
                      <input type="number" step={1} min={0} max={100} value={Math.round(factorIndirecto * 100)}
                        onChange={(e) => setFactorIndirecto(Number(e.target.value) / 100)}
                        className="w-12 rounded px-1 py-0.5" style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }} />%
                    </label>
                    <label className="flex items-center gap-1">Utilidad
                      <input type="number" step={1} min={0} max={100} value={Math.round(factorUtilidad * 100)}
                        onChange={(e) => setFactorUtilidad(Number(e.target.value) / 100)}
                        className="w-12 rounded px-1 py-0.5" style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }} />%
                    </label>
                    <label className="flex items-center gap-1">Impuesto
                      <input type="number" step={1} min={0} max={100} value={Math.round(factorImpuesto * 100)}
                        onChange={(e) => setFactorImpuesto(Number(e.target.value) / 100)}
                        className="w-12 rounded px-1 py-0.5" style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }} />%
                    </label>
                  </div>
                  <input
                    value={referenciaParametros}
                    onChange={(e) => setReferenciaParametros(e.target.value)}
                    placeholder="Fuente: contrato, convocatoria o análisis"
                    className="w-full rounded px-2 py-1 text-[10px]"
                    style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                  />
                  <button
                    onClick={handleGenerarPresupuestoReal}
                    disabled={generandoPresupuestoReal || tiposDelModelo.length === 0 || !referenciaParametros.trim()}
                    className="flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-medium mt-1"
                    style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
                  >
                    {generandoPresupuestoReal ? <Loader2 size={11} className="animate-spin" /> : <Calculator size={11} />}
                    Generar presupuesto
                  </button>
                  {mensajePresupuestoReal && <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{mensajePresupuestoReal}</p>}
                </div>
              )}

              {/* Tab 4D: zonas de trabajo y generación de cronograma */}
              {tabDerecho === 'cronograma4d' && (
                <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-3">
                  <div>
                    <div className="flex items-start gap-1.5 text-[10px] mb-2" style={{ color: 'var(--text-muted)' }}>
                      <Layers size={12} className="shrink-0 mt-0.5" />
                      <span>1. Asigna una zona de trabajo a los elementos del nivel filtrado arriba ({nivelFiltro === '__todos__' ? 'todos los niveles' : nivelFiltro}). Sin zona, se agrupa por nivel del IFC.</span>
                    </div>
                    <div className="flex gap-1">
                      <input
                        value={zonaInput}
                        onChange={(e) => setZonaInput(e.target.value)}
                        placeholder="ej. Torre A - Frente 1"
                        className="flex-1 px-1.5 py-1 rounded text-[10px]"
                        style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                      />
                      <button
                        onClick={handleAsignarZona}
                        disabled={asignandoZona || !zonaInput.trim()}
                        className="px-2 rounded text-[10px]"
                        style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}
                      >
                        {asignandoZona ? <Loader2 size={11} className="animate-spin" /> : 'Asignar'}
                      </button>
                    </div>
                    {mensajeZona && <p className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>{mensajeZona}</p>}
                  </div>

                  <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '0.5rem' }}>
                    <div className="text-[10px] mb-2" style={{ color: 'var(--text-muted)' }}>
                      2. Genera el cronograma: una actividad por zona×tipo, sin secuencia todavía -- eso se ajusta después en Programación, con criterio del programador, no se inventa.
                    </div>
                    <div className="flex gap-1 mb-1.5">
                      <input
                        type="date"
                        value={fechaInicio4D}
                        onChange={(e) => setFechaInicio4D(e.target.value)}
                        className="flex-1 px-1.5 py-1 rounded text-[10px]"
                        style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                      />
                      <input
                        type="number"
                        min={1}
                        value={diasPorDefecto4D}
                        onChange={(e) => setDiasPorDefecto4D(Number(e.target.value) || 1)}
                        title="Duración inicial sugerida; valide calendario, productividad y recursos antes de aprobar el programa"
                        className="w-16 px-1.5 py-1 rounded text-[10px]"
                        style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                      />
                    </div>
                    <button
                      onClick={handleGenerar4D}
                      disabled={generando4D || !fechaInicio4D}
                      className="w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-medium"
                      style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
                    >
                      {generando4D ? <Loader2 size={11} className="animate-spin" /> : <Layers size={11} />}
                      Generar cronograma 4D
                    </button>
                    {generacion4D && generacion4D.estado !== 'ERROR' && generacion4D.estado !== 'COMPLETADO' && (
                      <p className="text-[10px] mt-1.5 flex items-center gap-1" style={{ color: 'var(--text-muted)' }}>
                        <Loader2 size={10} className="animate-spin" /> Generando (agrupando por {generacion4D.agrupar_por})...
                      </p>
                    )}
                    {generacion4D?.estado === 'COMPLETADO' && (
                      <p className="text-[10px] mt-1.5" style={{ color: 'var(--text-secondary)' }}>
                        Listo: {generacion4D.num_actividades_generadas} actividad(es) creadas (agrupado por {generacion4D.agrupar_por}). Ábrelas en Programación para secuenciarlas y calcular la ruta crítica.
                      </p>
                    )}
                    {error4D && (
                      <p className="text-[10px] mt-1.5 flex items-center gap-1" style={{ color: 'var(--danger)' }}>
                        <AlertCircle size={10} /> {error4D}
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function BIMCalculator() {
  const [modo, setModo] = useState<'manual' | 'ifc'>('manual');
  const [elements, setElements] = useState<BuildingElement[]>([
    { id: '1', type: 'Muro', length: 10, width: 0.2, height: 3, quantity: 4, material: 'Ladrillo' },
    { id: '2', type: 'Columna', length: 0.4, width: 0.4, height: 3, quantity: 8, material: 'Concreto' },
    { id: '3', type: 'Losa', length: 10, width: 8, height: 0.15, quantity: 1, material: 'Concreto' },
    { id: '4', type: 'Cimentacion', length: 10, width: 0.6, height: 0.5, quantity: 4, material: 'Concreto' },
    { id: '5', type: 'Ventana', length: 1.5, width: 0.1, height: 1.2, quantity: 6, material: 'Vidrio' },
    { id: '6', type: 'Puerta', length: 0.9, width: 0.05, height: 2.1, quantity: 3, material: 'Madera' },
  ]);

  const addElement = () => {
    const id = Date.now().toString();
    setElements((prev) => [...prev, { id, type: 'Muro', length: 1, width: 0.2, height: 1, quantity: 1, material: 'Concreto' }]);
  };

  const removeElement = (id: string) => {
    setElements((prev) => prev.filter((e) => e.id !== id));
  };

  const updateElement = (id: string, updates: Partial<BuildingElement>) => {
    setElements((prev) => prev.map((e) => (e.id === id ? { ...e, ...updates } : e)));
  };

  const totalVolume = elements.reduce((sum, e) => sum + calcVolume(e), 0);
  const totalArea = elements.reduce((sum, e) => sum + calcArea(e), 0);
  const totalWeight = elements.reduce((sum, e) => sum + calcWeight(e), 0);
  const totalCost = elements.reduce((sum, e) => sum + calcCost(e), 0);

  const exportBOQ = () => {
    // Generar CSV con formato Excel-compatible (UTF-8 BOM para acentos)
    let csv = '\uFEFFTipo,Material,Longitud(m),Ancho(m),Altura(m),Cantidad,Volumen(m³),Area(m²),Peso(kg),Costo($)\n';
    for (const el of elements) {
      csv += `${el.type},${el.material},${el.length},${el.width},${el.height},${el.quantity},${calcVolume(el).toFixed(3)},${calcArea(el).toFixed(2)},${calcWeight(el).toFixed(1)},${calcCost(el).toFixed(2)}\n`;
    }
    csv += `TOTAL,,,,,,${totalVolume.toFixed(3)},${totalArea.toFixed(2)},${totalWeight.toFixed(1)},${totalCost.toFixed(2)}\n`;
    // Usar tipo Excel para mejor compatibilidad
    const blob = new Blob([csv], { type: 'application/vnd.ms-excel;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'memoria-de-calculos.xls';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="w-full h-full flex flex-col overflow-hidden" style={{ background: 'var(--abyss)', color: 'var(--text-primary)' }}>
      <div className="flex items-center justify-between px-3 py-2 shrink-0" style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border-subtle)' }}>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Building2 size={16} style={{ color: 'var(--accent-gold)' }} />
            <span className="text-sm font-semibold">Calculadora BIM</span>
          </div>
          <div className="flex rounded-md overflow-hidden" style={{ border: '1px solid var(--border-subtle)' }}>
            {(['manual', 'ifc'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setModo(m)}
                className="px-2.5 py-1 text-[11px] font-medium transition-colors"
                style={{
                  background: modo === m ? 'var(--accent-gold)' : 'transparent',
                  color: modo === m ? 'var(--void)' : 'var(--text-secondary)',
                }}
              >
                {m === 'manual' ? 'Manual' : 'Modelo IFC'}
              </button>
            ))}
          </div>
        </div>
        {modo === 'manual' && (
        <div className="flex items-center gap-2">
          <button
            onClick={exportBOQ}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all"
            style={{ background: 'var(--surface-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--accent-gold-dim)'; e.currentTarget.style.color = 'var(--text-primary)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border-subtle)'; e.currentTarget.style.color = 'var(--text-secondary)'; }}
          >
            <Download size={12} /> Exportar a Excel
          </button>
          <button
            onClick={addElement}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all"
            style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
            onMouseEnter={(e) => { e.currentTarget.style.boxShadow = 'var(--shadow-glow-gold)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none'; }}
          >
            <Plus size={12} /> Agregar Elemento
          </button>
        </div>
        )}
      </div>

      {modo === 'ifc' && <IFCPanel />}

      {modo === 'manual' && (
      <div className="flex-1 overflow-auto">
        {/* Summary */}
        <div className="grid grid-cols-4 gap-2 p-3">
          {[
            { label: 'Volumen Total', value: totalVolume, decimals: 2, suffix: ' m³', icon: <Calculator size={14} />, color: 'var(--accent-gold)' },
            { label: 'Área Total', value: totalArea, decimals: 2, suffix: ' m²', icon: <Building2 size={14} />, color: 'var(--info)' },
            { label: 'Peso Total', value: totalWeight / 1000, decimals: 2, suffix: ' t', icon: <HardHat size={14} />, color: 'var(--amber)' },
            { label: 'Costo Total', value: totalCost, decimals: 0, prefix: '$', icon: <Building2 size={14} />, color: 'var(--success)' },
          ].map((s) => (
            <div
              key={s.label}
              className="group relative flex flex-col px-3 py-2 rounded-md overflow-hidden transition-shadow"
              style={{ background: 'var(--glass-bg)', backdropFilter: 'var(--backdrop-blur)', border: '1px solid var(--border-subtle)' }}
              onMouseEnter={(e) => { e.currentTarget.style.boxShadow = 'var(--shadow-glow-gold)'; e.currentTarget.style.borderColor = 'var(--border-active)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.borderColor = 'var(--border-subtle)'; }}
            >
              <div className="flex items-center gap-1.5 mb-1" style={{ color: 'var(--text-muted)' }}>
                {s.icon}
                <span className="text-[10px]">{s.label}</span>
              </div>
              <span className="text-lg font-bold font-mono" style={{ color: s.color }}>
                {s.prefix}
                <AnimatedNumber
                  value={s.value}
                  decimals={s.decimals}
                  format={(n) => n.toLocaleString('es-MX', { minimumFractionDigits: s.decimals, maximumFractionDigits: s.decimals })}
                />
                {s.suffix}
              </span>
            </div>
          ))}
        </div>

        {elements.length === 0 && (
          <div
            className="mx-3 mb-3 rounded-lg py-10 flex flex-col items-center gap-3 text-center"
            style={{ border: '1px dashed var(--border-active)', background: 'var(--glass-bg)' }}
          >
            <Box className="w-6 h-6" style={{ color: 'var(--text-muted)' }} />
            <div>
              <p className="text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>Todavía no hay elementos en esta memoria de cálculo</p>
              <p className="text-[11px] mt-1" style={{ color: 'var(--text-muted)' }}>Agrega muros, columnas o losas para empezar a calcular volumen, peso y costo.</p>
            </div>
            <button
              onClick={addElement}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium"
              style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
            >
              <Plus size={12} /> Agregar el primer elemento
            </button>
          </div>
        )}

        {/* Elements table */}
        {elements.length > 0 && (
        <div className="px-3 pb-3">
          <div className="rounded-lg overflow-hidden" style={{ border: '1px solid var(--border-subtle)' }}>
            {/* Header */}
            <div className="grid grid-cols-12 gap-1 px-3 py-2 text-[9px] font-medium uppercase tracking-wider" style={{ background: 'var(--surface)', color: 'var(--text-muted)' }}>
              <div className="col-span-2">Tipo</div>
              <div className="col-span-1">Material</div>
              <div className="col-span-1">Long.</div>
              <div className="col-span-1">Ancho</div>
              <div className="col-span-1">Alto</div>
              <div className="col-span-1">Cant.</div>
              <div className="col-span-1">Vol m³</div>
              <div className="col-span-1">Área m²</div>
              <div className="col-span-1">Peso kg</div>
              <div className="col-span-1">Costo $</div>
              <div className="col-span-1" />
            </div>

            {elements.map((el) => (
              <div
                key={el.id}
                className="grid grid-cols-12 gap-1 px-3 py-1.5 text-[10px] items-center"
                style={{ borderTop: '1px solid var(--border-subtle)', background: 'var(--surface)' }}
              >
                <div className="col-span-2">
                  <select
                    value={el.type}
                    onChange={(e) => updateElement(el.id, { type: e.target.value as ElementType })}
                    className="w-full bg-transparent outline-none font-medium"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {ELEMENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div className="col-span-1">
                  <select
                    value={el.material}
                    onChange={(e) => updateElement(el.id, { material: e.target.value as Material })}
                    className="w-full bg-transparent outline-none"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    {MATERIALS.map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                </div>
                {(['length', 'width', 'height', 'quantity'] as const).map((field) => (
                  <div key={field} className="col-span-1">
                    <input
                      type="number"
                      value={el[field]}
                      onChange={(e) => updateElement(el.id, { [field]: Number(e.target.value) })}
                      className="w-full bg-transparent font-mono outline-none"
                      style={{ color: 'var(--text-primary)' }}
                      step={field === 'quantity' ? 1 : 0.01}
                    />
                  </div>
                ))}
                <div className="col-span-1 font-mono" style={{ color: 'var(--accent-gold)' }}>{calcVolume(el).toFixed(2)}</div>
                <div className="col-span-1 font-mono" style={{ color: 'var(--info)' }}>{calcArea(el).toFixed(1)}</div>
                <div className="col-span-1 font-mono" style={{ color: 'var(--amber)' }}>{calcWeight(el).toFixed(0)}</div>
                <div className="col-span-1 font-mono" style={{ color: 'var(--success)' }}>${calcCost(el).toFixed(0)}</div>
                <div className="col-span-1 text-right">
                  <button onClick={() => removeElement(el.id)} className="p-1 rounded hover:bg-[#222235] transition-colors" style={{ color: 'var(--danger)' }}>
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
        )}
      </div>
      )}
    </div>
  );
}
