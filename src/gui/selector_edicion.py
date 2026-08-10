"""
Selector de EDICIÓN — pantalla de ONBOARDING (primera ejecución de la instalación).

Se muestra UNA vez, antes del selector de perfil / login, cuando la instalación aún no tiene edición
definida (`verticales.edicion_definida()` es False). Pregunta al negocio su tipo de comercio y persiste la
elección (`verticales.fijar_edicion`, JSON local per-install). A partir de ahí la app es "Smart Manager
<Edición>" y su menú/botones/datos se gatean por la edición. NO es por empresa (una instalación = una edición).

Si la edición viene por entorno (`SMART_MANAGER_EDITION`, override / aprovisionamiento SaaS) esta pantalla
NO aparece. Emite `edicion_elegida(codigo)` al elegir.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from src.services import verticales
from src.utils.i18n import tr

_BG = "#0E1117"
_CIAN = "#00FFC6"
_BORDE = "#30363D"
_DIM = "#8B949E"

# Descripción + emoji por edición (para las tarjetas de elección).
_TARJETAS = [
    ("SUPERMARKET", "🛒", "Alimentación, bebidas, frescos. Venta a granel y báscula."),
    ("RETAIL", "🏬", "Tienda general: electrónica, hogar, regalos."),
    ("PHARMACY", "💊", "Farmacia y parafarmacia. Recetas y dispensación."),
    ("TEXTIL", "👕", "Moda y calzado. Variantes por talla y color."),
    ("BAKERY", "🥖", "Panadería, pastelería y cafetería. Obrador diario."),
]


class _TarjetaEdicion(QFrame):
    """Tarjeta clicable de una edición (contenedor con QLabels que ajustan línea → el texto no se corta)."""

    clicada = pyqtSignal(str)

    def __init__(self, codigo, parent=None):
        super().__init__(parent)
        self._codigo = codigo
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.rect().contains(ev.position().toPoint()):
            self.clicada.emit(self._codigo)
        super().mouseReleaseEvent(ev)


class SelectorEdicionWindow(QWidget):
    """Onboarding de edición. `edicion_elegida` emite el código (SUPERMARKET/RETAIL/…)."""

    edicion_elegida = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel_raiz")
        self.setStyleSheet(f"background:{_BG};")
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 40, 48, 40)
        root.setSpacing(14)

        titulo = QLabel(tr("edicion.titulo", default="Bienvenido a Smart Manager"))
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titulo.setStyleSheet(f"color:{_CIAN};font-size:30px;font-weight:900;letter-spacing:1px;")
        root.addWidget(titulo)

        sub = QLabel(tr("edicion.subtitulo", default="¿Qué tipo de comercio gestionas?"))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color:{_DIM};font-size:16px;")
        root.addWidget(sub)

        nota = QLabel(tr("edicion.nota",
                         default="Esta elección adapta el programa a tu negocio. Se pregunta solo una vez."))
        nota.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nota.setStyleSheet(f"color:{_DIM};font-size:12px;")
        root.addWidget(nota)
        root.addSpacing(8)

        grid = QGridLayout()
        grid.setSpacing(18)
        grid.setContentsMargins(0, 0, 0, 0)
        for i, (codigo, emoji, desc) in enumerate(_TARJETAS):
            grid.addWidget(self._tarjeta(codigo, emoji, desc), i // 3, i % 3)
        cont = QWidget()
        cont.setLayout(grid)
        root.addWidget(cont, 1, Qt.AlignmentFlag.AlignCenter)
        root.addStretch()

    def _tarjeta(self, codigo, emoji, desc):
        nombre = verticales.nombre_edicion(vertical=codigo)  # "Smart Manager Bakery & Coffee"
        card = _TarjetaEdicion(codigo)
        card.setObjectName("card")
        card.setFixedSize(270, 210)
        card.clicada.connect(self._elegir)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)
        f_emoji = QFont(); f_emoji.setPointSize(22)
        f_nom = QFont(); f_nom.setPointSize(11); f_nom.setBold(True)

        l_emoji = QLabel(emoji); l_emoji.setFont(f_emoji)
        l_nom = QLabel(nombre); l_nom.setObjectName("nom"); l_nom.setFont(f_nom); l_nom.setWordWrap(True)
        l_desc = QLabel(desc); l_desc.setObjectName("desc"); l_desc.setFont(f_nom); l_desc.setWordWrap(True)
        for lb in (l_emoji, l_nom, l_desc):
            lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addStretch()
        lay.addWidget(l_emoji)
        lay.addWidget(l_nom)
        lay.addWidget(l_desc)
        lay.addStretch()

        # Look integrado + hover-swap (borde/texto a cian), recoloreando también las QLabels hijas.
        card.setStyleSheet(
            f"QFrame#card{{background:#161B22;border:1px solid {_BORDE};border-radius:14px;}}"
            f"QFrame#card QLabel{{background:transparent;color:#E6EDF3;border:none;}}"
            f"QFrame#card QLabel#nom{{color:#E6EDF3;}}"
            f"QFrame#card QLabel#desc{{color:{_DIM};}}"
            f"QFrame#card:hover{{background:#0E1117;border:2px solid {_CIAN};}}"
            f"QFrame#card:hover QLabel{{color:{_CIAN};}}")
        return card

    def _elegir(self, codigo):
        if verticales.fijar_edicion(codigo):
            self.edicion_elegida.emit(codigo)
