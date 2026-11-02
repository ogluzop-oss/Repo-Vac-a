"""
Multialmacén — GUI de stock por almacén (INV.4.9).

Pantalla NUEVA dentro de INVENTARIO (no modifica las existentes). Permite consultar las
existencias de un artículo desglosadas por almacén. La fuente de verdad es `stock_almacen`;
la caché de articulos se recalcula automáticamente. Multiempresa.

El traspaso entre almacenes que vivía aquí se retiró (Ajuste post-lanzamiento · Módulo 1): esa
función la cubre ahora el módulo de Logística (traspasos con documento/palé/trazabilidad completa).
`db.stock_almacen.traspasar_stock` sigue existiendo (usado por tests), solo se quitó de esta GUI.
"""

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QTableWidgetItem, QVBoxLayout, QWidget

from src.db import stock_almacen as SA
from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _TEXT, _btn, _btn_x, _inp, _tabla
from src.gui.components.completer_articulos import instalar_sugerencias_articulo


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
        t = QLabel("Stock almacenes")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        f = QHBoxLayout()
        self.in_cod = _inp("🔍 Código artículo"); self.in_cod.setFixedWidth(200)
        self.in_cod.returnPressed.connect(self._buscar)
        instalar_sugerencias_articulo(self.in_cod)
        f.addWidget(QLabel("Artículo:")); f.addWidget(self.in_cod)
        f.addWidget(_btn("🔍", self._buscar, primary=True))
        f.addWidget(_btn("Ver existencias", self._buscar, primary=True))
        f.addStretch()
        for w in f.parent().findChildren(QLabel) if f.parent() else []:
            w.setStyleSheet(f"color:{_DIM};")
        root.addLayout(f)

        self.tabla = _tabla(["Almacén", "Tipo", "Tienda", "Cantidad"])
        root.addWidget(self.tabla)
        self.lbl_total = QLabel(""); self.lbl_total.setStyleSheet(f"color:{_TEXT};font-weight:700;")
        root.addWidget(self.lbl_total)

    def _id_empresa(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _buscar(self):
        cod = self.in_cod.text().strip()
        if cod and "–" in cod:  # viene del autocompletado "CÓDIGO – NOMBRE"
            cod = cod.split("–")[0].strip()
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
