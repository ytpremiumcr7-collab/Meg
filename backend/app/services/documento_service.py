# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
DocumentoService - Gestión de documentos electrónicos con cifrado.
"""
import hashlib
import io
from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expediente import Documento, ExpedienteObra
from app.services.base import BaseService
from app.core.errors import MegalodonException, ErrorCode
from app.core.crypto import cifrar_sobre, descifrar_sobre
from app.integrations.supabase_storage import storage_documentos


class DocumentoService(BaseService[Documento]):
    """Servicio de gestión documental con cifrado opcional."""

    def __init__(self, db: AsyncSession, tenant_id: UUID | None = None):
        # Documento es el modelo legacy sin tenant_id propio; su aislamiento se
        # hace por la relación ExpedienteObra en los métodos de dominio.
        # No usar tenant_required=True aquí porque BaseService exige una
        # columna tenant_id física y bloquearía todo el módulo documental.
        super().__init__(Documento, db, tenant_id=tenant_id, tenant_required=False)

    async def crear_documento(
        self,
        *,
        expediente_id: UUID,
        file_content: bytes,
        filename: str,
        tipo_documental: str,
        cifrar: bool = False,
        metadatos: Optional[dict] = None,
        tenant_id: Optional[str] = None,
        creado_por_id: Optional[UUID] = None,
    ) -> Documento:
        """Alias canónico para subir_documento.

        Mantiene el mismo contrato de producción y deja explícito el filtro
        de tenant para las validaciones de deduplicación y pertenencia.
        """
        # El filtro real de pertenencia queda en subir_documento():
        #   select(ExpedienteObra).where(ExpedienteObra.id == expediente_id)
        #   if tenant_id: ExpedienteObra.tenant_id == tenant_id
        return await self.subir_documento(
            expediente_id=expediente_id,
            file_content=file_content,
            filename=filename,
            tipo_documental=tipo_documental,
            cifrar=cifrar,
            metadatos=metadatos,
            tenant_id=tenant_id,
            creado_por_id=creado_por_id,
        )

    async def subir_documento(
        self,
        *,
        expediente_id: UUID,
        file_content: bytes,
        filename: str,
        tipo_documental: str,
        cifrar: bool = False,
        metadatos: Optional[dict] = None,
        tenant_id: Optional[str] = None,
        creado_por_id: Optional[UUID] = None,
    ) -> Documento:
        """Sube un documento al expediente y lo persiste en Supabase Storage."""

        # BUG ORIGINAL: se buscaba el expediente solo por ID, sin
        # verificar que perteneciera al tenant de quien sube el archivo.
        # Además de la fuga de acceso (subir a un expediente de otro
        # tenant), esto también corrompía datos: el archivo se cifraba
        # con la KEK del tenant_id del CALLER, pero quedaba etiquetado
        # bajo un expediente que podía ser de OTRO tenant -- al
        # descargarlo, descargar_documento deriva la KEK del tenant del
        # expediente, que ya no coincidiría con la usada para cifrar.
        query = select(ExpedienteObra).where(ExpedienteObra.id == expediente_id)
        if tenant_id:
            query = query.where(ExpedienteObra.tenant_id == tenant_id)
        result = await self.db.execute(query)
        expediente = result.scalar_one_or_none()
        if not expediente:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Expediente {expediente_id} no encontrado",
            )

        # Calcular hash (sobre el contenido ORIGINAL, antes de cifrar, para
        # que el hash sirva como huella del documento real y no del blob
        # cifrado, que cambiaría de nonce cada vez)
        hash_sha256 = hashlib.sha256(file_content).hexdigest()

        # Verificar duplicado por hash dentro del mismo tenant (evita
        # falsos positivos y fugas laterales entre organizaciones).
        dup_query = (
            select(Documento)
            .join(ExpedienteObra, Documento.expediente_id == ExpedienteObra.id)
            .where(Documento.hash_sha256 == hash_sha256)
        )
        if tenant_id is not None:
            dup_query = dup_query.where(ExpedienteObra.tenant_id == tenant_id)
        result = await self.db.execute(dup_query)
        if result.scalar_one_or_none():
            raise MegalodonException(
                ErrorCode.ARCHIVO_ERROR,
                "Documento duplicado detectado por hash",
                details={"hash": hash_sha256},
            )

        formato = filename.split(".")[-1].upper() if "." in filename else "DESCONOCIDO"

        contenido_a_subir = file_content
        nonce = None
        tag = None
        encrypted_dek_hex = None
        if cifrar:
            if not tenant_id:
                raise MegalodonException(
                    ErrorCode.ARCHIVO_ERROR,
                    "tenant_id requerido para cifrar documentos",
                )
            # Envelope encryption: DEK aleatoria por documento, envuelta
            # con la KEK del tenant derivada de ENCRYPTION_MASTER_KEY.
            # Solo se persiste encrypted_dek_hex -- la DEK en plano nunca
            # toca la BD. Ver app/core/crypto.py.
            contenido_a_subir, nonce, tag, encrypted_dek_hex = cifrar_sobre(
                file_content, tenant_id=tenant_id
            )

        # BUG ORIGINAL: `if self.storage: # TODO ... pass` -- nunca subía
        # nada a ningún lado. storage_path/storage_bucket se guardaban en
        # BD como si el archivo ya estuviera ahí, pero el archivo real
        # nunca se persistía.
        storage = storage_documentos()
        storage_path = f"expedientes/{expediente_id}/{uuid4()}_{filename}"
        await storage.subir(storage_path, contenido_a_subir, content_type="application/octet-stream")

        identificador = f"DOC-{expediente.identificador}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        documento = await self.create({
            "id": uuid4(),
            "identificador": identificador,
            "nombre": filename,
            "tipo_documental": tipo_documental,
            "formato": formato,
            "storage_path": storage_path,
            "storage_bucket": storage.bucket,
            "size_bytes": len(file_content),
            "hash_sha256": hash_sha256,
            "cifrado": cifrar,
            "nonce_cifrado": nonce.hex() if nonce else None,
            "tag_cifrado": tag.hex() if tag else None,
            "encryption_key_enc": encrypted_dek_hex,
            "metadatos": metadatos or {},
            "expediente_id": expediente_id,
            "tenant_id": expediente.tenant_id,
        }, creado_por_id=creado_por_id)

        # Actualizar Merkle root del expediente
        from app.services.expediente_service import ExpedienteService
        expediente_service = ExpedienteService(self.db)
        await expediente_service.calcular_merkle_root(expediente_id, tenant_id=expediente.tenant_id)

        return documento

    async def descargar_documento(
        self, documento_id: UUID, expediente_id: UUID, tenant_id: Optional[str] = None,
    ) -> tuple[bytes, str]:
        """Descarga un documento real de Supabase Storage, descifrando si
        es necesario. Valida que el documento pertenezca al expediente de la
        ruta (evita acceso cross-expediente por UUID conocido) Y que el
        expediente pertenezca al tenant que hace la solicitud.

        BUG ORIGINAL (x2): regresaba `contenido = b""` siempre -- un stub
        que nunca se conectó al storage (ya corregido). Y no validaba
        tenant en absoluto -- current_user se recibía en el endpoint pero
        nunca se usaba, así que cualquier tenant con un documento_id +
        expediente_id válidos de OTRO tenant podía descargarlo y
        descifrarlo (la KEK se deriva del tenant del expediente, no de
        quien pide la descarga).
        """
        documento = await self.get(documento_id, tenant_id=tenant_id)
        if not documento or str(documento.expediente_id) != str(expediente_id):
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Documento {documento_id} no encontrado en el expediente {expediente_id}",
            )

        expediente = await self.db.get(ExpedienteObra, documento.expediente_id)
        if not expediente or (tenant_id is not None and str(expediente.tenant_id) != str(tenant_id)):
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Documento {documento_id} no encontrado en el expediente {expediente_id}",
            )

        storage = storage_documentos()
        contenido = await storage.descargar(documento.storage_path)

        if documento.cifrado and documento.nonce_cifrado and documento.tag_cifrado:
            if not documento.encryption_key_enc:
                raise MegalodonException(
                    ErrorCode.ARCHIVO_ERROR,
                    "Documento marcado como cifrado pero sin DEK almacenada "
                    "(cifrado con versión anterior al sistema de envelope encryption). "
                    "Contacte a soporte.",
                )
            # Obtener tenant_id desde el expediente para derivar la KEK
            # (ya lo tenemos arriba de la validación de tenant).
            contenido = descifrar_sobre(
                contenido,
                nonce=bytes.fromhex(documento.nonce_cifrado),
                tag=bytes.fromhex(documento.tag_cifrado),
                encrypted_dek_hex=documento.encryption_key_enc,
                tenant_id=str(expediente.tenant_id),
            )

        return contenido, documento.nombre

    async def listar_por_expediente(
        self,
        expediente_id: UUID,
        tipo_documental: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> List[Documento]:
        """Lista documentos de un expediente.

        BUG ORIGINAL: no validaba que el expediente perteneciera al tenant
        de quien pregunta -- listaba documentos de cualquier expediente
        con solo conocer su UUID, sin importar el tenant."""
        if tenant_id is not None:
            exp_result = await self.db.execute(
                select(ExpedienteObra).where(
                    ExpedienteObra.id == expediente_id, ExpedienteObra.tenant_id == tenant_id,
                )
            )
            if exp_result.scalar_one_or_none() is None:
                raise MegalodonException(
                    ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                    f"Expediente {expediente_id} no encontrado",
                )

        query = select(Documento).where(Documento.expediente_id == expediente_id)
        if tipo_documental:
            query = query.where(Documento.tipo_documental == tipo_documental)
        query = query.order_by(Documento.created_at.desc())

        result = await self.db.execute(query)
        return result.scalars().all()
