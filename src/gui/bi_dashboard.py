"""
Business Intelligence — cuadro de mando (FASE BI-14).

Pantalla NUEVA. Muestra los KPIs por dominio (calculados al vuelo reutilizando el motor BI),
con filtro de periodo, forecasting de liquidez y exportación. Estilo dark+cian; empresa activa.
"""

import datetime as _dt
import logging

from PyQt6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QMessageBox, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _combo, _tabla
from src.services.bi import dashboard as _D
from src.services.bi import kpis as _K

logger = logging.getLogger("bi.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


class BIDashboardWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        try:
            _K.sincronizar_definiciones()
        except Exception:
            pass
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Business Intelligence · Cuadro de mando")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        self.cmb_periodo = _combo([("Mes", "mes"), ("Semana", "semana"), ("Día", "dia"), ("Año", "anio")])
        cab.addWidget(QLabel("Periodo:")); cab.addWidget(self.cmb_periodo)
        cab.addWidget(_btn("Calcular", self._load, primary=True))
        cab.addWidget(_btn("Exportar JSON", lambda: self._exportar("json")))
        cab.addWidget(_btn("Exportar CSV", lambda: self._exportar("csv")))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)

        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tbl = _tabla(["Dominio", "KPI", "Valor", "Unidad"])
        root.addWidget(self.tbl)
        self._dash = None
        self._load()

    def _load(self):
        try:
            per = self.cmb_periodo.currentData() or "mes"
            self._dash = _D.panel(_empresa(), periodo=per, con_forecast=True)
            filas = []
            for dom, items in self._dash["secciones"].items():
                for it in items:
                    filas.append((dom, it["nombre"], it["valor"], it.get("unidad")))
            self.tbl.setRowCount(len(filas))
            for i, (dom, nom, val, u) in enumerate(filas):
                for j, v in enumerate([dom, nom, f"{float(val):,.2f}", u]):
                    self.tbl.setItem(i, j, _it(v))
            fl = self._dash.get("forecast_liquidez", {})
            if fl.get("proyecciones"):
                p90 = next((p for p in fl["proyecciones"] if p["horizonte_dias"] == 90), None)
                if p90:
                    self.lbl.setText(f"Liquidez estimada a 90 días: {p90['liquidez_estimada']:.2f} €")
        except Exception as e:
            logger.error("load: %s", e)

    def _exportar(self, fmt):
        if not self._dash:
            return
        contenido = _D.exportar(self._dash, fmt)
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar BI", f"dashboard.{fmt}", f"{fmt.upper()} (*.{fmt})")
        if ruta:
            try:
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write(contenido)
                QMessageBox.information(self, "BI", "Exportado.")
            except Exception as e:
                QMessageBox.warning(self, "BI", str(e))
