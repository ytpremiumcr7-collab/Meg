"""Keep persisted process status honest when the broker rejects an enqueue."""
from app.core.errors import ErrorCode, MegalodonException
from app.models.base import EstadoProceso


async def encolar_proceso(db, registro, task, *, estado_field='estado', error_field='error', **kwargs):
    try:
        task.delay(**kwargs)
    except Exception as exc:
        setattr(registro, estado_field, EstadoProceso.ERROR.value)
        setattr(registro, error_field, 'No se pudo encolar; vuelve a intentar la operación')
        await db.commit()
        raise MegalodonException(ErrorCode.BIM_ERROR,
            'El servicio de procesamiento no está disponible', status_code=503) from exc
