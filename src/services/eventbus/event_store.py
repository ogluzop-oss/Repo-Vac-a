"""
Event Store (Fase III · B1) — persistencia de eventos (reutiliza el store existente `eventos`).

No crea un almacén nuevo: envuelve `services.eventos.bus` (tabla `eventos` + historial/estado). Permite
guardar, obtener y buscar eventos de forma homogénea para el Event Bus y el replay.
"""

import logging

logger = logging.getLogger("eventbus.store")


def guardar(tipo, *, id_empresa=None, id_tienda=None, usuario=None, origen=None, prioridad=None,
            ref_entidad=None, ref_id=None, payload=None, destinatarios=None) -> dict | None:
    try:
        from src.services.eventos import bus
        return bus.publicar(tipo, id_empresa=id_empresa, id_tienda=id_tienda, usuario=usuario,
                            origen=origen or "eventbus", prioridad=prioridad, ref_entidad=ref_entidad,
                            ref_id=ref_id, payload=payload, destinatarios=destinatarios)
    except Exception as e:
        logger.debug("guardar(%s): %s", tipo, e)
        return None


def obtener(id_evento, *, id_empresa=None) -> dict | None:
    try:
        from src.services.eventos import bus
        return bus.obtener(id_evento, id_empresa=id_empresa)
    except Exception as e:
        logger.debug("obtener(%s): %s", id_evento, e)
        return None


def buscar(*, tipo=None, estado=None, id_empresa=None, id_tienda=None, limite=500) -> list:
    try:
        from src.services.eventos import bus
        return bus.buscar(tipo=tipo, estado=estado, id_empresa=id_empresa, id_tienda=id_tienda,
                          limite=limite)
    except TypeError:
        # Firma sin `limite` en el bus: reintenta sin él.
        try:
            from src.services.eventos import bus
            return bus.buscar(tipo=tipo, estado=estado, id_empresa=id_empresa, id_tienda=id_tienda)
        except Exception as e:
            logger.debug("buscar: %s", e)
            return []
    except Exception as e:
        logger.debug("buscar: %s", e)
        return []
