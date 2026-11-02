"""
Tareas (restructuración Aprobaciones/Tareas, 2026-09).

Antes esta ventana era un módulo mixto ("Aprobaciones · Workflow/BPM") con 6 pestañas heterogéneas
(Pendientes, Diseñador, Automatización, Autonomía, Programador, Historial). Se ha segmentado: Pendientes
→ nuevo módulo "Aprobaciones" (`aprobaciones_gui.py`, filtrado a solo Autonomía IA/Automatización/riesgo
de crédito); Automatización → nuevo módulo "Automatización" (`automatizacion_gui.py`); Autonomía → nuevo
módulo "Autonomía IA" (`autonomia_ia_gui.py`); Diseñador e Historial se retiran por completo (Diseñador
sin ningún uso real detectado; Historial, auditoría genérica ya disponible en Seguridad).

Esta ventana ("Tareas", v_id="workflow" — se conserva el mismo v_id/routing para no romper nada externo
que lo referencie) conserva el Programador de Jobs TAL CUAL (tareas de FONDO internas de la app) y añade
un panel nuevo, "Tareas de tienda": encargos que un SUPERADMIN programa para el personal OPERARIO/
ADMINISTRADOR de la tienda a la que esté conectado (p. ej. "registrar la temperatura de las neveras"),
distinto del Programador (que planifica jobs de sistema, no encargos para una persona). Ver
`services.tareas_empleados` y `gui/paneles/panel_tareas_empleados.py`.
"""

import logging

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QTabWidget, QVBoxLayout, QWidget

from src.gui.catalogo_gestion import _BG, _CIAN, _btn_x
from src.gui.foundation import tokens as T

logger = logging.getLogger("workflow.gui")


class WorkflowWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Tareas")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(T.qss_tabs())
        root.addWidget(self.tabs)
        self._tab_tareas_tienda()
        # Programador de Jobs (tareas de FONDO internas de la app): SOLO SUPERADMIN.
        if str(self.usuario.get("perfil", "")).upper() == "SUPERADMIN":
            self._tab_programador()

    def _add_tab(self, w, titulo):
        """Añade una pestaña envuelta en un scroll de PÁGINA COMPLETA (las tablas no van apretadas)."""
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.Shape.NoFrame)
        sc.setStyleSheet("QScrollArea{background:transparent;border:none;}" + T.qss_scrollbar())
        sc.setWidget(w)
        self.tabs.addTab(sc, titulo)

    def _tab_tareas_tienda(self):
        try:
            from src.gui.paneles.panel_tareas_empleados import PanelTareasEmpleados
            self._add_tab(PanelTareasEmpleados(usuario=self.usuario), "Tareas de tienda")
        except Exception as e:
            logger.debug("tab tareas_tienda: %s", e)

    def _tab_programador(self):
        try:
            from src.gui.paneles.panel_jobs import PanelJobs
            self._add_tab(PanelJobs(usuario=self.usuario), "Programador")
        except Exception as e:
            logger.debug("tab programador: %s", e)
