"""Interruptor de despliegue del Portal de proveedor (DEGRADABLE).

El portal se construye COMPLETO y probado, pero el enlace remoto en vivo NO se despliega hasta el día de
producción (evitar costes). Mientras `portal_activo()` sea False, la empresa opera en local (la base de
datos compartida ya funciona); el día de producción se activa con la variable de entorno
`PORTAL_PROVEEDOR_LIVE=1` (o desde configuración), sin tocar código.
"""

import os

_VERDADERO = ("1", "true", "si", "sí", "yes", "on")


def portal_activo(id_empresa=None) -> bool:
    """¿Está DESPLEGADO el enlace remoto en vivo? Por defecto False (preparado, no desplegado)."""
    return str(os.getenv("PORTAL_PROVEEDOR_LIVE", "")).strip().lower() in _VERDADERO


def modo() -> str:
    """'en_vivo' si el enlace remoto está desplegado, 'local' (preparado) en caso contrario."""
    return "en_vivo" if portal_activo() else "local"
