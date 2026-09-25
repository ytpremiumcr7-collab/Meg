from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.engines.costos.parametros import (
    FuenteParametrosCosteo,
    ParametrosCosteoSnapshot,
    verificar_snapshot_almacenado,
)
from app.schemas.costos import ParametrosCosteoInput
from app.schemas.procurement.schemas import ProcurementEconomicModel


def test_snapshot_is_stable_and_deeply_immutable():
    evidence = {"documento": {"paginas": [3, 4]}}
    snapshot = ParametrosCosteoSnapshot(
        Decimal("0.12"), Decimal("0.08"), Decimal("0.16"), Decimal("0.02"),
        FuenteParametrosCosteo.CONTRATO, "Contrato OBRA-2026-17, anexo económico",
        evidencia=evidence,
    )
    first = snapshot.to_dict()
    assert snapshot.to_dict() == first
    assert len(first["sha256"]) == 64
    assert ParametrosCosteoSnapshot.from_dict(first).to_dict() == first
    evidence["documento"]["paginas"].append(5)
    assert snapshot.to_dict() == first
    with pytest.raises(TypeError):
        snapshot.evidencia["documento"] = {}  # type: ignore[index]
    with pytest.raises(AttributeError):
        snapshot.evidencia["documento"]["paginas"].append(5)


def test_snapshot_rejects_invalid_values():
    with pytest.raises(ValueError, match="referencia"):
        ParametrosCosteoSnapshot(
            Decimal("0.15"), Decimal("0.10"), Decimal("0.16"), Decimal("0"),
            FuenteParametrosCosteo.CAPTURA_USUARIO, "   ",
        )
    with pytest.raises(ValueError, match="4 decimales"):
        ParametrosCosteoSnapshot(
            Decimal("0.12345"), Decimal("0"), Decimal("0"), Decimal("0"),
            FuenteParametrosCosteo.CAPTURA_USUARIO, "prueba",
        )


def test_stored_snapshot_rejects_tampering_and_column_drift():
    snapshot = ParametrosCosteoSnapshot(
        Decimal("0.12"), Decimal("0.08"), Decimal("0.16"), Decimal("0.02"),
        FuenteParametrosCosteo.CONTRATO, "Contrato OBRA-2026-17",
    )
    payload = snapshot.to_dict()
    factores = (Decimal("0.12"), Decimal("0.08"), Decimal("0.16"), Decimal("0.02"))
    assert verificar_snapshot_almacenado(payload, factores) == snapshot

    manipulado = {**payload, "referencia": "otra fuente"}
    with pytest.raises(ValueError, match="huella"):
        verificar_snapshot_almacenado(manipulado, factores)
    with pytest.raises(ValueError, match="columnas"):
        verificar_snapshot_almacenado(payload, (*factores[:3], Decimal("0.03")))


def test_http_contract_requires_explicit_parameters_and_reference():
    with pytest.raises(ValidationError):
        ParametrosCosteoInput.model_validate({})
    with pytest.raises(ValidationError):
        ParametrosCosteoInput.model_validate({
            "factor_indirecto": 0.15, "factor_utilidad": 0.10,
            "factor_impuesto": 0.16, "factor_riesgo": 0,
            "fuente": "CAPTURA_USUARIO", "referencia": "   ",
        })


def test_procurement_requires_traceable_parameters_when_it_has_items():
    with pytest.raises(ValidationError, match="factor_impuesto"):
        ProcurementEconomicModel.model_validate({
            "partidas": [{"numero": 1}], "factor_indirecto": 0.10, "factor_utilidad": 0.08,
        })
    model = ProcurementEconomicModel.model_validate({
        "partidas": [{"numero": 1}], "factor_indirecto": 0.10,
        "factor_utilidad": 0.08, "factor_impuesto": 0.16,
        "factor_riesgo": 0, "source": "Convocatoria, anexo AE-05",
    })
    assert model.source == "Convocatoria, anexo AE-05"
