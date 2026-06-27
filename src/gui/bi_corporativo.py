"""
GUI BI Corporativo: BICorporativoWindow — cuadro de mando ejecutivo global sobre el DW.
Secciones (KPIs estrategicos / por dominio / alertas / IA) + ETL bajo demanda + export.
Reutiliza el estilo global. Aditivo: NO sustituye BIDashboardWindow existente.
"""

import logging

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QTabWidget, QVBoxLayout, QWidget

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _tabla

logger = logging.getLogger("gui.bi_corp")


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


class BICorporativoWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("BI Corporativo · Cuadro de mando ejecutivo")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("Recalcular DW", self._etl))
        cab.addWidget(_btn("Actualizar", self._load, primary=True))
        cab.addWidget(_btn("Exportar", self._export))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tabs = QTabWidget()
        self.tbl_kpi = _tabla(["KPI", "Valor", "Unidad"])
        self.tbl_sec = _tabla(["Seccion", "Metrica", "Valor"])
        self.tbl_alert = _tabla(["Tipo", "Severidad", "Mensaje"])
        self.tbl_ia = _tabla(["Categoria", "Detalle"])
        self.tabs.addTab(self.tbl_kpi, "KPIs estrategicos")
        self.tabs.addTab(self.tbl_sec, "Secciones")
        self.tabs.addTab(self.tbl_alert, "Alertas")
        self.tabs.addTab(self.tbl_ia, "IA ejecutiva")
        root.addWidget(self.tabs)
        self._panel = None
        self._load()

    def _etl(self):
        try:
            from src.services.bi_corp import dw
            r = dw.ejecutar_etl(id_empresa=_empresa())
            QMessageBox.information(self, "DW", f"ETL: {r['filas']} hechos actualizados")
            self._load()
        except Exception as e:
            QMessageBox.critical(self, "DW", str(e))

    def _load(self):
        try:
            from src.services.bi_corp import dashboard_corp
            p = dashboard_corp.panel(id_empresa=_empresa(), con_forecast=False, con_ia=True)
            self._panel = p
            kpis = p.get("kpis_estrategicos", [])
            self.tbl_kpi.setRowCount(len(kpis))
            for i, k in enumerate(kpis):
                for j, v in enumerate([k.get("etiqueta"), k.get("valor"), k.get("unidad")]):
                    self.tbl_kpi.setItem(i, j, _it(v))
            filas = [(s, m, val) for s, mets in p.get("secciones", {}).items() for m, val in mets.items()]
            self.tbl_sec.setRowCount(len(filas))
            for i, (s, m, val) in enumerate(filas):
                for j, v in enumerate([s, m, val]):
                    self.tbl_sec.setItem(i, j, _it(v))
            al = p.get("alertas", [])
            self.tbl_alert.setRowCount(len(al))
            for i, a in enumerate(al):
                for j, v in enumerate([a.get("tipo"), a.get("severidad"), a.get("mensaje")]):
                    self.tbl_alert.setItem(i, j, _it(v))
            ia = p.get("ia_ejecutiva", {})
            ia_filas = [("resumen", ia.get("resumen"))] + \
                       [("riesgo", r.get("motivo")) for r in ia.get("riesgos", [])] + \
                       [("recomendacion", r.get("accion")) for r in ia.get("recomendaciones", [])]
            self.tbl_ia.setRowCount(len(ia_filas))
            for i, (c, d) in enumerate(ia_filas):
                self.tbl_ia.setItem(i, 0, _it(c)); self.tbl_ia.setItem(i, 1, _it(d))
            self.lbl.setText(ia.get("resumen", "Panel corporativo actualizado."))
        except Exception as e:
            logger.error("load BI corp: %s", e)
            self.lbl.setText(f"Error: {e}")

    def _export(self):
        if not self._panel:
            return
        try:
            from src.services.bi_corp import dashboard_corp
            r = dashboard_corp.exportar_panel(self._panel, "xlsx")
            QMessageBox.information(self, "Export", r.get("ruta") if r.get("ok") else "Error")
        except Exception as e:
            QMessageBox.critical(self, "Export", str(e))
