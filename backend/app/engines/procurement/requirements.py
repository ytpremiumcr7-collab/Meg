from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class MinedRequirement:
    code: str
    category: str
    description: str
    mandatory: bool
    condition: dict[str, Any]
    source_reference: dict[str, Any]
    evidence_required: list[str]
    artifact_required: list[str]
    severity: str
    validator_code: str | None
    approver_role: str | None


class ProcurementRequirementMapper:
    """Maps requirements ONLY from the effective tender evidence supplied by the user.

    LegalRule/corpus data is deliberately not consulted here.  A tender requirement
    is authoritative only when it has evidence in the current tender package.
    Normative cross-checking belongs to the isolated normative/pre-fall layer.
    """

    def derive(
        self,
        *,
        tender_id: Any,
        source_texts: Iterable[dict[str, Any]],
        facts: dict[str, Any] | None = None,
    ) -> list[MinedRequirement]:
        _ = tender_id, facts
        result: list[MinedRequirement] = []
        seen: set[str] = set()
        for source in source_texts:
            # Extraction stage may provide structured candidate requirements.
            # Never synthesize an obligation merely because a word appears in text.
            candidates = source.get("requirements") or source.get("extracted_requirements") or []
            if not isinstance(candidates, list):
                raise ValueError("requirements extraídos debe ser una lista.")
            source_ref = {
                "source_id": source.get("source_id"),
                "source_hash": source.get("source_hash"),
                "uri": source.get("uri"),
                "document_id": source.get("document_id"),
                "revision": source.get("revision"),
            }
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    raise ValueError("Cada requisito extraído debe ser un objeto.")
                code = str(candidate.get("code") or "").strip()
                description = str(candidate.get("description") or "").strip()
                if not code or not description:
                    raise ValueError("Un requisito extraído requiere code y description.")
                if code in seen:
                    continue
                evidence = candidate.get("source_reference") or {}
                if not isinstance(evidence, dict):
                    raise ValueError(f"source_reference inválido para {code}.")
                merged_ref = {**source_ref, **evidence, "authority": "TENDER_SOURCE"}
                result.append(MinedRequirement(
                    code=code,
                    category=str(candidate.get("category") or "ADMINISTRATIVO").upper(),
                    description=description,
                    mandatory=bool(candidate.get("mandatory", True)),
                    condition=dict(candidate.get("condition") or {}),
                    source_reference=merged_ref,
                    evidence_required=[str(x) for x in candidate.get("evidence_required", [])],
                    artifact_required=[str(x) for x in candidate.get("artifact_required", [])],
                    severity=str(candidate.get("severity") or "BLOCKER").upper(),
                    validator_code=str(candidate["validator_code"]) if candidate.get("validator_code") else None,
                    approver_role=str(candidate["approver_role"]) if candidate.get("approver_role") else None,
                ))
                seen.add(code)
        return result
