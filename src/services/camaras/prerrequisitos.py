"""
Prerrequisitos de sistema de Videovigilancia (`ffmpeg` binario + `onvif-zeep` pip) — chequeo barato
para que la GUI muestre un aviso VISIBLE si falta algo, en vez de degradar en silencio. No duplica la
detección: reutiliza los mismos checks que ya usan `grabacion.py`/`ptz.py`.
"""


def estado() -> dict:
    """{'ffmpeg': bool, 'onvif': bool} — disponibilidad real de cada prerrequisito opcional."""
    try:
        from src.services.camaras.grabacion import _ffmpeg_disponible
        ffmpeg = _ffmpeg_disponible()
    except Exception:
        ffmpeg = False
    try:
        from src.services.camaras.ptz import _onvif_disponible
        onvif = _onvif_disponible()
    except Exception:
        onvif = False
    return {"ffmpeg": ffmpeg, "onvif": onvif}


_INSTRUCCIONES = {
    "ffmpeg": (
        "FFmpeg no está instalado (o no está en el PATH). La grabación seguirá funcionando con un "
        "motor alternativo (más uso de CPU). Para el motor de producción: winget install ffmpeg "
        "(Windows) o apt install ffmpeg (Linux)."
    ),
    "onvif": (
        "La librería ONVIF (onvif-zeep) no está instalada. El descubrimiento automático, los "
        "perfiles mainstream/substream y el control PTZ no están disponibles — puedes seguir dando "
        "de alta cámaras manualmente. Para activarlo: pip install onvif-zeep."
    ),
}


def instrucciones(clave) -> str:
    return _INSTRUCCIONES.get(clave, "")


def avisos_pendientes() -> list:
    """Lista de textos de aviso (uno por prerrequisito ausente), lista para pintar en la GUI."""
    st = estado()
    return [instrucciones(k) for k, ok in st.items() if not ok]
