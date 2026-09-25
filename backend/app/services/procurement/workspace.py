from __future__ import annotations
from hashlib import sha256
import json
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.errors import ErrorCode, MegalodonException
from app.models.procurement import TenderPackage, TenderDocument, TenderDocumentRevision, TenderRequirement, TenderEvidence, TenderArtifact, TenderLicitacionBridge, BridgeFieldContract
from app.models.licitacion import Licitacion


# FIX P1 auditoría 2026-09-14: contrato por defecto -- se usa SOLO para
# sembrar la tabla bridge_field_contracts (versión 1, global) la primera
# vez que se pide un bridge y no hay ninguna fila todavía. A partir de ahí
# el contrato vive en DB (BridgeFieldContract), no en este literal; un
# operador puede desactivar la v1 y activar una v2 sin tocar código.
# A diferencia del contrato original (solo 3 reglas TENDER_TO_LICITACION),
# éste ya incluye las reglas espejo LICITACION_TO_TENDER -- antes el
# endpoint /bridge/licitacion/{id}/sync aceptaba direction=LICITACION_TO_TENDER
# como válido pero, al no haber ninguna regla con esa dirección, la
# sincronización no hacía absolutamente nada y devolvía 200 igual: un caso
# de "funciona" disfrazado -- la API parecía aceptar la operación cuando en
# realidad era un no-op silencioso.
_DEFAULT_BRIDGE_CONTRACT_FIELDS = [
    {"source": "tender.jurisdiction_code", "target": "licitacion.jurisdiction_code", "direction": "TENDER_TO_LICITACION", "authority": "TenderPackage", "conflict_policy": "FAIL_CLOSED"},
    {"source": "tender.procedure_type", "target": "licitacion.tipo_procedimiento", "direction": "TENDER_TO_LICITACION", "authority": "TenderPackage", "conflict_policy": "FAIL_CLOSED"},
    {"source": "tender.canonical_model.economic.budget_total", "target": "licitacion.monto_estimado", "direction": "TENDER_TO_LICITACION", "authority": "TenderPackage", "conflict_policy": "FAIL_CLOSED"},
    {"source": "licitacion.jurisdiction_code", "target": "tender.jurisdiction_code", "direction": "LICITACION_TO_TENDER", "authority": "Licitacion", "conflict_policy": "FAIL_CLOSED"},
    {"source": "licitacion.tipo_procedimiento", "target": "tender.procedure_type", "direction": "LICITACION_TO_TENDER", "authority": "Licitacion", "conflict_policy": "FAIL_CLOSED"},
    {"source": "licitacion.monto_estimado", "target": "tender.canonical_model.economic.budget_total", "direction": "LICITACION_TO_TENDER", "authority": "Licitacion", "conflict_policy": "FAIL_CLOSED"},
]


def model_hash(model: dict) -> str:
    return sha256(json.dumps(model or {}, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()

class TenderWorkspaceService:
    def __init__(self, db: AsyncSession, user):
        self.db, self.user = db, user

    async def tender(self, tender_id: UUID, lock: bool=False) -> TenderPackage:
        q = select(TenderPackage).where(TenderPackage.id == tender_id, TenderPackage.tenant_id == self.user.tenant_id)
        if lock: q = q.with_for_update()
        row = await self.db.scalar(q)
        if row is None: raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "TenderPackage no encontrado.", 404)
        return row

    async def list_documents(self, tender_id: UUID) -> list[TenderDocument]:
        await self.tender(tender_id)
        return list((await self.db.scalars(select(TenderDocument).where(TenderDocument.tender_id == tender_id, TenderDocument.tenant_id == self.user.tenant_id).order_by(TenderDocument.artifact_code, TenderDocument.version.desc()))).all())

    async def get_document(self, tender_id: UUID, document_id: UUID) -> TenderDocument:
        await self.tender(tender_id)
        row = await self.db.scalar(select(TenderDocument).where(TenderDocument.id == document_id, TenderDocument.tender_id == tender_id, TenderDocument.tenant_id == self.user.tenant_id))
        if row is None: raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Documento de workspace no encontrado.", 404)
        return row

    async def _context(self, tender: TenderPackage, artifact_code: str) -> tuple[list[str], list[str], list[str]]:
        reqs = list((await self.db.scalars(select(TenderRequirement).where(TenderRequirement.tender_id == tender.id, TenderRequirement.tenant_id == self.user.tenant_id))).all())
        evid = list((await self.db.scalars(select(TenderEvidence).where(TenderEvidence.tender_id == tender.id, TenderEvidence.tenant_id == self.user.tenant_id))).all())
        related_reqs = [str(r.id) for r in reqs if artifact_code in (r.artifact_required or [])]
        sources = [str(e.id) for e in evid]
        deps = ["canonical_model.facts", "canonical_model.technical", "canonical_model.economic", "canonical_model.schedule"]
        return sources, related_reqs, deps

    async def open_or_create(self, tender_id: UUID, artifact_code: str, name: str, media_type: str="text/plain") -> TenderDocument:
        tender = await self.tender(tender_id)
        row = await self.db.scalar(select(TenderDocument).where(TenderDocument.tender_id == tender.id, TenderDocument.tenant_id == self.user.tenant_id, TenderDocument.artifact_code == artifact_code, TenderDocument.version == 1))
        if row: return row
        sources, reqs, deps = await self._context(tender, artifact_code)
        row = TenderDocument(tenant_id=self.user.tenant_id, creado_por_id=self.user.id, actualizado_por_id=self.user.id, tender_id=tender.id, artifact_code=artifact_code, name=name, media_type=media_type, content_text="", content_model={}, status="DRAFT", version=1, tender_revision=tender.current_revision, generated_from_revision=None, generated_model_hash=None, source_evidence_ids=sources, requirement_ids=reqs, data_dependencies=deps)
        self.db.add(row); await self.db.flush()
        self.db.add(TenderDocumentRevision(tenant_id=self.user.tenant_id, document_id=row.id, version=1, operation="CREATE", content_text="", content_model={}, tender_revision=tender.current_revision, human_modified=False, revision_metadata={"created": True}))
        await self.db.commit(); await self.db.refresh(row); return row

    async def update_document(self, tender_id: UUID, document_id: UUID, *, content_text: str, content_model: dict, expected_row_version: int) -> TenderDocument:
        tender = await self.tender(tender_id, lock=True)
        row = await self.get_document(tender_id, document_id)
        if row.locked or tender.frozen: raise MegalodonException(ErrorCode.CONFLICT, "El documento está bloqueado o el TenderPackage está congelado.", 409)
        if row.row_version != expected_row_version: raise MegalodonException(ErrorCode.CONFLICT, "Conflicto de versión del documento; recarga antes de guardar.", 409)
        row.version += 1; row.content_text = content_text; row.content_model = content_model or {}; row.tender_revision = tender.current_revision; row.human_modified = True; row.status = "DRAFT"; row.actualizado_por_id=self.user.id
        await self.db.flush()
        self.db.add(TenderDocumentRevision(tenant_id=self.user.tenant_id, document_id=row.id, version=row.version, operation="HUMAN_EDIT", content_text=content_text, content_model=content_model or {}, tender_revision=tender.current_revision, source_model_hash=model_hash(tender.canonical_model), human_modified=True, revision_metadata={"expected_row_version": expected_row_version}))
        await self.db.commit(); await self.db.refresh(row); return row

    async def history(self, tender_id: UUID, document_id: UUID) -> list[TenderDocumentRevision]:
        await self.get_document(tender_id, document_id)
        return list((await self.db.scalars(select(TenderDocumentRevision).where(TenderDocumentRevision.document_id == document_id, TenderDocumentRevision.tenant_id == self.user.tenant_id).order_by(TenderDocumentRevision.version.desc()))).all())

    async def regenerate(self, tender_id: UUID, document_id: UUID, *, generated_text: str, generated_model: dict, expected_row_version: int) -> TenderDocument:
        tender = await self.tender(tender_id, lock=True); row = await self.get_document(tender_id, document_id)
        if row.locked or tender.frozen: raise MegalodonException(ErrorCode.CONFLICT, "El documento está bloqueado o el TenderPackage está congelado.", 409)
        current_hash=model_hash(tender.canonical_model)
        if row.row_version != expected_row_version: raise MegalodonException(ErrorCode.CONFLICT, "Conflicto de versión del documento.", 409)
        if row.human_modified and (row.generated_model_hash != current_hash or row.tender_revision != tender.current_revision):
            row.last_conflict={"kind":"HUMAN_EDIT_WOULD_BE_OVERWRITTEN","document_version":row.version,"tender_revision":tender.current_revision,"current_model_hash":current_hash}; await self.db.commit(); raise MegalodonException(ErrorCode.CONFLICT, "Regeneración bloqueada: existe edición humana que podría perderse.", 409)
        row.version += 1; row.content_text=generated_text; row.content_model=generated_model or {}; row.tender_revision=tender.current_revision; row.generated_from_revision=tender.current_revision; row.generated_model_hash=current_hash; row.human_modified=False; row.last_conflict=None; row.status="GENERATED"; row.actualizado_por_id=self.user.id
        await self.db.flush(); self.db.add(TenderDocumentRevision(tenant_id=self.user.tenant_id, document_id=row.id, version=row.version, operation="REGENERATE", content_text=generated_text, content_model=generated_model or {}, tender_revision=tender.current_revision, source_model_hash=current_hash, human_modified=False, revision_metadata={"safe_regeneration": True})); await self.db.commit(); await self.db.refresh(row); return row

    async def lock_document(self, tender_id: UUID, document_id: UUID, locked: bool) -> TenderDocument:
        tender=await self.tender(tender_id, lock=True); row=await self.get_document(tender_id, document_id); row.locked=locked; row.status="VALIDATED" if locked else row.status; row.actualizado_por_id=self.user.id; await self.db.commit(); await self.db.refresh(row); return row

    async def sync_bridge(self, tender_id: UUID, licitacion_id: UUID, *, direction: str, expected_tender_revision: int, expected_licitacion_version: int) -> TenderLicitacionBridge:
        tender = await self.tender(tender_id, lock=True)
        lic = await self.db.scalar(select(Licitacion).where(Licitacion.id == licitacion_id, Licitacion.tenant_id == self.user.tenant_id))
        if lic is None:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Licitacion no encontrada.", 404)
        if lic.expediente_id != tender.expediente_id:
            raise MegalodonException(ErrorCode.CONFLICT, "TenderPackage y Licitacion pertenecen a expedientes distintos.", 409)
        bridge = await self.db.scalar(select(TenderLicitacionBridge).where(
            TenderLicitacionBridge.tenant_id == self.user.tenant_id,
            TenderLicitacionBridge.tender_package_id == tender.id,
            TenderLicitacionBridge.licitacion_id == lic.id,
            TenderLicitacionBridge.active.is_(True),
        ))
        if bridge is None:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Bridge no encontrado; créalo antes de sincronizar.", 404)
        if tender.current_revision != expected_tender_revision or lic.row_version != expected_licitacion_version:
            raise MegalodonException(ErrorCode.CONFLICT, "Conflicto de revisión en el bridge; recarga ambos agregados.", 409)

        mapping = (bridge.field_mapping or {}).get("fields") or []
        if not mapping:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Bridge sin contrato de campos; sincronización bloqueada.", 422)

        def read_path(root: dict, path: str):
            cur = root
            for part in path.split("."):
                if not isinstance(cur, dict) or part not in cur:
                    return None
                cur = cur[part]
            return cur

        def write_path(root: dict, path: str, value):
            parts = path.split(".")
            cur = root
            for part in parts[:-1]:
                cur = cur.setdefault(part, {})
            cur[parts[-1]] = value

        tender_view = {
            "jurisdiction_code": tender.jurisdiction_code,
            "procedure_type": tender.procedure_type,
            "canonical_model": tender.canonical_model or {},
        }
        lic_view = {
            "jurisdiction_code": lic.jurisdiction_code,
            "tipo_procedimiento": lic.tipo_procedimiento,
            "monto_estimado": float(lic.monto_estimado) if lic.monto_estimado is not None else None,
        }

        if direction not in {"TENDER_TO_LICITACION", "LICITACION_TO_TENDER"}:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Dirección de bridge no soportada.", 422)

        changed_tender = False
        changed_lic = False
        for field in mapping:
            if field.get("direction") != direction:
                continue
            source = str(field.get("source", ""))
            target = str(field.get("target", ""))
            authority = field.get("authority")
            if field.get("conflict_policy", "FAIL_CLOSED") != "FAIL_CLOSED":
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Política de conflicto de bridge no permitida.", 422)
            if direction == "TENDER_TO_LICITACION" and not source.startswith("tender."):
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Contrato de bridge inválido: origen TENDER_TO_LICITACION.", 422)
            if direction == "LICITACION_TO_TENDER" and not source.startswith("licitacion."):
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Contrato de bridge inválido: origen LICITACION_TO_TENDER.", 422)
            if authority not in {"TenderPackage", "Licitacion"}:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "Contrato de bridge sin autoridad explícita.", 422)

            src_root = tender_view if direction == "TENDER_TO_LICITACION" else lic_view
            src_path = source.split(".", 1)[1]
            value = read_path(src_root, src_path)
            if direction == "TENDER_TO_LICITACION":
                if target == "licitacion.jurisdiction_code": lic.jurisdiction_code = value; changed_lic = True
                elif target == "licitacion.tipo_procedimiento": lic.tipo_procedimiento = value; changed_lic = True
                elif target == "licitacion.monto_estimado" and value is not None: lic.monto_estimado = value; changed_lic = True
                else: raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"Campo destino de bridge no permitido: {target}", 422)
            else:
                if target == "tender.jurisdiction_code": tender.jurisdiction_code = value; changed_tender = True
                elif target == "tender.procedure_type": tender.procedure_type = str(value) if value else tender.procedure_type; changed_tender = True
                elif target == "tender.canonical_model.economic.budget_total" and value is not None:
                    canonical = dict(tender.canonical_model or {}); economic = dict(canonical.get("economic") or {}); economic["budget_total"] = value; canonical["economic"] = economic; tender.canonical_model = canonical; changed_tender = True
                else: raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, f"Campo destino de bridge no permitido: {target}", 422)

        if changed_tender:
            tender.current_revision += 1
        await self.db.flush()
        bridge.last_tender_revision = tender.current_revision
        bridge.last_licitacion_version = lic.row_version
        bridge.actualizado_por_id = self.user.id
        await self.db.commit()
        await self.db.refresh(bridge)
        return bridge

    async def _contrato_bridge_activo(self) -> BridgeFieldContract:
        """Contrato de campos activo para este tenant (o global si no tiene uno propio).

        FIX P1: antes bridge() escribía el mapping como dict literal en
        Python. Ahora se lee de DB; si no existe ninguno (primer uso en
        todo el sistema), se siembra aquí mismo la v1 -- documentada y
        auditable, no un dict flotando en el código del endpoint.
        """
        row = await self.db.scalar(
            select(BridgeFieldContract)
            .where(BridgeFieldContract.tenant_id == self.user.tenant_id, BridgeFieldContract.is_active == True)  # noqa: E712
            .order_by(BridgeFieldContract.version.desc())
        )
        if row:
            return row
        row = await self.db.scalar(
            select(BridgeFieldContract)
            .where(BridgeFieldContract.tenant_id.is_(None), BridgeFieldContract.is_active == True)  # noqa: E712
            .order_by(BridgeFieldContract.version.desc())
        )
        if row:
            return row
        # Nada sembrado todavía en todo el sistema -- se crea el contrato
        # global v1 ahora, una sola vez.
        row = BridgeFieldContract(
            tenant_id=None, version=1, is_active=True, fields=_DEFAULT_BRIDGE_CONTRACT_FIELDS,
            notes="Contrato global sembrado automáticamente al primer uso.",
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def bridge(self, tender_id: UUID, licitacion_id: UUID, relationship_type="PRIMARY") -> TenderLicitacionBridge:
        tender=await self.tender(tender_id); lic=await self.db.scalar(select(Licitacion).where(Licitacion.id==licitacion_id, Licitacion.tenant_id==self.user.tenant_id));
        if not lic: raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO,"Licitacion no encontrada.",404)
        if lic.expediente_id != tender.expediente_id: raise MegalodonException(ErrorCode.CONFLICT,"TenderPackage y Licitacion pertenecen a expedientes distintos.",409)
        row=await self.db.scalar(select(TenderLicitacionBridge).where(TenderLicitacionBridge.tenant_id==self.user.tenant_id,TenderLicitacionBridge.tender_package_id==tender.id,TenderLicitacionBridge.licitacion_id==lic.id))
        if row: return row
        contrato = await self._contrato_bridge_activo()
        mapping={"version": contrato.version, "contract_id": str(contrato.id), "fields": contrato.fields}
        row=TenderLicitacionBridge(tenant_id=self.user.tenant_id,creado_por_id=self.user.id,actualizado_por_id=self.user.id,tender_package_id=tender.id,licitacion_id=lic.id,expediente_id=tender.expediente_id,relationship_type=relationship_type,field_mapping=mapping,last_tender_revision=tender.current_revision,last_licitacion_version=lic.row_version)
        self.db.add(row); await self.db.commit(); await self.db.refresh(row); return row
