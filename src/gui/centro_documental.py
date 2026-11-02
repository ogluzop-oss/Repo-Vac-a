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

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.db import documentos as doc_db
from src.db.usuario import sesion_global
from src.gui.catalogo_gestion import _btn_salir_sidebar
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

# (clave de tipo, icono, clave i18n, texto por defecto) en el orden de la barra lateral.
#
# Sin "Todos" ni "Otros". "ticket" (tickets de compra del TPV) NUNCA tiene pestaña aquí ni
# aparece en ninguna categoría: es redundante con la ventana propia "Buscar/Reimprimir
# Ticket" del TPV (filtros de caja/empleado/forma de pago) y además se EXCLUYE en el propio
# chokepoint de datos (`db.documentos.listar_documentos`/`contar_por_tipo`), no solo aquí.
#
# Reorganización por MÓDULO (no por tipo documental): cada pestaña reúne TODOS los
# `tipo_documento` que genera un módulo real de la app (mismos límites que
# `gui/menu_principal.py` — v_id/tarjeta), para que "en cada pestaña aparezcan todos los
# archivos generados en el módulo que corresponda". La clave de tipo puede ser un string
# (tipo_documento exacto) o una tupla de varios tipos agrupados bajo la misma pestaña;
# `listar_documentos`/`contar_por_tipo` ya resuelven ambas formas de forma nativa
# (`tipo_documento IN (...)` cuando `tipo` es lista/tupla) — mismo mecanismo único, sin
# filtros paralelos. Varios módulos solo generan HOY un único tipo documental (Mermas,
# Producción, Mantenimiento, Calidad, Posventa, Etiquetas, Fiscal, Cámaras...): su pestaña
# sigue siendo un string simple, pero conceptualmente es igualmente "ese módulo" — si en el
# futuro ese módulo empieza a generar más tipos, caen en la MISMA pestaña sin tocar esta lista.
#
# Mapeo módulo → tipo(s), con la evidencia (grep de `registrar_documento(...)`/rutas de menú)
# que fijó cada decisión — ver cabecera de la tarea para el detalle completo:
#   - Proveedores   (v_id "compras")     : factura, factura_rect, albaran, pedido
#   - Logística     (v_id "logistica")   : recepcion, traspaso  (misma pantalla
#     `RecepcionPaleWindow` genera ambos — recepción de palés Y traspasos entre tienda/almacén)
#   - Reparto       (v_id "transporte")  : reparto (`api/routers/transporte.py`, módulo de
#     nivel superior propio, DISTINTO de Logística)
#   - Clientes      (v_id "clientes_crm"): presupuesto (`utils/presupuesto_pdf.py`, usado
#     únicamente desde `gui/crm_dashboard.py`)
#   - RRHH          (v_id "rrhh")        : contrato (`rrhh_contrato_inline.py` — SON
#     contratos de personal, no contratos comerciales) + certificado (genérico, mismo cajón
#     que `certificado_empresa`/`certificado_laboral` — ver `rrhh/firma_servicio.py`
#     TIPOS_FIRMABLES y `rrhh/persistencia.py`) + el resto de tipos RRHH ya agrupados
#   - Contabilidad  (v_id "contabilidad"): cierre_ejercicio, exportacion, informe_anual,
#     cuentas_anuales (históricos — `_cerrar()` ya no genera NUEVOS documentos de estos 3 tipos,
#     ver `services/contabilidad/cierre_anual_pdf.py`), cierre_anual_completo (NUEVO — el único
#     documento que genera `_cerrar()` desde la unificación: fusiona lo que antes eran 3 PDFs)
#   - Gestión Caja  (v_id "gestion_caja"): caja_registradora, caja_fuerte, cambio_cajero,
#     transferencia_efectivo, informe (Cierre Z — `services/tpv/cierre_z.py`)
#   - Mermas (mermas) / Producción (mrp) / Mantenimiento (gmao) / Calidad (calidad) /
#     Posventa (sat) / Etiquetas (etiquetas) / Fiscal (fiscal) / Cámaras (camaras) /
#     Auditoría (seguridad): un único tipo cada uno hoy, pestaña = módulo igualmente.
_TIPOS_PROVEEDORES = ("factura", "factura_rect", "albaran", "pedido")
_TIPOS_LOGISTICA = ("recepcion", "traspaso")
_TIPOS_CONTABILIDAD = ("cierre_ejercicio", "exportacion", "informe_anual", "cuentas_anuales",
                       "cierre_anual_completo")
_TIPOS_CAJA = ("caja_registradora", "caja_fuerte", "cambio_cajero", "transferencia_efectivo", "informe")
_TIPOS_RRHH = ("contrato", "certificado", "rrhh", "nomina", "finiquito", "modelo145",
               "certificado_empresa", "certificado_laboral", "carta_despido", "periodo_prueba")

_CATEGORIAS = [
    (_TIPOS_PROVEEDORES, "📋", "doc.tipo_compras",       "Proveedores"),
    (_TIPOS_LOGISTICA,   "📥", "doc.tipo_logistica",     "Logística"),
    ("reparto",          "🚚", "doc.tipo_reparto",       "Reparto"),
    ("presupuesto",      "💰", "doc.tipo_presupuesto",   "Presupuestos"),
    (_TIPOS_RRHH,        "👥", "doc.tipo_rrhh",          "RRHH"),
    (_TIPOS_CONTABILIDAD, "📊", "doc.tipo_contabilidad", "Contabilidad"),
    (_TIPOS_CAJA,        "🧮", "doc.tipo_caja",          "Gestión Caja"),
    ("merma",            "📉", "doc.tipo_merma",         "Mermas"),
    ("produccion",       "🏭", "doc.tipo_produccion",    "Producción"),
    ("mantenimiento",    "🔧", "doc.tipo_mantenimiento", "Mantenimiento"),
    ("inspeccion",       "🔬", "doc.tipo_inspeccion",    "Calidad"),
    ("intervencion",     "🎧", "doc.tipo_intervencion",  "Posventa"),
    ("etiqueta",         "🏷", "doc.tipo_etiqueta",      "Etiquetas"),
    ("fiscal",           "🏛", "doc.tipo_fiscal",        "Fiscal"),
    ("grabacion",        "📹", "doc.tipo_grabacion",     "Grabaciones"),
    ("auditoria",        "🔍", "doc.tipo_auditoria",     "Auditoría"),
]


def _resolver_tab(tipo_solicitado: str):
    """Resuelve `categoria_inicial` (un `tipo_documento` SUELTO, p. ej. "exportacion") a la
    clave de pestaña real en `_CATEGORIAS` que lo contiene — ahora que varios tipos viven
    agrupados bajo una pestaña de módulo (p. ej. "exportacion" vive dentro de `_TIPOS_CONTABILIDAD`).
    Compatibilidad hacia atrás: varias pantallas (`mostrar_stock.py`, `informe_reposicion.py`,
    `gestion_mermas.py`, `bi_dashboard.py`) abren Documentos con `categoria_inicial="exportacion"`
    tras generar un Excel, y esa firma pública no cambia. Si `tipo_solicitado` ya es la clave
    de una pestaña (string o tupla), o no coincide con ninguna, se devuelve tal cual."""
    if not tipo_solicitado:
        return tipo_solicitado
    for tipo, *_resto in _CATEGORIAS:
        if tipo == tipo_solicitado:
            return tipo
        if isinstance(tipo, tuple) and tipo_solicitado in tipo:
            return tipo
    return tipo_solicitado


def _mapa_empresas() -> dict:
    """id_empresa → nombre legible (nombre comercial / razón social)."""
    try:
        from src.db.empresa import listar_empresas
        out = {}
        for e in listar_empresas():
            out[e.get("id_empresa")] = (
                e.get("nombre_comercial") or e.get("razon_social")
                or e.get("nombre_empresa") or e.get("codigo_empresa") or "")
        return out
    except Exception:
        return {}


def _mapa_tiendas() -> dict:
    """id_tienda → {nombre, id_empresa} para resolver nombre y ámbito.

    Cliente fino (Strangler, Fase 3): los datos vienen de la CAPA DE DATOS (`db.tiendas.listar_tiendas`,
    que además loguea errores y filtra activas); la GUI solo ORQUESTA el mapa, sin SQL directo."""
    from src.db.tiendas import listar_tiendas
    out = {}
    for t in listar_tiendas():
        out[t["id"]] = {"nombre": t.get("nombre") or t.get("codigo_tienda") or str(t["id"]),
                        "id_empresa": t.get("id_empresa")}
    return out


class _AccionesDelegate(QStyledItemDelegate):
    """Pinta los iconos de acción (vectoriales, sin emojis ni widgets) en la columna
    Acciones y despacha el clic. Sin widgets por fila → tabla rápida y sin pantalla
    en blanco al abrir. Acciones: ver, descargar, imprimir, compartir, correo,
    eliminar (esta última solo si `puede_eliminar`)."""

    _ACC = ["ver", "descargar", "imprimir", "compartir", "correo", "eliminar"]
    _BW = 30      # ancho de cada chip
    _GAP = 4
    _PAD = 6

    def __init__(self, parent, on_action, puede_eliminar: bool):
        super().__init__(parent)
        self._on = on_action
        self._del = puede_eliminar
        self._hover = None  # (fila, índice de icono) bajo el ratón

    def _items(self):
        return self._ACC if self._del else self._ACC[:-1]

    def _rect_chip(self, cell, i):
        x = cell.x() + self._PAD + i * (self._BW + self._GAP)
        y = cell.y() + (cell.height() - 30) / 2
        return QRectF(x, y, self._BW, 30)

    def icono_en(self, posf, cell_rect):
        """Índice del icono bajo `posf` (QPointF) dentro de la celda, o None."""
        for i in range(len(self._items())):
            if self._rect_chip(cell_rect, i).contains(posf):
                return i
        return None

    def paint(self, p, option, index):
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i, acc in enumerate(self._items()):
            r = self._rect_chip(option.rect, i)
            col = QColor(_ROJO if acc == "eliminar" else _CIAN)
            if self._hover == (index.row(), i):   # hover swap: chip relleno + icono oscuro
                p.setPen(QPen(col, 1)); p.setBrush(col)
                p.drawRoundedRect(r, 7, 7)
                self._draw_icon(p, acc, r, QColor(_BG))
            else:
                p.setPen(QPen(QColor(_BORDE), 1)); p.setBrush(QColor(_BG2))
                p.drawRoundedRect(r, 7, 7)
                self._draw_icon(p, acc, r, col)
        p.restore()

    def _draw_icon(self, p, name, r, color):
        pen = QPen(color); pen.setWidthF(1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = r.center().x(), r.center().y()
        if name == "ver":
            p.drawEllipse(QPointF(cx, cy), 8.5, 5.2)
            p.setBrush(color); p.drawEllipse(QPointF(cx, cy), 2.1, 2.1)
        elif name == "descargar":
            p.drawLine(QPointF(cx, cy - 7), QPointF(cx, cy + 3))
            p.drawLine(QPointF(cx - 4, cy - 1), QPointF(cx, cy + 3))
            p.drawLine(QPointF(cx + 4, cy - 1), QPointF(cx, cy + 3))
            p.drawLine(QPointF(cx - 6, cy + 6), QPointF(cx + 6, cy + 6))
        elif name == "imprimir":
            p.drawRect(QRectF(cx - 4, cy - 8, 8, 4))           # papel arriba
            p.drawRoundedRect(QRectF(cx - 7, cy - 4, 14, 8), 1.5, 1.5)  # cuerpo
            p.setBrush(QColor(_BG2)); p.drawRect(QRectF(cx - 4, cy + 1, 8, 6))  # papel salida
            p.setBrush(Qt.BrushStyle.NoBrush); p.drawRect(QRectF(cx - 4, cy + 1, 8, 6))
        elif name == "compartir":
            a = QPointF(cx + 5, cy - 6); b = QPointF(cx - 5, cy); c = QPointF(cx + 5, cy + 6)
            p.drawLine(b, a); p.drawLine(b, c)
            p.setBrush(color)
            for pt in (a, b, c):
                p.drawEllipse(pt, 2.3, 2.3)
        elif name == "correo":
            p.drawRect(QRectF(cx - 8, cy - 5, 16, 11))
            p.drawLine(QPointF(cx - 8, cy - 5), QPointF(cx, cy + 1))
            p.drawLine(QPointF(cx + 8, cy - 5), QPointF(cx, cy + 1))
        elif name == "eliminar":
            p.drawLine(QPointF(cx - 7, cy - 5), QPointF(cx + 7, cy - 5))   # tapa
            p.drawLine(QPointF(cx - 2.5, cy - 5), QPointF(cx - 2.5, cy - 7))
            p.drawLine(QPointF(cx - 2.5, cy - 7), QPointF(cx + 2.5, cy - 7))
            p.drawLine(QPointF(cx + 2.5, cy - 7), QPointF(cx + 2.5, cy - 5))  # asa
            p.drawLine(QPointF(cx - 5, cy - 5), QPointF(cx - 4, cy + 8))
            p.drawLine(QPointF(cx + 5, cy - 5), QPointF(cx + 4, cy + 8))
            p.drawLine(QPointF(cx - 4, cy + 8), QPointF(cx + 4, cy + 8))     # cubo
            p.drawLine(QPointF(cx - 1.6, cy - 2), QPointF(cx - 1.6, cy + 5))
            p.drawLine(QPointF(cx + 1.6, cy - 2), QPointF(cx + 1.6, cy + 5))

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonRelease:
            items = self._items()
            for i in range(len(items)):
                if self._rect_chip(option.rect, i).contains(QPointF(event.position())):
                    self._on(index.row(), items[i])
                    return True
        return False


class CentroDocumentalWindow(QWidget):
    """Centro documental unificado de la empresa activa (todas si SUPERADMIN)."""

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None,
                 categoria_inicial="", **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self._main = main
        self.usuario = usuario
        if isinstance(usuario, dict):
            self.perfil = usuario.get("perfil", "OPERARIO")
        else:
            self.perfil = getattr(usuario, "perfil", "OPERARIO")
        # Categoría activa: sin "Todos", se abre en la primera pestaña real por defecto
        # (o en `categoria_inicial` si el llamador pide una concreta, p. ej. "exportacion" —
        # `_resolver_tab` la traduce a la pestaña de módulo que la contiene hoy).
        self._tipo_sel = _resolver_tab(categoria_inicial) or _CATEGORIAS[0][0]
        self._cat_btns = {}
        self._docs = []                  # filas mostradas (para resolver acciones)
        self._emp_map = {}
        self._tienda_map = {}
        self.setWindowTitle("Smart Manager — " + tr("doc.titulo", default="DOCUMENTOS"))
        self.setStyleSheet(f"background:{_BG};")
        self._build()
        QTimer.singleShot(0, self._cargar_inicial)

        # P3 (UX-TPV-01): sidebar colapsable con persistencia por usuario.
        toggle_btn = None
        try:
            from src.gui.sidebar_colapsable import instalar_sidebar_colapsable
            if getattr(self, "sidebar", None) is not None:
                toggle_btn = instalar_sidebar_colapsable(
                    self, self.sidebar, usuario=self.usuario, clave="centro_documental")
        except Exception:
            pass

        # Restricciones por perfil: ADMINISTRADOR no ve Contratos/Calidad/Certificados/Fiscal/
        # RRHH/Auditoría (información sensible reservada a SUPERADMIN). Se aplica DESPUÉS de
        # `instalar_sidebar_colapsable` porque este, al restaurar el estado expandido/colapsado,
        # vuelve a mostrar todos los botones de la sidebar — y se reconecta al toggle porque cada
        # colapsar/expandir repite ese mismo "mostrar todos" (mismo criterio que
        # `mostrar_stock.py`/`gestion_mermas.py`). `_cat_btns` es un diccionario clave por `tipo`
        # (no por índice posicional), así que se oculta directamente por esa clave. Tras la
        # reorganización por módulo, "contrato" y "certificado" viven dentro de la MISMA pestaña
        # agrupada "RRHH" (`_TIPOS_RRHH`) — ocultarla entera sigue cubriendo los mismos tipos
        # reales de antes (contrato/certificado/rrhh/nomina/finiquito/modelo145/
        # certificado_empresa/certificado_laboral/carta_despido/periodo_prueba), solo que
        # direccionados ahora por el identificador de pestaña agrupada en vez de 3 entradas sueltas.
        _TIPOS_OCULTAR_ADMIN = (
            _TIPOS_RRHH, "inspeccion", "fiscal", "auditoria",
        )
        if self.perfil == "ADMINISTRADOR":
            def _ocultar_restringidas():
                for t in _TIPOS_OCULTAR_ADMIN:
                    btn = self._cat_btns.get(t)
                    if btn is not None:
                        btn.setVisible(False)
            _ocultar_restringidas()
            if toggle_btn:
                toggle_btn.clicked.connect(_ocultar_restringidas)

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
        cab.addStretch()
        return cab

    def _build_sidebar(self) -> QWidget:
        # Sidebar al estilo del resto de la app: riel oscuro + border-right, sin
        # tarjeta redondeada; botones gris→blanco al pasar; activo en cian.
        wrap = QFrame(); wrap.setObjectName("sideWrap"); wrap.setFixedWidth(280); self.sidebar = wrap  # P3
        wrap.setStyleSheet(f"QFrame#sideWrap{{background:{_SIDEBAR};border:none;"
                           f"border-right:1px solid {_BORDE};}}")
        lay = QVBoxLayout(wrap); lay.setContentsMargins(0, 22, 0, 16); lay.setSpacing(2)
        # `tr()` normaliza a "frase" (primera mayúscula, resto minúsculas — `i18n._frase`) salvo
        # siglas conocidas, así que CUALQUIER texto de sidebar que pase por `tr()` necesita
        # `.upper()` explícito para quedar en mayúsculas de verdad (igual que ya hacían las
        # pestañas de categoría, dos bloques más abajo — aquí faltaba por descuido).
        cab = QLabel(tr("doc.categorias", default="SMART DOCUMENTS").upper())
        cab.setStyleSheet("color:#FFFFFF;font-family:'Segoe UI';font-weight:900;"
                          "font-size:16px;letter-spacing:2px;background:transparent;"
                          "border:none;padding:0 0 24px 28px;")
        lay.addWidget(cab)
        # Lista de categorías con scroll (scrollbar con el estilo global de la app).
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background:transparent;border:none;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cont = QWidget(); cont.setStyleSheet("background:transparent;")
        clay = QVBoxLayout(cont); clay.setContentsMargins(0, 0, 0, 0); clay.setSpacing(2)
        for tipo, icono, clave, defecto in _CATEGORIAS:
            b = QPushButton(f"   {tr(clave, default=defecto).upper()}")   # sin icono — sidebar: mayúsculas
            b.setObjectName("btn_sidebar")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setCheckable(True); b.setFixedHeight(52)
            b.clicked.connect(lambda _c, t=tipo: self._seleccionar_categoria(t))
            self._cat_btns[tipo] = b
            clay.addWidget(b)
        clay.addStretch()
        # Badges de notificación (círculo rojo + nº blanco) — mismo componente ya usado en el
        # resto de la app (`gui.foundation.tab_badges`), no un contador "[N]" pegado al texto.
        from src.gui.foundation.tab_badges import instalar_badges_sidebar
        self._badges = instalar_badges_sidebar(
            [self._cat_btns[tipo] for tipo, *_ in _CATEGORIAS], self._obtener_counts_sidebar)
        scroll.setWidget(cont)
        lay.addWidget(scroll, 1)
        # Botón SALIR (rojo) al fondo — mismo helper compartido que el resto de sidebars de la
        # app (`_btn_salir_sidebar`), en vez de reconstruirlo a mano con texto/tamaño propios.
        if self._volver:
            self._btn_salir = bsalir = _btn_salir_sidebar(self._volver_menu)
            lay.addWidget(bsalir)
        self._estilar_categorias()
        return wrap

    _SS_CAT = (
        "QPushButton{{background:transparent;color:#FFFFFF;text-align:left;"
        "padding:6px 8px 6px 24px;border:none;border-left:4px solid transparent;border-radius:0px;"
        "font-family:'Segoe UI';font-weight:900;font-size:12px;letter-spacing:0.5px;}}"
        "QPushButton:hover{{background:#FFFFFF;color:{sb};}}")
    _SS_CAT_ACT = (
        "QPushButton{{background:#1A2230;color:{ci};text-align:left;"
        "padding:6px 8px 6px 24px;border:none;border-left:4px solid {ci};border-radius:0px;"
        "font-family:'Segoe UI';font-weight:900;font-size:12px;letter-spacing:0.5px;}}")

    def _estilar_categorias(self):
        inact = self._SS_CAT.format(sb=_SIDEBAR)
        act = self._SS_CAT_ACT.format(ci=_CIAN, bg=_BG)
        for tipo, b in self._cat_btns.items():
            b.setStyleSheet(act if tipo == self._tipo_sel else inact)
        if getattr(self, "_badges", None) is not None:
            self._badges.refrescar()

    def _obtener_counts_sidebar(self) -> dict:
        """{índice de botón en `_CATEGORIAS`: nº documentos} para `instalar_badges_sidebar`."""
        conteo = self._conteo if hasattr(self, "_conteo") else {}
        out = {}
        for i, (tipo, *_r) in enumerate(_CATEGORIAS):
            # `tipo` puede ser una tupla (categoría agrupada, p. ej. "RRHH"): el contador
            # suma el recuento de cada tipo real que agrupa esa pestaña.
            if isinstance(tipo, tuple):
                out[i] = sum(conteo.get(t, 0) for t in tipo)
            else:
                out[i] = conteo.get(tipo, 0)
        return out

    def _build_panel(self) -> QVBoxLayout:
        col = QVBoxLayout(); col.setSpacing(12)

        # Buscador global + filtros.
        f1 = QHBoxLayout(); f1.setSpacing(8)
        self.inp_buscar = self._inp(tr("doc.buscar_ph",
                                       default="🔍 Buscar: referencia, hash, cliente, trabajador, importe…"))
        self.inp_buscar.returnPressed.connect(self._refrescar)
        f1.addWidget(self.inp_buscar, 1)
        b_buscar = self._btn("🔍", self._refrescar, primary=True)
        b_limpiar = self._btn(tr("doc.vaciar_pestana", default="VACIAR PESTAÑA"), self._limpiar, danger=True)
        f1.addWidget(b_buscar); f1.addWidget(b_limpiar)
        col.addLayout(f1)

        f2 = QHBoxLayout(); f2.setSpacing(8)
        # Fechas como desplegables de calendario (mismo widget que el buscador de
        # tickets). Rango amplio por defecto → muestra todos los documentos.
        from PyQt6.QtCore import QDate
        from src.gui.tpv import _FechaFilter
        hoy = QDate.currentDate()
        self.f_desde = _FechaFilter(hoy.addYears(-3))
        self.f_hasta = _FechaFilter(hoy)
        f2.addWidget(self._lbl_filtro(tr("doc.fecha_inicio", default="Fecha inicio")))
        f2.addWidget(self.f_desde)
        f2.addSpacing(8)
        f2.addWidget(self._lbl_filtro(tr("doc.fecha_fin", default="Fecha fin")))
        f2.addWidget(self.f_hasta)
        f2.addSpacing(12)
        self.inp_cliente = self._inp(tr("doc.cliente", default="Cliente"), 160)
        self.inp_trab = self._inp(tr("doc.trabajador", default="Trabajador"), 160)
        self.inp_ref = self._inp(tr("doc.referencia", default="Referencia"), 150)
        for w in (self.inp_cliente, self.inp_trab, self.inp_ref):
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
        # Iconos de acción pintados por delegate (sin widgets por fila → rápido).
        self._acc_delegate = _AccionesDelegate(
            self.tabla, self._accion_dispatch, sesion_global.es_admin())
        self.tabla.setItemDelegateForColumn(8, self._acc_delegate)
        # Seguimiento del ratón para el hover swap de los iconos de acción.
        self.tabla.setMouseTracking(True)
        self.tabla.viewport().setMouseTracking(True)
        self.tabla.viewport().installEventFilter(self)
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

    def _lbl_filtro(self, txt) -> QLabel:
        l = QLabel(txt)
        l.setStyleSheet(f"color:{_DIM};font-family:'Segoe UI';font-weight:900;"
                        f"font-size:12px;background:transparent;")
        return l

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
        # 1) Pintar de inmediato lo ya registrado (rápido) → sin pantalla en blanco.
        self._emp_map = _mapa_empresas()
        self._tienda_map = _mapa_tiendas()
        self._estilar_categorias()   # refleja la categoría inicial (si se abrió en una concreta)
        self._refrescar()
        # 2) Reconciliar la carpeta después del primer pintado (en lote, rápido) y
        #    refrescar solo si aparecen documentos nuevos.
        QTimer.singleShot(50, self._reconciliar_bg)

    def _reconciliar_bg(self):
        try:
            nuevos = doc_db.reconciliar_carpeta()
        except Exception as e:
            logger.debug("reconciliar_carpeta: %s", e); nuevos = 0
        if nuevos:
            self._refrescar()

    def _empresa_filtro(self):
        """SUPERADMIN ve todas las empresas; el resto SOLO la suya."""
        if sesion_global.es_superadmin():
            return None
        return sesion_global.empresa_id()

    def _seleccionar_categoria(self, tipo):
        if tipo == self._tipo_sel:
            return   # ya activa: nada que refrescar ni animar
        self._tipo_sel = tipo
        self._estilar_categorias()
        # Misma animación de deslizamiento que el resto de la app (`instalar_transicion_stack` en
        # Historial Logístico/Incidencias), adaptada a autotransición: aquí NO hay una página
        # "entrante" distinta que mostrar — las 23 categorías comparten la MISMA `self.tabla`, solo
        # cambia el filtro — así que se captura su instantánea, se refresca en el sitio por debajo
        # y se desliza la instantánea fuera para revelar la tabla ya actualizada (ver
        # `transiciones.deslizar_refresco`). A prueba de fallos: degrada a refresco instantáneo.
        try:
            from src.gui.transiciones import deslizar_refresco
            deslizar_refresco(self.tabla, self._refrescar)
        except Exception:
            self._refrescar()

    def _limpiar(self):
        """BORRA todos los documentos de la categoría (pestaña) seleccionada, con confirmación explícita.
        Solo administradores (como la eliminación individual). Acción destructiva e irreversible."""
        if not sesion_global.es_admin():
            self._aviso(tr("doc.limpiar", default="LIMPIAR"),
                        tr("doc.solo_admin", default="Solo un administrador puede borrar documentos."),
                        nivel="warning")
            return
        cat = next((defecto for tipo, _i, _c, defecto in _CATEGORIAS if tipo == self._tipo_sel), "")
        docs = doc_db.listar_documentos(
            tipo=self._tipo_sel or None, id_empresa=self._empresa_filtro(), limite=100000) or []
        n = len(docs)
        if n == 0:
            self._aviso(tr("doc.limpiar", default="LIMPIAR"),
                        tr("doc.nada_borrar", default="No hay documentos que borrar en «{c}».", c=cat),
                        nivel="info")
            return
        ok = True
        if mostrar_confirmacion is not None:
            ok = mostrar_confirmacion(
                self, tr("doc.borrar_cat_t", default="Borrar documentos"),
                tr("doc.borrar_cat_msg",
                   default="¿Seguro que quieres BORRAR los {n} documento(s) de «{c}»?\n"
                           "Esta acción NO se puede deshacer.", n=n, c=cat))
        if not ok:
            return
        borrados = 0
        for d in docs:
            try:
                # borrar_fichero=True → borra también el fichero del disco; si no, la reconciliación de la
                # carpeta (`reconciliar_carpeta`) los volvería a registrar al reentrar en Documentos.
                if doc_db.eliminar_documento(d.get("id_documento"), borrar_fichero=True):
                    borrados += 1
            except Exception:
                pass
        self._refrescar()
        self._aviso(tr("doc.borrar_cat_t", default="Borrar documentos"),
                    tr("doc.borrar_cat_ok", default="Borrados {b} de {n} documento(s) de «{c}».",
                       b=borrados, n=n, c=cat), nivel="success")

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

    def _refrescar(self):
        self._conteo = doc_db.contar_por_tipo(self._empresa_filtro())
        self._estilar_categorias()
        self._docs = doc_db.listar_documentos(
            tipo=self._tipo_sel or None,
            id_empresa=self._empresa_filtro(),
            fecha_desde=self.f_desde.date().toString("yyyy-MM-dd"),
            fecha_hasta=self.f_hasta.date().toString("yyyy-MM-dd"),
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
            _t = self._tienda_map.get(d.get("id_tienda")) if d.get("id_tienda") else None
            tnd = _t["nombre"] if _t else "—"
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
                self.tabla.setItem(r, c, it)
            self.tabla.setItem(r, 8, QTableWidgetItem(""))  # celda pintada por el delegate
        n = len(self._docs)
        self.lbl_estado.setText(tr("doc.n_resultados", default="{n} documento(s)", n=n))

    def eventFilter(self, obj, ev):
        # Hover swap de los iconos de acción: detecta el icono bajo el ratón.
        try:
            if getattr(self, "tabla", None) is not None and obj is self.tabla.viewport():
                t = ev.type()
                if t == QEvent.Type.MouseMove:
                    posf = ev.position()
                    idx = self.tabla.indexAt(posf.toPoint())
                    nuevo = None
                    if idx.isValid() and idx.column() == 8:
                        i = self._acc_delegate.icono_en(posf, self.tabla.visualRect(idx))
                        if i is not None:
                            nuevo = (idx.row(), i)
                    if nuevo != self._acc_delegate._hover:
                        self._acc_delegate._hover = nuevo
                        self.tabla.viewport().update()
                elif t == QEvent.Type.Leave:
                    if self._acc_delegate._hover is not None:
                        self._acc_delegate._hover = None
                        self.tabla.viewport().update()
        except Exception:
            pass
        return super().eventFilter(obj, ev)

    def _accion_dispatch(self, row, acc):
        """Despacha el clic en un icono de acción (lo dibuja _AccionesDelegate)."""
        if row < 0 or row >= len(self._docs):
            return
        d = self._docs[row]
        {"ver": self._ver, "descargar": self._descargar, "imprimir": self._imprimir,
         "compartir": self._compartir, "correo": self._enviar_correo,
         "eliminar": self._eliminar}.get(acc, lambda _d: None)(d)

    # ---------------------------------------------------------------- acciones
    def _aviso(self, titulo, msg, nivel="info"):
        if mostrar_mensaje is not None:
            mostrar_mensaje(self, titulo, msg, nivel=nivel)

    def _ruta_existente(self, d):
        ruta = d.get("ruta") or ""
        if ruta and os.path.exists(ruta):
            return ruta                        # DEV/local: fichero presente → sin cambios
        # Fase 12 (H1): en filesystem efímero (Fargate/S3) el fichero local puede no existir → se materializa
        # desde el StorageProvider (tenant + RBAC), a un temporal, para abrir/imprimir/compartir a nivel de SO.
        mat = self._materializar_desde_storage(d)
        if mat:
            return mat
        self._aviso(tr("doc.no_encontrado_t", default="Documento no encontrado"),
                    tr("doc.no_encontrado", default="El fichero ya no existe en disco."),
                    nivel="error")
        return None

    def _materializar_desde_storage(self, d):
        """Descarga el documento desde el StorageProvider a un temporal seguro (tenant-aware). None si no
        procede/falla. Reutiliza la capa segura `storage.documentos.abrir_documento` (no accede a S3 aquí)."""
        try:
            import tempfile

            from src.db.empresa import empresa_actual_id
            from src.services.storage.documentos import abrir_documento
            id_doc = d.get("id_documento")
            if not id_doc:
                return None
            r = abrir_documento(id_doc, id_empresa=empresa_actual_id(),
                                usuario=getattr(self, "usuario", None))
            if not r.get("ok") or not r.get("datos"):
                return None
            # "Repositorio cifrado" (petición explícita): la copia en storage puede estar cifrada
            # en reposo (se cifra ANTES de subirse — ver `cripto.cifrar_archivo_en_disco` en los
            # generadores) — se descifra aquí para que el temporal sea un PDF legible de verdad.
            from src.utils import cripto
            datos = cripto.descifrar_bytes_si_cifrado(r["datos"])
            ext = os.path.splitext(d.get("nombre") or "doc.pdf")[1] or ".pdf"
            fd, tmp = tempfile.mkstemp(prefix="smdoc_", suffix=ext)
            with os.fdopen(fd, "wb") as f:
                f.write(datos)
            return tmp
        except Exception:
            return None

    def _ver(self, d):
        ruta = self._ruta_existente(d)
        if ruta:
            try:
                from src.utils import plataforma
                plataforma.abrir_archivo(ruta)
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
                from src.utils import cripto
                shutil.copy2(cripto.resolver_ruta_legible(ruta), destino)
                self._aviso(tr("doc.ok_t", default="Hecho"),
                            tr("doc.descargado", default="Documento guardado."))
            except Exception as e:
                self._aviso("Error", str(e), nivel="error")

    def _imprimir(self, d):
        ruta = self._ruta_existente(d)
        if ruta:
            try:
                from src.utils import plataforma
                plataforma.imprimir_archivo(ruta)
            except Exception as e:
                self._aviso("Error", str(e), nivel="error")

    def _compartir(self, d):
        ruta = self._ruta_existente(d)
        if not ruta:
            return
        try:
            from PyQt6.QtWidgets import QApplication
            from src.utils import plataforma
            QApplication.clipboard().setText(ruta)
            plataforma.abrir_carpeta(ruta)
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
        self.close()  # cerrar de verdad (no dejar la ventana en la barra de tareas)
