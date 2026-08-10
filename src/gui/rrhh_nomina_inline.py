"""
Formulario INLINE de Nóminas (RRHH · Laboral). Sustituye al botón del asistente: los campos para
generar el recibo de salarios se rellenan directamente en la pestaña. Reutiliza el motor de cálculo
(`nomina_servicio`) y el generador de PDF autónomo (`nomina_pdf`). Autocompleta empresa y trabajador.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from assets.estilo_global import (
    COLOR_ACCION_TEXTO, COLOR_BORDE, COLOR_CIAN, COLOR_FONDO_APP, COLOR_FONDO_WIDGET,
    COLOR_TEXTO_SECUNDARIO, mostrar_mensaje,
)
from src.rrhh.documents.render.nomina_pdf import (
    DEVENGOS_NO_SALARIALES, DEVENGOS_SALARIALES, EMPRESA_CAMPOS, INFO_ADICIONAL,
    OTRAS_DEDUCCIONES, PERIODO_CAMPOS, TRABAJADOR_CAMPOS, generar_nomina_pdf,
)

logger = logging.getLogger("gui.rrhh.nomina_inline")

_INP_SS = (
    f"QLineEdit{{background:{COLOR_FONDO_WIDGET};color:#FFFFFF;border:1px solid {COLOR_BORDE};"
    f"border-radius:8px;padding:6px 10px;font-family:'Segoe UI';font-size:15px;}}"
    f"QLineEdit:focus{{border:1px solid {COLOR_CIAN};}}"
)
_LBL_SS = f"color:#C9D1D9;font-family:'Segoe UI';font-size:14px;font-weight:bold;background:transparent;"


class NominaInlineForm(QWidget):
    def __init__(self, id_empresa_getter, parent=None):
        super().__init__(parent)
        self._id_empresa = id_empresa_getter
        self._inputs = {}
        self._empleados = []
        self._build()
        self._cargar_empleados()

    # ── Construcción de UI ────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(10)

        # Barra superior: selección de empleado + acciones.
        top = QHBoxLayout(); top.setSpacing(10)
        top.addWidget(self._lbl("Empleado:"))
        self.cb_emp = QComboBox()
        self.cb_emp.setMinimumWidth(280)
        self.cb_emp.setStyleSheet(
            f"QComboBox{{background:{COLOR_FONDO_WIDGET};color:#FFF;border:1px solid {COLOR_BORDE};"
            f"border-radius:8px;padding:6px 10px;font-family:'Segoe UI';font-size:14px;}}")
        self.cb_emp.currentIndexChanged.connect(self._on_empleado)
        top.addWidget(self.cb_emp, 1)
        top.addWidget(self._btn("Autocompletar", self._autollenar_actual))
        top.addStretch()
        root.addLayout(top)

        # Zona scroll con las secciones de campos.
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        cont = QWidget(); self._form_ly = QVBoxLayout(cont)
        self._form_ly.setContentsMargins(2, 4, 12, 4); self._form_ly.setSpacing(14)
        # Estilo de campos Y etiquetas aplicado UNA sola vez por cascada (no widget a widget): con
        # ~86 campos + 86 etiquetas, hacer setStyleSheet por widget encarecía notablemente el montaje.
        # Las cabeceras de sección llevan su propio estilo (prevalece sobre esta regla de contenedor).
        cont.setStyleSheet(_INP_SS + f"QLabel{{{_LBL_SS}}}")

        self._seccion("Datos de la empresa")
        self._grid_texto(EMPRESA_CAMPOS)
        self._seccion("Datos del trabajador/a")
        self._grid_texto(TRABAJADOR_CAMPOS)
        self._seccion("Período de liquidación")
        self._grid_texto(PERIODO_CAMPOS)
        self._seccion("Parámetros de cálculo")
        self._grid_texto([("irpf_pct", "Tipo IRPF (%)"), ("num_pagas", "Nº pagas/año")])
        self._seccion("Devengos · Percepciones salariales")
        self._grid_importe(DEVENGOS_SALARIALES)
        self._seccion("Devengos · Percepciones no salariales")
        self._grid_importe(DEVENGOS_NO_SALARIALES)
        self._seccion("Deducciones (otras — SS e IRPF se calculan automáticamente)")
        self._grid_importe(OTRAS_DEDUCCIONES)
        self._seccion("Información adicional")
        self._grid_texto(INFO_ADICIONAL)

        self._form_ly.addStretch()
        scroll.setWidget(cont)
        root.addWidget(scroll, 1)

        # Barra inferior: resumen + acciones.
        self.lbl_resumen = QLabel("")
        self.lbl_resumen.setStyleSheet(f"color:{COLOR_CIAN};font-family:'Segoe UI';font-size:16px;"
                                       "font-weight:bold;background:transparent;")
        bottom = QHBoxLayout()
        bottom.addWidget(self.lbl_resumen, 1)
        bottom.addWidget(self._btn("Calcular", self._calcular))
        bottom.addWidget(self._btn("Generar nómina (PDF)", self._generar, primary=True))
        root.addLayout(bottom)

        # Valores por defecto sensatos.
        self._set("num_pagas", "12"); self._set("irpf_pct", "15")

    def _lbl(self, txt):
        l = QLabel(txt); l.setStyleSheet(_LBL_SS); return l

    def _btn(self, txt, cb, primary=False):
        b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(40)
        if primary:
            b.setStyleSheet(
                f"QPushButton{{background:{COLOR_CIAN};color:{COLOR_ACCION_TEXTO};border:none;"
                f"border-radius:10px;padding:8px 18px;font-family:'Segoe UI';font-weight:bold;font-size:15px;}}"
                f"QPushButton:hover{{background:{COLOR_ACCION_TEXTO};color:{COLOR_CIAN};"
                f"border:2px solid {COLOR_CIAN};}}")
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

    def _grid_texto(self, campos):
        self._grid(campos, importe=False)

    def _grid_importe(self, campos):
        self._grid(campos, importe=True)

    def _grid(self, campos, *, importe):
        grid = QGridLayout(); grid.setHorizontalSpacing(18); grid.setVerticalSpacing(8)
        cols = 2
        for i, (clave, etiqueta) in enumerate(campos):
            r, c = divmod(i, cols)
            cel = QVBoxLayout(); cel.setSpacing(2)
            cel.addWidget(QLabel(etiqueta))   # estilo por cascada desde el contenedor (ver _build)
            inp = QLineEdit()   # estilo por cascada desde el contenedor (ver _build)
            if importe:
                inp.setText("0"); inp.setAlignment(Qt.AlignmentFlag.AlignRight)
                inp.setPlaceholderText("0,00")
            self._inputs[clave] = inp
            cel.addWidget(inp)
            w = QWidget(); w.setLayout(cel)
            grid.addWidget(w, r, c)
        holder = QWidget(); holder.setLayout(grid)
        self._form_ly.addWidget(holder)

    # ── Datos ─────────────────────────────────────────────────────────────────
    def _set(self, clave, valor):
        if clave in self._inputs:
            self._inputs[clave].setText("" if valor is None else str(valor))

    def _cargar_empleados(self):
        try:
            from src.rrhh.db import empleados
            self._empleados = empleados.listar_empleados(self._id_empresa(), estado="activo") or []
        except Exception as e:
            logger.debug("cargar empleados: %s", e); self._empleados = []
        self.cb_emp.blockSignals(True)
        self.cb_emp.clear()
        self.cb_emp.addItem("— Selecciona un empleado —", None)
        for e in self._empleados:
            nom = f"{e.get('nombre','')} {e.get('apellidos','')}".strip()
            self.cb_emp.addItem(f"{nom}  ·  {e.get('nif','')}", e)
        self.cb_emp.blockSignals(False)

    def _on_empleado(self, _idx):
        emp = self.cb_emp.currentData()
        if emp:
            self._autollenar(emp)

    def _autollenar_actual(self):
        emp = self.cb_emp.currentData()
        if not emp:
            mostrar_mensaje(self, "Nóminas", "Selecciona primero un empleado.", "warning"); return
        self._autollenar(emp)

    def _autollenar(self, emp):
        # Empresa (datos corporativos).
        try:
            from src.db.empresa import datos_corporativos
            dc = datos_corporativos(self._id_empresa()) or {}
        except Exception:
            dc = {}
        mapa_emp = {
            "razon_social": dc.get("razon_social") or dc.get("nombre"),
            "nombre_comercial": dc.get("nombre_comercial"), "cif": dc.get("cif"),
            "ccc": dc.get("ccc"), "domicilio": dc.get("direccion_fiscal") or dc.get("direccion"),
            "cp": dc.get("cp"), "municipio": dc.get("municipio"), "provincia": dc.get("provincia"),
            "telefono": dc.get("telefono"), "email": dc.get("email") or dc.get("email_principal"),
            "cnae": dc.get("cnae"), "convenio": dc.get("convenio_colectivo") or dc.get("convenio"),
        }
        for k, v in mapa_emp.items():
            if v:
                self._set(k, v)
        # Trabajador.
        apellidos = (emp.get("apellidos") or "").split()
        mapa_trab = {
            "trab_nombre": emp.get("nombre"),
            "trab_apellido1": apellidos[0] if apellidos else "",
            "trab_apellido2": " ".join(apellidos[1:]) if len(apellidos) > 1 else "",
            "nif": emp.get("nif"), "num_ss": emp.get("num_ss"), "categoria": emp.get("categoria"),
            "grupo_prof": emp.get("grupo_prof"), "puesto": emp.get("puesto"),
            "fecha_alta": emp.get("fecha_alta"), "jornada": emp.get("jornada"),
            "trab_direccion": emp.get("direccion"), "trab_cp": emp.get("cp"),
            "trab_municipio": emp.get("municipio"), "trab_provincia": emp.get("provincia"),
        }
        for k, v in mapa_trab.items():
            if v:
                self._set(k, v)
        if emp.get("convenio"):
            self._set("convenio", emp.get("convenio"))
        # Salario base.
        if emp.get("salario_base"):
            self._set("salario_base", emp.get("salario_base"))
        # Contrato MAESTRO: unifica salario/jornada/convenio con el resto de documentos (fuente única).
        try:
            from src.rrhh import maestros
            K = maestros.entidad_contrato(emp.get("id"), self._id_empresa())
            if K.get("salario"):
                self._set("salario_base", K.get("salario"))
            if K.get("jornada"):
                self._set("jornada", K.get("jornada"))
        except Exception as e:
            logger.debug("nomina contrato maestro: %s", e)

    def _recoger(self) -> dict:
        return {k: (w.text().strip() if isinstance(w, QLineEdit) else "") for k, w in self._inputs.items()}

    # ── Acciones ──────────────────────────────────────────────────────────────
    def _calcular(self):
        try:
            from src.rrhh.documents.render.nomina_pdf import _preparar_engine
            from src.rrhh.nomina_servicio import calcular_desde_datos, num
            datos = self._recoger()
            res = calcular_desde_datos(_preparar_engine(datos))
            from src.utils import divisas
            eur = divisas.formatear
            total_dev = sum(num(datos.get(k)) for k, _ in DEVENGOS_SALARIALES + DEVENGOS_NO_SALARIALES)
            otras = sum(num(datos.get(k)) for k, _ in OTRAS_DEDUCCIONES)
            total_ded = round(res.ss_trabajador.get("total", 0.0) + res.irpf_importe + otras, 2)
            liq = round(total_dev - total_ded, 2)
            self.lbl_resumen.setText(
                f"Devengado: {eur(round(total_dev,2))}   ·   Deducciones: {eur(total_ded)}   ·   "
                f"Líquido: {eur(liq)}")
        except Exception as e:
            logger.error("calcular nómina: %s", e)
            mostrar_mensaje(self, "Nóminas", "No se pudo calcular la nómina.", "error")

    def _generar(self):
        datos = self._recoger()
        if not (datos.get("trab_nombre") or datos.get("nif")):
            mostrar_mensaje(self, "Nóminas", "Indica al menos el trabajador (nombre o NIF).", "warning")
            return
        try:
            ruta = generar_nomina_pdf(datos)
            try:
                from src.db.documentos import registrar_documento
                registrar_documento(ruta, tipo="nomina",
                                    nombre=ruta.split("\\")[-1].split("/")[-1],
                                    referencia=str(datos.get("nif") or ""))
            except Exception:
                pass
            self._calcular()
            mostrar_mensaje(self, "Nóminas",
                            "Nómina generada correctamente en /documentos/nominas.", "success")
            try:
                from src.utils import plataforma
                plataforma.abrir_carpeta(ruta.rsplit("\\", 1)[0].rsplit("/", 1)[0])
            except Exception:
                pass
        except Exception as e:
            logger.error("generar nómina: %s", e)
            mostrar_mensaje(self, "Nóminas", "No se pudo generar la nómina.", "error")
