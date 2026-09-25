"""ADS-B Exchange - Datos de vuelo para detección GPSJam."""
import os
import aiohttp
from typing import Dict, List, Any
from datetime import datetime, timezone


class ADSBExchangeClient:
    """Cliente para ADS-B Exchange API (requiere API key)."""

    def __init__(self):
        self.api_key = os.getenv("ADSBEXCHANGE_API_KEY", "")
        self.base_url = "https://api.adsbexchange.com/api/v2"
        self.http = aiohttp.ClientSession()

    async def close(self):
        if self.http and not self.http.closed:
            await self.http.close()

    async def get_aircraft_in_bbox(self, lat_min: float, lat_max: float,
                                    lon_min: float, lon_max: float) -> List[Dict]:
        """Obtener aeronaves en bounding box."""
        if not self.api_key:
            return [{"error": "ADSBEXCHANGE_API_KEY not configured"}]

        try:
            url = f"{self.base_url}/lat/{(lat_min + lat_max) / 2}/lon/{(lon_min + lon_max) / 2}/dist/250"
            headers = {"api-auth": self.api_key}
            async with self.http.get(url, headers=headers,
                                     timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    aircraft = data.get("ac", []) if isinstance(data, dict) else []
                    return [{
                        "hex": a.get("hex", ""),
                        "flight": a.get("flight", ""),
                        "latitude": a.get("lat"),
                        "longitude": a.get("lon"),
                        "altitude": a.get("alt_baro", 0),
                        "speed": a.get("gs", 0),
                        "heading": a.get("track", 0),
                        "type": a.get("t", ""),
                        "source": "adsbexchange.com",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    } for a in aircraft[:200]]
        except Exception as e:
            print(f"⚠️  Error ADS-B Exchange: {e}")
        return []

    async def get_aircraft_by_hex(self, hex_id: str) -> Dict[str, Any]:
        """Obtener aeronave por ID hexadecimal."""
        if not self.api_key:
            return {"error": "ADSBEXCHANGE_API_KEY not configured"}

        try:
            url = f"{self.base_url}/hex/{hex_id}"
            headers = {"api-auth": self.api_key}
            async with self.http.get(url, headers=headers,
                                     timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            print(f"⚠️  Error ADS-B hex: {e}")
        return {"error": "Failed to fetch aircraft"}

    def detect_gps_jam(self, aircraft_list: List[Dict]) -> List[Dict]:
        """Detectar posibles interferencias GPS basado en anomalías."""
        suspicious = []
        for ac in aircraft_list:
            # Detección simple: aeronaves sin posición válida o con altitud inconsistente
            lat = ac.get("latitude")
            lon = ac.get("longitude")
            alt = ac.get("altitude", 0)

            if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
                suspicious.append({
                    "hex": ac.get("hex", ""),
                    "flight": ac.get("flight", ""),
                    "reason": "invalid_position",
                    "last_known": {"lat": lat, "lon": lon, "alt": alt},
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            elif alt > 50000 or alt < -1000:  # Altitud imposible
                suspicious.append({
                    "hex": ac.get("hex", ""),
                    "flight": ac.get("flight", ""),
                    "reason": "altitude_anomaly",
                    "altitude": alt,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

        return suspicious
