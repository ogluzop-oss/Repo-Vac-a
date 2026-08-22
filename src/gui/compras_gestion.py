"""
Ventana de COMPRAS (E2-GUI) — expone el motor de compras (proveedores, pedidos,
recepciones, facturas, informes) en la interfaz principal.

Reutiliza los patrones visuales de `catalogo_gestion` (sidebar `sw` + QStackedWidget
+ helpers `_btn/_inp/_tabla/_combo` + estilo global), sin crear una arquitectura ni
estilos paralelos. La lógica de negocio vive en `src.db.compras` y `src.db.proveedores`
(ya probada en E2.1-E2.7); esta capa es solo presentación + orquestación.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QDialog, QFormLayout,
                             QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton, QStackedWidget,
                             QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget)

from src.db import compras as C
from src.db import proveedores as P
from src.gui.catalogo_gestion import (_BG, _BG2, _BORDE, _CIAN, _DIM, _ROJO, _SIDEBAR, _TEXT, _btn,
                                      _btn_cargando, _btn_salir_sidebar, _combo, _dialogo_frameless,
                                      _inp, _tabla)
from src.utils.i18n import tr

logger = logging.getLogger("gui.compras")

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None

try:
    from assets.estilo_global import mostrar_confirmacion
except Exception:  # pragma: no cover
    mostrar_confirmacion = None


def _aviso(parent, titulo, msg, nivel="info"):
    if mostrar_mensaje is not None:
        mostrar_mensaje(parent, titulo, msg, nivel=nivel)
    else:  # pragma: no cover
        logger.info("%s: %s", titulo, msg)


def _confirmar(parent, titulo, msg) -> bool:
    """Confirmación modal (unificada). Sin diálogo → asume aceptar (entornos de test)."""
    if mostrar_confirmacion is not None:
        return bool(mostrar_confirmacion(parent, titulo, msg))
    return True


def _pix_ojo(relleno=False, size=30) -> QPixmap:
    """Icono de OJO EXACTAMENTE igual al del módulo Documentos (centro_documental): chip redondeado
    (fondo _BG2 + borde _BORDE) con elipse + pupila; hover = chip relleno cyan + icono oscuro. Mismo
    trazo (1.7, extremos redondeados) y mismos radios (elipse 8.5×5.2, pupila 2.1)."""
    from PyQt6.QtCore import QRectF, QPointF
    pm = QPixmap(size, size); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    col = QColor(_CIAN)
    chip = QRectF(1, 1, size - 2, size - 2)
    if relleno:                                   # hover swap: chip relleno + icono oscuro
        p.setPen(QPen(col, 1)); p.setBrush(col); p.drawRoundedRect(chip, 7, 7)
        icon_col = QColor(_BG)
    else:
        p.setPen(QPen(QColor(_BORDE), 1)); p.setBrush(QColor(_BG2)); p.drawRoundedRect(chip, 7, 7)
        icon_col = col
    pen = QPen(icon_col); pen.setWidthF(1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
    cx, cy = size / 2.0, size / 2.0
    p.drawEllipse(QPointF(cx, cy), 8.5, 5.2)
    p.setBrush(icon_col); p.drawEllipse(QPointF(cx, cy), 2.1, 2.1)
    p.end()
    return pm


class _BotonOjo(QPushButton):
    """Botón-icono de OJO con hover swap idéntico al de Documentos (chip → chip relleno) para Acciones."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(34, 30)
        self.setStyleSheet("QPushButton{background:transparent;border:none;padding:0;}")
        self._normal = _pix_ojo(relleno=False)
        self._hover = _pix_ojo(relleno=True)
        self.setIcon(QIcon(self._normal))
        self.setIconSize(self._normal.size())

    def enterEvent(self, e):   # noqa: N802 (API Qt)
        self.setIcon(QIcon(self._hover)); super().enterEvent(e)

    def leaveEvent(self, e):   # noqa: N802 (API Qt)
        self.setIcon(QIcon(self._normal)); super().leaveEvent(e)


def _scroll_neon(inner):
    """Envuelve un widget en un QScrollArea con la MISMA scrollbar cyan del resto de la app (sin marco
    propio; el contorno neón lo pone el `::pane` del QTabWidget contenedor)."""
    from PyQt6.QtWidgets import QScrollArea
    sa = QScrollArea(); sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    sa.setWidget(inner)
    sa.setStyleSheet(
        "QScrollArea{border:none;background:transparent;}"
        "QScrollArea>QWidget>QWidget{background:transparent;}"
        "QScrollBar:vertical{background:transparent;width:16px;margin:0;}"
        f"QScrollBar::handle:vertical{{background:{_CIAN};min-height:36px;border-radius:5px;margin:3px;}}"
        "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;width:0;}"
        "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}")
    return sa


class ComprasWindow(QWidget):

    @staticmethod
    def _bolsa_visible() -> bool:
        """Bolsa de proveedores + mercado (Lonja) + Portal proveedor: solo Supermarket/Retail. En las
        ediciones simples (Bakery/Pharmacy/Textil) el flujo de compras es directo (pedido al proveedor)."""
        try:
            from src.services import verticales
            return verticales.visible("compras.bolsa")
        except Exception:
            return True

    def _construir_secciones(self):
        """Secciones (sidebar + páginas + cargadores) según la edición. En ediciones simples se retira la
        pestaña Portal proveedor (no hay portal/mercado)."""
        secs = [
            ("prov", "🏭", "Proveedores", self._page_proveedores, self._load_proveedores),
            ("ped", "📦", "Pedidos", self._page_pedidos, self._load_pedidos),
            ("rec", "📥", "Recepciones", self._page_recepciones, self._load_recepciones),
            ("fac", "🧾", "Facturas", self._page_facturas, self._load_facturas),
            ("inf", "📊", "Informes", self._page_informes, self._cargar_informe),
            ("avz", "🤝", "Avanzado", self._page_avanzado, lambda: None),
            ("cal", "🔬", "Calidad", self._page_calidad, lambda: None),
        ]
        return secs

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self._prov_sel = None
        self._ped_prov_sel = None
        self._bolsa = self._bolsa_visible()
        self._secciones = self._construir_secciones()
        self.setWindowTitle("Smart Manager — " + tr("compras.titulo", default="COMPRAS"))

        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        right = QWidget(); rcol = QVBoxLayout(right)
        rcol.setContentsMargins(24, 18, 24, 18); rcol.setSpacing(14)
        rcol.addLayout(self._build_header())
        self.stack = QStackedWidget()
        self._loaders = []
        for _sid, _ic, _lbl, page_fn, loader_fn in self._secciones:
            self.stack.addWidget(page_fn())
            self._loaders.append(loader_fn)
        rcol.addWidget(self.stack, 1)
        root.addWidget(right, 1)

        self._ir(0)

        # P3 (UX-TPV-01): sidebar colapsable con persistencia por usuario.
        try:
            from src.gui.sidebar_colapsable import instalar_sidebar_colapsable
            if getattr(self, "sidebar", None) is not None:
                instalar_sidebar_colapsable(self, self.sidebar, usuario=self.usuario, clave="compras")
        except Exception:
            pass

    # ── Cabecera / sidebar ───────────────────────────────────────────────────
    def _build_header(self):
        cab = QHBoxLayout()
        t = QLabel("🛒  " + tr("compras.titulo", default="COMPRAS Y PROVEEDORES"))
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch(1)
        return cab

    def _build_sidebar(self):
        wrap = QFrame(); wrap.setObjectName("sw"); wrap.setFixedWidth(280); self.sidebar = wrap  # P3
        wrap.setStyleSheet(f"#sw{{background:{_SIDEBAR};}}")
        lay = QVBoxLayout(wrap); lay.setContentsMargins(0, 22, 0, 16); lay.setSpacing(2)
        cab = QLabel(tr("compras.secciones", default="PROVEEDORES"))
        cab.setStyleSheet("color:#FFFFFF;padding:0 0 24px 28px;font-size:16px;font-weight:900;"
                          "letter-spacing:2px;background:transparent;")
        lay.addWidget(cab)
        self._sb_btns = []
        for i, (sid, icono, defecto, _pf, _lf) in enumerate(self._secciones):
            b = QPushButton(f"   {tr('compras.sec_' + sid, default=defecto)}")   # sin icono
            b.setObjectName("btn_sidebar")   # estilo global (acento, hover swap, sin brillo)
            b.setProperty("lg", "true")      # +2pt (14px) vía QSS global
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setCheckable(True); b.setFixedHeight(55)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, idx=i: self._ir(idx))
            self._sb_btns.append(b); lay.addWidget(b)
        lay.addStretch(1)
        if self._volver:   # SALIR AL MENÚ (rojo) al fondo del sidebar
            lay.addWidget(_btn_salir_sidebar(self._volver_menu))
        return wrap

    _SS_OFF = (f"QPushButton{{background:transparent;color:#FFFFFF;text-align:left;"
               f"padding:8px 8px 8px 24px;border:none;border-left:4px solid transparent;"
               f"border-radius:0px;font-size:13px;font-weight:900;}}"
               f"QPushButton:hover{{background:#FFFFFF;color:{_SIDEBAR};}}")
    _SS_ON = (f"QPushButton{{background:#1A2230;color:{_CIAN};text-align:left;"
              f"padding:8px 8px 8px 24px;border:none;border-left:4px solid {_CIAN};"
              f"border-radius:0px;font-size:13px;font-weight:900;}}")

    def _ir(self, idx):
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self._sb_btns):
            b.setChecked(i == idx)   # estilo via QSS global #btn_sidebar:checked
        # Recarga perezosa de la sección (cargador asociado en self._secciones).
        self._loaders[idx]()

    def _volver_menu(self):
        if callable(self._volver):
            self._volver()

    def _page_avanzado(self):
        """Compras avanzado (homologación/devoluciones/incidencias/evaluación) embebido."""
        try:
            from src.gui.compras_avanzado_gui import ComprasAvanzadoWindow
            return ComprasAvanzadoWindow(callback_vuelta=None, usuario=self.usuario, main=self)
        except Exception as e:
            logger.error("embed Compras avanzado: %s", e)
            return QWidget()

    def _page_calidad(self):
        """Calidad (inspecciones/NC/CAPA/auditorías): dominio de calidad de suministro/recepción,
        reutilizando el Dashboard de Calidad existente sin duplicarlo."""
        try:
            from src.gui.calidad_dashboard import CalidadDashboardWindow
            return CalidadDashboardWindow(callback_vuelta=None, usuario=self.usuario, main=self)
        except Exception as e:
            logger.error("embed Calidad: %s", e)
            return QWidget()

    # ── Sección Proveedores ──────────────────────────────────────────────────
    def _page_proveedores(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10); ly.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        self.in_prov_buscar = _inp(tr("compras.buscar_prov", default="Buscar proveedor…"))
        fila.addWidget(self.in_prov_buscar, 1)
        fila.addWidget(_btn(tr("compras.buscar", default="BUSCAR"), self._load_proveedores, primary=True))
        ly.addLayout(fila)
        # Formulario inline.
        form = QHBoxLayout()
        self.in_prov_razon = _inp(tr("compras.razon", default="Razón social"))
        self.in_prov_cif = _inp("CIF/NIF"); self.in_prov_cif.setFixedWidth(140)
        self.in_prov_email = _inp("Email")
        self.in_prov_tel = _inp("Teléfono"); self.in_prov_tel.setFixedWidth(140)
        for x in (self.in_prov_razon, self.in_prov_cif, self.in_prov_email, self.in_prov_tel):
            form.addWidget(x)
        form.addWidget(_btn(tr("compras.nuevo", default="NUEVO"), self._nuevo_proveedor, primary=True))
        form.addWidget(_btn(tr("compras.guardar", default="GUARDAR"), self._guardar_proveedor, primary=True))
        form.addWidget(_btn(tr("compras.eliminar", default="ELIMINAR"), self._eliminar_proveedor, danger=True))
        # La importación de tarifas de proveedor se realiza desde el PORTAL DE PROVEEDOR (cada
        # proveedor sube su propia lista de precios), no manualmente desde esta pantalla.
        ly.addLayout(form)
        self.tbl_prov = _tabla(["ID", tr("compras.razon", default="Razón social"), "CIF/NIF",
                                "Email", "Teléfono", tr("compras.estado", default="Estado"),
                                tr("compras.acciones", default="Acciones")])
        self.tbl_prov.cellClicked.connect(self._sel_proveedor)
        # Anchos equilibrados: columnas de tamaño similar y Email un poco más ancha (rellena el resto).
        hh = self.tbl_prov.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed); self.tbl_prov.setColumnWidth(0, 60)   # ID
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed); self.tbl_prov.setColumnWidth(6, 80)   # Acciones
        for c in (1, 2, 4, 5):   # Razón social · CIF/NIF · Teléfono · Estado (todas iguales)
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive); self.tbl_prov.setColumnWidth(c, 160)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)   # Email: un poco más ancha (rellena)
        ly.addWidget(self.tbl_prov, 1)
        return w

    def _load_proveedores(self):
        texto = self.in_prov_buscar.text().strip() or None
        filas = P.listar_proveedores(texto=texto)
        self._fill(self.tbl_prov, filas, ("id_proveedor", "razon_social", "cif_nif",
                                          "email", "telefono", "estado"))
        # Columna "Acciones": icono de OJO (Ficha del proveedor) por fila, cyan con hover swap.
        for r in range(self.tbl_prov.rowCount()):
            b = _BotonOjo()
            b.setToolTip(tr("compras.ficha_prov", default="Ficha del proveedor"))
            b.clicked.connect(lambda _=False, row=r: self._abrir_ficha_proveedor(row))
            # Fondo opaco del contenedor: tapa el hover de celda global (::item:hover) para que la
            # columna Acciones NO reaccione al pasar el ratón; sólo el botón del lápiz hace hover swap.
            # WA_StyledBackground es obligatorio: un QWidget plano ignora el 'background' de la hoja
            # de estilos si no se activa, por lo que sin esto el tinte turquesa se seguía viendo.
            cont = QWidget(); cont.setObjectName("celda_acciones")
            cont.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            cont.setStyleSheet(f"#celda_acciones{{background:{_BG};}}")
            lay = QHBoxLayout(cont); lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignCenter)
            self.tbl_prov.setCellWidget(r, 6, cont)

    def _abrir_ficha_proveedor(self, row):
        """Abre la 'Ficha del proveedor' de la fila (gran formato, por pestañas). Al cerrar, refresca la
        tabla porque los cambios se propagan a toda la app (misma BD)."""
        it = self.tbl_prov.item(row, 0)
        if not it:
            return
        try:
            pid = int(it.text())
        except ValueError:
            return
        dlg = FichaProveedorDialog(pid, self, id_empresa=self._emp_actual())
        dlg.exec()
        self._load_proveedores()

    def _nuevo_proveedor(self):
        self._prov_sel = None
        for x in (self.in_prov_razon, self.in_prov_cif, self.in_prov_email, self.in_prov_tel):
            x.clear()
        self.in_prov_razon.setFocus()

    def _sel_proveedor(self, row, _col):
        try:
            self._prov_sel = int(self.tbl_prov.item(row, 0).text())
            self.in_prov_razon.setText(self.tbl_prov.item(row, 1).text())
            self.in_prov_cif.setText(self.tbl_prov.item(row, 2).text())
            self.in_prov_email.setText(self.tbl_prov.item(row, 3).text())
            self.in_prov_tel.setText(self.tbl_prov.item(row, 4).text())
        except Exception:
            self._prov_sel = None

    def _eliminar_proveedor(self):
        """Elimina el proveedor seleccionado del registro (con confirmación y mensaje de éxito/error)."""
        if not self._prov_sel:
            _aviso(self, tr("compras.proveedores", default="Proveedores"),
                   tr("compras.sel_prov_eliminar",
                      default="Selecciona un proveedor de la tabla para eliminarlo."), "info")
            return
        razon = self.in_prov_razon.text().strip() or f"#{self._prov_sel}"
        if not _confirmar(self, tr("compras.eliminar_prov", default="Eliminar proveedor"),
                          tr("compras.eliminar_prov_conf",
                             default=f"¿Eliminar definitivamente el proveedor «{razon}» del registro?")):
            return
        try:
            ok = P.eliminar_proveedor(self._prov_sel)
        except Exception as e:
            logger.error("eliminar_proveedor: %s", e)
            _aviso(self, tr("compras.proveedores", default="Proveedores"),
                   f"No se pudo eliminar: {e}", "error")
            return
        if ok:
            self._prov_sel = None
            for x in (self.in_prov_razon, self.in_prov_cif, self.in_prov_email, self.in_prov_tel):
                x.clear()
            self._load_proveedores()
            _aviso(self, tr("compras.proveedores", default="Proveedores"),
                   tr("compras.prov_eliminado", default=f"Proveedor «{razon}» eliminado."), "success")
        else:
            _aviso(self, tr("compras.proveedores", default="Proveedores"),
                   tr("compras.prov_no_eliminado",
                      default="No se pudo eliminar (¿tiene pedidos/movimientos asociados?)."), "error")

    def _guardar_proveedor(self):
        razon = self.in_prov_razon.text().strip()
        if not razon:
            _aviso(self, tr("compras.titulo", default="Compras"),
                   tr("compras.falta_razon", default="La razón social es obligatoria."), "error")
            return False
        datos = dict(cif_nif=self.in_prov_cif.text().strip() or None,
                     email=self.in_prov_email.text().strip() or None,
                     telefono=self.in_prov_tel.text().strip() or None)
        if self._prov_sel:
            ok = P.actualizar_proveedor(self._prov_sel, razon_social=razon, **datos)
        else:
            ok = bool(P.crear_proveedor(razon, **datos))
        self._load_proveedores()
        return ok

    # ── Sección Pedidos ──────────────────────────────────────────────────────
    def _page_pedidos(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10); ly.setContentsMargins(0, 0, 0, 0)
        self._carrito = []   # artículos en cola (carrito de compra, en memoria)
        fila = QHBoxLayout()
        fila.addWidget(_btn(tr("compras.nuevo_pedido", default="NUEVO PEDIDO"), self._dlg_nuevo_pedido, primary=True))
        fila.addWidget(_btn(tr("compras.desde_reab", default="DESDE REPOSICIÓN"), self._desde_reab, primary=True))
        fila.addStretch(1)
        fila.addWidget(_btn_cargando(tr("compras.actualizar", default="🔄  ACTUALIZAR"), self._load_pedidos))
        ly.addLayout(fila)

        # En ediciones simples (Bakery/Pharmacy/Textil): flujo directo (pedido bajo encargo al proveedor),
        # SIN bolsa/mercado, sin filtros de precio, sin cola de subastas.
        if not self._bolsa:
            return self._page_pedidos_simple(w, ly)

        # ── BOLSA DE PROVEEDORES: comparar el precio de un artículo entre proveedores ──
        lbl_b = QLabel("🔎  " + tr("compras.bolsa_titulo",
                                    default="Bolsa de proveedores · precio del artículo por proveedor"))
        lbl_b.setStyleSheet(f"color:{_CIAN};font-weight:800;font-size:14px;padding-top:2px;")
        ly.addWidget(lbl_b)
        bfila = QHBoxLayout()
        self.in_bolsa_art = _inp(tr("compras.bolsa_articulo", default="Código de artículo…"))
        bfila.addWidget(self.in_bolsa_art, 1)
        try:
            _provs = P.listar_proveedores(estado="activo")
        except Exception:
            _provs = []
        self.cmb_bolsa_prov = _combo(
            [(tr("compras.bolsa_todos", default="Todos los proveedores"), None)]
            + [(p.get("razon_social"), p.get("id_proveedor")) for p in _provs])
        bfila.addWidget(self.cmb_bolsa_prov)
        self.cmb_bolsa_orden = _combo([
            (tr("compras.bolsa_precio_asc", default="Precio ↑ (más barato)"), ("precio", False)),
            (tr("compras.bolsa_precio_desc", default="Precio ↓ (más caro)"), ("precio", True)),
            (tr("compras.bolsa_por_prov", default="Por proveedor"), ("proveedor", False))])
        self.cmb_bolsa_orden.setMinimumWidth(200)   # que no se corte el texto del desplegable
        bfila.addWidget(self.cmb_bolsa_orden)
        bfila.addWidget(_btn(tr("compras.bolsa_buscar", default="BUSCAR"), self._buscar_bolsa, primary=True))
        ly.addLayout(bfila)
        # Acciones sobre la tabla: JUSTO ENCIMA de la bolsa (bajo el buscador).
        mbar = QHBoxLayout()
        self.btn_watchlist = _btn("👁  " + tr("compras.watchlist", default="AÑADIR A WATCHLIST"),
                                  self._add_watchlist, primary=True)
        mbar.addWidget(self.btn_watchlist)
        # Indicador de artículo crítico/estratégico (en watchlist): evaluación preventiva activa.
        self.lbl_watchlist = QLabel("")
        self.lbl_watchlist.setStyleSheet(f"color:{_CIAN};background:transparent;font-weight:800;"
                                         "font-size:12px;padding-left:8px;")
        mbar.addWidget(self.lbl_watchlist)
        mbar.addStretch(1)
        ly.addLayout(mbar)
        # Tabla de la BOLSA (SOLO proveedores locales, tabla proveedor_precios_negociados). Columnas finales:
        # Proveedor · Precio (tarifa pactada) · Precio ref. · Desvío % · PVP Sugerido · Unidad · Acción.
        self.tbl_bolsa = _tabla([tr("compras.proveedor", default="Proveedor"),
                                 tr("compras.precio_eur", default="Precio (€)"),
                                 tr("compras.precio_ref", default="Precio ref. (€)"),
                                 tr("compras.desvio_col", default="Desvío %"),
                                 tr("compras.pvp_sugerido_col", default="PVP Sugerido (€)"),
                                 tr("compras.unidad", default="Unidad"),
                                 tr("compras.accion", default="Acción")])
        hh = self.tbl_bolsa.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed); self.tbl_bolsa.setColumnWidth(6, 90)
        # Doble clic en una fila → añade esa tarifa a la cola (equivale al botón Acción).
        self.tbl_bolsa.cellDoubleClicked.connect(self._bolsa_doble_clic)
        ly.addWidget(self.tbl_bolsa, 1)

        # ── Carrito: ARTÍCULOS EN COLA (se agrupan por proveedor al tramitar) ──
        colabar = QHBoxLayout()
        lbl_p = QLabel("🛒  " + tr("compras.cola_titulo", default="Artículos en cola"))
        lbl_p.setStyleSheet(f"color:{_CIAN};font-weight:800;font-size:14px;padding-top:2px;")
        colabar.addWidget(lbl_p); colabar.addStretch(1)
        # TRAMITAR TODOS junto a CANCELAR, sobre la cola: crea/envía los pedidos de toda la cola.
        colabar.addWidget(_btn(tr("compras.tramitar_todos", default="TRAMITAR TODOS"),
                               self._tramitar_todos, primary=True))
        # CANCELAR justo ENCIMA de la lista: cancela los artículos MARCADOS (casillas de la derecha).
        colabar.addWidget(_btn(tr("compras.cancelar", default="CANCELAR"), self._cancelar_seleccionados,
                               danger=True))
        ly.addLayout(colabar)
        self.tbl_carrito = _tabla([tr("compras.articulo", default="Artículo"),
                                   tr("compras.precio", default="Precio"),
                                   tr("compras.cantidad", default="Cantidad"),
                                   tr("compras.precio_total", default="Precio total"),
                                   tr("compras.sel", default="✓")])
        # Doble clic en un artículo de la cola → editar cantidad (con confirmación).
        self.tbl_carrito.cellDoubleClicked.connect(self._carrito_doble_clic)
        ly.addWidget(self.tbl_carrito, 1)
        return w

    def _page_pedidos_simple(self, w, ly):
        """Pedidos en ediciones simples: selecciona un proveedor REGISTRADO y pídele bajo encargo.
        Sin bolsa/mercado ni cola de subastas (esa cola solo tiene sentido con el mercado/Lonja)."""
        lbl = QLabel("🏭  " + tr("compras.prov_sel_titulo",
                                  default="Proveedores registrados · selecciona uno y pulsa NUEVO PEDIDO"))
        lbl.setStyleSheet(f"color:{_CIAN};font-weight:800;font-size:14px;padding-top:2px;")
        ly.addWidget(lbl)
        bfila = QHBoxLayout()
        self.in_ped_buscar = _inp(tr("compras.buscar_prov", default="Buscar proveedor…"))
        bfila.addWidget(self.in_ped_buscar, 1)
        bfila.addWidget(_btn(tr("compras.buscar", default="BUSCAR"), self._load_pedidos, primary=True))
        ly.addLayout(bfila)
        self.tbl_ped_prov = _tabla(["ID", tr("compras.razon", default="Razón social"), "CIF/NIF",
                                    "Email", "Teléfono", tr("compras.estado", default="Estado")])
        self.tbl_ped_prov.cellClicked.connect(self._sel_ped_prov)
        ly.addWidget(self.tbl_ped_prov, 1)
        return w

    def _sel_ped_prov(self, row, _col):
        try:
            self._ped_prov_sel = int(self.tbl_ped_prov.item(row, 0).text())
        except Exception:
            self._ped_prov_sel = None

    # ── Bolsa de proveedores (tarifas fijas locales) ──────────────────────────
    def _emp_actual(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _buscar_bolsa(self):
        """Bolsa de proveedores: SOLO tarifas pactadas locales (`proveedor_precios_negociados`). Muestra por
        proveedor el Precio pactado, el Precio ref. del artículo, el % de desvío, el PVP sugerido (coste ×
        margen) y la unidad, con ALERTA PREVENTIVA (rojo ▲ si el precio supera la referencia, verde ▼ si es
        igual o menor) ANTES de añadir a la cola."""
        cod = (self.in_bolsa_art.text() or "").strip().upper()
        self.tbl_bolsa.setRowCount(0)
        self._bolsa_rows = []
        if not cod:
            return
        self._bolsa_cod = cod
        idp_sel = self.cmb_bolsa_prov.currentData()
        orden, desc = self.cmb_bolsa_orden.currentData() or ("precio", False)
        filas = []
        try:
            from src.services.compras import proveedores_pro as PP
            for t in PP.bolsa_precios(cod, id_proveedor=idp_sel,
                                      orden=("proveedor" if orden == "proveedor" else "precio"),
                                      id_empresa=self._emp_actual()):
                precio = float(t.get("precio_neto") if t.get("precio_neto") is not None
                               else (t.get("precio") or 0))
                filas.append({"origen": "tarifa", "proveedor": t.get("proveedor"), "precio": precio,
                              "unidad": t.get("unidad_medida"), "id_proveedor": t.get("id_proveedor"),
                              "codigo": cod})
        except Exception as e:
            logger.error("bolsa_precios: %s", e)
        # Precio ref. del artículo = último coste de compra (histórico ERP).
        self._ref_mercado = self._precio_ref_mercado(cod)
        if orden == "proveedor":
            filas.sort(key=lambda f: (f.get("proveedor") or ""))
        else:
            filas.sort(key=lambda f: (f.get("precio") if f.get("precio") is not None else 1e18),
                       reverse=bool(desc))
        self._bolsa_rows = filas
        ref = self._ref_mercado
        try:
            from src.services.compras import precios_dinamicos as PD
            _umbral, margen = PD._reglas(self._emp_actual())
            en_wl = PD.en_watchlist(cod, id_empresa=self._emp_actual())
        except Exception:
            PD = None; margen = 30.0; en_wl = False
        verde, rojo = QColor("#3FB950"), QColor("#F85149")
        for r in filas:
            row = self.tbl_bolsa.rowCount(); self.tbl_bolsa.insertRow(row)
            precio = float(r.get("precio") or 0)
            pref = f"{ref:.2f}" if ref is not None else "—"
            # ALERTA PREVENTIVA: rojo ▲ si el precio supera la referencia; verde ▼ si es igual o menor.
            caro = (ref is not None and precio > ref)
            flecha = "▲ " if caro else "▼ "
            color = rojo if caro else verde
            pvp = f"{PD.pvp_sugerido(precio, margen):.2f}" if PD else f"{precio * (1 + margen / 100):.2f}"
            desv_txt = f"{(precio - ref) / ref * 100.0:+.1f}%" if ref not in (None, 0) else "—"
            # Columnas: Proveedor · Precio (€) · Precio ref. (€) · Desvío % · PVP Sugerido (€) · Unidad
            vals = [r.get("proveedor"), f"{flecha}{precio:.2f}", pref, desv_txt, pvp, r.get("unidad")]
            for c, v in enumerate(vals):
                it = QTableWidgetItem("" if v is None else str(v))
                if c in (1, 3):                     # Precio y Desvío %: color de alerta preventiva
                    it.setForeground(color)
                    if en_wl:                       # artículo crítico (watchlist): alerta DESTACADA (negrita)
                        f = it.font(); f.setBold(True); it.setFont(f)
                self.tbl_bolsa.setItem(row, c, it)
            # Columna Acción: botón para añadir esta fila a la cola.
            b = _btn("＋", lambda _=False, rr=row: self._accion_bolsa(rr), primary=True)
            b.setFixedWidth(70); b.setToolTip(tr("compras.add_cola", default="Añadir a la cola"))
            cont = QWidget(); lay = QHBoxLayout(cont); lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignCenter)
            self.tbl_bolsa.setCellWidget(row, 6, cont)
        self._refrescar_watchlist_btn()   # refleja el estado crítico/watchlist del artículo buscado
        if not filas:
            _aviso(self, tr("compras.bolsa_titulo", default="Bolsa"),
                   tr("compras.bolsa_vacia3",
                      default="No hay tarifas de proveedor registradas para ese artículo."), "info")
            return
        # Motor de precios dinámicos: sugerencia de PVP si la variación de coste es significativa.
        if PD is not None:
            try:
                coste = PD.coste_mas_bajo(filas)
                self._sugerencia_pvp(PD.sugerencia_precio_venta(cod, coste, id_empresa=self._emp_actual()))
            except Exception as e:
                logger.debug("sugerencia PVP: %s", e)

    def _precio_ref_mercado(self, codigo):
        """Precio ref. del artículo: valor manual si lo hay, si no media ponderada 30 días, si no precio
        de alta (resuelto por `precios_dinamicos.precio_referencia`)."""
        try:
            from src.services.compras import precios_dinamicos as PD
            return PD.precio_referencia(codigo, id_empresa=self._emp_actual())
        except Exception:
            return None

    def _sugerencia_pvp(self, sug):
        """Muestra la sugerencia de PVP del motor de precios dinámicos cuando el coste se desvía."""
        if not sug or not sug.get("significativo") or not sug.get("coste"):
            return
        var = sug.get("variacion_pct")
        tendencia = ("bajada" if sug.get("desvio") == "oportunidad" else "subida")
        _aviso(self, tr("compras.pvp_sugerido", default="Precio dinámico"),
               tr("compras.pvp_msg",
                  default="Coste más bajo {c:.2f}€ ({t} {v}% vs. ref.). PVP sugerido: {p:.2f}€ "
                          "(margen {m:.0f}%). Considera actualizar el precio de venta.",
                  c=float(sug["coste"]), t=tendencia,
                  v=(abs(var) if var is not None else 0), p=float(sug["pvp_sugerido"]),
                  m=float(sug["margen_pct"])),
               "warning" if sug.get("desvio") == "alerta" else "success")

    def _nombre_articulo(self, codigo):
        """Nombre del artículo por su código (para el toast). Degrada al propio código si no se encuentra."""
        try:
            from src.db import articulos as A
            r = A.buscar_uno(codigo, id_empresa=self._emp_actual())
            if r and r[1]:
                return r[1]
        except Exception:
            pass
        return codigo

    def _add_watchlist(self):
        """Alterna el artículo buscado en la WATCHLIST (seguimiento crítico/estratégico, migr 0209):
        si no está, lo añade; si ya está, lo quita. Toast inmediato con el nombre del artículo."""
        cod = getattr(self, "_bolsa_cod", None)
        if not cod:
            _aviso(self, "Watchlist", tr("compras.wl_busca",
                                         default="Busca un artículo antes de añadirlo a la watchlist."),
                   "warning")
            return
        from src.services.compras import precios_dinamicos as PD
        emp = self._emp_actual()
        nombre = self._nombre_articulo(cod)
        if PD.en_watchlist(cod, id_empresa=emp):
            ok = PD.quitar_watchlist(cod, id_empresa=emp)
            _aviso(self, "Watchlist",
                   tr("compras.wl_quitado", default="👁️ {n} quitado de la Watchlist.", n=nombre)
                   if ok else tr("compras.wl_err", default="No se pudo actualizar la watchlist."),
                   "success" if ok else "error")
        else:
            ok = PD.añadir_watchlist(cod, id_empresa=emp)
            _aviso(self, "Watchlist",
                   tr("compras.wl_ok2", default="👁️ {n} añadido a la Watchlist.", n=nombre)
                   if ok else tr("compras.wl_err", default="No se pudo actualizar la watchlist."),
                   "success" if ok else "error")
        self._refrescar_watchlist_btn()

    def _refrescar_watchlist_btn(self):
        """Refleja en el botón/indicador si el artículo buscado está en la watchlist (estado crítico)."""
        if not hasattr(self, "btn_watchlist"):
            return
        cod = getattr(self, "_bolsa_cod", None)
        dentro = False
        if cod:
            try:
                from src.services.compras import precios_dinamicos as PD
                dentro = PD.en_watchlist(cod, id_empresa=self._emp_actual())
            except Exception:
                dentro = False
        if dentro:
            self.btn_watchlist.setText("👁  " + tr("compras.watchlist_quitar", default="QUITAR DE WATCHLIST"))
            # Acento sutil (danger tenue): distingue el estado "ya en seguimiento" sin romper el tema.
            self.btn_watchlist.setStyleSheet(
                f"QPushButton{{background:{_BG2};color:{_ROJO};border:2px solid {_ROJO};border-radius:8px;"
                f"font-weight:900;font-size:12px;padding:0 14px;}}"
                f"QPushButton:hover{{background:{_ROJO};color:{_BG};border-color:{_ROJO};}}")
            self.lbl_watchlist.setText(tr("compras.wl_critico",
                                          default="⭐ En Watchlist · seguimiento crítico (evaluación preventiva)"))
        else:
            self.btn_watchlist.setText("👁  " + tr("compras.watchlist", default="AÑADIR A WATCHLIST"))
            self.btn_watchlist.setStyleSheet(
                f"QPushButton{{background:{_BG2};color:{_CIAN};border:2px solid {_CIAN};border-radius:8px;"
                f"font-weight:900;font-size:12px;padding:0 14px;}}"
                f"QPushButton:hover{{background:{_CIAN};color:{_BG};border-color:{_CIAN};}}")
            self.lbl_watchlist.setText("")

    def _bolsa_sel(self):
        r = self.tbl_bolsa.currentRow()
        rows = getattr(self, "_bolsa_rows", []) or []
        return rows[r] if 0 <= r < len(rows) else None

    def _bolsa_doble_clic(self, fila_idx, col):
        """Doble clic: en la columna «Precio ref.» (2) abre el editor rápido del Precio ref.; en cualquier
        otra columna añade esa tarifa a la cola (igual que el botón Acción)."""
        if col == 2:
            self._editar_precio_ref()
        else:
            self._accion_bolsa(fila_idx)

    def _editar_precio_ref(self):
        """Editor RÁPIDO del Precio ref. del artículo buscado (sin salir de Pedidos). Guarda un valor
        MANUAL prioritario o lo restablece a la media histórica; refresca al instante Desvío % y colores."""
        cod = getattr(self, "_bolsa_cod", None)
        if not cod:
            _aviso(self, tr("compras.precio_ref", default="Precio ref."),
                   tr("compras.pref_busca", default="Busca un artículo antes de editar su precio ref."),
                   "warning")
            return
        from src.services.compras import precios_dinamicos as PD
        emp = self._emp_actual()
        actual = PD.precio_referencia(cod, id_empresa=emp)
        manual = PD.es_ref_manual(cod, id_empresa=emp)
        media = PD.media_historica(cod, id_empresa=emp)
        dlg = _DialogoPrecioRef(cod, actual, manual, media, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if dlg.restablecer:
            PD.restablecer_precio_referencia(cod, id_empresa=emp)
            _aviso(self, tr("compras.precio_ref", default="Precio ref."),
                   tr("compras.pref_reset", default="Precio ref. restablecido a la media histórica."),
                   "success")
        elif dlg.valor is not None:
            PD.set_precio_referencia(cod, dlg.valor, id_empresa=emp)
            _aviso(self, tr("compras.precio_ref", default="Precio ref."),
                   tr("compras.pref_set", default="Precio ref. fijado manualmente a {v:.2f} €.", v=dlg.valor),
                   "success")
        else:
            return
        self._buscar_bolsa()   # recalcula Desvío % + indicadores verde ▼ / rojo ▲ al instante

    def _accion_bolsa(self, row):
        """Añade la tarifa de la fila `row` a la cola de artículos (pregunta la cantidad)."""
        rows = getattr(self, "_bolsa_rows", []) or []
        if not (0 <= row < len(rows)):
            return
        fila = rows[row]
        dlg = _DialogoCantidad(tr("compras.cuantas_uds", default="¿Cuántas unidades?"),
                               f"{self._bolsa_cod} · {fila.get('proveedor')}", 1, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.cantidad:
            return
        self._agregar_carrito(fila, dlg.cantidad)

    # ── Carrito (artículos en cola) ──────────────────────────────────────────
    def _agregar_carrito(self, fila, cant):
        """Añade la fila (tarifa o b2b) a la cola. Si ya está el mismo artículo/proveedor/origen/unidad,
        suma cantidad. Las líneas 'b2b' se despachan en paralelo al conector al tramitar."""
        origen = fila.get("origen") or "tarifa"
        codigo = fila.get("codigo") or self._bolsa_cod
        idp = fila.get("id_proveedor")
        if origen == "tarifa" and not idp:
            _aviso(self, "Bolsa", tr("compras.solo_tarifa",
                                     default="Esta tarifa no tiene proveedor local asociado."), "warning")
            return
        precio = float(fila.get("precio") or 0)
        idp = int(idp) if idp else None
        uni = fila.get("unidad")
        for it in self._carrito:
            if (it["codigo"] == codigo and it.get("origen") == origen
                    and it["id_proveedor"] == idp and it["unidad"] == uni):
                it["cantidad"] += int(cant)
                break
        else:
            self._carrito.append({"codigo": codigo, "id_proveedor": idp, "origen": origen,
                                  "proveedor": fila.get("proveedor"), "precio": precio,
                                  "cantidad": int(cant), "unidad": uni,
                                  "ref_externa": fila.get("ref_externa")})
        self._render_carrito()

    def _render_carrito(self):
        """Pinta la cola como un carrito: artículo · precio · cantidad · precio total · ✓ + fila TOTAL.
        La última columna lleva una casilla por fila para poder cancelar VARIOS a la vez."""
        t = getattr(self, "tbl_carrito", None)
        if t is None:
            return
        t.setRowCount(0)
        total = 0.0
        for it in self._carrito:
            pt = float(it["precio"]) * int(it["cantidad"]); total += pt
            r = t.rowCount(); t.insertRow(r)
            art = f"{it['codigo']} · {it.get('proveedor') or ''} ({it.get('unidad') or 'unidad'})"
            for c, v in enumerate([art, f"{float(it['precio']):.2f}", str(it["cantidad"]), f"{pt:.2f}"]):
                t.setItem(r, c, QTableWidgetItem(v))
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            chk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            t.setItem(r, 4, chk)
        # Fila TOTAL (resaltada) con el precio total de todos los artículos.
        r = t.rowCount(); t.insertRow(r)
        neg = QFont(); neg.setBold(True)
        celda_tot = QTableWidgetItem(tr("compras.total", default="TOTAL").upper())
        celda_val = QTableWidgetItem(f"{total:.2f}")
        for cel in (celda_tot, celda_val):
            cel.setFont(neg); cel.setForeground(QColor(_CIAN))
        t.setItem(r, 0, celda_tot)
        t.setItem(r, 1, QTableWidgetItem("")); t.setItem(r, 2, QTableWidgetItem(""))
        t.setItem(r, 3, celda_val); t.setItem(r, 4, QTableWidgetItem(""))

    def _load_pedidos(self):
        """ACTUALIZAR / entrar en Pedidos. Mercado → repinta la cola; simple → lista proveedores."""
        if not self._bolsa:
            texto = (self.in_ped_buscar.text().strip() or None) if hasattr(self, "in_ped_buscar") else None
            filas = P.listar_proveedores(texto=texto)
            self._fill(self.tbl_ped_prov, filas, ("id_proveedor", "razon_social", "cif_nif",
                                                  "email", "telefono", "estado"))
            return
        self._render_carrito()
        # ACTUALIZAR refresca EN VIVO la bolsa superior si hay una búsqueda activa: vuelve a leer las
        # tarifas pactadas locales (proveedor_precios_negociados).
        if hasattr(self, "in_bolsa_art") and self.in_bolsa_art.text().strip():
            self._buscar_bolsa()

    def _carrito_sel_idx(self):
        """Índice del artículo seleccionado en la cola (la fila TOTAL queda excluida)."""
        r = self.tbl_carrito.currentRow() if hasattr(self, "tbl_carrito") else -1
        return r if 0 <= r < len(self._carrito) else None

    def _carrito_doble_clic(self, fila_idx, _col):
        """Doble clic en un artículo de la cola → editar cantidad (con confirmación)."""
        if _col == 4:   # columna de la casilla ✓ → no abrir el editor de cantidad
            return
        if not (0 <= fila_idx < len(self._carrito)):
            return
        it = self._carrito[fila_idx]
        dlg = _DialogoCantidad(tr("compras.editar_cantidad", default="Editar cantidad"),
                               it["codigo"], it["cantidad"], self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.cantidad:
            if _confirmar(self, tr("compras.editar_cantidad", default="Editar cantidad"),
                          tr("compras.editar_cantidad_msg",
                             default="¿Cambiar la cantidad de {c} a {n}?", c=it["codigo"], n=dlg.cantidad)):
                it["cantidad"] = dlg.cantidad
                self._render_carrito()

    def _cancelar_seleccionados(self):
        """CANCELAR: retira de la cola TODOS los artículos MARCADOS con la casilla (con una confirmación)."""
        t = getattr(self, "tbl_carrito", None)
        marcados = []
        if t is not None:
            for r in range(min(t.rowCount(), len(self._carrito))):
                cel = t.item(r, 4)
                if cel is not None and cel.checkState() == Qt.CheckState.Checked:
                    marcados.append(r)
        if not marcados:
            _aviso(self, tr("compras.cola_titulo", default="Artículos en cola"),
                   tr("compras.cola_sel_multi",
                      default="Marca con la casilla ✓ los artículos que quieras cancelar."), "warning")
            return
        if not _confirmar(self, tr("compras.retirar", default="Cancelar de la cola"),
                          tr("compras.retirar_multi",
                             default="¿Cancelar {n} artículo(s) marcado(s) de la cola?", n=len(marcados))):
            return
        for r in sorted(marcados, reverse=True):
            del self._carrito[r]
        self._render_carrito()

    def _tramitar_lineas(self, items):
        """Crea+envía los pedidos (agrupados por proveedor). En ese instante calcula el PVP dinámico por
        línea (coste × margen), lo registra en el pedido y genera una etiqueta QR de trazabilidad por
        pedido. Devuelve nº de pedidos enviados. Los PDF generados se guardan en `self._etiquetas_qr`."""
        from collections import defaultdict
        try:
            from src.services.compras import precios_dinamicos as PD
            _u, margen = PD._reglas(self._emp_actual())
        except Exception:
            margen = 30.0
        grupos = defaultdict(list)
        for it in items:
            idp = it.get("id_proveedor")
            grupos[int(idp) if idp else 0].append(it)
        n = 0
        self._etiquetas_qr = []
        for idp, its in grupos.items():
            if not idp:
                continue
            lineas = [{"codigo": it["codigo"], "cantidad": int(it["cantidad"]),
                       "precio_unitario": float(it["precio"]),
                       # PVP dinámico calculado EN LA TRAMITACIÓN según el coste pactado.
                       "pvp_sugerido": round(float(it["precio"]) * (1 + margen / 100.0), 2),
                       "descripcion": f"{it['codigo']} · {it.get('unidad') or 'unidad'}"} for it in its]
            pid = C.crear_pedido(id_proveedor=idp, lineas=lineas, usuario=self.usuario.get("nombre"))
            if pid and C.enviar_pedido(pid):
                n += 1
                self._generar_etiqueta_qr(pid, its)
        return n

    def _generar_etiqueta_qr(self, id_pedido, items):
        """Genera la etiqueta imprimible con QR (ref+UUID del pedido, empresa, proveedor, fecha, bultos)
        y la indexa en el Centro Documental. Best-effort: si falla, el pedido ya está creado igual."""
        try:
            import datetime as _dt

            from src.utils.etiqueta_pedido import generar_etiqueta_pedido_pdf
            from src.utils.recursos import ruta_datos
            ped = C.obtener_pedido(id_pedido, id_empresa=self._emp_actual()) or {}
            prov = ""
            try:
                p = P.obtener_proveedor(ped.get("id_proveedor"), id_empresa=self._emp_actual()) or {}
                prov = p.get("razon_social") or ""
            except Exception:
                pass
            empresa = ""
            try:
                from src.db import empresa as _EMP
                empresa = (_EMP.obtener_empresa(self._emp_actual()) or {}).get("nombre") or ""
            except Exception:
                pass
            datos = {
                "referencia": ped.get("numero") or f"PC{id_pedido:06d}",
                "uuid": ped.get("uuid") or "",
                "empresa": empresa, "proveedor": prov,
                "fecha": str(ped.get("fecha") or _dt.datetime.now())[:19],
                "lineas": [{"codigo": it.get("codigo"), "descripcion": it.get("codigo"),
                            "cantidad": int(it.get("cantidad") or 0)} for it in items],
                "total": ped.get("total"),
            }
            archivo = ruta_datos("etiquetas_pedidos", f"ETIQ_{datos['referencia']}.pdf")
            ruta = generar_etiqueta_pedido_pdf(datos, archivo)
            if ruta:
                self._etiquetas_qr.append(ruta)
                try:
                    from src.db import documentos as _DOC
                    _DOC.registrar_documento(ruta, tipo="etiqueta_pedido",
                                             nombre=f"Etiqueta {datos['referencia']}")
                except Exception as e:
                    logger.debug("registrar etiqueta pedido: %s", e)
        except Exception as e:
            logger.warning("_generar_etiqueta_qr(%s): %s", id_pedido, e)

    def _tramitar_todos(self):
        """Tramita TODA la cola: crea y envía los pedidos (agrupados por proveedor) → Recepciones."""
        if not self._carrito:
            _aviso(self, tr("compras.cola_titulo", default="Artículos en cola"),
                   tr("compras.cola_vacia", default="No hay artículos en cola que tramitar."), "info")
            return
        if not _confirmar(self, tr("compras.tramitar_todos", default="Tramitar todos"),
                          tr("compras.tramitar_msg",
                             default="¿Tramitar todos los artículos en cola? Se enviarán los pedidos a los "
                                     "proveedores y aparecerán en Recepciones.")):
            return
        n = self._tramitar_lineas(self._carrito)
        etiquetas = len(getattr(self, "_etiquetas_qr", []) or [])
        self._carrito = []
        self._render_carrito()
        self._load_recepciones()
        _aviso(self, tr("compras.tramitar_todos", default="Tramitar todos"),
               tr("compras.tramitar_hecho_qr",
                  default="Se han enviado {n} pedido(s) y generado {e} etiqueta(s) QR de trazabilidad "
                          "(en Documentos). Puedes verlos en la pestaña Recepciones.", n=n, e=etiquetas),
               "success" if n else "warning")

    def _enviar_carrito_sel(self):
        """ENVIAR: tramita SOLO el artículo seleccionado de la cola (con confirmación) → Recepciones."""
        idx = self._carrito_sel_idx()
        if idx is None:
            _aviso(self, tr("compras.cola_titulo", default="Artículos en cola"),
                   tr("compras.cola_sel", default="Selecciona un artículo de la cola."), "warning")
            return
        it = self._carrito[idx]
        if not _confirmar(self, tr("compras.enviar", default="Enviar"),
                          tr("compras.enviar_msg", default="¿Enviar el pedido de {c} a {p}?",
                             c=it["codigo"], p=it.get("proveedor") or "")):
            return
        if self._tramitar_lineas([it]):
            del self._carrito[idx]
            self._render_carrito()
            self._load_recepciones()
            _aviso(self, tr("compras.enviar", default="Enviar"),
                   tr("compras.enviar_hecho", default="Pedido enviado. Está en la pestaña Recepciones."),
                   "success")

    def crear_pedido(self, id_proveedor, lineas):
        """Crea un pedido (BORRADOR) directamente. Núcleo testeable / uso programático."""
        return C.crear_pedido(id_proveedor=id_proveedor, lineas=lineas,
                              usuario=self.usuario.get("nombre"))

    def _dlg_nuevo_pedido(self):
        """NUEVO PEDIDO. Mercado → añade líneas a la cola. Simple → exige un proveedor SELECCIONADO y
        crea+envía el pedido directamente (bajo encargo, sin cola)."""
        provs = P.listar_proveedores(estado="activo")
        if not provs:
            _aviso(self, "Compras", tr("compras.sin_prov", default="Cree un proveedor primero."), "error")
            return

        if not self._bolsa:
            if not self._ped_prov_sel:
                _aviso(self, tr("compras.pedidos", default="Pedidos"),
                       tr("compras.sel_prov_pedido",
                          default="Selecciona antes un proveedor de la tabla para iniciar el pedido."), "info")
                return
            if not any(p["id_proveedor"] == self._ped_prov_sel for p in provs):
                _aviso(self, tr("compras.pedidos", default="Pedidos"),
                       tr("compras.prov_inactivo", default="El proveedor seleccionado ya no está activo."),
                       "warning")
                return
            dlg = _DialogoPedido(provs, self, id_prov_fijo=self._ped_prov_sel)
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.lineas:
                lineas = [{"codigo": ln["codigo"], "descripcion": ln.get("descripcion"),
                           "cantidad": int(ln["cantidad"]),
                           "precio_unitario": float(ln.get("precio_unitario") or 0)} for ln in dlg.lineas]
                pid = C.crear_pedido(id_proveedor=self._ped_prov_sel, lineas=lineas,
                                     usuario=self.usuario.get("nombre"))
                if pid and C.enviar_pedido(pid):
                    _aviso(self, tr("compras.pedidos", default="Pedidos"),
                           tr("compras.pedido_creado",
                              default="Pedido creado y enviado. Lo verás en Recepciones."), "success")
                else:
                    _aviso(self, tr("compras.pedidos", default="Pedidos"),
                           tr("compras.pedido_error", default="No se pudo crear el pedido."), "error")
            return

        dlg = _DialogoPedido(provs, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.lineas:
            prov = next((p for p in provs if p["id_proveedor"] == dlg.id_proveedor), {})
            for ln in dlg.lineas:
                self._carrito.append({"codigo": ln["codigo"], "id_proveedor": dlg.id_proveedor,
                                      "proveedor": prov.get("razon_social"),
                                      "precio": float(ln.get("precio_unitario") or 0),
                                      "cantidad": int(ln["cantidad"]), "unidad": "unidad"})
            self._render_carrito()

    def _desde_reab(self):
        """DESDE REPOSICIÓN: NO genera un pedido automáticamente. Muestra la lista de propuestas de
        reposición (artículos bajo mínimos) para que el usuario decida cuáles comprar/pujar; al elegir
        uno, se busca en la bolsa unificada."""
        try:
            from src.db import reabastecimiento as R
            props = R.listar_propuestas(estados=("pendiente",))
        except Exception as e:
            logger.error("listar propuestas reposición: %s", e)
            props = []
        if not props:
            _aviso(self, "Compras", tr("compras.reab_vacio", default="No hay propuestas de reposición."),
                   "info")
            return
        dlg = _DialogoReposicion(props, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.codigo:
            # En modo mercado, al elegir un artículo se busca en la bolsa. En modo simple no hay bolsa:
            # "Desde reposición" solo sirve para VER la lista de artículos bajo mínimos.
            if self._bolsa and hasattr(self, "in_bolsa_art"):
                self.in_bolsa_art.setText(dlg.codigo)
                self._buscar_bolsa()

    # ── Sección Recepciones ──────────────────────────────────────────────────
    def _page_recepciones(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10); ly.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        fila.addWidget(QLabel(tr("compras.pedidos_recep", default="Pedidos pendientes de recibir")))
        fila.addStretch(1)
        fila.addWidget(_btn(tr("compras.recibir_todo", default="RECIBIR TODO"), self._recibir_sel, primary=True))
        # Cancelar un pedido YA tramitado aplicando la política de cancelación.
        fila.addWidget(_btn(tr("compras.cancelar_pedido", default="❌  CANCELAR PEDIDO"),
                            self._cancelar_recepcion_sel, danger=True))
        fila.addWidget(_btn_cargando(tr("compras.actualizar", default="🔄  ACTUALIZAR"), self._load_recepciones))
        ly.addLayout(fila)
        # "Estado prov." = seguimiento que el proveedor reporta desde el Portal (bidireccional).
        self.tbl_rec = _tabla(["ID", tr("compras.numero", default="Número"),
                               tr("compras.proveedor", default="Proveedor"),
                               tr("compras.estado", default="Estado"),
                               tr("compras.estado_prov", default="Estado prov."),
                               tr("compras.total", default="Total"), tr("compras.fecha", default="Fecha")])
        ly.addWidget(self.tbl_rec, 1)
        return w

    def _cancelar_recepcion_sel(self):
        """Cancela el pedido tramitado seleccionado APLICANDO la política de cancelación
        (tipo de producto × estado × origen: gratuita / recargo / bloqueo / vinculante)."""
        r = self.tbl_rec.currentRow()
        if r < 0:
            _aviso(self, tr("compras.cancelar_pedido", default="Cancelar pedido"),
                   tr("compras.sel_pedido", default="Selecciona un pedido de la tabla."), "warning")
            return
        try:
            pid = int(self.tbl_rec.item(r, 0).text())
        except Exception:
            return
        from src.services.compras import cancelaciones as CANC
        pol = CANC.evaluar(pid)
        if not pol["puede_cancelar"]:
            _aviso(self, tr("compras.cancelar_pedido", default="Cancelar pedido"), pol["motivo"], "warning")
            return
        extra = (tr("compras.recargo_aviso", default=" Se aplicará un recargo del {r:.0f}%.",
                    r=pol["recargo_pct"]) if pol["recargo_pct"] > 0 else "")
        if not _confirmar(self, tr("compras.cancelar_pedido", default="Cancelar pedido"),
                          tr("compras.cancelar_pedido_msg",
                             default="¿Cancelar el pedido {p}? {m}{e}", p=pid, m=pol["motivo"], e=extra)):
            return
        res = CANC.cancelar_pedido(pid, usuario=self.usuario.get("nombre"))
        if res["ok"]:
            msg = tr("compras.cancelado_ok", default="Pedido cancelado.")
            if res["recargo_pct"] > 0:
                msg += tr("compras.recargo_aplicado", default=" Recargo aplicado: {r:.0f}%.",
                          r=res["recargo_pct"])
            _aviso(self, tr("compras.cancelar_pedido", default="Cancelar pedido"), msg, "success")
            self._load_recepciones()
        else:
            _aviso(self, tr("compras.cancelar_pedido", default="Cancelar pedido"),
                   res["politica"]["motivo"], "error")

    def _load_recepciones(self):
        filas = [p for p in C.historico_pedidos() if p["estado"] in ("ENVIADO", "PARCIAL")]
        # (El estado reportado por el proveedor desde el portal externo se retiró; en Fase 2 lo aportará
        # el conector B2B para las líneas de origen 'b2b'.)
        for p in filas:
            p["estado_prov"] = "—"
        self._fill(self.tbl_rec, filas,
                   ("id_pedido", "numero", "proveedor", "estado", "estado_prov", "total", "fecha"))

    def recibir_pedido(self, id_pedido):
        """Recibe TODO lo pendiente del pedido. Núcleo testeable."""
        ped = C.obtener_pedido(id_pedido)
        if not ped:
            return None
        pend = [{"id_linea": ln["id"], "cantidad": ln["cantidad"] - ln["cantidad_recibida"]}
                for ln in ped["lineas"] if ln["cantidad"] - ln["cantidad_recibida"] > 0]
        res = C.recibir(id_pedido, pend, usuario=self.usuario.get("nombre")) if pend else None
        self._load_recepciones()
        return res

    def _recibir_sel(self):
        r = self.tbl_rec.currentRow()
        if r < 0:
            return
        try:
            pid = int(self.tbl_rec.item(r, 0).text())
        except Exception:
            return
        res = self.recibir_pedido(pid)
        if res:
            _aviso(self, "Compras", tr("compras.recibido", default="Recepción registrada.")
                   + f" ({res['estado_pedido']})")

    # ── Sección Facturas ─────────────────────────────────────────────────────
    def _page_facturas(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10); ly.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        fila.addWidget(_btn(tr("compras.nueva_factura", default="NUEVA FACTURA"), self._dlg_nueva_factura, primary=True))
        fila.addWidget(_btn(tr("compras.validar", default="VALIDAR"), self._validar_factura_sel, primary=True))
        fila.addStretch(1)
        fila.addWidget(_btn_cargando(tr("compras.actualizar", default="🔄  ACTUALIZAR"), self._load_facturas))
        ly.addLayout(fila)
        self.tbl_fac = _tabla(["ID", tr("compras.numero", default="Nº factura"),
                               tr("compras.pedido", default="Pedido"),
                               tr("compras.total", default="Total"), tr("compras.estado", default="Estado"),
                               tr("compras.fecha", default="Fecha")])
        ly.addWidget(self.tbl_fac, 1)
        return w

    def _load_facturas(self):
        filas = C.listar_facturas()
        self._fill(self.tbl_fac, filas,
                   ("id_factura", "numero_factura", "id_pedido", "total", "estado", "fecha_registro"))

    def registrar_factura(self, id_proveedor, numero, base, iva=0.0, id_pedido=None):
        """Registra una factura de proveedor. Núcleo testeable."""
        fid = C.registrar_factura(id_proveedor=id_proveedor, numero_factura=numero,
                                  base=base, iva=iva, id_pedido=id_pedido)
        self._load_facturas()
        return fid

    def _dlg_nueva_factura(self):
        provs = P.listar_proveedores(estado="activo")
        if not provs:
            _aviso(self, "Compras", tr("compras.sin_prov", default="Cree un proveedor primero."), "error")
            return
        dlg = _DialogoFactura(provs, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.numero:
            self.registrar_factura(dlg.id_proveedor, dlg.numero, dlg.base, dlg.iva)

    def _validar_factura_sel(self):
        r = self.tbl_fac.currentRow()
        if r < 0:
            return
        try:
            fid = int(self.tbl_fac.item(r, 0).text())
        except Exception:
            return
        res = C.validar_factura(fid)
        self._load_facturas()
        _aviso(self, "Compras", f"{res.get('estado')} (dif: {res.get('diferencia')})")

    # ── Sección Informes ─────────────────────────────────────────────────────
    def _page_informes(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10); ly.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        self.cb_informe = _combo([
            (tr("compras.inf_prov", default="Compras por proveedor"), 0),
            (tr("compras.inf_per", default="Compras por periodo"), 1),
            (tr("compras.inf_art", default="Costes por artículo"), 2),
            (tr("compras.inf_rank", default="Proveedores más usados"), 3),
            (tr("compras.inf_hist", default="Histórico de pedidos"), 4),
        ])
        self.cb_informe.currentIndexChanged.connect(lambda _i: self._cargar_informe())
        fila.addWidget(self.cb_informe, 1)
        fila.addWidget(_btn_cargando(tr("compras.actualizar", default="🔄  ACTUALIZAR"), self._cargar_informe))
        ly.addLayout(fila)
        self.tbl_inf = _tabla(["", "", "", ""])
        ly.addWidget(self.tbl_inf, 1)
        return w

    def _cargar_informe(self):
        idx = self.cb_informe.currentIndex() if hasattr(self, "cb_informe") else 0
        if idx == 0:
            self.tbl_inf.setColumnCount(3)
            self.tbl_inf.setHorizontalHeaderLabels(["Proveedor", "Facturas", "Total"])
            self._fill(self.tbl_inf, C.compras_por_proveedor(), ("proveedor", "facturas", "total"))
        elif idx == 1:
            self.tbl_inf.setColumnCount(3)
            self.tbl_inf.setHorizontalHeaderLabels(["Periodo", "Facturas", "Total"])
            self._fill(self.tbl_inf, C.compras_por_periodo(), ("periodo", "facturas", "total"))
        elif idx == 2:
            self.tbl_inf.setColumnCount(4)
            self.tbl_inf.setHorizontalHeaderLabels(["Artículo", "Unidades", "Gasto", "Precio medio"])
            self._fill(self.tbl_inf, C.costes_por_articulo(),
                       ("codigo_articulo", "unidades", "gasto", "precio_medio"))
        elif idx == 3:
            self.tbl_inf.setColumnCount(3)
            self.tbl_inf.setHorizontalHeaderLabels(["Proveedor", "Pedidos", "Total"])
            self._fill(self.tbl_inf, C.proveedores_mas_utilizados(), ("proveedor", "pedidos", "total"))
        else:
            self.tbl_inf.setColumnCount(5)
            self.tbl_inf.setHorizontalHeaderLabels(["Número", "Proveedor", "Estado", "Total", "Fecha"])
            self._fill(self.tbl_inf, C.historico_pedidos(),
                       ("numero", "proveedor", "estado", "total", "fecha"))

    # ── Utilidad de tablas ───────────────────────────────────────────────────
    @staticmethod
    def _fill(tabla, filas, claves):
        tabla.setRowCount(0)
        for f in filas:
            r = tabla.rowCount(); tabla.insertRow(r)
            for c, k in enumerate(claves):
                tabla.setItem(r, c, QTableWidgetItem("" if f.get(k) is None else str(f.get(k))))


# ── Diálogos mínimos ─────────────────────────────────────────────────────────
class _DialogoCantidad(QDialog):
    """Popup de cantidad (frameless, esquinas redondeadas, sin barra de título de Windows).
    Se usa al añadir un artículo a la cola y al editar la cantidad de un artículo de la cola."""

    def __init__(self, titulo, articulo, cantidad=1, parent=None):
        super().__init__(parent)
        self.cantidad = None
        v = _dialogo_frameless(self, titulo=titulo, ancho=400)
        lbl = QLabel(str(articulo))
        lbl.setStyleSheet(f"color:{_TEXT};background:transparent;font-size:13px;font-weight:700;")
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        self.in_cant = _inp(tr("compras.cantidad", default="Cantidad"))
        self.in_cant.setText(str(int(cantidad) if cantidad else 1))
        self.in_cant.selectAll()
        self.in_cant.returnPressed.connect(self._ok)
        v.addWidget(self.in_cant)
        row = QHBoxLayout(); row.addStretch(1)
        row.addWidget(_btn(tr("compras.cancelar", default="Cancelar"), self.reject))
        row.addWidget(_btn(tr("compras.aceptar", default="Aceptar"), self._ok, primary=True))
        v.addLayout(row)
        self.in_cant.setFocus()

    def _ok(self):
        try:
            c = int(self.in_cant.text() or 0)
        except ValueError:
            c = 0
        if c > 0:
            self.cantidad = c
            self.accept()


class _DialogoPrecioRef(QDialog):
    """Editor rápido del Precio ref. de un artículo (frameless). Permite fijar un valor MANUAL prioritario
    o restablecerlo a la media histórica. Expone `valor` (float|None) y `restablecer` (bool)."""

    def __init__(self, codigo, actual, es_manual, media, parent=None):
        super().__init__(parent)
        self.valor = None
        self.restablecer = False
        self.setFixedSize(440, 340)
        v = _dialogo_frameless(self, titulo=tr("compras.precio_ref", default="Precio de referencia"),
                               ancho=440)
        cab = QLabel(f"{codigo}")
        cab.setStyleSheet(f"color:{_CIAN};background:transparent;font-size:14px;font-weight:900;")
        v.addWidget(cab)
        origen = (tr("compras.pref_manual", default="valor manual (prioritario)") if es_manual
                  else tr("compras.pref_auto", default="cálculo automático"))
        info = QLabel(tr("compras.pref_info",
                         default="Precio ref. actual: {a} € · origen: {o}.",
                         a=(f"{actual:.2f}" if actual is not None else "—"), o=origen))
        info.setStyleSheet(f"color:{_DIM};background:transparent;font-size:12px;"); info.setWordWrap(True)
        v.addWidget(info)
        med = QLabel(tr("compras.pref_media",
                        default="Media histórica (30 días): {m}.",
                        m=(f"{media:.2f} €" if media is not None else "sin histórico")))
        med.setStyleSheet(f"color:{_DIM};background:transparent;font-size:11px;")
        v.addWidget(med)
        cap = QLabel(tr("compras.pref_nuevo", default="Nuevo Precio ref. manual (€)"))
        cap.setStyleSheet(f"color:{_DIM};background:transparent;font-weight:700;font-size:12px;")
        v.addWidget(cap)
        self.in_val = _inp("0.00")
        if actual is not None:
            self.in_val.setText(f"{float(actual):.2f}")
        self.in_val.returnPressed.connect(self._ok)
        v.addWidget(self.in_val)
        v.addWidget(_btn(tr("compras.pref_restablecer", default="↺  Restablecer a media histórica"),
                         self._reset, primary=True))
        v.addStretch(1)
        row = QHBoxLayout(); row.addStretch(1)
        row.addWidget(_btn(tr("compras.cancelar", default="Cancelar"), self.reject))
        row.addWidget(_btn(tr("compras.guardar", default="Guardar"), self._ok, primary=True))
        v.addLayout(row)
        self.in_val.setFocus(); self.in_val.selectAll()

    def _reset(self):
        self.restablecer = True
        self.accept()

    def _ok(self):
        try:
            v = float((self.in_val.text() or "0").replace(",", "."))
        except ValueError:
            return
        if v <= 0:
            return
        self.valor = round(v, 2)
        self.accept()


class _DialogoReposicion(QDialog):
    """Lista de propuestas de reposición (artículos bajo mínimos). El usuario elige uno para buscarlo en
    la bolsa unificada y decidir si comprar o pujar (frameless)."""

    def __init__(self, propuestas, parent=None):
        super().__init__(parent)
        self.codigo = None
        self._props = propuestas
        v = _dialogo_frameless(self, titulo=tr("compras.desde_reab", default="Propuestas de reposición"),
                               ancho=620)
        info = QLabel(tr("compras.reab_info",
                         default="Artículos bajo mínimos. Elige uno y pulsa «Buscar en la bolsa» para "
                                 "decidir si comprarlo o pujar por él."))
        info.setStyleSheet(f"color:{_DIM};background:transparent;font-size:11px;")
        info.setWordWrap(True)
        v.addWidget(info)
        self.tbl = _tabla(["Código", "Artículo", "Sugerido", "Stock", "Objetivo"])
        for p in propuestas:
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            for c, val in enumerate([p.get("codigo"), p.get("nombre"), p.get("cantidad"),
                                     p.get("stock_actual"), p.get("stock_objetivo")]):
                self.tbl.setItem(r, c, QTableWidgetItem("" if val is None else str(val)))
        self.tbl.cellDoubleClicked.connect(lambda *_: self._ok())
        v.addWidget(self.tbl)
        row = QHBoxLayout(); row.addStretch(1)
        row.addWidget(_btn(tr("compras.cerrar", default="Cerrar"), self.reject))
        row.addWidget(_btn("🔎  " + tr("compras.reab_buscar", default="Buscar en la bolsa"),
                           self._ok, primary=True))
        v.addLayout(row)

    def _ok(self):
        r = self.tbl.currentRow()
        if 0 <= r < len(self._props):
            self.codigo = str(self._props[r].get("codigo") or "").strip().upper()
            if self.codigo:
                self.accept()


def _cap(txt):
    lab = QLabel(txt); lab.setStyleSheet(f"color:{_DIM};background:transparent;font-weight:700;font-size:14px;")
    return lab


def _big(w):
    """Sube +1pt el texto de un campo de la Ficha (12→13px), sin tocar el estilo global de `_inp`/`_combo`
    (la última regla del mismo selector gana)."""
    w.setStyleSheet(w.styleSheet() + "QLineEdit{font-size:13px;}QComboBox{font-size:13px;}")
    return w


class FichaProveedorDialog(QDialog):
    """Ficha COMPLETA del proveedor (gran formato, por pestañas): Datos Generales · Tarifas y Precios
    Negociados · Condiciones Comerciales y Pago · Historial y Documentos. Solo orquesta interfaz; toda
    la persistencia va a la BD PERMANENTE (`proveedores` + `proveedor_precios_negociados` + direcciones
    0008) vía `db/proveedores` y `services/compras/proveedores_pro`, sin tocar otros módulos. Las tarifas
    guardadas aquí alimentan el origen='tarifa' de la bolsa de Pedidos."""

    _FORMAS_PAGO = ["", "Transferencia", "Recibo domiciliado", "Pagaré", "Confirming", "Efectivo", "Otro"]

    def __init__(self, id_proveedor, parent=None, id_empresa=None):
        super().__init__(parent)
        self._pid = id_proveedor
        self._emp = id_empresa
        self._prov = P.obtener_proveedor(id_proveedor, id_empresa=id_empresa) or {}
        self._tarifas = []
        # VENTANA COMPLETA: ocupa toda el área disponible de la pantalla (no se ve la pantalla anterior
        # de fondo). Se posiciona en el origen del área útil y se fija ese tamaño.
        scr = QGuiApplication.primaryScreen()
        av = scr.availableGeometry() if scr else None
        if av is not None:
            self.setGeometry(av)
        else:
            self.resize(1120, 740)
        v = _dialogo_frameless(self)   # sin título: cabecera propia con X
        v.addLayout(self._cabecera())
        tabs = QTabWidget()
        # Sin línea alrededor del contenido de cada sub-pestaña (el contorno turquesa lo ponen las
        # tablas). Se conserva el fondo del pane para el contenido con scroll.
        tabs.setStyleSheet(f"QTabWidget::pane{{border:none;background:{_BG};}}")
        # Cada pestaña envuelta en scroll (misma scrollbar cyan de la app) para que el contenido no se corte.
        tabs.addTab(_scroll_neon(self._tab_generales()),
                    tr("compras.ficha_generales", default="Datos Generales"))
        tabs.addTab(_scroll_neon(self._tab_tarifas()),
                    tr("compras.ficha_tarifas", default="Tarifas y Precios Negociados"))
        tabs.addTab(_scroll_neon(self._tab_condiciones()),
                    tr("compras.ficha_condiciones", default="Condiciones Comerciales y Pago"))
        tabs.addTab(_scroll_neon(self._tab_historial()),
                    tr("compras.ficha_historial", default="Historial y Documentos"))
        v.addWidget(tabs, 1)
        bar = QHBoxLayout(); bar.addStretch(1)
        bar.addWidget(_btn(tr("compras.cerrar", default="Cerrar"), self.reject))
        bar.addWidget(_btn(tr("compras.guardar", default="Guardar"), self._guardar, primary=True))
        v.addLayout(bar)
        self._cargar_tarifas()
        self._cargar_historial()

    # ── Cabecera con X compacta (algo más alta para que la ✕ no se corte por abajo) ──
    def _cabecera(self):
        hdr = QHBoxLayout()
        t = QLabel(tr("compras.ficha_prov", default="Ficha del proveedor"))
        t.setStyleSheet(f"color:{_CIAN};background:transparent;font-weight:900;font-size:17px;")
        hdr.addWidget(t)
        sub = self._prov.get("razon_social") or ""
        if sub:
            s = QLabel(f"·  {sub}")
            s.setStyleSheet(f"color:{_DIM};background:transparent;font-weight:700;font-size:13px;")
            hdr.addWidget(s)
        hdr.addStretch(1)
        x = QPushButton("✕"); x.setCursor(Qt.CursorShape.PointingHandCursor); x.setFixedSize(42, 48)
        x.setToolTip(tr("compras.cerrar", default="Cerrar"))
        x.setStyleSheet(f"QPushButton{{background:transparent;color:{_ROJO};border:2px solid {_ROJO};"
                        f"border-radius:8px;font-weight:900;font-size:15px;padding:0;}}"
                        f"QPushButton:hover{{background:{_ROJO};color:#0D1117;}}")
        x.clicked.connect(self.reject)
        hdr.addWidget(x)
        return hdr

    # ── a) Datos Generales ────────────────────────────────────────────────────
    def _tab_generales(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(8)
        p = self._prov
        self.f_razon = _big(_inp("Razón social")); self.f_razon.setText(p.get("razon_social") or "")
        self.f_nombre_com = _big(_inp("Nombre comercial"))
        self.f_nombre_com.setText(p.get("nombre_comercial") or "")
        self.f_cif = _big(_inp("CIF/NIF")); self.f_cif.setText(p.get("cif_nif") or "")
        self.f_estado = _big(_combo([("Activo", "activo"), ("Inactivo", "inactivo")],
                                    actual=(p.get("estado") or "activo")))
        self.f_email = _big(_inp("Email")); self.f_email.setText(p.get("email") or "")
        self.f_tel = _big(_inp("Teléfono")); self.f_tel.setText(p.get("telefono") or "")
        self.f_persona = _big(_inp("Persona de contacto"))
        self.f_persona.setText(p.get("persona_contacto") or "")
        self.f_web = _big(_inp("https://…")); self.f_web.setText(p.get("web") or "")

        lbl = QLabel("🏢  " + tr("compras.ficha_identificacion", default="Identificación"))
        lbl.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:13px;")
        ly.addWidget(lbl)
        g1 = QFormLayout(); g1.setHorizontalSpacing(18); g1.setVerticalSpacing(6)
        g1.addRow(_cap("Razón social"), self.f_razon)
        g1.addRow(_cap("Nombre comercial"), self.f_nombre_com)
        g1.addRow(_cap("CIF/NIF"), self.f_cif)
        g1.addRow(_cap("Estado"), self.f_estado)
        ly.addLayout(g1)

        lbl2 = QLabel("📇  " + tr("compras.ficha_contacto", default="Contacto principal"))
        lbl2.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:13px;padding-top:6px;")
        ly.addWidget(lbl2)
        g2 = QFormLayout(); g2.setHorizontalSpacing(18); g2.setVerticalSpacing(6)
        g2.addRow(_cap("Email"), self.f_email)
        g2.addRow(_cap("Teléfono"), self.f_tel)
        g2.addRow(_cap("Persona de contacto"), self.f_persona)
        g2.addRow(_cap("Web"), self.f_web)
        ly.addLayout(g2)

        lbl3 = QLabel("📍  " + tr("compras.ficha_direcciones", default="Direcciones (fiscal y almacén)"))
        lbl3.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:13px;padding-top:6px;")
        ly.addWidget(lbl3)
        self.tbl_dir = _tabla(["Tipo", "Dirección", "CP", "Municipio", "Provincia", "País"])
        ly.addWidget(self.tbl_dir, 1)
        db = QHBoxLayout()
        db.addWidget(_btn(tr("compras.ficha_add_dir", default="Añadir dirección"),
                          self._add_direccion, primary=True))
        db.addStretch(1)
        ly.addLayout(db)
        self._cargar_direcciones()
        return w

    def _cargar_direcciones(self):
        self.tbl_dir.setRowCount(0)
        try:
            dirs = P.listar_direcciones(self._pid)
        except Exception:
            dirs = []
        for d in dirs:
            r = self.tbl_dir.rowCount(); self.tbl_dir.insertRow(r)
            for c, k in enumerate(("tipo", "direccion", "cp", "municipio", "provincia", "pais")):
                self.tbl_dir.setItem(r, c, QTableWidgetItem(str(d.get(k) or "")))

    def _add_direccion(self):
        dlg = _DialogoDireccion(self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.datos:
            return
        d = dlg.datos
        P.agregar_direccion(self._pid, direccion=d.get("direccion"), tipo=d.get("tipo") or "fiscal",
                            cp=d.get("cp"), municipio=d.get("municipio"), provincia=d.get("provincia"),
                            pais=d.get("pais") or "España")
        self._cargar_direcciones()

    # ── b) Tarifas y Precios Negociados ───────────────────────────────────────
    def _tab_tarifas(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(8)
        info = QLabel(tr("compras.ficha_tarifas_info",
                         default="Estas tarifas alimentan automáticamente el origen «tarifa» de la bolsa "
                                 "en Pedidos."))
        info.setStyleSheet(f"color:{_DIM};background:transparent;font-size:11px;"); info.setWordWrap(True)
        ly.addWidget(info)
        self.tbl_tarifas = _tabla(["Código Artículo", "Descripción", "Precio Negociado (€)",
                                   "Descuento (%)", "Fecha Actualización"])
        ly.addWidget(self.tbl_tarifas, 1)
        bar = QHBoxLayout()
        bar.addWidget(_btn(tr("compras.ficha_add_tarifa", default="Añadir Artículo / Tarifa"),
                           self._add_tarifa, primary=True))
        bar.addWidget(_btn(tr("compras.editar", default="Editar"), self._editar_tarifa, primary=True))
        bar.addWidget(_btn(tr("compras.eliminar", default="Eliminar"), self._eliminar_tarifa, danger=True))
        bar.addStretch(1)
        bar.addWidget(_btn("📁  " + tr("compras.ficha_import_tarifas", default="Importar Tarifas (CSV/Excel)"),
                           self._importar_tarifas, primary=True))
        ly.addLayout(bar)
        return w

    def _cargar_tarifas(self):
        from src.services.compras import proveedores_pro as PP
        try:
            self._tarifas = PP.listar_tarifas_proveedor(self._pid, id_empresa=self._emp)
        except Exception as e:
            logger.error("cargar tarifas ficha: %s", e); self._tarifas = []
        self.tbl_tarifas.setRowCount(0)
        for t in self._tarifas:
            r = self.tbl_tarifas.rowCount(); self.tbl_tarifas.insertRow(r)
            fecha = str(t.get("fecha") or "")[:10]
            vals = [t.get("codigo"), t.get("descripcion"),
                    f"{float(t.get('precio') or 0):.2f}", f"{float(t.get('descuento') or 0):.0f}", fecha]
            for c, val in enumerate(vals):
                self.tbl_tarifas.setItem(r, c, QTableWidgetItem("" if val is None else str(val)))

    def _tarifa_sel(self):
        r = self.tbl_tarifas.currentRow()
        return self._tarifas[r] if 0 <= r < len(self._tarifas) else None

    def _add_tarifa(self, _=False, base=None):
        dlg = _DialogoTarifa(self, base=base)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.datos:
            return
        from src.services.compras import proveedores_pro as PP
        d = dlg.datos
        PP.set_precio_negociado(self._pid, d["codigo"], d["precio"], descuento=d["descuento"],
                                unidad_medida=d["unidad"], id_empresa=self._emp)
        self._cargar_tarifas()

    def _editar_tarifa(self):
        t = self._tarifa_sel()
        if not t:
            _aviso(self, tr("compras.ficha_tarifas", default="Tarifas"),
                   tr("compras.ficha_sel_tarifa", default="Selecciona una tarifa de la tabla."), "warning")
            return
        self._add_tarifa(base={"codigo": t.get("codigo"), "descripcion": t.get("descripcion"),
                               "precio": t.get("precio"), "descuento": t.get("descuento"),
                               "unidad": t.get("unidad_medida")})

    def _eliminar_tarifa(self):
        t = self._tarifa_sel()
        if not t:
            _aviso(self, tr("compras.ficha_tarifas", default="Tarifas"),
                   tr("compras.ficha_sel_tarifa", default="Selecciona una tarifa de la tabla."), "warning")
            return
        if not _confirmar(self, tr("compras.eliminar", default="Eliminar"),
                          tr("compras.ficha_del_tarifa", default="¿Eliminar la tarifa de «{c}»?",
                             c=t.get("codigo"))):
            return
        from src.services.compras import proveedores_pro as PP
        if PP.eliminar_tarifa(t.get("id"), id_empresa=self._emp):
            self._cargar_tarifas()
        else:
            _aviso(self, tr("compras.ficha_tarifas", default="Tarifas"),
                   tr("compras.ficha_del_err", default="No se pudo eliminar la tarifa."), "error")

    def _importar_tarifas(self):
        from PyQt6.QtWidgets import QFileDialog
        ruta, _ = QFileDialog.getOpenFileName(self, tr("compras.ficha_import_tarifas",
                                                       default="Importar Tarifas"), "",
                                              "Tarifas (*.csv *.xlsx *.xls *.json *.tsv);;Todos (*)")
        if not ruta:
            return
        from src.services.compras import proveedores_pro as PP
        res = PP.importar_tarifas_proveedor(self._pid, ruta, id_empresa=self._emp)
        self._cargar_tarifas()
        _aviso(self, tr("compras.ficha_import_tarifas", default="Importar Tarifas"),
               tr("compras.ficha_import_res",
                  default="Importadas {i} de {t} tarifas ({e} con error).",
                  i=res.get("importadas", 0), t=res.get("total", 0), e=res.get("errores", 0)),
               "success" if res.get("importadas") else "warning")

    # ── c) Condiciones Comerciales y Pago ─────────────────────────────────────
    def _tab_condiciones(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(8)
        p = self._prov
        self.c_forma = _big(_combo([(f or "—", f) for f in self._FORMAS_PAGO],
                                   actual=(p.get("forma_pago") or "")))
        self.c_dias_pago = _big(_inp("0")); self.c_dias_pago.setText(str(p.get("plazo_pago") or ""))
        self.c_iban = _big(_inp("ES00 0000 0000 0000 0000 0000")); self.c_iban.setText(p.get("iban") or "")
        self.c_dias_entrega = _big(_inp("0")); self.c_dias_entrega.setText(str(p.get("lead_time_dias") or ""))
        self.c_pedido_min = _big(_inp("0.00"))
        pm = p.get("pedido_minimo")
        self.c_pedido_min.setText(f"{float(pm):.2f}" if pm not in (None, "") else "")
        lbl = QLabel("💳  " + tr("compras.ficha_pago", default="Condiciones de pago y entrega"))
        lbl.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:13px;")
        ly.addWidget(lbl)
        g = QFormLayout(); g.setHorizontalSpacing(18); g.setVerticalSpacing(8)
        g.addRow(_cap("Forma de pago pactada"), self.c_forma)
        g.addRow(_cap("Días de pago"), self.c_dias_pago)
        g.addRow(_cap("IBAN de abono"), self.c_iban)
        g.addRow(_cap("Días de entrega estimados"), self.c_dias_entrega)
        g.addRow(_cap("Pedido mínimo (€)"), self.c_pedido_min)
        ly.addLayout(g)
        ly.addStretch(1)
        return w

    # ── d) Historial y Documentos ─────────────────────────────────────────────
    def _tab_historial(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(8)
        lp = QLabel("📦  " + tr("compras.ficha_pedidos", default="Histórico de pedidos"))
        lp.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:13px;")
        ly.addWidget(lp)
        self.tbl_hist_ped = _tabla(["Pedido", "Fecha", "Estado", "Total (€)"])
        ly.addWidget(self.tbl_hist_ped, 1)
        lf = QLabel("🧾  " + tr("compras.ficha_facturas", default="Facturas emitidas"))
        lf.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:13px;padding-top:4px;")
        ly.addWidget(lf)
        self.tbl_hist_fac = _tabla(["Factura", "Fecha", "Estado", "Total (€)"])
        ly.addWidget(self.tbl_hist_fac, 1)
        ln = QLabel("📝  " + tr("compras.ficha_notas", default="Notas internas / incidencias"))
        ln.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:13px;padding-top:4px;")
        ly.addWidget(ln)
        self.n_obs = QTextEdit(); self.n_obs.setPlainText(self._prov.get("observaciones") or "")
        self.n_obs.setFixedHeight(90)
        self.n_obs.setStyleSheet(f"QTextEdit{{background:{_BG};color:{_TEXT};border:2px solid {_BORDE};"
                                 f"border-radius:8px;padding:6px;font-size:12px;}}"
                                 f"QTextEdit:focus{{border-color:{_CIAN};}}")
        ly.addWidget(self.n_obs)
        return w

    def _cargar_historial(self):
        def _fecha(d):
            for k in ("fecha", "creado_en", "fecha_pedido", "fecha_factura", "creada"):
                if d.get(k):
                    return str(d[k])[:10]
            return ""
        try:
            peds = C.listar_pedidos(id_empresa=self._emp, id_proveedor=self._pid) or []
        except Exception:
            peds = []
        for d in peds:
            r = self.tbl_hist_ped.rowCount(); self.tbl_hist_ped.insertRow(r)
            vals = [d.get("id_pedido"), _fecha(d), d.get("estado"),
                    f"{float(d.get('total') or 0):.2f}"]
            for c, val in enumerate(vals):
                self.tbl_hist_ped.setItem(r, c, QTableWidgetItem("" if val is None else str(val)))
        try:
            facs = C.listar_facturas(id_empresa=self._emp, id_proveedor=self._pid) or []
        except Exception:
            facs = []
        for d in facs:
            r = self.tbl_hist_fac.rowCount(); self.tbl_hist_fac.insertRow(r)
            vals = [d.get("numero_factura") or d.get("id_factura"), _fecha(d), d.get("estado"),
                    f"{float(d.get('total') or 0):.2f}"]
            for c, val in enumerate(vals):
                self.tbl_hist_fac.setItem(r, c, QTableWidgetItem("" if val is None else str(val)))

    # ── Guardado (Datos Generales + Condiciones + notas) ──────────────────────
    def _guardar(self):
        razon = self.f_razon.text().strip()
        if not razon:
            _aviso(self, tr("compras.proveedores", default="Proveedores"),
                   tr("compras.falta_razon", default="La razón social es obligatoria."), "error")
            return

        def _num(txt, entero=False):
            t = (txt or "").strip().replace(",", ".")
            if not t:
                return None
            try:
                return int(float(t)) if entero else float(t)
            except ValueError:
                return None

        ok = P.actualizar_proveedor(
            self._pid, id_empresa=self._emp,
            razon_social=razon,
            nombre_comercial=self.f_nombre_com.text().strip() or None,
            cif_nif=self.f_cif.text().strip() or None,
            estado=self.f_estado.currentData(),
            email=self.f_email.text().strip() or None,
            telefono=self.f_tel.text().strip() or None,
            persona_contacto=self.f_persona.text().strip() or None,
            web=self.f_web.text().strip() or None,
            forma_pago=self.c_forma.currentData() or None,
            plazo_pago=_num(self.c_dias_pago.text(), entero=True),
            iban=self.c_iban.text().strip() or None,
            lead_time_dias=_num(self.c_dias_entrega.text(), entero=True),
            pedido_minimo=_num(self.c_pedido_min.text()),
            observaciones=self.n_obs.toPlainText().strip() or None)
        _aviso(self, tr("compras.ficha_prov", default="Ficha del proveedor"),
               tr("compras.prov_editado", default="Proveedor actualizado.") if ok
               else tr("compras.prov_no_editado", default="No se pudo actualizar."),
               "success" if ok else "error")
        if ok:
            self.accept()


class _DialogoTarifa(QDialog):
    """Alta/edición de una tarifa de proveedor (código + precio + descuento + unidad)."""

    _UNIDADES = ("unidad", "caja", "pale", "kg")

    def __init__(self, parent=None, base=None):
        super().__init__(parent)
        self.datos = None
        base = base or {}
        self.setFixedSize(440, 340)
        v = _dialogo_frameless(self, titulo=tr("compras.ficha_add_tarifa", default="Artículo / Tarifa"),
                               ancho=440)
        self.in_cod = _inp("Código de artículo"); self.in_cod.setText(str(base.get("codigo") or ""))
        self.in_precio = _inp("0.00")
        if base.get("precio") is not None:
            self.in_precio.setText(f"{float(base['precio']):.2f}")
        self.in_dto = _inp("0")
        if base.get("descuento") is not None:
            self.in_dto.setText(f"{float(base['descuento']):.0f}")
        self.cb_unidad = _combo([(u.capitalize(), u) for u in self._UNIDADES],
                                actual=(base.get("unidad") or "unidad"))
        for lab, wdg in (("Código de artículo", self.in_cod), ("Precio negociado (€)", self.in_precio),
                         ("Descuento (%)", self.in_dto), ("Unidad de medida", self.cb_unidad)):
            v.addWidget(_cap(lab)); v.addWidget(wdg)
        v.addStretch(1)
        row = QHBoxLayout(); row.addStretch(1)
        row.addWidget(_btn(tr("compras.cancelar", default="Cancelar"), self.reject))
        row.addWidget(_btn(tr("compras.guardar", default="Guardar"), self._ok, primary=True))
        v.addLayout(row)

    def _ok(self):
        cod = self.in_cod.text().strip()
        try:
            precio = float((self.in_precio.text() or "0").replace(",", "."))
            dto = float((self.in_dto.text() or "0").replace(",", "."))
        except ValueError:
            return
        if not cod or precio <= 0:
            return
        self.datos = {"codigo": cod, "precio": precio, "descuento": dto,
                      "unidad": self.cb_unidad.currentData()}
        self.accept()


class _DialogoDireccion(QDialog):
    """Alta de una dirección de proveedor (fiscal / almacén) sobre las tablas 0008."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.datos = None
        self.setFixedSize(460, 420)
        v = _dialogo_frameless(self, titulo=tr("compras.ficha_add_dir", default="Añadir dirección"),
                               ancho=460)
        self.cb_tipo = _combo([("Fiscal", "fiscal"), ("Almacén", "almacen"), ("Envío", "envio")])
        self.in_dir = _inp("Dirección"); self.in_cp = _inp("CP")
        self.in_mun = _inp("Municipio"); self.in_prov = _inp("Provincia")
        self.in_pais = _inp("País"); self.in_pais.setText("España")
        for lab, wdg in (("Tipo", self.cb_tipo), ("Dirección", self.in_dir), ("CP", self.in_cp),
                         ("Municipio", self.in_mun), ("Provincia", self.in_prov), ("País", self.in_pais)):
            v.addWidget(_cap(lab)); v.addWidget(wdg)
        v.addStretch(1)
        row = QHBoxLayout(); row.addStretch(1)
        row.addWidget(_btn(tr("compras.cancelar", default="Cancelar"), self.reject))
        row.addWidget(_btn(tr("compras.guardar", default="Guardar"), self._ok, primary=True))
        v.addLayout(row)

    def _ok(self):
        if not self.in_dir.text().strip():
            return
        self.datos = {"tipo": self.cb_tipo.currentData(), "direccion": self.in_dir.text().strip(),
                      "cp": self.in_cp.text().strip() or None, "municipio": self.in_mun.text().strip() or None,
                      "provincia": self.in_prov.text().strip() or None,
                      "pais": self.in_pais.text().strip() or "España"}
        self.accept()


class _DialogoPedido(QDialog):
    def __init__(self, proveedores, parent=None, id_prov_fijo=None):
        super().__init__(parent)
        self.id_proveedor = None; self.lineas = []
        self._provs = proveedores
        # Frameless (sin barra de Windows), esquinas redondeadas, fondo uniforme y más grande.
        self.setFixedSize(640, 720)
        v = _dialogo_frameless(self, titulo=tr("compras.nuevo_pedido", default="Nuevo pedido"), ancho=640)
        cap = QLabel(tr("compras.proveedor", default="Proveedor"))
        cap.setStyleSheet(f"color:{_DIM};background:transparent;font-size:11px;")
        v.addWidget(cap)
        self.cb = _combo([(p["razon_social"], p["id_proveedor"]) for p in proveedores])
        if id_prov_fijo is not None:
            # Modo simple: proveedor ya elegido en la tabla → se fija y se bloquea el desplegable.
            idx = next((i for i, p in enumerate(proveedores) if p["id_proveedor"] == id_prov_fijo), -1)
            if idx >= 0:
                self.cb.setCurrentIndex(idx)
            self.cb.setEnabled(False)
        v.addWidget(self.cb)
        form = QFormLayout()
        self.in_cod = _inp("Código"); self.in_desc = _inp("Descripción")
        self.in_cant = _inp("Cantidad"); self.in_precio = _inp("Precio ud.")
        form.addRow("Código", self.in_cod); form.addRow("Descripción", self.in_desc)
        form.addRow("Cantidad", self.in_cant); form.addRow("Precio ud.", self.in_precio)
        v.addLayout(form)
        self.tbl = _tabla(["Código", "Cant.", "Precio"]); v.addWidget(self.tbl, 1)
        v.addWidget(_btn(tr("compras.add_linea", default="AÑADIR LÍNEA"), self._add))
        row = QHBoxLayout(); row.addStretch(1)
        row.addWidget(_btn(tr("compras.cancelar", default="Cancelar"), self.reject))
        row.addWidget(_btn(tr("compras.aceptar", default="Aceptar"), self._ok, primary=True))
        v.addLayout(row)

    def _add(self):
        try:
            cant = int(self.in_cant.text() or 0); precio = float(self.in_precio.text() or 0)
        except ValueError:
            return
        if not self.in_cod.text().strip() or cant <= 0:
            return
        self.lineas.append({"codigo": self.in_cod.text().strip(), "descripcion": self.in_desc.text().strip(),
                            "cantidad": cant, "precio_unitario": precio})
        r = self.tbl.rowCount(); self.tbl.insertRow(r)
        self.tbl.setItem(r, 0, QTableWidgetItem(self.in_cod.text().strip()))
        self.tbl.setItem(r, 1, QTableWidgetItem(str(cant)))
        self.tbl.setItem(r, 2, QTableWidgetItem(str(precio)))
        for x in (self.in_cod, self.in_desc, self.in_cant, self.in_precio):
            x.clear()

    def _ok(self):
        i = self.cb.currentIndex()
        if 0 <= i < len(self._provs) and self.lineas:
            self.id_proveedor = self._provs[i]["id_proveedor"]
            self.accept()
        else:
            self.reject()


class _DialogoFactura(QDialog):
    def __init__(self, proveedores, parent=None):
        super().__init__(parent)
        self.id_proveedor = None; self.numero = None; self.base = 0.0; self.iva = 0.0
        self._provs = proveedores
        self.setFixedSize(520, 380)
        v = _dialogo_frameless(self, titulo=tr("compras.nueva_factura", default="Nueva factura"), ancho=520)
        form = QFormLayout()
        self.cb = _combo([(p["razon_social"], p["id_proveedor"]) for p in proveedores])
        self.in_num = _inp("Nº factura"); self.in_base = _inp("Base"); self.in_iva = _inp("IVA")
        form.addRow(tr("compras.proveedor", default="Proveedor"), self.cb)
        form.addRow("Nº factura", self.in_num); form.addRow("Base", self.in_base); form.addRow("IVA", self.in_iva)
        v.addLayout(form); v.addStretch(1)
        row = QHBoxLayout(); row.addStretch(1)
        row.addWidget(_btn(tr("compras.cancelar", default="Cancelar"), self.reject))
        row.addWidget(_btn(tr("compras.aceptar", default="Aceptar"), self._ok, primary=True))
        v.addLayout(row)

    def _ok(self):
        i = self.cb.currentIndex()
        if not (0 <= i < len(self._provs)) or not self.in_num.text().strip():
            self.reject(); return
        try:
            self.base = float(self.in_base.text() or 0); self.iva = float(self.in_iva.text() or 0)
        except ValueError:
            self.reject(); return
        self.id_proveedor = self._provs[i]["id_proveedor"]; self.numero = self.in_num.text().strip()
        self.accept()
