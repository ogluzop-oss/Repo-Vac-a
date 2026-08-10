"""
IA Communication Assistant (CCP Fase II · B9) — asistente de comunicaciones DEGRADABLE.

Ayuda a redactar/responder/traducir/corregir/resumir/cambiar tono/generar asunto/clasificar/extraer.
Reutiliza la IA existente del ERP (`utils.ai_translator` para traducir; Copilot/SomaKernel si están)
de forma DEGRADABLE: si no hay backend IA, funciones deterministas mínimas. NUNCA accede al motor de
correo; para enviar, el consumidor usa `ccp.enviar_comunicacion`. API-First (sin PyQt).
"""

import logging
import re

logger = logging.getLogger("ccp.ia_asistente")


def _idioma_actual():
    try:
        from src.utils import i18n
        return i18n.current_language()
    except Exception:
        return "es"


def disponible() -> bool:
    """True si hay algún backend IA (traductor u otro). Degradable si False."""
    try:
        from src.utils import ai_translator  # noqa: F401
        return True
    except Exception:
        return False


def traducir(texto, idioma_destino, *, dominio="comunicaciones") -> str:
    if not texto:
        return texto
    try:
        from src.utils import ai_translator
        return ai_translator.traducir(texto, idioma_destino, dominio=dominio)
    except Exception:
        return texto   # degradación: original


def resumir(texto, *, max_frases=2) -> str:
    if not texto:
        return ""
    frases = re.split(r"(?<=[.!?])\s+", texto.strip())
    return " ".join(frases[:max_frases]).strip()


def generar_asunto(texto, *, max_len=60) -> str:
    if not texto:
        return ""
    primera = re.split(r"(?<=[.!?])\s+", texto.strip())[0]
    return (primera[:max_len]).strip()


def corregir(texto) -> str:
    """Corrección mínima determinista (espacios/duplicados). Degradable."""
    if not texto:
        return texto
    t = re.sub(r"\s+", " ", texto).strip()
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    return t


TONOS = ("formal", "cercano", "neutro", "urgente")


def cambiar_tono(texto, tono="formal") -> str:
    if not texto:
        return texto
    saludos = {"formal": "Estimado/a cliente:", "cercano": "¡Hola!", "urgente": "IMPORTANTE:",
               "neutro": ""}
    pre = saludos.get(tono, "")
    return (pre + "\n\n" + texto).strip() if pre else texto


def clasificar(texto) -> str:
    """Clasificación por palabras clave (determinista, degradable)."""
    t = (texto or "").lower()
    reglas = [("factura", "facturacion"), ("pedido", "compras"), ("nómina", "rrhh"),
              ("nomina", "rrhh"), ("incidencia", "sat"), ("reclam", "sat"), ("contrato", "legal"),
              ("promo", "marketing")]
    for k, cat in reglas:
        if k in t:
            return cat
    return "general"


def extraer(texto) -> dict:
    """Extrae entidades básicas (correos, teléfonos, importes) — determinista."""
    t = texto or ""
    return {
        "correos": re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", t),
        "telefonos": re.findall(r"(?:(?:\+34|0034)?\s?)?[6-9]\d{2}[\s.-]?\d{3}[\s.-]?\d{3}", t),
        "importes": re.findall(r"\d+[.,]?\d*\s?(?:€|EUR)", t),
    }


def redactar(intencion, *, contexto=None, idioma=None, tono="formal") -> dict:
    """Sugiere (asunto, cuerpo) para una intención. Con IA si está; si no, plantilla determinista.
    NO envía: el consumidor usa `ccp.enviar_comunicacion` con el resultado."""
    idioma = idioma or _idioma_actual()
    cuerpo = str(intencion or "")
    ctx = contexto or {}
    if ctx:
        detalles = "; ".join(f"{k}: {v}" for k, v in ctx.items())
        cuerpo = f"{cuerpo}\n\n{detalles}"
    cuerpo = cambiar_tono(cuerpo, tono)
    asunto = generar_asunto(str(intencion or ""))
    if idioma and idioma != "es":
        asunto, cuerpo = traducir(asunto, idioma), traducir(cuerpo, idioma)
    return {"asunto": asunto, "cuerpo": cuerpo, "idioma": idioma, "ia": disponible()}


def responder(mensaje_original, *, intencion="acuse", idioma=None, tono="formal") -> dict:
    """Sugiere una respuesta a un mensaje recibido (degradable)."""
    base = {"acuse": "Hemos recibido su mensaje y le responderemos a la mayor brevedad.",
            "confirmacion": "Confirmamos la recepción y tramitación de su solicitud.",
            "rechazo": "Lamentamos no poder atender su solicitud en este momento."}
    return redactar(base.get(intencion, base["acuse"]), idioma=idioma, tono=tono)
