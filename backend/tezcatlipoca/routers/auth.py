from services.redis_client import redis_client
from core.rate_limit import rate_limit_standard, rate_limit_strict
from core.megalodon_bridge import (
    MEGALODON_REFRESH_COOKIE,
    MEGALODON_SESSION_COOKIE,
    attach_identity,
    load_megalodon_user,
    sync_shadow_user,
)
from app.config import settings
from app.core.deps import get_db as megalodon_get_db
from app.core.token_revocation import revoke_jti
import structlog

logger = structlog.get_logger("tezcatlipoca.auth")
# Antes `logger` no estaba importado/definido en ningún lado de este
# archivo: las dos llamadas en _record_auth_attempt() (abajo) hacían
# NameError apenas fallaba Redis. Como esa función corre dentro de un
# asyncio.Task en segundo plano (fire-and-forget) para no bloquear el
# login, el NameError no tumbaba el request -- pero sí rompía en
# silencio el registro forense de intentos de auth fallidos, que es
# precisamente el dato que se necesita ver cuando hay actividad
# sospechosa.
"""Auth Router V3 — JWT + SQLite + Rate Limiting + httpOnly Cookies.

Production-ready authentication with:
- bcrypt password hashing (12 rounds)
- JWT access + refresh tokens
- Token revocation (blacklist)
- Rate limiting on auth endpoints
- Request logging
- httpOnly cookies (Secure, SameSite=Strict)
- Session tracking in database
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
import jwt
import bcrypt

from db.models import (
    get_async_db, User, TokenBlacklist, ApiLog, UserSession,
    
)

router = APIRouter(tags=["auth"])

# ─── Config ───
import os
JWT_SECRET = settings.SECRET_KEY
JWT_ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24      # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS = 7
MAX_LOGIN_ATTEMPTS = 5
LOGIN_COOLDOWN_MINUTES = 15

# Cookie settings
COOKIE_NAME = MEGALODON_SESSION_COOKIE
REFRESH_COOKIE_NAME = MEGALODON_REFRESH_COOKIE
COOKIE_SECURE = settings.is_production
COOKIE_SAMESITE = "Strict"
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", None)  # Set for production domain
COOKIE_PATH = "/"

security_bearer = HTTPBearer(auto_error=False)

# ─── Models ───

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8, max_length=128)
    tier: str = Field(default="restricted", pattern=r"^(restricted|full|admin)$")

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    token_type: str = "bearer"
    expires_in: int
    user: dict

class UserResponse(BaseModel):
    username: str
    tier: str
    created_at: str
    api_calls_total: int

class RefreshRequest(BaseModel):
    refresh_token: str

# ─── Helpers ───

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())

def _create_token(username: str, tier: str, token_type: str = "access") -> tuple:
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    if token_type == "access":
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    else:
        expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": username,
        "tier": tier,
        "type": token_type,
        "jti": jti,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM), jti, expire

def _decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# ═══════════════════════════════════════════════════════════════════
# FASE 2 -- PUENTE DE IDENTIDAD CON MEGALODON (decisión de producto:
# los recursos de Tezcatlipoca son por tenant de Megalodon, no
# globales ni por usuario suelto).
#
# Megalodon ya firma sus access tokens con SECRET_KEY/HS256 y ya
# incluye tenant_id + role en el payload (ver
# backend/app/services/auth_service.py::create_access_token). JWT_SECRET
# arriba en este archivo YA leía SECRET_KEY como fallback desde antes
# de este cambio, así que ambos backends firman/verifican con el mismo
# secreto sin tocar configuración adicional.
#
# Esto reemplaza la verificación de token propia de Tezcatlipoca por
# decodificar el token de Megalodon directamente. NO se preserva el
# mecanismo de revocación por jti/TokenBlacklist para estos tokens:
# los tokens de Megalodon no traen jti, y su revocación es
# responsabilidad de Megalodon, no de este puente. En la práctica el
# expuesto es pequeño (ACCESS_TOKEN_EXPIRE_MINUTES de Megalodon, 30 min
# por default) pero queda documentado a propósito, no oculto.
# ═══════════════════════════════════════════════════════════════════

# Mapa de decisión: rol de Megalodon -> tier de Tezcatlipoca. Esto SÍ es
# una decisión de control de acceso real (¿debería un TECNICO poder
# activar honeypots o votar en mesh_governance?) -- se dejó así porque
# es la lectura más conservadora de los nombres de rol existentes, pero
# revísalo antes de confiar en él para producción.
_MEGALODON_ROLE_TO_TIER = {
    "superadmin": "admin",
    "admin": "admin",
    "tecnico": "full",
    "revisor": "restricted",
    "lector": "restricted",
    "invitado": "restricted",
}


def _decode_megalodon_token(token: str) -> Optional[dict]:
    """Decodifica un access token emitido por Megalodon (mismo
    SECRET_KEY/HS256). Devuelve None si es inválido, expiró, o es un
    refresh token (esos no deben autenticar llamadas a la API)."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    if payload.get("type") != "access":
        return None
    if not payload.get("sub") or not payload.get("tenant_id"):
        return None
    return payload


async def _sync_shadow_user(db: AsyncSession, megalodon_user) -> User:
    """Crea o actualiza la fila espejo local a partir del usuario de Megalodon."""
    shadow_user = await sync_shadow_user(db, megalodon_user)
    return shadow_user

async def _is_token_revoked(db: AsyncSession, jti: str) -> bool:
    # Check Redis first (fast)
    if await redis_client.is_token_blacklisted(jti):
        return True
    # Fallback to DB
    result = await db.execute(select(TokenBlacklist).where(TokenBlacklist.token_jti == jti))
    return result.scalar_one_or_none() is not None

async def _is_session_revoked(db: AsyncSession, session_token: str) -> bool:
    """Check if session is still active in database."""
    result = await db.execute(
        select(UserSession).where(
            UserSession.session_token == session_token,
            UserSession.is_active == True,
            UserSession.expires_at > datetime.now(timezone.utc)
        )
    )
    session = result.scalar_one_or_none()
    return session is None

async def _create_session(db: AsyncSession, user_id: int, jti: str, ip: str, ua: str, expires_at: datetime) -> str:
    """Create a session record in database."""
    session_token = str(uuid.uuid4())
    session = UserSession(
        user_id=user_id,
        session_token=session_token,
        jti=jti,
        ip_address=ip,
        user_agent=ua,
        expires_at=expires_at
    )
    db.add(session)
    await db.commit()
    return session_token

async def _revoke_session(db: AsyncSession, session_token: str):
    """Revoke a session in database."""
    result = await db.execute(select(UserSession).where(UserSession.session_token == session_token))
    session = result.scalar_one_or_none()
    if session:
        session.is_active = False
        await db.commit()

async def _set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    """Set httpOnly cookies with JWT tokens."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
        path=COOKIE_PATH,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
        path=COOKIE_PATH,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )

async def _clear_auth_cookies(response: Response):
    """Clear auth cookies."""
    response.delete_cookie(key=COOKIE_NAME, path=COOKIE_PATH, domain=COOKIE_DOMAIN)
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=COOKIE_PATH, domain=COOKIE_DOMAIN)
    response.delete_cookie(key="megalodon_session", path=COOKIE_PATH, domain=COOKIE_DOMAIN)
    response.delete_cookie(key="megalodon_refresh_token", path=COOKIE_PATH, domain=COOKIE_DOMAIN)

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security_bearer),
    megalodon_db: AsyncSession = Depends(megalodon_get_db),
    shadow_db: AsyncSession = Depends(get_async_db),
) -> User:
    """Autentica con Megalodon y mantiene un espejo local mínimo.

    Todo request de datos/operaciones de Tezcatlipoca debe pertenecer a un
    tenant de Megalodon. Los datasets públicos siguen siendo globales como
    dato de origen, pero la consulta, cuota, auditoría y cualquier resultado
    persistido quedan bajo el contexto del tenant.
    """
    megalodon_user = await load_megalodon_user(request, credentials, megalodon_db)
    if not getattr(megalodon_user, "tenant_id", None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario autenticado no tiene tenant activo.",
        )
    user = await _sync_shadow_user(shadow_db, megalodon_user)
    attach_identity(request, megalodon_user, user)
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

def require_role(roles: list):
    """Dependency factory to require specific user roles."""
    async def _check_role(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
    ):
        if current_user.tier not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: one of {roles}"
            )
        return current_user
    return _check_role

async def _log_request(db: AsyncSession, user_id: Optional[int], endpoint: str, method: str, status_code: int, ip: str = "", ua: str = "", tenant_id: Optional[str] = None):
    """Log API request to database."""
    log = ApiLog(
        user_id=user_id,
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        ip_address=ip,
        user_agent=ua,
        tenant_id=tenant_id,
    )
    db.add(log)
    await db.commit()

# ─── Rate Limiting (Redis-backed) ───
async def _check_rate_limit(ip: str) -> bool:
    """Check if IP is rate limited for login attempts."""
    allowed, remaining = await redis_client.check_rate_limit(
        f"login:{ip}", MAX_LOGIN_ATTEMPTS, LOGIN_COOLDOWN_MINUTES * 60
    )
    return allowed

def _record_attempt(ip: str) -> None:
    """Registra un intento de login en Redis para auditoria post-incidente.

    El rate limiting propiamente dicho ya se maneja en _check_rate_limit().
    Este registro es puramente de auditoria y forense.
    """
    import asyncio
    from datetime import datetime, timezone
    from services.redis_client import redis_client

    async def _do_record() -> None:
        try:
            connected = await redis_client.connect()
            if not connected or redis_client._client is None:
                return
            ts = datetime.now(timezone.utc).isoformat()
            day_key = datetime.now(timezone.utc).strftime("%Y%m%d")
            key = f"auth:attempts:{ip}:{day_key}"
            await redis_client._client.lpush(key, ts)
            await redis_client._client.expire(key, 86400 * 7)
        except Exception as exc:
            logger.warning(
                "auth_attempt_record_failed",
                ip=ip,
                error=str(exc),
                note="audit_record_only_rate_limit_still_active",
            )

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_do_record())
    except RuntimeError as exc:
        logger.debug("auth_attempt_no_running_loop", error=str(exc))

# ─── Endpoints ───

@router.post("/register", response_model=TokenResponse)
async def register(
    req: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_strict)
):
    """Register a new user account.

    DESACTIVADO (Fase 2): login único vía Megalodon. Crear cuentas acá
    generaría una segunda puerta de entrada con su propia tabla de
    contraseñas -- exactamente la superficie duplicada que esta fase
    buscaba cerrar. El cuerpo original se deja abajo sin usar como
    referencia, no se borró.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Este registro ya no está activo. Crea la cuenta en Megalodon "
               "(/api/v1/auth/register); Tezcatlipoca la reconoce automáticamente "
               "por tenant en el primer request autenticado.",
    )
    # Check if user exists
    result = await db.execute(select(User).where(User.username == req.username))
    if result.scalar_one_or_none():
        await _log_request(db, None, "/api/auth/register", "POST", 409, request.client.host, request.headers.get("user-agent", ""))
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    password_hash = _hash_password(req.password)
    user = User(
        username=req.username,
        password_hash=password_hash,
        tier=req.tier
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token, access_jti, access_exp = _create_token(req.username, req.tier, "access")
    refresh_token, refresh_jti, refresh_exp = _create_token(req.username, req.tier, "refresh")

    # Create session in DB
    await _create_session(db, user.id, access_jti, 
                         request.client.host if request.client else "", 
                         request.headers.get("user-agent", ""), 
                         access_exp)

    await _set_auth_cookies(response, access_token, refresh_token)

    _log_request(db, user.id, "/api/auth/register", "POST", 200, request.client.host, request.headers.get("user-agent", ""))

    return TokenResponse(
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={"username": req.username, "tier": req.tier, "created_at": user.created_at.isoformat()}
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_strict)
):
    """Authenticate and receive JWT tokens via httpOnly cookies.

    DESACTIVADO (Fase 2): login único vía Megalodon. Cuerpo original
    abajo, sin usar, como referencia.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Este login ya no está activo. Autentícate en Megalodon "
               "(/api/v1/auth/login); usa ese mismo token contra las rutas "
               "/api/tezcatlipoca/*.",
    )
    client_ip = request.client.host if request.client else "unknown"

    # Rate limiting
    if not await _check_rate_limit(client_ip):
        _log_request(db, None, "/api/auth/login", "POST", 429, client_ip, request.headers.get("user-agent", ""))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Try again in {LOGIN_COOLDOWN_MINUTES} minutes."
        )

    result = await db.execute(select(User).where(User.username == req.username, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user or not _verify_password(req.password, user.password_hash):
        _record_attempt(client_ip)
        _log_request(db, None, "/api/auth/login", "POST", 401, client_ip, request.headers.get("user-agent", ""))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    # Update last login
    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    access_token, access_jti, access_exp = _create_token(user.username, user.tier, "access")
    refresh_token, refresh_jti, refresh_exp = _create_token(user.username, user.tier, "refresh")

    # Create session in DB
    await _create_session(db, user.id, access_jti, 
                         client_ip, 
                         request.headers.get("user-agent", ""), 
                         access_exp)

    await _set_auth_cookies(response, access_token, refresh_token)

    _log_request(db, user.id, "/api/auth/login", "POST", 200, client_ip, request.headers.get("user-agent", ""))

    return TokenResponse(
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "username": user.username,
            "tier": user.tier,
            "created_at": user.created_at.isoformat()
        }
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_standard)):
    """Get current authenticated user information."""
    return UserResponse(
        username=current_user.username,
        tier=current_user.tier,
        created_at=current_user.created_at.isoformat(),
        api_calls_total=current_user.api_calls_total
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_strict)
):
    """Refresh access token using refresh cookie.

    DESACTIVADO (Fase 2): el refresh de sesión ahora es responsabilidad
    de Megalodon. Cuerpo original abajo, sin usar, como referencia.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Este refresh ya no está activo. Usa el endpoint de refresh "
               "de Megalodon (/api/v1/auth/refresh).",
    )
    # Try cookie first
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)

    # Fallback to body (for API clients)
    if not refresh_token:
        body = await request.json()
        refresh_token = body.get("refresh_token")

    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")

    payload = _decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    # Check if refresh token is revoked
    jti = payload.get("jti")
    if jti and await _is_token_revoked(db, jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")

    username = payload.get("sub")
    result = await db.execute(select(User).where(User.username == username, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access_token, access_jti, access_exp = _create_token(user.username, user.tier, "access")
    new_refresh_token, refresh_jti, refresh_exp = _create_token(user.username, user.tier, "refresh")

    # Create new session
    await _create_session(db, user.id, access_jti, 
                         request.client.host if request.client else "", 
                         request.headers.get("user-agent", ""), 
                         access_exp)

    await _set_auth_cookies(response, access_token, new_refresh_token)

    return TokenResponse(
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "username": user.username,
            "tier": user.tier,
            "created_at": user.created_at.isoformat()
        }
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    megalodon_db: AsyncSession = Depends(megalodon_get_db),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    """Logout unificado: revoca sesión Megalodon y limpia el espejo local."""
    token = request.cookies.get(COOKIE_NAME) or request.cookies.get(MEGALODON_SESSION_COOKIE)
    session_token = request.cookies.get("osint_session")  # Optional session tracking

    if not token:
        credentials = await security_bearer(request)
        if credentials:
            token = credentials.credentials

    if token:
        payload = _decode_token(token)
        if payload and payload.get("jti"):
            expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
            await revoke_jti(payload["jti"], expires_at, token_kind=payload.get("type", "access"), reason="tezcatlipoca_logout")
            blacklist = TokenBlacklist(
                token_jti=payload["jti"],
                expires_at=expires_at,
            )
            db.add(blacklist)
            await db.commit()

    if session_token:
        await _revoke_session(db, session_token)

    await _clear_auth_cookies(response)

    _log_request(
        db,
        current_user.id,
        "/api/auth/logout",
        "POST",
        200,
        request.client.host if request.client else "",
        request.headers.get("user-agent", ""),
    )

    return {"status": "logged_out", "username": current_user.username}


@router.get("/users/count")
async def get_user_count(
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Get total user count (admin only)."""
    result = await db.execute(select(func.count()).select_from(User))
    count = result.scalar()
    return {"total_users": count}


@router.get("/sessions")
async def get_active_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Get active sessions for current user."""
    result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == current_user.id,
            UserSession.is_active == True,
            UserSession.expires_at > datetime.now(timezone.utc)
        )
    )
    sessions = result.scalars().all()

    return {
        "sessions": [
            {
                "id": s.id,
                "ip_address": s.ip_address,
                "user_agent": s.user_agent,
                "created_at": s.created_at.isoformat(),
                "expires_at": s.expires_at.isoformat(),
                "last_active": s.last_active.isoformat() if s.last_active else None
            }
            for s in sessions
        ]
    }


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_strict)
):
    """Revoke a specific session (user can only revoke their own)."""
    result = await db.execute(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.is_active = False
    await db.commit()

    return {"status": "revoked", "session_id": session_id}


@router.on_event("startup")
async def auth_startup():
    await redis_client.connect()

@router.on_event("shutdown")
async def auth_shutdown():
    await redis_client.disconnect()
