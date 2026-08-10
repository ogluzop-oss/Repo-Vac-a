"""
Replay (Fase III · B1) — reconstrucción/re-despacho de eventos históricos.

SOLO lectura del histórico. Recupera eventos por filtros y (opcionalmente) los vuelve a entregar a un
handler para reconstruir un proceso. No modifica el histórico.
"""

import logging

from src.services.eventbus import event_store as _store

logger = logging.getLogger("eventbus.replay")


def replay(*, tipo=None, id_empresa=None, ref_entidad=None, ref_id=None, desde=None, hasta=None,
           handler=None, limite=1000) -> list:
    """Devuelve los eventos históricos que casan con los filtros (orden cronológico ascendente). Si se
    pasa `handler`, se le entrega cada evento (re-despacho de reconstrucción)."""
    eventos = _store.buscar(tipo=tipo, id_empresa=id_empresa, limite=limite)
    # Filtros locales (por si el bus no los soporta en la consulta).
    def _ok(e):
        if ref_entidad and str(e.get("ref_entidad")) != str(ref_entidad):
            return False
        if ref_id is not None and str(e.get("ref_id")) != str(ref_id):
            return False
        f = str(e.get("creado") or e.get("created_at") or "")
        if desde and f < str(desde):
            return False
        if hasta and f > str(hasta):
            return False
        return True
    eventos = [e for e in eventos if _ok(e)]
    eventos.sort(key=lambda e: str(e.get("id") or e.get("creado") or ""))
    if handler:
        for e in eventos:
            try:
                handler(e)
            except Exception as ex:
                logger.debug("replay handler: %s", ex)
    return eventos
