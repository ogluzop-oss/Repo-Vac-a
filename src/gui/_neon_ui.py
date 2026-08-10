"""
Primitivas visuales "neón" compartidas (paleta + helpers de estilo) extraídas de `gui/tpv.py`.

Son PRESENTACIÓN (no lógica de negocio): copiadas literalmente de tpv.py para que los módulos extraídos
por Strangler (Canal Web, Portal Web) reutilicen el mismo look&feel SIN importar `gui.tpv` (evita el
acoplamiento privado). No añade comportamiento nuevo; es un simple hogar común para estas utilidades.
"""

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QBitmap, QPainter, QRegion
from PyQt6.QtWidgets import QFrame, QLabel, QPushButton

# ── Paleta / tipografía (idéntica a tpv.py) ──
_BG = "#0E1117"
_BG2 = "#161B22"
_CIAN = "#00FFC6"
_ROJO = "#FF4C4C"
_VERDE = "#3FB950"
_AMBAR = "#F1C40F"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_TEXT2 = "#8B949E"
_FONT = "Segoe UI"


def _lbl(text: str, bold: bool = False, size: int = 12, color: str = _TEXT) -> QLabel:
    lb = QLabel(text)
    lb.setStyleSheet(
        f"color:{color};font-family:'{_FONT}';font-size:{size}px;"
        f"font-weight:{'900' if bold else '500'};background:transparent;border:none;"
    )
    return lb


def _btn(
    text: str,
    color_bg: str = _BG2,
    color_fg: str = _TEXT,
    color_border: str = _BORDE,
    hover_bg: str = _CIAN,
    hover_fg: str = "#0D1117",
    h: int = 38,
    radius: int = 10,
) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(h)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(
        f"QPushButton{{background:{color_bg};color:{color_fg};"
        f"border:2px solid {color_border};border-radius:{radius}px;"
        f"font-family:'{_FONT}';font-weight:900;font-size:13px;padding:0 12px;outline:0;}}"
        f"QPushButton:hover{{background:{hover_bg};color:{hover_fg};}}"
        f"QPushButton:focus{{outline:0;}}"
    )
    return b


def _card() -> QFrame:
    f = QFrame()
    f.setStyleSheet(
        f"QFrame{{background:{_BG2};border:1px solid {_BORDE};" f"border-radius:14px;}}"
    )
    return f


def _sep() -> QFrame:
    s = QFrame()
    s.setFrameShape(QFrame.Shape.HLine)
    s.setStyleSheet(
        f"QFrame{{color:{_BORDE};background:{_BORDE};max-height:1px;border:none;}}"
    )
    s.setFixedHeight(1)
    return s


class _RoundTableCorners(QObject):
    """Redondea las esquinas exteriores de un QTableWidget con una máscara: las 4
    del widget y, además, las superiores de la cabecera (para que el contorno
    neón no se corte arriba)."""

    def __init__(self, table, radius=10):
        super().__init__(table)
        self._r = radius
        self._table = table
        table.installEventFilter(self)
        table.horizontalHeader().installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show) and obj.width() > 0:
            from PyQt6.QtCore import QRect

            if obj is self._table:
                rect = QRect(0, 0, obj.width(), obj.height())  # 4 esquinas
            else:  # cabecera: redondear solo arriba (extiende el rect por abajo)
                rect = QRect(0, 0, obj.width(), obj.height() + self._r)
            bmp = QBitmap(obj.size())
            bmp.fill(Qt.GlobalColor.color0)
            p = QPainter(bmp)
            p.setBrush(Qt.GlobalColor.color1)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, self._r, self._r)
            p.end()
            obj.setMask(QRegion(bmp))
        return False


class _RoundWidgetCorners(QObject):
    """Enmascara las 4 esquinas de un widget a un rect REDONDEADO (setMask) para que su contenido, la
    SELECCIÓN y la SCROLLBAR no sobresalgan del borde. Para QListWidget/QFrame (sin cabecera)."""

    def __init__(self, widget, radius=10):
        super().__init__(widget)
        self._r = radius
        self._w = widget
        widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show) and obj.width() > 0:
            from PyQt6.QtCore import QRect
            bmp = QBitmap(obj.size())
            bmp.fill(Qt.GlobalColor.color0)
            p = QPainter(bmp)
            p.setBrush(Qt.GlobalColor.color1)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRect(0, 0, obj.width(), obj.height()), self._r, self._r)
            p.end()
            obj.setMask(QRegion(bmp))
        return False


def _ss_lista_neon() -> str:
    """Estilo de QListWidget con contorno neón, filas de esquinas REDONDEADAS (la selección/hover no
    sobresalen) y hover swap por fila."""
    return (
        f"QListWidget{{background:{_BG};color:{_TEXT};border:2px solid {_CIAN};border-radius:10px;"
        f"font-family:'{_FONT}';font-size:12px;outline:0;padding:4px;}}"
        f"QListWidget::item{{padding:8px 10px;border-radius:8px;margin:2px;}}"
        f"QListWidget::item:selected{{background:rgba(0,255,198,0.18);color:{_CIAN};}}"
        f"QListWidget::item:hover{{background:rgba(0,255,198,0.10);color:{_CIAN};}}"
        + _ss_scroll_neon()
    )


def _ss_scroll_neon() -> str:
    """Scrollbars finas, con MARGEN (no tocan las esquinas redondeadas ni el borde neón → el contorno NO se
    corta) y asa redondeada. Se anexa al estilo de tablas/listas."""
    return (
        f"QScrollBar:vertical{{background:transparent;width:12px;margin:8px 4px 8px 0;border:none;}}"
        f"QScrollBar::handle:vertical{{background:rgba(0,255,198,0.35);border-radius:5px;min-height:26px;}}"
        f"QScrollBar::handle:vertical:hover{{background:{_CIAN};}}"
        f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;background:none;border:none;}}"
        f"QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{{background:none;}}"
        f"QScrollBar:horizontal{{background:transparent;height:12px;margin:0 8px 4px 8px;border:none;}}"
        f"QScrollBar::handle:horizontal{{background:rgba(0,255,198,0.35);border-radius:5px;min-width:26px;}}"
        f"QScrollBar::handle:horizontal:hover{{background:{_CIAN};}}"
        f"QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{{width:0;background:none;border:none;}}"
        f"QScrollBar::add-page:horizontal,QScrollBar::sub-page:horizontal{{background:none;}}"
    )


def _ss_tabla_neon() -> str:
    """Estilo de tabla con contorno neón, cabeceras redondeadas, hover swap y scrollbars que no cortan el borde."""
    return (
        f"QTableWidget{{background:{_BG};color:{_TEXT};border:2px solid {_CIAN};"
        f"border-radius:10px;gridline-color:{_BORDE};font-family:'{_FONT}';font-size:12px;"
        f"selection-background-color:rgba(0,255,198,0.18);selection-color:{_CIAN};}}"
        f"QTableWidget::item{{padding:6px 10px;}}"
        f"QTableWidget::item:alternate{{background:#0B0F14;}}"
        f"QHeaderView::section{{background:{_BG2};color:{_CIAN};border:none;"
        f"border-bottom:2px solid {_CIAN};padding:9px 8px;font-weight:900;font-family:'{_FONT}';}}"
        f"QHeaderView::section:first{{border-top-left-radius:8px;}}"
        f"QHeaderView::section:last{{border-top-right-radius:8px;}}"
        f"QHeaderView::section:hover{{background:{_CIAN};color:#0D1117;}}"
        + _ss_scroll_neon()
    )
