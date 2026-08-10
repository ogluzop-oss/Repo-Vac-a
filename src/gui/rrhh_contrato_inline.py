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

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from assets.estilo_global import (
    COLOR_ACCION_TEXTO, COLOR_BORDE, COLOR_CIAN, COLOR_FONDO_WIDGET, mostrar_mensaje,
)

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
        self._build()
        self._cargar_empleados()

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

        self._form_ly.addStretch()
        scroll.setWidget(cont)
        root.addWidget(scroll, 1)

        bottom = QHBoxLayout(); bottom.addStretch()
        bottom.addWidget(self._btn("Generar contrato (PDF)", self._generar, primary=True))
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
            mostrar_mensaje(self, "Contrato", "Contrato generado correctamente.", "success")
            try:
                from src.utils import plataforma
                plataforma.abrir_carpeta(ruta.replace("\\", "/").rsplit("/", 1)[0])
            except Exception:
                pass
        except Exception as e:
            logger.error("generar contrato: %s", e)
            mostrar_mensaje(self, "Contrato", "No se pudo generar el contrato.", "error")
