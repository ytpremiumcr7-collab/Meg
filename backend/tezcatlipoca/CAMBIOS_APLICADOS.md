
╔══════════════════════════════════════════════════════════════════════════════╗
║           🔧 TU-OSINT-PLATFORM v2.1.0 — CAMBIOS APLICADOS                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

📁 ARCHIVOS MODIFICADOS (12 total)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔧 BACKEND — Routers corregidos (3):
  ✅ routers/cyber.py        — Quitado prefix="/cyber" duplicado
  ✅ routers/scm.py          — Quitado prefix="/scm" duplicado  
  ✅ routers/wormhole.py     — Quitado prefix="/wormhole" duplicado

🎨 FRONTEND — API Client (1):
  ✅ frontend/src/services/api.ts
     • 76 métodos sincronizados con backend
     • Auth mock (funciona sin backend auth)
     • Manejo de errores consistente

🎨 FRONTEND — Hooks (2):
  ✅ frontend/src/hooks/useApi.ts        — Hook genérico sin rutas hardcodeadas
  ✅ frontend/src/hooks/useWebSocket.ts  — Reconexión automática con backoff

🎨 FRONTEND — Componentes conectados (6):
  ✅ components/ReconPanel.tsx     — IP, Domain, CVE, Shodan, Censys
  ✅ components/MeshTerminal.tsx   — /status, /peers, /proposals, /vote, /propose
  ✅ components/SnapshotPanel.tsx  — Listar, crear, borrar snapshots
  ✅ components/TimeMachine.tsx   — Cargar snapshots por fecha
  ✅ components/LayerPanel.tsx    — Fetch capas desde /api/layers/
  ✅ components/IntelPanel.tsx    — Fallback a APIs cuando WS no llega

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🌐 RUTAS CORREGIDAS (antes → después)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ❌ /api/cyber/cyber/shodan/search  →  ✅ /api/cyber/shodan/search
  ❌ /api/scm/scm/vendors          →  ✅ /api/scm/vendors
  ❌ /api/wormhole/wormhole/tunnels  →  ✅ /api/wormhole/tunnels
  ❌ /api/aviation/flights           →  ✅ /api/aviation/adsb/aircraft
  ❌ /api/mesh/peers                 →  ✅ /api/mesh_governance/nodes
  ❌ /api/telemetry/summary          →  ✅ /api/telemetry/
  ❌ /api/malware/feeds              →  ✅ /api/malware/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚀 CÓMO INICIAR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. Backend:
     cd osint_platform/Mys_Latinoamerica
     python main.py

  2. Frontend (en otra terminal):
     cd osint_platform/Mys_Latinoamerica/frontend
     npm run dev

  3. Verificar rutas (en otra terminal):
     cd osint_platform/Mys_Latinoamerica
     python verify_osint.py

  4. Abrir navegador:
     http://localhost:5173

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️  NOTAS IMPORTANTES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  • Auth es MOCK (simulado). El login funciona pero no valida contra backend.
    Para producción, implementar /api/auth/login y /api/auth/register.

  • Algunos servicios necesitan API keys en .env:
    - SHODAN_API_KEY
    - CENSYS_API_ID / CENSYS_API_SECRET
    - GREYNOISE_API_KEY
    - NASA_EARTHDATA_USER / PASS
    - COPERNICUS_USER / PASS

  • WebSocket (/ws/live) debe empujar datos con nombres de capa correctos:
    flights, quakes, mesh, malware, firms, weather, etc.

  • Endpoints aún NO implementados en backend:
    /api/auth/login, /api/auth/register
    /api/aviation/military
    /api/transport/ships, /api/transport/fishing
    /api/sar/anomalies, /api/sar/scenes

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
