"""Real IFC and persisted aggregates: regression cases from the October audit."""
from pathlib import Path
from uuid import uuid4
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errors import MegalodonException
from app.models.bim import ModeloBIM, ElementoBIM
from app.models.presupuesto import Presupuesto, Partida
from app.services.bim_service import BIMService
from app.services.presupuesto_service import PresupuestoService
from app.engines.costos.parametros import ParametrosCosteoSnapshot, FuenteParametrosCosteo
from tests.integration.test_closure_two_tenants import make_expediente

PARAMS = ParametrosCosteoSnapshot(Decimal('0'), Decimal('0'), Decimal('0'), Decimal('0'),
    FuenteParametrosCosteo.CAPTURA_USUARIO, 'Regression fixture')

async def model(db, tenant, user):
    exp = make_expediente(tenant, user)
    db.add(exp)
    await db.flush()
    obj = ModeloBIM(tenant_id=tenant.id, expediente_id=exp.id, identificador=uuid4().hex,
        nombre='Wall', ruta_archivo='fixture.ifc')
    db.add(obj)
    await db.commit()
    return exp, obj

@pytest.mark.asyncio
async def test_reprocessing_preserves_identity_mapping_and_mesh_on_read(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    svc = BIMService(db_session, tenant.id)
    content = (Path(__file__).parents[1] / 'fixtures/ifc/wall_millimetres.ifc').read_bytes()
    await svc.procesar_ifc(modelo_id=obj.id, file_content=content)
    element = (await svc.listar_elementos(obj.id, exp.id, incluir_malla=True))[0]
    original_id, mesh = element.id, list(element.malla_vertices)
    await svc.asignar_zonas_4d(obj.id, exp.id, [{'elemento_id': original_id, 'zona_4d': 'Zone A'}])
    await db_session.commit()
    await svc.procesar_ifc(modelo_id=obj.id, file_content=content)
    elements = await svc.listar_elementos(obj.id, exp.id, incluir_malla=True)
    assert len(elements) == 1
    assert elements[0].id == original_id
    assert elements[0].zona_4d == 'Zone A'
    without_mesh = await svc.listar_elementos(obj.id, exp.id)
    assert without_mesh[0].malla_vertices is None
    await db_session.commit()
    model_id, exp_id = obj.id, exp.id
    db_session.expire_all()
    assert (await svc.listar_elementos(model_id, exp_id, incluir_malla=True))[0].malla_vertices == mesh

@pytest.mark.asyncio
async def test_mapping_rejects_other_tenant_or_expediente_atomically(db_session, tenant_a_user, tenant_b_user):
    tenant, user = tenant_a_user
    other, other_user = tenant_b_user
    exp, obj = await model(db_session, tenant, user)
    exp_other = make_expediente(other, other_user)
    exp_same = make_expediente(tenant, user)
    db_session.add_all([exp_other, exp_same]); await db_session.flush()
    element = ElementoBIM(modelo_id=obj.id, global_id=uuid4().hex, express_id=1, tipo='IfcWall')
    budgets = [Presupuesto(tenant_id=t.id, expediente_id=e.id, identificador=uuid4().hex,
        nombre='Budget', factor_indirecto=0, factor_utilidad=0, factor_impuesto=0)
        for t,e in [(other,exp_other),(tenant,exp_same),(tenant,exp)]]
    db_session.add_all([element,*budgets]); await db_session.flush()
    parts = [Partida(tenant_id=b.tenant_id, presupuesto_id=b.id, numero=1,
        descripcion='Wall',unidad='m2',cantidad=1,precio_unitario=10,importe=10) for b in budgets]
    db_session.add_all(parts); await db_session.commit()
    svc = BIMService(db_session, tenant.id)
    for bad in parts[:2]:
        with pytest.raises(MegalodonException):
            await svc.mapear_a_partidas(obj.id, exp.id, [
                {'elemento_id':element.id,'partida_id':parts[2].id},
                {'elemento_id':element.id,'partida_id':bad.id}])
        assert element.partida_id is None
    assert await svc.mapear_a_partidas(obj.id, exp.id,
        [{'elemento_id':element.id,'partida_id':parts[2].id}]) == 1

@pytest.mark.asyncio
async def test_unpriced_or_missing_quantity_budget_cannot_be_validated(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    db_session.add(ElementoBIM(modelo_id=obj.id, global_id=uuid4().hex, express_id=1, tipo='IfcWall'))
    await db_session.commit()
    budget = await BIMService(db_session, tenant.id).crear_presupuesto_desde_bim(
        modelo_id=obj.id, expediente_id=exp.id, parametros_costeo=PARAMS)
    assert budget.partidas[0].cantidad == 0
    assert budget.estado == 'BORRADOR'
    svc = PresupuestoService(db_session, tenant.id)
    for state in ['CALCULADO','VALIDADO','APROBADO']:
        with pytest.raises(MegalodonException):
            await svc.cambiar_estado(budget.id, exp.id, state)

@pytest.mark.asyncio
async def test_websocket_uses_current_identity_policy(db_session, tenant_a_user, monkeypatch):
    from app.api.v1 import websocket
    from app.services.auth_service import AuthService
    from tests.conftest import AsyncSessionLocalTest
    monkeypatch.setattr(websocket, 'AsyncSessionLocal', AsyncSessionLocalTest)
    tenant, user = tenant_a_user
    token = AuthService(db_session).create_access_token(user.id, user.email, tenant.id, user.role, auth_version=user.auth_version)
    assert await websocket._validar_token_ws(token)
    user.auth_version += 1
    await db_session.commit()
    assert await websocket._validar_token_ws(token) is None
    token = AuthService(db_session).create_access_token(user.id, user.email, tenant.id, user.role, auth_version=user.auth_version)
    user.is_active = False
    await db_session.commit()
    assert await websocket._validar_token_ws(token) is None

@pytest.mark.asyncio
async def test_reader_cannot_mutate_and_module_policy_applies_http(async_client, db_session, tenant_a_user):
    from tests.conftest import _login
    from app.models.entitlements import AppModulo
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    user.role = 'lector'
    await db_session.commit()
    headers = await _login(async_client, user.email)
    base = f'/api/v1/bim/{exp.id}/modelos/{obj.id}'
    assert (await async_client.post(base + '/mapear-partidas', json=[], headers=headers)).status_code == 403
    module = await db_session.scalar(select(AppModulo).where(AppModulo.app_id == 'bim-calculator'))
    module.requiere_plan = 'PRO'
    await db_session.commit()
    try:
        assert (await async_client.get(base, headers=headers)).status_code == 403
    finally:
        module.requiere_plan = None
        await db_session.commit()

@pytest.mark.asyncio
async def test_budget_creation_cannot_bypass_costing_quota(db_session, tenant_a_user):
    from app.models.entitlements import TenantUso
    tenant, user = tenant_a_user
    exp, _ = await model(db_session, tenant, user)
    svc = PresupuestoService(db_session, tenant.id)
    for _ in range(3):
        await svc.crear_desde_costeo(expediente_id=exp.id, nombre='Metered',
            partidas_data=[{'descripcion':'Wall','unidad':'m2','cantidad':1,'precio_unitario':10}],
            parametros_costeo=PARAMS)
    with pytest.raises(MegalodonException) as exc:
        await svc.crear_desde_costeo(expediente_id=exp.id, nombre='Fourth',
            partidas_data=[{'descripcion':'Wall','unidad':'m2','cantidad':1,'precio_unitario':10}],
            parametros_costeo=PARAMS)
    assert exc.value.status_code == 402
    usage = await db_session.scalar(select(TenantUso).where(TenantUso.tenant_id == tenant.id))
    assert usage.corridas_costeo == 3

@pytest.mark.asyncio
async def test_model_uploads_have_immutable_unique_keys_and_queue_failure_visible(db_session, tenant_a_user, monkeypatch):
    from app.services import bim_service
    from app.core.process_queue import encolar_proceso
    class Storage:
        def __init__(self): self.objects = {}
        async def subir(self, path, content, **options):
            assert options['overwrite'] is False
            assert path not in self.objects
            self.objects[path] = content
        async def eliminar(self, paths):
            for path in paths: self.objects.pop(path, None)
    storage = Storage()
    monkeypatch.setattr(bim_service, 'storage_bim', lambda: storage)
    tenant, user = tenant_a_user
    exp, _ = await model(db_session, tenant, user)
    svc = BIMService(db_session, tenant.id)
    a = await svc.crear_modelo(expediente_id=exp.id, nombre='A', file_content=b'A', filename='../same.ifc')
    b = await svc.crear_modelo(expediente_id=exp.id, nombre='B', file_content=b'B', filename='../same.ifc')
    assert a.ruta_archivo != b.ruta_archivo
    assert storage.objects[a.ruta_archivo] == b'A'
    assert storage.objects[b.ruta_archivo] == b'B'
    class UnavailableQueue:
        def delay(self, **kwargs): raise ConnectionError('Broker down')
    with pytest.raises(MegalodonException) as exc:
        await encolar_proceso(db_session, a, UnavailableQueue(),
            estado_field='estado_procesamiento', error_field='error_procesamiento')
    assert exc.value.status_code == 503
    await db_session.refresh(a)
    assert a.estado_procesamiento == 'ERROR'

@pytest.mark.asyncio
async def test_partially_measurable_group_is_pending(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    db_session.add_all([ElementoBIM(modelo_id=obj.id, global_id=uuid4().hex, express_id=i,
        tipo='IfcWall', area=area) for i, area in [(1,16),(2,None)]])
    await db_session.commit()
    budget = await BIMService(db_session, tenant.id).crear_presupuesto_desde_bim(
        modelo_id=obj.id, expediente_id=exp.id, parametros_costeo=PARAMS)
    assert budget.partidas[0].cantidad == 0
    assert budget.estado == 'BORRADOR'

@pytest.mark.asyncio
async def test_database_rejects_cross_expediente_mapping_postgres(db_session, tenant_a_user):
    from sqlalchemy.exc import IntegrityError
    if db_session.get_bind().dialect.name != 'postgresql':
        pytest.skip('Constraint trigger requires PostgreSQL migrations')
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    other = make_expediente(tenant, user)
    db_session.add(other); await db_session.flush()
    budget = Presupuesto(tenant_id=tenant.id, expediente_id=other.id, identificador=uuid4().hex,
        nombre='Other', factor_indirecto=0, factor_utilidad=0, factor_impuesto=0)
    db_session.add(budget); await db_session.flush()
    part = Partida(tenant_id=tenant.id, presupuesto_id=budget.id, numero=1,
        descripcion='Wall',unidad='m2',cantidad=1,precio_unitario=10,importe=10)
    db_session.add(part); await db_session.flush()
    element = ElementoBIM(modelo_id=obj.id, global_id=uuid4().hex, express_id=1, tipo='IfcWall', partida_id=part.id)
    db_session.add(element)
    with pytest.raises(IntegrityError, match='BIM: partida fuera'):
        await db_session.flush()
    await db_session.rollback()
