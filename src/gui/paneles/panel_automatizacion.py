"""
Panel Automatización — pestaña alojada en Aprobaciones (Workflow). Muestra reglas, ejecuciones y el
panel-resumen del AutomationService. Orquesta el servicio; no calcula ni ejecuta lógica de negocio.
Construido con componentes Enterprise. Aditivo (no altera las pestañas existentes de Workflow).
"""

import logging

from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.gui.components import (EnterpriseCard, EnterpriseDashboardGrid,
                                EnterpriseTable)
from src.gui.foundation import tokens as T

logger = logging.getLogger("gui.paneles.automatizacion")


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


class PanelAutomatizacion(QWidget):
    def __init__(self, usuario=None, id_empresa=None, parent=None):
        super().__init__(parent)
        self.usuario = usuario or {}
        self.id_empresa = _emp(id_empresa)
        self.setStyleSheet(f"background:{T.BG};color:{T.TEXT};")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        self.grid = EnterpriseDashboardGrid(columnas=4)
        root.addWidget(self.grid)

        # Cada tabla lleva su propio Actualizar (emoji) a la derecha de su barra de búsqueda.
        root.addWidget(QLabel("Reglas de automatización"))
        self.t_reglas = EnterpriseTable(["Código", "Nombre", "Disparador", "Acción", "Activa"],
                                        con_busqueda=True, con_actualizar=self._cargar)
        root.addWidget(self.t_reglas)

        root.addWidget(QLabel("Ejecuciones recientes"))
        self.t_ejec = EnterpriseTable(["Regla", "Acción", "Estado", "Creado"], con_busqueda=True,
                                      pagina=15, con_actualizar=self._cargar)
        root.addWidget(self.t_ejec)

        self._cargar()

    def _cargar(self):
        emp = self.id_empresa
        self.grid.limpiar()
        try:
            from src.services import automatizacion
            res = automatizacion.panel.resumen(emp) or {}
            for clave, etiqueta, concepto in (("total", "Ejecuciones", "automatizacion"),
                                              ("pendientes", "Pendientes", "tarea"),
                                              ("propuestas", "Propuestas", "info"),
                                              ("tiempo_ahorrado_min", "Min. ahorrados", "ok")):
                self.grid.add_card(EnterpriseCard(etiqueta, res.get(clave, 0), modo="kpi", concepto=concepto))
        except Exception as e:
            logger.debug("panel automatizacion: %s", e)

        try:
            from src.db.conexion import _filas_a_dicts, obtener_conexion
            with obtener_conexion() as c, c.cursor() as cur:
                cur.execute("SELECT codigo, nombre, trigger_tipo, accion, activa FROM "
                            "automatizaciones_reglas WHERE id_empresa=%s OR id_empresa IS NULL "
                            "ORDER BY codigo LIMIT 200", (emp,))
                reglas = _filas_a_dicts(cur, cur.fetchall())
                cur.execute("SELECT codigo_regla, accion, estado, creado FROM "
                            "automatizaciones_ejecuciones WHERE id_empresa=%s ORDER BY creado DESC LIMIT 200", (emp,))
                ejec = _filas_a_dicts(cur, cur.fetchall())
        except Exception as e:
            logger.debug("tablas automatizacion: %s", e)
            reglas, ejec = [], []
        self.t_reglas.set_datos([{"Código": r.get("codigo"), "Nombre": r.get("nombre"),
                                  "Disparador": r.get("trigger_tipo"), "Acción": r.get("accion"),
                                  "Activa": "Sí" if r.get("activa") else "No"} for r in reglas])
        self.t_ejec.set_datos([{"Regla": e.get("codigo_regla"), "Acción": e.get("accion"),
                                "Estado": e.get("estado"), "Creado": str(e.get("creado"))} for e in ejec])
