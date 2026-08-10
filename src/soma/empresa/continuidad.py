"""
CONTINUIDAD entre días (Fase 8). Al volver, SOMA transmite que NO ha olvidado el trabajo: retoma las
misiones pendientes, recuerda lo aprendido de la empresa y adapta el tono al clima del día. Nunca
inventa recuerdos: todo se basa en memoria real (misiones persistidas, conocimiento empresarial,
recomendaciones). Construye un hallazgo para el camino proactivo YA existente (`kernel.intervenir`),
sin modificar el kernel.
"""

import logging

from src.soma.direccion import temporal
from src.soma.empresa import clima, conocimiento, reanudacion

logger = logging.getLogger("soma.empresa.continuidad")


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


def resumen_dia(id_empresa=None, usuario=None) -> str:
    """Frase de continuidad: qué quedó pendiente + lo que SOMA sabe de la empresa. '' si no hay nada."""
    partes = []
    r = reanudacion.resumen(id_empresa, usuario)
    if r:
        partes.append(r)
    saber = conocimiento.frase(id_empresa, limite=1)
    if saber:
        partes.append(f"Recuerdo que {saber[0].lower()}{saber[1:]}" if saber else "")
    return " ".join(p for p in partes if p)


def saludo_continuidad(id_empresa=None, usuario=None):
    """Construye el hallazgo de saludo continuo (para kernel.intervenir). Devuelve None si no hay nada
    relevante que decir (para no ser intrusivo en cada login)."""
    emp = _emp(id_empresa)
    # Prioridad 1: retomar una misión pendiente (lo más valioso para la continuidad).
    hz = reanudacion.hallazgo_continuidad(emp, usuario)
    m = temporal.momento()
    cl = clima.clima(emp)
    if hz is not None:
        hz["mensaje"] = f"{temporal.saludo(m)}. {cl['matiz']}{hz['mensaje']} ¿Lo retomamos?"
        return hz
    # Prioridad 2: si no hay misión pendiente pero sí conocimiento útil, un saludo breve con contexto.
    saber = conocimiento.frase(emp, limite=1)
    if saber or cl["nivel"] in ("carga", "buenas_noticias"):
        msg = f"{temporal.saludo(m)}. {cl['matiz']}Continúo exactamente donde lo dejamos."
        if saber:
            msg += f" {saber}"
        return {
            "clave": "continuidad_saludo", "tipo": "objetivo", "dominio": "empresa",
            "titulo": "Continuidad", "mensaje": msg.strip(), "prioridad": "MEDIA",
            "por_que": "Mantengo la continuidad del trabajo entre sesiones a partir de la memoria real.",
            "consecuencias": "", "si_no_hago_nada": "", "especialistas": [], "datos": {},
        }
    return None   # nada relevante → no molestar
