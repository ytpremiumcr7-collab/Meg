# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
FirmaService - Orquestación del módulo de firma electrónica.

BUG ORIGINAL (el más grave del backend hasta ahora): firmar_documento()
hacía `pdf_bytes = b""` -- un placeholder -- y `validar_firma()` hacía
exactamente lo mismo. O sea, firmar un documento no firmaba NADA: tomaba
bytes vacíos, les ponía una "firma" encima, y el resultado (que tampoco se
guardaba en ningún lado -- otro TODO sin implementar) se descartaba.
Cualquier "documento firmado" hasta ahora nunca existió.

Ahora sí: descarga el documento real de Supabase Storage, lo descifra si
aplica, lo firma de verdad con PAdES-LT + sello de tiempo RFC 3161 real
(TSA), y sube el resultado firmado de vuelta a storage -- sin pisar el
original (control de versiones mínimo: original y firmado quedan como
paths distintos, referenciados en los metadatos del documento).
"""
import os
import tempfile
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.modules.firma.firma_electronica import (
    ModuloFirmaElectronica, CertificadoFIEL, FirmaDocumento
)
from app.modules.firma.pades_lt import PAdESLTSigner
from app.modules.firma.cfdi40 import CFDISATSigner
from app.modules.firma.plataformas import (
    PlataformaLicitacion, formato_requerido, advertencias_previas_a_firma,
)
from app.models.expediente import Documento, ExpedienteObra
from app.integrations.supabase_storage import storage_documentos
from app.core.crypto import descifrar_contenido
from app.core.errors import MegalodonException, ErrorCode


class FirmaService:
    """Servicio de firma electrónica para documentos de obra pública."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.modulo = ModuloFirmaElectronica()

    async def _obtener_documento(self, documento_id: UUID) -> Documento:
        result = await self.db.execute(select(Documento).where(Documento.id == documento_id))
        documento = result.scalar_one_or_none()
        if not documento:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Documento {documento_id} no encontrado")
        return documento

    async def _contenido_real(self, documento: Documento) -> bytes:
        """Descarga el contenido real del documento (descifrando si aplica).
        Antes esto siempre era b"" -- un placeholder que nunca tocaba storage."""
        storage = storage_documentos()
        contenido = await storage.descargar(documento.storage_path)
        if documento.cifrado and documento.nonce_cifrado and documento.tag_cifrado:
            contenido = descifrar_contenido(
                contenido, bytes.fromhex(documento.nonce_cifrado), bytes.fromhex(documento.tag_cifrado),
            )
        return contenido

    async def firmar_documento(
        self,
        *,
        documento_id: UUID,
        certificado_cer: bytes,
        certificado_key: bytes,
        password: str,
        razon: str = "Firma de documento de obra pública",
        ubicacion: str = "México",
        usuario_id: UUID,
        usar_tsa: bool = True,
        tsa_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Firma un documento real del expediente con e.firma (PAdES-LT +
        sello de tiempo RFC 3161 si usar_tsa=True)."""
        documento = await self._obtener_documento(documento_id)
        pdf_bytes = await self._contenido_real(documento)

        cer_path = key_path = input_path = output_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".cer", delete=False) as f:
                f.write(certificado_cer)
                cer_path = f.name
            with tempfile.NamedTemporaryFile(suffix=".key", delete=False) as f:
                f.write(certificado_key)
                key_path = f.name

            # Certificado (para RFC/nombre/vigencia -- el motor de carga
            # ya existente en firma_electronica.py sigue siendo válido).
            cert = self.modulo.cargar_certificado_fiel(cer_path, key_path, password)

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(pdf_bytes)
                input_path = f.name
            output_path = input_path + ".firmado.pdf"

            if usar_tsa:
                # Firma real PAdES-LT con sello de tiempo RFC 3161 desde
                # una TSA pública real (DigiCert por default).
                signer = PAdESLTSigner(cer_path, key_path, password, tsa_url=tsa_url)
                try:
                    resultado_firma = signer.sign_pades_lt(
                        input_path, output_path, reason=razon, location=ubicacion, use_lta=True,
                    )
                finally:
                    signer.cleanup()
            else:
                # Ruta sin TSA (más rápida, sin dependencia de red externa).
                pdf_firmado = self.modulo.firmar_documento_pdf(
                    pdf_bytes=pdf_bytes, certificado=cert, razon=razon,
                    ubicacion=ubicacion, agregar_sello_tiempo=False,
                )
                with open(output_path, "wb") as f:
                    f.write(pdf_firmado)
                resultado_firma = {"profile": "PAdES-B", "tsa_url": None}

            with open(output_path, "rb") as f:
                pdf_firmado_bytes = f.read()

            # Subir el PDF firmado como un archivo NUEVO -- no se pisa el
            # original, para no perder trazabilidad de "antes/después".
            storage = storage_documentos()
            path_firmado = f"{documento.storage_path}.firmado.pdf"
            await storage.subir(path_firmado, pdf_firmado_bytes, content_type="application/pdf")

            metadatos = dict(documento.metadatos or {})
            firmas = metadatos.get("firmas", [])
            firmas.append({
                "rfc": cert.rfc,
                "nombre": cert.nombre,
                "fecha": cert.vigencia_inicio.isoformat(),
                "razon": razon,
                "usuario_id": str(usuario_id),
                "storage_path_firmado": path_firmado,
                "perfil": resultado_firma.get("profile"),
                "tsa_url": resultado_firma.get("tsa_url"),
            })
            metadatos["firmas"] = firmas
            documento.metadatos = metadatos
            await self.db.commit()

            return {
                "documento_id": str(documento_id),
                "firmante": cert.nombre,
                "rfc": cert.rfc,
                "fecha_firma": cert.vigencia_inicio.isoformat(),
                "razon": razon,
                "sello_tiempo": usar_tsa,
                "perfil_firma": resultado_firma.get("profile"),
                "storage_path_firmado": path_firmado,
            }
        finally:
            for p in (cer_path, key_path, input_path, output_path):
                if p and os.path.exists(p):
                    os.unlink(p)

    async def validar_firma(self, documento_id: UUID) -> Dict[str, Any]:
        """Valida las firmas del documento FIRMADO real (no del original
        sin firmar). Antes: pdf_bytes = b"" -- siempre validaba nada."""
        documento = await self._obtener_documento(documento_id)
        metadatos = documento.metadatos or {}
        firmas = metadatos.get("firmas", [])
        if not firmas:
            raise MegalodonException(ErrorCode.FIRMA_INVALIDA, "Este documento no tiene firmas registradas")

        path_firmado = firmas[-1].get("storage_path_firmado")
        if not path_firmado:
            raise MegalodonException(ErrorCode.FIRMA_INVALIDA, "No se encontró el archivo firmado en storage")

        storage = storage_documentos()
        pdf_firmado = await storage.descargar(path_firmado)
        return self.modulo.validar_firma_pdf(pdf_firmado)

    async def firmar_hash_expediente(
        self,
        expediente_id: UUID,
        certificado: CertificadoFIEL,
    ) -> Dict[str, Any]:
        """Firma el Merkle root de un expediente para trazabilidad."""
        result = await self.db.execute(select(ExpedienteObra).where(ExpedienteObra.id == expediente_id))
        expediente = result.scalar_one_or_none()
        if not expediente:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Expediente {expediente_id} no encontrado")
        if not expediente.merkle_root:
            raise MegalodonException(ErrorCode.FIRMA_INVALIDA, "El expediente no tiene Merkle root calculado")

        merkle_bytes = expediente.merkle_root.encode()
        firma = self.modulo.firmar_hash_documento(merkle_bytes, certificado)

        metadatos = dict(expediente.metadatos or {})
        metadatos["firma_merkle"] = {
            "firma": firma, "rfc": certificado.rfc, "fecha": certificado.vigencia_inicio.isoformat(),
        }
        expediente.metadatos = metadatos
        await self.db.commit()

        return {
            "expediente_id": str(expediente_id),
            "merkle_root": expediente.merkle_root,
            "firma": firma,
            "firmante": certificado.rfc,
        }

    # ─── CFDI 4.0: sellado digital (NO timbrado -- eso requiere un PAC) ──

    async def sellar_cfdi(
        self,
        *,
        xml_cfdi: bytes,
        certificado_cer: bytes,
        certificado_key: bytes,
        password: str,
    ) -> Dict[str, Any]:
        """Genera cadena original + sello digital de un CFDI 4.0.

        Importante: esto NO timbra el CFDI. El timbrado fiscal requiere
        un PAC (Proveedor Autorizado de Certificación) autorizado por el
        SAT -- este método deja el XML sellado, listo para mandarlo a
        cualquier PAC.
        """
        cer_path = key_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".cer", delete=False) as f:
                f.write(certificado_cer)
                cer_path = f.name
            with tempfile.NamedTemporaryFile(suffix=".key", delete=False) as f:
                f.write(certificado_key)
                key_path = f.name

            signer = CFDISATSigner(cer_path, key_path, password)
            resultado = signer.sellar_xml(xml_cfdi)

            if not resultado.success:
                raise MegalodonException(ErrorCode.FIRMA_INVALIDA, resultado.error or "Error al sellar CFDI")

            return {
                "xml_sellado": resultado.xml_sellado,
                "cadena_original": resultado.cadena_original,
                "sello_digital": resultado.sello_digital,
                "no_certificado": resultado.no_certificado,
                "nota": "XML sellado, NO timbrado. El timbrado fiscal requiere un PAC autorizado por el SAT.",
            }
        finally:
            for p in (cer_path, key_path):
                if p and os.path.exists(p):
                    os.unlink(p)

    # ─── Formato de firma exigido por plataforma gubernamental ─────────

    def formato_requerido_plataforma(self, plataforma: PlataformaLicitacion, tipo_documento: str) -> Dict[str, Any]:
        return {
            "plataforma": plataforma.value,
            "tipo_documento": tipo_documento,
            "formato_requerido": formato_requerido(plataforma, tipo_documento),
        }
