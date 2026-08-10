"""
CRM — Ficha avanzada de clientes (VTA.1).

Pantalla NUEVA. Búsqueda/listado + alta + edición de crédito/segmento + historial comercial
(ventas/devoluciones/saldo) + puntos de fidelización. Multiempresa. No modifica el TPV.
"""

import logging

from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                             QDoubleSpinBox, QFormLayout, QHBoxLayout, QInputDialog,
                             QLabel, QLineEdit, QMessageBox, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from src.db import clientes as CL
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _TEXT, _btn, _btn_x, _inp, _tabla)

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
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        f = QHBoxLayout()
        self.in_busca = _inp("Buscar (nombre/NIF/email)")
        f.addWidget(self.in_busca)
        f.addWidget(_btn("Buscar", self._buscar, primary=True))
        f.addWidget(_btn("Nuevo", self._nuevo))
        f.addWidget(_btn("Editar crédito/segmento", self._editar))
        f.addWidget(_btn("Fiscalidad", self._fiscalidad))
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

    def _fiscalidad(self):
        """Edita los atributos fiscales del cliente (FASE 3.1): el CRM es el ORIGEN
        ÚNICO de decisión fiscal de la factura (IVA/recargo/ISP/intracom/IRPF)."""
        c = self._sel()
        if not c:
            return
        c = CL.obtener_cliente(c["id"]) or c
        dlg = QDialog(self)
        dlg.setWindowTitle("Fiscalidad del cliente")
        dlg.setStyleSheet(f"background:{_BG};color:{_TEXT};")
        form = QFormLayout(dlg)
        cb_reg = QComboBox(); cb_reg.addItems(list(CL.REGIMENES_FISCALES))
        cb_reg.setCurrentText((c.get("regimen_fiscal") or "general"))
        in_nifiva = QLineEdit(c.get("nif_iva") or "")
        cb_vies = QComboBox(); cb_vies.addItems(["", "pendiente", "valido", "invalido"])
        cb_vies.setCurrentText(c.get("validacion_vies") or "")
        ck_recargo = QCheckBox("Aplica recargo de equivalencia")
        ck_recargo.setChecked(bool(int(c.get("aplica_recargo_equivalencia") or 0)))
        ck_isp = QCheckBox("Operación con inversión del sujeto pasivo (ISP)")
        ck_isp.setChecked(bool(int(c.get("aplica_isp") or 0)))
        ck_irpf = QCheckBox("Retención de IRPF")
        ck_irpf.setChecked(bool(int(c.get("aplica_retencion_irpf") or 0)))
        sp_irpf = QDoubleSpinBox(); sp_irpf.setRange(0, 100); sp_irpf.setSuffix(" %")
        sp_irpf.setValue(float(c.get("porcentaje_retencion") or 0))
        in_cond = QLineEdit(c.get("condiciones_pago") or "")
        in_cond.setPlaceholderText("contado / 15 / 30 / 60 / 30-60-90")
        form.addRow("Régimen fiscal:", cb_reg)
        form.addRow("NIF-IVA (intracom.):", in_nifiva)
        form.addRow("Validación VIES:", cb_vies)
        form.addRow("", ck_recargo)
        form.addRow("", ck_isp)
        form.addRow("", ck_irpf)
        form.addRow("% retención IRPF:", sp_irpf)
        form.addRow("Condiciones de pago:", in_cond)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        reg = cb_reg.currentText()
        CL.actualizar_cliente(
            c["id"], id_empresa=self._emp(),
            regimen_fiscal=reg,
            nif_iva=in_nifiva.text().strip() or None,
            validacion_vies=cb_vies.currentText() or None,
            aplica_recargo_equivalencia=1 if ck_recargo.isChecked() else 0,
            aplica_isp=1 if ck_isp.isChecked() else 0,
            aplica_retencion_irpf=1 if ck_irpf.isChecked() else 0,
            porcentaje_retencion=sp_irpf.value() if ck_irpf.isChecked() else None,
            es_intracomunitario=1 if reg == "intracomunitario" else 0,
            es_extranjero=1 if reg == "extranjero" else 0,
            condiciones_pago=in_cond.text().strip() or None)
        self._buscar()

    def _historial(self):
        c = self._sel()
        if not c:
            return
        h = CL.historial_comercial(c["id"], self._emp())
        self.lbl.setText(f"{c['nombre']}: ventas {len(h['ventas'])} ({h['total_ventas']}) · "
                         f"devoluciones {len(h['devoluciones'])} ({h['total_devoluciones']}) · "
                         f"saldo {h['saldo']}")
