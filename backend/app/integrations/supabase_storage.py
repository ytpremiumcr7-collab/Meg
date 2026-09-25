# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Integración con Supabase Storage.

Se usa la service role key, no login de usuario final: el backend ya es
la única fuente de verdad de autenticación (especificación, sección 5.4 —
"La autenticación canónica del sistema debe ser backend-owned"). Supabase
aquí es solo infraestructura de almacenamiento, nunca un segundo sistema
de auth paralelo.

Nota sobre concurrencia: la comunidad de supabase-py ha reportado que
compartir un cliente async entre requests puede mezclar estado de sesión
CUANDO se usa sign_in_with_password por usuario. Eso no aplica aquí --
nunca se inicia sesión de usuario final en este cliente, solo se opera
como la identidad de servicio (service role key) en cada llamada, así que
un cliente compartido (singleton) es seguro.
"""
import asyncio
from typing import List, Optional

from app.config import settings
from app.core.errors import MegalodonException, ErrorCode

_client = None
_client_lock = asyncio.Lock()


async def get_storage_client():
    """Cliente async compartido de Supabase."""
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:
                if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
                    raise MegalodonException(
                        ErrorCode.ARCHIVO_ERROR,
                        "SUPABASE_URL / SUPABASE_SERVICE_KEY no están configurados",
                    )
                # Import diferido: si Supabase no está configurado (ej. en
                # tests locales sin storage), el resto del backend no debe
                # tronar solo por importar este módulo.
                from supabase import acreate_client
                _client = await acreate_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    return _client


def _extraer_signed_url(resultado) -> Optional[str]:
    """El shape exacto de la respuesta de create_signed_url ha variado
    entre versiones de supabase-py (a veces dict con 'signedURL', a veces
    'signedUrl', a veces un objeto con atributo). Esto no se pudo
    verificar contra un entorno real -- no hay red en el sandbox donde se
    escribió este código -- así que se maneja de forma defensiva. Si al
    correrlo en Railway no aparece la URL, imprime `resultado` y ajusta
    esta función a la forma real de tu versión instalada.
    """
    if resultado is None:
        return None
    if isinstance(resultado, dict):
        return resultado.get("signedURL") or resultado.get("signedUrl") or resultado.get("signed_url")
    return getattr(resultado, "signed_url", None) or getattr(resultado, "signedURL", None)


class SupabaseStorage:
    """Wrapper delgado sobre un bucket de Supabase Storage."""

    def __init__(self, bucket: str):
        self.bucket = bucket

    async def subir(self, path: str, contenido: bytes, content_type: str = "application/octet-stream") -> str:
        """Sube (o sobreescribe, upsert=true) un archivo. Regresa el path
        dentro del bucket, que es lo que se debe guardar en BD (nunca
        guardar URLs firmadas, esas expiran)."""
        client = await get_storage_client()
        try:
            await client.storage.from_(self.bucket).upload(
                path, contenido, {"content-type": content_type, "upsert": "true"}
            )
        except Exception as e:
            raise MegalodonException(ErrorCode.ARCHIVO_ERROR, f"Error al subir '{path}' a storage: {e}")
        return path

    async def descargar(self, path: str) -> bytes:
        client = await get_storage_client()
        try:
            return await client.storage.from_(self.bucket).download(path)
        except Exception as e:
            raise MegalodonException(ErrorCode.ARCHIVO_ERROR, f"Error al descargar '{path}' de storage: {e}")

    async def eliminar(self, paths: List[str]) -> None:
        client = await get_storage_client()
        try:
            await client.storage.from_(self.bucket).remove(paths)
        except Exception as e:
            raise MegalodonException(ErrorCode.ARCHIVO_ERROR, f"Error al eliminar de storage: {e}")

    async def url_firmada(self, path: str, expira_segundos: int = 3600) -> Optional[str]:
        """URL temporal para que el frontend descargue directo desde
        Supabase, sin pasar el archivo por el backend (útil para modelos
        BIM grandes o PDFs pesados)."""
        client = await get_storage_client()
        try:
            resultado = await client.storage.from_(self.bucket).create_signed_url(path, expira_segundos)
        except Exception as e:
            raise MegalodonException(ErrorCode.ARCHIVO_ERROR, f"Error al firmar URL de '{path}': {e}")
        return _extraer_signed_url(resultado)


# Wrappers listos para los dominios que ya los necesitan.
def storage_bim() -> SupabaseStorage:
    return SupabaseStorage(settings.SUPABASE_BUCKET_BIM)


def storage_documentos() -> SupabaseStorage:
    return SupabaseStorage(settings.SUPABASE_BUCKET_DOCUMENTOS)


def storage_exportaciones() -> SupabaseStorage:
    return SupabaseStorage(settings.SUPABASE_BUCKET_EXPORTS)
