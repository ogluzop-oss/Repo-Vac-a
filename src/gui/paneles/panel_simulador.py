"""
Panel Simulador (pestaña del Centro de Inteligencia Empresarial). Permite lanzar simulaciones
what-if VIRTUALES orquestando SOLO el SimulationService (nunca toca datos reales). Presenta el
impacto por métrica, el riesgo recalculado y la lista de escenarios.
"""

import logging

from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidgetItem

from src.gui.components import (EnterpriseFilter, EnterpriseRiskIndicator,
                                EnterpriseTable)
from src.gui.foundation import tokens as T
from src.gui.foundation.shell import QtEnterprisePanel

logger = logging.getLogger("gui.paneles.simulador")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


def _aviso(parent, titulo, msg, nivel="info"):
    try:
        from assets.estilo_global import mostrar_mensaje
        mostrar_mensaje(parent, titulo, msg, nivel=nivel)
    except Exception:
        pass


class _CompararDialog(QDialog):
    """Comparativa de varios escenarios frente al estado actual (`SimulationService.comparar`).
    Usa `_dialogo_frameless`/`_tabla` de `catalogo_gestion` — mismo precedente ya documentado en
    `panel_gobierno._FormDialog` para diálogos modales dentro de un panel Enterprise: la librería
    Enterprise (`gui/components`) no tiene un primitivo de diálogo modal propio."""

    def __init__(self, parent, resultado):
        super().__init__(parent)
        from src.gui.catalogo_gestion import _btn, _dialogo_frameless, _tabla
        v = _dialogo_frameless(self, "Comparar escenarios", ancho=640)
        tabla = _tabla(["Métrica", "Actual", "Escenario", "Valor", "Δ", "Δ %"])
        filas = [(f["metrica"], f["actual"], e.get("nombre"), e.get("valor"), e.get("delta"), e.get("delta_pct"))
                 for f in resultado.get("filas", []) for e in f.get("escenarios", [])]
        tabla.setRowCount(len(filas))
        for i, row in enumerate(filas):
            for j, val in enumerate(row):
                tabla.setItem(i, j, _it(val))
        tabla.setMinimumSize(600, 320)
        v.addWidget(tabla)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Cerrar", self.accept, primary=True))
        v.addLayout(fila)


class _EvaluarAgentesDialog(QDialog):
    """Evaluación por agentes IA de un escenario (`SimulationService.evaluar_con_agentes`) —
    titulares por dominio siempre presentes + el texto de cada agente cuando responde. Mismo
    precedente que `_CompararDialog` para el diálogo modal."""

    def __init__(self, parent, resultado):
        super().__init__(parent)
        from src.gui.catalogo_gestion import _btn, _dialogo_frameless, _tabla
        v = _dialogo_frameless(self, "Evaluación por agentes IA", ancho=640)
        tabla = _tabla(["Dominio", "Detalle"])
        filas = [(t.get("dominio"), t.get("texto")) for t in resultado.get("titulares", [])]
        filas += [(e.get("dominio"), f"[{e.get('agente')}] {e.get('texto')}")
                 for e in resultado.get("evaluaciones_agentes", [])]
        tabla.setRowCount(len(filas))
        for i, (dom, txt) in enumerate(filas):
            tabla.setItem(i, 0, _it(dom)); tabla.setItem(i, 1, _it(txt))
        tabla.setMinimumSize(600, 280)
        v.addWidget(tabla)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Cerrar", self.accept, primary=True))
        v.addLayout(fila)

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
        self.add_toolbar_widget(self._btn("Eliminar escenario", self._eliminar_escenario, T.CRITICO))
        self.add_toolbar_widget(self._btn("Comparar", self._comparar_escenarios, T.ANALISIS))
        self.add_toolbar_widget(self._btn("Evaluar con agentes", self._evaluar_agentes, T.ANALISIS))
        self.toolbar_stretch()
        self.riesgo = EnterpriseRiskIndicator("BAJO")
        self.add_toolbar_widget(self.riesgo)

        self.aviso = QLabel("Simulación VIRTUAL: no modifica ningún dato real.")
        self.aviso.setStyleSheet(f"color:{T.ADVERTENCIA};font-size:11px;")
        self.contenido.addWidget(self.aviso)

        self.contenido.addWidget(QLabel("Impacto por métrica"))
        self.tabla = EnterpriseTable(["Métrica", "Base", "Simulado", "Δ %"], con_busqueda=False,
                                     con_actualizar=self._simular, actualizar_pos="derecha",
                                     mostrar_contador=False)
        self.contenido.addWidget(self.tabla)

        self.contenido.addWidget(QLabel("Escenarios guardados (Ctrl+clic para seleccionar varios y comparar)"))
        self.tabla_esc = EnterpriseTable(["Id", "Nombre", "Estado", "Confianza"], con_busqueda=True,
                                         con_actualizar=self._cargar_escenarios, actualizar_pos="derecha",
                                         mostrar_contador=False)
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

    def _eliminar_escenario(self):
        r = self.tabla_esc.tabla.currentRow()
        if r < 0 or self.tabla_esc.tabla.item(r, 0) is None:
            self.set_status("Selecciona antes un escenario en la tabla.", "advertencia")
            _aviso(self, "Simulador", "Selecciona antes un escenario en la tabla.", "warning")
            return
        try:
            eid = int(self.tabla_esc.tabla.item(r, 0).text())
        except (TypeError, ValueError):
            return
        emp = _emp(self.id_empresa)
        try:
            from src.services import simulador
            ok = simulador.servicio().eliminar_escenario(eid, emp)
        except Exception as e:
            self.set_status(f"No se pudo eliminar el escenario: {e}", "critico")
            _aviso(self, "Simulador", f"No se pudo eliminar el escenario: {e}", "error")
            return
        if ok:
            self.set_status(f"Escenario #{eid} eliminado.", "ok")
            _aviso(self, "Simulador", f"Escenario #{eid} eliminado correctamente.", "success")
            self._cargar_escenarios()
        else:
            self.set_status(f"No se pudo eliminar el escenario #{eid}.", "critico")
            _aviso(self, "Simulador", f"No se pudo eliminar el escenario #{eid}.", "error")

    def _escenarios_seleccionados(self):
        ids = []
        for idx in self.tabla_esc.tabla.selectedIndexes():
            if idx.column() != 0:
                continue
            it = self.tabla_esc.tabla.item(idx.row(), 0)
            if it and it.text():
                try:
                    ids.append(int(it.text()))
                except ValueError:
                    pass
        return sorted(set(ids))

    def _comparar_escenarios(self):
        ids = self._escenarios_seleccionados()
        if len(ids) < 2:
            self.set_status("Selecciona 2 o más escenarios (Ctrl+clic) para compararlos.", "advertencia")
            _aviso(self, "Simulador", "Selecciona 2 o más escenarios en la tabla (Ctrl+clic) "
                  "para compararlos.", "warning")
            return
        emp = _emp(self.id_empresa)
        try:
            from src.services import simulador
            r = simulador.servicio().comparar(ids, emp)
        except Exception as e:
            self.set_status(f"No se pudo comparar: {e}", "critico")
            _aviso(self, "Simulador", f"No se pudo comparar los escenarios: {e}", "error")
            return
        _CompararDialog(self, r).exec()
        self.set_status(f"Comparados {len(ids)} escenarios.", "ok")
        _aviso(self, "Simulador", f"Comparación de {len(ids)} escenarios completada.", "success")

    def _evaluar_agentes(self):
        r = self.tabla_esc.tabla.currentRow()
        if r < 0 or self.tabla_esc.tabla.item(r, 0) is None:
            self.set_status("Selecciona antes un escenario en la tabla.", "advertencia")
            _aviso(self, "Simulador", "Selecciona antes un escenario en la tabla.", "warning")
            return
        try:
            eid = int(self.tabla_esc.tabla.item(r, 0).text())
        except (TypeError, ValueError):
            return
        emp = _emp(self.id_empresa)
        uid = self.usuario.get("nombre") if isinstance(self.usuario, dict) else None
        rol = (self.usuario.get("perfil") if isinstance(self.usuario, dict) else None) or "ADMINISTRADOR"
        try:
            from src.services import simulador
            r_ev = simulador.servicio().evaluar_con_agentes(eid, emp, usuario=uid, rol=rol)
        except Exception as e:
            self.set_status(f"No se pudo evaluar con agentes: {e}", "critico")
            _aviso(self, "Simulador", f"No se pudo evaluar el escenario con agentes: {e}", "error")
            return
        if "simulacion" not in r_ev:
            self.set_status(f"Escenario #{eid}: {r_ev.get('error') or 'sin datos de simulación'}", "critico")
            _aviso(self, "Simulador",
                  f"Escenario #{eid}: {r_ev.get('error') or 'sin datos de simulación'}.", "error")
            return
        _EvaluarAgentesDialog(self, r_ev).exec()
        self.set_status(f"Evaluación por agentes del escenario #{eid} completada.", "ok")
        _aviso(self, "Simulador", f"Evaluación por agentes del escenario #{eid} completada.", "success")

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
