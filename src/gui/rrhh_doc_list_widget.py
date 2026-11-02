"""
Widget reutilizable RRHH: lista de documentos/registros de UN TIPO concreto, filtrada SIEMPRE al
empleado seleccionado en el desplegable de arriba de cada pestaña del sidebar de RRHH, con un
botón de reapertura por fila (PDF) o de apertura del registro.

Nace para evitar construir esta misma tabla ~8 veces (Contratos, Nóminas, Finiquitos,
Certificados de empresa, Certificados laborales, Cartas de despido, Periodo de prueba, Modelo
Fiscal Empleados) — mismo criterio de "librería visual única" que el resto de la app (ver
CLAUDE.md, sección Enterprise Shell): una sola implementación, cada pestaña la instancia con sus
propios `fetch_fn`/`abrir_fn`. No sustituye a `EnterpriseTable` (RRHH sigue con su propio look
`_tabla` de `catalogo_gestion.py`, igual que el resto de formularios inline hermanos —
`rrhh_baja_inline.py`, `rrhh_alta_inline.py`); es deliberadamente pequeño (Strangler Pattern: no
se crea un framework nuevo para esto).
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QPushButton, QTableWidgetItem, QVBoxLayout, QWidget

from assets.estilo_global import COLOR_CIAN
from src.gui.catalogo_gestion import _tabla

logger = logging.getLogger("gui.rrhh.doc_list")


class EmpleadoRegistrosList(QWidget):
    """Tabla de solo lectura con los registros/documentos de un tipo, filtrados al empleado
    indicado en la última llamada a `refrescar(id_empleado)`.

    - `columnas`: [(clave_o_callable, etiqueta), ...] — si `clave` es callable, recibe la fila
      (dict) y debe devolver el valor a mostrar; si es str, se usa `fila.get(clave)`.
    - `fetch_fn(id_empleado, id_empresa) -> list[dict]`: consulta ya existente de la capa de
      datos real (nunca un motor paralelo) — p.ej. `rrhh.db.contratos.listar_contratos`.
    - `id_empresa_getter`: callable sin argumentos (mismo patrón que el resto de formularios
      inline de RRHH).
    - `abrir_fn(fila)` (opcional): si se indica, añade una columna con un botón por fila que la
      invoca (reabrir el PDF con `plataforma.abrir_archivo`, o mostrar el detalle del registro).
    """

    def __init__(self, titulo, columnas, fetch_fn, id_empresa_getter, *, abrir_fn=None,
                 boton="Abrir", parent=None):
        super().__init__(parent)
        self._columnas = columnas
        self._fetch_fn = fetch_fn
        self._id_empresa = id_empresa_getter
        self._abrir_fn = abrir_fn
        self._boton_txt = boton
        self._filas = []

        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(6)
        lbl = QLabel(titulo.upper())
        lbl.setStyleSheet(
            f"color:{COLOR_CIAN};font-family:'Segoe UI';font-size:14px;font-weight:900;"
            "letter-spacing:1px;background:transparent;margin-top:6px;")
        root.addWidget(lbl)
        cabeceras = [et for _c, et in columnas] + ([boton] if abrir_fn else [])
        self.tbl = _tabla(cabeceras)
        self.tbl.setMinimumHeight(150)
        self.tbl.setMaximumHeight(220)
        root.addWidget(self.tbl)

    def refrescar(self, id_empleado):
        """Vuelve a consultar `fetch_fn` para `id_empleado` (o vacía la tabla si es None/0 —
        NUNCA muestra datos de otro empleado ni de "todos")."""
        if not id_empleado:
            self.tbl.setRowCount(0)
            self._filas = []
            return
        try:
            id_empresa = self._id_empresa() if self._id_empresa else None
            self._filas = self._fetch_fn(id_empleado, id_empresa) or []
        except Exception as e:
            logger.debug("EmpleadoRegistrosList.refrescar(%s): %s", id_empleado, e)
            self._filas = []
        n = len(self._columnas)
        self.tbl.setRowCount(len(self._filas))
        for i, fila in enumerate(self._filas):
            for j, (clave, _et) in enumerate(self._columnas):
                val = clave(fila) if callable(clave) else fila.get(clave)
                self.tbl.setItem(i, j, QTableWidgetItem("" if val is None else str(val)))
            if self._abrir_fn:
                btn = QPushButton(self._boton_txt)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(
                    f"QPushButton{{background:transparent;color:{COLOR_CIAN};"
                    f"border:1px solid {COLOR_CIAN};border-radius:6px;padding:3px 10px;"
                    "font-family:'Segoe UI';font-size:12px;font-weight:bold;}"
                    f"QPushButton:hover{{background:{COLOR_CIAN};color:#0E1117;}}")
                btn.clicked.connect(lambda _=False, f=fila: self._abrir_fn(f))
                self.tbl.setCellWidget(i, n, btn)
