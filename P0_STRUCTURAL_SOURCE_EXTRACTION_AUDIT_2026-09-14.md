# Megalodon — P0 Structural Source Extraction Audit

## Honest status
The previous V2 source-extraction implementation was deliberately conservative but was still scaffolding-level in one critical sense: it mainly recognized configured headings and numbered lines. It was not sufficient for a production-grade document-engineering extractor.

This revision replaces that limitation with real deterministic document-structure extraction primitives:

- PDF text layer with page references.
- PDF table extraction through `pdfplumber`.
- OCR fallback for scanned PDF pages using `pdf2image` + `pytesseract`.
- DOCX paragraphs and table cells.
- XLSX sheets, rows and cell coordinates.
- Explicit official identifiers when present.
- Explicit mandatory fields only when the source/table contains a configured field.
- Source references carrying document/version/revision/page/section/table/row/cell/field/original text.
- Deterministic `MODIFICA`, `SUSTITUYE`, `ACLARA` relation detection.
- Relations require an explicit target identifier; unresolved relations are never applied automatically.
- Dependency/flow/format configuration remains data-driven and does not create legal obligations.

## No AI
The extraction path contains no OpenAI/Anthropic/LLM/embedding/semantic-similarity path. OCR is mechanical character recognition and is treated as extraction evidence, not as an authority generator.

## TenderRequirement provenance
Effective requirements can be materialized from:
1. a confirmed candidate extracted from a client-supplied official source; or
2. an explicit human edit in the client's editable Workspace, with tenant/document/version validation.

The Workspace path is intentionally preserved because the Workspace is an authorized human proposal-editing layer.

Normative engines may validate, warn, justify, or provide reference. They do not construct proposal requirements.

## Remaining production work
Exact dependency/format extraction contracts must be calibrated against representative official source files for CONAGUA, SICT, CFE, federal, communications/roads, school infrastructure, state/municipal and private/remodeling flows. The engine is real; exact templates should be derived from actual source layouts, not invented in code.
