"""Durable delivery and atomic BIM results, safe against repeated messages.

Services commit savepoints inside the executor's outer transaction. Domain
results and job completion become visible together, including 4D creation.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.errors import MegalodonException, ErrorCode
from app.models.base import engine
from app.models.bim import ModeloBIM, GeneracionBIM4D5D, AnalisisClash
from app.models.process_job import TrabajoProceso

logger = logging.getLogger(__name__)
MAX_INTENTOS = 3
PLAZO_ENTREGA = 2400  # longer than the 30-minute worker hard limit
ENTIDADES = {'BIM_IFC': (ModeloBIM, 'estado_procesamiento', 'error_procesamiento'),
             'BIM_4D': (GeneracionBIM4D5D, 'estado', 'error'),
             'BIM_CLASH': (AnalisisClash, 'estado', 'error')}


def registrar_trabajo(db, registro, tipo, parametros):
    """Add the intent to the caller's transaction; never commit here."""
    if tipo not in ENTIDADES:
        raise ValueError('Tipo de trabajo no permitido')
    job = TrabajoProceso(id=uuid4(), tenant_id=registro.tenant_id,
        entidad_id=registro.id, tipo=tipo, parametros=parametros,
        estado='PENDIENTE', intentos=0, proxima_publicacion=datetime.now(timezone.utc))
    db.add(job)
    return job


def _enviar(job_id):
    from app.workers.process_tasks import ejecutar_proceso
    ejecutar_proceso.apply_async(kwargs={'trabajo_id':job_id}, task_id=job_id, retry=False)


async def publicar_pendientes(db_engine=engine, *, enviar=_enviar, limite=20):
    """Publish due/expired deliveries independently of Redis availability."""
    enviados = 0
    for _ in range(limite):
        async with db_engine.begin() as connection:
            if connection.dialect.name == 'sqlite':
                await connection.exec_driver_sql('BEGIN IMMEDIATE')
            async with AsyncSession(bind=connection, expire_on_commit=False) as db:
                now = datetime.now(timezone.utc)
                job = await db.scalar(select(TrabajoProceso).where(
                    TrabajoProceso.estado.in_(['PENDIENTE', 'ENVIADO']),
                    TrabajoProceso.proxima_publicacion <= now
                ).order_by(TrabajoProceso.proxima_publicacion).limit(1)
                  .with_for_update(skip_locked=True))
                if job is None:
                    break
                try:
                    await asyncio.to_thread(enviar, str(job.id))
                except Exception:
                    job.error_publicacion = 'Esperando conexión con el servicio de procesamiento'
                    job.proxima_publicacion = now + timedelta(seconds=15)
                    logger.warning('process_publish_unavailable', extra={'job_id':str(job.id)})
                else:
                    job.estado = 'ENVIADO'
                    job.error_publicacion = None
                    job.proxima_publicacion = now + timedelta(seconds=PLAZO_ENTREGA)
                    enviados += 1
                await db.flush()
    return enviados


async def _entidad(db, job):
    cls, state_field, error_field = ENTIDADES[job.tipo]
    entity = await db.scalar(select(cls).where(cls.id == job.entidad_id,
        cls.tenant_id == job.tenant_id).with_for_update())
    if entity is None:
        raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO,
            'El registro de este trabajo ya no existe', status_code=404)
    return entity, state_field, error_field


async def _procesar(db, job, entity):
    from app.services.bim_service import BIMService
    service = BIMService(db, job.tenant_id)
    params = job.parametros
    if job.tipo == 'BIM_IFC':
        from app.integrations.supabase_storage import storage_bim
        content = await storage_bim().descargar(entity.ruta_archivo)
        await service.procesar_ifc(modelo_id=entity.id, file_content=content,
            tipos_elementos=params.get('tipos_elementos'), extraer_malla=params.get('extraer_malla', True))
    elif job.tipo == 'BIM_4D':
        from sqlalchemy import func
        from app.models.programacion import ActividadPrograma
        program = await service.generar_actividades_4d(modelo_id=entity.modelo_id,
            expediente_id=entity.expediente_id,
            fecha_inicio=datetime.fromisoformat(params['fecha_inicio_iso']),
            dias_por_defecto=params['dias_por_defecto'],
            creado_por_id=entity.creado_por_id, tenant_id=job.tenant_id)
        entity.programa_id = program.id
        entity.num_actividades_generadas = await db.scalar(select(func.count()).where(
            ActividadPrograma.programa_id == program.id))
    else:
        from app.services.clash_service import ClashService
        await ClashService(db, job.tenant_id).ejecutar_analisis_worker(entity.id)


async def ejecutar_trabajo(trabajo_id, db_engine=engine):
    """Lock delivery and commit exactly one domain result, including restarts."""
    job_id = UUID(str(trabajo_id))
    try:
        async with db_engine.begin() as connection:
            if connection.dialect.name == 'sqlite':
                await connection.exec_driver_sql('BEGIN IMMEDIATE')
            async with AsyncSession(bind=connection, expire_on_commit=False,
                                    join_transaction_mode='create_savepoint') as db:
                job = await db.scalar(select(TrabajoProceso).where(
                    TrabajoProceso.id == job_id).with_for_update())
                if job is None:
                    return 'ELIMINADO'
                if job.estado in ('COMPLETADO', 'ERROR'):
                    return job.estado
                entity, state_field, error_field = await _entidad(db, job)
                if getattr(entity, state_field) != 'COMPLETADO':
                    setattr(entity, state_field, 'EN_PROCESO')
                    await _procesar(db, job, entity)
                setattr(entity, state_field, 'COMPLETADO')
                setattr(entity, error_field, None)
                job.estado = 'COMPLETADO'
                job.intentos += 1
                job.error = None
                await db.commit()
                return 'COMPLETADO'
    except Exception as exc:
        logger.exception('process_execution_failed', extra={'job_id':str(job_id)})
        # All domain writes have rolled back before recording a retry.
        async with db_engine.begin() as connection:
            if connection.dialect.name == 'sqlite':
                await connection.exec_driver_sql('BEGIN IMMEDIATE')
            async with AsyncSession(bind=connection, expire_on_commit=False) as db:
                job = await db.scalar(select(TrabajoProceso).where(
                    TrabajoProceso.id == job_id).with_for_update())
                if job is None or job.estado in ('COMPLETADO', 'ERROR'):
                    return job.estado if job else 'ELIMINADO'
                job.intentos += 1
                deterministic = isinstance(exc, MegalodonException) and exc.code != ErrorCode.ARCHIVO_ERROR
                final = deterministic or job.intentos >= MAX_INTENTOS
                job.estado = 'ERROR' if final else 'PENDIENTE'
                job.error = ('No se pudo completar. Revisa los datos y vuelve a intentar.' if final
                    else 'Se interrumpió el procesamiento; se reintentará automáticamente.')
                job.proxima_publicacion = datetime.now(timezone.utc) + timedelta(seconds=15 * job.intentos)
                try:
                    entity, state_field, error_field = await _entidad(db, job)
                except MegalodonException:
                    pass
                else:
                    setattr(entity, state_field, 'ERROR' if final else 'PENDIENTE')
                    setattr(entity, error_field, job.error)
                await db.flush()
                return job.estado
