"""
Ventana de CONTABILIDAD (E6.7) — expone el motor contable en la interfaz principal.

Reutiliza los patrones visuales de `catalogo_gestion`/`compras_gestion` (sidebar `sw`
+ QStackedWidget + helpers _btn/_inp/_tabla/_combo + estilo global). Solo presentación;
la lógica vive en `src.services.contabilidad.*` (ya probada en E6.1-E6.6).
"""

from __future__ import annotations

import datetime as _dt
import logging
import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _SIDEBAR, _btn, _btn_cargando, _btn_salir_sidebar,
                                      _combo, _dialogo_frameless, _inp, _lbl, _tabla)
from src.gui.transiciones import StackedActual
from src.services.seguridad import pestanas_app
from src.services.contabilidad import asientos as A
from src.services.contabilidad import cuentas as K
from src.services.contabilidad import informes as I
from src.services.contabilidad import iva as IVA
from src.services.contabilidad import mapeo as M
from src.services.contabilidad import posting as Pg
from src.utils.i18n import tr

logger = logging.getLogger("gui.contabilidad")

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None


def _aviso(parent, titulo, msg, nivel="info"):
    if mostrar_mensaje is not None:
        mostrar_mensaje(parent, titulo, msg, nivel=nivel)
    else:  # pragma: no cover
        logger.info("%s: %s", titulo, msg)


def _confirmar(parent, titulo, mensaje) -> bool:
    try:
        from assets.estilo_global import mostrar_confirmacion
        return mostrar_confirmacion(parent, titulo, mensaje)
    except Exception:
        return False


class _PedirTextoDialog(QDialog):
    """Diálogo de entrada de texto propio (sustituye a QInputDialog): sin barra nativa de
    Windows, esquinas redondeadas y botón con hover swap — mismo patrón que `camaras_gui.py`."""

    def __init__(self, titulo, prompt, texto="", parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QLineEdit
        v = _dialogo_frameless(self, titulo, ancho=380)
        v.addWidget(_lbl(prompt, dim=False))
        self.inp = QLineEdit(texto); self.inp.setFixedHeight(36)
        self.inp.setStyleSheet(f"QLineEdit{{background:{_BG};color:{_CIAN};border:2px solid {_CIAN};"
                               "border-radius:8px;padding:0 10px;}")
        self.inp.returnPressed.connect(self.accept)
        v.addWidget(self.inp)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Aceptar", self.accept, primary=True))
        v.addLayout(fila)
        self.inp.setFocus()

    def valor(self):
        return self.inp.text()


def _pedir_texto(parent, titulo, prompt, texto=""):
    d = _PedirTextoDialog(titulo, prompt, texto, parent)
    ok = d.exec() == QDialog.DialogCode.Accepted
    return d.valor(), ok


class _PedirOpcionDialog(QDialog):
    def __init__(self, titulo, prompt, opciones, parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, titulo, ancho=380)
        v.addWidget(_lbl(prompt, dim=False))
        self.cmb = _combo([(o, o) for o in opciones])
        v.addWidget(self.cmb)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Aceptar", self.accept, primary=True))
        v.addLayout(fila)

    def valor(self):
        return self.cmb.currentText()


def _pedir_opcion(parent, titulo, prompt, opciones):
    d = _PedirOpcionDialog(titulo, prompt, opciones, parent)
    ok = d.exec() == QDialog.DialogCode.Accepted
    return d.valor(), ok


class _BloqueadosDialog(QDialog):
    """Revisión manual de eventos de la cola contable bloqueados por ejercicio cerrado (ver
    `services.contabilidad.posting._separar_bloqueados_por_cierre` — antes se reintentaban en
    SILENCIO en cada arranque de la app, para siempre, sin que nadie pudiera verlos ni actuar).
    Lista + botón REINTENTAR (requiere haber reabierto antes el ejercicio correspondiente, si no
    se volverá a bloquear en el siguiente «PROCESAR CONTABILIZACIÓN PENDIENTE»)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, tr("contab.bloqueados_t", default="EVENTOS BLOQUEADOS"), ancho=760)
        v.addWidget(_lbl(tr("contab.bloqueados_ayuda",
                            default="Eventos que no se pudieron contabilizar porque su ejercicio ya "
                                    "cerró. Reabre el ejercicio (pestaña Cierres) antes de reintentar."),
                         dim=True))
        self.tbl = _tabla_c(["Fecha", "Evento", "Ref", "Motivo"])
        self.tbl.setMinimumHeight(320)
        v.addWidget(self.tbl, 1)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn(tr("contab.reintentar", default="REINTENTAR SELECCIONADO"),
                            self._reintentar, primary=True))
        fila.addWidget(_btn(tr("comun.cerrar", default="Cerrar"), self.accept))
        v.addLayout(fila)
        self._cargar()

    def _cargar(self):
        self._filas = Pg.listar_bloqueados_por_cierre()
        self.tbl.setRowCount(0)
        for f in self._filas:
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            vals = [f.get("fecha_evento"), f.get("evento"), f.get("ref"), f.get("ultimo_error")]
            for c, val in enumerate(vals):
                self.tbl.setItem(r, c, QTableWidgetItem("" if val is None else str(val)))

    def _reintentar(self):
        fila = self.tbl.currentRow()
        if fila < 0 or fila >= len(self._filas):
            _aviso(self, "Contabilidad",
                   tr("contab.bloq_selecciona", default="Selecciona un evento de la tabla."), "warning")
            return
        ev = self._filas[fila]
        if Pg.reintentar_bloqueado(ev["id"]):
            _aviso(self, "Contabilidad",
                   tr("contab.bloq_reintentado",
                      default="Marcado para reintentar — pulsa «PROCESAR CONTABILIZACIÓN PENDIENTE» "
                              "para contabilizarlo (si su ejercicio sigue cerrado, volverá a bloquearse)."))
            self._cargar()
        else:
            _aviso(self, "Contabilidad",
                   tr("contab.bloq_no_reintentado", default="No se pudo reencolar este evento."), "warning")


def _tabla_c(cols):
    """Igual que _tabla pero con las CABECERAS +2pt (11px → 13px), solo para Contabilidad.
    No toca el helper global _tabla (compartido por el resto de módulos)."""
    t = _tabla(cols)
    t.setStyleSheet(t.styleSheet().replace("font-size:11px", "font-size:13px"))
    return t


class ContabilidadWindow(QWidget):
    _SECCIONES = [
        ("plan", "📒", "Plan de cuentas"),
        ("diario", "📓", "Diario"),
        ("mayor", "📚", "Mayor"),
        ("balances", "⚖️", "Balances"),
        ("gastos", "💸", "Gastos"),
        ("iva", "🧾", "Libros IVA"),
        ("cierres", "🔒", "Cierres"),
        ("plantillas", "🔁", "Plantillas de asiento"),
        ("mapeo", "🗺️", "Mapeo de cuentas"),
        # Migrados (módulo fiscal): AEAT (embebido) + documentos fiscales, ahora en 3 pestañas separadas
        # (con los campos a rellenar EN LA PROPIA pestaña, sin ventana emergente).
        ("aeat", "📑", "AEAT"),
        ("libro_ing", "📈", "Libro de Ingresos"),
        ("libro_gas", "📉", "Libro de Gastos"),
        ("auditoria", "🔍", "Informe Auditoría"),
        ("calc_fiscal", "🧮", "Calculadora Fiscal"),
    ]

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.anio = _dt.date.today().year
        self.setWindowTitle("Smart Manager — " + tr("contab.titulo", default="CONTABILIDAD"))

        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self._sidebar())
        right = QWidget(); rcol = QVBoxLayout(right)
        rcol.setContentsMargins(24, 18, 24, 18); rcol.setSpacing(14)
        rcol.addLayout(self._header())
        # Lazy loading (init en primer acceso): construir las 11 páginas por adelantado —
        # 2 de ellas embeben ventanas completas (AEAT + FiscalPanels en _page_aeat) — es lo
        # que hacía que el módulo tardara demasiado en abrirse. Solo se construye de verdad
        # la página que se va a mostrar; el resto queda como placeholder hasta que el usuario
        # pulsa esa sección del sidebar (ver `_asegurar_pagina`).
        # StackedActual (no QStackedWidget "a pelo"): evita que una página ancha (p. ej. la
        # Calculadora Fiscal, que embebe su propio asistente de 5 pasos) deje abultado para
        # siempre el ancho mínimo del stack y recorte el contenido de las demás pestañas.
        self.stack = StackedActual()
        # OJO: este orden debe coincidir EXACTAMENTE con `_SECCIONES` (el sidebar conecta cada
        # botón a `_ir(idx)` usando la POSICIÓN en `_SECCIONES` como índice directo sobre esta
        # lista) — un desajuste aquí hace que un botón del sidebar cargue la página de OTRA
        # sección (bug real encontrado: desde "Plantillas" en adelante las dos listas estaban
        # desalineadas, así que p. ej. pulsar "Calculadora Fiscal" mostraba "Mapeo de cuentas").
        self._page_factories = [
            self._page_plan, self._page_diario, self._page_mayor, self._page_balances,
            self._page_gastos, self._page_iva, self._page_cierres, self._page_plantillas,
            self._page_mapeo, self._page_aeat, self._page_libro_ingresos,
            self._page_libro_gastos, self._page_auditoria, self._page_calc_fiscal,
        ]
        self._paginas_listas = set()
        for _ in self._page_factories:
            self.stack.addWidget(QWidget())
        rcol.addWidget(self.stack, 1)
        root.addWidget(right, 1)
        self._ir(0)

        # Aviso de bienvenida SOLO si la contabilidad de la empresa todavía no está activada — sin
        # plan de cuentas/ejercicio abierto ninguna sección del módulo tiene datos con los que trabajar.
        # Diferido con QTimer (patrón ya usado en el proyecto para diálogos al abrir una ventana) para
        # que el modal aparezca ya con la ventana visible, no antes.
        if not K.contabilidad_activa():
            QTimer.singleShot(0, self._aviso_activar_contabilidad)

        # P3 (UX-TPV-01): sidebar colapsable con persistencia por usuario.
        try:
            from src.gui.sidebar_colapsable import instalar_sidebar_colapsable
            if getattr(self, "sidebar", None) is not None:
                instalar_sidebar_colapsable(self, self.sidebar, usuario=self.usuario, clave="contabilidad")
        except Exception:
            pass

    # ── Cabecera / sidebar ───────────────────────────────────────────────────
    def _header(self):
        cab = QHBoxLayout()
        t = QLabel("📊  " + tr("contab.titulo", default="CONTABILIDAD"))
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch(1)
        if not K.contabilidad_activa():
            cab.addWidget(_btn(tr("contab.activar", default="ACTIVAR CONTABILIDAD"),
                               self._activar, primary=True))
        return cab

    def _sidebar(self):
        from PyQt6.QtWidgets import QScrollArea
        from src.gui.foundation.tokens import qss_scrollbar
        wrap = QFrame(); wrap.setObjectName("sw"); wrap.setFixedWidth(280); self.sidebar = wrap  # P3 (280: cabe "SMART ACCOUNTING")
        wrap.setStyleSheet(f"#sw{{background:{_SIDEBAR};}}")
        outer = QVBoxLayout(wrap); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        # El contenido de la sidebar va dentro de un QScrollArea con la scrollbar ESTÁNDAR del software
        # (turquesa, extremos redondeados): con muchas secciones ningún botón queda cortado (p. ej.
        # "SALIR AL MENÚ"). Opaco (color de la sidebar) para no transparentar nada en la ventana frameless.
        scroll = QScrollArea(wrap); scroll.setObjectName("sb_scroll")
        scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea#sb_scroll{{background:{_SIDEBAR};border:none;}}")
        scroll.verticalScrollBar().setStyleSheet(qss_scrollbar())

        # OJO: los fondos del content/viewport DEBEN llevar selector (#objectName). Un stylesheet sin
        # selector ("background:...") casca a TODOS los descendientes —incluidos los botones— y les pisa
        # el 'background:transparent', rompiendo el hover swap y el :checked global. Con selector, el fondo
        # se aplica SOLO al contenedor y los botones conservan su estilo global #btn_sidebar.
        content = QWidget(); content.setObjectName("sb_content")
        content.setStyleSheet(f"#sb_content{{background:{_SIDEBAR};}}")
        lay = QVBoxLayout(content); lay.setContentsMargins(0, 0, 0, 16); lay.setSpacing(2)
        cab = QLabel("SMART ACCOUNTING")   # título de marca de la sidebar (igual en todos los idiomas)
        cab.setStyleSheet("color:#FFFFFF;padding:0 0 24px 28px;font-size:16px;font-weight:900;"
                          "letter-spacing:2px;background:transparent;")
        lay.addWidget(cab)
        self._sb = []
        # Acceso completo (perfil o concesión de módulo en Seguridad · Roles) → todas las
        # secciones visibles por defecto (una regla de pestaña puntual aún puede DENEGAR una en
        # concreto). Sin acceso completo — entró solo por una concesión de pestaña suelta (Seguridad
        # · Reglas de acceso) — ninguna sección se ve por defecto: solo la(s) concedida(s).
        _tiene_completo = pestanas_app.tiene_modulo_completo("contabilidad", self.usuario, False)
        for i, (sid, icono, defecto) in enumerate(self._SECCIONES):
            b = QPushButton(f"   {tr('contab.sec_' + sid, default=defecto).upper()}")   # sin icono — sidebar: mayúsculas
            # Mismo tamaño de texto (12px, base) que el resto de sidebars de la app — consistencia
            # exigida explícitamente; la variante +2pt (`lg="true"`) se retira aquí.
            b.setObjectName("btn_sidebar")   # estilo global (acento, hover swap, sin brillo)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setCheckable(True); b.setFixedHeight(55)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, idx=i: self._ir(idx))
            if not pestanas_app.visible(f"contabilidad.{sid}", self.usuario, _tiene_completo):
                b.setVisible(False)
            self._sb.append(b); lay.addWidget(b)
        lay.addStretch(1)
        if self._volver:   # SALIR AL MENÚ (rojo) al fondo del sidebar
            lay.addWidget(_btn_salir_sidebar(self._volver_menu))
        scroll.setWidget(content)
        outer.addWidget(scroll)
        return wrap

    _ON = (f"QPushButton{{background:#1A2230;color:{_CIAN};text-align:left;padding:8px 8px 8px 24px;"
           f"border:none;border-left:4px solid {_CIAN};border-radius:0px;font-size:13px;font-weight:900;}}")
    _OFF = (f"QPushButton{{background:transparent;color:#FFFFFF;text-align:left;padding:8px 8px 8px 24px;"
            f"border:none;border-left:4px solid transparent;border-radius:0px;font-size:13px;font-weight:900;}}"
            f"QPushButton:hover{{background:#FFFFFF;color:{_SIDEBAR};}}")

    def _asegurar_pagina(self, idx):
        """Construye la página `idx` la primera vez que se visita (lazy loading) y la
        sustituye por su placeholder en el stack, conservando la posición."""
        if idx in self._paginas_listas:
            return
        nuevo = self._page_factories[idx]()
        viejo = self.stack.widget(idx)
        self.stack.removeWidget(viejo)
        self.stack.insertWidget(idx, nuevo)
        if viejo is not None:
            viejo.deleteLater()
        self._paginas_listas.add(idx)

    def _ir(self, idx):
        self._asegurar_pagina(idx)
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self._sb):
            b.setChecked(i == idx)   # estilo via QSS global #btn_sidebar:checked
        [self._load_plan, self._load_diario, lambda: None, self._load_balances,
         self._load_gastos, self._load_iva, lambda: None, lambda: None,
         lambda: None, lambda: None, lambda: None,
         lambda: None, lambda: None, lambda: None][idx]()   # aeat + libro_ing/gas + auditoría +
        # calc_fiscal + plantillas + mapeo: sin carga aquí (se cargan solas en su propia página)

    def _volver_menu(self):
        if callable(self._volver):
            self._volver()

    # ── Migrados: AEAT (embebido) + documentos fiscales (libros/auditoría) ───────
    def _page_aeat(self):
        """Pestaña AEAT con 4 apartados: Generar (modelos AEAT) · Certificados · Registros Verifactu ·
        Facturae (FACe). El módulo Fiscal del menú principal se MIGRA aquí reutilizando `FiscalPanels`
        (misma implementación que la ventana Fiscal; sin duplicar). Degradable: si algo falla, se
        muestra solo lo disponible."""
        from PyQt6.QtWidgets import QTabWidget
        tabs = QTabWidget()
        tabs.setStyleSheet("QTabWidget::pane { border: none; }")   # sin líneas grises alrededor del contenido
        # 1) Generar — modelos AEAT (303/390/111/190/347/349): el AEATWindow existente.
        try:
            from src.gui.aeat_gui import AEATWindow
            tabs.addTab(AEATWindow(callback_vuelta=None, usuario=self.usuario, main=self), "Generar")
        except Exception as e:
            logger.error("embed AEAT (Generar) en Contabilidad: %s", e)
            tabs.addTab(QWidget(), "Generar")
        # 2) + 3) + 4) Certificados, Registros Verifactu y Facturae (FACe) — módulo Fiscal migrado
        # (reutiliza FiscalPanels).
        try:
            from src.gui.fiscal_gui import FiscalPanels
            self._fiscal_panels = FiscalPanels(usuario=self.usuario, host=self)
            tabs.addTab(self._fiscal_panels.pagina_certificados, "Certificados")
            tabs.addTab(self._fiscal_panels.pagina_verifactu, "Registros Verifactu")
            tabs.addTab(self._fiscal_panels.pagina_facturae, "Facturae (FACe)")
        except Exception as e:
            logger.error("embed Fiscal (Certificados/Verifactu) en AEAT: %s", e)
        # Animación de deslizamiento al cambiar de sub-pestaña (Generar/Certificados/Registros
        # Verifactu/Facturae) — mismo mecanismo ya usado en el resto de la app (p. ej. el toggle
        # Recepción/Traspaso de `recepcion_pale.py`), sin motor nuevo.
        try:
            from src.gui.transiciones import instalar_transicion_tabs
            instalar_transicion_tabs(tabs)
        except Exception:
            pass
        return tabs

    # ── Documentos fiscales: 3 pestañas con campos INLINE (sin ventana emergente) ─────────────
    def _page_libro_ingresos(self):
        # Sin Empresa/CIF/Domicilio (ya se ve en toda la app) y con selector de calendario en vez
        # de texto libre para desde/hasta. El documento generado (`render_libro_ingresos`) ya
        # muestra SOLO los ingresos brutos del período (facturas de cliente reales, fecha exacta
        # por fila) — sin comparativa interanual ni cruce con gastos, tal cual se pidió.
        return self._panel_fiscal(
            "LIBRO INGRESOS", "📈  Libro de Ingresos",
            "Genera el libro de ingresos de la empresa para el período indicado.",
            mostrar_empresa=False, fecha_picker=True, boton_cierre=True,
            boton_texto="GENERAR\nLIBRO DE\nINGRESOS")

    # ── Libro de Gastos: período + 2 secciones nuevas (fijos mensuales / extraordinarios) ──────
    def _page_libro_gastos(self):
        """Ya NO reutiliza `_panel_fiscal` (el layout diverge demasiado: botón de generación en la
        MISMA fila que las fechas, más dos secciones de alta/listado completas debajo) — pero sigue
        reutilizando sus piezas (`_datos_empresa`, `_generar_doc_fiscal`, `_date_neon`, `_texto_periodo`)
        para que "GENERAR LIBRO DE GASTOS" funcione exactamente igual que el resto de documentos
        fiscales de esta ventana. El documento (`render_libro_gastos`) ya muestra SOLO el gasto
        bruto del período (manuales + facturas de compra vía `listar_gastos_completo`) — sin
        comparativa interanual ni total vs ingresos."""
        from PyQt6.QtCore import QDate
        from src.gui.ventas import _date_neon
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(16)
        t = QLabel("📉  Libro de Gastos"); t.setStyleSheet(f"color:{_CIAN};font-size:17px;font-weight:900;")
        ly.addWidget(t)
        sub = QLabel("Genera el libro de gastos de la empresa para el período indicado.")
        sub.setStyleSheet(f"color:{_DIM};"); sub.setWordWrap(True); ly.addWidget(sub)

        e = self._datos_empresa()
        in_nombre = _inp(""); in_nombre.setText(e["nombre"])
        in_cif = _inp(""); in_cif.setText(e["cif"])
        in_dir = _inp(""); in_dir.setText(e["dir"])

        fila = QHBoxLayout()
        in_ini = _date_neon(QDate(QDate.currentDate().year(), 1, 1)); in_ini.setMinimumWidth(140)
        in_fin = _date_neon(QDate.currentDate()); in_fin.setMinimumWidth(140)
        ld = QLabel("Período · desde:"); ld.setStyleSheet(f"color:{_DIM};font-weight:700;")
        lh = QLabel("hasta:"); lh.setStyleSheet(f"color:{_DIM};font-weight:700;")
        fila.addWidget(ld); fila.addWidget(in_ini)
        fila.addWidget(lh); fila.addWidget(in_fin)
        panel = {"tipo": "LIBRO GASTOS", "nombre": in_nombre, "cif": in_cif, "dir": in_dir,
                 "ini": in_ini, "fin": in_fin, "sub": None, "ruta": None}
        fila.addWidget(_btn("📄  GENERAR LIBRO DE GASTOS", lambda: self._generar_doc_fiscal(panel), primary=True))
        fila.addStretch(1)
        ly.addLayout(fila)

        lbl_res = QLabel(""); lbl_res.setWordWrap(True); lbl_res.setVisible(False)
        lbl_res.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        panel["res"] = lbl_res; ly.addWidget(lbl_res)
        btn_open = _btn("📂  ABRIR PDF", lambda: self._abrir_pdf(panel), primary=True)
        btn_open.setVisible(False); panel["open"] = btn_open
        ly.addWidget(btn_open, alignment=Qt.AlignmentFlag.AlignLeft)

        linea = QFrame(); linea.setFrameShape(QFrame.Shape.HLine)
        linea.setStyleSheet(f"background:{_DIM};max-height:1px;border:none;")
        ly.addWidget(linea)

        self._sec_gasto = {}   # naturaleza -> widgets de esa sección (form + tabla + estado de edición)
        ly.addWidget(self._seccion_gasto_naturaleza(
            "fijo_mensual", "🏢  Gastos fijos mensuales",
            "Materiales, alquiler, suministros y demás gastos recurrentes del negocio."))
        ly.addWidget(self._seccion_gasto_naturaleza(
            "extraordinario", "🎯  Gastos extraordinarios",
            "Publicidad y otros gastos puntuales fuera de la operativa mensual habitual."))
        ly.addStretch()
        return w

    def _seccion_gasto_naturaleza(self, naturaleza, titulo, subtitulo):
        """Construye UNA sección (form de alta + tabla propia) de "Libro de Gastos". Reutiliza el
        motor existente `registrar_gasto`/`anular_gasto`/`listar_gastos` (migr. 0277 añadió
        `naturaleza_gasto` para que cada sección liste SOLO sus propias filas) — no se crea una
        tabla de gastos paralela. "Editar" (decisión documentada, ver `_editar_gasto_seccion`):
        ANULAR + REGISTRAR DE NUEVO con los valores editados, nunca mutar in-place un asiento ya
        contabilizado — mismo criterio de inmutabilidad que ya usa `asientos.anular` para todo el
        libro diario."""
        box = QFrame(); bly = QVBoxLayout(box); bly.setContentsMargins(0, 8, 0, 0); bly.setSpacing(8)
        t = QLabel(titulo); t.setStyleSheet(f"color:{_CIAN};font-size:14px;font-weight:900;")
        bly.addWidget(t)
        s = QLabel(subtitulo); s.setStyleSheet(f"color:{_DIM};"); s.setWordWrap(True); bly.addWidget(s)

        from PyQt6.QtCore import QDate
        from src.gui.ventas import _date_neon
        f1 = QHBoxLayout()
        in_nombre = _inp("Nombre (obligatorio)")
        cmb_tipo = _combo([(et, cod) for cod, et, _c, _iva in M.TIPOS_GASTO])
        cmb_tipo.setMinimumWidth(220); cmb_tipo.view().setMinimumWidth(300)
        from PyQt6.QtWidgets import QComboBox as _QComboBox
        cmb_tipo.setSizeAdjustPolicy(_QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        cmb_tipo.setMinimumContentsLength(16)
        in_importe = _inp("Importe €"); in_importe.setFixedWidth(120)
        in_fecha = _date_neon(QDate.currentDate()); in_fecha.setMinimumWidth(140)
        for et, wd in (("Nombre:", in_nombre), ("Tipo:", cmb_tipo), ("Importe:", in_importe), ("Fecha:", in_fecha)):
            lb = QLabel(et); lb.setStyleSheet(f"color:{_DIM};"); f1.addWidget(lb); f1.addWidget(wd)
        btn_registrar = _btn("➕  REGISTRAR", None, primary=True)
        f1.addWidget(btn_registrar)
        bly.addLayout(f1)

        tabla = _tabla_c(["Nº", "Fecha", "Nombre", "Importe", "Estado", "Editar", "Eliminar"])
        tabla.setMinimumHeight(180)
        bly.addWidget(tabla)

        estado = {"naturaleza": naturaleza, "in_nombre": in_nombre, "cmb_tipo": cmb_tipo,
                 "in_importe": in_importe, "in_fecha": in_fecha, "btn_registrar": btn_registrar,
                 "tabla": tabla, "cache": [], "editando_id": None}
        self._sec_gasto[naturaleza] = estado
        btn_registrar.clicked.connect(lambda: self._guardar_gasto_seccion(naturaleza))
        self._load_gastos_seccion(naturaleza)
        return box

    def _guardar_gasto_seccion(self, naturaleza):
        """Alta nueva O guardado de una edición en curso (ver `estado['editando_id']`)."""
        st = self._sec_gasto[naturaleza]
        nombre = st["in_nombre"].text().strip()
        if not nombre:
            _aviso(self, "Libro de Gastos", "Indica un nombre para el gasto.", "warning")
            return
        try:
            importe = float((st["in_importe"].text() or "0").replace(",", ".").strip())
        except ValueError:
            importe = 0.0
        if importe <= 0:
            _aviso(self, "Libro de Gastos", "Introduce un importe válido.", "warning")
            return
        tipo = st["cmb_tipo"].currentData()
        fecha = st["in_fecha"].date().toString("yyyy-MM-dd")
        editando_id = st["editando_id"]
        if editando_id is not None:
            # Editar = anular el asiento original + registrar uno nuevo con los valores editados
            # (nunca se muta in-place un asiento ya contabilizado: mismo criterio de inmutabilidad
            # del libro diario/`asientos.anular`).
            if not Pg.anular_gasto(editando_id):
                _aviso(self, "Libro de Gastos", "No se pudo anular el gasto original para editarlo.", "error")
                return
        r = Pg.registrar_gasto(tipo, importe, fecha=fecha, concepto=nombre,
                               naturaleza_gasto=naturaleza)
        if not r:
            _aviso(self, "Libro de Gastos",
                  "No se pudo registrar (¿contabilidad activada?).", "warning")
            return
        st["in_nombre"].clear(); st["in_importe"].clear()
        st["editando_id"] = None
        st["btn_registrar"].setText("➕  REGISTRAR")
        _aviso(self, "Libro de Gastos",
              f"Gasto «{nombre}» registrado (asiento nº {r.get('numero')}).", "success")
        self._load_gastos_seccion(naturaleza)
        self._load_diario()

    def _load_gastos_seccion(self, naturaleza):
        st = self._sec_gasto[naturaleza]
        st["cache"] = Pg.listar_gastos(anio=self.anio, naturaleza_gasto=naturaleza)
        tabla = st["tabla"]
        tabla.setRowCount(len(st["cache"]))
        for i, a in enumerate(st["cache"]):
            vals = [a.get("numero"), a.get("fecha"), a.get("concepto"), a.get("total_debe"), a.get("estado")]
            for c, v in enumerate(vals):
                tabla.setItem(i, c, QTableWidgetItem("" if v is None else str(v)))
            anulado = a.get("estado") != "contabilizado"
            b_edit = QPushButton("✏️"); b_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            b_edit.setEnabled(not anulado)
            b_edit.setStyleSheet(
                f"QPushButton{{background:transparent;color:{_CIAN};border:1px solid {_CIAN};"
                "border-radius:6px;padding:3px 10px;font-weight:bold;}"
                f"QPushButton:hover{{background:{_CIAN};color:{_BG};}}"
                "QPushButton:disabled{color:#555;border-color:#555;}")
            b_edit.clicked.connect(lambda _=False, fila=a: self._editar_gasto_seccion(naturaleza, fila))
            tabla.setCellWidget(i, 5, b_edit)
            b_del = QPushButton("🗑️"); b_del.setCursor(Qt.CursorShape.PointingHandCursor)
            b_del.setEnabled(not anulado)
            b_del.setStyleSheet(
                "QPushButton{background:transparent;color:#FF5C5C;border:1px solid #FF5C5C;"
                "border-radius:6px;padding:3px 10px;font-weight:bold;}"
                "QPushButton:hover{background:#FF5C5C;color:#0B1118;}"
                "QPushButton:disabled{color:#555;border-color:#555;}")
            b_del.clicked.connect(lambda _=False, fila=a: self._eliminar_gasto_seccion(naturaleza, fila))
            tabla.setCellWidget(i, 6, b_del)

    def _editar_gasto_seccion(self, naturaleza, fila):
        st = self._sec_gasto[naturaleza]
        if fila.get("estado") != "contabilizado":
            _aviso(self, "Libro de Gastos", "Solo se pueden editar gastos contabilizados.", "warning")
            return
        st["in_nombre"].setText(str(fila.get("concepto") or ""))
        st["in_importe"].setText(str(fila.get("total_debe") or ""))
        try:
            from PyQt6.QtCore import QDate as _QDate
            f = str(fila.get("fecha") or "")
            qd = _QDate.fromString(f[:10], "yyyy-MM-dd")
            if qd.isValid():
                st["in_fecha"].setDate(qd)
        except Exception:
            pass
        st["editando_id"] = fila.get("id")
        st["btn_registrar"].setText("💾  GUARDAR CAMBIOS")
        _aviso(self, "Libro de Gastos",
              "Edita los campos y pulsa «GUARDAR CAMBIOS» (se anula el asiento original y se "
              "registra uno nuevo con los valores editados).", "info")

    def _eliminar_gasto_seccion(self, naturaleza, fila):
        if fila.get("estado") != "contabilizado":
            _aviso(self, "Libro de Gastos", "Solo se pueden eliminar gastos contabilizados.", "warning")
            return
        if not _confirmar(self, "Eliminar gasto",
                          f"¿Eliminar «{fila.get('concepto')}» ({fila.get('total_debe')} €)? "
                          "Se anulará mediante contraasiento (no se borra el registro contable)."):
            return
        r = Pg.anular_gasto(fila["id"])
        if r:
            _aviso(self, "Libro de Gastos", "Gasto eliminado (anulado por contraasiento).", "success")
            self._load_gastos_seccion(naturaleza)
            self._load_diario()
        else:
            _aviso(self, "Libro de Gastos", "No se pudo eliminar el gasto.", "warning")

    def _page_calc_fiscal(self):
        """Calculadora Fiscal: asistente paso a paso que estima el Impuesto de Sociedades y el
        ahorro fiscal por deducciones. Autocontenida (`gui.calculadora_fiscal_wizard`); toda la
        lógica vive en `services.contabilidad.calculadora_fiscal`."""
        try:
            from src.gui.calculadora_fiscal_wizard import CalculadoraFiscalWizard
            return CalculadoraFiscalWizard(usuario=self.usuario)
        except Exception as e:
            logger.error("embed Calculadora Fiscal en Contabilidad: %s", e)
            return QWidget()

    def _page_auditoria(self):
        w = self._panel_fiscal(
            "INFORME AUDIT", "🔍  Informe de Auditoría",
            "Genera un informe de auditoría del ámbito elegido para el período indicado.",
            subtipos=["CAJA", "RRHH", "ACCESOS", "MOVIMIENTOS", "DOCUMENTOS"])
        # `cadena_auditoria_valida` re-deriva el hash encadenado del diario contable y no tenía
        # ningún botón que la llamara — verificación de integridad, no un informe en PDF, así que
        # se añade aparte del formulario compartido (`_panel_fiscal`, reutilizado por otros paneles
        # que no necesitan esta acción).
        w.layout().addWidget(_btn("🔒  Verificar integridad de la cadena contable",
                                  self._verificar_cadena_auditoria, primary=True))
        return w

    def _verificar_cadena_auditoria(self):
        from src.services.contabilidad import asientos as _A
        try:
            ok = _A.cadena_auditoria_valida(id_empresa=None, anio=self.anio)
        except Exception as ex:
            logger.error("cadena_auditoria_valida: %s", ex)
            _aviso(self, "Auditoría", f"No se pudo verificar la cadena contable: {ex}", "error")
            return
        _aviso(self, "Auditoría",
              "La cadena de asientos contables del ejercicio es íntegra (sin alteraciones detectadas)."
              if ok else "⚠️ Se ha detectado una discrepancia en la cadena de hashes del diario "
              "contable — posible alteración de registros.",
              "success" if ok else "error")

    # ── Plantillas de asiento + recurrentes (genuinamente ausente, sin frontend) ─────────
    def _page_plantillas(self):
        from PyQt6.QtWidgets import QAbstractItemView
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        ly.addWidget(QLabel("Plantillas de asiento reutilizables y asientos recurrentes "
                            "(alquileres, cuotas, provisiones…)."))
        form = QHBoxLayout()
        self.in_plant_cod = _inp("Código"); self.in_plant_cod.setFixedWidth(120)
        self.in_plant_nom = _inp("Nombre")
        self.in_plant_conc = _inp("Concepto (opcional)")
        form.addWidget(self.in_plant_cod); form.addWidget(self.in_plant_nom); form.addWidget(self.in_plant_conc)
        ly.addLayout(form)

        ly.addWidget(QLabel("Líneas (cuenta / debe / haber / descripción) — deben cuadrar Σdebe=Σhaber:"))
        self.tbl_plant_lineas = _tabla_c(["Cuenta", "Debe", "Haber", "Descripción"])
        self.tbl_plant_lineas.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        self.tbl_plant_lineas.setRowCount(4)
        for r in range(4):
            for c in range(4):
                self.tbl_plant_lineas.setItem(r, c, QTableWidgetItem(""))
        ly.addWidget(self.tbl_plant_lineas)
        fl = QHBoxLayout()
        fl.addWidget(_btn("+ Añadir línea", self._plant_add_linea, primary=True))
        fl.addWidget(_btn("− Quitar línea", self._plant_quitar_linea, danger=True))
        fl.addStretch(1)
        fl.addWidget(_btn("💾  Crear / actualizar plantilla", self._crear_plantilla, primary=True))
        ly.addLayout(fl)

        ly.addWidget(QLabel("Plantillas existentes:"))
        self.tbl_plant = _tabla_c(["Id", "Código", "Nombre", "Concepto"])
        ly.addWidget(self.tbl_plant, 1)
        acc = QHBoxLayout()
        acc.addWidget(_btn("📄  Generar asiento ahora", self._generar_desde_plantilla, primary=True))
        acc.addWidget(_btn("🔁  Programar recurrente", self._programar_recurrente, primary=True))
        acc.addStretch(1)
        acc.addWidget(_btn_cargando("🔄  Actualizar", self._load_plantillas))
        ly.addLayout(acc)
        self._plant_cache = []
        self._load_plantillas()
        return w

    def _load_plantillas(self):
        from src.services.contabilidad import plantillas as PL
        self._plant_cache = PL.listar_plantillas()
        self.tbl_plant.setRowCount(len(self._plant_cache))
        for i, p in enumerate(self._plant_cache):
            for j, v in enumerate([p.get("id"), p.get("codigo"), p.get("nombre"), p.get("concepto")]):
                self.tbl_plant.setItem(i, j, QTableWidgetItem("" if v is None else str(v)))

    def _plant_add_linea(self):
        r = self.tbl_plant_lineas.rowCount()
        self.tbl_plant_lineas.insertRow(r)
        for c in range(4):
            self.tbl_plant_lineas.setItem(r, c, QTableWidgetItem(""))
        _aviso(self, "Plantillas", "Línea añadida.", "success")

    def _plant_quitar_linea(self):
        r = self.tbl_plant_lineas.currentRow()
        if r < 0:
            _aviso(self, "Plantillas", "Selecciona antes una línea en la tabla.", "warning")
            return
        if not _confirmar(self, "Quitar línea", f"¿Quitar la línea {r + 1} de la plantilla?"):
            return
        try:
            self.tbl_plant_lineas.removeRow(r)
        except Exception as e:
            _aviso(self, "Plantillas", f"No se pudo quitar la línea: {e}", "error")
            return
        _aviso(self, "Plantillas", "Línea quitada.", "success")

    def _crear_plantilla(self):
        cod = self.in_plant_cod.text().strip()
        nom = self.in_plant_nom.text().strip()
        if not cod or not nom:
            _aviso(self, "Plantillas", "Indica código y nombre de la plantilla.", "warning")
            return
        lineas = []
        for r in range(self.tbl_plant_lineas.rowCount()):
            cta_item = self.tbl_plant_lineas.item(r, 0)
            cta = cta_item.text().strip() if cta_item else ""
            if not cta:
                continue

            def _num(c, _r=r):
                it = self.tbl_plant_lineas.item(_r, c)
                try:
                    return float((it.text() if it else "0").replace(",", ".") or 0)
                except ValueError:
                    return 0.0
            desc_item = self.tbl_plant_lineas.item(r, 3)
            lineas.append({"cuenta": cta, "debe": _num(1), "haber": _num(2),
                           "descripcion": desc_item.text().strip() if desc_item else ""})
        if not lineas:
            _aviso(self, "Plantillas", "Añade al menos una línea con cuenta.", "warning")
            return
        from src.services.contabilidad import plantillas as PL
        pid = PL.crear_plantilla(cod, nom, lineas, concepto=self.in_plant_conc.text().strip() or None)
        _aviso(self, "Plantillas", f"Plantilla «{cod}» guardada (#{pid})." if pid
              else "No se pudo guardar la plantilla.", "success" if pid else "error")
        self._load_plantillas()

    def _plant_sel(self):
        r = self.tbl_plant.currentRow()
        if r < 0 or r >= len(self._plant_cache):
            _aviso(self, "Plantillas", "Selecciona antes una plantilla en la tabla.", "warning")
            return None
        return self._plant_cache[r]

    def _generar_desde_plantilla(self):
        p = self._plant_sel()
        if not p:
            return
        fecha, ok = _pedir_texto(self, "Generar asiento", "Fecha (AAAA-MM-DD):",
                                 _dt.date.today().isoformat())
        if not ok or not fecha.strip():
            return
        from src.services.contabilidad import plantillas as PL
        res = PL.generar_desde_plantilla(p["id"], fecha.strip())
        _aviso(self, "Plantillas", f"Asiento generado (nº {res.get('numero')})." if res
              else "No se pudo generar el asiento (revisa que las líneas cuadren).",
              "success" if res else "error")

    def _programar_recurrente(self):
        p = self._plant_sel()
        if not p:
            return
        periodos = ["mensual", "bimensual", "trimestral", "semestral", "anual"]
        periodo, ok = _pedir_opcion(self, "Programar recurrente", "Periodicidad:", periodos)
        if not ok:
            return
        fecha, ok2 = _pedir_texto(self, "Programar recurrente", "Próxima fecha (AAAA-MM-DD):",
                                  _dt.date.today().isoformat())
        if not ok2 or not fecha.strip():
            return
        from src.services.contabilidad import plantillas as PL
        rid = PL.programar_recurrente(p["id"], periodicidad=periodo, proxima_fecha=fecha.strip())
        _aviso(self, "Plantillas", f"Recurrencia programada (#{rid}); se generará sola vía Scheduler."
              if rid else "No se pudo programar la recurrencia.", "success" if rid else "error")

    # ── Mapeo de cuentas (evento/clave → cuenta contable) ───────────────────────────────
    def _page_mapeo(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        # Sin setWordWrap, esta frase (una sola línea) pedía 2124px de ancho mínimo ella sola —
        # con diferencia el mayor responsable de que TODAS las pestañas de Contabilidad quedaran
        # cortadas por la derecha en cuanto se visitaba esta (bug real confirmado por el usuario;
        # se veía justo en el propio texto cortado, "...Plan Genera").
        _lbl_mapeo_desc = QLabel("Cuenta contable a la que se contabiliza cada concepto (ventas, IVA, "
                                 "formas de pago, compras, terceros…). Sin un valor propio para la "
                                 "empresa se usa el del Plan General Contable.")
        _lbl_mapeo_desc.setWordWrap(True)
        ly.addWidget(_lbl_mapeo_desc)
        fila = QHBoxLayout()
        ambitos = sorted({k.split(":")[0] for k in M.DEFAULTS})
        self.cmb_mapeo_amb = _combo([(a, a) for a in ambitos])
        self.cmb_mapeo_amb.setSizeAdjustPolicy(self.cmb_mapeo_amb.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_mapeo_amb.setMinimumContentsLength(12)
        self.in_mapeo_clave = _inp("Clave (opcional, p.ej. 'efectivo')")
        self.in_mapeo_cuenta = _inp("Código de cuenta (p.ej. 700)")
        fila.addWidget(QLabel("Ámbito:")); fila.addWidget(self.cmb_mapeo_amb)
        fila.addWidget(QLabel("Clave:")); fila.addWidget(self.in_mapeo_clave)
        fila.addWidget(QLabel("Cuenta:")); fila.addWidget(self.in_mapeo_cuenta)
        fila.addWidget(_btn("💾  Guardar", self._guardar_mapeo, primary=True))
        ly.addLayout(fila)
        self.tbl_mapeo = _tabla_c(["Ámbito", "Clave", "Cuenta efectiva"])
        ly.addWidget(self.tbl_mapeo, 1)
        ly.addWidget(_btn_cargando("🔄  Actualizar", self._load_mapeo))
        self._load_mapeo()
        return w

    def _load_mapeo(self):
        filas = []
        for k in sorted(M.DEFAULTS):
            amb, clave = k.split(":", 1) if ":" in k else (k, "")
            filas.append((amb, clave, M.cuenta(amb, clave)))
        self.tbl_mapeo.setRowCount(len(filas))
        for i, (amb, clave, cta) in enumerate(filas):
            for j, v in enumerate([amb, clave, cta]):
                self.tbl_mapeo.setItem(i, j, QTableWidgetItem("" if v is None else str(v)))

    def _guardar_mapeo(self):
        amb = self.cmb_mapeo_amb.currentData()
        clave = self.in_mapeo_clave.text().strip()
        cuenta = self.in_mapeo_cuenta.text().strip()
        if not amb or not cuenta:
            _aviso(self, "Mapeo de cuentas", "Indica el ámbito y el código de cuenta.", "warning")
            return
        ok = M.set_mapeo(amb, cuenta, clave)
        _aviso(self, "Mapeo de cuentas",
              f"Mapeo {amb}{(':' + clave) if clave else ''} → {cuenta} guardado."
              if ok else "No se pudo guardar el mapeo.", "success" if ok else "error")
        self._load_mapeo()

    def _datos_empresa(self):
        try:
            from src.db import empresa as _emp
            emp = (_emp.datos_corporativos().get("empresa")) or {}
            return {"nombre": emp.get("razon_social") or emp.get("nombre_empresa") or emp.get("nombre") or "",
                    "cif": emp.get("cif") or emp.get("nif") or "",
                    "dir": emp.get("direccion") or emp.get("domicilio") or emp.get("direccion_fiscal") or ""}
        except Exception:
            return {"nombre": "", "cif": "", "dir": ""}

    def _panel_fiscal(self, tipo, titulo, subtitulo, subtipos=None, mostrar_empresa=True,
                      fecha_picker=False, boton_cierre=False, boton_texto="📄  GENERAR DOCUMENTO"):
        """Panel embebido con los campos del documento fiscal + generación (reutiliza el motor de PDF del
        asistente existente, SIN mostrar la ventana emergente).

        `mostrar_empresa=False` (Libro de Ingresos/Gastos — la empresa activa ya se ve en toda la
        app, repetirla en cada pestaña fiscal no aportaba nada) oculta las filas Empresa/CIF/
        Domicilio fiscal del formulario SIN dejar de rellenarlas: `_generar_doc_fiscal` sigue
        leyéndolas igual (siguen poblando `emp_nombre/emp_cif/emp_dir` para el PDF).
        `fecha_picker=True` cambia desde/hasta de campo de texto a `_date_neon` (mismo selector de
        calendario que Ventas/pestaña "Gastos"), por defecto 1-enero del año en curso → hoy.
        `boton_cierre=True` usa `self._boton_cierre` (mismo botón rectangular de la pestaña
        Cierres) en vez del botón de ancho completo por defecto."""
        from PyQt6.QtWidgets import QFormLayout
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(12)
        t = QLabel(titulo); t.setStyleSheet(f"color:{_CIAN};font-size:17px;font-weight:900;")
        ly.addWidget(t)
        sub = QLabel(subtitulo); sub.setStyleSheet(f"color:{_DIM};"); sub.setWordWrap(True); ly.addWidget(sub)

        e = self._datos_empresa()
        form = QFormLayout(); form.setSpacing(10)

        def _lbl(txt):
            la = QLabel(txt); la.setStyleSheet(f"color:{_DIM};font-weight:700;"); return la

        in_nombre = _inp("Nombre / Razón social"); in_nombre.setText(e["nombre"])
        in_cif = _inp("CIF"); in_cif.setText(e["cif"])
        in_dir = _inp("Domicilio fiscal"); in_dir.setText(e["dir"])
        if fecha_picker:
            from PyQt6.QtCore import QDate
            from src.gui.ventas import _date_neon
            in_ini = _date_neon(QDate(QDate.currentDate().year(), 1, 1))
            in_fin = _date_neon(QDate.currentDate())
            in_ini.setMinimumWidth(140); in_fin.setMinimumWidth(140)
        else:
            in_ini = _inp("dd/mm/aaaa"); in_ini.setText("01/01/" + str(_dt.date.today().year))
            in_fin = _inp("dd/mm/aaaa"); in_fin.setText(_dt.date.today().strftime("%d/%m/%Y"))
        if mostrar_empresa:
            form.addRow(_lbl("Empresa:"), in_nombre)
            form.addRow(_lbl("CIF:"), in_cif)
            form.addRow(_lbl("Domicilio fiscal:"), in_dir)
        form.addRow(_lbl("Período · desde:"), in_ini)
        form.addRow(_lbl("Período · hasta:"), in_fin)
        cmb_sub = None
        if subtipos:
            cmb_sub = _combo([(s, s) for s in subtipos]); cmb_sub.setMinimumWidth(220)
            form.addRow(_lbl("Ámbito de auditoría:"), cmb_sub)
        ly.addLayout(form)

        panel = {"tipo": tipo, "nombre": in_nombre, "cif": in_cif, "dir": in_dir,
                 "ini": in_ini, "fin": in_fin, "sub": cmb_sub, "ruta": None}
        if boton_cierre:
            fila_btn = QHBoxLayout(); fila_btn.addStretch(1)
            fila_btn.addWidget(self._boton_cierre(boton_texto, lambda: self._generar_doc_fiscal(panel)))
            fila_btn.addStretch(1)
            ly.addLayout(fila_btn)
        else:
            ly.addWidget(_btn(boton_texto, lambda: self._generar_doc_fiscal(panel), primary=True))
        lbl_res = QLabel(""); lbl_res.setWordWrap(True); lbl_res.setVisible(False)
        lbl_res.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        panel["res"] = lbl_res; ly.addWidget(lbl_res)
        btn_open = _btn("📂  ABRIR PDF", lambda: self._abrir_pdf(panel), primary=True)
        btn_open.setVisible(False); panel["open"] = btn_open
        ly.addWidget(btn_open, alignment=Qt.AlignmentFlag.AlignLeft)
        ly.addStretch()
        return w

    @staticmethod
    def _texto_periodo(widget):
        """Lee un campo de período (QLineEdit de texto o `_date_neon` QDateEdit) como
        'dd/mm/aaaa' — formato que ya consumen `render_libro_ingresos`/`render_libro_gastos`/
        `render` de auditoría. Centraliza lo que `_gasto_fecha_str` ya hacía solo para la pestaña
        "Gastos", ahora también para los paneles fiscales con `fecha_picker=True`."""
        try:
            from PyQt6.QtWidgets import QDateEdit
            if isinstance(widget, QDateEdit):
                return widget.date().toString("dd/MM/yyyy")
        except Exception:
            pass
        return (widget.text() or "").strip()

    def _generar_doc_fiscal(self, panel):
        from src.db.empresa import empresa_actual_id
        datos = {"emp_nombre": panel["nombre"].text().strip(), "emp_cif": panel["cif"].text().strip(),
                 "emp_dir": panel["dir"].text().strip(), "periodo_ini": self._texto_periodo(panel["ini"]),
                 "periodo_fin": self._texto_periodo(panel["fin"]),
                 # Necesarios para que los renders de Libro Ingresos/Gastos/Auditoría consulten
                 # datos reales (antes solo se pasaba texto de formulario, nunca la empresa/año).
                 "id_empresa": empresa_actual_id(), "anio": self.anio}
        if panel["sub"] is not None:
            datos["subtipo"] = panel["sub"].currentText()
        try:
            # Reutiliza EXACTAMENTE la generación del asistente fiscal (no se duplica el PDF): se instancia
            # el wizard, se le inyectan los datos y se genera, SIN mostrarlo (los campos ya están en la pestaña).
            from src.gui.gestion_usuarios import _WizardDocumentoFiscal
            wiz = _WizardDocumentoFiscal(tipo_inicial=panel["tipo"], parent=self)
            wiz._tipo = panel["tipo"]
            wiz._datos.update(datos)
            wiz._generar_pdf()
            ruta = getattr(wiz, "_pdf_ruta", None)
            wiz.deleteLater()
        except Exception as ex:
            logger.error("generar doc fiscal (%s): %s", panel["tipo"], ex)
            _aviso(self, "Documentos fiscales", f"No se pudo generar el documento: {ex}", "error")
            return
        if ruta and os.path.exists(ruta):
            panel["ruta"] = ruta
            panel["res"].setText("✅  Documento generado correctamente."); panel["res"].setVisible(True)
            panel["open"].setVisible(True)
        else:
            _aviso(self, "Documentos fiscales", "No se pudo generar el documento.", "error")

    def _abrir_pdf(self, panel):
        ruta = panel.get("ruta")
        if not ruta:
            return
        try:
            from src.utils import plataforma
            plataforma.abrir_archivo(ruta)
        except Exception as ex:
            logger.error("abrir pdf fiscal: %s", ex)

    def _activar(self):
        if K.activar(id_empresa=None, anio=self.anio):
            _aviso(self, "Contabilidad", tr("contab.activada", default="Contabilidad activada."))
            self._load_plan()

    def _aviso_activar_contabilidad(self):
        _aviso(self, tr("contab.activar_titulo", default="Contabilidad no activada"),
              tr("contab.activar_msg",
                 default="Antes de poder usar este módulo, actívalo pulsando el botón "
                         "«ACTIVAR CONTABILIDAD» en la esquina superior derecha. Esto crea el plan de "
                         "cuentas y abre el ejercicio contable del año en curso."),
              nivel="warning")

    @staticmethod
    def _fill(tabla, filas, claves):
        tabla.setRowCount(0)
        for f in filas:
            r = tabla.rowCount(); tabla.insertRow(r)
            for c, k in enumerate(claves):
                tabla.setItem(r, c, QTableWidgetItem("" if f.get(k) is None else str(f.get(k))))

    # ── Plan de cuentas ──────────────────────────────────────────────────────
    def _page_plan(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        fila = QHBoxLayout()
        self.in_plan_buscar = _inp(tr("contab.buscar_cuenta", default="Buscar cuenta…"))
        fila.addWidget(self.in_plan_buscar, 1)
        fila.addWidget(_btn(tr("contab.buscar", default="🔍"), self._load_plan, primary=True))
        ly.addLayout(fila)
        self.tbl_plan = _tabla_c(["Código", "Nombre", "Grupo", "Tipo", "Naturaleza"])
        ly.addWidget(self.tbl_plan, 1)
        return w

    def _load_plan(self):
        self._asegurar_pagina(0)   # lazy loading: garantiza tbl_plan aunque se llame sin pasar por _ir()
        filas = K.listar_cuentas(texto=self.in_plan_buscar.text().strip() or None)
        self._fill(self.tbl_plan, filas, ("codigo", "nombre", "grupo", "tipo", "naturaleza"))

    # ── Diario ───────────────────────────────────────────────────────────────
    def _page_diario(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        fila = QHBoxLayout()
        fila.addWidget(QLabel(tr("contab.diario", default="Libro Diario")))
        fila.addStretch(1)
        fila.addWidget(_btn_cargando(tr("contab.refrescar", default="REFRESCAR"), self._load_diario))
        ly.addLayout(fila)
        self.tbl_diario = _tabla_c(["Nº", "Fecha", "Concepto", "Origen", "Debe", "Haber", "Estado"])
        ly.addWidget(self.tbl_diario, 1)
        return w

    def _load_diario(self):
        self._asegurar_pagina(1)
        filas = A.listar_diario(anio=self.anio)
        self._fill(self.tbl_diario, filas,
                   ("numero", "fecha", "concepto", "origen", "total_debe", "total_haber", "estado"))

    # ── Mayor ────────────────────────────────────────────────────────────────
    def _page_mayor(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        fila = QHBoxLayout()
        self.in_mayor_cta = _inp(tr("contab.cuenta", default="Cuenta (p.ej. 700)"))
        self.in_mayor_cta.setFixedWidth(180)
        fila.addWidget(self.in_mayor_cta)
        fila.addWidget(_btn(tr("contab.ver_mayor", default="VER MAYOR"), self._load_mayor, primary=True))
        self.lbl_mayor = QLabel(""); self.lbl_mayor.setStyleSheet(f"color:{_CIAN};")
        fila.addWidget(self.lbl_mayor); fila.addStretch(1)
        ly.addLayout(fila)
        self.tbl_mayor = _tabla_c(["Fecha", "Asiento", "Concepto", "Debe", "Haber", "Saldo"])
        ly.addWidget(self.tbl_mayor, 1)
        return w

    def _load_mayor(self):
        self._asegurar_pagina(2)
        cod = self.in_mayor_cta.text().strip()
        if not cod:
            return
        m = I.mayor(cod, anio=self.anio)
        self._fill(self.tbl_mayor, m["apuntes"], ("fecha", "numero", "descripcion", "debe", "haber", "saldo"))
        self.lbl_mayor.setText(f"{cod} · saldo {m['saldo']}")

    # ── Balances ─────────────────────────────────────────────────────────────
    def _page_balances(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        fila = QHBoxLayout()
        fila.addWidget(QLabel(tr("contab.sumas_saldos", default="Balance de sumas y saldos")))
        fila.addStretch(1)
        fila.addWidget(_btn_cargando(tr("contab.refrescar", default="REFRESCAR"), self._load_balances))
        ly.addLayout(fila)
        self.lbl_bal = QLabel(""); self.lbl_bal.setStyleSheet(f"color:{_CIAN};font-weight:bold;")
        ly.addWidget(self.lbl_bal)
        self.tbl_bal = _tabla_c(["Código", "Nombre", "Debe", "Haber", "Saldo"])
        ly.addWidget(self.tbl_bal, 1)
        return w

    def _load_balances(self):
        self._asegurar_pagina(3)
        b = I.balance_sumas_saldos(anio=self.anio)
        self._fill(self.tbl_bal, b["cuentas"], ("codigo", "nombre", "debe", "haber", "saldo"))
        bs = I.balance_situacion(anio=self.anio)
        pyg = I.perdidas_ganancias(anio=self.anio)
        self.lbl_bal.setText(
            f"Σ debe {b['total_debe']} = Σ haber {b['total_haber']} ({'cuadra' if b['cuadra'] else 'DESCUADRE'})  ·  "
            f"Activo {bs['activo']} = Pasivo {bs['pasivo']} + PN {bs['patrimonio_neto']}  ·  "
            f"Resultado {pyg['resultado']}")

    # ── Gastos (entrada directa de suministros/servicios/dietas…) ────────────────
    def _page_gastos(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        ly.addWidget(QLabel(tr("contab.gastos_titulo",
                               default="Registro de gastos (suministros, servicios, dietas…)")))
        # Fila 1: tipo · importe · forma de pago · IVA
        f1 = QHBoxLayout()
        self.cmb_gasto_tipo = _combo([(et, cod) for cod, et, _c, _iva in M.TIPOS_GASTO])
        self.cmb_gasto_tipo.setMinimumWidth(240)          # combo cerrado
        self.cmb_gasto_tipo.view().setMinimumWidth(300)   # popup: el global ::item gasta 40px pad+margen
        # Sin esto, el tipo de gasto más largo (política por defecto: ajustarse al contenido MÁS
        # ancho) hacía que el combo pidiera hasta 432px — con el resto de la fila, la pestaña
        # entera pedía más ancho del que hay en pantalla y Windows no podía concederle esa
        # geometría (bug real: "entrar en Gastos bloquea toda la app" — mismo mecanismo ya
        # resuelto en Contabilidad/RRHH/Cámaras/Mermas/Configuración).
        from PyQt6.QtWidgets import QComboBox as _QComboBox
        self.cmb_gasto_tipo.setSizeAdjustPolicy(_QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_gasto_tipo.setMinimumContentsLength(18)
        self._gasto_lleva_iva = {cod: iva for cod, _et, _c, iva in M.TIPOS_GASTO}
        self.in_gasto_importe = _inp(tr("contab.g_importe_ph", default="Importe total €"))
        self.in_gasto_importe.setFixedWidth(150)
        self.cmb_gasto_fp = _combo([("Banco / Tarjeta", "banco"), ("Efectivo", "efectivo"),
                                    ("A crédito", "credito")])
        self.cmb_gasto_fp.setMinimumWidth(150)
        self.cmb_gasto_fp.view().setMinimumWidth(190)
        self.cmb_gasto_iva = _combo([("IVA automático", "auto"), ("21%", "21"), ("10%", "10"),
                                     ("4%", "4"), ("Sin IVA", "no")])
        self.cmb_gasto_iva.setMinimumWidth(150)
        self.cmb_gasto_iva.view().setMinimumWidth(190)
        for et, wd in ((tr("contab.g_tipo", default="Tipo:"), self.cmb_gasto_tipo),
                       (tr("contab.g_importe", default="Importe:"), self.in_gasto_importe),
                       (tr("contab.g_pago", default="Pago:"), self.cmb_gasto_fp),
                       (tr("contab.g_iva", default="IVA:"), self.cmb_gasto_iva)):
            lb = QLabel(et); lb.setStyleSheet(f"color:{_DIM};"); f1.addWidget(lb); f1.addWidget(wd)
        f1.addStretch(1)
        ly.addLayout(f1)
        # Fila 2: concepto · fecha · botón registrar
        f2 = QHBoxLayout()
        self.in_gasto_concepto = _inp(tr("contab.g_concepto_ph", default="Concepto / proveedor (opcional)"))
        # Fecha: mismo selector de calendario neón que Ventas (Fecha Inicio/Fin). Fallback a texto.
        try:
            from PyQt6.QtCore import QDate
            from src.gui.ventas import _date_neon
            self.in_gasto_fecha = _date_neon(QDate.currentDate())
            self.in_gasto_fecha.setMinimumWidth(140)
        except Exception:
            self.in_gasto_fecha = _inp("YYYY-MM-DD"); self.in_gasto_fecha.setFixedWidth(130)
            self.in_gasto_fecha.setText(_dt.date.today().strftime("%Y-%m-%d"))
        lc = QLabel(tr("contab.g_concepto", default="Concepto:")); lc.setStyleSheet(f"color:{_DIM};")
        lf = QLabel(tr("contab.g_fecha", default="Fecha:")); lf.setStyleSheet(f"color:{_DIM};")
        f2.addWidget(lc); f2.addWidget(self.in_gasto_concepto, 1)
        f2.addWidget(lf); f2.addWidget(self.in_gasto_fecha)
        f2.addWidget(_btn(tr("contab.g_registrar", default="REGISTRAR GASTO"), self._registrar_gasto, primary=True))
        ly.addLayout(f2)
        self.cmb_gasto_tipo.currentIndexChanged.connect(self._gasto_tipo_cambiado)
        self.lbl_gasto = QLabel(""); self.lbl_gasto.setStyleSheet(f"color:{_CIAN};font-weight:bold;")
        ly.addWidget(self.lbl_gasto)
        self.tbl_gastos = _tabla_c(["Nº", "Fecha", "Concepto", "Importe", "Estado"])
        ly.addWidget(self.tbl_gastos, 1)
        acc = QHBoxLayout(); acc.addStretch(1)
        acc.addWidget(_btn(tr("contab.g_anular", default="ANULAR SELECCIONADO"), self._anular_gasto, danger=True))
        ly.addLayout(acc)
        self._gastos_cache = []

        # ── Gastos de viaje de empleados (petición explícita: madurar esta misma pestaña
        # "Gastos" para que TAMBIÉN registre/gestione los gastos de viaje por empleado — motor
        # reutilizado tal cual, `services.gastos_viaje.gastos`, ya usado por el autoservicio móvil;
        # ningún motor paralelo. Dato distinto del registro contable de arriba (ahí no hay
        # empleado/aprobación/ticket/OCR: es el asiento directo del contable) — conviven en la
        # misma pestaña, cada uno con su propia sección, sin mezclar sus tablas.
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{_DIM};background:{_DIM};")
        sep.setFixedHeight(1)
        ly.addWidget(sep)
        ly.addWidget(QLabel(tr("contab.gv_titulo", default="GASTOS DE VIAJE DE EMPLEADOS"),
                            styleSheet=f"color:{_CIAN};font-weight:900;margin-top:6px;"))

        fgv1 = QHBoxLayout()
        self.gv_empleado = _combo(self._opciones_empleados())
        self.gv_categoria = _combo([("Transporte", "transporte"), ("Alojamiento", "alojamiento"),
                                    ("Dietas", "dietas"), ("Otros", "otros")])
        self.gv_fecha = _inp("Fecha AAAA-MM-DD")
        self.gv_fecha.setText(_dt.date.today().strftime("%Y-%m-%d"))
        self.gv_importe = _inp("Importe €")
        for lbl, wd in ((tr("contab.gv_empleado", default="Empleado:"), self.gv_empleado),
                        (tr("contab.gv_categoria", default="Categoría:"), self.gv_categoria),
                        (tr("contab.gv_fecha", default="Fecha:"), self.gv_fecha),
                        (tr("contab.gv_importe", default="Importe:"), self.gv_importe)):
            fgv1.addWidget(QLabel(lbl, styleSheet=f"color:{_DIM};")); fgv1.addWidget(wd)
        ly.addLayout(fgv1)

        fgv2 = QHBoxLayout()
        self.gv_concepto = _inp(tr("contab.gv_concepto_ph", default="Concepto (p. ej. Taxi aeropuerto)"))
        self._gv_ticket_ruta = None
        self._gv_ocr_origen = False
        self.lbl_gv_ticket = QLabel(tr("contab.gv_sin_ticket", default="Sin ticket adjunto."),
                                    styleSheet=f"color:{_DIM};")
        fgv2.addWidget(self.gv_concepto, 1)
        fgv2.addWidget(_btn(tr("contab.gv_adjuntar_btn", default="📎 Adjuntar/Leer ticket (IA)"),
                           self._gv_elegir_ticket))
        ly.addLayout(fgv2)
        ly.addWidget(self.lbl_gv_ticket)

        fgv3 = QHBoxLayout(); fgv3.addStretch(1)
        fgv3.addWidget(_btn(tr("contab.gv_registrar_btn", default="REGISTRAR GASTO DE VIAJE"),
                           self._gv_registrar, primary=True))
        ly.addLayout(fgv3)

        fgv_filtro = QHBoxLayout()
        fgv_filtro.addWidget(QLabel(tr("contab.gv_estado", default="Estado:"), styleSheet=f"color:{_DIM};"))
        self.gv_filtro_estado = _combo(
            [("(Todos)", None), ("Pendiente", "pendiente"), ("Aprobado", "aprobado"),
             ("Rechazado", "rechazado"), ("Reembolsado", "reembolsado")], "pendiente")
        self.gv_filtro_estado.currentIndexChanged.connect(self._gv_cargar)
        fgv_filtro.addWidget(self.gv_filtro_estado)
        fgv_filtro.addWidget(_btn("🔄 " + tr("contab.gv_actualizar", default="Actualizar"), self._gv_cargar))
        fgv_filtro.addStretch(1)
        ly.addLayout(fgv_filtro)

        self.tbl_gv = _tabla_c(["ID", "Código", "Empleado", "Fecha", "Categoría", "Concepto",
                               "Importe", "OCR", "Estado"])
        self.tbl_gv.cellClicked.connect(self._gv_seleccionar)
        ly.addWidget(self.tbl_gv, 1)
        accgv = QHBoxLayout()
        self.gv_motivo_rechazo = _inp(tr("contab.gv_motivo_ph", default="Motivo del rechazo (si procede)"))
        accgv.addWidget(self.gv_motivo_rechazo, 1)
        accgv.addWidget(_btn(tr("contab.gv_aprobar_btn", default="Aprobar"), self._gv_aprobar, primary=True))
        accgv.addWidget(_btn(tr("contab.gv_rechazar_btn", default="Rechazar"), self._gv_rechazar, danger=True))
        ly.addLayout(accgv)
        self._gv_sel = None
        self._gv_cargar()
        return w

    # ── Gastos de viaje de empleados (sección dentro de la pestaña "Gastos") ──────────────────
    _GV_CATEGORIAS_LBL = {"transporte": "Transporte", "alojamiento": "Alojamiento",
                          "dietas": "Dietas", "otros": "Otros"}
    _GV_ESTADOS_LBL = {"pendiente": "Pendiente", "aprobado": "Aprobado",
                       "rechazado": "Rechazado", "reembolsado": "Reembolsado"}

    def _opciones_empleados(self):
        try:
            from src.rrhh.db import empleados as EMP_DB
            return [(f"{e.get('nombre', '')} {e.get('apellidos') or ''}".strip() or f"#{e['id']}", e["id"])
                   for e in EMP_DB.listar_empleados()]
        except Exception as e:
            logger.error("_opciones_empleados: %s", e)
            return []

    def _mapa_nombres_empleados(self):
        return dict(reversed(opt) for opt in self._opciones_empleados())

    def _gv_elegir_ticket(self):
        from PyQt6.QtWidgets import QFileDialog
        ruta, _f = QFileDialog.getOpenFileName(
            self, tr("contab.gv_elegir_ticket_t", default="Elegir foto/PDF del ticket"), "",
            "Imágenes y PDF (*.png *.jpg *.jpeg *.webp *.gif *.pdf)")
        if not ruta:
            return
        self._gv_ticket_ruta = ruta
        self.lbl_gv_ticket.setText(f"{os.path.basename(ruta)}  ({tr('contab.gv_extrayendo', default='extrayendo con IA…')})")
        try:
            from src.services.gastos_viaje import ticket_ocr
            r = ticket_ocr.extraer_ticket(ruta)
        except Exception as e:
            r = {"ok": False, "error": str(e)}
        if r.get("ok"):
            d = r["datos"]
            if d.get("importe") is not None:
                self.gv_importe.setText(str(d["importe"]))
            if d.get("fecha"):
                self.gv_fecha.setText(str(d["fecha"]))
            if d.get("concepto") or d.get("comercio"):
                self.gv_concepto.setText(str(d.get("concepto") or d.get("comercio")))
            if d.get("categoria_sugerida"):
                idx = self.gv_categoria.findData(d["categoria_sugerida"])
                if idx >= 0:
                    self.gv_categoria.setCurrentIndex(idx)
            self._gv_ocr_origen = True
            self.lbl_gv_ticket.setText(
                tr("contab.gv_ocr_ok", default="Ticket leído por IA — revisa los datos antes de registrar."))
        else:
            self._gv_ocr_origen = False
            self.lbl_gv_ticket.setText(
                tr("contab.gv_ocr_error", default="No se pudo leer automáticamente ({e}) — rellena a mano.",
                   e=r.get("error")))

    def _gv_registrar(self):
        from src.services.gastos_viaje.gastos import GastoViajeError
        from src.services.gastos_viaje import gastos as GV
        id_emp = self.gv_empleado.currentData()
        if not id_emp:
            _aviso(self, "Gastos de viaje", tr("contab.gv_sin_empleados",
                                               default="No hay empleados disponibles."), "warning")
            return
        try:
            r = GV.crear_gasto(id_emp, self.gv_fecha.text().strip() or None, self.gv_categoria.currentData(),
                               self.gv_importe.text().strip().replace(",", "."),
                               concepto=self.gv_concepto.text().strip(), ruta_ticket=self._gv_ticket_ruta,
                               ocr_origen=self._gv_ocr_origen)
        except GastoViajeError as e:
            _aviso(self, "Gastos de viaje", str(e), "warning"); return
        if not r.get("ok"):
            _aviso(self, "Gastos de viaje", tr("contab.gv_no_registrado",
                                               default="No se pudo registrar el gasto."), "warning")
            return
        _aviso(self, "Gastos de viaje", tr("contab.gv_registrado_ok", default="Gasto {c} registrado.",
                                          c=r["codigo"]))
        self._gv_ticket_ruta = None; self._gv_ocr_origen = False
        self.lbl_gv_ticket.setText(tr("contab.gv_sin_ticket", default="Sin ticket adjunto."))
        self.gv_importe.clear(); self.gv_concepto.clear()
        self._gv_cargar()

    def _gv_cargar(self, *_args):
        from src.services.gastos_viaje import gastos as GV
        estado = self.gv_filtro_estado.currentData()
        nombres = self._mapa_nombres_empleados()
        self._gv_lista = GV.listar_gastos(estado=estado)
        self.tbl_gv.setRowCount(len(self._gv_lista))
        for i, r in enumerate(self._gv_lista):
            vals = [r.get("id"), r.get("codigo"), nombres.get(r.get("id_empleado"), r.get("id_empleado")),
                    r.get("fecha_gasto"), self._GV_CATEGORIAS_LBL.get(r.get("categoria"), r.get("categoria")),
                    r.get("concepto"), r.get("importe"), "✔" if r.get("ocr_origen") else "—",
                    self._GV_ESTADOS_LBL.get(r.get("estado"), r.get("estado"))]
            for j, v in enumerate(vals):
                self.tbl_gv.setItem(i, j, QTableWidgetItem("" if v is None else str(v)))
        self._gv_sel = None

    def _gv_seleccionar(self, row, _c):
        try:
            self._gv_sel = self._gv_lista[row]
        except (IndexError, AttributeError):
            self._gv_sel = None

    def _gv_aprobar(self):
        from src.services.gastos_viaje import gastos as GV
        if not self._gv_sel:
            _aviso(self, "Gastos de viaje", tr("contab.gv_selecciona",
                                               default="Selecciona primero un gasto en la tabla."), "warning")
            return
        try:
            r = GV.aprobar(self._gv_sel["id"], usuario=self._usuario_nombre())
        except GV.GastoViajeError as e:
            _aviso(self, "Gastos de viaje", str(e), "warning"); return
        if r.get("ok"):
            _aviso(self, "Gastos de viaje", tr("contab.gv_aprobado_ok",
                                               default="Gasto aprobado — se incluirá en la próxima nómina del empleado."))
            self._gv_cargar()
        else:
            _aviso(self, "Gastos de viaje", tr("contab.gv_no_aprobado",
                                               default="No se pudo aprobar el gasto."), "warning")

    def _gv_rechazar(self):
        from src.services.gastos_viaje import gastos as GV
        if not self._gv_sel:
            _aviso(self, "Gastos de viaje", tr("contab.gv_selecciona",
                                               default="Selecciona primero un gasto en la tabla."), "warning")
            return
        try:
            r = GV.rechazar(self._gv_sel["id"], self.gv_motivo_rechazo.text().strip(),
                            usuario=self._usuario_nombre())
        except GV.GastoViajeError as e:
            _aviso(self, "Gastos de viaje", str(e), "warning"); return
        if r.get("ok"):
            _aviso(self, "Gastos de viaje", tr("contab.gv_rechazado_ok", default="Gasto rechazado."))
            self.gv_motivo_rechazo.clear()
            self._gv_cargar()
        else:
            _aviso(self, "Gastos de viaje", tr("contab.gv_no_rechazado",
                                               default="No se pudo rechazar el gasto."), "warning")

    def _usuario_nombre(self):
        u = self.usuario or {}
        return u.get("nombre") if isinstance(u, dict) else None

    def _gasto_fecha_str(self):
        """Fecha del formulario como 'YYYY-MM-DD', tanto si es calendario (QDateEdit) como texto."""
        w = self.in_gasto_fecha
        try:
            from PyQt6.QtWidgets import QDateEdit
            if isinstance(w, QDateEdit):
                return w.date().toString("yyyy-MM-dd")
        except Exception:
            pass
        return (w.text() or "").strip() or None

    def _gasto_tipo_cambiado(self):
        """Si el tipo de gasto es exento (seguros, comisiones bancarias) preselecciona 'Sin IVA'."""
        cod = self.cmb_gasto_tipo.currentData()
        lleva = self._gasto_lleva_iva.get(cod, True)
        self.cmb_gasto_iva.setCurrentIndex(0 if lleva else 4)   # 0=IVA automático · 4=Sin IVA

    def _registrar_gasto(self):
        tipo = self.cmb_gasto_tipo.currentData()
        try:
            total = float((self.in_gasto_importe.text() or "0").replace(",", ".").strip())
        except ValueError:
            total = 0.0
        if total <= 0:
            _aviso(self, "Gastos", tr("contab.g_importe_invalido", default="Introduce un importe válido."), "warning")
            return
        sel = self.cmb_gasto_iva.currentData()
        con_iva = sel != "no"
        tipo_iva = None if sel in ("auto", "no") else float(sel)
        fecha = self._gasto_fecha_str()
        concepto = (self.in_gasto_concepto.text() or "").strip() or None
        fp = self.cmb_gasto_fp.currentData()
        r = Pg.registrar_gasto(tipo, total, fecha=fecha, forma_pago=fp, concepto=concepto,
                               con_iva=con_iva, tipo_iva=tipo_iva)
        if r:
            self.lbl_gasto.setText(
                tr("contab.g_ok", default="Gasto registrado") + f": asiento nº {r.get('numero')} · {total:.2f} €")
            self.in_gasto_importe.clear(); self.in_gasto_concepto.clear()
            self._load_gastos(); self._load_diario()
        else:
            _aviso(self, "Gastos", tr("contab.g_error",
                                      default="No se pudo registrar (¿contabilidad activada?)."), "warning")

    def _anular_gasto(self):
        row = self.tbl_gastos.currentRow()
        if row < 0 or row >= len(self._gastos_cache):
            _aviso(self, "Gastos", tr("contab.g_selecc", default="Selecciona un gasto en la tabla."), "warning")
            return
        a = self._gastos_cache[row]
        if a.get("estado") != "contabilizado":
            _aviso(self, "Gastos", tr("contab.g_no_anulable",
                                      default="Solo se pueden anular gastos contabilizados."), "warning")
            return
        r = Pg.anular_gasto(a["id"])
        if r:
            self.lbl_gasto.setText(
                tr("contab.g_anulado", default="Gasto anulado (contraasiento nº") + f" {r.get('numero')}).")
            self._load_gastos(); self._load_diario()
        else:
            _aviso(self, "Gastos", tr("contab.g_no_anulado", default="No se pudo anular."), "warning")

    def _load_gastos(self):
        self._asegurar_pagina(4)
        self._gastos_cache = Pg.listar_gastos(anio=self.anio)
        self.tbl_gastos.setRowCount(0)
        for a in self._gastos_cache:
            r = self.tbl_gastos.rowCount(); self.tbl_gastos.insertRow(r)
            vals = [a.get("numero"), a.get("fecha"), a.get("concepto"), a.get("total_debe"), a.get("estado")]
            for c, v in enumerate(vals):
                self.tbl_gastos.setItem(r, c, QTableWidgetItem("" if v is None else str(v)))

    # ── Libros IVA ───────────────────────────────────────────────────────────
    def _page_iva(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        fila = QHBoxLayout()
        fila.addWidget(_btn(tr("contab.iva_rep", default="REPERCUTIDO"), lambda: self._load_iva("repercutido")))
        fila.addWidget(_btn(tr("contab.iva_sop", default="SOPORTADO"), lambda: self._load_iva("soportado")))
        fila.addWidget(_btn(tr("contab.m303", default="BORRADOR 303"), self._mostrar_303, primary=True))
        fila.addStretch(1)
        ly.addLayout(fila)
        self.lbl_iva = QLabel(""); self.lbl_iva.setStyleSheet(f"color:{_CIAN};font-weight:bold;")
        ly.addWidget(self.lbl_iva)
        self.tbl_iva = _tabla_c(["Fecha", "Asiento", "Ref", "Tipo IVA", "Base", "Cuota"])
        ly.addWidget(self.tbl_iva, 1)
        return w

    def _load_iva(self, tipo="repercutido"):
        self._asegurar_pagina(5)
        lib = IVA.libro_iva(tipo, anio=self.anio)
        self._fill(self.tbl_iva, lib["lineas"], ("fecha", "numero", "ref", "tipo_iva", "base", "cuota"))
        self.lbl_iva.setText(f"{tipo}: base {lib['total_base']} · cuota {lib['total_cuota']}")

    def _mostrar_303(self):
        r = IVA.resumen_303(anio=self.anio)
        _aviso(self, "Borrador modelo 303",
               f"Devengado: {r['iva_devengado_cuota']} · Deducible: {r['iva_deducible_cuota']}\n"
               f"Resultado: {r['resultado']} ({r['sentido']})")

    # ── Cierres ──────────────────────────────────────────────────────────────
    def _page_cierres(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(14)
        ly.addWidget(QLabel(tr("contab.cierres", default="Cierres y contabilización")))
        # Dos botones MEDIANOS con forma de rectángulo VERTICAL (esquinas redondeadas + hover swap),
        # centrados en el medio de la pestaña.
        ly.addStretch(2)
        fila = QHBoxLayout(); fila.setSpacing(30)
        fila.addStretch(1)
        fila.addWidget(self._boton_cierre(
            tr("contab.procesar", default="PROCESAR\nCONTABILIZACIÓN\nPENDIENTE"), self._procesar))
        fila.addWidget(self._boton_cierre(
            tr("contab.cerrar_ej", default="CERRAR\nEJERCICIO\nANUAL"), self._cerrar))
        fila.addWidget(self._boton_cierre(
            tr("contab.reabrir_ej", default="REABRIR\nEJERCICIO\nANUAL"), self._reabrir))
        fila.addWidget(self._boton_cierre(
            tr("contab.ver_bloqueados", default="EVENTOS\nBLOQUEADOS"), self._ver_bloqueados))
        fila.addStretch(1)
        ly.addLayout(fila)
        ly.addStretch(3)
        return w

    def _boton_cierre(self, texto, slot):
        """Botón rectangular vertical (mediano) con esquinas redondeadas y hover swap (relleno cian +
        texto oscuro al pasar el ratón), para la pestaña Cierres."""
        b = QPushButton(texto)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setFixedSize(250, 300)   # rectángulo VERTICAL (más alto que ancho)
        b.setStyleSheet(
            f"QPushButton{{background:{_BG};color:{_CIAN};border:2px solid {_CIAN};border-radius:22px;"
            f"font-family:'Segoe UI';font-weight:900;font-size:16px;letter-spacing:1px;padding:18px;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0B1118;}}"          # hover swap
            f"QPushButton:pressed{{background:{_CIAN};color:#0B1118;padding-top:20px;}}")
        b.clicked.connect(slot)
        return b

    def _procesar(self):
        res = Pg.procesar_cola()
        msg = tr("contab.posting_ok", default="Posting procesado") + f": {res['asientos']} asientos."
        if res.get("bloqueados"):
            msg += "\n" + tr(
                "contab.posting_bloqueados",
                default="{n} evento(s) con el ejercicio ya cerrado no se pudieron contabilizar — "
                        "ver «EVENTOS BLOQUEADOS».", n=res["bloqueados"])
        _aviso(self, "Contabilidad", msg)
        self._load_diario()

    def _ver_bloqueados(self):
        _BloqueadosDialog(self).exec()

    def _cerrar(self):
        from src.services.contabilidad import cierre as Ci

        # Validaciones PRE-cierre (nuevo): si hay bloqueantes (p.ej. un asiento descuadrado, o el
        # ejercicio anterior sin cerrar), se avisa claramente y NO se llega a invocar
        # `cerrar_ejercicio_formal` — evita cerrar un ejercicio sobre datos ya sabidos incorrectos.
        try:
            validacion = Ci.validar_cierre(self.anio)
        except Exception as ex:
            logger.error("validar_cierre: %s", ex)
            validacion = {"ok": True, "bloqueantes": [], "avisos": []}
        if not validacion.get("ok"):
            _aviso(self, "Contabilidad",
                   "No se puede cerrar el ejercicio — problemas bloqueantes:\n\n"
                   + "\n".join(f"• {b}" for b in validacion.get("bloqueantes") or []),
                   "error")
            return
        if validacion.get("avisos"):
            _aviso(self, "Contabilidad",
                   "Avisos (no bloquean el cierre, pero conviene revisarlos):\n\n"
                   + "\n".join(f"• {a}" for a in validacion["avisos"]),
                   "warning")

        usuario = (self.usuario or {}).get("nombre") if isinstance(self.usuario, dict) else None
        r = Ci.cerrar_ejercicio_formal(self.anio, usuario=usuario)
        if r.get("ok"):
            destino = r.get("destino")
            extra = f" Apertura {destino} generada." if r.get("apertura") else ""
            _aviso(self, "Contabilidad",
                   tr("contab.cerrado", default=f"Ejercicio {self.anio} cerrado (regularización + cierre).{extra}"),
                   "success")
            # UN solo documento del cierre (ver `services/contabilidad/cierre_anual_pdf.py`):
            # antes se generaban y registraban TRES PDFs separados (cierre/informe anual/cuentas
            # anuales) — decisión de producto: cerrar el ejercicio deja un único documento, con
            # todas las secciones fusionadas y sin cifras repetidas. Se genera y registra aquí
            # mismo, ANTES de abrir el diálogo del Informe Anual, para que lo que el usuario ve a
            # continuación coincida con un documento que YA está a salvo en disco/`documentos`.
            self._generar_documento_cierre_anual_unico(r)
            self._load_diario()
            # El cierre del ejercicio ahora INCLUYE el Informe Anual de Empresa — se abre
            # automáticamente justo después de cerrar, en vez de requerir un botón aparte (antes
            # "INFORME ANUAL {año}" en esta misma pestaña), para que cerrar el ejercicio muestre de
            # una vez toda la información del año (facturación, plantilla, inversión, P&G, etc.).
            self._abrir_informe_anual()
        elif r.get("motivo") == "ya_cerrado":
            _aviso(self, "Contabilidad", tr("contab.ya_cerrado", default="El ejercicio ya estaba cerrado."), "warning")
        else:
            _aviso(self, "Contabilidad", tr("contab.no_cerrado", default="No se pudo cerrar."), "warning")

    def _generar_documento_cierre_anual_unico(self, resultado):
        """Genera y registra el ÚNICO documento del cierre del ejercicio anual: resumen del cierre
        contable + operativa del ejercicio + estados financieros (Balance/ECPN/Estado de Flujos) +
        Memoria/Informe de Gestión/Propuesta de Aplicación del Resultado + comparación interanual,
        todo fusionado en un solo PDF (ver `services/contabilidad/cierre_anual_pdf.py` para el
        detalle de qué se fusiona/omite y por qué). Sustituye a las tres llamadas separadas que
        `_cerrar()` hacía antes (`_generar_pdf_cierre`/`_generar_pdf_informe_anual_auto`/
        `_generar_pdf_cuentas_anuales_auto`, ahora @deprecated — ver sus docstrings). Mismo patrón
        best-effort/no-fatal que esas: un fallo aquí nunca debe impedir que el cierre del ejercicio
        se dé por correcto (ya se marcó cerrado antes de llegar aquí); solo se registra el error.
        Tipo de documento registrado: "cierre_anual_completo" (NUEVO — ver `db/documentos.py`
        TIPOS y `gui/centro_documental.py` _TIPOS_CONTABILIDAD)."""
        try:
            from src.db.empresa import empresa_actual_id
            from src.services.contabilidad import cierre_anual_service
            from src.services.contabilidad.cierre_anual_pdf import generar_pdf_cierre_anual_unificado
            from src.services.contabilidad.informe_anual import generar_informe_anual
            emp = empresa_actual_id()
            datos_informe_anual = generar_informe_anual(self.anio, emp)
            datos_cuentas_anuales = cierre_anual_service.generar_cuentas_anuales_completas(
                self.anio, id_empresa=emp)
            ruta = generar_pdf_cierre_anual_unificado(
                self.anio, emp, resultado, datos_informe_anual, datos_cuentas_anuales,
                datos_empresa=self._datos_empresa())
            if ruta:
                from src.db import documentos
                documentos.registrar_documento(
                    ruta, tipo="cierre_anual_completo", nombre=os.path.basename(ruta),
                    referencia=f"CIERRE-ANUAL-{self.anio}", estado="generado", id_empresa=emp)
        except Exception as ex:
            logger.error("generar documento cierre anual unico: %s", ex)

    def _generar_pdf_cierre(self, resultado):
        """@deprecated: ya no se invoca desde `_cerrar()` (sustituida por
        `_generar_documento_cierre_anual_unico`, que genera UN único PDF unificado — ver
        `services/contabilidad/cierre_anual_pdf.py`). Se conserva sin cambios por si algo la
        sigue invocando directamente (p. ej. tests); no eliminar hasta confirmar cero referencias
        (CLAUDE.md: ciclo de deprecación — Strangler Pattern).

        Genera y registra el PDF del cierre (bug real corregido: antes no se generaba ningún
        documento al cerrar el ejercicio)."""
        try:
            from src.db.empresa import empresa_actual_id
            from src.services.contabilidad import cierre_pdf
            emp = empresa_actual_id()
            ruta = cierre_pdf.generar_pdf_cierre(self.anio, id_empresa=emp, resultado=resultado,
                                                 datos_empresa=self._datos_empresa())
            if ruta:
                from src.db import documentos
                documentos.registrar_documento(
                    ruta, tipo="cierre_ejercicio", nombre=os.path.basename(ruta),
                    referencia=f"CIERRE-{self.anio}", estado="generado", id_empresa=emp)
        except Exception as ex:
            logger.error("generar pdf cierre: %s", ex)

    def _generar_pdf_informe_anual_auto(self):
        """@deprecated: ya no se invoca desde `_cerrar()` (sustituida por
        `_generar_documento_cierre_anual_unico` — ver su docstring y la de `_generar_pdf_cierre`).
        Se conserva sin cambios por si algo la sigue invocando directamente; no eliminar hasta
        confirmar cero referencias.

        Genera y registra AUTOMÁTICAMENTE el PDF del Informe Anual de Empresa al cerrar el
        ejercicio (ver nota en `_cerrar`). Mismo patrón best-effort/no-fatal que
        `_generar_pdf_cierre`: un fallo aquí nunca debe impedir que el cierre del ejercicio se dé
        por correcto (ya se marcó cerrado antes de llegar aquí); solo se registra el error."""
        try:
            from src.db.empresa import empresa_actual_id
            from src.services.contabilidad.informe_anual import generar_informe_anual
            from src.services.contabilidad.informe_anual_pdf import generar_pdf_informe_anual
            emp = empresa_actual_id()
            datos = generar_informe_anual(self.anio, emp)
            ruta = generar_pdf_informe_anual(self.anio, emp, datos, datos_empresa=self._datos_empresa())
            if ruta:
                from src.db import documentos
                documentos.registrar_documento(
                    ruta, tipo="informe_anual", nombre=os.path.basename(ruta),
                    referencia=f"INFORME-ANUAL-{self.anio}", estado="generado", id_empresa=emp)
        except Exception as ex:
            logger.error("generar pdf informe anual (auto): %s", ex)

    def _generar_pdf_cuentas_anuales_auto(self):
        """@deprecated: ya no se invoca desde `_cerrar()` (sustituida por
        `_generar_documento_cierre_anual_unico` — ver su docstring y la de `_generar_pdf_cierre`).
        Se conserva sin cambios por si algo la sigue invocando directamente; no eliminar hasta
        confirmar cero referencias.

        Genera y registra AUTOMÁTICAMENTE el PDF de Cuentas Anuales (Balance/ECPN/Estado de
        Flujos + Memoria/Informe de Gestión/Propuesta de Aplicación del Resultado) al cerrar el
        ejercicio. Mismo patrón best-effort/no-fatal que `_generar_pdf_cierre`/
        `_generar_pdf_informe_anual_auto`: un fallo aquí nunca debe impedir que el cierre del
        ejercicio se dé por correcto (ya se marcó cerrado antes de llegar aquí); solo se registra
        el error. Documento DISTINTO del Informe Anual de Empresa (operativo) — ver orquestador
        `cierre_anual_service.generar_cuentas_anuales_completas` (pura composición, sin cálculo
        propio) y `cuentas_anuales_pdf.generar_pdf_cuentas_anuales`."""
        try:
            from src.db.empresa import empresa_actual_id
            from src.services.contabilidad import cierre_anual_service
            from src.services.contabilidad.cuentas_anuales_pdf import generar_pdf_cuentas_anuales
            emp = empresa_actual_id()
            datos = cierre_anual_service.generar_cuentas_anuales_completas(self.anio, id_empresa=emp)
            ruta = generar_pdf_cuentas_anuales(
                self.anio, emp, datos.get("memoria"), datos.get("informe_gestion"),
                datos.get("propuesta"), datos_empresa=self._datos_empresa(),
                balance=datos.get("balance"), ecpn=datos.get("ecpn"),
                estado_flujos=datos.get("estado_flujos"))
            if ruta:
                from src.db import documentos
                documentos.registrar_documento(
                    ruta, tipo="cuentas_anuales", nombre=os.path.basename(ruta),
                    referencia=f"CUENTAS-ANUALES-{self.anio}", estado="generado", id_empresa=emp)
        except Exception as ex:
            logger.error("generar pdf cuentas anuales (auto): %s", ex)

    def _reabrir(self):
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("finanzas.critica", self):
            return
        from src.services.contabilidad import cierre as Ci
        usuario = (self.usuario or {}).get("nombre") if isinstance(self.usuario, dict) else None
        r = Ci.reabrir_ejercicio_formal(self.anio, usuario=usuario)
        if r.get("ok"):
            _aviso(self, "Contabilidad",
                   tr("contab.reabierto", default=f"Ejercicio {self.anio} reabierto."), "success")
            self._load_diario()
        elif r.get("motivo") == "no_cerrado":
            _aviso(self, "Contabilidad",
                   tr("contab.no_estaba_cerrado", default="El ejercicio no estaba cerrado."), "warning")
        elif r.get("motivo") == "siguiente_cerrado":
            _aviso(self, "Contabilidad",
                   tr("contab.reabrir_siguiente_primero",
                      default="Primero debes reabrir el ejercicio siguiente."), "warning")
        else:
            _aviso(self, "Contabilidad", tr("contab.no_reabierto", default="No se pudo reabrir."), "warning")

    def _abrir_informe_anual(self):
        """Abre el Informe Anual de Empresa (diálogo Enterprise, `gui.informe_anual_gui`) para el
        ejercicio en curso de esta ventana — solo orquesta: toda la agregación/render vive en el
        propio módulo (servicio `informe_anual` + panel Enterprise). Se invoca automáticamente al
        cerrar el ejercicio (ver `_cerrar`); ya no tiene botón propio en esta pestaña.

        NO MODAL (`.show()`, no `.exec()`): tras cerrar el ejercicio el usuario puede querer seguir
        trabajando en Contabilidad mientras repasa el informe — un modal bloquearía la ventana entera
        sin necesidad (es puramente informativo, no pide ninguna decisión). Bug real encontrado:
        un `.exec()` aquí cuelga indefinidamente cualquier llamada no interactiva a `_cerrar()` (p.ej.
        `tests/integration/test_contab_gui.py::test_cierre_ejercicio_desde_gui`), ya que nadie puede
        cerrar el diálogo. Se guarda la referencia en `self._dlg_informe_anual` para que Qt no lo
        destruya nada más salir de esta función (si no, el diálogo no-modal desaparecería al instante
        por falta de referencias)."""
        try:
            from src.db.empresa import empresa_actual_id
            from src.gui.informe_anual_gui import InformeAnualDialog
            self._dlg_informe_anual = InformeAnualDialog(
                self.anio, id_empresa=empresa_actual_id(), usuario=self.usuario, parent=self)
            self._dlg_informe_anual.show()
        except Exception as ex:
            logger.error("abrir informe anual: %s", ex)
            _aviso(self, "Informe Anual", f"No se pudo abrir el Informe Anual: {ex}", "error")
