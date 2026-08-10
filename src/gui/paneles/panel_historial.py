"""
Panel Historial — pestaña alojada en Aprobaciones (Workflow). Historial unificado de aprobaciones,
ejecuciones y reversiones a partir de la auditoría existente (`auditoria_logs`). Solo lectura; no
duplica tablas ni lógica. Construido con componentes Enterprise.
"""

import logging

from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.gui.components import EnterpriseTable
from src.gui.foundation import tokens as T

logger = logging.getLogger("gui.paneles.historial")

# Prefijos de acción de auditoría relevantes para el ciclo Workflow/Automatización/Autonomía.
_PREFIJOS = ("WF_", "PLAN_", "ACCION_", "MODO_AUTONOMIA", "GEMELO_", "DELEGACION_")


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


class PanelHistorial(QWidget):
    def __init__(self, usuario=None, id_empresa=None, parent=None):
        super().__init__(parent)
        self.usuario = usuario or {}
        self.id_empresa = _emp(id_empresa)
        self.setStyleSheet(f"background:{T.BG};color:{T.TEXT};")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.addWidget(QLabel("Historial de aprobaciones, ejecuciones y reversiones"))
        # Botón Actualizar (emoji) integrado a la derecha de la barra de búsqueda de la tabla.
        self.tabla = EnterpriseTable(["Fecha", "Usuario", "Acción", "Detalle"], con_busqueda=True,
                                     pagina=20, con_actualizar=self._cargar)
        root.addWidget(self.tabla)
        self._cargar()

    def _cargar(self):
        emp = self.id_empresa
        filas = []
        try:
            from src.db.conexion import _filas_a_dicts, obtener_conexion
            like = " OR ".join(["accion LIKE %s"] * len(_PREFIJOS))
            params = [f"{p}%" for p in _PREFIJOS]
            with obtener_conexion() as c, c.cursor() as cur:
                cur.execute(f"SELECT fecha, usuario, accion, detalles FROM auditoria_logs "
                            f"WHERE ({like}) ORDER BY fecha DESC LIMIT 500", params)
                filas = _filas_a_dicts(cur, cur.fetchall())
        except Exception as e:
            logger.debug("historial: %s", e)
        self.tabla.set_datos([{"Fecha": str(f.get("fecha")), "Usuario": f.get("usuario"),
                               "Acción": f.get("accion"), "Detalle": f.get("detalles")} for f in filas])
