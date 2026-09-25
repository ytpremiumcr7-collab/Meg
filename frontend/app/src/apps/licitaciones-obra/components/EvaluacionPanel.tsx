import { useEffect, useState } from 'react';
import { ClipboardCheck, Play, AlertTriangle } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';

export default function EvaluacionPanel({ expedienteId }: { expedienteId: string }) {
  const [workspace, setWorkspace] = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const load = async () => { try { setWorkspace(await megalodonClient.licitacionesObra.workspace(expedienteId)); } catch (e) { setError((e as Error).message); } };
  useEffect(() => { void load(); }, [expedienteId]);
  const evaluate = async () => { setRunning(true); setError(''); try { await megalodonClient.licitacionesObra.evaluacion.evaluar(expedienteId); await load(); } catch (e) { setError((e as Error).message); } finally { setRunning(false); } };
  return <div className="space-y-6"><header className="flex items-center justify-between"><div><h2 className="text-xl font-bold flex items-center gap-2"><ClipboardCheck className="w-5 h-5 text-violet-400" /> Evaluación determinista</h2><p className="text-sm text-zinc-500">La evaluación se ejecuta sobre las proposiciones almacenadas y los criterios de la convocatoria.</p></div><button disabled={running} onClick={() => void evaluate()} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-500/20 border border-violet-500/30 text-violet-300 disabled:opacity-40"><Play className="w-4 h-4" /> {running ? 'Evaluando…' : 'Evaluar proposiciones'}</button></header>
    {error && <div className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-300 flex gap-2"><AlertTriangle className="w-4 h-4" />{error}</div>}
    <div className="grid grid-cols-3 gap-3 text-sm"><Metric l="Estado" v={workspace?.licitacion?.estado || '—'} /><Metric l="Proposiciones" v={String(workspace?.proposiciones?.length || 0)} /><Metric l="Evaluaciones" v={String(workspace?.evaluaciones?.length || 0)} /></div>
    <div className="space-y-2">{(workspace?.evaluaciones || []).map((e: any) => <div key={e.id} className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 flex justify-between"><div><b>{e.tipo}</b><div className="text-xs text-zinc-500">Proposición {e.proposicion_id}</div></div><div className="text-right"><div className={e.resultado === 'APROBADA' ? 'text-emerald-400' : 'text-red-400'}>{e.resultado}</div><div className="text-xs text-zinc-500">{e.puntaje ?? '—'} puntos</div></div></div>)}</div>
  </div>;
}
function Metric({ l, v }: { l: string; v: string }) { return <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4"><div className="text-xs text-zinc-500">{l}</div><div className="mt-1 font-semibold text-zinc-200">{v}</div></div>; }
