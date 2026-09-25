from __future__ import annotations
import asyncio
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import httpx
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
except Exception:  # pragma: no cover - fallback sin dependencia opcional
    class IntervalTrigger:  # type: ignore[override]
        def __init__(self, seconds: int):
            self.seconds = seconds

    class AsyncIOScheduler:
        def __init__(self):
            self._running = False
            self._jobs = []
        def add_job(self, func, trigger=None, id=None, replace_existing=False, **kwargs):
            self._jobs.append((func, trigger, id, kwargs))
            return None
        def start(self):
            self._running = True
        def shutdown(self, wait: bool = False):
            self._running = False
        @property
        def running(self):
            return self._running

from services.observable_cache import ObservableCache
from core.observability import build_logger

logger = build_logger("tu_osint.data_fetcher")

class DataFetcherEngine:
    """Enterprise-grade data ingestion runtime with generic fetch dispatch."""

    JOBS = [
        ("fetch_opensky", 60),
        ("fetch_adsb_lol", 60),
        ("fetch_ais", 30),
        ("fetch_usgs", 60),
        ("fetch_firms", 120),
        ("fetch_openaq", 120),
        ("fetch_nws", 120),
        ("fetch_nws_alerts", 120),
        ("fetch_gdelt", 300),
        ("fetch_deepstate", 600),
        ("fetch_telegram_osint", 300),
        ("fetch_malware_feeds", 300),
        ("fetch_cisa_kev", 300),
        ("fetch_carrier_tracker", 1800),
        ("fetch_fishing_activity", 1800),
        ("fetch_power_plants", 1800),
        ("fetch_cctv", 3600),
        ("fetch_kiwisdr", 3600),
        ("fetch_radio_browser", 3600),
        ("fetch_shodan", 21600),
        ("fetch_censys", 21600),
        ("fetch_greynoise", 21600),
        ("fetch_volcanoes", 21600),
        ("fetch_ioda", 21600),
        ("fetch_sentinel_hub", 21600),
        ("fetch_modis_terra", 21600),
        ("fetch_viirs_nightlights", 21600),
        ("fetch_sar_asf", 21600),
        ("fetch_sar_opera", 21600),
        ("fetch_meshtastic", 3600),
        ("fetch_aprs", 3600),
        ("fetch_satnogs", 3600),
        ("fetch_amtrak", 3600),
        ("fetch_digitraffic", 3600),
        ("fetch_gibs_layers", 21600),
        ("fetch_esri_imagery", 21600),
        ("fetch_noaa_goes", 900),
        ("fetch_nasa_eonet", 1800),
        ("fetch_openaerialmap", 21600),
        ("fetch_readymap", 21600),
        ("fetch_versatiles", 21600),
        ("fetch_cloudflare_radar", 1800),
        ("fetch_submarine_cables", 21600),
        ("fetch_world_bank", 21600),
        ("fetch_gbif", 21600),
    ]

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.cache = ObservableCache()
        self.http = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            headers={"User-Agent": os.getenv("REQUEST_USER_AGENT", "TU-OSINT-Platform/2.3.5")},
            follow_redirects=True,
        )
        self.metrics = defaultdict(lambda: {"success": 0, "fail": 0, "latency_ms": []})
        self.last_fetch: dict[str, float] = {}
        self.ws_manager = None
        self.malware_aggregator = None
        self.opensky_user = os.getenv("OPENSKY_USER")
        self.opensky_pass = os.getenv("OPENSKY_PASS")
        self.nasa_firms_key = os.getenv("NASA_FIRMS_KEY")
        self.gfw_token = os.getenv("GFW_API_TOKEN")
        self.shodan_key = os.getenv("SHODAN_API_KEY")
        self.censys_id = os.getenv("CENSYS_API_ID")
        self.censys_secret = os.getenv("CENSYS_API_SECRET")
        self.greynoise_key = os.getenv("GREYNOISE_API_KEY")
        self.radio_browser_query = os.getenv("RADIO_BROWSER_QUERY", "").strip()
        self.radio_browser_countrycode = os.getenv("RADIO_BROWSER_COUNTRYCODE", "").strip().upper()
        self.radio_browser_tag = os.getenv("RADIO_BROWSER_TAG", "").strip()
        self.radio_browser_limit = max(1, min(int(os.getenv("RADIO_BROWSER_LIMIT", "100")), 200))

    def __getattr__(self, name: str):
        if name.startswith("fetch_"):
            async def _runner():
                return await self._dispatch(name)
            return _runner
        raise AttributeError(name)

    async def close(self):
        if self.http and not self.http.is_closed:
            await self.http.aclose()

    async def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        await self.close()

    def set_websocket_manager(self, ws_manager):
        self.ws_manager = ws_manager
        self.cache.add_observer(self._publish_update)

    def _publish_update(self, key: str, value: Any):
        if not self.ws_manager:
            return
        try:
            asyncio.create_task(self.ws_manager.broadcast({
                "type": "update",
                "layer": key,
                "data": value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }, layer_filter={key}))
        except RuntimeError as e:
            # Típicamente "no running event loop" si _publish_update se
            # llama fuera de un contexto async (p.ej. durante shutdown).
            # No es un error de datos, pero se deja traza en debug.
            logger.debug(f"[_publish_update] no se pudo agendar broadcast para {key!r}: {e}")

    def _record(self, name: str, ok: bool, started: float):
        bucket = self.metrics[name]
        bucket["success" if ok else "fail"] += 1
        bucket["latency_ms"].append(round((time.perf_counter() - started) * 1000, 2))

    async def _json(self, url: str, *, params=None, headers=None, fallback=None):
        try:
            resp = await self.http.get(url, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            # Fuente externa caída/lenta/rate-limited es esperado en un
            # agregador de 40+ APIs públicas gratuitas -- se cae al
            # fallback (normalmente lista vacía) para no tumbar el job,
            # pero se loguea en debug para poder diferenciar "la fuente
            # está caída" de "cambié la URL y ya no responde nunca".
            logger.debug(f"[_json] GET {url} falló, usando fallback: {e}")
            return fallback if fallback is not None else {}

    async def _dispatch(self, method_name: str):
        started = time.perf_counter()
        key = method_name.removeprefix("fetch_")
        handler = getattr(self, f"_fetch_{key}", None)
        try:
            if handler:
                value = await handler()
            else:
                value = await self._generic_fetch(key)
            self.cache[key] = value
            self.last_fetch[key] = time.time()
            self._record(method_name, True, started)
            return value
        except Exception as exc:
            self._record(method_name, False, started)
            logger.warning(f"[_dispatch] job {method_name} falló: {exc}")
            return {"error": str(exc), "source": key}

    async def _generic_fetch(self, key: str):
        return {"items": [], "source": key, "timestamp": datetime.now(timezone.utc).isoformat()}

    async def _fetch_opensky(self):
        url = "https://opensky-network.org/api/states/all"
        auth = (self.opensky_user, self.opensky_pass) if self.opensky_user and self.opensky_pass else None
        try:
            resp = await self.http.get(url, auth=auth)
            resp.raise_for_status()
            data = resp.json()
            states = []
            for row in data.get("states", [])[:200]:
                states.append({
                    "icao24": row[0],
                    "callsign": (row[1] or "").strip(),
                    "longitude": row[5],
                    "latitude": row[6],
                    "altitude": row[7],
                    "velocity": row[9],
                    "heading": row[10],
                    "vertical_rate": row[11],
                    "country": row[2],
                    "on_ground": bool(row[8]),
                    "source": "opensky",
                })
            return states
        except Exception as e:
            logger.debug(f"[_fetch_opensky] falló: {e}")
            return []

    async def _fetch_usgs(self):
        data = await self._json(
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson",
            fallback={"features": []},
        )
        return data.get("features", [])

    async def _fetch_nws(self):
        data = await self._json("https://api.open-meteo.com/v1/forecast?latitude=19.43&longitude=-99.13&current=temperature_2m,wind_speed_10m")
        return data

    async def _fetch_openaq(self):
        data = await self._json("https://api.openaq.org/v2/latest?limit=100", fallback={"results": []})
        return data.get("results", [])

    async def _fetch_nasa_eonet(self):
        data = await self._json("https://eonet.gsfc.nasa.gov/api/v3/events?status=open", fallback={"events": []})
        return data.get("events", [])

    async def _fetch_cisa_kev(self):
        data = await self._json("https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json", fallback={"vulnerabilities": []})
        return data.get("vulnerabilities", [])

    async def _fetch_volcanoes(self):
        data = await self._json("https://volcano.si.edu/feeds/weekly.xml", fallback={"items": []})
        return data

    async def _fetch_gdelt(self):
        params = {"query": "conflict", "mode": "ArtList", "maxrecords": 50, "format": "json"}
        return await self._json("https://api.gdeltproject.org/api/v2/doc/doc", params=params, fallback={"articles": []})

    async def _fetch_radio_browser(self):
        params = {
            "hidebroken": "true",
            "order": "clickcount",
            "reverse": "true",
            "limit": self.radio_browser_limit,
        }
        if self.radio_browser_query:
            params["name"] = self.radio_browser_query
        if self.radio_browser_countrycode:
            params["countrycode"] = self.radio_browser_countrycode
        if self.radio_browser_tag:
            params["tag"] = self.radio_browser_tag

        data = await self._json(
            "https://api.radio-browser.info/json/stations/search",
            params=params,
            fallback=[],
        )
        stations: list[dict[str, Any]] = []
        if isinstance(data, list):
            for st in data[: self.radio_browser_limit]:
                stations.append({
                    "stationuuid": st.get("stationuuid", ""),
                    "name": st.get("name", ""),
                    "country": st.get("country", ""),
                    "countrycode": st.get("countrycode", ""),
                    "tags": st.get("tags", ""),
                    "codec": st.get("codec", ""),
                    "bitrate": st.get("bitrate", 0),
                    "homepage": st.get("homepage", ""),
                    "url": st.get("url_resolved") or st.get("url", ""),
                    "favicon": st.get("favicon", ""),
                    "votes": st.get("votes", 0),
                    "clickcount": st.get("clickcount", 0),
                    "language": st.get("language", ""),
                    "source": "radio-browser.info",
                    "type": "internet_radio",
                })
        return stations

    async def _fetch_malware_feeds(self):
        if self.malware_aggregator:
            return await self.malware_aggregator.get_feeds()
        return {"feeds": {}, "scoring": {}, "source": "uninitialized"}

    async def start(self):
        if self.scheduler.running:
            return
        for name, seconds in self.JOBS:
            self.scheduler.add_job(getattr(self, name), IntervalTrigger(seconds=seconds), id=name, replace_existing=True, max_instances=1)
        self.scheduler.start()

    async def refresh_all(self):
        results = await asyncio.gather(*(getattr(self, name)() for name, _ in self.JOBS), return_exceptions=True)
        return {name: result for (name, _), result in zip(self.JOBS, results)}

    async def get_live_batch(self) -> Dict[str, Any]:
        malware = self.cache.get("malware", {})
        malware_list = []
        if isinstance(malware, dict):
            for src, items in malware.get("feeds", {}).items():
                for item in items[:20]:
                    malware_list.append({"source": src, **item})
        elif isinstance(malware, list):
            malware_list = malware[:20]

        return {
            "flights": self.cache.get("flights", [])[:100],
            "military_flights": self.cache.get("military_flights", [])[:100],
            "ships": self.cache.get("ships", [])[:100],
            "quakes": self.cache.get("quakes", [])[:50],
            "firms": self.cache.get("firms", [])[:100],
            "weather": self.cache.get("weather", {}),
            "air_quality": self.cache.get("air_quality", []),
            "radio_browser": self.cache.get("radio_browser", [])[:100],
            "milware": malware_list,
            "malware": malware_list,
            "cisa_kev": self.cache.get("cisa_kev", [])[:50],
            "gdelt_conflict": self.cache.get("gdelt", {}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_summary(self) -> Dict[str, Any]:
        return {
            "sources": len(self.JOBS),
            "cache_keys": list(self.cache.keys()),
            "metrics": {k: {"success": v["success"], "fail": v["fail"], "samples": len(v["latency_ms"])} for k, v in self.metrics.items()},
            "last_fetch": self.last_fetch,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
