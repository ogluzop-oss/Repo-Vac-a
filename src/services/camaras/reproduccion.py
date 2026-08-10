"""
Reproducción de grabaciones (videovigilancia) — localización, fechas disponibles y extracción de clips.

SOLO lectura. Aislamiento por empresa+departamento (SUPERADMIN puede cruzar con `permitir_super`). El
clip (tipo "clip de Twitch") se extrae con OpenCV (rango de frames → mp4). API-First (sin PyQt).
"""

import datetime as _dt
import logging
import os

from src.db.conexion import _fila_a_dict, _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("camaras.reproduccion")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def grabacion_de(id_camara, fecha, *, id_empresa=None, permitir_super=False) -> dict | None:
    """Grabación de una cámara en una fecha. Aislada por empresa salvo SUPERADMIN."""
    id_empresa = _emp(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            if permitir_super:
                cur.execute("SELECT * FROM camaras_grabaciones WHERE id_camara=%s AND fecha=%s",
                            (id_camara, fecha))
            else:
                cur.execute("SELECT * FROM camaras_grabaciones WHERE id_camara=%s AND fecha=%s AND "
                            "id_empresa=%s", (id_camara, fecha, id_empresa))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.debug("grabacion_de: %s", e)
        return None


def fechas_disponibles(id_camara, *, id_empresa=None, permitir_super=False, limite=365) -> list:
    """Fechas con grabación de una cámara (para el filtro de días anteriores)."""
    id_empresa = _emp(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            if permitir_super:
                cur.execute("SELECT fecha FROM camaras_grabaciones WHERE id_camara=%s ORDER BY fecha "
                            "DESC LIMIT %s", (id_camara, int(limite)))
            else:
                cur.execute("SELECT fecha FROM camaras_grabaciones WHERE id_camara=%s AND id_empresa=%s "
                            "ORDER BY fecha DESC LIMIT %s", (id_camara, id_empresa, int(limite)))
            return [str(r.get("fecha")) for r in _filas_a_dicts(cur, cur.fetchall())]
    except Exception as e:
        logger.debug("fechas_disponibles: %s", e)
        return []


def extraer_clip(id_camara, fecha, *, inicio_seg, fin_seg, id_empresa=None, permitir_super=False,
                 destino=None) -> str | None:
    """Extrae un clip [inicio_seg, fin_seg] de la grabación del día → nuevo mp4. Devuelve la ruta."""
    grab = grabacion_de(id_camara, fecha, id_empresa=id_empresa, permitir_super=permitir_super)
    if not grab or not grab.get("ruta") or not os.path.exists(grab["ruta"]):
        return None
    try:
        import cv2
    except Exception:
        return None
    origen = grab["ruta"]
    cap = cv2.VideoCapture(origen)
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 4
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 320)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 240)
    if not destino:
        carpeta = os.path.join(os.path.dirname(origen), "clips")
        os.makedirs(carpeta, exist_ok=True)
        marca = _dt.datetime.now().strftime("%H%M%S")
        destino = os.path.join(carpeta, f"clip_{fecha}_{int(inicio_seg)}-{int(fin_seg)}_{marca}.mp4")
    writer = cv2.VideoWriter(destino, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    f_ini, f_fin = int(inicio_seg * fps), int(fin_seg * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, f_ini))
    n = 0
    while n < (f_fin - f_ini):
        ok, frame = cap.read()
        if not ok:
            break
        writer.write(frame); n += 1
    writer.release(); cap.release()
    # Los clips también se registran en Documentos (grabacion).
    try:
        from src.db.documentos import registrar_documento
        registrar_documento(destino, tipo="grabacion", nombre=os.path.basename(destino),
                            referencia=str(fecha), id_empresa=grab.get("id_empresa"))
    except Exception:
        pass
    return destino if n > 0 else None
