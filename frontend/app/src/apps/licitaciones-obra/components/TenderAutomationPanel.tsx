import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, Download, FileArchive, FileCheck2, Play, RefreshCw, Upload, ShieldCheck } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';

type Props = { expedienteId: string };

export default function TenderAutomationPanel({ expedienteId }: Props) {
  const [tender, setTender] = useState<any>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [identifier, setIdentifier] = useState('');
  const [title, setTitle] = useState('');
  const [catalog, setCatalog] = useState<any>({ profiles: [], legal_sources: [], articles: [], case_packs: [], project_types: {}, scope_scales: {}, funding_sources: {}, object_classes: {}, legal_regimes: {} });
  const [jurisdiction, setJurisdiction] = useState('');
  const [governmentLevel, setGovernmentLevel] = useState('');
  const [authority, setAuthority] = useState('');
  const [evaluationCriterion, setEvaluationCriterion] = useState('');
  const [procedureType, setProcedureType] = useState('LICITACION_PUBLICA');
  const [contractType, setContractType] = useState('UNIT_PRICES');
  const [approvalRole, setApprovalRole] = useState('revisor');
  const [projectType, setProjectType] = useState('');
  const [scopeScale, setScopeScale] = useState('');
  const [casePackCode, setCasePackCode] = useState('');
  const [fundingSource, setFundingSource] = useState('');
  const [objectClass, setObjectClass] = useState('');
  const [legalRegime, setLegalRegime] = useState('');
  const [flowMode, setFlowMode] = useState<'LICITANTE' | 'CONVOCANTE'>('LICITANTE');
  const [busy, setBusy] = useState(false);
  const [findings, setFindings] = useState<any[]>([]);
  const [requirements, setRequirements] = useState<any[]>([]);
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const [error, setError] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<string>('');
  const [readiness, setReadiness] = useState<any>(null);
  const [montoEstimado, setMontoEstimado] = useState('');
  const [presupuestoDepMiles, setPresupuestoDepMiles] = useState('');
  const [procedureRecommendation, setProcedureRecommendation] = useState<any>(null);
  const [presupuestos, setPresupuestos] = useState<any[]>([]);
  const [selectedPresupuestoId, setSelectedPresupuestoId] = useState('');
  const [bridgeInfo, setBridgeInfo] = useState<any>(null);
  const [formatChecklist, setFormatChecklist] = useState<Array<{ code: string; title: string; category: string; required: boolean; status: 'PENDIENTE' | 'REVISADO' | 'EDITADO' | 'LISTO'; notes: string }>>([]);
  const [workspaceDocs, setWorkspaceDocs] = useState<any[]>([]);
  const [activeDoc, setActiveDoc] = useState<any>(null);
  const [docDraft, setDocDraft] = useState('');
  const [economicDraft, setEconomicDraft] = useState<{ budget_total: string; object: string; authority: string }>({ budget_total: '', object: '', authority: '' });

  useEffect(() => {
    megalodonClient.procurement.catalog().then(setCatalog).catch((e) => setError((e as Error).message));
  }, []);

  const selectedProfile = useMemo(() => catalog.profiles.find((p: any) => p.code === jurisdiction), [catalog, jurisdiction]);

  const refresh = async (id?: string) => {
    const target = id || tender?.id;
    if (!target) return;
    const full = await megalodonClient.procurement.get(target);
    setTender(full); setJurisdiction(full.jurisdiction_code || ""); setProcedureType(full.procedure_type || ""); setContractType(full.contract_type || ""); setEvaluationCriterion(full.evaluation_criterion || ""); setProjectType(full.project_type || ""); setScopeScale(full.scope_scale || ""); setCasePackCode(full.case_pack_code || ""); setFundingSource(full.funding_source || ""); setObjectClass(full.object_class || ""); setLegalRegime(full.legal_regime || "");
    const readinessResult = await megalodonClient.procurement.readiness(target).catch(() => null);
    setReadiness(readinessResult);
    const list = await megalodonClient.procurement.list({ expediente_id: expedienteId });
    const current = list.find((item: any) => item.id === target);
    if (current) setTender({ ...full, ...current, id: target, canonical_model: full.canonical_model, source_manifest: full.source_manifest });
    const docs = await megalodonClient.procurement.workspaceDocuments(target).catch(() => []);
    setWorkspaceDocs(Array.isArray(docs) ? docs : []);
    const fullModel = full.canonical_model || {};
    const eco = fullModel.economic || {};
    const facts = fullModel.facts || {};
    setEconomicDraft({
      budget_total: eco.budget_total != null ? String(eco.budget_total) : (eco.budget_total_reference != null ? String(eco.budget_total_reference) : ''),
      object: facts.object || full.title || '',
      authority: facts.authority || '',
    });
    if (Array.isArray(fullModel.format_checklist) && fullModel.format_checklist.length) {
      setFormatChecklist(fullModel.format_checklist.map((f: any) => ({
        code: String(f.code),
        title: String(f.title || f.code),
        category: String(f.category || 'TECNICO'),
        required: f.required !== false,
        status: (f.status || 'PENDIENTE') as any,
        notes: String(f.notes || ''),
      })));
    }
  };

  useEffect(() => {
    let mounted = true;
    Promise.all([
      megalodonClient.procurement.list({ expediente_id: expedienteId }),
      megalodonClient.presupuestos.list(expedienteId).catch(() => []),
    ]).then(([rows, presup]: [any[], any[]]) => {
      if (!mounted) return;
      setPresupuestos(Array.isArray(presup) ? presup : []);
      if (!rows.length) return;
      const latest = rows[0];
      megalodonClient.procurement.get(latest.id).then((full) => {
        if (!mounted) return;
        setTender(full);
        setJurisdiction(full.jurisdiction_code || "");
        setProcedureType(full.procedure_type || "");
        setContractType(full.contract_type || "");
        setEvaluationCriterion(full.evaluation_criterion || "");
        setProjectType(full.project_type || "");
        setScopeScale(full.scope_scale || "");
        setCasePackCode(full.case_pack_code || "");
        setFundingSource(full.funding_source || "");
        setObjectClass(full.object_class || "");
        setLegalRegime(full.legal_regime || "");
        const eco = full.canonical_model?.economic || {};
        const facts = full.canonical_model?.facts || {};
        setEconomicDraft({
          budget_total: eco.budget_total != null ? String(eco.budget_total) : '',
          object: facts.object || full.title || '',
          authority: facts.authority || '',
        });
        if (eco.presupuesto_id) setSelectedPresupuestoId(String(eco.presupuesto_id));
      });
    }).catch(() => undefined);
    return () => { mounted = false; };
  }, [expedienteId]);

  const recommendProcedure = async (materializeOnTender = false) => {
    if (!jurisdiction) {
      setError('Selecciona primero la dependencia / jurisdicción.');
      return;
    }
    const monto = Number(String(montoEstimado).replace(/,/g, ''));
    if (!Number.isFinite(monto) || monto <= 0) {
      setError('Captura un monto estimado válido (pesos) para recomendar el procedimiento.');
      return;
    }
    if (flowMode === 'CONVOCANTE') {
      const presupuesto = presupuestoDepMiles.trim()
        ? Number(String(presupuestoDepMiles).replace(/,/g, ''))
        : NaN;
      const isFederal = (governmentLevel || selectedProfile?.government_level || '').toUpperCase() === 'FEDERAL'
        || String(jurisdiction).toUpperCase().startsWith('MX-FED');
      if (isFederal && !Number.isFinite(presupuesto)) {
        setError('Modo CONVOCANTE federal: captura el presupuesto autorizado de la dependencia (miles MXN, Anexo 9 PEF).');
        return;
      }
    }
    if (flowMode === 'LICITANTE' && materializeOnTender) {
      setError('Modo LICITANTE: no se materializa el procedimiento desde umbrales (viene de la convocatoria).');
      return;
    }
    const presupuesto = presupuestoDepMiles.trim()
      ? Number(String(presupuestoDepMiles).replace(/,/g, ''))
      : null;
    setBusy(true); setError('');
    try {
      const esObra = (objectClass || selectedProfile?.matter || 'PUBLIC_WORKS') === 'PUBLIC_WORKS';
      const payload = {
        jurisdiction_code: jurisdiction,
        monto,
        es_obra_publica: esObra,
        presupuesto_dependencia_miles: flowMode === 'CONVOCANTE' && Number.isFinite(presupuesto as number) ? presupuesto : (Number.isFinite(presupuesto as number) ? presupuesto : null),
        ejercicio_fiscal: new Date().getFullYear(),
        investigacion_mercado_realizada: false,
        tender_id: materializeOnTender && tender?.id ? tender.id : null,
        flow_mode: flowMode,
        procedure_type_declared: flowMode === 'LICITANTE' ? (procedureType || null) : null,
      };
      const result = materializeOnTender && tender?.id
        ? await megalodonClient.procurement.recommendProcedureForTender(tender.id, payload)
        : await megalodonClient.procurement.recommendProcedure(payload);
      setProcedureRecommendation(result);
      const recommended = result.procedure_type || result.procedimiento;
      if (recommended && result.valido && flowMode === 'CONVOCANTE') {
        const allowed = selectedProfile?.allowed_procedures || [];
        if (!allowed.length || allowed.includes(recommended)) {
          setProcedureType(recommended);
        }
      }
      if (materializeOnTender && tender?.id && flowMode === 'CONVOCANTE') {
        await refresh(tender.id);
      }
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };


  useEffect(() => {
    const pack = (selectedProfile?.case_packs || []).find((p: any) => p.code === casePackCode);
    const artifacts = pack?.artifacts || [];
    if (!artifacts.length) {
      setFormatChecklist((prev) => {
        if (prev.length) return prev;
        return (selectedProfile?.format_definitions || []).map((a: any) => ({
          code: String(a.format_code || a.code),
          title: String(a.title || a.format_code || a.code),
          category: String(a.category || 'TECNICO'),
          required: a.required !== false,
          status: 'PENDIENTE' as const,
          notes: '',
        }));
      });
      return;
    }
    setFormatChecklist((prev) => {
      const byCode = Object.fromEntries(prev.map((x) => [x.code, x]));
      return artifacts.map((a: any) => ({
        code: String(a.code || a.title || 'FMT'),
        title: String(a.title || a.code),
        category: String(a.category || 'TECNICO'),
        required: a.required !== false,
        status: (byCode[String(a.code)]?.status as any) || 'PENDIENTE',
        notes: byCode[String(a.code)]?.notes || '',
      }));
    });
  }, [selectedProfile, casePackCode, flowMode]);

  const hydrateFromPresupuesto = async () => {
    if (!tender?.id) {
      setError('Crea o selecciona un tender antes de hidratar desde presupuesto.');
      return;
    }
    setBusy(true); setError('');
    try {
      const result = await megalodonClient.procurement.hydrateFromPresupuesto(tender.id, {
        presupuesto_id: selectedPresupuestoId || undefined,
        overwrite_economic: true,
      });
      setBridgeInfo(result.bridge || result);
      const eco = result.economic_summary || {};
      const facts = result.facts || {};
      setEconomicDraft({
        budget_total: eco.budget_total != null ? String(eco.budget_total) : economicDraft.budget_total,
        object: facts.object || economicDraft.object,
        authority: facts.authority || economicDraft.authority,
      });
      setFormatChecklist((prev) => prev.map((f) => {
        const econ = f.category.toUpperCase().includes('ECON') || f.code.startsWith('AE') || f.code.startsWith('ECO') || f.code.startsWith('PE');
        if (!econ) return f;
        return { ...f, status: f.status === 'LISTO' ? f.status : 'REVISADO', notes: f.notes || 'Borrador desde presupuesto programable — revisa y edita' };
      }));
      await refresh(tender.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const updateFormatItem = (code: string, patch: Partial<{ status: 'PENDIENTE' | 'REVISADO' | 'EDITADO' | 'LISTO'; notes: string }>) => {
    setFormatChecklist((prev) => prev.map((f) => (f.code === code ? { ...f, ...patch } : f)));
  };

  const createTender = async () => {

    setBusy(true); setError('');
    try {
      const created = await megalodonClient.procurement.create({
        expediente_id: expedienteId,
        identifier,
        title,
        jurisdiction_code: jurisdiction || null,
        procedure_type: procedureType,
        contract_type: contractType,
        source_manifest: { authority: jurisdiction },
        evaluation_criterion: evaluationCriterion || null,
        project_type: projectType || null,
        scope_scale: scopeScale || null,
        case_pack_code: casePackCode || null,
        funding_source: fundingSource || null,
        object_class: objectClass || null,
        legal_regime: legalRegime || null,
        canonical_model: {
          facts: {
            contract_type: contractType,
            procedure_type: procedureType,
            jurisdiction_code: jurisdiction,
            government_level: governmentLevel,
            authority,
            evaluation_criterion: evaluationCriterion,
            project_type: projectType,
            scope_scale: scopeScale,
            case_pack_code: casePackCode || null,
            funding_source: fundingSource,
            object_class: objectClass,
            legal_regime: legalRegime,
            procedure_recommendation: procedureRecommendation || null,
          },
          technical: {}, economic: { partidas: [], budget_total: Number(String(montoEstimado).replace(/,/g, '')) || null }, schedule: { activities: [] }, risk: {}, bidder: {},
          approvals: { required_roles: [approvalRole] }, submission: {},
        },
      });
      setTender(created);
      const readinessResult = await megalodonClient.procurement.readiness(created.id).catch(() => null);
      setReadiness(readinessResult);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  const ingest = async () => {
    if (!tender || !files.length) return;
    setBusy(true); setError('');
    try {
      const ingested = await megalodonClient.procurement.ingest(tender.id, files);
      const detected = ingested.flatMap((item: any) => item?.detected_formats || []);
      if (detected.length) {
        setFormatChecklist((prev) => {
          const byCode = Object.fromEntries(prev.map((x) => [x.code, x]));
          for (const item of detected) {
            const code = String(item.code || '');
            if (!code) continue;
            byCode[code] = byCode[code] || {
              code,
              title: String(item.title || code),
              category: 'TECNICO',
              required: item.required === true,
              status: 'PENDIENTE',
              notes: 'Detectado por coincidencia determinista contra el catálogo DB; confirma antes de compilar.',
            };
          }
          return Object.values(byCode) as typeof prev;
        });
      }
      await refresh(tender.id);
      setFiles([]);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  const waitForJob = async (id: string, kind: 'RUN' | 'COMPILE') => {
    for (let attempt = 0; attempt < 180; attempt += 1) {
      const job = await megalodonClient.procurement.job(id);
      setJobStatus(`${job.status} · ${job.progress}%`);
      if (job.status === 'SUCCEEDED') {
        if (kind === 'RUN') {
          setFindings(job.result?.findings || []);
        } else {
          setArtifacts(job.result?.artifacts || []);
        }
        await refresh(tender?.id);
        return;
      }
      if (job.status === 'FAILED') throw new Error(job.error_message || 'El job de Procurement falló.');
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    throw new Error('El job excedió el tiempo máximo de observación del cliente; continúa ejecutándose en segundo plano.');
  };

  const execute = async () => {
    if (!tender) return;
    setBusy(true); setError(''); setFindings([]);
    try {
      const derived = await megalodonClient.procurement.deriveRequirements(tender.id);
      setRequirements(derived);
      const key = `procurement-run:${tender.id}:r${tender.current_revision}`;
      const queued = await megalodonClient.procurement.enqueueRun(tender.id, key);
      setJobId(queued.job_id);
      await waitForJob(queued.job_id, 'RUN');
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };


  const saveSemiAutoReview = async () => {
    if (!tender?.id) {
      setError('No hay tender para guardar la revisión.');
      return false;
    }
    setBusy(true); setError('');
    try {
      const ref = Number(String(economicDraft.budget_total).replace(/,/g, ''));
      const result = await megalodonClient.procurement.applySemiAutoReview(tender.id, {
        authority: economicDraft.authority || undefined,
        object: economicDraft.object || undefined,
        budget_total_reference: Number.isFinite(ref) ? ref : undefined,
        format_checklist: formatChecklist,
        reason: 'SEMI_AUTO_REVIEW',
      });
      if (result?.format_checklist) {
        setFormatChecklist(result.format_checklist.map((f: any) => ({
          code: String(f.code),
          title: String(f.title || f.code),
          category: String(f.category || 'TECNICO'),
          required: f.required !== false,
          status: (f.status || 'PENDIENTE') as any,
          notes: String(f.notes || ''),
        })));
      }
      await refresh(tender.id);
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const compile = async () => {
    if (!tender) return;
    const pendingRequired = formatChecklist.filter((f) => f.required && f.status !== 'LISTO' && f.status !== 'EDITADO');
    if (pendingRequired.length) {
      setError(`Semi-automatización: marca como LISTO o EDITADO los formatos obligatorios: ${pendingRequired.map((f) => f.code).join(', ')}.`);
      return;
    }
    setBusy(true); setError('');
    try {
      // Persistir edición humana ANTES de hidratar/compilar
      const ref = Number(String(economicDraft.budget_total).replace(/,/g, ''));
      const reviewed = await megalodonClient.procurement.applySemiAutoReview(tender.id, {
        authority: economicDraft.authority || undefined,
        object: economicDraft.object || undefined,
        budget_total_reference: Number.isFinite(ref) ? ref : undefined,
        format_checklist: formatChecklist,
        reason: 'SEMI_AUTO_REVIEW_BEFORE_COMPILE',
      });
      const reviewedRevision = Number(reviewed?.current_revision || reviewed?.revision || tender.current_revision);
      if (selectedPresupuestoId || presupuestos.length) {
        await megalodonClient.procurement.hydrateFromPresupuesto(tender.id, {
          presupuesto_id: selectedPresupuestoId || undefined,
          overwrite_economic: true,
        }).catch(() => null);
      }
      const key = `procurement-compile:${tender.id}:r${reviewedRevision}`;
      const queued = await megalodonClient.procurement.enqueueCompile(tender.id, key);
      setJobId(queued.job_id);
      await waitForJob(queued.job_id, 'COMPILE');
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  const approve = async () => {
    if (!tender) return;
    setBusy(true); setError('');
    try { await megalodonClient.procurement.approve(tender.id, { role: approvalRole, decision: 'APPROVED' }); await refresh(tender.id); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  const buildSubmission = async () => {
    if (!tender) return;
    setBusy(true); setError('');
    try { await megalodonClient.procurement.submission(tender.id); await refresh(tender.id); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  const downloadSubmission = async () => {
    if (!tender) return;
    setBusy(true); setError('');
    try {
      const result = await megalodonClient.procurement.submissionDownload(tender.id);
      window.open(result.url, '_blank', 'noopener,noreferrer');
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  const openWorkspaceDocument = async (doc: any) => {
    if (!tender?.id) return;
    try { const full = await megalodonClient.procurement.workspaceGetDocument(tender.id, doc.id); setActiveDoc(full); setDocDraft(full.content_text || ''); }
    catch (e) { setError((e as Error).message); }
  };

  const saveWorkspaceDocument = async () => {
    if (!tender?.id || !activeDoc) return;
    setBusy(true); setError('');
    try { const saved = await megalodonClient.procurement.workspaceUpdateDocument(tender.id, activeDoc.id, { content_text: docDraft, content_model: activeDoc.content_model || {}, expected_row_version: activeDoc.row_version }); setActiveDoc(saved); setDocDraft(saved.content_text || ''); setWorkspaceDocs((prev) => prev.map((d) => d.id === saved.id ? saved : d)); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };

  const statusText = useMemo(() => tender?.state || 'SIN_EXPEDIENTE', [tender]);

  return (
    <div className="space-y-5 max-w-6xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-zinc-100 flex items-center gap-2"><ShieldCheck className="w-5 h-5 text-cyan-400" /> Automatización de proposición</h2>
          <p className="text-sm text-zinc-500 mt-1">Expediente canónico, jurisdicción, artículos, reglas, evidencia, costeo, programa, QA y submission.</p>
        </div>
        {tender && <button onClick={() => refresh()} className="p-2 rounded-lg border border-zinc-700 hover:bg-zinc-800"><RefreshCw className="w-4 h-4" /></button>}
      </div>

      {jobId && <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-3 py-2 text-xs text-cyan-200">Job Procurement: {jobId} · {jobStatus || 'ENCOLADO'}</div>}
      {tender && <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 space-y-4">
        <div className="flex items-center justify-between"><div><h3 className="font-semibold text-zinc-100">Workspace documental</h3><p className="text-xs text-zinc-500">Documentos editables del TenderPackage. Las ediciones humanas quedan versionadas y bloquean regeneraciones destructivas.</p></div><span className="text-xs text-zinc-500">r{tender.current_revision}</span></div>
        <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
          <div className="space-y-2">{workspaceDocs.length ? workspaceDocs.map((doc) => <button key={doc.id} type="button" onClick={() => void openWorkspaceDocument(doc)} className={`w-full text-left rounded-lg border px-3 py-2 text-xs ${activeDoc?.id === doc.id ? 'border-cyan-600 bg-cyan-500/10' : 'border-zinc-800 bg-zinc-950/30'}`}><div className="font-medium text-zinc-200">{doc.artifact_code}</div><div className="text-zinc-500">v{doc.version} · {doc.status} {doc.human_modified ? '· editado' : ''}</div></button>) : <div className="text-xs text-zinc-500">Después de compilar aparecerán los documentos disponibles.</div>}</div>
          <div className="space-y-3">{activeDoc ? <><div className="flex items-center justify-between text-xs text-zinc-500"><span>{activeDoc.name} · fila {activeDoc.row_version}</span><span>{activeDoc.locked ? 'BLOQUEADO' : 'EDITABLE'}</span></div><textarea value={docDraft} disabled={activeDoc.locked || tender.frozen} onChange={(e) => setDocDraft(e.target.value)} className="min-h-[280px] w-full rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-200 font-mono" placeholder="Contenido editable del documento..."/><div className="flex gap-2"><button type="button" disabled={busy || activeDoc.locked || tender.frozen} onClick={() => void saveWorkspaceDocument()} className="px-3 py-2 rounded-lg bg-cyan-600 text-white text-xs disabled:opacity-40">Guardar versión</button><button type="button" disabled={busy} onClick={() => void megalodonClient.procurement.workspaceHistory(tender.id, activeDoc.id).then((h) => { if (h?.[0]) setDocDraft(h[0].content_text || '') }).catch((e) => setError((e as Error).message))} className="px-3 py-2 rounded-lg border border-zinc-700 text-xs">Ver última versión</button></div><div className="text-[11px] text-zinc-500">Fuentes: {(activeDoc.source_evidence_ids || []).length} · requisitos relacionados: {(activeDoc.requirement_ids || []).length} · dependencias: {(activeDoc.data_dependencies || []).join(', ')}</div></> : <div className="text-xs text-zinc-500">Selecciona un documento para editarlo.</div>}</div>
        </div>
      </section>}

      {!tender ? (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 space-y-4">
                  <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 space-y-3">
          <div className="text-xs font-semibold text-zinc-300">Modo de trabajo</div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => { setFlowMode('LICITANTE'); setProcedureRecommendation(null); }}
              className={`px-3 py-1.5 rounded-lg text-xs border ${flowMode === 'LICITANTE' ? 'border-cyan-600 bg-cyan-500/15 text-cyan-200' : 'border-zinc-700 text-zinc-400'}`}>
              LICITANTE — responder convocatoria
            </button>
            <button type="button" onClick={() => { setFlowMode('CONVOCANTE'); setProcedureRecommendation(null); }}
              className={`px-3 py-1.5 rounded-lg text-xs border ${flowMode === 'CONVOCANTE' ? 'border-amber-600 bg-amber-500/15 text-amber-100' : 'border-zinc-700 text-zinc-400'}`}>
              CONVOCANTE — planear procedimiento (Anexo 9)
            </button>
          </div>
          <p className="text-[11px] text-zinc-500">
            {flowMode === 'LICITANTE'
              ? 'El procedimiento suele venir en la convocatoria. No se exige presupuesto de dependencia ni se materializa desde umbrales.'
              : 'Planeación previa a publicar. En federal se exige presupuesto autorizado (miles) del Anexo 9 PEF para elegir el tramo.'}
          </p>
        </div>
        {procedureRecommendation && (
            <div className={`rounded-lg border px-3 py-2 text-xs ${procedureRecommendation.valido ? 'border-emerald-800/60 bg-emerald-950/20 text-emerald-200' : 'border-amber-800/60 bg-amber-950/20 text-amber-100'}`}>
              <div className="font-semibold">
                Recomendación DB: {procedureRecommendation.procedure_type || procedureRecommendation.procedimiento}
                {procedureRecommendation.datos_verificados ? ' · VERIFICADO' : procedureRecommendation.es_candidato ? ' · CANDIDATO' : ' · PENDIENTE / SIN DETERMINAR'}
              </div>
              <div className="mt-1 opacity-90">{procedureRecommendation.justificacion?.fundamento || procedureRecommendation.observaciones?.[0] || 'Sin fundamento'}</div>
              <div className="mt-1 opacity-70">
                Umbrales: AD {procedureRecommendation.umbrales?.adjudicacion_directa != null ? `$${Number(procedureRecommendation.umbrales.adjudicacion_directa).toLocaleString()}` : 'N/D'}
                {' · '}INV {procedureRecommendation.umbrales?.invitacion_tres != null ? `$${Number(procedureRecommendation.umbrales.invitacion_tres).toLocaleString()}` : 'N/D'}
                {procedureRecommendation.fuente_umbral ? ` · Fuente: ${procedureRecommendation.fuente_umbral}` : ''}
              </div>
              <div className="mt-1 text-[11px] opacity-60">El select de procedimiento queda editable: revisa y corrige si el expediente lo exige.</div>
              {procedureRecommendation.es_candidato && (
                <div className="mt-1 text-[11px] text-amber-300">
                  CANDIDATO: no se materializa en el tender automáticamente. Confirma Anexo 9 / fuente primaria o elige el procedimiento manualmente.
                  {procedureRecommendation.materialize_blocked_reason ? ` (${procedureRecommendation.materialize_blocked_reason})` : ''}
                </div>
              )}
              {procedureRecommendation.materialized === false && procedureRecommendation.tender_id && (
                <div className="mt-1 text-[11px] text-amber-300">Materialización bloqueada en servidor — el tender no cambió procedure_type.</div>
              )}
            </div>
          )}
          <div className="grid md:grid-cols-2 gap-3">
            <input value={identifier} onChange={e => setIdentifier(e.target.value)} aria-label="Identificador de licitación" className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm" />
            <input value={title} onChange={e => setTitle(e.target.value)} aria-label="Nombre / objeto de la obra" className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm" />
            <select value={jurisdiction} onChange={e => { setJurisdiction(e.target.value); setProcedureRecommendation(null); const p = catalog.profiles.find((x: any) => x.code === e.target.value); setGovernmentLevel(p?.government_level || ""); setAuthority(p?.authority || ""); setProcedureType(p?.allowed_procedures?.[0] || ""); setContractType(p?.allowed_contract_types?.[0] || ""); setEvaluationCriterion(p?.allowed_evaluation_criteria?.[0] || ""); setCasePackCode(p?.case_packs?.[0]?.code || ""); setFundingSource(p?.allowed_funding_sources?.[0] || ""); setLegalRegime(p?.allowed_legal_regimes?.[0] || ""); setObjectClass(p?.matter || ""); }} className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm"><option value="">Selecciona dependencia / entidad y régimen</option>{catalog.profiles.map((p: any) => <option key={p.code} value={p.code}>{p.authority} · {p.government_level} · {p.code}{p.ready_for_execution ? "" : " · requiere configuración jurídica"}</option>)}</select>
            <input value={montoEstimado} onChange={e => setMontoEstimado(e.target.value)} placeholder="Monto estimado (MXN, sin IVA)" aria-label="Monto estimado" className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm" />
            {flowMode === 'CONVOCANTE' ? (
              <input value={presupuestoDepMiles} onChange={e => setPresupuestoDepMiles(e.target.value)} placeholder="Presupuesto autorizado dependencia (miles MXN) — Anexo 9 PEF" aria-label="Presupuesto autorizado de la dependencia en miles (Anexo 9 PEF)" className="rounded-lg bg-zinc-950 border border-amber-900/40 px-3 py-2 text-sm" required />
            ) : (
              <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 py-2 text-[11px] text-zinc-500">Presupuesto Anexo 9 oculto en modo LICITANTE (no aplica al armar propuesta).</div>
            )}
            <div className="flex gap-2 items-center">
              <select value={procedureType} onChange={e => setProcedureType(e.target.value)} className="flex-1 rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm" disabled={!selectedProfile}><option value="">Tipo de procedimiento</option>{(selectedProfile?.allowed_procedures || []).map((v: string) => <option key={v} value={v}>{v}</option>)}</select>
              <button type="button" disabled={busy || !jurisdiction || !montoEstimado} onClick={() => recommendProcedure(false)} className="px-3 py-2 rounded-lg border border-cyan-700/50 bg-cyan-500/10 text-cyan-300 text-xs whitespace-nowrap disabled:opacity-40" title="Consulta umbrales en DB y propone el procedimiento; puedes corregirlo">Recomendar desde DB</button>
            </div>
            <select value={contractType} onChange={e => setContractType(e.target.value)} className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm" disabled={!selectedProfile}><option value="">Tipo de contrato</option>{(selectedProfile?.allowed_contract_types || []).map((v: string) => <option key={v} value={v}>{v}</option>)}</select>
            <select value={evaluationCriterion} onChange={e => setEvaluationCriterion(e.target.value)} className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm" disabled={!selectedProfile}><option value="">Criterio de evaluación</option>{(selectedProfile?.allowed_evaluation_criteria || []).map((v: string) => <option key={v} value={v}>{catalog.evaluation_criteria?.[v] || v}</option>)}</select>
            <select value={projectType} onChange={e => setProjectType(e.target.value)} className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm"><option value="">Tipo de obra / servicio</option>{Object.entries(catalog.project_types || {}).map(([k,v]: any) => <option key={k} value={k}>{v}</option>)}</select>
            <select value={scopeScale} onChange={e => setScopeScale(e.target.value)} className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm"><option value="">Escala</option>{Object.entries(catalog.scope_scales || {}).map(([k,v]: any) => <option key={k} value={k}>{v}</option>)}</select>
            {selectedProfile && <select value={fundingSource} onChange={e => setFundingSource(e.target.value)} className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm"><option value="">Fuente de recursos</option>{(selectedProfile.allowed_funding_sources || []).map((v: string) => <option key={v} value={v}>{catalog.funding_sources?.[v] || v}</option>)}</select>}
            {selectedProfile && <select value={objectClass} onChange={e => setObjectClass(e.target.value)} className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm"><option value="">Clase del objeto</option>{Object.entries(catalog.object_classes || {}).map(([k,v]: any) => <option key={k} value={k}>{v}</option>)}</select>}
            {selectedProfile && <select value={legalRegime} onChange={e => setLegalRegime(e.target.value)} className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm"><option value="">Régimen jurídico</option>{(selectedProfile.allowed_legal_regimes || []).map((v: string) => <option key={v} value={v}>{catalog.legal_regimes?.[v] || v}</option>)}</select>}
            <select value={casePackCode} onChange={e => setCasePackCode(e.target.value)} className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm" disabled={!selectedProfile}><option value="">Paquete documental: derivar de convocatoria</option>{(selectedProfile?.case_packs || []).map((p: any) => <option key={p.code} value={p.code}>{p.name}</option>)}</select>
            <select value={approvalRole} onChange={e => setApprovalRole(e.target.value)} aria-label="Rol de aprobación final" className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm"><option value="">Rol de aprobación</option>{((tender?.canonical_model?.approvals?.required_roles || selectedProfile?.required_approval_roles || ['revisor']) as string[]).map((role: string) => <option key={role} value={role}>{role}</option>)}</select>
          </div>
          <button disabled={busy || !identifier || !title || !jurisdiction || !procedureType || !contractType || !evaluationCriterion || !selectedProfile?.ready_for_execution} onClick={createTender} className="px-4 py-2 rounded-lg bg-cyan-500/20 border border-cyan-500/30 text-cyan-300 disabled:opacity-40">Crear expediente de automatización</button>
        </div>
      ) : (
        <>
          <section className="rounded-xl border border-cyan-900/40 bg-cyan-950/10 p-4 space-y-3">
            <div className="text-sm font-semibold text-cyan-300">Perfil jurídico seleccionado</div>
            <div className="text-xs text-zinc-400">{tender.jurisdiction_code} · {selectedProfile?.authority || tender.canonical_model?.facts?.authority || ""} · procedimiento: {tender.procedure_type || procedureType || "—"}</div>
            <div className="grid grid-cols-4 gap-2 text-xs"><span>Reglas: {selectedProfile?.rule_count ?? "—"}</span><span>Fuentes: {selectedProfile?.source_count ?? "—"}</span><span>Artículos: {selectedProfile?.article_count ?? "—"}</span><span>{selectedProfile?.ready_for_execution ? "OPERABLE" : "NO OPERABLE"}</span><span>Escala: {tender.scope_scale || "—"}</span><span>Paquete: {tender.case_pack_code || "Derivado"}</span><span>Recursos: {tender.funding_source || "—"}</span><span>Régimen: {tender.legal_regime || "—"}</span></div>
            <div className="flex flex-wrap gap-2 items-end pt-1">
              <input value={montoEstimado} onChange={e => setMontoEstimado(e.target.value)} placeholder="Monto estimado (MXN)" className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-xs w-44" />
              <input value={presupuestoDepMiles} onChange={e => setPresupuestoDepMiles(e.target.value)} placeholder="Presupuesto dep. (miles)" className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-xs w-48" />
              <button type="button" disabled={busy || !montoEstimado || flowMode === 'LICITANTE' || !!procedureRecommendation?.es_candidato} onClick={() => recommendProcedure(true)} className="px-3 py-2 rounded-lg border border-cyan-700/50 bg-cyan-500/10 text-cyan-300 text-xs disabled:opacity-40" title={procedureRecommendation?.es_candidato ? 'Bloqueado: umbral CANDIDATO no se materializa' : 'Materializa solo si datos VERIFICADOS'}>Re-recomendar y materializar en tender</button>
            </div>
            {procedureRecommendation && (
              <div className={`rounded-md border px-2 py-2 text-xs ${procedureRecommendation.valido ? 'border-emerald-800/50 text-emerald-200' : 'border-amber-800/50 text-amber-100'}`}>
                {procedureRecommendation.procedure_type || procedureRecommendation.procedimiento}
                {!procedureRecommendation.datos_verificados ? ' · dato no verificado' : ''}
                {procedureRecommendation.justificacion?.fundamento ? ` — ${procedureRecommendation.justificacion.fundamento}` : ''}
              </div>
            )}
          </section>

          <div className="grid md:grid-cols-4 gap-3">
            <Metric label="Estado" value={statusText} />
            <Metric label="Revisión" value={String(tender.current_revision ?? tender.revision ?? 1)} />
            <Metric label="Jurisdicción" value={tender.jurisdiction_code || 'Pendiente'} />
            <Metric label="Congelado" value={tender.frozen ? 'Sí' : 'No'} />
            <Metric label="Readiness" value={readiness ? (readiness.ready ? 'READY' : `${readiness.findings?.length || 0} bloqueos`) : '—'} />
          </div>

          {readiness && !readiness.ready && <section className="rounded-xl border border-amber-900/50 bg-amber-950/15 p-4"><div className="text-sm font-semibold text-amber-300">Gates de negocio pendientes</div><div className="mt-2 grid md:grid-cols-2 gap-2 text-xs text-amber-100">{(readiness.findings || []).map((f: any) => <div key={f.code} className="rounded-md border border-amber-900/50 px-2 py-2">[{f.severity}] {f.code}: {f.message}</div>)}</div></section>}

          <div className="grid lg:grid-cols-2 gap-4">
            <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 space-y-4">
              <h3 className="font-semibold text-zinc-200">1. Fuentes</h3>
              <input type="file" multiple onChange={e => setFiles(Array.from(e.target.files || []))} className="w-full text-sm" />
              <div className="flex gap-2">
                <button disabled={busy || !files.length} onClick={ingest} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-zinc-700 hover:bg-zinc-800 disabled:opacity-40"><Upload className="w-4 h-4" /> Ingresar fuentes</button>
                <button disabled={busy} onClick={execute} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-cyan-500/15 border border-cyan-500/25 text-cyan-300 disabled:opacity-40"><Play className="w-4 h-4" /> Ejecutar dominio</button>
              </div>
            </section>

            <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 space-y-3">
              <h3 className="font-semibold text-zinc-200">2. Requisitos derivados</h3>
              {requirements.length ? requirements.map(r => <div key={r.id} className="flex items-start gap-2 text-sm"><CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5" /><div><b>{r.code}</b><div className="text-zinc-500">{r.description}</div></div></div>) : <p className="text-sm text-zinc-500">Aún no se han derivado requisitos de las reglas configuradas.</p>}
            </section>
          </div>

          {findings.length > 0 && <section className="rounded-xl border border-red-900/50 bg-red-950/20 p-5"><h3 className="font-semibold text-red-300 mb-3 flex items-center gap-2"><AlertTriangle className="w-4 h-4" /> Hallazgos bloqueantes</h3>{findings.map((f, i) => <div key={i} className="text-sm text-red-200 mb-2">[{f.severity}] {f.code}: {f.message}</div>)}</section>}

          <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 space-y-4">
            <h3 className="font-semibold text-zinc-200">2b. Presupuesto → proposición (semi-auto)</h3>
            <p className="text-xs text-zinc-500">Montos y catálogo desde el presupuesto programable. Tú eliges el presupuesto, revisas, editas notas de cada formato y marcas LISTO. No es envío a ciegas.</p>
            <div className="flex flex-wrap gap-2 items-end">
              <label className="text-xs text-zinc-400 flex flex-col gap-1 min-w-[220px]">
                Presupuesto del expediente
                <select value={selectedPresupuestoId} onChange={(e) => setSelectedPresupuestoId(e.target.value)} className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm">
                  <option value="">Automático (más usable)</option>
                  {presupuestos.map((p: any) => (
                    <option key={p.id} value={p.id}>{p.identificador || p.id} · ${Number(p.monto_total || 0).toLocaleString()} · {p.estado || ''}</option>
                  ))}
                </select>
              </label>
              <button type="button" disabled={busy || !tender} onClick={() => void hydrateFromPresupuesto()} className="px-3 py-2 rounded-lg border border-cyan-700/50 bg-cyan-500/10 text-cyan-300 text-xs disabled:opacity-40">
                Hidratar borrador desde presupuesto
              </button>
              <button type="button" disabled={busy || !tender} onClick={() => void saveSemiAutoReview()} className="px-3 py-2 rounded-lg border border-emerald-700/50 bg-emerald-500/10 text-emerald-300 text-xs disabled:opacity-40">
                Guardar revisión (facts + checklist)
              </button>
            </div>
            {bridgeInfo && (
              <div className="text-xs text-zinc-400 font-mono rounded-lg border border-zinc-800 p-3">
                bridge: {bridgeInfo.status || '—'}
                {bridgeInfo.presupuesto_identificador ? ` · ${bridgeInfo.presupuesto_identificador}` : ''}
                {bridgeInfo.budget_total != null ? ` · total ${Number(bridgeInfo.budget_total).toLocaleString()}` : ''}
                {bridgeInfo.partidas != null ? ` · partidas ${bridgeInfo.partidas}` : ''}
                {bridgeInfo.message ? ` · ${bridgeInfo.message}` : ''}
              </div>
            )}
            <div className="grid md:grid-cols-3 gap-2">
              <label className="text-xs text-zinc-400 flex flex-col gap-1">Convocante (editable)
                <input value={economicDraft.authority} onChange={(e) => setEconomicDraft((d) => ({ ...d, authority: e.target.value }))} className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm" placeholder="Autoridad / dependencia" />
              </label>
              <label className="text-xs text-zinc-400 flex flex-col gap-1 md:col-span-2">Objeto (editable)
                <input value={economicDraft.object} onChange={(e) => setEconomicDraft((d) => ({ ...d, object: e.target.value }))} className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm" placeholder="Objeto de la proposición" />
              </label>
              <label className="text-xs text-zinc-400 flex flex-col gap-1">Monto total borrador (referencia)
                <input value={economicDraft.budget_total} onChange={(e) => setEconomicDraft((d) => ({ ...d, budget_total: e.target.value }))} className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm" placeholder="Desde presupuesto" />
              </label>
            </div>
            <p className="text-[11px] text-zinc-500">Fuente de verdad del catálogo/APU: presupuesto programable en DB. Si el monto no cuadra, corrige partidas allá.</p>
          </section>

          <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 space-y-4">
            <h3 className="font-semibold text-zinc-200">2c. Checklist de formatos (case pack)</h3>
            <p className="text-xs text-zinc-500">Marca LISTO o EDITADO solo cuando hayas revisado. Obligatorios pendientes bloquean compilar.</p>
            {!formatChecklist.length && <p className="text-sm text-zinc-500">Selecciona un case pack o usa el fallback económico en modo LICITANTE.</p>}
            <div className="space-y-2">
              {formatChecklist.map((f) => (
                <div key={f.code} className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3 flex flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-2 justify-between">
                    <div className="text-sm text-zinc-200">
                      <span className="font-mono text-cyan-300">{f.code}</span>
                      <span className="mx-2 text-zinc-500">·</span>
                      {f.title}
                      <span className="ml-2 text-[10px] uppercase tracking-wide text-zinc-500">{f.category}{f.required ? ' · obligatorio' : ''}</span>
                    </div>
                    <select value={f.status} onChange={(e) => updateFormatItem(f.code, { status: e.target.value as any })} className="rounded-md bg-zinc-900 border border-zinc-700 px-2 py-1 text-xs">
                      <option value="PENDIENTE">PENDIENTE</option>
                      <option value="REVISADO">REVISADO</option>
                      <option value="EDITADO">EDITADO</option>
                      <option value="LISTO">LISTO</option>
                    </select>
                  </div>
                  <input value={f.notes} onChange={(e) => updateFormatItem(f.code, { notes: e.target.value })} className="rounded-md bg-zinc-950 border border-zinc-800 px-2 py-1 text-xs text-zinc-300" placeholder="Notas / correcciones del formato" />
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 space-y-4">
            <h3 className="font-semibold text-zinc-200">3. Cierre documental</h3>
            <div className="flex flex-wrap gap-2">
              <button disabled={busy || !!findings.length} onClick={compile} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-zinc-700 hover:bg-zinc-800 disabled:opacity-40"><FileCheck2 className="w-4 h-4" /> Compilar documentos</button>
              <button disabled={busy || tender.state !== 'READY_FOR_HUMAN_REVIEW'} onClick={approve} className="px-3 py-2 rounded-lg bg-emerald-500/15 border border-emerald-500/25 text-emerald-300 disabled:opacity-40">Aprobar</button>
              <button disabled={busy || tender.state !== 'HUMAN_APPROVAL'} onClick={buildSubmission} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-500/15 border border-amber-500/25 text-amber-300 disabled:opacity-40"><FileArchive className="w-4 h-4" /> Construir submission</button>
              <button disabled={busy || tender.state !== 'SUBMISSION_READY'} onClick={downloadSubmission} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-zinc-700 hover:bg-zinc-800 disabled:opacity-40"><Download className="w-4 h-4" /> Descargar paquete</button>
            </div>
            {artifacts.map(a => <div key={a.id} className="text-xs text-zinc-400 font-mono">{a.code} · v{a.version} · {a.content_hash}</div>)}
          </section>
        </>
      )}

      {error && <div className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-300">{error}</div>}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4"><div className="text-xs text-zinc-500">{label}</div><div className="mt-1 text-sm font-semibold text-zinc-200 truncate">{value}</div></div>;
}
