"""Known quantities remain costed; missing quantities require traceable completion."""
from uuid import uuid4
from decimal import Decimal
import pytest
from app.models.bim import ElementoBIM
from app.models.catalogo_apu import CatalogoAPU
from app.services.bim_service import BIMService
from app.services.presupuesto_service import PresupuestoService
from app.core.errors import MegalodonException
from tests.integration.test_bim_regressions import model, PARAMS


@pytest.mark.asyncio
async def test_partial_group_keeps_measured_cost_and_manual_completion_is_traceable(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    known = ElementoBIM(modelo_id=obj.id,global_id=uuid4().hex,express_id=1,tipo='IfcWall',volumen=2.4)
    missing = ElementoBIM(modelo_id=obj.id,global_id=uuid4().hex,express_id=2,tipo='IfcWall')
    apu = CatalogoAPU(tenant_id=tenant.id,clave='TEST',descripcion='Synthetic wall',tipo='CONCEPTO',unidad=' m3 ',precio_unitario=125,fuente='TEST_SYNTHETIC')
    db_session.add_all([known,missing,apu]); await db_session.commit()
    service = BIMService(db_session,tenant.id)
    options = dict(modelo_id=obj.id,expediente_id=exp.id,parametros_costeo=PARAMS,mapeo_catalogo={'IfcWall':apu.id})
    partial = await service.crear_presupuesto_desde_bim(**options)
    assert partial.monto_total == Decimal('300.00')
    assert sorted(p.cantidad for p in partial.partidas) == [0,Decimal('2.4000')]
    assert partial.estado == 'BORRADOR'
    assert partial.metadatos['bim_cobertura']['elementos_pendientes'] == [str(missing.id)]
    from io import BytesIO
    from openpyxl import load_workbook
    exported = await PresupuestoService(db_session,tenant.id).generar_excel(partial.id,exp.id)
    workbook = load_workbook(BytesIO(exported))
    assert 'PARCIAL' in workbook.active['A1'].value
    assert str(missing.id) in workbook.active['B4'].value
    with pytest.raises(MegalodonException):
        await PresupuestoService(db_session,tenant.id).cambiar_estado(partial.id,exp.id,'CALCULADO')
    # Even manually increasing the pending line cannot erase the coverage evidence.
    partial.partidas[1].cantidad = 1
    partial.partidas[1].importe = 125
    await db_session.commit()
    with pytest.raises(MegalodonException):
        await PresupuestoService(db_session,tenant.id).cambiar_estado(partial.id,exp.id,'CALCULADO')
    capture = {'elemento_id':missing.id,'unidad':'m3','cantidad':1.6,'referencia':'Levantamiento de obra revisado'}
    complete = await service.crear_presupuesto_desde_bim(**options,cantidades_complementarias=[capture],creado_por_id=user.id)
    assert complete.monto_total == Decimal('500.00')
    assert complete.estado == 'CALCULADO'
    assert complete.metadatos['bim_cobertura']['completa'] is True
    assert complete.metadatos['bim_cobertura']['capturas'][0]['usuario_id'] == str(user.id)
    assert missing.volumen is None  # Original IFC evidence is preserved.
    for operation in [lambda:PresupuestoService(db_session,tenant.id).actualizar_cantidad_partida(
            complete.id,exp.id,complete.partidas[0].id,5),
        lambda:PresupuestoService(db_session,tenant.id).eliminar_partida(complete.id,exp.id,complete.partidas[0].id)]:
        with pytest.raises(MegalodonException): await operation()
    await PresupuestoService(db_session,tenant.id).cambiar_estado(complete.id,exp.id,'VALIDADO')
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.models.programacion import ActividadPrograma
    program = await service.generar_actividades_4d(modelo_id=obj.id,expediente_id=exp.id,
        fecha_inicio=datetime(2026,10,6,tzinfo=timezone.utc),dias_por_defecto=5,
        creado_por_id=user.id,tenant_id=tenant.id)
    activities = (await db_session.scalars(select(ActividadPrograma).where(ActividadPrograma.programa_id==program.id))).all()
    assert sum(a.costo_presupuestado for a in activities) == Decimal('500.00')
    for invalid in [dict(capture,unidad='m2'),dict(capture,elemento_id=uuid4()),dict(capture,elemento_id=known.id)]:
        with pytest.raises(MegalodonException):
            await service.crear_presupuesto_desde_bim(**options,cantidades_complementarias=[invalid],creado_por_id=user.id)


@pytest.mark.asyncio
async def test_non_geometric_catalog_unit_needs_reviewed_quantity(db_session,tenant_a_user):
    tenant,user = tenant_a_user
    exp,obj = await model(db_session,tenant,user)
    element = ElementoBIM(modelo_id=obj.id,global_id=uuid4().hex,express_id=1,tipo='IfcBeam',volumen=2)
    apu = CatalogoAPU(tenant_id=tenant.id,clave='KG',descripcion='Steel synthetic',tipo='CONCEPTO',unidad='kg',precio_unitario=20,fuente='TEST_SYNTHETIC')
    db_session.add_all([element,apu]); await db_session.commit()
    budget = await BIMService(db_session,tenant.id).crear_presupuesto_desde_bim(
        modelo_id=obj.id,expediente_id=exp.id,parametros_costeo=PARAMS,mapeo_catalogo={'IfcBeam':apu.id},
        creado_por_id=user.id,cantidades_complementarias=[{'elemento_id':element.id,'unidad':'kg','cantidad':7.5,'referencia':'Lista de acero revisada'}])
    assert budget.monto_total == Decimal('150.00')
    assert budget.metadatos['bim_cobertura']['completa'] is True
