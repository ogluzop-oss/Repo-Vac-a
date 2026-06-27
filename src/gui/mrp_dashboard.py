"""
GUIs MRP / Fabricacion (BLOQUE 3): MRPDashboardWindow, BOMWindow, OrdenesFabricacionWindow,
FabricacionWindow. Reutilizan el estilo global y los servicios MRP. Operativo ligero.
"""

import logging

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _tabla

logger = logging.getLogger("gui.mrp")


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


class MRPDashboardWindow(QWidget):
    """Cuadro de mando de fabricacion: Ordenes, Sugerencias MRP, KPIs."""
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("MRP / Fabricacion · Cuadro de mando")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("Actualizar", self._load, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tabs = QTabWidget()
        self.tbl_of = _tabla(["ID", "Codigo", "Articulo", "Cant", "Producido", "Estado"])
        self.tbl_sug = _tabla(["Tipo", "Articulo", "Cantidad", "Estado"])
        self.tbl_kpi = _tabla(["KPI", "Valor"])
        self.tabs.addTab(self.tbl_of, "Ordenes")
        self.tabs.addTab(self.tbl_sug, "Sugerencias MRP")
        self.tabs.addTab(self.tbl_kpi, "KPIs")
        root.addWidget(self.tabs)
        self._load()

    def _load(self):
        eid = _empresa()
        try:
            from src.services.mrp import analitica, ordenes, planificador
            ofs = ordenes.listar(id_empresa=eid)
            self.tbl_of.setRowCount(len(ofs))
            for i, o in enumerate(ofs):
                for j, v in enumerate([o.get("id"), o.get("codigo"), o.get("articulo_final"),
                                       o.get("cantidad"), o.get("cantidad_producida"), o.get("estado")]):
                    self.tbl_of.setItem(i, j, _it(v))
            sug = planificador.listar_sugerencias(id_empresa=eid)
            self.tbl_sug.setRowCount(len(sug))
            for i, s in enumerate(sug):
                for j, v in enumerate([s.get("tipo"), s.get("articulo"), s.get("cantidad"), s.get("estado")]):
                    self.tbl_sug.setItem(i, j, _it(v))
            k = analitica.kpis(id_empresa=eid)
            self.tbl_kpi.setRowCount(len(k))
            for i, (nombre, val) in enumerate(k.items()):
                self.tbl_kpi.setItem(i, 0, _it(nombre)); self.tbl_kpi.setItem(i, 1, _it(val))
            self.lbl.setText(f"OF en curso: {k.get('of_en_curso', 0)} · Eficiencia: {k.get('eficiencia_pct', 0)}%")
        except Exception as e:
            logger.error("load MRP: %s", e)
            self.lbl.setText(f"Error: {e}")


class OrdenesFabricacionWindow(MRPDashboardWindow):
    """Vista centrada en ordenes de fabricacion (reutiliza el dashboard)."""


class BOMWindow(QWidget):
    """Listado de BOM por empresa."""
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Listas de materiales (BOM)")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("Actualizar", self._load, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        self.tbl = _tabla(["ID", "Articulo final", "Version", "Estado"])
        root.addWidget(self.tbl)
        self._load()

    def _load(self):
        from src.db.conexion import obtener_conexion
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT id, articulo_final, version, estado FROM bom WHERE id_empresa=%s "
                            "ORDER BY id DESC", (_empresa(),))
                filas = cur.fetchall()
            self.tbl.setRowCount(len(filas))
            for i, r in enumerate(filas):
                r = list(r.values()) if isinstance(r, dict) else r
                for j, v in enumerate(r):
                    self.tbl.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("load BOM: %s", e)


class FabricacionWindow(MRPDashboardWindow):
    """Alias operativo de fabricacion (reutiliza el dashboard)."""
