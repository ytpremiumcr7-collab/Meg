"""Real HTTP responses used by the project creation screen."""
from uuid import UUID
from datetime import datetime
import pytest
from tests.conftest import _login


@pytest.mark.asyncio
async def test_create_and_list_project_serialize_native_uuid_and_date(async_client,tenant_a_user):
    _,user = tenant_a_user
    headers=await _login(async_client,user.email)
    response=await async_client.post('/api/v1/expedientes',headers=headers,json={
        'titulo':'Obra sintética de contrato HTTP','organo':'CI','unidad_administrativa':'Pruebas',
        'serie_documental':'02100','subserie_documental':'02100-01'})
    assert response.status_code == 200
    item=response.json()
    UUID(item['id']);datetime.fromisoformat(item['created_at'])
    listing=await async_client.get('/api/v1/expedientes',headers=headers)
    assert listing.status_code == 200
    assert any(p['id']==item['id'] for p in listing.json())
    dashboard=await async_client.get('/api/v1/dashboard/stats',headers=headers)
    assert dashboard.status_code == 200
