# Frontend ↔ Backend Alignment Closure — 2026-08-11

## Scope verified
The legacy `licitaciones-obra` interface is aligned with explicit backend workspace endpoints backed by the existing `LicitacionService`, deterministic technical/economic engines, `ContratoService`, persisted `EntregableContrato` records and the real contract state machine.

## Business behavior now exposed
- Planning uses the actual `Licitacion` aggregate and persists type of work/funding in its real participation rules.
- Proposals are read from tenant-scoped persisted `Proposicion` records.
- Technical/economic evaluation executes real engines over persisted proposal envelopes and persists `EvaluacionLicitacion` results.
- Award/fallo uses the existing `LicitacionService.emitir_fallo`.
- Contract creation uses the actual `ContratoService` and requires an admitted proposal.
- Estimates use persisted `EntregableContrato` records; approval updates real contract physical/financial progress.
- Contract termination is now a guarded business operation: the contract must be VIGENTE, have at least one deliverable, have all deliverables approved, and report 100% physical and financial progress.
- Finiquito remains a separate terminal operation and only runs for TERMINADO/RESCINDIDO contracts.
- Procurement approval roles are derived from jurisdiction policy or the real application role `revisor`; the UI no longer exposes a synthetic free-form role by default.

## Frontend exposure boundary
The UI shows business state, blockers, requirements, evidence, artifacts, evaluation outcomes, contract milestones and the next permitted action. It does not expose raw DB state, internal worker payloads, storage implementation details or canonical JSON internals as an operator-facing contract.

## Regression boundary
No existing CostOS, CPM, BIM, Topography, Monte Carlo, Fallo or PreFall engine was replaced. The legacy routes are preserved; new bridge routes orchestrate existing services and models instead of duplicating their domain logic.

## Verification
- All changed backend Python modules compile successfully.
- Full backend tree compiles successfully.
- Only 14 code files differ from the immediately previous baseline, all within the affected Procurement/UI/Contract boundary.
- Archive is rebuilt from the complete source tree after removing generated Python caches and transient TypeScript build metadata.
- Frontend package install/build requires a clean dependency environment; this sandbox's extracted `node_modules` is incomplete and is not used as evidence of a production build failure.
