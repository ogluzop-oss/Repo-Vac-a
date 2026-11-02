"""
Lectura de tickets de gasto con IA (petición explícita: "escaneo de tickets mediante la cámara del
móvil con lectura automática de datos mediante OCR"). MISMO patrón degradable exacto que
`services/contabilidad/factura_ocr_ia.py` (visión de Claude vía `ejecutar_tarea_ia`, `disponible()`
para que la GUI/móvil sepan si pueden ofrecer el botón sin llamar al modelo, `set_backend()`
inyectable para pruebas) — dominio distinto (ticket de gasto de EMPLEADO, no factura de PROVEEDOR),
así que es un fichero hermano, no una reutilización forzada de un prompt ajeno. "La IA propone, el
humano confirma": nunca crea el gasto directamente, solo devuelve un borrador para que la pantalla
(móvil o escritorio) lo muestre editable antes de guardar."""

import base64
import json
import logging
import mimetypes
import os

logger = logging.getLogger("gastos_viaje.ocr")

try:
    from src.utils.ai_translator import _MODEL as _MODEL
except Exception:                                        # pragma: no cover
    _MODEL = os.getenv("SMART_AI_MODEL", "claude-sonnet-4-6")

_CAMPOS = ("comercio", "fecha", "importe", "categoria_sugerida", "concepto")
_CATEGORIAS_VALIDAS = ("transporte", "alojamiento", "dietas", "otros")

_SYSTEM_PROMPT = (
    "Eres un asistente que extrae los datos clave de un TICKET o RECIBO de gasto de viaje de "
    "empleado (no una factura de proveedor) a partir de su foto o PDF. Responde EXCLUSIVAMENTE "
    "con un objeto JSON con estas claves: comercio (nombre del establecimiento), fecha "
    "(AAAA-MM-DD), importe (número total pagado, con punto decimal, sin símbolo de moneda), "
    "categoria_sugerida (una de: transporte, alojamiento, dietas, otros — la que mejor encaje "
    "según el tipo de comercio/ticket) y concepto (descripción breve, p. ej. 'Taxi aeropuerto' o "
    "'Comida de trabajo'). Usa null en cualquier campo que no puedas leer con certeza. No "
    "incluyas explicaciones ni texto fuera del JSON.")

_backend = None
_intentado = False


def set_backend(fn):
    """Inyecta un backend `fn(mime, datos_base64) -> str` (para pruebas o proveedores propios)."""
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

    def _call(mime, datos_b64):
        from src.services.ia_control_uso import ejecutar_tarea_ia, resolver_tenant_actual
        tipo_bloque = "document" if mime == "application/pdf" else "image"

        def _llamar():
            return cliente.messages.create(
                model=_MODEL, max_tokens=512,
                system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": [
                    {"type": tipo_bloque, "source": {"type": "base64", "media_type": mime, "data": datos_b64}},
                    {"type": "text", "text": "Extrae los datos de este ticket de gasto."},
                ]}])

        id_empresa, id_usuario = resolver_tenant_actual()
        msg = ejecutar_tarea_ia(id_empresa, id_usuario, "expense_ticket_ocr", _llamar)
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
    """True si hay backend IA (paquete `anthropic` + `ANTHROPIC_API_KEY`). Chequeo para la GUI/
    móvil, sin llamar al modelo — misma convención que `factura_ocr_ia.disponible()`."""
    return _obtener_backend() is not None


def _parse(raw):
    try:
        ini, fin = raw.find("{"), raw.rfind("}")
        obj = json.loads(raw[ini:fin + 1]) if ini >= 0 and fin > ini else {}
    except (json.JSONDecodeError, ValueError):
        return {}
    datos = {k: obj.get(k) for k in _CAMPOS if obj.get(k) not in (None, "")}
    if datos.get("categoria_sugerida") not in _CATEGORIAS_VALIDAS:
        datos.pop("categoria_sugerida", None)
    return datos


_MIME_PERMITIDOS = {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}


def extraer_ticket(ruta_archivo) -> dict:
    """Extrae el borrador de un ticket de gasto desde `ruta_archivo` (foto o PDF). Devuelve
    siempre {ok, datos|error} — NUNCA lanza, degradación honesta: sin backend disponible devuelve
    ok=False con el motivo real (nunca inventa importes)."""
    backend = _obtener_backend()
    if backend is None:
        return {"ok": False, "error": "IA no disponible (falta el paquete «anthropic» o la "
                "variable de entorno ANTHROPIC_API_KEY)."}
    mime, _enc = mimetypes.guess_type(ruta_archivo)
    if mime not in _MIME_PERMITIDOS:
        return {"ok": False, "error": f"Formato no soportado para lectura por IA: "
                f"{mime or 'desconocido'} (usa foto JPEG/PNG o PDF)."}
    try:
        with open(ruta_archivo, "rb") as f:
            datos_b64 = base64.b64encode(f.read()).decode("ascii")
        raw = backend(mime, datos_b64)
        datos = _parse(raw)
    except Exception as e:
        logger.error("extraer_ticket: %s", e)
        return {"ok": False, "error": str(e)}
    if not datos:
        return {"ok": False, "error": "La IA no devolvió ningún dato reconocible del ticket."}
    return {"ok": True, "datos": datos}
