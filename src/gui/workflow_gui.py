"""
Workflow · Bandeja de aprobaciones + Diseñador (FASE WF-3 / WF-11).

Pantalla NUEVA. Bandeja: tareas pendientes del usuario (aprobar/rechazar), e histórico.
Diseñador: lista de definiciones por empresa y alta de plantillas por defecto. Estilo dark+cian;
acotada a la empresa activa. Reutiliza el motor (resolución de aprobadores vía RBAC).
"""

import logging

from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QMessageBox, QTableWidgetItem, QTabWidget,
                             QVBoxLayout, QWidget)

from src.db import workflow as _W
from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _btn_x, _combo, _tabla
from src.gui.foundation import tokens as T
from src.services.workflow import plantillas as _P
from src.services.workflow import workflow_engine as _E

logger = logging.getLogger("workflow.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


def _actor():
    try:
        from src.db.usuario import sesion_global
        return getattr(sesion_global, "usuario_actual", None) or {}
    except Exception:
        return {}


class WorkflowWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Aprobaciones · Workflow / BPM")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        # (El botón Actualizar de la cabecera se retira: cada pestaña tiene su propio refresco.)
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(T.qss_tabs())   # mismo diseño de pestañas que el Centro de Inteligencia
        root.addWidget(self.tabs)
        self._tab_bandeja()
        self._tab_disenador()
        self._tab_enterprise()

    def _add_tab(self, w, titulo):
        """Añade una pestaña envuelta en un scroll de PÁGINA COMPLETA (las tablas no van apretadas)."""
        from PyQt6.QtWidgets import QScrollArea
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.Shape.NoFrame)
        sc.setStyleSheet("QScrollArea{background:transparent;border:none;}" + T.qss_scrollbar())
        sc.setWidget(w)
        self.tabs.addTab(sc, titulo)

    def _tab_enterprise(self):
        """Enterprise 4/10: Automatización, Autonomía Supervisada e Historial alojados en
        Aprobaciones (misma familia: propuesta→aprobación→ejecución). Aditivo y compatible."""
        for factory, titulo in ((self._panel_automatizacion, "Automatización"),
                                (self._panel_autonomia, "Autonomía"),
                                (self._panel_jobs, "Programador"),
                                (self._panel_historial, "Historial")):
            try:
                self._add_tab(factory(), titulo)
            except Exception as e:
                logger.debug("tab enterprise %s: %s", titulo, e)

    def _panel_automatizacion(self):
        from src.gui.paneles.panel_automatizacion import PanelAutomatizacion
        return PanelAutomatizacion(usuario=self.usuario)

    def _panel_autonomia(self):
        from src.gui.paneles.panel_autonomia import PanelAutonomia
        return PanelAutonomia(usuario=self.usuario)

    def _panel_jobs(self):
        from src.gui.paneles.panel_jobs import PanelJobs
        return PanelJobs(usuario=self.usuario)

    def _panel_historial(self):
        from src.gui.paneles.panel_historial import PanelHistorial
        return PanelHistorial(usuario=self.usuario)

    # ── Bandeja ───────────────────────────────────────────────────────────────
    def _tab_bandeja(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        bar.addWidget(_btn("Aprobar", self._aprobar, primary=True))
        bar.addWidget(_btn("Rechazar", self._rechazar, danger=True))
        bar.addStretch()
        bar.addWidget(_btn("🔄  Actualizar", self._load_bandeja))
        lay.addLayout(bar)
        self.tbl = _tabla(["Tarea", "Instancia", "Entidad", "Entidad ID", "Permiso", "Rol", "Estado"])
        self.tbl.cellClicked.connect(self._sel)
        lay.addWidget(self.tbl)
        self._add_tab(w, "Pendientes")
        self._sel_tarea = None
        self._load_bandeja()

    def _load_bandeja(self):
        try:
            tareas = _E.tareas_para_usuario(_actor(), id_empresa=_empresa())
            self.tbl.setRowCount(len(tareas))
            for i, t in enumerate(tareas):
                vals = [t["id"], t["id_instancia"], t.get("entidad"), t.get("entidad_id"),
                        t.get("permiso_requerido"), t.get("asignado_rol"), t["estado"]]
                for j, v in enumerate(vals):
                    self.tbl.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("load_bandeja: %s", e)

    def _sel(self, row, _c):
        try:
            self._sel_tarea = int(self.tbl.item(row, 0).text())
        except Exception:
            self._sel_tarea = None

    def _aprobar(self):
        if not self._sel_tarea:
            return
        try:
            _E.aprobar_tarea(self._sel_tarea, actor=_actor(), id_empresa=_empresa())
            self._load_bandeja()
        except Exception as e:
            QMessageBox.warning(self, "Workflow", str(e))

    def _rechazar(self):
        if not self._sel_tarea:
            return
        try:
            _E.rechazar_tarea(self._sel_tarea, actor=_actor(), comentario="rechazado", id_empresa=_empresa())
            self._load_bandeja()
        except Exception as e:
            QMessageBox.warning(self, "Workflow", str(e))

    # ── Diseñador ─────────────────────────────────────────────────────────────
    def _tab_disenador(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.cmb_ent = _combo([(e, e) for e in _P.PLANTILLAS])
        self.cmb_ent.setMinimumWidth(230)   # evita texto cortado en el desplegable
        bar.addWidget(QLabel("Entidad:")); bar.addWidget(self.cmb_ent)
        bar.addWidget(_btn("Crear plantilla", self._crear_plantilla, primary=True))
        bar.addWidget(_btn("Sembrar todas", self._seed))
        bar.addStretch()
        bar.addWidget(_btn("🔄  Actualizar", self._load_def))
        lay.addLayout(bar)
        self.tbl_def = _tabla(["ID", "Código", "Nombre", "Entidad", "Activo"])
        lay.addWidget(self.tbl_def)
        self._add_tab(w, "Diseñador")
        self._load_def()

    def _load_def(self):
        try:
            # Cliente fino (Fase 3): datos desde la capa de datos; la GUI solo orquesta.
            from src.db.workflow import listar_definiciones
            filas = listar_definiciones(_empresa())
            self.tbl_def.setRowCount(len(filas))
            for i, d in enumerate(filas):
                for j, v in enumerate([d["id"], d["codigo"], d["nombre"], d["entidad"], d["activo"]]):
                    self.tbl_def.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("load_def: %s", e)

    def _crear_plantilla(self):
        _P.crear_plantilla(self.cmb_ent.currentData(), id_empresa=_empresa())
        self._load_def()

    def _seed(self):
        _P.seed_plantillas(_empresa())
        self._load_def()

    def refrescar(self):
        self._load_bandeja(); self._load_def()
