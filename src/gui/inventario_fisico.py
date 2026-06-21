"""
Inventario físico (INV.2) — GUI de recuento e inventario auditado.

Pantalla NUEVA dentro de INVENTARIO (no modifica las existentes). Permite crear/abrir
inventarios, contar artículos, ver diferencias, cerrar (con ajuste auditado vía INV.1) y
consultar históricos. Multiempresa/multitienda por contexto activo. Reutiliza helpers de
catalogo_gestion.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QHBoxLayout, QInputDialog, QLabel, QMessageBox,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from src.db import inventario_fisico as inv
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _TEXT, _btn, _combo,
                                      _inp, _tabla)

logger = logging.getLogger("inventario.fisico.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class InventarioFisicoWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self._inv_id = None
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)

        cab = QHBoxLayout()
        t = QLabel("Inventario físico · Recuento auditado")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)

        # ── selector de inventario ──
        sel = QHBoxLayout()
        self.f_estado = _combo([("(todos)", None), ("BORRADOR", inv.BORRADOR),
                                ("ABIERTO", inv.ABIERTO), ("CERRADO", inv.CERRADO),
                                ("ANULADO", inv.ANULADO)])
        self.cmb_inv = _combo([])
        self.cmb_inv.currentIndexChanged.connect(self._cargar_lineas)
        sel.addWidget(QLabel("Estado:")); sel.addWidget(self.f_estado)
        self.f_estado.currentIndexChanged.connect(self._recargar)
        sel.addWidget(QLabel("Inventario:")); sel.addWidget(self.cmb_inv, 1)
        sel.addWidget(_btn("Nuevo", self._nuevo, primary=True))
        sel.addWidget(_btn("Abrir", self._abrir))
        sel.addWidget(_btn("Cerrar", self._cerrar))
        sel.addWidget(_btn("Anular", self._anular, danger=True))
        root.addLayout(sel)

        self.lbl_estado = QLabel(""); self.lbl_estado.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl_estado)

        # ── recuento ──
        rec = QHBoxLayout()
        self.in_cod = _inp("Código artículo"); self.in_cod.setFixedWidth(180)
        self.in_cant = _inp("Contado"); self.in_cant.setFixedWidth(110)
        rec.addWidget(QLabel("Contar:")); rec.addWidget(self.in_cod)
        rec.addWidget(self.in_cant)
        rec.addWidget(_btn("Registrar recuento", self._contar, primary=True))
        rec.addStretch()
        root.addLayout(rec)

        self.tabla = _tabla(["Artículo", "Esperado", "Contado", "Diferencia", "Observaciones"])
        root.addWidget(self.tabla)
        self.lbl_resumen = QLabel(""); self.lbl_resumen.setStyleSheet(f"color:{_TEXT};")
        root.addWidget(self.lbl_resumen)

        self._recargar()

    # ── helpers ──
    def _id_empresa(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _recargar(self):
        self.cmb_inv.blockSignals(True)
        self.cmb_inv.clear()
        for c in inv.listar_inventarios(self._id_empresa(), estado=self.f_estado.currentData()):
            self.cmb_inv.addItem(f"#{c['id']} · {c['nombre']} [{c['estado']}]", c["id"])
        self.cmb_inv.blockSignals(False)
        self._cargar_lineas()

    def _inv_actual(self):
        return self.cmb_inv.currentData()

    def _cargar_lineas(self):
        iid = self._inv_actual()
        self._inv_id = iid
        if not iid:
            self.tabla.setRowCount(0); self.lbl_estado.setText(""); self.lbl_resumen.setText("")
            return
        cab = inv.obtener_inventario(iid, self._id_empresa()) or {}
        self.lbl_estado.setText(f"Estado: {cab.get('estado','')} · tienda {cab.get('id_tienda')}")
        lineas = inv.listar_lineas(iid, self._id_empresa())
        self.tabla.setRowCount(len(lineas))
        for i, l in enumerate(lineas):
            for j, v in enumerate([l.get("codigo_articulo"), l.get("stock_esperado"),
                                   l.get("stock_contado"), l.get("diferencia"),
                                   l.get("observaciones")]):
                self.tabla.setItem(i, j, _it(v))
        r = inv.resumen(iid, self._id_empresa())
        self.lbl_resumen.setText(
            f"Líneas {r['lineas']} · contadas {r['contadas']} · con diferencia "
            f"{r['con_diferencia']} · sobrante +{r['sobrante']} · faltante {r['faltante']}")

    def _usuario(self):
        return (self.usuario or {}).get("nombre")

    # ── acciones ──
    def _nuevo(self):
        nombre, ok = QInputDialog.getText(self, "Nuevo inventario", "Nombre:")
        if not ok or not nombre.strip():
            return
        iid = inv.crear_inventario(nombre.strip(), id_empresa=self._id_empresa(),
                                   usuario=self._usuario())
        if iid:
            self._recargar()
            i = self.cmb_inv.findData(iid)
            if i >= 0:
                self.cmb_inv.setCurrentIndex(i)
        else:
            QMessageBox.warning(self, "Inventario", "No se pudo crear el inventario.")

    def _abrir(self):
        iid = self._inv_actual()
        if not iid:
            return
        try:
            inv.abrir_inventario(iid, self._id_empresa())
        except inv.InventarioError as e:
            QMessageBox.warning(self, "Inventario", str(e)); return
        self._recargar()

    def _anular(self):
        iid = self._inv_actual()
        if not iid:
            return
        if QMessageBox.question(self, "Anular", "¿Anular este inventario?") != \
                QMessageBox.StandardButton.Yes:
            return
        try:
            inv.anular_inventario(iid, self._id_empresa())
        except inv.InventarioError as e:
            QMessageBox.warning(self, "Inventario", str(e)); return
        self._recargar()

    def _contar(self):
        iid = self._inv_actual()
        if not iid:
            QMessageBox.information(self, "Inventario", "Selecciona un inventario."); return
        cod = self.in_cod.text().strip()
        try:
            cant = int(self.in_cant.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Inventario", "Cantidad contada no válida."); return
        try:
            inv.registrar_recuento(iid, cod, cant, id_empresa=self._id_empresa())
        except inv.InventarioError as e:
            QMessageBox.warning(self, "Inventario", str(e)); return
        self.in_cod.clear(); self.in_cant.clear()
        self._cargar_lineas()

    def _cerrar(self):
        iid = self._inv_actual()
        if not iid:
            return
        if QMessageBox.question(
                self, "Cerrar inventario",
                "Al cerrar se aplicarán los AJUSTES de stock auditados. ¿Continuar?") != \
                QMessageBox.StandardButton.Yes:
            return
        try:
            res = inv.cerrar_inventario(iid, usuario=self._usuario(), id_empresa=self._id_empresa())
        except inv.InventarioError as e:
            QMessageBox.warning(self, "Inventario", str(e)); return
        QMessageBox.information(self, "Inventario",
                               f"Inventario cerrado. Ajustes aplicados: {res['ajustes_aplicados']}.")
        self._recargar()
