"""
CRM — Ficha avanzada de clientes (VTA.1).

Pantalla NUEVA. Búsqueda/listado + alta + edición de crédito/segmento + historial comercial
(ventas/devoluciones/saldo) + puntos de fidelización. Multiempresa. No modifica el TPV.
"""

import logging

from PyQt6.QtWidgets import (QHBoxLayout, QInputDialog, QLabel, QMessageBox,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from src.db import clientes as CL
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _TEXT, _btn, _inp, _tabla)

logger = logging.getLogger("ventas.clientes.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class ClientesWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Clientes (CRM)")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)

        f = QHBoxLayout()
        self.in_busca = _inp("Buscar (nombre/NIF/email)")
        f.addWidget(self.in_busca)
        f.addWidget(_btn("Buscar", self._buscar, primary=True))
        f.addWidget(_btn("Nuevo", self._nuevo))
        f.addWidget(_btn("Editar crédito/segmento", self._editar))
        f.addWidget(_btn("Historial", self._historial))
        f.addStretch()
        root.addLayout(f)

        self.tabla = _tabla(["id", "Nombre", "NIF", "Segmento", "Límite crédito",
                             "Riesgo", "Puntos", "Estado"])
        root.addWidget(self.tabla)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_TEXT};")
        root.addWidget(self.lbl)
        self._buscar()

    def _emp(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _buscar(self):
        txt = self.in_busca.text().strip()
        self._data = (CL.buscar_clientes(txt, self._emp()) if txt
                      else CL.listar_clientes(self._emp()))
        self.tabla.setRowCount(len(self._data))
        for i, c in enumerate(self._data):
            for j, v in enumerate([c.get("id"), c.get("nombre"), c.get("nif"), c.get("segmento"),
                                   c.get("limite_credito"), c.get("riesgo_actual"),
                                   c.get("saldo_puntos"), c.get("estado")]):
                self.tabla.setItem(i, j, _it(v))

    def _sel(self):
        i = self.tabla.currentRow()
        return self._data[i] if 0 <= i < len(self._data) else None

    def _nuevo(self):
        nombre, ok = QInputDialog.getText(self, "Nuevo cliente", "Nombre:")
        if ok and nombre.strip():
            CL.crear_cliente(nombre.strip(), id_empresa=self._emp())
            self._buscar()

    def _editar(self):
        c = self._sel()
        if not c:
            return
        seg, ok = QInputDialog.getText(self, "Segmento", "Segmento:", text=c.get("segmento") or "")
        if not ok:
            return
        lim, ok2 = QInputDialog.getDouble(self, "Límite de crédito", "Límite:",
                                          float(c.get("limite_credito") or 0), 0, 1e9, 2)
        if not ok2:
            return
        CL.actualizar_cliente(c["id"], id_empresa=self._emp(), segmento=seg.strip() or None,
                              limite_credito=lim)
        self._buscar()

    def _historial(self):
        c = self._sel()
        if not c:
            return
        h = CL.historial_comercial(c["id"], self._emp())
        self.lbl.setText(f"{c['nombre']}: ventas {len(h['ventas'])} ({h['total_ventas']}) · "
                         f"devoluciones {len(h['devoluciones'])} ({h['total_devoluciones']}) · "
                         f"saldo {h['saldo']}")
