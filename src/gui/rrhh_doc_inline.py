"""
Formulario INLINE genérico para documentos RRHH (altas, bajas, finiquitos, certificados, cartas…).
Sustituye al botón del asistente: los campos se rellenan directamente en la pestaña. Reutilizable:
recibe las secciones de campos, una función de autocompletado y el generador de PDF del documento.

Para la nómina existe un formulario específico (`rrhh_nomina_inline.NominaInlineForm`) con cálculo; el
resto de documentos usan este genérico (solo datos + generación).
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from assets.estilo_global import (
    COLOR_ACCION_TEXTO, COLOR_BORDE, COLOR_CIAN, COLOR_FONDO_WIDGET, mostrar_mensaje,
)

logger = logging.getLogger("gui.rrhh.doc_inline")

_INP_SS = (
    f"background:{COLOR_FONDO_WIDGET};color:#FFFFFF;border:1px solid {COLOR_BORDE};"
    f"border-radius:8px;padding:6px 10px;font-family:'Segoe UI';font-size:15px;"
)
_LBL_SS = "color:#C9D1D9;font-family:'Segoe UI';font-size:14px;font-weight:bold;background:transparent;"
# Desplegables: 1px menos que los campos de texto (petición del usuario).
_CB_SS = _INP_SS.replace("font-size:15px", "font-size:14px")


class DocumentoInlineForm(QWidget):
    def __init__(self, id_empresa_getter, secciones, generar_fn, *, tipo_doc="documento",
                 autollenar_fn=None, campos_grandes=(), campos_combo=None, parent=None):
        super().__init__(parent)
        self._id_empresa = id_empresa_getter
        self._secciones = secciones
        self._generar_fn = generar_fn
        self._tipo_doc = tipo_doc
        self._autollenar_fn = autollenar_fn
        self._campos_grandes = set(campos_grandes or ())
        self._campos_combo = dict(campos_combo or {})   # clave → [opciones]
        self._inputs = {}
        self._tablas = {}                                # clave → (QTableWidget, columnas)
        self._empleados = []
        self._build()
        self._cargar_empleados()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(10)

        top = QHBoxLayout(); top.setSpacing(10)
        top.addWidget(self._lbl("Empleado:"))
        self.cb_emp = QComboBox(); self.cb_emp.setMinimumWidth(280)
        self.cb_emp.setStyleSheet(f"QComboBox{{{_CB_SS}}}")
        self.cb_emp.currentIndexChanged.connect(self._on_empleado)
        top.addWidget(self.cb_emp, 1)
        top.addWidget(self._btn("Autocompletar", self._autollenar_actual))
        top.addStretch()
        root.addLayout(top)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        cont = QWidget(); self._form_ly = QVBoxLayout(cont)
        self._form_ly.setContentsMargins(2, 4, 12, 4); self._form_ly.setSpacing(14)
        for titulo, contenido in self._secciones:
            self._seccion(titulo)
            if isinstance(contenido, dict) and "tabla" in contenido:
                self._tabla_widget(*contenido["tabla"])
            else:
                self._grid(contenido)
        self._form_ly.addStretch()
        scroll.setWidget(cont)
        root.addWidget(scroll, 1)

        bottom = QHBoxLayout(); bottom.addStretch()
        bottom.addWidget(self._btn(f"Generar {self._tipo_doc} (PDF)", self._generar, primary=True))
        root.addLayout(bottom)

    def _lbl(self, txt):
        l = QLabel(txt); l.setStyleSheet(_LBL_SS); return l

    def _btn(self, txt, cb, primary=False):
        b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(40)
        if primary:
            b.setStyleSheet(
                f"QPushButton{{background:{COLOR_CIAN};color:{COLOR_ACCION_TEXTO};border:none;"
                f"border-radius:10px;padding:8px 18px;font-family:'Segoe UI';font-weight:bold;font-size:15px;}}"
                f"QPushButton:hover{{background:{COLOR_ACCION_TEXTO};color:{COLOR_CIAN};border:2px solid {COLOR_CIAN};}}")
        else:
            b.setStyleSheet(
                f"QPushButton{{background:transparent;color:{COLOR_CIAN};border:2px solid {COLOR_CIAN};"
                f"border-radius:10px;padding:8px 18px;font-family:'Segoe UI';font-weight:bold;font-size:15px;}}"
                f"QPushButton:hover{{background:{COLOR_CIAN};color:{COLOR_ACCION_TEXTO};}}")
        b.clicked.connect(cb); return b

    def _seccion(self, titulo):
        line = QFrame(); line.setFixedHeight(1); line.setStyleSheet(f"background:{COLOR_BORDE};")
        lbl = QLabel(titulo.upper())
        lbl.setStyleSheet(f"color:{COLOR_CIAN};font-family:'Segoe UI';font-size:15px;font-weight:900;"
                          "letter-spacing:1px;background:transparent;margin-top:4px;")
        self._form_ly.addWidget(lbl); self._form_ly.addWidget(line)

    def _grid(self, campos):
        grid = QGridLayout(); grid.setHorizontalSpacing(18); grid.setVerticalSpacing(8)
        col = 0; row = 0
        for clave, etiqueta in campos:
            grande = clave in self._campos_grandes
            cel = QVBoxLayout(); cel.setSpacing(2)
            cel.addWidget(self._lbl(etiqueta))
            if clave in self._campos_combo:
                inp = QComboBox(); inp.setStyleSheet(f"QComboBox{{{_CB_SS}}}")
                inp.addItems(list(self._campos_combo[clave]))
            elif grande:
                inp = QPlainTextEdit(); inp.setFixedHeight(70)
                inp.setStyleSheet(f"QPlainTextEdit{{{_INP_SS}}}")
            else:
                inp = QLineEdit(); inp.setStyleSheet(f"QLineEdit{{{_INP_SS}}}")
            self._inputs[clave] = inp
            cel.addWidget(inp)
            w = QWidget(); w.setLayout(cel)
            span = 2 if grande else 1
            grid.addWidget(w, row, col, 1, span)
            col += span
            if col >= 2:
                col = 0; row += 1
        holder = QWidget(); holder.setLayout(grid)
        self._form_ly.addWidget(holder)

    def _tabla_widget(self, clave, columnas, n_filas):
        """Tabla editable (p.ej. bases de cotización mensuales). `columnas`=[(subclave,label),...]."""
        tw = QTableWidget(n_filas, len(columnas))
        tw.setHorizontalHeaderLabels([lbl for _, lbl in columnas])
        tw.verticalHeader().setVisible(False)
        tw.setFixedHeight(min(n_filas, 8) * 34 + 34)
        tw.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tw.setStyleSheet(
            f"QTableWidget{{background:{COLOR_FONDO_WIDGET};color:#FFF;gridline-color:{COLOR_BORDE};"
            f"border:1px solid {COLOR_BORDE};border-radius:8px;font-family:'Segoe UI';font-size:15px;}}"
            f"QHeaderView::section{{background:{COLOR_FONDO_WIDGET};color:{COLOR_CIAN};font-weight:bold;"
            f"border:none;border-bottom:1px solid {COLOR_BORDE};padding:6px;}}")
        for r in range(n_filas):
            for c in range(len(columnas)):
                tw.setItem(r, c, QTableWidgetItem(""))
        self._tablas[clave] = (tw, columnas)
        self._form_ly.addWidget(tw)

    # ── Datos ─────────────────────────────────────────────────────────────────
    def _set(self, clave, valor):
        w = self._inputs.get(clave)
        if w is None:
            return
        txt = "" if valor is None else str(valor)
        if isinstance(w, QComboBox):
            i = w.findText(txt)
            if i >= 0:
                w.setCurrentIndex(i)
        elif isinstance(w, QPlainTextEdit):
            w.setPlainText(txt)
        else:
            w.setText(txt)

    def _get(self, w):
        if isinstance(w, QComboBox):
            return w.currentText().strip()
        return w.toPlainText().strip() if isinstance(w, QPlainTextEdit) else w.text().strip()

    def _recoger(self) -> dict:
        datos = {k: self._get(w) for k, w in self._inputs.items()}
        # Tablas → lista de dicts (solo filas con algún dato).
        for clave, (tw, columnas) in self._tablas.items():
            filas = []
            for r in range(tw.rowCount()):
                fila = {}
                vacia = True
                for c, (subclave, _) in enumerate(columnas):
                    it = tw.item(r, c)
                    val = it.text().strip() if it else ""
                    fila[subclave] = val
                    if val:
                        vacia = False
                if not vacia:
                    filas.append(fila)
            datos[clave] = filas
        return datos

    def _cargar_empleados(self):
        try:
            from src.rrhh.db import empleados
            self._empleados = empleados.listar_empleados(self._id_empresa(), estado="activo") or []
        except Exception as e:
            logger.debug("cargar empleados: %s", e); self._empleados = []
        self.cb_emp.blockSignals(True); self.cb_emp.clear()
        self.cb_emp.addItem("— Selecciona un empleado —", None)
        for e in self._empleados:
            nom = f"{e.get('nombre','')} {e.get('apellidos','')}".strip()
            self.cb_emp.addItem(f"{nom}  ·  {e.get('nif','')}", e)
        self.cb_emp.blockSignals(False)

    def _on_empleado(self, _i):
        emp = self.cb_emp.currentData()
        if emp:
            self._autollenar(emp)

    def _autollenar_actual(self):
        emp = self.cb_emp.currentData()
        if not emp:
            mostrar_mensaje(self, self._tipo_doc.capitalize(), "Selecciona primero un empleado.", "warning")
            return
        self._autollenar(emp)

    def _autollenar(self, emp):
        try:
            from src.db.empresa import datos_corporativos
            dc = datos_corporativos(self._id_empresa()) or {}
        except Exception:
            dc = {}
        if self._autollenar_fn:
            try:
                self._autollenar_fn(emp, dc, self._set)
            except Exception as e:
                logger.debug("autollenar_fn: %s", e)

    def _generar(self):
        datos = self._recoger()
        if not (datos.get("nif") or datos.get("nombre_completo") or datos.get("trab_nombre")):
            mostrar_mensaje(self, self._tipo_doc.capitalize(),
                            "Indica al menos el trabajador (nombre o NIF).", "warning")
            return
        try:
            ruta = self._generar_fn(datos)
            try:
                from src.db.documentos import registrar_documento
                registrar_documento(ruta, tipo=self._tipo_doc,
                                    nombre=ruta.replace("\\", "/").split("/")[-1],
                                    referencia=str(datos.get("nif") or ""))
            except Exception:
                pass
            mostrar_mensaje(self, self._tipo_doc.capitalize(),
                            f"Documento generado correctamente.", "success")
            try:
                from src.utils import plataforma
                plataforma.abrir_carpeta(ruta.replace("\\", "/").rsplit("/", 1)[0])
            except Exception:
                pass
        except Exception as e:
            logger.error("generar %s: %s", self._tipo_doc, e)
            mostrar_mensaje(self, self._tipo_doc.capitalize(), "No se pudo generar el documento.", "error")
