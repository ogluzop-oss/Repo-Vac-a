"""
Panel Programador (Jobs Opt-In) — pestaña alojada en Aprobaciones. Permite CONFIGURAR desde el ERP los
Jobs Enterprise (habilitar/deshabilitar, frecuencia, prioridad, timeout, reintentos) y ejecutarlos
manualmente. Orquesta SOLO el Scheduler existente (`services.scheduler` + `scheduler_registry`): no
crea motores nuevos ni lógica duplicada. La seguridad (permiso RBAC por job) y la auditoría (quién
cambió la config) las aplica el propio servicio.
"""

import logging

from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QVBoxLayout, QWidget)

from src.gui.components import EnterpriseFilter, EnterpriseTable
from src.gui.foundation import tokens as T

logger = logging.getLogger("gui.paneles.jobs")


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


class PanelJobs(QWidget):
    _COLS = ["Código", "Nombre", "Categoría", "Pesado", "Habilitado", "Frecuencia (h)",
             "Prioridad", "Timeout (s)", "Reintentos", "Última", "Próxima"]

    def __init__(self, usuario=None, id_empresa=None, parent=None):
        super().__init__(parent)
        self.usuario = usuario or {}
        self.id_empresa = _emp(id_empresa)
        self._sel = None
        self.setStyleSheet(f"background:{T.BG};color:{T.TEXT};")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        root.addWidget(QLabel("Programador de Jobs Enterprise (opt-in) — configurable desde el ERP"))
        self.tabla = EnterpriseTable(self._COLS, con_busqueda=True, con_actualizar=self._cargar)
        self.tabla.tabla.cellClicked.connect(self._sel_fila)
        root.addWidget(self.tabla)

        # Barra de configuración del job seleccionado.
        barra = QHBoxLayout()
        self.cmb_hab = EnterpriseFilter([("Habilitar", "1"), ("Deshabilitar", "0")])
        self.cmb_hab.setFixedWidth(150)
        self.in_freq = self._inp("Frecuencia (h)", 90)
        self.cmb_prio = EnterpriseFilter([("crítica", "critica"), ("alta", "alta"),
                                          ("normal", "normal"), ("baja", "baja")])
        self.cmb_prio.setFixedWidth(130)
        self.in_timeout = self._inp("Timeout (s)", 90)
        self.in_reint = self._inp("Reintentos", 80)
        barra.addWidget(QLabel("Estado:")); barra.addWidget(self.cmb_hab)
        barra.addWidget(QLabel("Frec.:")); barra.addWidget(self.in_freq)
        barra.addWidget(QLabel("Prioridad:")); barra.addWidget(self.cmb_prio)
        barra.addWidget(QLabel("Timeout:")); barra.addWidget(self.in_timeout)
        barra.addWidget(QLabel("Reint.:")); barra.addWidget(self.in_reint)
        barra.addWidget(self._btn("Guardar configuración", self._guardar, T.OK))
        barra.addWidget(self._btn("Ejecutar ahora", self._ejecutar, T.INFO))
        barra.addStretch(1)
        root.addLayout(barra)

        self.status = QLabel("")
        self.status.setStyleSheet(f"color:{T.DIM};font-size:11px;")
        root.addWidget(self.status)
        self._cargar()

    def _inp(self, ph, w):
        e = QLineEdit(); e.setPlaceholderText(ph); e.setFixedWidth(w)
        e.setStyleSheet(f"QLineEdit{{background:{T.BG2};color:{T.TEXT};border:2px solid {T.BORDE};"
                        f"border-radius:8px;padding:0 8px;}}")
        return e

    def _btn(self, txt, slot, color):
        from PyQt6.QtCore import Qt
        b = QPushButton(txt); b.clicked.connect(slot)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton{{background:{T.BG2};color:{color};border:2px solid {color};"
                        f"border-radius:8px;font-weight:800;padding:5px 12px;}}"
                        f"QPushButton:hover{{background:{color};color:{T.BG};}}")
        return b

    def _uid(self):
        return self.usuario.get("nombre") if isinstance(self.usuario, dict) else None

    def _set_status(self, txt, rol="info"):
        self.status.setStyleSheet(f"color:{T.color(rol)};font-size:11px;")
        self.status.setText(txt)

    def _cargar(self):
        from src.services import scheduler as S
        self._jobs = S.estado_jobs(self.id_empresa)
        filas = [{
            "Código": j["codigo"], "Nombre": j["nombre"], "Categoría": j["categoria"],
            "Pesado": "Sí" if j["pesado"] else "No", "Habilitado": "Sí" if j["habilitado"] else "No",
            "Frecuencia (h)": j["frecuencia_h"], "Prioridad": j["prioridad"],
            "Timeout (s)": j["timeout_seg"], "Reintentos": j["reintentos"],
            "Última": str(j["ultima"] or "—"), "Próxima": str(j["proxima"] or "—"),
        } for j in self._jobs]
        self.tabla.set_datos(filas)
        hab = len([j for j in self._jobs if j["habilitado"]])
        self._set_status(f"{len(self._jobs)} jobs · {hab} habilitados · "
                         f"{len([j for j in self._jobs if j['pesado']])} pesados (opt-in)", "info")

    def _sel_fila(self, row, _col):
        it = self.tabla.tabla.item(row, 0)
        self._sel = it.text() if it else None

    def _guardar(self):
        if not self._sel:
            self._set_status("Selecciona un job en la tabla.", "advertencia")
            return
        from src.services import scheduler as S
        kw = {"usuario": self._uid(), "id_empresa": self.id_empresa}
        kw["habilitado"] = (self.cmb_hab.currentData() == "1")
        kw["prioridad"] = self.cmb_prio.currentData()
        for campo, widget, cast in (("intervalo_horas", self.in_freq, int),
                                    ("timeout_seg", self.in_timeout, int),
                                    ("max_reintentos", self.in_reint, int)):
            t = (widget.text() or "").strip()
            if t:
                try:
                    kw[campo] = cast(t)
                except ValueError:
                    pass
        r = S.configurar_job(self._sel, **kw)
        if r.get("ok"):
            self._set_status(f"Configuración guardada para «{self._sel}».", "ok")
            self._cargar()
        else:
            self._set_status(f"No se pudo configurar: {r.get('motivo')}", "critico")

    def _ejecutar(self):
        if not self._sel:
            self._set_status("Selecciona un job en la tabla.", "advertencia")
            return
        from src.services import scheduler as S
        r = S.ejecutar_ahora(self._sel, usuario=self._uid(), id_empresa=self.id_empresa)
        if r.get("ok") is False:
            self._set_status(f"No ejecutado: {r.get('motivo')}", "critico")
        else:
            self._set_status(f"«{self._sel}» ejecutado: {r.get('estado')} "
                             f"({r.get('duracion_ms', 0)} ms)", "ok")
            self._cargar()
