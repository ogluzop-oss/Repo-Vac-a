"""
Compras avanzado (CMP) — GUI de devoluciones, incidencias, evaluación de proveedores y
condiciones/homologación.

Pantalla NUEVA (no modifica `compras_gestion.py`). Expone las capacidades CMP.1/3/4/8 sin
tocar el flujo principal proveedor→pedido→recepción→factura. Multiempresa por contexto.
"""

import logging

from PyQt6.QtWidgets import (QHBoxLayout, QInputDialog, QLabel, QMessageBox,
                             QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from src.db import compras as C, proveedores as P
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _TEXT, _btn, _combo, _inp, _tabla)

logger = logging.getLogger("compras.avanzado.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class ComprasAvanzadoWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Compras avanzado")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)

        tabs = QTabWidget()
        tabs.addTab(self._tab_proveedores(), "Proveedores / Homologación")
        tabs.addTab(self._tab_devoluciones(), "Devoluciones")
        tabs.addTab(self._tab_incidencias(), "Incidencias")
        tabs.addTab(self._tab_evaluacion(), "Evaluación")
        root.addWidget(tabs)

    def _emp(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _provs(self):
        return [(f"{p['razon_social']} ({p.get('cif_nif') or ''})", p["id_proveedor"])
                for p in P.listar_proveedores(self._emp())]

    # ── Proveedores / Homologación / Condiciones ──────────────────────────────
    def _tab_proveedores(self):
        w = QWidget(); ly = QVBoxLayout(w)
        self.cmb_prov = _combo(self._provs() or [("(sin proveedores)", None)])
        ly.addWidget(self.cmb_prov)
        b = QHBoxLayout()
        b.addWidget(_btn("Aprobar (homologar)", lambda: self._homolog("aprobado"), primary=True))
        b.addWidget(_btn("Suspender", lambda: self._homolog("suspendido")))
        b.addWidget(_btn("Bloquear", lambda: self._homolog("bloqueado"), danger=True))
        b.addWidget(_btn("Editar descuento", self._set_descuento))
        b.addStretch()
        ly.addLayout(b)
        self.lbl_cond = QLabel(""); self.lbl_cond.setStyleSheet(f"color:{_TEXT};")
        ly.addWidget(self.lbl_cond)
        self.cmb_prov.currentIndexChanged.connect(self._refresca_cond)
        self._refresca_cond()
        return w

    def _refresca_cond(self):
        pid = self.cmb_prov.currentData()
        if not pid:
            self.lbl_cond.setText(""); return
        c = P.condiciones_comerciales(pid, self._emp())
        self.lbl_cond.setText(f"Descuento {c.get('descuento')}% · plazo pago {c.get('plazo_pago')}d · "
                              f"lead time {c.get('lead_time_dias')}d · homologado {c.get('homologado')} · "
                              f"bloqueado {c.get('bloqueado')}")

    def _homolog(self, estado):
        pid = self.cmb_prov.currentData()
        if pid and C.set_homologacion_estado(pid, estado, self._emp()):
            self._refresca_cond()

    def _set_descuento(self):
        pid = self.cmb_prov.currentData()
        if not pid:
            return
        val, ok = QInputDialog.getDouble(self, "Descuento", "Descuento %:", 0, 0, 100, 2)
        if ok:
            P.actualizar_proveedor(pid, id_empresa=self._emp(), descuento=val)
            self._refresca_cond()

    # ── Devoluciones ──────────────────────────────────────────────────────────
    def _tab_devoluciones(self):
        w = QWidget(); ly = QVBoxLayout(w)
        f = QHBoxLayout()
        self.cmb_prov_dev = _combo(self._provs() or [("(sin proveedores)", None)])
        self.in_cod_dev = _inp("Código"); self.in_cod_dev.setFixedWidth(140)
        self.in_cant_dev = _inp("Cantidad"); self.in_cant_dev.setFixedWidth(90)
        self.in_lote_dev = _inp("Lote (opc.)"); self.in_lote_dev.setFixedWidth(110)
        for ww in (QLabel("Proveedor:"), self.cmb_prov_dev, self.in_cod_dev, self.in_cant_dev,
                   self.in_lote_dev):
            if isinstance(ww, QLabel):
                ww.setStyleSheet(f"color:{_DIM};")
            f.addWidget(ww)
        f.addWidget(_btn("Devolver", self._devolver, primary=True))
        ly.addLayout(f)
        self.tbl_dev = _tabla(["id", "Proveedor", "Total", "Estado", "Fecha"])
        ly.addWidget(self.tbl_dev)
        self._carga_dev()
        return w

    def _carga_dev(self):
        data = C.listar_devoluciones(self._emp())
        self.tbl_dev.setRowCount(len(data))
        for i, d in enumerate(data):
            for j, v in enumerate([d.get("id_devolucion"), d.get("id_proveedor"),
                                   d.get("total"), d.get("estado"), d.get("fecha")]):
                self.tbl_dev.setItem(i, j, _it(v))

    def _devolver(self):
        pid = self.cmb_prov_dev.currentData()
        cod = self.in_cod_dev.text().strip()
        try:
            cant = int(self.in_cant_dev.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Devolución", "Cantidad no válida."); return
        if not cod:
            QMessageBox.information(self, "Devolución", "Indica el código."); return
        did = C.crear_devolucion(id_proveedor=pid,
                                 lineas=[{"codigo": cod, "cantidad": cant,
                                          "lote": self.in_lote_dev.text().strip() or None}],
                                 usuario=(self.usuario or {}).get("nombre"), id_empresa=self._emp())
        if did:
            self.in_cod_dev.clear(); self.in_cant_dev.clear(); self.in_lote_dev.clear()
            self._carga_dev()
        else:
            QMessageBox.warning(self, "Devolución", "No se pudo registrar la devolución.")

    # ── Incidencias ───────────────────────────────────────────────────────────
    def _tab_incidencias(self):
        w = QWidget(); ly = QVBoxLayout(w)
        self.tbl_inc = _tabla(["id", "Tipo", "Artículo", "Cantidad", "Estado", "Fecha"])
        ly.addWidget(self.tbl_inc)
        ly.addWidget(_btn("Actualizar", self._carga_inc))
        self._carga_inc()
        return w

    def _carga_inc(self):
        data = C.listar_incidencias(self._emp())
        self.tbl_inc.setRowCount(len(data))
        for i, d in enumerate(data):
            for j, v in enumerate([d.get("id"), d.get("tipo"), d.get("codigo_articulo"),
                                   d.get("cantidad"), d.get("estado"), d.get("fecha")]):
                self.tbl_inc.setItem(i, j, _it(v))

    # ── Evaluación ────────────────────────────────────────────────────────────
    def _tab_evaluacion(self):
        w = QWidget(); ly = QVBoxLayout(w)
        self.cmb_prov_eval = _combo(self._provs() or [("(sin proveedores)", None)])
        ly.addWidget(self.cmb_prov_eval)
        ly.addWidget(_btn("Calcular KPIs", self._kpis, primary=True))
        self.lbl_kpis = QLabel(""); self.lbl_kpis.setStyleSheet(f"color:{_TEXT};font-weight:700;")
        ly.addWidget(self.lbl_kpis)
        return w

    def _kpis(self):
        pid = self.cmb_prov_eval.currentData()
        if not pid:
            return
        k = C.calcular_kpis_proveedor(pid, self._emp())
        self.lbl_kpis.setText(f"Valoración global: {k['valoracion_global']} · incidencias "
                              f"{k['incidencias']} · rechazos {k['rechazos']} · devoluciones "
                              f"{k['devoluciones']} · pedidos recibidos {k['pedidos_recibidos']}")
        C.registrar_evaluacion(pid, id_empresa=self._emp())
