"""
CRM-I — Dashboard CRM. Secciones: Leads, Pipeline, Oportunidades, Actividades, Forecast,
CRM SaaS, KPIs. Reutiliza el estilo global y los servicios CRM. Read-only/operativo ligero.
"""

import logging

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _tabla

logger = logging.getLogger("gui.crm")


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


class CRMDashboardWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("CRM Comercial · Cuadro de mando")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("Actualizar", self._load, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)

        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)

        self.tabs = QTabWidget()
        self.tbl_leads = _tabla(["ID", "Nombre", "Empresa", "Estado", "Prioridad", "Valor", "Score"])
        self.tbl_ops = _tabla(["ID", "Titulo", "Estado", "Valor", "Prob %", "Cierre prev."])
        self.tbl_saas = _tabla(["Fase", "Nº"])
        self.tbl_kpi = _tabla(["KPI", "Valor"])
        self.tabs.addTab(self.tbl_leads, "Leads")
        self.tabs.addTab(self.tbl_ops, "Oportunidades")
        self.tabs.addTab(self.tbl_saas, "CRM SaaS")
        self.tabs.addTab(self.tbl_kpi, "KPIs / Forecast")
        root.addWidget(self.tabs)
        self._load()

    def _load(self):
        eid = _empresa()
        try:
            from src.services.crm import analitica, crm_saas, leads, oportunidades
            ls = leads.listar_leads(id_empresa=eid)
            self.tbl_leads.setRowCount(len(ls))
            for i, l in enumerate(ls):
                for j, v in enumerate([l.get("id"), l.get("nombre"), l.get("empresa"), l.get("estado"),
                                       l.get("prioridad"), l.get("valor_estimado"), l.get("score")]):
                    self.tbl_leads.setItem(i, j, _it(v))
            ops = oportunidades.listar(id_empresa=eid)
            self.tbl_ops.setRowCount(len(ops))
            for i, o in enumerate(ops):
                for j, v in enumerate([o.get("id"), o.get("titulo"), o.get("estado"), o.get("valor"),
                                       o.get("probabilidad"), o.get("fecha_cierre_prevista")]):
                    self.tbl_ops.setItem(i, j, _it(v))
            emb = crm_saas.embudo()
            self.tbl_saas.setRowCount(len(emb))
            for i, (f, n) in enumerate(emb.items()):
                self.tbl_saas.setItem(i, 0, _it(f)); self.tbl_saas.setItem(i, 1, _it(n))
            k = analitica.kpis(id_empresa=eid)
            self.tbl_kpi.setRowCount(len(k))
            for i, (nombre, val) in enumerate(k.items()):
                self.tbl_kpi.setItem(i, 0, _it(nombre)); self.tbl_kpi.setItem(i, 1, _it(val))
            self.lbl.setText(f"Forecast ponderado: {k.get('forecast', 0)} € · Conversión: {k.get('conversion_pct', 0)}%")
        except Exception as e:
            logger.error("load CRM: %s", e)
            self.lbl.setText(f"Error: {e}")
