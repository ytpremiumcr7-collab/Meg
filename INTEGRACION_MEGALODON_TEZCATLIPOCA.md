# Integración Megalodon + Tezcatlipoca

## Fuente de verdad
- **Autenticación / identidad**: `backend/app/services/auth_service.py`
- **Tenant / roles / plan**: `backend/app/models/user.py` + `backend/app/core/entitlements.py`
- **Tezcatlipoca** consume esa identidad y mantiene un **shadow user** local únicamente para auditoría y llaves locales.

## Puente operativo
- `backend/tezcatlipoca/core/megalodon_bridge.py`
  - extrae el token de `megalodon_session`
  - valida el JWT con `AuthService` de Megalodon
  - sincroniza el usuario espejo local
  - propaga `tenant_id`, `role`, `tier` y `email` a `request.state`

## SaaS gates
- `ai_channel`, `cyber`, `geo`, `geo_threats`, `malware`, `transport`, `aviation`, `sar`, `photogrammetry`, `telemetry`, `wormhole` y `mesh_governance` ahora están sujetos al plan de Megalodon.
- El nivel mínimo se calcula con `app.core.entitlements.requiere_plan_minimo()` y el plan efectivo del tenant.

## Health / readiness
- `backend/app/main.py`
  - `/health`
  - `/ready` verifica:
    - base de datos
    - estado del startup de Tezcatlipoca dentro del proceso unificado

## Criterio de integración
- Megalodon decide quién entra.
- Tezcatlipoca decide qué módulos puede usar ese tenant.
- El backend unificado arranca con un solo proceso y un solo `SECRET_KEY`.
