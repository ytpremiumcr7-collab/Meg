"""Baseline: esquema completo (~30 tablas) + invitations

Revision ID: 55225d1e7443
Revises: 06d589924524
Create Date: 2026-08-08 00:00:00.000000

CIERRA EL GAP documentado en 06d589924524 y en 9f3a1c7d2b4e: hasta
ahora no existía ninguna migración que creara el esquema base
(users, tenants, expedientes_obra, documentos, licitaciones,
contratos, compliance, presupuestos, programas_obra, bim, etc.) --
`alembic upgrade head` sobre una base de datos nueva fallaba en cuanto
9f3a1c7d2b4e intentaba tocar tablas que jamás se habían creado por
Alembic.

DECISIÓN DE DISEÑO: en vez de escribir a mano ~30 `op.create_table()`
(alto riesgo de que se desalineen de los modelos reales, que es
justo el tipo de bug que esta auditoría ya encontró dos veces), esta
migración delega en `Base.metadata.create_all()` usando el MISMO
mecanismo que ya usa `alembic/env.py` para autogenerate: importa
`app.models` completo (por su efecto secundario de registro) y crea
exactamente lo que el código Python declara como fuente de verdad.
`checkfirst=True` la hace segura de re-correr sobre una base que ya
tenga algunas tablas (no falla con "relation already exists").

Efecto secundario intencional: como `zona_4d` (columna en
`elementos_bim`) y las tablas `generaciones_bim_4d5d` /
`elemento_bim_actividad` YA están declaradas en `app/models/bim.py`,
esta baseline las crea también. Por eso 9f3a1c7d2b4e (que antes las
creaba a mano y ahora corre DESPUÉS de esta baseline en la cadena) se
reescribió para ser idempotente: revisa con `sqlalchemy.inspect` si
ya existen antes de intentar crearlas, así que no importa si baseline
ya hizo el trabajo o si -- en una base ya parchada a mano, como
asumía su docstring original -- ya estaban ahí desde antes.

LIMITACIÓN CONOCIDA de este enfoque: al no ser `op.create_table()`
explícitos, esta migración no tiene un `downgrade()` selectivo tabla
por tabla (abajo se deja como no-op documentado) y no captura tipos
de columna exactos en el archivo de migración -- vive en el modelo,
no en el historial de Alembic. Para un baseline "canónico" a la
autogenerate (con downgrade real y DDL explícito), regenerar esto con
`alembic revision --autogenerate` contra una base de datos real vacía
en cuanto haya una disponible, y reemplazar este archivo.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "55225d1e7443"
down_revision: Union[str, None] = "06d589924524"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Import diferido (no a nivel de módulo) para no acoplar la carga
    # de todas las migraciones a que app.models sea importable -- solo
    # esta migración específica lo necesita.
    import app.models  # noqa: F401  (efecto secundario: registra todo en Base.metadata)
    import tezcatlipoca.db.models  # noqa: F401  (efecto secundario: registra todo en Tezcatlipoca Base.metadata)
    from app.models.base import Base
    from tezcatlipoca.db.models import Base as TezBase

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)
    TezBase.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    # El baseline se mantiene como punto de reconstrucción; el rollback
    # destructivo del esquema completo es una operación explícita de
    # infraestructura y no se ejecuta silenciosamente desde Alembic.
    return None
