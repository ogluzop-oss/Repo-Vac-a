"""
Panel Simulador (pestaña del Centro de Inteligencia Empresarial). Permite lanzar simulaciones
what-if VIRTUALES orquestando SOLO el SimulationService (nunca toca datos reales). Presenta el
impacto por métrica, el riesgo recalculado y la lista de escenarios.
"""

import logging

from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton

from src.gui.components import (EnterpriseFilter, EnterpriseRiskIndicator,
                                EnterpriseTable)
from src.gui.foundation import tokens as T
from src.gui.foundation.shell import QtEnterprisePanel

logger = logging.getLogger("gui.paneles.simulador")

_VARIABLES = [("Precio (%)", "precio"), ("Descuento (%)", "descuento"), ("Promoción (%)", "promocion"),
              ("Salario (%)", "salario"), ("Plantilla (±)", "plantilla"), ("Stock (%)", "stock"),
              ("Coste proveedor (%)", "proveedor"), ("Gastos (€)", "gastos"),
              ("Tiendas (±)", "tiendas"), ("Almacenes (±)", "almacenes")]


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


class PanelSimulador(QtEnterprisePanel):
    titulo = "Simulador"
    concepto = "simulador"

    def cargar(self):
        self.add_toolbar_widget(QLabel("¿Qué ocurriría si…?"))
        self.cmb = EnterpriseFilter(_VARIABLES)
        self.cmb.setFixedWidth(230)   # más ancho: no corta el texto de las opciones
        self.add_toolbar_widget(self.cmb)
        self.inp = QLineEdit()
        self.inp.setPlaceholderText("valor (p.ej. 5)")
        self.inp.setFixedWidth(120)
        self.inp.setStyleSheet(f"QLineEdit{{background:{T.BG2};color:{T.TEXT};border:2px solid {T.BORDE};"
                               f"border-radius:8px;padding:0 10px;}}")
        self.add_toolbar_widget(self.inp)
        self.add_toolbar_widget(self._btn("Simular", self._simular, T.INFO))
        self.add_toolbar_widget(self._btn("Crear escenario", self._crear_escenario, T.OK))
        self.toolbar_stretch()
        self.riesgo = EnterpriseRiskIndicator("BAJO")
        self.add_toolbar_widget(self.riesgo)

        self.aviso = QLabel("Simulación VIRTUAL: no modifica ningún dato real.")
        self.aviso.setStyleSheet(f"color:{T.ADVERTENCIA};font-size:11px;")
        self.contenido.addWidget(self.aviso)

        self.contenido.addWidget(QLabel("Impacto por métrica"))
        self.tabla = EnterpriseTable(["Métrica", "Base", "Simulado", "Δ %"], con_busqueda=False)
        self.contenido.addWidget(self.tabla)

        self.contenido.addWidget(QLabel("Escenarios guardados"))
        self.tabla_esc = EnterpriseTable(["Id", "Nombre", "Estado", "Confianza"], con_busqueda=True)
        self.contenido.addWidget(self.tabla_esc)

        self._cargar_escenarios()
        self.set_status("Selecciona una variable y un valor, y pulsa Simular.", "info")

    def _btn(self, txt, slot, color):
        from PyQt6.QtCore import Qt
        b = QPushButton(txt); b.clicked.connect(slot)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton{{background:{T.BG2};color:{color};border:2px solid {color};"
                        f"border-radius:8px;font-weight:800;font-size:14px;padding:5px 14px;}}"
                        f"QPushButton:hover{{background:{color};color:{T.BG};}}")
        return b

    def _variables(self):
        var = self.cmb.currentData()
        try:
            val = float((self.inp.text() or "0").replace(",", "."))
        except ValueError:
            val = 0.0
        return [{"variable": var, "valor": val}]

    def _simular(self):
        emp = _emp(self.id_empresa)
        try:
            from src.services import simulador
            r = simulador.servicio().simular_directo(self._variables(), emp)
        except Exception as e:
            self.set_status(f"Simulador no disponible: {e}", "critico")
            return
        filas = [{"Métrica": d["metrica"], "Base": d["base"], "Simulado": d["simulado"],
                  "Δ %": d["delta_pct"]} for d in r.get("diferencias", [])]
        self.tabla.set_datos(filas)
        self.riesgo.set_nivel((r.get("riesgo") or {}).get("nivel", "BAJO"))
        self.set_status(f"Simulación completada · confianza {r.get('confianza')} · VIRTUAL", "ok")

    def _crear_escenario(self):
        emp = _emp(self.id_empresa)
        var = self.cmb.currentData()
        try:
            from src.services import simulador
            svc = simulador.servicio()
            uid = self.usuario.get("nombre") if isinstance(self.usuario, dict) else None
            eid = svc.crear_escenario(f"Escenario {var}", usuario=uid, id_empresa=emp)
            v = self._variables()[0]
            getattr(svc, "añadir_variable")(eid, v["variable"], v["valor"], id_empresa=emp)
            svc.simular(eid, emp)
        except Exception as e:
            self.set_status(f"No se pudo crear el escenario: {e}", "critico")
            return
        self._cargar_escenarios()
        self.set_status(f"Escenario #{eid} creado y simulado (VIRTUAL).", "ok")

    def _cargar_escenarios(self):
        emp = _emp(self.id_empresa)
        filas = []
        try:
            from src.services import simulador
            for e in simulador.servicio().escenarios(emp):
                filas.append({"Id": e.get("id"), "Nombre": e.get("nombre"),
                              "Estado": e.get("estado"), "Confianza": e.get("confianza")})
        except Exception as e:
            logger.debug("escenarios: %s", e)
        self.tabla_esc.set_datos(filas)
