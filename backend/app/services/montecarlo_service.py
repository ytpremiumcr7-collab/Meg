from __future__ import annotations

import hashlib
import json
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, MegalodonException
from app.core.entitlements import EntitlementsService
from app.models.expediente import ExpedienteObra
from app.models.montecarlo import EstadoMonteCarlo, MonteCarloRun
from app.models.presupuesto import Presupuesto
from app.models.programacion import ProgramaObra
from app.models.user import Tenant, User


class MonteCarloService:
    """Capa de negocio SaaS para corridas Monte Carlo."""

    def __init__(self, db: AsyncSession, tenant_id: UUID | None = None):
        self.db = db
        self.tenant_id = tenant_id

    def _effective_tenant(self, tenant_id: UUID | None = None) -> UUID:
        value = tenant_id or self.tenant_id
        if value is None:
            raise MegalodonException(ErrorCode.AUTH_ERROR, "Contexto tenant requerido para MonteCarloService", status_code=403)
        return value

    @staticmethod
    def request_hash(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def _get_tenant(self, tenant_id: UUID) -> Tenant:
        tenant = await self.db.get(Tenant, tenant_id)
        if tenant is None or not tenant.is_active:
            raise MegalodonException(ErrorCode.AUTH_ERROR, "Tenant no disponible.", status_code=403)
        return tenant

    async def _validate_context(
        self,
        tenant_id: UUID,
        expediente_id: Optional[UUID],
        presupuesto_id: Optional[UUID],
        programa_id: Optional[UUID],
    ) -> tuple[Optional[UUID], Optional[UUID], Optional[UUID]]:
        expediente = None
        presupuesto = None
        programa = None

        if expediente_id is not None:
            expediente = await self.db.scalar(
                select(ExpedienteObra).where(
                    ExpedienteObra.id == expediente_id,
                    ExpedienteObra.tenant_id == tenant_id,
                )
            )
            if expediente is None:
                raise MegalodonException(ErrorCode.TAREA_NO_ENCONTRADA, "Expediente no encontrado en el tenant.", status_code=404)

        if presupuesto_id is not None:
            presupuesto = await self.db.scalar(select(Presupuesto).join(ExpedienteObra, ExpedienteObra.id == Presupuesto.expediente_id).where(Presupuesto.id == presupuesto_id, ExpedienteObra.tenant_id == tenant_id))
            if presupuesto is None:
                raise MegalodonException(ErrorCode.TAREA_NO_ENCONTRADA, "Presupuesto no encontrado.", status_code=404)
            if expediente is not None and presupuesto.expediente_id != expediente.id:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "El presupuesto no pertenece al expediente.", status_code=422)
            budget_expediente = await self.db.scalar(
                select(ExpedienteObra).where(
                    ExpedienteObra.id == presupuesto.expediente_id,
                    ExpedienteObra.tenant_id == tenant_id,
                )
            )
            if budget_expediente is None:
                raise MegalodonException(ErrorCode.TAREA_NO_ENCONTRADA, "Presupuesto fuera del tenant.", status_code=404)
            expediente_id = budget_expediente.id

        if programa_id is not None:
            programa = await self.db.scalar(select(ProgramaObra).join(ExpedienteObra, ExpedienteObra.id == ProgramaObra.expediente_id).where(ProgramaObra.id == programa_id, ExpedienteObra.tenant_id == tenant_id))
            if programa is None:
                raise MegalodonException(ErrorCode.TAREA_NO_ENCONTRADA, "Programa de obra no encontrado.", status_code=404)
            program_expediente = await self.db.scalar(
                select(ExpedienteObra).where(
                    ExpedienteObra.id == programa.expediente_id,
                    ExpedienteObra.tenant_id == tenant_id,
                )
            )
            if program_expediente is None:
                raise MegalodonException(ErrorCode.TAREA_NO_ENCONTRADA, "Programa fuera del tenant.", status_code=404)
            if expediente_id is not None and programa.expediente_id != expediente_id:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "El programa no pertenece al expediente.", status_code=422)
            expediente_id = program_expediente.id

        return expediente_id, presupuesto_id, programa_id

    async def recuperar_por_idempotencia(self, tenant_id: UUID, idempotency_key: str, request_hash: str) -> MonteCarloRun | None:
        run = await self.db.scalar(
            select(MonteCarloRun).where(
                MonteCarloRun.tenant_id == tenant_id,
                MonteCarloRun.idempotency_key == idempotency_key,
            )
        )
        if run is not None and run.request_hash != request_hash:
            raise MegalodonException(
                ErrorCode.PARAMETRO_INVALIDO,
                "La Idempotency-Key ya fue usada con una carga diferente.",
                status_code=409,
            )
        return run

    async def crear_corrida(
        self,
        *,
        user: User,
        payload: dict[str, Any],
        idempotency_key: Optional[str],
    ) -> tuple[MonteCarloRun, bool]:
        await self._get_tenant(user.tenant_id)
        request_hash = self.request_hash(payload)

        if idempotency_key:
            existente = await self.recuperar_por_idempotencia(user.tenant_id, idempotency_key, request_hash)
            if existente is not None:
                return existente, True

        expediente_id, presupuesto_id, programa_id = await self._validate_context(
            user.tenant_id,
            payload.get("expediente_id"),
            payload.get("presupuesto_id"),
            payload.get("programa_id"),
        )

        # Si el presupuesto es la fuente de verdad y no se envió base explícita,
        # se utiliza el monto aprobado/actual persistido.
        presupuesto_base = payload.get("presupuesto_base")
        if presupuesto_base is None and presupuesto_id:
            presupuesto = await self.db.scalar(select(Presupuesto).join(ExpedienteObra, ExpedienteObra.id == Presupuesto.expediente_id).where(Presupuesto.id == presupuesto_id, ExpedienteObra.tenant_id == tenant_id))
            presupuesto_base = float(presupuesto.monto_total)
        if not presupuesto_base or presupuesto_base <= 0:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "Se requiere un presupuesto_base > 0 o un presupuesto_id válido.")
        if float(payload["presupuesto_maximo"]) < float(presupuesto_base):
            raise MegalodonException(
                ErrorCode.PARAMETRO_INVALIDO,
                "presupuesto_maximo no puede ser menor que el presupuesto base efectivo.",
            )

        if payload.get("plazo_base_dias") is None and programa_id is not None:
            programa = await self.db.scalar(select(ProgramaObra).join(ExpedienteObra, ExpedienteObra.id == ProgramaObra.expediente_id).where(ProgramaObra.id == programa_id, ExpedienteObra.tenant_id == tenant_id))
            if programa and programa.duracion_plan_dias:
                payload["plazo_base_dias"] = int(programa.duracion_plan_dias)
        if payload.get("plazo_maximo_dias") is not None and payload.get("plazo_base_dias") is None:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "plazo_maximo_dias requiere plazo_base_dias o programa_id con duración plan.")
        if payload.get("plazo_base_dias") is not None and payload.get("plazo_maximo_dias") is not None and payload["plazo_maximo_dias"] < payload["plazo_base_dias"]:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "plazo_maximo_dias no puede ser menor que el plazo base efectivo.")

        variables = payload.get("variables") or []
        nombres = [str(v.get("nombre", "")).strip() for v in variables]
        if len(nombres) != len(set(nombres)):
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "Las variables de riesgo deben tener nombres únicos.")

        limite = int(payload.get("iteraciones", 10_000))
        if limite > 100_000:
            entitlements = EntitlementsService(self.db)
            tenant = await self._get_tenant(user.tenant_id)
            plan = entitlements.calcular_plan_efectivo(tenant)
            limites = await entitlements.obtener_limites(plan)
            if not limites or not limites.permite_jobs_pesados:
                raise MegalodonException(
                    ErrorCode.VALIDACION_FALLIDA,
                    "Las simulaciones de alta carga requieren un plan con jobs pesados habilitados.",
                    status_code=402,
                    details={"plan": plan, "iteraciones": limite, "umbral": 100_000},
                )

        entitlements = EntitlementsService(self.db)
        tenant = await self._get_tenant(user.tenant_id)
        await entitlements.verificar_y_registrar_uso(
            tenant, "corridas_costeo", 1, auto_commit=False
        )

        task_id = str(uuid4())
        run = MonteCarloRun(
            tenant_id=user.tenant_id,
            creado_por_id=user.id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            expediente_id=expediente_id,
            presupuesto_id=presupuesto_id,
            programa_id=programa_id,
            estado=EstadoMonteCarlo.PENDIENTE.value,
            progreso=0,
            iteraciones=limite,
            seed=int(payload["seed"] if payload.get("seed") is not None else secrets.randbelow(2_147_483_647)),
            presupuesto_base=float(presupuesto_base),
            presupuesto_maximo=float(payload["presupuesto_maximo"]),
            plazo_base_dias=payload.get("plazo_base_dias"),
            plazo_maximo_dias=payload.get("plazo_maximo_dias"),
            variables=payload["variables"],
            configuracion=payload,
        )
        self.db.add(run)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            if idempotency_key:
                existente = await self.recuperar_por_idempotencia(user.tenant_id, idempotency_key, request_hash)
                if existente is not None:
                    return existente, True
            raise
        await self.db.refresh(run)
        return run, False

    async def revertir_reserva_por_fallo_enqueue(self, tenant_id: UUID) -> None:
        tenant = await self._get_tenant(tenant_id)
        await EntitlementsService(self.db).revertir_uso(tenant, "corridas_costeo", 1)

    async def marcar_encolado(self, run_id: UUID, tenant_id: UUID | None = None) -> None:
        run = await self.db.scalar(select(MonteCarloRun).where(MonteCarloRun.id == run_id, MonteCarloRun.tenant_id == self._effective_tenant(tenant_id)))
        if run is None:
            return
        run.estado = EstadoMonteCarlo.ENCOLADO.value
        run.progreso = 0
        await self.db.commit()

    async def marcar_en_proceso(self, run_id: str, tenant_id: UUID | None = None) -> bool:
        run = await self.db.scalar(select(MonteCarloRun).where(MonteCarloRun.id == UUID(run_id), MonteCarloRun.tenant_id == self._effective_tenant(tenant_id)))
        if run is None:
            return False
        if run.estado in {EstadoMonteCarlo.CANCELADO.value, EstadoMonteCarlo.ERROR.value, EstadoMonteCarlo.COMPLETADO.value}:
            return False
        run.estado = EstadoMonteCarlo.EN_PROCESO.value
        run.started_at = datetime.now(timezone.utc)
        run.progreso = max(run.progreso, 1)
        await self.db.commit()
        return True

    async def actualizar_progreso(self, task_id: str, progreso: int, tenant_id: UUID | None = None) -> None:
        run = await self.db.scalar(select(MonteCarloRun).where(MonteCarloRun.task_id == task_id, MonteCarloRun.tenant_id == self._effective_tenant(tenant_id)))
        if run is None:
            return
        run.estado = EstadoMonteCarlo.EN_PROCESO.value
        run.progreso = max(0, min(100, int(progreso)))
        await self.db.commit()

    async def completar(self, task_id: str, resultado: dict[str, Any], execution_ms: int, tenant_id: UUID | None = None) -> None:
        run = await self.db.scalar(select(MonteCarloRun).where(MonteCarloRun.task_id == task_id, MonteCarloRun.tenant_id == self._effective_tenant(tenant_id)))
        if run is None or run.estado == EstadoMonteCarlo.CANCELADO.value:
            return
        run.estado = EstadoMonteCarlo.COMPLETADO.value
        run.progreso = 100
        run.resultado = resultado
        run.execution_ms = execution_ms
        run.finished_at = datetime.now(timezone.utc)
        await self.db.commit()

        if run.presupuesto_id:
            presupuesto = await self.db.scalar(select(Presupuesto).where(Presupuesto.id == run.presupuesto_id, Presupuesto.expediente_id == run.expediente_id))
            if presupuesto is not None and presupuesto.expediente_id == run.expediente_id:
                presupuesto.resultado_montecarlo = {
                    "run_id": str(run.id),
                    "task_id": run.task_id,
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                    **resultado,
                }
                await self.db.commit()

    async def cancelar(self, task_id: str, tenant_id: UUID) -> MonteCarloRun:
        run = await self.db.scalar(
            select(MonteCarloRun).where(
                MonteCarloRun.task_id == task_id,
                MonteCarloRun.tenant_id == tenant_id,
            )
        )
        if run is None:
            raise MegalodonException(ErrorCode.TAREA_NO_ENCONTRADA, "La simulación no existe en este tenant.", status_code=404)
        if run.estado in {EstadoMonteCarlo.COMPLETADO.value, EstadoMonteCarlo.ERROR.value, EstadoMonteCarlo.CANCELADO.value}:
            return run
        run.estado = EstadoMonteCarlo.CANCELADO.value
        run.progreso = 0 if run.estado == EstadoMonteCarlo.PENDIENTE.value else run.progreso
        run.finished_at = datetime.now(timezone.utc)
        await self.db.commit()
        return run

    async def esta_cancelada(self, task_id: str, tenant_id: UUID | None = None) -> bool:
        run = await self.db.scalar(select(MonteCarloRun.estado).where(MonteCarloRun.task_id == task_id, MonteCarloRun.tenant_id == self._effective_tenant(tenant_id)))
        return run == EstadoMonteCarlo.CANCELADO.value

    async def fallar(self, task_id: str, exc: Exception, execution_ms: int = 0, tenant_id: UUID | None = None) -> None:
        run = await self.db.scalar(select(MonteCarloRun).where(MonteCarloRun.task_id == task_id, MonteCarloRun.tenant_id == self._effective_tenant(tenant_id)))
        if run is None:
            return
        run.estado = EstadoMonteCarlo.ERROR.value
        run.error_codigo = getattr(getattr(exc, "code", None), "value", "MONTECARLO_ERROR")
        run.error_mensaje = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        run.execution_ms = execution_ms
        await self.db.commit()
