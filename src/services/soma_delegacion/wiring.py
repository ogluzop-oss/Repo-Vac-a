"""
Suscripción genérica de la delegación a SOMA al Event Bus (`services.eventos`) — un tipo nuevo
con `evento` definido en el catálogo se engancha SOLO. `registrar_suscripciones()` se llama una
vez al arrancar la app (`main.py`), mismo criterio que el resto de `registrar_jobs_*()`.
"""

import logging

logger = logging.getLogger("soma_delegacion.wiring")

_suscrito = False


def registrar_suscripciones():
    global _suscrito
    if _suscrito:
        return
    from src.services import eventos as _EV
    from src.services.soma_delegacion import catalogo, motor

    for tipo_def in catalogo.listar():
        evento = tipo_def.get("evento")
        adaptador = tipo_def.get("contexto_desde_evento")
        if not evento or not adaptador:
            continue

        def _handler(ev, _tipo=tipo_def["codigo"], _adaptador=adaptador):
            try:
                contexto = _adaptador(ev)
                if contexto is None:
                    return
                id_empresa = ev.get("id_empresa")
                if not id_empresa:
                    return
                motor.procesar_evento(_tipo, contexto, id_empresa=id_empresa)
            except Exception as e:
                logger.error("handler de delegación SOMA (%s): %s", _tipo, e)

        _EV.suscribir(evento, _handler)
        logger.info("Delegación SOMA: '%s' suscrito al evento '%s'.", tipo_def["codigo"], evento)
    _suscrito = True
