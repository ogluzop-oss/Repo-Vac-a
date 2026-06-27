"""
GUIs GMAO (BLOQUE 4): GMAODashboardWindow, ActivosWindow, PlanesMantenimientoWindow,
OrdenesTrabajoWindow. Reutilizan el estilo global y los servicios GMAO.
"""

import logging

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _tabla

logger = logging.getLogger("gui.gmao")


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


class GMAODashboardWindow(QWidget):
    """Cuadro de mando de mantenimiento: Activos, OT, Planes, KPIs."""
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("GMAO · Mantenimiento")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("Actualizar", self._load, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tabs = QTabWidget()
        self.tbl_act = _tabla(["ID", "Codigo", "Nombre", "Tipo", "Estado", "Criticidad"])
        self.tbl_ot = _tabla(["ID", "Codigo", "Tipo", "Activo", "Estado", "Prioridad"])
        self.tbl_plan = _tabla(["ID", "Codigo", "Nombre", "Frecuencia", "Proxima"])
        self.tbl_kpi = _tabla(["KPI", "Valor"])
        self.tabs.addTab(self.tbl_act, "Activos")
        self.tabs.addTab(self.tbl_ot, "Ordenes de trabajo")
        self.tabs.addTab(self.tbl_plan, "Planes")
        self.tabs.addTab(self.tbl_kpi, "KPIs")
        root.addWidget(self.tabs)
        self._load()

    def _load(self):
        eid = _empresa()
        try:
            from src.services.gmao import activos, analitica, ordenes, planes
            acts = activos.listar(id_empresa=eid)
            self.tbl_act.setRowCount(len(acts))
            for i, a in enumerate(acts):
                for j, v in enumerate([a.get("id"), a.get("codigo"), a.get("nombre"), a.get("tipo"),
                                       a.get("estado"), a.get("criticidad")]):
                    self.tbl_act.setItem(i, j, _it(v))
            ots = ordenes.listar(id_empresa=eid)
            self.tbl_ot.setRowCount(len(ots))
            for i, o in enumerate(ots):
                for j, v in enumerate([o.get("id"), o.get("codigo"), o.get("tipo"), o.get("id_activo"),
                                       o.get("estado"), o.get("prioridad")]):
                    self.tbl_ot.setItem(i, j, _it(v))
            pls = planes.listar(id_empresa=eid)
            self.tbl_plan.setRowCount(len(pls))
            for i, p in enumerate(pls):
                for j, v in enumerate([p.get("id"), p.get("codigo"), p.get("nombre"),
                                       p.get("frecuencia"), p.get("proxima_fecha")]):
                    self.tbl_plan.setItem(i, j, _it(v))
            k = analitica.kpis(id_empresa=eid)
            self.tbl_kpi.setRowCount(len(k))
            for i, (nombre, val) in enumerate(k.items()):
                self.tbl_kpi.setItem(i, 0, _it(nombre)); self.tbl_kpi.setItem(i, 1, _it(val))
            self.lbl.setText(f"MTTR: {k.get('mttr_horas', 0)}h · Disponibilidad: {k.get('disponibilidad_pct', 0)}%")
        except Exception as e:
            logger.error("load GMAO: %s", e)
            self.lbl.setText(f"Error: {e}")


class ActivosWindow(GMAODashboardWindow): """Vista de activos (reutiliza dashboard)."""
class PlanesMantenimientoWindow(GMAODashboardWindow): """Vista de planes (reutiliza dashboard)."""
class OrdenesTrabajoWindow(GMAODashboardWindow): """Vista de OT (reutiliza dashboard)."""
