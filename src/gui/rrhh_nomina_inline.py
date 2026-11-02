"""
Formulario INLINE de Nóminas (RRHH · Laboral). Sustituye al botón del asistente: los campos para
generar el recibo de salarios se rellenan directamente en la pestaña. Reutiliza el motor de cálculo
(`nomina_servicio`) y el generador de PDF autónomo (`nomina_pdf`). Autocompleta empresa y trabajador.
"""

import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from assets.estilo_global import (
    COLOR_ACCION_TEXTO, COLOR_BORDE, COLOR_CIAN, COLOR_FONDO_APP, COLOR_FONDO_WIDGET,
    COLOR_TEXTO_SECUNDARIO, mostrar_mensaje,
)
from src.gui.rrhh_doc_list_widget import EmpleadoRegistrosList
from src.rrhh.documents.render.nomina_pdf import (
    DEVENGOS_NO_SALARIALES, DEVENGOS_SALARIALES, EMPRESA_CAMPOS, INFO_ADICIONAL,
    OTRAS_DEDUCCIONES, PERIODO_CAMPOS, TRABAJADOR_CAMPOS, generar_nomina_pdf,
)
from src.rrhh.nomina_servicio import GestionNominaError, num

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
            f"border-radius:8px;padding:6px 10px;font-family:'Segoe UI';font-size:14px;}}"
            f"QComboBox::drop-down{{border:none;width:22px;background:transparent;}}")
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

        # Los DATOS DE EMPRESA ya no se piden aquí: se inyectan automáticamente al recoger, desde
        # "Datos de empresa" (Configuración). Ver `_empresa_valores`.
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

        # Nóminas ya generadas para el empleado seleccionado (`rrhh_nominas`, alimentada por
        # `persistencia.registrar_generacion` al generar el PDF — ver `_generar`). Vive DENTRO del
        # mismo QScrollArea que el resto del formulario (una sección más de `_form_ly`, no un
        # bloque fijo aparte fuera de él): así queda literalmente debajo de los campos, en el
        # mismo flujo desplazable de arriba a abajo, en vez de competir por altura fija con el
        # formulario cuando la ventana es pequeña.
        self._lista = EmpleadoRegistrosList(
            "Nóminas generadas del empleado",
            [("anio", "Año"), ("mes", "Mes"), ("bruto", "Bruto"), ("neto", "Neto"),
             ("estado", "Estado")],
            self._listar_nominas_empleado, self._id_empresa,
            abrir_fn=self._abrir_documento, boton="Reabrir")
        self._form_ly.addWidget(self._lista)

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

        # Valores por defecto sensatos. El IRPF YA NO se precarga a un 15% fijo (Fase F.2): se
        # autorrellena desde `rrhh_datos_fiscales.irpf_pct_calculado` al elegir empleado
        # (`_autollenar`) — este campo queda vacío hasta entonces, editable como excepción puntual
        # igual que el resto de campos del formulario.
        self._set("num_pagas", "12")

        # Prellenado automático del prorrateo de pagas extra (mismo motor que el cálculo final —
        # `nomina_motor.calcular_prorrateo_pagas_extra`) cuando cambian "Salario base" o "Nº
        # pagas/año". Solo PREFILL: si el usuario edita después el campo a mano, no se vuelve a
        # pisar mientras no cambien de nuevo esos dos campos de origen (ver `_actualizar_prorrateo_auto`).
        self._prorrateo_auto = None
        self._inputs["salario_base"].textChanged.connect(self._actualizar_prorrateo_auto)
        self._inputs["num_pagas"].textChanged.connect(self._actualizar_prorrateo_auto)

    def _lbl(self, txt):
        l = QLabel(txt); l.setStyleSheet(_LBL_SS); return l

    def _btn(self, txt, cb, primary=False):
        b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(40)
        if primary:
            b.setStyleSheet(
                f"QPushButton{{background:{COLOR_FONDO_WIDGET};color:{COLOR_CIAN};border:2px solid {COLOR_CIAN};"
                f"border-radius:10px;padding:8px 18px;font-family:'Segoe UI';font-weight:bold;font-size:15px;}}"
                f"QPushButton:hover{{background:{COLOR_CIAN};color:{COLOR_ACCION_TEXTO};"
                f"border-color:{COLOR_CIAN};}}")
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

    def _actualizar_prorrateo_auto(self):
        """Prellena 'Pagas extraordinarias prorrateadas' con el mismo cálculo del motor
        (`salario_base * max(num_pagas-12,0)/12`) al cambiar salario base o nº de pagas. No
        bloquea el campo: si el usuario ya lo editó a mano a un valor distinto del último
        auto-rellenado, no se lo pisa (solo prefill, nunca fuerza)."""
        campo = self._inputs.get("pagas_extra_prorrateadas")
        if campo is None:
            return
        try:
            from src.rrhh.nomina_motor import calcular_prorrateo_pagas_extra
            salario = num(self._inputs["salario_base"].text())
            num_pagas = int(num(self._inputs["num_pagas"].text()) or 12) or 12
            valor = calcular_prorrateo_pagas_extra(salario, num_pagas)
        except Exception as e:
            logger.debug("actualizar prorrateo auto: %s", e); return
        actual = num(campo.text())
        if self._prorrateo_auto is None or abs(actual - self._prorrateo_auto) < 0.005:
            campo.blockSignals(True)
            campo.setText(str(valor) if valor else "0")
            campo.blockSignals(False)
            self._prorrateo_auto = valor

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

    def _listar_nominas_empleado(self, id_empleado, id_empresa):
        from src.rrhh.db import nominas as NM
        return NM.listar_nominas(id_empleado, id_empresa)

    def _abrir_documento(self, fila):
        ruta = fila.get("ref_documento")
        if ruta and os.path.exists(ruta):
            from src.utils import plataforma
            plataforma.abrir_archivo(ruta)
        else:
            mostrar_mensaje(self, "Nóminas", "El documento no está disponible en disco.", "warning")

    def _on_empleado(self, _idx):
        emp = self.cb_emp.currentData()
        self._lista.refrescar(emp.get("id") if emp else None)
        if emp:
            self._autollenar(emp)

    def _autollenar_actual(self):
        emp = self.cb_emp.currentData()
        if not emp:
            mostrar_mensaje(self, "Nóminas", "Selecciona primero un empleado.", "warning"); return
        self._autollenar(emp)

    def _autollenar(self, emp):
        # Los datos de EMPRESA ya no se muestran en el formulario: se inyectan al recoger
        # (`_empresa_valores`). Aquí solo se autocompleta al trabajador y su contrato.
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
        # IBAN de domiciliación (petición explícita): se cablea con el expediente del empleado,
        # pero SOLO la máscara (4 últimos dígitos) — el IBAN completo nunca se muestra ni se
        # imprime en la nómina generada, se queda cifrado en `rrhh_empleados.iban`.
        if emp.get("iban_mascara"):
            self._set("iban", emp.get("iban_mascara"))
        # Salario base (mensual). `rrhh_empleados.salario_base` YA es mensual (fuente de partida
        # si aún no hay contrato con datos propios).
        if emp.get("salario_base"):
            self._set("salario_base", emp.get("salario_base"))

        # Contrato MAESTRO: unifica jornada/convenio/modelo de pago con el resto de documentos.
        K = {}
        try:
            from src.rrhh import maestros
            K = maestros.entidad_contrato(emp.get("id"), self._id_empresa()) or {}
            if K.get("jornada"):
                self._set("jornada", K.get("jornada"))
        except Exception as e:
            logger.debug("nomina contrato maestro: %s", e)
        self._contrato_actual = K

        modelo_pago = str(K.get("modelo_pago") or "fijo").strip().lower()
        if modelo_pago == "hora":
            # Fase F.3: el bruto NUNCA sale de un salario fijo — se calcula a partir de las horas
            # REALMENTE fichadas en el periodo (misma fuente que la Fase E,
            # `db.usuario.listar_fichajes_empleado`) × la tarifa/hora del contrato. Estimación con
            # el periodo actualmente seleccionado (o el mes en curso si aún no se ha elegido) —
            # "Autocompletar" recalcula si se cambia el periodo.
            horas = self._horas_fichadas_periodo(emp)
            tarifa = num(K.get("tarifa_hora"))
            self._set("salario_base", round(horas * tarifa, 2))
        elif K.get("salario"):
            # Bug F4.3.0 (Fase F.1): el contrato guarda el salario en BRUTO ANUAL — hay que
            # dividir entre el Nº DE PAGAS (mismo criterio que `NominaInput.desde_anual`, no un
            # /12 fijo) antes de volcarlo al campo MENSUAL del formulario. Antes de esta corrección
            # se copiaba el importe anual tal cual, tratándolo como si fuera ya mensual.
            try:
                num_pagas = int(num(self._inputs["num_pagas"].text()) or 12) or 12
            except Exception:
                num_pagas = 12
            self._set("salario_base", round(num(K.get("salario")) / num_pagas, 2))

        # IRPF real (Fase F.2): ya NO se precarga un 15% fijo — se lee
        # `rrhh_datos_fiscales.irpf_pct_calculado` (Fase B2, `IRPFCalculatorService`), el ÚNICO
        # campo del que la nómina debe tomar el IRPF. Queda editable como excepción puntual.
        try:
            from src.rrhh.db import datos_fiscales as _df
            df = _df.obtener_datos_fiscales(emp.get("id"), self._id_empresa())
            if df and df.get("irpf_pct_calculado") is not None:
                self._set("irpf_pct", df.get("irpf_pct_calculado"))
        except Exception as e:
            logger.debug("nomina irpf_pct_calculado: %s", e)

    def _horas_fichadas_periodo(self, emp) -> float:
        """Horas REALMENTE fichadas por `emp` en el periodo actualmente seleccionado en el
        formulario (o el mes en curso si aún no se ha elegido ninguno) — Fase F.3, misma fuente
        de fichajes que la bolsa de horas de la Fase E."""
        id_usuario = emp.get("id_usuario")
        if not id_usuario:
            return 0.0
        try:
            from src.rrhh.nomina_servicio import _resolver_periodo
            # OJO: lee los campos de periodo DIRECTAMENTE de los widgets (no vía `_recoger()`,
            # que a su vez puede invocar este método → recursión infinita).
            periodo = {"periodo_anio": self._inputs["periodo_anio"].text().strip(),
                      "periodo_mes": self._inputs["periodo_mes"].text().strip()}
            anio, mes = _resolver_periodo(periodo)
        except Exception:
            import datetime as _dt
            hoy = _dt.date.today()
            anio, mes = hoy.year, hoy.month
        try:
            from src.db.usuario import listar_fichajes_empleado
            fichajes = listar_fichajes_empleado(id_usuario, anio=anio, mes=mes) or []
            return round(sum(int(f.get("segundos") or 0) for f in fichajes) / 3600.0, 2)
        except Exception as e:
            logger.debug("horas fichadas periodo (%s): %s", id_usuario, e)
            return 0.0

    def _recoger(self) -> dict:
        datos = {k: (w.text().strip() if isinstance(w, QLineEdit) else "") for k, w in self._inputs.items()}
        datos.update(self._empresa_valores())     # datos de empresa inyectados automáticamente
        # Fase F: id_empleado/id_empresa habilitan el enriquecimiento automático de
        # `calcular_desde_datos` (IRPF real ya viene precargado arriba; IT y bolsa de horas se
        # resuelven aquí, en el momento del cálculo, para reflejar siempre el periodo vigente).
        emp = self.cb_emp.currentData()
        if emp:
            datos["id_empleado"] = emp.get("id")
            modelo_pago = str(getattr(self, "_contrato_actual", {}).get("modelo_pago") or "fijo")
            datos["modelo_pago"] = modelo_pago.strip().lower()
            if datos["modelo_pago"] == "hora":
                datos.setdefault("tarifa_hora", str(num(self._contrato_actual.get("tarifa_hora"))))
                datos.setdefault("horas_trabajadas_periodo",
                                 str(self._horas_fichadas_periodo(emp)))
        datos["id_empresa"] = self._id_empresa()
        return datos

    def _empresa_valores(self) -> dict:
        """Datos de EMPRESA resueltos desde 'Datos de empresa' (Configuración) para las claves de
        `EMPRESA_CAMPOS`. Fuente única = capa de maestros (`entidad_empresa`)."""
        try:
            from src.rrhh import maestros
            emp = maestros.entidad_empresa(self._id_empresa()) or {}
        except Exception as e:
            logger.debug("nomina empresa_valores: %s", e); emp = {}
        return {k: (emp.get(k) or "") for k, _ in EMPRESA_CAMPOS}

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
        except GestionNominaError as e:
            mostrar_mensaje(self, "Nóminas", str(e), "error")
        except Exception as e:
            logger.error("calcular nómina: %s", e)
            mostrar_mensaje(self, "Nóminas", "No se pudo calcular la nómina.", "error")

    def _generar(self):
        datos = self._recoger()
        if not (datos.get("trab_nombre") or datos.get("nif")):
            mostrar_mensaje(self, "Nóminas", "Indica al menos el trabajador (nombre o NIF).", "warning")
            return
        id_emp = (self.cb_emp.currentData() or {}).get("id")
        if id_emp:
            # Hereda anticipos/conceptos recurrentes aprobados (`rrhh_gestion.py`) que hasta ahora nunca
            # llegaban a la nómina generada. Solo se rellenan las claves que el usuario ha dejado en
            # blanco: `preparar_datos_nomina` usa `dict.setdefault`, que no pisaría un valor ya tecleado,
            # pero `_recoger()` ya crea TODAS las claves (aunque sea con ""), así que hay que pasarle solo
            # las vacías y fusionar el resultado de vuelta — si no, el setdefault nunca dispara.
            try:
                from src.services.rrhh import nominas_pro
                rellenos = {k: v for k, v in datos.items() if v in ("", None)}
                enriquecido = nominas_pro.preparar_datos_nomina(id_emp, rellenos, id_empresa=self._id_empresa())
                datos.update({k: v for k, v in enriquecido.items() if k in rellenos})
            except Exception as e:
                logger.debug("preparar_datos_nomina: %s", e)
        try:
            ruta = generar_nomina_pdf(datos)
            try:
                from src.db.documentos import registrar_documento
                registrar_documento(ruta, tipo="nomina",
                                    nombre=ruta.split("\\")[-1].split("/")[-1],
                                    referencia=str(datos.get("nif") or ""))
            except Exception:
                pass
            # Fase F.7: reconecta el camino de escritura a `rrhh_nominas`, hoy huérfano (solo
            # alcanzable desde el wizard antiguo, ya sin uso). Reutiliza SIEMPRE
            # `persistencia.registrar_generacion` → `_registrar_nomina` (nunca duplica su mapeo
            # de columnas) — mismo `datos` "engine-ready" (`_preparar_engine`) que ya usa el PDF,
            # así lo persistido coincide exactamente con lo mostrado. Nace SIEMPRE en
            # `estado='borrador'` (columna por defecto): un humano la aprueba desde el listado de
            # nóminas del expediente, nunca se aprueba automáticamente.
            try:
                from src.rrhh.documents.render.nomina_pdf import _preparar_engine
                from src.rrhh.nomina_servicio import _resolver_periodo
                import calendar as _cal
                import datetime as _dt_
                anio_p, mes_p = _resolver_periodo(datos)
                fecha_periodo = _dt_.date(anio_p, mes_p, _cal.monthrange(anio_p, mes_p)[1])
                datos_persist = _preparar_engine(datos)
                datos_persist["fecha"] = fecha_periodo.strftime("%d/%m/%Y")
                from src.rrhh import persistencia
                persistencia.registrar_generacion("NÓMINA", datos_persist, ruta,
                                                   id_empresa=self._id_empresa())
            except Exception as e:
                logger.error("registrar nómina en expediente (rrhh_nominas): %s", e)
            if id_emp:
                # No es idempotente (rebajaría la cuota dos veces si se regenera el mismo PDF) — se pide
                # confirmación explícita al humano antes de aplicarla, nunca automático.
                try:
                    from assets.estilo_global import mostrar_confirmacion
                    if mostrar_confirmacion(
                            self, "Anticipos",
                            "¿Aplicar la cuota de anticipo pendiente de este empleado a esta nómina?"):
                        from src.services.rrhh import nominas_pro
                        nominas_pro.amortizar_anticipos(id_emp, id_empresa=self._id_empresa())
                except Exception as e:
                    logger.debug("amortizar_anticipos: %s", e)
                # Gastos de viaje aprobados (petición explícita): igual de explícito/no-automático
                # que los anticipos — ya se inyectaron en "dietas" al generar el PDF
                # (`nominas_pro.preparar_datos_nomina`), aquí solo se marcan como reembolsados.
                try:
                    from src.services.gastos_viaje import gastos as gastos_viaje
                    pendiente = gastos_viaje.total_pendiente_reembolso(id_emp, id_empresa=self._id_empresa())
                    if pendiente:
                        from assets.estilo_global import mostrar_confirmacion
                        if mostrar_confirmacion(
                                self, "Gastos de viaje",
                                f"Esta nómina incluye {pendiente:.2f}€ de gastos de viaje aprobados "
                                "(ya sumados en «Dietas»). ¿Marcarlos como reembolsados?"):
                            gastos_viaje.marcar_reembolsados(id_emp, id_empresa=self._id_empresa())
                except Exception as e:
                    logger.debug("marcar_reembolsados gastos de viaje: %s", e)
            if id_emp:
                self._lista.refrescar(id_emp)
            self._calcular()
            mostrar_mensaje(self, "Nóminas",
                            "Nómina generada correctamente en /documentos/nominas.", "success")
            try:
                from src.utils import plataforma
                plataforma.abrir_carpeta(ruta.rsplit("\\", 1)[0].rsplit("/", 1)[0])
            except Exception:
                pass
        except GestionNominaError as e:
            mostrar_mensaje(self, "Nóminas", str(e), "error")
        except Exception as e:
            logger.error("generar nómina: %s", e)
            mostrar_mensaje(self, "Nóminas", "No se pudo generar la nómina.", "error")
