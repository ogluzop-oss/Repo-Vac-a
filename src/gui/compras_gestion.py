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
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                             QFrame, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from src.db import compras as C
from src.db import proveedores as P
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _SIDEBAR, _TEXT, _btn, _btn_salir_sidebar,
                                      _combo, _dialogo_frameless, _inp, _tabla)
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
    _SECCIONES = [
        ("prov", "🏭", "Proveedores"),
        ("ped", "📦", "Pedidos"),
        ("rec", "📥", "Recepciones"),
        ("fac", "🧾", "Facturas"),
        ("inf", "📊", "Informes"),
        ("avz", "🤝", "Avanzado"),
        ("portal", "🔗", "Portal proveedor"),
        ("cal", "🔬", "Calidad"),
    ]

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self._prov_sel = None
        self.setWindowTitle("Smart Manager — " + tr("compras.titulo", default="COMPRAS"))

        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        right = QWidget(); rcol = QVBoxLayout(right)
        rcol.setContentsMargins(24, 18, 24, 18); rcol.setSpacing(14)
        rcol.addLayout(self._build_header())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_proveedores())
        self.stack.addWidget(self._page_pedidos())
        self.stack.addWidget(self._page_recepciones())
        self.stack.addWidget(self._page_facturas())
        self.stack.addWidget(self._page_informes())
        self.stack.addWidget(self._page_avanzado())
        self.stack.addWidget(self._page_portal())     # portal de proveedor (enlace bidireccional)
        self.stack.addWidget(self._page_calidad())   # dominio calidad (dashboard embebido)
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
        for i, (sid, icono, defecto) in enumerate(self._SECCIONES):
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
        # Recarga perezosa de la sección.
        [self._load_proveedores, self._load_pedidos, self._load_recepciones,
         self._load_facturas, lambda: self._cargar_informe(), lambda: None,
         lambda: None, lambda: None][idx]()   # Avanzado, Portal y Calidad cargan sus propios datos

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

    def _page_portal(self):
        """Portal de proveedor (enlace bidireccional empresa↔proveedor) embebido. Disponible en todas
        las versiones; la lógica vive en `services.compras.portal`."""
        try:
            from src.gui.portal_proveedor_gui import PortalProveedorWindow
            self._portal_win = PortalProveedorWindow(callback_vuelta=None, usuario=self.usuario, main=self)
            return self._portal_win
        except Exception as e:
            logger.error("embed Portal proveedor: %s", e)
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
        # La importación de tarifas de proveedor se realiza desde el PORTAL DE PROVEEDOR (cada
        # proveedor sube su propia lista de precios), no manualmente desde esta pantalla.
        ly.addLayout(form)
        self.tbl_prov = _tabla(["ID", tr("compras.razon", default="Razón social"), "CIF/NIF",
                                "Email", "Teléfono", tr("compras.estado", default="Estado")])
        self.tbl_prov.cellClicked.connect(self._sel_proveedor)
        ly.addWidget(self.tbl_prov, 1)
        return w

    def _load_proveedores(self):
        texto = self.in_prov_buscar.text().strip() or None
        filas = P.listar_proveedores(texto=texto)
        self._fill(self.tbl_prov, filas, ("id_proveedor", "razon_social", "cif_nif",
                                          "email", "telefono", "estado"))

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
        fila.addWidget(_btn(tr("compras.enviar", default="ENVIAR"), self._enviar_carrito_sel, primary=True))
        fila.addWidget(_btn(tr("compras.desde_reab", default="DESDE REPOSICIÓN"), self._desde_reab, primary=True))
        fila.addWidget(_btn(tr("compras.tramitar_todos", default="TRAMITAR TODOS"),
                            self._tramitar_todos, primary=True))
        # CANCELAR va DETRÁS de "Tramitar todos": retira el artículo seleccionado de la cola.
        fila.addWidget(_btn(tr("compras.cancelar", default="CANCELAR"), self._quitar_carrito_sel, danger=True))
        fila.addStretch(1)
        fila.addWidget(_btn(tr("compras.actualizar", default="🔄  ACTUALIZAR"), self._load_pedidos, primary=True))
        ly.addLayout(fila)

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
        self.tbl_bolsa = _tabla([tr("compras.proveedor", default="Proveedor"),
                                 tr("compras.precio", default="Precio"),
                                 tr("compras.descuento", default="Dto %"),
                                 tr("compras.precio_neto", default="Precio neto"),
                                 tr("compras.unidad", default="Unidad"),
                                 tr("compras.cant_min", default="Cant. mín."),
                                 tr("compras.fecha", default="Fecha")])
        # Doble clic en una tarifa → popup de cantidad → se añade a la cola.
        self.tbl_bolsa.cellDoubleClicked.connect(self._bolsa_doble_clic)
        ly.addWidget(self.tbl_bolsa, 1)
        hint = QLabel(tr("compras.bolsa_hint",
                         default="Doble clic sobre una tarifa para añadir el artículo a la cola."))
        hint.setStyleSheet(f"color:{_DIM};font-size:11px;")
        ly.addWidget(hint)

        # ── Carrito: ARTÍCULOS EN COLA (se agrupan por proveedor al tramitar) ──
        lbl_p = QLabel("🛒  " + tr("compras.cola_titulo", default="Artículos en cola"))
        lbl_p.setStyleSheet(f"color:{_CIAN};font-weight:800;font-size:14px;padding-top:2px;")
        ly.addWidget(lbl_p)
        self.tbl_carrito = _tabla([tr("compras.articulo", default="Artículo"),
                                   tr("compras.precio", default="Precio"),
                                   tr("compras.cantidad", default="Cantidad"),
                                   tr("compras.precio_total", default="Precio total")])
        # Doble clic en un artículo de la cola → editar cantidad (con confirmación).
        self.tbl_carrito.cellDoubleClicked.connect(self._carrito_doble_clic)
        ly.addWidget(self.tbl_carrito, 1)
        return w

    # ── Bolsa de proveedores ─────────────────────────────────────────────────
    def _buscar_bolsa(self):
        """Busca un artículo y muestra las tarifas VIGENTES de cada proveedor (bolsa)."""
        cod = (self.in_bolsa_art.text() or "").strip().upper()
        self.tbl_bolsa.setRowCount(0)
        self._bolsa_rows = []
        if not cod:
            return
        self._bolsa_cod = cod
        from src.services.compras import proveedores_pro as PP
        orden, desc = self.cmb_bolsa_orden.currentData() or ("precio", False)
        self._bolsa_rows = PP.bolsa_precios(cod, id_proveedor=self.cmb_bolsa_prov.currentData(),
                                            orden=orden, descendente=desc)
        for r in self._bolsa_rows:
            row = self.tbl_bolsa.rowCount(); self.tbl_bolsa.insertRow(row)
            vals = [r.get("proveedor"),
                    f"{float(r.get('precio') or 0):.2f} {r.get('divisa') or ''}".strip(),
                    f"{float(r.get('descuento') or 0):.0f}",
                    f"{float(r.get('precio_neto') or 0):.2f}",
                    r.get("unidad_medida"), r.get("cantidad_minima"),
                    str(r.get("fecha") or "")[:10]]
            for c, v in enumerate(vals):
                self.tbl_bolsa.setItem(row, c, QTableWidgetItem("" if v is None else str(v)))
        if not self._bolsa_rows:
            _aviso(self, tr("compras.bolsa_titulo", default="Bolsa"),
                   tr("compras.bolsa_vacia",
                      default="Ningún proveedor tiene tarifa vigente para ese artículo."), "info")

    def _bolsa_doble_clic(self, fila_idx, _col):
        """Doble clic en una tarifa de la bolsa → pide cantidad y añade el artículo a la cola."""
        rows = getattr(self, "_bolsa_rows", []) or []
        if not (0 <= fila_idx < len(rows)):
            return
        fila = rows[fila_idx]
        dlg = _DialogoCantidad(tr("compras.cuantas_uds", default="¿Cuántas unidades?"),
                               f"{self._bolsa_cod} · {fila.get('proveedor')}", 1, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.cantidad:
            self._agregar_carrito(fila, dlg.cantidad)

    # ── Carrito (artículos en cola) ──────────────────────────────────────────
    def _agregar_carrito(self, fila, cant):
        """Añade una tarifa a la cola. Si ya está el mismo artículo/proveedor/unidad, suma cantidad."""
        precio = float(fila.get("precio_neto") or fila.get("precio") or 0)
        idp = int(fila["id_proveedor"]); uni = fila.get("unidad_medida")
        for it in self._carrito:
            if it["codigo"] == self._bolsa_cod and it["id_proveedor"] == idp and it["unidad"] == uni:
                it["cantidad"] += int(cant)
                break
        else:
            self._carrito.append({"codigo": self._bolsa_cod, "id_proveedor": idp,
                                  "proveedor": fila.get("proveedor"), "precio": precio,
                                  "cantidad": int(cant), "unidad": uni})
        self._render_carrito()

    def _render_carrito(self):
        """Pinta la cola como un carrito: artículo · precio · cantidad · precio total + fila TOTAL."""
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
        # Fila TOTAL (resaltada) con el precio total de todos los artículos.
        r = t.rowCount(); t.insertRow(r)
        neg = QFont(); neg.setBold(True)
        celda_tot = QTableWidgetItem(tr("compras.total", default="TOTAL").upper())
        celda_val = QTableWidgetItem(f"{total:.2f}")
        for cel in (celda_tot, celda_val):
            cel.setFont(neg); cel.setForeground(QColor(_CIAN))
        t.setItem(r, 0, celda_tot)
        t.setItem(r, 1, QTableWidgetItem("")); t.setItem(r, 2, QTableWidgetItem(""))
        t.setItem(r, 3, celda_val)

    def _load_pedidos(self):
        """Al entrar en Pedidos / pulsar ACTUALIZAR: repinta la cola (carrito, en memoria)."""
        self._render_carrito()

    def _carrito_sel_idx(self):
        """Índice del artículo seleccionado en la cola (la fila TOTAL queda excluida)."""
        r = self.tbl_carrito.currentRow() if hasattr(self, "tbl_carrito") else -1
        return r if 0 <= r < len(self._carrito) else None

    def _carrito_doble_clic(self, fila_idx, _col):
        """Doble clic en un artículo de la cola → editar cantidad (con confirmación)."""
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

    def _quitar_carrito_sel(self):
        """CANCELAR: retira de la cola el artículo seleccionado (con confirmación)."""
        idx = self._carrito_sel_idx()
        if idx is None:
            _aviso(self, tr("compras.cola_titulo", default="Artículos en cola"),
                   tr("compras.cola_sel", default="Selecciona un artículo de la cola."), "warning")
            return
        it = self._carrito[idx]
        if _confirmar(self, tr("compras.retirar", default="Retirar de la cola"),
                      tr("compras.retirar_msg", default="¿Retirar {c} ({p}) de la cola?",
                         c=it["codigo"], p=it.get("proveedor") or "")):
            del self._carrito[idx]
            self._render_carrito()

    def _tramitar_lineas(self, items):
        """Agrupa artículos por proveedor y crea+envía un pedido por proveedor. Devuelve nº de pedidos."""
        from collections import defaultdict
        grupos = defaultdict(list)
        for it in items:
            grupos[int(it["id_proveedor"])].append(it)
        n = 0
        for idp, its in grupos.items():
            lineas = [{"codigo": it["codigo"], "cantidad": int(it["cantidad"]),
                       "precio_unitario": float(it["precio"]),
                       "descripcion": f"{it['codigo']} · {it.get('unidad') or 'unidad'}"} for it in its]
            pid = C.crear_pedido(id_proveedor=idp, lineas=lineas, usuario=self.usuario.get("nombre"))
            if pid and C.enviar_pedido(pid):
                n += 1
        return n

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
        """NUEVO PEDIDO: alta manual de artículos (proveedor + líneas) que se añaden a la cola."""
        provs = P.listar_proveedores(estado="activo")
        if not provs:
            _aviso(self, "Compras", tr("compras.sin_prov", default="Cree un proveedor primero."), "error")
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
        """DESDE REPOSICIÓN: genera el pedido con las propuestas de reposición y lo tramita
        (queda ENVIADO) para que aparezca directamente en la pestaña Recepciones."""
        pid = C.crear_pedido_desde_propuestas()
        if pid:
            C.enviar_pedido(pid)
            self._load_recepciones()
            _aviso(self, "Compras",
                   tr("compras.reab_ok",
                      default="Pedido de reposición enviado. Puedes verlo en la pestaña Recepciones."))
        else:
            _aviso(self, "Compras", tr("compras.reab_vacio", default="No hay propuestas pendientes."), "warning")

    # ── Sección Recepciones ──────────────────────────────────────────────────
    def _page_recepciones(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10); ly.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        fila.addWidget(QLabel(tr("compras.pedidos_recep", default="Pedidos pendientes de recibir")))
        fila.addStretch(1)
        fila.addWidget(_btn(tr("compras.recibir_todo", default="RECIBIR TODO"), self._recibir_sel, primary=True))
        fila.addWidget(_btn(tr("compras.actualizar", default="🔄  ACTUALIZAR"), self._load_recepciones, primary=True))
        ly.addLayout(fila)
        # "Estado prov." = seguimiento que el proveedor reporta desde el Portal (bidireccional).
        self.tbl_rec = _tabla(["ID", tr("compras.numero", default="Número"),
                               tr("compras.proveedor", default="Proveedor"),
                               tr("compras.estado", default="Estado"),
                               tr("compras.estado_prov", default="Estado prov."),
                               tr("compras.total", default="Total"), tr("compras.fecha", default="Fecha")])
        ly.addWidget(self.tbl_rec, 1)
        return w

    def _load_recepciones(self):
        filas = [p for p in C.historico_pedidos() if p["estado"] in ("ENVIADO", "PARCIAL")]
        # Estado reportado por el proveedor desde el Portal (si lo hay), por pedido.
        try:
            from src.services.compras import portal
            segui = portal.estados_pedidos(ids=[p["id_pedido"] for p in filas] or None)
        except Exception:
            segui = {}
        for p in filas:
            p["estado_prov"] = segui.get(p["id_pedido"], "—")
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
        fila.addWidget(_btn(tr("compras.actualizar", default="🔄  ACTUALIZAR"), self._load_facturas, primary=True))
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
        fila.addWidget(_btn(tr("compras.actualizar", default="🔄  ACTUALIZAR"), self._cargar_informe, primary=True))
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


class _DialogoPedido(QDialog):
    def __init__(self, proveedores, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("compras.nuevo_pedido", default="Nuevo pedido"))
        self.id_proveedor = None; self.lineas = []
        self._provs = proveedores
        ly = QVBoxLayout(self)
        self.cb = _combo([p["razon_social"] for p in proveedores])
        ly.addWidget(QLabel(tr("compras.proveedor", default="Proveedor"))); ly.addWidget(self.cb)
        form = QFormLayout()
        self.in_cod = _inp("Código"); self.in_desc = _inp("Descripción")
        self.in_cant = _inp("Cantidad"); self.in_precio = _inp("Precio ud.")
        form.addRow("Código", self.in_cod); form.addRow("Descripción", self.in_desc)
        form.addRow("Cantidad", self.in_cant); form.addRow("Precio ud.", self.in_precio)
        ly.addLayout(form)
        self.tbl = _tabla(["Código", "Cant.", "Precio"]); ly.addWidget(self.tbl)
        ly.addWidget(_btn(tr("compras.add_linea", default="AÑADIR LÍNEA"), self._add))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject)
        ly.addWidget(bb)

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
        self.setWindowTitle(tr("compras.nueva_factura", default="Nueva factura"))
        self.id_proveedor = None; self.numero = None; self.base = 0.0; self.iva = 0.0
        self._provs = proveedores
        ly = QVBoxLayout(self); form = QFormLayout()
        self.cb = _combo([p["razon_social"] for p in proveedores])
        self.in_num = _inp("Nº factura"); self.in_base = _inp("Base"); self.in_iva = _inp("IVA")
        form.addRow(tr("compras.proveedor", default="Proveedor"), self.cb)
        form.addRow("Nº factura", self.in_num); form.addRow("Base", self.in_base); form.addRow("IVA", self.in_iva)
        ly.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject)
        ly.addWidget(bb)

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
