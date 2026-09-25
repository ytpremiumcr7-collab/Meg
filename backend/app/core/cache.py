# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Cache con Redis para servicios de busqueda y catalogos.
"""
import pickle
from typing import Optional, Any


class CacheService:
    """Servicio de cache con Redis."""

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.enabled = redis_client is not None

    async def get(self, key: str) -> Optional[Any]:
        """Obtiene valor del cache."""
        if not self.enabled:
            return None
        data = await self.redis.get(key)
        if data is None:
            return None
        try:
            return pickle.loads(data)
        except Exception:
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = 300,  # 5 minutos default
    ) -> bool:
        """Guarda valor en cache."""
        if not self.enabled:
            return False
        try:
            serialized = pickle.dumps(value)
            await self.redis.setex(key, ttl, serialized)
            return True
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        """Elimina valor del cache."""
        if not self.enabled:
            return False
        await self.redis.delete(key)
        return True

    async def delete_pattern(self, pattern: str) -> int:
        """Elimina valores por patron."""
        if not self.enabled:
            return 0
        keys = []
        async for key in self.redis.scan_iter(match=pattern):
            keys.append(key)
        if keys:
            await self.redis.delete(*keys)
        return len(keys)

    def key(self, prefix: str, *parts) -> str:
        """Genera una clave de cache."""
        parts_str = ":".join(str(p) for p in parts)
        return f"meg:{prefix}:{parts_str}"


cache_service: Optional[CacheService] = None


def get_cache() -> CacheService:
    global cache_service
    if cache_service is None:
        cache_service = CacheService()
    return cache_service
