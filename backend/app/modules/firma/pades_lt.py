#!/usr/bin/env python3
# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
================================================================================
Megalodon PAdES-LT Signer — Firma PDF de Larga Duración (sin mocks)
================================================================================
Implementación completa de PAdES-B-LT y PAdES-B-LTA usando pyHanko.
Incluye:
  • Firma RSA-SHA256 con certificado e.firma SAT
  • Sello de tiempo RFC 3161 desde TSA configurable
  • Incrustación de info de revocación (OCSP/CRL) en DSS
  • Validación de contexto X.509
  • Compatible con plataformas mexicanas que exijan PAdES-LT

Dependencias:
    pip install pyhanko pyhanko-certvalidator

Nota: pyHanko requiere que la clave y certificado estén en formato PEM
      o PFX. Este módulo convierte automáticamente desde .cer/.key SAT.
"""

import os
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Optional, List, Union

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

# pyHanko imports


class PAdESLTError(Exception):
    """Error verificable durante firma PAdES-LT/LTA."""


def _import_pyhanko():
    try:
        from pyhanko.sign import signers, timestamps
        from pyhanko.sign.fields import SigSeedSubFilter
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko_certvalidator import ValidationContext
        from pyhanko_certvalidator.fetchers.requests_fetchers import RequestsFetcherBackend
        return signers, timestamps, SigSeedSubFilter, IncrementalPdfFileWriter, ValidationContext, RequestsFetcherBackend
    except Exception as exc:  # pragma: no cover - dependencia opcional
        raise PAdESLTError(
            "pyHanko no está disponible en este entorno; la firma PAdES-LT/LTA requiere esa dependencia"
        ) from exc

class PAdESLTSigner:
    """
    Firmador PAdES-LT/LTA para documentos PDF usando e.firma del SAT.
    """

    # TSAs públicos conocidos (configurables)
    DEFAULT_TSA_URLS = [
        "http://timestamp.digicert.com",           # DigiCert (global)
        "http://tsa.starfieldtech.com",            # Starfield
        "http://timestamp.globalsign.com/scripts/timstamp.dll",  # GlobalSign
    ]

    def __init__(self, cer_path: str, key_path: str, password: str,
                 tsa_url: Optional[str] = None,
                 trust_roots: Optional[List[str]] = None):
        """
        Inicializa firmador PAdES-LT.

        Args:
            cer_path: Ruta al .cer del SAT
            key_path: Ruta al .key cifrado del SAT
            password: Contraseña de la .key
            tsa_url: URL del TSA (Time Stamping Authority). Si None, usa defaults.
            trust_roots: Rutas a certificados raíz de confianza adicionales (PEM)
        """
        self.cer_path = Path(cer_path)
        self.key_path = Path(key_path)
        self.password = password.encode("utf-8") if isinstance(password, str) else password
        self.tsa_url = tsa_url
        self.trust_roots = trust_roots or []

        self._cert: Optional[x509.Certificate] = None
        self._private_key = None
        self._pyhanko_signer = None
        self._timestamper = None

        self._load_crypto_materials()
        self._setup_pyhanko()

    def _load_crypto_materials(self) -> None:
        """Carga .cer y descifra .key del SAT."""
        if not self.cer_path.exists():
            raise PAdESLTError(f"Certificado no encontrado: {self.cer_path}")
        if not self.key_path.exists():
            raise PAdESLTError(f"Clave privada no encontrada: {self.key_path}")

        # Cargar certificado
        cer_data = self.cer_path.read_bytes()
        try:
            self._cert = x509.load_der_x509_certificate(cer_data, default_backend())
        except Exception:
            self._cert = x509.load_pem_x509_certificate(cer_data, default_backend())

        # Cargar clave privada
        key_data = self.key_path.read_bytes()
        last_err = None
        for loader in [
            lambda: serialization.load_der_private_key(key_data, password=self.password, backend=default_backend()),
            lambda: serialization.load_pem_private_key(key_data, password=self.password, backend=default_backend()),
        ]:
            try:
                self._private_key = loader()
                break
            except Exception as e:
                last_err = e
        if not self._private_key:
            raise PAdESLTError(f"No se pudo descifrar .key: {last_err}")

    def _setup_pyhanko(self) -> None:
        """
        Prepara el signer de pyHanko.
        pyHanko puede cargar desde PEM o PFX. Convertimos a PEM en memoria.
        """
        # Exportar certificado y clave a archivos temporales PEM
        self._temp_dir = Path(tempfile.mkdtemp(prefix="megalodon_pades_"))

        cert_pem = self._cert.public_bytes(serialization.Encoding.PEM)
        key_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )

        self._cert_pem_path = self._temp_dir / "cert.pem"
        self._key_pem_path = self._temp_dir / "key.pem"
        self._cert_pem_path.write_bytes(cert_pem)
        self._key_pem_path.write_bytes(key_pem)

        signers, timestamps, SigSeedSubFilter, IncrementalPdfFileWriter, ValidationContext, RequestsFetcherBackend = _import_pyhanko()

        # Cargar en pyHanko
        self._pyhanko_signer = signers.SimpleSigner.load(
            key_file=str(self._key_pem_path),
            cert_file=str(self._cert_pem_path),
            ca_chain_files=[],  # pyHanko inferirá cadena si está en el cert
            key_passphrase=None  # Ya desciframos nosotros
        )

        # Configurar TSA
        tsa_url = self.tsa_url or self.DEFAULT_TSA_URLS[0]
        self._timestamper = timestamps.HTTPTimeStamper(tsa_url)

    def sign_pades_lt(self, input_pdf: str, output_pdf: str,
                      field_name: str = "Signature1",
                      reason: str = "Firma con e.firma SAT / Megalodon",
                      location: str = "Mexico",
                      use_lta: bool = False) -> dict:
        """
        Firma PDF con PAdES-B-LT (Long Term) o PAdES-B-LTA (Archival).

        Args:
            input_pdf: PDF original
            output_pdf: PDF firmado de salida
            field_name: Nombre del campo de firma
            reason: Razón de firma
            location: Ubicación
            use_lta: Si True, genera PAdES-B-LTA (incluye DocumentTimeStamp)

        Returns:
            dict con rutas y estado
        """
        # Crear contexto de validación
        # Nota: Para validación completa necesitamos certificados raíz.
        # pyHanko usará los del sistema si están disponibles.
        try:
            signers, timestamps, SigSeedSubFilter, IncrementalPdfFileWriter, ValidationContext, RequestsFetcherBackend = _import_pyhanko()
            vc = ValidationContext(
                trust_roots=self.trust_roots if self.trust_roots else None,
                allow_fetching=True,
                fetcher_backend=RequestsFetcherBackend()
            )
        except Exception as e:
            raise RuntimeError(
                "No se pudo construir un ValidationContext verificable para PAdES-LT/LTA. "
                "La firma se rechaza para no producir un documento cuya cadena de confianza no pueda validarse."
            ) from e

        signature_meta = signers.PdfSignatureMetadata(
            field_name=field_name,
            md_algorithm="sha256",
            subfilter=SigSeedSubFilter.PADES,
            validation_context=vc,
            embed_validation_info=True,   # Esto hace LT (Long Term)
            use_pades_lta=use_lta,        # Esto hace LTA (Archival)
            reason=reason,
            location=location,
        )

        signers, timestamps, SigSeedSubFilter, IncrementalPdfFileWriter, ValidationContext, RequestsFetcherBackend = _import_pyhanko()
        with open(input_pdf, "rb") as inf:
            w = IncrementalPdfFileWriter(inf)
            with open(output_pdf, "wb") as outf:
                signers.sign_pdf(
                    w,
                    signature_meta=signature_meta,
                    signer=self._pyhanko_signer,
                    timestamper=self._timestamper,
                    output=outf
                )

        return {
            "success": True,
            "output_path": str(Path(output_pdf).resolve()),
            "profile": "PAdES-B-LTA" if use_lta else "PAdES-B-LT",
            "tsa_url": self.tsa_url or self.DEFAULT_TSA_URLS[0],
            "digest": "sha256",
            "validation_info_embedded": True,
            "document_timestamp": use_lta
        }

    def lta_update(self, pdf_path: str, output_path: Optional[str] = None) -> dict:
        """
        Actualiza un PDF firmado PAdES-LTA agregando un nuevo DocumentTimeStamp.
        Útil para mantener la cadena de confianza antes de que expire el último TSA.
        """
        out = output_path or pdf_path
        signers, timestamps, SigSeedSubFilter, IncrementalPdfFileWriter, ValidationContext, RequestsFetcherBackend = _import_pyhanko()
        from pyhanko.sign import PdfTimeStamper
        timestamper = PdfTimeStamper(self._timestamper)

        with open(pdf_path, "rb") as inf:
            w = IncrementalPdfFileWriter(inf)
            with open(out, "wb") as outf:
                timestamper.timestamp_pdf(w, output=outf)

        return {
            "success": True,
            "output_path": str(Path(out).resolve()),
            "action": "LTA_update",
            "tsa_url": self.tsa_url or self.DEFAULT_TSA_URLS[0]
        }

    def cleanup(self):
        """Borra archivos temporales PEM."""
        import shutil
        if hasattr(self, '_temp_dir') and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)

    def __del__(self):
        self.cleanup()


# =============================================================================
# CLI / TEST
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Megalodon PAdES-LT Signer")
    parser.add_argument("--cer", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--tsa", default=None, help="URL del TSA")
    parser.add_argument("--lta", action="store_true", help="Generar PAdES-B-LTA")
    parser.add_argument("--lta-update", action="store_true", help="Actualizar timestamp LTA")
    args = parser.parse_args()

    signer = PAdESLTSigner(args.cer, args.key, args.password, tsa_url=args.tsa)

    if args.lta_update:
        result = signer.lta_update(args.input, args.output)
    else:
        result = signer.sign_pades_lt(args.input, args.output, use_lta=args.lta)

    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))
    signer.cleanup()
