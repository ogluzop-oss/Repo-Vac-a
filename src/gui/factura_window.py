"""
Ventana de Facturación del TPV.

Permite localizar ventas registradas (asignadas o no a un cliente), revisar el ticket
digital antes de facturar, asignar la venta a un CLIENTE REGISTRADO y generar la factura
comercial. Reutiliza la infraestructura existente:
  - búsqueda/listado de ventas:  src.db.ventas_busqueda (incluye escaneo de código de ticket)
  - clientes registrados:        src.db.clientes
  - cálculo de base/IVA:         src.utils.fiscalidad
  - creación de la factura:      src.db.facturas_cliente.crear_factura

Regla de negocio: NO se permite generar una factura sin asignar antes la venta a un
cliente registrado.
"""
import logging
import os

from PyQt6.QtCore import QEvent, QObject, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QBitmap, QColor, QFont, QIcon, QPainter, QPen, QPixmap, QRegion
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenu, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from assets.estilo_global import mostrar_confirmacion, mostrar_mensaje
from src.db import clientes as CLI
from src.db import facturas_cliente as FC
from src.db import ventas_busqueda as VB
from src.utils import factura_pdf, fiscalidad
from src.utils.i18n import tr

logger = logging.getLogger(__name__)

_CIAN = "#00FFC6"
_FONDO = "#0E1117"
_PANEL = "#161B22"
_BORDE = "#30363D"
_TEXTO = "#E6EDF3"

_INPUT_SS = (
    f"QLineEdit{{background:{_PANEL};color:{_TEXTO};border:2px solid {_BORDE};"
    f"border-radius:10px;padding:8px 14px;font-size:14px;font-family:'Segoe UI';min-height:24px;}}"
    f"QLineEdit:focus{{border-color:{_CIAN};}}"
)
_BTN_CIAN = (
    f"QPushButton{{background:{_CIAN};color:#0B1118;border:none;border-radius:10px;"
    f"padding:10px 18px;font-weight:bold;font-family:'Segoe UI';font-size:14px;}}"
    f"QPushButton:hover{{background:#FFFFFF;}}"
    f"QPushButton:disabled{{background:#2A3038;color:#6E7681;}}"
)
_BTN_GREY = (
    f"QPushButton{{background:transparent;color:{_TEXTO};border:2px solid {_BORDE};"
    f"border-radius:10px;padding:10px 18px;font-weight:bold;font-family:'Segoe UI';font-size:13px;}}"
    f"QPushButton:hover{{border-color:{_CIAN};color:{_CIAN};}}"
)
_TABLA_SS = (
    f"QTableWidget{{background:{_PANEL};color:{_TEXTO};border:2px solid {_CIAN};"
    f"border-radius:12px;gridline-color:{_BORDE};font-size:13px;font-family:'Segoe UI';}}"
    f"QTableWidget::item{{padding:6px;}}"
    f"QTableWidget::item:selected{{background:{_CIAN};color:#0B1118;}}"
    f"QHeaderView::section{{background:{_FONDO};color:{_CIAN};border:none;"
    f"border-bottom:2px solid {_CIAN};padding:8px;font-weight:bold;}}"
    f"QHeaderView::section:hover{{background:{_CIAN};color:#0B1118;}}"
    f"QHeaderView::section:horizontal:first{{border-top-left-radius:10px;}}"
    f"QHeaderView::section:horizontal:last{{border-top-right-radius:10px;}}"
)


def _icono_accion(name: str, color: str, size: int = 22) -> QIcon:
    """Iconos vectoriales 'ver' y 'eliminar' (mismos trazos que el Centro Documental)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color)); pen.setWidthF(1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
    cx, cy = size / 2, size / 2
    if name == "ver":
        p.drawEllipse(QPointF(cx, cy), 8.5, 5.2)
        p.setBrush(QColor(color)); p.drawEllipse(QPointF(cx, cy), 2.1, 2.1)
    elif name == "eliminar":
        p.drawLine(QPointF(cx - 7, cy - 5), QPointF(cx + 7, cy - 5))
        p.drawLine(QPointF(cx - 2.5, cy - 5), QPointF(cx - 2.5, cy - 7))
        p.drawLine(QPointF(cx - 2.5, cy - 7), QPointF(cx + 2.5, cy - 7))
        p.drawLine(QPointF(cx + 2.5, cy - 7), QPointF(cx + 2.5, cy - 5))
        p.drawLine(QPointF(cx - 5, cy - 5), QPointF(cx - 4, cy + 8))
        p.drawLine(QPointF(cx + 5, cy - 5), QPointF(cx + 4, cy + 8))
        p.drawLine(QPointF(cx - 4, cy + 8), QPointF(cx + 4, cy + 8))
        p.drawLine(QPointF(cx - 1.6, cy - 2), QPointF(cx - 1.6, cy + 5))
        p.drawLine(QPointF(cx + 1.6, cy - 2), QPointF(cx + 1.6, cy + 5))
    p.end()
    return QIcon(pm)


class _IconBtn(QPushButton):
    """Botón solo-icono con HOVER SWAP (icono oscuro sobre fondo de acento), como las
    acciones del Centro Documental."""

    def __init__(self, name: str, color: str):
        super().__init__()
        self._accent = color
        self._ic_normal = _icono_accion(name, color)
        self._ic_hover = _icono_accion(name, "#0B1118")
        self.setIcon(self._ic_normal)
        self.setIconSize(QSize(20, 20))
        self.setFixedSize(36, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._ss_normal = (f"QPushButton{{background:transparent;border:1px solid {_BORDE};"
                           f"border-radius:7px;}}")
        self._ss_hover = (f"QPushButton{{background:{color};border:1px solid {color};"
                          f"border-radius:7px;}}")
        self.setStyleSheet(self._ss_normal)

    def enterEvent(self, e):  # noqa: N802
        self.setIcon(self._ic_hover)
        self.setStyleSheet(self._ss_hover)
        super().enterEvent(e)

    def leaveEvent(self, e):  # noqa: N802
        self.setIcon(self._ic_normal)
        self.setStyleSheet(self._ss_normal)
        super().leaveEvent(e)


class _RoundTableCorners(QObject):
    """Redondea con máscara las esquinas exteriores de la tabla y las superiores de la
    cabecera (el QSS por sí solo no redondea la cabecera de forma fiable)."""

    def __init__(self, table, radius=12):
        super().__init__(table)
        self._r = radius
        self._table = table
        table.installEventFilter(self)
        table.horizontalHeader().installEventFilter(self)

    def eventFilter(self, obj, event):  # noqa: N802 (API Qt)
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show) and obj.width() > 0:
            if obj is self._table:
                rect = QRect(0, 0, obj.width(), obj.height())
            else:  # cabecera: redondea solo arriba (extiende el rect por abajo)
                rect = QRect(0, 0, obj.width(), obj.height() + self._r)
            bmp = QBitmap(obj.size())
            bmp.fill(Qt.GlobalColor.color0)
            p = QPainter(bmp)
            p.setBrush(Qt.GlobalColor.color1)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, self._r, self._r)
            p.end()
            obj.setMask(QRegion(bmp))
        return False


def _fmt_eur(v) -> str:
    try:
        return f"{float(v or 0):.2f} €"
    except Exception:
        return "0,00 €"


def _nif_match(c: dict, nif: str) -> bool:
    return (c.get("nif") or "").strip().upper() == (nif or "").strip().upper()


# ============================================================
# Ticket digital (vista de confirmación, solo lectura)
# ============================================================
class _TicketDialog(QDialog):
    def __init__(self, venta: dict, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(700, 620)
        _root = QVBoxLayout(self)
        _root.setContentsMargins(0, 0, 0, 0)
        card = QFrame(self)
        card.setObjectName("card")
        card.setStyleSheet(
            f"QFrame#card{{background:{_FONDO};border:2px solid {_CIAN};border-radius:18px;}}")
        _root.addWidget(card)
        ly = QVBoxLayout(card)
        ly.setContentsMargins(22, 22, 22, 22)
        ly.setSpacing(10)

        tit = QLabel(tr("fact.ticket_header", default="🧾 TICKET DIGITAL"))
        tit.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:18px;")
        ly.addWidget(tit)

        cab = (f"Ticket Nº {venta.get('id')}   ·   {venta.get('fecha')}\n"
               f"Cajero: {venta.get('empleado') or '—'}   ·   Caja: {venta.get('numero_caja') or '—'}\n"
               f"Cliente: {venta.get('cliente_nombre') or tr('fact.no_client', default='(sin asignar)')}"
               + (f"   ·   NIF: {venta.get('cliente_nif')}" if venta.get('cliente_nif') else ""))
        lcab = QLabel(cab)
        lcab.setStyleSheet(f"color:{_TEXTO};font-size:13px;")
        lcab.setWordWrap(True)
        ly.addWidget(lcab)

        items = venta.get("items") or []
        tabla = QTableWidget(len(items), 4)
        tabla.setHorizontalHeaderLabels([
            tr("fact.col_item", default="Artículo"), tr("fact.col_qty", default="Cant."),
            tr("fact.col_price", default="P.Unit."), tr("fact.col_subtotal", default="Subtotal")])
        tabla.setStyleSheet(_TABLA_SS)
        _RoundTableCorners(tabla)
        tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tabla.verticalHeader().setVisible(False)
        tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i, it in enumerate(items):
            tabla.setItem(i, 0, QTableWidgetItem(str(it.get("nombre") or it.get("codigo_articulo") or "")))
            tabla.setItem(i, 1, QTableWidgetItem(str(it.get("cantidad") or 0)))
            tabla.setItem(i, 2, QTableWidgetItem(_fmt_eur(it.get("precio_unitario"))))
            tabla.setItem(i, 3, QTableWidgetItem(_fmt_eur(it.get("subtotal"))))
        ly.addWidget(tabla, 1)

        desg = fiscalidad.desglose_iva(venta.get("total"))
        tot = QLabel(
            f"{tr('fact.base', default='Base imponible')}: {_fmt_eur(desg.get('base'))}\n"
            f"{tr('fact.iva', default='IVA')} ({desg.get('tipo')}%): {_fmt_eur(desg.get('cuota'))}\n"
            f"{tr('fact.total', default='TOTAL')}: {_fmt_eur(venta.get('total'))}")
        tot.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:15px;")
        tot.setAlignment(Qt.AlignmentFlag.AlignRight)
        ly.addWidget(tot)

        bcerrar = QPushButton(tr("fact.close", default="CERRAR"))
        bcerrar.setStyleSheet(_BTN_GREY)
        bcerrar.clicked.connect(self.accept)
        ly.addWidget(bcerrar, alignment=Qt.AlignmentFlag.AlignRight)


# ============================================================
# Selector de cliente registrado (popup de asignación)
# ============================================================
class _SelectorClienteDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cliente = None
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(660, 540)
        _root = QVBoxLayout(self)
        _root.setContentsMargins(0, 0, 0, 0)
        card = QFrame(self)
        card.setObjectName("card")
        card.setStyleSheet(
            f"QFrame#card{{background:{_FONDO};border:2px solid {_CIAN};border-radius:18px;}}")
        _root.addWidget(card)
        ly = QVBoxLayout(card)
        ly.setContentsMargins(22, 22, 22, 22)
        ly.setSpacing(12)

        tit = QLabel(tr("fact.assign_header", default="👤 SELECCIONE UN CLIENTE REGISTRADO"))
        tit.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:17px;")
        ly.addWidget(tit)

        info = QLabel(tr("fact.assign_info",
                         default="Si no encuentra al cliente deseado, asegúrese de haber registrado "
                                 "correctamente al cliente en la función «Clientes» del TPV."))
        info.setWordWrap(True)
        info.setStyleSheet("color:#F0B429;font-size:12px;background:transparent;")
        ly.addWidget(info)

        fila = QHBoxLayout()
        self.buscar = QLineEdit()
        self.buscar.setPlaceholderText(tr("fact.client_search_ph", default="Nombre, NIF, teléfono o email…"))
        self.buscar.setStyleSheet(_INPUT_SS)
        self.buscar.returnPressed.connect(self._buscar)
        b = QPushButton(tr("fact.search", default="BUSCAR"))
        b.setStyleSheet(_BTN_CIAN)
        b.clicked.connect(self._buscar)
        fila.addWidget(self.buscar, 1)
        fila.addWidget(b)
        ly.addLayout(fila)

        self.tabla = QTableWidget(0, 4)
        self.tabla.setHorizontalHeaderLabels(["Nombre", "NIF", "Teléfono", "Email"])
        self.tabla.setStyleSheet(_TABLA_SS)
        _RoundTableCorners(self.tabla)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla.doubleClicked.connect(self._aceptar)
        ly.addWidget(self.tabla, 1)

        botones = QHBoxLayout()
        bc = QPushButton(tr("fact.cancel", default="CANCELAR"))
        bc.setStyleSheet(_BTN_GREY)
        bc.clicked.connect(self.reject)
        ba = QPushButton(tr("fact.assign_btn", default="ASIGNAR Y FACTURAR"))
        ba.setStyleSheet(_BTN_CIAN)
        ba.clicked.connect(self._aceptar)
        botones.addStretch()
        botones.addWidget(bc)
        botones.addWidget(ba)
        ly.addLayout(botones)

        self._filas = []
        self._cargar(CLI.listar_clientes(limite=200))

    def _cargar(self, lista):
        self._filas = lista or []
        self.tabla.setRowCount(len(self._filas))
        for i, c in enumerate(self._filas):
            self.tabla.setItem(i, 0, QTableWidgetItem(str(c.get("nombre") or "")))
            self.tabla.setItem(i, 1, QTableWidgetItem(str(c.get("nif") or "")))
            self.tabla.setItem(i, 2, QTableWidgetItem(str(c.get("telefono") or "")))
            self.tabla.setItem(i, 3, QTableWidgetItem(str(c.get("email") or "")))

    def _buscar(self):
        self._cargar(CLI.buscar_clientes(self.buscar.text().strip(), limite=200))

    def _aceptar(self, *_):
        r = self.tabla.currentRow()
        if r < 0 or r >= len(self._filas):
            mostrar_mensaje(self, tr("fact.no_sel_title", default="Sin selección"),
                            tr("fact.no_sel_client", default="Seleccione un cliente de la lista."), "warning")
            return
        self.cliente = self._filas[r]
        self.accept()


# ============================================================
# Ventana principal de Facturación
# ============================================================
class FacturaWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None):
        super().__init__()
        self._callback_vuelta = callback_vuelta
        self.usuario = usuario or {}
        self.setWindowTitle(tr("fact.window_title", default="Facturas"))
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(f"background:{_FONDO};color:{_TEXTO};")
        self._ventas = []
        self._build()
        self._buscar()  # carga inicial: ventas recientes

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)

        # Cabecera
        cab = QHBoxLayout()
        tit = QLabel(tr("fact.title", default="🧾 FACTURAS"))
        tit.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:22px;")
        cab.addWidget(tit)
        cab.addStretch()
        bvolver = QPushButton("✕")
        bvolver.setFixedSize(50, 44)
        bvolver.setCursor(Qt.CursorShape.PointingHandCursor)
        bvolver.setStyleSheet(
            "QPushButton{background:transparent;color:#F85149;border:2px solid #F85149;"
            "border-radius:9px;font-size:18px;font-weight:900;}"
            "QPushButton:hover{background:#F85149;color:#0B1118;}")
        bvolver.clicked.connect(self._volver)
        cab.addWidget(bvolver)
        root.addLayout(cab)

        desc = QLabel(tr("fact.desc",
                         default="Busque la venta por cliente (nombre, NIF, teléfono, email) o escanee el "
                                 "código de barras del ticket. Doble clic en una venta para ver su ticket."))
        desc.setStyleSheet("color:#8B949E;font-size:12px;")
        desc.setWordWrap(True)
        root.addWidget(desc)

        # Barra de búsqueda
        fila = QHBoxLayout()
        self.buscar = QLineEdit()
        self.buscar.setPlaceholderText(tr("fact.search_ph",
                                          default="Cliente, NIF, teléfono, email o código de barras del ticket…"))
        self.buscar.setStyleSheet(_INPUT_SS)
        self.buscar.returnPressed.connect(self._buscar)
        bb = QPushButton(tr("fact.search", default="BUSCAR"))
        bb.setStyleSheet(_BTN_CIAN)
        bb.setMinimumWidth(120)   # evita que el texto se corte en horizontal
        bb.setMinimumHeight(44)   # altura suficiente: el padding+fuente recortaban el texto abajo
        bb.clicked.connect(self._buscar)
        fila.addWidget(self.buscar, 1)
        fila.addWidget(bb)
        root.addLayout(fila)

        # Tabla de ventas
        self.tabla = QTableWidget(0, 8)
        self.tabla.setHorizontalHeaderLabels([
            tr("fact.col_ticket", default="Ticket"), tr("fact.col_date", default="Fecha"),
            tr("fact.col_client", default="Cliente"), tr("fact.col_total", default="Importe"),
            tr("fact.col_pay", default="Pago"), tr("fact.col_cashier", default="Cajero"),
            tr("fact.col_nitems", default="Artículos"), tr("fact.col_actions", default="Acciones")])
        self.tabla.setStyleSheet(_TABLA_SS)
        _RoundTableCorners(self.tabla)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(52)  # alto de fila (botones Acciones)
        self.tabla.verticalHeader().setMinimumSectionSize(50)
        hh = self.tabla.horizontalHeader()
        for c in range(self.tabla.columnCount()):  # anchura equitativa para todas las columnas
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        self.tabla.doubleClicked.connect(lambda *_: self._ver_ticket())
        self.tabla.itemSelectionChanged.connect(self._sync_botones)
        root.addWidget(self.tabla, 1)

        # Acciones
        acc = QHBoxLayout()
        self.lbl_estado = QLabel("")
        self.lbl_estado.setStyleSheet("color:#8B949E;font-size:12px;")
        acc.addWidget(self.lbl_estado)
        acc.addStretch()
        # Tipo de documento (FASE 3.3/3.4): factura / simplificada / proforma / intracom.
        self.cmb_tipo = QComboBox()
        self.cmb_tipo.addItem(tr("fact.tipo_factura", default="Factura"), "factura")
        self.cmb_tipo.addItem(tr("fact.tipo_simpl", default="Simplificada"), "simplificada")
        self.cmb_tipo.addItem(tr("fact.tipo_proforma", default="Proforma"), "proforma")
        self.cmb_tipo.addItem(tr("fact.tipo_intra", default="Intracomunitaria"), "intracomunitaria")
        self.cmb_tipo.setMinimumWidth(180)   # cabe "Intracomunitaria" sin abreviar
        self.cmb_tipo.setMinimumContentsLength(16)
        self.cmb_tipo.setStyleSheet(
            "QComboBox{background:#0D1117;color:#E6EDF3;border:2px solid #30363D;border-radius:8px;"
            "padding:4px 10px;font-weight:700;}QComboBox:hover{border-color:#22F4E6;}"
            "QComboBox QAbstractItemView{min-width:180px;}")
        self.btn_ticket = QPushButton(tr("fact.view_ticket", default="👁  VER TICKET"))
        self.btn_ticket.setStyleSheet(_BTN_GREY)
        self.btn_ticket.clicked.connect(self._ver_ticket)
        self.btn_dist = QPushButton(tr("fact.distribuir", default="📤  EXPORTAR / ENVIAR"))
        self.btn_dist.setStyleSheet(_BTN_GREY)
        self.btn_dist.clicked.connect(self._distribuir)
        # Cobro express (ledger, NO pasarela): registra el saldo pendiente de la venta como cobrado en 1 clic.
        self.btn_cobrar = QPushButton(tr("fact.cobrar_express", default="💶  COBRAR"))
        self.btn_cobrar.setStyleSheet(_BTN_CIAN)
        self.btn_cobrar.setToolTip(tr("fact.cobrar_tip",
                                      default="Registra el saldo pendiente de la venta como cobrado (efectivo)."))
        self.btn_cobrar.clicked.connect(self._cobrar_express)
        self.btn_factura = QPushButton(tr("fact.generate", default="🧾  GENERAR FACTURA"))
        self.btn_factura.setStyleSheet(_BTN_CIAN)
        self.btn_factura.clicked.connect(self._generar_factura)
        acc.addWidget(self.cmb_tipo)
        acc.addWidget(self.btn_ticket)
        acc.addWidget(self.btn_dist)
        acc.addWidget(self.btn_cobrar)
        acc.addWidget(self.btn_factura)
        root.addLayout(acc)
        self._sync_botones()

    # ---- datos ----
    def _buscar(self):
        texto = self.buscar.text().strip()
        try:
            self._ventas = VB.buscar_ventas(texto=texto or None, limite=500, excluir_ocultas=True)
        except Exception as e:
            logger.error("buscar_ventas: %s", e)
            self._ventas = []
        # Mapa venta -> nº de factura ya generada (para el botón "Abrir factura").
        mapa = {}
        try:
            # Mapa = factura PRINCIPAL por venta (se omiten las rectificativas/abonos, que son
            # documentos aparte). Se conserva la más reciente por venta y su estado.
            for f in FC.listar_facturas(limite=1000):
                if not f.get("id_venta") or f.get("tipo_documento") == "rectificativa":
                    continue
                if f["id_venta"] in mapa:
                    continue  # listar_facturas viene en orden DESC → la primera es la más reciente
                num = f.get("numero") or f"FC{int(f.get('id_factura') or 0):06d}"
                mapa[f["id_venta"]] = {"id": f.get("id_factura"), "numero": num,
                                       "estado": f.get("estado")}
        except Exception:
            pass
        self._mapa_fac = mapa   # venta_id -> factura (para exportar/enviar)
        self.tabla.setRowCount(len(self._ventas))
        for i, v in enumerate(self._ventas):
            cli = v.get("cliente_nombre") or tr("fact.no_client", default="(sin asignar)")
            celdas = [str(v.get("id")), str(v.get("fecha") or ""), cli,
                      _fmt_eur(v.get("total")), str(v.get("forma_pago") or ""),
                      str(v.get("empleado") or ""), str(v.get("n_items") or 0)]
            for j, txt in enumerate(celdas):
                it = QTableWidgetItem(txt)
                if j == 6:  # "Artículos" centrado
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tabla.setItem(i, j, it)
            # Columna "Acciones": ver (ojo) y eliminar (papelera) la factura si existe.
            fac = mapa.get(v.get("id"))
            if fac:
                cont = QWidget(); cl = QHBoxLayout(cont)
                cl.setContentsMargins(6, 4, 6, 4); cl.setSpacing(8)
                cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                bver = _IconBtn("ver", _CIAN)
                bver.clicked.connect(
                    lambda _=False, n=fac["numero"], fid=fac["id"]: self._abrir_factura_pdf(n, fid))
                cl.addWidget(bver)
                if fac.get("estado") == "anulada":
                    et = QLabel(tr("fact.anulada", default="ANULADA"))
                    et.setStyleSheet("color:#F85149;font-weight:900;font-size:11px;")
                    cl.addWidget(et)
                else:
                    bdel = _IconBtn("eliminar", "#F85149")
                    bdel.setToolTip(tr("fact.anular_tip", default="Anular factura (genera abono)"))
                    bdel.clicked.connect(
                        lambda _=False, fid=fac["id"], n=fac["numero"], vid=v.get("id"):
                        self._anular_factura(fid, n, vid))
                    cl.addWidget(bdel)
                self.tabla.setCellWidget(i, 7, cont)
            else:
                it = QTableWidgetItem("—")
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tabla.setItem(i, 7, it)
            self.tabla.setRowHeight(i, 52)  # espacio para los botones de acción
        self.lbl_estado.setText(tr("fact.found", default="{n} venta(s) encontrada(s)", n=len(self._ventas)))
        self._sync_botones()

    def _abrir_factura_pdf(self, numero, id_factura=None):
        """Abre el PDF de la factura. Si el fichero no existe, lo REGENERA desde el snapshot
        congelado (documento idéntico al emitido)."""
        ruta = factura_pdf.ruta_factura(numero)
        if not os.path.exists(ruta) and id_factura is not None:
            try:
                snap = FC.obtener_snapshot(id_factura)
                if snap:
                    factura_pdf.generar_pdf_desde_snapshot(snap)
            except Exception as e:
                logger.error("regenerar factura desde snapshot: %s", e)
        if os.path.exists(ruta):
            from src.utils import plataforma
            plataforma.abrir_archivo(ruta)
            if id_factura is not None:
                try:
                    FC.registrar_evento(id_factura, "vista")
                except Exception:
                    pass
        else:
            mostrar_mensaje(self, tr("fact.error", default="Factura"),
                            tr("fact.pdf_missing", default="El PDF de la factura no está disponible."), "warning")

    def _quitar_fila(self, venta_id):
        """Quita la fila de la venta indicada de la tabla (tras eliminar su factura)."""
        for i, v in enumerate(self._ventas):
            if v.get("id") == venta_id:
                self.tabla.removeRow(i)
                self._ventas.pop(i)
                break
        self.lbl_estado.setText(
            tr("fact.found", default="{n} venta(s) encontrada(s)", n=len(self._ventas)))
        self._sync_botones()

    def _anular_factura(self, id_factura, numero, venta_id=None):
        """Anula la factura (estado='anulada') y genera una factura de abono (rectificativa).
        NO elimina ningún documento ni archivo: conformidad fiscal. Con confirmación."""
        if not mostrar_confirmacion(
                self, tr("fact.anul_title", default="Anular factura"),
                tr("fact.anul_msg", default="¿Anular la factura {n}? Se generará una factura de "
                   "abono (rectificativa). No se elimina ningún documento.", n=numero)):
            return
        try:
            res = FC.anular_factura(id_factura)
        except Exception as e:
            logger.error("anular_factura: %s", e); res = {"ok": False}
        if not res.get("ok"):
            mostrar_mensaje(self, tr("fact.error", default="Error"),
                            tr("fact.anul_err", default="No se pudo anular la factura."), "warning")
            return
        # PDF del abono + alta en el Centro Documental (no se toca el PDF original).
        try:
            if res.get("id_abono"):
                ab = FC.obtener_factura(res["id_abono"]) or {}
                cli = {}
                if ab.get("id_cliente"):
                    cli = CLI.obtener_cliente(ab.get("id_cliente")) or {}
                items = [{"nombre": l.get("descripcion") or l.get("codigo_articulo"),
                          "cantidad": l.get("cantidad"),
                          "precio_unitario": l.get("precio_unitario"),
                          "subtotal": l.get("subtotal")} for l in (ab.get("lineas") or [])]
                imp_ab = FC.obtener_impuestos(res["id_abono"])
                snap_ab = factura_pdf.construir_snapshot(
                    ab, cli, items, impuestos=imp_ab, emisor=factura_pdf.emisor())
                FC.guardar_snapshot(res["id_abono"], snap_ab)
                factura_pdf.generar_y_registrar(ab, cli, items, snapshot=snap_ab)
        except Exception as e:
            logger.error("PDF abono: %s", e)
        mostrar_mensaje(
            self, tr("fact.anul_ok_title", default="Factura anulada"),
            tr("fact.anul_ok", default="Factura {n} anulada. Abono {a} generado.",
               n=numero, a=res.get("numero_abono") or ""), "success")
        self.raise_(); self.activateWindow()
        # Refresco DIFERIDO: no destruir el botón emisor dentro de su propio clic.
        QTimer.singleShot(0, self._buscar)

    def _venta_seleccionada(self) -> dict | None:
        r = self.tabla.currentRow()
        if 0 <= r < len(self._ventas):
            return self._ventas[r]
        return None

    def _sync_botones(self):
        v = self._venta_seleccionada()
        hay = v is not None
        self.btn_ticket.setEnabled(hay)
        self.btn_factura.setEnabled(hay)
        if hasattr(self, "btn_dist"):
            self.btn_dist.setEnabled(hay)
        if hasattr(self, "btn_cobrar"):
            self.btn_cobrar.setEnabled(hay and self._saldo_pendiente(v) > 0.005)

    def _saldo_pendiente(self, venta) -> float:
        """Saldo pendiente de cobro de la venta (best-effort; 0 ante cualquier problema)."""
        if not venta:
            return 0.0
        try:
            from src.db import cobros as CB
            return CB.saldo_pendiente(venta.get("id"), float(venta.get("total") or 0))
        except Exception:
            return 0.0

    def _cobrar_express(self):
        """Cobro express de FACTURACIÓN: registra el saldo pendiente de la venta seleccionada como cobrado
        (ledger `db/cobros`, método efectivo). No es un cobro por pasarela (eso es Comercio Digital)."""
        v = self._venta_seleccionada()
        if not v:
            return
        saldo = self._saldo_pendiente(v)
        if saldo <= 0.005:
            mostrar_mensaje(self, tr("fact.cobrar_title", default="Cobro"),
                            tr("fact.cobrar_ya", default="La venta ya está cobrada por completo."), "info")
            return
        if not mostrar_confirmacion(
                self, tr("fact.cobrar_title", default="Cobro express"),
                tr("fact.cobrar_msg", default="¿Registrar el cobro del saldo pendiente ({s}) como efectivo?",
                   s=_fmt_eur(saldo))):
            return
        try:
            from src.db import cobros as CB
            r = CB.cobrar_pendiente(v.get("id"), float(v.get("total") or 0), metodo="efectivo")
        except Exception as e:
            logger.error("cobrar_express: %s", e); r = {"ok": False, "error": str(e)}
        if r.get("ok"):
            mostrar_mensaje(self, tr("fact.cobrar_title", default="Cobro express"),
                            tr("fact.cobrar_ok", default="Cobro registrado: {s}.",
                               s=_fmt_eur(r.get("importe") or saldo)), "success")
            self._sync_botones()
        else:
            mostrar_mensaje(self, tr("fact.cobrar_title", default="Cobro express"),
                            tr("fact.cobrar_err", default="No se pudo registrar el cobro."), "warning")

    def _distribuir(self):
        """Exporta (PDF/Facturae) o envía por email la factura de la venta seleccionada
        (FASE 3.8). Reutiliza el servicio de distribución."""
        v = self._venta_seleccionada()
        fac = (getattr(self, "_mapa_fac", {}) or {}).get(v.get("id")) if v else None
        if not fac:
            mostrar_mensaje(self, tr("fact.error", default="Facturas"),
                            tr("fact.sin_factura", default="La venta seleccionada no tiene factura generada."),
                            "warning")
            return
        fid = fac["id"]
        menu = QMenu(self)
        a_pdf = menu.addAction(tr("fact.exp_pdf", default="Exportar PDF"))
        a_xml = menu.addAction(tr("fact.exp_facturae", default="Exportar Facturae (XML)"))
        a_mail = menu.addAction(tr("fact.env_email", default="Enviar por email"))
        act = menu.exec(self.btn_dist.mapToGlobal(self.btn_dist.rect().bottomLeft()))
        if act is None:
            return
        from src.services.facturacion import distribucion as D
        try:
            if act == a_pdf:
                ruta = D.exportar_factura(fid, "pdf")
                _ok = bool(ruta)
                msg = tr("fact.exp_ok", default="PDF exportado.") if _ok else tr("fact.exp_err", default="No se pudo exportar.")
            elif act == a_xml:
                ruta = D.exportar_factura(fid, "facturae")
                _ok = bool(ruta)
                msg = tr("fact.exp_ok", default="Facturae exportado.") if _ok else tr("fact.exp_err", default="No se pudo exportar (¿documento no fiscal?).")
            else:
                # email: requiere una cuenta de correo corporativo configurada (OAuth).
                res = D.enviar_factura_email(fid, id_correo=self._correo_id(), destinatario=None)
                _ok = res.get("ok")
                msg = (tr("fact.env_ok", default="Factura enviada a {d}.", d=res.get("destinatario") or "")
                       if _ok else tr("fact.env_err", default="No se pudo enviar: {m}", m=res.get("mensaje") or ""))
        except Exception as e:
            logger.error("distribuir: %s", e); _ok, msg = False, str(e)
        mostrar_mensaje(self, tr("fact.distribuir", default="Distribución"), msg,
                        "success" if _ok else "warning")

    def _correo_id(self):
        """Primera cuenta de correo corporativo de la empresa (para enviar facturas)."""
        try:
            from src.db import correo as C
            cuentas = C.listar_correos() if hasattr(C, "listar_correos") else []
            return (cuentas[0].get("id_correo") or cuentas[0].get("correo")) if cuentas else None
        except Exception:
            return None

    def _ver_ticket(self):
        v = self._venta_seleccionada()
        if not v:
            return
        completa = VB.obtener_venta_completa(v.get("id"))
        if not completa:
            mostrar_mensaje(self, tr("fact.error", default="Error"),
                            tr("fact.no_ticket", default="No se pudo cargar el ticket de la venta."), "warning")
            return
        _TicketDialog(completa, self).exec()

    # ---- facturación ----
    def _generar_factura(self):
        v = self._venta_seleccionada()
        if not v:
            return
        completa = VB.obtener_venta_completa(v.get("id"))
        if not completa:
            mostrar_mensaje(self, tr("fact.error", default="Error"),
                            tr("fact.no_ticket", default="No se pudo cargar la venta."), "warning")
            return

        # 1) ¿La venta ya está asignada a un cliente REGISTRADO?
        cliente = None
        nif = completa.get("cliente_nif")
        if nif:
            try:
                cands = CLI.buscar_clientes(nif, limite=20)
                cliente = next((c for c in cands if _nif_match(c, nif)), None)
            except Exception:
                cliente = None

        # 2) Si no, pedir selección de cliente registrado (popup de asignación).
        if cliente is None:
            dlg = _SelectorClienteDialog(self)
            if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.cliente:
                # Regla de negocio: no se factura sin cliente registrado asignado.
                mostrar_mensaje(
                    self, tr("fact.need_client_title", default="Factura no generada"),
                    tr("fact.need_client", default="No se puede generar una factura sin asignar la "
                       "venta a un cliente registrado."), "warning")
                return
            cliente = dlg.cliente
            # Asignar (denormalizar) el cliente a la venta.
            VB.asignar_cliente_venta(v.get("id"), cliente.get("id"),
                                     cliente.get("nombre"), cliente.get("nif"))

        # 3) Crear la factura con base/IVA desglosados del total IVA-incluido.
        desg = fiscalidad.desglose_iva(completa.get("total"))
        lineas = [{
            "codigo": it.get("codigo_articulo"),
            "codigo_articulo": it.get("codigo_articulo"),
            "descripcion": it.get("nombre"),
            "cantidad": it.get("cantidad"),
            "precio_unitario": it.get("precio_unitario"),
            "subtotal": it.get("subtotal"),               # subtotal REAL (granel/descuentos)
            "peso_vendido": it.get("peso_vendido"),        # peso para líneas a granel
            "precio_kg": it.get("precio_kg"),
            "modo_venta": it.get("modo_venta"),
        } for it in (completa.get("items") or [])]
        try:
            tipo_doc = self.cmb_tipo.currentData() or "factura"
            fid = FC.crear_factura(id_cliente=cliente.get("id"), id_venta=v.get("id"),
                                   lineas=lineas, base=desg.get("base"), iva=desg.get("cuota"),
                                   tipo_documento=tipo_doc)
        except Exception as e:
            logger.error("crear_factura: %s", e)
            fid = None
        if not fid:
            mostrar_mensaje(self, tr("fact.error", default="Error"),
                            tr("fact.gen_err", default="No se pudo generar la factura."), "error")
            return

        # PDF de la factura + alta en el Centro Documental (tipo 'factura').
        numero = f"FC{fid:06d}"
        try:
            fdata = FC.obtener_factura(fid) or {}
            numero = fdata.get("numero") or numero
            fdata.setdefault("numero", numero)
            fdata.setdefault("base", desg.get("base"))
            fdata.setdefault("iva", desg.get("cuota"))
            fdata.setdefault("total", completa.get("total"))
            fdata["forma_pago"] = completa.get("forma_pago")
            try:
                impuestos = FC.obtener_impuestos(fid)
            except Exception:
                impuestos = None
            fiscal = None  # QR/leyenda legal del registro fiscal de la venta (si Verifactu activo)
            try:
                from src.services.fiscal.ticket import info_ticket
                fiscal = info_ticket(v.get("id"))
            except Exception:
                fiscal = None
            # Items del documento = líneas REALES almacenadas (cantidad decimal/granel, subtotal real).
            items_doc = [{
                "nombre": l.get("descripcion") or l.get("codigo_articulo"),
                "codigo_articulo": l.get("codigo_articulo"),
                "cantidad": l.get("cantidad"),
                "precio_unitario": l.get("precio_unitario"),
                "subtotal": l.get("subtotal"),
                "iva": l.get("iva"),
            } for l in (fdata.get("lineas") or [])] or (completa.get("items") or [])
            # Snapshot documental INMUTABLE (emisor/receptor/líneas/impuestos/totales/fiscal/moneda).
            snap = None
            try:
                snap = factura_pdf.construir_snapshot(
                    fdata, cliente, items_doc,
                    impuestos=impuestos, fiscal=fiscal, emisor=factura_pdf.emisor())
                FC.guardar_snapshot(fid, snap)
            except Exception as e:
                logger.error("snapshot factura: %s", e); snap = None
            factura_pdf.generar_y_registrar(fdata, cliente, items_doc,
                                            impuestos=impuestos, fiscal=fiscal, snapshot=snap)
        except Exception as e:
            logger.error("PDF/registro factura: %s", e)

        mostrar_mensaje(
            self, tr("fact.ok_title", default="Factura generada"),
            tr("fact.ok_msg", default="Factura {num} generada para {cli}.",
               num=numero, cli=cliente.get("nombre") or ""), "success")
        self.raise_(); self.activateWindow()
        self._buscar()  # refresca (la venta queda con cliente asignado)

    def _volver(self):
        if self._callback_vuelta:
            self._callback_vuelta()
        else:
            self.close()
