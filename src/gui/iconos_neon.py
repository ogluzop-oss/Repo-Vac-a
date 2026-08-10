"""
Iconos neón reutilizables de la app. `icono_mas` dibuja el '+' turquesa (recuadro redondeado + signo más)
y `BotonMas` es un QPushButton cuyo icono se OSCURECE al pasar el ratón (para no perderse sobre el hover
cian de los botones de acento). Único punto de verdad del icono '+' (lo usan Artículos y Etiquetas).
"""

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QPushButton

_CIAN = "#00FFC6"


def icono_mas(px=20, color=_CIAN):
    """Icono '+' estilo neón: dos pasadas (halo translúcido + trazo nítido) para dar el brillo."""
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    m = px * 0.12          # margen exterior
    rad = px * 0.26        # radio de esquinas del recuadro
    cx = px / 2.0
    brazo = px * 0.20      # medio-largo de cada brazo del '+'
    for ancho, alpha in ((3.2, 70), (1.7, 255)):
        col = QColor(color); col.setAlpha(alpha)
        pen = QPen(col); pen.setWidthF(ancho)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawRoundedRect(QRectF(m, m, px - 2 * m, px - 2 * m), rad, rad)
        p.drawLine(QPointF(cx - brazo, cx), QPointF(cx + brazo, cx))
        p.drawLine(QPointF(cx, cx - brazo), QPointF(cx, cx + brazo))
    p.end()
    return QIcon(pm)


class BotonMas(QPushButton):
    """Botón con icono '+' neón que se oscurece al pasar el ratón."""

    def __init__(self, text, parent=None, px=20):
        super().__init__(text, parent)
        self._px = px
        self._ic_norm = icono_mas(px, _CIAN)
        self._ic_hover = icono_mas(px, "#0E1117")
        self.setIcon(self._ic_norm)
        self.setIconSize(QSize(px, px))

    def enterEvent(self, e):
        self.setIcon(self._ic_hover)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.setIcon(self._ic_norm)
        super().leaveEvent(e)
