"""
Plantillas corporativas de la CCP (Parte H) — envoltorio evolutivo, no sustituto.

Reutiliza el sistema existente `src.services.plantillas_correo` (variables {{...}}, multiempresa) y deja
GANCHOS preparados para firma, logotipo y pie legal por empresa/idioma. Hoy `render` delega en el
sistema actual; los ganchos son no-op ampliables sin romper nada.
"""

import logging

logger = logging.getLogger("ccp.plantillas")

# Ganchos de decoración (firma/logo/pie). Preparados; hoy no modifican el cuerpo.
_DECORADORES: list = []


def registrar_decorador(fn):
    """Registra un decorador `fn(asunto, cuerpo, *, id_empresa, idioma) -> (asunto, cuerpo)` para
    firma/logo/pie corporativo. Punto de extensión (Parte H). Ninguno activo por defecto."""
    _DECORADORES.append(fn)
    return fn


def render(codigo, variables=None, *, id_empresa=None, idioma=None):
    """Devuelve (asunto, cuerpo) de una plantilla corporativa con variables sustituidas, aplicando los
    decoradores registrados (firma/logo/pie). None si la plantilla no existe."""
    try:
        from src.services import plantillas_correo as _pl
        r = _pl.render(codigo, variables or {}, id_empresa)
    except Exception as e:
        logger.debug("render plantilla %s: %s", codigo, e)
        r = None
    if not r:
        return None
    asunto, cuerpo = r
    for fn in _DECORADORES:
        try:
            asunto, cuerpo = fn(asunto, cuerpo, id_empresa=id_empresa, idioma=idioma)
        except Exception as e:
            logger.debug("decorador plantilla: %s", e)
    return asunto, cuerpo
