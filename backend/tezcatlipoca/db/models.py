# Copyright © 2026 Cristian Rodriguez
# Tezcatlipoca — Database models (ASYNC, unified with Megalodon runtime)
#
# DECISIÓN DE ARQUITECTURA (2026-08-08):
#   - Un solo runtime, una sola capa async de acceso a datos.
#   - No más create_engine síncrono + sessionmaker dentro del proceso async.
#   - El engine async se deriva de la misma DATABASE_URL que Megalodon.
#   - Si TEZCATLIPOCA_DATABASE_URL no está set, se deriva automáticamente
#     reemplazando +asyncpg por +psycopg2 en la URL de Megalodon — AHORA
#     se hace al revés: la URL de Megalodon YA es asyncpg, así que se usa
#     directamente (o se fuerza +asyncpg si viene con +psycopg2).

import os
from datetime import datetime, timezone
from typing import Optional, List, AsyncGenerator

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, Boolean, JSON, LargeBinary,
    select, delete,
)
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine,
)
from sqlalchemy.orm import declarative_base

# ─── Database URL — unificada con Megalodon ──────────────────────────
# Prioridad: TEZCATLIPOCA_DATABASE_URL > DATABASE_URL (async) > fallback
DATABASE_URL = os.getenv("TEZCATLIPOCA_DATABASE_URL")
if not DATABASE_URL:
    raw = os.getenv("DATABASE_URL")
    if not raw:
        if os.getenv("ENVIRONMENT", "development").lower() == "production":
            raise RuntimeError("DATABASE_URL es obligatorio en producción; no se permite SQLite implícito.")
        raw = "sqlite+aiosqlite:///./megalodon_dev.db"
    # Asegurar que sea async
    if "+psycopg2" in raw:
        DATABASE_URL = raw.replace("+psycopg2", "+asyncpg")
    elif raw.startswith("postgresql://") and "+asyncpg" not in raw:
        DATABASE_URL = raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        DATABASE_URL = raw

POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))

engine_args = {
    "echo": os.getenv("DB_ECHO", "false").lower() == "true",
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}

if DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}
else:
    engine_args.update({"pool_size": POOL_SIZE, "max_overflow": MAX_OVERFLOW})

engine: AsyncEngine = create_async_engine(DATABASE_URL, **engine_args)
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

Base = declarative_base()


class User(Base):
    """User accounts — espejo/caché local sincronizado desde JWT de Megalodon.

    Tabla separada para no colisionar con el `users` de Megalodon.
    """
    __tablename__ = "tezcatlipoca_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    tier = Column(String(20), default="restricted")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    api_calls_today = Column(Integer, default=0)
    api_calls_total = Column(Integer, default=0)
    megalodon_user_id = Column(String(36), unique=True, index=True, nullable=True)
    tenant_id = Column(String(36), index=True, nullable=True)


class UserSession(Base):
    """Active user sessions tracked via httpOnly cookies."""
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    session_token = Column(String(255), unique=True, index=True, nullable=False)
    jti = Column(String(255), nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_active = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)


class Snapshot(Base):
    """Map state snapshots."""
    __tablename__ = "snapshots"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    user_id = Column(Integer, nullable=True)
    tenant_id = Column(String(36), index=True, nullable=True)
    layers = Column(JSON, default=list)
    viewport = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Tunnel(Base):
    """Encrypted tunnel metadata (wormhole router)."""
    __tablename__ = "tunnels"

    id = Column(String(32), primary_key=True)
    tenant_id = Column(String(36), index=True, nullable=False)
    owner_user_id = Column(Integer, nullable=False)
    owner_username = Column(String(255), nullable=True)
    destination = Column(String(512), nullable=False)
    encryption = Column(String(50), default="aes-256-gcm")
    status = Column(String(20), default="active")
    bytes_transferred = Column(Integer, default=0)
    packets = Column(Integer, default=0)
    latency_ms = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)


class DeadDrop(Base):
    """Ephemeral encrypted message (wormhole router, dead-drop pattern)."""
    __tablename__ = "dead_drops"

    id = Column(String(32), primary_key=True)
    tenant_id = Column(String(36), index=True, nullable=False)
    owner_user_id = Column(Integer, nullable=False)
    owner_username = Column(String(255), nullable=True)
    encrypted_payload = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    max_reads = Column(Integer, default=1)
    reads = Column(Integer, default=0)
    status = Column(String(20), default="active")


class ApiLog(Base):
    """API request logs with explicit tenant context for enterprise audit."""
    __tablename__ = "api_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    tenant_id = Column(String(36), index=True, nullable=True)
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    status_code = Column(Integer, nullable=True)
    response_time_ms = Column(Float, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class TokenBlacklist(Base):
    """Revoked JWT tokens."""
    __tablename__ = "token_blacklist"

    id = Column(Integer, primary_key=True, index=True)
    token_jti = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SystemSetting(Base):
    """Persisted system settings."""
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(36), index=True, nullable=True)
    key = Column(String(255), nullable=False, index=True)
    value = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ─── Async DB helpers ────────────────────────────────────────────────

async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Generador de sesión async REAL — para FastAPI Depends()."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db_async():
    """Verify the migrated schema; runtime never owns migration privileges."""
    from scripts.verify_migrated_schema import verify
    async with engine.connect() as connection:
        await connection.run_sync(verify)
