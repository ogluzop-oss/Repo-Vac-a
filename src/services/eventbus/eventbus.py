"""
Corporate Event Bus (Fase III · B1) — fachada del bus de eventos corporativo.

Punto único para publicar/suscribir/reproducir eventos entre módulos, sobre el bus existente
(`services.eventos`). Cataloga los eventos estándar (Event Registry), gestiona suscripciones y permite
replay. Síncrono; preparado para asíncrono. Multiempresa. API-First (sin PyQt).
"""

import logging

from src.services.eventbus import event_registry as _reg
from src.services.eventbus import event_store as _store
from src.services.eventbus import replay as _replay
from src.services.eventbus import subscription_manager as _subs

logger = logging.getLogger("eventbus")


def publish(tipo, *, id_empresa=None, id_tienda=None, usuario=None, origen=None, prioridad=None,
            ref_entidad=None, ref_id=None, payload=None, destinatarios=None) -> dict | None:
    """Publica un evento (lo persiste y avisa a los suscriptores). Si el evento no está catalogado, se
    publica igualmente pero se avisa por log (recomendado registrarlo en el Event Registry)."""
    if not _reg.es_estandar(tipo):
        logger.debug("evento '%s' no catalogado (considera registrar_evento)", tipo)
    return _store.guardar(tipo, id_empresa=id_empresa, id_tienda=id_tienda, usuario=usuario,
                          origen=origen, prioridad=prioridad, ref_entidad=ref_entidad, ref_id=ref_id,
                          payload=payload, destinatarios=destinatarios)


def subscribe(tipo, handler) -> bool:
    return _subs.subscribe(tipo, handler)


def unsubscribe(tipo, handler) -> bool:
    return _subs.unsubscribe(tipo, handler)


def replay(**filtros) -> list:
    return _replay.replay(**filtros)


def catalogo() -> dict:
    return _reg.catalogo()


def registrar_evento(nombre, **kw):
    return _reg.registrar_evento(nombre, **kw)


def suscripciones(tipo=None) -> dict:
    return _subs.suscripciones(tipo)
