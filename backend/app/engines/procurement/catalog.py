"""Catálogo de procurement — labels y case packs desde DB.

Los dicts PROCEDURES / CONTRACT_TYPES / etc. ya NO son autoridad de runtime.
Se cargan de catalog_terms. Si el dominio está vacío → dict vacío (fail-closed
de vocabulario; el API puede reportarlo).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import CatalogTerm, JurisdictionProfile, LegalRule

# Dominios canónicos (códigos de dominio, no labels)
CATALOG_DOMAINS = (
    "PROCEDURES",
    "CONTRACT_TYPES",
    "EVALUATION_CRITERIA",
    "PROJECT_TYPES",
    "FUNDING_SOURCES",
    "OBJECT_CLASSES",
    "LEGAL_REGIMES",
    "SCOPE_SCALES",
)


async def load_catalog_terms(
    db: AsyncSession,
    *,
    tenant_id,
    domain: str | None = None,
) -> dict[str, dict[str, str]]:
    """Return { domain: { code: label } } from catalog_terms.

    Tenant override wins over global (tenant_id NULL).
    """
    q = select(CatalogTerm).where(
        CatalogTerm.active.is_(True),
        or_(CatalogTerm.tenant_id == tenant_id, CatalogTerm.tenant_id.is_(None)),
    )
    if domain:
        q = q.where(CatalogTerm.domain == domain.upper())
    rows = (
        await db.execute(
            q.order_by(
                CatalogTerm.domain.asc(),
                CatalogTerm.sort_order.asc(),
                CatalogTerm.code.asc(),
                CatalogTerm.tenant_id.desc().nullslast(),
            )
        )
    ).scalars().all()

    out: dict[str, dict[str, str]] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.domain.upper(), row.code.upper())
        if key in seen:
            continue  # tenant row already preferred by order
        seen.add(key)
        out.setdefault(row.domain.upper(), {})[row.code.upper()] = row.label
    return out


async def load_domain_map(
    db: AsyncSession,
    *,
    tenant_id,
    domain: str,
) -> dict[str, str]:
    all_maps = await load_catalog_terms(db, tenant_id=tenant_id, domain=domain)
    return all_maps.get(domain.upper(), {})


def _normalize_pack(raw: dict[str, Any], *, jurisdiction_code: str) -> dict[str, Any] | None:
    code = str(raw.get("code") or "").strip().upper()
    if not code:
        return None
    artifacts = []
    for item in raw.get("artifacts") or []:
        if not isinstance(item, dict):
            continue
        acode = str(item.get("code") or "").strip()
        if not acode:
            continue
        artifacts.append(
            {
                "code": acode,
                "title": str(item.get("title") or acode),
                "category": str(item.get("category") or "TECNICO").upper(),
                "source_marker": str(item.get("source_marker") or acode),
                "required": bool(item.get("required", True)),
                "requires_uploaded_template": bool(item.get("requires_uploaded_template", False)),
                "description": str(item.get("description") or ""),
            }
        )
    return {
        "code": code,
        "name": str(raw.get("name") or code),
        "jurisdiction_code": str(raw.get("jurisdiction_code") or jurisdiction_code).upper(),
        "project_type": str(raw.get("project_type") or "").upper() or None,
        "description": str(raw.get("description") or ""),
        "artifacts": artifacts,
    }


async def load_case_packs(
    db: AsyncSession,
    *,
    tenant_id,
    jurisdiction_code: str | None = None,
) -> list[dict[str, Any]]:
    """Case packs desde JurisdictionProfile.templates['case_packs'] + LegalRule."""
    query = select(JurisdictionProfile).where(
        JurisdictionProfile.active.is_(True),
        or_(JurisdictionProfile.tenant_id == tenant_id, JurisdictionProfile.tenant_id.is_(None)),
    )
    if jurisdiction_code:
        query = query.where(JurisdictionProfile.code == str(jurisdiction_code).upper())
    profiles = (
        await db.execute(query.order_by(JurisdictionProfile.tenant_id.desc().nullslast()))
    ).scalars().all()

    packs: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        templates = profile.templates or {}
        raw_packs = templates.get("case_packs") or []
        if isinstance(raw_packs, dict):
            raw_packs = list(raw_packs.values())
        for raw in raw_packs:
            if not isinstance(raw, dict):
                continue
            normalized = _normalize_pack(raw, jurisdiction_code=profile.code)
            if normalized is None:
                continue
            packs[normalized["code"]] = normalized

        rules = (
            await db.execute(
                select(LegalRule).where(
                    LegalRule.active.is_(True),
                    LegalRule.jurisdiction_code == profile.code,
                    or_(LegalRule.tenant_id == tenant_id, LegalRule.tenant_id.is_(None)),
                )
            )
        ).scalars().all()
        derived_artifacts: dict[str, dict[str, Any]] = {}
        for rule in rules:
            req = rule.requirement or {}
            for code in req.get("artifact_required") or []:
                acode = str(code).strip()
                if not acode:
                    continue
                derived_artifacts.setdefault(
                    acode,
                    {
                        "code": acode,
                        "title": str(req.get("description") or acode),
                        "category": str(req.get("category") or rule.domain or "TECNICO").upper(),
                        "source_marker": str(req.get("source_marker") or acode),
                        "required": bool(req.get("mandatory", True)),
                        "requires_uploaded_template": False,
                        "description": str(req.get("description") or ""),
                    },
                )
        generic_code = f"GENERIC_{profile.code}"
        if derived_artifacts and generic_code not in packs:
            packs[generic_code] = {
                "code": generic_code,
                "name": f"Paquete derivado — {profile.authority}",
                "jurisdiction_code": profile.code,
                "project_type": None,
                "description": (
                    "Artefactos derivados de LegalRule.artifact_required para esta jurisdicción."
                ),
                "artifacts": list(derived_artifacts.values()),
            }

    return list(packs.values())


async def get_case_pack(
    db: AsyncSession,
    *,
    tenant_id,
    code: str | None,
) -> dict[str, Any] | None:
    if not code:
        return None
    packs = await load_case_packs(db, tenant_id=tenant_id)
    needle = str(code).upper()
    for pack in packs:
        if pack["code"] == needle:
            return pack
    return None


async def get_configured_case_pack(
    db: AsyncSession, *, tenant_id, jurisdiction_code: str, code: str | None
) -> dict[str, Any] | None:
    """Return only a case pack explicitly configured in the selected profile.

    This is the safe path for proposal compilation: LegalRule/corpus-derived
    artifacts are deliberately excluded from the primary elaboration flow.
    """
    if not code:
        return None
    query = select(JurisdictionProfile).where(
        JurisdictionProfile.active.is_(True),
        JurisdictionProfile.code == str(jurisdiction_code).upper(),
        or_(JurisdictionProfile.tenant_id == tenant_id, JurisdictionProfile.tenant_id.is_(None)),
    ).order_by(JurisdictionProfile.tenant_id.desc().nullslast())
    profile = await db.scalar(query)
    if profile is None:
        return None
    for raw in (profile.templates or {}).get("case_packs") or []:
        if isinstance(raw, dict) and str(raw.get("code") or "").upper() == str(code).upper():
            return _normalize_pack(raw, jurisdiction_code=profile.code)
    return None


async def case_packs_for_jurisdiction(
    db: AsyncSession,
    *,
    tenant_id,
    jurisdiction_code: str,
) -> list[dict[str, Any]]:
    return await load_case_packs(db, tenant_id=tenant_id, jurisdiction_code=jurisdiction_code)


async def build_catalog_payload(
    db: AsyncSession,
    *,
    tenant_id,
) -> dict[str, Any]:
    """Vocabularios listos para /procurement/catalog (sin perfiles)."""
    maps = await load_catalog_terms(db, tenant_id=tenant_id)
    missing = [d for d in CATALOG_DOMAINS if not maps.get(d)]
    return {
        "procedures": maps.get("PROCEDURES", {}),
        "contract_types": maps.get("CONTRACT_TYPES", {}),
        "evaluation_criteria": maps.get("EVALUATION_CRITERIA", {}),
        "project_types": maps.get("PROJECT_TYPES", {}),
        "scope_scales": maps.get("SCOPE_SCALES", {}),
        "funding_sources": maps.get("FUNDING_SOURCES", {}),
        "object_classes": maps.get("OBJECT_CLASSES", {}),
        "legal_regimes": maps.get("LEGAL_REGIMES", {}),
        "vocabulary_complete": len(missing) == 0,
        "vocabulary_missing_domains": missing,
    }
