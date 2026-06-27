"""
Centro de notificaciones (FASE COM-2).

Bandeja de entrada del usuario activo: filtro por prioridad/módulo, marcar leída y eliminar.
Estilo dark+cian; acotada a la empresa activa.
"""

import logging

from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QMessageBox, QTableWidgetItem, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _combo, _tabla
from src.services import notificaciones as _N

logger = logging.getLogger("notificaciones.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


def _usuario():
    try:
        from src.db.usuario import sesion_global
        return getattr(sesion_global, "usuario_actual", None) or {}
    except Exception:
        return {}


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


class NotificacionesWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Centro de notificaciones")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("Actualizar", self._load))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)

        bar = QHBoxLayout()
        self.cmb_prio = _combo([("(todas)", None), ("crítica", "critica"), ("alta", "alta"),
                                ("normal", "normal"), ("baja", "baja")])
        self.cmb_prio.currentIndexChanged.connect(self._load)
        bar.addWidget(QLabel("Prioridad:")); bar.addWidget(self.cmb_prio)
        bar.addWidget(_btn("Marcar leída", self._leer))
        bar.addWidget(_btn("Eliminar", self._eliminar, danger=True))
        bar.addStretch(); lay = root
        lay.addLayout(bar)
        self.tbl = _tabla(["ID", "Prioridad", "Módulo", "Título", "Mensaje", "Fecha"])
        self.tbl.cellClicked.connect(self._sel)
        lay.addWidget(self.tbl)
        self._sel_id = None
        self._load()

    def _load(self):
        try:
            prio = self.cmb_prio.currentData()
            filas = _N.pendientes_usuario(_usuario(), id_empresa=_empresa())
            if prio:
                filas = [f for f in filas if f.get("prioridad") == prio]
            self.tbl.setRowCount(len(filas))
            for i, n in enumerate(filas):
                vals = [n["id"], n.get("prioridad"), n.get("modulo"), n.get("titulo"),
                        (n.get("mensaje") or "")[:60], n.get("fecha_creacion")]
                for j, v in enumerate(vals):
                    self.tbl.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("load: %s", e)

    def _sel(self, row, _c):
        try:
            self._sel_id = int(self.tbl.item(row, 0).text())
        except Exception:
            self._sel_id = None

    def _leer(self):
        if self._sel_id:
            u = _usuario()
            _N.marcar_leida(self._sel_id, u.get("id"), id_empresa=_empresa())
            self._load()

    def _eliminar(self):
        if self._sel_id:
            _N.eliminar(self._sel_id, id_empresa=_empresa())
            self._load()
