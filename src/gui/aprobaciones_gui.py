"""
Aprobaciones — módulo de nivel superior propio (restructuración 2026-09). Antes era la pestaña
"Pendientes" embebida en el módulo mezclado "Aprobaciones"/"Tareas"; ahora es su propio módulo,
renombrada "Aprobaciones Pendientes", solo para SUPERADMIN.

Alcance restringido a propósito: tras retirar la pestaña "Diseñador" (sin ningún uso real detectado),
las ÚNICAS acciones del sistema que generan un paso de aprobación aquí son los planes de acción
sugeridos por Autonomía IA (`entidad="plan_ejecucion"`), las sugerencias que Automatización escala a
aprobación (`entidad="automatizacion"`) y las decisiones de riesgo de crédito
(`entidad="credito"`) — las 3 únicas definiciones de workflow que el motor autoprovisiona ahora que no
queda ninguna UI de Diseñador para darlas de alta a mano (ver
`workflow_engine._DEFINICIONES_SISTEMA`). Cualquier otra `entidad` que pudiera existir en datos
antiguos (pedidos de compra, tesorería, RRHH...) se filtra fuera de esta bandeja a propósito.
"""

import logging

from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QTableWidgetItem, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import _BG, _CIAN, _btn, _btn_cargando, _btn_x, _tabla
from src.services.workflow import workflow_engine as _E

logger = logging.getLogger("aprobaciones.gui")

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None


def _aviso(parent, titulo, msg, nivel="info"):
    if mostrar_mensaje is not None:
        mostrar_mensaje(parent, titulo, msg, nivel=nivel)

ENTIDADES_SISTEMA = ("plan_ejecucion", "automatizacion", "credito")


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


class AprobacionesWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Aprobaciones Pendientes")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        bar = QHBoxLayout()
        bar.addWidget(_btn("Aprobar", self._aprobar, primary=True))
        bar.addWidget(_btn("Rechazar", self._rechazar, danger=True))
        bar.addWidget(_btn("Cancelar flujo", self._cancelar_flujo, danger=True))
        bar.addStretch()
        bar.addWidget(_btn_cargando("🔄  Actualizar", self._cargar, primary=True))
        root.addLayout(bar)

        self.tbl = _tabla(["Tarea", "Instancia", "Origen", "Entidad ID", "Permiso", "Rol", "Estado"])
        self.tbl.cellClicked.connect(self._sel)
        root.addWidget(self.tbl)

        self._sel_tarea = None
        self._sel_instancia = None
        self._cargar()

    def _cargar(self):
        try:
            todas = _E.tareas_para_usuario(_actor(), id_empresa=_empresa())
            tareas = [t for t in todas if t.get("entidad") in ENTIDADES_SISTEMA]
            self.tbl.setRowCount(len(tareas))
            for i, t in enumerate(tareas):
                vals = [t["id"], t["id_instancia"], t.get("entidad"), t.get("entidad_id"),
                        t.get("permiso_requerido"), t.get("asignado_rol"), t["estado"]]
                for j, v in enumerate(vals):
                    self.tbl.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("_cargar: %s", e)

    def _sel(self, row, _c):
        try:
            self._sel_tarea = int(self.tbl.item(row, 0).text())
        except Exception:
            self._sel_tarea = None
        try:
            self._sel_instancia = int(self.tbl.item(row, 1).text())
        except Exception:
            self._sel_instancia = None

    def _aprobar(self):
        if not self._sel_tarea:
            _aviso(self, "Aprobaciones", "Selecciona antes una tarea en la tabla.", "warning")
            return
        try:
            r = _E.aprobar_tarea(self._sel_tarea, actor=_actor(), id_empresa=_empresa())
            _aviso(self, "Aprobaciones", f"Tarea aprobada (instancia → {r.get('estado')}).", "success")
            self._cargar()
        except Exception as e:
            _aviso(self, "Aprobaciones", f"No se pudo aprobar: {e}", "error")

    def _rechazar(self):
        if not self._sel_tarea:
            _aviso(self, "Aprobaciones", "Selecciona antes una tarea en la tabla.", "warning")
            return
        try:
            _E.rechazar_tarea(self._sel_tarea, actor=_actor(), comentario="rechazado", id_empresa=_empresa())
            _aviso(self, "Aprobaciones", "Tarea rechazada.", "success")
            self._cargar()
        except Exception as e:
            _aviso(self, "Aprobaciones", f"No se pudo rechazar: {e}", "error")

    def _cancelar_flujo(self):
        if not self._sel_instancia:
            _aviso(self, "Aprobaciones", "Selecciona antes una tarea en la tabla.", "warning")
            return
        try:
            _E.cancelar_flujo(self._sel_instancia, actor=_actor(), id_empresa=_empresa())
            _aviso(self, "Aprobaciones", f"Flujo (instancia #{self._sel_instancia}) cancelado.", "success")
            self._cargar()
        except Exception as e:
            _aviso(self, "Aprobaciones", f"No se pudo cancelar el flujo: {e}", "error")
