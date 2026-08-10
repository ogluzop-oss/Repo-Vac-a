"""
IA documental — análisis del centro documental (`db/documentos`): clasifica por tipo, detecta posibles
DUPLICADOS (mismo hash de contenido), señala documentos sin clasificar y resume. Heurístico honesto (reglas +
conteos); el resumen en lenguaje natural se apoya en `ia/resumenes` (degradable, sin fingir IA). NO borra ni
modifica documentos (solo lee/analiza/recomienda). Multiempresa.
"""

import logging

logger = logging.getLogger("ia.documental")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def analizar(id_empresa=None) -> dict:
    id_empresa = _emp(id_empresa)
    try:
        from src.services.prediccion import configuracion as C
        if not C.activo("documental", id_empresa):
            return {"dominio": "documental", "activo": False, "resumen": {}, "duplicados": [],
                    "sugerencias": [], "alertas": [], "motor": {"tipo": "heuristica", "es_ml": False}}
    except Exception:
        pass
    from src.db import documentos
    por_tipo = documentos.contar_por_tipo(id_empresa) or {}
    docs = documentos.listar_documentos(id_empresa=id_empresa) or []
    por_hash, sin_tipo = {}, 0
    for d in docs:
        h = d.get("hash_documental") or d.get("hash")
        if h:
            por_hash.setdefault(h, []).append(d.get("nombre") or d.get("id"))
        if not (d.get("tipo") or "").strip() or (d.get("tipo") == "otros"):
            sin_tipo += 1
    duplicados = [{"hash": h, "documentos": v} for h, v in por_hash.items() if len(v) > 1]
    sugerencias = []
    if duplicados:
        sugerencias.append(f"{len(duplicados)} grupo(s) de documentos duplicados (mismo contenido).")
    if sin_tipo:
        sugerencias.append(f"{sin_tipo} documento(s) sin clasificar (tipo 'otros').")
    total = sum(por_tipo.values()) if por_tipo else len(docs)
    alertas = [{"tipo": "documental", "severidad": "baja", "mensaje": s} for s in sugerencias]
    return {"dominio": "documental", "activo": True,
            "resumen": {"total": total, "por_tipo": por_tipo, "sin_tipo": sin_tipo,
                        "duplicados": len(duplicados)},
            "duplicados": duplicados[:50], "sugerencias": sugerencias, "alertas": alertas,
            "motor": {"tipo": "heuristica", "es_ml": False}}


def resumen_texto(texto, *, dominio=None) -> str | None:
    """Resumen en lenguaje natural de un documento. Degradable: usa `ia/resumenes` si hay backend IA; si no,
    devuelve None (nunca finge un resumen). No forma parte del análisis heurístico anterior."""
    try:
        from src.services.ia import resumenes
        return resumenes.resumir(texto) if hasattr(resumenes, "resumir") else None
    except Exception as e:
        logger.debug("resumen_texto degradado: %s", e)
        return None
