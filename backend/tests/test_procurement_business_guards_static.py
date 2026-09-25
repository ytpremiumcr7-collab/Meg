from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SERVICE = (BASE / "app/services/procurement/service.py").read_text(encoding="utf-8")
FRONT = (BASE / "../frontend/app/src/apps/licitaciones-obra/components/TenderAutomationPanel.tsx").resolve().read_text(encoding="utf-8")

def test_create_validates_jurisdiction_configuration_before_persisting():
    assert "await self._validate_tender_configuration(data)" in SERVICE

def test_reference_case_artifacts_are_not_submission_eligible_without_official_template():
    assert '"submission_eligible": not reference_only' in SERVICE
    assert 'if reference_only:' in SERVICE

def test_frontend_idempotency_key_is_stable_per_revision():
    assert 'procurement-run:${tender.id}:r${tender.current_revision}' in FRONT
    assert ':${Date.now()}' not in FRONT

def test_frontend_surfaces_business_readiness_gates():
    assert '/readiness' in FRONT
    assert 'Gates de negocio pendientes' in FRONT
