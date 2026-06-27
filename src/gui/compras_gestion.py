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
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QFrame,
                             QHBoxLayout, QLabel, QPushButton, QStackedWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from src.db import compras as C
from src.db import proveedores as P
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _SIDEBAR, _btn, _combo,
                                      _inp, _tabla)
from src.utils.i18n import tr

logger = logging.getLogger("gui.compras")

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None


def _aviso(parent, titulo, msg, nivel="info"):
    if mostrar_mensaje is not None:
        mostrar_mensaje(parent, titulo, msg, nivel=nivel)
    else:  # pragma: no cover
        logger.info("%s: %s", titulo, msg)


class ComprasWindow(QWidget):
    _SECCIONES = [
        ("prov", "🏭", "Proveedores"),
        ("ped", "📦", "Pedidos"),
        ("rec", "📥", "Recepciones"),
        ("fac", "🧾", "Facturas"),
        ("inf", "📊", "Informes"),
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
        if self._volver:
            cab.addWidget(_btn(tr("compras.volver", default="VOLVER AL MENÚ"),
                               self._volver_menu, primary=True))
        return cab

    def _build_sidebar(self):
        wrap = QFrame(); wrap.setObjectName("sw"); wrap.setFixedWidth(230); self.sidebar = wrap  # P3
        wrap.setStyleSheet(f"#sw{{background:{_SIDEBAR};}}")
        lay = QVBoxLayout(wrap); lay.setContentsMargins(0, 22, 0, 16); lay.setSpacing(2)
        cab = QLabel(tr("compras.secciones", default="GESTIÓN"))
        cab.setStyleSheet(f"color:{_DIM};padding:0 0 8px 24px;font-size:11px;font-weight:bold;")
        lay.addWidget(cab)
        self._sb_btns = []
        for i, (sid, icono, defecto) in enumerate(self._SECCIONES):
            b = QPushButton(f"  {icono}   {tr('compras.sec_' + sid, default=defecto)}")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, idx=i: self._ir(idx))
            self._sb_btns.append(b); lay.addWidget(b)
        lay.addStretch(1)
        return wrap

    _SS_OFF = (f"QPushButton{{background:transparent;color:{_DIM};text-align:left;"
               f"padding:8px 8px 8px 24px;border:none;font-size:13px;}}"
               f"QPushButton:hover{{background:#FFFFFF;color:{_SIDEBAR};}}")
    _SS_ON = (f"QPushButton{{background:{_CIAN};color:{_BG};text-align:left;"
              f"padding:8px 8px 8px 24px;border:none;font-size:13px;font-weight:bold;}}")

    def _ir(self, idx):
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self._sb_btns):
            b.setStyleSheet(self._SS_ON if i == idx else self._SS_OFF)
        # Recarga perezosa de la sección.
        [self._load_proveedores, self._load_pedidos, self._load_recepciones,
         self._load_facturas, lambda: self._cargar_informe()][idx]()

    def _volver_menu(self):
        if callable(self._volver):
            self._volver()

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
        form.addWidget(_btn(tr("compras.nuevo", default="NUEVO"), self._nuevo_proveedor))
        form.addWidget(_btn(tr("compras.guardar", default="GUARDAR"), self._guardar_proveedor, primary=True))
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
        fila = QHBoxLayout()
        fila.addWidget(_btn(tr("compras.nuevo_pedido", default="NUEVO PEDIDO"), self._dlg_nuevo_pedido, primary=True))
        fila.addWidget(_btn(tr("compras.enviar", default="ENVIAR"), self._enviar_pedido_sel))
        fila.addWidget(_btn(tr("compras.cancelar", default="CANCELAR"), self._cancelar_pedido_sel, danger=True))
        fila.addWidget(_btn(tr("compras.desde_reab", default="DESDE REPOSICIÓN"), self._desde_reab))
        fila.addStretch(1)
        fila.addWidget(_btn(tr("compras.refrescar", default="REFRESCAR"), self._load_pedidos))
        ly.addLayout(fila)
        self.tbl_ped = _tabla(["ID", tr("compras.numero", default="Número"),
                               tr("compras.proveedor", default="Proveedor"),
                               tr("compras.estado", default="Estado"),
                               tr("compras.total", default="Total"), tr("compras.fecha", default="Fecha")])
        ly.addWidget(self.tbl_ped, 1)
        return w

    def _load_pedidos(self):
        filas = C.historico_pedidos()
        self._fill(self.tbl_ped, filas, ("id_pedido", "numero", "proveedor", "estado", "total", "fecha"))

    def _pedido_sel_id(self):
        r = self.tbl_ped.currentRow()
        if r < 0:
            return None
        try:
            return int(self.tbl_ped.item(r, 0).text())
        except Exception:
            return None

    def crear_pedido(self, id_proveedor, lineas):
        """Crea un pedido (BORRADOR). Núcleo testeable usado por el diálogo."""
        pid = C.crear_pedido(id_proveedor=id_proveedor, lineas=lineas,
                             usuario=self.usuario.get("nombre"))
        self._load_pedidos()
        return pid

    def _dlg_nuevo_pedido(self):
        provs = P.listar_proveedores(estado="activo")
        if not provs:
            _aviso(self, "Compras", tr("compras.sin_prov", default="Cree un proveedor primero."), "error")
            return
        dlg = _DialogoPedido(provs, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.lineas:
            self.crear_pedido(dlg.id_proveedor, dlg.lineas)

    def _enviar_pedido_sel(self):
        pid = self._pedido_sel_id()
        if pid and C.enviar_pedido(pid):
            self._load_pedidos()

    def _cancelar_pedido_sel(self):
        pid = self._pedido_sel_id()
        if pid and C.cancelar_pedido(pid):
            self._load_pedidos()

    def _desde_reab(self):
        pid = C.crear_pedido_desde_propuestas()
        if pid:
            _aviso(self, "Compras", tr("compras.reab_ok", default="Pedido borrador creado desde reposición."))
            self._load_pedidos()
        else:
            _aviso(self, "Compras", tr("compras.reab_vacio", default="No hay propuestas pendientes."), "warning")

    # ── Sección Recepciones ──────────────────────────────────────────────────
    def _page_recepciones(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10); ly.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        fila.addWidget(QLabel(tr("compras.pedidos_recep", default="Pedidos pendientes de recibir")))
        fila.addStretch(1)
        fila.addWidget(_btn(tr("compras.recibir_todo", default="RECIBIR TODO"), self._recibir_sel, primary=True))
        fila.addWidget(_btn(tr("compras.refrescar", default="REFRESCAR"), self._load_recepciones))
        ly.addLayout(fila)
        self.tbl_rec = _tabla(["ID", tr("compras.numero", default="Número"),
                               tr("compras.proveedor", default="Proveedor"),
                               tr("compras.estado", default="Estado"), tr("compras.total", default="Total")])
        ly.addWidget(self.tbl_rec, 1)
        return w

    def _load_recepciones(self):
        filas = [p for p in C.historico_pedidos() if p["estado"] in ("ENVIADO", "PARCIAL")]
        self._fill(self.tbl_rec, filas, ("id_pedido", "numero", "proveedor", "estado", "total"))

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
        fila.addWidget(_btn(tr("compras.validar", default="VALIDAR"), self._validar_factura_sel))
        fila.addStretch(1)
        fila.addWidget(_btn(tr("compras.refrescar", default="REFRESCAR"), self._load_facturas))
        ly.addLayout(fila)
        self.tbl_fac = _tabla(["ID", tr("compras.numero", default="Nº factura"),
                               tr("compras.pedido", default="Pedido"),
                               tr("compras.total", default="Total"), tr("compras.estado", default="Estado")])
        ly.addWidget(self.tbl_fac, 1)
        return w

    def _load_facturas(self):
        filas = C.listar_facturas()
        self._fill(self.tbl_fac, filas, ("id_factura", "numero_factura", "id_pedido", "total", "estado"))

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
        fila.addWidget(_btn(tr("compras.refrescar", default="REFRESCAR"), self._cargar_informe))
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
            self.tbl_inf.setColumnCount(4)
            self.tbl_inf.setHorizontalHeaderLabels(["Número", "Proveedor", "Estado", "Total"])
            self._fill(self.tbl_inf, C.historico_pedidos(), ("numero", "proveedor", "estado", "total"))

    # ── Utilidad de tablas ───────────────────────────────────────────────────
    @staticmethod
    def _fill(tabla, filas, claves):
        tabla.setRowCount(0)
        for f in filas:
            r = tabla.rowCount(); tabla.insertRow(r)
            for c, k in enumerate(claves):
                tabla.setItem(r, c, QTableWidgetItem("" if f.get(k) is None else str(f.get(k))))


# ── Diálogos mínimos ─────────────────────────────────────────────────────────
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
