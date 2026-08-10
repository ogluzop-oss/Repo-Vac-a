"""
Personalidad de SOMA (Fase 3). Da coherencia al carácter: profesional, cercano, claro, natural y
seguro — nunca un chatbot genérico. NO reescribe las respuestas del CopilotService (que ya aportan
el contenido): solo aplica un tono ligero y elige la EXPRESIÓN (estado del personaje) adecuada según
el tipo de respuesta. Sutil por diseño.
"""

import logging

from src.soma.personality.emotions import Emociones
from src.soma.personality.expressions import Expresiones
from src.soma.personality.tone import Tono

logger = logging.getLogger("soma.personality")

# Coletillas breves y humanas para ciertos casos (sin caer en el "chatbot genérico").
_ERROR_CIERRE = " Si quieres, puedo intentarlo de otra manera."
_VACIO = "No he encontrado nada que responder a eso, pero puedo ayudarte si me das algún detalle más."


class Personalidad:
    nombre = "SOMA"

    def __init__(self):
        self.tono = Tono()
        self.expresiones = Expresiones()
        self.emociones = Emociones()

    def modular(self, respuesta, *, tipo="respuesta", contexto=None) -> str:
        """Ajusta ligeramente el texto según el tipo ('respuesta' | 'confirmacion' | 'error')."""
        texto = (respuesta or "").strip()
        if not texto:
            return _VACIO if tipo != "error" else ("Ha ocurrido un problema." + _ERROR_CIERRE)
        if tipo == "error" and _ERROR_CIERRE.strip() not in texto:
            texto = texto.rstrip(".") + "." + _ERROR_CIERRE
        return self.tono.aplicar(texto, contexto=contexto)

    def expresion_para(self, tipo="respuesta") -> str:
        """Estado/expresión del personaje según el tipo de interacción."""
        return {"respuesta": "HABLANDO", "confirmacion": "CONFIRMACION", "error": "ERROR"}.get(
            tipo, "HABLANDO")


_personalidad = None


def personalidad() -> Personalidad:
    global _personalidad
    if _personalidad is None:
        _personalidad = Personalidad()
    return _personalidad
