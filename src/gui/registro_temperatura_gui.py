"""
Registro Temperatura — módulo nuevo (restructuración Aprobaciones/Tareas, 2026-09). Control de cadena
de frío (neveras/cámaras/congeladores) registrado in situ por el personal OPERARIO/ADMINISTRADOR de
cada tienda. Solo disponible para esos dos roles — distinto de la TAREA "revisar temperaturas" que un
SUPERADMIN pueda programar en el módulo Tareas (aquello es el recordatorio; esto es la lectura real).

Sin selector de tienda: usa siempre la tienda propia del empleado (`usuario.centro_codigo`), igual que
el resto de módulos operativos de tienda — no hay concepto de "conectarse a otra tienda" para estos
roles.
"""

import logging

from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QMessageBox, QTableWidgetItem, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _btn_x, _combo, _inp, _tabla
from src.gui.foundation import tokens as T

logger = logging.getLogger("registro_temperatura.gui")

_EQUIPOS = ["Nevera", "Cámara frigorífica", "Congelador", "Vitrina refrigerada", "Otro"]


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class RegistroTemperaturaWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.id_tienda = self.usuario.get("centro_codigo")
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Temperaturas")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        if not self.id_tienda:
            aviso = QLabel("Tu usuario no tiene tienda asignada — no se puede registrar temperatura.")
            aviso.setStyleSheet(f"color:{T.ADVERTENCIA};font-size:13px;")
            root.addWidget(aviso)
            root.addStretch()
            return

        bar = QHBoxLayout()
        self.cmb_equipo = _combo([(e, e) for e in _EQUIPOS])
        self.cmb_equipo.setEditable(True)
        self.cmb_equipo.setMinimumWidth(200)
        self.in_valor = _inp("Temperatura (°C)", 140)
        self.in_obs = _inp("Observaciones (opcional)", 260)
        bar.addWidget(QLabel("Equipo:")); bar.addWidget(self.cmb_equipo)
        bar.addWidget(QLabel("Valor:")); bar.addWidget(self.in_valor)
        bar.addWidget(self.in_obs)
        bar.addStretch()
        bar.addWidget(_btn("Registrar", self._registrar, primary=True))
        root.addLayout(bar)

        self.status = QLabel("")
        self.status.setStyleSheet(f"color:{_DIM};font-size:11px;")
        root.addWidget(self.status)

        self.tbl = _tabla(["Equipo", "Valor (°C)", "Observaciones", "Usuario", "Fecha"])
        root.addWidget(self.tbl)

        self._cargar()

    def _uid(self):
        return self.usuario.get("id") if isinstance(self.usuario, dict) else None

    def _registrar(self):
        from src.services import registro_temperatura as RT
        equipo = (self.cmb_equipo.currentText() or "").strip()
        valor = (self.in_valor.text() or "").strip()
        obs = self.in_obs.text()
        r = RT.registrar(self.id_tienda, equipo, valor, usuario=self._uid(), observaciones=obs)
        if r.get("ok"):
            self.status.setStyleSheet(f"color:{_CIAN};font-size:11px;")
            self.status.setText("Temperatura registrada.")
            self.in_valor.clear(); self.in_obs.clear()
            self._cargar()
        else:
            self.status.setStyleSheet("color:#FF5C5C;font-size:11px;")
            self.status.setText(r.get("error", "No se pudo registrar."))

    def _cargar(self):
        from src.services import registro_temperatura as RT
        filas = RT.listar(self.id_tienda)
        self.tbl.setRowCount(len(filas))
        for i, f in enumerate(filas):
            vals = [f.get("equipo"), f.get("valor"), f.get("observaciones"), f.get("usuario"),
                    f.get("fecha_registro")]
            for j, v in enumerate(vals):
                self.tbl.setItem(i, j, _it(v))
