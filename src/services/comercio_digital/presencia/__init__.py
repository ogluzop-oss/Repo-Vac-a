"""
PCD · Digital Presence Generator (CD-003/004 · Fase 8).

Genera PROPUESTAS de contenido para la Experiencia Comercial Pública (descripción/SEO/social/reclamo/
ficha) de una publicación. La IA SOLO PROPONE: el resultado se almacena como una VERSIÓN nueva de la
Product Publication Layer con `origen='ia_propuesta'`. NUNCA publica, NUNCA ejecuta acciones de
negocio; la aprobación/publicación la gobierna Workflow.

Invariantes (ratificadas):
  · IA Provider-Agnostic (I9): se consume ÚNICAMENTE `capabilities.ia()` (AI Runtime). Nunca se acopla
    a GPT/Claude/Gemini/Fable ni a proveedor alguno. Degradable: sin proveedor → heurístico determinista.
  · IA propone → PPL almacena versiones → Workflow decide. La IA nunca publica ni actúa sobre el negocio.
  · Reutiliza por capacidades: IA (propuesta), Event Bus (PresenceProposed) y Observabilidad
    (Correlation ID / Communication ID). Toda propuesta queda registrada (N9, vía evento + versión PPL).
  · No mueve stock, no reserva, no sincroniza, no publica en canales, no toca Availability/Fulfillment.
"""

from __future__ import annotations

import logging
import unicodedata
import uuid

from src.services.comercio_digital import publicaciones as _ppl

logger = logging.getLogger("cd.presencia")

FASE = 8

# Tipos de contenido que el generador puede PROPONER (no ejecuta lógica comercial).
TIPOS_CONTENIDO = ("descripcion", "seo", "social", "reclamo", "ficha")


def _emp(id_empresa=None):
    from src.services.comercio_digital._base import emp as _emp_base
    return _emp_base(id_empresa)
def _correlation_id() -> str:
    from src.services.comercio_digital import _base
    return _base.correlation_id("cdpres")


def _publicar(tipo, *, id_empresa=None, ref_id=None, payload=None):
    from src.services.comercio_digital import _base
    _base.publicar_evento(tipo, id_empresa=id_empresa, origen="comercio_digital.presencia",
                          ref_entidad="cd_publicacion", ref_id=ref_id, payload=payload)


def _slug(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    t = "".join(c if c.isalnum() else "-" for c in t.lower()).strip("-")
    while "--" in t:
        t = t.replace("--", "-")
    return t


def _heuristico(base_contenido, base_seo, tipos, idioma) -> dict:
    """Propuesta DETERMINISTA de reserva (sin proveedor de IA). No es IA: es la degradación elegante."""
    nombre = base_contenido.get("nombre") or base_seo.get("titulo") or "Producto"
    contenido, seo = {}, {}
    if "descripcion" in tipos:
        contenido["descripcion"] = f"{nombre}. Disponible en nuestra tienda."
    if "reclamo" in tipos:
        contenido["reclamo"] = f"{nombre} — calidad garantizada"
    if "social" in tipos:
        contenido["social"] = f"Descubre {nombre}"
    if "ficha" in tipos:
        contenido["ficha"] = {"titulo": nombre}
    if "seo" in tipos:
        seo["titulo"] = nombre
        seo["slug"] = _slug(nombre)
        seo["descripcion"] = f"{nombre} — compra online."
    return {"contenido": contenido, "seo": seo}


def _ia_proponer(spec) -> dict | None:
    """Propuesta por la CAPACIDAD de IA (provider-agnostic). Devuelve None si no hay proveedor o no
    produce un resultado utilizable → el llamador degrada al heurístico. Nunca acopla a un proveedor."""
    try:
        from src.platform import capabilities as cap
        ia = cap.ia()
        if ia is None or not hasattr(ia, "agente"):
            return None
        ag = ia.agente("comercio")
        if hasattr(ag, "generar_documento"):
            r = ag.generar_documento("presencia_comercial", spec, id_empresa=spec.get("id_empresa"))
            if isinstance(r, dict) and (r.get("contenido") or r.get("seo")):
                return {"contenido": r.get("contenido", {}), "seo": r.get("seo", {})}
    except Exception as e:
        logger.debug("IA no disponible para propuesta: %s", e)
    return None


def proponer(id_publicacion, *, tipos=None, idioma=None, region="", id_empresa=None, actor=None,
             contexto=None, communication_id=None):
    """Genera una PROPUESTA de presencia y la almacena como versión PPL `origen='ia_propuesta'`. NO
    publica; el estado de la publicación NO cambia (lo gobierna Workflow). Devuelve la versión creada y
    metadatos de la propuesta."""
    emp = _emp(id_empresa)
    base = _ppl.obtener_version(id_publicacion, None, emp)
    if base is None:
        return None
    tipos = tuple(t for t in (tipos or TIPOS_CONTENIDO) if t in TIPOS_CONTENIDO) or TIPOS_CONTENIDO
    cid = _correlation_id()
    spec = {"base": base["contenido"], "seo": base["seo"], "tipos": list(tipos), "idioma": idioma,
            "contexto": contexto or {}, "id_empresa": emp}

    propuesta = _ia_proponer(spec)
    motor = "ia"
    if propuesta is None:
        propuesta = _heuristico(base["contenido"], base["seo"], tipos, idioma)
        motor = "heuristico"

    nuevo_contenido = {**base["contenido"], **propuesta.get("contenido", {})}
    nuevo_seo = {**base["seo"], **propuesta.get("seo", {})}
    version = _ppl.nueva_version(id_publicacion, contenido=nuevo_contenido, seo=nuevo_seo,
                                 id_empresa=emp, actor=actor or "presencia", origen="ia_propuesta",
                                 communication_id=communication_id)
    if version is None:
        return None
    _publicar("PresenceProposed", id_empresa=emp, ref_id=id_publicacion,
              payload={"version": version, "tipos": list(tipos), "motor": motor,
                       "provider_agnostic": True, "publicado": False, "correlation_id": cid,
                       "communication_id": communication_id})
    return {"id_publicacion": id_publicacion, "version": version, "motor": motor,
            "provider_agnostic": True, "publicado": False, "tipos": list(tipos),
            "propuesta": propuesta, "correlation_id": cid}


def descriptor() -> dict:
    return {"servicio": "cd_presencia", "rfc": "CD-003/004", "fase": FASE, "estado": "implementado",
            "tipos_contenido": list(TIPOS_CONTENIDO), "solo_propone": True, "publica": False,
            "ejecuta_negocio": False, "provider_agnostic": True, "gobernado_por": "workflow",
            "almacena_en": "product_publication_layer", "origen_version": "ia_propuesta",
            "degradable": True, "mueve_stock": False}


__all__ = ["FASE", "TIPOS_CONTENIDO", "proponer", "descriptor"]
