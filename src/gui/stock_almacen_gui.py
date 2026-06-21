"""
Multialmacén — GUI de stock por almacén y traspasos (INV.4.9).

Pantalla NUEVA dentro de INVENTARIO (no modifica las existentes). Permite consultar las
existencias de un artículo desglosadas por almacén y realizar traspasos reales entre
almacenes (descuento origen + incremento destino + kárdex). La fuente de verdad es
`stock_almacen`; la caché de articulos se recalcula automáticamente. Multiempresa.
"""

import logging

from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QMessageBox, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from src.db import stock_almacen as SA
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _TEXT, _btn, _combo, _inp, _tabla)

logger = logging.getLogger("inventario.stock_almacen.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class StockAlmacenWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)

        cab = QHBoxLayout()
        t = QLabel("Stock por almacén")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)

        f = QHBoxLayout()
        self.in_cod = _inp("Código artículo"); self.in_cod.setFixedWidth(200)
        f.addWidget(QLabel("Artículo:")); f.addWidget(self.in_cod)
        f.addWidget(_btn("Ver existencias", self._buscar, primary=True))
        f.addStretch()
        for w in f.parent().findChildren(QLabel) if f.parent() else []:
            w.setStyleSheet(f"color:{_DIM};")
        root.addLayout(f)

        self.tabla = _tabla(["Almacén", "Tipo", "Tienda", "Cantidad"])
        root.addWidget(self.tabla)
        self.lbl_total = QLabel(""); self.lbl_total.setStyleSheet(f"color:{_TEXT};font-weight:700;")
        root.addWidget(self.lbl_total)

        # ── traspaso entre almacenes ──
        tr = QHBoxLayout()
        self.cmb_orig = _combo(self._almacenes())
        self.cmb_dest = _combo(self._almacenes())
        self.in_qty = _inp("Cantidad"); self.in_qty.setFixedWidth(110)
        tr.addWidget(QLabel("Traspasar de:")); tr.addWidget(self.cmb_orig)
        tr.addWidget(QLabel("a:")); tr.addWidget(self.cmb_dest)
        tr.addWidget(self.in_qty)
        tr.addWidget(_btn("Traspasar", self._traspasar, primary=True))
        tr.addStretch()
        root.addLayout(tr)

    def _id_empresa(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _almacenes(self):
        opts = []
        try:
            for a in SA.listar_almacenes(self._id_empresa()):
                opts.append((f"{a.get('nombre')} [{a.get('tipo_almacen')}]", a.get("id")))
        except Exception as e:
            logger.warning("listar almacenes: %s", e)
        return opts or [("(sin almacenes)", None)]

    def _buscar(self):
        cod = self.in_cod.text().strip()
        if not cod:
            return
        data = SA.obtener_stock_articulo(cod, self._id_empresa())
        filas = data["detalle"]
        self.tabla.setRowCount(len(filas))
        for i, d in enumerate(filas):
            for j, v in enumerate([d.get("nombre"), d.get("tipo_almacen"),
                                   d.get("id_tienda"), d.get("cantidad")]):
                self.tabla.setItem(i, j, _it(v))
        self.lbl_total.setText(f"Total global: {data['total']}")

    def _traspasar(self):
        cod = self.in_cod.text().strip()
        if not cod:
            QMessageBox.information(self, "Traspaso", "Indica el código de artículo."); return
        orig, dest = self.cmb_orig.currentData(), self.cmb_dest.currentData()
        try:
            qty = int(self.in_qty.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Traspaso", "Cantidad no válida."); return
        if not orig or not dest or orig == dest:
            QMessageBox.warning(self, "Traspaso", "Selecciona almacén origen y destino distintos."); return
        ok = SA.traspasar_stock(cod, orig, dest, qty, id_empresa=self._id_empresa(),
                                usuario=(self.usuario or {}).get("nombre"))
        if ok:
            self.in_qty.clear(); self._buscar()
        else:
            QMessageBox.warning(self, "Traspaso", "No se pudo realizar el traspaso "
                                "(¿stock insuficiente en origen?).")
