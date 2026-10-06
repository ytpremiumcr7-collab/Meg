"""Synthetic acceptance identities/catalog in disposable CI staging only."""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4


async def main():
    if os.getenv('GITHUB_ACTIONS') != 'true' or os.getenv('ENVIRONMENT') != 'staging':
        raise SystemExit('Seeding is confined to disposable GitHub CI staging.')
    from sqlalchemy.engine import make_url
    url = make_url(os.environ['DATABASE_URL'])
    if url.database != 'bim_acceptance' or url.host not in ('localhost','127.0.0.1'):
        raise SystemExit('Dedicated local acceptance database required.')
    import app.models
    from app.models.base import AsyncSessionLocal, engine
    from app.models.user import Tenant, User, UserRole
    from app.models.catalogo_apu import CatalogoAPU
    from app.services.auth_service import AuthService
    from app.services.entitlements_service import EntitlementsService
    if len(sys.argv) == 3 and sys.argv[1] == '--programs-for':
        from sqlalchemy import select
        from app.models.expediente import ExpedienteObra
        from app.services.programacion_service import ProgramacionService
        credentials = json.loads(Path(os.environ['BIM_ACCEPTANCE_CREDENTIALS']).read_text())
        async with AsyncSessionLocal() as db:
            user = await db.scalar(select(User).where(User.email == credentials['reviewer']))
            obra = await db.get(ExpedienteObra, UUID(sys.argv[2]))
            if not user or not obra or obra.tenant_id != user.tenant_id:
                raise SystemExit('Acceptance obra ownership required.')
            service = ProgramacionService(db, user.tenant_id)
            for number in range(21):
                await service.crear_programa(expediente_id=obra.id,nombre=f'Programa previo {number}',
                    descripcion='Synthetic acceptance pagination fixture',
                    fecha_inicio=datetime(2026,10,6,tzinfo=timezone.utc),
                    actividades_data=[{'id':'A','nombre':'Actividad previa','duracion':1}],
                    creado_por_id=user.id,tenant_id=user.tenant_id)
        await engine.dispose()
        return
    if len(sys.argv) != 1:
        raise SystemExit('Unsupported acceptance seed arguments.')
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
