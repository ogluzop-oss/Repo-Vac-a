"""
Directorio Corporativo (CCP · Parte E) — evolución de la Agenda Corporativa.

Vista consolidada de SOLO LECTURA con navegación Internos vs Externos, resuelta a través del Servicio
Corporativo de Resolución de Destinatarios (datos vivos, sin duplicar). Multiempresa estricto. La
Agenda anterior se conserva; el Directorio es su evolución.
"""

import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

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


class DirectorioCorporativoDialog(QDialog):
    def __init__(self, parent=None, contexto=None):
        super().__init__(parent)
        self._contexto = contexto
        self._grupo = "todos"   # todos | internos | externos
        self.setWindowTitle("Directorio corporativo")
        self.setMinimumSize(760, 560)
        self.setStyleSheet(f"QDialog{{background:{_BG};}}")
        self._build()
        self._timer = QTimer(self); self._timer.setSingleShot(True); self._timer.setInterval(180)
        self._timer.timeout.connect(self._cargar)
        self._cargar()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(18, 16, 18, 16); root.setSpacing(10)
        t = QLabel("🏢  DIRECTORIO CORPORATIVO")
        t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:16px;")
        root.addWidget(t)
        sub = QLabel("Contactos internos y externos consolidados (solo lectura, datos vivos). "
                     "Aislado por empresa.")
        sub.setStyleSheet(f"color:{_DIM};font-family:'Segoe UI';font-size:11px;"); sub.setWordWrap(True)
        root.addWidget(sub)

        # Segmento Internos/Externos.
        seg = QHBoxLayout(); seg.setSpacing(8)
        self._bg = QButtonGroup(self)
        for clave, txt in (("todos", "Todos"), ("internos", "Internos"), ("externos", "Externos")):
            b = QPushButton(txt); b.setCheckable(True); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(34)
            b.setStyleSheet(
                f"QPushButton{{background:transparent;color:{_TEXT};border:1px solid {_BORDE};"
                f"border-radius:8px;padding:4px 16px;font-weight:bold;}}"
                f"QPushButton:checked{{background:{_CIAN};color:{_BG};border:1px solid {_CIAN};}}")
            b.clicked.connect(lambda _=False, c=clave: self._set_grupo(c))
            self._bg.addButton(b); seg.addWidget(b)
            if clave == "todos":
                b.setChecked(True)
        seg.addStretch()
        root.addLayout(seg)

        self.inp = QLineEdit(); self.inp.setFixedHeight(36)
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
        self.tbl.setStyleSheet(
            f"QTableWidget{{background:{_BG2};color:{_TEXT};gridline-color:{_BORDE};border:1px solid "
            f"{_BORDE};border-radius:10px;font-family:'Segoe UI';font-size:12px;}}"
            f"QHeaderView::section{{background:{_BG2};color:{_CIAN};font-weight:bold;border:none;"
            f"border-bottom:1px solid {_BORDE};padding:6px;}}")
        root.addWidget(self.tbl, 1)

        self.lbl_n = QLabel(""); self.lbl_n.setStyleSheet(f"color:{_DIM};font-size:11px;")
        root.addWidget(self.lbl_n)
        b = QPushButton("Cerrar"); b.setFixedHeight(36); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton{{background:transparent;color:{_CIAN};border:2px solid {_CIAN};"
                        f"border-radius:10px;font-weight:900;padding:6px 18px;}}"
                        f"QPushButton:hover{{background:{_CIAN};color:{_BG};}}")
        b.clicked.connect(self.accept); root.addWidget(b, 0, Qt.AlignmentFlag.AlignRight)

    def _set_grupo(self, grupo):
        self._grupo = grupo; self._cargar()

    def _cargar(self):
        try:
            res = _dest.buscar_destinatarios(None, self.inp.text().strip(), contexto=self._contexto,
                                             limite=500)
        except Exception as e:
            logger.debug("directorio cargar: %s", e); res = []
        if self._grupo == "internos":
            res = [d for d in res if d.tipo in _INTERNOS]
        elif self._grupo == "externos":
            res = [d for d in res if d.tipo in _EXTERNOS]
        self.tbl.setRowCount(len(res))
        for i, d in enumerate(res):
            self.tbl.setItem(i, 0, QTableWidgetItem(("★ " if d.favorito else "") + d.nombre_mostrado))
            self.tbl.setItem(i, 1, QTableWidgetItem(d.correo))
            self.tbl.setItem(i, 2, QTableWidgetItem(d.etiqueta))
            av = QTableWidgetItem("; ".join(d.avisos) if d.avisos else "")
            if d.avisos:
                from PyQt6.QtGui import QColor
                av.setForeground(QColor(_AMBAR))
            self.tbl.setItem(i, 3, av)
        self.lbl_n.setText(f"{len(res)} contacto(s) · {self._grupo}")


def abrir_directorio_corporativo(parent=None, contexto=None):
    DirectorioCorporativoDialog(parent, contexto=contexto).exec()
