"""
Selector de perfil — ventana PREVIA al login.

Muestra los perfiles/empleados registrados de la empresa como botones cuadrados (icono de
persona + nombre), con buscador por nombre y scrollbar del diseño global de la app. Al pulsar
un perfil, emite `perfil_elegido(nombre)`; el login pre-rellena y BLOQUEA el nombre y solo pide
la contraseña. AISLAMIENTO ESTRICTO por empresa: solo lista perfiles de la empresa activa
(`db.usuario.listar_usuarios_empresa`), nunca de otra (privacidad entre empresas).
"""

import os

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QGridLayout, QLabel, QLineEdit, QScrollArea, QToolButton,
                             QVBoxLayout, QWidget)

from src.utils.i18n import tr

_BG = "#0E1117"
_CIAN = "#00FFC6"
_BORDE = "#30363D"
_DIM = "#8B949E"


def _icono_persona(color=_CIAN, size=56):
    """Icono de persona (contorno) al estilo del aportado: cabeza (círculo) + torso (cúpula)."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidth(max(2, size // 16))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Cabeza
    hd = size * 0.30
    p.drawEllipse(QRectF((size - hd) / 2, size * 0.13, hd, hd))
    # Torso: cúpula (media elipse) con base plana
    bw, bh = size * 0.60, size * 0.34
    bx, by = (size - bw) / 2, size * 0.52
    p.drawArc(QRectF(bx, by, bw, bh * 2), 0, 180 * 16)
    p.drawLine(QPointF(bx, by + bh), QPointF(bx + bw, by + bh))
    p.end()
    return QIcon(pix)


class SelectorPerfilWindow(QWidget):
    """Ventana de selección de perfil previa al login. `perfil_elegido` emite el nombre elegido."""

    perfil_elegido = pyqtSignal(str)

    def __init__(self, id_empresa=None, parent=None):
        super().__init__(parent)
        self._id_empresa = id_empresa
        self._botones = []          # [(QToolButton, nombre_lower, nombre)]
        self._icono = _icono_persona()
        self._ncols = 0
        self.setObjectName("panel_raiz")
        self.setStyleSheet(f"background:{_BG};")
        self._setup_ui()
        self.cargar_perfiles()

    # ── UI ──────────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 34, 40, 34)
        root.setSpacing(18)

        # Logo corporativo (si existe) + título.
        try:
            from src.gui.login import _resolver_logo
            logo_path = _resolver_logo()
        except Exception:
            logo_path = ""
        if logo_path and os.path.exists(logo_path):
            self._lbl_logo = QLabel()
            self._lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._lbl_logo.setStyleSheet("background:transparent;border:none;")
            pix = QPixmap(logo_path)
            if not pix.isNull():
                self._lbl_logo.setPixmap(pix.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio,
                                                    Qt.TransformationMode.SmoothTransformation))
            root.addWidget(self._lbl_logo, 0, Qt.AlignmentFlag.AlignCenter)

        self._lbl_titulo = QLabel(tr("selector.title", default="SELECCIONA TU PERFIL"))
        self._lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_titulo.setFont(QFont("Segoe UI", 18, QFont.Weight.Black))
        self._lbl_titulo.setStyleSheet(f"color:{_CIAN};letter-spacing:2px;background:transparent;")
        root.addWidget(self._lbl_titulo)

        # Buscador por nombre.
        self.buscador = QLineEdit()
        self.buscador.setPlaceholderText(tr("selector.search_ph", default="Buscar empleado por nombre…"))
        self.buscador.setFixedHeight(46)
        self.buscador.setFont(QFont("Segoe UI", 11))
        self.buscador.setStyleSheet(
            f"QLineEdit{{background:#161B22;color:#FFFFFF;border:2px solid {_CIAN};"
            f"border-radius:12px;padding:6px 16px;font-family:'Segoe UI';}}"
            f"QLineEdit:focus{{border:2px solid #00E6B2;background:#1A2230;}}")
        self.buscador.textChanged.connect(lambda _t: self._reflow())
        root.addWidget(self.buscador)

        # Área con scroll (scrollbar del diseño global) + rejilla de botones.
        try:
            from src.gui.foundation import tokens as _T
            _sb = _T.qss_scrollbar()
        except Exception:
            _sb = ""
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(f"QScrollArea{{background:{_BG};border:none;}}" + _sb)
        cont = QWidget()
        cont.setStyleSheet(f"background:{_BG};")
        self.grid = QGridLayout(cont)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setSpacing(16)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.scroll.setWidget(cont)
        root.addWidget(self.scroll, 1)

        self.lbl_vacio = QLabel("")
        self.lbl_vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_vacio.setStyleSheet(f"color:{_DIM};font-size:14px;background:transparent;")
        self.lbl_vacio.setVisible(False)
        root.addWidget(self.lbl_vacio)

    def _crear_boton(self, nombre):
        b = QToolButton()
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        b.setIcon(self._icono)
        b.setIconSize(QSize(56, 56))
        b.setText(nombre)
        b.setFixedSize(150, 150)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolTip(nombre)
        b.setStyleSheet(
            f"""
            QToolButton {{
                background:#161B22; color:#FFFFFF; border:2px solid {_BORDE};
                border-radius:16px; font-family:'Segoe UI'; font-size:13px; font-weight:700;
                padding:10px 6px;
            }}
            QToolButton:hover {{ background:{_CIAN}; color:#0E1117; border:2px solid {_CIAN}; }}
            QToolButton:pressed {{ background:#00C79A; color:#0E1117; }}
            """)
        b.clicked.connect(lambda _c=False, n=nombre: self.perfil_elegido.emit(n))
        return b

    # ── datos ─────────────────────────────────────────────────────────────────
    def cargar_perfiles(self):
        """Carga los perfiles de la empresa activa (aislamiento estricto) y construye los botones."""
        from src.db.usuario import listar_usuarios_empresa
        # Limpia botones anteriores.
        for w, _nl, _n in self._botones:
            w.setParent(None)
            w.deleteLater()
        self._botones = []
        perfiles = listar_usuarios_empresa(self._id_empresa)
        vistos = set()
        for u in perfiles:
            nombre = (u.get("nombre") or "").strip()
            if not nombre or nombre.lower() in vistos:
                continue
            vistos.add(nombre.lower())
            b = self._crear_boton(nombre)
            self._botones.append((b, nombre.lower(), nombre))
        self._ncols = 0   # fuerza reflow
        self._reflow()

    def tiene_perfiles(self):
        return len(self._botones) > 0

    # ── disposición responsiva ──────────────────────────────────────────────────
    def _columnas(self):
        ancho = self.scroll.viewport().width() if hasattr(self, "scroll") else self.width()
        return max(2, ancho // 172)   # botón 150 + spacing 16 ≈ 166

    def _reflow(self):
        filtro = self.buscador.text().strip().lower()
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        ncols = self._columnas()
        r = c = 0
        visibles = 0
        for w, nombre_lower, _nombre in self._botones:
            if filtro and filtro not in nombre_lower:
                w.hide()
                continue
            w.show()
            self.grid.addWidget(w, r, c, Qt.AlignmentFlag.AlignHCenter)
            visibles += 1
            c += 1
            if c >= ncols:
                c = 0
                r += 1
        self._ncols = ncols
        if not self._botones:
            self.lbl_vacio.setText(tr("selector.empty", default="No hay perfiles registrados en esta empresa."))
            self.lbl_vacio.setVisible(True)
        elif visibles == 0:
            self.lbl_vacio.setText(tr("selector.no_match", default="Ningún empleado coincide con la búsqueda."))
            self.lbl_vacio.setVisible(True)
        else:
            self.lbl_vacio.setVisible(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Solo re-disponer si cambia el nº de columnas (evita trabajo en cada píxel).
        if self._columnas() != self._ncols:
            self._reflow()

    def showEvent(self, event):
        super().showEvent(event)
        self.buscador.setFocus()

    def _retraducir(self, *_):
        self._lbl_titulo.setText(tr("selector.title", default="SELECCIONA TU PERFIL"))
        self.buscador.setPlaceholderText(tr("selector.search_ph", default="Buscar empleado por nombre…"))
        self._reflow()
