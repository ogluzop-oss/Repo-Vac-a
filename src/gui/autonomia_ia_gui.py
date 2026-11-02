"""
Autonomía IA — módulo de nivel superior propio (extraído de la antigua pestaña "Autonomía" embebida en
Aprobaciones/Workflow-BPM, restructuración 2026-09). Mismo contenido exacto (`PanelAutonomia`), sin
cambios de lógica — solo cambia de casa: ahora es una tarjeta de menú propia, solo para SUPERADMIN.
"""

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from src.gui.catalogo_gestion import _BG, _CIAN, _btn_x
from src.gui.foundation import tokens as T


class AutonomiaIAWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Autonomía IA")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        from src.gui.paneles.panel_autonomia import PanelAutonomia
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.Shape.NoFrame)
        sc.setStyleSheet("QScrollArea{background:transparent;border:none;}" + T.qss_scrollbar())
        sc.setWidget(PanelAutonomia(usuario=self.usuario))
        root.addWidget(sc)
