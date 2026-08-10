"""
PCD · Publicaciones · Modelo/vocabulario (CD-001/004 · Fase 7). Constantes estables de la Product
Publication Layer y constructor de REFERENCIAS de media (nunca almacena ficheros).
"""

from __future__ import annotations

# Tipologías representables (EXTENSIBLE: se aceptan futuras tipologías sin tocar el motor).
TIPOS = ("producto", "servicio", "digital", "pack", "variante")

# Objetivos comerciales (solo arquitectura; la lógica comercial llega en fases posteriores).
OBJETIVOS = ("vender", "branding", "captacion", "reservas", "catalogo", "campana", "preventa")

# Estados de publicación. La EJECUCIÓN/gobierno de transiciones es de Workflow (no hay motor paralelo).
ESTADOS = ("BORRADOR", "VALIDADA", "PROGRAMADA", "PUBLICADA", "PAUSADA", "RETIRADA", "ARCHIVADA")

# Origen del contenido de una versión. La IA solo PROPONE (ia_propuesta); nunca publica directamente.
ORIGENES = ("manual", "ia_propuesta")

# Campos SEO soportados (sin generación automática en esta fase).
SEO_CAMPOS = ("titulo", "descripcion", "slug", "metadatos", "open_graph", "twitter_cards", "schema_org")

# Tipos de media referenciables (siempre por referencia: Storage/CDN/Centro Documental).
MEDIA_TIPOS = ("imagen", "video", "documento", "ficha_tecnica", "descargable")

# Estado → evento de Event Bus (los no mapeados emiten PublicationUpdated).
EVENTO_ESTADO = {"PUBLICADA": "PublicationPublished", "ARCHIVADA": "PublicationArchived"}


def media_ref(tipo, *, referencia=None, backend="documental", documento_id=None, url=None, meta=None):
    """Construye una REFERENCIA de media. NUNCA almacena el archivo: reutiliza la abstracción de
    Storage/CDN o el Centro Documental (por `documento_id`). `backend` ∈ {documental, storage, cdn, url}."""
    return {"tipo": tipo, "backend": backend, "documento_id": documento_id,
            "referencia": referencia, "url": url, "meta": meta or {}}


def seo_vacio() -> dict:
    return {c: None for c in SEO_CAMPOS}


__all__ = ["TIPOS", "OBJETIVOS", "ESTADOS", "ORIGENES", "SEO_CAMPOS", "MEDIA_TIPOS", "EVENTO_ESTADO",
           "media_ref", "seo_vacio"]
