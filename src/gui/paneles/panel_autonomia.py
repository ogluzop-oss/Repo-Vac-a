"""
Panel Autonomía Supervisada — pestaña alojada en Aprobaciones (Workflow). Orquesta SOLO el
ExecutiveActionService: modo de empresa, indicador de autonomía, lista de planes y el circuito
gobernado solicitar→aprobar→ejecutar(por fases)→revertir. Nunca ejecuta sin aprobación; las
acciones críticas quedan como propuesta (garantía 10.14 en el servicio). GUI = orquestación.
"""

import logging

from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                             QWidget)

from src.gui.components import (EnterpriseCard, EnterpriseDashboardGrid,
                                EnterpriseFilter, EnterpriseTable)
from src.gui.foundation import tokens as T

logger = logging.getLogger("gui.paneles.autonomia")

_MODOS = [("Manual", "MANUAL"), ("Asistida", "ASISTIDA"), ("Semiautomática", "SEMIAUTO"),
          ("Avanzada", "AVANZADA")]


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


def _svc():
    from src.services import autonomia
    return autonomia.servicio()


class PanelAutonomia(QWidget):
    def __init__(self, usuario=None, id_empresa=None, parent=None):
        super().__init__(parent)
        self.usuario = usuario or {}
        self.id_empresa = _emp(id_empresa)
        self.setStyleSheet(f"background:{T.BG};color:{T.TEXT};")
        self._plan_sel = None
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        self.grid = EnterpriseDashboardGrid(columnas=4)
        root.addWidget(self.grid)

        # Barra: modo de empresa + circuito
        barra = QHBoxLayout()
        barra.addWidget(QLabel("Modo de empresa:"))
        self.cmb_modo = EnterpriseFilter(_MODOS)
        self.cmb_modo.setFixedWidth(210)   # más ancho: no corta el texto de los modos
        barra.addWidget(self.cmb_modo)
        barra.addWidget(self._btn("Aplicar modo", self._aplicar_modo, T.ANALISIS))
        barra.addStretch(1)
        barra.addWidget(self._btn("Solicitar aprob.", self._solicitar, T.INFO))
        barra.addWidget(self._btn("Aprobar", self._aprobar, T.OK))
        barra.addWidget(self._btn("Ejecutar", self._ejecutar, T.INFO))
        barra.addWidget(self._btn("Revertir", self._revertir, T.CRITICO))
        root.addLayout(barra)

        self.aviso = QLabel("La IA propone, la organización decide, el sistema ejecuta solo lo "
                            "autorizado. Las acciones críticas quedan como propuesta.")
        self.aviso.setStyleSheet(f"color:{T.ADVERTENCIA};font-size:11px;")
        self.aviso.setWordWrap(True)
        root.addWidget(self.aviso)

        root.addWidget(QLabel("Planes de ejecución"))
        # Actualizar en la esquina superior derecha de la tabla; contador "N filas" abajo-izquierda.
        self.t_planes = EnterpriseTable(["Id", "Nombre", "Estado", "Riesgo", "Modo"], con_busqueda=True,
                                        con_actualizar=self._cargar, contador_abajo=True,
                                        actualizar_pos="derecha")
        self.t_planes.tabla.cellClicked.connect(self._sel_plan)
        root.addWidget(self.t_planes)

        self.status = QLabel("")
        self.status.setStyleSheet(f"color:{T.DIM};font-size:11px;")
        root.addWidget(self.status)

        self._cargar()

    def _btn(self, txt, slot, color):
        from PyQt6.QtCore import Qt
        b = QPushButton(txt); b.clicked.connect(slot)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton{{background:{T.BG2};color:{color};border:2px solid {color};"
                        f"border-radius:8px;font-weight:800;font-size:14px;padding:5px 12px;}}"
                        f"QPushButton:hover{{background:{color};color:{T.BG};}}")
        return b

    def _perfil(self):
        return (self.usuario.get("perfil") if isinstance(self.usuario, dict) else None) or "ADMINISTRADOR"

    def _uid(self):
        return self.usuario.get("nombre") if isinstance(self.usuario, dict) else None

    def _sel_plan(self, row, _col):
        it = self.t_planes.tabla.item(row, 0)
        self._plan_sel = int(it.text()) if it and it.text().isdigit() else None

    def _set_status(self, txt, rol="info"):
        self.status.setStyleSheet(f"color:{T.color(rol)};font-size:11px;")
        self.status.setText(txt)

    def _aplicar_modo(self):
        try:
            _svc().establecer_modo(self.cmb_modo.currentData(), self.id_empresa)
            self._set_status(f"Modo de empresa: {self.cmb_modo.currentData()}", "ok")
            self._cargar()
        except Exception as e:
            self._set_status(f"Error modo: {e}", "critico")

    def _requiere_plan(self):
        if not self._plan_sel:
            self._set_status("Selecciona un plan en la tabla.", "advertencia")
            return False
        return True

    def _solicitar(self):
        if not self._requiere_plan():
            return
        try:
            r = _svc().solicitar_aprobacion(self._plan_sel, usuario=self._uid(), perfil=self._perfil(),
                                            id_empresa=self.id_empresa)
            self._set_status(f"Plan #{self._plan_sel}: {r.get('estado')}", "info")
            self._cargar()
        except Exception as e:
            self._set_status(f"Error: {e}", "critico")

    def _aprobar(self):
        if not self._requiere_plan():
            return
        try:
            r = _svc().aprobar_plan(self._plan_sel, usuario=self._uid(), perfil=self._perfil(),
                                    id_empresa=self.id_empresa)
            ok = r.get("aprobado")
            self._set_status((f"Plan #{self._plan_sel} APROBADO" if ok else f"No aprobado: {r.get('motivo')}"),
                             "ok" if ok else "critico")
            self._cargar()
        except Exception as e:
            self._set_status(f"Error: {e}", "critico")

    def _ejecutar(self):
        if not self._requiere_plan():
            return
        try:
            r = _svc().ejecutar(self._plan_sel, usuario=self._uid(), perfil=self._perfil(),
                                id_empresa=self.id_empresa)
            if r.get("error"):
                self._set_status(f"No ejecutado: {r['error']}", "critico")
            else:
                self._set_status(f"Plan #{self._plan_sel} → {r.get('estado')} "
                                 "(críticas tramitadas como propuesta)", "ok")
            self._cargar()
        except Exception as e:
            self._set_status(f"Error: {e}", "critico")

    def _revertir(self):
        if not self._requiere_plan():
            return
        try:
            r = _svc().revertir(self._plan_sel, usuario=self._uid(), id_empresa=self.id_empresa)
            self._set_status(f"Plan #{self._plan_sel} revertido ({r.get('revertidas', 0)} acciones)", "advertencia")
            self._cargar()
        except Exception as e:
            self._set_status(f"Error: {e}", "critico")

    def _cargar(self):
        emp = self.id_empresa
        svc = _svc()
        self.grid.limpiar()
        try:
            db = svc.dashboard(emp)
            self.grid.add_card(EnterpriseCard("Automatización", f"{db.get('nivel_automatizacion_pct', 0)}%",
                                              modo="kpi", concepto="autonomia"))
            self.grid.add_card(EnterpriseCard("Ejecutados", db.get("planes_ejecutados", 0), modo="kpi", concepto="ok"))
            self.grid.add_card(EnterpriseCard("Reversiones", db.get("reversiones", 0), modo="kpi", concepto="riesgo"))
            self.grid.add_card(EnterpriseCard("Modo", db.get("modo_empresa", "-"), modo="estado", concepto="gobierno"))
        except Exception as e:
            logger.debug("dashboard autonomia: %s", e)
        try:
            filas = [{"Id": p.get("id"), "Nombre": p.get("nombre"), "Estado": p.get("estado"),
                      "Riesgo": p.get("riesgo"), "Modo": p.get("modo")} for p in svc.planes(emp)]
            self.t_planes.set_datos(filas)
        except Exception as e:
            logger.debug("planes: %s", e)
