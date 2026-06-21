"""
Gestión de almacenes (INV.7.1) — GUI CRUD sobre la tabla `almacen`.

Pantalla NUEVA dentro de INVENTARIO. Alta/edición/activación/baja lógica de almacenes
(nombre, código, tipo, tienda asociada, estado). No elimina físicamente (conserva
existencias e histórico). Multiempresa por contexto activo.
"""

import logging

from PyQt6.QtWidgets import (QHBoxLayout, QInputDialog, QLabel, QMessageBox,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from src.db import stock_almacen as SA
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _btn, _combo, _inp, _tabla)

logger = logging.getLogger("inventario.almacenes.gui")

_TIPOS = ["central", "regional", "logistico", "tienda", "temporal"]


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class AlmacenesWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)

        cab = QHBoxLayout()
        t = QLabel("Gestión de almacenes")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)

        # alta
        f = QHBoxLayout()
        self.in_nombre = _inp("Nombre"); self.in_codigo = _inp("Código"); self.in_codigo.setFixedWidth(120)
        self.cmb_tipo = _combo([(t, t) for t in _TIPOS])
        f.addWidget(QLabel("Nombre:")); f.addWidget(self.in_nombre)
        f.addWidget(QLabel("Código:")); f.addWidget(self.in_codigo)
        f.addWidget(QLabel("Tipo:")); f.addWidget(self.cmb_tipo)
        f.addWidget(_btn("Crear", self._crear, primary=True))
        for w in (f.itemAt(i).widget() for i in range(f.count())):
            if isinstance(w, QLabel):
                w.setStyleSheet(f"color:{_DIM};")
        root.addLayout(f)

        self.tabla = _tabla(["id", "Nombre", "Código", "Tipo", "Tienda", "Estado", "Activo"])
        root.addWidget(self.tabla)

        acc = QHBoxLayout()
        acc.addWidget(_btn("Renombrar", self._renombrar))
        acc.addWidget(_btn("Activar", lambda: self._activar(True)))
        acc.addWidget(_btn("Desactivar", lambda: self._activar(False), danger=True))
        acc.addStretch()
        root.addLayout(acc)
        self._cargar()

    def _id_empresa(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _cargar(self):
        self._data = SA.listar_almacenes(self._id_empresa(), solo_activos=False)
        self.tabla.setRowCount(len(self._data))
        for i, a in enumerate(self._data):
            for j, v in enumerate([a.get("id"), a.get("nombre"), a.get("codigo_almacen"),
                                   a.get("tipo_almacen"), a.get("id_tienda"),
                                   a.get("estado"), a.get("activo")]):
                self.tabla.setItem(i, j, _it(v))

    def _sel(self):
        i = self.tabla.currentRow()
        return self._data[i] if 0 <= i < len(self._data) else None

    def _crear(self):
        nombre = self.in_nombre.text().strip()
        codigo = self.in_codigo.text().strip()
        if not nombre or not codigo:
            QMessageBox.information(self, "Almacenes", "Indica nombre y código."); return
        rid = SA.crear_almacen(nombre, codigo, self.cmb_tipo.currentData(),
                               id_empresa=self._id_empresa())
        if rid:
            self.in_nombre.clear(); self.in_codigo.clear(); self._cargar()
        else:
            QMessageBox.warning(self, "Almacenes", "No se pudo crear (¿nombre/código duplicado?).")

    def _renombrar(self):
        a = self._sel()
        if not a:
            return
        nuevo, ok = QInputDialog.getText(self, "Renombrar", "Nuevo nombre:", text=a.get("nombre") or "")
        if ok and nuevo.strip():
            SA.actualizar_almacen(a["id"], id_empresa=self._id_empresa(), nombre=nuevo.strip())
            self._cargar()

    def _activar(self, activo):
        a = self._sel()
        if not a:
            return
        SA.activar_almacen(a["id"], activo=activo, id_empresa=self._id_empresa())
        self._cargar()
