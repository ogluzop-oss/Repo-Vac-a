"""
Replay Engine (Fase III · B6) — reconstrucción de cualquier proceso empresarial (solo lectura).

Dado un Communication ID / entidad / contacto, reconstruye qué ocurrió, cuándo, quién y qué se envió,
uniendo eventos + comunicaciones + timeline + auditoría. NUNCA modifica el histórico. Multiempresa.
API-First (sin PyQt).
"""

import logging

from src.services.audit_replay import timeline_builder as _tb

logger = logging.getLogger("audit_replay.engine")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def reconstruir(*, id_empresa=None, com_id=None, correo=None, ref_entidad=None, ref_id=None) -> dict:
    """Reconstrucción unificada. Devuelve {resumen, cronologia:[...]} en orden cronológico."""
    id_empresa = _emp(id_empresa)
    crono = _tb.construir(id_empresa, com_id=com_id, correo=correo, ref_entidad=ref_entidad,
                          ref_id=ref_id)
    por_fuente = {}
    for it in crono:
        por_fuente[it["fuente"]] = por_fuente.get(it["fuente"], 0) + 1
    return {
        "resumen": {"total": len(crono), "por_fuente": por_fuente,
                    "inicio": crono[0]["fecha"] if crono else None,
                    "fin": crono[-1]["fecha"] if crono else None},
        "cronologia": crono,
    }
