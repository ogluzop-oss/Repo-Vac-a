"""
Panel Gemelo Digital (pestaña del Centro de Inteligencia Empresarial). Muestra el estado vivo por
dominios, el riesgo global, las alertas y un visor de dependencias, orquestando SOLO el
DigitalTwinService. No calcula nada: presenta lo que devuelve el servicio.
"""

import logging

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from src.gui.components import (EnterpriseCard, EnterpriseDashboardGrid,
                                EnterpriseRiskIndicator, EnterpriseTable)
from src.gui.foundation import tokens as T
from src.gui.foundation.shell import QtEnterprisePanel

logger = logging.getLogger("gui.paneles.gemelo")

_RIESGO_ROL = {"BAJO": "ok", "MEDIO": "advertencia", "ALTO": "critico"}


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


class PanelGemelo(QtEnterprisePanel):
    titulo = "Gemelo Digital"
    concepto = "gemelo"
    permiso = None

    def cargar(self):
        # Toolbar
        self.add_toolbar_widget(QLabel("Estado vivo de la organización"))
        self.toolbar_stretch()
        self.riesgo_global = EnterpriseRiskIndicator("BAJO")
        self.add_toolbar_widget(self.riesgo_global)
        # Botón Actualizar (emoji + texto)
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QPushButton
        b_ref = QPushButton("🔄 Actualizar")
        b_ref.setCursor(Qt.CursorShape.PointingHandCursor)
        b_ref.clicked.connect(self._refrescar)
        b_ref.setStyleSheet(T.qss_boton(T.INFO))
        self.add_toolbar_widget(b_ref)

        # Rejilla de dominios
        self.grid = EnterpriseDashboardGrid(columnas=3)
        self.contenido.addWidget(self.grid)

        # Tabla de alertas
        self.contenido.addWidget(QLabel("Alertas por dominio"))
        self.tabla_alertas = EnterpriseTable(["Dominio", "Alerta"], con_busqueda=True)
        self.contenido.addWidget(self.tabla_alertas)

        self._refrescar()

    def _refrescar(self):
        emp = _emp(self.id_empresa)
        try:
            from src.services import gemelo
            g = gemelo.servicio().estado_empresa(emp)
        except Exception as e:
            logger.error("estado_empresa: %s", e)
            self.set_status(f"Gemelo no disponible: {e}", "critico")
            return
        riesgo = str(g.get("riesgo_global", "BAJO")).upper()
        self.riesgo_global.set_nivel(riesgo)
        self.grid.limpiar()
        alertas = []
        for dom, est in (g.get("dominios") or {}).items():
            r = str(est.get("riesgo", "BAJO")).upper()
            self.grid.add_card(EnterpriseCard(
                str(dom).capitalize(), r, modo="riesgo", riesgo=r, concepto=self._concepto(dom),
                subtitulo=est.get("resumen", "")[:90]))
            for a in est.get("alertas", []):
                alertas.append({"Dominio": dom, "Alerta": a})
        self.tabla_alertas.set_datos(alertas)
        self.set_status(f"Riesgo global: {riesgo} · {len(alertas)} alertas · empresa {emp}",
                        _RIESGO_ROL.get(riesgo, "neutro"))

    def _concepto(self, dom):
        return {"empresa": "empresa", "inventario": "stock", "comercial": "dinero",
                "financiero": "dinero", "logistico": "tienda", "rrhh": "usuario"}.get(dom, "info")
