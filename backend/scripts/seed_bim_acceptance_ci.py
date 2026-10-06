"""Synthetic acceptance identities/catalog in disposable CI staging only."""
import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4


async def main():
    if os.getenv('GITHUB_ACTIONS') != 'true' or os.getenv('ENVIRONMENT') != 'staging':
        raise SystemExit('Seeding is confined to disposable GitHub CI staging.')
    import app.models
    from app.models.base import AsyncSessionLocal, engine
    from app.models.user import Tenant, User, UserRole
    from app.models.catalogo_apu import CatalogoAPU
    from app.services.auth_service import AuthService
    from app.services.entitlements_service import EntitlementsService
    password = uuid4().hex
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name='BIM acceptance (synthetic)', slug='bim-ci-'+uuid4().hex, plan='ENTERPRISE', is_active=True)
        db.add(tenant)
        await db.flush()
        service = AuthService(db)
        users = [User(email=uuid4().hex+'@bim-ci.local', full_name='CI '+role.value,
            role=role, tenant_id=tenant.id, is_active=True, is_verified=True,
            hashed_password=service.hash_password(password)) for role in (UserRole.REVISOR, UserRole.LECTOR)]
        db.add_all(users)
        db.add(CatalogoAPU(tenant_id=tenant.id, clave='CI-WALL-ONLY',
            descripcion='Muro de prueba sintética CI', tipo='CONCEPTO', unidad='m3',
            precio_unitario=125, fuente='CI_SYNTHETIC_NOT_MARKET_PRICE'))
        await db.commit()
        await EntitlementsService(db).sembrar_planes_default()
        await EntitlementsService(db).sembrar_modulos_default()
        destination = Path(os.environ['BIM_ACCEPTANCE_CREDENTIALS'])
        destination.write_text(json.dumps({'reviewer':users[0].email, 'reader':users[1].email,
            'password':password, 'catalog_description':'Muro de prueba sintética CI'}))
        destination.chmod(0o600)
    await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
