"""
CENTRO DOCUMENTAL UNIFICADO — visor/gestor (no generador).

Repositorio oficial de TODOS los documentos del sistema. No genera documentos:
los visualiza y organiza a partir del registro `documentos_registro`
(ver src/db/documentos.py), respetando la arquitectura multiempresa/multitienda.

Barra lateral por categoría · panel con tabla neón · filtros · buscador global ·
acciones por fila (ver, descargar, imprimir, compartir, enviar por correo,
eliminar). Multi-tenant: el SUPERADMIN ve todas las empresas; el resto, la suya.
"""

from __future__ import annotations

import logging
import os
import shutil

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.db import documentos as doc_db
from src.db.usuario import sesion_global
from src.utils.i18n import tr

try:
    from assets.estilo_global import mostrar_confirmacion, mostrar_mensaje
except Exception:
    mostrar_mensaje = mostrar_confirmacion = None

logger = logging.getLogger("gui.documentos")

_BG = "#0E1117"
_BG2 = "#161B22"
_SIDEBAR = "#111418"   # color de las sidebars del resto de la app
_CIAN = "#00FFC6"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_DIM = "#8B949E"
_ROJO = "#F85149"

# (clave de tipo, icono, clave i18n) en el orden de la barra lateral.
_CATEGORIAS = [
    ("",            "🗂", "doc.cat_todos",        "Todos"),
    ("contrato",    "📄", "doc.tipo_contrato",    "Contratos"),
    ("factura",     "🧾", "doc.tipo_factura",     "Facturas"),
    ("factura_rect", "↩", "doc.tipo_factura_rect", "Facturas rectificativas"),
    ("ticket",      "🎫", "doc.tipo_ticket",      "Tickets"),
    ("albaran",     "📦", "doc.tipo_albaran",     "Albaranes"),
    ("pedido",      "🛒", "doc.tipo_pedido",      "Pedidos"),
    ("traspaso",    "🔁", "doc.tipo_traspaso",    "Traspasos"),
    ("recepcion",   "📥", "doc.tipo_recepcion",   "Recepciones"),
    ("merma",       "📉", "doc.tipo_merma",       "Mermas"),
    ("informe",     "📊", "doc.tipo_informe",     "Informes"),
    ("exportacion", "📑", "doc.tipo_exportacion", "Exportaciones Excel"),
    ("certificado", "📜", "doc.tipo_certificado", "Certificados"),
    ("rrhh",        "👥", "doc.tipo_rrhh",        "RRHH"),
    ("auditoria",   "🔍", "doc.tipo_auditoria",   "Auditoría"),
    ("otros",       "🗃", "doc.tipo_otros",       "Otros"),
]


def _mapa_empresas() -> dict:
    try:
        from src.db.empresa import listar_empresas
        return {e.get("id_empresa"): (e.get("codigo_empresa") or e.get("nombre_empresa") or "")
                for e in listar_empresas()}
    except Exception:
        return {}


def _mapa_tiendas() -> dict:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, codigo_tienda, nombre FROM tiendas")
            out = {}
            for f in cur.fetchall():
                if isinstance(f, dict):
                    out[f["id"]] = f.get("codigo_tienda") or f.get("nombre") or str(f["id"])
                else:
                    out[f[0]] = f[1] or f[2] or str(f[0])
            return out
    except Exception:
        return {}


class CentroDocumentalWindow(QWidget):
    """Centro documental unificado de la empresa activa (todas si SUPERADMIN)."""

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self._main = main
        self._tipo_sel = ""              # categoría activa ("" = todos)
        self._cat_btns = {}
        self._docs = []                  # filas mostradas (para resolver acciones)
        self._emp_map = {}
        self._tienda_map = {}
        self.setWindowTitle("Smart Manager — " + tr("doc.titulo", default="DOCUMENTOS"))
        self.setStyleSheet(f"background:{_BG};")
        self._build()
        QTimer.singleShot(0, self._cargar_inicial)

    # ---------------------------------------------------------------- construcción
    def _build(self):
        # Sidebar a toda altura (izquierda) + panel derecho con cabecera y tabla,
        # igual que el resto de pantallas de la app.
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self._build_sidebar(), 0)
        right = QWidget(); right.setStyleSheet(f"background:{_BG};")
        rcol = QVBoxLayout(right); rcol.setContentsMargins(24, 18, 24, 18); rcol.setSpacing(14)
        rcol.addLayout(self._build_header())
        rcol.addLayout(self._build_panel(), 1)
        root.addWidget(right, 1)

    def _build_header(self) -> QHBoxLayout:
        cab = QHBoxLayout()
        titulo = QLabel("🗂  " + tr("doc.titulo", default="DOCUMENTOS"))
        titulo.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;"
                             f"font-size:22px;background:transparent;")
        cab.addWidget(titulo)
        cab.addSpacing(18)
        self.lbl_ctx = QLabel("")
        self.lbl_ctx.setStyleSheet(f"color:{_DIM};font-family:'Segoe UI';font-weight:700;"
                                   f"font-size:14px;background:transparent;")
        cab.addWidget(self.lbl_ctx)
        cab.addStretch()
        if self._volver:
            bvol = QPushButton(tr("doc.volver", default="VOLVER AL MENÚ"))
            bvol.setCursor(Qt.CursorShape.PointingHandCursor); bvol.setFixedHeight(38)
            bvol.setStyleSheet(
                f"QPushButton{{background:{_BG};color:{_CIAN};border:2px solid {_CIAN};"
                f"border-radius:9px;font-weight:900;padding:0 18px;}}"
                f"QPushButton:hover{{background:{_CIAN};color:{_BG};}}")
            bvol.clicked.connect(self._volver_menu)
            cab.addWidget(bvol)
        return cab

    def _build_sidebar(self) -> QWidget:
        # Sidebar al estilo del resto de la app: riel oscuro + border-right, sin
        # tarjeta redondeada; botones gris→blanco al pasar; activo en cian.
        wrap = QFrame(); wrap.setObjectName("sideWrap"); wrap.setFixedWidth(250)
        wrap.setStyleSheet(f"QFrame#sideWrap{{background:{_SIDEBAR};border:none;"
                           f"border-right:1px solid {_BORDE};}}")
        lay = QVBoxLayout(wrap); lay.setContentsMargins(0, 22, 0, 16); lay.setSpacing(2)
        cab = QLabel(tr("doc.categorias", default="CATEGORÍAS"))
        cab.setStyleSheet("color:#FFFFFF;font-family:'Segoe UI';font-weight:900;"
                          "font-size:13px;letter-spacing:1.5px;background:transparent;"
                          "border:none;padding:0 0 16px 28px;")
        lay.addWidget(cab)
        for tipo, icono, clave, defecto in _CATEGORIAS:
            b = QPushButton(f"  {icono}   {tr(clave, default=defecto)}")
            b.setObjectName("btn_sidebar")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setCheckable(True); b.setFixedHeight(42)
            b.clicked.connect(lambda _c, t=tipo: self._seleccionar_categoria(t))
            self._cat_btns[tipo] = b
            lay.addWidget(b)
        lay.addStretch()
        self._estilar_categorias()
        return wrap

    _SS_CAT = (
        "QPushButton{{background:transparent;color:#8B949E;text-align:left;"
        "padding:6px 8px 6px 24px;border:none;border-radius:0px;font-family:'Segoe UI';"
        "font-weight:900;font-size:14px;letter-spacing:0.5px;}}"
        "QPushButton:hover{{background:#FFFFFF;color:{sb};}}")
    _SS_CAT_ACT = (
        "QPushButton{{background:{ci};color:{bg};text-align:left;"
        "padding:6px 8px 6px 24px;border:none;border-radius:0px;font-family:'Segoe UI';"
        "font-weight:900;font-size:14px;letter-spacing:0.5px;}}")

    def _estilar_categorias(self):
        inact = self._SS_CAT.format(sb=_SIDEBAR)
        act = self._SS_CAT_ACT.format(ci=_CIAN, bg=_BG)
        for tipo, b in self._cat_btns.items():
            n = self._conteo.get(tipo) if hasattr(self, "_conteo") else None
            base = b.text().split("   [")[0]
            b.setText(f"{base}   [{n}]" if n else base)
            b.setStyleSheet(act if tipo == self._tipo_sel else inact)

    def _build_panel(self) -> QVBoxLayout:
        col = QVBoxLayout(); col.setSpacing(12)

        # Buscador global + filtros.
        f1 = QHBoxLayout(); f1.setSpacing(8)
        self.inp_buscar = self._inp(tr("doc.buscar_ph",
                                       default="Buscar: referencia, hash, cliente, trabajador, importe…"))
        self.inp_buscar.returnPressed.connect(self._refrescar)
        f1.addWidget(self.inp_buscar, 1)
        b_buscar = self._btn(tr("doc.buscar", default="BUSCAR"), self._refrescar, primary=True)
        b_limpiar = self._btn(tr("doc.limpiar", default="LIMPIAR"), self._limpiar)
        f1.addWidget(b_buscar); f1.addWidget(b_limpiar)
        col.addLayout(f1)

        f2 = QHBoxLayout(); f2.setSpacing(8)
        self.inp_desde = self._inp(tr("doc.fecha_desde", default="Fecha desde (dd/mm/aaaa)"), 170)
        self.inp_hasta = self._inp(tr("doc.fecha_hasta", default="Fecha hasta (dd/mm/aaaa)"), 170)
        self.inp_cliente = self._inp(tr("doc.cliente", default="Cliente"), 160)
        self.inp_trab = self._inp(tr("doc.trabajador", default="Trabajador"), 160)
        self.inp_ref = self._inp(tr("doc.referencia", default="Referencia"), 150)
        for w in (self.inp_desde, self.inp_hasta, self.inp_cliente, self.inp_trab, self.inp_ref):
            w.returnPressed.connect(self._refrescar)
            f2.addWidget(w)
        f2.addStretch()
        col.addLayout(f2)

        # Tabla.
        cols = [
            tr("doc.col_doc", default="Documento"), tr("doc.col_tipo", default="Tipo"),
            tr("doc.col_empresa", default="Empresa"), tr("doc.col_tienda", default="Tienda"),
            tr("doc.col_fecha", default="Fecha"), tr("doc.col_usuario", default="Usuario"),
            tr("doc.col_ref", default="Referencia"), tr("doc.col_estado", default="Estado"),
            tr("doc.col_acciones", default="Acciones"),
        ]
        self.tabla = QTableWidget(0, len(cols))
        self.tabla.setHorizontalHeaderLabels(cols)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        vh = self.tabla.verticalHeader()
        vh.setVisible(False)
        # Filas más altas para que los chips de acción (32×30) quepan completos
        # (antes se recortaban y solo se veía el borde superior).
        vh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        vh.setDefaultSectionSize(46)
        self.tabla.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tabla.setWordWrap(False)  # texto en una sola línea (sin celdas a 2 líneas)
        hh = self.tabla.horizontalHeader()
        hh.setHighlightSections(False)
        # Documento se estira; el resto, ancho fijo moderado (sin scroll horizontal,
        # dejando el máximo espacio a la columna Documento).
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        anchos = {1: 88, 2: 84, 3: 56, 4: 128, 5: 90, 6: 104, 7: 88, 8: 214}
        for c, w in anchos.items():
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
            self.tabla.setColumnWidth(c, w)
        self.tabla.setStyleSheet(f"""
            QTableWidget{{background:transparent;color:{_TEXT};border:none;
                          gridline-color:{_BORDE};font-family:'Segoe UI';font-size:13px;outline:none;}}
            QHeaderView::section{{background:{_BG};color:{_CIAN};border:none;
                                  border-bottom:2px solid {_BORDE};padding:9px;font-weight:900;font-size:11px;}}
            QHeaderView::section:first{{border-top-left-radius:10px;}}
            QHeaderView::section:last{{border-top-right-radius:10px;}}
            QHeaderView::section:hover{{background:{_CIAN};color:{_BG};}}
            QTableWidget::item{{padding:7px;}}
            QTableWidget::item:selected{{background:#00FFC622;color:white;}}
        """)
        wrap = QFrame(); wrap.setObjectName("tablaWrap")
        wrap.setStyleSheet(f"QFrame#tablaWrap{{background:{_BG2};border:2px solid {_CIAN};"
                           f"border-radius:14px;}}")
        wl = QVBoxLayout(wrap); wl.setContentsMargins(5, 5, 5, 5); wl.addWidget(self.tabla)
        col.addWidget(wrap, 1)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setStyleSheet(f"color:{_DIM};font-family:'Segoe UI';font-size:11px;"
                                      f"background:transparent;")
        col.addWidget(self.lbl_estado)
        return col

    # ---------------------------------------------------------------- helpers UI
    def _inp(self, ph="", w=None) -> QLineEdit:
        e = QLineEdit(); e.setFixedHeight(36); e.setPlaceholderText(ph)
        if w:
            e.setFixedWidth(w)
        e.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:9px;padding:0 12px;font-size:12px;font-family:'Segoe UI';}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}")
        return e

    def _btn(self, txt, slot, primary=False, danger=False, peq=False) -> QPushButton:
        b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFixedHeight(30 if peq else 36)
        if danger:
            c, bg, borde = _ROJO, _BG2, _ROJO
        elif primary:
            c, bg, borde = _CIAN, _BG2, _CIAN
        else:
            c, bg, borde = _DIM, _BG2, _BORDE
        b.setStyleSheet(
            f"QPushButton{{background:{bg};color:{c};border:2px solid {borde};border-radius:9px;"
            f"font-weight:900;font-size:{'11' if peq else '12'}px;padding:0 {'10' if peq else '16'}px;}}"
            f"QPushButton:hover{{background:{c};color:{_BG};border-color:{c};}}")
        b.clicked.connect(slot)
        return b

    # ---------------------------------------------------------------- datos
    def _cargar_inicial(self):
        # Importa al registro los documentos que ya existían en documentos/.
        try:
            doc_db.reconciliar_carpeta()
        except Exception as e:
            logger.debug("reconciliar_carpeta: %s", e)
        self._emp_map = _mapa_empresas()
        self._tienda_map = _mapa_tiendas()
        self._actualizar_ctx_label()
        self._refrescar()

    def _actualizar_ctx_label(self):
        try:
            from src.db.empresa import empresa_actual_id, tienda_actual_id
            emp = self._emp_map.get(empresa_actual_id(), "")
            tnd = self._tienda_map.get(tienda_actual_id(), "—")
            ambito = (tr("doc.ambito_todas", default="todas las empresas")
                      if sesion_global.es_superadmin() else emp)
            self.lbl_ctx.setText(tr("doc.contexto", default="Empresa: {emp}   ·   Tienda: {tnd}",
                                    emp=ambito, tnd=tnd))
        except Exception:
            pass

    def _empresa_filtro(self):
        """SUPERADMIN ve todas las empresas; el resto SOLO la suya."""
        if sesion_global.es_superadmin():
            return None
        return sesion_global.empresa_id()

    def _seleccionar_categoria(self, tipo):
        self._tipo_sel = tipo
        self._estilar_categorias()
        self._refrescar()

    def _limpiar(self):
        for w in (self.inp_buscar, self.inp_desde, self.inp_hasta,
                  self.inp_cliente, self.inp_trab, self.inp_ref):
            w.clear()
        self._tipo_sel = ""
        self._estilar_categorias()
        self._refrescar()

    @staticmethod
    def _fmt_fecha(val):
        """Fecha de la tabla en formato corto y legible: dd/mm/aaaa HH:MM."""
        if not val:
            return ""
        import datetime as _dt
        if isinstance(val, _dt.datetime):
            return val.strftime("%d/%m/%Y %H:%M")
        s = str(val)
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return _dt.datetime.strptime(s[:19], fmt).strftime("%d/%m/%Y %H:%M")
            except ValueError:
                continue
        return s[:16]

    @staticmethod
    def _fecha_sql(txt):
        txt = (txt or "").strip()
        if not txt:
            return None
        import datetime as _dt
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return _dt.datetime.strptime(txt, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def _refrescar(self):
        self._conteo = doc_db.contar_por_tipo(self._empresa_filtro())
        self._estilar_categorias()
        self._docs = doc_db.listar_documentos(
            tipo=self._tipo_sel or None,
            id_empresa=self._empresa_filtro(),
            fecha_desde=self._fecha_sql(self.inp_desde.text()),
            fecha_hasta=self._fecha_sql(self.inp_hasta.text()),
            cliente=self.inp_cliente.text().strip() or None,
            trabajador=self.inp_trab.text().strip() or None,
            referencia=self.inp_ref.text().strip() or None,
            texto=self.inp_buscar.text().strip() or None,
        )
        self._pintar_tabla()

    def _pintar_tabla(self):
        self.tabla.setRowCount(0)
        for d in self._docs:
            r = self.tabla.rowCount(); self.tabla.insertRow(r)
            tipo = d.get("tipo_documento") or "otros"
            tipo_lbl = tr(doc_db.TIPOS.get(tipo, "doc.tipo_otros"), default=tipo)
            emp = self._emp_map.get(d.get("id_empresa"), "")
            tnd = self._tienda_map.get(d.get("id_tienda"), "—") if d.get("id_tienda") else "—"
            fecha = self._fmt_fecha(d.get("fecha_generacion"))
            valores = [
                d.get("nombre") or "", tipo_lbl, emp, tnd, fecha,
                d.get("trabajador") or "—", d.get("referencia") or "—",
                d.get("estado") or "",
            ]
            for c, v in enumerate(valores):
                it = QTableWidgetItem(str(v))
                if c in (1, 2, 3, 4, 7):
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 0:
                    it.setToolTip(f"{d.get('nombre') or ''}\n{d.get('ruta') or ''}")
                self.tabla.setItem(r, c, it)
            self.tabla.setCellWidget(r, 8, self._acciones_widget(d))
        n = len(self._docs)
        self.lbl_estado.setText(tr("doc.n_resultados", default="{n} documento(s)", n=n))

    def _acciones_widget(self, d) -> QWidget:
        w = QWidget(); w.setStyleSheet("background:transparent;")
        lay = QHBoxLayout(w); lay.setContentsMargins(2, 1, 2, 1); lay.setSpacing(3)

        def mini(icono, slot, danger=False):
            b = QPushButton(icono); b.setFixedSize(32, 30)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            # Sin font propia: con la fuente por defecto los emojis de color SÍ
            # renderizan (como en la barra lateral). Sin tooltip (no casa con el
            # diseño global de la app).
            hov = _ROJO if danger else _CIAN
            b.setStyleSheet(
                f"QPushButton{{background:{_BG2};border:1px solid {_BORDE};border-radius:7px;"
                f"font-size:15px;}}"
                f"QPushButton:hover{{background:{hov};border-color:{hov};}}")
            b.clicked.connect(lambda: slot(d))
            return b

        lay.addWidget(mini("👁", self._ver))
        lay.addWidget(mini("📥", self._descargar))
        lay.addWidget(mini("🖨", self._imprimir))
        lay.addWidget(mini("🔗", self._compartir))
        lay.addWidget(mini("📧", self._enviar_correo))
        if sesion_global.es_admin():
            lay.addWidget(mini("🗑", self._eliminar, danger=True))
        lay.addStretch()
        return w

    # ---------------------------------------------------------------- acciones
    def _aviso(self, titulo, msg, nivel="info"):
        if mostrar_mensaje is not None:
            mostrar_mensaje(self, titulo, msg, nivel=nivel)

    def _ruta_existente(self, d):
        ruta = d.get("ruta") or ""
        if not ruta or not os.path.exists(ruta):
            self._aviso(tr("doc.no_encontrado_t", default="Documento no encontrado"),
                        tr("doc.no_encontrado", default="El fichero ya no existe en disco."),
                        nivel="error")
            return None
        return ruta

    def _ver(self, d):
        ruta = self._ruta_existente(d)
        if ruta:
            try:
                os.startfile(ruta)  # noqa: S606 (Windows)
            except Exception as e:
                self._aviso("Error", str(e), nivel="error")

    def _descargar(self, d):
        ruta = self._ruta_existente(d)
        if not ruta:
            return
        destino, _ = QFileDialog.getSaveFileName(
            self, tr("doc.descargar", default="Descargar"), os.path.basename(ruta))
        if destino:
            try:
                shutil.copy2(ruta, destino)
                self._aviso(tr("doc.ok_t", default="Hecho"),
                            tr("doc.descargado", default="Documento guardado."))
            except Exception as e:
                self._aviso("Error", str(e), nivel="error")

    def _imprimir(self, d):
        ruta = self._ruta_existente(d)
        if ruta:
            try:
                os.startfile(ruta, "print")  # noqa: S606 (Windows)
            except Exception as e:
                self._aviso("Error", str(e), nivel="error")

    def _compartir(self, d):
        ruta = self._ruta_existente(d)
        if not ruta:
            return
        try:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(ruta)
            os.startfile(os.path.dirname(ruta))  # noqa: S606 (Windows)
            self._aviso(tr("doc.compartir", default="Compartir"),
                        tr("doc.compartido", default="Ruta copiada y carpeta abierta."))
        except Exception as e:
            self._aviso("Error", str(e), nivel="error")

    def _enviar_correo(self, d):
        ruta = self._ruta_existente(d)
        if not ruta:
            return
        try:
            from src.gui.correo_corporativo import enviar_documento_por_correo
            enviar_documento_por_correo(self, ruta, asunto=d.get("nombre") or "")
        except Exception as e:
            self._aviso("Error", str(e), nivel="error")

    def _eliminar(self, d):
        if not sesion_global.es_admin():
            return
        ok = True
        if mostrar_confirmacion is not None:
            ok = mostrar_confirmacion(
                self, tr("doc.eliminar", default="Eliminar"),
                tr("doc.eliminar_msg",
                   default="¿Eliminar «{n}» del centro documental?", n=d.get("nombre") or ""))
        if not ok:
            return
        doc_db.eliminar_documento(d.get("id_documento"))
        self._refrescar()

    def _volver_menu(self):
        if self._volver:
            self._volver()
