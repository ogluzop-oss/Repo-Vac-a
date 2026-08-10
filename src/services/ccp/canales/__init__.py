"""
Registro de canales de la CCP. Los canales se registran aquí (Email operativo desde el inicio; los
preparados se registran al importar `preparados`). Añadir un canal real futuro = registrar su clase.
"""

from src.services.ccp.canales.base import CanalComunicacion, CanalPreparado  # noqa: F401
from src.services.ccp.canales.email import EmailChannel

_REGISTRO: dict = {}


def registrar_canal(canal: CanalComunicacion):
    if not getattr(canal, "clave", None):
        raise ValueError("El canal debe tener 'clave'.")
    _REGISTRO[canal.clave] = canal
    return canal


def canal(clave):
    return _REGISTRO.get(clave)


def canales() -> list:
    return list(_REGISTRO.values())


def canales_operativos() -> list:
    return [c for c in _REGISTRO.values() if c.disponible()]


# Email = único canal operativo en esta fase.
registrar_canal(EmailChannel())

# Canales OMNICANAL degradables (B8): reales si hay credenciales, si no `no_operativo`. Import
# diferido para registrar sin acoplar el núcleo.
try:
    from src.services.ccp.canales import omnichannel as _omni  # noqa: F401
except Exception:
    pass
