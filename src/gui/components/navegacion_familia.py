"""
Navegación "siguiente/anterior artículo de la misma familia" — SOLO en el módulo "Info artículo"
(petición explícita: "estos botones tan solo deben estar disponibles en las búsquedas realizadas en
el módulo info artículo" — no en el resto de barras de búsqueda de la app).

Reutiliza el motor YA EXISTENTE de familias (`db.familias.familia_de_articulo`/
`articulos_de_familia`) — "familia" aquí es `articulos.id_familia`/`familias_producto` (el
vocabulario GLOBAL de familia de producto), NO las subfamilias de venta a granel
(`familias_granel`), que son un concepto distinto y no relacionado.

Uso (código) — se AÑADE junto al panel de detalle de artículo de "Info artículo":

    from src.gui.components.navegacion_familia import NavegadorFamiliaArticulo
    self.nav_familia = NavegadorFamiliaArticulo(on_navegar=self._mostrar_articulo_por_codigo)
    layout.addWidget(self.nav_familia)
    ...
    # tras cada búsqueda que encuentre un artículo con éxito:
    self.nav_familia.establecer(codigo_encontrado)

`on_navegar(codigo)` se llama cuando el usuario pulsa una flecha — el propio llamador decide cómo
mostrar ese artículo (reutiliza normalmente el mismo método que ya usa para renderizar el
resultado de una búsqueda manual).

Las flechas se pintan A MANO (dos trazos, centrados por geometría pura) en vez de usar un glifo de
texto "◀"/"▶": el centrado por fuente/CSS de esos caracteres no es fiable (mismo motivo ya resuelto
para el botón ✕ de cierre — ver `gui/tpv.py::_BotonCerrarX`). Siempre VISIBLES tras una búsqueda
(aunque la familia tenga un solo artículo, en cuyo caso aparecen deshabilitadas con "1 / 1") para
que el control sea descubrible — ocultarlas del todo hacía parecer que la función no existía.
"""

import logging

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

try:
    from assets.estilo_global import COLOR_CIAN, COLOR_TEXTO_SECUNDARIO, _blindar_tamano_fijo
except Exception:  # pragma: no cover
    COLOR_CIAN = "#00FFC6"
    COLOR_TEXTO_SECUNDARIO = "#8B949E"
    _blindar_tamano_fijo = None

logger = logging.getLogger("gui.navegacion_familia")


class _BotonFlecha(QPushButton):
    """Botón circular con una flecha pintada a mano (dos trazos en V, centrados por geometría
    pura) — `sentido=-1` apunta a la izquierda, `sentido=1` a la derecha. Mismo criterio de
    centrado exacto que `_BotonCerrarX` (gui/tpv.py)."""

    def __init__(self, sentido: int, size: int = 34, parent=None):
        super().__init__(parent)
        self._sentido = sentido
        self._size = size
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QPushButton{{background:transparent;border:2px solid {COLOR_CIAN};"
            f"border-radius:{size // 2}px;padding:0;}}"
            f"QPushButton:hover:enabled{{background:{COLOR_CIAN};}}"
            f"QPushButton:disabled{{border-color:{COLOR_TEXTO_SECUNDARIO};}}"
        )
        if _blindar_tamano_fijo:
            _blindar_tamano_fijo(self, size, size)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self.isEnabled():
            color = QColor(COLOR_TEXTO_SECUNDARIO)
        elif self.underMouse():
            color = QColor("#0D1117")
        else:
            color = QColor(COLOR_CIAN)
        pen = QPen(color)
        pen.setWidthF(max(1.6, self._size * 0.09))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        cx, cy = self._size / 2, self._size / 2
        half = self._size * 0.17
        tip_x = cx + (half * 0.9 * self._sentido)
        back_x = cx - (half * 0.9 * self._sentido)
        p.drawLine(QPointF(back_x, cy - half), QPointF(tip_x, cy))
        p.drawLine(QPointF(tip_x, cy), QPointF(back_x, cy + half))
        p.end()


class NavegadorFamiliaArticulo(QWidget):
    """Flechas + contador "2 / 7". Siempre visible tras `establecer()`; deshabilitadas (pero
    visibles) cuando el artículo no tiene familia o su familia tiene un único artículo."""

    def __init__(self, on_navegar, parent=None):
        super().__init__(parent)
        self._on_navegar = on_navegar
        self._codigos: list[str] = []
        self._idx = -1

        ly = QHBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(10)

        self.btn_izq = _BotonFlecha(-1)
        self.btn_izq.setToolTip("Artículo anterior de la misma familia")
        self.btn_izq.clicked.connect(lambda: self._mover(-1))

        self.lbl_pos = QLabel("")
        self.lbl_pos.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_pos.setStyleSheet(
            f"color:{COLOR_TEXTO_SECUNDARIO};font-weight:700;font-size:11px;background:transparent;border:none;")
        self.lbl_pos.setMinimumWidth(50)

        self.btn_der = _BotonFlecha(1)
        self.btn_der.setToolTip("Siguiente artículo de la misma familia")
        self.btn_der.clicked.connect(lambda: self._mover(1))

        ly.addWidget(self.btn_izq)
        ly.addWidget(self.lbl_pos)
        ly.addWidget(self.btn_der)
        self.hide()  # oculto SOLO hasta la primera búsqueda; luego permanece visible

    def establecer(self, codigo_articulo: str, id_empresa=None) -> None:
        """Recalcula los "hermanos" de familia de `codigo_articulo` y reinicia la posición sobre
        él. Siempre se MUESTRA (deshabilitada si no hay más de un artículo en la familia) para que
        el control sea descubrible — antes se ocultaba del todo y parecía que no existía."""
        codigo_articulo = str(codigo_articulo or "").strip()
        self._codigos = []
        self._idx = -1
        if not codigo_articulo:
            self.hide()
            return
        try:
            from src.db import familias as F
            fam = F.familia_de_articulo(codigo_articulo, id_empresa=id_empresa)
            if fam:
                hermanos = F.articulos_de_familia(fam["id"], id_empresa=id_empresa)
                self._codigos = [h["codigo"] for h in hermanos]
        except Exception as e:
            logger.debug("NavegadorFamiliaArticulo.establecer: %s", e)
            self._codigos = []
        if codigo_articulo not in self._codigos:
            self._codigos.append(codigo_articulo)
        try:
            self._idx = self._codigos.index(codigo_articulo)
        except ValueError:
            self._idx = 0
        self.show()
        self._actualizar()

    def limpiar(self) -> None:
        self._codigos = []
        self._idx = -1
        self.hide()

    def _mover(self, delta: int) -> None:
        if len(self._codigos) < 2:
            return
        self._idx = (self._idx + delta) % len(self._codigos)
        self._actualizar()
        if self._on_navegar:
            self._on_navegar(self._codigos[self._idx])

    def _actualizar(self) -> None:
        n = len(self._codigos)
        self.lbl_pos.setText(f"{self._idx + 1} / {n}" if n else "")
        activo = n > 1
        self.btn_izq.setEnabled(activo)
        self.btn_der.setEnabled(activo)
