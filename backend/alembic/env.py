# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Configuración de Alembic para migraciones.
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.config import settings
from app.models.base import Base

# BUG ORIGINAL (y BUG RECURRENTE): env.py mantenía una lista manual de
# imports de modelos para poblar Base.metadata antes de autogenerate. Ya
# se había corregido una vez (agregando bim/validador) pero la lista
# volvió a quedarse corta -- le faltaban compliance, licitacion,
# contrato, catalogo_apu, catalogo_conceptos, workflow, rules_engine,
# catalogo_juridico, catalogo_procedimiento, proveedor, entidad,
# audit_ledger, documento, planeacion, notifications, y ahora
# entitlements. Una lista mantenida a mano siempre se puede volver a
# quedar corta. Se importa el paquete completo en su lugar: cualquier
# modelo que app/models/__init__.py registre, Alembic lo ve, sin volver
# a tener que acordarse de actualizar esta lista.
import app.models  # noqa: F401  (el import por su efecto secundario: registra todo en Base.metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url():
    return str(settings.DATABASE_URL).replace("postgresql://", "postgresql+asyncpg://")


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
