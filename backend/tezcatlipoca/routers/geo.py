"""Geo Router - Datos agregados para Solar Geo Platform.

Endpoints optimizados para consumo por el frontend 3D del sistema solar.
Sirve vuelos, barcos y terremotos en formato estandarizado.
"""
from core.rate_limit import rate_limit_standard, rate_limit_strict
from fastapi import APIRouter, Request, Query, Depends
from db.models import User
from routers.auth import get_current_user, require_role
from app.core.entitlements import PlanTipo, requiere_plan_minimo
from typing import List, Dict, Any
from datetime import datetime, timezone

router = APIRouter(tags=["Geo"])


@router.get("/flights")
async def get_geo_flights(
    lat_min: float = Query(-90, ge=-90, le=90),
    lat_max: float = Query(90, ge=-90, le=90),
    lon_min: float = Query(-180, ge=-180, le=180),
    lon_max: float = Query(180, ge=-180, le=180),
    limit: int = Query(500, ge=1, le=2000),
    req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Obtener vuelos en formato compatible con Solar Geo Platform."""
    adsb = req.app.state.adsb_exchange
    df = req.app.state.data_fetcher

    flights = []

    # Intentar ADS-B Exchange primero
    if adsb:
        try:
            data = await adsb.get_aircraft_in_bbox(lat_min, lat_max, lon_min, lon_max)
            ac_list = data.get("ac", []) if isinstance(data, dict) else []
            for ac in ac_list[:limit]:
                flights.append({
                    "icao": ac.get("hex", ""),
                    "hex": ac.get("hex", ""),
                    "lat": ac.get("lat"),
                    "lon": ac.get("lon"),
                    "alt": ac.get("alt_baro", 0),
                    "track": ac.get("track", 0),
                    "spd": ac.get("gs", 0),
                    "flight": ac.get("flight", "").strip(),
                    "airline": ac.get("flight", "")[:2] if ac.get("flight") else "N/A",
                    "from": ac.get("from", "N/A"),
                    "to": ac.get("to", "N/A"),
                    "type": ac.get("t", "N/A"),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
        except Exception as e:
            print(f"⚠️  Error ADS-B flights: {e}")

    # Fallback a cache del data_fetcher
    if not flights and df and hasattr(df, 'cache'):
        cached = df.cache.get('flights', [])
        for f in cached[:limit]:
            if lat_min <= f.get('lat', 0) <= lat_max and lon_min <= f.get('lon', 0) <= lon_max:
                flights.append({
                    "icao": f.get("icao24", ""),
                    "hex": f.get("icao24", ""),
                    "lat": f.get("lat"),
                    "lon": f.get("lon"),
                    "alt": f.get("altitude", 0),
                    "track": f.get("heading", 0),
                    "spd": f.get("velocity", 0),
                    "flight": f.get("callsign", "").strip(),
                    "airline": f.get("callsign", "")[:2] if f.get("callsign") else "N/A",
                    "from": "N/A",
                    "to": "N/A",
                    "type": "N/A",
                    "timestamp": f.get("timestamp", datetime.now(timezone.utc).isoformat())
                })

    return {
        "type": "flights",
        "count": len(flights),
        "bbox": [lat_min, lon_min, lat_max, lon_max],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ac": flights
    }


@router.get("/ships")
async def get_geo_ships(
    lat_min: float = Query(-90, ge=-90, le=90),
    lat_max: float = Query(90, ge=-90, le=90),
    lon_min: float = Query(-180, ge=-180, le=180),
    lon_max: float = Query(180, ge=-180, le=180),
    limit: int = Query(500, ge=1, le=2000),
    req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Obtener barcos en formato compatible con Solar Geo Platform."""
    ais = req.app.state.ais_connector
    df = req.app.state.data_fetcher

    ships = []

    # Intentar AIS connector primero
    if ais:
        try:
            ship_list = ais.get_ships_in_bbox(lat_min, lat_max, lon_min, lon_max)
            for s in ship_list[:limit]:
                ships.append({
                    "mmsi": s.get("mmsi", ""),
                    "shipname": s.get("name", "Desconocido"),
                    "latitude": s.get("latitude"),
                    "longitude": s.get("longitude"),
                    "sog": s.get("sog", 0),
                    "cog": s.get("cog", 0),
                    "heading": s.get("heading", 0),
                    "shiptype": s.get("type", "N/A"),
                    "destination": s.get("destination", "N/A"),
                    "eta": s.get("eta", "N/A"),
                    "timestamp": s.get("timestamp", datetime.now(timezone.utc).isoformat())
                })
        except Exception as e:
            print(f"⚠️  Error AIS ships: {e}")

    # Fallback a cache del data_fetcher (fishing vessels)
    if not ships and df and hasattr(df, 'cache'):
        cached = df.cache.get('fishing', [])
        for v in cached[:limit]:
            if lat_min <= v.get('lat', 0) <= lat_max and lon_min <= v.get('lon', 0) <= lon_max:
                ships.append({
                    "mmsi": v.get("id", ""),
                    "shipname": v.get("name", "Desconocido"),
                    "latitude": v.get("lat"),
                    "longitude": v.get("lon"),
                    "sog": 0,
                    "cog": 0,
                    "heading": 0,
                    "shiptype": v.get("type", "fishing"),
                    "destination": v.get("flag", "N/A"),
                    "eta": "N/A",
                    "timestamp": v.get("timestamp", datetime.now(timezone.utc).isoformat())
                })

    return {
        "type": "ships",
        "count": len(ships),
        "bbox": [lat_min, lon_min, lat_max, lon_max],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ships": ships
    }


@router.get("/earthquakes")
async def get_geo_earthquakes(
    min_magnitude: float = Query(2.5, ge=0, le=10),
    days: int = Query(1, ge=1, le=30),
    limit: int = Query(500, ge=1, le=2000),
    req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Obtener terremotos en formato GeoJSON compatible con Solar Geo Platform."""
    df = req.app.state.data_fetcher

    features = []

    # Intentar cache del data_fetcher primero
    if df and hasattr(df, 'cache'):
        cached = df.cache.get('quakes', [])
        for q in cached[:limit]:
            mag = q.get("mag", 0)
            if mag >= min_magnitude:
                features.append({
                    "type": "Feature",
                    "id": q.get("id", ""),
                    "geometry": {
                        "type": "Point",
                        "coordinates": [
                            q.get("lon", 0),
                            q.get("lat", 0),
                            q.get("depth", 0)
                        ]
                    },
                    "properties": {
                        "mag": mag,
                        "place": q.get("place", "Desconocido"),
                        "time": q.get("timestamp", datetime.now(timezone.utc).isoformat()),
                        "tsunami": q.get("tsunami", 0),
                        "alert": q.get("alert", "green"),
                        "url": q.get("url", "")
                    }
                })

    # Si no hay cache, hacer fetch directo a USGS
    if not features:
        try:
            import httpx
            from datetime import timedelta
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=days)
            url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
            if min_magnitude >= 4.5:
                url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson"
            elif min_magnitude >= 2.5:
                url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    for f in data.get("features", [])[:limit]:
                        props = f.get("properties", {})
                        if props.get("mag", 0) >= min_magnitude:
                            features.append(f)
        except Exception as e:
            print(f"⚠️  Error USGS directo: {e}")

    return {
        "type": "FeatureCollection",
        "metadata": {
            "count": len(features),
            "min_magnitude": min_magnitude,
            "days": days,
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        "features": features
    }


@router.get("/context")
async def get_geo_context(
    lat_min: float = Query(-90, ge=-90, le=90),
    lat_max: float = Query(90, ge=-90, le=90),
    lon_min: float = Query(-180, ge=-180, le=180),
    lon_max: float = Query(180, ge=-180, le=180),
    earthquake_days: int = Query(1, ge=1, le=30),
    earthquake_magnitude: float = Query(2.5, ge=0, le=10),
    limit: int = Query(100, ge=1, le=500),
    req: Request = None,
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    """Contexto geoespacial consolidado para la experiencia Topografía de Megalodon.

    No calcula topografía: entrega únicamente fuentes externas/contextuales de Tezcatlipoca
    para el área consultada. La identidad y tenant se resuelven desde Megalodon mediante
    el bridge compartido. Cuando una fuente no está disponible, se reporta como unavailable
    en lugar de fabricar datos.
    """
    df = getattr(req.app.state, "data_fetcher", None)
    adsb = getattr(req.app.state, "adsb_exchange", None)
    ais = getattr(req.app.state, "ais_connector", None)

    aircraft = []
    if adsb:
        try:
            raw = await adsb.get_aircraft_in_bbox(lat_min, lat_max, lon_min, lon_max)
            for ac in (raw.get("ac", []) if isinstance(raw, dict) else [])[:limit]:
                lat = ac.get("lat")
                lon = ac.get("lon")
                if lat is None or lon is None:
                    continue
                aircraft.append({
                    "hex": ac.get("hex", ""),
                    "callsign": (ac.get("flight") or "").strip(),
                    "lat": lat, "lon": lon,
                    "altitude": ac.get("alt_baro"),
                    "track": ac.get("track"),
                    "speed": ac.get("gs"),
                    "source": "adsb_exchange",
                })
        except Exception as exc:
            aircraft = []
            req.app.state.tez_geo_context_last_error = str(exc)

    ships = []
    if ais:
        try:
            raw_ships = ais.get_ships_in_bbox(lat_min, lat_max, lon_min, lon_max)
            for ship in raw_ships[:limit]:
                lat = ship.get("latitude")
                lon = ship.get("longitude")
                if lat is None or lon is None:
                    continue
                ships.append({
                    "mmsi": ship.get("mmsi", ""),
                    "name": ship.get("name", ""),
                    "lat": lat, "lon": lon,
                    "sog": ship.get("sog"),
                    "cog": ship.get("cog"),
                    "source": "ais",
                })
        except Exception as exc:
            req.app.state.tez_geo_context_last_error = str(exc)

    earthquakes = []
    if df and hasattr(df, "cache"):
        for q in df.cache.get("quakes", [])[:limit]:
            lat, lon = q.get("lat"), q.get("lon")
            mag = q.get("mag")
            if lat is None or lon is None or mag is None:
                continue
            if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
                continue
            if float(mag) < earthquake_magnitude:
                continue
            earthquakes.append({
                "id": q.get("id", ""),
                "lat": lat, "lon": lon,
                "magnitude": mag,
                "place": q.get("place", ""),
                "time": q.get("timestamp"),
                "source": "usgs_cache",
            })

    telemetry = {
        "status": "online" if df else "offline",
        "sources": list(df.cache.keys())[:20] if df and hasattr(df, "cache") else [],
        "metrics": getattr(df, "metrics", {}) if df else {},
    }

    return {
        "tenant_id": getattr(req.state, "tenant_id", None),
        "user_id": getattr(req.state, "megalodon_user_id", None),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bbox": [lat_min, lon_min, lat_max, lon_max],
        "sources": {
            "gnss": {"status": "not_streamed_by_tezcatlipoca_context"},
            "adsb_exchange": {"status": "available" if adsb else "unavailable"},
            "ais": {"status": "available" if ais else "unavailable"},
            "usgs": {"status": "cache" if df and hasattr(df, "cache") else "unavailable"},
            "telemetry": telemetry,
        },
        "aircraft": aircraft,
        "ships": ships,
        "earthquakes": earthquakes,
    }
