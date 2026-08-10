"""
Mapeo de columnas asistido por IA (Fase 2). DEGRADABLE: usa Claude si hay paquete `anthropic` +
`ANTHROPIC_API_KEY`; si no, cae limpiamente a la heurística de `mapeo.sugerir_mapeo`. Reutiliza el patrón de
backend inyectable de `utils/ai_translator` (N7, sin motor LLM nuevo). La IA solo PROPONE; el usuario confirma.
"""

import json
import logging
import os

from src.services.importacion.mapeo import sugerir_mapeo
from src.services.importacion.modelo import CAMPOS, PRODUCTOS

logger = logging.getLogger("importacion.mapeo_ia")

try:
    from src.utils.ai_translator import _MODEL as _MODEL
except Exception:                                        # pragma: no cover
    _MODEL = os.getenv("SMART_AI_MODEL", "claude-sonnet-4-6")

_backend = None
_intentado = False


def set_backend(fn):
    """Inyecta un backend LLM `fn(system_prompt, user_text) -> str` (para pruebas o proveedores propios)."""
    global _backend, _intentado
    _backend = fn
    _intentado = True


def _anthropic_backend():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
    except Exception:
        return None
    cliente = anthropic.Anthropic(api_key=api_key)

    def _call(system_prompt, user_text):
        msg = cliente.messages.create(
            model=_MODEL, max_tokens=1000,
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_text}])
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()

    return _call


def _obtener_backend():
    global _backend, _intentado
    if _backend is not None:
        return _backend
    if not _intentado:
        _intentado = True
        _backend = _anthropic_backend()
    return _backend


def disponible() -> bool:
    """True si hay backend IA (paquete + API key). Chequeo para la GUI, sin llamar al modelo."""
    return _obtener_backend() is not None


def _system_prompt(entidad):
    campos = CAMPOS.get(entidad, {})
    lineas = [f"- {c}{' (OBLIGATORIO)' if req else ''}" for c, (req, _s) in campos.items()]
    return ("Eres un asistente de migración de datos de un ERP. Debes emparejar las COLUMNAS de un fichero de "
            "una empresa con los CAMPOS CANÓNICOS del sistema. Campos canónicos:\n" + "\n".join(lineas) +
            "\n\nResponde EXCLUSIVAMENTE con un objeto JSON {campo_canonico: nombre_de_columna_o_null}. "
            "No incluyas explicaciones ni texto fuera del JSON. Usa null si ningún campo encaja.")


def _user_prompt(columnas, muestra):
    partes = ["COLUMNAS DEL FICHERO:", json.dumps(list(columnas), ensure_ascii=False)]
    if muestra:
        partes += ["\nMUESTRA DE FILAS:", json.dumps(muestra[:3], ensure_ascii=False, default=str)]
    return "\n".join(partes)


def _parse(raw, columnas, entidad):
    campos = set(CAMPOS.get(entidad, {}))
    cols = set(columnas)
    try:
        ini, fin = raw.find("{"), raw.rfind("}")
        obj = json.loads(raw[ini:fin + 1]) if ini >= 0 and fin > ini else {}
    except (json.JSONDecodeError, ValueError):
        return {}
    return {k: v for k, v in obj.items() if k in campos and v in cols}


def sugerir_mapeo_ia(columnas, entidad=PRODUCTOS, *, muestra=None) -> dict:
    """Sugiere el mapeo con IA; si no hay backend o falla, devuelve la heurística. La IA manda, la heurística
    rellena los huecos que la IA deje sin asignar."""
    base = sugerir_mapeo(columnas, entidad)                     # respaldo SIEMPRE disponible
    backend = _obtener_backend()
    if not backend or not columnas:
        return base
    try:
        raw = backend(_system_prompt(entidad), _user_prompt(columnas, muestra))
        propuesto = _parse(raw, columnas, entidad)
    except Exception as e:
        logger.debug("mapeo IA degradado a heurística: %s", e)
        return base
    if not propuesto:
        return base
    combinado = dict(base)
    combinado.update(propuesto)                                 # la IA tiene prioridad
    return combinado
