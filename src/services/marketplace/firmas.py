"""
Marketplace · Firmas digitales (Fase IV · Bloque 2). Verifica la integridad y autenticidad de un
plugin. DEGRADABLE: usa HMAC-SHA256 con una clave de firma (env MARKETPLACE_SIGNING_KEY) como sello
verificable ahora mismo; la arquitectura admite sustituirlo por PKI real (X.509) sin cambiar la API.

Estados posibles de un plugin: firmado · no_firmado · caducado · revocado · corrupto.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime

FIRMADO, NO_FIRMADO, CADUCADO, REVOCADO, CORRUPTO = (
    "firmado", "no_firmado", "caducado", "revocado", "corrupto")


def _clave() -> bytes:
    return (os.getenv("MARKETPLACE_SIGNING_KEY") or "smart-manager-marketplace-dev-key").encode()


def _canonico(manifest: dict) -> bytes:
    """Serialización canónica del manifest EXCLUYENDO los propios campos de firma."""
    limpio = {k: v for k, v in (manifest or {}).items()
              if k not in ("firma", "firma_caducidad", "firma_revocada")}
    return json.dumps(limpio, sort_keys=True, ensure_ascii=False).encode()


def hash_manifest(manifest: dict) -> str:
    return hashlib.sha256(_canonico(manifest)).hexdigest()


def checksum(datos) -> str:
    """SHA-256 de bytes o de un fichero (ruta)."""
    h = hashlib.sha256()
    if isinstance(datos, (bytes, bytearray)):
        h.update(datos)
    elif isinstance(datos, str) and os.path.isfile(datos):
        with open(datos, "rb") as f:
            for bloque in iter(lambda: f.read(65536), b""):
                h.update(bloque)
    else:
        h.update(str(datos).encode())
    return h.hexdigest()


def firmar(manifest: dict) -> str:
    """Devuelve la firma HMAC-SHA256 del manifest canónico (para empaquetar plugins de prueba)."""
    return hmac.new(_clave(), _canonico(manifest), hashlib.sha256).hexdigest()


def verificar(manifest: dict, *, revocadas=()) -> str:
    """Determina el estado de firma de un plugin. `manifest` puede incluir `firma` y
    `firma_caducidad` (ISO). `revocadas` = colección de hashes/claves revocados."""
    firma = (manifest or {}).get("firma")
    if not firma:
        return NO_FIRMADO
    # Revocación (por clave o por hash del manifest).
    if manifest.get("clave") in set(revocadas) or hash_manifest(manifest) in set(revocadas):
        return REVOCADO
    # Integridad/autenticidad.
    esperada = firmar(manifest)
    if not hmac.compare_digest(firma, esperada):
        return CORRUPTO
    # Caducidad.
    cad = manifest.get("firma_caducidad")
    if cad:
        try:
            if datetime.fromisoformat(str(cad)) < datetime.now():
                return CADUCADO
        except Exception:
            pass
    return FIRMADO


def es_valida(estado) -> bool:
    return estado == FIRMADO


__all__ = ["FIRMADO", "NO_FIRMADO", "CADUCADO", "REVOCADO", "CORRUPTO",
           "hash_manifest", "checksum", "firmar", "verificar", "es_valida"]
