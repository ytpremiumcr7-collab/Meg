import { useEffect, useState } from 'react';
import { Users, RefreshCw, AlertTriangle } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';

export default function ProposicionesPanel({ expedienteId }: { expedienteId: string }) {
  const [data, setData] = useState<any>({ proposiciones: [], licitacion: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true); setError('');
    try { setData(await megalodonClient.licitacionesObra.proposiciones.list(expedienteId)); }
    catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, [expedienteId]);

  return <div className="space-y-6"><header className="flex items-center justify-between"><div><h2 className="text-xl font-bold flex items-center gap-2"><Users className="w-5 h-5 text-amber-400" /> Proposiciones</h2><p className="text-sm text-zinc-500">Licitación: {data.licitacion?.folio || '—'} · Estado: {data.licitacion?.estado || '—'}</p></div><button onClick={() => void load()} className="flex items-center gap-2 px-3 py-2 border border-zinc-700 rounded-lg text-sm"><RefreshCw className="w-4 h-4" /> Actualizar</button></header>
    {error && <div className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-300 flex gap-2"><AlertTriangle className="w-4 h-4" />{error}</div>}
    {loading ? <div className="text-sm text-zinc-400">Cargando proposiciones…</div> : data.proposiciones.length === 0 ? <div className="rounded-xl border border-zinc-800 p-6 text-sm text-zinc-500">No existen proposiciones registradas para la licitación.</div> : <div className="space-y-3">{data.proposiciones.map((p: any) => <div key={p.id} className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 flex items-center justify-between"><div><div className="font-semibold text-zinc-200">{p.proveedor?.razon_social || 'Proveedor sin razón social'}</div><div className="text-xs text-zinc-500 font-mono">{p.proveedor?.rfc || p.proveedor_id}</div></div><div className="flex items-center gap-6 text-sm"><span className="text-zinc-300">${Number(p.monto).toLocaleString()}</span><span className="text-zinc-400">{p.plazo_dias} días</span><span className={p.estado === 'ADMITIDA' ? 'text-emerald-400' : p.estado === 'DESECHADA' ? 'text-red-400' : 'text-amber-400'}>{p.estado}</span></div></div>)}</div>}
  </div>;
}
