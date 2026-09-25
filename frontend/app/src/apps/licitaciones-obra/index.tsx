/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 *
 * App: Licitaciones de Obra
 * Integración ZIP 2 — Ciclo completo de licitación pública mexicana
 * Planeación → Convocatoria → Proposiciones → Evaluación → Fallo → 
 * Contrato → Ejecución → Finiquito
 */
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FileText, Gavel, Users, ClipboardCheck, Calculator,
  Shield, TrendingUp, BookOpen, AlertCircle, CheckCircle2,
  Clock, DollarSign, Scale, ChevronRight, Download, Printer
} from 'lucide-react';
import { useExpedienteStore } from '@/stores/useExpedienteStore';
import { megalodonClient } from '@/lib/api-client';

// Componentes de fase
import PlaneacionPanel from './components/PlaneacionPanel';
import ConvocatoriaPanel from './components/ConvocatoriaPanel';
import ProposicionesPanel from './components/ProposicionesPanel';
import TenderAutomationPanel from './components/TenderAutomationPanel';
import EvaluacionPanel from './components/EvaluacionPanel';
import FalloPanel from './components/FalloPanel';
import ContratoPanel from './components/ContratoPanel';
import EstimacionesPanel from './components/EstimacionesPanel';
import FiniquitoPanel from './components/FiniquitoPanel';

type Fase = 'planeacion' | 'convocatoria' | 'automatizacion' | 'proposiciones' | 'evaluacion' |
  'fallo' | 'contrato' | 'ejecucion' | 'finiquito';

interface FaseConfig {
  id: Fase;
  label: string;
  icon: React.ElementType;
  color: string;
  bgColor: string;
  borderColor: string;
}

const FASES: FaseConfig[] = [
  { id: 'planeacion', label: 'Planeación', icon: FileText, color: 'text-blue-400', bgColor: 'bg-blue-500/10', borderColor: 'border-blue-500/30' },
  { id: 'convocatoria', label: 'Convocatoria', icon: BookOpen, color: 'text-emerald-400', bgColor: 'bg-emerald-500/10', borderColor: 'border-emerald-500/30' },
  { id: 'automatizacion', label: 'Automatización', icon: Shield, color: 'text-cyan-400', bgColor: 'bg-cyan-500/10', borderColor: 'border-cyan-500/30' },
  { id: 'proposiciones', label: 'Proposiciones', icon: Users, color: 'text-amber-400', bgColor: 'bg-amber-500/10', borderColor: 'border-amber-500/30' },
  { id: 'evaluacion', label: 'Evaluación', icon: ClipboardCheck, color: 'text-violet-400', bgColor: 'bg-violet-500/10', borderColor: 'border-violet-500/30' },
  { id: 'fallo', label: 'Fallo', icon: Gavel, color: 'text-rose-400', bgColor: 'bg-rose-500/10', borderColor: 'border-rose-500/30' },
  { id: 'contrato', label: 'Contrato', icon: FileText, color: 'text-orange-400', bgColor: 'bg-orange-500/10', borderColor: 'border-orange-500/30' },
  { id: 'ejecucion', label: 'Ejecución', icon: TrendingUp, color: 'text-cyan-400', bgColor: 'bg-cyan-500/10', borderColor: 'border-cyan-500/30' },
  { id: 'finiquito', label: 'Finiquito', icon: Shield, color: 'text-teal-400', bgColor: 'bg-teal-500/10', borderColor: 'border-teal-500/30' },
];

export default function LicitacionesObraApp() {
  const [faseActiva, setFaseActiva] = useState<Fase>('planeacion');
  const [resumenCiclo, setResumenCiclo] = useState<any>(null);
  const [cargandoResumen, setCargandoResumen] = useState(false);
  const expediente = useExpedienteStore((s) => s.expedienteActivo());

  const cargarResumen = async () => {
    if (!expediente) return;
    setCargandoResumen(true);
    try {
      const res = await megalodonClient.licitacionesObra.resumenCiclo(expediente.id);
      setResumenCiclo(res);
    } catch (e) {
      console.error('Error cargando resumen:', e);
    } finally {
      setCargandoResumen(false);
    }
  };

  if (!expediente) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center p-8 rounded-2xl bg-zinc-800/50 border border-zinc-700">
          <FileText className="w-16 h-16 mx-auto mb-4 text-zinc-500" />
          <h2 className="text-xl font-bold text-zinc-300 mb-2">Sin Expediente Activo</h2>
          <p className="text-zinc-500 max-w-md">
            Selecciona un expediente activo en la app "Proyectos" para gestionar licitaciones de obra.
          </p>
        </div>
      </div>
    );
  }

  const faseActualIdx = FASES.findIndex(f => f.id === faseActiva);

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f] text-zinc-100 overflow-hidden">
      {/* Header */}
      <div className="border-b border-zinc-800/80 px-5 py-4 shrink-0">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-500/15 border border-amber-500/30 flex items-center justify-center">
              <Gavel className="w-5 h-5 text-amber-400" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-zinc-100">Licitaciones de Obra</h1>
              <p className="text-xs text-zinc-500 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                Expediente: <span className="text-zinc-300 font-mono">{expediente.identificador || expediente.id}</span>
              </p>
            </div>
          </div>
          <button
            onClick={cargarResumen}
            disabled={cargandoResumen}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-zinc-800/60 border border-zinc-700 
                     hover:bg-zinc-700/60 text-xs text-zinc-400 transition-colors"
          >
            <Scale className="w-3.5 h-3.5" />
            {cargandoResumen ? 'Cargando...' : 'Resumen del Ciclo'}
          </button>
        </div>

        {/* Timeline de fases */}
        <div className="flex items-center gap-1 overflow-x-auto pb-1 scrollbar-thin">
          {FASES.map((fase, idx) => {
            const Icon = fase.icon;
            const isActive = fase.id === faseActiva;
            const isPast = idx < faseActualIdx;
            const isFuture = idx > faseActualIdx;

            return (
              <button
                key={fase.id}
                onClick={() => setFaseActiva(fase.id)}
                className={`
                  flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-medium
                  transition-all duration-200 whitespace-nowrap shrink-0
                  ${isActive
                    ? `${fase.bgColor} ${fase.borderColor} border shadow-lg`
                    : isPast
                      ? 'bg-zinc-800/40 text-zinc-500 hover:bg-zinc-800/60'
                      : 'bg-zinc-900/30 text-zinc-600 hover:bg-zinc-800/40'
                  }
                `}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? fase.color : ''}`} />
                <span className={isActive ? 'text-zinc-100' : ''}>{fase.label}</span>
                {isPast && <CheckCircle2 className="w-3 h-3 text-emerald-500" />}
                {isActive && <div className={`w-1.5 h-1.5 rounded-full ${fase.color.replace('text-', 'bg-')}`} />}
              </button>
            );
          })}
        </div>
      </div>

      {/* Resumen del ciclo (si está cargado) */}
      {resumenCiclo && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          className="border-b border-zinc-800/80 bg-zinc-900/30 px-5 py-3 shrink-0"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6 text-xs">
              <span className="text-zinc-500">Estado: <span className="text-emerald-400 font-medium">{resumenCiclo.licitacion?.estado || '—'}</span></span>
              <span className="text-zinc-500">Proposiciones: <span className="text-zinc-200 font-medium">{resumenCiclo.summary?.proposiciones ?? 0}</span></span>
              <span className="text-zinc-500">Evaluaciones: <span className="text-zinc-200 font-medium">{resumenCiclo.summary?.evaluaciones ?? 0}</span></span>
              <span className="text-zinc-500">Contrato: <span className="text-cyan-400 font-medium">{resumenCiclo.summary?.contrato ? 'Sí' : 'No'}</span></span>
            </div>
            <button onClick={() => setResumenCiclo(null)} className="text-zinc-600 hover:text-zinc-400">
              <AlertCircle className="w-4 h-4" />
            </button>
          </div>
        </motion.div>
      )}

      {/* Contenido de la fase activa */}
      <div className="flex-1 overflow-auto p-5">
        <AnimatePresence mode="wait">
          <motion.div
            key={faseActiva}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
            className="h-full"
          >
            {faseActiva === 'planeacion' && <PlaneacionPanel expedienteId={expediente.id} />}
            {faseActiva === 'convocatoria' && <ConvocatoriaPanel expedienteId={expediente.id} />}
            {faseActiva === 'automatizacion' && <TenderAutomationPanel expedienteId={expediente.id} />}
            {faseActiva === 'proposiciones' && <ProposicionesPanel expedienteId={expediente.id} />}
            {faseActiva === 'evaluacion' && <EvaluacionPanel expedienteId={expediente.id} />}
            {faseActiva === 'fallo' && <FalloPanel expedienteId={expediente.id} />}
            {faseActiva === 'contrato' && <ContratoPanel expedienteId={expediente.id} />}
            {faseActiva === 'ejecucion' && <EstimacionesPanel expedienteId={expediente.id} />}
            {faseActiva === 'finiquito' && <FiniquitoPanel expedienteId={expediente.id} />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
