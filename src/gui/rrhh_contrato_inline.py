"""
Formulario INLINE de CONTRATOS laborales (sustituye al botón del asistente en la pestaña Contratos).

Los campos del contrato se rellenan directamente en la pestaña. NO reimplementa la generación del
PDF: reutiliza EXACTAMENTE el motor existente `_WizardDocumentoFiscal._generar_pdf` (que ya resuelve
los datos de empresa/representante/centro desde `datos_corporativos` — DATOS DE EMPRESA — y construye
el contrato). Este formulario solo recoge los datos del trabajador y del contrato, los vuelca en el
`_datos` del asistente y dispara su generación.

Además añade un selector de empleado que autorrellena los datos del trabajador desde la capa de
datos MAESTROS unificada (`src.rrhh.maestros`).
"""

import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from assets.estilo_global import (
    COLOR_ACCION_TEXTO, COLOR_BORDE, COLOR_CIAN, COLOR_FONDO_WIDGET, mostrar_confirmacion,
    mostrar_mensaje,
)
from src.gui.rrhh_doc_list_widget import EmpleadoRegistrosList

logger = logging.getLogger("gui.rrhh.contrato_inline")

_INP_SS = (
    f"background:{COLOR_FONDO_WIDGET};color:#FFFFFF;border:1px solid {COLOR_BORDE};"
    f"border-radius:8px;padding:6px 10px;font-family:'Segoe UI';font-size:15px;"
)
_LBL_SS = "color:#C9D1D9;font-family:'Segoe UI';font-size:14px;font-weight:bold;background:transparent;"
# Desplegables: 1px menos que los campos de texto (petición del usuario).
_CB_SS = _INP_SS.replace("font-size:15px", "font-size:14px")

MODALIDADES = ["INDEFINIDO", "TEMPORAL", "FIJO DISCONTINUO", "PARCIAL", "PRÁCTICAS", "SUSTITUCIÓN"]
SEXOS = ["—", "MUJER", "HOMBRE", "OTRO"]
DISTANCIA = ["NO", "SÍ"]
JORNADAS = ["TIEMPO COMPLETO", "TIEMPO PARCIAL"]
PAGAS = ["12", "14"]
ASISTENCIA = ["No procede", "Comité de Empresa", "Delegado Sindical",
              "Representación Legal de los Trabajadores"]
CLAUSULAS = [
    "Prorrateo de pagas extraordinarias",
    "Obligaciones de no competencia desleal (arts. 4.1 y 21.1 ET)",
    "Uso restringido de Internet y correo corporativo",
    "Protección de datos personales (LOPDGDD 3/2018)",
    "Compensación de horas extra con descanso",
    "Interrupción del período de prueba por IT/nacimiento",
    "Vacaciones en días laborables",
    "Obligación de comunicar baja/alta médica de forma inmediata",
]

# Fase B (RRHH — Contratos: modelo de pago, cláusula de bolsa de horas y complemento de
# convenio por IT). Deliberadamente SIN IRPF: vive en `rrhh_datos_fiscales` (Fase B2), nunca
# en el contrato. (etiqueta, valor guardado en `rrhh_contratos`).
MODELO_PAGO = [("Fijo mensual", "fijo"), ("Tarifa por hora", "hora")]
COMPENSACION_BOLSA = [
    ("Descanso compensatorio", "descanso"),
    ("A elección del trabajador", "eleccion_trabajador"),
    ("Siempre en pago", "pago"),
]
COMPLEMENTO_IT_TIPO = [
    ("Porcentaje hasta", "porcentaje_hasta"),
    ("Importe fijo", "importe_fijo"),
    ("Ninguno", "ninguno"),
]

# (clave en _datos del asistente, etiqueta, tipo). tipo: "line" | ("combo", opciones)
_TRABAJADOR = [
    ("trabajador", "Nombre completo", "line"),
    ("nif", "NIF / NIE", "line"),
    ("fecha_nacimiento", "Fecha de nacimiento (DD/MM/AAAA)", "line"),
    ("ss", "Nº Seguridad Social", "line"),
    ("nacionalidad", "Nacionalidad", "line"),
    ("sexo", "Sexo", ("combo", SEXOS)),
    ("nivel_formativo", "Nivel formativo", "line"),
    ("cod_nivel_formativo", "Cód. nivel formativo", "line"),
    ("titulacion", "Titulación (si procede)", "line"),
    ("municipio_domicilio", "Municipio de domicilio", "line"),
    ("cod_municipio_dom", "Cód. municipio", "line"),
    ("provincia_domicilio", "Provincia", "line"),
    ("cod_provincia_dom", "Cód. provincia", "line"),
    ("pais_domicilio", "País", "line"),
    ("cod_pais_dom", "Cód. país (ej. 724)", "line"),
    ("cp_domicilio", "Código postal", "line"),
    ("telefono_trab", "Teléfono", "line"),
    ("email_trab", "Correo electrónico", "line"),
]
_CONTRATO = [
    ("subtipo", "Modalidad de contrato", ("combo", MODALIDADES)),
    ("fecha", "Fecha de inicio (DD/MM/AAAA)", "line"),
    ("fecha_fin", "Fecha fin (temporal / sustitución / prácticas)", "line"),
    ("puesto", "Puesto / Cargo", "line"),
    ("grupo_prof", "Grupo profesional", "line"),
    ("funciones", "Funciones principales", "line"),
    ("trabajo_distancia", "Trabajo a distancia", ("combo", DISTANCIA)),
    ("tipo_jornada", "Tipo de jornada", ("combo", JORNADAS)),
    ("horas_semanales", "Horas semanales", "line"),
    ("distribucion", "Distribución horaria", "line"),
]
_RETRIBUCION = [
    ("salario", "Salario bruto anual (€)", "line"),
    ("num_pagas", "Nº de pagas", ("combo", PAGAS)),
    ("periodo_prueba", "Período de prueba", "line"),
    ("vacaciones", "Vacaciones", "line"),
    ("convenio", "Convenio colectivo aplicable", "line"),
]
_ASISTENCIA = [
    ("asist_tipo", "Tipo de representación", ("combo", ASISTENCIA)),
    ("asist_nombre", "Nombre y apellidos", "line"),
    ("asist_nif", "DNI / NIE", "line"),
    ("asist_cargo", "Cargo", "line"),
    ("asist_org", "Organización / sindicato", "line"),
]


class ContratoInlineForm(QWidget):
    def __init__(self, id_empresa_getter, parent=None):
        super().__init__(parent)
        self._id_empresa = id_empresa_getter
        self._inputs = {}          # clave → widget
        self._checks = []          # [(texto, QCheckBox)]
        self._empleados = []
        self._wz = None            # motor de generación (asistente), perezoso
        self._combo_centro = None
        self._combo_rep = None
        self._id_contrato_actual = None    # Fase B: id real en rrhh_contratos (None = sin generar aún)
        self._contrato_firmado = False     # Fase B: estado `firmado` del contrato cargado/generado
        self._build()
        self._cargar_empleados()
        self._actualizar_visibilidad_firmado()

    # ── Motor de generación (asistente existente, reutilizado sin modificar) ────
    def _wizard(self):
        if self._wz is None:
            from PyQt6.QtWidgets import QDialog
            from src.gui.gestion_usuarios import _WizardDocumentoFiscal
            # Construcción LIGERA: se omite `_build()` del asistente (monta toda su UI multipágina,
            # ~300 ms). Solo necesitamos sus combos (centros/representantes) y su `_generar_pdf`, que
            # trabajan a partir de `_datos`/`_tipo`. Reutiliza el motor de generación sin su interfaz.
            wz = _WizardDocumentoFiscal.__new__(_WizardDocumentoFiscal)
            QDialog.__init__(wz)
            wz._tipo = "CONTRATO"
            wz._subtipo_inicial = None
            wz._paso = 0
            wz._datos = {}
            self._wz = wz
        return self._wz

    # ── UI ──────────────────────────────────────────────────────────────────────
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

        self._seccion("Datos del trabajador/a")
        self._grid(_TRABAJADOR)
        self._seccion("Datos del contrato")
        self._grid(_CONTRATO)
        # Centro de trabajo y representante legal: combos del asistente (DATOS DE EMPRESA).
        self._grid_combos_empresa()
        self._seccion("Retribución y condiciones")
        self._grid(_RETRIBUCION)
        self._grid_modelo_pago()
        self._seccion("Cláusula de bolsa de horas (distribución irregular de jornada)")
        self._grid_bolsa_horas()
        self._seccion("Complemento de convenio por IT")
        self._grid_complemento_it()
        self._seccion("Asistencia legal de los trabajadores")
        self._grid(_ASISTENCIA)
        self._seccion("Cofinanciación y cláusulas adicionales")
        self._chk_fse = QCheckBox(
            "Contrato cofinanciado — mostrar logos institucionales (FSE+ / UE / Ministerio / SEPE)")
        self._chk_fse.setChecked(True)
        self._chk_fse.setStyleSheet(_LBL_SS)
        self._form_ly.addWidget(self._chk_fse)
        for txt in CLAUSULAS:
            cb = QCheckBox(txt); cb.setChecked(True); cb.setStyleSheet(_LBL_SS)
            self._form_ly.addWidget(cb); self._checks.append((txt, cb))

        # Contratos ya generados para el empleado seleccionado (`rrhh_contratos`, alimentada por
        # `registrar_generacion` al generar el PDF — ver `_generar`). Vive DENTRO del mismo
        # QScrollArea que el resto del formulario (una sección más de `_form_ly`, no un bloque fijo
        # aparte fuera de él): así queda literalmente debajo de los campos, en el mismo flujo
        # desplazable de arriba a abajo, en vez de competir por altura fija con el formulario cuando
        # la ventana es pequeña.
        self._lista = EmpleadoRegistrosList(
            "Contratos generados del empleado",
            [("modalidad", "Modalidad"), ("fecha_inicio", "Inicio"), ("fecha_fin", "Fin"),
             ("salario", "Salario"), ("estado", "Estado")],
            self._listar_contratos_empleado, self._id_empresa,
            abrir_fn=self._abrir_documento, boton="Reabrir")
        self._form_ly.addWidget(self._lista)

        self._form_ly.addStretch()
        scroll.setWidget(cont)
        root.addWidget(scroll, 1)

        bottom = QHBoxLayout(); bottom.addStretch()
        # Firmado: solo SUPERADMIN, y solo una vez el contrato tiene un id real (generado/
        # guardado) — oculto en cualquier otro caso (ver `_actualizar_visibilidad_firmado`).
        self.btn_firmado = self._btn("Firmado", self._marcar_firmado_click)
        self.btn_firmado.setVisible(False)
        bottom.addWidget(self.btn_firmado)
        bottom.addWidget(self._btn("Generar contrato (PDF)", self._generar, primary=True))
        root.addLayout(bottom)

    def _lbl(self, txt):
        l = QLabel(txt); l.setStyleSheet(_LBL_SS); return l

    def _btn(self, txt, cb, primary=False):
        b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(40)
        if primary:
            b.setStyleSheet(
                f"QPushButton{{background:{COLOR_FONDO_WIDGET};color:{COLOR_CIAN};border:2px solid {COLOR_CIAN};"
                f"border-radius:10px;padding:8px 18px;font-family:'Segoe UI';font-weight:bold;font-size:15px;}}"
                f"QPushButton:hover{{background:{COLOR_CIAN};color:{COLOR_ACCION_TEXTO};border-color:{COLOR_CIAN};}}")
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
        for clave, etiqueta, tipo in campos:
            cel = QVBoxLayout(); cel.setSpacing(2)
            cel.addWidget(self._lbl(etiqueta))
            if isinstance(tipo, tuple) and tipo[0] == "combo":
                inp = QComboBox(); inp.setStyleSheet(f"QComboBox{{{_CB_SS}}}"); inp.addItems(tipo[1])
            else:
                inp = QLineEdit(); inp.setStyleSheet(f"QLineEdit{{{_INP_SS}}}")
                if clave == "pais_domicilio":
                    inp.setText("ESPAÑA")
            self._inputs[clave] = inp
            cel.addWidget(inp)
            w = QWidget(); w.setLayout(cel)
            grid.addWidget(w, row, col, 1, 1)
            col += 1
            if col >= 2:
                col = 0; row += 1
        holder = QWidget(); holder.setLayout(grid)
        self._form_ly.addWidget(holder)

    def _grid_combos_empresa(self):
        """Centro de trabajo y representante legal, reutilizando los combos del asistente (que se
        pueblan desde DATOS DE EMPRESA: centros registrados + tiendas + almacenes + representantes)."""
        wz = self._wizard()
        grid = QGridLayout(); grid.setHorizontalSpacing(18); grid.setVerticalSpacing(8)
        c1 = QVBoxLayout(); c1.setSpacing(2)
        c1.addWidget(self._lbl("Centro de trabajo (registrado en DATOS DE EMPRESA)"))
        self._combo_centro = wz._mk_combo_centros()
        c1.addWidget(self._combo_centro)
        w1 = QWidget(); w1.setLayout(c1); grid.addWidget(w1, 0, 0)
        c2 = QVBoxLayout(); c2.setSpacing(2)
        c2.addWidget(self._lbl("Representante legal (firmante del contrato)"))
        self._combo_rep = wz._mk_combo_representantes()
        c2.addWidget(self._combo_rep)
        w2 = QWidget(); w2.setLayout(c2); grid.addWidget(w2, 0, 1)
        holder = QWidget(); holder.setLayout(grid)
        self._form_ly.addWidget(holder)

    def _combo_valores(self, pares, valor_defecto=None):
        """Combo (etiqueta, valor) — a diferencia de `_grid()` (que usa el texto tal cual),
        estos combos guardan un valor de BD distinto de la etiqueta visible (p. ej.
        "Fijo mensual" → 'fijo'), así que usan `currentData()`/`findData()`."""
        cb = QComboBox(); cb.setStyleSheet(f"QComboBox{{{_CB_SS}}}")
        for etiqueta, valor in pares:
            cb.addItem(etiqueta, valor)
        if valor_defecto is not None:
            i = cb.findData(valor_defecto)
            if i >= 0:
                cb.setCurrentIndex(i)
        return cb

    def _grid_modelo_pago(self):
        """Modelo de pago (Fijo mensual / Tarifa por hora). En modo "hora" se muestra la
        tarifa/hora y se des-enfatiza (deshabilita) el salario bruto anual, que deja de
        aplicar — ambos modelos coexisten por contrato, nunca se mezclan."""
        grid = QGridLayout(); grid.setHorizontalSpacing(18); grid.setVerticalSpacing(8)
        c1 = QVBoxLayout(); c1.setSpacing(2)
        c1.addWidget(self._lbl("Modelo de pago"))
        self.cb_modelo_pago = self._combo_valores(MODELO_PAGO, "fijo")
        self.cb_modelo_pago.currentIndexChanged.connect(self._actualizar_visibilidad_modelo_pago)
        c1.addWidget(self.cb_modelo_pago)
        w1 = QWidget(); w1.setLayout(c1); grid.addWidget(w1, 0, 0)
        c2 = QVBoxLayout(); c2.setSpacing(2)
        c2.addWidget(self._lbl("Tarifa por hora (€)"))
        self.inp_tarifa_hora = QLineEdit(); self.inp_tarifa_hora.setStyleSheet(f"QLineEdit{{{_INP_SS}}}")
        c2.addWidget(self.inp_tarifa_hora)
        w2 = QWidget(); w2.setLayout(c2); grid.addWidget(w2, 0, 1)
        self._w_tarifa_hora = w2
        holder = QWidget(); holder.setLayout(grid)
        self._form_ly.addWidget(holder)
        self._actualizar_visibilidad_modelo_pago()

    def _actualizar_visibilidad_modelo_pago(self, *_args):
        es_hora = self.cb_modelo_pago.currentData() == "hora"
        self._w_tarifa_hora.setVisible(es_hora)
        salario_w = self._inputs.get("salario")
        if salario_w is not None:
            salario_w.setEnabled(not es_hora)

    def _grid_bolsa_horas(self):
        """Cláusula opcional (checkbox) — vigencia/compensación/plus/regularización. Los 4
        campos se deshabilitan en bloque mientras la cláusula no esté activada (Qt propaga
        `setEnabled` al contenedor y a sus hijos)."""
        self.chk_bolsa_horas = QCheckBox("Activar cláusula de bolsa de horas")
        self.chk_bolsa_horas.setStyleSheet(_LBL_SS)
        self.chk_bolsa_horas.toggled.connect(self._actualizar_visibilidad_bolsa_horas)
        self._form_ly.addWidget(self.chk_bolsa_horas)

        grid = QGridLayout(); grid.setHorizontalSpacing(18); grid.setVerticalSpacing(8)
        c1 = QVBoxLayout(); c1.setSpacing(2)
        c1.addWidget(self._lbl("Vigencia (meses)"))
        self.inp_bolsa_vigencia = QLineEdit("12"); self.inp_bolsa_vigencia.setStyleSheet(f"QLineEdit{{{_INP_SS}}}")
        c1.addWidget(self.inp_bolsa_vigencia)
        grid.addWidget(self._envolver(c1), 0, 0)

        c2 = QVBoxLayout(); c2.setSpacing(2)
        c2.addWidget(self._lbl("Compensación de las horas"))
        self.cb_bolsa_compensacion = self._combo_valores(COMPENSACION_BOLSA, "descanso")
        c2.addWidget(self.cb_bolsa_compensacion)
        grid.addWidget(self._envolver(c2), 0, 1)

        c3 = QVBoxLayout(); c3.setSpacing(2)
        c3.addWidget(self._lbl("Plus por disponibilidad (€) — opcional"))
        self.inp_bolsa_plus = QLineEdit(); self.inp_bolsa_plus.setStyleSheet(f"QLineEdit{{{_INP_SS}}}")
        c3.addWidget(self.inp_bolsa_plus)
        grid.addWidget(self._envolver(c3), 1, 0)

        c4 = QVBoxLayout(); c4.setSpacing(2)
        c4.addWidget(self._lbl("Periodo de regularización (meses)"))
        self.inp_bolsa_regularizacion = QLineEdit("12")
        self.inp_bolsa_regularizacion.setStyleSheet(f"QLineEdit{{{_INP_SS}}}")
        c4.addWidget(self.inp_bolsa_regularizacion)
        grid.addWidget(self._envolver(c4), 1, 1)

        self._w_bolsa_campos = QWidget(); self._w_bolsa_campos.setLayout(grid)
        self._w_bolsa_campos.setEnabled(False)
        self._form_ly.addWidget(self._w_bolsa_campos)

    def _actualizar_visibilidad_bolsa_horas(self, activa):
        self._w_bolsa_campos.setEnabled(bool(activa))

    def _grid_complemento_it(self):
        """Cláusula opcional independiente de la anterior — alimenta el motor de
        Incapacidad Temporal (Fase F), que no forma parte de esta fase."""
        self.chk_complemento_it = QCheckBox("Activar complemento de convenio por IT")
        self.chk_complemento_it.setStyleSheet(_LBL_SS)
        self.chk_complemento_it.toggled.connect(self._actualizar_visibilidad_complemento_it)
        self._form_ly.addWidget(self.chk_complemento_it)

        grid = QGridLayout(); grid.setHorizontalSpacing(18); grid.setVerticalSpacing(8)
        c1 = QVBoxLayout(); c1.setSpacing(2)
        c1.addWidget(self._lbl("Tipo de complemento"))
        self.cb_it_tipo = self._combo_valores(COMPLEMENTO_IT_TIPO, "ninguno")
        c1.addWidget(self.cb_it_tipo)
        grid.addWidget(self._envolver(c1), 0, 0)

        c2 = QVBoxLayout(); c2.setSpacing(2)
        c2.addWidget(self._lbl("Porcentaje (%) — p. ej. 100"))
        self.inp_it_porcentaje = QLineEdit(); self.inp_it_porcentaje.setStyleSheet(f"QLineEdit{{{_INP_SS}}}")
        c2.addWidget(self.inp_it_porcentaje)
        grid.addWidget(self._envolver(c2), 0, 1)

        c3 = QVBoxLayout(); c3.setSpacing(2)
        c3.addWidget(self._lbl("Tramo de días — inicio"))
        self.inp_it_tramo_inicio = QLineEdit(); self.inp_it_tramo_inicio.setStyleSheet(f"QLineEdit{{{_INP_SS}}}")
        c3.addWidget(self.inp_it_tramo_inicio)
        grid.addWidget(self._envolver(c3), 1, 0)

        c4 = QVBoxLayout(); c4.setSpacing(2)
        c4.addWidget(self._lbl("Tramo de días — fin"))
        self.inp_it_tramo_fin = QLineEdit(); self.inp_it_tramo_fin.setStyleSheet(f"QLineEdit{{{_INP_SS}}}")
        c4.addWidget(self.inp_it_tramo_fin)
        grid.addWidget(self._envolver(c4), 1, 1)

        self._w_it_campos = QWidget(); self._w_it_campos.setLayout(grid)
        self._w_it_campos.setEnabled(False)
        self._form_ly.addWidget(self._w_it_campos)

    def _actualizar_visibilidad_complemento_it(self, activa):
        self._w_it_campos.setEnabled(bool(activa))

    @staticmethod
    def _envolver(cel_layout):
        w = QWidget(); w.setLayout(cel_layout); return w

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
        else:
            w.setText(txt)

    def _get(self, w):
        return w.currentText().strip() if isinstance(w, QComboBox) else w.text().strip()

    def _recoger(self) -> dict:
        datos = {k: self._get(w) for k, w in self._inputs.items()}
        if datos.get("sexo") == "—":
            datos["sexo"] = ""
        datos["fse"] = self._chk_fse.isChecked()
        datos["clausulas_adicionales"] = [t for t, cb in self._checks if cb.isChecked()]
        # Centro de trabajo (dict o None) y representante (id) — igual que el asistente.
        cd = self._combo_centro.currentData() if self._combo_centro else None
        if isinstance(cd, dict):
            datos["id_centro"] = cd.get("id_centro")
            datos["centro_info"] = cd
        else:
            datos["id_centro"] = None
            datos["centro_info"] = None
        datos["id_representante"] = self._combo_rep.currentData() if self._combo_rep else None
        return datos

    # ── Fase B: modelo de pago / bolsa de horas / complemento IT ───────────────
    @staticmethod
    def _num_or_none(txt):
        txt = (txt or "").strip().replace(",", ".")
        if not txt:
            return None
        try:
            return float(txt)
        except ValueError:
            return None

    @staticmethod
    def _int_or_default(txt, defecto):
        txt = (txt or "").strip()
        if not txt:
            return defecto
        try:
            return int(float(txt))
        except ValueError:
            return defecto

    @staticmethod
    def _int_or_none(txt):
        txt = (txt or "").strip()
        if not txt:
            return None
        try:
            return int(float(txt))
        except ValueError:
            return None

    def _recoger_campos_extendidos(self) -> dict:
        """Campos nuevos de `rrhh_contratos` (Fase B) — persistidos vía `actualizar_contrato`,
        NUNCA vía `_datos` del asistente (que solo conoce los campos base del PDF)."""
        modelo = self.cb_modelo_pago.currentData() or "fijo"
        activa_bh = self.chk_bolsa_horas.isChecked()
        activa_it = self.chk_complemento_it.isChecked()
        return {
            "modelo_pago": modelo,
            "tarifa_hora": self._num_or_none(self.inp_tarifa_hora.text()) if modelo == "hora" else None,
            "bolsa_horas_activa": 1 if activa_bh else 0,
            "bolsa_horas_vigencia_meses": self._int_or_default(self.inp_bolsa_vigencia.text(), 12),
            "bolsa_horas_compensacion": self.cb_bolsa_compensacion.currentData() or "descanso",
            "bolsa_horas_plus_disponibilidad": self._num_or_none(self.inp_bolsa_plus.text()),
            "bolsa_horas_periodo_regularizacion_meses":
                self._int_or_default(self.inp_bolsa_regularizacion.text(), 12),
            "complemento_it_activo": 1 if activa_it else 0,
            "complemento_it_tipo": self.cb_it_tipo.currentData() or "ninguno",
            "complemento_it_porcentaje": self._num_or_none(self.inp_it_porcentaje.text()),
            "complemento_it_tramo_dias_inicio": self._int_or_none(self.inp_it_tramo_inicio.text()),
            "complemento_it_tramo_dias_fin": self._int_or_none(self.inp_it_tramo_fin.text()),
        }

    def _set_valores_extendidos(self, contrato):
        """Vuelca en los widgets el contrato ya guardado — el equivalente de `_autollenar`
        para los campos de esta fase, para que "editar" (reseleccionar el empleado) muestre
        lo último guardado en vez de siempre partir de los valores por defecto."""
        i = self.cb_modelo_pago.findData(contrato.get("modelo_pago") or "fijo")
        if i >= 0:
            self.cb_modelo_pago.setCurrentIndex(i)
        tarifa = contrato.get("tarifa_hora")
        self.inp_tarifa_hora.setText("" if tarifa is None else str(tarifa))
        self._actualizar_visibilidad_modelo_pago()

        activa_bh = bool(contrato.get("bolsa_horas_activa"))
        self.chk_bolsa_horas.setChecked(activa_bh)
        self.inp_bolsa_vigencia.setText(str(contrato.get("bolsa_horas_vigencia_meses") or 12))
        j = self.cb_bolsa_compensacion.findData(contrato.get("bolsa_horas_compensacion") or "descanso")
        if j >= 0:
            self.cb_bolsa_compensacion.setCurrentIndex(j)
        plus = contrato.get("bolsa_horas_plus_disponibilidad")
        self.inp_bolsa_plus.setText("" if plus is None else str(plus))
        self.inp_bolsa_regularizacion.setText(
            str(contrato.get("bolsa_horas_periodo_regularizacion_meses") or 12))
        self._w_bolsa_campos.setEnabled(activa_bh)

        activa_it = bool(contrato.get("complemento_it_activo"))
        self.chk_complemento_it.setChecked(activa_it)
        k = self.cb_it_tipo.findData(contrato.get("complemento_it_tipo") or "ninguno")
        if k >= 0:
            self.cb_it_tipo.setCurrentIndex(k)
        pct = contrato.get("complemento_it_porcentaje")
        self.inp_it_porcentaje.setText("" if pct is None else str(pct))
        ti = contrato.get("complemento_it_tramo_dias_inicio")
        tf = contrato.get("complemento_it_tramo_dias_fin")
        self.inp_it_tramo_inicio.setText("" if ti is None else str(ti))
        self.inp_it_tramo_fin.setText("" if tf is None else str(tf))
        self._w_it_campos.setEnabled(activa_it)

    def _resetear_campos_extendidos(self):
        self.cb_modelo_pago.setCurrentIndex(0)
        self.inp_tarifa_hora.clear()
        self._actualizar_visibilidad_modelo_pago()
        self.chk_bolsa_horas.setChecked(False)
        self.inp_bolsa_vigencia.setText("12")
        self.cb_bolsa_compensacion.setCurrentIndex(0)
        self.inp_bolsa_plus.clear()
        self.inp_bolsa_regularizacion.setText("12")
        self._w_bolsa_campos.setEnabled(False)
        self.chk_complemento_it.setChecked(False)
        i = self.cb_it_tipo.findData("ninguno")
        self.cb_it_tipo.setCurrentIndex(i if i >= 0 else 0)
        self.inp_it_porcentaje.clear()
        self.inp_it_tramo_inicio.clear()
        self.inp_it_tramo_fin.clear()
        self._w_it_campos.setEnabled(False)

    def _cargar_contrato_vigente(self, emp):
        """Al elegir un empleado, carga el contrato más reciente que ya tenga (si existe) en
        los campos de esta fase — y habilita el botón "Firmado" si corresponde. No crea nada:
        solo lectura hasta que se pulse "Generar contrato (PDF)" o "Firmado"."""
        self._id_contrato_actual = None
        self._contrato_firmado = False
        contrato = None
        try:
            from src.rrhh.db import contratos as CT
            lista = CT.listar_contratos(emp.get("id"), self._id_empresa())
            contrato = lista[0] if lista else None
        except Exception as e:
            logger.debug("cargar contrato vigente: %s", e)
        if contrato:
            self._id_contrato_actual = contrato.get("id")
            self._contrato_firmado = bool(contrato.get("firmado"))
            self._set_valores_extendidos(contrato)
        else:
            self._resetear_campos_extendidos()
        self._actualizar_visibilidad_firmado()

    def _actualizar_visibilidad_firmado(self):
        visible = False
        try:
            from src.db.usuario import sesion_global
            visible = (sesion_global.es_superadmin() and bool(self._id_contrato_actual)
                       and not self._contrato_firmado)
        except Exception as e:
            logger.debug("visibilidad firmado: %s", e)
        self.btn_firmado.setVisible(visible)

    def _marcar_firmado_click(self):
        from src.db.usuario import sesion_global
        if not sesion_global.es_superadmin() or not self._id_contrato_actual:
            return
        if not mostrar_confirmacion(
                self, "Firmar contrato",
                "¿Confirmas que el contrato ha sido firmado por el trabajador?\n\n"
                "Se marcará el contrato como firmado y, si tiene activada la cláusula de "
                "bolsa de horas, se dará de alta su seguimiento (vigencia y plazo de "
                "regularización) a partir de hoy."):
            return
        try:
            from src.rrhh.db import contratos as CT
            usuario = getattr(sesion_global, "usuario_actual", None) or {}
            ok = CT.marcar_firmado(self._id_contrato_actual, self._id_empresa(),
                                   creado_por=usuario.get("id"))
        except Exception as e:
            logger.error("marcar_firmado: %s", e)
            ok = False
        if ok:
            self._contrato_firmado = True
            self._actualizar_visibilidad_firmado()
            mostrar_mensaje(self, "Contrato", "Contrato marcado como firmado.", "success")
        else:
            mostrar_mensaje(self, "Contrato", "No se pudo marcar el contrato como firmado.", "error")

    def _persistir_campos_extendidos(self, nif, ruta):
        """Tras `_generar_pdf()` (que ya disparó, best-effort, `registrar_generacion` →
        `contratos.crear_contrato` con los campos base), localiza esa fila recién creada por
        `ref_documento=ruta` (único por generación — evita depender del orden de
        fecha_inicio/id, que puede no reflejar "la más reciente" si se backdata una fecha de
        inicio) y la completa con los campos nuevos de esta fase."""
        from src.rrhh.db import contratos as CT, empleados
        emp = empleados.obtener_por_nif((nif or "").strip(), self._id_empresa())
        if not emp:
            return
        id_contrato = None
        for c in CT.listar_contratos(emp["id"], self._id_empresa()):
            if c.get("ref_documento") == ruta:
                id_contrato = c.get("id")
                break
        if not id_contrato:
            return
        CT.actualizar_contrato(id_contrato, self._id_empresa(), **self._recoger_campos_extendidos())
        self._id_contrato_actual = id_contrato
        self._contrato_firmado = False

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

    def _listar_contratos_empleado(self, id_empleado, id_empresa):
        from src.rrhh.db import contratos as CT
        return CT.listar_contratos(id_empleado, id_empresa)

    def _abrir_documento(self, fila):
        ruta = fila.get("ref_documento")
        if ruta and os.path.exists(ruta):
            from src.utils import plataforma
            plataforma.abrir_archivo(ruta)
        else:
            mostrar_mensaje(self, "Contrato", "El documento no está disponible en disco.", "warning")

    def _on_empleado(self, _i):
        emp = self.cb_emp.currentData()
        self._lista.refrescar(emp.get("id") if emp else None)
        if emp:
            self._autollenar(emp)
            self._cargar_contrato_vigente(emp)
        else:
            self._resetear_campos_extendidos()
            self._id_contrato_actual = None
            self._contrato_firmado = False
            self._actualizar_visibilidad_firmado()

    def _autollenar_actual(self):
        emp = self.cb_emp.currentData()
        if not emp:
            mostrar_mensaje(self, "Contrato", "Selecciona primero un empleado.", "warning")
            return
        self._autollenar(emp)

    def _autollenar(self, emp):
        """Autocompleta los datos del trabajador desde la capa de datos MAESTROS unificada."""
        try:
            from src.rrhh import maestros
            flat = maestros.campos_documento(emp, self._id_empresa())
        except Exception as e:
            logger.debug("autollenar contrato: %s", e); flat = {}
        mapa = {
            "trabajador": flat.get("nombre"), "nif": flat.get("nif"), "ss": flat.get("num_ss"),
            "fecha_nacimiento": flat.get("fecha_nacimiento"), "nacionalidad": flat.get("nacionalidad"),
            "municipio_domicilio": flat.get("municipio"), "provincia_domicilio": flat.get("provincia"),
            "cp_domicilio": flat.get("cp"), "telefono_trab": flat.get("telefono"),
            "email_trab": flat.get("email"), "puesto": flat.get("puesto"),
            "convenio": flat.get("convenio"),
        }
        for k, v in mapa.items():
            if v:
                self._set(k, v)
        # Sexo (H/M → etiqueta del combo).
        sx = (str(emp.get("sexo") or "").strip().upper()[:1])
        if sx == "H":
            self._set("sexo", "HOMBRE")
        elif sx in ("M", "F"):
            self._set("sexo", "MUJER")
        # Modalidad: si el tipo de contrato maestro coincide con una opción.
        tc = str(flat.get("tipo_contrato") or "").strip().upper()
        if tc in MODALIDADES:
            self._set("subtipo", tc)

    # ── Generación (reutiliza el motor del asistente, sin modificarlo) ──────────
    def _generar(self):
        datos = self._recoger()
        if not datos.get("trabajador"):
            mostrar_mensaje(self, "Contrato", "Indica al menos el nombre del trabajador.", "warning")
            return
        try:
            wz = self._wizard()
            wz._datos = dict(datos)                 # el motor lee TODO desde _datos
            wz._generar_pdf()                        # generación EXISTENTE (sin cambios)
            ruta = getattr(wz, "_pdf_ruta", None)
            if not ruta:
                mostrar_mensaje(self, "Contrato", "No se pudo generar el contrato.", "error")
                return
            try:
                from src.db.documentos import registrar_documento
                registrar_documento(ruta, tipo="contrato",
                                    nombre=ruta.replace("\\", "/").split("/")[-1],
                                    referencia=str(datos.get("nif") or ""))
            except Exception:
                pass
            # Fase B: la fila base en rrhh_contratos ya la creó `_generar_pdf` (best-effort,
            # vía `registrar_generacion`) — aquí solo la completamos con los campos nuevos de
            # esta fase, que el motor genérico del asistente no conoce.
            self._id_contrato_actual = None
            self._contrato_firmado = False
            try:
                self._persistir_campos_extendidos(datos.get("nif"), ruta)
            except Exception as e:
                logger.debug("persistir campos extendidos del contrato: %s", e)
            self._actualizar_visibilidad_firmado()
            emp_sel = self.cb_emp.currentData()
            if emp_sel and emp_sel.get("id"):
                self._lista.refrescar(emp_sel["id"])
            mostrar_mensaje(self, "Contrato", "Contrato generado correctamente.", "success")
            try:
                from src.utils import plataforma
                plataforma.abrir_carpeta(ruta.replace("\\", "/").rsplit("/", 1)[0])
            except Exception:
                pass
        except Exception as e:
            logger.error("generar contrato: %s", e)
            mostrar_mensaje(self, "Contrato", "No se pudo generar el contrato.", "error")
