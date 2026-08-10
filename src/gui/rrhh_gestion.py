"""
GUI de RRHH — gestión de empleados y visor de expediente (F4.4).

Capa VISUAL sobre la infraestructura ya existente (no recalcula, no toca motor/
persistencia/migraciones): consume `src/rrhh/db/*` (empleados + expediente) y reutiliza
los patrones de `catalogo_gestion`/`contabilidad_gestion` (sidebar, helpers, estilo).

- Listado de empleados (búsqueda + filtro por estado, por id_empresa/id_tienda).
- Alta/edición de empleado (rrhh_empleados) con validaciones.
- Visor de expediente (ficha + contratos + nóminas + vacaciones + ausencias + documentos)
  vía `empleados.expediente()`.
"""

import json
import logging
import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QDialog, QFormLayout, QFrame, QHBoxLayout,
                             QLabel, QMessageBox, QPushButton, QStackedWidget, QTabWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import (_BG, _BG2, _BORDE, _CIAN, _DIM, _SIDEBAR, _TEXT,
                                      _btn, _btn_salir_sidebar, _btn_x, _combo,
                                      _dialogo_frameless, _inp, _tabla)

logger = logging.getLogger("rrhh.gui")

_ESTADOS = [("Activo", "activo"), ("Baja", "baja"), ("Suspendido", "suspendido"),
            ("Excedencia", "excedencia")]
_SEXOS = [("—", ""), ("Hombre", "H"), ("Mujer", "M"), ("Otro", "X")]

# Descripción de cada función laboral (mostrada en su pestaña).
_LABORAL_DESC = {
    "CONTRATO": "Genera contratos laborales con validación legal automática (indefinido, "
                "temporal, fijo discontinuo, parcial, prácticas, sustitución).",
    "NÓMINA": "Cálculo y generación de nóminas con IRPF y cotización.",
    "ALTA": "Tramita altas en la Seguridad Social (preparado para SS RED).",
    "BAJA": "Tramita bajas y situaciones de incapacidad temporal.",
    "FINIQUITO": "Genera finiquitos con cálculo automático de conceptos.",
    "CERTIFICADO": "Emite certificados de empresa y de vida laboral.",
    "CERT LABORAL": "Certificados laborales: antigüedad, funciones, ingresos y jornada.",
    "CARTA DESPIDO": "Redacta cartas de despido con motivos predeterminados y validación legal.",
    "VACACIONES": "Solicitudes, aprobaciones y denegaciones de vacaciones.",
}

# Descripción de la pestaña "Periodo prueba" (despido por no superar el período de prueba).
_PRUEBA_DESC = ("Genera el documento de extinción del contrato durante el período de prueba "
                "(art. 14 ET) para trabajadores que NO lo hayan superado. Reutiliza el asistente "
                "de cartas de despido con el motivo «Período de prueba» preseleccionado.")


def _it(txt):
    return QTableWidgetItem("" if txt is None else str(txt))


# ── Formulario de alta / edición ──────────────────────────────────────────────
class EmpleadoFormDialog(QDialog):
    """Alta/edición sobre rrhh_empleados. `empleado` (dict) → modo edición."""

    def __init__(self, empleado=None, id_empresa=None, parent=None):
        super().__init__(parent)
        self.empleado = empleado or {}
        self.id_empresa = id_empresa
        self.resultado_id = None
        self.setWindowTitle("Editar empleado" if empleado else "Nuevo empleado")
        self.setStyleSheet(f"QLabel{{color:{_TEXT};font-size:12px;}}")
        self._build()

    def _build(self):
        root = _dialogo_frameless(self, "Editar empleado" if self.empleado else "Nuevo empleado", ancho=560)
        tabs = QTabWidget()
        tabs.setStyleSheet(f"QTabBar::tab{{background:{_SIDEBAR};color:{_DIM};padding:8px 14px;}}"
                           f"QTabBar::tab:selected{{color:{_CIAN};}}"
                           f"QTabWidget::pane{{border:1px solid {_BORDE};}}")
        e = self.empleado
        # Identificación
        self.in_nombre = _inp("Nombre", ); self.in_nombre.setText(e.get("nombre", ""))
        self.in_apellidos = _inp(); self.in_apellidos.setText(e.get("apellidos") or "")
        self.cb_sexo = _combo(_SEXOS, e.get("sexo") or "")
        self.in_fnac = _inp("AAAA-MM-DD"); self.in_fnac.setText(str(e.get("fecha_nacimiento") or ""))
        self.in_nac = _inp(); self.in_nac.setText(e.get("nacionalidad") or "")
        self.in_nif = _inp("NIF/NIE *"); self.in_nif.setText(e.get("nif") or "")
        self.in_ss = _inp(); self.in_ss.setText(e.get("num_ss") or "")
        tabs.addTab(self._form([
            ("Nombre *", self.in_nombre), ("Apellidos", self.in_apellidos), ("Sexo", self.cb_sexo),
            ("Fecha nacimiento", self.in_fnac), ("Nacionalidad", self.in_nac),
            ("NIF/NIE *", self.in_nif), ("Nº Seguridad Social", self.in_ss)]), "Identificación")
        # Contacto
        self.in_dir = _inp(); self.in_dir.setText(e.get("direccion") or "")
        self.in_mun = _inp(); self.in_mun.setText(e.get("municipio") or "")
        self.in_prov = _inp(); self.in_prov.setText(e.get("provincia") or "")
        self.in_cp = _inp(); self.in_cp.setText(e.get("cp") or "")
        self.in_pais = _inp(); self.in_pais.setText(e.get("pais") or "ESPAÑA")
        self.in_tel = _inp(); self.in_tel.setText(e.get("telefono") or "")
        self.in_email = _inp(); self.in_email.setText(e.get("email") or "")
        tabs.addTab(self._form([
            ("Dirección", self.in_dir), ("Municipio", self.in_mun), ("Provincia", self.in_prov),
            ("CP", self.in_cp), ("País", self.in_pais), ("Teléfono", self.in_tel),
            ("Email", self.in_email)]), "Contacto")
        # Laboral
        self.cb_centro = _combo(self._opciones_centros(), e.get("id_centro"))
        self.in_cat = _inp(); self.in_cat.setText(e.get("categoria") or "")
        self.in_grupo = _inp(); self.in_grupo.setText(e.get("grupo_prof") or "")
        self.in_conv = _inp(); self.in_conv.setText(e.get("convenio") or "")
        self.in_puesto = _inp(); self.in_puesto.setText(e.get("puesto") or "")
        self.in_sal = _inp("0.00"); self.in_sal.setText(str(e.get("salario_base") or ""))
        self.in_jor = _inp(); self.in_jor.setText(e.get("jornada") or "")
        self.cb_estado = _combo(_ESTADOS, e.get("estado") or "activo")
        tabs.addTab(self._form([
            ("Centro de trabajo", self.cb_centro), ("Categoría", self.in_cat),
            ("Grupo profesional", self.in_grupo), ("Convenio", self.in_conv),
            ("Puesto", self.in_puesto), ("Salario base mensual", self.in_sal),
            ("Jornada", self.in_jor), ("Estado", self.cb_estado)]), "Laboral")
        root.addWidget(tabs)
        botones = QHBoxLayout(); botones.addStretch()
        botones.addWidget(_btn("Cancelar", self.reject))       # gris (secundario)
        botones.addWidget(_btn("Guardar", self._guardar, primary=True))
        root.addLayout(botones)

    def _form(self, filas):
        w = QWidget(); fl = QFormLayout(w)
        for et, widget in filas:
            lab = QLabel(et); lab.setStyleSheet(f"color:{_DIM};")
            fl.addRow(lab, widget)
        return w

    def _opciones_centros(self):
        ops = [("— Sin centro —", None)]
        try:
            from src.rrhh.db import centros
            for c in centros.listar_centros(self.id_empresa):
                ops.append((c.get("nombre_centro") or c.get("id_centro"), c.get("id_centro")))
        except Exception as ex:
            logger.error("opciones_centros: %s", ex)
        return ops

    def _campos(self):
        def _f(x):
            try:
                return float(str(x).replace(",", ".")) if str(x).strip() else 0.0
            except ValueError:
                return 0.0
        return dict(
            nombre=self.in_nombre.text().strip(), apellidos=self.in_apellidos.text().strip(),
            sexo=self.cb_sexo.currentData(), fecha_nacimiento=self.in_fnac.text().strip() or None,
            nacionalidad=self.in_nac.text().strip(), nif=self.in_nif.text().strip().upper(),
            num_ss=self.in_ss.text().strip(), direccion=self.in_dir.text().strip(),
            municipio=self.in_mun.text().strip(), provincia=self.in_prov.text().strip(),
            cp=self.in_cp.text().strip(), pais=self.in_pais.text().strip(),
            telefono=self.in_tel.text().strip(), email=self.in_email.text().strip(),
            id_centro=self.cb_centro.currentData(), categoria=self.in_cat.text().strip(),
            grupo_prof=self.in_grupo.text().strip(), convenio=self.in_conv.text().strip(),
            puesto=self.in_puesto.text().strip(), salario_base=_f(self.in_sal.text()),
            jornada=self.in_jor.text().strip(), estado=self.cb_estado.currentData() or "activo")

    def _guardar(self):
        from src.rrhh.db import empleados
        campos = self._campos()
        if not campos["nombre"] or not campos["nif"]:
            QMessageBox.warning(self, "RRHH", "Nombre y NIF/NIE son obligatorios.")
            return
        if self.empleado.get("id"):
            ok = empleados.actualizar_empleado(self.empleado["id"], self.id_empresa, **campos)
            if ok:
                self.resultado_id = self.empleado["id"]; self.accept()
            else:
                QMessageBox.warning(self, "RRHH", "No se pudo actualizar el empleado.")
        else:
            eid = empleados.crear_empleado(id_empresa=self.id_empresa, **campos)
            if eid:
                self.resultado_id = eid; self.accept()
            else:
                QMessageBox.warning(self, "RRHH",
                                    "No se pudo crear (¿NIF duplicado en esta empresa?).")


# ── Visor de expediente ───────────────────────────────────────────────────────
class ExpedienteDialog(QDialog):
    def __init__(self, id_empleado, id_empresa=None, parent=None):
        super().__init__(parent)
        self.id_empleado = id_empleado
        self.id_empresa = id_empresa
        self.setWindowTitle("Expediente del trabajador")
        self.setMinimumSize(820, 560)
        self.setStyleSheet(f"QDialog{{background:{_BG};}} QLabel{{color:{_TEXT};}}")
        self._build()

    def _build(self):
        from src.rrhh.db import empleados
        exp = empleados.expediente(self.id_empleado, self.id_empresa) or {}
        self.exp = exp
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.setStyleSheet(f"QTabBar::tab{{background:{_SIDEBAR};color:{_DIM};padding:8px 14px;}}"
                           f"QTabBar::tab:selected{{color:{_CIAN};}}"
                           f"QTabWidget::pane{{border:1px solid {_BORDE};}}")
        emp = exp.get("empleado") or {}
        tabs.addTab(self._ficha(emp), "Ficha")
        tabs.addTab(self._tabla_simple(exp.get("contratos"),
                    ["Modalidad", "Inicio", "Fin", "Salario", "Estado"],
                    lambda r: [r.get("modalidad"), r.get("fecha_inicio"), r.get("fecha_fin"),
                               r.get("salario"), r.get("estado")]), "Contratos")
        tabs.addTab(self._tabla_simple(exp.get("nominas"),
                    ["Año", "Mes", "Bruto", "Base", "IRPF", "SS", "Neto"],
                    lambda r: [r.get("anio"), r.get("mes"), r.get("bruto"), r.get("base"),
                               r.get("irpf_importe"), r.get("ss_importe"), r.get("neto")]), "Nóminas")
        tabs.addTab(self._tabla_simple(exp.get("vacaciones"),
                    ["Año", "Tipo", "Inicio", "Fin", "Días", "Estado"],
                    lambda r: [r.get("anio"), r.get("tipo"), r.get("fecha_inicio"),
                               r.get("fecha_fin"), r.get("dias"), r.get("estado")]), "Vacaciones")
        tabs.addTab(self._tabla_simple(exp.get("ausencias"),
                    ["Tipo", "Inicio", "Fin", "Días", "Motivo"],
                    lambda r: [r.get("tipo"), r.get("fecha_inicio"), r.get("fecha_fin"),
                               r.get("dias"), r.get("motivo")]), "Ausencias")
        tabs.addTab(self._tabla_simple(exp.get("control_horario"),
                    ["Fecha", "Entrada", "Salida", "Efectivo (min)", "Exceso", "Déficit"],
                    lambda r: [r.get("fecha"), r.get("hora_entrada"), r.get("hora_salida"),
                               r.get("tiempo_efectivo_min"), r.get("exceso_min"),
                               r.get("deficit_min")]), "Control horario")
        tabs.addTab(self._docs(exp.get("documentos")), "Documentos")
        root.addWidget(tabs)
        cerrar = _btn("Cerrar", self.accept)
        root.addWidget(cerrar, alignment=Qt.AlignmentFlag.AlignRight)

    def _ficha(self, emp):
        w = QWidget(); fl = QFormLayout(w)
        campos = [("Nombre", f"{emp.get('nombre','')} {emp.get('apellidos','') or ''}".strip()),
                  ("NIF/NIE", emp.get("nif")), ("Nº SS", emp.get("num_ss")),
                  ("Puesto", emp.get("puesto")), ("Categoría", emp.get("categoria")),
                  ("Grupo prof.", emp.get("grupo_prof")), ("Convenio", emp.get("convenio")),
                  ("Salario base", emp.get("salario_base")), ("Jornada", emp.get("jornada")),
                  ("Estado", emp.get("estado")), ("Email", emp.get("email")),
                  ("Teléfono", emp.get("telefono"))]
        for et, val in campos:
            lab = QLabel(et); lab.setStyleSheet(f"color:{_DIM};")
            v = QLabel("" if val is None else str(val)); v.setStyleSheet(f"color:{_TEXT};font-weight:700;")
            fl.addRow(lab, v)
        return w

    def _tabla_simple(self, filas, cols, fila_fn):
        filas = filas or []
        t = _tabla(cols)
        t.setRowCount(len(filas))
        for i, r in enumerate(filas):
            for j, val in enumerate(fila_fn(r)):
                t.setItem(i, j, _it(val))
        return t

    def _docs(self, docs):
        docs = docs or []
        w = QWidget(); ly = QVBoxLayout(w)
        self.tbl_docs = _tabla(["Fecha", "Tipo", "Estado firma", "Referencia"])
        self.tbl_docs.setRowCount(len(docs))
        self._docs_data = docs
        for i, d in enumerate(docs):
            estado = d.get("estado_firma") if d.get("requiere_firma") else "—"
            self.tbl_docs.setItem(i, 0, _it(d.get("fecha")))
            self.tbl_docs.setItem(i, 1, _it(d.get("tipo_doc")))
            self.tbl_docs.setItem(i, 2, _it(estado))
            self.tbl_docs.setItem(i, 3, _it(d.get("ref_documento")))
        ly.addWidget(self.tbl_docs)
        bar = QHBoxLayout()
        bar.addWidget(_btn("Abrir PDF", self._abrir_pdf))
        bar.addWidget(_btn("Ver datos", self._ver_snapshot))
        ly.addLayout(bar)
        return w

    def _doc_sel(self):
        i = self.tbl_docs.currentRow()
        return self._docs_data[i] if 0 <= i < len(self._docs_data) else None

    def _abrir_pdf(self):
        d = self._doc_sel()
        ruta = (d or {}).get("ref_documento")
        if ruta and os.path.exists(ruta):
            try:
                from src.utils import plataforma
                plataforma.abrir_archivo(ruta)
            except Exception as ex:
                QMessageBox.warning(self, "RRHH", f"No se pudo abrir: {ex}")
        else:
            QMessageBox.information(self, "RRHH", "El PDF no está disponible en disco.")

    def _ver_snapshot(self):
        d = self._doc_sel()
        snap = (d or {}).get("datos_snapshot")
        if not snap:
            QMessageBox.information(self, "RRHH", "Sin datos de snapshot."); return
        try:
            txt = json.dumps(json.loads(snap), ensure_ascii=False, indent=2)
        except Exception:
            txt = str(snap)
        QMessageBox.information(self, "Datos del documento", txt[:4000])


# ── Ventana principal ─────────────────────────────────────────────────────────
class RRHHWindow(QWidget):
    # Módulo LABORAL clasificado por pestañas (icono, etiqueta sidebar, tipo de wizard).
    # (icono, etiqueta, tipo_wizard, subtipo_inicial)
    _LABORAL_SECCIONES = [
        ("📄", "Contratos", "CONTRATO", None),
        ("📊", "Nóminas", "NÓMINA", None),
        ("✅", "Altas laborales", "ALTA", None),
        ("❌", "Bajas laborales", "BAJA", None),
        ("💼", "Finiquitos", "FINIQUITO", None),
        ("🏢", "Certificados de empresa", "CERTIFICADO", None),
        ("📃", "Certificados laborales", "CERT LABORAL", None),
        ("📮", "Cartas de despido", "CARTA DESPIDO", None),
        # Vacaciones se gestiona en la pestaña Empleados (Vac./Ausencias). Aquí: periodo de prueba.
        ("🧪", "Periodo prueba", "CARTA DESPIDO", "PERÍODO DE PRUEBA"),
    ]

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.main = main
        # OJO: no fijar el stylesheet de fondo en la VENTANA — se propaga a los botones del
        # sidebar y rompe su estilo. El fondo se aplica al panel derecho (como Contabilidad).

        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        right = QWidget(); right.setStyleSheet(f"background:{_BG};"); rcol = QVBoxLayout(right)
        rcol.setContentsMargins(24, 18, 24, 18); rcol.setSpacing(14)
        self._lbl_tit = QLabel("Recursos Humanos · Empleados")
        self._lbl_tit.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        rcol.addWidget(self._lbl_tit)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_empleados())                      # 0 — Empleados
        # LAZY LOADING (regla de arquitectura): cada pestaña laboral monta un formulario pesado
        # (consulta de empleados y, en Contratos, el motor del asistente). Construirlas todas al abrir
        # RRHH congelaba la carga. Se difieren: se crea un placeholder y el contenido real se monta en
        # el PRIMER acceso a la pestaña (ver _ir).
        self._lazy_laboral = {}
        for i, (ic, lab, tipo, sub) in enumerate(self._LABORAL_SECCIONES, start=1):  # 1..9
            ph = QWidget(); phl = QVBoxLayout(ph); phl.setContentsMargins(0, 0, 0, 0)
            self.stack.addWidget(ph)
            self._lazy_laboral[i] = (phl, ic, lab, tipo, sub)
        rcol.addWidget(self.stack, 1)
        root.addWidget(right, 1)

        self._ir(0)
        self._cargar()

        # Pre-carga de IMPORTS en segundo plano (no construye widgets → no bloquea la UI ni causa
        # tirones). Calienta los módulos pesados que usan los formularios (reportlab/fuentes de los
        # generadores PDF y el motor del asistente) para que el PRIMER clic en cada pestaña solo
        # cueste montar sus widgets. Hilo demonio, silencioso ante cualquier fallo.
        self._precargar_imports_en_segundo_plano()

        # Pre-cacheo de pestañas: se construyen en segundo plano (orden de la barra lateral: las de
        # arriba, más usadas, primero) para que el cambio de pestaña sea INSTANTÁNEO. El coste real de
        # montar un formulario es el *polish* del QSS de Qt (~60-200ms), inevitable al construir; se
        # hace aquí, ocioso y espaciado, en vez de al primer clic. Arranque suave tras asentar la UI.
        QTimer.singleShot(350, self._precachear_laboral)

        # P3 (UX-TPV-01): sidebar colapsable con persistencia por usuario.
        try:
            from src.gui.sidebar_colapsable import instalar_sidebar_colapsable
            if getattr(self, "sidebar", None) is not None:
                instalar_sidebar_colapsable(self, self.sidebar, usuario=self.usuario, clave="rrhh")
        except Exception:
            pass

    # ── Sidebar + navegación ─────────────────────────────────────────────────
    def _build_sidebar(self):
        wrap = QFrame(); wrap.setObjectName("sw"); wrap.setFixedWidth(280); self.sidebar = wrap
        wrap.setStyleSheet(f"#sw{{background:{_SIDEBAR};}}")
        lay = QVBoxLayout(wrap); lay.setContentsMargins(0, 22, 0, 16); lay.setSpacing(2)
        cab = QLabel("RRHH · LABORAL")
        cab.setStyleSheet("color:#FFFFFF;padding:0 0 24px 28px;font-size:16px;font-weight:900;"
                          "letter-spacing:2px;background:transparent;")
        lay.addWidget(cab)
        self._sb_btns = []
        secciones = [("👥", "Empleados")] + [(ic, lab) for ic, lab, _, _ in self._LABORAL_SECCIONES]
        for i, (ic, lab) in enumerate(secciones):
            b = QPushButton(f"   {lab}")   # sin icono
            b.setObjectName("btn_sidebar")   # estilo global (acento, hover swap, sin brillo)
            b.setProperty("lg", "true")      # +2pt (14px) vía QSS global
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setCheckable(True); b.setFixedHeight(55)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, idx=i: self._ir(idx))
            self._sb_btns.append(b); lay.addWidget(b)
        lay.addStretch()
        if self._volver:
            lay.addWidget(_btn_salir_sidebar(self._volver))
        return wrap

    _SS_OFF = (f"QPushButton{{background:transparent;color:#FFFFFF;text-align:left;"
               f"padding:8px 8px 8px 24px;border:none;border-left:4px solid transparent;"
               f"border-radius:0px;font-size:13px;font-weight:900;}}"
               f"QPushButton:hover{{background:#FFFFFF;color:{_SIDEBAR};}}")
    _SS_ON = (f"QPushButton{{background:#1A2230;color:{_CIAN};text-align:left;"
              f"padding:8px 8px 8px 24px;border:none;border-left:4px solid {_CIAN};"
              f"border-radius:0px;font-size:13px;font-weight:900;}}")

    def _precargar_imports_en_segundo_plano(self):
        """Importa (en un hilo demonio) los módulos pesados de los formularios laborales para que el
        primer acceso a cada pestaña no pague el coste de importación (reportlab/fuentes/motor). Solo
        realiza imports: no crea ni toca widgets Qt. Silencioso ante cualquier error."""
        import threading

        def _warm():
            for mod in (
                "src.rrhh.maestros",
                "src.rrhh.documents.render.estilo_pdf",       # reportlab + fuentes (base común)
                "src.rrhh.documents.render.nomina_pdf",
                "src.gui.rrhh_doc_inline",
                "src.gui.rrhh_nomina_inline",
                "src.gui.rrhh_contrato_inline",
                "src.gui.gestion_usuarios",                    # motor del asistente (módulo grande)
            ):
                try:
                    __import__(mod)
                except Exception:
                    pass

        try:
            threading.Thread(target=_warm, name="rrhh-warm-imports", daemon=True).start()
        except Exception:
            logger.debug("pre-carga de imports RRHH no disponible")

    def _construir_laboral(self, idx):
        """Monta el contenido real de una pestaña laboral (lazy loading) si aún no está construida.
        La apertura de RRHH no construye ninguna (solo Empleados) → abre al instante; cada formulario
        se monta por pre-cacheo en segundo plano o, si el usuario se adelanta, en su primer clic."""
        lz = getattr(self, "_lazy_laboral", {}).pop(idx, None)
        if lz:
            phl, ic, lab, tipo, sub = lz
            phl.addWidget(self._page_laboral(ic, lab, tipo, sub))

    # Orden de pre-cacheo: de la pestaña MÁS LIGERA a la más pesada (coste de montaje medido). Así los
    # primeros tirones de fondo son mínimos (imperceptibles) y los formularios grandes (Nóminas,
    # Contratos) se montan al final, con la UI ya asentada. Índices de _LABORAL_SECCIONES (1..9).
    _PRECACHE_ORDEN = [4, 7, 8, 6, 3, 5, 9, 2, 1]

    def _precachear_laboral(self):
        """Construye en segundo plano (idle) la siguiente pestaña pendiente (más ligera primero) y se
        reprograma hasta terminar. Deja las pestañas listas para un cambio de pestaña instantáneo."""
        pend = getattr(self, "_lazy_laboral", None)
        if not pend:
            return
        siguiente = next((i for i in self._PRECACHE_ORDEN if i in pend), min(pend))
        try:
            self._construir_laboral(siguiente)
        except Exception:
            logger.exception("pre-cacheo pestaña laboral")
        if self._lazy_laboral:
            QTimer.singleShot(90, self._precachear_laboral)

    def _ir(self, idx):
        # Lazy loading: construir el contenido real de la pestaña laboral en su primer acceso
        # (si el pre-cacheo aún no la ha montado).
        self._construir_laboral(idx)
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self._sb_btns):
            b.setChecked(i == idx)   # estilo via QSS global #btn_sidebar:checked

    # ── Página 0: Empleados (registro/creación) ──────────────────────────────
    def _page_empleados(self):
        w = QWidget(); col = QVBoxLayout(w); col.setContentsMargins(0, 0, 0, 0); col.setSpacing(12)
        tb = QHBoxLayout()
        self.in_buscar = _inp("Buscar nombre / apellidos / NIF…")
        self.in_buscar.returnPressed.connect(self._cargar)
        self.cb_filtro = _combo([("Todos", ""), ("Activos", "activo"), ("Bajas", "baja"),
                                 ("Suspendidos", "suspendido"), ("Excedencias", "excedencia")], "")
        self.cb_filtro.setMinimumWidth(160)   # evita texto cortado en el desplegable
        self.cb_filtro.currentIndexChanged.connect(self._cargar)
        tb.addWidget(self.in_buscar, 2); tb.addWidget(self.cb_filtro, 1)
        tb.addWidget(_btn("Buscar", self._cargar))
        tb.addWidget(_btn("Nuevo", self._nuevo, primary=True))
        tb.addWidget(_btn("Editar", self._editar))
        tb.addWidget(_btn("Vac./Ausencias", self._gestion_laboral))
        tb.addWidget(_btn("Control horario", self._control_horario))
        tb.addWidget(_btn("Expediente", self._expediente, primary=True))
        col.addLayout(tb)
        self.tbl = _tabla(["Nombre", "Apellidos", "NIF/NIE", "Puesto", "Convenio", "Estado", "Alta"])
        self.tbl.doubleClicked.connect(self._expediente)
        col.addWidget(self.tbl)
        return w

    # ── Páginas 1..9: funciones del módulo laboral (lanzan el wizard existente) ──
    def _page_laboral(self, icono, titulo, tipo, subtipo=None):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(14)
        cab = QLabel(f"{icono}  {titulo.upper()}")
        cab.setStyleSheet(f"color:{_CIAN};font-size:18px;font-weight:900;")
        ly.addWidget(cab)

        # CONTRATOS: formulario INLINE (reutiliza el motor de generación del asistente, sin tocarlo).
        if tipo == "CONTRATO":
            try:
                from src.gui.rrhh_contrato_inline import ContratoInlineForm
                ly.addWidget(ContratoInlineForm(self._id_empresa, parent=w), 1)
                return w
            except Exception as e:
                logger.error("formulario inline contrato: %s", e)  # fallback al asistente si falla

        # NÓMINAS: formulario INLINE (los campos se rellenan directamente en la pestaña, sin asistente).
        if tipo == "NÓMINA":
            try:
                from src.gui.rrhh_nomina_inline import NominaInlineForm
                ly.addWidget(NominaInlineForm(self._id_empresa, parent=w), 1)
                return w
            except Exception as e:
                logger.error("formulario inline nómina: %s", e)  # fallback al asistente si algo falla

        # ALTAS LABORALES: formulario INLINE genérico (sustituye al asistente).
        if tipo == "ALTA":
            try:
                ly.addWidget(self._form_alta(w), 1)
                return w
            except Exception as e:
                logger.error("formulario inline alta: %s", e)  # fallback al asistente si algo falla

        # BAJAS LABORALES: formulario INLINE genérico.
        if tipo == "BAJA":
            try:
                ly.addWidget(self._form_baja(w), 1)
                return w
            except Exception as e:
                logger.error("formulario inline baja: %s", e)  # fallback al asistente si algo falla

        # FINIQUITOS: formulario INLINE genérico (con importes/totales calculados en el PDF).
        if tipo == "FINIQUITO":
            try:
                ly.addWidget(self._form_finiquito(w), 1)
                return w
            except Exception as e:
                logger.error("formulario inline finiquito: %s", e)  # fallback al asistente si algo falla

        # CERTIFICADO DE EMPRESA (SEPE): formulario INLINE con tabla mensual de bases.
        if tipo == "CERTIFICADO":
            try:
                ly.addWidget(self._form_cert_empresa(w), 1)
                return w
            except Exception as e:
                logger.error("formulario inline cert. empresa: %s", e)  # fallback al asistente

        # CERTIFICADO LABORAL: formulario INLINE genérico.
        if tipo == "CERT LABORAL":
            try:
                ly.addWidget(self._form_cert_laboral(w), 1)
                return w
            except Exception as e:
                logger.error("formulario inline cert. laboral: %s", e)  # fallback al asistente

        # CARTA DE DESPIDO (no periodo de prueba): formulario INLINE genérico.
        if tipo == "CARTA DESPIDO" and subtipo != "PERÍODO DE PRUEBA":
            try:
                ly.addWidget(self._form_carta_despido(w), 1)
                return w
            except Exception as e:
                logger.error("formulario inline carta despido: %s", e)  # fallback al asistente

        # CARTA DE NO SUPERACIÓN DEL PERÍODO DE PRUEBA: formulario INLINE genérico.
        if tipo == "CARTA DESPIDO" and subtipo == "PERÍODO DE PRUEBA":
            try:
                ly.addWidget(self._form_periodo_prueba(w), 1)
                return w
            except Exception as e:
                logger.error("formulario inline periodo prueba: %s", e)  # fallback al asistente

        texto = _PRUEBA_DESC if subtipo == "PERÍODO DE PRUEBA" else _LABORAL_DESC.get(tipo, "")
        desc = QLabel(texto)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color:{_DIM};font-size:13px;")
        ly.addWidget(desc)
        ly.addSpacing(8)
        btn = _btn(f"ABRIR ASISTENTE · {titulo.upper()}",
                   lambda _=False, t=tipo, s=subtipo: self._abrir_wizard_laboral(t, s), primary=True)
        ly.addWidget(btn)
        ly.addStretch()
        return w

    def _form_alta(self, parent):
        """Formulario inline de ALTA LABORAL (genérico) con autocompletado empresa+trabajador."""
        from src.gui.rrhh_doc_inline import DocumentoInlineForm
        from src.rrhh.documents.render import alta_pdf as A

        secciones = [
            ("Datos de la empresa", A.EMPRESA_CAMPOS),
            ("Datos del trabajador/a", A.TRABAJADOR_CAMPOS),
            ("Datos del contrato", A.CONTRATO_CAMPOS),
            ("Funciones", [A.FUNCIONES_CAMPO]),
            ("Seguridad Social", A.SS_CAMPOS),
        ]

        def _autollenar(emp, dc, setter):
            self._autollenar_maestros(emp, setter)  # datos maestros unificados

        return DocumentoInlineForm(self._id_empresa, secciones, A.generar_alta_pdf,
                                   tipo_doc="alta", autollenar_fn=_autollenar,
                                   campos_grandes=("funciones",), parent=parent)

    def _form_baja(self, parent):
        """Formulario inline de BAJA LABORAL (genérico) con desplegable de tipo y autocompletado."""
        from src.gui.rrhh_doc_inline import DocumentoInlineForm
        from src.rrhh.documents.render import baja_pdf as B

        secciones = [
            ("Datos de la empresa", B.EMPRESA_CAMPOS),
            ("Datos del trabajador/a", B.TRABAJADOR_CAMPOS),
            ("Datos de la baja", B.BAJA_CAMPOS),
            ("Gestión de la empresa", B.GESTION_CAMPOS + [B.OBSERVACIONES_CAMPO]),
        ]

        def _autollenar(emp, dc, setter):
            self._autollenar_maestros(emp, setter)  # datos maestros unificados

        return DocumentoInlineForm(self._id_empresa, secciones, B.generar_baja_pdf,
                                   tipo_doc="baja", autollenar_fn=_autollenar,
                                   campos_grandes=("observaciones",),
                                   campos_combo={"tipo_baja": B.TIPOS_BAJA}, parent=parent)

    def _form_finiquito(self, parent):
        """Formulario inline de FINIQUITO (genérico): datos + conceptos con importe; el PDF calcula
        total bruto, retenciones y líquido."""
        from src.gui.rrhh_doc_inline import DocumentoInlineForm
        from src.rrhh.documents.render import finiquito_pdf as F

        secciones = [
            ("Datos de la empresa", F.EMPRESA_CAMPOS),
            ("Datos del trabajador/a", F.TRABAJADOR_CAMPOS),
            ("Extinción de la relación laboral", F.EXTINCION_CAMPOS),
            ("Detalle de conceptos (días/unidades)", F.DETALLE_CAMPOS),
            ("Conceptos devengados (importes)", F.CONCEPTOS_IMPORTE),
            ("Deducciones", F.DESCUENTOS_IMPORTE + [F.RETENCION_CAMPO]),
            ("Declaración y firmas", [("declaracion", "Declaración"), F.TESTIGOS_CAMPO]),
        ]

        def _autollenar(emp, dc, setter):
            self._autollenar_maestros(emp, setter)  # datos maestros unificados

        return DocumentoInlineForm(
            self._id_empresa, secciones, F.generar_finiquito_pdf, tipo_doc="finiquito",
            autollenar_fn=_autollenar,
            campos_combo={"motivo_extincion": F.MOTIVOS, "tipo_despido": F.TIPOS_DESPIDO,
                          "declaracion": F.DECLARACION}, parent=parent)

    def _form_cert_empresa(self, parent):
        """Formulario inline del CERTIFICADO DE EMPRESA (SEPE) con tabla mensual de bases de cotización."""
        from src.gui.rrhh_doc_inline import DocumentoInlineForm
        from src.rrhh.documents.render import certificado_empresa_pdf as C

        secciones = [
            ("Datos de la empresa", C.EMPRESA_CAMPOS),
            ("Datos del trabajador/a", C.TRABAJADOR_CAMPOS),
            ("Relación laboral", C.RELACION_CAMPOS),
            ("Bases de cotización (relación mensual — hasta 6 meses)",
             {"tabla": ("bases_mensuales", C.BASES_COLUMNAS, 6)}),
            ("Vacaciones", C.VACACIONES_CAMPOS),
            ("Causa del cese", [C.CAUSA_CESE_CAMPO]),
        ]

        def _autollenar(emp, dc, setter):
            self._autollenar_maestros(emp, setter)  # datos maestros unificados

        return DocumentoInlineForm(
            self._id_empresa, secciones, C.generar_certificado_empresa_pdf,
            tipo_doc="certificado_empresa", autollenar_fn=_autollenar,
            campos_combo={"motivo_baja": C.MOTIVOS_BAJA, "causa_cese": C.CAUSAS_CESE}, parent=parent)

    def _form_cert_laboral(self, parent):
        """Formulario inline del CERTIFICADO LABORAL (genérico) con funciones multilínea y finalidad."""
        from src.gui.rrhh_doc_inline import DocumentoInlineForm
        from src.rrhh.documents.render import cert_laboral_pdf as L

        secciones = [
            ("Datos de la empresa", L.EMPRESA_CAMPOS),
            ("Datos del trabajador/a", L.TRABAJADOR_CAMPOS),
            ("Contenido del certificado", L.CONTENIDO_CAMPOS + [L.FUNCIONES_CAMPO]),
            ("Finalidad", [L.FINALIDAD_CAMPO]),
            ("Expedición y firma", L.EXPEDICION_CAMPOS),
        ]

        def _autollenar(emp, dc, setter):
            self._autollenar_maestros(emp, setter)  # datos maestros unificados
            if emp.get("municipio"):
                setter("lugar", emp.get("municipio"))

        return DocumentoInlineForm(
            self._id_empresa, secciones, L.generar_cert_laboral_pdf, tipo_doc="certificado_laboral",
            autollenar_fn=_autollenar, campos_grandes=("funciones",),
            campos_combo={"finalidad": L.FINALIDADES}, parent=parent)

    def _form_carta_despido(self, parent):
        """Formulario inline de la CARTA DE DESPIDO (genérico) con relato de hechos y firmas."""
        from src.gui.rrhh_doc_inline import DocumentoInlineForm
        from src.rrhh.documents.render import carta_despido_pdf as D

        secciones = [
            ("Datos de la empresa", D.EMPRESA_CAMPOS),
            ("Datos del trabajador/a", D.TRABAJADOR_CAMPOS),
            ("Encabezado", D.ENCABEZADO_CAMPOS),
            ("Datos laborales", D.DATOS_LABORALES_CAMPOS),
            ("Comunicación de despido", D.COMUNICACION_CAMPOS),
            ("Relato de los hechos (cronológico y detallado)", [D.HECHOS_CAMPO]),
            ("Liquidación", D.LIQUIDACION_CAMPOS),
            ("Firmas", [("recibi_estado", "Estado del recibí"), D.TESTIGOS_CAMPO]),
        ]

        def _autollenar(emp, dc, setter):
            self._autollenar_maestros(emp, setter)  # datos maestros unificados

        return DocumentoInlineForm(
            self._id_empresa, secciones, D.generar_carta_despido_pdf, tipo_doc="carta_despido",
            autollenar_fn=_autollenar, campos_grandes=("hechos",),
            campos_combo={"tipo_despido": D.TIPOS_DESPIDO, "recibi_estado": D.RECIBI_ESTADOS},
            parent=parent)

    def _form_periodo_prueba(self, parent):
        """Formulario inline de la CARTA DE NO SUPERACIÓN DEL PERÍODO DE PRUEBA (art. 14 ET)."""
        from src.gui.rrhh_doc_inline import DocumentoInlineForm
        from src.rrhh.documents.render import periodo_prueba_pdf as P

        secciones = [
            ("Datos de la empresa", P.EMPRESA_CAMPOS),
            ("Datos del trabajador/a", P.TRABAJADOR_CAMPOS),
            ("Datos del contrato", P.CONTRATO_CAMPOS),
            ("Comunicación", P.COMUNICACION_CAMPOS),
            ("Explicación (opcional — no obligatoria en período de prueba)", [P.EXPLICACION_CAMPO]),
            ("Liquidación", P.LIQUIDACION_CAMPOS),
            ("Devolución de bienes de la empresa", P.BIENES_CAMPOS),
            ("Firmas", [("recibi_estado", "Estado del recibí"),
                        ("representante_empresa", "Representante de la empresa"),
                        ("cargo", "Cargo"), P.TESTIGOS_CAMPO]),
        ]

        def _autollenar(emp, dc, setter):
            self._autollenar_maestros(emp, setter)  # datos maestros unificados

        bienes_combo = {c[0]: P.ESTADO_BIEN for c in P.BIENES_CAMPOS}
        return DocumentoInlineForm(
            self._id_empresa, secciones, P.generar_periodo_prueba_pdf, tipo_doc="periodo_prueba",
            autollenar_fn=_autollenar, campos_grandes=("explicacion",),
            campos_combo={"recibi_estado": P.RECIBI_ESTADOS, **bienes_combo},
            parent=parent)

    def _autollenar_maestros(self, emp, setter):
        """Autocompleta cualquier documento desde la capa de datos MAESTROS unificada
        (Empresa · Trabajador · Contrato · Nómina · Incidencias · Extinción). Cada formulario
        recoge solo las claves que tiene; el resto se ignora. Fuente única = coherencia."""
        try:
            from src.rrhh import maestros
            for clave, valor in maestros.campos_documento(emp, self._id_empresa()).items():
                setter(clave, valor)
        except Exception as e:
            logger.debug("autollenar maestros: %s", e)

    def _id_empresa(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    # ── Documentación LABORAL (migrada): reutiliza el wizard existente (lógica intacta) ──
    def _abrir_wizard_laboral(self, tipo, subtipo=None):
        try:
            from src.gui.gestion_usuarios import _WizardDocumentoFiscal
            _WizardDocumentoFiscal(tipo_inicial=tipo, parent=self,
                                   subtipo_inicial=subtipo).exec()
        except Exception as e:
            logger.error("wizard laboral: %s", e)

    def _cargar(self):
        from src.rrhh.db import empleados
        estado = self.cb_filtro.currentData() or None
        texto = self.in_buscar.text().strip() or None
        self._filas = empleados.listar_empleados(self._id_empresa(), estado=estado, texto=texto)
        self.tbl.setRowCount(len(self._filas))
        for i, e in enumerate(self._filas):
            vals = [e.get("nombre"), e.get("apellidos"), e.get("nif"), e.get("puesto"),
                    e.get("convenio"), e.get("estado"), e.get("fecha_alta")]
            for j, v in enumerate(vals):
                self.tbl.setItem(i, j, _it(v))

    def _sel(self):
        i = self.tbl.currentRow()
        return self._filas[i] if 0 <= i < len(self._filas) else None

    def _nuevo(self):
        dlg = EmpleadoFormDialog(id_empresa=self._id_empresa(), parent=self)
        if dlg.exec():
            self._cargar()

    def _editar(self):
        e = self._sel()
        if not e:
            QMessageBox.information(self, "RRHH", "Selecciona un empleado."); return
        dlg = EmpleadoFormDialog(empleado=e, id_empresa=self._id_empresa(), parent=self)
        if dlg.exec():
            self._cargar()

    def _expediente(self, *_):
        e = self._sel()
        if not e:
            QMessageBox.information(self, "RRHH", "Selecciona un empleado."); return
        ExpedienteDialog(e["id"], self._id_empresa(), parent=self).exec()

    def _gestion_laboral(self, *_):
        e = self._sel()
        if not e:
            QMessageBox.information(self, "RRHH", "Selecciona un empleado."); return
        GestionLaboralDialog(e["id"], self._id_empresa(), parent=self).exec()

    def _control_horario(self, *_):
        e = self._sel()
        if not e:
            QMessageBox.information(self, "RRHH", "Selecciona un empleado."); return
        ControlHorarioDialog(e["id"], self._id_empresa(), parent=self).exec()


# ── Gestión operativa de vacaciones y ausencias (F4.7) ────────────────────────
class GestionLaboralDialog(QDialog):
    def __init__(self, id_empleado, id_empresa=None, parent=None):
        super().__init__(parent)
        self.id_empleado = id_empleado
        self.id_empresa = id_empresa
        self.setWindowTitle("Vacaciones y ausencias")
        self.setMinimumSize(760, 560)
        self.setStyleSheet(f"QDialog{{background:{_BG};}} QLabel{{color:{_TEXT};}}")
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        self.lbl_saldo = QLabel(""); self.lbl_saldo.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        root.addWidget(self.lbl_saldo)
        tabs = QTabWidget()
        tabs.setStyleSheet(f"QTabBar::tab{{background:{_SIDEBAR};color:{_DIM};padding:8px 14px;}}"
                           f"QTabBar::tab:selected{{color:{_CIAN};}}"
                           f"QTabWidget::pane{{border:1px solid {_BORDE};}}")
        tabs.addTab(self._tab_vac(), "Vacaciones")
        tabs.addTab(self._tab_aus(), "Ausencias")
        tabs.addTab(self._tab_cal(), "Calendario")
        root.addWidget(tabs)
        root.addWidget(_btn("Cerrar", self.accept), alignment=Qt.AlignmentFlag.AlignRight)
        self._refrescar()

    # Vacaciones
    def _tab_vac(self):
        w = QWidget(); ly = QVBoxLayout(w)
        self.tbl_vac = _tabla(["id", "Inicio", "Fin", "Días", "Estado", "Aprob. por"])
        ly.addWidget(self.tbl_vac)
        f = QHBoxLayout()
        self.v_ini = _inp("Inicio AAAA-MM-DD"); self.v_fin = _inp("Fin AAAA-MM-DD")
        f.addWidget(self.v_ini); f.addWidget(self.v_fin)
        f.addWidget(_btn("Solicitar", self._solicitar, primary=True))
        ly.addLayout(f)
        a = QHBoxLayout()
        a.addWidget(_btn("Aprobar", lambda: self._estado_vac("aprobar")))
        a.addWidget(_btn("Denegar", lambda: self._estado_vac("denegar")))
        a.addWidget(_btn("Cancelar", lambda: self._estado_vac("cancelar")))
        ly.addLayout(a)
        return w

    # Ausencias
    def _tab_aus(self):
        from src.rrhh import ausencias_servicio as AS
        w = QWidget(); ly = QVBoxLayout(w)
        self.tbl_aus = _tabla(["id", "Tipo", "Inicio", "Fin", "Días", "Motivo"])
        ly.addWidget(self.tbl_aus)
        f = QHBoxLayout()
        self.a_tipo = _combo([(et, k) for k, et in AS.TIPOS.items()])
        self.a_ini = _inp("Inicio"); self.a_fin = _inp("Fin"); self.a_mot = _inp("Motivo")
        for wd in (self.a_tipo, self.a_ini, self.a_fin, self.a_mot):
            f.addWidget(wd)
        f.addWidget(_btn("Registrar", self._registrar_aus, primary=True))
        ly.addLayout(f)
        return w

    def _tab_cal(self):
        w = QWidget(); ly = QVBoxLayout(w)
        self.tbl_cal = _tabla(["Tipo", "Estado", "Inicio", "Fin", "Días"])
        ly.addWidget(self.tbl_cal)
        return w

    def _refrescar(self):
        from src.rrhh import ausencias_servicio as AS
        from src.rrhh import vacaciones_servicio as VS
        s = VS.saldo(self.id_empleado, id_empresa=self.id_empresa)
        self.lbl_saldo.setText(
            f"Saldo {s['anio']}: asignados {s['asignados']} · disfrutados {s['disfrutados']} · "
            f"pendientes {s['pendientes']} · disponibles {s['disponibles']}")
        self._vac = VS.listar(self.id_empleado, self.id_empresa)
        self.tbl_vac.setRowCount(len(self._vac))
        for i, v in enumerate(self._vac):
            for j, val in enumerate([v.get("id"), v.get("fecha_inicio"), v.get("fecha_fin"),
                                     v.get("dias"), v.get("estado"), v.get("aprobado_por")]):
                self.tbl_vac.setItem(i, j, _it(val))
        self._aus = AS.listar(self.id_empleado, self.id_empresa)
        self.tbl_aus.setRowCount(len(self._aus))
        for i, a in enumerate(self._aus):
            for j, val in enumerate([a.get("id"), a.get("tipo"), a.get("fecha_inicio"),
                                     a.get("fecha_fin"), a.get("dias"), a.get("motivo")]):
                self.tbl_aus.setItem(i, j, _it(val))
        cal = AS.calendario(self.id_empleado, self.id_empresa)
        self.tbl_cal.setRowCount(len(cal))
        for i, ev in enumerate(cal):
            for j, val in enumerate([ev.get("tipo"), ev.get("estado"), ev.get("fecha_inicio"),
                                     ev.get("fecha_fin"), ev.get("dias")]):
                self.tbl_cal.setItem(i, j, _it(val))

    def _usuario(self):
        u = getattr(self.parent(), "usuario", None) or {}
        return u.get("nombre") if isinstance(u, dict) else None

    def _solicitar(self):
        from src.rrhh import vacaciones_servicio as VS
        try:
            VS.solicitar(self.id_empleado, self.v_ini.text().strip(), self.v_fin.text().strip(),
                         id_empresa=self.id_empresa)
        except VS.GestionLaboralError as e:
            QMessageBox.warning(self, "Vacaciones", str(e)); return
        self.v_ini.clear(); self.v_fin.clear(); self._refrescar()

    def _vac_sel(self):
        i = self.tbl_vac.currentRow()
        return self._vac[i] if 0 <= i < len(self._vac) else None

    def _estado_vac(self, accion):
        from src.rrhh import vacaciones_servicio as VS
        v = self._vac_sel()
        if not v:
            QMessageBox.information(self, "Vacaciones", "Selecciona una solicitud."); return
        fn = {"aprobar": VS.aprobar, "denegar": VS.denegar, "cancelar": VS.cancelar}[accion]
        try:
            fn(v["id"], usuario=self._usuario(), id_empresa=self.id_empresa)
        except VS.GestionLaboralError as e:
            QMessageBox.warning(self, "Vacaciones", str(e)); return
        self._refrescar()

    def _registrar_aus(self):
        from src.rrhh import ausencias_servicio as AS
        from src.rrhh.vacaciones_servicio import GestionLaboralError
        try:
            AS.registrar(self.id_empleado, self.a_tipo.currentData(), self.a_ini.text().strip(),
                         self.a_fin.text().strip(), motivo=self.a_mot.text().strip(),
                         id_empresa=self.id_empresa)
        except GestionLaboralError as e:
            QMessageBox.warning(self, "Ausencias", str(e)); return
        self.a_ini.clear(); self.a_fin.clear(); self.a_mot.clear(); self._refrescar()


# ── Control horario (RD 8/2019) — F4.9 ────────────────────────────────────────
class ControlHorarioDialog(QDialog):
    def __init__(self, id_empleado, id_empresa=None, parent=None):
        super().__init__(parent)
        self.id_empleado = id_empleado
        self.id_empresa = id_empresa
        self.setWindowTitle("Control horario")
        self.setMinimumSize(820, 580)
        self.setStyleSheet(f"QDialog{{background:{_BG};}} QLabel{{color:{_TEXT};}}")
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        self.lbl_tot = QLabel(""); self.lbl_tot.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        root.addWidget(self.lbl_tot)
        self.tbl = _tabla(["id", "Fecha", "Entrada", "Salida", "Pausa(s)", "Efectivo(min)",
                           "Exceso", "Déficit"])
        root.addWidget(self.tbl)
        # alta de jornada
        f = QHBoxLayout()
        self.in_fecha = _inp("Fecha AAAA-MM-DD")
        self.in_ent = _inp("Entrada AAAA-MM-DD HH:MM")
        self.in_sal = _inp("Salida AAAA-MM-DD HH:MM")
        self.in_plan = _inp("Plan. min (480)")
        for wd in (self.in_fecha, self.in_ent, self.in_sal, self.in_plan):
            f.addWidget(wd)
        f.addWidget(_btn("Registrar", self._registrar, primary=True))
        root.addLayout(f)
        b = QHBoxLayout()
        b.addWidget(_btn("Ver incidencias", self._incidencias))
        b.addWidget(_btn("Exportar CSV", self._export_csv))
        b.addWidget(_btn("Importar fichajes", self._importar))
        b.addWidget(_btn("Cerrar", self.accept))
        root.addLayout(b)
        self._refrescar()

    def _refrescar(self):
        from src.rrhh import control_horario as CH
        self._filas = CH.listar_jornadas(self.id_empleado, self.id_empresa)
        self.tbl.setRowCount(len(self._filas))
        for i, j in enumerate(self._filas):
            for k, val in enumerate([j.get("id"), j.get("fecha"), j.get("hora_entrada"),
                                     j.get("hora_salida"), j.get("pausa_segundos"),
                                     j.get("tiempo_efectivo_min"), j.get("exceso_min"),
                                     j.get("deficit_min")]):
                self.tbl.setItem(i, k, _it(val))
        t = CH._totales(self._filas)
        self.lbl_tot.setText(f"Días {t['dias']} · efectivo {t['efectivo_min']} min · "
                             f"exceso {t['exceso_min']} · déficit {t['deficit_min']}")

    def _registrar(self):
        from src.rrhh import control_horario as CH
        try:
            plan = int(self.in_plan.text().strip() or CH.JORNADA_DEFECTO_MIN)
            CH.registrar_jornada(self.id_empleado, self.in_fecha.text().strip(),
                                 self.in_ent.text().strip(), self.in_sal.text().strip() or None,
                                 planificada_min=plan, usuario=self._usuario(),
                                 id_empresa=self.id_empresa)
        except CH.ControlHorarioError as e:
            QMessageBox.warning(self, "Control horario", str(e)); return
        for w in (self.in_fecha, self.in_ent, self.in_sal, self.in_plan):
            w.clear()
        self._refrescar()

    def _usuario(self):
        u = getattr(self.parent(), "usuario", None) or {}
        return u.get("nombre") if isinstance(u, dict) else None

    def _incidencias(self):
        from src.rrhh import control_horario as CH
        inc = CH.alertas(self.id_empleado, self.id_empresa)
        if not inc:
            QMessageBox.information(self, "Control horario", "Sin incidencias."); return
        txt = "\n".join(f"· {i['fecha']}: {i['tipo']} — {i['detalle']}" for i in inc[:40])
        QMessageBox.information(self, "Incidencias", txt)

    def _export_csv(self):
        from src.rrhh import control_horario as CH
        from PyQt6.QtWidgets import QFileDialog
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar CSV", "control_horario.csv",
                                              "CSV (*.csv)")
        if not ruta:
            return
        try:
            with open(ruta, "w", encoding="utf-8", newline="") as fh:
                fh.write(CH.exportar_csv(self._filas))
            QMessageBox.information(self, "Control horario", f"Exportado a {ruta}")
        except Exception as e:
            QMessageBox.warning(self, "Control horario", f"No se pudo exportar: {e}")

    def _importar(self):
        QMessageBox.information(self, "Control horario",
                               "Importación desde fichajes disponible vía API "
                               "(control_horario.importar_de_fichajes).")
