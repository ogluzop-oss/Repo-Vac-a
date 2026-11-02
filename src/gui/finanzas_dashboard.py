"""
FASE H (GUI) — Dashboard financiero ejecutivo. Secciones: Tesoreria, Ratios/KPIs, Financiacion,
Credito/Riesgo. Reutiliza el estilo global y services.finanzas.dashboard. Solo lectura (salvo el umbral
de morosidad tolerada, editable en "Riesgo / Crédito").

Las recomendaciones de `services.finanzas.ia.recomendaciones()` ya NO se muestran aqui en una tabla
aislada de solo lectura: se emiten al circuito unico "la IA propone, un humano decide" que ya usa el
resto de la app (`services.finanzas.ia.registrar_en_automatizacion()` -> `services.automatizacion.acciones`
-> Centro/Automatizacion/Aprobaciones), via el job `fin_recomendaciones`
(`services.finanzas.dashboard.registrar_jobs_finanzas`).
"""

import logging

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QTabWidget, QVBoxLayout, QWidget

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _btn_cargando, _tabla

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
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"QTabBar::tab{{background:{_BG};color:{_DIM};padding:8px 14px;}}"
                                f"QTabBar::tab:selected{{color:{_CIAN};}}"
                                f"QTabWidget::pane{{border:none;}}")
        self.tbl_ratios = _tabla(["Ratio / KPI", "Valor"])
        self.tbl_fin = _tabla(["Indicador", "Valor"])
        self.tbl_alertas = _tabla(["Cliente", "Tipo", "Importe", "Estado"])
        self.tabs.addTab(self._envolver_ratios(self.tbl_ratios), "Ratios / KPIs")
        self.tabs.addTab(self._envolver(self.tbl_fin), "Tesorería / Deuda")
        self.tabs.addTab(self._envolver_riesgo(self.tbl_alertas), "Riesgo / Crédito")
        root.addWidget(self.tabs)
        self._load()

    def _envolver(self, tabla):
        """Tabla pegada directamente al borde de la pestaña: su contorno se veía más fino por
        arriba que por los otros lados — se le da un margen superior, igual que en el resto de
        la app (mismo criterio que `mrp_dashboard`/`bi_corporativo`)."""
        w = QWidget(); ly = QVBoxLayout(w)
        ly.setContentsMargins(0, 12, 0, 0)
        ly.addWidget(tabla)
        return w

    def _envolver_ratios(self, tabla):
        """Igual que `_envolver`, más el botón 'Actualizar' propio de esta subpestaña (antes vivía en la
        cabecera compartida de toda la ventana) — mismo patrón que `tesoreria_gui.py._tab_prevision`:
        una fila con el botón pegado a la esquina superior derecha, justo encima de la tabla."""
        w = QWidget(); ly = QVBoxLayout(w)
        ly.setContentsMargins(0, 12, 0, 0)
        top = QHBoxLayout()
        top.addStretch(1)
        top.addWidget(_btn_cargando("🔄  Actualizar", self._load, primary=True))
        ly.addLayout(top)
        ly.addWidget(tabla)
        return w

    def _envolver_riesgo(self, tabla):
        """Igual que `_envolver`, más una fila para fijar el % de morosidad TOLERADO de los propios
        clientes de esta empresa (afecta a la alerta de riesgo del Gemelo Financiero) — cada empresa
        decide su propia tolerancia, sin relación con la caducidad de su suscripción a Smart Manager."""
        w = QWidget(); ly = QVBoxLayout(w)
        ly.setContentsMargins(0, 12, 0, 0)
        fila = QHBoxLayout()
        lbl = QLabel("Morosidad de clientes tolerada antes de alerta:")
        lbl.setStyleSheet(f"color:{_DIM};")
        fila.addWidget(lbl)
        self.inp_morosidad = QLineEdit()
        self.inp_morosidad.setFixedWidth(70)
        self.inp_morosidad.setStyleSheet(
            f"QLineEdit{{background:{_BG};color:{_CIAN};border:2px solid {_CIAN};border-radius:6px;"
            f"padding:4px 8px;}}")
        fila.addWidget(self.inp_morosidad)
        fila.addWidget(QLabel("%", styleSheet=f"color:{_DIM};"))
        fila.addWidget(_btn("Guardar", self._guardar_morosidad, primary=True))
        fila.addStretch()
        ly.addLayout(fila)
        ly.addWidget(tabla)
        return w

    def _guardar_morosidad(self):
        from assets.estilo_global import mostrar_mensaje
        from src.services.facturacion import config as fact_cfg
        if fact_cfg.guardar_morosidad_tolerada(_empresa(), self.inp_morosidad.text()):
            mostrar_mensaje(self, "Morosidad tolerada", "Umbral guardado correctamente.", nivel="success")
        else:
            mostrar_mensaje(self, "Morosidad tolerada",
                            "Introduce un porcentaje válido (0-100).", nivel="warning")

    def _load(self):
        eid = _empresa()
        try:
            from src.services.facturacion import config as fact_cfg
            self.inp_morosidad.setText(str(fact_cfg.obtener_morosidad_tolerada(eid)))
        except Exception:
            pass
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
            rt = d.get("riesgo_tesoreria", {})
            self.lbl.setText(f"EBITDA: {ratios.get('ebitda', 0)} € · Riesgo tesoreria: {rt.get('nivel', '-')}")
        except Exception as e:
            logger.error("load finanzas: %s", e)
            self.lbl.setText(f"Error: {e}")
