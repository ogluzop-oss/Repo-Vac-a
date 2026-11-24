"""
Directorio Corporativo (CCP · Parte E) — evolución de la Agenda Corporativa.

Vista consolidada de SOLO LECTURA con navegación Internos vs Externos, resuelta a través del Servicio
Corporativo de Resolución de Destinatarios (datos vivos, sin duplicar). Multiempresa estricto. La
Agenda anterior se conserva; el Directorio es su evolución.
"""

import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from src.gui._neon_ui import _BotonCerrarX, _RoundTableCorners, _ss_tabla_neon
from src.gui.components import EnterpriseTabs
from src.gui.transiciones import abrir_dialogo_deslizante, instalar_transicion_tabs
from src.services import destinatarios as _dest

logger = logging.getLogger("gui.directorio_corporativo")

_BG = "#0E1117"
_BG2 = "#161B22"
_CIAN = "#00FFC6"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_DIM = "#8B949E"
_AMBAR = "#F0A050"

# Clasificación de tipos en Internos vs Externos (Parte E).
_INTERNOS = {"empleado", "usuario", "centro", "tienda", "almacen", "representante"}
_EXTERNOS = {"cliente", "proveedor", "contacto", "lead", "banco", "acreedor", "historico"}

_ETIQUETAS_TAB = {0: "todos", 1: "internos", 2: "externos"}


class DirectorioCorporativoDialog(QDialog):
    def __init__(self, parent=None, contexto=None):
        super().__init__(parent)
        self._contexto = contexto
        self.setWindowTitle("Directorio corporativo")
        self.setMinimumSize(760, 560)
        # SIN barra negra de Windows: ventana sin marco (se cierra con la X). Petición explícita:
        # se abre a PANTALLA COMPLETA, sin el contorno turquesa que antes rodeaba la ventana (por lo
        # mismo, ya no hace falta enmascarar esquinas redondeadas: a pantalla completa, tocando los
        # bordes físicos de la pantalla, no hay esquina visible que redondear), y con la misma
        # animación de deslizamiento que el resto de diálogos a pantalla completa de la app — ver
        # `abrir_directorio_corporativo`/`abrir_dialogo_deslizante`, que es quien de verdad fija la
        # geometría a pantalla completa de forma fiable (fijarla aquí en `__init__` no basta: el
        # HWND frameless puede asentarse con una geometría menor DESPUÉS de este punto en Windows).
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        # "border:none" EXPLÍCITO (no basta con omitirlo): la hoja de estilos global de la app pone
        # `border:2px solid CIAN` a TODO QDialog por defecto (`assets/estilo_global.py`,
        # QSS_DIALOGS) y, como esta hoja local no redeclaraba esa propiedad, seguía colándose por
        # debajo pese a quitar el contorno de aquí.
        self.setStyleSheet(f"QDialog{{background:{_BG};border:none;}}")
        self._drag = None
        self._build()
        self._timer = QTimer(self); self._timer.setSingleShot(True); self._timer.setInterval(180)
        self._timer.timeout.connect(self._cargar)
        self._cargar()

    # Arrastre de la ventana sin marco (no hay barra de título de Windows).
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = None
        super().mouseReleaseEvent(e)

    @staticmethod
    def _crear_tabla() -> QTableWidget:
        """Mismo diseño que el resto de tablas de la app: contorno turquesa, cabeceras redondeadas y
        hover swap (petición explícita — antes esta tabla tenía un estilo propio más plano, sin
        esquinas redondeadas en la cabecera ni hover)."""
        t = QTableWidget(0, 4)
        t.setHorizontalHeaderLabels(["Nombre", "Correo", "Tipo", "Aviso"])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        t.horizontalHeader().setHighlightSections(False)
        t.setFrameShape(QTableWidget.Shape.NoFrame)
        # SIN scrollbar propia (petición explícita): debe llevar la scrollbar ESTÁNDAR de toda la
        # app, no la más fina de `_neon_ui` — mismo criterio que Agenda Corporativa.
        t.setStyleSheet(_ss_tabla_neon(incluir_scroll_propio=False))
        t._mask = _RoundTableCorners(t, radius=10)
        return t

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(18, 16, 18, 16); root.setSpacing(10)
        cab = QHBoxLayout()
        t = QLabel("🏢  DIRECTORIO CORPORATIVO")
        t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:16px;")
        cab.addWidget(t); cab.addStretch()
        btn_x = _BotonCerrarX(32); btn_x.clicked.connect(self.accept)
        cab.addWidget(btn_x)
        root.addLayout(cab)
        sub = QLabel("Contactos internos y externos consolidados (solo lectura, datos vivos). "
                     "Aislado por empresa.")
        sub.setStyleSheet(f"color:{_DIM};font-family:'Segoe UI';font-size:11px;"); sub.setWordWrap(True)
        root.addWidget(sub)

        fila_busq = QHBoxLayout(); fila_busq.setSpacing(8)
        self.inp = QLineEdit()
        # Misma altura (48px) que el botón de la lupa de al lado (petición explícita).
        self.inp.setFixedHeight(48)
        self.inp.setPlaceholderText("🔍 Buscar por nombre, empresa, CIF, correo, teléfono…")
        self.inp.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_CIAN};border-radius:10px;"
            f"padding:6px 12px;font-family:'Segoe UI';font-size:13px;}}")
        self.inp.textEdited.connect(lambda _=None: self._timer.start())
        self.inp.returnPressed.connect(self._cargar)
        fila_busq.addWidget(self.inp, 1)
        # 48x48 (no 36x36/44x44): evita que el glifo emoji 🔍 se vea recortado.
        btn_buscar = QPushButton("🔍"); btn_buscar.setFixedSize(48, 48)
        btn_buscar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_buscar.setStyleSheet(f"QPushButton{{background:transparent;color:{_CIAN};border:2px solid {_CIAN};"
                                 f"border-radius:10px;font-weight:900;padding:0;}}"
                                 f"QPushButton:hover{{background:{_CIAN};color:{_BG};}}")
        btn_buscar.clicked.connect(self._cargar)
        fila_busq.addWidget(btn_buscar)
        root.addLayout(fila_busq)

        # "Todos/Internos/Externos" pasa de segmento de botones a pestañas DE VERDAD (petición
        # explícita): mismo diseño de pestañas que CCP (`ccp_panel.py`) + deslizamiento al cambiar,
        # y cada una con su PROPIA tabla (también petición explícita: "las tres tablas").
        self.tabs = EnterpriseTabs()
        self.tbl_todos = self._crear_tabla()
        self.tbl_internos = self._crear_tabla()
        self.tbl_externos = self._crear_tabla()
        self.tabs.addTab(self.tbl_todos, "Todos")
        self.tabs.addTab(self.tbl_internos, "Internos")
        self.tabs.addTab(self.tbl_externos, "Externos")
        instalar_transicion_tabs(self.tabs)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs, 1)

        self.lbl_n = QLabel(""); self.lbl_n.setStyleSheet(f"color:{_DIM};font-size:11px;")
        root.addWidget(self.lbl_n)

    def _on_tab_changed(self, idx):
        grupo = _ETIQUETAS_TAB.get(idx, "todos")
        tabla = (self.tbl_todos, self.tbl_internos, self.tbl_externos)[idx if 0 <= idx <= 2 else 0]
        self.lbl_n.setText(f"{tabla.rowCount()} contacto(s) · {grupo}")

    @staticmethod
    def _rellenar_tabla(tabla, datos):
        tabla.setRowCount(len(datos))
        for i, d in enumerate(datos):
            tabla.setItem(i, 0, QTableWidgetItem(("★ " if d.favorito else "") + d.nombre_mostrado))
            tabla.setItem(i, 1, QTableWidgetItem(d.correo))
            tabla.setItem(i, 2, QTableWidgetItem(d.etiqueta))
            av = QTableWidgetItem("; ".join(d.avisos) if d.avisos else "")
            if d.avisos:
                av.setForeground(QColor(_AMBAR))
            tabla.setItem(i, 3, av)

    def _cargar(self):
        try:
            res = _dest.buscar_destinatarios(None, self.inp.text().strip(), contexto=self._contexto,
                                             limite=500)
        except Exception as e:
            logger.debug("directorio cargar: %s", e); res = []
        internos = [d for d in res if d.tipo in _INTERNOS]
        externos = [d for d in res if d.tipo in _EXTERNOS]
        self._rellenar_tabla(self.tbl_todos, res)
        self._rellenar_tabla(self.tbl_internos, internos)
        self._rellenar_tabla(self.tbl_externos, externos)
        self._on_tab_changed(self.tabs.currentIndex())


def abrir_directorio_corporativo(parent=None, contexto=None):
    abrir_dialogo_deslizante(DirectorioCorporativoDialog(parent, contexto=contexto), parent)
