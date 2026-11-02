"""
Formulario INLINE de REGISTRO de ALTAS LABORALES (pestaña "Altas laborales" del sidebar de RRHH).

Sustituye al antiguo formulario que generaba un PDF ("Generar alta (PDF)"): esta pestaña es pura
REGISTRACIÓN. Investigación previa a este cambio (ver informe de la tarea): los datos que pedía el
alta (nombre, DNI/NIE, Nº Seguridad Social, fecha de nacimiento, sexo, nacionalidad, dirección,
municipio, provincia, CP, teléfono, email…) son EXACTAMENTE columnas ya existentes en
`rrhh_empleados` — el mismo registro que gestiona la pestaña "Empleados" de esta misma ventana
(`EmpleadoFormDialog`, con CRUD en `src.rrhh.db.empleados`). No existe (ni hace falta crear) una
tabla `rrhh_altas` separada: un "alta laboral" en este dominio ES el alta del empleado en
`rrhh_empleados` (estado=activo + fecha_alta). Este formulario reutiliza esa misma capa de datos
(`crear_empleado`/`actualizar_empleado`/`obtener_por_nif`) en vez de inventar un segundo mecanismo
paralelo. Los datos puramente contractuales (tipo de contrato, horario, cláusulas…) ya tienen su
propio hogar en la pestaña "Contratos" (`rrhh_contrato_inline.py` / `rrhh_contratos`) y quedan fuera
de este formulario para no duplicar responsabilidades.
"""

import datetime as _dt
import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QTableWidgetItem, QVBoxLayout, QWidget,
)

from assets.estilo_global import (
    COLOR_ACCION_TEXTO, COLOR_BORDE, COLOR_CIAN, COLOR_FONDO_WIDGET, mostrar_mensaje,
)
from src.gui.catalogo_gestion import _tabla

logger = logging.getLogger("gui.rrhh.alta_inline")

_INP_SS = (
    f"background:{COLOR_FONDO_WIDGET};color:#FFFFFF;border:1px solid {COLOR_BORDE};"
    f"border-radius:8px;padding:6px 10px;font-family:'Segoe UI';font-size:15px;"
)
_LBL_SS = "color:#C9D1D9;font-family:'Segoe UI';font-size:14px;font-weight:bold;background:transparent;"
_CB_SS = _INP_SS.replace("font-size:15px", "font-size:14px")

_SEXOS = [("—", ""), ("Hombre", "H"), ("Mujer", "M"), ("Otro", "X")]


def _normalizar_fecha(txt):
    """AAAA-MM-DD o DD/MM/AAAA → ISO (o None). Copia deliberada del helper equivalente de
    `rrhh_gestion.py` — los formularios inline hermanos (contrato/nómina/modelo145) tampoco
    importan de `rrhh_gestion` para evitar el ciclo de imports (esa ventana es quien los
    construye a ELLOS, no al revés)."""
    txt = (txt or "").strip()
    if not txt:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return _dt.datetime.strptime(txt, fmt).date().isoformat()
        except ValueError:
            continue
    return None


class AltaLaboralForm(QWidget):
    """Registro directo de una alta laboral (sin PDF): upsert sobre `rrhh_empleados`.

    Sin lista de "registros ya generados" (auditoría lista-por-pestaña, ver informe de la tarea):
    un alta NO es un evento repetible con historial propio — es el estado actual de
    `rrhh_empleados` (estado/fecha_alta), y no genera ningún documento. Por empleado solo puede
    existir UN alta vigente, así que una lista filtrada al empleado seleccionado tendría como
    mucho una fila (la misma que ya rellena el formulario de arriba) — no aporta nada nuevo. La
    tabla que sí muestra esta pantalla ("EMPLEADOS ACTUALMENTE DE ALTA", más abajo) es,
    deliberadamente, la vista de conjunto de la EMPRESA, no del empleado seleccionado."""

    def __init__(self, id_empresa_getter, parent=None):
        super().__init__(parent)
        self._id_empresa = id_empresa_getter
        self._empleados = []
        self._editando_id = None   # id del empleado si se eligió uno existente (reactivar/corregir)
        self._build()
        self._cargar_empleados()

    # ── UI helpers ────────────────────────────────────────────────────────────
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

    def _seccion(self, ly, titulo):
        line = QFrame(); line.setFixedHeight(1); line.setStyleSheet(f"background:{COLOR_BORDE};")
        lbl = QLabel(titulo.upper())
        lbl.setStyleSheet(f"color:{COLOR_CIAN};font-family:'Segoe UI';font-size:15px;font-weight:900;"
                          "letter-spacing:1px;background:transparent;margin-top:4px;")
        ly.addWidget(lbl); ly.addWidget(line)

    def _campo(self, grid, row, col, etiqueta, widget, span=1):
        cel = QVBoxLayout(); cel.setSpacing(2)
        cel.addWidget(self._lbl(etiqueta)); cel.addWidget(widget)
        w = QWidget(); w.setLayout(cel)
        grid.addWidget(w, row, col, 1, span)

    def _line(self):
        w = QLineEdit(); w.setStyleSheet(f"QLineEdit{{{_INP_SS}}}"); return w

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(10)

        top = QHBoxLayout(); top.setSpacing(10)
        top.addWidget(self._lbl("Empleado:"))
        self.cb_emp = QComboBox(); self.cb_emp.setMinimumWidth(320)
        self.cb_emp.setStyleSheet(f"QComboBox{{{_CB_SS}}}")
        self.cb_emp.currentIndexChanged.connect(self._on_empleado)
        top.addWidget(self.cb_emp, 1)
        top.addWidget(self._btn("Limpiar (nuevo)", self._nuevo))
        root.addLayout(top)

        self.lbl_modo = QLabel("Nueva alta: se creará un empleado nuevo.")
        self.lbl_modo.setStyleSheet("color:#9BA3AE;font-family:'Segoe UI';font-size:13px;"
                                    "background:transparent;")
        root.addWidget(self.lbl_modo)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        cont = QWidget(); form_ly = QVBoxLayout(cont)
        form_ly.setContentsMargins(2, 4, 12, 4); form_ly.setSpacing(14)

        # Identificación
        self._seccion(form_ly, "Datos del trabajador/a")
        g1 = QGridLayout(); g1.setHorizontalSpacing(18); g1.setVerticalSpacing(8)
        self.in_nombre = self._line()
        self._campo(g1, 0, 0, "Nombre *", self.in_nombre)
        self.in_apellidos = self._line()
        self._campo(g1, 0, 1, "Apellidos", self.in_apellidos)
        self.in_nif = self._line(); self.in_nif.editingFinished.connect(self._buscar_por_nif)
        self._campo(g1, 1, 0, "DNI/NIE *", self.in_nif)
        self.in_ss = self._line()
        self._campo(g1, 1, 1, "Nº Seguridad Social", self.in_ss)
        self.in_fnac = self._line(); self.in_fnac.setPlaceholderText("AAAA-MM-DD")
        self._campo(g1, 2, 0, "Fecha de nacimiento", self.in_fnac)
        self.cb_sexo = QComboBox(); self.cb_sexo.setStyleSheet(f"QComboBox{{{_CB_SS}}}")
        for et, val in _SEXOS:
            self.cb_sexo.addItem(et, val)
        self._campo(g1, 2, 1, "Sexo", self.cb_sexo)
        self.in_nac = self._line()
        self._campo(g1, 3, 0, "Nacionalidad", self.in_nac)
        w1 = QWidget(); w1.setLayout(g1); form_ly.addWidget(w1)

        # Contacto
        self._seccion(form_ly, "Contacto")
        g2 = QGridLayout(); g2.setHorizontalSpacing(18); g2.setVerticalSpacing(8)
        self.in_dir = self._line()
        self._campo(g2, 0, 0, "Dirección", self.in_dir, span=2)
        self.in_mun = self._line()
        self._campo(g2, 1, 0, "Municipio", self.in_mun)
        self.in_prov = self._line()
        self._campo(g2, 1, 1, "Provincia", self.in_prov)
        self.in_cp = self._line()
        self._campo(g2, 2, 0, "Código Postal", self.in_cp)
        self.in_tel = self._line()
        self._campo(g2, 2, 1, "Teléfono", self.in_tel)
        self.in_email = self._line()
        self._campo(g2, 3, 0, "Email", self.in_email, span=2)
        w2 = QWidget(); w2.setLayout(g2); form_ly.addWidget(w2)

        # Datos laborales básicos (el detalle contractual vive en la pestaña "Contratos")
        self._seccion(form_ly, "Alta laboral")
        g3 = QGridLayout(); g3.setHorizontalSpacing(18); g3.setVerticalSpacing(8)
        self.in_puesto = self._line()
        self._campo(g3, 0, 0, "Puesto", self.in_puesto)
        self.in_categoria = self._line()
        self._campo(g3, 0, 1, "Categoría", self.in_categoria)
        self.in_convenio = self._line()
        self._campo(g3, 1, 0, "Convenio", self.in_convenio)
        self.in_jornada = self._line()
        self._campo(g3, 1, 1, "Jornada", self.in_jornada)
        self.in_salario = self._line(); self.in_salario.setPlaceholderText("0.00")
        self._campo(g3, 2, 0, "Salario base mensual", self.in_salario)
        self.cb_centro = QComboBox(); self.cb_centro.setStyleSheet(f"QComboBox{{{_CB_SS}}}")
        self._campo(g3, 2, 1, "Centro de trabajo", self.cb_centro)
        self.in_falta = self._line(); self.in_falta.setPlaceholderText("AAAA-MM-DD (vacío = hoy)")
        self._campo(g3, 3, 0, "Fecha de alta", self.in_falta)
        w3 = QWidget(); w3.setLayout(g3); form_ly.addWidget(w3)

        form_ly.addStretch()
        scroll.setWidget(cont)
        root.addWidget(scroll, 1)

        bottom = QHBoxLayout(); bottom.addStretch()
        bottom.addWidget(self._btn("Registrar alta", self._registrar, primary=True))
        root.addLayout(bottom)

        root.addWidget(self._lbl("EMPLEADOS ACTUALMENTE DE ALTA"))
        self.tbl = _tabla(["Nombre", "Apellidos", "NIF/NIE", "Puesto", "Fecha alta"])
        self.tbl.setMinimumHeight(160)
        self.tbl.cellClicked.connect(self._sel_lista)
        root.addWidget(self.tbl)

        self._cargar_centros()

    def _cargar_centros(self):
        self.cb_centro.clear()
        self.cb_centro.addItem("— Sin centro —", None)
        try:
            from src.rrhh.db import centros
            for c in centros.listar_centros(self._id_empresa()):
                self.cb_centro.addItem(c.get("nombre_centro") or str(c.get("id_centro")),
                                       c.get("id_centro"))
        except Exception as e:
            logger.debug("cargar centros: %s", e)

    # ── Datos ─────────────────────────────────────────────────────────────────
    def _cargar_empleados(self):
        try:
            from src.rrhh.db import empleados
            self._empleados = empleados.listar_empleados(self._id_empresa()) or []
        except Exception as e:
            logger.debug("cargar empleados: %s", e); self._empleados = []
        self.cb_emp.blockSignals(True); self.cb_emp.clear()
        self.cb_emp.addItem("— Nuevo empleado —", None)
        for e in self._empleados:
            nom = f"{e.get('nombre','')} {e.get('apellidos','')}".strip()
            self.cb_emp.addItem(f"{nom}  ·  {e.get('nif','')}  ·  ({e.get('estado','')})", e)
        self.cb_emp.blockSignals(False)
        self._refrescar_lista()

    def _refrescar_lista(self):
        try:
            from src.rrhh.db import empleados
            activos = empleados.listar_empleados(self._id_empresa(), estado="activo") or []
        except Exception as e:
            logger.debug("listar activos: %s", e); activos = []
        self.tbl.setRowCount(len(activos))
        for i, e in enumerate(activos):
            vals = [e.get("nombre"), e.get("apellidos"), e.get("nif"), e.get("puesto"),
                   e.get("fecha_alta")]
            for j, v in enumerate(vals):
                self.tbl.setItem(i, j, QTableWidgetItem("" if v is None else str(v)))
        self._activos_cache = activos

    def _sel_lista(self, row, _col):
        try:
            emp = self._activos_cache[row]
        except (IndexError, AttributeError):
            return
        # El combo guarda el dict completo del empleado como data: localizarlo por id.
        for idx in range(self.cb_emp.count()):
            d = self.cb_emp.itemData(idx)
            if isinstance(d, dict) and d.get("id") == emp.get("id"):
                self.cb_emp.setCurrentIndex(idx)
                break

    def _nuevo(self):
        self.cb_emp.setCurrentIndex(0)

    def _on_empleado(self, _i):
        emp = self.cb_emp.currentData()
        self._editando_id = emp.get("id") if emp else None
        if not emp:
            self._limpiar_formulario()
            self.lbl_modo.setText("Nueva alta: se creará un empleado nuevo.")
            return
        self._rellenar_formulario(emp)
        self.lbl_modo.setText(
            f"Reactivando/actualizando el alta de un empleado existente (estado actual: "
            f"{emp.get('estado') or '—'}).")

    def _limpiar_formulario(self):
        for w in (self.in_nombre, self.in_apellidos, self.in_nif, self.in_ss, self.in_fnac,
                 self.in_nac, self.in_dir, self.in_mun, self.in_prov, self.in_cp, self.in_tel,
                 self.in_email, self.in_puesto, self.in_categoria, self.in_convenio,
                 self.in_jornada, self.in_salario, self.in_falta):
            w.clear()
        self.cb_sexo.setCurrentIndex(0)
        self.cb_centro.setCurrentIndex(0)

    def _rellenar_formulario(self, e):
        self.in_nombre.setText(e.get("nombre") or "")
        self.in_apellidos.setText(e.get("apellidos") or "")
        self.in_nif.setText(e.get("nif") or "")
        self.in_ss.setText(e.get("num_ss") or "")
        self.in_fnac.setText(str(e.get("fecha_nacimiento") or ""))
        self.in_nac.setText(e.get("nacionalidad") or "")
        i = self.cb_sexo.findData(e.get("sexo") or "")
        self.cb_sexo.setCurrentIndex(i if i >= 0 else 0)
        self.in_dir.setText(e.get("direccion") or "")
        self.in_mun.setText(e.get("municipio") or "")
        self.in_prov.setText(e.get("provincia") or "")
        self.in_cp.setText(e.get("cp") or "")
        self.in_tel.setText(e.get("telefono") or "")
        self.in_email.setText(e.get("email") or "")
        self.in_puesto.setText(e.get("puesto") or "")
        self.in_categoria.setText(e.get("categoria") or "")
        self.in_convenio.setText(e.get("convenio") or "")
        self.in_jornada.setText(e.get("jornada") or "")
        self.in_salario.setText(str(e.get("salario_base") or ""))
        ic = self.cb_centro.findData(e.get("id_centro"))
        self.cb_centro.setCurrentIndex(ic if ic >= 0 else 0)
        self.in_falta.setText(str(e.get("fecha_alta") or ""))

    def _buscar_por_nif(self):
        """Si el NIF tecleado ya existe en la empresa y no hay un empleado seleccionado en el
        combo, ofrece cargarlo en vez de arriesgarse a un duplicado (mismo criterio de
        identidad por NIF que usa `EmpleadoFormDialog`/`crear_empleado`)."""
        if self._editando_id:
            return
        nif = self.in_nif.text().strip().upper()
        if not nif:
            return
        try:
            from src.rrhh.db import empleados
            existente = empleados.obtener_por_nif(nif, self._id_empresa())
        except Exception as e:
            logger.debug("buscar por nif: %s", e); return
        if existente:
            i = -1
            for idx in range(self.cb_emp.count()):
                d = self.cb_emp.itemData(idx)
                if isinstance(d, dict) and d.get("id") == existente.get("id"):
                    i = idx; break
            if i >= 0:
                self.cb_emp.setCurrentIndex(i)   # dispara _on_empleado → rellena y avisa

    # ── Registro ──────────────────────────────────────────────────────────────
    def _recoger(self) -> dict:
        def _f(x):
            try:
                return float(str(x).replace(",", ".")) if str(x).strip() else 0.0
            except ValueError:
                return 0.0
        return dict(
            nombre=self.in_nombre.text().strip(), apellidos=self.in_apellidos.text().strip(),
            nif=self.in_nif.text().strip().upper(), num_ss=self.in_ss.text().strip(),
            fecha_nacimiento=_normalizar_fecha(self.in_fnac.text()),
            sexo=self.cb_sexo.currentData(), nacionalidad=self.in_nac.text().strip(),
            direccion=self.in_dir.text().strip(), municipio=self.in_mun.text().strip(),
            provincia=self.in_prov.text().strip(), cp=self.in_cp.text().strip(),
            telefono=self.in_tel.text().strip(), email=self.in_email.text().strip(),
            puesto=self.in_puesto.text().strip(), categoria=self.in_categoria.text().strip(),
            convenio=self.in_convenio.text().strip(), jornada=self.in_jornada.text().strip(),
            salario_base=_f(self.in_salario.text()), id_centro=self.cb_centro.currentData(),
            estado="activo",
            fecha_alta=_normalizar_fecha(self.in_falta.text()) or _dt.date.today().isoformat(),
        )

    def _registrar(self):
        from src.rrhh.db import empleados
        if self.in_fnac.text().strip() and _normalizar_fecha(self.in_fnac.text()) is None:
            mostrar_mensaje(self, "Altas laborales",
                           "Fecha de nacimiento no válida. Usa AAAA-MM-DD o DD/MM/AAAA.", "warning")
            return
        if self.in_falta.text().strip() and _normalizar_fecha(self.in_falta.text()) is None:
            mostrar_mensaje(self, "Altas laborales",
                           "Fecha de alta no válida. Usa AAAA-MM-DD o DD/MM/AAAA.", "warning")
            return
        campos = self._recoger()
        if not campos["nombre"] or not campos["nif"]:
            mostrar_mensaje(self, "Altas laborales", "Nombre y DNI/NIE son obligatorios.", "warning")
            return
        try:
            if self._editando_id:
                ok = empleados.actualizar_empleado(self._editando_id, self._id_empresa(), **campos)
                eid = self._editando_id if ok else None
            else:
                eid = empleados.crear_empleado(id_empresa=self._id_empresa(), **campos)
                ok = eid is not None
        except Exception as e:
            logger.error("registrar alta: %s", e); ok = False; eid = None
        if not ok:
            mostrar_mensaje(
                self, "Altas laborales",
                "No se pudo registrar el alta (¿NIF duplicado en esta empresa? revisa también el "
                "resto de campos).", "error")
            return
        mostrar_mensaje(self, "Altas laborales", "Alta registrada correctamente.", "success")
        self._cargar_empleados()
        # Deja el formulario mostrando el empleado recién dado de alta/actualizado (en vez de
        # volver silenciosamente a "Nuevo empleado" con el combo desincronizado del estado real).
        for idx in range(self.cb_emp.count()):
            d = self.cb_emp.itemData(idx)
            if isinstance(d, dict) and d.get("id") == eid:
                self.cb_emp.setCurrentIndex(idx)
                break
