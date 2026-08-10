"""
Centro de Inteligencia Empresarial — hub ejecutivo de Smart Manager AI.

Sustituye a la antigua ventana BI: deja de ser solo KPIs y se convierte en el lugar desde donde se
dirige toda la empresa. Contenedor único (Enterprise Shell, `QtEnterpriseWindow`) con 5 pestañas y
**lazy loading** (cada una se inicializa solo en su primer acceso):

    Dashboard Ejecutivo · Centro de Actividad (pilar) · Gemelo Digital · Predicción · Simulador

Las pestañas Dashboard y Centro de Actividad reutilizan las ventanas existentes embebidas
(`BIDashboardWindow`, `CentroActividadWindow`) — no se reescribe nada (compatibilidad + Strangler).
"""

import logging

from src.gui.foundation.shell import QtEnterpriseWindow

logger = logging.getLogger("gui.inteligencia")


class InteligenciaWindow(QtEnterpriseWindow):
    titulo_ventana = "Centro de Inteligencia Empresarial"
    concepto = "inteligencia"

    def _crear_pestanas(self):
        usuario, main = self.usuario, self.main

        # 1) Dashboard Ejecutivo — reutiliza la ventana BI existente (embebida, sin botón volver).
        def _dashboard():
            from src.gui.bi_dashboard import BIDashboardWindow
            return BIDashboardWindow(callback_vuelta=None, usuario=usuario, main=main)

        # 2) Centro de Actividad — PILAR (visión operativa). Reutiliza la ventana existente.
        def _actividad():
            from src.gui.centro_actividad import CentroActividadWindow
            return CentroActividadWindow(callback_vuelta=None, usuario=usuario, main=main)

        # 3-5) Paneles Enterprise (heredan de QtEnterprisePanel).
        def _gemelo():
            from src.gui.paneles.panel_gemelo import PanelGemelo
            return PanelGemelo(usuario=usuario, main=main)

        def _prediccion():
            from src.gui.paneles.panel_prediccion import PanelPrediccion
            return PanelPrediccion(usuario=usuario, main=main)

        def _simulador():
            from src.gui.paneles.panel_simulador import PanelSimulador
            return PanelSimulador(usuario=usuario, main=main)

        # BI Corporativo (multiempresa/OLAP/consolidación) — analítica corporativa dentro del hub.
        def _bi_corp():
            from src.gui.bi_corporativo import BICorporativoWindow
            return BICorporativoWindow(callback_vuelta=None, usuario=usuario, main=main)

        self.registrar_pestana("Dashboard Ejecutivo", _dashboard, concepto="dashboard")
        self.registrar_pestana("Centro de Actividad", _actividad, concepto="actividad", destacada=True)
        self.registrar_pestana("Gemelo Digital", _gemelo, concepto="gemelo")
        self.registrar_pestana("Predicción", _prediccion, concepto="prediccion")
        self.registrar_pestana("Simulador", _simulador, concepto="simulador")
        self.registrar_pestana("BI Corporativo", _bi_corp, concepto="dashboard")
