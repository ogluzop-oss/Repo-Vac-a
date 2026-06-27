"""
FASE H (GUI) — Dashboard financiero ejecutivo. Secciones: Tesoreria, Ratios/KPIs, Financiacion,
Credito/Riesgo, Presupuestos, Anomalias IA, Recomendaciones. Reutiliza el estilo global y
services.finanzas.dashboard. Solo lectura.
"""

import logging

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _tabla

logger = logging.getLogger("gui.finanzas")


def _it(v):
    from PyQt6.QtWidgets import QTableWidgetItem
    return QTableWidgetItem("" if v is None else str(v))


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


class FinanzasDashboardWindow(QWidget):
    """Cuadro de mando financiero corporativo."""
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Finanzas · Cuadro de mando ejecutivo")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("Actualizar", self._load, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tabs = QTabWidget()
        self.tbl_ratios = _tabla(["Ratio / KPI", "Valor"])
        self.tbl_fin = _tabla(["Indicador", "Valor"])
        self.tbl_alertas = _tabla(["Cliente", "Tipo", "Importe", "Estado"])
        self.tbl_rec = _tabla(["Prioridad", "Tipo", "Accion"])
        self.tabs.addTab(self.tbl_ratios, "Ratios / KPIs")
        self.tabs.addTab(self.tbl_fin, "Tesoreria / Deuda")
        self.tabs.addTab(self.tbl_alertas, "Riesgo / Credito")
        self.tabs.addTab(self.tbl_rec, "Recomendaciones IA")
        root.addWidget(self.tabs)
        self._load()

    def _load(self):
        eid = _empresa()
        try:
            from src.services.finanzas import dashboard
            d = dashboard.panel(id_empresa=eid)
            ratios = d.get("ratios", {})
            self.tbl_ratios.setRowCount(len(ratios))
            for i, (k, v) in enumerate(ratios.items()):
                self.tbl_ratios.setItem(i, 0, _it(k)); self.tbl_ratios.setItem(i, 1, _it(v))
            tes = d.get("tesoreria", {}); deuda = d.get("deuda", {})
            fin_rows = list(tes.items()) + [("deuda_total", deuda.get("total"))]
            self.tbl_fin.setRowCount(len(fin_rows))
            for i, (k, v) in enumerate(fin_rows):
                self.tbl_fin.setItem(i, 0, _it(k)); self.tbl_fin.setItem(i, 1, _it(v))
            al = d.get("alertas_credito", [])
            self.tbl_alertas.setRowCount(len(al))
            for i, a in enumerate(al):
                for j, v in enumerate([a.get("id_cliente"), a.get("tipo"), a.get("importe"), a.get("estado")]):
                    self.tbl_alertas.setItem(i, j, _it(v))
            rec = d.get("recomendaciones", [])
            self.tbl_rec.setRowCount(len(rec))
            for i, r in enumerate(rec):
                for j, v in enumerate([r.get("prioridad"), r.get("tipo"), r.get("accion")]):
                    self.tbl_rec.setItem(i, j, _it(v))
            rt = d.get("riesgo_tesoreria", {})
            self.lbl.setText(f"EBITDA: {ratios.get('ebitda', 0)} € · Riesgo tesoreria: {rt.get('nivel', '-')}")
        except Exception as e:
            logger.error("load finanzas: %s", e)
            self.lbl.setText(f"Error: {e}")
