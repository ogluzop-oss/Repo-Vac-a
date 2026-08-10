"""
Registro de transportes (Fase 4, SUBFASE 4.1). Permite seleccionar el transporte por nombre
(local/LAN/VPN/Internet/Cloud/Edge). Por defecto se registra el transporte LOCAL. Los demas se
añadiran registrando su implementacion del contrato `Transporte` — sin tocar el motor.
"""

import logging

logger = logging.getLogger("sync_transport.registry")

_TRANSPORTES = {}


def registrar(transporte) -> None:
    _TRANSPORTES[transporte.nombre] = transporte


def obtener(nombre="local"):
    return _TRANSPORTES.get(nombre) or _TRANSPORTES.get("local")


def disponibles() -> list:
    return sorted(_TRANSPORTES.keys())


# Alta del transporte por defecto.
try:
    from src.services.sync_transport.local import LocalLoopback
    registrar(LocalLoopback())
except Exception as e:  # pragma: no cover
    logger.warning("registro transporte local: %s", e)
