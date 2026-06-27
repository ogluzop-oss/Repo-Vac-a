"""
GUIs Calidad (BLOQUE 3): CalidadDashboardWindow, InspeccionesWindow, NoConformidadesWindow,
CAPAWindow, AuditoriasWindow. Reutilizan el estilo global y los servicios de calidad.
"""

import logging

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _tabla

logger = logging.getLogger("gui.calidad")


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


class CalidadDashboardWindow(QWidget):
    """Cuadro de mando de calidad: Inspecciones, NC, CAPA, Auditorias, KPIs."""
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Calidad · Cuadro de mando")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("Actualizar", self._load, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tabs = QTabWidget()
        self.tbl_insp = _tabla(["ID", "Fase", "Articulo", "Inspecc.", "Rechaz.", "Resultado"])
        self.tbl_nc = _tabla(["ID", "Codigo", "Origen", "Severidad", "Estado"])
        self.tbl_capa = _tabla(["ID", "Tipo", "NC", "Estado"])
        self.tbl_aud = _tabla(["ID", "Codigo", "Tipo", "Estado", "Resultado"])
        self.tbl_kpi = _tabla(["KPI", "Valor"])
        self.tabs.addTab(self.tbl_insp, "Inspecciones")
        self.tabs.addTab(self.tbl_nc, "No conformidades")
        self.tabs.addTab(self.tbl_capa, "CAPA")
        self.tabs.addTab(self.tbl_aud, "Auditorias")
        self.tabs.addTab(self.tbl_kpi, "KPIs")
        root.addWidget(self.tabs)
        self._load()

    def _load(self):
        eid = _empresa()
        try:
            from src.services.calidad import (analitica, auditorias, capa, inspecciones,
                                              no_conformidades)
            ins = inspecciones.listar(id_empresa=eid)
            self.tbl_insp.setRowCount(len(ins))
            for i, x in enumerate(ins):
                for j, v in enumerate([x.get("id"), x.get("fase"), x.get("articulo"),
                                       x.get("cantidad_inspeccionada"), x.get("cantidad_rechazada"),
                                       x.get("resultado")]):
                    self.tbl_insp.setItem(i, j, _it(v))
            ncs = no_conformidades.listar(id_empresa=eid)
            self.tbl_nc.setRowCount(len(ncs))
            for i, x in enumerate(ncs):
                for j, v in enumerate([x.get("id"), x.get("codigo"), x.get("origen"),
                                       x.get("severidad"), x.get("estado")]):
                    self.tbl_nc.setItem(i, j, _it(v))
            cps = capa.listar(id_empresa=eid)
            self.tbl_capa.setRowCount(len(cps))
            for i, x in enumerate(cps):
                for j, v in enumerate([x.get("id"), x.get("tipo"), x.get("id_nc"), x.get("estado")]):
                    self.tbl_capa.setItem(i, j, _it(v))
            auds = auditorias.listar(id_empresa=eid)
            self.tbl_aud.setRowCount(len(auds))
            for i, x in enumerate(auds):
                for j, v in enumerate([x.get("id"), x.get("codigo"), x.get("tipo"),
                                       x.get("estado"), x.get("resultado")]):
                    self.tbl_aud.setItem(i, j, _it(v))
            k = analitica.kpis(id_empresa=eid)
            self.tbl_kpi.setRowCount(len(k))
            for i, (nombre, val) in enumerate(k.items()):
                self.tbl_kpi.setItem(i, 0, _it(nombre)); self.tbl_kpi.setItem(i, 1, _it(val))
            self.lbl.setText(f"Tasa rechazo: {k.get('tasa_rechazo_pct', 0)}% · NC abiertas: {k.get('nc_abiertas', 0)}")
        except Exception as e:
            logger.error("load calidad: %s", e)
            self.lbl.setText(f"Error: {e}")


class InspeccionesWindow(CalidadDashboardWindow): """Vista de inspecciones (reutiliza dashboard)."""
class NoConformidadesWindow(CalidadDashboardWindow): """Vista de NC (reutiliza dashboard)."""
class CAPAWindow(CalidadDashboardWindow): """Vista de CAPA (reutiliza dashboard)."""
class AuditoriasWindow(CalidadDashboardWindow): """Vista de auditorias (reutiliza dashboard)."""
