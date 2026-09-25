# Copyright © 2026 Cristian Rodriguez
# All rights reserved.

"""
Bootstrap de tests — settings mínimas inyectadas ANTES de importar app.main.

app.config.Settings exige DATABASE_URL, REDIS_URL, CELERY_BROKER_URL,
CELERY_RESULT_BACKEND y SECRET_KEY. Sin estas variables, la recolección de
tests truena antes de empezar. Este módulo las inyecta vía os.environ antes
de que cualquier import de app.* las lea.
"""

import os

# ─── Settings de prueba (inyectadas antes de cualquier import de app.*) ──
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./.pytest_megalodon_test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/14")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/13")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-long-1234567890ab")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("LOG_LEVEL", "ERROR")
os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "")
os.environ.setdefault("TEZCATLIPOCA_DATABASE_URL", os.environ["DATABASE_URL"])

# Ahora sí importar app.main
import pytest
import pytest_asyncio
from uuid import uuid4
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models.base import Base
from app.core.deps import get_db
from tezcatlipoca.db.models import Base as TezBase

TEST_DATABASE_URL = os.environ["DATABASE_URL"]

engine_test = create_async_engine(TEST_DATABASE_URL, echo=False)
AsyncSessionLocalTest = sessionmaker(engine_test, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with AsyncSessionLocalTest() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(TezBase.metadata.create_all)

    yield

    async with engine_test.begin() as conn:
        await conn.run_sync(TezBase.metadata.drop_all)
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def db_session():
    async with AsyncSessionLocalTest() as session:
        yield session


def _make_unique_email(email: str) -> str:
    local, at, domain = email.partition("@")
    suffix = uuid4().hex[:8]
    if not at:
        return f"{email}-{suffix}"
    return f"{local}+{suffix}@{domain}"


async def _create_tenant_and_user(
    db_session: AsyncSession,
    tenant_slug: str,
    email: str,
    password: str = "testpass123",
    role=None,
):
    from app.models.user import Tenant, User, UserRole as _UserRole
    from app.services.auth_service import AuthService

    role = role or _UserRole.TECNICO

    unique_slug = f"{tenant_slug}-{uuid4().hex[:8]}"
    tenant = Tenant(name=tenant_slug, slug=unique_slug, is_active=True)
    db_session.add(tenant)
    await db_session.flush()

    auth_service = AuthService(db_session)
    unique_email = _make_unique_email(email)
    user = User(
        email=unique_email,
        hashed_password=auth_service.hash_password(password),
        full_name=f"Test User {unique_email}",
        role=role,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(user)
    return tenant, user


async def _login(async_client: AsyncClient, email: str, password: str = "testpass123") -> dict:
    response = await async_client.post("/api/v1/auth/login", data={
        "username": email,
        "password": password,
    })
    assert response.status_code == 200, (
        f"Login de test falló ({response.status_code}): {response.text}"
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def tenant_a_user(db_session: AsyncSession):
    tenant, user = await _create_tenant_and_user(
        db_session, "tenant-a-test", "usera@tenant-a-test.mx"
    )
    return tenant, user


@pytest_asyncio.fixture
async def tenant_b_user(db_session: AsyncSession):
    tenant, user = await _create_tenant_and_user(
        db_session, "tenant-b-test", "userb@tenant-b-test.mx"
    )
    return tenant, user


@pytest_asyncio.fixture
async def auth_headers(async_client: AsyncClient, tenant_a_user):
    _, user = tenant_a_user
    return await _login(async_client, user.email)
