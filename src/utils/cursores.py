"""
Cursores personalizados de la app (opt-in, DEGRADABLE).

Sustituye SOLO 3 formas estándar de cursor —flecha (Arrow), mano (PointingHand) y texto (I-beam)— por
imágenes propias en ``assets/cursores/``, dejando INTACTOS los demás estados (espera/cruz/redimensionar/
prohibido…). Si falta algún fichero (o Qt no puede cargarlo), ese estado usa el cursor del sistema, sin
romper nada.

Ficheros esperados (PNG con transparencia, ~24–32 px):
  · ``assets/cursores/arrow.png``   → flecha   · hotspot 0,0
  · ``assets/cursores/hand.png``    → mano      · hotspot en la punta del dedo (arriba)
  · ``assets/cursores/ibeam.png``   → texto     · hotspot centrado

Mecanismo: un event-filter en la ``QApplication`` remapea, cuando un widget fija uno de esos 3 cursores, el
cursor por el personalizado (los .png no llevan hotspot incorporado → se usa uno razonable por forma). La
flecha se fija además como cursor por DEFECTO de cada ventana (los hijos la heredan salvo que fijen el suyo).
"""

import logging
import os

logger = logging.getLogger("cursores")

_DIR = os.path.join("assets", "cursores")
# (nombres_aceptados, forma_estándar). Se usa el PRIMER fichero que exista de cada lista.
_FICHEROS = (
    (("arrow.png", "flecha.png"), "ArrowCursor"),
    (("hand.png", "pointer.png", "mano.png"), "PointingHandCursor"),
    (("ibeam.png", "texto.png", "cursor.png"), "IBeamCursor"),
    (("openhand.png", "open hand.png", "open_hand.png", "grab.png", "mano_abierta.png"),
     "OpenHandCursor"),
    (("closedhand.png", "close hand.png", "closed hand.png", "closed_hand.png", "fist.png", "puno.png"),
     "ClosedHandCursor"),
)
_MAX_PX = 32   # tamaño de cursor estándar; los PNG más grandes se reducen a este (proporcionalmente)


def _hotspot(forma, pm):
    w, h = pm.width(), pm.height()
    if forma == "ArrowCursor":
        return 0, 0
    if forma == "PointingHandCursor":
        return int(w * 0.35), 0          # punta del dedo (arriba, algo a la izquierda)
    return w // 2, h // 2                  # I-beam (y cualquier otro): centrado


def _cargar():
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QCursor, QPixmap
    mapa = {}
    for nombres, forma in _FICHEROS:
        ruta = next((os.path.join(_DIR, n) for n in nombres
                     if os.path.exists(os.path.join(_DIR, n))), None)
        if ruta is None:
            continue
        pm = QPixmap(ruta)
        if pm.isNull():
            logger.debug("Cursor no cargable: %s", ruta)
            continue
        # Reduce a tamaño de cursor estándar si el PNG es grande (se ve proporcionado en pantalla).
        if max(pm.width(), pm.height()) > _MAX_PX:
            pm = pm.scaled(_MAX_PX, _MAX_PX, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        hx, hy = _hotspot(forma, pm)   # hotspot calculado sobre el tamaño final
        mapa[getattr(Qt.CursorShape, forma)] = QCursor(pm, hx, hy)
    return mapa


def instalar(app):
    """Instala el override de cursores en la QApplication. Devuelve el filtro (o None si no hay ficheros)."""
    if app is None:
        return None
    try:
        mapa = _cargar()
    except Exception as e:
        logger.debug("cursores._cargar: %s", e)
        return None
    if not mapa:
        logger.info("Cursores personalizados: sin ficheros en %s (se usan los del sistema).", _DIR)
        return None

    from PyQt6.QtCore import QEvent, QObject, Qt
    from PyQt6.QtWidgets import QWidget

    flecha = mapa.get(Qt.CursorShape.ArrowCursor)

    class _Remapeador(QObject):
        def __init__(self):
            super().__init__()
            self._reentrante = False

        def eventFilter(self, obj, ev):  # noqa: N802 (API Qt)
            t = ev.type()
            if self._reentrante or not isinstance(obj, QWidget):
                return False
            try:
                if t == QEvent.Type.CursorChange:
                    nuevo = mapa.get(obj.cursor().shape())
                    if nuevo is not None:
                        self._reentrante = True
                        obj.setCursor(nuevo)
                        self._reentrante = False
                elif t == QEvent.Type.Show and flecha is not None and obj.isWindow():
                    # Flecha personalizada como cursor por defecto de cada ventana nueva.
                    if obj.cursor().shape() == Qt.CursorShape.ArrowCursor:
                        self._reentrante = True
                        obj.setCursor(flecha)
                        self._reentrante = False
            except Exception:
                self._reentrante = False
            return False

    rem = _Remapeador()
    app.installEventFilter(rem)
    app._remapeador_cursores = rem   # evita el GC del filtro
    if flecha is not None:
        for w in app.topLevelWidgets():
            try:
                if w.cursor().shape() == Qt.CursorShape.ArrowCursor:
                    w.setCursor(flecha)
            except Exception:
                pass
    logger.info("Cursores personalizados instalados: %s", [k.name for k in mapa])
    return rem
