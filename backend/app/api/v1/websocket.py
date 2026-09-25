# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
WebSocket para progreso en tiempo real de tareas largas.
Soporta: OCR, BIM, Monte Carlo, generación de PDF/Excel.
"""
import asyncio
import json
import logging
from typing import Dict, NamedTuple, Optional, Set
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from fastapi.security import OAuth2PasswordBearer

from app.config import settings
from app.core.task_ownership import verify_task_owner
from app.core.token_revocation import is_jti_revoked
from app.core.deps import SESSION_COOKIE_NAME
from app.workers.celery_app import celery_app

router = APIRouter()
logger = logging.getLogger(__name__)


class _TokenWS(NamedTuple):
    user_id: str
    tenant_id: str

# BUG ORIGINAL (hueco de revocación, tarea C): los dos endpoints de
# abajo decodificaban el JWT a mano con jose_jwt.decode(...) y nunca
# llamaban a is_jti_revoked -- a diferencia de TODO el resto de la API,
# que pasa por app.core.deps.get_current_user (que sí revisa
# is_jti_revoked internamente). En la práctica esto significaba que un
# usuario que hacía logout (que llama a revoke_jti sobre su access
# token) podía seguir abriendo conexiones WebSocket con ese mismo token
# ya "cerrado" hasta que expirara por tiempo (hasta
# ACCESS_TOKEN_EXPIRE_MINUTES). AHORA: se agrega el mismo chequeo que
# usa el resto de la API, vía _validar_token_ws() abajo.
#
# HUECO DISTINTO, CERRADO EN ESTA SESIÓN: ni aquí ni en GET
# /riesgo/simular/{task_id}/status (app/api/v1/montecarlo.py) -- ni,
# se descubrió al revisar, en GET /extraer/{task_id}/status
# (app/api/v1/ocr.py) -- se verificaba que el task_id suscrito/
# consultado le perteneciera al tenant del usuario autenticado --
# cualquier usuario autenticado de CUALQUIER tenant podía suscribirse
# al progreso de un task_id de OTRO tenant si lo adivinaba o lo
# capturaba (los IDs de Celery son UUID4, así que adivinarlos a ciegas
# es inviable, pero igual era un control de acceso ausente, no solo un
# secreto largo). Se cierra con app.core.task_ownership: un hash en
# Redis task_id -> tenant_id poblado en el momento en que cada endpoint
# que hace `.delay()`/`send_task` crea la tarea (OCR, Monte Carlo) y
# consultado aquí, en el `action == "subscribe"` de abajo, antes de
# aceptar la suscripción. BIM no se tocó a propósito: sus dos `.delay()`
# (app/api/v1/bim.py) nunca devuelven el task_id de Celery al cliente
# -- el frontend hace polling sobre recursos ya scopeados por tenant
# (modelo_id / generacion_id vía el `db` normal), así que no hay
# task_id de Celery expuesto por ahí para que este WS lo reciba.


async def _validar_token_ws(token: str) -> Optional[_TokenWS]:
    """Decodifica y valida un JWT para WebSocket: firma, expiración Y
    revocación. Devuelve (user_id, tenant_id) si es válido, o None si no.
    Comparte la política de la API HTTP: un token revocado no autentica
    nada, tampoco un WebSocket. El tenant_id sale del propio claim del
    access token (ver AuthService.create_access_token), el mismo que usa
    el resto de la API vía get_current_user -- no hay que ir a la base
    de datos para esto."""
    import jwt
    from jwt.exceptions import PyJWTError

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except PyJWTError:
        return None

    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    if not user_id or not tenant_id:
        return None

    jti = payload.get("jti")
    if jti and await is_jti_revoked(jti, token_kind="access"):
        return None

    return _TokenWS(user_id=user_id, tenant_id=tenant_id)

# Gestor de conexiones activas
class ConnectionManager:
    """Gestiona conexiones WebSocket activas por usuario y tarea."""

    def __init__(self):
        # user_id -> Set[WebSocket]
        self.user_connections: Dict[str, Set[WebSocket]] = {}
        # task_id -> Set[WebSocket]
        self.task_connections: Dict[str, Set[WebSocket]] = {}
        # layer -> Set[WebSocket] (compatibilidad con broadcasters de
        # datos tipo Tezcatlipoca / data_fetcher)
        self.layer_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(websocket)

    def disconnect(self, websocket: WebSocket, user_id: str):
        """Elimina la conexión de TODOS los índices antes de descartarla."""
        if user_id in self.user_connections:
            self.user_connections[user_id].discard(websocket)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

        # Una conexión puede haberse suscrito a varias tareas y capas.
        # Mantenerla en estos índices después del cierre retiene el objeto
        # WebSocket y provoca fugas de memoria/iteraciones inútiles con el
        # paso del tiempo. La limpieza es deliberadamente O(n) sobre las
        # suscripciones activas: ocurre solo al desconectar.
        for task_id, sockets in list(self.task_connections.items()):
            sockets.discard(websocket)
            if not sockets:
                del self.task_connections[task_id]

        for layer, sockets in list(self.layer_connections.items()):
            sockets.discard(websocket)
            if not sockets:
                del self.layer_connections[layer]

    def subscribe_to_task(self, websocket: WebSocket, task_id: str):
        if task_id not in self.task_connections:
            self.task_connections[task_id] = set()
        self.task_connections[task_id].add(websocket)

    def unsubscribe_from_task(self, websocket: WebSocket, task_id: str):
        if task_id in self.task_connections:
            self.task_connections[task_id].discard(websocket)
            if not self.task_connections[task_id]:
                del self.task_connections[task_id]

    def subscribe_to_layer(self, websocket: WebSocket, layer: str):
        if layer not in self.layer_connections:
            self.layer_connections[layer] = set()
        self.layer_connections[layer].add(websocket)

    def unsubscribe_from_layer(self, websocket: WebSocket, layer: str):
        if layer in self.layer_connections:
            self.layer_connections[layer].discard(websocket)
            if not self.layer_connections[layer]:
                del self.layer_connections[layer]

    async def send_to_user(self, user_id: str, message: dict):
        """Envía mensaje a todas las conexiones de un usuario."""
        if user_id not in self.user_connections:
            return

        disconnected = []
        for ws in self.user_connections[user_id]:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        # Limpiar desconectados
        for ws in disconnected:
            self.user_connections[user_id].discard(ws)

    async def send_to_task(self, task_id: str, message: dict):
        """Envía mensaje a todos los suscritos a una tarea."""
        if task_id not in self.task_connections:
            return

        disconnected = []
        for ws in self.task_connections[task_id]:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            self.task_connections[task_id].discard(ws)

    async def broadcast(self, message: dict, layer_filter: Optional[Set[str]] = None):
        """Broadcast a todos los usuarios conectados.

        `layer_filter` es compatible con los broadcasters de datos de
        Tezcatlipoca: si hay suscripciones por capa, se respeta el filtro;
        si no existen suscripciones de capa, se hace broadcast general
        como compatibilidad hacia atrás.
        """
        if layer_filter:
            targets = set()
            for layer in layer_filter:
                targets.update(self.layer_connections.get(layer, set()))
            if targets:
                for ws in list(targets):
                    try:
                        await ws.send_json(message)
                    except Exception as exc:
                        logger.warning("websocket_layer_broadcast_failed", extra={"error": str(exc), "layer": sorted(layer_filter)})
                return

        for user_id in list(self.user_connections.keys()):
            await self.send_to_user(user_id, message)


manager = ConnectionManager()


@router.websocket("/ws/progreso")
async def websocket_progreso(websocket: WebSocket, token: Optional[str] = None):
    """
    WebSocket para seguimiento de progreso de tareas.

    Protocolo:
    1. Cliente se conecta con ?token=<jwt> o con cookie de sesión httpOnly
    2. Cliente envía: {"action": "subscribe", "task_id": "..."}
    3. Servidor envía progreso: {"type": "progress", "task_id": "...", "progress": 45, "status": "..."}
    4. Cliente envía: {"action": "unsubscribe", "task_id": "..."}
    """
    # (nota: no se toca la base de datos más allá de la revocación, así
    # que no hace falta sesión. Los imports de sessionmaker/engine/User/
    # select que había antes nunca se usaban.)
    cookie_token = websocket.cookies.get(SESSION_COOKIE_NAME)
    auth = await _validar_token_ws(cookie_token or token or "")
    if not auth:
        await websocket.close(code=4001, reason="Token inválido, expirado o revocado")
        return
    user_id, tenant_id = auth

    await manager.connect(websocket, user_id)

    try:
        while True:
            # Recibir mensajes del cliente
            data = await websocket.receive_json()
            action = data.get("action")
            task_id = data.get("task_id")

            if action == "subscribe" and task_id:
                if not await verify_task_owner(task_id, tenant_id=tenant_id):
                    await websocket.send_json({
                        "type": "error",
                        "task_id": task_id,
                        "message": "Tarea no encontrada",
                    })
                    continue

                manager.subscribe_to_task(websocket, task_id)

                # Enviar estado actual de la tarea
                task = celery_app.AsyncResult(task_id)
                await websocket.send_json({
                    "type": "status",
                    "task_id": task_id,
                    "status": task.status,
                    "result": task.result if task.ready() else None,
                })

                # Iniciar polling de progreso si está en progreso
                if task.status == "PENDING" or task.status == "STARTED":
                    asyncio.create_task(_poll_task_progress(task_id, websocket))

            elif action == "unsubscribe" and task_id:
                manager.unsubscribe_from_task(websocket, task_id)

            elif action == "subscribe_layer" and data.get("layer"):
                manager.subscribe_to_layer(websocket, data["layer"])

            elif action == "unsubscribe_layer" and data.get("layer"):
                manager.unsubscribe_from_layer(websocket, data["layer"])

            elif action == "ping":
                await websocket.send_json({"type": "pong", "timestamp": data.get("timestamp")})

    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception as e:
        manager.disconnect(websocket, user_id)
        await websocket.close(code=1011, reason=str(e))


async def _poll_task_progress(task_id: str, websocket: WebSocket):
    """Hace polling del progreso de una tarea Celery."""
    max_attempts = 300  # 5 minutos máximo (1 segundo entre polls)

    for _ in range(max_attempts):
        try:
            task = celery_app.AsyncResult(task_id)

            if task.ready():
                await manager.send_to_task(task_id, {
                    "type": "complete",
                    "task_id": task_id,
                    "status": task.status,
                    "result": task.result if task.status == "SUCCESS" else None,
                    "error": str(task.result) if task.status == "FAILURE" else None,
                })
                break

            # Intentar obtener progreso desde meta
            info = task.info
            progress = 0
            if info and isinstance(info, dict):
                progress = info.get("progress", 0)

            await manager.send_to_task(task_id, {
                "type": "progress",
                "task_id": task_id,
                "status": task.status,
                "progress": progress,
            })

            await asyncio.sleep(1)

        except Exception:
            break


@router.websocket("/ws/notificaciones")
async def websocket_notificaciones(websocket: WebSocket, token: Optional[str] = None):
    """
    WebSocket para notificaciones push del sistema.
    """
    cookie_token = websocket.cookies.get(SESSION_COOKIE_NAME)
    auth = await _validar_token_ws(cookie_token or token or "")
    if not auth:
        await websocket.close(code=4001, reason="Token inválido, expirado o revocado")
        return
    user_id = auth.user_id

    await manager.connect(websocket, user_id)

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("action") == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": data.get("timestamp"),
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)


# Función helper para emitir progreso desde workers
async def emitir_progreso(task_id: str, progress: int, message: str = ""):
    """Emite progreso de una tarea a todos los suscriptores."""
    await manager.send_to_task(task_id, {
        "type": "progress",
        "task_id": task_id,
        "progress": progress,
        "message": message,
        "timestamp": asyncio.get_event_loop().time(),
    })
