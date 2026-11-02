"""
Formulario INLINE de Finiquitos (RRHH · Laboral). Mismo patrón/UX que `rrhh_nomina_inline.
NominaInlineForm`: selección de empleado + "Autocompletar" (datos maestros) + "Calcular" (motor
`finiquito_servicio`, que reutiliza `nomina_motor`/`nomina_servicio` para la parte salarial/SS/
IRPF del finiquito — nunca la duplica) + "Generar finiquito (PDF)" (documento legal, generación
sin cambios: `finiquito_pdf.generar_finiquito_pdf`).

Sustituye, solo para el tipo FINIQUITO, al formulario genérico `rrhh_doc_inline.
DocumentoInlineForm` (que no sabe calcular nada) — el resto de documentos RRHH lo siguen usando
sin cambios.
"""

import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from assets.estilo_global import (
    COLOR_ACCION_TEXTO, COLOR_BORDE, COLOR_CIAN, COLOR_FONDO_WIDGET, mostrar_mensaje,
)
from src.gui.rrhh_doc_list_widget import EmpleadoRegistrosList
from src.rrhh.documents.render.finiquito_pdf import (
    CONCEPTOS_IMPORTE, DECLARACION, DESCUENTOS_IMPORTE, DETALLE_CAMPOS, EMPRESA_CAMPOS,
    EXTINCION_CAMPOS, MOTIVOS, RETENCION_CAMPO, TESTIGOS_CAMPO, TIPOS_DESPIDO, TRABAJADOR_CAMPOS,
    generar_finiquito_pdf,
)
from src.rrhh.finiquito_servicio import GestionFiniquitoError, calcular_y_guardar_borrador

logger = logging.getLogger("gui.rrhh.finiquito_inline")

_INP_SS = (
    f"background:{COLOR_FONDO_WIDGET};color:#FFFFFF;border:1px solid {COLOR_BORDE};"
    f"border-radius:8px;padding:6px 10px;font-family:'Segoe UI';font-size:15px;"
)
_LBL_SS = "color:#C9D1D9;font-family:'Segoe UI';font-size:14px;font-weight:bold;background:transparent;"
_CB_SS = _INP_SS.replace("font-size:15px", "font-size:14px")

_CAMPOS_COMBO = {"motivo_extincion": MOTIVOS, "tipo_despido": TIPOS_DESPIDO, "declaracion": DECLARACION}


class FiniquitoInlineForm(QWidget):
    def __init__(self, id_empresa_getter, parent=None):
        super().__init__(parent)
        self._id_empresa = id_empresa_getter
        self._inputs = {}
        self._empleados = []
        # Disciplina borrador/aprobada (mismo espíritu que rrhh_nominas.estado): id/estado del
        # borrador persistido en `rrhh_finiquitos` por el último "Calcular" — ver `_calcular`.
        self._finiquito_id = None
        self._finiquito_estado = None
        self._build()
        self._cargar_empleados()

    # ── Construcción de UI ────────────────────────────────────────────────────
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
        cont.setStyleSheet(f"QLineEdit{{{_INP_SS}}}QComboBox{{{_CB_SS}}}QLabel{{{_LBL_SS}}}")

        self._seccion("Datos del trabajador/a")
        self._grid(TRABAJADOR_CAMPOS)
        self._seccion("Extinción de la relación laboral")
        self._grid(EXTINCION_CAMPOS)
        self._seccion("Detalle de conceptos (días/unidades) — 'Calcular' rellena lo automático")
        self._grid(DETALLE_CAMPOS)
        self._seccion("Conceptos devengados (importes)")
        self._grid(CONCEPTOS_IMPORTE, importe=True)
        self._seccion("Deducciones (S.S. trabajador se calcula automáticamente)")
        self._grid(DESCUENTOS_IMPORTE + [RETENCION_CAMPO], importe=True)
        self._seccion("Declaración y firmas")
        self._grid([("declaracion", "Declaración"), TESTIGOS_CAMPO])

        # Finiquitos (borrador/aprobada) ya registrados para el empleado seleccionado
        # (`rrhh_finiquitos`, migr 0265 — mismo dato que ya lista `ExpedienteDialog._tab_finiquitos`,
        # reutilizado aquí sin duplicar la lógica de aprobación, que sigue solo en el expediente).
        # Vive DENTRO del mismo QScrollArea que el resto del formulario (una sección más de
        # `_form_ly`, no un bloque fijo aparte fuera de él): así queda literalmente debajo de los
        # campos, en el mismo flujo desplazable de arriba a abajo, en vez de competir por altura
        # fija con el formulario cuando la ventana es pequeña.
        self._lista = EmpleadoRegistrosList(
            "Finiquitos del empleado",
            [("fecha_efectos", "Fecha efectos"), ("total_bruto", "Bruto"),
             ("total_liquido", "Líquido"), ("estado", "Estado")],
            self._listar_finiquitos_empleado, self._id_empresa,
            abrir_fn=self._abrir_documento, boton="Reabrir")
        self._form_ly.addWidget(self._lista)

        self._form_ly.addStretch()
        scroll.setWidget(cont)
        root.addWidget(scroll, 1)

        self.lbl_resumen = QLabel("")
        self.lbl_resumen.setStyleSheet(f"color:{COLOR_CIAN};font-family:'Segoe UI';font-size:15px;"
                                       "font-weight:bold;background:transparent;")
        self.lbl_resumen.setWordWrap(True)
        bottom = QHBoxLayout()
        bottom.addWidget(self.lbl_resumen, 1)
        bottom.addWidget(self._btn("Calcular", self._calcular))
        bottom.addWidget(self._btn("Generar finiquito (PDF)", self._generar, primary=True))
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

    def _grid(self, campos, *, importe=False):
        grid = QGridLayout(); grid.setHorizontalSpacing(18); grid.setVerticalSpacing(8)
        for i, (clave, etiqueta) in enumerate(campos):
            r, c = divmod(i, 2)
            cel = QVBoxLayout(); cel.setSpacing(2)
            cel.addWidget(QLabel(etiqueta))
            if clave in _CAMPOS_COMBO:
                inp = QComboBox(); inp.addItems(list(_CAMPOS_COMBO[clave]))
            else:
                inp = QLineEdit()
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

    def _cargar_empleados(self):
        try:
            from src.rrhh.db import empleados
            self._empleados = empleados.listar_empleados(self._id_empresa(), estado="activo") or []
        except Exception as e:
            logger.debug("finiquito: cargar empleados: %s", e); self._empleados = []
        self.cb_emp.blockSignals(True); self.cb_emp.clear()
        self.cb_emp.addItem("— Selecciona un empleado —", None)
        for e in self._empleados:
            nom = f"{e.get('nombre','')} {e.get('apellidos','')}".strip()
            self.cb_emp.addItem(f"{nom}  ·  {e.get('nif','')}", e)
        self.cb_emp.blockSignals(False)

    def _listar_finiquitos_empleado(self, id_empleado, id_empresa):
        from src.rrhh.db import finiquitos as FQ
        return FQ.listar_finiquitos(id_empleado, id_empresa)

    def _abrir_documento(self, fila):
        ruta = fila.get("ref_documento")
        if ruta and os.path.exists(ruta):
            from src.utils import plataforma
            plataforma.abrir_archivo(ruta)
        else:
            mostrar_mensaje(self, "Finiquitos", "El documento no está disponible en disco.", "warning")

    def _on_empleado(self, _idx):
        emp = self.cb_emp.currentData()
        # Cambiar de empleado invalida cualquier borrador calculado para el anterior: no debe
        # reutilizarse el id de otro empleado ni la etiqueta de "borrador guardado".
        self._finiquito_id = None
        self._finiquito_estado = None
        self._lista.refrescar(emp.get("id") if emp else None)
        if emp:
            self._autollenar(emp)

    def _autollenar_actual(self):
        emp = self.cb_emp.currentData()
        if not emp:
            mostrar_mensaje(self, "Finiquitos", "Selecciona primero un empleado.", "warning"); return
        self._autollenar(emp)

    def _autollenar(self, emp):
        """Datos maestros unificados (Empresa · Trabajador · Contrato · Incidencias · Extinción) —
        mismo origen (`maestros.campos_documento`) que usaba el formulario genérico anterior."""
        try:
            from src.rrhh import maestros
            for clave, valor in maestros.campos_documento(emp, self._id_empresa()).items():
                self._set(clave, valor)
        except Exception as e:
            logger.debug("finiquito autollenar maestros: %s", e)

    def _recoger(self) -> dict:
        datos = {k: self._get(w) for k, w in self._inputs.items()}
        datos.update(self._empresa_valores())
        return datos

    def _empresa_valores(self) -> dict:
        try:
            from src.rrhh import maestros
            emp = maestros.entidad_empresa(self._id_empresa()) or {}
        except Exception as e:
            logger.debug("finiquito empresa_valores: %s", e); emp = {}
        return {k: (emp.get(k) or "") for k, _ in EMPRESA_CAMPOS}

    # ── Acciones ──────────────────────────────────────────────────────────────
    def _calcular(self):
        emp = self.cb_emp.currentData()
        if not emp:
            mostrar_mensaje(self, "Finiquitos", "Selecciona primero un empleado.", "warning")
            return
        fecha_efectos = self._get(self._inputs.get("fecha_efectos")) if "fecha_efectos" in self._inputs else ""
        if not fecha_efectos:
            mostrar_mensaje(self, "Finiquitos",
                            "Indica la fecha de efectos (DD/MM/AAAA) antes de calcular.", "warning")
            return
        try:
            res, id_finiquito = calcular_y_guardar_borrador(
                emp.get("id"), self._id_empresa(), fecha_efectos)
        except GestionFiniquitoError as e:
            mostrar_mensaje(self, "Finiquitos", str(e), "error")
            return
        except Exception as e:
            logger.error("calcular finiquito: %s", e)
            mostrar_mensaje(self, "Finiquitos", "No se pudo calcular el finiquito.", "error")
            return

        self._finiquito_id = id_finiquito
        self._finiquito_estado = "borrador" if id_finiquito else None
        if not id_finiquito:
            # El cálculo salió bien pero no se pudo guardar el borrador (ver docstring de
            # `calcular_y_guardar_borrador`): se avisa explícitamente en vez de dejar creer que
            # ya quedó guardado — "Generar" seguirá funcionando pero SIEMPRE con marca de agua.
            logger.warning("finiquito calculado para empleado %s pero el borrador NO se guardó "
                           "en rrhh_finiquitos", emp.get("id"))

        self._set("dias_trabajados", res.dias_trabajados)
        self._set("vac_generadas", res.vac_generadas)
        self._set("vac_disfrutadas", res.vac_disfrutadas)
        self._set("vac_pendientes", res.vac_pendientes)
        self._set("pagas_prorrateadas", "Sí")   # ver finiquito_servicio: suposición por defecto documentada
        self._set("imp_salario_pendiente", res.imp_salario_pendiente)
        self._set("imp_vacaciones", res.imp_vacaciones)
        self._set("imp_pagas", res.imp_pagas)
        self._set("imp_horas_extras", res.imp_horas_extras)
        self._set("retencion_pct", res.retencion_pct)
        self._set("desc_ss_trabajador", res.desc_ss_trabajador)

        from src.utils import divisas
        eur = divisas.formatear
        estado_txt = ("guardado como BORRADOR — pendiente de aprobación SUPERADMIN" if id_finiquito
                     else "calculado (AVISO: el borrador no se pudo guardar en BD)")
        self.lbl_resumen.setText(
            f"Auto-calculado ({estado_txt}) — Bruto: {eur(res.total_bruto)}   ·   S.S. trabajador: "
            f"{eur(res.desc_ss_trabajador)}   ·   Líquido (sin indemnización/otros manuales): "
            f"{eur(res.total_liquido)}")
        self._lista.refrescar(emp.get("id"))

    def _generar(self):
        datos = self._recoger()
        if not (datos.get("nif") or datos.get("nombre")):
            mostrar_mensaje(self, "Finiquitos", "Indica al menos el trabajador (nombre o DNI).", "warning")
            return
        # Disciplina borrador/aprobada (mismo espíritu que rrhh_nominas): el PDF SIGUE siendo
        # generable en cualquier momento (igual que la nómina — la aprobación es un flag de
        # auditoría, no un bloqueo técnico), pero mientras el borrador calculado en `_calcular`
        # no esté 'aprobada' (o directamente no se haya calculado/guardado en esta sesión), el
        # documento sale con marca de agua "BORRADOR" para que nadie lo confunda con el
        # finiquito definitivo firmado.
        es_borrador = self._finiquito_estado != "aprobada"
        try:
            ruta = generar_finiquito_pdf(datos, borrador=es_borrador)
            try:
                from src.db.documentos import registrar_documento
                registrar_documento(ruta, tipo="finiquito",
                                    nombre=ruta.replace("\\", "/").split("/")[-1],
                                    referencia=str(datos.get("nif") or ""))
            except Exception:
                pass
            if self._finiquito_id:
                try:
                    from src.rrhh.db import finiquitos as _db_finiquitos
                    _db_finiquitos.actualizar_finiquito(
                        self._finiquito_id, self._id_empresa(), ref_documento=ruta)
                except Exception as e:
                    logger.debug("finiquito: no se pudo enlazar ref_documento: %s", e)
            emp_sel = self.cb_emp.currentData()
            if emp_sel and emp_sel.get("id"):
                self._lista.refrescar(emp_sel["id"])
            if es_borrador:
                mostrar_mensaje(
                    self, "Finiquitos",
                    "Finiquito BORRADOR generado en /documentos/finiquitos (marca de agua: "
                    "pendiente de aprobación). Un SUPERADMIN debe aprobarlo desde el expediente "
                    "del empleado para obtener el documento definitivo.", "warning")
            else:
                mostrar_mensaje(self, "Finiquitos",
                                "Finiquito generado correctamente en /documentos/finiquitos.", "success")
            try:
                from src.utils import plataforma
                plataforma.abrir_carpeta(ruta.replace("\\", "/").rsplit("/", 1)[0])
            except Exception:
                pass
        except Exception as e:
            logger.error("generar finiquito: %s", e)
            mostrar_mensaje(self, "Finiquitos", "No se pudo generar el finiquito.", "error")
