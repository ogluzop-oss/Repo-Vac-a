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
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (QDialog, QFormLayout,
                             QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton, QStackedWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from src.db import compras as C
from src.db import proveedores as P
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _SIDEBAR, _TEXT, _btn, _btn_cargando,
                                      _btn_salir_sidebar, _combo, _dialogo_frameless, _inp, _tabla)
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
        # Columna "Acciones": lápiz de edición (emoji) por proveedor, centrado y completo.
        for r in range(self.tbl_prov.rowCount()):
            b = QPushButton("✏️"); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedSize(34, 30)
            b.setToolTip(tr("compras.editar_prov", default="Editar proveedor"))
            b.setStyleSheet("QPushButton{background:transparent;border:none;font-size:14px;padding:0;}"
                            "QPushButton:hover{background:#1A2230;border-radius:6px;}")
            b.clicked.connect(lambda _=False, row=r: self._editar_proveedor(row))
            cont = QWidget(); lay = QHBoxLayout(cont); lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignCenter)
            self.tbl_prov.setCellWidget(r, 6, cont)

    def _editar_proveedor(self, row):
        """Abre un diálogo para editar el proveedor de la fila. Los cambios se propagan a todas las
        pantallas (misma BD)."""
        it = self.tbl_prov.item(row, 0)
        if not it:
            return
        try:
            pid = int(it.text())
        except ValueError:
            return
        def _txt(c):
            x = self.tbl_prov.item(row, c)
            return x.text() if x else ""
        dlg = _DialogoEditarProveedor({"razon_social": _txt(1), "cif_nif": _txt(2),
                                       "email": _txt(3), "telefono": _txt(4)}, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.datos:
            return
        d = dlg.datos
        if not d["razon_social"]:
            _aviso(self, tr("compras.proveedores", default="Proveedores"),
                   tr("compras.falta_razon", default="La razón social es obligatoria."), "error"); return
        ok = P.actualizar_proveedor(pid, razon_social=d["razon_social"], cif_nif=d["cif_nif"] or None,
                                    email=d["email"] or None, telefono=d["telefono"] or None)
        self._load_proveedores()
        _aviso(self, tr("compras.proveedores", default="Proveedores"),
               tr("compras.prov_editado", default="Proveedor actualizado.") if ok
               else tr("compras.prov_no_editado", default="No se pudo actualizar."),
               "success" if ok else "error")

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
        mbar.addWidget(_btn("🛒  " + tr("compras.comprar_ya", default="COMPRAR YA"),
                            self._comprar_ya, primary=True))
        mbar.addWidget(_btn("👁  " + tr("compras.watchlist", default="AÑADIR A WATCHLIST"),
                            self._add_watchlist, primary=True))
        mbar.addStretch(1)
        ly.addLayout(mbar)
        # Tabla UNIFICADA: tarifas fijas (tuyas) + ofertas en vivo del mercado (Lonja), clasificadas por
        # ORIGEN, con precio en divisa original + convertido a tu divisa de referencia.
        self.tbl_bolsa = _tabla([tr("compras.origen", default="Origen"),
                                 tr("compras.proveedor", default="Proveedor"),
                                 tr("compras.precio", default="Precio"),
                                 tr("compras.divisa", default="Divisa"),
                                 tr("compras.precio_ref", default="Precio ref."),
                                 tr("compras.puja_min", default="Puja mín."),
                                 tr("compras.disponible", default="Disponible"),
                                 tr("compras.unidad", default="Unidad")])
        # Doble clic → comprar ya (tarifa: a la cola; en vivo: compra directa del mercado).
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
        """Unifica en la bolsa: TARIFAS fijas locales (origen 'tarifa', `proveedor_precios_negociados`) +
        CATÁLOGO REMOTO en tiempo real del conector B2B (origen 'b2b')."""
        cod = (self.in_bolsa_art.text() or "").strip().upper()
        self.tbl_bolsa.setRowCount(0)
        self._bolsa_rows = []
        if not cod:
            return
        self._bolsa_cod = cod
        idp_sel = self.cmb_bolsa_prov.currentData()
        orden, desc = self.cmb_bolsa_orden.currentData() or ("precio", False)
        filas = []
        # 1) Tarifas fijas locales.
        try:
            from src.services.compras import proveedores_pro as PP
            for t in PP.bolsa_precios(cod, id_proveedor=idp_sel,
                                      orden=("proveedor" if orden == "proveedor" else "precio"),
                                      id_empresa=self._emp_actual()):
                precio = float(t.get("precio_neto") if t.get("precio_neto") is not None
                               else (t.get("precio") or 0))
                filas.append({"origen": "tarifa", "proveedor": t.get("proveedor"), "precio": precio,
                              "divisa": t.get("divisa") or "EUR", "precio_ref": precio, "disponible": None,
                              "unidad": t.get("unidad_medida"), "id_proveedor": t.get("id_proveedor"),
                              "codigo": cod, "ref_externa": None})
        except Exception as e:
            logger.error("bolsa_precios: %s", e)
        # 2) Catálogo remoto B2B (tiempo real; degradable si no hay conector configurado).
        try:
            from src.services.compras import b2b_client as B2B
            for x in B2B.obtener_catalogo(cod, id_empresa=self._emp_actual()):
                precio = float(x.get("precio") or 0)
                filas.append({"origen": "b2b", "proveedor": x.get("proveedor") or "B2B", "precio": precio,
                              "divisa": x.get("divisa") or "EUR", "precio_ref": precio,
                              "disponible": x.get("stock"), "unidad": x.get("unidad"),
                              "id_proveedor": x.get("proveedor_id"), "codigo": x.get("codigo") or cod,
                              "ref_externa": x.get("ref_externa"), "nombre": x.get("nombre")})
        except Exception as e:
            logger.debug("bolsa b2b: %s", e)
        # Precio ref. de mercado (Fase 3): índice histórico de compra, para detectar desvíos.
        self._ref_mercado = self._precio_ref_mercado(cod)
        if orden == "proveedor":
            filas.sort(key=lambda f: (f.get("proveedor") or ""))
        else:
            filas.sort(key=lambda f: (f.get("precio_ref") if f.get("precio_ref") is not None else 1e18),
                       reverse=bool(desc))
        self._bolsa_rows = filas
        self._bolsa_ref = "EUR"
        ref = self._ref_mercado
        try:
            from src.services.compras import precios_dinamicos as PD
            umbral = PD._reglas(self._emp_actual())[0]
        except Exception:
            PD = None; umbral = 10.0
        verde, rojo = QColor("#3FB950"), QColor("#F85149")
        for r in filas:
            row = self.tbl_bolsa.rowCount(); self.tbl_bolsa.insertRow(row)
            origen = "B2B" if r["origen"] == "b2b" else "Tarifa"
            pref = f"{ref:.2f} EUR" if ref is not None else "—"
            disp = "—" if r.get("disponible") is None else f"{float(r['disponible']):.0f}"
            precio = float(r.get("precio") or 0)
            # Monitor de desvíos (emulación Google Shopping): verde = oportunidad, rojo = incremento.
            desvio = PD.evaluar_desvio(precio, ref, umbral) if PD else "normal"
            flecha = {"oportunidad": "▼ ", "alerta": "▲ "}.get(desvio, "")
            vals = [origen, r.get("proveedor"), f"{flecha}{precio:.2f}", r.get("divisa"),
                    pref, "—", disp, r.get("unidad")]
            for c, v in enumerate(vals):
                it = QTableWidgetItem("" if v is None else str(v))
                if c == 2 and desvio == "oportunidad":
                    it.setForeground(verde)
                elif c == 2 and desvio == "alerta":
                    it.setForeground(rojo)
                elif r["origen"] == "b2b" and c != 2:
                    it.setForeground(QColor(_CIAN))
                self.tbl_bolsa.setItem(row, c, it)
        if not filas:
            _aviso(self, tr("compras.bolsa_titulo", default="Bolsa"),
                   tr("compras.bolsa_vacia2", default="No hay tarifas ni catálogo B2B para ese artículo."),
                   "info")
            return
        # Motor de precios dinámicos: sugerencia de PVP si la variación de coste es significativa.
        if PD is not None:
            try:
                coste = PD.coste_mas_bajo(filas)
                sug = PD.sugerencia_precio_venta(cod, coste, id_empresa=self._emp_actual())
                self._sugerencia_pvp(sug)
            except Exception as e:
                logger.debug("sugerencia PVP: %s", e)

    def _precio_ref_mercado(self, codigo):
        """Precio de referencia (índice de mercado) = último coste de compra del artículo (histórico ERP)."""
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

    def _add_watchlist(self):
        """Añade el artículo buscado a la watchlist de monitorización de coste."""
        cod = getattr(self, "_bolsa_cod", None)
        if not cod:
            _aviso(self, "Watchlist", tr("compras.wl_busca",
                                         default="Busca un artículo antes de añadirlo a la watchlist."),
                   "warning")
            return
        from src.services.compras import precios_dinamicos as PD
        if PD.añadir_watchlist(cod, id_empresa=self._emp_actual()):
            _aviso(self, "Watchlist", tr("compras.wl_ok", default="«{c}» añadido a la watchlist.", c=cod),
                   "success")
        else:
            _aviso(self, "Watchlist", tr("compras.wl_err", default="No se pudo añadir a la watchlist."),
                   "error")

    def _bolsa_sel(self):
        r = self.tbl_bolsa.currentRow()
        rows = getattr(self, "_bolsa_rows", []) or []
        return rows[r] if 0 <= r < len(rows) else None

    def _bolsa_doble_clic(self, fila_idx, _col):
        """Doble clic → comprar ya (añade a la cola)."""
        rows = getattr(self, "_bolsa_rows", []) or []
        if 0 <= fila_idx < len(rows):
            self._comprar_ya()

    def _comprar_ya(self):
        """Añade la tarifa seleccionada a la cola (pedido a tu proveedor)."""
        fila = self._bolsa_sel()
        if not fila:
            _aviso(self, "Bolsa", tr("compras.bolsa_sel", default="Selecciona una fila de la bolsa."),
                   "warning")
            return
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
        """Crea+envía el pedido ERP estándar (agrupado por proveedor). Para las líneas de origen 'b2b',
        además despacha la orden a la plataforma externa vía b2b_client (en paralelo). Devuelve nº pedidos."""
        from collections import defaultdict
        grupos = defaultdict(list)
        for it in items:
            idp = it.get("id_proveedor") or self._resolver_proveedor_b2b(it)
            grupos[int(idp) if idp else 0].append(it)
        n = 0
        for idp, its in grupos.items():
            if not idp:
                continue
            lineas = [{"codigo": it["codigo"], "cantidad": int(it["cantidad"]),
                       "precio_unitario": float(it["precio"]),
                       "descripcion": f"{it['codigo']} · {it.get('unidad') or 'unidad'}"} for it in its]
            pid = C.crear_pedido(id_proveedor=idp, lineas=lineas, usuario=self.usuario.get("nombre"))
            if pid and C.enviar_pedido(pid):
                n += 1
                b2b_its = [it for it in its if it.get("origen") == "b2b"]
                if b2b_its:
                    self._despachar_b2b(pid, idp, b2b_its)
        return n

    def _resolver_proveedor_b2b(self, it):
        """Resuelve (o crea) un proveedor LOCAL para una línea B2B sin proveedor local, por su nombre."""
        nombre = (it.get("proveedor") or "Proveedor B2B").strip()
        try:
            for p in (P.listar_proveedores(texto=nombre) or []):
                if (p.get("razon_social") or "").strip().lower() == nombre.lower():
                    return p["id_proveedor"]
            return P.crear_proveedor(nombre)
        except Exception as e:
            logger.debug("_resolver_proveedor_b2b: %s", e)
            return None

    def _despachar_b2b(self, id_pedido, id_proveedor, items):
        """Despacha la orden de compra a la plataforma B2B externa (best-effort; el pedido ERP ya existe)."""
        try:
            from src.services.compras import b2b_client as B2B
            payload = {"pedido_erp": id_pedido, "id_proveedor": id_proveedor,
                       "lineas": [{"ref_externa": it.get("ref_externa"), "codigo": it.get("codigo"),
                                   "cantidad": int(it["cantidad"]), "precio": float(it["precio"])}
                                  for it in items]}
            res = B2B.enviar_orden_compra(payload, id_empresa=self._emp_actual())
            if res.get("ok"):
                logger.info("Orden B2B despachada: %s (pedido ERP %s)", res.get("id_externo"), id_pedido)
            else:
                logger.info("Orden B2B no despachada (pedido %s): %s", id_pedido, res.get("mensaje"))
        except Exception as e:
            logger.debug("_despachar_b2b: %s", e)

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
        self._carrito = []
        self._render_carrito()
        self._load_recepciones()
        _aviso(self, tr("compras.tramitar_todos", default="Tramitar todos"),
               tr("compras.tramitar_hecho",
                  default="Se han enviado {n} pedido(s). Puedes verlos en la pestaña Recepciones.", n=n),
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


class _DialogoEditarProveedor(QDialog):
    """Edición de un proveedor (frameless). Guarda vía P.actualizar_proveedor (propaga a toda la app)."""

    def __init__(self, datos, parent=None):
        super().__init__(parent)
        self.datos = None
        self.setFixedSize(460, 360)
        v = _dialogo_frameless(self, titulo=tr("compras.editar_prov", default="Editar proveedor"), ancho=460)
        self.in_razon = _inp("Razón social"); self.in_razon.setText(datos.get("razon_social", ""))
        self.in_cif = _inp("CIF/NIF"); self.in_cif.setText(datos.get("cif_nif", ""))
        self.in_email = _inp("Email"); self.in_email.setText(datos.get("email", ""))
        self.in_tel = _inp("Teléfono"); self.in_tel.setText(datos.get("telefono", ""))
        for lab, wdg in [("Razón social", self.in_razon), ("CIF/NIF", self.in_cif),
                         ("Email", self.in_email), ("Teléfono", self.in_tel)]:
            cap = QLabel(lab); cap.setStyleSheet(f"color:{_DIM};background:transparent;font-weight:700;")
            v.addWidget(cap); v.addWidget(wdg)
        v.addStretch()
        row = QHBoxLayout()
        row.addWidget(_btn(tr("compras.cancelar", default="Cancelar"), self.reject))
        row.addWidget(_btn(tr("compras.guardar", default="Guardar"), self._ok, primary=True))
        v.addLayout(row)

    def _ok(self):
        self.datos = {"razon_social": self.in_razon.text().strip(), "cif_nif": self.in_cif.text().strip(),
                      "email": self.in_email.text().strip(), "telefono": self.in_tel.text().strip()}
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
