"""Saved TIN -> volume persistence, using the real domain service and database."""
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.errors import MegalodonException
from app.models.expediente import ExpedienteObra
from app.models.topografia import CalculoVolumen, Levantamiento, SuperficieTIN
from app.services.topografia_service import TopografiaService


async def surfaces(db, tenant, user):
    exp = ExpedienteObra(
        tenant_id=tenant.id, responsable_id=user.id, identificador=uuid4().hex,
        titulo="TIN regression", organo="Dependencia", unidad_administrativa="UA",
        serie_documental="OBRA", subserie_documental="LICITACION", proyecto_nombre="TIN",
    )
    db.add(exp)
    await db.flush()
    survey = Levantamiento(expediente_id=exp.id, identificador=uuid4().hex, nombre="TIN")
    db.add(survey)
    await db.flush()
    common = dict(
        expediente_id=exp.id, levantamiento_id=survey.id,
        area_plan_m2=1, area_superficie_m2=1, elevacion_min=0,
        elevacion_max=1, elevacion_media=.25, num_puntos=4, num_triangulos=2,
    )
    existing = SuperficieTIN(
        **common, nombre="Existing", malla_vertices=[0,0,1, 1,0,0, 1,1,0, 0,1,0],
        malla_caras=[2,3,1, 1,3,0],
    )
    project = SuperficieTIN(
        **common, nombre="Project", malla_vertices=[0,0,0, 1,0,0, 1,1,0, 0,1,0],
        malla_caras=[0,1,2, 0,2,3],
    )
    db.add_all([existing, project])
    await db.commit()
    return existing, project


@pytest.mark.asyncio
@pytest.mark.parametrize("against_surface", [False, True])
async def test_domain_persists_volume_of_the_saved_faces(db_session, tenant_a_user, against_surface):
    tenant, user = tenant_a_user
    existing, project = await surfaces(db_session, tenant, user)
    args = ({"superficie_proyecto_id": project.id} if against_surface else {"elevacion_referencia": 0})
    calculation = await TopografiaService(db_session, tenant.id).calcular_volumen(
        superficie_existente_id=existing.id, **args,
    )
    await db_session.refresh(calculation)
    assert float(calculation.volumen_corte_m3) == .167
    assert float(calculation.volumen_terraplen_m3) == 0
    assert float(calculation.area_analizada_m2) == 1


@pytest.mark.asyncio
async def test_domain_does_not_persist_success_for_corrupt_faces(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    existing, _ = await surfaces(db_session, tenant, user)
    existing.malla_caras = [0, 1, 9]
    await db_session.commit()
    with pytest.raises(MegalodonException):
        await TopografiaService(db_session, tenant.id).calcular_volumen(
            superficie_existente_id=existing.id, elevacion_referencia=0,
        )
    count = await db_session.scalar(select(func.count()).select_from(CalculoVolumen).where(
        CalculoVolumen.superficie_existente_id == existing.id,
    ))
    assert count == 0
