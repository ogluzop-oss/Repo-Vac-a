"""
Detección de movimiento (videovigilancia) — análisis OpenCV REAL por diferencia de fotogramas. €0, sin
hardware ni servicios de pago. Genera EVENTOS con AISLAMIENTO ESTRICTO por empresa + departamento
(`camaras_eventos`). Honestidad: si no hay OpenCV o no hay fotogramas reales, NO inventa eventos.
"""

import datetime as _dt
import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("camaras.deteccion")

UMBRAL_INTENSIDAD = 25       # diferencia de gris (0-255) para considerar que un píxel cambió
AREA_MIN_RATIO = 0.015       # fracción del fotograma que debe cambiar para contar como movimiento
COOLDOWN_SEG = 10            # antirrebote: como máximo 1 evento cada N s por cámara


class DetectorMovimiento:
    """Detector CON ESTADO (guarda el fotograma anterior). `procesar(frame)` devuelve la fracción de imagen
    que cambió (0.0-1.0); el llamador compara con `area_min_ratio`. Diferencia de fotogramas en gris + blur +
    umbral. Determinista y testeable; NO depende de red ni hardware."""

    def __init__(self, umbral=UMBRAL_INTENSIDAD, area_min_ratio=AREA_MIN_RATIO):
        self.umbral = umbral
        self.area_min_ratio = area_min_ratio
        self._prev = None

    def procesar(self, frame) -> float:
        try:
            import cv2
        except Exception:
            return 0.0
        if frame is None:
            return 0.0
        try:
            gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gris = cv2.GaussianBlur(gris, (21, 21), 0)
        except Exception:
            return 0.0
        if self._prev is None or self._prev.shape != gris.shape:
            self._prev = gris
            return 0.0
        delta = cv2.absdiff(self._prev, gris)
        self._prev = gris
        _, umbralizado = cv2.threshold(delta, self.umbral, 255, cv2.THRESH_BINARY)
        cambiados = cv2.countNonZero(umbralizado)
        total = umbralizado.shape[0] * umbralizado.shape[1] or 1
        return cambiados / total

    def hay_movimiento(self, frame) -> bool:
        return self.procesar(frame) >= self.area_min_ratio


def analizar_grabacion(ruta, *, umbral=UMBRAL_INTENSIDAD, area_min_ratio=AREA_MIN_RATIO,
                       cooldown_seg=COOLDOWN_SEG) -> list:
    """Analiza un fichero de grabación y devuelve los instantes (segundos desde el inicio) con movimiento.
    Post-proceso REAL para la ruta de producción (FFmpeg stream-copy no decodifica en vivo). Vídeo estático →
    lista vacía (no fabrica eventos)."""
    try:
        import cv2
    except Exception:
        return []
    cap = cv2.VideoCapture(str(ruta))
    if not cap or not cap.isOpened():
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    fps = fps if 1.0 <= fps <= 120.0 else 25.0
    det = DetectorMovimiento(umbral=umbral, area_min_ratio=area_min_ratio)
    eventos, idx, ultimo = [], 0, -1e9
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            score = det.procesar(frame)
            t = idx / fps
            if score >= area_min_ratio and (t - ultimo) >= cooldown_seg:
                ultimo = t
                eventos.append({"instante_seg": round(t, 2), "score": round(score, 4)})
            idx += 1
    finally:
        cap.release()
    return eventos


def registrar_evento(camara, tipo="movimiento", *, instante=None, score=0.0, id_empresa=None) -> int | None:
    """Registra un evento de una cámara con AISLAMIENTO (id_empresa + id_centro de la propia cámara)."""
    id_empresa = id_empresa or (camara or {}).get("id_empresa")
    if not id_empresa:
        try:
            from src.db.empresa import empresa_actual_id
            id_empresa = empresa_actual_id()
        except Exception:
            id_empresa = None
    if not id_empresa:
        return None
    instante = instante or _dt.datetime.now()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO camaras_eventos (id_empresa, id_centro, id_camara, tipo, instante, "
                        "score, estado) VALUES (%s,%s,%s,%s,%s,%s,'nuevo')",
                        (id_empresa, str(camara.get("id_centro")), camara.get("id"), tipo, instante,
                         float(score or 0.0)))
            eid = cur.lastrowid
            conn.commit()
            return eid
    except Exception as e:
        logger.debug("registrar_evento: %s", e)
        return None


def listar_eventos(id_empresa=None, id_centro=None, *, id_camara=None, desde=None, hasta=None,
                   limite=200) -> list:
    """Eventos de UN departamento de UNA empresa (aislamiento estricto). Nunca cruza departamentos/empresas."""
    if not id_empresa:
        try:
            from src.db.empresa import empresa_actual_id
            id_empresa = empresa_actual_id()
        except Exception:
            id_empresa = None
    if not id_empresa or id_centro is None:
        return []
    q = "SELECT * FROM camaras_eventos WHERE id_empresa=%s AND id_centro=%s"
    p = [id_empresa, str(id_centro)]
    if id_camara is not None:
        q += " AND id_camara=%s"
        p.append(id_camara)
    if desde:
        q += " AND instante >= %s"
        p.append(desde)
    if hasta:
        q += " AND instante <= %s"
        p.append(hasta)
    q += " ORDER BY instante DESC, id DESC LIMIT %s"
    p.append(int(limite))
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, tuple(p))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("listar_eventos: %s", e)
        return []
