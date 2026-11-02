"""
Pestaña INLINE "Modelo Fiscal Empleados" (Modelo 145 AEAT) — Fase B2 del plan de RRHH/IRPF.

Mismo patrón que `rrhh_contrato_inline.py`/`rrhh_nomina_inline.py`: selector de empleado arriba,
formulario debajo, botones de acción abajo. Persiste en `rrhh_datos_fiscales` +
`rrhh_datos_fiscales_hijos`/`_ascendientes` (`src.rrhh.db.datos_fiscales`, patrón "borrar e
insertar" para las tablas hijas) y dispara `IRPFCalculatorService` para recalcular el % de IRPF tras
cada guardado. El PDF lo genera `src.rrhh.documents.render.render_modelo145`.

Completamente independiente de `FiscalWindow`/`fiscal_gui.py` (facturación electrónica AEAT):
este módulo es RRHH/nómina (comunicación de datos al pagador), no facturación.
"""

import datetime as _dt
import json
import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from assets.estilo_global import (
    COLOR_ACCION_TEXTO, COLOR_BORDE, COLOR_CIAN, COLOR_FONDO_WIDGET, mostrar_mensaje,
)
from src.gui.rrhh_doc_list_widget import EmpleadoRegistrosList
from src.rrhh.documents.render.render_modelo145 import (
    GRADOS_DISCAPACIDAD, SITUACIONES_FAMILIARES,
)

logger = logging.getLogger("gui.rrhh.modelo145_inline")

_INP_SS = (
    f"background:{COLOR_FONDO_WIDGET};color:#FFFFFF;border:1px solid {COLOR_BORDE};"
    f"border-radius:8px;padding:6px 10px;font-family:'Segoe UI';font-size:15px;"
)
_LBL_SS = "color:#C9D1D9;font-family:'Segoe UI';font-size:14px;font-weight:bold;background:transparent;"
_CB_SS = _INP_SS.replace("font-size:15px", "font-size:14px")

# (código interno, etiqueta) — mismos códigos que `render_modelo145`/`irpf_calculator`/BD.
_SITUACIONES = [(k, v) for k, v in SITUACIONES_FAMILIARES.items()]
_GRADOS = [(k, v) for k, v in GRADOS_DISCAPACIDAD.items()]


def _num(txt, default=None):
    txt = (txt or "").strip().replace(",", ".")
    if not txt:
        return default
    try:
        return float(txt)
    except ValueError:
        return default


def _int(txt, default=None):
    v = _num(txt, default)
    return int(v) if v is not None else default


class Modelo145InlineForm(QWidget):
    def __init__(self, id_empresa_getter, parent=None):
        super().__init__(parent)
        self._id_empresa = id_empresa_getter
        self._empleados = []
        self._empleado_actual_id = None
        self._build()
        self._cargar_empleados()

    # ── UI ──────────────────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(10)

        top = QHBoxLayout(); top.setSpacing(10)
        top.addWidget(self._lbl("Empleado:"))
        self.cb_emp = QComboBox(); self.cb_emp.setMinimumWidth(280)
        self.cb_emp.setStyleSheet(f"QComboBox{{{_CB_SS}}}")
        self.cb_emp.currentIndexChanged.connect(self._on_empleado)
        top.addWidget(self.cb_emp, 1)
        top.addStretch()
        root.addLayout(top)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        cont = QWidget(); self._form_ly = QVBoxLayout(cont)
        self._form_ly.setContentsMargins(2, 4, 12, 4); self._form_ly.setSpacing(14)

        # ── 1. Perceptor ─────────────────────────────────────────────────────────
        self._seccion("1. Perceptor")
        self._lbl_ident = QLabel("—")
        self._lbl_ident.setStyleSheet("color:#8B98A5;font-family:'Segoe UI';font-size:13px;"
                                      "background:transparent;")
        self._form_ly.addWidget(self._lbl_ident)

        grid1 = QGridLayout(); grid1.setHorizontalSpacing(18); grid1.setVerticalSpacing(8)
        grid1.addWidget(self._lbl("Situación familiar"), 0, 0)
        self.cb_situacion = QComboBox(); self.cb_situacion.setStyleSheet(f"QComboBox{{{_CB_SS}}}")
        for cod, et in _SITUACIONES:
            self.cb_situacion.addItem(et, cod)
        self.cb_situacion.currentIndexChanged.connect(self._on_situacion)
        grid1.addWidget(self.cb_situacion, 1, 0)
        grid1.addWidget(self._lbl("NIF del cónyuge (solo situación 2ª)"), 0, 1)
        self.in_nif_conyuge = QLineEdit(); self.in_nif_conyuge.setStyleSheet(f"QLineEdit{{{_INP_SS}}}")
        grid1.addWidget(self.in_nif_conyuge, 1, 1)
        holder1 = QWidget(); holder1.setLayout(grid1); self._form_ly.addWidget(holder1)

        grid2 = QGridLayout(); grid2.setHorizontalSpacing(18); grid2.setVerticalSpacing(8)
        grid2.addWidget(self._lbl("Discapacidad del trabajador/a"), 0, 0)
        self.cb_discapacidad = QComboBox(); self.cb_discapacidad.setStyleSheet(f"QComboBox{{{_CB_SS}}}")
        for cod, et in _GRADOS:
            self.cb_discapacidad.addItem(et, cod)
        grid2.addWidget(self.cb_discapacidad, 1, 0)
        holder2 = QWidget(); holder2.setLayout(grid2); self._form_ly.addWidget(holder2)

        self.chk_ayuda = QCheckBox("Necesita ayuda de terceras personas o movilidad reducida")
        self.chk_ayuda.setStyleSheet(_LBL_SS)
        self._form_ly.addWidget(self.chk_ayuda)
        self.chk_movilidad = QCheckBox("Movilidad geográfica (cambio de residencia por motivos de empleo)")
        self.chk_movilidad.setStyleSheet(_LBL_SS)
        self._form_ly.addWidget(self.chk_movilidad)
        self.chk_rentas_irreg = QCheckBox("Percibe rentas con período de generación superior a 2 años "
                                          "(irregularidad de rentas)")
        self.chk_rentas_irreg.setStyleSheet(_LBL_SS)
        self._form_ly.addWidget(self.chk_rentas_irreg)

        # ── 2. Hijos y otros descendientes ──────────────────────────────────────
        self._seccion("2. Hijos y otros descendientes")
        self.tbl_hijos = self._crear_tabla(
            ["Año nacimiento", "Año adopción", "Grado discapacidad", "Cómputo por entero", ""])
        self._form_ly.addWidget(self.tbl_hijos)
        bar_h = QHBoxLayout()
        bar_h.addWidget(self._btn("+ Añadir hijo/descendiente", lambda: self._fila_hijo()))
        bar_h.addStretch()
        self._form_ly.addLayout(bar_h)

        # ── 3. Ascendientes ──────────────────────────────────────────────────────
        self._seccion("3. Ascendientes")
        self.tbl_ascendientes = self._crear_tabla(
            ["Año nacimiento", "Grado discapacidad", "Convive con otros descendientes", ""])
        self._form_ly.addWidget(self.tbl_ascendientes)
        bar_a = QHBoxLayout()
        bar_a.addWidget(self._btn("+ Añadir ascendiente", lambda: self._fila_ascendiente()))
        bar_a.addStretch()
        self._form_ly.addLayout(bar_a)

        # ── 4. Pensiones compensatorias y anualidades por alimentos ─────────────
        self._seccion("4. Pensiones compensatorias y anualidades por alimentos")
        grid4 = QGridLayout(); grid4.setHorizontalSpacing(18); grid4.setVerticalSpacing(8)
        grid4.addWidget(self._lbl("Pensión compensatoria al cónyuge (€/año)"), 0, 0)
        self.in_pension = QLineEdit(); self.in_pension.setStyleSheet(f"QLineEdit{{{_INP_SS}}}")
        self.in_pension.setPlaceholderText("0,00")
        grid4.addWidget(self.in_pension, 1, 0)
        grid4.addWidget(self._lbl("Anualidades por alimentos a los hijos (€/año)"), 0, 1)
        self.in_anualidades = QLineEdit(); self.in_anualidades.setStyleSheet(f"QLineEdit{{{_INP_SS}}}")
        self.in_anualidades.setPlaceholderText("0,00")
        grid4.addWidget(self.in_anualidades, 1, 1)
        holder4 = QWidget(); holder4.setLayout(grid4); self._form_ly.addWidget(holder4)

        # ── 5. Vivienda habitual ─────────────────────────────────────────────────
        self._seccion("5. Deducción por vivienda habitual")
        self.chk_vivienda = QCheckBox("Pagos por adquisición/rehabilitación de vivienda habitual con "
                                      "derecho a deducción (contrato anterior al 1/1/2013)")
        self.chk_vivienda.setStyleSheet(_LBL_SS)
        self._form_ly.addWidget(self.chk_vivienda)

        # Modelos 145 ya generados para el empleado seleccionado (vínculo RRHH real
        # `rrhh_documentos`, ver `_generar_pdf`). Vive DENTRO del mismo QScrollArea que el resto
        # del formulario (una sección más de `_form_ly`, no un bloque fijo aparte fuera de él): así
        # queda literalmente debajo de los campos, en el mismo flujo desplazable de arriba a abajo,
        # en vez de competir por altura fija con el formulario cuando la ventana es pequeña.
        self._lista = EmpleadoRegistrosList(
            "Modelos 145 generados del empleado",
            [("fecha", "Fecha"),
             (lambda f: os.path.basename((f.get("ref_documento") or "").replace("\\", "/")),
              "Documento")],
            self._listar_documentos_empleado, self._id_empresa,
            abrir_fn=self._abrir_documento, boton="Reabrir")
        self._form_ly.addWidget(self._lista)

        self._form_ly.addStretch()
        scroll.setWidget(cont)
        root.addWidget(scroll, 1)

        self.lbl_resultado = QLabel("")
        self.lbl_resultado.setStyleSheet(f"color:{COLOR_CIAN};font-family:'Segoe UI';font-size:15px;"
                                         "font-weight:bold;background:transparent;")
        root.addWidget(self.lbl_resultado)

        bottom = QHBoxLayout(); bottom.addStretch()
        bottom.addWidget(self._btn("Guardar Datos Fiscales", self._guardar, primary=True))
        bottom.addWidget(self._btn("Generar y Descargar Modelo 145 (PDF)", self._generar_pdf, primary=True))
        root.addLayout(bottom)

        self._on_situacion()   # estado inicial del campo NIF cónyuge

    def _lbl(self, txt):
        l = QLabel(txt); l.setStyleSheet(_LBL_SS); return l

    def _btn(self, txt, cb, primary=False):
        b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(38)
        if primary:
            b.setStyleSheet(
                f"QPushButton{{background:{COLOR_FONDO_WIDGET};color:{COLOR_CIAN};border:2px solid {COLOR_CIAN};"
                f"border-radius:10px;padding:8px 16px;font-family:'Segoe UI';font-weight:bold;font-size:14px;}}"
                f"QPushButton:hover{{background:{COLOR_CIAN};color:{COLOR_ACCION_TEXTO};border-color:{COLOR_CIAN};}}")
        else:
            b.setStyleSheet(
                f"QPushButton{{background:transparent;color:{COLOR_CIAN};border:2px solid {COLOR_CIAN};"
                f"border-radius:10px;padding:8px 16px;font-family:'Segoe UI';font-weight:bold;font-size:14px;}}"
                f"QPushButton:hover{{background:{COLOR_CIAN};color:{COLOR_ACCION_TEXTO};}}")
        b.clicked.connect(cb); return b

    def _seccion(self, titulo):
        line = QFrame(); line.setFixedHeight(1); line.setStyleSheet(f"background:{COLOR_BORDE};")
        lbl = QLabel(titulo.upper())
        lbl.setStyleSheet(f"color:{COLOR_CIAN};font-family:'Segoe UI';font-size:15px;font-weight:900;"
                          "letter-spacing:1px;background:transparent;margin-top:4px;")
        self._form_ly.addWidget(lbl); self._form_ly.addWidget(line)

    def _crear_tabla(self, cabeceras):
        t = QTableWidget(0, len(cabeceras))
        t.setHorizontalHeaderLabels(cabeceras)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setMinimumHeight(90)
        # Mismo idioma "ESTÁNDAR" de tabla que el resto de la app (ver `foundation/tokens.qss_tabla`
        # / `EnterpriseTable`): contorno neón turquesa 2px + esquinas redondeadas 12px + hover swap
        # en cabeceras + radio superior en la primera/última columna. Cabecera +2px sobre el
        # tamaño anterior (12px → 14px).
        t.setStyleSheet(
            f"QTableWidget{{background:{COLOR_FONDO_WIDGET};color:#FFFFFF;border:2px solid {COLOR_CIAN};"
            f"border-radius:12px;gridline-color:{COLOR_BORDE};font-family:'Segoe UI';font-size:13px;"
            f"outline:none;}}"
            f"QHeaderView::section{{background:#0D1520;color:{COLOR_CIAN};border:none;"
            f"border-bottom:2px solid {COLOR_BORDE};padding:6px;font-weight:bold;font-size:14px;}}"
            f"QHeaderView::section:hover{{background:{COLOR_CIAN};color:#0D1520;}}"
            f"QHeaderView::section:first{{border-top-left-radius:12px;}}"
            f"QHeaderView::section:last{{border-top-right-radius:12px;}}")
        return t

    def _on_situacion(self, _i=None):
        self.in_nif_conyuge.setEnabled(self.cb_situacion.currentData() == "2")

    # ── Filas dinámicas: hijos ──────────────────────────────────────────────────
    def _fila_hijo(self, datos=None):
        datos = datos or {}
        t = self.tbl_hijos
        r = t.rowCount(); t.insertRow(r)

        in_nac = QLineEdit(); in_nac.setStyleSheet(f"QLineEdit{{{_INP_SS}}}")
        in_nac.setPlaceholderText("AAAA")
        if datos.get("anio_nacimiento"):
            in_nac.setText(str(datos["anio_nacimiento"]))
        t.setCellWidget(r, 0, in_nac)

        in_ado = QLineEdit(); in_ado.setStyleSheet(f"QLineEdit{{{_INP_SS}}}")
        in_ado.setPlaceholderText("AAAA (si aplica)")
        if datos.get("anio_adopcion"):
            in_ado.setText(str(datos["anio_adopcion"]))
        t.setCellWidget(r, 1, in_ado)

        cb_grado = QComboBox(); cb_grado.setStyleSheet(f"QComboBox{{{_CB_SS}}}")
        for cod, et in _GRADOS:
            cb_grado.addItem(et, cod)
        idx = cb_grado.findData(datos.get("grado_discapacidad") or "ninguna")
        if idx >= 0:
            cb_grado.setCurrentIndex(idx)
        t.setCellWidget(r, 2, cb_grado)

        chk_entero = QCheckBox(); chk_entero.setChecked(bool(datos.get("computo_entero")))
        w_chk = QWidget(); lc = QHBoxLayout(w_chk); lc.setContentsMargins(0, 0, 0, 0)
        lc.setAlignment(Qt.AlignmentFlag.AlignCenter); lc.addWidget(chk_entero)
        t.setCellWidget(r, 3, w_chk)

        t.setCellWidget(r, 4, self._btn_eliminar_fila(t, r))

    def _fila_ascendiente(self, datos=None):
        datos = datos or {}
        t = self.tbl_ascendientes
        r = t.rowCount(); t.insertRow(r)

        in_nac = QLineEdit(); in_nac.setStyleSheet(f"QLineEdit{{{_INP_SS}}}")
        in_nac.setPlaceholderText("AAAA")
        if datos.get("anio_nacimiento"):
            in_nac.setText(str(datos["anio_nacimiento"]))
        t.setCellWidget(r, 0, in_nac)

        cb_grado = QComboBox(); cb_grado.setStyleSheet(f"QComboBox{{{_CB_SS}}}")
        for cod, et in _GRADOS:
            cb_grado.addItem(et, cod)
        idx = cb_grado.findData(datos.get("grado_discapacidad") or "ninguna")
        if idx >= 0:
            cb_grado.setCurrentIndex(idx)
        t.setCellWidget(r, 1, cb_grado)

        chk_conv = QCheckBox(); chk_conv.setChecked(bool(datos.get("convivencia_otros_descendientes")))
        w_chk = QWidget(); lc = QHBoxLayout(w_chk); lc.setContentsMargins(0, 0, 0, 0)
        lc.setAlignment(Qt.AlignmentFlag.AlignCenter); lc.addWidget(chk_conv)
        t.setCellWidget(r, 2, w_chk)

        t.setCellWidget(r, 3, self._btn_eliminar_fila(t, r))

    def _btn_eliminar_fila(self, tabla, _row):
        b = QPushButton("Eliminar"); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            "QPushButton{background:transparent;color:#F85149;border:1px solid #F85149;"
            "border-radius:6px;padding:4px 8px;font-family:'Segoe UI';font-size:11px;font-weight:bold;}"
            "QPushButton:hover{background:#F85149;color:#FFFFFF;}")
        b.clicked.connect(lambda: self._eliminar_fila(tabla, b))
        return b

    def _eliminar_fila(self, tabla, boton):
        for r in range(tabla.rowCount()):
            if tabla.cellWidget(r, tabla.columnCount() - 1) is boton:
                tabla.removeRow(r)
                return

    def _limpiar_tabla(self, tabla):
        tabla.setRowCount(0)

    # ── Datos: empleados ──────────────────────────────────────────────────────
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

    def _listar_documentos_empleado(self, id_empleado, id_empresa):
        from src.rrhh.db import documentos as rrhh_docs
        return rrhh_docs.listar_documentos(id_empleado, id_empresa, tipo_doc="modelo145")

    def _abrir_documento(self, fila):
        ruta = fila.get("ref_documento")
        if ruta and os.path.exists(ruta):
            from src.utils import plataforma
            plataforma.abrir_archivo(ruta)
        else:
            mostrar_mensaje(self, "Modelo 145", "El documento no está disponible en disco.", "warning")

    def _on_empleado(self, _i):
        emp = self.cb_emp.currentData()
        self._limpiar_tabla(self.tbl_hijos)
        self._limpiar_tabla(self.tbl_ascendientes)
        self._reset_formulario()
        self.lbl_resultado.setText("")
        self._lista.refrescar(emp.get("id") if emp else None)
        if not emp:
            self._empleado_actual_id = None
            self._lbl_ident.setText("—")
            return
        self._empleado_actual_id = emp.get("id")
        nom = f"{emp.get('nombre','')} {emp.get('apellidos','')}".strip()
        self._lbl_ident.setText(
            f"{nom}  ·  NIF: {emp.get('nif','—')}  ·  Nacimiento: {emp.get('fecha_nacimiento','—')}")
        self._cargar_datos_fiscales(self._empleado_actual_id)

    def _reset_formulario(self):
        self.cb_situacion.setCurrentIndex(self.cb_situacion.findData("3"))
        self.in_nif_conyuge.clear()
        self.cb_discapacidad.setCurrentIndex(self.cb_discapacidad.findData("ninguna"))
        self.chk_ayuda.setChecked(False)
        self.chk_movilidad.setChecked(False)
        self.chk_rentas_irreg.setChecked(False)
        self.in_pension.clear()
        self.in_anualidades.clear()
        self.chk_vivienda.setChecked(False)
        self._on_situacion()

    def _cargar_datos_fiscales(self, id_empleado):
        try:
            from src.rrhh.db import datos_fiscales as DF
            df = DF.obtener_datos_fiscales(id_empleado, self._id_empresa())
        except Exception as e:
            logger.debug("cargar_datos_fiscales(%s): %s", id_empleado, e); df = None
        if not df:
            return
        idx = self.cb_situacion.findData(df.get("situacion_familiar") or "3")
        if idx >= 0:
            self.cb_situacion.setCurrentIndex(idx)
        self.in_nif_conyuge.setText(df.get("nif_conyuge") or "")
        idx = self.cb_discapacidad.findData(df.get("discapacidad_trabajador") or "ninguna")
        if idx >= 0:
            self.cb_discapacidad.setCurrentIndex(idx)
        self.chk_ayuda.setChecked(bool(df.get("ayuda_terceros_movilidad")))
        self.chk_movilidad.setChecked(bool(df.get("movilidad_geografica")))
        self.chk_rentas_irreg.setChecked(bool(df.get("rentas_irregulares")))
        if df.get("pension_compensatoria_anual") is not None:
            self.in_pension.setText(str(df.get("pension_compensatoria_anual")))
        if df.get("anualidades_alimentos_anual") is not None:
            self.in_anualidades.setText(str(df.get("anualidades_alimentos_anual")))
        self.chk_vivienda.setChecked(bool(df.get("vivienda_habitual_pre2013")))
        self._on_situacion()
        for h in (df.get("hijos") or []):
            self._fila_hijo(h)
        for a in (df.get("ascendientes") or []):
            self._fila_ascendiente(a)
        if df.get("irpf_pct_calculado") is not None:
            self.lbl_resultado.setText(
                f"Último IRPF calculado: {df.get('irpf_pct_calculado')}%  "
                f"(calculado el {df.get('fecha_calculo') or '—'})")

    # ── Recolección ───────────────────────────────────────────────────────────
    def _recoger_hijos(self):
        filas = []
        t = self.tbl_hijos
        for r in range(t.rowCount()):
            in_nac = t.cellWidget(r, 0)
            in_ado = t.cellWidget(r, 1)
            cb_grado = t.cellWidget(r, 2)
            w_chk = t.cellWidget(r, 3)
            chk = w_chk.findChild(QCheckBox) if w_chk else None
            filas.append({
                "anio_nacimiento": _int(in_nac.text()) if in_nac else None,
                "anio_adopcion": _int(in_ado.text()) if in_ado else None,
                "grado_discapacidad": cb_grado.currentData() if cb_grado else "ninguna",
                "computo_entero": bool(chk.isChecked()) if chk else False,
            })
        return filas

    def _recoger_ascendientes(self):
        filas = []
        t = self.tbl_ascendientes
        for r in range(t.rowCount()):
            in_nac = t.cellWidget(r, 0)
            cb_grado = t.cellWidget(r, 1)
            w_chk = t.cellWidget(r, 2)
            chk = w_chk.findChild(QCheckBox) if w_chk else None
            filas.append({
                "anio_nacimiento": _int(in_nac.text()) if in_nac else None,
                "grado_discapacidad": cb_grado.currentData() if cb_grado else "ninguna",
                "convivencia_otros_descendientes": bool(chk.isChecked()) if chk else False,
            })
        return filas

    def _recoger(self) -> dict:
        return {
            "situacion_familiar": self.cb_situacion.currentData(),
            "nif_conyuge": self.in_nif_conyuge.text().strip() or None,
            "discapacidad_trabajador": self.cb_discapacidad.currentData(),
            "ayuda_terceros_movilidad": self.chk_ayuda.isChecked(),
            "movilidad_geografica": self.chk_movilidad.isChecked(),
            "rentas_irregulares": self.chk_rentas_irreg.isChecked(),
            "pension_compensatoria_anual": _num(self.in_pension.text()),
            "anualidades_alimentos_anual": _num(self.in_anualidades.text()),
            "vivienda_habitual_pre2013": self.chk_vivienda.isChecked(),
            "hijos": self._recoger_hijos(),
            "ascendientes": self._recoger_ascendientes(),
        }

    # ── Acciones ──────────────────────────────────────────────────────────────
    def _guardar(self):
        if not self._empleado_actual_id:
            mostrar_mensaje(self, "Modelo 145", "Selecciona primero un empleado.", "warning")
            return
        campos = self._recoger()
        hijos = campos.pop("hijos")
        ascendientes = campos.pop("ascendientes")
        try:
            from src.rrhh.db import datos_fiscales as DF
            id_df = DF.guardar_datos_fiscales(
                self._empleado_actual_id, self._id_empresa(),
                hijos=hijos, ascendientes=ascendientes, **campos)
        except Exception as e:
            logger.error("guardar datos fiscales: %s", e); id_df = None
        if not id_df:
            mostrar_mensaje(self, "Modelo 145", "No se pudieron guardar los datos fiscales.", "error")
            return
        # Recalcula el IRPF automáticamente tras cada guardado.
        try:
            from src.rrhh.irpf_calculator import IRPFCalculatorError, IRPFCalculatorService
            resultado = IRPFCalculatorService().calcular(self._empleado_actual_id, self._id_empresa())
            self.lbl_resultado.setText(
                f"Datos guardados. IRPF calculado: {resultado['tipo_irpf_pct']}%  "
                f"(retribución bruta anual prevista: {resultado['retribucion_bruta_anual']:.2f} €, "
                f"mínimo personal y familiar: {resultado['minimo_personal_familiar']:.2f} €)")
            mostrar_mensaje(self, "Modelo 145",
                            "Datos fiscales guardados y IRPF recalculado correctamente.", "success")
        except IRPFCalculatorError as e:
            self.lbl_resultado.setText("Datos guardados. No se pudo calcular el IRPF: " + str(e))
            mostrar_mensaje(self, "Modelo 145",
                            f"Datos guardados, pero no se pudo calcular el IRPF: {e}", "warning")
        except Exception as e:
            logger.error("calcular IRPF: %s", e)
            mostrar_mensaje(self, "Modelo 145",
                            "Datos guardados, pero no se pudo calcular el IRPF.", "warning")

    def _generar_pdf(self):
        emp = self.cb_emp.currentData()
        if not emp:
            mostrar_mensaje(self, "Modelo 145", "Selecciona primero un empleado.", "warning")
            return
        campos = self._recoger()
        try:
            from src.rrhh import maestros
            empresa = maestros.entidad_empresa(self._id_empresa())
        except Exception as e:
            logger.debug("modelo145 entidad_empresa: %s", e); empresa = {}
        datos_pdf = {
            "emp_razon_social": empresa.get("razon_social"), "emp_cif": empresa.get("cif"),
            "nombre": f"{emp.get('nombre','')} {emp.get('apellidos','')}".strip(),
            "nif": emp.get("nif"), "fecha_nacimiento": emp.get("fecha_nacimiento"),
            **campos,
        }
        # Adjunta el último IRPF calculado (si lo hay) como nota informativa.
        try:
            from src.rrhh.db import datos_fiscales as DF
            df = DF.obtener_datos_fiscales(self._empleado_actual_id, self._id_empresa())
            if df and df.get("irpf_pct_calculado") is not None:
                datos_pdf["irpf_pct_calculado"] = df.get("irpf_pct_calculado")
        except Exception as e:
            logger.debug("modelo145 irpf_pct_calculado: %s", e)
        try:
            from src.rrhh.documents.render.render_modelo145 import generar_modelo145_pdf
            ruta = generar_modelo145_pdf(datos_pdf)
            try:
                from src.db.documentos import registrar_documento
                registrar_documento(ruta, tipo="modelo145",
                                    nombre=ruta.replace("\\", "/").split("/")[-1],
                                    referencia=str(emp.get("nif") or ""))
            except Exception:
                pass
            # Vínculo RRHH real (`rrhh_documentos`) — `persistencia._TIPO_DOC` no tiene entrada para
            # MODELO145 (es fiscal, Fase B2, posterior a esa tabla); se enlaza directo con el
            # empleado ya conocido por el desplegable, sin pasar por `persistencia.registrar_generacion`.
            try:
                from src.rrhh.db import documentos as rrhh_docs
                rrhh_docs.crear_documento(
                    emp["id"], self._id_empresa(), tipo_doc="modelo145",
                    fecha=_dt.date.today().isoformat(), ref_documento=ruta,
                    datos_snapshot=json.dumps(datos_pdf, ensure_ascii=False, default=str),
                    cifrado=True)
            except Exception as e:
                logger.warning("registrar modelo145 en rrhh_documentos (no crítico): %s", e)
            self._lista.refrescar(emp["id"])
            mostrar_mensaje(self, "Modelo 145",
                            "Modelo 145 generado correctamente en /documentos/modelo145.", "success")
            try:
                from src.utils import plataforma
                plataforma.abrir_carpeta(ruta.replace("\\", "/").rsplit("/", 1)[0])
            except Exception:
                pass
        except Exception as e:
            logger.error("generar modelo145: %s", e)
            mostrar_mensaje(self, "Modelo 145", "No se pudo generar el Modelo 145.", "error")
