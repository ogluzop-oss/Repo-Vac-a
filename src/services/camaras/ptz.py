"""
Control PTZ (pan / tilt / zoom) vía ONVIF — DEGRADABLE y HONESTO.

Real SOLO si la librería `onvif` (onvif-zeep) está instalada Y la cámara expone el servicio PTZ. Si no,
`capacidades`/`mover` informan 'no disponible' y NUNCA fingen un movimiento. Las credenciales se obtienen
descifradas de la fuente de la cámara (`registro.fuente_efectiva`), nunca en claro desde la BD.
"""

import logging
from urllib.parse import urlparse

logger = logging.getLogger("camaras.ptz")

# dirección → (pan, tilt, zoom) unitario
DIRECCIONES = {
    "izquierda": (-1.0, 0.0, 0.0), "derecha": (1.0, 0.0, 0.0),
    "arriba": (0.0, 1.0, 0.0), "abajo": (0.0, -1.0, 0.0),
    "zoom_in": (0.0, 0.0, 1.0), "zoom_out": (0.0, 0.0, -1.0),
}


def _onvif_disponible() -> bool:
    try:
        import onvif  # noqa: F401
        return True
    except Exception:
        return False


def disponible() -> bool:
    """True si la librería ONVIF está instalada (chequeo BARATO, sin conexión de red). Útil para la GUI:
    habilitar/deshabilitar los controles PTZ sin bloquear la interfaz sondeando la cámara."""
    return _onvif_disponible()


def _conexion(camara):
    """(host, usuario, contraseña, puerto) a partir de la fuente REAL descifrada de la cámara."""
    try:
        from src.services.camaras.registro import fuente_efectiva
        u = urlparse(fuente_efectiva(camara) or "")
        return u.hostname, (u.username or ""), (u.password or ""), 80
    except Exception:
        return None, "", "", 80


def capacidades(camara) -> dict:
    """Qué soporta realmente: {'onvif': bool, 'ptz': bool, 'motivo': str}. Honesto: sin librería o sin
    soporte real → False (no se simula)."""
    if not _onvif_disponible():
        return {"onvif": False, "ptz": False, "motivo": "librería ONVIF no instalada (onvif-zeep)"}
    host, user, pwd, puerto = _conexion(camara)
    if not host:
        return {"onvif": True, "ptz": False, "motivo": "cámara sin host/credenciales ONVIF"}
    try:
        from onvif import ONVIFCamera
        cam = ONVIFCamera(host, puerto, user, pwd)
        cam.create_ptz_service()
        return {"onvif": True, "ptz": True, "motivo": "ok"}
    except Exception as e:
        return {"onvif": True, "ptz": False, "motivo": f"sin PTZ: {e}"}


def mover(camara, direccion, *, velocidad=0.5, segundos=0.5) -> dict:
    """Mueve la cámara (movimiento continuo + parada). Devuelve {'ok': bool, 'motivo': str}. Degradable:
    si no hay ONVIF/soporte, `ok=False` con el motivo real, sin fingir el movimiento."""
    if direccion not in DIRECCIONES:
        return {"ok": False, "motivo": "dirección no válida"}
    if not _onvif_disponible():
        return {"ok": False, "motivo": "ONVIF no disponible (instala 'onvif-zeep')"}
    host, user, pwd, puerto = _conexion(camara)
    if not host:
        return {"ok": False, "motivo": "cámara sin host/credenciales ONVIF"}
    try:
        import time

        from onvif import ONVIFCamera
        cam = ONVIFCamera(host, puerto, user, pwd)
        media = cam.create_media_service()
        ptz = cam.create_ptz_service()
        token = media.GetProfiles()[0].token
        x, y, z = DIRECCIONES[direccion]
        req = ptz.create_type("ContinuousMove")
        req.ProfileToken = token
        req.Velocity = {"PanTilt": {"x": x * velocidad, "y": y * velocidad}, "Zoom": {"x": z * velocidad}}
        ptz.ContinuousMove(req)
        time.sleep(max(0.1, float(segundos)))
        ptz.Stop({"ProfileToken": token})
        return {"ok": True, "motivo": "ok"}
    except Exception as e:
        logger.debug("ptz.mover(%s): %s", direccion, e)
        return {"ok": False, "motivo": f"error ONVIF: {e}"}
