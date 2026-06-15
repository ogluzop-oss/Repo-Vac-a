"""
GESTIÓN DE CATÁLOGO ONLINE — panel operativo interno (Fase 2).

Administra el overlay de catálogo sobre `articulos` (ver src/db/catalogo.py):
productos (alta desde artículos + ficha web), categorías/subcategorías, marcas,
etiquetas, galerías de imágenes, atributos, variantes, destacados/recomendados,
visibilidad web y SEO. Multiempresa/multitienda (usa la `vista_operativa`).

Barra lateral al estilo del resto de la app (Centro Documental / Logística).
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                             QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QPlainTextEdit, QPushButton, QSpinBox, QStackedWidget,
                             QTableWidget, QTableWidgetItem, QTabWidget,
                             QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from src.db import catalogo as cat
from src.utils.i18n import tr

try:
    from assets.estilo_global import mostrar_confirmacion, mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = mostrar_confirmacion = None

logger = logging.getLogger("gui.catalogo")

_BG = "#0E1117"
_BG2 = "#161B22"
_SIDEBAR = "#111418"
_CIAN = "#00FFC6"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_DIM = "#8B949E"
_ROJO = "#F85149"
_FONT = "Segoe UI"


def _aviso(parent, titulo, msg, nivel="info"):
    if mostrar_mensaje:
        mostrar_mensaje(parent, titulo, msg, nivel)


def _confirmar(parent, titulo, msg) -> bool:
    if mostrar_confirmacion:
        return mostrar_confirmacion(parent, titulo, msg)
    return True


def _inp(ph="", w=None) -> QLineEdit:
    e = QLineEdit(); e.setFixedHeight(34); e.setPlaceholderText(ph)
    if w:
        e.setFixedWidth(w)
    e.setStyleSheet(f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                    f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
                    f"QLineEdit:focus{{border-color:{_CIAN};}}")
    return e


def _btn(txt, slot=None, primary=False, danger=False) -> QPushButton:
    b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(34)
    c, bg, bd = ((_ROJO, _BG2, _ROJO) if danger else
                 (_CIAN, _BG2, _CIAN) if primary else (_DIM, _BG2, _BORDE))
    b.setStyleSheet(f"QPushButton{{background:{bg};color:{c};border:2px solid {bd};border-radius:8px;"
                    f"font-weight:900;font-size:12px;padding:0 14px;font-family:'{_FONT}';}}"
                    f"QPushButton:hover{{background:{c};color:{_BG};border-color:{c};}}")
    if slot:
        b.clicked.connect(slot)
    return b


def _lbl(txt, dim=True, size=12, bold=True):
    l = QLabel(txt)
    l.setStyleSheet(f"color:{_DIM if dim else _TEXT};font-family:'{_FONT}';"
                    f"font-weight:{'900' if bold else '500'};font-size:{size}px;background:transparent;")
    return l


def _combo(opciones, actual=None) -> QComboBox:
    cb = QComboBox(); cb.setFixedHeight(34)
    cb.setStyleSheet(
        f"QComboBox{{combobox-popup:0;background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
        f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
        f"QComboBox:hover,QComboBox:on{{border-color:{_CIAN};}}"
        f"QComboBox::drop-down{{border:none;width:22px;}}"
        f"QComboBox QAbstractItemView{{background:#0D1117;color:{_TEXT};border:2px solid {_CIAN};"
        f"border-radius:8px;selection-background-color:{_CIAN};selection-color:#0D1117;}}")
    for etq, val in opciones:
        cb.addItem(etq, val)
    if actual is not None:
        i = cb.findData(actual)
        if i >= 0:
            cb.setCurrentIndex(i)
    return cb


def _chk(txt, val=False) -> QCheckBox:
    c = QCheckBox(txt); c.setChecked(bool(val)); c.setCursor(Qt.CursorShape.PointingHandCursor)
    c.setStyleSheet(f"QCheckBox{{color:{_TEXT};font-family:'{_FONT}';font-size:12px;font-weight:700;}}"
                    f"QCheckBox::indicator{{width:18px;height:18px;}}")
    return c


def _tabla(cols) -> QTableWidget:
    t = QTableWidget(0, len(cols))
    t.setHorizontalHeaderLabels(cols)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(40)
    t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    t.setStyleSheet(f"""
        QTableWidget{{background:transparent;color:{_TEXT};border:none;gridline-color:{_BORDE};
                      font-family:'{_FONT}';font-size:13px;outline:none;}}
        QHeaderView::section{{background:{_BG};color:{_CIAN};border:none;
                              border-bottom:2px solid {_BORDE};padding:8px;font-weight:900;font-size:11px;}}
        QTableWidget::item{{padding:6px;}}
        QTableWidget::item:selected{{background:#00FFC622;color:white;}}""")
    return t


def _wrap_tabla(t) -> QFrame:
    w = QFrame(); w.setObjectName("tw")
    w.setStyleSheet(f"QFrame#tw{{background:{_BG2};border:2px solid {_CIAN};border-radius:14px;}}")
    ly = QVBoxLayout(w); ly.setContentsMargins(5, 5, 5, 5); ly.addWidget(t)
    return w


# ════════════════════════════════════════════════════════════════════════════
# Editor de ficha de producto (overlay + galería/atributos/variantes/etiquetas)
# ════════════════════════════════════════════════════════════════════════════
class _ProductoEditor(QDialog):
    def __init__(self, codigo_articulo, nombre_articulo="", parent=None):
        super().__init__(parent)
        self._cod = codigo_articulo
        self._nombre = nombre_articulo
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(720, 640)
        # Garantiza overlay (crea si no existe) y carga la ficha.
        cat.upsert_producto(codigo_articulo)
        self._prod = cat.obtener_producto(codigo_articulo=codigo_articulo)
        self._pid = self._prod["id"]
        self._build()

    def _txtarea(self, val=""):
        t = QPlainTextEdit(); t.setPlainText(val or ""); t.setFixedHeight(70)
        t.setStyleSheet(f"QPlainTextEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                        f"border-radius:8px;padding:6px;font-size:12px;font-family:'{_FONT}';}}"
                        f"QPlainTextEdit:focus{{border-color:{_CIAN};}}")
        return t

    def _build(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        cuerpo = QFrame(); cuerpo.setObjectName("pe")
        cuerpo.setStyleSheet(f"QFrame#pe{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        outer.addWidget(cuerpo)
        v = QVBoxLayout(cuerpo); v.setContentsMargins(22, 18, 22, 18); v.setSpacing(10)
        hdr = QHBoxLayout()
        hdr.addWidget(_lbl(f"📦  {self._nombre or self._cod}  ·  {self._cod}", dim=False, size=15))
        hdr.addStretch()
        bx = QPushButton("✕"); bx.setFixedSize(34, 34); bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet(f"QPushButton{{background:{_BG2};color:{_DIM};border:1px solid {_BORDE};"
                         f"border-radius:8px;font-weight:900;}}QPushButton:hover{{color:{_ROJO};border-color:{_ROJO};}}")
        bx.clicked.connect(self.reject); hdr.addWidget(bx)
        v.addLayout(hdr)

        tabs = QTabWidget()
        tabs.setStyleSheet(
            f"QTabWidget::pane{{border:1px solid {_BORDE};border-radius:8px;}}"
            f"QTabBar::tab{{background:{_BG2};color:{_DIM};padding:8px 14px;font-family:'{_FONT}';"
            f"font-weight:900;font-size:11px;border:1px solid {_BORDE};border-bottom:none;}}"
            f"QTabBar::tab:selected{{background:{_CIAN};color:{_BG};}}")
        tabs.addTab(self._tab_ficha(), tr("cat.tab_ficha", default="Ficha"))
        tabs.addTab(self._tab_galeria(), tr("cat.tab_galeria", default="Galería"))
        tabs.addTab(self._tab_atributos(), tr("cat.tab_atributos", default="Atributos"))
        tabs.addTab(self._tab_variantes(), tr("cat.tab_variantes", default="Variantes"))
        v.addWidget(tabs, 1)

        fila = QHBoxLayout()
        fila.addWidget(_btn(tr("cat.eliminar_ficha", default="Quitar del catálogo"), self._eliminar, danger=True))
        fila.addStretch()
        fila.addWidget(_btn(tr("cat.cerrar", default="CERRAR"), self.reject))
        fila.addWidget(_btn(tr("cat.guardar", default="GUARDAR FICHA"), self._guardar, primary=True))
        v.addLayout(fila)

    def _tab_ficha(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(7); ly.setContentsMargins(12, 12, 12, 12)
        p = self._prod
        ly.addWidget(_lbl(tr("cat.titulo_web", default="Título web")))
        self.inp_titulo = _inp(); self.inp_titulo.setText(p.get("titulo_web") or ""); ly.addWidget(self.inp_titulo)
        ly.addWidget(_lbl(tr("cat.desc_web", default="Descripción web")))
        self.inp_desc = self._txtarea(p.get("descripcion_web") or ""); ly.addWidget(self.inp_desc)
        fila = QHBoxLayout()
        colc = QVBoxLayout(); colc.addWidget(_lbl(tr("cat.categoria", default="Categoría")))
        cats = [("—", None)] + _cats_planas()
        self.cmb_cat = _combo(cats, p.get("id_categoria")); colc.addWidget(self.cmb_cat); fila.addLayout(colc)
        colm = QVBoxLayout(); colm.addWidget(_lbl(tr("cat.marca", default="Marca")))
        marcas = [("—", None)] + [(m["nombre"], m["id"]) for m in cat.listar_marcas()]
        self.cmb_marca = _combo(marcas, p.get("id_marca")); colm.addWidget(self.cmb_marca); fila.addLayout(colm)
        colo = QVBoxLayout(); colo.addWidget(_lbl(tr("cat.orden", default="Orden")))
        self.sp_orden = QSpinBox(); self.sp_orden.setRange(0, 99999); self.sp_orden.setValue(int(p.get("orden") or 0))
        self.sp_orden.setFixedHeight(34)
        self.sp_orden.setStyleSheet(f"QSpinBox{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                                    f"border-radius:8px;padding:0 8px;font-size:12px;}}")
        colo.addWidget(self.sp_orden); fila.addLayout(colo)
        ly.addLayout(fila)
        filc = QHBoxLayout()
        self.ck_dest = _chk(tr("cat.destacado", default="Destacado"), p.get("destacado"))
        self.ck_reco = _chk(tr("cat.recomendado", default="Recomendado"), p.get("recomendado"))
        self.ck_vis = _chk(tr("cat.visible", default="Visible en la web"), p.get("visible_web"))
        for c in (self.ck_dest, self.ck_reco, self.ck_vis):
            filc.addWidget(c)
        filc.addStretch(); ly.addLayout(filc)
        ly.addWidget(_lbl(tr("cat.seo_title", default="SEO · título")))
        self.inp_seo_t = _inp(); self.inp_seo_t.setText(p.get("seo_title") or ""); ly.addWidget(self.inp_seo_t)
        ly.addWidget(_lbl(tr("cat.seo_desc", default="SEO · descripción")))
        self.inp_seo_d = _inp(); self.inp_seo_d.setText(p.get("seo_descripcion") or ""); ly.addWidget(self.inp_seo_d)
        ly.addStretch()
        return w

    def _tab_galeria(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(12, 12, 12, 12); ly.setSpacing(8)
        fila = QHBoxLayout()
        self.inp_img = _inp(tr("cat.img_url_ph", default="URL de la imagen (https://… o ruta local)"))
        fila.addWidget(self.inp_img, 1)
        fila.addWidget(_btn(tr("cat.add", default="Añadir"), self._add_imagen, primary=True))
        ly.addLayout(fila)
        self.tbl_img = _tabla([tr("cat.img", default="Imagen"), tr("cat.portada", default="Portada"), ""])
        self.tbl_img.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_img.setColumnWidth(1, 90); self.tbl_img.setColumnWidth(2, 90)
        ly.addWidget(_wrap_tabla(self.tbl_img), 1)
        self._recargar_imagenes()
        return w

    def _recargar_imagenes(self):
        imgs = cat.listar_imagenes(self._pid)
        self.tbl_img.setRowCount(0)
        for im in imgs:
            r = self.tbl_img.rowCount(); self.tbl_img.insertRow(r)
            self.tbl_img.setItem(r, 0, QTableWidgetItem(im.get("url") or ""))
            self.tbl_img.setItem(r, 1, QTableWidgetItem("★" if im.get("es_portada") else ""))
            cont = QWidget(); h = QHBoxLayout(cont); h.setContentsMargins(2, 2, 2, 2); h.setSpacing(4)
            bp = _btn("★", lambda _c, i=im["id"]: self._portada(i)); bp.setFixedWidth(34)
            bd = _btn("🗑", lambda _c, i=im["id"]: self._del_imagen(i), danger=True); bd.setFixedWidth(34)
            h.addWidget(bp); h.addWidget(bd)
            self.tbl_img.setCellWidget(r, 2, cont)

    def _add_imagen(self):
        url = self.inp_img.text().strip()
        if not url:
            return
        cat.anadir_imagen(self._pid, url, es_portada=not cat.listar_imagenes(self._pid))
        self.inp_img.clear(); self._recargar_imagenes()

    def _del_imagen(self, id_img):
        cat.eliminar_imagen(id_img); self._recargar_imagenes()

    def _portada(self, id_img):
        cat.marcar_portada(self._pid, id_img); self._recargar_imagenes()

    def _tab_atributos(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(12, 12, 12, 12); ly.setSpacing(8)
        fila = QHBoxLayout()
        self.inp_attr_n = _inp(tr("cat.attr_nombre", default="Atributo (ej. Color)"))
        self.inp_attr_v = _inp(tr("cat.attr_valor", default="Valor (ej. Azul)"))
        fila.addWidget(self.inp_attr_n); fila.addWidget(self.inp_attr_v)
        fila.addWidget(_btn(tr("cat.add", default="Añadir"), self._add_attr, primary=True))
        ly.addLayout(fila)
        self.tbl_attr = _tabla([tr("cat.attr", default="Atributo"), tr("cat.valor", default="Valor"), ""])
        self.tbl_attr.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_attr.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl_attr.setColumnWidth(2, 60)
        ly.addWidget(_wrap_tabla(self.tbl_attr), 1)
        self._recargar_attr()
        return w

    def _recargar_attr(self):
        self.tbl_attr.setRowCount(0)
        for a in cat.listar_atributos_producto(self._pid):
            r = self.tbl_attr.rowCount(); self.tbl_attr.insertRow(r)
            self.tbl_attr.setItem(r, 0, QTableWidgetItem(a.get("nombre") or ""))
            self.tbl_attr.setItem(r, 1, QTableWidgetItem(a.get("valor") or ""))
            bd = _btn("🗑", lambda _c, i=a["id"]: (cat.eliminar_atributo_producto(i), self._recargar_attr()), danger=True)
            self.tbl_attr.setCellWidget(r, 2, bd)

    def _add_attr(self):
        n = self.inp_attr_n.text().strip(); val = self.inp_attr_v.text().strip()
        if not n:
            return
        cat.set_atributo_producto(self._pid, n, val)
        self.inp_attr_n.clear(); self.inp_attr_v.clear(); self._recargar_attr()

    def _tab_variantes(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(12, 12, 12, 12); ly.setSpacing(8)
        fila = QHBoxLayout()
        self.inp_var_n = _inp(tr("cat.var_nombre", default="Variante (ej. Talla M)"))
        self.inp_var_sku = _inp(tr("cat.var_sku", default="SKU"), 140)
        fila.addWidget(self.inp_var_n); fila.addWidget(self.inp_var_sku)
        fila.addWidget(_btn(tr("cat.add", default="Añadir"), self._add_var, primary=True))
        ly.addLayout(fila)
        self.tbl_var = _tabla([tr("cat.variante", default="Variante"), "SKU", ""])
        self.tbl_var.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_var.setColumnWidth(1, 160); self.tbl_var.setColumnWidth(2, 60)
        ly.addWidget(_wrap_tabla(self.tbl_var), 1)
        self._recargar_var()
        return w

    def _recargar_var(self):
        self.tbl_var.setRowCount(0)
        for vr in cat.listar_variantes(self._pid):
            r = self.tbl_var.rowCount(); self.tbl_var.insertRow(r)
            self.tbl_var.setItem(r, 0, QTableWidgetItem(vr.get("nombre") or ""))
            self.tbl_var.setItem(r, 1, QTableWidgetItem(vr.get("sku") or ""))
            bd = _btn("🗑", lambda _c, i=vr["id"]: (cat.eliminar_variante(i), self._recargar_var()), danger=True)
            self.tbl_var.setCellWidget(r, 2, bd)

    def _add_var(self):
        n = self.inp_var_n.text().strip()
        if not n:
            return
        cat.crear_variante(self._pid, sku=self.inp_var_sku.text().strip() or None, nombre=n)
        self.inp_var_n.clear(); self.inp_var_sku.clear(); self._recargar_var()

    def _guardar(self):
        cat.upsert_producto(
            self._cod, titulo_web=self.inp_titulo.text().strip(),
            descripcion_web=self.inp_desc.toPlainText().strip(),
            id_categoria=self.cmb_cat.currentData(), id_marca=self.cmb_marca.currentData(),
            destacado=1 if self.ck_dest.isChecked() else 0,
            recomendado=1 if self.ck_reco.isChecked() else 0,
            visible_web=1 if self.ck_vis.isChecked() else 0,
            orden=self.sp_orden.value(), seo_title=self.inp_seo_t.text().strip(),
            seo_descripcion=self.inp_seo_d.text().strip())
        self.accept()

    def _eliminar(self):
        if _confirmar(self, tr("cat.titulo", default="CATÁLOGO"),
                      tr("cat.conf_quitar", default="¿Quitar este producto del catálogo online?")):
            cat.eliminar_producto(self._pid)
            self.accept()


def _cats_planas():
    """Categorías aplanadas como [(nombre_indentado, id)] para combos jerárquicos."""
    salida = []

    def rec(nodos, nivel):
        for n in nodos:
            salida.append(("   " * nivel + n["nombre"], n["id"]))
            rec(n.get("hijos", []), nivel + 1)
    rec(cat.arbol_categorias(), 0)
    return salida


# ════════════════════════════════════════════════════════════════════════════
# Ventana principal de gestión del catálogo
# ════════════════════════════════════════════════════════════════════════════
class CatalogoWindow(QWidget):
    """Gestión del catálogo online de la empresa activa (panel operativo interno)."""

    _SECCIONES = [("productos", "📦", "Productos"), ("categorias", "🗂", "Categorías"),
                  ("marcas", "🏷", "Marcas"), ("etiquetas", "🔖", "Etiquetas"),
                  ("web", "🌐", "Web propia")]

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self._main = main
        self._sec_btns = {}
        self.setWindowTitle("Smart Manager — " + tr("cat.titulo", default="CATÁLOGO"))
        self.setStyleSheet(f"background:{_BG};")
        self._build()
        QTimer.singleShot(0, self._recargar_todo)

    def _build(self):
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self._build_sidebar(), 0)
        right = QWidget(); right.setStyleSheet(f"background:{_BG};")
        rcol = QVBoxLayout(right); rcol.setContentsMargins(24, 18, 24, 18); rcol.setSpacing(14)
        rcol.addLayout(self._build_header())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._panel_productos())
        self.stack.addWidget(self._panel_categorias())
        self.stack.addWidget(self._panel_marcas())
        self.stack.addWidget(self._panel_etiquetas())
        self.stack.addWidget(self._panel_web())
        rcol.addWidget(self.stack, 1)
        root.addWidget(right, 1)
        self._seleccionar(0)

    def _build_header(self):
        cab = QHBoxLayout()
        t = QLabel("🛍  " + tr("cat.titulo", default="CATÁLOGO ONLINE"))
        t.setStyleSheet(f"color:{_CIAN};font-family:'{_FONT}';font-weight:900;font-size:22px;background:transparent;")
        cab.addWidget(t); cab.addSpacing(16)
        self.lbl_ctx = _lbl("", size=14); cab.addWidget(self.lbl_ctx)
        cab.addStretch()
        if self._volver:
            cab.addWidget(_btn(tr("cat.volver", default="VOLVER AL MENÚ"), self._volver_menu, primary=True))
        return cab

    def _build_sidebar(self):
        wrap = QFrame(); wrap.setObjectName("sw"); wrap.setFixedWidth(230)
        wrap.setStyleSheet(f"QFrame#sw{{background:{_SIDEBAR};border:none;border-right:1px solid {_BORDE};}}")
        lay = QVBoxLayout(wrap); lay.setContentsMargins(0, 22, 0, 16); lay.setSpacing(2)
        cab = QLabel(tr("cat.secciones", default="GESTIÓN"))
        cab.setStyleSheet(f"color:#FFFFFF;font-family:'{_FONT}';font-weight:900;font-size:13px;"
                          f"letter-spacing:1.5px;background:transparent;border:none;padding:0 0 16px 28px;")
        lay.addWidget(cab)
        for i, (sid, icono, defecto) in enumerate(self._SECCIONES):
            b = QPushButton(f"  {icono}   {tr('cat.sec_' + sid, default=defecto)}")
            b.setCursor(Qt.CursorShape.PointingHandCursor); b.setCheckable(True); b.setFixedHeight(42)
            b.clicked.connect(lambda _c, idx=i: self._seleccionar(idx))
            self._sec_btns[i] = b; lay.addWidget(b)
        lay.addStretch()
        return wrap

    _SS_OFF = (f"QPushButton{{background:transparent;color:{_DIM};text-align:left;padding:6px 8px 6px 24px;"
               f"border:none;font-family:'{_FONT}';font-weight:900;font-size:14px;}}"
               f"QPushButton:hover{{background:#FFFFFF;color:{_SIDEBAR};}}")
    _SS_ON = (f"QPushButton{{background:{_CIAN};color:{_BG};text-align:left;padding:6px 8px 6px 24px;"
              f"border:none;font-family:'{_FONT}';font-weight:900;font-size:14px;}}")

    def _seleccionar(self, idx):
        self.stack.setCurrentIndex(idx)
        for i, b in self._sec_btns.items():
            b.setChecked(i == idx); b.setStyleSheet(self._SS_ON if i == idx else self._SS_OFF)

    # ── Panel Productos ──────────────────────────────────────────────────────
    def _panel_productos(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10); ly.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        self.inp_busca_prod = _inp(tr("cat.buscar_prod", default="Buscar artículo por nombre o código…"))
        self.inp_busca_prod.returnPressed.connect(self._recargar_productos)
        fila.addWidget(self.inp_busca_prod, 1)
        fila.addWidget(_btn(tr("cat.buscar", default="BUSCAR"), self._recargar_productos, primary=True))
        fila.addWidget(_btn(tr("cat.editar_ficha", default="EDITAR FICHA"), self._editar_producto, primary=True))
        ly.addLayout(fila)
        self.tbl_prod = _tabla([tr("cat.col_codigo", default="Código"), tr("cat.col_articulo", default="Artículo"),
                                tr("cat.col_encat", default="En catálogo"), tr("cat.col_dest", default="Dest."),
                                tr("cat.col_reco", default="Reco."), tr("cat.col_vis", default="Visible")])
        self.tbl_prod.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in (0, 2, 3, 4, 5):
            self.tbl_prod.setColumnWidth(c, 110)
        self.tbl_prod.doubleClicked.connect(lambda *_: self._editar_producto())
        ly.addWidget(_wrap_tabla(self.tbl_prod), 1)
        self.lbl_prod = _lbl("", size=11); ly.addWidget(self.lbl_prod)
        return w

    def _recargar_productos(self):
        arts = cat.articulos_para_catalogo(texto=self.inp_busca_prod.text().strip() or None)
        self._arts = arts
        self.tbl_prod.setRowCount(0)
        for a in arts:
            r = self.tbl_prod.rowCount(); self.tbl_prod.insertRow(r)
            vals = [a.get("codigo"), a.get("nombre") or "",
                    "✓" if a.get("id_producto") else "—",
                    "★" if a.get("destacado") else "", "✓" if a.get("recomendado") else "",
                    "✓" if (a.get("visible_web") if a.get("id_producto") else 0) else ""]
            for c, val in enumerate(vals):
                it = QTableWidgetItem(str(val))
                if c != 1:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tbl_prod.setItem(r, c, it)
        self.lbl_prod.setText(tr("cat.n_articulos", default="{n} artículo(s)", n=len(arts)))

    def _editar_producto(self):
        r = self.tbl_prod.currentRow()
        if r < 0 or not getattr(self, "_arts", None) or r >= len(self._arts):
            _aviso(self, tr("cat.titulo", default="CATÁLOGO"),
                   tr("cat.sel_articulo", default="Selecciona un artículo de la tabla."), "warning")
            return
        a = self._arts[r]
        _ProductoEditor(a["codigo"], a.get("nombre") or "", parent=self).exec()
        self._recargar_productos()

    # ── Panel Categorías ─────────────────────────────────────────────────────
    def _panel_categorias(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10); ly.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        self.inp_cat = _inp(tr("cat.cat_nombre", default="Nombre de categoría"))
        fila.addWidget(self.inp_cat, 1)
        fila.addWidget(_btn(tr("cat.crear_raiz", default="CREAR RAÍZ"), lambda: self._crear_categoria(False), primary=True))
        fila.addWidget(_btn(tr("cat.crear_sub", default="CREAR SUBCATEGORÍA"), lambda: self._crear_categoria(True), primary=True))
        fila.addWidget(_btn(tr("cat.renombrar", default="RENOMBRAR"), self._renombrar_categoria))
        fila.addWidget(_btn(tr("cat.eliminar", default="ELIMINAR"), self._eliminar_categoria, danger=True))
        ly.addLayout(fila)
        self.tree_cat = QTreeWidget(); self.tree_cat.setHeaderHidden(True)
        self.tree_cat.setStyleSheet(
            f"QTreeWidget{{background:{_BG2};color:{_TEXT};border:2px solid {_CIAN};border-radius:14px;"
            f"font-family:'{_FONT}';font-size:13px;padding:6px;}}"
            f"QTreeWidget::item{{height:30px;}}"
            f"QTreeWidget::item:selected{{background:#00FFC622;color:white;}}")
        ly.addWidget(self.tree_cat, 1)
        return w

    def _recargar_categorias(self):
        self.tree_cat.clear()

        def add(nodos, parent):
            for n in nodos:
                it = QTreeWidgetItem([n["nombre"]]); it.setData(0, Qt.ItemDataRole.UserRole, n["id"])
                (parent.addChild(it) if parent else self.tree_cat.addTopLevelItem(it))
                add(n.get("hijos", []), it)
        add(cat.arbol_categorias(), None)
        self.tree_cat.expandAll()

    def _cat_sel(self):
        it = self.tree_cat.currentItem()
        return it.data(0, Qt.ItemDataRole.UserRole) if it else None

    def _crear_categoria(self, como_sub):
        nombre = self.inp_cat.text().strip()
        if not nombre:
            _aviso(self, tr("cat.titulo", default="CATÁLOGO"), tr("cat.falta_nombre", default="Escribe un nombre."), "warning")
            return
        parent = self._cat_sel() if como_sub else None
        if como_sub and not parent:
            _aviso(self, tr("cat.titulo", default="CATÁLOGO"),
                   tr("cat.sel_padre", default="Selecciona la categoría padre."), "warning")
            return
        cat.crear_categoria(nombre, parent_id=parent)
        self.inp_cat.clear(); self._recargar_categorias()

    def _renombrar_categoria(self):
        cid = self._cat_sel(); nombre = self.inp_cat.text().strip()
        if not cid or not nombre:
            _aviso(self, tr("cat.titulo", default="CATÁLOGO"),
                   tr("cat.sel_y_nombre", default="Selecciona una categoría y escribe el nuevo nombre."), "warning")
            return
        cat.actualizar_categoria(cid, nombre=nombre); self.inp_cat.clear(); self._recargar_categorias()

    def _eliminar_categoria(self):
        cid = self._cat_sel()
        if not cid:
            return
        if _confirmar(self, tr("cat.titulo", default="CATÁLOGO"),
                      tr("cat.conf_del_cat", default="¿Eliminar la categoría? Sus subcategorías subirán de nivel.")):
            cat.eliminar_categoria(cid); self._recargar_categorias()

    # ── Panel Marcas ─────────────────────────────────────────────────────────
    def _panel_marcas(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10); ly.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        self.inp_marca = _inp(tr("cat.marca_nombre", default="Nombre de marca"))
        fila.addWidget(self.inp_marca, 1)
        fila.addWidget(_btn(tr("cat.crear", default="CREAR"), self._crear_marca, primary=True))
        fila.addWidget(_btn(tr("cat.renombrar", default="RENOMBRAR"), self._renombrar_marca))
        fila.addWidget(_btn(tr("cat.eliminar", default="ELIMINAR"), self._eliminar_marca, danger=True))
        ly.addLayout(fila)
        self.tbl_marca = _tabla([tr("cat.col_marca", default="Marca")])
        self.tbl_marca.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        ly.addWidget(_wrap_tabla(self.tbl_marca), 1)
        return w

    def _recargar_marcas(self):
        self._marcas = cat.listar_marcas()
        self.tbl_marca.setRowCount(0)
        for m in self._marcas:
            r = self.tbl_marca.rowCount(); self.tbl_marca.insertRow(r)
            self.tbl_marca.setItem(r, 0, QTableWidgetItem(m.get("nombre") or ""))

    def _marca_sel(self):
        r = self.tbl_marca.currentRow()
        return self._marcas[r]["id"] if getattr(self, "_marcas", None) and 0 <= r < len(self._marcas) else None

    def _crear_marca(self):
        n = self.inp_marca.text().strip()
        if n:
            cat.crear_marca(n); self.inp_marca.clear(); self._recargar_marcas()

    def _renombrar_marca(self):
        mid = self._marca_sel(); n = self.inp_marca.text().strip()
        if mid and n:
            cat.actualizar_marca(mid, nombre=n); self.inp_marca.clear(); self._recargar_marcas()

    def _eliminar_marca(self):
        mid = self._marca_sel()
        if mid and _confirmar(self, tr("cat.titulo", default="CATÁLOGO"),
                              tr("cat.conf_del_marca", default="¿Eliminar la marca?")):
            cat.eliminar_marca(mid); self._recargar_marcas()

    # ── Panel Etiquetas ──────────────────────────────────────────────────────
    def _panel_etiquetas(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(10); ly.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        self.inp_etq = _inp(tr("cat.etq_nombre", default="Nombre de etiqueta"))
        fila.addWidget(self.inp_etq, 1)
        fila.addWidget(_btn(tr("cat.crear", default="CREAR"), self._crear_etiqueta, primary=True))
        fila.addWidget(_btn(tr("cat.eliminar", default="ELIMINAR"), self._eliminar_etiqueta, danger=True))
        ly.addLayout(fila)
        self.tbl_etq = _tabla([tr("cat.col_etq", default="Etiqueta")])
        self.tbl_etq.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        ly.addWidget(_wrap_tabla(self.tbl_etq), 1)
        return w

    def _recargar_etiquetas(self):
        self._etqs = cat.listar_etiquetas()
        self.tbl_etq.setRowCount(0)
        for e in self._etqs:
            r = self.tbl_etq.rowCount(); self.tbl_etq.insertRow(r)
            self.tbl_etq.setItem(r, 0, QTableWidgetItem(e.get("nombre") or ""))

    def _crear_etiqueta(self):
        n = self.inp_etq.text().strip()
        if n:
            cat.crear_etiqueta(n); self.inp_etq.clear(); self._recargar_etiquetas()

    def _eliminar_etiqueta(self):
        r = self.tbl_etq.currentRow()
        if getattr(self, "_etqs", None) and 0 <= r < len(self._etqs):
            if _confirmar(self, tr("cat.titulo", default="CATÁLOGO"),
                          tr("cat.conf_del_etq", default="¿Eliminar la etiqueta?")):
                cat.eliminar_etiqueta(self._etqs[r]["id"]); self._recargar_etiquetas()

    # ── Panel Web propia (Escenario B) ───────────────────────────────────────
    def _panel_web(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setSpacing(8); ly.setContentsMargins(0, 0, 0, 0)
        ly.addWidget(_lbl(tr("cat.web_intro",
                             default="Genera la tienda online propia a partir de este catálogo "
                                     "(se mantiene sincronizada en vivo)."), dim=False, size=13))
        self.ck_web = _chk(tr("cat.web_activa", default="Tienda online activa"))
        ly.addWidget(self.ck_web)
        ly.addWidget(_lbl(tr("cat.web_nombre", default="Nombre de la tienda")))
        self.inp_web_nombre = _inp(); ly.addWidget(self.inp_web_nombre)
        ly.addWidget(_lbl(tr("cat.web_desc", default="Descripción / eslogan")))
        self.inp_web_desc = _inp(); ly.addWidget(self.inp_web_desc)
        fila = QHBoxLayout()
        colc = QVBoxLayout(); colc.addWidget(_lbl(tr("cat.web_color", default="Color de marca (#hex)")))
        self.inp_web_color = _inp("#00FFC6", 140); colc.addWidget(self.inp_web_color); fila.addLayout(colc)
        colm = QVBoxLayout(); colm.addWidget(_lbl(tr("cat.web_moneda", default="Moneda")))
        self.inp_web_moneda = _inp("EUR", 100); colm.addWidget(self.inp_web_moneda); fila.addLayout(colm)
        fila.addStretch(); ly.addLayout(fila)
        ly.addWidget(_lbl(tr("cat.web_logo", default="URL del logo (opcional)")))
        self.inp_web_logo = _inp(); ly.addWidget(self.inp_web_logo)
        ly.addWidget(_lbl(tr("cat.web_dominio", default="Dominio propio (opcional)")))
        self.inp_web_dominio = _inp(); ly.addWidget(self.inp_web_dominio)
        ly.addSpacing(6)
        self.lbl_web_url = _lbl("", size=12); self.lbl_web_url.setWordWrap(True)
        self.lbl_web_url.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        ly.addWidget(self.lbl_web_url)
        fb = QHBoxLayout(); fb.addStretch()
        fb.addWidget(_btn(tr("cat.guardar", default="GUARDAR"), self._guardar_web, primary=True))
        ly.addLayout(fb); ly.addStretch()
        return w

    def _recargar_web(self):
        from src.db import web_tienda
        from src.db.empresa import empresa_actual_id
        cfg = web_tienda.obtener_config()
        self.ck_web.setChecked(bool(cfg.get("activa")))
        self.inp_web_nombre.setText(cfg.get("nombre") or "")
        self.inp_web_desc.setText(cfg.get("descripcion") or "")
        self.inp_web_color.setText(cfg.get("color") or "#00FFC6")
        self.inp_web_moneda.setText(cfg.get("moneda") or "EUR")
        self.inp_web_logo.setText(cfg.get("logo_url") or "")
        self.inp_web_dominio.setText(cfg.get("dominio") or "")
        eid = empresa_actual_id()
        self.lbl_web_url.setText(tr("cat.web_url",
                                    default="URL pública de la tienda:  /tienda/{eid}  "
                                            "(servida por el backend de Smart Manager AI)", eid=eid))

    def _guardar_web(self):
        from src.db import web_tienda
        web_tienda.guardar_config(
            activa=1 if self.ck_web.isChecked() else 0,
            nombre=self.inp_web_nombre.text().strip(), descripcion=self.inp_web_desc.text().strip(),
            color=self.inp_web_color.text().strip() or "#00FFC6",
            moneda=(self.inp_web_moneda.text().strip() or "EUR").upper(),
            logo_url=self.inp_web_logo.text().strip(), dominio=self.inp_web_dominio.text().strip())
        _aviso(self, tr("cat.titulo", default="CATÁLOGO"),
               tr("cat.web_guardada", default="Configuración de la web guardada."), "info")

    # ── Carga / navegación ───────────────────────────────────────────────────
    def _recargar_todo(self):
        try:
            from src.db.empresa import empresa_actual_id
            from src.db import tiendas as _t
            self.lbl_ctx.setText(tr("cat.contexto", default="Tienda: {t}", t=_t.etiqueta_tienda_actual() or "—"))
        except Exception:
            pass
        self._recargar_productos(); self._recargar_categorias()
        self._recargar_marcas(); self._recargar_etiquetas(); self._recargar_web()

    def _volver_menu(self):
        if callable(self._volver):
            self._volver()
        self.close()
