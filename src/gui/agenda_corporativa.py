"""
Agenda Corporativa Virtual (Parte O) — vista consolidada de SOLO LECTURA.

No es una agenda nueva ni duplica datos: es una representación unificada de todos los contactos
corporativos (clientes, proveedores, empleados, usuarios, contactos, centros, leads…) resuelta a
través del Servicio Corporativo de Resolución de Destinatarios (punto único). Multiempresa estricto.
"""

import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from src.gui._neon_ui import _RoundTableCorners, _ss_tabla_neon
from src.services import destinatarios as _dest

logger = logging.getLogger("gui.agenda_corporativa")

_BG = "#0E1117"
_BG2 = "#161B22"
_CIAN = "#00FFC6"
_ROJO = "#FF4C4C"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_DIM = "#8B949E"
_AMBAR = "#F0A050"


class AgendaCorporativaDialog(QDialog):
    """Diálogo de consulta de la agenda corporativa consolidada (solo lectura)."""

    def __init__(self, parent=None, contexto=None):
        super().__init__(parent)
        self._contexto = contexto
        self.setWindowTitle("Agenda corporativa")
        self.setMinimumSize(720, 520)
        # SIN barra negra de Windows: ventana sin marco con contorno propio (se cierra con el botón "Cerrar").
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setStyleSheet(f"QDialog{{background:{_BG};border:2px solid {_CIAN};border-radius:14px;}}")
        self._drag = None
        self._build()
        self._timer = QTimer(self); self._timer.setSingleShot(True); self._timer.setInterval(180)
        self._timer.timeout.connect(self._cargar)
        self._cargar()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(18, 16, 18, 16); root.setSpacing(10)
        t = QLabel("📇  AGENDA CORPORATIVA")
        t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:16px;")
        root.addWidget(t)
        sub = QLabel("Vista consolidada (solo lectura). Los datos viven en sus módulos; aquí solo se "
                     "representan. Aislada por empresa.")
        sub.setStyleSheet(f"color:{_DIM};font-family:'Segoe UI';font-size:11px;")
        sub.setWordWrap(True); root.addWidget(sub)

        self.inp = QLineEdit(); self.inp.setFixedHeight(38)
        self.inp.setPlaceholderText("Buscar por nombre, empresa, CIF, correo, teléfono…")
        self.inp.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_CIAN};border-radius:10px;"
            f"padding:6px 12px;font-family:'Segoe UI';font-size:13px;}}")
        self.inp.textEdited.connect(lambda _=None: self._timer.start())
        root.addWidget(self.inp)

        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(["Nombre", "Correo", "Tipo", "Aviso"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl.horizontalHeader().setHighlightSections(False)
        self.tbl.setFrameShape(QTableWidget.Shape.NoFrame)
        self.tbl.setStyleSheet(_ss_tabla_neon())                       # contorno neón + cabeceras redondeadas + hover swap
        self._mask_tbl = _RoundTableCorners(self.tbl, radius=10)       # máscara → el contorno no se corta
        root.addWidget(self.tbl, 1)

        self.lbl_n = QLabel(""); self.lbl_n.setStyleSheet(f"color:{_DIM};font-size:11px;")
        root.addWidget(self.lbl_n)
        fila = QHBoxLayout(); fila.addStretch()
        # "Directorio" con el MISMO estilo que "Cerrar" (contorno cian + hover swap a relleno).
        bd = QPushButton("🏢  Directorio ▸"); bd.setFixedHeight(38)
        bd.setCursor(Qt.CursorShape.PointingHandCursor)
        bd.setStyleSheet(f"QPushButton{{background:transparent;color:{_CIAN};border:2px solid {_CIAN};"
                         f"border-radius:10px;font-weight:900;padding:6px 18px;}}"
                         f"QPushButton:hover{{background:{_CIAN};color:{_BG};}}")
        bd.clicked.connect(self._abrir_directorio)
        # "Cerrar" en ROJO (mismo diseño: contorno + hover swap a relleno).
        b = QPushButton("Cerrar"); b.setFixedHeight(38); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton{{background:transparent;color:{_ROJO};border:2px solid {_ROJO};"
                        f"border-radius:10px;font-weight:900;padding:6px 18px;}}"
                        f"QPushButton:hover{{background:{_ROJO};color:{_BG};}}")
        b.clicked.connect(self.accept)
        fila.addWidget(bd); fila.addWidget(b); root.addLayout(fila)

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

    def _abrir_directorio(self):
        try:
            from src.gui.directorio_corporativo import abrir_directorio_corporativo
            abrir_directorio_corporativo(self, contexto=self._contexto)
        except Exception as e:
            logger.debug("abrir directorio: %s", e)

    def _cargar(self):
        try:
            res = _dest.buscar_destinatarios(None, self.inp.text().strip(), contexto=self._contexto,
                                             limite=500)
        except Exception as e:
            logger.debug("agenda cargar: %s", e); res = []
        self.tbl.setRowCount(len(res))
        for i, d in enumerate(res):
            self.tbl.setItem(i, 0, QTableWidgetItem("★ " + d.nombre_mostrado if d.favorito
                                                    else d.nombre_mostrado))
            self.tbl.setItem(i, 1, QTableWidgetItem(d.correo))
            self.tbl.setItem(i, 2, QTableWidgetItem(d.etiqueta))
            av = QTableWidgetItem("; ".join(d.avisos) if d.avisos else "")
            if d.avisos:
                from PyQt6.QtGui import QColor
                av.setForeground(QColor(_AMBAR))
            self.tbl.setItem(i, 3, av)
        self.lbl_n.setText(f"{len(res)} contacto(s)")


def abrir_agenda_corporativa(parent=None, contexto=None):
    """Abre la agenda corporativa consolidada."""
    AgendaCorporativaDialog(parent, contexto=contexto).exec()
