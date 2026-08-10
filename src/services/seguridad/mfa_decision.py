"""
Decisión ADAPTATIVA de MFA (Gobernanza MFA · Fase 6). Punto ÚNICO que combina, en el orden aprobado:
POLÍTICA EMPRESA → OVERRIDE ROL → CONTEXTO DE TERMINAL → factor activo del usuario → dispositivo de
confianza. Devuelve una decisión coherente (sin contradicciones) que consumen el login de escritorio
y la API. No crea motor nuevo: orquesta `mfa_politica` (política), `mfa` (factor) y `mfa_dispositivos`
(confianza). No exige nada por sí mismo: informa a los llamadores.
"""

import logging

logger = logging.getLogger("seguridad.mfa_decision")


def evaluar(usuario, *, id_empresa=None, codigo_terminal=None, contexto=None) -> dict:
    """Resuelve si un login necesita segundo factor y si el usuario DEBE tener MFA.

    Devuelve:
      · `reto_requerido`  → hay que pedir el 2º factor ahora (usuario con factor activo, no en un
                            terminal de confianza y no en contexto sin-MFA).
      · `obligatorio`     → la política (empresa/rol/suelo crítico) exige que el usuario tenga MFA.
      · `debe_enrolar`    → es obligatorio pero el usuario aún no tiene factor (prompt de alta; NO se
                            bloquea el acceso por API/UI para evitar lockout — enforcement gradual).
      · `confiable`/`activo`/`metodos`/`motivo` → contexto de la decisión.
    """
    from src.services.seguridad import mfa, mfa_politica
    uid = (usuario or {}).get("id")
    pol = mfa_politica.politica_efectiva(usuario, id_empresa=id_empresa, contexto=contexto)
    metodos = pol.get("metodos") or ["totp"]

    # Contexto NO humano / autoservicio (API/M2M, autocobro/kiosco): nunca reto ni obligación humana.
    if pol.get("modo") in mfa_politica.CONTEXTOS_SIN_MFA:
        return {"reto_requerido": False, "obligatorio": False, "debe_enrolar": False,
                "confiable": False, "activo": False, "metodos": metodos, "motivo": pol.get("modo")}

    try:
        activo = bool(mfa.mfa_activo(uid)) if uid else False
    except Exception:
        activo = False

    # Dispositivo de confianza (Fase 4): en ESE terminal no se re-pide el 2º factor.
    confiable = False
    if codigo_terminal:
        try:
            from src.services.seguridad import mfa_dispositivos
            confiable = mfa_dispositivos.es_de_confianza(uid, codigo_terminal, id_empresa)
        except Exception:
            confiable = False

    obligatorio = bool(pol.get("obligatorio"))
    return {"reto_requerido": bool(activo and not confiable),
            "obligatorio": obligatorio,
            "debe_enrolar": bool(obligatorio and not activo),
            "confiable": confiable, "activo": activo, "metodos": metodos,
            "critico": bool(pol.get("critico")), "motivo": pol.get("modo")}
