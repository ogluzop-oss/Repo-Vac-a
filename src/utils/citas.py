"""
Recordatorios de citas/eventos del calendario (pestaña PLANIFICAR CITAS).

Lee los eventos de HOY desde la agenda única (`src.services.calendario`, tabla
`calendario_eventos` en BD, multiempresa) — NO desde el JSON legado
(documentos/eventos_citas.json). Ese fichero se migra UNA sola vez a BD
(`gestion_usuarios._migrar_json_citas`) y se renombra a `.migrado.bak`: seguir
leyéndolo aquí dejaba el aviso de "cita de hoy" roto en silencio en cualquier
instalación ya migrada (bug corregido por este módulo).

El menú principal muestra una notificación flotante SOLO el día del evento (nunca
antes). Cuando el usuario pulsa "ENTENDIDO", el evento se marca como visto
(documentos/citas_avisos_vistos.json, lista de ids de evento) para no volver a
avisar. Shape devuelto sin cambios: (fecha, [{"asunto","hora_inicio","hora_fin"}, ...]).
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
_VISTOS_FILE = os.path.join(_DOCS, "citas_avisos_vistos.json")


def _cargar(path, default):
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.debug("No se pudo leer %s: %s", path, e)
    return default


def _fmt_hora(valor) -> str:
    """datetime/str de BD -> 'Hh MMmin' (mismo formato que usaba el JSON legado)."""
    import datetime as _dt
    if valor is None:
        return "0h 00min"
    try:
        if isinstance(valor, str):
            valor = _dt.datetime.fromisoformat(valor.replace("T", " ").split(".")[0])
        return f"{valor.hour}h {valor.minute:02d}min"
    except Exception:
        return "0h 00min"


def pendientes_hoy():
    """Devuelve (fecha_hoy, [eventos de HOY aún no vistos]). Solo el día del evento;
    nunca eventos futuros ni pasados. Lee la agenda única (BD, services.calendario),
    nunca el JSON legado."""
    hoy = date.today().strftime("%Y-%m-%d")
    try:
        from src.services import calendario
        filas = calendario.eventos_dia(hoy)
    except Exception as e:
        logger.debug("No se pudieron leer los eventos de hoy: %s", e)
        return hoy, []
    eventos = [{
        "id": f.get("id"),
        "asunto": f.get("titulo") or "Evento",
        "hora_inicio": _fmt_hora(f.get("inicio")),
        "hora_fin": _fmt_hora(f.get("fin")) if f.get("fin") else _fmt_hora(f.get("inicio")),
    } for f in filas]
    if not eventos:
        return hoy, []
    data = _cargar(_VISTOS_FILE, [])
    vistos = set(data) if isinstance(data, list) else set()
    pend = [e for e in eventos if str(e["id"]) not in vistos]
    return hoy, pend


def marcar_vistos(fecha: str, eventos: list):
    """Marca esos eventos (por id numérico del evento en BD) como vistos para que no
    se vuelva a avisar. `fecha` se conserva en la firma por compatibilidad (no usada)."""
    data = _cargar(_VISTOS_FILE, [])
    vistos = set(data) if isinstance(data, list) else set()
    for e in eventos:
        eid = e.get("id")
        if eid is not None:
            vistos.add(str(eid))
    try:
        os.makedirs(_DOCS, exist_ok=True)
        with open(_VISTOS_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(vistos), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("No se pudo guardar avisos vistos: %s", e)
