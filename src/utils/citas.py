"""
Recordatorios de citas/eventos del calendario (pestaña PLANIFICAR CITAS).

Los eventos se guardan en documentos/eventos_citas.json con la forma:
    { "yyyy-MM-dd": [ {"asunto","hora_inicio","hora_fin"}, ... ] }

El menú principal muestra una notificación flotante SOLO el día del evento (nunca
antes). Cuando el usuario pulsa "ENTENDIDO", el evento se marca como visto
(documentos/citas_avisos_vistos.json) para no volver a avisar.
"""

import json
import logging
import os
from datetime import date

logger = logging.getLogger("citas")

_DOCS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "documentos",
)
_EVENTS_FILE = os.path.join(_DOCS, "eventos_citas.json")
_VISTOS_FILE = os.path.join(_DOCS, "citas_avisos_vistos.json")


def _cargar(path, default):
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.debug("No se pudo leer %s: %s", path, e)
    return default


def _clave(fecha: str, ev: dict) -> str:
    return f"{fecha}|{ev.get('asunto','')}|{ev.get('hora_inicio','')}"


def pendientes_hoy():
    """Devuelve (fecha_hoy, [eventos de HOY aún no vistos]). Solo el día del evento;
    nunca eventos futuros ni pasados."""
    hoy = date.today().strftime("%Y-%m-%d")
    eventos = _cargar(_EVENTS_FILE, {}).get(hoy) or []
    if not eventos:
        return hoy, []
    data = _cargar(_VISTOS_FILE, [])
    vistos = set(data) if isinstance(data, list) else set()
    pend = [e for e in eventos if _clave(hoy, e) not in vistos]
    return hoy, pend


def marcar_vistos(fecha: str, eventos: list):
    """Marca esos eventos como vistos para que no se vuelva a avisar."""
    data = _cargar(_VISTOS_FILE, [])
    vistos = set(data) if isinstance(data, list) else set()
    for e in eventos:
        vistos.add(_clave(fecha, e))
    try:
        os.makedirs(_DOCS, exist_ok=True)
        with open(_VISTOS_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(vistos), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("No se pudo guardar avisos vistos: %s", e)
