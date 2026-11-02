"""
Lectura de facturas con IA (Fase D — Paso 2 del wizard "Calculadora Fiscal"): extrae
proveedor/NIF/fecha/base/cuota IVA/total de una imagen o PDF de una factura de proveedor
mediante visión de Claude. Sigue el MISMO patrón DEGRADABLE que
`services/importacion/mapeo_ia.py` (check de paquete `anthropic` + `ANTHROPIC_API_KEY`,
`disponible()` para que la GUI sepa si puede ofrecer el botón sin llamar al modelo,
`set_backend()` inyectable para pruebas, misma convención de modelo vía
`utils.ai_translator._MODEL`). La IA SOLO propone un borrador: la GUI del wizard nunca
escribe una factura de compra real sin que el usuario confirme explícitamente cada campo
(mismo principio de gobernanza "la IA propone, el humano confirma" ya aplicado en RRHH/B2B/
Migración).
"""

import base64
import json
import logging
import mimetypes
import os

logger = logging.getLogger("contab.factura_ocr_ia")

try:
    from src.utils.ai_translator import _MODEL as _MODEL
except Exception:                                        # pragma: no cover
    _MODEL = os.getenv("SMART_AI_MODEL", "claude-sonnet-4-6")

_CAMPOS = ("proveedor", "nif", "fecha", "numero_factura", "base", "cuota_iva", "total")

_SYSTEM_PROMPT = (
    "Eres un asistente de contabilidad que extrae los datos clave de una factura de "
    "proveedor a partir de su imagen o PDF. Responde EXCLUSIVAMENTE con un objeto JSON con "
    "estas claves: proveedor (razón social), nif (NIF/CIF del proveedor), fecha "
    "(AAAA-MM-DD), numero_factura, base (importe base imponible, número, sin símbolo de "
    "moneda, usa punto decimal), cuota_iva (importe de la cuota de IVA, número) y total "
    "(importe total, número). Usa null en cualquier campo que no puedas leer con certeza. "
    "No incluyas explicaciones ni texto fuera del JSON.")

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
                model=_MODEL, max_tokens=1024,
                system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": [
                    {"type": tipo_bloque, "source": {"type": "base64", "media_type": mime, "data": datos_b64}},
                    {"type": "text", "text": "Extrae los datos de esta factura de proveedor."},
                ]}])

        id_empresa, id_usuario = resolver_tenant_actual()
        msg = ejecutar_tarea_ia(id_empresa, id_usuario, "invoice_ocr", _llamar)
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
    """True si hay backend IA (paquete `anthropic` + `ANTHROPIC_API_KEY`). Chequeo para la
    GUI, sin llamar al modelo — misma convención que `mapeo_ia.disponible()`."""
    return _obtener_backend() is not None


def _parse(raw):
    try:
        ini, fin = raw.find("{"), raw.rfind("}")
        obj = json.loads(raw[ini:fin + 1]) if ini >= 0 and fin > ini else {}
    except (json.JSONDecodeError, ValueError):
        return {}
    return {k: obj.get(k) for k in _CAMPOS if obj.get(k) not in (None, "")}


_MIME_PERMITIDOS = {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}


def extraer_factura(ruta_archivo) -> dict:
    """Extrae el borrador de una factura desde `ruta_archivo` (imagen o PDF). Devuelve
    siempre {ok, datos|error} — NUNCA lanza, degradación honesta: sin backend disponible
    devuelve ok=False con el motivo real (nunca inventa datos)."""
    backend = _obtener_backend()
    if backend is None:
        return {"ok": False, "error": "IA no disponible (falta el paquete «anthropic» o la "
                "variable de entorno ANTHROPIC_API_KEY)."}
    mime, _enc = mimetypes.guess_type(ruta_archivo)
    if mime not in _MIME_PERMITIDOS:
        return {"ok": False, "error": f"Formato no soportado para lectura por IA: "
                f"{mime or 'desconocido'} (usa imagen PNG/JPEG/GIF/WEBP o PDF)."}
    try:
        with open(ruta_archivo, "rb") as f:
            datos_b64 = base64.b64encode(f.read()).decode("ascii")
        raw = backend(mime, datos_b64)
        datos = _parse(raw)
    except Exception as e:
        logger.error("extraer_factura: %s", e)
        return {"ok": False, "error": str(e)}
    if not datos:
        return {"ok": False, "error": "La IA no devolvió ningún dato reconocible de la factura."}
    return {"ok": True, "datos": datos}


def resolver_o_crear_proveedor(nif, razon_social, id_empresa=None):
    """Busca un proveedor existente por NIF EXACTO; si no existe, da de alta uno nuevo con los
    datos del borrador ya confirmado por el usuario. Devuelve (id_proveedor, creado_bool).
    Nunca crea un duplicado si el NIF ya coincide con un proveedor existente de la empresa."""
    from src.db import proveedores as P
    nif = (nif or "").strip()
    if nif:
        candidatos = P.listar_proveedores(id_empresa=id_empresa, texto=nif, limite=10)
        exacto = next((c for c in candidatos
                       if (c.get("cif_nif") or "").strip().upper() == nif.upper()), None)
        if exacto:
            return exacto["id_proveedor"], False
    nombre = (razon_social or "").strip() or nif or "Proveedor sin identificar"
    pid = P.crear_proveedor(nombre, cif_nif=nif or None, id_empresa=id_empresa)
    return pid, bool(pid)
