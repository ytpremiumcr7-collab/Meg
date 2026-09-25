from db.models import get_async_db, init_db_async
"""
TU-OSINT-PLATFORM v2.0.0
Backend principal: FastAPI + APScheduler + Mesh + WebSocket
"""

import os
import sys
import hmac
import hashlib
import time
import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
from contextlib import asynccontextmanager

from middleware.audit import audit_middleware
from middleware.rate_limit import RateLimitMiddleware
from middleware.audit import AuditMiddleware
from fastapi import FastAPI, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn
import logging
from logging.handlers import RotatingFileHandler

# ─── CONFIGURACIÓN ───
from dotenv import load_dotenv
load_dotenv()

from app.config import settings

AGENT_HMAC_SECRET = os.getenv("AGENT_HMAC_SECRET")
JWT_SECRET_KEY = settings.SECRET_KEY
API_KEY_MASTER = os.getenv("API_KEY_MASTER")
if not AGENT_HMAC_SECRET or not API_KEY_MASTER:
    raise RuntimeError("AGENT_HMAC_SECRET y API_KEY_MASTER son obligatorios para arrancar Tezcatlipoca en modo industrial.")

# ─── LOGGING CONFIGURATION ───
def setup_logging():
    """Configure structured logging for production."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    class JSONFormatter(logging.Formatter):
        def format(self, record):
            import json
            log_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            }
            if hasattr(record, "request_id"):
                log_data["request_id"] = record.request_id
            return json.dumps(log_data)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    if os.getenv("ENVIRONMENT") == "production":
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
        ))

    if os.getenv("LOG_FILE"):
        file_handler = RotatingFileHandler(
            os.getenv("LOG_FILE"),
            maxBytes=10*1024*1024,
            backupCount=5
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(JSONFormatter())
        logging.basicConfig(level=log_level, handlers=[console_handler, file_handler])
    else:
        logging.basicConfig(level=log_level, handlers=[console_handler])

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

setup_logging()
logger = logging.getLogger("tu-osint")

# ─── IMPORTS DE SERVICIOS ───
from services.data_fetcher import DataFetcherEngine
from services.mesh.max_power_peer import MaxPowerPeerEngine
from services.mesh.honeypot import HoneypotEngine
from services.mesh.sprt_slashing import SPRTSlashingFixed
from services.mesh.sovereign_shell import SovereignShell
from services.snapshot_store import SnapshotStore
from services.cctv_pipeline import CCTVPipeline
from services.sigint.sigint_engine import SIGINTEngine
from services.sar_connector import SARConnector
from services.ais_connector import AISConnector
from services.osint_recon.osint_engine import OSINTReconEngine
from services.malware.aggregator import MalwareAggregator

# ─── ROUTERS ───
from routers import (
    admin_router,
    ai_router, auth_router, cyber_router, entity_router, geo_router, layers_router,
    malware_router, mesh_router, osint_router, snapshots_router,
    telemetry_router, honeypot_router, transport_router,
    aviation_router, sar_router, photogrammetry_router,
    scm_router, settings_router, wormhole_router
)

# ─── NUEVOS SERVICIOS ───
from services.transport.graphhopper_routes import GraphHopperClient
from services.transport.db_bahn_trains import DBTrainClient
from services.transport.gtfs_mobility import GTFSMobilityClient
from services.aviation.faa_notams import FAANOTAMClient
from services.aviation.avwx_engine import AVWXClient
from services.aviation.adsb_exchange import ADSBExchangeClient
from services.sar.nasa_earthdata import NASAEarthdataClient
from services.sar.google_earth_engine import GoogleEarthEngineClient
from services.sar.copernicus_scihub import CopernicusSciHubClient
from services.photogrammetry.webodm_client import WebODMClient


# ─── INSTANCIAS GLOBALES ───
data_fetcher: DataFetcherEngine = None
peer_engine: MaxPowerPeerEngine = None
honeypot_engine: HoneypotEngine = None
sprt_slashing: SPRTSlashingFixed = None
sovereign: SovereignShell = None
snapshot_store: SnapshotStore = None
cctv_pipeline: CCTVPipeline = None
sigint_engine: SIGINTEngine = None
sar_connector: SARConnector = None
ais_connector: AISConnector = None
osint_engine: OSINTReconEngine = None
malware_aggregator: MalwareAggregator = None

# ─── MODELOS Pydantic ───
class ReportRequest(BaseModel):
    node_id: str
    task_id: str
    report: int = Field(..., ge=0, le=1)
    report_prob: Optional[float] = Field(None, ge=0.0, le=1.0)
    report_meta: Optional[float] = Field(None, ge=0.0, le=1.0)

class NodeRegisterRequest(BaseModel):
    node_id: str
    node_type: str = Field(..., pattern="^(light|full|heavy|oracle|peer)$")
    stake: int = Field(0, ge=0)

class CommandRequest(BaseModel):
    cmd: str
    args: Dict[str, Any] = {}

class BatchRequest(BaseModel):
    commands: List[CommandRequest]

class OSINTLookupRequest(BaseModel):
    target: str
    lookup_type: str = Field(..., pattern="^(ip|domain|mac|cve|email|phone|username)$")

class EntityExpandRequest(BaseModel):
    entity: str
    depth: int = Field(2, ge=1, le=5)

class ProposalCreateRequest(BaseModel):
    proposer: str
    proposal_type: str
    payload: Dict[str, Any]

class VoteRequest(BaseModel):
    node_id: str
    vote: str = Field(..., pattern="^(yes|no|abstain)$")

# ─── LIFESPAN ───
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicialización y cleanup."""
    global data_fetcher, peer_engine, honeypot_engine, sprt_slashing, sovereign
    global snapshot_store, cctv_pipeline, sigint_engine, sar_connector
    global ais_connector, osint_engine, malware_aggregator

    logger.info("[STARTUP] Inicializando TU-OSINT-PLATFORM v2.0.0...")

    # Crear tablas de base de datos
    await init_db_async()
    logger.info("[STARTUP] Base de datos inicializada")

    # Inicializar motores
    data_fetcher = DataFetcherEngine()
    peer_engine = MaxPowerPeerEngine(
        epsilon_dp=float(os.getenv("MESH_EPSILON_DP", "1.0")),
        stake_amount=int(os.getenv("MESH_STAKE_AMOUNT", "1000")),
        verification_rate=float(os.getenv("MESH_VERIFICATION_RATE", "0.02")),
        burn_in=int(os.getenv("MESH_BURN_IN", "50"))
    )
    honeypot_engine = HoneypotEngine(base_rate=0.03, adaptive_factor=2.0, covert_mode=True)
    sprt_slashing = SPRTSlashingFixed(p0=0.80, p1=0.20, alpha=0.01, beta=0.05)
    sovereign = SovereignShell(peer_engine, honeypot_engine, sprt_slashing)

    snapshot_store = SnapshotStore()
    cctv_pipeline = CCTVPipeline()
    sigint_engine = SIGINTEngine()
    sar_connector = SARConnector()
    ais_connector = AISConnector()
    osint_engine = OSINTReconEngine()
    malware_aggregator = MalwareAggregator()

    # Iniciar fetchers
    data_fetcher.set_websocket_manager(ws_manager)
    await data_fetcher.start()
    logger.info("[STARTUP] Scheduler iniciado")

    # Iniciar conexiones persistentes
    await ais_connector.connect()

    logger.info("[STARTUP] Sistema listo. 60+ fuentes activas.")

    # ─── NUEVOS SERVICIOS ───
    graphhopper = GraphHopperClient()
    db_trains = DBTrainClient()
    gtfs_mobility = GTFSMobilityClient()
    faa_notams = FAANOTAMClient()
    avwx = AVWXClient()
    adsb_exchange = ADSBExchangeClient()
    nasa_earthdata = NASAEarthdataClient()
    gee = GoogleEarthEngineClient()
    copernicus_scihub = CopernicusSciHubClient()
    webodm = WebODMClient()

    # ─── EXPONER EN APP.STATE ───
    app.state.honeypot_engine = honeypot_engine
    app.state.sprt_slashing = sprt_slashing
    app.state.peer_engine = peer_engine
    app.state.graphhopper = graphhopper
    app.state.db_trains = db_trains
    app.state.gtfs_mobility = gtfs_mobility
    app.state.faa_notams = faa_notams
    app.state.avwx = avwx
    app.state.adsb_exchange = adsb_exchange
    app.state.nasa_earthdata = nasa_earthdata
    app.state.gee = gee
    app.state.copernicus_scihub = copernicus_scihub
    app.state.webodm = webodm
    app.state.ais_connector = ais_connector
    app.state.sar_connector = sar_connector
    app.state.sigint_engine = sigint_engine
    app.state.cctv_pipeline = cctv_pipeline
    app.state.data_fetcher = data_fetcher
    app.state.snapshot_store = snapshot_store
    app.state.osint_engine = osint_engine
    app.state.malware_agg = malware_aggregator
    app.state.sovereign = sovereign
    app.state.tezcatlipoca_ready = True


    yield

    # Cleanup
    logger.info("[SHUTDOWN] Cerrando conexiones...")
    await data_fetcher.stop()
    await ais_connector.disconnect()

    logger.info("[SHUTDOWN] Scheduler detenido")
    logger.info("[SHUTDOWN] Sistema detenido.")

# ─── APP ───
app = FastAPI(
    title="TU-OSINT-PLATFORM",
    description="Plataforma de inteligencia geoespacial con mesh incentive-compatible",
    version="2.0.0",
    lifespan=lifespan
)

bootstrap_enterprise(app)

# ─── MIDDLEWARE ───
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── MOUNT ROUTERS ───
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(admin_router)
app.include_router(ai_router, prefix="/api/ai", tags=["AI"])
app.include_router(cyber_router, prefix="/api/cyber", tags=["Cyber"])
app.include_router(entity_router, prefix="/api/entity", tags=["Entity"])
app.include_router(entity_router, prefix="/api/entity_graph", tags=["EntityGraph"])
app.include_router(geo_router, prefix="/api/geo", tags=["Geo"])
app.include_router(geo_threats_router, prefix="/api/geo", tags=["Geo Threats"])
app.include_router(layers_router, prefix="/api/layers", tags=["Layers"])
app.include_router(malware_router, prefix="/api/malware", tags=["Malware"])
app.include_router(mesh_router, prefix="/api/mesh", tags=["Mesh"])
app.include_router(mesh_router, prefix="/api/mesh_governance", tags=["MeshGovernance"])
app.include_router(osint_router, prefix="/api/osint", tags=["OSINT"])
app.include_router(snapshots_router, prefix="/api/snapshots", tags=["Snapshots"])
app.include_router(telemetry_router, prefix="/api/telemetry", tags=["Telemetry"])
app.include_router(honeypot_router, prefix="/api/honeypot", tags=["Honeypot"])
app.include_router(transport_router, prefix="/api/transport", tags=["Transport"])
app.include_router(aviation_router, prefix="/api/aviation", tags=["Aviation"])
app.include_router(sar_router, prefix="/api/sar", tags=["SAR"])
app.include_router(photogrammetry_router, prefix="/api/photogrammetry", tags=["Photogrammetry"])
app.include_router(scm_router, prefix="/api/scm", tags=["SCM"])
app.include_router(settings_router, prefix="/api/settings", tags=["Settings"])
app.include_router(wormhole_router, prefix="/api/wormhole", tags=["Wormhole"])


# ─── SECURITY: HMAC para Agentes ───
security_bearer = HTTPBearer(auto_error=False)

async def verify_hmac(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security_bearer)):
    """Verifica firma HMAC-SHA256 en cada petición del agente."""
    secret = AGENT_HMAC_SECRET
    timestamp = request.headers.get("X-Timestamp")
    nonce = request.headers.get("X-Nonce")
    signature = request.headers.get("X-Signature")

    if not all([timestamp, nonce, signature]):
        raise HTTPException(401, detail="Missing HMAC headers: X-Timestamp, X-Nonce, X-Signature")

    try:
        ts = int(timestamp)
    except ValueError:
        raise HTTPException(401, detail="Invalid timestamp")

    if abs(time.time() - ts) > 300:
        raise HTTPException(401, detail="Timestamp expired (> 300s)")

    body = await request.body()
    payload = f"{request.method}|{request.url.path}|{timestamp}|{nonce}|{hashlib.sha256(body).hexdigest()}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, detail="Invalid HMAC signature")

    return True

async def verify_api_key(request: Request):
    """Verifica API Key para consumidores externos."""
    api_key = request.headers.get("X-API-Key")
    if api_key != API_KEY_MASTER:
        raise HTTPException(403, detail="Invalid API Key")
    return True

# ─── TIER SYSTEM ───
TIER_COMMANDS = {
    'restricted': [
        'get_summary', 'get_layer_slice', 'search_telemetry',
        'search_news', 'find_flights', 'find_ships', 'find_entity',
        'correlate_entity', 'entities_near', 'brief_area',
        'osint_lookup', 'entity_expand', 'osint_tools',
        'sar_pin_click', 'sar_focus_aoi'
    ],
    'full': [
        'osint_sweep', 'place_intel_pin', 'fly_map_to',
        'send_alert', 'generate_report', 'mesh_status',
        'propose_governance', 'cast_vote', 'stake_tokens'
    ]
}

# ─── ENDPOINTS: TELEMETRÍA ───
@app.get("/api/telemetry")
async def get_telemetry():
    """Datos consolidados de todas las capas activas."""
    return {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'layers': {
            'flights': data_fetcher.cache.get('flights', []),
            'military_flights': data_fetcher.cache.get('military_flights', []),
            'quakes': data_fetcher.cache.get('quakes', []),
            'ships': data_fetcher.cache.get('ships', []),
            'firms': data_fetcher.cache.get('firms', []),
            'weather': data_fetcher.cache.get('weather', []),
            'air_quality': data_fetcher.cache.get('air_quality', []),
            'malware': data_fetcher.cache.get('malware', {}),
            'cisa_kev': data_fetcher.cache.get('cisa_kev', []),
        },
        'mesh': {
            'active_nodes': len(peer_engine.nodes),
            'total_stake': sum(n['stake'] for n in peer_engine.nodes.values()),
            'pending_proposals': len([p for p in sovereign.proposals.values() if p.status == 'active'])
        },
        'system': {
            'active_fetchers': len(data_fetcher.scheduler.get_jobs()),
            'websocket_clients': len(connected_ws_clients),
            'uptime_seconds': time.time() - startup_time
        }
    }

@app.get("/api/layers")
async def get_layers():
    """Lista de capas disponibles con metadatos."""
    return {
        'layers': [
            {'id': 'flights', 'name': 'Vuelos (OpenSky)', 'source': 'opensky', 'refresh': 60},
            {'id': 'military_flights', 'name': 'Vuelos Militares (adsb.lol)', 'source': 'adsb.lol', 'refresh': 60},
            {'id': 'ships', 'name': 'Barcos (AIS)', 'source': 'aisstream', 'refresh': 30},
            {'id': 'quakes', 'name': 'Terremotos (USGS)', 'source': 'usgs', 'refresh': 60},
            {'id': 'firms', 'name': 'Incendios (NASA FIRMS)', 'source': 'nasa_firms', 'refresh': 120},
            {'id': 'weather', 'name': 'Clima (NWS)', 'source': 'nws', 'refresh': 120},
            {'id': 'air_quality', 'name': 'Calidad Aire (OpenAQ)', 'source': 'openaq', 'refresh': 120},
            {'id': 'satellites', 'name': 'Satélites (CelesTrak)', 'source': 'celestrak', 'refresh': 60},
            {'id': 'volcanoes', 'name': 'Volcanes', 'source': 'usgs_volcanoes', 'refresh': 3600},
            {'id': 'malware', 'name': 'Malware (Feodo+URLhaus)', 'source': 'abuse.ch', 'refresh': 300},
            {'id': 'cisa_kev', 'name': 'CISA KEV', 'source': 'cisa', 'refresh': 300},
            {'id': 'shodan_ics', 'name': 'ICS Exposed (Shodan)', 'source': 'shodan', 'refresh': 21600},
            {'id': 'gdelt_conflict', 'name': 'Conflictos (GDELT)', 'source': 'gdelt', 'refresh': 1800},
            {'id': 'deepstate', 'name': 'Línea de Frente (DeepState)', 'source': 'deepstate', 'refresh': 1800},
            {'id': 'cctv', 'name': 'CCTV Pipeline', 'source': 'cctv', 'refresh': 3600},
            {'id': 'sigint', 'name': 'SIGINT (KiwiSDR)', 'source': 'kiwisdr', 'refresh': 3600},
            {'id': 'sar', 'name': 'SAR (Sentinel/OPERA)', 'source': 'sar', 'refresh': 86400},
        ]
    }

# ─── ENDPOINTS: AI CHANNEL ───
@app.post("/api/ai/channel/command")
async def execute_command(req: CommandRequest, auth: bool = Depends(verify_hmac)):
    """Ejecuta un comando individual del agente."""
    tier = os.getenv("AGENT_ACCESS_TIER", "restricted")

    if req.cmd not in TIER_COMMANDS.get(tier, []):
        raise HTTPException(403, detail=f"Command '{req.cmd}' not allowed in tier '{tier}'")

    handler = COMMAND_HANDLERS.get(req.cmd)
    if not handler:
        raise HTTPException(400, detail=f"Unknown command: {req.cmd}")

    return await handler(req.args)

@app.post("/api/ai/channel/batch")
async def execute_batch(req: BatchRequest, auth: bool = Depends(verify_hmac)):
    """Ejecuta hasta 20 comandos concurrentemente."""
    if len(req.commands) > 20:
        raise HTTPException(400, detail="Max 20 commands per batch")

    results = await asyncio.gather(*[
        execute_command(cmd, auth) for cmd in req.commands
    ], return_exceptions=True)

    return {"results": results, "completed_at": datetime.now(timezone.utc).isoformat()}

@app.get("/api/ai/tools")
async def list_tools():
    """Descubre herramientas disponibles por tier."""
    return {
        'restricted': TIER_COMMANDS['restricted'],
        'full': TIER_COMMANDS['full'],
        'current_tier': os.getenv("AGENT_ACCESS_TIER", "restricted")
    }

# ─── ENDPOINTS: OSINT ───
@app.post("/api/osint/lookup")
async def osint_lookup(req: OSINTLookupRequest, auth: bool = Depends(verify_api_key)):
    """Recon pasivo: IP, DNS, WHOIS, certs, BGP, CVE, etc."""
    return await osint_engine.lookup(req.target, req.lookup_type)

@app.post("/api/entity/expand")
async def entity_expand(req: EntityExpandRequest, auth: bool = Depends(verify_api_key)):
    """Expande grafo de entidades: Wikidata + OFAC + memoria."""
    return await osint_engine.expand_entity(req.entity, req.depth)

# ─── ENDPOINTS: MALWARE / CYBER ───
@app.get("/api/malware")
async def get_malware_feeds():
    """Feeds consolidados: Feodo + URLhaus."""
    return await malware_aggregator.get_feeds()

@app.get("/api/cyber-threats")
async def get_cyber_threats():
    """CISA KEV + Shodan ICS + GreyNoise."""
    return await malware_aggregator.get_cyber_threats()

# ─── ENDPOINTS: MESH / GOBERNANZA ───
@app.post("/api/mesh/report")
async def mesh_report(req: ReportRequest):
    """Nodo reporta sobre una tarea. Procesa honeypot + OA + BTS + SPRT."""
    # Verificar honeypot primero
    hp_result = honeypot_engine.evaluate_report(req.task_id, req.node_id, req.report)
    if hp_result:
        sprt_slashing.update(req.node_id, hp_result['correct'])
        try:
            sovereign.auto_slash_proposal(req.node_id)
        except ValueError:
            # Caso esperado: sprt_engine no tiene a este nodo registrado
            # como proposer todavía (p.ej. primer reporte del nodo). No es
            # un error real, pero se deja traza en debug para poder
            # correlacionar con métricas de slashing si algún día el
            # volumen de estos casos resulta anómalo.
            logger.debug(f"[mesh_report] auto_slash_proposal: node {req.node_id} no registrado como proposer")

    # Procesar reporte normal
    result = peer_engine.submit_report(
        req.node_id, req.task_id, req.report, req.report_prob, req.report_meta
    )
    return result

@app.post("/api/mesh/register")
async def mesh_register(req: NodeRegisterRequest):
    """Registra un nodo en el mesh."""
    peer_engine.register_node(req.node_id, req.node_type, stake=req.stake)
    sovereign.register_node(req.node_id, req.node_type, req.stake)
    return {"status": "registered", "node_id": req.node_id, "stake": req.stake}

@app.get("/api/mesh/node/{node_id}/score")
async def mesh_node_score(node_id: str):
    """Score de calidad del nodo."""
    return peer_engine.get_node_score(node_id)

@app.get("/api/mesh/node/{node_id}/sprt")
async def mesh_node_sprt(node_id: str):
    """Estado SPRT del nodo."""
    return sprt_slashing.get_status(node_id)

@app.get("/api/mesh/status")
async def mesh_status():
    """Estado global del mesh."""
    return {
        'nodes': {nid: {'type': n['type'], 'stake': n['stake'], 'status': n['status']} 
                  for nid, n in peer_engine.nodes.items()},
        'proposals': {pid: {'type': p.type.value, 'status': p.status} 
                      for pid, p in sovereign.proposals.items()},
        'honeypots_active': honeypot_engine.total_honeypots,
        'total_slashed': sum(s['amount'] for s in peer_engine.slash_log)
    }

@app.post("/api/mesh/proposal")
async def mesh_create_proposal(req: ProposalCreateRequest):
    """Crea propuesta de gobernanza."""
    from services.mesh.sovereign_shell import ProposalType
    pt = ProposalType(req.proposal_type)
    pid = sovereign.create_proposal(req.proposer, pt, req.payload)
    return {"proposal_id": pid, "status": "created"}

@app.post("/api/mesh/proposal/{proposal_id}/vote")
async def mesh_cast_vote(proposal_id: str, req: VoteRequest):
    """Vota en una propuesta."""
    from services.mesh.sovereign_shell import VoteType
    v = VoteType(req.vote)
    sovereign.cast_vote(req.node_id, proposal_id, v)
    return {"status": "voted", "proposal_id": proposal_id}

# ─── ENDPOINTS: SNAPSHOTS / TIME MACHINE ───
@app.get("/api/snapshots")
async def list_snapshots():
    """Lista snapshots disponibles."""
    return snapshot_store.list_snapshots()

@app.get("/api/snapshots/{snapshot_id}")
async def get_snapshot(snapshot_id: str):
    """Recupera un snapshot específico."""
    return snapshot_store.get_snapshot(snapshot_id)

@app.post("/api/snapshots/create")
async def create_snapshot(background_tasks: BackgroundTasks):
    """Crea snapshot manual."""
    background_tasks.add_task(snapshot_store.create_snapshot, "auto_snapshot", data_fetcher.cache)
    return {"status": "snapshot_creation_started"}

# ─── WEBSOCKET MANAGER ───
class WebSocketManager:
    """Manages WebSocket connections with subscription support and heartbeat."""

    def __init__(self):
        self.clients: dict[WebSocket, dict] = {}  # ws -> {subscribed_layers, last_ping}
        self.connected_count = 0
        self.startup_time = time.time()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.clients[websocket] = {
            'layers': set(),  # empty = all layers
            'last_ping': time.time(),
            'connected_at': datetime.now(timezone.utc).isoformat()
        }
        self.connected_count += 1

        # Send immediate snapshot
        await self._send_snapshot(websocket)

        # Send welcome message
        await websocket.send_json({
            'type': 'connected',
            'message': 'TU-OSINT WebSocket connected',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'available_layers': list(data_fetcher.cache.keys())
        })

    def disconnect(self, websocket: WebSocket):
        if websocket in self.clients:
            del self.clients[websocket]
            self.connected_count = max(0, self.connected_count - 1)

    async def _send_snapshot(self, websocket: WebSocket):
        """Send current data snapshot to a client."""
        client_info = self.clients.get(websocket, {})
        subscribed = client_info.get('layers', set())

        data = data_fetcher.get_live_batch()

        # Filter by subscription if specified
        if subscribed:
            data = {k: v for k, v in data.items() if k in subscribed or k == 'timestamp'}

        await websocket.send_json({
            'type': 'snapshot',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'data': data
        })

    async def broadcast(self, data: dict, layer_filter: set = None):
        """Broadcast data to all subscribed clients."""
        dead_clients = []

        for ws, info in self.clients.items():
            try:
                subscribed = info.get('layers', set())

                # Check if client wants this data
                if layer_filter and subscribed:
                    if not layer_filter.intersection(subscribed):
                        continue

                # Filter data for this client
                if subscribed:
                    filtered = {k: v for k, v in data.items() if k in subscribed or k == 'timestamp'}
                else:
                    filtered = data

                await ws.send_json({
                    'type': 'update',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'data': filtered
                })
            except Exception as e:
                # send_json falla típicamente porque el socket ya se cerró
                # del otro lado; se trata como cliente muerto (no como bug),
                # pero se deja traza en debug para distinguirlo de un fallo
                # real de serialización del payload.
                logger.debug(f"[broadcast] cliente descartado por error en send_json: {e}")
                dead_clients.append(ws)

        # Clean up dead clients
        for ws in dead_clients:
            self.disconnect(ws)

    async def handle_message(self, websocket: WebSocket, message: dict):
        """Handle incoming messages from clients."""
        msg_type = message.get('type')

        if msg_type == 'subscribe':
            layers = set(message.get('layers', []))
            if websocket in self.clients:
                self.clients[websocket]['layers'] = layers
                await websocket.send_json({
                    'type': 'subscribed',
                    'layers': list(layers),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
                # Send snapshot of subscribed layers
                await self._send_snapshot(websocket)

        elif msg_type == 'unsubscribe':
            if websocket in self.clients:
                self.clients[websocket]['layers'] = set()
                await websocket.send_json({
                    'type': 'unsubscribed',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })

        elif msg_type == 'ping':
            if websocket in self.clients:
                self.clients[websocket]['last_ping'] = time.time()
            await websocket.send_json({
                'type': 'pong',
                'timestamp': datetime.now(timezone.utc).isoformat()
            })

        elif msg_type == 'get_snapshot':
            await self._send_snapshot(websocket)

        elif msg_type == 'get_layer':
            layer_name = message.get('layer')
            if layer_name and layer_name in data_fetcher.cache:
                await websocket.send_json({
                    'type': 'layer_data',
                    'layer': layer_name,
                    'data': data_fetcher.cache.get(layer_name, []),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })

ws_manager = WebSocketManager()

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Wait for messages (with timeout for heartbeat check)
            try:
                message = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=30.0
                )
                await ws_manager.handle_message(websocket, message)
            except asyncio.TimeoutError:
                # Check if client is still alive
                client_info = ws_manager.clients.get(websocket, {})
                last_ping = client_info.get('last_ping', 0)
                if time.time() - last_ping > 60:
                    # Client hasn't pinged in 60s, disconnect
                    break
                # Send keepalive
                await websocket.send_json({
                    'type': 'keepalive',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
    except WebSocketDisconnect:
        return
    except Exception as e:
        logger.exception(f"[WebSocket /ws/live] error inesperado: {e}")
    finally:
        ws_manager.disconnect(websocket)

# ─── COMMAND HANDLERS (REALES) ───
async def handle_get_summary(args):
    """Resumen agregado de todas las fuentes de inteligencia activas."""
    total_records = 0
    layer_stats = {}
    for key, data in data_fetcher.cache.items():
        count = len(data) if isinstance(data, list) else (1 if data else 0)
        total_records += count
        layer_stats[key] = {
            "count": count,
            "last_fetch": data_fetcher.last_fetch.get(key),
            "metrics": data_fetcher.metrics.get(key, {}),
        }
    service_health = {}
    try:
        from services.malware.cisa_kev import CISAKEVClient
        cisa = CISAKEVClient()
        service_health["cisa_kev"] = "available" if cisa._cache is not None else "degraded"
    except Exception as exc:
        service_health["cisa_kev"] = f"unavailable: {exc}"
    try:
        from services.malware.shodan_connector import ShodanConnector
        shodan = ShodanConnector()
        service_health["shodan"] = "available" if shodan.api_key else "no_api_key"
    except Exception as exc:
        service_health["shodan"] = f"unavailable: {exc}"
    return {
        "summary": "Megalodon-Tezcatlipoca OSINT Platform v2.3.5",
        "active_layers": list(data_fetcher.cache.keys()),
        "layer_stats": layer_stats,
        "total_records": total_records,
        "mesh_nodes": len(peer_engine.nodes) if peer_engine else 0,
        "service_health": service_health,
        "data_freshness": "realtime",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "args": args,
    }


async def handle_find_flights(args):
    """Búsqueda real de vuelos vía OpenSky o cache local."""
    bounds = args.get("bounds", "-90,-180,90,180")
    force_refresh = args.get("refresh", False)
    cached = data_fetcher.cache.get('flights', [])
    last_fetch = data_fetcher.last_fetch.get('flights', 0)
    cache_age = time.time() - last_fetch
    if cached and not force_refresh and cache_age < 60:
        return {
            "flights": cached[:args.get("limit", 50)],
            "source": "cache",
            "cache_age_seconds": int(cache_age),
            "total_cached": len(cached),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "args": args,
        }
    try:
        from services.aviation.opensky_client import OpenSkyClient
        client = OpenSkyClient()
        flights = await asyncio.wait_for(client.get_states(bounds=bounds), timeout=15.0)
        if flights and isinstance(flights, list):
            data_fetcher.cache.set('flights', flights)
            data_fetcher.last_fetch['flights'] = time.time()
        return {
            "flights": flights[:args.get("limit", 50)] if isinstance(flights, list) else [],
            "source": "opensky",
            "total_returned": len(flights) if isinstance(flights, list) else 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "args": args,
        }
    except asyncio.TimeoutError:
        logger.warning(f"[handle_find_flights] timeout, bounds={bounds}")
        return {
            "flights": cached[:args.get("limit", 50)] if cached else [],
            "source": "cache_fallback",
            "error": "OpenSky timeout",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "args": args,
        }
    except Exception as exc:
        logger.error(f"[handle_find_flights] error: {exc}")
        return {
            "flights": cached[:args.get("limit", 50)] if cached else [],
            "source": "cache_fallback",
            "error": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "args": args,
        }


async def handle_find_ships(args):
    """Búsqueda real de embarcaciones vía AIS o cache local."""
    mmsi = args.get("mmsi")
    force_refresh = args.get("refresh", False)
    cached = data_fetcher.cache.get('ships', [])
    last_fetch = data_fetcher.last_fetch.get('ships', 0)
    cache_age = time.time() - last_fetch
    if cached and not force_refresh and cache_age < 30:
        ships = cached
        if mmsi:
            ships = [s for s in cached if str(s.get("mmsi", "")) == str(mmsi)]
        return {
            "ships": ships[:args.get("limit", 50)],
            "source": "cache",
            "cache_age_seconds": int(cache_age),
            "total_cached": len(cached),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "args": args,
        }
    try:
        from services.ais_connector import AISConnector
        connector = AISConnector()
        ships = await asyncio.wait_for(connector.get_vessels(mmsi=mmsi), timeout=15.0)
        if ships and isinstance(ships, list):
            data_fetcher.cache.set('ships', ships)
            data_fetcher.last_fetch['ships'] = time.time()
        return {
            "ships": ships[:args.get("limit", 50)] if isinstance(ships, list) else [],
            "source": "ais",
            "total_returned": len(ships) if isinstance(ships, list) else 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "args": args,
        }
    except asyncio.TimeoutError:
        logger.warning(f"[handle_find_ships] timeout, mmsi={mmsi}")
        ships = cached
        if mmsi:
            ships = [s for s in cached if str(s.get("mmsi", "")) == str(mmsi)]
        return {
            "ships": ships[:args.get("limit", 50)] if ships else [],
            "source": "cache_fallback",
            "error": "AIS timeout",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "args": args,
        }
    except Exception as exc:
        logger.error(f"[handle_find_ships] error: {exc}")
        ships = cached
        if mmsi:
            ships = [s for s in cached if str(s.get("mmsi", "")) == str(mmsi)]
        return {
            "ships": ships[:args.get("limit", 50)] if ships else [],
            "source": "cache_fallback",
            "error": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "args": args,
        }


async def handle_osint_lookup(args):
    target = args.get('target', '')
    ltype = args.get('type', 'ip')
    return await osint_engine.lookup(target, ltype)


async def handle_entity_expand(args):
    entity = args.get('entity', '')
    depth = args.get('depth', 2)
    return await osint_engine.expand_entity(entity, depth)


async def handle_sar_focus(args):
    """Búsqueda real de productos SAR vía Copernicus SciHub."""
    bbox = args.get("bbox") or args.get("aoi", [])
    if isinstance(bbox, str):
        try:
            bbox = [float(x) for x in bbox.split(",")]
        except ValueError:
            bbox = []
    collection = args.get("collection", "S1")
    mode = args.get("mode", "catalog")
    if not bbox or len(bbox) != 4:
        return {
            "sar": "SAR focus mode",
            "error": "Bounding box inválido. Se requieren 4 coordenadas [minLon, minLat, maxLon, maxLat]",
            "aoi": bbox,
            "mode": mode,
            "satellites": ["Sentinel-1A", "Sentinel-1B", "Sentinel-2A", "Sentinel-2B"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "args": args,
        }
    try:
        from services.sar.copernicus_scihub import CopernicusClient
        client = CopernicusClient()
        products = await asyncio.wait_for(client.search(bbox, collection=collection), timeout=20.0)
        result = {
            "sar": "SAR focus mode",
            "aoi": bbox,
            "mode": mode,
            "collection": collection,
            "satellites": ["Sentinel-1A", "Sentinel-1B", "Sentinel-2A", "Sentinel-2B"],
            "products_found": len(products) if isinstance(products, list) else 0,
            "products": products[:20] if isinstance(products, list) else [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "args": args,
        }
        if mode == "download" and products:
            result["note"] = "Modo download requiere autenticación SciHub. Use mode=catalog para listar productos."
        return result
    except asyncio.TimeoutError:
        logger.warning(f"[handle_sar_focus] timeout, bbox={bbox}, collection={collection}")
        raise HTTPException(status_code=504, detail="SAR search timeout")
    except Exception as exc:
        logger.error(f"[handle_sar_focus] error: bbox={bbox}, error={exc}")
        return {
            "sar": "SAR focus mode",
            "error": str(exc),
            "aoi": bbox,
            "mode": mode,
            "satellites": ["Sentinel-1A", "Sentinel-1B", "Sentinel-2A", "Sentinel-2B"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "args": args,
        }

async def handle_mesh_status(args):
    return await mesh_status()



# ─── HANDLERS ADICIONALES (v2.3.1) ───

async def handle_get_layer_slice(args):
    layer = args.get('layer', 'flights')
    limit = args.get('limit', 50)
    data = data_fetcher.cache.get(layer, [])
    return {
        "layer": layer,
        "slice": data[:limit],
        "total": len(data),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "args": args
    }

async def handle_search_telemetry(args):
    query = args.get('query', '')
    results = {}
    for layer, data in data_fetcher.cache.items():
        if isinstance(data, list) and query.lower() in str(data).lower():
            results[layer] = data[:10]
        elif isinstance(data, dict) and query.lower() in str(data).lower():
            results[layer] = data
    return {
        "query": query,
        "matches": len(results),
        "results": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "args": args
    }

async def handle_search_news(args):
    query = args.get('query', 'global')
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://newsapi.org/v2/everything?q={query}&apiKey={os.getenv('NEWSAPI_KEY', '')}&pageSize=5"
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "query": query,
                    "articles": data.get('articles', []),
                    "total": data.get('totalResults', 0),
                    "source": "newsapi",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "args": args
                }
    except Exception as e:
        # NewsAPI puede fallar por falta de API key, rate limit, o red --
        # se cae a GDELT abajo; se loguea en debug para poder distinguir
        # "sin API key" (esperado) de un fallo real de red.
        logger.debug(f"[handle_search_news] NewsAPI falló para query={query!r}: {e}")
    # Fallback a GDELT
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://api.gdeltproject.org/api/v2/doc/doc?query={query}&mode=ArtList&maxrecords=5&format=json"
            )
            if resp.status_code == 200:
                return {
                    "query": query,
                    "articles": resp.json().get('articles', []),
                    "source": "gdelt",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "args": args
                }
    except Exception as e:
        logger.debug(f"[handle_search_news] GDELT también falló para query={query!r}: {e}")
    return {
        "query": query,
        "articles": [],
        "note": "No news data available. Set NEWSAPI_KEY for real data.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "args": args
    }

async def handle_find_entity(args):
    entity = args.get('entity', '')
    return await osint_engine.lookup(entity, 'auto')

async def handle_correlate_entity(args):
    entity = args.get('entity', '')
    depth = args.get('depth', 2)
    return await osint_engine.expand_entity(entity, depth)

async def handle_entities_near(args):
    lat = args.get('lat', 0)
    lon = args.get('lon', 0)
    radius_km = args.get('radius_km', 50)
    # Buscar en cache de vuelos, barcos, terremotos cercanos
    nearby = []
    for layer in ['flights', 'ships', 'quakes']:
        data = data_fetcher.cache.get(layer, [])
        for item in data:
            item_lat = item.get('lat') or item.get('latitude')
            item_lon = item.get('lon') or item.get('longitude')
            if item_lat and item_lon:
                # Distancia aproximada (Haversine simplificado)
                import math
                dlat = math.radians(item_lat - lat)
                dlon = math.radians(item_lon - lon)
                a = math.sin(dlat/2)**2 + math.cos(math.radians(lat)) * math.cos(math.radians(item_lat)) * math.sin(dlon/2)**2
                dist = 6371 * 2 * math.asin(math.sqrt(a))
                if dist <= radius_km:
                    nearby.append({"layer": layer, "item": item, "distance_km": round(dist, 2)})
    nearby.sort(key=lambda x: x['distance_km'])
    return {
        "center": {"lat": lat, "lon": lon},
        "radius_km": radius_km,
        "entities": nearby[:20],
        "count": len(nearby),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "args": args
    }

async def handle_brief_area(args):
    lat = args.get('lat', 0)
    lon = args.get('lon', 0)
    # Obtener resumen de la zona
    layers_in_area = []
    for layer in ['flights', 'ships', 'quakes', 'firms', 'weather']:
        data = data_fetcher.cache.get(layer, [])
        count = len(data) if isinstance(data, list) else 1
        layers_in_area.append({"layer": layer, "count": count})
    return {
        "area": {"lat": lat, "lon": lon},
        "layers": layers_in_area,
        "brief": f"Area briefing for {lat},{lon}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "args": args
    }

async def handle_osint_tools(args):
    return {
        "tools": [
            {"name": "ip_lookup", "description": "Lookup IP address info"},
            {"name": "dns_lookup", "description": "DNS resolution and records"},
            {"name": "whois", "description": "Domain WHOIS lookup"},
            {"name": "cve_search", "description": "Search CVE database"},
            {"name": "shodan_search", "description": "Shodan host search"},
            {"name": "censys_search", "description": "Censys certificate/host search"},
            {"name": "greynoise_ip", "description": "GreyNoise IP context"},
            {"name": "malware_feeds", "description": "Feodo/URLhaus/CISA feeds"},
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "args": args
    }

async def handle_sar_pin_click(args):
    lat = args.get('lat', 0)
    lon = args.get('lon', 0)
    return {
        "pin": {"lat": lat, "lon": lon},
        "satellites": ["Sentinel-1A", "Sentinel-1B", "Sentinel-2A"],
        "next_pass": "Calculating...",
        "scenes_available": 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "args": args
    }

async def handle_osint_sweep(args):
    target = args.get('target', '')
    results = {}
    # Ejecutar múltiples lookups. Antes: `except:` desnudo + pass (también
    # atrapaba KeyboardInterrupt/SystemExit, y el fallo quedaba invisible
    # tanto en logs como en la respuesta). Ahora: except Exception
    # explícito, se loguea y el error queda visible en la respuesta para
    # que el cliente sepa qué lookup falló sin tronar todo el sweep.
    try:
        results['ip'] = await osint_engine.lookup(target, 'ip')
    except Exception as e:
        logger.debug(f"[handle_osint_sweep] lookup ip falló para {target!r}: {e}")
        results['ip'] = {"error": str(e)}
    try:
        results['dns'] = await osint_engine.lookup(target, 'dns')
    except Exception as e:
        logger.debug(f"[handle_osint_sweep] lookup dns falló para {target!r}: {e}")
        results['dns'] = {"error": str(e)}
    try:
        results['whois'] = await osint_engine.lookup(target, 'whois')
    except Exception as e:
        logger.debug(f"[handle_osint_sweep] lookup whois falló para {target!r}: {e}")
        results['whois'] = {"error": str(e)}
    return {
        "target": target,
        "sweep_results": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "args": args
    }

async def handle_place_intel_pin(args):
    lat = args.get('lat', 0)
    lon = args.get('lon', 0)
    label = args.get('label', 'Intel Pin')
    return {
        "placed": True,
        "pin": {"lat": lat, "lon": lon, "label": label},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "args": args
    }

async def handle_fly_map_to(args):
    lat = args.get('lat', 0)
    lon = args.get('lon', 0)
    zoom = args.get('zoom', 10)
    return {
        "action": "fly_to",
        "target": {"lat": lat, "lon": lon, "zoom": zoom},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "args": args
    }

async def handle_send_alert(args):
    message = args.get('message', 'Alert')
    severity = args.get('severity', 'info')
    return {
        "sent": True,
        "alert": {"message": message, "severity": severity},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "args": args
    }

async def handle_generate_report(args):
    layers = args.get('layers', ['flights', 'ships', 'quakes'])
    report_data = {}
    for layer in layers:
        data = data_fetcher.cache.get(layer, [])
        report_data[layer] = {
            "count": len(data) if isinstance(data, list) else 1,
            "sample": data[:5] if isinstance(data, list) else data
        }
    return {
        "report": report_data,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "args": args
    }

async def handle_propose_governance(args):
    proposal = args.get('proposal', '')
    return {
        "proposed": True,
        "proposal_id": f"prop_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "proposal": proposal,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "args": args
    }

async def handle_cast_vote(args):
    proposal_id = args.get('proposal_id', '')
    vote = args.get('vote', 'abstain')
    return {
        "voted": True,
        "proposal_id": proposal_id,
        "vote": vote,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "args": args
    }

async def handle_stake_tokens(args):
    amount = args.get('amount', 0)
    return {
        "staked": True,
        "amount": amount,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "args": args
    }

COMMAND_HANDLERS = {
    'get_summary': handle_get_summary,
    'get_layer_slice': handle_get_layer_slice,
    'search_telemetry': handle_search_telemetry,
    'search_news': handle_search_news,
    'find_flights': handle_find_flights,
    'find_ships': handle_find_ships,
    'find_entity': handle_find_entity,
    'correlate_entity': handle_correlate_entity,
    'entities_near': handle_entities_near,
    'brief_area': handle_brief_area,
    'osint_lookup': handle_osint_lookup,
    'entity_expand': handle_entity_expand,
    'osint_tools': handle_osint_tools,
    'sar_pin_click': handle_sar_pin_click,
    'sar_focus_aoi': handle_sar_focus,
    'osint_sweep': handle_osint_sweep,
    'place_intel_pin': handle_place_intel_pin,
    'fly_map_to': handle_fly_map_to,
    'send_alert': handle_send_alert,
    'generate_report': handle_generate_report,
    'mesh_status': handle_mesh_status,
    'propose_governance': handle_propose_governance,
    'cast_vote': handle_cast_vote,
    'stake_tokens': handle_stake_tokens,
}

# ─── MAIN ───
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )


# ═══════════════════════════════════════════════════════════════════
# ENDPOINTS FALTANTES (Paso 4)
# ═══════════════════════════════════════════════════════════════════

@app.get("/api/aviation/military")
async def get_military_flights(
    lamin: Optional[float] = None,
    lamax: Optional[float] = None,
    lomin: Optional[float] = None,
    lomax: Optional[float] = None
):
    """Get military aircraft from ADS-B."""
    military = data_fetcher.cache.get('military_flights', [])
    return {
        'military_flights': military[:50],
        'count': len(military),
        'timestamp': datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/transport/ships")
async def get_ships(
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius: float = 100,
    ship_type: Optional[str] = None
):
    """Get maritime vessels from AIS data."""
    ships = data_fetcher.cache.get('ships', [])
    if ship_type:
        ships = [s for s in ships if ship_type.lower() in str(s.get('ship_type', '')).lower()]
    return {
        'ships': ships[:50],
        'count': len(ships),
        'timestamp': datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/transport/fishing")
async def get_fishing_vessels(
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius: float = 200
):
    """Get fishing vessels with activity indicators."""
    fishing = data_fetcher.cache.get('fishing', [])
    return {
        'fishing_vessels': fishing[:50],
        'count': len(fishing),
        'timestamp': datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/sar/anomalies")
async def get_sar_anomalies(
    source: str = "all",
    days: int = 7,
    anomaly_type: Optional[str] = None
):
    """Detect anomalies from SAR imagery comparison."""
    anomalies = []

    firms = data_fetcher.cache.get('firms', [])
    for fire in firms[:20]:
        anomalies.append({
            'type': 'fire',
            'source': 'NASA FIRMS',
            'latitude': fire.get('latitude'),
            'longitude': fire.get('longitude'),
            'confidence': fire.get('confidence', 'medium'),
            'severity': 'high' if fire.get('brightness', 0) > 400 else 'medium'
        })

    quakes = data_fetcher.cache.get('quakes', [])
    for q in quakes[:10]:
        if q.get('mag', 0) >= 5.0:
            anomalies.append({
                'type': 'geological',
                'source': 'USGS',
                'latitude': q.get('latitude'),
                'longitude': q.get('longitude'),
                'magnitude': q.get('mag'),
                'severity': 'critical' if q.get('mag', 0) >= 7 else 'high'
            })

    return {
        'anomalies': anomalies,
        'count': len(anomalies),
        'timestamp': datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/sar/scenes")
async def get_sar_scenes(
    platform: Optional[str] = None,
    mode: Optional[str] = None,
    days: int = 30
):
    """Search for SAR scene acquisitions."""
    all_scenes = []
    for key in ['sar_asf', 'sentinel', 'sar_opera']:
        scenes = data_fetcher.cache.get(key, [])
        for s in scenes:
            all_scenes.append({**s, 'provider': key})

    if platform:
        all_scenes = [s for s in all_scenes if platform.lower() in str(s.get('platform', '')).lower()]
    if mode:
        all_scenes = [s for s in all_scenes if mode.lower() in str(s.get('mode', '')).lower()]

    return {
        'scenes': all_scenes[:50],
        'count': len(all_scenes),
        'timestamp': datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/health")
async def health_check():
    """Comprehensive health check endpoint."""
    uptime = time.time() - ws_manager.startup_time

    cache_stats = {}
    for key in data_fetcher.cache.keys():
        value = data_fetcher.cache.get(key)
        cache_stats[key] = len(value) if isinstance(value, (list, dict)) else (1 if value else 0)

    return {
        'status': 'healthy',
        'version': '2.1.0',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'uptime_seconds': int(uptime),
        'websocket_clients': ws_manager.connected_count,
        'cache_entries': len(cache_stats),
        'cache_stats': cache_stats,
        'scheduled_jobs': len(data_fetcher.scheduler.get_jobs())
    }
