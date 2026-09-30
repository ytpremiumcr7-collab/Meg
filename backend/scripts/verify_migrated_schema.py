"""Read-only check of migrated tables/columns before application tests.

Run with: python -m scripts.verify_migrated_schema
Never creates missing tables; a migration gap must fail installation checks.
"""
import asyncio

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401
from app.config import settings
from app.models.base import Base
from tezcatlipoca.db.models import Base as TezBase


def verify(connection):
    inspector = inspect(connection)
    gaps = []
    count = 0
    for metadata in (Base.metadata, TezBase.metadata):
        for table in metadata.tables.values():
            count += 1
            if not inspector.has_table(table.name, schema=table.schema):
                gaps.append(f'{table.name}: missing table')
                continue
            columns = {c['name'] for c in inspector.get_columns(table.name, schema=table.schema)}
            for name in sorted(set(table.columns.keys()) - columns):
                gaps.append(f'{table.name}.{name}: missing column')
    if gaps:
        raise RuntimeError('Migrated schema does not support application models:\n' + '\n'.join(gaps))
    print(f'Migrated schema contains all required columns across {count} tables.')


async def main():
    url = str(settings.DATABASE_URL).replace('postgresql://', 'postgresql+asyncpg://')
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(verify)
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
