# TenderRequirement — source-grounded call-graph gate

## Invariant

`TenderRequirement` is an **effective proposal requirement**. It may be materialized only from an official source document supplied to the current tender and made effective through the explicit human review/confirmation path.

The normative corpus (`LegalSource -> LegalArticle -> LegalRule` and juridical engines) is a **reference/validation layer**. It may explain, validate, warn, compare, select/recommend a procedure, or attach a cross-reference, but it must not create or silently mutate an effective proposal requirement.

Megalodon is mechanical/deterministic in this path. There is no AI/LLM dependency in source extraction or requirement mapping.

## Backward traversal from `TenderRequirement`

```text
TenderRequirement DB row
    ^
    | construction
    +-- ProcurementService.derive_requirements()
    |       ^
    |       +-- ProcurementService.confirm_requirement_candidates()
    |               ^
    |               +-- TenderEvidence.requirement_candidates
    |                       ^
    |                       +-- ProcurementService.ingest_source()
    |                               ^
    |                               +-- TenderSourceExtractor.extract()
    |                               +-- TenderSourceExtractor.extract_requirement_candidates()
    |                                      ^
    |                                      +-- selected JurisdictionProfile.templates.requirement_extraction
    |                                      +-- dependency / flow / physical format / official format
    |                                      +-- supplied source bytes only
    |
    +-- ProcurementService.add_requirement()
            ^
            +-- now fail-closed:
                requires an ACTIVE SOURCE_DOCUMENT in this tender/tenant
                requires matching extracted candidate
                requires candidate.status == CONFIRMED
                merges source_reference with authority=TENDER_SOURCE
```

## Normative path audit

```text
LegalSource -> LegalArticle -> LegalRule
       |
       +--> JuridicoService / MotorJuridico / SelectorProcedimiento
       |       +--> normative consultation / procedure recommendation
       |       +--> no TenderRequirement construction
       |
       +--> MotorGarantias
       |       +--> deterministic contract guarantee/penalty calculation
       |       +--> no TenderRequirement construction
       |
       +--> ProcurementService catalog / jurisdiction validation
               +--> configuration / validation / readiness
               +--> no TenderRequirement construction
```

The only `TenderRequirement(...)` constructors found under `backend/app` are in `services/procurement/service.py`, in `derive_requirements()` and `add_requirement()`.

No `TenderRequirement` constructor or import was found in the juridical engine/service files audited:

- `engines/juridico/motor_juridico.py`
- `engines/juridico/selector_procedimiento.py`
- `services/juridico_service.py`

## Important distinction: normative references are still allowed

`TenderRequirement` retains `legal_rule_id` / `legal_article_id` for traceability and validation. `add_requirement()` may resolve these references if supplied, but **the source text, description, and existence of the effective requirement come from the confirmed tender source candidate**. A missing or invalid normative reference no longer turns a source-grounded proposal requirement into a corpus-derived requirement.

## Source sufficiency semantics

The pipeline now distinguishes three states:

1. **`OFFICIAL_SOURCE_REQUIRED`** — the user has not supplied a source role required by the selected dependency/flow. This is a user/input blocker.
2. **`EXTRACTION_INCOMPLETE`** — the required source is present, but the mechanical extractor produced no structured candidates. This is an engine/configuration defect, **not** user omission.
3. **`REQUIREMENT_REVIEW_REQUIRED`** — candidates were extracted from supplied official sources but have not yet been confirmed by the user. Megalodon is capable of mapping/elaborating them; human confirmation is the workflow gate.

This prevents the misleading message “no effective requirements confirmed by the user” from being used as a proxy for “the extractor cannot map the source”.

## Extraction architecture

The source extractor is configured per:

- dependency/profile: CONAGUA, SICT, CFE, federal, state, municipal, federal acquisitions, private;
- engineering flow: hydraulic/PTAR, roads/communications, electrical, public works, school infrastructure, acquisitions/services, remodeling/private construction;
- source role: convocatoria, anexo, junta-aclaraciones result, modificación;
- physical format: PDF, DOCX, XLSX;
- official format code when detected;
- document revision/version when explicitly present.

Each candidate carries traceability such as:

`document`, `document_version`, tender `revision`, `page`, `section`, `table`, `row`, `cell`, `field`, `text_original`, source hash/id, extraction method, dependency, flow and format mapping.

The extractor never converts arbitrary legal/corpus text into a requirement. If the configured source structure is absent, it returns zero candidates.

## Current known limitation

The implementation is deliberately conservative. It now has dependency/flow/format-specific deterministic maps and structural locations, but it is not yet a full document-forensics engine. The next hardening layer should add deterministic table semantics, official requirement identifiers, page/worksheet/cell preservation for all supported parsers, and explicit `MODIFIES` / `SUPERSEDES` relations between clarification/addendum evidence and earlier requirements.
