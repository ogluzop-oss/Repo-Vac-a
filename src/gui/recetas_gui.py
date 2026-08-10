"""
Recetas y dispensación (edición Pharmacy). SOLO orquesta `services.recetas` (que descuenta stock por el motor
oficial). La receta la EMITE un médico; la farmacia la REGISTRA (paciente + prescriptor + líneas) para
DISPENSAR los medicamentos con receta (descuenta stock). El farmacéutico nunca "crea" una prescripción.
Ventana compatible con el menú (callback_vuelta, usuario, main, parent). Acceso gateado con
`verticales.visible("pharmacy.recetas")`.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from src.gui.foundation import tokens as T
from src.gui._neon_ui import _RoundTableCorners, _ss_tabla_neon
from src.services import recetas as _R

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None

logger = logging.getLogger("gui.recetas")


class RecetasWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.main = main
        self.setStyleSheet(f"background:{T.BG};color:{T.TEXT};")
        self._build()
        self._cargar_pendientes()

    def _emp(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _btn(self, txt, cb, *, primary=False, rojo=False):
        b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(36)
        col = T.CRITICO if rojo else T.INFO
        if primary:
            b.setStyleSheet(f"QPushButton{{background:{col};color:{T.BG};border:none;border-radius:8px;"
                            "font-weight:800;padding:6px 14px;}"
                            f"QPushButton:hover{{background:{T.BG};color:{col};border:1px solid {col};}}")
        else:
            b.setStyleSheet(f"QPushButton{{background:transparent;color:{col};border:1px solid {col};"
                            "border-radius:8px;padding:6px 14px;}"
                            f"QPushButton:hover{{background:{col};color:{T.BG};}}")
        b.clicked.connect(cb)
        return b

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(18, 16, 18, 16); root.setSpacing(12)
        cab = QHBoxLayout()
        tit = QLabel("💊  RECETAS Y DISPENSACIÓN")
        tit.setStyleSheet(f"color:{T.INFO};font-size:20px;font-weight:900;")
        cab.addWidget(tit); cab.addStretch()
        if self._volver:
            cab.addWidget(self._btn("✕", self._volver, rojo=True))
        root.addLayout(cab)

        cuerpo = QHBoxLayout(); cuerpo.setSpacing(16)
        # Izquierda: registrar la receta que el paciente presenta (emitida por un médico) para dispensarla.
        izq = QVBoxLayout()
        titr = QLabel("Registrar receta del médico")
        titr.setStyleSheet(f"color:{T.TEXT};font-size:14px;font-weight:800;")
        izq.addWidget(titr)
        self.in_paciente = QLineEdit(); self.in_paciente.setPlaceholderText("Paciente")
        self.in_medico = QLineEdit(); self.in_medico.setPlaceholderText("Médico prescriptor (quien emite la receta)")
        for w in (self.in_paciente, self.in_medico):
            w.setStyleSheet(f"QLineEdit{{background:{T.BG2};color:{T.TEXT};border:1px solid {T.BORDE};"
                            "border-radius:8px;padding:6px;}")
        izq.addWidget(self.in_paciente); izq.addWidget(self.in_medico)
        self.tabla = QTableWidget(0, 3)
        self.tabla.setHorizontalHeaderLabels(["Código", "Cant.", "Posología"])
        hh = self.tabla.horizontalHeader()
        hh.setStretchLastSection(True)
        hh.setHighlightSections(False)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setFrameShape(QTableWidget.Shape.NoFrame)
        self.tabla.setStyleSheet(_ss_tabla_neon())
        self.tabla._round = _RoundTableCorners(self.tabla, radius=10)
        izq.addWidget(self.tabla, 1)
        add = QHBoxLayout()
        self.in_cod = QLineEdit(); self.in_cod.setPlaceholderText("Código medicamento")
        self.in_cant = QSpinBox(); self.in_cant.setRange(1, 10000); self.in_cant.setValue(1)
        self.in_pos = QLineEdit(); self.in_pos.setPlaceholderText("Posología")
        for w in (self.in_cod, self.in_pos):
            w.setStyleSheet(f"QLineEdit{{background:{T.BG2};color:{T.TEXT};border:1px solid {T.BORDE};"
                            "border-radius:8px;padding:5px;}")
        add.addWidget(self.in_cod, 2); add.addWidget(self.in_cant); add.addWidget(self.in_pos, 2)
        add.addWidget(self._btn("＋", self._add_linea))
        izq.addLayout(add)
        izq.addWidget(self._btn("Registrar receta", self._crear, primary=True))
        cuerpo.addLayout(izq, 1)

        # Derecha: pendientes
        der = QVBoxLayout()
        der.addWidget(QLabel("Recetas pendientes"))
        self.lst = QListWidget()
        self.lst.setStyleSheet(f"QListWidget{{background:{T.BG2};color:{T.TEXT};border:1px solid {T.BORDE};"
                               "border-radius:8px;}")
        der.addWidget(self.lst, 1)
        der.addWidget(self._btn("Dispensar seleccionada", self._dispensar, primary=True))
        cuerpo.addLayout(der, 1)
        root.addLayout(cuerpo, 1)

    def _add_linea(self, cod=None, cant=None, pos=None):
        # `clicked` pasa un bool (checked); si cod es None/bool → invocación desde el botón "＋".
        manual = cod is None or isinstance(cod, bool)
        cod = (self.in_cod.text() if manual else cod).strip()
        pos = (self.in_pos.text() if pos is None else pos).strip()
        if manual and (not cod or not pos):
            faltan = ([] if cod else ["el código del medicamento"]) + ([] if pos else ["la posología"])
            self._aviso("Indica " + " y ".join(faltan) + " antes de añadir la línea.")
            return
        cant = self.in_cant.value() if cant is None else int(cant)
        r = self.tabla.rowCount(); self.tabla.insertRow(r)
        self.tabla.setItem(r, 0, QTableWidgetItem(cod))
        self.tabla.setItem(r, 1, QTableWidgetItem(str(cant)))
        self.tabla.setItem(r, 2, QTableWidgetItem(pos or ""))
        self.in_cod.clear(); self.in_cant.setValue(1); self.in_pos.clear()

    def _items(self):
        out = []
        for r in range(self.tabla.rowCount()):
            cod = (self.tabla.item(r, 0).text() if self.tabla.item(r, 0) else "").strip()
            try:
                cant = int(self.tabla.item(r, 1).text())
            except Exception:
                cant = 0
            pos = self.tabla.item(r, 2).text() if self.tabla.item(r, 2) else ""
            if cod and cant > 0:
                out.append({"codigo": cod, "cantidad": cant, "posologia": pos})
        return out

    def _crear(self):
        paciente = self.in_paciente.text().strip()
        items = self._items()
        if not paciente or not items:
            self._aviso("Indica el paciente y al menos un medicamento de la receta.")
            return
        rid = _R.registrar_receta(paciente, items, medico=self.in_medico.text().strip() or None,
                                  id_empresa=self._emp(),
                                  usuario=(self.usuario.get("nombre") or self.usuario.get("usuario")))
        if rid:
            self.ultima_id = rid
            self.tabla.setRowCount(0); self.in_paciente.clear(); self.in_medico.clear()
            self._cargar_pendientes()
            self._aviso(f"Receta #{rid} registrada.", "info")
        else:
            self._aviso("No se pudo registrar la receta.", "error")

    def _cargar_pendientes(self):
        self.lst.clear()
        try:
            for r in _R.listar_recetas(id_empresa=self._emp()):
                if r["estado"] in ("PENDIENTE", "PARCIAL"):
                    it = QListWidgetItem(f"#{r['id']} · {r['paciente']} · {r['estado']}")
                    it.setData(Qt.ItemDataRole.UserRole, r["id"])
                    self.lst.addItem(it)
        except Exception as e:
            logger.debug("cargar pendientes: %s", e)

    def _dispensar(self):
        it = self.lst.currentItem()
        if not it:
            self._aviso("Selecciona una receta pendiente.")
            return
        res = _R.dispensar(it.data(Qt.ItemDataRole.UserRole), id_empresa=self._emp(),
                           usuario=(self.usuario.get("nombre") or self.usuario.get("usuario")))
        self._cargar_pendientes()
        if res.get("ok"):
            self._aviso(f"Dispensada ({res['estado']}, {res['dispensadas']} uds).", "info")
        else:
            self._aviso(res.get("error", "No se pudo dispensar."), "error")

    def _aviso(self, msg, tipo="warning"):
        if mostrar_mensaje:
            mostrar_mensaje(self, "Recetas", msg, tipo)
        else:  # pragma: no cover
            logger.info("recetas: %s", msg)
