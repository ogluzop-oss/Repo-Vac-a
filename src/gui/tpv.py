# src/gui/tpv.py
"""Terminal Punto de Venta (TPV) — Enterprise Edition"""

from __future__ import annotations

import datetime
import json
import logging
import os

from PyQt6.QtCore import QByteArray, QEvent, QObject, QPoint, QPointF, QRectF, QSize, Qt, QTimer
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtGui import (
    QBitmap,
    QColor,
    QFont,
    QIcon,
    QIntValidator,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygon,
    QRegion,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.db.conexion import (
    obtener_articulo,
    obtener_conexion,
    stock_signals,
    transaccion,
)
from src.db.usuario import listar_usuarios, sesion_global, validar_login_empleado
from src.utils import divisas, i18n
from src.utils.customer_display_bridge import customer_display_bridge
from src.utils.i18n import tr

logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTES DE ESTILO
# ============================================================

_BG = "#0E1117"
_BG2 = "#161B22"
_CIAN = "#00FFC6"
_ROJO = "#FF4C4C"
_VERDE = "#3FB950"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_TEXT2 = "#8B949E"
_AMBAR = "#F1C40F"
_FONT = "Segoe UI"

# Extras rápidos del TPV (bolsas / sobres de regalo). código → (icono, nombre por defecto, precio, iva).
# El precio/nombre se sobrescribe si existe un artículo con ese código (para que la tienda lo configure).
_EXTRAS_TPV = {
    "BOLSA_GRANDE":         ("🛍", "Bolsa grande",        0.20, 21),
    "BOLSA_PEQUENA":        ("👜", "Bolsa pequeña",       0.10, 21),
    "SOBRE_REGALO_PEQUENO": ("🎁", "Sobre regalo peq.",   0.50, 21),
    "SOBRE_REGALO_GRANDE":  ("🎀", "Sobre regalo grande", 1.00, 21),
}

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LOGO_CORP_PATH = os.path.join(_ROOT, "documentos", "logo_corporativo.png")
_CAJA_STATE_FILE = os.path.join(_ROOT, "documentos", "estado_caja.json")
_RETENIDAS_FILE = os.path.join(_ROOT, "documentos", "tpv_retenidas.json")
_AUDIT_FILE = os.path.join(_ROOT, "documentos", "tpv_auditoria.json")
_TICKETS_DIR = os.path.join(_ROOT, "documentos", "Tickets")


# ============================================================
# HELPERS DE ESTILO
# ============================================================


def _lbl(text: str, bold: bool = False, size: int = 12, color: str = _TEXT) -> QLabel:
    lb = QLabel(text)
    lb.setStyleSheet(
        f"color:{color};font-family:'{_FONT}';font-size:{size}px;"
        f"font-weight:{'900' if bold else '500'};background:transparent;border:none;"
    )
    return lb


def _btn(
    text: str,
    color_bg: str = _BG2,
    color_fg: str = _TEXT,
    color_border: str = _BORDE,
    hover_bg: str = _CIAN,
    hover_fg: str = "#0D1117",
    h: int = 38,
    radius: int = 10,
) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(h)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(
        f"QPushButton{{background:{color_bg};color:{color_fg};"
        f"border:2px solid {color_border};border-radius:{radius}px;"
        f"font-family:'{_FONT}';font-weight:900;font-size:13px;padding:0 12px;outline:0;}}"
        f"QPushButton:hover{{background:{hover_bg};color:{hover_fg};}}"
        f"QPushButton:focus{{outline:0;}}"
    )
    return b


def _card() -> QFrame:
    f = QFrame()
    f.setStyleSheet(
        f"QFrame{{background:{_BG2};border:1px solid {_BORDE};" f"border-radius:14px;}}"
    )
    return f


def _fmt_peso(peso) -> str:
    """Formatea kilogramos mostrando decimales SOLO si son > 0 (evita '1.000 kg' para 1 kg, que se lee
    como 1000). Separador decimal español (coma). Ej.: 1.0→'1', 1.5→'1,5', 1.234→'1,234'."""
    try:
        p = round(float(peso), 3)
    except Exception:
        return str(peso)
    if p == int(p):
        return str(int(p))
    return f"{p:.3f}".rstrip("0").rstrip(".").replace(".", ",")


def _solo_texto(s: str) -> str:
    """Quita un icono/símbolo inicial (y espacios) del texto de un botón,
    p. ej. '⚖  BÁSCULA' -> 'BÁSCULA'. Conserva acentos y ñ."""
    import re

    out = re.sub(r"^[^0-9A-Za-zÁÉÍÓÚÑÜáéíóúñü]+", "", s or "").strip()
    return out or (s or "")


class _RoundTableCorners(QObject):
    """Redondea las esquinas exteriores de un QTableWidget con una máscara: las 4
    del widget y, además, las superiores de la cabecera (para que el contorno
    neón no se corte arriba)."""

    def __init__(self, table, radius=10):
        super().__init__(table)
        self._r = radius
        self._table = table
        table.installEventFilter(self)
        table.horizontalHeader().installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show) and obj.width() > 0:
            from PyQt6.QtCore import QRect

            if obj is self._table:
                rect = QRect(0, 0, obj.width(), obj.height())  # 4 esquinas
            else:  # cabecera: redondear solo arriba (extiende el rect por abajo)
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


def _ss_tabla_neon() -> str:
    """Estilo de tabla con contorno neón, cabeceras redondeadas y hover swap."""
    return (
        f"QTableWidget{{background:{_BG};color:{_TEXT};border:2px solid {_CIAN};"
        f"border-radius:10px;gridline-color:{_BORDE};font-family:'{_FONT}';font-size:12px;"
        f"selection-background-color:rgba(0,255,198,0.18);selection-color:{_CIAN};}}"
        f"QTableWidget::item{{padding:6px 10px;}}"
        f"QTableWidget::item:alternate{{background:#0B0F14;}}"
        f"QHeaderView::section{{background:{_BG2};color:{_CIAN};border:none;"
        f"border-bottom:2px solid {_CIAN};padding:9px 8px;font-weight:900;font-family:'{_FONT}';}}"
        f"QHeaderView::section:first{{border-top-left-radius:8px;}}"
        f"QHeaderView::section:last{{border-top-right-radius:8px;}}"
        f"QHeaderView::section:hover{{background:{_CIAN};color:#0D1117;}}"
    )


def _ss_tabla_interior() -> str:
    """Estilo de tabla SIN borde (para ir DENTRO de un QFrame con contorno neón): cabeceras con esquinas
    redondeadas y hover swap; el contorno redondeado lo aporta el contenedor, así no se corta."""
    return (
        f"QTableWidget{{background:{_BG};color:{_TEXT};border:none;gridline-color:{_BORDE};"
        f"font-family:'{_FONT}';font-size:13px;selection-background-color:rgba(0,255,198,0.18);"
        f"selection-color:{_CIAN};}}"
        f"QTableWidget::item{{padding:6px 10px;}}"
        f"QHeaderView::section{{background:{_BG2};color:{_CIAN};border:none;"
        f"border-bottom:2px solid {_CIAN};padding:9px 8px;font-weight:900;font-family:'{_FONT}';font-size:12px;}}"
        f"QHeaderView::section:first{{border-top-left-radius:9px;}}"
        f"QHeaderView::section:last{{border-top-right-radius:9px;}}"
        f"QHeaderView::section:hover{{background:{_CIAN};color:#0D1117;}}"
    )


def _sep() -> QFrame:
    s = QFrame()
    s.setFrameShape(QFrame.Shape.HLine)
    s.setStyleSheet(
        f"QFrame{{color:{_BORDE};background:{_BORDE};max-height:1px;border:none;}}"
    )
    s.setFixedHeight(1)
    return s


def _icono_papelera(color: str, size: int = 22) -> QIcon:
    """Icono de papelera vectorial, estilo 'line icon' limpio (4x supersampling)."""
    S = 4
    W = size * S
    pm = QPixmap(W, W)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = QColor(color)
    pen = QPen(c)
    pen.setWidthF(W * 0.075)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    def X(f):
        return W * f

    # Asa superior (mango)
    p.drawLine(QPointF(X(0.40), X(0.20)), QPointF(X(0.60), X(0.20)))
    # Barra de la tapa
    p.drawLine(QPointF(X(0.20), X(0.30)), QPointF(X(0.80), X(0.30)))
    # Cuerpo del cubo (trapecio con base redondeada)
    body = QPainterPath()
    body.moveTo(X(0.27), X(0.32))
    body.lineTo(X(0.32), X(0.78))
    body.quadTo(X(0.33), X(0.84), X(0.40), X(0.84))
    body.lineTo(X(0.60), X(0.84))
    body.quadTo(X(0.67), X(0.84), X(0.68), X(0.78))
    body.lineTo(X(0.73), X(0.32))
    p.drawPath(body)
    # Tres rayas verticales internas
    pen2 = QPen(c)
    pen2.setWidthF(W * 0.05)
    pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen2)
    for fx in (0.42, 0.50, 0.58):
        p.drawLine(QPointF(X(fx), X(0.40)), QPointF(X(fx), X(0.74)))
    p.end()
    return QIcon(
        pm.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )


def _icono_lapiz(color: str, size: int = 22) -> QIcon:
    """Icono de lápiz vectorial, estilo 'line icon' limpio (4x supersampling)."""
    S = 4
    W = size * S
    pm = QPixmap(W, W)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = QColor(color)
    pen = QPen(c)
    pen.setWidthF(W * 0.075)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    def X(f):
        return W * f

    # Lápiz diagonal centrado en el cuadro (centro ~0.50, 0.50).
    # Cuerpo (rectángulo girado 45°)
    body = QPainterPath()
    body.moveTo(X(0.28), X(0.62))  # esquina interior junto a la punta
    body.lineTo(X(0.64), X(0.26))  # hacia el cabezal
    body.lineTo(X(0.76), X(0.38))  # ancho del lápiz en el cabezal
    body.lineTo(X(0.40), X(0.74))  # vuelta a la zona de la punta
    body.closeSubpath()
    p.drawPath(body)
    # Banda que separa cuerpo y cabezal
    p.drawLine(QPointF(X(0.56), X(0.34)), QPointF(X(0.68), X(0.46)))
    # Punta de la mina (triángulo lleno en la esquina inferior-izquierda)
    tip = QPainterPath()
    tip.moveTo(X(0.28), X(0.62))
    tip.lineTo(X(0.40), X(0.74))
    tip.lineTo(X(0.20), X(0.82))  # vértice de la punta
    tip.closeSubpath()
    p.setBrush(c)
    p.drawPath(tip)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.end()
    return QIcon(
        pm.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )


class _IconButton(QPushButton):
    """Botón de icono dibujado que intercambia el color del icono en hover
    (Qt no recolorea un QIcon vía QSS, así que lo hacemos en enter/leaveEvent)."""

    def __init__(
        self, draw_fn, color_base: str, color_hover: str, icon_px: int = 20, parent=None
    ):
        super().__init__(parent)
        self._draw_fn = draw_fn
        self._color_base = color_base
        self._color_hover = color_hover
        self._icon_px = icon_px
        self.setIconSize(QSize(icon_px, icon_px))
        self._set_icon(color_base)

    def _set_icon(self, color):
        self.setIcon(self._draw_fn(color, self._icon_px))

    def enterEvent(self, event):
        self._set_icon(self._color_hover)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_icon(self._color_base)
        super().leaveEvent(event)


def _confirmar(
    parent,
    titulo: str,
    mensaje: str,
    txt_ok: str = "ACEPTAR",
    txt_cancel: str = "CANCELAR",
) -> bool:
    """
    Diálogo de confirmación frameless (mismo estilo que el resto de la app).
    Reemplaza a QMessageBox.question(), que sobre ventanas frameless+translúcidas
    en Windows se renderiza invisible y congela la UI (sólo cierra con ESC).
    Devuelve True si el usuario acepta.
    """
    dlg = QDialog(parent)
    dlg.setModal(True)
    dlg.setWindowFlag(Qt.WindowType.FramelessWindowHint)
    dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    dlg.setFixedWidth(420)
    outer = QVBoxLayout(dlg)
    outer.setContentsMargins(0, 0, 0, 0)
    cuerpo = QFrame()
    cuerpo.setObjectName("cuerpo_confirm")
    cuerpo.setStyleSheet(
        f"QFrame#cuerpo_confirm{{background:{_BG};border:2px solid {_CIAN};"
        f"border-radius:20px;}}"
    )
    outer.addWidget(cuerpo)
    v = QVBoxLayout(cuerpo)
    v.setContentsMargins(24, 22, 24, 22)
    v.setSpacing(12)
    v.addWidget(_lbl(titulo, bold=True, size=16, color=_CIAN))
    msg = _lbl(mensaje, bold=True, size=13, color=_TEXT)  # Segoe UI Bold
    msg.setWordWrap(True)
    v.addWidget(msg)
    v.addSpacing(4)
    fila = QHBoxLayout()
    fila.setSpacing(12)
    b_cancel = _btn(txt_cancel, h=44)
    b_cancel.clicked.connect(dlg.reject)
    b_ok = _btn(
        txt_ok,
        color_bg=_ROJO,
        color_fg="#FFFFFF",
        color_border=_ROJO,
        hover_bg="#FFFFFF",
        hover_fg=_ROJO,
        h=44,
    )
    b_ok.clicked.connect(dlg.accept)
    fila.addWidget(b_cancel)
    fila.addWidget(b_ok)
    v.addLayout(fila)
    return dlg.exec() == QDialog.DialogCode.Accepted


def _elegir_recuperar(parent, titulo, mensaje, txt_sumar, txt_reemplazar) -> str | None:
    """Diálogo de 3 opciones al recuperar una venta retenida con el carrito no vacío:
    cancelar, SUMAR (añadir a los artículos actuales) o REEMPLAZAR. Devuelve
    'sumar', 'reemplazar' o None (cancelar)."""
    dlg = QDialog(parent)
    dlg.setModal(True)
    dlg.setWindowFlag(Qt.WindowType.FramelessWindowHint)
    dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    dlg.setFixedWidth(640)
    res = {"v": None}
    outer = QVBoxLayout(dlg)
    outer.setContentsMargins(0, 0, 0, 0)
    cuerpo = QFrame()
    cuerpo.setObjectName("cuerpo_confirm")
    cuerpo.setStyleSheet(
        f"QFrame#cuerpo_confirm{{background:{_BG};border:2px solid {_CIAN};border-radius:20px;}}"
    )
    outer.addWidget(cuerpo)
    v = QVBoxLayout(cuerpo)
    v.setContentsMargins(24, 22, 24, 22)
    v.setSpacing(12)
    v.addWidget(_lbl(titulo, bold=True, size=16, color=_CIAN))
    msg = _lbl(mensaje, bold=True, size=13, color=_TEXT)  # Segoe UI Bold
    msg.setWordWrap(True)
    v.addWidget(msg)
    v.addSpacing(4)
    fila = QHBoxLayout()
    fila.setSpacing(10)
    b_cancel = _btn(tr("common.cancel", default="Cancelar").upper(), h=46)
    b_sumar = _btn(
        txt_sumar,
        color_bg=_CIAN,
        color_fg="#0D1117",
        color_border=_CIAN,
        hover_bg="#FFFFFF",
        hover_fg="#0D1117",
        h=46,
    )
    b_reemp = _btn(
        txt_reemplazar,
        color_bg=_VERDE,
        color_fg="#0D1117",
        color_border=_VERDE,
        hover_bg="#FFFFFF",
        hover_fg="#0D1117",
        h=46,
    )

    def _set(val):
        res["v"] = val
        dlg.accept()

    b_cancel.clicked.connect(dlg.reject)
    b_sumar.clicked.connect(lambda: _set("sumar"))
    b_reemp.clicked.connect(lambda: _set("reemplazar"))
    fila.addWidget(b_cancel)
    fila.addWidget(b_sumar)
    fila.addWidget(b_reemp)
    v.addLayout(fila)
    dlg.exec()
    return res["v"]


def _aviso_modal(parent, titulo: str, mensaje: str):
    """Aviso centrado en una ventana frameless con un único botón ENTENDIDO.
    Modal pero con su propia ventana (no congela como QMessageBox sobre frameless
    translúcido)."""
    dlg = QDialog(parent)
    dlg.setModal(True)
    dlg.setWindowFlag(Qt.WindowType.FramelessWindowHint)
    dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    dlg.setFixedWidth(440)
    outer = QVBoxLayout(dlg)
    outer.setContentsMargins(0, 0, 0, 0)
    cuerpo = QFrame()
    cuerpo.setObjectName("cuerpo_aviso")
    cuerpo.setStyleSheet(
        f"QFrame#cuerpo_aviso{{background:{_BG};border:2px solid #F1C40F;"
        f"border-radius:20px;}}"
    )
    outer.addWidget(cuerpo)
    v = QVBoxLayout(cuerpo)
    v.setContentsMargins(26, 22, 26, 22)
    v.setSpacing(14)
    v.addWidget(_lbl("⚠  " + titulo, bold=True, size=16, color=_AMBAR))
    msg = _lbl(mensaje, bold=True, size=14, color=_TEXT)  # Segoe UI Bold, +1pt
    msg.setWordWrap(True)
    v.addWidget(msg)
    v.addSpacing(4)
    b_ok = _btn(
        "ENTENDIDO",
        color_bg=_AMBAR,
        color_fg="#0D1117",
        color_border=_AMBAR,
        hover_bg="#FFFFFF",
        hover_fg="#0D1117",
        h=46,
    )
    b_ok.clicked.connect(dlg.accept)
    v.addWidget(b_ok)
    # Centrar sobre la pantalla
    try:
        scr = QApplication.primaryScreen().availableGeometry()
        dlg.adjustSize()
        dlg.move(
            scr.center().x() - dlg.width() // 2, scr.center().y() - dlg.height() // 2
        )
    except Exception:
        pass
    dlg.exec()


# ============================================================
# AUXILIARES — ESTADO CAJA
# ============================================================


def _leer_estado_caja() -> dict:
    try:
        if os.path.exists(_CAJA_STATE_FILE):
            with open(_CAJA_STATE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            fecha_caja = data.get("fecha", "")
            fecha_hoy = datetime.datetime.now().strftime("%Y-%m-%d")
            if fecha_caja and fecha_caja != fecha_hoy:
                # Estado de un día anterior — no se puede operar sin abrir la caja hoy
                return {
                    "estado": "SIN_APERTURA",
                    "ultimos_cierres": data.get("ultimos_cierres", {}),
                }
            return data
    except Exception:
        pass
    return {"estado": "SIN_APERTURA"}


def _guardar_estado_caja(est: dict):
    try:
        os.makedirs(os.path.dirname(_CAJA_STATE_FILE), exist_ok=True)
        with open(_CAJA_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(est, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error guardando estado caja: {e}")


def _norm_nombre(s) -> str:
    """Normaliza un nombre para comparar (sin distinción de may/min ni espacios)."""
    return str(s or "").strip().casefold()


def _caja_pertenece(caja: dict, nombre_empleado: str = "", id_empleado=None) -> bool:
    """Una caja registradora es INTRANSFERIBLE: solo pertenece al cajero
    responsable durante su turno. Se casa preferentemente por id de empleado y,
    como respaldo (cajas antiguas sin id), por nombre normalizado.

    NUNCA devuelve True por defecto: si no hay coincidencia, no pertenece.
    """
    rid = caja.get("responsable_id")
    if id_empleado is not None and rid is not None:
        return str(rid) == str(id_empleado)
    nombre_empleado = _norm_nombre(nombre_empleado)
    if not nombre_empleado:
        return False
    return _norm_nombre(caja.get("responsable")) == nombre_empleado


def _caja_activa(est: dict, nombre_empleado: str = "", id_empleado=None) -> dict | None:
    """Devuelve la caja del cajero indicado (responsable). Retorna None si el TPV
    debe bloquearse o si el empleado no tiene ninguna caja asignada."""
    estado = est.get("estado", "SIN_APERTURA")
    if estado not in ("PRIMERA_CAJA_ABIERTA", "OPERATIVA"):
        return None
    for c in est.get("cajas_activas", []):
        if _caja_pertenece(c, nombre_empleado, id_empleado):
            return c
    return None


def _cajas_de_empleado(est: dict, nombre_empleado: str = "", id_empleado=None) -> list:
    """Cajas activas asignadas EXCLUSIVAMENTE al empleado (por responsable).
    Si no tiene ninguna asignada, devuelve lista vacía (TPV bloqueado)."""
    estado = est.get("estado", "SIN_APERTURA")
    if estado not in ("PRIMERA_CAJA_ABIERTA", "OPERATIVA"):
        return []
    return [
        c
        for c in est.get("cajas_activas", [])
        if _caja_pertenece(c, nombre_empleado, id_empleado)
    ]


def _motivo_bloqueo(est: dict) -> str:
    """Texto explicativo del motivo por el que el TPV está bloqueado."""
    estado = est.get("estado", "SIN_APERTURA")
    if estado == "SIN_APERTURA":
        return tr("bloq.reason_no_apertura")
    if estado == "CAJA_FUERTE_ABIERTA":
        return tr("bloq.reason_cf_abierta")
    if estado in ("CIERRE_CAJAS", "CIERRE_COMPLETADO"):
        return tr("bloq.reason_cerradas")
    return tr("bloq.reason_default")


# ============================================================
# AUXILIARES — RETENIDAS / AUDITORÍA
# ============================================================


def _leer_retenidas() -> list[dict]:
    try:
        if os.path.exists(_RETENIDAS_FILE):
            with open(_RETENIDAS_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _guardar_retenidas(lst: list[dict]):
    os.makedirs(os.path.dirname(_RETENIDAS_FILE), exist_ok=True)
    with open(_RETENIDAS_FILE, "w", encoding="utf-8") as f:
        json.dump(lst, f, indent=2, ensure_ascii=False)


def _log_auditoria(entry: dict):
    try:
        os.makedirs(os.path.dirname(_AUDIT_FILE), exist_ok=True)
        lst: list[dict] = []
        if os.path.exists(_AUDIT_FILE):
            with open(_AUDIT_FILE, encoding="utf-8") as f:
                lst = json.load(f)
        lst.append(entry)
        with open(_AUDIT_FILE, "w", encoding="utf-8") as f:
            json.dump(lst, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error log auditoría: {e}")


# ============================================================
# BLOQUE — DIÁLOGO LOGIN TPV
# ============================================================


class _SeleccionCajaDialog(QDialog):
    """Selector de caja cuando un empleado tiene más de una asignada."""

    def __init__(self, cajas: list, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._caja_sel: dict | None = None
        self._cajas = cajas
        self._build()

    def _build(self):
        card = QFrame(self)
        card.setObjectName("sc")
        card.setStyleSheet(
            f"QFrame#sc{{background:{_BG};border:2px solid {_CIAN};border-radius:20px;}}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(card)

        ly = QVBoxLayout(card)
        ly.setContentsMargins(32, 24, 32, 24)
        ly.setSpacing(12)

        h = QLabel(tr("sel_caja.header"))
        h.setStyleSheet(
            f"color:{_CIAN};font-family:'{_FONT}';font-weight:900;font-size:18px;"
            f"background:transparent;"
        )
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(h)

        ly.addWidget(_sep())

        _btn_caja_ss = (
            f"QPushButton{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:10px;font-family:'{_FONT}';font-weight:700;font-size:14px;"
            f"text-align:left;padding:0 16px;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0D1117;border-color:{_CIAN};}}"
        )
        for caja in self._cajas:
            cid = caja.get("id", "?")
            resp = caja.get("responsable", "?")
            fondo = float(caja.get("fondo", 0.0))
            btn = QPushButton(
                tr(
                    "sel_caja.caja_btn",
                    cid=cid,
                    resp=resp,
                    fondo=divisas.formatear(fondo),
                )
            )
            btn.setFixedHeight(54)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_btn_caja_ss)
            btn.clicked.connect(lambda checked, c=caja: self._seleccionar(c))
            ly.addWidget(btn)

        ly.addSpacing(4)
        btn_cancel = QPushButton(tr("common.cancel"))
        btn_cancel.setFixedHeight(40)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(
            f"QPushButton{{background:{_BG2};color:{_TEXT2};border:2px solid {_BORDE};"
            f"border-radius:10px;font-family:'{_FONT}';font-weight:700;font-size:13px;}}"
            f"QPushButton:hover{{background:#30363D;color:{_TEXT};}}"
        )
        btn_cancel.clicked.connect(self.reject)
        ly.addWidget(btn_cancel)

    def _seleccionar(self, caja: dict):
        self._caja_sel = caja
        self.accept()

    def get_caja(self) -> dict | None:
        return self._caja_sel


# ============================================================


class _LoginTPVDialog(QDialog):
    """Identificación del empleado antes de acceder al TPV.
    Paso 1: seleccionar nombre de la lista.
    Paso 2: introducir PIN de 4 dígitos mediante pad numérico táctil."""

    _PIN_LEN = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._nombre_empleado: str = ""
        self._id_empleado = None
        self._pin: str = ""
        self._build()

    # ── construcción ────────────────────────────────────────────

    def _build(self):
        card = QFrame(self)
        card.setObjectName("lc")
        card.setStyleSheet(
            f"QFrame#lc{{background:{_BG};border:2px solid {_CIAN};"
            f"border-radius:20px;}}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(card)

        ly = QVBoxLayout(card)
        ly.setContentsMargins(36, 24, 36, 24)
        ly.setSpacing(16)

        # Cabecera: título centrado + botón ✕ (volver al menú) en la esquina superior derecha.
        h = QLabel(tr("login_tpv.header"))
        h.setStyleSheet(
            f"color:{_CIAN};font-family:'{_FONT}';font-weight:900;font-size:20px;"
        )
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_cerrar = QPushButton("✕")
        btn_cerrar.setFixedSize(38, 38)
        btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cerrar.setToolTip(tr("login_tpv.back_menu_tip", default="Volver al menú"))
        btn_cerrar.setStyleSheet(
            f"QPushButton{{background:{_BG};color:{_ROJO};border:2px solid {_ROJO};"
            f"border-radius:8px;font-family:'{_FONT}';font-weight:900;font-size:16px;}}"
            f"QPushButton:hover{{background:{_ROJO};color:#FFF;}}"
        )
        btn_cerrar.clicked.connect(self.reject)
        # El título ocupa TODO el ancho (centrado) y el botón ✕ flota en la esquina superior derecha
        # SUPERPUESTO (misma celda del grid) → el título queda perfectamente centrado en la ventana.
        from PyQt6.QtWidgets import QGridLayout
        hbar = QGridLayout()
        hbar.setContentsMargins(0, 0, 0, 0)
        hbar.setColumnStretch(0, 1)   # la celda ocupa TODO el ancho → el título se centra de verdad
        hbar.addWidget(h, 0, 0)
        hbar.addWidget(btn_cerrar, 0, 0,
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        ly.addLayout(hbar)

        # Cuerpo: lista izquierda + pin derecha
        body = QHBoxLayout()
        body.setSpacing(40)
        ly.addLayout(body)

        # ── columna izquierda: lista de empleados ───────────────
        col_izq = QVBoxLayout()
        col_izq.setSpacing(10)

        lbl_lista = QLabel(tr("login_tpv.select_name"))
        lbl_lista.setStyleSheet(f"color:{_TEXT2};font-family:'{_FONT}';font-size:13px;")
        col_izq.addWidget(lbl_lista)

        from PyQt6.QtWidgets import QListWidget

        self._lista = QListWidget()
        self._lista.setFixedWidth(260)
        self._lista.setFixedHeight(260)
        self._lista.setStyleSheet(
            f"QListWidget{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:10px;font-family:'{_FONT}';font-size:13px;outline:none;}}"
            f"QListWidget::item{{padding:10px 12px;border-bottom:1px solid #21262D;}}"
            f"QListWidget::item:selected{{background:{_CIAN};color:#0D1117;font-weight:bold;}}"
            f"QListWidget::item:hover{{background:#21262D;}}"
        )
        self._lista.itemSelectionChanged.connect(self._on_sel_empleado)
        col_izq.addWidget(self._lista)

        try:
            for u in listar_usuarios():
                nombre = u.get("nombre") or u.get("usuario") or ""
                if nombre:
                    self._lista.addItem(nombre.upper())
        except Exception:
            pass

        body.addLayout(col_izq)

        # ── columna derecha: PIN pad ────────────────────────────
        col_der = QVBoxLayout()
        col_der.setSpacing(10)
        col_der.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
        )

        self._lbl_sel = QLabel("—")
        self._lbl_sel.setStyleSheet(
            f"color:{_CIAN};font-family:'{_FONT}';font-weight:900;font-size:14px;"
        )
        self._lbl_sel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col_der.addWidget(self._lbl_sel)

        # Indicadores de dígitos (4 puntos)
        dots_row = QHBoxLayout()
        dots_row.setSpacing(16)
        dots_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dots: list[QLabel] = []
        for _ in range(self._PIN_LEN):
            d = QLabel("○")
            d.setFixedSize(34, 34)
            d.setAlignment(Qt.AlignmentFlag.AlignCenter)
            d.setStyleSheet(f"color:#30363D;font-size:28px;font-family:'{_FONT}';")
            dots_row.addWidget(d)
            self._dots.append(d)
        col_der.addLayout(dots_row)

        # Grid numérico 3×4: 1-9, ⌫, 0, ✔
        _btn_ss = (
            f"QPushButton{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:10px;font-family:'{_FONT}';font-weight:900;font-size:18px;}}"
            f"QPushButton:hover{{background:#21262D;border-color:{_CIAN};}}"
            f"QPushButton:pressed{{background:{_CIAN};color:#0D1117;}}"
        )
        _btn_del_ss = (
            f"QPushButton{{background:{_BG2};color:{_ROJO};border:2px solid {_BORDE};"
            f"border-radius:10px;font-family:'{_FONT}';font-weight:900;font-size:16px;}}"
            f"QPushButton:hover{{background:{_ROJO};color:#FFF;border-color:{_ROJO};}}"
        )
        _btn_ok_ss = (
            f"QPushButton{{background:{_CIAN};color:#0D1117;border:2px solid {_CIAN};"
            f"border-radius:10px;font-family:'{_FONT}';font-weight:900;font-size:16px;}}"
            f"QPushButton:hover{{background:#FFF;color:#0D1117;}}"
            f"QPushButton:disabled{{background:#1C2128;color:#484F58;border-color:#30363D;}}"
        )

        _BTN_W = 90
        _BTN_H = 48
        _SPACING = 8

        grid = QGridLayout()
        grid.setSpacing(_SPACING)
        grid.setContentsMargins(0, 0, 0, 0)

        teclas = [
            ("1", 0, 0),
            ("2", 0, 1),
            ("3", 0, 2),
            ("4", 1, 0),
            ("5", 1, 1),
            ("6", 1, 2),
            ("7", 2, 0),
            ("8", 2, 1),
            ("9", 2, 2),
            ("⌫", 3, 0),
            ("0", 3, 1),
        ]
        for label, row, col in teclas:
            btn = QPushButton(label)
            btn.setFixedHeight(_BTN_H)
            btn.setMinimumWidth(_BTN_W)
            btn.setMaximumWidth(_BTN_W)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_btn_del_ss if label == "⌫" else _btn_ss)
            btn.clicked.connect(lambda _, t=label: self._tecla(t))
            grid.addWidget(btn, row, col)

        self._btn_entrar = QPushButton("✔")
        self._btn_entrar.setFixedHeight(_BTN_H)
        self._btn_entrar.setMinimumWidth(_BTN_W)
        self._btn_entrar.setMaximumWidth(_BTN_W)
        self._btn_entrar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_entrar.setStyleSheet(_btn_ok_ss)
        self._btn_entrar.setEnabled(False)
        self._btn_entrar.clicked.connect(self._confirmar)
        grid.addWidget(self._btn_entrar, 3, 2)

        col_der.addLayout(grid)

        # Error
        self._lbl_err = QLabel("")
        self._lbl_err.setStyleSheet(
            f"color:{_ROJO};font-family:'{_FONT}';font-size:12px;"
        )
        self._lbl_err.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col_der.addWidget(self._lbl_err)

        body.addLayout(col_der)

    # ── lógica ─────────────────────────────────────────────────

    def _on_sel_empleado(self):
        items = self._lista.selectedItems()
        if items:
            self._nombre_empleado = items[0].text()
            self._lbl_sel.setText(self._nombre_empleado)
            self._pin = ""
            self._actualizar_dots()
            self._lbl_err.setText("")
        else:
            self._nombre_empleado = ""
            self._lbl_sel.setText("—")

    def _tecla(self, t: str):
        if not self._nombre_empleado:
            self._lbl_err.setText(tr("login_tpv.err_select_first"))
            return
        if t == "⌫":
            self._pin = self._pin[:-1]
        elif len(self._pin) < self._PIN_LEN:
            self._pin += t
        self._actualizar_dots()
        self._lbl_err.setText("")
        self._btn_entrar.setEnabled(len(self._pin) == self._PIN_LEN)

    def _actualizar_dots(self):
        for i, d in enumerate(self._dots):
            if i < len(self._pin):
                d.setText("●")
                d.setStyleSheet(f"color:{_CIAN};font-size:26px;font-family:'{_FONT}';")
            else:
                d.setText("○")
                d.setStyleSheet(f"color:#30363D;font-size:26px;font-family:'{_FONT}';")

    def _confirmar(self):
        if not self._nombre_empleado or len(self._pin) != self._PIN_LEN:
            return
        resultado = validar_login_empleado(self._nombre_empleado, self._pin)
        if resultado:
            self._nombre_empleado = (
                resultado.get("nombre") or self._nombre_empleado
            ).upper()
            self._id_empleado = resultado.get("id")
            self.accept()
        else:
            self._lbl_err.setText(tr("login_tpv.err_wrong_pin"))
            self._pin = ""
            self._actualizar_dots()
            self._btn_entrar.setEnabled(False)

    def showEvent(self, event):
        super().showEvent(event)
        # Diferir el centrado un tick para que el layout esté finalizado
        QTimer.singleShot(0, self._centrar_en_pantalla)

    def _centrar_en_pantalla(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(
            screen.x() + (screen.width() - self.width()) // 2,
            screen.y() + (screen.height() - self.height()) // 2,
        )

    def get_nombre_empleado(self) -> str:
        return self._nombre_empleado

    def get_id_empleado(self):
        return self._id_empleado


# ============================================================
# BLOQUE — PANTALLA BLOQUEADA
# ============================================================


class _PantallaBlockeada(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{_BG};")

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(18)

        ico = _lbl("🔒", size=60)
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ico)

        t = _lbl(tr("bloq.title"), bold=True, size=20)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)

        self.lbl_motivo = _lbl(
            tr("bloq.motivo_default"),
            size=13,
            color=_TEXT2,
        )
        self.lbl_motivo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_motivo)

        self.btn_ir = _btn(
            tr("bloq.go_caja"),
            color_bg=_CIAN,
            color_fg="#0D1117",
            color_border=_CIAN,
            hover_bg="#FFFFFF",
            hover_fg="#0D1117",
            h=46,
        )
        self.btn_ir.setFixedWidth(260)
        lay.addWidget(self.btn_ir, alignment=Qt.AlignmentFlag.AlignCenter)

        self.btn_reintentar = _btn(tr("bloq.retry"), h=38)
        self.btn_reintentar.setFixedWidth(260)
        lay.addWidget(self.btn_reintentar, alignment=Qt.AlignmentFlag.AlignCenter)

        self.btn_menu = _btn(
            tr("bloq.back_menu"),
            color_fg=_ROJO,
            color_border=_ROJO,
            hover_bg=_ROJO,
            hover_fg="#FFF",
            h=38,
        )
        self.btn_menu.setFixedWidth(260)
        lay.addWidget(self.btn_menu, alignment=Qt.AlignmentFlag.AlignCenter)

    def set_motivo(self, texto: str):
        self.lbl_motivo.setText(texto)


class _ComboMaxPopup(QComboBox):
    """QComboBox que limita la altura del popup a N items visibles, forzando
    la scrollbar de forma fiable (setMaxVisibleItems se ignora cuando el combo
    tiene stylesheet personalizado). Mide la altura REAL de cada item."""

    def __init__(self, max_items: int = 5, item_h: int = 44, parent=None):
        super().__init__(parent)
        self._max_items = max_items
        self._item_h = item_h  # fallback si no se puede medir
        # Configurar el contenedor del popup AQUÍ (antes de que exista el handle
        # nativo). Hacerlo en el filtro de eventos sobre una ventana ya visible
        # recrea el HWND en cada apertura → lentitud y QWindowsWindow::setGeometry.
        try:
            _cont = self.view().parent()
            if isinstance(_cont, QWidget) and _cont is not self:
                _cont.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                _cont.setWindowFlags(
                    _cont.windowFlags()
                    | Qt.WindowType.FramelessWindowHint
                    | Qt.WindowType.NoDropShadowWindowHint
                )
        except Exception:
            pass

    def showPopup(self):
        super().showPopup()
        # Aplicar el cap inmediatamente Y tras el ciclo de eventos: Qt
        # recalcula la geometría del contenedor en su propio relayout justo
        # después de showPopup, así que un solo ajuste se pierde (dejaba un
        # hueco vacío bajo los items y el contenedor más alto que la vista).
        self._cap_popup()
        QTimer.singleShot(0, self._cap_popup)

    def _cap_popup(self):
        try:
            view = self.view()
            if self.count() <= self._max_items:
                return
            # Altura real de un item (sizeHintForRow), con fallback.
            ih = view.sizeHintForRow(0)
            if ih <= 0:
                ih = self._item_h
            # La vista tiene padding 10px (arriba+abajo = 20) + borde 1px*2.
            alto_view = self._max_items * ih + 22
            view.setFixedHeight(alto_view)
            # Encoger TAMBIÉN el contenedor del popup (QComboBoxPrivateContainer):
            # si solo se encoge la vista, el contenedor mantiene la altura para
            # los 8 items y queda un hueco vacío debajo.
            cont = view.parentWidget()
            if cont is not None and cont is not self:
                cont.setFixedHeight(alto_view)
                cont.updateGeometry()
        except Exception:
            pass


# ============================================================
# BLOQUE — DIALOGO EDICIÓN DE LÍNEA
# ============================================================


class _LineaEditDialog(QDialog):
    def __init__(self, linea: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("linea.title"))
        self.setFixedWidth(380)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos = None
        self._linea = dict(linea)

        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _cuerpo = QFrame()
        _cuerpo.setObjectName("cuerpo_linea_edit")
        _cuerpo.setStyleSheet(
            f"QFrame#cuerpo_linea_edit{{background:{_BG};border:2px solid {_CIAN};"
            f"border-radius:20px;}}"
        )
        _outer.addWidget(_cuerpo)
        lay = QVBoxLayout(_cuerpo)
        lay.setSpacing(12)
        lay.setContentsMargins(22, 20, 22, 20)

        lay.addWidget(_lbl(tr("linea.header"), bold=True, size=15, color=_CIAN))
        lay.addWidget(
            _lbl(
                linea.get("nombre", tr("linea.default_name")),
                bold=True,
                size=13,
                color=_TEXT2,
            )
        )
        lay.addWidget(_sep())

        _inp_ss = (
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:1px solid {_BORDE};"
            f"border-radius:6px;padding:5px 10px;font-size:13px;}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}"
        )
        _spin_ss = (
            f"QSpinBox{{background:{_BG2};color:{_TEXT};border:1px solid {_BORDE};"
            f"border-radius:6px;padding:4px 8px;font-size:13px;}}"
        )

        def _row(label, widget):
            h = QHBoxLayout()
            h.addWidget(_lbl(label, bold=True, size=14))
            h.addWidget(widget)
            lay.addLayout(h)

        self.spin_qty = QSpinBox()
        self.spin_qty.setRange(1, 9999)
        self.spin_qty.setValue(int(linea.get("cantidad", 1)))
        self.spin_qty.setStyleSheet(_spin_ss)
        _row(tr("linea.qty"), self.spin_qty)

        self.inp_precio = QLineEdit(f"{linea.get('precio', 0):.2f}")
        self.inp_precio.setStyleSheet(_inp_ss)
        _row(tr("linea.unit_price"), self.inp_precio)

        self.inp_dto = QLineEdit(f"{linea.get('descuento_pct', 0):.1f}")
        self.inp_dto.setStyleSheet(_inp_ss)
        _row(tr("linea.discount"), self.inp_dto)

        lay.addWidget(_sep())

        br = QHBoxLayout()
        btn_cancel = _btn(
            tr("common.cancel"),
            color_fg=_ROJO,
            color_border=_ROJO,
            hover_bg=_ROJO,
            hover_fg="#FFF",
        )
        btn_ok = _btn(
            tr("common.accept"),
            color_bg=_VERDE,
            color_fg="#0D1117",
            color_border=_VERDE,
            hover_bg="#FFF",
            hover_fg="#0D1117",
        )
        br.addWidget(btn_cancel)
        br.addStretch()
        br.addWidget(btn_ok)
        lay.addLayout(br)

        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._aceptar)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def _aceptar(self):
        try:
            precio = float(self.inp_precio.text().replace(",", "."))
            dto = float(self.inp_dto.text().replace(",", "."))
            if precio < 0 or not (0 <= dto <= 100):
                raise ValueError
            self._linea["cantidad"] = self.spin_qty.value()
            self._linea["precio"] = round(precio, 2)
            self._linea["descuento_pct"] = round(dto, 2)
            self._linea["subtotal"] = round(
                self._linea["cantidad"] * precio * (1 - dto / 100), 2
            )
            self.accept()
        except ValueError:
            QMessageBox.warning(self, tr("linea.err_title"), tr("linea.err_msg"))

    def get_linea(self) -> dict:
        return self._linea


# ============================================================
# BLOQUE — DIALOGO VENTAS RETENIDAS
# ============================================================


class _RetenidasDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(520)
        self.setMinimumHeight(400)
        self._recuperada: dict | None = None

        card = QFrame(self)
        card.setObjectName("ret_card")
        card.setStyleSheet(
            f"QFrame#ret_card{{background:{_BG};border:2px solid {_CIAN};border-radius:20px;}}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setSpacing(10)
        lay.setContentsMargins(24, 20, 24, 20)

        _hdr = QHBoxLayout()
        _hdr.addWidget(_lbl(tr("retenidas.title"), bold=True, size=16))
        _hdr.addStretch()
        _bx = QPushButton("✕")
        _bx.setCursor(Qt.CursorShape.PointingHandCursor)
        _bx.setFixedSize(36, 36)
        _bx.setStyleSheet(
            f"QPushButton{{background:transparent;color:{_ROJO};border:2px solid {_ROJO};"
            f"border-radius:9px;font-weight:900;font-size:16px;}}"
            f"QPushButton:hover{{background:{_ROJO};color:#0D1117;}}")
        _bx.clicked.connect(self.reject)
        _hdr.addWidget(_bx)
        lay.addLayout(_hdr)
        lay.addWidget(_sep())

        self._lista_lay = QVBoxLayout()
        self._lista_lay.setSpacing(6)
        self._lista_lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll_w = QWidget()
        scroll_w.setStyleSheet(f"background:{_BG};")
        scroll_w.setLayout(self._lista_lay)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(scroll_w)
        scroll.setStyleSheet(f"background:{_BG};border:none;")
        lay.addWidget(scroll, 1)

        self._cargar()

    def _cargar(self):
        while self._lista_lay.count():
            item = self._lista_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        retenidas = _leer_retenidas()
        if not retenidas:
            self._lista_lay.addWidget(_lbl(tr("retenidas.empty"), color=_TEXT2))
            return

        for i, r in enumerate(retenidas):
            card = _card()
            cl = QVBoxLayout(card)
            cl.setSpacing(4)
            cl.setContentsMargins(12, 8, 12, 8)

            fecha_str = r.get("fecha", "")[:19].replace("T", " ")
            total = r.get("total", 0.0)
            lineas = r.get("lineas", [])

            header = QHBoxLayout()
            header.addWidget(_lbl(f"#{i+1}  {fecha_str}", bold=True))
            header.addStretch()
            header.addWidget(
                _lbl(f"{divisas.formatear(total)}", bold=True, color=_CIAN)
            )
            cl.addLayout(header)

            resumen = ", ".join(f"{l['nombre']} x{l['cantidad']}" for l in lineas[:3])
            if len(lineas) > 3:
                resumen += tr("retenidas.more", n=len(lineas) - 3)
            cl.addWidget(_lbl(resumen, size=11, color=_TEXT2))

            fila_btns = QHBoxLayout()
            btn_rec = _btn(
                tr("retenidas.recover"),
                color_bg=_CIAN,
                color_fg="#0D1117",
                color_border=_CIAN,
                hover_bg="#FFF",
                hover_fg="#0D1117",
                h=30,
            )
            btn_del = _btn(
                tr("retenidas.delete"),
                color_bg=_BG,
                color_fg=_ROJO,
                color_border=_ROJO,
                hover_bg=_ROJO,
                hover_fg="#FFF",
                h=30,
            )
            btn_rec.clicked.connect(lambda checked, idx=i: self._recuperar(idx))
            btn_del.clicked.connect(lambda checked, idx=i: self._eliminar(idx))
            fila_btns.addWidget(btn_rec)
            fila_btns.addWidget(btn_del)
            fila_btns.addStretch()
            cl.addLayout(fila_btns)

            self._lista_lay.addWidget(card)

    def _recuperar(self, idx: int):
        retenidas = _leer_retenidas()
        if 0 <= idx < len(retenidas):
            self._recuperada = retenidas.pop(idx)
            _guardar_retenidas(retenidas)
            self.accept()

    def _eliminar(self, idx: int):
        retenidas = _leer_retenidas()
        if 0 <= idx < len(retenidas):
            retenidas.pop(idx)
            _guardar_retenidas(retenidas)
            self._cargar()

    def get_recuperada(self) -> dict | None:
        return self._recuperada


# ============================================================
# BLOQUE — DIALOGO DE PAGO
# ============================================================


class _BilleteButton(QPushButton):
    """Botón de denominación rápida que muestra la IMAGEN del billete (de
    assets/currencies/<DIVISA>/banknotes). Si no hay imagen, dibuja una
    representación estilizada con la etiqueta. Rectangular y alto para el billete."""

    def __init__(self, valor, etiqueta, imagen=None, parent=None):
        super().__init__(parent)
        self._valor = valor
        self._etiqueta = etiqueta
        self._pix = QPixmap(imagen) if imagen else QPixmap()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(88)

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        hover = self.underMouse()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(_BG2))
        p.drawRoundedRect(r, 8, 8)

        # Área de imagen (arriba) + área de texto (abajo, el valor del billete).
        text_h = 20.0
        img_area = QRectF(
            r.x() + 6, r.y() + 6, r.width() - 12, r.height() - text_h - 10
        )
        if not self._pix.isNull():
            # Rellenar el área recortando el sobrante (KeepAspectRatioByExpanding):
            # TODOS los billetes quedan del MISMO tamaño, ninguno más pequeño.
            scaled = self._pix.scaled(
                img_area.size().toSize(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = img_area.x() + (img_area.width() - scaled.width()) / 2
            y = img_area.y() + (img_area.height() - scaled.height()) / 2
            path = QPainterPath()
            path.addRoundedRect(img_area, 5, 5)
            p.save()
            p.setClipPath(path)
            p.drawPixmap(int(x), int(y), scaled)
            p.restore()
        else:
            p.setBrush(QColor("#2E5E46"))
            p.setPen(QPen(QColor("#3FAE7E"), 1))
            p.drawRoundedRect(img_area, 6, 6)

        # Valor del billete debajo de la imagen.
        p.setPen(QColor("#E6EDF3"))
        p.setFont(QFont(_FONT, 11, QFont.Weight.Black))
        p.drawText(
            QRectF(r.x(), r.bottom() - text_h - 1, r.width(), text_h),
            int(Qt.AlignmentFlag.AlignCenter),
            self._etiqueta,
        )

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(_CIAN if hover else _BORDE), 2))
        p.drawRoundedRect(r, 8, 8)
        p.end()


class _PagoDialog(QDialog):
    _NUMPAD_W = 270  # ancho del teclado numérico y del botón de importe exacto

    def __init__(self, total: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("pago.title"))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        # Pantalla completa (geometría fijada en showEvent) con un único contorno:
        # el del QDialog global. Sin translucidez ni borde interno (sin doble
        # contorno). El contenido va en un panel centrado para no verse vacío.
        self.setObjectName("dlg_cobrar")
        self.setStyleSheet(f"#dlg_cobrar {{ background: {_BG}; }}")
        # Importe a cobrar redondeado a la precisión de la divisa (p. ej. Won = 0 decimales):
        # así lo mostrado coincide con lo cobrado y el cambio se calcula sobre el valor real.
        self._total = divisas.redondear(total)
        self._resultado: dict | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addStretch()
        fila = QHBoxLayout()
        fila.addStretch()
        root.addLayout(fila)
        root.addStretch()

        panel = QFrame()
        panel.setObjectName("pago_panel")
        panel.setStyleSheet(
            f"QFrame#pago_panel{{background:{_BG2};border:none;border-radius:26px;}}"
        )
        fila.addWidget(panel)
        fila.addStretch()

        body = QHBoxLayout(panel)
        body.setContentsMargins(48, 40, 48, 40)
        body.setSpacing(48)

        # Columna izquierda: información de cobro.
        izq = QWidget()
        izq.setFixedWidth(540)
        lay = QVBoxLayout(izq)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        body.addWidget(izq, 0, Qt.AlignmentFlag.AlignTop)

        # Columna derecha: teclado numérico + importe entregado exacto (mismo ancho).
        der = QVBoxLayout()
        der.setSpacing(14)
        der.addWidget(self._build_pago_numpad(), 0, Qt.AlignmentFlag.AlignTop)
        self.btn_exacto = _btn(
            f"{tr('pago.exact_label', default='Importe entregado exacto:')}\n{divisas.formatear(self._total)}",
            color_bg=_CIAN,
            color_fg="#0D1117",
            color_border=_CIAN,
            hover_bg="#FFF",
            hover_fg="#0D1117",
            h=60,
        )
        self.btn_exacto.setFixedWidth(self._NUMPAD_W)
        self.btn_exacto.clicked.connect(self._pago_exacto)
        der.addWidget(self.btn_exacto)
        der.addStretch()
        body.addLayout(der, 0)

        # Solo el VALOR numérico en verde; la etiqueta conserva su color.
        _tot_val = f"<span style='color:{_VERDE};'>{divisas.formatear(self._total)}</span>"
        _tot_html = tr("pago.total_label", x="\x00").replace("\x00", _tot_val)
        lay.addWidget(
            _lbl(_tot_html, bold=True, size=22, color=_CIAN)
        )
        lay.addWidget(_sep())

        # Tabs forma de pago
        tabs = QHBoxLayout()
        tabs.setSpacing(6)
        self._tab_btns = []
        for label in (tr("pago.tab_cash"), tr("pago.tab_card"), tr("pago.tab_mixed")):
            b = _btn(label, h=42)
            tabs.addWidget(b)
            self._tab_btns.append(b)
        lay.addLayout(tabs)
        lay.addSpacing(2)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background:transparent;")
        self._stack.addWidget(self._panel_efectivo())
        self._stack.addWidget(self._panel_tarjeta())
        self._stack.addWidget(self._panel_mixto())
        lay.addWidget(self._stack)

        lay.addWidget(_sep())

        br = QHBoxLayout()
        btn_cancelar = _btn(
            tr("pago.cancel"),
            color_fg=_ROJO,
            color_border=_ROJO,
            hover_bg=_ROJO,
            hover_fg="#FFF",
            h=50,
        )
        self.btn_cobrar = _btn(
            tr("pago.charge"),
            color_bg=_VERDE,
            color_fg="#0D1117",
            color_border=_VERDE,
            hover_bg="#FFF",
            hover_fg="#0D1117",
            h=50,
        )
        br.addWidget(btn_cancelar)
        br.addStretch()
        br.addWidget(self.btn_cobrar)
        lay.addLayout(br)

        self._tab_btns[0].clicked.connect(lambda: self._tab(0))
        self._tab_btns[1].clicked.connect(lambda: self._tab(1))
        self._tab_btns[2].clicked.connect(lambda: self._tab(2))
        btn_cancelar.clicked.connect(self.reject)
        self.btn_cobrar.clicked.connect(self._cobrar)

        self._tab(0)

    def showEvent(self, e):
        # Fijar la geometría a pantalla completa en el show (setGeometry en
        # __init__ no siempre se respeta antes del primer show en Windows).
        super().showEvent(e)
        try:
            self.setGeometry(QApplication.primaryScreen().availableGeometry())
        except Exception:
            pass

    # --- tabs ---

    def _tab(self, idx: int):
        self._stack.setCurrentIndex(idx)
        for i, b in enumerate(self._tab_btns):
            if i == idx:
                b.setStyleSheet(
                    f"QPushButton{{background:{_CIAN};color:#0D1117;border:2px solid {_CIAN};"
                    f"border-radius:10px;font-family:'{_FONT}';font-weight:900;font-size:13px;padding:0 12px;}}"
                    f"QPushButton:hover{{background:#FFF;color:#0D1117;}}"
                )
            else:
                b.setStyleSheet(
                    f"QPushButton{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                    f"border-radius:10px;font-family:'{_FONT}';font-weight:900;font-size:13px;padding:0 12px;}}"
                    f"QPushButton:hover{{background:{_CIAN};color:#0D1117;}}"
                )

    # --- panel efectivo ---

    def _panel_efectivo(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        _inp_ss = (
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:6px 12px;font-size:18px;font-weight:900;font-family:'{_FONT}';}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}"
        )

        lay.addWidget(_lbl(tr("pago.amount_given"), bold=True, size=14))
        self.inp_ef = QLineEdit("0.00")
        self.inp_ef.setStyleSheet(_inp_ss)
        self.inp_ef.textChanged.connect(self._actualizar_cambio)
        lay.addWidget(self.inp_ef)

        # Billetes rápidos según la divisa activa (assets/currencies/<DIVISA>):
        # cada divisa tiene su propio conjunto de billetes, así que el nº de
        # botones cambia con la divisa seleccionada.
        grid = QGridLayout()
        grid.setSpacing(12)
        billetes = [
            d
            for d in divisas.denominaciones(descendente=False)
            if d["tipo"] == "billete"
        ]
        for i, d in enumerate(billetes):
            b = _BilleteButton(d["valor"], d["etiqueta"], d.get("imagen"))
            b.clicked.connect(
                lambda checked, v=float(d["valor"]): self.inp_ef.setText(f"{v:.2f}")
            )
            grid.addWidget(b, i // 3, i % 3)
        lay.addLayout(grid)

        self.lbl_cambio = _lbl(
            tr("pago.change", x="0,00"), bold=True, size=13, color=_VERDE
        )
        lay.addWidget(self.lbl_cambio)
        self._actualizar_cambio()
        return w

    def _pago_exacto(self):
        """Importe entregado exacto: cambia a efectivo y rellena el campo 'importe
        entregado' con el total. NO cobra: deja la transacción lista para que el
        cajero la finalice con el botón verde COBRAR."""
        self._tab(0)
        # Inserta el total con los decimales propios de la divisa (Won = 0 → "2", EUR → "2.00").
        self.inp_ef.setText(f"{self._total:.{divisas.decimales()}f}")
        self.inp_ef.setFocus()

    # --- teclado numérico ---

    def _active_input(self):
        """Campo de texto al que afecta el teclado según la pestaña activa."""
        idx = self._stack.currentIndex()
        if idx == 0:
            return self.inp_ef
        if idx == 2:
            return getattr(self, "inp_mx_ef", None)
        return None

    def _build_pago_numpad(self) -> QFrame:
        card = QFrame()
        card.setObjectName("pago_numpad")
        card.setFixedWidth(self._NUMPAD_W)
        card.setStyleSheet(
            f"QFrame#pago_numpad{{background:{_BG2};border:1px solid {_BORDE};border-radius:14px;}}"
        )
        gl = QGridLayout(card)
        gl.setContentsMargins(12, 12, 12, 12)
        gl.setSpacing(8)

        # min-width:0 anula el `QDialog QPushButton{min-width:120px}` global, que si
        # no haría que los 3 botones no cupieran en el ancho del teclado.
        _ss_num = (
            f"QPushButton{{background:{_BG};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:14px;font-family:'{_FONT}';font-weight:900;font-size:22px;min-width:0;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0D1117;border-color:{_CIAN};}}"
            f"QPushButton:pressed{{background:{_CIAN};color:#0D1117;}}"
        )
        _ss_del = (
            f"QPushButton{{background:{_BG};color:{_ROJO};border:2px solid {_ROJO};"
            f"border-radius:14px;font-family:'{_FONT}';font-weight:900;font-size:20px;min-width:0;}}"
            f"QPushButton:hover{{background:{_ROJO};color:#FFF;}}"
        )
        layout_keys = [
            ("7", 0, 0, "num"),
            ("8", 0, 1, "num"),
            ("9", 0, 2, "num"),
            ("4", 1, 0, "num"),
            ("5", 1, 1, "num"),
            ("6", 1, 2, "num"),
            ("1", 2, 0, "num"),
            ("2", 2, 1, "num"),
            ("3", 2, 2, "num"),
            (".", 3, 0, "num"),
            ("0", 3, 1, "num"),
            ("⌫", 3, 2, "del"),
        ]
        for c in range(3):
            gl.setColumnStretch(c, 1)
        for txt, row, col, sk in layout_keys:
            b = QPushButton(txt)
            b.setFixedHeight(54)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setStyleSheet(_ss_del if sk == "del" else _ss_num)
            b.clicked.connect(lambda checked, t=txt: self._num_pago(t))
            gl.addWidget(b, row, col)
        return card

    def _num_pago(self, tecla: str):
        inp = self._active_input()
        if inp is None:
            return
        cur = inp.text().strip()
        if tecla == "⌫":
            inp.setText(cur[:-1])
        elif tecla == ".":
            if "." not in cur:
                inp.setText((cur or "0") + ".")
        else:  # dígito
            if cur in ("", "0", "0.00"):
                inp.setText(tecla)
            else:
                inp.setText(cur + tecla)
        inp.setFocus()

    def _actualizar_cambio(self):
        try:
            entregado = divisas.redondear(float(self.inp_ef.text().replace(",", ".")))
            cambio = divisas.redondear(entregado - self._total)
            color = _VERDE if cambio >= 0 else _ROJO
            self.lbl_cambio.setText(tr("pago.change", x=divisas.formatear(cambio)))
            self.lbl_cambio.setStyleSheet(
                f"color:{color};font-family:'{_FONT}';font-size:13px;"
                f"font-weight:900;background:transparent;"
            )
        except ValueError:
            self.lbl_cambio.setText(tr("pago.change_dash"))

    # --- panel tarjeta ---

    def _panel_tarjeta(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        lay.addWidget(
            _lbl(
                tr("pago.card_amount", x=divisas.formatear(self._total)),
                bold=True,
                size=14,
            )
        )
        lay.addWidget(_lbl(tr("pago.card_hint"), size=12, color=_TEXT2))
        lay.addStretch()
        return w

    # --- panel mixto ---

    def _panel_mixto(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        _inp_ss = (
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:1px solid {_BORDE};"
            f"border-radius:6px;padding:5px 10px;font-size:13px;}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}"
        )

        lay.addWidget(
            _lbl(
                tr("pago.mixed_total", x=divisas.formatear(self._total)),
                bold=True,
                size=14,
            )
        )

        fila = QHBoxLayout()
        fila.addWidget(_lbl(tr("pago.mixed_cash"), size=12))
        self.inp_mx_ef = QLineEdit("0.00")
        self.inp_mx_ef.setStyleSheet(_inp_ss)
        self.inp_mx_ef.textChanged.connect(self._actualizar_mixto)
        fila.addWidget(self.inp_mx_ef)
        lay.addLayout(fila)

        self.lbl_mx_tj = _lbl(tr("pago.mixed_card", x="0,00"), size=12, color=_TEXT2)
        self.lbl_mx_cambio = _lbl(
            tr("pago.mixed_change", x="0,00"), bold=True, color=_VERDE
        )
        lay.addWidget(self.lbl_mx_tj)
        lay.addWidget(self.lbl_mx_cambio)
        lay.addStretch()
        return w

    def _actualizar_mixto(self):
        try:
            ef = float(self.inp_mx_ef.text().replace(",", "."))
            tj = max(0.0, self._total - ef)
            cambio = max(0.0, ef - self._total)
            self.lbl_mx_tj.setText(tr("pago.mixed_card", x=divisas.formatear(tj)))
            self.lbl_mx_cambio.setText(
                tr("pago.mixed_change", x=divisas.formatear(cambio))
            )
        except ValueError:
            pass

    # --- cobrar ---

    def _cobrar(self):
        idx = self._stack.currentIndex()

        if idx == 0:  # efectivo
            try:
                entregado = float(self.inp_ef.text().replace(",", "."))
            except ValueError:
                QMessageBox.warning(
                    self, tr("pago.err_invalid_title"), tr("pago.err_invalid_msg")
                )
                return
            if entregado < self._total - 0.005:
                QMessageBox.warning(
                    self,
                    tr("pago.err_insufficient_title"),
                    tr(
                        "pago.err_insufficient_msg",
                        e=divisas.formatear(entregado),
                        t=divisas.formatear(self._total),
                    ),
                )
                return
            self._resultado = {
                "forma_pago": "efectivo",
                "total": self._total,
                "entregado": round(entregado, 2),
                "cambio": round(entregado - self._total, 2),
                "efectivo_neto": round(self._total, 2),
            }

        elif idx == 1:  # tarjeta
            self._resultado = {
                "forma_pago": "tarjeta",
                "total": self._total,
                "entregado": self._total,
                "cambio": 0.0,
                "efectivo_neto": 0.0,
            }

        else:  # mixto
            try:
                ef = float(self.inp_mx_ef.text().replace(",", "."))
            except ValueError:
                QMessageBox.warning(
                    self, tr("pago.err_invalid_title"), tr("pago.err_cash_msg")
                )
                return
            if ef < 0 or ef > self._total + 0.005:
                QMessageBox.warning(
                    self, tr("pago.err_invalid_title"), tr("pago.err_cash_over")
                )
                return
            tj = round(max(0.0, self._total - ef), 2)
            cambio = round(max(0.0, ef - self._total), 2)
            self._resultado = {
                "forma_pago": "mixto",
                "total": self._total,
                "entregado": round(ef + tj, 2),
                "cambio": cambio,
                "efectivo_neto": round(ef, 2),
                "tarjeta": tj,
            }

        self.accept()

    def get_resultado(self) -> dict | None:
        return self._resultado


# ============================================================
# BÁSCULA — VENTA A GRANEL
# ============================================================


def _es_gerente_o_admin() -> bool:
    """True si el usuario en sesión es GERENTE o ADMINISTRADOR."""
    try:
        u = sesion_global.usuario_actual or {}
        return (u.get("perfil", "") or "").upper() in ("GERENTE", "ADMINISTRADOR")
    except Exception:
        return False


class _BasculaDialog(QDialog):
    """Venta a granel — SELECTOR de familia (rejilla 3×3). Al elegir una familia se abre la ventana con
    sus productos (venta por PESO en la mayoría; por UNIDADES en Panes y Bollería)."""

    def __init__(self, caja_id: str = "—", cajero: str = "—", parent=None, mostrar_gestion: bool = True):
        super().__init__(parent)
        self._caja_id = caja_id
        self._cajero = cajero
        self._mostrar_gestion = mostrar_gestion   # False en autocobro: sin editar precios / gestión
        self._linea_resultado: dict | None = None
        self.setWindowTitle(tr("bascula.title"))
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setObjectName("dlg_bascula")
        self.setStyleSheet(f"#dlg_bascula {{ background: {_BG}; }}")
        try:
            self.setGeometry(QApplication.primaryScreen().availableGeometry())
        except Exception:
            self.setMinimumSize(900, 640)
        self._drag_pos = None
        self._build_ui()

    def showEvent(self, e):
        super().showEvent(e)
        try:
            self.setGeometry(QApplication.primaryScreen().availableGeometry())
        except Exception:
            pass

    # Arrastre de ventana frameless
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def _build_ui(self):
        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(12, 12, 12, 12)
        _cuerpo = QFrame()
        _cuerpo.setObjectName("cuerpo_ventana")
        _cuerpo.setStyleSheet(
            f"QFrame#cuerpo_ventana{{background:{_BG};border:none;border-radius:24px;}}"
        )
        _outer.addWidget(_cuerpo)
        root = QVBoxLayout(_cuerpo)
        root.setContentsMargins(16, 14, 16, 16)
        root.setSpacing(12)
        cab = QFrame()
        cab.setStyleSheet(
            f"QFrame{{background:{_BG2};border:1px solid {_BORDE};border-radius:12px;}}"
        )
        cl = QHBoxLayout(cab)
        cl.setContentsMargins(18, 12, 18, 12)
        cl.addWidget(_lbl(tr("bascula.header"), bold=True, size=20, color=_CIAN))
        cl.addStretch()
        cl.addWidget(_lbl(tr("bascula.info", caja=self._caja_id, cajero=self._cajero),
                          size=12, color=_TEXT2))
        cl.addSpacing(16)
        btn_cerrar = QPushButton("✕")
        btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cerrar.setFixedSize(38, 38)
        btn_cerrar.setStyleSheet(
            f"QPushButton{{background:transparent;color:{_ROJO};border:2px solid {_ROJO};"
            f"border-radius:9px;font-family:'{_FONT}';font-weight:900;font-size:16px;}}"
            f"QPushButton:hover{{background:{_ROJO};color:#0D1117;}}"
        )
        btn_cerrar.clicked.connect(self.reject)
        cl.addWidget(btn_cerrar)
        root.addWidget(cab)
        root.addWidget(_lbl(tr("bascula.pick_family", default="Selecciona una familia de productos"),
                            size=13, color=_TEXT2))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{_BG};border:1px solid {_BORDE};border-radius:12px;}}"
        )
        host = QWidget()
        host.setStyleSheet("background:transparent;")
        self._fam_grid = QGridLayout(host)
        self._fam_grid.setContentsMargins(16, 16, 16, 16)
        self._fam_grid.setSpacing(14)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)
        self._pintar_familias()
        # El botón de gestión/edición de precios NO se muestra en el autocobro (mostrar_gestion=False).
        if self._mostrar_gestion:
            self.btn_cfg = _btn(tr("bascula.edit_prices"), color_fg=_CIAN, color_border=_CIAN,
                                hover_bg=_CIAN, hover_fg="#0D1117", h=44)
            self.btn_cfg.clicked.connect(self._abrir_gestion)
            root.addWidget(self.btn_cfg)

    def _familias_a_mostrar(self):
        from src.services.tpv import bulk_products_service as B
        from src.services.tpv import familias_granel as F

        con = {F.normalizar(p.get("categoria")) for p in B.listar_productos_activos()}
        familias = F.familias()
        # 'Otros' solo si contiene productos (datos legacy) → como 10ª tarjeta.
        if F.FAMILIA_OTROS in con:
            familias = familias + F.familias(incluir_otros=True)[-1:]
        return familias, con

    def _pintar_familias(self):
        while self._fam_grid.count():
            it = self._fam_grid.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        familias, con = self._familias_a_mostrar()
        cols = 3  # rejilla 3×3 (9 familias principales)
        for i, f in enumerate(familias):
            self._fam_grid.addWidget(self._crear_card_familia(f), i // cols, i % cols)

    def _crear_card_familia(self, f):
        modo = (tr("bascula.by_unit", default="por unidad") if f["por_unidad"]
                else tr("bascula.by_weight", default="por peso"))
        btn = QPushButton(f"{f['emoji']}\n{f['etiqueta']}\n({modo})")
        btn.setMinimumSize(200, 140)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:16px;font-family:'{_FONT}';font-weight:900;font-size:16px;}}"
            f"QPushButton:hover{{border-color:{_CIAN};color:{_CIAN};}}"
        )
        btn.clicked.connect(lambda _=False, cod=f["codigo"]: self._abrir_familia(cod))
        return btn

    def _abrir_familia(self, codigo):
        dlg = _BasculaFamiliaDialog(codigo, caja_id=self._caja_id, cajero=self._cajero, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._linea_resultado = dlg.get_linea()
            self.accept()

    def get_linea(self) -> dict | None:
        return self._linea_resultado

    def _abrir_gestion(self):
        if not _es_gerente_o_admin():
            QMessageBox.warning(
                self, tr("bascula.perm_denied_title"), tr("bascula.perm_denied_msg")
            )
            return
        _GestionGranelDialog(self).exec()
        self._pintar_familias()

    def _tick(self):
        pass


class _BasculaFamiliaDialog(QDialog):
    """Productos de UNA familia a granel + panel de venta. Peso (báscula/manual) en la mayoría; número
    de UNIDADES en Panes y Bollería. Produce la línea para el ticket (`get_linea`)."""

    def __init__(self, familia: str, caja_id: str = "—", cajero: str = "—", parent=None):
        super().__init__(parent)
        from src.services.tpv import familias_granel as F

        self._F = F
        self._familia = familia
        self._caja_id = caja_id
        self._cajero = cajero
        self._producto_sel: dict | None = None
        self._linea_resultado: dict | None = None
        self._por_unidad = F.vendido_por_unidad(familia)
        self._scale = None
        if not self._por_unidad:
            try:
                from src.services.tpv.scale_service import get_scale_manager
                self._scale = get_scale_manager()
                self._scale.detect_and_connect()
            except Exception:
                self._scale = None
        self.setWindowTitle(tr("bascula.title"))
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setObjectName("dlg_bascula_fam")
        self.setStyleSheet(f"#dlg_bascula_fam {{ background: {_BG}; }}")
        try:
            self.setGeometry(QApplication.primaryScreen().availableGeometry())
        except Exception:
            self.setMinimumSize(900, 640)
        self._drag_pos = None
        self._build_ui()
        self._cargar_productos()
        if self._scale is not None and getattr(self._scale, "has_hardware", False):
            self._scale.start_polling(self._on_peso_hardware, interval_ms=300)

    def showEvent(self, e):
        super().showEvent(e)
        try:
            self.setGeometry(QApplication.primaryScreen().availableGeometry())
        except Exception:
            pass

    def closeEvent(self, e):
        try:
            if self._scale is not None:
                self._scale.stop_polling()
        except Exception:
            pass
        super().closeEvent(e)

    # Arrastre de ventana frameless
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def _build_ui(self):
        from PyQt6.QtWidgets import QSpinBox

        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(12, 12, 12, 12)
        _cuerpo = QFrame()
        _cuerpo.setObjectName("cuerpo_ventana")
        _cuerpo.setStyleSheet(
            f"QFrame#cuerpo_ventana{{background:{_BG};border:none;border-radius:24px;}}"
        )
        _outer.addWidget(_cuerpo)
        root = QVBoxLayout(_cuerpo)
        root.setContentsMargins(16, 14, 16, 16)
        root.setSpacing(12)
        # Cabecera: volver + familia + modo + cerrar.
        cab = QFrame()
        cab.setStyleSheet(
            f"QFrame{{background:{_BG2};border:1px solid {_BORDE};border-radius:12px;}}"
        )
        cl = QHBoxLayout(cab)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(10)
        btn_back = _btn("←  " + tr("bascula.back_families", default="Familias"), color_fg=_CIAN,
                        color_border=_CIAN, hover_bg=_CIAN, hover_fg="#0D1117", h=40)
        btn_back.clicked.connect(self.reject)
        cl.addWidget(btn_back)
        cl.addSpacing(6)
        cl.addWidget(_lbl(f"{self._F.emoji(self._familia)}  {self._F.etiqueta(self._familia)}",
                          bold=True, size=20, color=_CIAN))
        cl.addStretch()
        modo_hdr = (tr("bascula.mode_unit_hdr", default="Venta por unidades") if self._por_unidad
                    else tr("bascula.mode_weight_hdr", default="Venta por peso"))
        cl.addWidget(_lbl(modo_hdr, size=12, color=_TEXT2))
        cl.addSpacing(12)
        btn_cerrar = QPushButton("✕")
        btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cerrar.setFixedSize(38, 38)
        btn_cerrar.setStyleSheet(
            f"QPushButton{{background:transparent;color:{_ROJO};border:2px solid {_ROJO};"
            f"border-radius:9px;font-family:'{_FONT}';font-weight:900;font-size:16px;}}"
            f"QPushButton:hover{{background:{_ROJO};color:#0D1117;}}"
        )
        btn_cerrar.clicked.connect(self.reject)
        cl.addWidget(btn_cerrar)
        root.addWidget(cab)

        body = QHBoxLayout()
        body.setSpacing(12)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            f"QScrollArea{{background:{_BG};border:1px solid {_BORDE};border-radius:12px;}}"
        )
        self._grid_host = QWidget()
        self._grid_host.setStyleSheet("background:transparent;")
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(12, 12, 12, 12)
        self._grid.setSpacing(10)
        self._scroll.setWidget(self._grid_host)
        body.addWidget(self._scroll, 7)

        panel = QFrame()
        panel.setStyleSheet(
            f"QFrame{{background:{_BG2};border:1px solid {_BORDE};border-radius:12px;}}"
        )
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(18, 16, 18, 16)
        pl.setSpacing(10)
        pl.addWidget(_lbl(tr("bascula.selected_product"), bold=True, size=12, color=_TEXT2))
        self.lbl_prod = _lbl(tr("bascula.none"), bold=True, size=18, color=_TEXT)
        self.lbl_prod.setWordWrap(True)
        pl.addWidget(self.lbl_prod)
        self.lbl_precio_kg = _lbl(tr("bascula.price_dash"), bold=True, size=14, color=_CIAN)
        pl.addWidget(self.lbl_precio_kg)
        pl.addWidget(_sep())
        if self._por_unidad:
            # ── Venta por UNIDADES (Panes / Bollería): NO se pesa. ──
            self.spin_peso = None
            pl.addWidget(_lbl(tr("bascula.units", default="UNIDADES"), bold=True, size=12, color=_TEXT2))
            self.spin_uds = QSpinBox()
            self.spin_uds.setRange(0, 999)
            self.spin_uds.setSingleStep(1)
            self.spin_uds.setValue(0)
            self.spin_uds.setSuffix(" ud")
            self.spin_uds.setFixedHeight(54)
            self.spin_uds.setStyleSheet(
                f"QSpinBox{{background:{_BG};color:{_TEXT};border:2px solid {_BORDE};"
                f"border-radius:10px;font-family:'{_FONT}';font-weight:900;font-size:24px;padding:4px 12px;}}"
                f"QSpinBox:focus{{border-color:{_CIAN};}}"
            )
            self.spin_uds.valueChanged.connect(self._recalcular)
            pl.addWidget(self.spin_uds)
        else:
            # ── Venta por PESO (báscula/manual). ──
            self.spin_uds = None
            self.lbl_modo = _lbl("", bold=True, size=11, color=_TEXT2)
            pl.addWidget(self.lbl_modo)
            pl.addWidget(_lbl(tr("bascula.weight"), bold=True, size=12, color=_TEXT2))
            self.spin_peso = QDoubleSpinBox()
            self.spin_peso.setDecimals(3)
            self.spin_peso.setRange(0.0, 100.0)
            self.spin_peso.setSingleStep(0.050)
            self.spin_peso.setValue(0.0)
            self.spin_peso.setSuffix(" kg")
            self.spin_peso.setFixedHeight(54)
            self.spin_peso.setStyleSheet(
                f"QDoubleSpinBox{{background:{_BG};color:{_TEXT};border:2px solid {_BORDE};"
                f"border-radius:10px;font-family:'{_FONT}';font-weight:900;font-size:24px;padding:4px 12px;}}"
                f"QDoubleSpinBox:focus{{border-color:{_CIAN};}}"
            )
            self.spin_peso.valueChanged.connect(self._recalcular)
            pl.addWidget(self.spin_peso)
            self.btn_tara = _btn(tr("bascula.tare"), h=36)
            self.btn_tara.clicked.connect(self._tara)
            pl.addWidget(self.btn_tara)
        pl.addWidget(_sep())
        self.lbl_total = _lbl(tr("bascula.total", x="0,00"), bold=True, size=26, color=_VERDE)
        self.lbl_total.setAlignment(Qt.AlignmentFlag.AlignRight)
        pl.addWidget(self.lbl_total)
        pl.addStretch()
        self.btn_add = QPushButton(tr("bascula.add_to_ticket"))
        self.btn_add.setFixedHeight(56)
        self.btn_add.setEnabled(False)
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setStyleSheet(
            f"QPushButton{{background:{_VERDE};color:#0D1117;border:none;border-radius:12px;"
            f"font-family:'{_FONT}';font-weight:900;font-size:17px;}}"
            f"QPushButton:hover{{background:#FFF;}}"
            f"QPushButton:disabled{{background:#1C2128;color:#484F58;}}"
        )
        self.btn_add.clicked.connect(self._aceptar)
        pl.addWidget(self.btn_add)
        body.addWidget(panel, 3)
        root.addLayout(body, 1)
        if not self._por_unidad:
            self._refrescar_modo()

    def _refrescar_modo(self):
        if self._scale is not None and getattr(self._scale, "has_hardware", False):
            self.lbl_modo.setText(tr("bascula.mode_auto"))
            self.lbl_modo.setStyleSheet(
                f"color:{_VERDE};font-family:'{_FONT}';font-weight:900;font-size:11px;background:transparent;"
            )
            self.spin_peso.setReadOnly(True)
        else:
            self.lbl_modo.setText(tr("bascula.mode_manual"))
            self.lbl_modo.setStyleSheet(
                f"color:{_TEXT2};font-family:'{_FONT}';font-weight:900;font-size:11px;background:transparent;"
            )
            self.spin_peso.setReadOnly(False)

    def _cargar_productos(self):
        from src.services.tpv import bulk_products_service as B

        F = self._F
        todos = B.listar_productos_activos()
        prods = [p for p in todos if F.normalizar(p.get("categoria")) == self._familia]
        while self._grid.count():
            it = self._grid.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        if not prods:
            self._grid.addWidget(_lbl(tr("bascula.no_products"), size=14, color=_TEXT2), 0, 0)
            return
        cols = 3
        fila = 0
        subs = F.subfamilias(self._familia)
        if subs:
            for s in subs:
                grupo = [p for p in prods
                         if F.normalizar_subfamilia(self._familia, p.get("subfamilia")) == s["codigo"]]
                if not grupo:
                    continue
                self._grid.addWidget(_lbl(s["etiqueta"], bold=True, size=13, color=_CIAN),
                                     fila, 0, 1, cols)
                fila += 1
                for i, p in enumerate(grupo):
                    self._grid.addWidget(self._crear_boton_producto(p), fila + i // cols, i % cols)
                fila += (len(grupo) + cols - 1) // cols
        else:
            for i, p in enumerate(prods):
                self._grid.addWidget(self._crear_boton_producto(p), i // cols, i % cols)

    def _crear_boton_producto(self, p: dict) -> QPushButton:
        emoji = p.get("emoji", "🛒")
        nombre = p.get("nombre", "—")
        precio = float(p.get("precio_kg", 0) or 0)
        sufijo = tr("bascula.per_unit", default="/ud") if self._por_unidad else tr("bascula.per_kg", default="/kg")
        btn = QPushButton(f"{emoji}\n{nombre}\n{divisas.formatear(precio)}{sufijo}")
        btn.setMinimumSize(150, 110)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:14px;font-family:'{_FONT}';font-weight:900;font-size:14px;}}"
            f"QPushButton:hover{{border-color:{_CIAN};}}"
        )
        btn.clicked.connect(lambda _=False, prod=p: self._seleccionar(prod))
        return btn

    def _seleccionar(self, p: dict):
        self._producto_sel = p
        self.lbl_prod.setText(f"{p.get('emoji','')} {p.get('nombre','—')}")
        precio_txt = divisas.formatear(float(p.get("precio_kg", 0)))
        if self._por_unidad:
            self.lbl_precio_kg.setText(tr("bascula.price_ud", default="Precio: {x}/ud", x=precio_txt))
        else:
            self.lbl_precio_kg.setText(tr("bascula.price", x=precio_txt))
        self.btn_add.setEnabled(True)
        if self._por_unidad:
            if self.spin_uds.value() == 0:
                self.spin_uds.setValue(1)
            self.spin_uds.setFocus()
            self.spin_uds.selectAll()
        elif self._scale is None or not getattr(self._scale, "has_hardware", False):
            self.spin_peso.setFocus()
            self.spin_peso.selectAll()
        self._recalcular()

    def _on_peso_hardware(self, peso):
        if peso is not None:
            QTimer.singleShot(0, lambda: self._set_peso_seguro(peso))

    def _set_peso_seguro(self, peso: float):
        try:
            self.spin_peso.blockSignals(True)
            self.spin_peso.setValue(float(peso))
            self.spin_peso.blockSignals(False)
            self._recalcular()
        except Exception:
            pass

    def _tara(self):
        try:
            if self._scale is not None:
                self._scale.tare()
        except Exception:
            pass
        if self.spin_peso is not None:
            self.spin_peso.setValue(0.0)

    def _recalcular(self):
        from src.services.tpv import bulk_products_service as B

        if not self._producto_sel:
            self.lbl_total.setText(tr("bascula.total", x="0,00"))
            return
        precio = float(self._producto_sel.get("precio_kg", 0) or 0)
        if self._por_unidad:
            total = divisas.redondear(self.spin_uds.value() * precio)
        else:
            total = B.calcular_total(self.spin_peso.value(), precio)
        self.lbl_total.setText(tr("bascula.total", x=divisas.formatear(total)))

    def _aceptar(self):
        from src.services.tpv import bulk_products_service as B

        if not self._producto_sel:
            _aviso_modal(self, tr("bascula.sel_product_title"), tr("bascula.sel_product_msg"))
            return
        precio = float(self._producto_sel.get("precio_kg", 0) or 0)
        nombre = self._producto_sel.get("nombre", "Granel")
        codigo = (self._producto_sel.get("codigo_interno")
                  or f"GRANEL-{self._producto_sel.get('id','')}")
        if self._por_unidad:
            uds = int(self.spin_uds.value())
            if uds <= 0:
                _aviso_modal(self, tr("bascula.units_missing_title", default="Indica las unidades"),
                             tr("bascula.units_missing_msg",
                                default="Introduce cuántas unidades quiere el cliente."))
                return
            subtotal = divisas.redondear(uds * precio)
            self._linea_resultado = {
                "codigo": codigo,
                "nombre": tr("bascula.line_name_ud", default="{nombre}  ×{uds} ud", nombre=nombre, uds=uds),
                "seccion": self._producto_sel.get("categoria", "GRANEL"),
                "cantidad": uds,
                "precio": precio,
                "descuento_pct": 0.0,
                "subtotal": subtotal,
                "precio_kg": precio,
                "modo_venta": "UNIDAD",
            }
            self.accept()
            return
        # Venta por peso.
        peso = self.spin_peso.value()
        ok, msg = B.validar_peso(peso)
        if not ok:
            if peso <= 0:
                _aviso_modal(self, tr("bascula.weight_missing_title"),
                             tr("bascula.weight_missing_msg"))
            else:
                _aviso_modal(self, tr("bascula.weight_invalid_title"), msg)
            return
        total = divisas.redondear(B.calcular_total(peso, precio))
        self._linea_resultado = {
            "codigo": codigo,
            "nombre": tr("bascula.line_name", nombre=nombre, peso=_fmt_peso(peso),
                         precio=divisas.formatear(precio)),
            "seccion": self._producto_sel.get("categoria", "GRANEL"),
            "cantidad": 1,
            "precio": total,
            "descuento_pct": 0.0,
            "subtotal": total,
            "peso": peso,
            "precio_kg": precio,
            "modo_venta": "PESO",
        }
        self.accept()

    def get_linea(self) -> dict | None:
        return self._linea_resultado


class _VentaOnlineDialog(QDialog):
    """Venta online desde tienda (F2): consulta de disponibilidad multi-origen
    (tienda/central/otras tiendas/online), captura de cliente y envío, estado y
    generación del pedido online + comprobante."""

    def __init__(self, empleado="—", id_caja="—", parent=None):
        super().__init__(parent)
        self._empleado = empleado
        self._id_caja = id_caja
        self._lineas = []  # [{codigo,nombre,cantidad,precio,subtotal,origen_stock}]
        self._cliente = {}
        self._art = None  # disponibilidad del artículo consultado
        self.setWindowTitle(tr("online.title", default="VENTA ONLINE"))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setObjectName("dlg_online")
        self.setStyleSheet(f"#dlg_online {{ background: {_BG}; }}")
        try:
            self.setGeometry(QApplication.primaryScreen().availableGeometry())
        except Exception:
            self.setMinimumSize(1100, 700)
        self._build()

    def showEvent(self, e):
        super().showEvent(e)
        try:
            self.setGeometry(QApplication.primaryScreen().availableGeometry())
        except Exception:
            pass

    def _inp(self, ph="", w=None):
        e = QLineEdit()
        e.setFixedHeight(34)
        e.setPlaceholderText(ph)
        if w:
            e.setFixedWidth(w)
        e.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}"
        )
        return e

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        card = QFrame(self)
        card.setObjectName("vo")
        card.setStyleSheet(
            f"QFrame#vo{{background:{_BG};border:none;border-radius:18px;}}"
        )
        root.addWidget(card)
        ly = QVBoxLayout(card)
        ly.setContentsMargins(28, 22, 28, 22)
        ly.setSpacing(14)

        hdr = QHBoxLayout()
        hdr.addWidget(
            _lbl(
                "🌐  " + tr("online.title", default="VENTA ONLINE"),
                bold=True,
                size=18,
                color=_CIAN,
            )
        )
        hdr.addStretch()
        bx = QPushButton("✕")
        bx.setFixedSize(36, 36)
        bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet(
            f"QPushButton{{background:{_BG2};color:{_TEXT2};border:1px solid {_BORDE};"
            f"border-radius:8px;font-weight:900;}}QPushButton:hover{{border-color:{_ROJO};color:{_ROJO};}}"
        )
        bx.clicked.connect(self.reject)
        hdr.addWidget(bx)
        ly.addLayout(hdr)
        ly.addWidget(_sep())

        body = QHBoxLayout()
        body.setSpacing(24)
        ly.addLayout(body, 1)
        body.addLayout(self._col_articulos(), 1)
        body.addWidget(self._col_cliente(), 0)

    # ── columna izquierda: artículo + disponibilidad + líneas ──
    def _col_articulos(self):
        col = QVBoxLayout()
        col.setSpacing(10)
        r1 = QHBoxLayout()
        r1.setSpacing(8)
        self.inp_codigo = self._inp(tr("online.cod_ph", default="Código de artículo…"))
        self.inp_codigo.returnPressed.connect(self._consultar)
        b_cons = _btn(
            tr("online.consultar", default="CONSULTAR"),
            color_fg=_CIAN,
            color_border=_CIAN,
            hover_bg=_CIAN,
            h=34,
        )
        b_cons.clicked.connect(self._consultar)
        r1.addWidget(
            _lbl(
                tr("online.articulo", default="Artículo"),
                bold=True,
                size=12,
                color=_TEXT2,
            )
        )
        r1.addWidget(self.inp_codigo, 1)
        r1.addWidget(b_cons)
        col.addLayout(r1)

        self.lbl_disp = _lbl(
            tr(
                "online.disp_vacio",
                default="Consulta un artículo para ver su disponibilidad.",
            ),
            size=12,
            color=_TEXT2,
        )
        self.lbl_disp.setWordWrap(True)
        disp_card = _card()
        dl = QVBoxLayout(disp_card)
        dl.setContentsMargins(14, 10, 14, 10)
        dl.addWidget(self.lbl_disp)
        col.addWidget(disp_card)

        # Almacén de ORIGEN: solo los almacenes con stock FÍSICO del artículo consultado (datos del stock por
        # almacén / Kárdex). El trabajador elige de dónde traer el producto para este pedido.
        r_alm = QHBoxLayout()
        r_alm.setSpacing(8)
        r_alm.addWidget(_lbl(tr("online.almacen", default="Almacén de origen"),
                             bold=True, size=12, color=_TEXT2))
        self.cmb_almacen = QComboBox()
        self.cmb_almacen.setFixedHeight(34)
        self.cmb_almacen.setMinimumWidth(260)
        self.cmb_almacen.setStyleSheet(
            f"QComboBox{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};border-radius:8px;"
            f"padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
            f"QComboBox:focus{{border-color:{_CIAN};}}")
        r_alm.addWidget(self.cmb_almacen, 1)
        col.addLayout(r_alm)

        r2 = QHBoxLayout()
        r2.setSpacing(8)
        self.inp_cant = self._inp(tr("online.cant", default="Cant."), 90)
        self.inp_cant.setText("1")
        r2.addWidget(
            _lbl(
                tr("online.cantidad", default="Cantidad"),
                bold=True,
                size=12,
                color=_TEXT2,
            )
        )
        r2.addWidget(self.inp_cant)
        b_add = _btn(
            tr("online.add", default="AÑADIR LÍNEA"),
            color_bg=_CIAN,
            color_fg="#0D1117",
            color_border=_CIAN,
            hover_bg="#FFF",
            hover_fg="#0D1117",
            h=34,
        )
        b_add.clicked.connect(self._add_linea)
        b_quit = _btn(
            tr("online.quitar", default="QUITAR"),
            color_fg=_ROJO,
            color_border=_ROJO,
            hover_bg=_ROJO,
            hover_fg="#FFF",
            h=34,
        )
        b_quit.clicked.connect(self._quitar_linea)
        r2.addWidget(b_add)
        r2.addStretch()
        r2.addWidget(b_quit)
        col.addLayout(r2)

        self.tabla = QTableWidget(0, 6)
        self.tabla.setHorizontalHeaderLabels(
            [
                tr("online.col_cod", default="Código"),
                tr("online.col_art", default="Artículo"),
                tr("online.col_cant", default="Cant."),
                tr("online.col_precio", default="Precio"),
                tr("online.col_sub", default="Subtotal"),
                tr("online.col_alm", default="Almacén"),
            ]
        )
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        for cidx in (0, 2, 3, 4):
            hh.setSectionResizeMode(cidx, QHeaderView.ResizeMode.Fixed)
        self.tabla.setColumnWidth(0, 110)
        self.tabla.setColumnWidth(2, 70)
        self.tabla.setColumnWidth(3, 100)
        self.tabla.setColumnWidth(4, 110)
        self.tabla.setStyleSheet(_ss_tabla_neon())
        _RoundTableCorners(self.tabla)
        col.addWidget(self.tabla, 1)

        self.lbl_total = _lbl(
            tr("online.total", default="TOTAL:  {x}", x=divisas.formatear(0)),
            bold=True,
            size=16,
            color=_CIAN,
        )
        self.lbl_total.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        col.addWidget(self.lbl_total)
        return col

    # ── columna derecha: cliente + envío + estado + crear ──
    def _col_cliente(self):
        w = QFrame()
        w.setFixedWidth(360)
        w.setObjectName("voc")
        w.setStyleSheet(
            f"QFrame#voc{{background:{_BG2};border:1px solid {_BORDE};border-radius:14px;}}"
        )
        col = QVBoxLayout(w)
        col.setContentsMargins(16, 14, 16, 16)
        col.setSpacing(10)
        col.addWidget(
            _lbl(
                tr("online.cliente", default="CLIENTE Y ENVÍO"),
                bold=True,
                size=13,
                color=_CIAN,
            )
        )
        self.inp_cli_nombre = self._inp(
            tr("online.cli_nombre", default="Nombre / Razón social")
        )
        self.inp_cli_tel = self._inp(tr("online.cli_tel", default="Teléfono"))
        self.inp_cli_email = self._inp(tr("online.cli_email", default="Email"))
        self.inp_cli_dir = self._inp(tr("online.cli_dir", default="Dirección de envío"))
        b_buscar = _btn(
            tr("online.buscar_cli", default="BUSCAR CLIENTE"),
            color_fg=_CIAN,
            color_border=_CIAN,
            hover_bg=_CIAN,
            h=34,
        )
        b_buscar.clicked.connect(self._buscar_cliente)
        col.addWidget(b_buscar)
        for ww in (
            self.inp_cli_nombre,
            self.inp_cli_tel,
            self.inp_cli_email,
            self.inp_cli_dir,
        ):
            col.addWidget(ww)

        # Tipo de pedido: entrega a domicilio o recogida en tienda (Click & Collect). Mismo flujo.
        col.addSpacing(6)
        col.addWidget(_lbl(tr("online.tipo_pedido", default="Tipo de pedido"), bold=True, size=12,
                           color=_TEXT2))
        self.cmb_cumplimiento = QComboBox()
        self.cmb_cumplimiento.setFixedHeight(36)
        self.cmb_cumplimiento.setStyleSheet(
            f"QComboBox{{combobox-popup:0;background:{_BG};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
            f"QComboBox:hover,QComboBox:on{{border-color:{_CIAN};}}"
            f"QComboBox::drop-down{{border:none;width:22px;}}"
            f"QComboBox QAbstractItemView{{background:#0D1117;color:{_TEXT};border:2px solid {_CIAN};"
            f"border-radius:8px;selection-background-color:{_CIAN};selection-color:#0D1117;}}"
        )
        self.cmb_cumplimiento.addItem("🚚 " + tr("online.tipo_delivery", default="Entrega a domicilio"),
                                      "DELIVERY")
        self.cmb_cumplimiento.addItem("🏪 " + tr("online.tipo_pickup_full", default="Recogida en tienda"),
                                      "PICKUP_STORE")
        self.cmb_cumplimiento.currentIndexChanged.connect(self._cambio_cumplimiento)
        col.addWidget(self.cmb_cumplimiento)

        col.addSpacing(6)
        col.addWidget(
            _lbl(
                tr("online.estado", default="Estado del pedido"),
                bold=True,
                size=12,
                color=_TEXT2,
            )
        )
        from src.services.tpv.online_orders_service import ESTADOS

        self.cmb_estado = QComboBox()
        self.cmb_estado.setFixedHeight(36)
        self.cmb_estado.setStyleSheet(
            f"QComboBox{{combobox-popup:0;background:{_BG};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
            f"QComboBox:hover,QComboBox:on{{border-color:{_CIAN};}}"
            f"QComboBox::drop-down{{border:none;width:22px;}}"
            f"QComboBox QAbstractItemView{{background:#0D1117;color:{_TEXT};border:2px solid {_CIAN};"
            f"border-radius:8px;selection-background-color:{_CIAN};selection-color:#0D1117;}}"
        )
        for e in ESTADOS:
            self.cmb_estado.addItem(e, e)
        col.addWidget(self.cmb_estado)
        col.addStretch()
        b_crear = _btn(
            tr("online.crear", default="CREAR PEDIDO"),
            color_bg=_VERDE,
            color_fg="#0D1117",
            color_border=_VERDE,
            hover_bg="#FFF",
            hover_fg="#0D1117",
            h=48,
        )
        b_crear.clicked.connect(self._crear)
        col.addWidget(b_crear)
        return w

    # ── lógica ──
    def _msg(self, titulo, texto, nivel="info"):
        try:
            from assets.estilo_global import mostrar_mensaje as _mm

            _mm(self, titulo, texto, nivel=nivel)
        except Exception:
            pass

    def _consultar(self):
        codigo = self.inp_codigo.text().strip()
        if not codigo:
            return
        from src.services.tpv import online_orders_service as OS

        disp = OS.consultar_disponibilidad(codigo)
        if not disp.get("nombre"):
            self._art = None
            self.lbl_disp.setText(
                tr(
                    "online.no_art",
                    default="No se encontró el artículo «{c}».",
                    c=codigo,
                )
            )
            return
        self._art = disp
        self._poblar_almacenes(codigo)
        otras = (
            ", ".join(f"{t['nombre']}: {t['stock']}" for t in disp["otras_tiendas"])
            or "—"
        )
        self.lbl_disp.setText(
            f"<b>{disp['nombre']}</b>  ·  {divisas.formatear(disp['precio'])}<br>"
            + tr(
                "online.disp_linea",
                default="Tienda: {t}   ·   Central: {c}   ·   Otras tiendas: {o}   ·   Online: {n}",
                t=disp["tienda"],
                c=disp["central"],
                o=otras,
                n=disp["online"],
            )
        )

    def _poblar_almacenes(self, codigo):
        """Rellena el combo con los almacenes que tienen stock FÍSICO del artículo (fuente: stock por
        almacén / Kárdex). Si ninguno tiene stock, ofrece «bajo pedido»."""
        self.cmb_almacen.clear()
        try:
            from src.db import stock_almacen as SA
            detalle = SA.obtener_stock_articulo(codigo).get("detalle", []) or []
        except Exception:
            detalle = []
        con_stock = [d for d in detalle if int(d.get("cantidad") or 0) > 0]
        if not con_stock:
            self.cmb_almacen.addItem(
                tr("online.alm_sin_stock", default="(sin stock físico — bajo pedido)"), None)
            return
        for d in con_stock:
            self.cmb_almacen.addItem(
                f"{d.get('nombre')}  ·  {int(d['cantidad'])} ud.", d.get("id_almacen"))

    def _add_linea(self):
        if not self._art:
            self._msg(
                tr("online.title", default="VENTA ONLINE"),
                tr("online.consulta_primero", default="Consulta primero un artículo."),
                "warning",
            )
            return
        try:
            cant = max(1, int(float(self.inp_cant.text().replace(",", "."))))
        except ValueError:
            cant = 1
        precio = float(self._art.get("precio") or 0)
        id_alm = self.cmb_almacen.currentData() if hasattr(self, "cmb_almacen") else None
        alm_nom = (self.cmb_almacen.currentText().split("  ·")[0].strip()
                   if getattr(self, "cmb_almacen", None) and self.cmb_almacen.count() else "—")
        self._lineas.append(
            {
                "codigo": self._art["codigo"],
                "nombre": self._art["nombre"],
                "cantidad": cant,
                "precio": precio,
                "subtotal": round(cant * precio, 2),
                "id_almacen": id_alm,        # almacén de origen elegido (stock físico / Kárdex)
                "almacen": alm_nom,
                "origen_stock": "central",   # compat con crear_pedido_online
            }
        )
        self._refrescar_tabla()

    def _quitar_linea(self):
        r = self.tabla.currentRow()
        if 0 <= r < len(self._lineas):
            self._lineas.pop(r)
            self._refrescar_tabla()

    def _refrescar_tabla(self):
        self.tabla.setRowCount(0)
        total = 0.0
        for l in self._lineas:
            r = self.tabla.rowCount()
            self.tabla.insertRow(r)
            total += l["subtotal"]
            vals = [
                l["codigo"],
                l["nombre"],
                str(l["cantidad"]),
                divisas.formatear(l["precio"]),
                divisas.formatear(l["subtotal"]),
                l.get("almacen") or "—",
            ]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c in (2, 3, 4):
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tabla.setItem(r, c, it)
        self.lbl_total.setText(
            tr("online.total", default="TOTAL:  {x}", x=divisas.formatear(total))
        )

    def _buscar_cliente(self):
        dlg = _ClienteDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            cli = dlg.get_cliente() or {}
            self._cliente = cli
            self.inp_cli_nombre.setText(cli.get("nombre") or "")
            self.inp_cli_tel.setText(cli.get("telefono") or "")
            self.inp_cli_email.setText(cli.get("email") or "")

    def _crear(self):
        if not self._lineas:
            self._msg(
                tr("online.title", default="VENTA ONLINE"),
                tr("online.sin_lineas", default="Añade al menos un artículo."),
                "warning",
            )
            return
        nombre = self.inp_cli_nombre.text().strip()
        if not nombre:
            self._msg(
                tr("online.title", default="VENTA ONLINE"),
                tr("online.sin_cliente", default="Indica el nombre del cliente."),
                "warning",
            )
            return
        cliente = {
            "id": (self._cliente or {}).get("id"),
            "nombre": nombre,
            "telefono": self.inp_cli_tel.text().strip(),
            "email": self.inp_cli_email.text().strip(),
        }
        # Recogida en tienda (Click & Collect): mismo flujo de creación, reutiliza pickup.reservar.
        if hasattr(self, "cmb_cumplimiento") and self.cmb_cumplimiento.currentData() == "PICKUP_STORE":
            self._crear_recogida(cliente)
            return

        from src.services.tpv import online_orders_service as OS

        pid = OS.crear_pedido_online(
            cliente,
            self._lineas,
            direccion_envio=self.inp_cli_dir.text().strip(),
            estado=self.cmb_estado.currentData() or "PENDIENTE",
        )
        if not pid:
            self._msg(
                tr("online.title", default="VENTA ONLINE"),
                tr("online.error", default="No se pudo crear el pedido."),
                "error",
            )
            return
        try:
            OS.generar_comprobante(pid)
        except Exception:
            pass
        # Vuelca los artículos del pedido a la CESTA del TPV para cobrarlos desde ahí (se añaden a lo que ya
        # hubiera en la cesta, no la reemplazan).
        volcado = self._volcar_a_tpv()
        self._msg(
            tr("online.ok_t", default="Pedido online creado"),
            (tr("online.ok_tpv",
                default="Pedido {p} registrado. Sus artículos se han añadido a la cesta del TPV para "
                        "cobrarlos.", p=pid) if volcado
             else tr("online.ok", default="Pedido {p} registrado y comprobante generado.", p=pid)),
            "success",
        )
        self.accept()

    def _tpv_window(self):
        """Busca la ventana TPV subiendo por la cadena de padres (el TPV abre el Portal con parent=self)."""
        w = self.parent()
        while w is not None:
            if isinstance(w, TPVWindow):
                return w
            w = w.parent()
        return None

    def _volcar_a_tpv(self) -> bool:
        """Añade las líneas del pedido a la cesta del TPV (si hay un TPV en la cadena de padres)."""
        tpv = self._tpv_window()
        if tpv is None:
            return False
        try:
            tpv.agregar_lineas_externas(self._lineas)
            return True
        except Exception:
            return False

    def _cambio_cumplimiento(self):
        """Al elegir recogida en tienda, el envío/estado no aplican (los gobierna el servicio pickup)."""
        try:
            es_pickup = self.cmb_cumplimiento.currentData() == "PICKUP_STORE"
            self.inp_cli_dir.setEnabled(not es_pickup)
            self.cmb_estado.setEnabled(not es_pickup)
            if es_pickup:
                self.inp_cli_dir.setPlaceholderText(
                    tr("online.pickup_dir_na", default="(recogida en tienda — sin envío)"))
        except Exception:
            pass

    def _crear_recogida(self, cliente):
        """Crea una reserva Click & Collect reutilizando el servicio `pickup.reservar` (mismo flujo de
        creación de pedido; NO duplica lógica ni crea otra pantalla). La tienda es la ACTIVA."""
        try:
            from src.db.empresa import tienda_actual_id
            id_tienda = tienda_actual_id()
        except Exception:
            id_tienda = None
        if not id_tienda:
            self._msg(tr("online.title", default="VENTA ONLINE"),
                      tr("online.pickup_sin_tienda",
                         default="Selecciona una tienda para la recogida."), "warning")
            return
        from src.services.comercio_digital import pickup
        lineas = [{"codigo": l.get("codigo"), "cantidad": l.get("cantidad")} for l in self._lineas]
        r = pickup.reservar(id_tienda=id_tienda, cliente=cliente, lineas=lineas, canal="tpv",
                            actor=self._empleado)
        if not r.get("ok"):
            self._msg(tr("online.title", default="VENTA ONLINE"),
                      tr("online.pickup_err", default="No se pudo crear la reserva: {m}",
                         m=r.get("motivo", "")), "error")
            return
        self._msg(tr("online.pickup_ok_t", default="Reserva de recogida creada"),
                  tr("online.pickup_ok",
                     default="Reserva {p} creada (pendiente de pago y recogida).",
                     p=str(r.get("id_tx"))[:8]), "success")
        self.accept()


class _TiendaOnlineConfigDialog(QDialog):
    """Configuración de la tienda online (plataforma + URL + credenciales API).

    @deprecated (Rearquitectura CD · Fase 4): diálogo HUÉRFANO (sin llamadores). Edita `ecommerce_config`
    (Escenario A: conexión a una plataforma EXTERNA — WooCommerce/Shopify/Prestashop), que es una
    responsabilidad DISTINTA de la web propia (Escenario B · `web_config`, administrada en Canal Web) y
    NO una duplicidad de ésta. Se conserva como capa de compatibilidad; su futura ubicación es un
    conector oficial del Marketplace + `comercio_digital.conexiones` (Secret Manager). No eliminar hasta
    consolidar Escenario A; hoy no se elimina para no romper `ecommerce_config`/adaptadores en uso."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(480)
        self._guardado = False
        from src.db import ecommerce as _ec

        self._cfg = _ec.obtener_config()
        self._build()

    def _inp(self, val=""):
        e = QLineEdit(val or "")
        e.setFixedHeight(36)
        e.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}"
        )
        return e

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        cuerpo = QFrame()
        cuerpo.setObjectName("cfgto")
        cuerpo.setStyleSheet(
            f"QFrame#cfgto{{background:{_BG};border:2px solid {_CIAN};border-radius:18px;}}"
        )
        outer.addWidget(cuerpo)
        v = QVBoxLayout(cuerpo)
        v.setContentsMargins(24, 22, 24, 22)
        v.setSpacing(10)
        v.addWidget(
            _lbl(
                "⚙  " + tr("online.cfg_title", default="TIENDA ONLINE"),
                bold=True,
                size=16,
                color=_CIAN,
            )
        )
        v.addWidget(
            _lbl(
                tr("online.cfg_plat", default="Plataforma"),
                bold=True,
                size=12,
                color=_TEXT2,
            )
        )
        from src.db.ecommerce import PLATAFORMAS

        self.cmb = QComboBox()
        self.cmb.setFixedHeight(36)
        self.cmb.setStyleSheet(
            f"QComboBox{{combobox-popup:0;background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
            f"QComboBox:hover,QComboBox:on{{border-color:{_CIAN};}}"
            f"QComboBox::drop-down{{border:none;width:22px;}}"
            f"QComboBox QAbstractItemView{{background:#0D1117;color:{_TEXT};border:2px solid {_CIAN};"
            f"border-radius:8px;selection-background-color:{_CIAN};selection-color:#0D1117;}}"
        )
        etiquetas = {
            "web": "Web propia",
            "woocommerce": "WooCommerce",
            "shopify": "Shopify",
            "prestashop": "PrestaShop",
        }
        for p in PLATAFORMAS:
            self.cmb.addItem(etiquetas.get(p, p), p)
        i = self.cmb.findData(self._cfg.get("plataforma", "web"))
        if i >= 0:
            self.cmb.setCurrentIndex(i)
        v.addWidget(self.cmb)
        v.addWidget(
            _lbl(
                tr("online.cfg_url", default="URL de la tienda (https://…)"),
                bold=True,
                size=12,
                color=_TEXT2,
            )
        )
        self.inp_url = self._inp(self._cfg.get("base_url"))
        v.addWidget(self.inp_url)
        v.addWidget(
            _lbl(
                tr("online.cfg_key", default="API key / Consumer key / Token"),
                bold=True,
                size=12,
                color=_TEXT2,
            )
        )
        self.inp_key = self._inp(self._cfg.get("api_key"))
        v.addWidget(self.inp_key)
        v.addWidget(
            _lbl(
                tr("online.cfg_secret", default="API secret (si aplica)"),
                bold=True,
                size=12,
                color=_TEXT2,
            )
        )
        self.inp_secret = self._inp(self._cfg.get("api_secret"))
        v.addWidget(self.inp_secret)
        v.addSpacing(4)
        fila = QHBoxLayout()
        fila.setSpacing(10)
        b_cancel = _btn(tr("online.cfg_cancel", default="CANCELAR"), h=44)
        b_cancel.clicked.connect(self.reject)
        b_ok = _btn(
            tr("online.cfg_save", default="GUARDAR"),
            color_bg=_VERDE,
            color_fg="#0D1117",
            color_border=_VERDE,
            hover_bg="#FFF",
            hover_fg="#0D1117",
            h=44,
        )
        b_ok.clicked.connect(self._guardar)
        fila.addWidget(b_cancel)
        fila.addWidget(b_ok)
        v.addLayout(fila)

    def _guardar(self):
        from src.db import ecommerce as _ec

        _ec.guardar_config(
            plataforma=self.cmb.currentData(),
            base_url=self.inp_url.text().strip(),
            api_key=self.inp_key.text().strip(),
            api_secret=self.inp_secret.text().strip(),
        )
        self._guardado = True
        self.accept()


class _EnvioDialog(QDialog):
    """Datos de envío al marcar un pedido como ENVIADO (transportista + nº seguimiento)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(440)
        self._build()

    def _inp(self, ph=""):
        e = QLineEdit()
        e.setFixedHeight(36)
        e.setPlaceholderText(ph)
        e.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}"
        )
        return e

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        cuerpo = QFrame()
        cuerpo.setObjectName("envto")
        cuerpo.setStyleSheet(
            f"QFrame#envto{{background:{_BG};border:2px solid {_CIAN};border-radius:18px;}}"
        )
        outer.addWidget(cuerpo)
        v = QVBoxLayout(cuerpo)
        v.setContentsMargins(24, 22, 24, 22)
        v.setSpacing(10)
        v.addWidget(
            _lbl(
                "🚚  " + tr("online.env_title", default="DATOS DE ENVÍO"),
                bold=True,
                size=16,
                color=_CIAN,
            )
        )
        v.addWidget(
            _lbl(
                tr("online.env_transportista", default="Transportista"),
                bold=True,
                size=12,
                color=_TEXT2,
            )
        )
        self.inp_trans = self._inp(
            tr("online.env_trans_ph", default="Ej.: SEUR, Correos, MRW…")
        )
        v.addWidget(self.inp_trans)
        v.addWidget(
            _lbl(
                tr("online.env_seguimiento", default="Nº de seguimiento"),
                bold=True,
                size=12,
                color=_TEXT2,
            )
        )
        self.inp_seg = self._inp(
            tr("online.env_seg_ph", default="Nº de tracking del envío")
        )
        v.addWidget(self.inp_seg)
        v.addSpacing(4)
        fila = QHBoxLayout()
        fila.setSpacing(10)
        b_cancel = _btn(tr("online.cfg_cancel", default="CANCELAR"), h=44)
        b_cancel.clicked.connect(self.reject)
        b_ok = _btn(
            tr("online.env_ok", default="MARCAR ENVIADO"),
            color_bg=_VERDE,
            color_fg="#0D1117",
            color_border=_VERDE,
            hover_bg="#FFF",
            hover_fg="#0D1117",
            h=44,
        )
        b_ok.clicked.connect(self.accept)
        fila.addWidget(b_cancel)
        fila.addWidget(b_ok)
        v.addLayout(fila)

    def transportista(self):
        return self.inp_trans.text().strip()

    def seguimiento(self):
        return self.inp_seg.text().strip()


class _PasarelaConfigDialog(QDialog):
    """Configuración de la pasarela de pago (proveedor + credenciales + modo)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(480)
        from src.db import pagos as _pg

        self._cfg = _pg.obtener_config()
        self._build()

    def _inp(self, val=""):
        e = QLineEdit(val or "")
        e.setFixedHeight(36)
        e.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}"
        )
        return e

    def _combo(self, opciones, actual):
        cb = QComboBox()
        cb.setFixedHeight(36)
        cb.setStyleSheet(
            f"QComboBox{{combobox-popup:0;background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
            f"QComboBox:hover,QComboBox:on{{border-color:{_CIAN};}}"
            f"QComboBox::drop-down{{border:none;width:22px;}}"
            f"QComboBox QAbstractItemView{{background:#0D1117;color:{_TEXT};border:2px solid {_CIAN};"
            f"border-radius:8px;selection-background-color:{_CIAN};selection-color:#0D1117;}}"
        )
        for etq, val in opciones:
            cb.addItem(etq, val)
        i = cb.findData(actual)
        if i >= 0:
            cb.setCurrentIndex(i)
        return cb

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        cuerpo = QFrame()
        cuerpo.setObjectName("pasto")
        cuerpo.setStyleSheet(
            f"QFrame#pasto{{background:{_BG};border:2px solid {_CIAN};border-radius:18px;}}"
        )
        outer.addWidget(cuerpo)
        v = QVBoxLayout(cuerpo)
        v.setContentsMargins(24, 22, 24, 22)
        v.setSpacing(10)
        v.addWidget(
            _lbl(
                "💳  " + tr("online.pas_title", default="PASARELA DE PAGO"),
                bold=True,
                size=16,
                color=_CIAN,
            )
        )
        v.addWidget(
            _lbl(
                tr("online.pas_prov", default="Proveedor"),
                bold=True,
                size=12,
                color=_TEXT2,
            )
        )
        # El combo se construye desde el registro de pasarelas (extensible): añadir
        # una pasarela nueva la hace aparecer aquí sin tocar este diálogo.
        from src.services.tpv.pagos.registry import (
            pasarelas_registradas,
            proveedor_por_defecto,
        )

        _rec = tr("online.pas_recomendado", default="recomendado")
        opciones = [
            (meta["etiqueta"] + (f"  ({_rec})" if meta["recomendada"] else ""), nombre)
            for nombre, meta in pasarelas_registradas().items()
        ]
        self.cmb = self._combo(
            opciones, self._cfg.get("proveedor") or proveedor_por_defecto()
        )
        v.addWidget(self.cmb)
        v.addWidget(
            _lbl(
                tr("online.pas_key", default="API key / Client ID / Nº terminal"),
                bold=True,
                size=12,
                color=_TEXT2,
            )
        )
        self.inp_key = self._inp(self._cfg.get("api_key"))
        v.addWidget(self.inp_key)
        v.addWidget(
            _lbl(
                tr(
                    "online.pas_secret",
                    default="API secret / Client secret / Clave Redsys",
                ),
                bold=True,
                size=12,
                color=_TEXT2,
            )
        )
        self.inp_secret = self._inp(self._cfg.get("api_secret"))
        v.addWidget(self.inp_secret)
        v.addWidget(
            _lbl(
                tr("online.pas_com", default="Comercio / FUC (Redsys)"),
                bold=True,
                size=12,
                color=_TEXT2,
            )
        )
        self.inp_com = self._inp(self._cfg.get("comercio"))
        v.addWidget(self.inp_com)
        v.addWidget(
            _lbl(
                tr(
                    "online.pas_whsecret",
                    default="Webhook secret (confirmación automática del pago)",
                ),
                bold=True,
                size=12,
                color=_TEXT2,
            )
        )
        self.inp_whsecret = self._inp(self._cfg.get("webhook_secret"))
        v.addWidget(self.inp_whsecret)
        fila_m = QHBoxLayout()
        fila_m.setSpacing(10)
        colm = QVBoxLayout()
        colm.addWidget(
            _lbl(
                tr("online.pas_modo", default="Modo"), bold=True, size=12, color=_TEXT2
            )
        )
        self.cmb_modo = self._combo(
            [("Test", "test"), ("Live", "live")], self._cfg.get("modo", "test")
        )
        colm.addWidget(self.cmb_modo)
        fila_m.addLayout(colm)
        colc = QVBoxLayout()
        colc.addWidget(
            _lbl(
                tr("online.pas_moneda", default="Moneda"),
                bold=True,
                size=12,
                color=_TEXT2,
            )
        )
        self.inp_moneda = self._inp(self._cfg.get("moneda") or "EUR")
        colc.addWidget(self.inp_moneda)
        fila_m.addLayout(colc)
        v.addLayout(fila_m)
        v.addSpacing(4)
        fila = QHBoxLayout()
        fila.setSpacing(10)
        b_cancel = _btn(tr("online.cfg_cancel", default="CANCELAR"), h=44)
        b_cancel.clicked.connect(self.reject)
        b_ok = _btn(
            tr("online.cfg_save", default="GUARDAR"),
            color_bg=_VERDE,
            color_fg="#0D1117",
            color_border=_VERDE,
            hover_bg="#FFF",
            hover_fg="#0D1117",
            h=44,
        )
        b_ok.clicked.connect(self._guardar)
        fila.addWidget(b_cancel)
        fila.addWidget(b_ok)
        v.addLayout(fila)

    def _guardar(self):
        from src.db import pagos as _pg
        from src.gui.mfa_gui import step_up_sesion

        if not step_up_sesion("pagos.pasarela.configurar", self):
            return
        _pg.guardar_config(
            proveedor=self.cmb.currentData(),
            api_key=self.inp_key.text().strip(),
            api_secret=self.inp_secret.text().strip(),
            comercio=self.inp_com.text().strip(),
            modo=self.cmb_modo.currentData(),
            moneda=(self.inp_moneda.text().strip() or "EUR").upper(),
            webhook_secret=self.inp_whsecret.text().strip(),
        )
        self.accept()


class _CobroDialog(QDialog):
    """Cobro online de un pedido: genera enlace de pago y verifica el cobro. Cuando el pedido es una
    reserva Click & Collect (`es_pickup`), amplía el diálogo con cobro/cancelación+reembolso de la
    reserva reutilizando el servicio `pickup` (pagar / cancelar → pagos.refund). No crea otra pantalla."""

    def __init__(self, pedido: dict, parent=None, *, es_pickup=False, id_tx=None):
        super().__init__(parent)
        self._pid = pedido.get("id_pedido")
        self._es_pickup = es_pickup
        self._id_tx = id_tx or pedido.get("id_pedido")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(540)
        self._build()
        self._refrescar()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        cuerpo = QFrame()
        cuerpo.setObjectName("cobto")
        cuerpo.setStyleSheet(
            f"QFrame#cobto{{background:{_BG};border:2px solid {_CIAN};border-radius:18px;}}"
        )
        outer.addWidget(cuerpo)
        v = QVBoxLayout(cuerpo)
        v.setContentsMargins(24, 22, 24, 22)
        v.setSpacing(10)
        v.addWidget(
            _lbl(
                "💳  " + tr("online.cobro_title", default="COBRO ONLINE"),
                bold=True,
                size=16,
                color=_CIAN,
            )
        )
        self.lbl_info = _lbl("", size=12, color=_TEXT)
        v.addWidget(self.lbl_info)
        self.lbl_estado = _lbl("", bold=True, size=12, color=_CIAN)
        v.addWidget(self.lbl_estado)
        self.inp_enlace = QLineEdit()
        self.inp_enlace.setReadOnly(True)
        self.inp_enlace.setFixedHeight(34)
        self.inp_enlace.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT2};border:1px solid {_BORDE};"
            f"border-radius:8px;padding:0 10px;font-size:11px;font-family:'{_FONT}';}}"
        )
        v.addWidget(self.inp_enlace)
        fila_e = QHBoxLayout()
        fila_e.setSpacing(10)
        self.b_gen = _btn(
            tr("online.cobro_gen", default="Generar enlace de pago"),
            color_fg=_CIAN,
            color_border=_CIAN,
            hover_bg=_CIAN,
            h=40,
        )
        self.b_gen.clicked.connect(self._generar)
        self.b_open = _btn(tr("online.cobro_open", default="Abrir"), h=40)
        self.b_open.clicked.connect(self._abrir)
        self.b_copy = _btn(tr("online.cobro_copy", default="Copiar"), h=40)
        self.b_copy.clicked.connect(self._copiar)
        for b in (self.b_gen, self.b_open, self.b_copy):
            fila_e.addWidget(b)
        v.addLayout(fila_e)
        v.addSpacing(2)
        fila = QHBoxLayout()
        fila.setSpacing(10)
        b_cfg = _btn(tr("online.cobro_cfg", default="Configurar pasarela"), h=44)
        b_cfg.clicked.connect(self._configurar)
        b_ver = _btn(
            tr("online.cobro_verificar", default="VERIFICAR PAGO"),
            color_bg=_VERDE,
            color_fg="#0D1117",
            color_border=_VERDE,
            hover_bg="#FFF",
            hover_fg="#0D1117",
            h=44,
        )
        b_ver.clicked.connect(self._verificar)
        b_close = _btn(tr("online.cfg_cancel", default="CERRAR"), h=44)
        b_close.clicked.connect(self.reject)
        fila.addWidget(b_cfg)
        fila.addWidget(b_close)
        fila.addWidget(b_ver)
        v.addLayout(fila)

        # Reserva Click & Collect: cobro / cancelación + reembolso (reutiliza pickup). Oculta los
        # controles de enlace de pago legacy (no aplican a una reserva).
        if self._es_pickup:
            for b in (self.b_gen, self.b_open, self.b_copy, b_ver, b_cfg):
                b.setVisible(False)
            self.inp_enlace.setVisible(False)
            fila_pk = QHBoxLayout()
            fila_pk.setSpacing(10)
            b_pk_cobrar = _btn("💳  " + tr("online.pk_cobrar", default="Cobrar reserva"),
                               color_bg=_VERDE, color_fg="#0D1117", color_border=_VERDE,
                               hover_bg="#FFF", hover_fg="#0D1117", h=44)
            b_pk_cobrar.clicked.connect(self._pk_cobrar)
            b_pk_cancel = _btn("✖  " + tr("online.pk_cancelar", default="Cancelar y reembolsar"),
                               color_fg=_TEXT2, color_border=_BORDE, hover_bg=_ROJO, h=44)
            b_pk_cancel.clicked.connect(self._pk_cancelar)
            fila_pk.addWidget(b_pk_cobrar)
            fila_pk.addWidget(b_pk_cancel)
            v.addLayout(fila_pk)

    def _pk_cobrar(self):
        from assets.estilo_global import mostrar_mensaje as _mm

        from src.services.comercio_digital import pickup
        r = pickup.pagar(self._id_tx)
        _mm(self, tr("online.cobro_title", default="COBRO ONLINE"),
            tr("online.pk_pagado", default="Reserva cobrada (PAGADA).") if r.get("ok")
            else tr("online.pk_pago_err", default="No se pudo cobrar la reserva."),
            "success" if r.get("ok") else "error")
        self._refrescar()

    def _pk_cancelar(self):
        from assets.estilo_global import mostrar_mensaje as _mm

        from src.services.comercio_digital import pickup
        try:
            from src.db.usuario import sesion_global
            u = sesion_global.usuario_actual or None
        except Exception:
            u = None
        r = pickup.cancelar(self._id_tx, usuario=u)
        if r.get("ok"):
            _mm(self, tr("online.cobro_title", default="COBRO ONLINE"),
                tr("online.pk_cancelado", default="Reserva cancelada y reembolsada."), "success")
            self.accept()
        else:
            _mm(self, tr("online.cobro_title", default="COBRO ONLINE"),
                tr("online.pk_cancel_err", default="No se pudo cancelar: {m}",
                   m=r.get("motivo", "")), "error")

    def _ped(self):
        from src.services.tpv import online_orders_service as OS

        return OS.obtener_pedido(self._pid) or {}

    def _refrescar_pickup(self):
        import json as _json

        from src.services.comercio_digital import transacciones
        tx = transacciones.obtener(self._id_tx) or {}
        meta = tx.get("metadata")
        if isinstance(meta, str):
            try:
                meta = _json.loads(meta)
            except Exception:
                meta = {}
        total = divisas.formatear(float((meta or {}).get("total_cotizado") or 0))
        self.lbl_info.setText(tr("online.pk_info",
                                 default="Reserva {pid} · Total {total} · Recogida en tienda",
                                 pid=str(self._id_tx)[:8], total=total))
        self.lbl_estado.setText(tr("online.pk_estado", default="Estado: {e}",
                                   e=tx.get("estado") or "—"))

    def _refrescar(self):
        if self._es_pickup:
            self._refrescar_pickup()
            return
        from src.services.tpv.pagos import pasarela_actual

        p = self._ped()
        total = divisas.formatear(float(p.get("total") or 0))
        self.lbl_info.setText(
            tr(
                "online.cobro_info",
                default="Pedido {pid} · Total {total} · Pasarela: {prov}",
                pid=str(self._pid)[:8],
                total=total,
                prov=getattr(pasarela_actual(), "nombre", "—"),
            )
        )
        ep = p.get("estado_pago") or tr("online.cobro_sin", default="sin iniciar")
        self.lbl_estado.setText(
            tr("online.cobro_estado", default="Estado del pago: {e}", e=ep)
        )
        enlace = p.get("enlace_pago") or ""
        self.inp_enlace.setText(enlace)
        self.b_open.setEnabled(bool(enlace))
        self.b_copy.setEnabled(bool(enlace))

    def _generar(self):
        from src.services.tpv import online_orders_service as OS
        from assets.estilo_global import mostrar_mensaje as _mm

        res = OS.crear_cobro(self._pid)
        if not res.get("ok"):
            _mm(
                self,
                tr("online.cobro_title", default="COBRO ONLINE"),
                res.get("mensaje")
                or tr("online.cobro_err", default="No se pudo iniciar el cobro."),
                "warning",
            )
        self._refrescar()

    def _abrir(self):
        enlace = self.inp_enlace.text().strip()
        if enlace:
            try:
                import webbrowser

                webbrowser.open(enlace)
            except Exception:
                pass

    def _copiar(self):
        QApplication.clipboard().setText(self.inp_enlace.text().strip())

    def _configurar(self):
        _PasarelaConfigDialog(parent=self).exec()
        self._refrescar()

    def _verificar(self):
        from src.services.tpv import online_orders_service as OS
        from assets.estilo_global import mostrar_mensaje as _mm

        estado = OS.verificar_pago(self._pid)
        if estado == "pagado":
            _mm(
                self,
                tr("online.cobro_title", default="COBRO ONLINE"),
                tr(
                    "online.cobro_pagado",
                    default="Pago confirmado. El pedido se ha marcado como PAGADO.",
                ),
                "info",
            )
            self.accept()
        else:
            _mm(
                self,
                tr("online.cobro_title", default="COBRO ONLINE"),
                tr(
                    "online.cobro_pend",
                    default="El pago aún no consta como completado (estado: {e}).",
                    e=estado,
                ),
                "warning",
            )
            self._refrescar()


# --- Canal Web extraído (Fase WEB-07) ---------------------------------------------------------
# `_CanalWebConfigDialog` se movió a `gui/canal_web_config.py` (módulo Canal Web) para eliminar el
# acoplamiento privado TPV<->Canal Web. El TPV ya NO configura la web: solo navega a Portal Web
# (`gui/portal_web_gui.PortalWebWindow`). La config del canal se abre desde el Catálogo (redirección
# "Web") y desde el asistente Canal Web. NO reintroducir configuración de Canal Web en el TPV.
# ----------------------------------------------------------------------------------------------


# --- Portal Web extraído (Fase WEB-08) ---------------------------------------------------------
# `_GestionPedidosOnlineDialog` (Centro de gestión de pedidos online / Canal Web) se movió a
# `gui/portal_web_home.py` como `PortalWebHome` (núcleo del Portal Web para empleados). El TPV ya
# NO contiene lógica del Portal Web: solo lo abre (router → PortalWebWindow). NO reintroducir aquí.
# ----------------------------------------------------------------------------------------------


class _GestionGranelDialog(QDialog):
    """Gestión de productos a granel (precio, estado, alta). Sólo gerente/admin."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("ges_granel.title"))
        self.setModal(True)
        self.setMinimumSize(900, 560)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("dlg_gestion_granel")
        self._drag_pos = None
        self._build_ui()
        self._cargar()

    # Arrastre de ventana frameless
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def _build_ui(self):
        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _cuerpo = QFrame()
        _cuerpo.setObjectName("cuerpo_gestion_granel")
        _cuerpo.setStyleSheet(
            f"QFrame#cuerpo_gestion_granel{{background:{_BG};border:2px solid {_CIAN};"
            f"border-radius:24px;}}"
        )
        _outer.addWidget(_cuerpo)
        root = QVBoxLayout(_cuerpo)
        root.setContentsMargins(16, 14, 16, 16)
        root.setSpacing(12)
        cab = QHBoxLayout()
        cab.addWidget(_lbl(tr("ges_granel.header"), bold=True, size=18, color=_CIAN))
        cab.addStretch()
        btn_cerrar_top = QPushButton("✕")
        btn_cerrar_top.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cerrar_top.setFixedSize(50, 44)
        btn_cerrar_top.setStyleSheet(
            f"QPushButton{{background:transparent;color:{_ROJO};border:2px solid {_ROJO};"
            f"border-radius:9px;font-weight:900;font-size:18px;}}"
            f"QPushButton:hover{{background:{_ROJO};color:#0D1117;}}")
        btn_cerrar_top.clicked.connect(self.accept)
        cab.addWidget(btn_cerrar_top)
        root.addLayout(cab)
        self.tabla = QTableWidget()
        self.tabla.setColumnCount(5)
        self.tabla.setHorizontalHeaderLabels(
            [
                tr("ges_granel.col_product"),
                tr("ges_granel.col_family", default="Familia"),
                tr("ges_granel.col_price"),
                tr("ges_granel.col_status"),
                tr("ges_granel.col_actions"),
            ]
        )
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(52)
        self.tabla.setStyleSheet(
            f"QTableWidget{{background:{_BG};color:{_TEXT};border:1px solid {_BORDE};"
            f"font-family:'{_FONT}';font-size:13px;gridline-color:{_BORDE};}}"
            f"QTableWidget::item{{padding:4px 6px;}}"
            f"QHeaderView::section{{background:{_BG2};color:{_TEXT2};border:none;"
            f"border-bottom:1px solid {_BORDE};padding:8px;font-weight:700;}}"
        )
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(1, 240)
        hh.resizeSection(2, 90)
        hh.resizeSection(3, 100)
        hh.resizeSection(4, 300)
        root.addWidget(self.tabla, 1)
        btn_nuevo = _btn(
            tr("ges_granel.new"),
            color_bg=_CIAN,
            color_fg="#0D1117",
            color_border=_CIAN,
            hover_bg="#FFF",
            h=44,
        )
        btn_nuevo.clicked.connect(self._nuevo)
        root.addWidget(btn_nuevo)

    def _cargar(self):
        from src.services.tpv import bulk_products_service as B
        from src.services.tpv import familias_granel as F

        productos = B.listar_todos()
        self.tabla.setRowCount(len(productos))
        for row, p in enumerate(productos):
            emoji = p.get("emoji", "🛒")
            self.tabla.setItem(
                row, 0, QTableWidgetItem(f"{emoji}  {p.get('nombre','—')}")
            )
            fam = F.normalizar(p.get("categoria"))
            texto_fam = F.etiqueta(fam)
            if F.tiene_subfamilias(fam):
                sub = F.normalizar_subfamilia(fam, p.get("subfamilia"))
                texto_fam = f"{texto_fam} · {F.etiqueta_subfamilia(fam, sub)}"
            self.tabla.setItem(row, 1, QTableWidgetItem(f"{F.emoji(fam)}  {texto_fam}"))
            it_precio = QTableWidgetItem(f"{float(p.get('precio_kg',0)):.2f}")
            it_precio.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(row, 2, it_precio)
            activo = bool(p.get("activo", 1))
            it_estado = QTableWidgetItem(
                tr("ges_granel.active") if activo else tr("ges_granel.inactive")
            )
            it_estado.setForeground(QColor(_VERDE if activo else _ROJO))
            it_estado.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(row, 3, it_estado)
            cont = QWidget()
            cont.setStyleSheet("background:transparent;")
            hl = QHBoxLayout(cont)
            hl.setContentsMargins(10, 6, 10, 6)
            hl.setSpacing(14)
            b_edit = QPushButton(tr("ges_granel.edit"))
            b_edit.setFixedHeight(34)
            b_edit.setStyleSheet(
                f"QPushButton{{background:{_BG2};color:{_CIAN};border:1px solid {_CIAN};"
                f"border-radius:6px;font-size:14px;font-weight:700;padding:4px 4px;}}"
                f"QPushButton:hover{{background:{_CIAN};color:#0D1117;}}"
            )
            b_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            b_edit.clicked.connect(lambda _=False, pr=p: self._editar(pr))
            b_tog = QPushButton(
                tr("ges_granel.deactivate") if activo else tr("ges_granel.activate")
            )
            b_tog.setFixedHeight(34)
            b_tog.setStyleSheet(
                f"QPushButton{{background:{_BG2};color:{_TEXT2};border:1px solid {_BORDE};"
                f"border-radius:6px;font-size:14px;font-weight:700;padding:4px 4px;}}"
                f"QPushButton:hover{{background:#30363D;color:{_TEXT};}}"
            )
            b_tog.setCursor(Qt.CursorShape.PointingHandCursor)
            b_tog.clicked.connect(lambda _=False, pr=p: self._toggle(pr))
            hl.addWidget(b_edit)
            hl.addWidget(b_tog)
            self.tabla.setCellWidget(row, 4, cont)

    def _nuevo(self):
        self._editar(None)

    def _editar(self, p: dict | None):
        if _EditarGranelDialog(p, self).exec() == QDialog.DialogCode.Accepted:
            self._cargar()

    def _toggle(self, p: dict):
        from src.services.tpv import bulk_products_service as B

        B.cambiar_estado(p["id"], not bool(p.get("activo", 1)))
        self._cargar()


class _EditarGranelDialog(QDialog):
    """Alta / edición de un producto a granel."""

    def __init__(self, p: dict | None, parent=None):
        super().__init__(parent)
        self._p = p
        self.setWindowTitle(
            tr("ed_granel.title_edit") if p else tr("ed_granel.title_new")
        )
        self.setModal(True)
        self.setFixedWidth(440)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("dlg_editar_granel")
        self._drag_pos = None
        self._build_ui()

    # Arrastre de ventana frameless
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def _build_ui(self):
        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _cuerpo = QFrame()
        _cuerpo.setObjectName("cuerpo_editar_granel")
        _cuerpo.setStyleSheet(
            f"QFrame#cuerpo_editar_granel{{background:{_BG};border:2px solid {_CIAN};"
            f"border-radius:22px;}}"
        )
        _outer.addWidget(_cuerpo)
        # Título de cabecera (ya no hay barra de Windows)
        root = QVBoxLayout(_cuerpo)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(10)
        _titulo = tr("ed_granel.header_edit") if self._p else tr("ed_granel.header_new")
        root.addWidget(_lbl(_titulo, bold=True, size=15, color=_CIAN))
        root.addSpacing(4)
        root.addWidget(_lbl(tr("ed_granel.name"), bold=True, size=12, color=_TEXT2))
        self.inp_nombre = QLineEdit(self._p.get("nombre", "") if self._p else "")
        self.inp_nombre.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:8px;font-size:14px;}}QLineEdit:focus{{border-color:{_CIAN};}}"
        )
        root.addWidget(self.inp_nombre)
        row = QHBoxLayout()
        col1 = QVBoxLayout()
        col1.addWidget(_lbl(tr("ed_granel.emoji"), bold=True, size=12, color=_TEXT2))
        self.inp_emoji = QLineEdit(self._p.get("emoji", "🛒") if self._p else "🛒")
        self.inp_emoji.setMaxLength(4)
        self.inp_emoji.setFixedWidth(80)
        self.inp_emoji.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:8px;font-size:18px;}}"
        )
        col1.addWidget(self.inp_emoji)
        row.addLayout(col1)
        col2 = QVBoxLayout()
        # El rótulo del precio se adapta: €/kg (peso) o €/Unidad (Panes/Bollería). Ver _on_familia_cambiada.
        self.lbl_precio_titulo = _lbl(tr("ed_granel.price"), bold=True, size=12, color=_TEXT2)
        col2.addWidget(self.lbl_precio_titulo)
        self.spin_precio = QDoubleSpinBox()
        self.spin_precio.setDecimals(3)
        self.spin_precio.setRange(0.0, 9999.0)
        self.spin_precio.setValue(
            float(self._p.get("precio_kg", 0)) if self._p else 0.0
        )
        self.spin_precio.setStyleSheet(
            f"QDoubleSpinBox{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:8px;font-size:14px;font-weight:900;}}"
            f"QDoubleSpinBox:focus{{border-color:{_CIAN};}}"
        )
        col2.addWidget(self.spin_precio)
        row.addLayout(col2)
        root.addLayout(row)
        # ── FAMILIA (obligatoria) + SUBFAMILIA (solo Panes/Bollería) ──────────────────────────────
        from src.services.tpv import familias_granel as F
        self._F = F

        def _estilo_combo(cmb, view_name):
            # Mismo diseño que el resto de desplegables de la app: popup en modo LISTA
            # (combobox-popup:0 → sin los botones-triángulo de subir/bajar), borde neón, items con
            # esquinas redondeadas, hover/selección turquesa y una altura de item algo mayor.
            cmb.setProperty("horario_cb", True)   # el filtro global de estilos ignora este combo
            # La scrollbar se estiliza a nivel de COMBO (QComboBox QAbstractItemView QScrollBar…), igual
            # que en el selector de idioma del login: así el border-radius del asa (extremos redondeados)
            # se aplica de forma fiable en el popup. `margin` vertical deja aire para que se vean las
            # puntas redondeadas del asa turquesa.
            cmb.setStyleSheet(
                f"QComboBox{{combobox-popup:0;background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                f"border-radius:8px;padding:6px 12px;font-size:14px;font-family:'{_FONT}';}}"
                f"QComboBox:hover,QComboBox:on{{border-color:{_CIAN};}}"
                f"QComboBox::drop-down{{border:none;width:26px;}}"
                f"QComboBox QAbstractItemView{{background:#0D1117;color:{_TEXT};border:2px solid {_CIAN};"
                f"border-radius:12px;outline:0px;}}"
                # Scrollbar estándar de la app (tokens.qss_scrollbar): el `margin:3px` va en el ASA
                # (no en la scrollbar) → así el border-radius se dibuja como extremos redondeados; si el
                # asa toca los bordes del groove, Qt la dibuja cuadrada.
                f"QComboBox QAbstractItemView QScrollBar:vertical{{background:transparent;width:16px;"
                f"margin:0;}}"
                f"QComboBox QAbstractItemView QScrollBar::handle:vertical{{background:{_CIAN};"
                f"min-height:36px;border-radius:5px;margin:3px;}}"
                f"QComboBox QAbstractItemView QScrollBar::handle:vertical:hover{{background:#7AFFF0;}}"
                f"QComboBox QAbstractItemView QScrollBar::add-line:vertical,"
                f"QComboBox QAbstractItemView QScrollBar::sub-line:vertical{{height:0;width:0;}}"
                f"QComboBox QAbstractItemView QScrollBar::add-page:vertical,"
                f"QComboBox QAbstractItemView QScrollBar::sub-page:vertical{{background:transparent;}}")
            v = cmb.view(); v.setObjectName(view_name)
            v.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            v.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            v.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            v.setStyleSheet(
                f"QListView#{view_name}{{background:#0D1117;color:{_TEXT};border:2px solid {_CIAN};"
                f"border-radius:12px;padding:6px;outline:0px;}}"
                f"QListView#{view_name}::item{{min-height:34px;padding:6px 12px;border-radius:8px;"
                f"margin:2px 2px;}}"
                f"QListView#{view_name}::item:hover,QListView#{view_name}::item:selected"
                f"{{background:{_CIAN};color:#0D1117;border-radius:8px;}}")

        root.addWidget(_lbl(tr("ed_granel.family", default="Familia del producto"), bold=True,
                            size=12, color=_TEXT2))
        self.cmb_cat = _ComboMaxPopup(max_items=6, item_h=52)
        self.cmb_cat.setMaxVisibleItems(6)
        for f in F.familias():
            self.cmb_cat.addItem(f"{f['emoji']}  {f['etiqueta']}", f["codigo"])
        _estilo_combo(self.cmb_cat, "cat_popup_view")
        root.addWidget(self.cmb_cat)

        self.lbl_sub = _lbl(tr("ed_granel.subfamily", default="Apartado"), bold=True, size=12,
                            color=_TEXT2)
        root.addWidget(self.lbl_sub)
        self.cmb_sub = _ComboMaxPopup(max_items=5, item_h=52)
        _estilo_combo(self.cmb_sub, "sub_popup_view")
        root.addWidget(self.cmb_sub)

        self.cmb_cat.currentIndexChanged.connect(self._on_familia_cambiada)
        # Preselección (edición) o primera familia (alta).
        fam_ini = F.normalizar(self._p.get("categoria")) if self._p else F.familias()[0]["codigo"]
        idx = self.cmb_cat.findData(fam_ini)
        self.cmb_cat.setCurrentIndex(idx if idx >= 0 else 0)
        self._on_familia_cambiada()
        if self._p:
            sub_ini = F.normalizar_subfamilia(fam_ini, self._p.get("subfamilia"))
            j = self.cmb_sub.findData(sub_ini)
            if j >= 0:
                self.cmb_sub.setCurrentIndex(j)
        root.addSpacing(6)
        botones = QHBoxLayout()
        b_cancel = _btn(
            tr("common.cancel"),
            color_fg=_ROJO,
            color_border=_ROJO,
            hover_bg=_ROJO,
            hover_fg="#FFF",
        )
        b_cancel.clicked.connect(self.reject)
        b_guardar = _btn(
            tr("common.save"),
            color_bg=_VERDE,
            color_fg="#0D1117",
            color_border=_VERDE,
            hover_bg="#FFF",
        )
        b_guardar.clicked.connect(self._guardar)
        botones.addWidget(b_cancel)
        botones.addWidget(b_guardar)
        root.addLayout(botones)

    def _on_familia_cambiada(self):
        """Adapta el formulario a la familia: rótulo de precio (€/kg vs €/Unidad) y combo de subfamilia."""
        fam = self.cmb_cat.currentData() or self.cmb_cat.currentText()
        # Rótulo del precio: Panes/Bollería se venden por unidad.
        if self._F.vendido_por_unidad(fam):
            self.lbl_precio_titulo.setText(tr("ed_granel.price_ud", default="Precio €/Unidad"))
        else:
            self.lbl_precio_titulo.setText(tr("ed_granel.price", default="Precio €/kg"))
        # Subfamilia (apartados) solo para familias que la tienen.
        subs = self._F.subfamilias(fam)
        self.cmb_sub.blockSignals(True)
        self.cmb_sub.clear()
        for s in subs:
            self.cmb_sub.addItem(s["etiqueta"], s["codigo"])
        self.cmb_sub.blockSignals(False)
        visible = bool(subs)
        self.lbl_sub.setVisible(visible)
        self.cmb_sub.setVisible(visible)

    def _guardar(self):
        from src.services.tpv import bulk_products_service as B

        familia = self.cmb_cat.currentData() or "OTROS"
        # La subfamilia solo aplica a familias con apartados (Panes/Bollería); se decide por taxonomía,
        # no por visibilidad de widget (robusto aunque el diálogo no esté mostrado).
        subfamilia = self.cmb_sub.currentData() if self._F.subfamilias(familia) else ""
        ok, msg = B.guardar_producto(
            nombre=self.inp_nombre.text().strip(),
            precio_kg=self.spin_precio.value(),
            emoji=self.inp_emoji.text().strip() or "🛒",
            categoria=familia,
            subfamilia=subfamilia or "",
            pid=self._p.get("id") if self._p else None,
        )
        if ok:
            self.accept()
        else:
            QMessageBox.warning(self, tr("ed_granel.err_title"), msg)


# ============================================================
# DEVOLUCIONES
# ============================================================


class _AutorizacionDialog(QDialog):
    """Pide credenciales de un GERENTE/ADMINISTRADOR para autorizar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.autorizador = None
        self.setWindowTitle(tr("autoriz.title"))
        self.setModal(True)
        self.setFixedWidth(380)
        self.setStyleSheet(f"QDialog{{background:{_BG};}}")
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(10)
        root.addWidget(_lbl(tr("autoriz.header"), bold=True, size=15, color=_CIAN))
        root.addWidget(_lbl(tr("autoriz.subtitle"), size=11, color=_TEXT2))
        root.addSpacing(6)
        root.addWidget(_lbl(tr("autoriz.user"), bold=True, size=11, color=_TEXT2))
        self.inp_user = QLineEdit()
        self.inp_user.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:8px;font-size:14px;}}QLineEdit:focus{{border-color:{_CIAN};}}"
        )
        root.addWidget(self.inp_user)
        root.addWidget(_lbl(tr("autoriz.pin"), bold=True, size=11, color=_TEXT2))
        self.inp_pin = QLineEdit()
        self.inp_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_pin.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:8px;font-size:14px;}}QLineEdit:focus{{border-color:{_CIAN};}}"
        )
        root.addWidget(self.inp_pin)
        root.addSpacing(8)
        bl = QHBoxLayout()
        b_cancel = _btn(
            tr("common.cancel"),
            color_fg=_ROJO,
            color_border=_ROJO,
            hover_bg=_ROJO,
            hover_fg="#FFF",
        )
        b_cancel.clicked.connect(self.reject)
        b_ok = _btn(
            tr("autoriz.authorize"),
            color_bg=_VERDE,
            color_fg="#0D1117",
            color_border=_VERDE,
            hover_bg="#FFF",
        )
        b_ok.clicked.connect(self._validar)
        bl.addWidget(b_cancel)
        bl.addWidget(b_ok)
        root.addLayout(bl)

    def _validar(self):
        from src.services.tpv import refund_service as R

        ok, res = R.verificar_autorizacion(
            self.inp_user.text().strip(), self.inp_pin.text()
        )
        if ok:
            self.autorizador = res
            self.accept()
        else:
            QMessageBox.warning(self, tr("autoriz.err_title"), res)


class _AutorizacionAdminDialog(QDialog):
    """Pide credenciales y autoriza SOLO si el perfil es ADMINISTRADOR o SUPERADMIN."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.autorizado = False
        self.autorizador = None
        self.setModal(True)
        self.setFixedWidth(400)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        body = QFrame()
        body.setObjectName("aabody")
        body.setStyleSheet(f"QFrame#aabody{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        outer.addWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(10)
        root.addWidget(_lbl("🔒  " + tr("tpv.pb_auth_title", default="AUTORIZACIÓN REQUERIDA"),
                            bold=True, size=16, color=_CIAN))
        root.addWidget(_lbl(tr("tpv.pb_auth_sub",
                               default="Credenciales de un administrador o superadministrador."),
                            size=11, color=_TEXT2))
        root.addWidget(_lbl(tr("autoriz.user", default="Usuario"), bold=True, size=11, color=_TEXT2))
        self.inp_user = QLineEdit()
        self.inp_user.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:8px;font-size:14px;}}QLineEdit:focus{{border-color:{_CIAN};}}")
        root.addWidget(self.inp_user)
        root.addWidget(_lbl(tr("autoriz.pin", default="Contraseña"), bold=True, size=11, color=_TEXT2))
        self.inp_pin = QLineEdit()
        self.inp_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_pin.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:8px;font-size:14px;}}QLineEdit:focus{{border-color:{_CIAN};}}")
        self.inp_pin.returnPressed.connect(self._validar)
        root.addWidget(self.inp_pin)
        root.addSpacing(6)
        bl = QHBoxLayout()
        b_cancel = _btn(tr("common.cancel", default="Cancelar"), color_fg=_ROJO, color_border=_ROJO,
                        hover_bg=_ROJO, hover_fg="#FFF")
        b_cancel.clicked.connect(self.reject)
        b_ok = _btn("✔  " + tr("autoriz.authorize", default="AUTORIZAR"), color_bg=_VERDE,
                    color_fg="#0D1117", color_border=_VERDE, hover_bg="#FFF")
        b_ok.clicked.connect(self._validar)
        bl.addWidget(b_cancel)
        bl.addWidget(b_ok)
        root.addLayout(bl)

    def _validar(self):
        from src.db.usuario import validar_login_empleado
        u = validar_login_empleado(self.inp_user.text().strip(), self.inp_pin.text())
        perfil = ((u or {}).get("perfil") or "").upper()
        if u and perfil in ("ADMINISTRADOR", "SUPERADMIN", "SUPER_ADMIN"):
            self.autorizado = True
            self.autorizador = u
            self.accept()
        else:
            QMessageBox.warning(self, tr("tpv.price_bags", default="Precio bolsas"),
                                tr("tpv.pb_denegado",
                                   default="Se requiere un administrador o superadministrador."))


class _DevolucionDialog(QDialog):
    """Flujo de devolución: ticket → plazo → autorización → ítems → reembolso."""

    def __init__(self, empleado: str = "—", id_caja: str = "—", parent=None):
        super().__init__(parent)
        self._empleado = empleado
        self._id_caja = id_caja
        self._eval = None
        self._autorizador = None
        self._checks = []
        self.setWindowTitle(tr("devol.title"))
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        # Pantalla completa con un único contorno (el del QDialog global). Sin
        # translucidez ni borde de tarjeta interno (sin doble contorno).
        self.setObjectName("dlg_devolucion")
        self.setStyleSheet(f"#dlg_devolucion {{ background: {_BG}; }}")
        try:
            self.setGeometry(QApplication.primaryScreen().availableGeometry())
        except Exception:
            self.setMinimumSize(760, 600)
        self._build_ui()

    def showEvent(self, e):
        super().showEvent(e)
        try:
            self.setGeometry(QApplication.primaryScreen().availableGeometry())
        except Exception:
            pass

    def _build_ui(self):
        _outer = QVBoxLayout(self)
        # Margen para no tapar el contorno neón del QDialog global.
        _outer.setContentsMargins(12, 12, 12, 12)
        _cuerpo = QFrame()
        _cuerpo.setObjectName("cuerpo_devolucion")
        _cuerpo.setStyleSheet(
            f"QFrame#cuerpo_devolucion{{background:{_BG};border:none;border-radius:22px;}}"
        )
        _outer.addWidget(_cuerpo)
        root = QVBoxLayout(_cuerpo)
        root.setContentsMargins(16, 14, 16, 16)
        root.setSpacing(12)
        _hd = QHBoxLayout()
        _hd.addWidget(_lbl(tr("devol.header"), bold=True, size=20, color=_CIAN))
        _hd.addStretch()
        _bx = QPushButton("✕")
        _bx.setCursor(Qt.CursorShape.PointingHandCursor)
        _bx.setFixedSize(50, 44)
        _bx.setStyleSheet(
            f"QPushButton{{background:transparent;color:{_ROJO};border:2px solid {_ROJO};"
            f"border-radius:9px;font-weight:900;font-size:18px;}}"
            f"QPushButton:hover{{background:{_ROJO};color:#0D1117;}}")
        _bx.clicked.connect(self.reject)
        _hd.addWidget(_bx)
        root.addLayout(_hd)
        busq = QHBoxLayout()
        busq.addWidget(_lbl(tr("devol.ticket_num"), bold=True, size=13, color=_TEXT2))
        self.inp_ticket = QLineEdit()
        self.inp_ticket.setPlaceholderText(tr("devol.ticket_placeholder"))
        self.inp_ticket.setValidator(QIntValidator(1, 99999999, self))
        self.inp_ticket.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:8px 12px;font-size:15px;}}QLineEdit:focus{{border-color:{_CIAN};}}"
        )
        self.inp_ticket.returnPressed.connect(self._buscar)
        busq.addWidget(self.inp_ticket, 1)
        b_buscar = _btn(
            tr("devol.search"),
            color_bg=_CIAN,
            color_fg="#0D1117",
            color_border=_CIAN,
            hover_bg="#FFF",
            h=40,
        )
        b_buscar.clicked.connect(self._buscar)
        busq.addWidget(b_buscar)
        root.addLayout(busq)
        self.lbl_estado = _lbl("", bold=True, size=13)
        self.lbl_estado.setWordWrap(True)
        self.lbl_estado.setStyleSheet(
            f"color:{_TEXT2};background:{_BG2};border:1px solid {_BORDE};"
            f"border-radius:10px;padding:10px;font-family:'{_FONT}';"
        )
        self.lbl_estado.hide()
        root.addWidget(self.lbl_estado)
        self.tabla = QTableWidget()
        self.tabla.setColumnCount(5)
        self.tabla.setHorizontalHeaderLabels(
            [
                tr("devol.col_return"),
                tr("devol.col_article"),
                tr("devol.col_sold"),
                tr("devol.col_price"),
                tr("devol.col_subtotal"),
            ]
        )
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setStyleSheet(_ss_tabla_neon())
        _RoundTableCorners(self.tabla)
        hh = self.tabla.horizontalHeader()
        for c in range(5):  # anchura equitativa para todas las columnas
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.tabla, 1)
        fila = QHBoxLayout()
        col_m = QVBoxLayout()
        col_m.addWidget(
            _lbl(tr("devol.reason_label"), bold=True, size=12, color=_TEXT2)
        )
        # _ScrollCombo(6): dimensiona el popup para mostrar los 6 motivos a la vez
        # (sin scrollbar → sin columna de barra que corte el contorno del popup).
        self.inp_motivo = _ScrollCombo(6)
        self.inp_motivo.setEditable(True)  # permite un motivo libre si se elige "Otro"
        self.inp_motivo.setFixedHeight(40)
        self.inp_motivo.lineEdit().setPlaceholderText(tr("devol.reason_placeholder"))
        for _m in [
            tr("devol.reason_defecto", default="Producto defectuoso / tara"),
            tr("devol.reason_talla", default="Talla o medida incorrecta"),
            tr("devol.reason_no_deseado", default="No deseado / cambio de opinión"),
            tr("devol.reason_equivocado", default="Producto equivocado"),
            tr("devol.reason_caducado", default="Producto caducado / mal estado"),
            tr("devol.reason_otro", default="Otro motivo"),
        ]:
            self.inp_motivo.addItem(_m)
        self.inp_motivo.setCurrentIndex(-1)
        self.inp_motivo.setStyleSheet(
            # combobox-popup:0 → popup de LISTA justo debajo del campo (sin él, Qt usa
            # un menú nativo que el filtro global reposicionaba desplazado a la derecha).
            f"QComboBox{{combobox-popup:0;background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:6px 10px;font-size:13px;font-family:'{_FONT}';}}"
            f"QComboBox:hover,QComboBox:on{{border-color:{_CIAN};}}"
            f"QComboBox::drop-down{{border:none;width:24px;}}"
            f"QComboBox QAbstractItemView{{background:#0D1117;color:{_TEXT};border:2px solid {_CIAN};"
            f"border-radius:8px;outline:none;padding:2px;"
            f"selection-background-color:{_CIAN};selection-color:#0D1117;}}"
            f"QComboBox QAbstractItemView::item{{min-height:30px;padding:2px 10px;}}"
            # (El estilo de la scrollbar del popup lo aplica el filtro global
            # _apply_combo_extras → _sm_combo_view, ya con margen para no cortar el borde.)
        )
        col_m.addWidget(self.inp_motivo)
        fila.addLayout(col_m, 2)
        col_r = QVBoxLayout()
        col_r.addWidget(
            _lbl(tr("devol.refund_method"), bold=True, size=12, color=_TEXT2)
        )
        self.cmb_reembolso = QComboBox()
        # El TEXTO mostrado se traduce, pero el VALOR lógico (userData) se mantiene
        # en español para no romper las comprobaciones de método de reembolso.
        self.cmb_reembolso.addItem(tr("devol.pay_cash"), "EFECTIVO")
        self.cmb_reembolso.addItem(tr("devol.pay_card"), "TARJETA")
        self.cmb_reembolso.addItem(tr("devol.pay_voucher"), "VALE TIENDA")
        self.cmb_reembolso.setStyleSheet(
            f"QComboBox{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:8px;font-size:13px;}}"
        )
        col_r.addWidget(self.cmb_reembolso)
        fila.addLayout(col_r, 1)
        root.addLayout(fila)
        bl = QHBoxLayout()
        self.btn_procesar = QPushButton(tr("devol.process"))
        self.btn_procesar.setFixedHeight(46)
        self.btn_procesar.setMinimumWidth(720); self.btn_procesar.setMaximumWidth(820)
        self.btn_procesar.setEnabled(False)
        self.btn_procesar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_procesar.setStyleSheet(
            f"QPushButton{{background:{_VERDE};color:#0D1117;border:2px solid {_VERDE};"
            f"border-radius:12px;font-family:'{_FONT}';font-weight:900;font-size:15px;"
            f"min-width:720px;max-width:820px;}}"  # gana al min-width del QSS global
            f"QPushButton:hover{{background:#FFF;}}"
            f"QPushButton:disabled{{background:#1C2128;color:#6E7681;border:2px solid #30363D;}}"
        )
        self.btn_procesar.clicked.connect(self._procesar)
        bl.addStretch()
        bl.addWidget(self.btn_procesar)
        bl.addStretch()
        root.addLayout(bl)

    def _buscar(self):
        from src.services.tpv import refund_validation_service as RV

        txt = self.inp_ticket.text().strip()
        if not txt:
            return
        self._eval = RV.evaluar_ticket(int(txt))
        self._autorizador = None
        self.lbl_estado.show()
        if not self._eval.get("existe"):
            self.lbl_estado.setText(
                "⚠  " + self._eval.get("mensaje", tr("devol.not_found"))
            )
            self.lbl_estado.setStyleSheet(
                f"color:{_ROJO};background:{_BG2};border:1px solid {_ROJO};"
                f"border-radius:10px;padding:10px;font-family:'{_FONT}';font-weight:700;"
            )
            self.tabla.setRowCount(0)
            self.btn_procesar.setEnabled(False)
            return
        venta = self._eval["venta"]
        if "tarjeta" in (venta.get("forma_pago") or "").lower():
            _idx = self.cmb_reembolso.findData("TARJETA")
            if _idx >= 0:
                self.cmb_reembolso.setCurrentIndex(_idx)
            self.cmb_reembolso.setEnabled(False)
        else:
            self.cmb_reembolso.setEnabled(True)
        if self._eval["dentro_plazo"]:
            self.lbl_estado.setText(
                tr(
                    "devol.status_ok",
                    id=venta["id"],
                    total=divisas.formatear(venta["total"]),
                    fp=venta["forma_pago"],
                    limite=self._eval["fecha_limite"],
                )
            )
            self.lbl_estado.setStyleSheet(
                f"color:{_VERDE};background:{_BG2};border:1px solid {_VERDE};"
                f"border-radius:10px;padding:10px;font-family:'{_FONT}';font-weight:700;"
            )
            self.btn_procesar.setEnabled(True)
        else:
            self._mostrar_alerta_caducado(venta)
        self._cargar_items(venta)

    def _mostrar_alerta_caducado(self, venta):
        self.lbl_estado.setText(
            tr(
                "devol.status_expired",
                msg=self._eval["mensaje"],
                id=venta["id"],
                total=divisas.formatear(venta["total"]),
                fecha=venta["fecha"],
                limite=self._eval["fecha_limite"],
            )
        )
        self.lbl_estado.setStyleSheet(
            f"color:{_ROJO};background:{_BG2};border:2px solid {_ROJO};"
            f"border-radius:10px;padding:12px;font-family:'{_FONT}';font-weight:900;"
        )
        self.btn_procesar.setEnabled(False)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr("devol.expired_box_title"))
        box.setText(tr("devol.expired_box_text"))
        box.setInformativeText(
            tr(
                "devol.expired_box_info",
                total=divisas.formatear(venta["total"]),
                fecha=venta["fecha"],
                limite=self._eval["fecha_limite"],
            )
        )
        box.addButton(tr("devol.btn_cancel"), QMessageBox.ButtonRole.RejectRole)
        btn_auth = box.addButton(
            tr("devol.btn_request_auth"), QMessageBox.ButtonRole.AcceptRole
        )
        box.exec()
        if box.clickedButton() == btn_auth:
            self._solicitar_autorizacion()

    def _solicitar_autorizacion(self):
        dlg = _AutorizacionDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.autorizador:
            self._autorizador = dlg.autorizador
            self.lbl_estado.setText(
                self.lbl_estado.text()
                + "\n"
                + tr("devol.authorized_by", nombre=self._autorizador)
            )
            self.lbl_estado.setStyleSheet(
                f"color:{_CIAN};background:{_BG2};border:2px solid {_CIAN};"
                f"border-radius:10px;padding:12px;font-family:'{_FONT}';font-weight:900;"
            )
            self.btn_procesar.setEnabled(True)

    def _cargar_items(self, venta):
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import QCheckBox

        from src.db import devoluciones_baneados as _ban

        items = venta.get("items", [])
        self.tabla.setRowCount(len(items))
        self._checks = []
        baneados = []
        for row, it in enumerate(items):
            cod = str(it.get("codigo_articulo") or it.get("codigo") or "")
            ban = _ban.esta_baneado(cod) if cod else None
            chk = QCheckBox()
            if ban:
                # Solo ESTE artículo queda excluido de la devolución; el resto del
                # ticket se puede devolver con normalidad.
                chk.setChecked(False)
                chk.setEnabled(False)
                baneados.append((str(it.get("nombre", "—")), ban.get("motivo") or ""))
            else:
                chk.setChecked(True)
            self._checks.append(chk)
            cont = QWidget()
            cont.setStyleSheet("background:transparent;")
            hl = QHBoxLayout(cont)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.addWidget(chk)
            hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setCellWidget(row, 0, cont)

            it_nom = QTableWidgetItem(
                ("🚫  " if ban else "") + str(it.get("nombre", "—"))
            )
            it_cant = QTableWidgetItem(str(it.get("cantidad", 0)))
            it_cant.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_pre = QTableWidgetItem(
                f"{divisas.formatear(float(it.get('precio_unitario',0)))}"
            )
            it_pre.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_sub = QTableWidgetItem(
                f"{divisas.formatear(float(it.get('subtotal',0)))}"
            )
            it_sub.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            if ban:
                # TACHADO en rojo en toda la fila (solo afecta a este artículo).
                fuente = QFont()
                fuente.setStrikeOut(True)
                for celda in (it_nom, it_cant, it_pre, it_sub):
                    celda.setForeground(QColor(_ROJO))
                    celda.setFont(fuente)
            self.tabla.setItem(row, 1, it_nom)
            self.tabla.setItem(row, 2, it_cant)
            self.tabla.setItem(row, 3, it_pre)
            self.tabla.setItem(row, 4, it_sub)

        if baneados:
            self._avisar_baneados(baneados)

    def _avisar_baneados(self, baneados):
        """Mensaje centrado: el ticket contiene artículos no devolubles (baneados)."""
        lineas = "\n".join(f"•  {nombre}: {motivo}" for nombre, motivo in baneados)
        cuerpo = (
            tr(
                "devol.ban_intro",
                default="Estos artículos quedan EXCLUIDOS de la devolución (aparecen tachados). "
                "El resto del ticket sí se puede devolver:",
            )
            + "\n\n"
            + lineas
        )
        titulo = tr("devol.ban_titulo", default="🚫 Artículos no devolubles")
        try:
            from assets.estilo_global import mostrar_mensaje as _mm

            _mm(self, titulo, cuerpo, "warning")
        except Exception:
            QMessageBox.warning(self, titulo, cuerpo)

    def _procesar(self):
        from src.services.tpv import refund_service as R

        if not self._eval or not self._eval.get("existe"):
            return
        venta = self._eval["venta"]
        motivo = self.inp_motivo.currentText().strip()
        if not motivo:
            QMessageBox.warning(
                self, tr("devol.reason_required_title"), tr("devol.reason_required_msg")
            )
            return
        items = venta.get("items", [])
        seleccion = [items[i] for i, chk in enumerate(self._checks) if chk.isChecked()]
        if not seleccion:
            QMessageBox.warning(
                self, tr("devol.no_selection_title"), tr("devol.no_selection_msg")
            )
            return
        forma_reembolso = (
            self.cmb_reembolso.currentData() or self.cmb_reembolso.currentText()
        )
        forma_original = venta.get("forma_pago", "")
        ok, msg = R.metodo_reembolso_permitido(forma_original, forma_reembolso)
        if not ok:
            QMessageBox.warning(self, tr("devol.method_not_allowed_title"), msg)
            return
        total = round(sum(float(it.get("subtotal", 0)) for it in seleccion), 2)
        if "tarjeta" in forma_reembolso.lower():
            from src.services.tpv.card_terminal_service import get_terminal

            res = get_terminal().devolver(total)
            if not res.ok:
                QMessageBox.critical(
                    self,
                    tr("devol.terminal_title"),
                    tr("devol.terminal_rejected", msg=res.mensaje),
                )
                return
        requirio = not self._eval["dentro_plazo"]
        ok, msg, dev_id = R.procesar_devolucion(
            venta_id=venta["id"],
            items_devolver=seleccion,
            forma_reembolso=forma_reembolso,
            forma_pago_original=forma_original,
            empleado=self._empleado,
            numero_caja=self._id_caja,
            motivo=motivo,
            autorizado_por=self._autorizador,
            requirio_autorizacion=requirio,
        )
        if ok:
            for it in seleccion:
                try:
                    stock_signals.stock_actualizado.emit(
                        str(it.get("codigo_articulo", ""))
                    )
                except Exception:
                    pass
            QMessageBox.information(self, tr("devol.refund_done_title"), msg)
            self.accept()
        else:
            QMessageBox.critical(self, tr("devol.error_title"), msg)


# ============================================================
# BLOQUE — SELECCIÓN / ALTA DE CLIENTE
# ============================================================


class _ClienteDialog(QDialog):
    """Selecciona un cliente existente, da de alta uno nuevo, o usa el cliente
    genérico (sin identificar). Devuelve el cliente elegido vía get_cliente()."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(1060, 600)
        self._cliente: dict | None = None
        self._build()
        # Ventana completa: ocupa (casi) toda la pantalla disponible al mostrarse.
        try:
            scr = self.screen().availableGeometry()
            self.resize(int(scr.width() * 0.92), int(scr.height() * 0.9))
            self.move(scr.center() - self.rect().center())
        except Exception:
            pass

    def _build(self):
        card = QFrame(self)
        card.setObjectName("cl")
        card.setStyleSheet(
            f"QFrame#cl{{background:{_BG};border:2px solid {_CIAN};border-radius:18px;}}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(card)
        ly = QVBoxLayout(card)
        ly.setContentsMargins(24, 20, 24, 20)
        ly.setSpacing(12)

        hdr = QHBoxLayout()
        hdr.addWidget(
            _lbl(
                "👤  " + tr("tpv.cli_title", default="CLIENTE DE LA VENTA"),
                bold=True,
                size=16,
                color=_CIAN,
            )
        )
        hdr.addStretch()
        bx = QPushButton("✕")
        bx.setFixedSize(34, 34)
        bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet(
            f"QPushButton{{background:{_BG2};color:{_TEXT2};border:1px solid {_BORDE};border-radius:8px;font-weight:900;}}QPushButton:hover{{border-color:{_ROJO};color:{_ROJO};}}"
        )
        bx.clicked.connect(self.reject)
        hdr.addWidget(bx)
        ly.addLayout(hdr)

        _iss = (
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:6px 10px;font-size:13px;font-family:'{_FONT}';}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}"
        )
        f = QHBoxLayout()
        f.setSpacing(8)
        self.inp_buscar = QLineEdit()
        self.inp_buscar.setStyleSheet(_iss)
        self.inp_buscar.setPlaceholderText(
            tr("tpv.cli_search_ph", default="Buscar por nombre, NIF, teléfono o email…")
        )
        self.inp_buscar.returnPressed.connect(self._buscar)
        b_b = _btn(
            tr("tpv.find_btn", default="BUSCAR"),
            color_bg=_CIAN,
            color_fg="#0D1117",
            color_border=_CIAN,
            hover_bg="#FFF",
            hover_fg="#0D1117",
            h=38,
        )
        b_b.clicked.connect(self._buscar)
        f.addWidget(self.inp_buscar, 1)
        f.addWidget(b_b)

        # Cuerpo en dos columnas: izquierda = clientes registrados (tabla),
        # derecha = alta/edición de cliente. Así la tabla nunca queda tapada.
        cuerpo = QHBoxLayout(); cuerpo.setSpacing(16)
        izq = QVBoxLayout(); izq.setSpacing(10)
        izq.addLayout(f)

        self.tabla = QTableWidget(0, 4)
        self.tabla.setHorizontalHeaderLabels(
            [
                tr("tpv.cli_c_name", default="Nombre"),
                tr("tpv.cli_c_nif", default="NIF"),
                tr("tpv.cli_c_phone", default="Teléfono"),
                tr("tpv.cli_c_email", default="Email"),
            ]
        )
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setStyleSheet(_ss_tabla_neon())
        _RoundTableCorners(self.tabla)
        self.tabla.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.tabla.doubleClicked.connect(self._usar_seleccionado)
        izq.addWidget(self.tabla, 1)
        cuerpo.addLayout(izq, 1)

        # Alta rápida de cliente nuevo (columna derecha)
        nb = QFrame()
        nb.setMaximumWidth(440)
        nb.setStyleSheet(
            f"QFrame{{background:{_BG2};border:1px solid {_BORDE};border-radius:10px;}}"
        )
        nl = QVBoxLayout(nb)
        nl.setContentsMargins(12, 10, 12, 10)
        nl.setSpacing(6)
        nl.addWidget(
            _lbl(
                tr("tpv.cli_new", default="NUEVO CLIENTE"),
                bold=True,
                size=12,
                color=_TEXT2,
            )
        )
        self._editando_id = None  # alta vs edición (se fija al pulsar EDITAR)
        # Fila 1: Nombre / Razón social + NIF/CIF
        r1 = QHBoxLayout(); r1.setSpacing(8)
        self.n_nombre = QLineEdit(); self.n_nombre.setStyleSheet(_iss)
        self.n_nombre.setPlaceholderText(tr("tpv.cli_name", default="Nombre / Razón social"))
        self.n_nif = QLineEdit(); self.n_nif.setStyleSheet(_iss)
        self.n_nif.setPlaceholderText(tr("tpv.cli_nif", default="NIF / CIF")); self.n_nif.setFixedWidth(160)
        r1.addWidget(self.n_nombre, 1); r1.addWidget(self.n_nif); nl.addLayout(r1)
        # Fila 2: Teléfono + Email
        r2 = QHBoxLayout(); r2.setSpacing(8)
        self.n_tel = QLineEdit(); self.n_tel.setStyleSheet(_iss)
        self.n_tel.setPlaceholderText(tr("tpv.cli_phone", default="Teléfono")); self.n_tel.setFixedWidth(160)
        self.n_email = QLineEdit(); self.n_email.setStyleSheet(_iss)
        self.n_email.setPlaceholderText(tr("tpv.cli_email", default="Email"))
        r2.addWidget(self.n_tel); r2.addWidget(self.n_email, 1); nl.addLayout(r2)
        # Fila 3: Domicilio
        self.n_dir = QLineEdit(); self.n_dir.setStyleSheet(_iss)
        self.n_dir.setPlaceholderText(tr("tpv.cli_addr", default="Domicilio"))
        nl.addWidget(self.n_dir)
        # Fila 4: C.P. + Población
        r3 = QHBoxLayout(); r3.setSpacing(8)
        self.n_cp = QLineEdit(); self.n_cp.setStyleSheet(_iss)
        self.n_cp.setPlaceholderText(tr("tpv.cli_cp", default="C.P.")); self.n_cp.setFixedWidth(100)
        self.n_pob = QLineEdit(); self.n_pob.setStyleSheet(_iss)
        self.n_pob.setPlaceholderText(tr("tpv.cli_city", default="Población"))
        r3.addWidget(self.n_cp); r3.addWidget(self.n_pob, 1); nl.addLayout(r3)
        # Fila 5: Provincia + País
        r4 = QHBoxLayout(); r4.setSpacing(8)
        self.n_prov = QLineEdit(); self.n_prov.setStyleSheet(_iss)
        self.n_prov.setPlaceholderText(tr("tpv.cli_prov", default="Provincia"))
        self.n_pais = QLineEdit(); self.n_pais.setStyleSheet(_iss)
        self.n_pais.setPlaceholderText(tr("tpv.cli_country", default="País")); self.n_pais.setFixedWidth(160)
        r4.addWidget(self.n_prov, 1); r4.addWidget(self.n_pais); nl.addLayout(r4)
        # Fila 6: botón crear/guardar
        self.b_alta = _btn(
            tr("tpv.cli_create", default="CREAR Y USAR"),
            color_bg=_VERDE, color_fg="#0D1117", color_border=_VERDE,
            hover_bg="#FFF", hover_fg="#0D1117", h=38,
        )
        self.b_alta.clicked.connect(self._crear_y_usar)
        r5 = QHBoxLayout(); r5.addStretch(); r5.addWidget(self.b_alta); nl.addLayout(r5)
        nl.addStretch()
        cuerpo.addWidget(nb, 0, Qt.AlignmentFlag.AlignTop)
        ly.addLayout(cuerpo, 1)

        # Acciones inferiores
        br = QHBoxLayout()
        b_gen = _btn(tr("tpv.cli_generic", default="CLIENTE GENÉRICO"), h=40)
        b_gen.clicked.connect(self._usar_generico)
        b_use = _btn(
            "✔  " + tr("tpv.cli_use", default="USAR SELECCIONADO"),
            color_bg=_CIAN,
            color_fg="#0D1117",
            color_border=_CIAN,
            hover_bg="#FFF",
            hover_fg="#0D1117",
            h=40,
        )
        b_use.clicked.connect(self._usar_seleccionado)
        b_edit = _btn("✏️ " + tr("tpv.cli_edit", default="EDITAR"), h=40)
        b_edit.clicked.connect(self._editar_seleccionado)
        br.addWidget(b_gen)
        br.addStretch()
        br.addWidget(b_edit)
        br.addStretch()
        br.addWidget(b_use)
        ly.addLayout(br)
        QTimer.singleShot(0, self.inp_buscar.setFocus)
        self._buscar()

    def _buscar(self):
        from src.db.clientes import buscar_clientes

        filas = buscar_clientes(self.inp_buscar.text().strip())
        self.tabla.setRowCount(len(filas))
        for r, c in enumerate(filas):
            for col, key in enumerate(("nombre", "nif", "telefono", "email")):
                it = QTableWidgetItem(str(c.get(key) or "—"))
                it.setData(Qt.ItemDataRole.UserRole, c)
                self.tabla.setItem(r, col, it)

    def _usar_seleccionado(self):
        row = self.tabla.currentRow()
        if row < 0:
            return
        it = self.tabla.item(row, 0)
        self._cliente = it.data(Qt.ItemDataRole.UserRole) if it else None
        self.accept()

    def _usar_generico(self):
        self._cliente = None
        self.accept()

    def _editar_seleccionado(self):
        """Carga el cliente registrado seleccionado en el formulario para editar/añadir datos."""
        row = self.tabla.currentRow()
        if row < 0:
            return
        it = self.tabla.item(row, 0)
        cli = it.data(Qt.ItemDataRole.UserRole) if it else None
        if not cli:
            return
        self._editando_id = cli.get("id")
        self.n_nombre.setText(cli.get("nombre") or "")
        self.n_nif.setText(cli.get("nif") or "")
        self.n_tel.setText(cli.get("telefono") or "")
        self.n_email.setText(cli.get("email") or "")
        self.n_dir.setText(cli.get("direccion") or "")
        self.n_cp.setText(cli.get("cp") or "")
        self.n_pob.setText(cli.get("poblacion") or "")
        self.n_prov.setText(cli.get("provincia") or "")
        self.n_pais.setText(cli.get("pais") or "")
        self.b_alta.setText(tr("tpv.cli_save", default="GUARDAR CAMBIOS"))
        self.n_nombre.setFocus()

    def _crear_y_usar(self):
        from src.db.clientes import actualizar_cliente, crear_cliente, obtener_cliente

        nombre = self.n_nombre.text().strip()
        if not nombre:
            self.n_nombre.setFocus()
            return
        campos = dict(
            nombre=nombre,
            nif=self.n_nif.text().strip() or None,
            telefono=self.n_tel.text().strip() or None,
            email=self.n_email.text().strip() or None,
            direccion=self.n_dir.text().strip() or None,
            cp=self.n_cp.text().strip() or None,
            poblacion=self.n_pob.text().strip() or None,
            provincia=self.n_prov.text().strip() or None,
            pais=self.n_pais.text().strip() or None,
        )
        if self._editando_id:  # modo edición
            actualizar_cliente(self._editando_id, **campos)
            self._cliente = obtener_cliente(self._editando_id)
            self.accept()
            return
        cid = crear_cliente(
            campos["nombre"], nif=campos["nif"], telefono=campos["telefono"],
            email=campos["email"], direccion=campos["direccion"], cp=campos["cp"],
            poblacion=campos["poblacion"], provincia=campos["provincia"], pais=campos["pais"])
        if cid:
            self._cliente = obtener_cliente(cid)
            self.accept()

    def get_cliente(self) -> dict | None:
        return self._cliente


# ============================================================
# BLOQUE — BÚSQUEDA / REIMPRESIÓN DE TICKETS
# ============================================================


class _ScrollCombo(QComboBox):
    """QComboBox que limita el popup a N filas y muestra scrollbar para el resto.
    Fijar la altura en showPopup() es determinista (no depende de que el estilo
    respete setMaxVisibleItems)."""

    def __init__(self, maxvis=5, parent=None):
        super().__init__(parent)
        self._maxvis = maxvis
        self.setMaxVisibleItems(maxvis)

    def showPopup(self):
        super().showPopup()
        view = self.view()
        n = self.count()
        visibles = min(n, self._maxvis)  # nunca más de maxvis filas a la vez
        row_h = view.sizeHintForRow(0)
        if row_h <= 0:
            row_h = 30
        alto = row_h * visibles + 2 * view.frameWidth() + 4
        popup = view.parentWidget() or view
        popup.setMaximumHeight(alto)
        popup.resize(popup.width(), alto)
        # Scrollbar solo si hay más opciones de las visibles.
        view.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if n > self._maxvis
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )


class _TriLineEdit(QLineEdit):
    """QLineEdit que pinta un triángulo cian en su extremo derecho (indicador de
    desplegable). Se pinta sobre el propio campo, así no queda tapado."""

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width() - 15
        cy = self.height() // 2
        p.setBrush(QColor(_CIAN))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(
            QPolygon(
                [QPoint(cx - 5, cy - 3), QPoint(cx + 5, cy - 3), QPoint(cx, cy + 4)]
            )
        )
        p.end()


class _FechaFilter(QWidget):
    """Filtro de fecha SIN QDateEdit. Evita el bug de Windows por el que un
    QAbstractSpinBox dentro de un diálogo frameless se vuelve ventana nativa con
    MINMAXINFO degenerado (maxtrack ancho 0) y entra en bucle de setGeometry →
    cuelgue. Aquí es un QLineEdit de solo lectura + calendario neón como overlay
    hijo de la ventana (posición determinista)."""

    def __init__(self, qdate, parent=None):
        super().__init__(parent)
        self._date = qdate
        self._popup = None
        self._backdrop = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._le = _TriLineEdit(qdate.toString("dd/MM/yyyy"))
        self._le.setReadOnly(True)
        self._le.setFixedHeight(34)
        # smKeepCursor: que el filtro global de estilo no le imponga el IBeam de
        # texto; este campo actúa como botón desplegable (cursor manita).
        self._le.setProperty("smKeepCursor", True)
        self._le.setCursor(Qt.CursorShape.PointingHandCursor)
        self._le.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:0 26px 0 10px;font-size:12px;font-family:'{_FONT}';}}"
            f"QLineEdit:hover{{border-color:{_CIAN};}}"
        )
        self._le.mousePressEvent = lambda _e: self._toggle()
        lay.addWidget(self._le)

    def date(self):
        return self._date

    def setDate(self, d):
        self._date = d
        self._le.setText(d.toString("dd/MM/yyyy"))

    def _toggle(self):
        if self._popup is not None:
            self._close()
            return
        from src.gui.ventas import _VentasCalendarWidget

        win = self.window()
        bd = QWidget(win)
        bd.setGeometry(0, 0, win.width(), win.height())
        bd.setStyleSheet("background: transparent;")
        bd.mousePressEvent = lambda _e: self._close()
        bd.show()
        bd.raise_()
        self._backdrop = bd

        fr = QFrame(win)
        fr.setStyleSheet(
            f"QFrame{{background:#11181D;border:2px solid {_CIAN};border-radius:12px;}}"
        )
        v = QVBoxLayout(fr)
        v.setContentsMargins(11, 11, 11, 11)
        v.setSpacing(0)
        cal = _VentasCalendarWidget(fr)
        cal.setSelectedDate(self._date)
        v.addWidget(cal)
        cal.clicked.connect(lambda qd: (self.setDate(qd), self._close()))
        fr.setFixedSize(cal.minimumWidth() + 22, cal.minimumHeight() + 22)
        tl = self.mapTo(win, QPoint(0, self.height()))
        x = max(6, min(tl.x(), win.width() - fr.width() - 6))
        y = tl.y()
        if y + fr.height() > win.height() - 4:
            y = self.mapTo(win, QPoint(0, 0)).y() - fr.height()
        fr.move(x, max(6, y))
        fr.show()
        fr.raise_()
        self._popup = fr

        def _retry(c=cal, n=8):
            try:
                if c._ensure_custom_nav():
                    return
            except Exception:
                pass
            if n > 0:
                QTimer.singleShot(30, lambda: _retry(c, n - 1))

        QTimer.singleShot(0, _retry)

    def _close(self):
        for a in ("_popup", "_backdrop"):
            w = getattr(self, a, None)
            if w is not None:
                try:
                    w.hide()
                    w.deleteLater()
                except RuntimeError:
                    pass
                setattr(self, a, None)


class _BuscarTicketDialog(QDialog):
    """Búsqueda, localización y reimpresión de tickets a pantalla completa.
    Filtros: nº ticket/código escaneado, artículo, rango de fechas (calendario)
    y horas, empleado, caja, forma de pago y rango de importes. Permite
    reimprimir (copia) o emitir TICKET REGALO (sin precios)."""

    _ISS = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        # NO translúcido: a pantalla completa no hace falta y, con QDateEdit dentro,
        # provoca que el campo se vuelva ventana nativa con MINMAXINFO degenerado
        # (Windows entra en bucle de setGeometry al recolocar hijos → cuelgue).
        # Fondo sólido = _BG, que coincide con el de la tarjeta → esquinas limpias.
        self.setObjectName("buscar_ticket_dlg")
        self.setStyleSheet(f"#buscar_ticket_dlg {{ background: {_BG}; }}")
        self._build()
        try:
            scr = QApplication.primaryScreen().availableGeometry()
            self.setGeometry(scr)
        except Exception:
            self.setMinimumSize(1100, 700)

    def _inp(self, ph="", w=None):
        e = QLineEdit()
        e.setFixedHeight(34)
        if w:
            e.setFixedWidth(w)
        e.setPlaceholderText(ph)
        e.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}"
        )
        return e

    def _combo(self, items, w=None, maxvis=8):
        cb = _ScrollCombo(maxvis)
        cb.setFixedHeight(34)
        if w:
            cb.setFixedWidth(w)
        cb.setStyleSheet(
            # combobox-popup:0 → popup en modo lista: respeta maxVisibleItems y
            # muestra scrollbar cuando hay más opciones.
            f"QComboBox{{combobox-popup:0;background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
            f"QComboBox:hover,QComboBox:on{{border-color:{_CIAN};}}"
            f"QComboBox::drop-down{{border:none;width:22px;}}"
            f"QComboBox QAbstractItemView{{background:#0D1117;color:{_TEXT};border:2px solid {_CIAN};"
            f"border-radius:8px;outline:none;padding:2px;"
            f"selection-background-color:{_CIAN};selection-color:#0D1117;}}"
            f"QComboBox QAbstractItemView::item{{min-height:28px;padding:2px 10px;}}"
            f"QComboBox QAbstractItemView QScrollBar:vertical{{background:#0D1117;width:10px;margin:3px;border-radius:5px;}}"
            f"QComboBox QAbstractItemView QScrollBar::handle:vertical{{background:{_CIAN};border-radius:5px;min-height:28px;}}"
            f"QComboBox QAbstractItemView QScrollBar::add-line:vertical,"
            f"QComboBox QAbstractItemView QScrollBar::sub-line:vertical{{height:0;}}"
        )
        for label, data in items:
            cb.addItem(label, data)
        return cb

    def _lbl_r(self, txt, w=84):
        l = _lbl(txt, bold=True, size=12, color=_TEXT2)
        l.setFixedWidth(w)
        l.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return l

    def _build(self):
        card = QFrame(self)
        card.setObjectName("bt")
        # Sin borde interno: el contorno neón ya lo aporta el chrome de la ventana
        # (un solo contorno externo, no dos concéntricos).
        card.setStyleSheet(
            f"QFrame#bt{{background:{_BG};border:none;border-radius:18px;}}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.addWidget(card)
        ly = QVBoxLayout(card)
        ly.setContentsMargins(28, 22, 28, 22)
        ly.setSpacing(12)

        hdr = QHBoxLayout()
        hdr.addWidget(
            _lbl(
                "🔎  " + tr("tpv.find_title", default="BUSCAR / REIMPRIMIR TICKET"),
                bold=True,
                size=17,
                color=_CIAN,
            )
        )
        hdr.addStretch()
        bx = QPushButton("✕")
        bx.setFixedSize(36, 36)
        bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet(
            f"QPushButton{{background:{_BG2};color:{_TEXT2};border:1px solid {_BORDE};border-radius:8px;font-weight:900;}}QPushButton:hover{{border-color:{_ROJO};color:{_ROJO};}}"
        )
        bx.clicked.connect(self.reject)
        hdr.addWidget(bx)
        ly.addLayout(hdr)
        ly.addWidget(_sep())

        from PyQt6.QtCore import QDate

        hoy = QDate.currentDate()

        # Fila 1: Nº ticket (escáner) + Artículo
        r1 = QHBoxLayout()
        r1.setSpacing(8)
        self.inp_ticket = self._inp(
            tr(
                "tpv.find_q_ph",
                default="Escanear QR / código de barras o nº de ticket…",
            )
        )
        self.inp_ticket.returnPressed.connect(self._buscar)
        self.inp_articulo = self._inp(
            tr("vta.ph_article", default="Código o nombre de artículo")
        )
        r1.addWidget(self._lbl_r(tr("vta.lbl_ticket", default="Nº Ticket")))
        r1.addWidget(self.inp_ticket, 1)
        r1.addSpacing(10)
        r1.addWidget(self._lbl_r(tr("vta.lbl_article", default="Artículo"), 70))
        r1.addWidget(self.inp_articulo, 1)
        ly.addLayout(r1)

        # Fila 2: Fechas (calendario) + Horas
        r2 = QHBoxLayout()
        r2.setSpacing(8)
        self.fecha_desde = _FechaFilter(hoy.addDays(-30))
        self.fecha_hasta = _FechaFilter(hoy)
        self.hora_desde = self._inp(
            tr("vta.ph_time_from", default="Hora desde (HH:MM)")
        )
        self.hora_hasta = self._inp(tr("vta.ph_time_to", default="Hora hasta (HH:MM)"))
        r2.addWidget(self._lbl_r(tr("tpv.find_date_from", default="Fecha inicio")))
        r2.addWidget(self.fecha_desde, 1)
        r2.addSpacing(8)
        r2.addWidget(self._lbl_r(tr("tpv.find_date_to", default="Fecha fin")))
        r2.addWidget(self.fecha_hasta, 1)
        r2.addSpacing(8)
        r2.addWidget(self._lbl_r(tr("vta.lbl_time_from", default="Hora desde")))
        r2.addWidget(self.hora_desde, 1)
        r2.addSpacing(8)
        r2.addWidget(self._lbl_r(tr("vta.lbl_time_to", default="Hora hasta")))
        r2.addWidget(self.hora_hasta, 1)
        ly.addLayout(r2)

        # Fila 3: Empleado + Caja + Forma de pago + Precios
        r3 = QHBoxLayout()
        r3.setSpacing(8)
        from src.db.ventas_busqueda import obtener_empleados

        emp_items = [(tr("vta.opt_all_m", default="Todos"), "")] + [
            (e, e) for e in obtener_empleados()
        ]
        self.cmb_emp = self._combo(emp_items, maxvis=2)  # máx 2 visibles + scrollbar
        self.cmb_caja = self._combo(
            [(tr("vta.opt_all_f", default="Todas"), "")]
            + [(str(i), str(i)) for i in range(1, 21)],
            w=120,
            maxvis=5,
        )  # máx 5 visibles + scrollbar; ancho para que "Todas" se vea
        self.cmb_pago = self._combo(
            [
                (tr("vta.opt_all_m", default="Todos"), ""),
                (tr("vta.pay_cash", default="efectivo"), "efectivo"),
                (tr("vta.pay_card", default="tarjeta"), "tarjeta"),
                ("mixto", "mixto"),
                (tr("vta.pay_coupon", default="cupón"), "cupón"),
            ],
            w=150,
            maxvis=4,
        )  # 4 visibles + scrollbar
        self.inp_pmin = self._inp(tr("vta.ph_price_min", default="Importe mínimo"), 120)
        self.inp_pmax = self._inp(tr("vta.ph_price_max", default="Importe máximo"), 120)
        r3.addWidget(self._lbl_r(tr("vta.lbl_employee", default="Empleado")))
        r3.addWidget(self.cmb_emp, 1)
        r3.addSpacing(8)
        r3.addWidget(self._lbl_r(tr("vta.lbl_register", default="Caja"), 48))
        r3.addWidget(self.cmb_caja)
        r3.addSpacing(8)
        r3.addWidget(self._lbl_r(tr("vta.lbl_payment", default="Forma de pago"), 100))
        r3.addWidget(self.cmb_pago)
        r3.addSpacing(8)
        r3.addWidget(self._lbl_r(tr("vta.lbl_price_min", default="Precio mín."), 84))
        r3.addWidget(self.inp_pmin)
        r3.addWidget(self._lbl_r(tr("vta.lbl_price_max", default="Precio máx."), 84))
        r3.addWidget(self.inp_pmax)
        ly.addLayout(r3)

        # Botonera
        bb = QHBoxLayout()
        bb.setSpacing(10)
        b_buscar = _btn(
            tr("tpv.find_btn", default="BUSCAR"),
            color_bg=_CIAN,
            color_fg="#0D1117",
            color_border=_CIAN,
            hover_bg="#FFF",
            hover_fg="#0D1117",
            h=38,
        )
        b_buscar.clicked.connect(self._buscar)
        b_limpiar = _btn(tr("vta.btn_clear", default="LIMPIAR"), h=38)
        b_limpiar.clicked.connect(self._limpiar)
        bb.addWidget(b_buscar)
        bb.addWidget(b_limpiar)
        bb.addStretch()
        ly.addLayout(bb)

        # Tabla (columnas como BUSCAR VENTAS + Cliente): esquinas redondeadas,
        # contorno neón y hover swap en cabeceras.
        self.tabla = QTableWidget(0, 7)
        self.tabla.setHorizontalHeaderLabels(
            [
                tr("vta.col_ticket", default="Ticket"),
                tr("vta.col_date", default="Fecha"),
                tr("vta.col_employee", default="Empleado"),
                tr("vta.col_register", default="Caja"),
                tr("vta.col_payment", default="Forma de pago"),
                tr("tpv.find_c_cli", default="Cliente"),
                tr("vta.col_total", default="Total"),
            ]
        )
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setStyleSheet(_ss_tabla_neon())
        self.tabla.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        _RoundTableCorners(self.tabla)
        self.tabla.doubleClicked.connect(lambda: self._emitir(regalo=False))
        ly.addWidget(self.tabla, 1)

        self.lbl_info = _lbl("", size=11, color=_TEXT2)
        br = QHBoxLayout()
        br.addWidget(self.lbl_info)
        br.addStretch()
        b_re = _btn(
            "🖨  " + tr("tpv.find_reprint", default="REIMPRIMIR"),
            color_bg=_CIAN,
            color_fg="#0D1117",
            color_border=_CIAN,
            hover_bg="#FFF",
            hover_fg="#0D1117",
            h=42,
        )
        b_re.clicked.connect(lambda: self._emitir(regalo=False))
        b_gift = _btn(
            "🎁  " + tr("vta.btn_gift", default="TICKET REGALO"),
            color_bg=_VERDE,
            color_fg="#0D1117",
            color_border=_VERDE,
            hover_bg="#FFF",
            hover_fg="#0D1117",
            h=42,
        )
        b_gift.clicked.connect(lambda: self._emitir(regalo=True))
        br.addWidget(b_re)
        br.addWidget(b_gift)
        ly.addLayout(br)
        QTimer.singleShot(0, self.inp_ticket.setFocus)
        self._buscar()

    def _limpiar(self):
        from PyQt6.QtCore import QDate

        hoy = QDate.currentDate()
        for w in (
            self.inp_ticket,
            self.inp_articulo,
            self.hora_desde,
            self.hora_hasta,
            self.inp_pmin,
            self.inp_pmax,
        ):
            w.clear()
        self.fecha_desde.setDate(hoy.addDays(-30))
        self.fecha_hasta.setDate(hoy)
        for cb in (self.cmb_emp, self.cmb_caja, self.cmb_pago):
            cb.setCurrentIndex(0)
        self._buscar()

    def _buscar(self):
        from src.db.ventas_busqueda import buscar_ventas

        idemp = None
        try:
            from src.db.empresa import empresa_actual_id

            idemp = empresa_actual_id()
        except Exception:
            pass
        filas = buscar_ventas(
            ticket=self.inp_ticket.text().strip() or None,
            articulo=self.inp_articulo.text().strip() or None,
            fecha_desde=self.fecha_desde.date().toString("yyyy-MM-dd"),
            fecha_hasta=self.fecha_hasta.date().toString("yyyy-MM-dd"),
            hora_desde=self.hora_desde.text().strip() or None,
            hora_hasta=self.hora_hasta.text().strip() or None,
            empleado=(self.cmb_emp.currentData() or "").strip() or None,
            caja=(self.cmb_caja.currentData() or "").strip() or None,
            forma_pago=(self.cmb_pago.currentData() or "").strip() or None,
            precio_min=self.inp_pmin.text().strip() or None,
            precio_max=self.inp_pmax.text().strip() or None,
            id_empresa=idemp,
        )
        self.tabla.setRowCount(len(filas))
        for r, v in enumerate(filas):
            fecha = v.get("fecha")
            fecha_txt = (
                fecha.strftime("%d/%m/%Y %H:%M")
                if hasattr(fecha, "strftime")
                else str(fecha or "")
            )
            vals = [
                f"T-{int(v.get('id') or 0):06d}",
                fecha_txt,
                str(v.get("empleado") or "—"),
                f"CAJA-{int(v.get('numero_caja') or 1):02d}",
                str(v.get("forma_pago") or "—"),
                str(v.get("cliente_nombre") or "—"),
                divisas.formatear(v.get("total", 0)),
            ]
            for c, t in enumerate(vals):
                it = QTableWidgetItem(t)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it.setData(Qt.ItemDataRole.UserRole, v.get("id"))
                if c == 6:
                    it.setForeground(QColor(_CIAN))
                self.tabla.setItem(r, c, it)
        self.lbl_info.setText(
            tr("tpv.find_count", default="{n} resultado(s)", n=len(filas))
        )

    def _emitir(self, regalo=False):
        row = self.tabla.currentRow()
        if row < 0:
            return
        it = self.tabla.item(row, 0)
        venta_id = it.data(Qt.ItemDataRole.UserRole) if it else None
        if venta_id is None:
            return
        try:
            from src.utils.ticket_data import reimprimir_ticket

            ruta = reimprimir_ticket(venta_id, regalo=regalo)
            if ruta:
                from src.utils import plataforma
                plataforma.abrir_archivo(ruta)
            else:
                from assets.estilo_global import mostrar_mensaje as _mm

                _mm(
                    self,
                    tr("tpv.find_err_t", default="Sin datos"),
                    tr("tpv.find_err", default="No se pudo recuperar la venta."),
                    "warning",
                )
        except Exception as e:
            logger.warning("Error emitiendo ticket: %s", e)


# ============================================================
# BLOQUE — VENTANA PRINCIPAL TPV
# ============================================================


class _EscanearTarjetaDialog(QDialog):
    """Ventana para escanear (o teclear) el código de barras de la tarjeta regalo que se vende."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.codigo = ""
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(440)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        body = QFrame()
        body.setObjectName("scanbody")
        body.setStyleSheet(f"QFrame#scanbody{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        outer.addWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(12)
        v.addWidget(_lbl("💳  " + tr("tpv.gift_scan_title", default="TARJETA REGALO"),
                         bold=True, size=17, color=_CIAN))
        v.addWidget(_lbl(tr("tpv.gift_scan_msg", default="Escanea el código de barras de la tarjeta"),
                         size=12, color=_TEXT2))
        self.inp = QLineEdit()
        self.inp.setPlaceholderText(tr("tpv.gift_scan_ph", default="Código de barras de la tarjeta…"))
        self.inp.setFixedHeight(54)
        self.inp.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};border-radius:10px;"
            f"padding:0 14px;font-size:18px;font-family:'{_FONT}';}}QLineEdit:focus{{border-color:{_CIAN};}}")
        self.inp.returnPressed.connect(self._aceptar)
        v.addWidget(self.inp)
        self.lbl_err = _lbl("", bold=True, size=12, color=_ROJO)
        v.addWidget(self.lbl_err)
        fila = QHBoxLayout()
        b_cancel = _btn(tr("common.cancel", default="Cancelar"), color_fg=_ROJO, color_border=_ROJO,
                        hover_bg=_ROJO, hover_fg="#FFF", h=46)
        b_cancel.clicked.connect(self.reject)
        b_ok = _btn("➡  " + tr("tpv.gift_scan_next", default="CONTINUAR"), color_bg=_VERDE,
                    color_fg="#0D1117", color_border=_VERDE, hover_bg="#FFF", h=46)
        b_ok.clicked.connect(self._aceptar)
        fila.addWidget(b_cancel)
        fila.addWidget(b_ok)
        v.addLayout(fila)
        QTimer.singleShot(0, self.inp.setFocus)

    def _aceptar(self):
        cod = self.inp.text().strip()
        if not cod:
            self.lbl_err.setText(tr("tpv.gift_scan_falta", default="Escanea o introduce el código de la tarjeta."))
            return
        self.codigo = cod
        self.accept()


class _ImporteTarjetaDialog(QDialog):
    """Ventana pequeña para introducir el importe a cargar en una tarjeta regalo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.importe = 0.0
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(400)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        body = QFrame()
        body.setObjectName("tarjbody")
        body.setStyleSheet(f"QFrame#tarjbody{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        outer.addWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(12)
        v.addWidget(_lbl("💳  " + tr("tpv.gift_card_amount_title", default="TARJETA REGALO"),
                         bold=True, size=17, color=_CIAN))
        v.addWidget(_lbl(tr("tpv.gift_card_amount_msg", default="Importe a cargar en la tarjeta"),
                         size=12, color=_TEXT2))
        self.spin = QDoubleSpinBox()
        self.spin.setDecimals(2)
        self.spin.setRange(0.0, 9999.0)
        self.spin.setSingleStep(5.0)
        self.spin.setSuffix("  " + divisas.simbolo())
        self.spin.setFixedHeight(54)
        self.spin.setStyleSheet(
            f"QDoubleSpinBox{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:10px;font-family:'{_FONT}';font-weight:900;font-size:24px;padding:4px 12px;}}"
            f"QDoubleSpinBox:focus{{border-color:{_CIAN};}}")
        v.addWidget(self.spin)
        fila = QHBoxLayout()
        b_cancel = _btn(tr("common.cancel", default="Cancelar"), color_fg=_ROJO, color_border=_ROJO,
                        hover_bg=_ROJO, hover_fg="#FFF", h=46)
        b_cancel.clicked.connect(self.reject)
        b_ok = _btn("✔  " + tr("tpv.gift_card_add", default="AÑADIR"), color_bg=_VERDE, color_fg="#0D1117",
                    color_border=_VERDE, hover_bg="#FFF", h=46)
        b_ok.clicked.connect(self._aceptar)
        fila.addWidget(b_cancel)
        fila.addWidget(b_ok)
        v.addLayout(fila)
        QTimer.singleShot(0, self.spin.setFocus)

    def _aceptar(self):
        val = round(float(self.spin.value()), 2)
        if val <= 0:
            return
        self.importe = val
        self.accept()


class _PreciosBolsasDialog(QDialog):
    """Ajuste de los precios de los extras del TPV (bolsas / sobres de regalo)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        try:
            self.setGeometry(QApplication.primaryScreen().availableGeometry())  # ventana completa
        except Exception:
            self.setMinimumSize(900, 600)
        from src.services.tpv import extras_precios
        self._svc = extras_precios
        self._items = extras_precios.listar()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        body = QFrame()
        body.setObjectName("pbbody")
        body.setStyleSheet(f"QFrame#pbbody{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        outer.addWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(26, 20, 26, 20)
        v.setSpacing(14)
        # Cabecera con X roja.
        hd = QHBoxLayout()
        hd.addWidget(_lbl("⚙  " + tr("tpv.precio_bolsas_title", default="PRECIO DE BOLSAS Y SOBRES"),
                          bold=True, size=18, color=_CIAN))
        hd.addStretch()
        bx = QPushButton("✕")
        bx.setFixedSize(40, 40)
        bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet(f"QPushButton{{background:transparent;color:{_ROJO};border:2px solid {_ROJO};"
                         f"border-radius:9px;font-weight:900;font-size:18px;}}"
                         f"QPushButton:hover{{background:{_ROJO};color:#0D1117;}}")
        bx.clicked.connect(self._cerrar)
        hd.addWidget(bx)
        v.addLayout(hd)
        # Tabla con contorno neón, esquinas redondeadas y hover swap en cabeceras.
        tbl = QTableWidget(len(self._items), 3)
        tbl.setHorizontalHeaderLabels([
            tr("tpv.pb_col_bolsa", default="BOLSA"),
            tr("tpv.pb_col_actual", default="PRECIO ACTUAL"),
            tr("tpv.pb_col_nuevo", default="NUEVO PRECIO")])
        # NUEVO PRECIO editable como CELDA (no un widget): así no hay resaltado al pasar el ratón; la
        # celda solo se selecciona/edita al hacer clic (doble clic o empezar a teclear).
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                            | QAbstractItemView.EditTrigger.SelectedClicked
                            | QAbstractItemView.EditTrigger.EditKeyPressed
                            | QAbstractItemView.EditTrigger.AnyKeyPressed)
        tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        tbl.verticalHeader().setVisible(False)
        tbl.verticalHeader().setDefaultSectionSize(56)
        for i in range(3):
            tbl.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        # Tabla SIN borde propio: el contorno neón + esquinas redondeadas los aporta un QFrame contenedor,
        # así las cabeceras no cortan el contorno.
        tbl.setStyleSheet(_ss_tabla_interior())
        tbl.setFrameShape(QFrame.Shape.NoFrame)
        tbl.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tbl.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tbl.setFixedHeight(len(self._items) * 56 + 52)   # todas las filas visibles, sin scroll
        self._tbl = tbl
        self._orig = {}
        for row, it in enumerate(self._items):
            cod = it["codigo"]
            it_nom = QTableWidgetItem(it["nombre"])
            it_nom.setFlags(it_nom.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tbl.setItem(row, 0, it_nom)
            it_act = QTableWidgetItem(divisas.formatear(it["precio"]))
            it_act.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_act.setFlags(it_act.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tbl.setItem(row, 1, it_act)
            # NUEVO PRECIO: editable, con el precio actual como valor inicial.
            it_nue = QTableWidgetItem(f"{float(it['precio']):.2f}")
            it_nue.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_nue.setForeground(QColor(_CIAN))
            it_nue.setData(Qt.ItemDataRole.UserRole, cod)
            tbl.setItem(row, 2, it_nue)
            self._orig[cod] = round(float(it["precio"]), 2)
        # Contenedor con borde neón turquesa + esquinas redondeadas (la tabla va dentro con margen).
        wrap = QFrame()
        wrap.setObjectName("pbwrap")
        wrap.setStyleSheet(f"QFrame#pbwrap{{background:{_BG};border:2px solid {_CIAN};border-radius:12px;}}")
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(6, 6, 6, 6)
        wl.addWidget(tbl)
        wrap.setSizePolicy(wrap.sizePolicy().horizontalPolicy(),
                           __import__("PyQt6.QtWidgets", fromlist=["QSizePolicy"]).QSizePolicy.Policy.Fixed)
        v.addWidget(wrap, alignment=Qt.AlignmentFlag.AlignTop)
        # Mensaje INLINE de confirmación de cambios sin guardar (evita QMessageBox, que con SOMA activo
        # puede congelar la app). Oculto por defecto; se muestra al cerrar con cambios pendientes.
        self._barra_conf = QFrame()
        self._barra_conf.setStyleSheet(f"QFrame{{background:{_BG2};border:2px solid {_AMBAR};border-radius:12px;}}")
        bc = QHBoxLayout(self._barra_conf)
        bc.setContentsMargins(16, 10, 16, 10)
        bc.addWidget(_lbl("⚠  " + tr("tpv.pb_conf_msg",
                                     default="Has modificado precios. ¿Quieres guardar los cambios?"),
                          bold=True, size=13, color=_AMBAR))
        bc.addStretch()
        b_desc = _btn(tr("tpv.pb_no", default="DESCARTAR"), color_fg=_ROJO, color_border=_ROJO,
                      hover_bg=_ROJO, hover_fg="#FFF", h=40)
        b_desc.clicked.connect(self.reject)
        b_guar = _btn("💾  " + tr("tpv.pb_si", default="GUARDAR"), color_bg=_VERDE, color_fg="#0D1117",
                      color_border=_VERDE, hover_bg="#FFF", h=40)
        b_guar.clicked.connect(self._guardar)
        bc.addWidget(b_desc)
        bc.addWidget(b_guar)
        self._barra_conf.setVisible(False)
        v.addWidget(self._barra_conf)
        # Aviso inline de error (en vez de QMessageBox).
        self._lbl_error = _lbl("", bold=True, size=12, color=_ROJO)
        v.addWidget(self._lbl_error)
        v.addStretch()
        # Botón guardar.
        fila = QHBoxLayout()
        fila.addStretch()
        b_save = _btn("💾  " + tr("tpv.pb_guardar", default="GUARDAR CAMBIOS"), color_bg=_VERDE,
                      color_fg="#0D1117", color_border=_VERDE, hover_bg="#FFF", h=48)
        b_save.clicked.connect(self._guardar)
        fila.addWidget(b_save)
        v.addLayout(fila)

    def showEvent(self, e):
        super().showEvent(e)
        try:
            self.setGeometry(QApplication.primaryScreen().availableGeometry())
        except Exception:
            pass

    def _nuevos_precios(self):
        """Lee la columna NUEVO PRECIO: {codigo: precio}. Ignora celdas con texto inválido."""
        out = {}
        for row in range(self._tbl.rowCount()):
            it = self._tbl.item(row, 2)
            if not it:
                continue
            cod = it.data(Qt.ItemDataRole.UserRole)
            try:
                val = round(float(it.text().strip().replace(",", ".").replace("€", "").strip()), 2)
            except (TypeError, ValueError):
                continue
            if cod is not None and val >= 0:
                out[cod] = val
        return out

    def _dirty(self):
        nuevos = self._nuevos_precios()
        return any(nuevos.get(cod) is not None and nuevos[cod] != orig
                   for cod, orig in self._orig.items())

    def _cambios(self):
        nuevos = self._nuevos_precios()
        return {cod: nuevos[cod] for cod, orig in self._orig.items()
                if nuevos.get(cod) is not None and nuevos[cod] != orig}

    def _guardar(self):
        cambios = self._cambios()
        if not cambios:
            self.accept()
            return
        ok, msg = self._svc.guardar(cambios)
        if ok:
            self.accept()
        else:
            self._lbl_error.setText("⚠  " + str(msg))   # inline, sin QMessageBox

    def _cerrar(self):
        # Si hay cambios sin guardar, muestra la confirmación INLINE (no un QMessageBox: con SOMA activo
        # los modales del sistema pueden congelar la app). Si no hay cambios, cierra directamente.
        if self._dirty():
            self._barra_conf.setVisible(True)
        else:
            self.reject()


class _PinEmpleadoDialog(QDialog):
    """COMPRA PERSONAL: pide el PIN (4 dígitos) del empleado y valida su identidad. Regla anti-fraude:
    el empleado NO puede ser el cajero que opera esta caja (no puede descontarse en su propia caja).
    Feedback INLINE (sin QMessageBox: SOMA activo en el proceso principal)."""

    def __init__(self, tpv, parent=None):
        super().__init__(parent or tpv)
        self._tpv = tpv
        self.empleado = None
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(430)
        main = QVBoxLayout(self); main.setContentsMargins(0, 0, 0, 0)
        cont = QFrame()
        cont.setStyleSheet(f"QFrame{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        main.addWidget(cont)
        ly = QVBoxLayout(cont); ly.setContentsMargins(24, 20, 24, 20); ly.setSpacing(10)
        ly.addWidget(_lbl(tr("tpv.staff_purchase", default="Compra personal"), bold=True, size=16,
                          color=_CIAN))
        sub = _lbl(tr("tpv.staff_pin_sub",
                      default="Introduce el PIN de empleado para aplicar su descuento a toda la compra."),
                   size=11, color=_TEXT2)
        sub.setWordWrap(True)
        ly.addWidget(sub)
        self.inp_pin = QLineEdit()
        self.inp_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_pin.setMaxLength(4)
        from PyQt6.QtGui import QIntValidator
        self.inp_pin.setValidator(QIntValidator(0, 9999, self))
        self.inp_pin.setPlaceholderText(tr("tpv.staff_pin_ph", default="PIN (4 dígitos)"))
        self.inp_pin.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};border-radius:8px;"
            f"padding:10px;font-size:16px;}}QLineEdit:focus{{border-color:{_CIAN};}}")
        self.inp_pin.returnPressed.connect(self._validar)
        ly.addWidget(self.inp_pin)
        self.lbl_err = _lbl("", size=11, color=_ROJO); self.lbl_err.setWordWrap(True)
        ly.addWidget(self.lbl_err)
        bl = QHBoxLayout()
        b_cancel = _btn(tr("common.cancel", default="Cancelar"), color_fg=_ROJO, color_border=_ROJO,
                        hover_bg=_ROJO, hover_fg="#FFF")
        b_cancel.clicked.connect(self.reject)
        b_ok = _btn(tr("tpv.apply", default="Aplicar"), color_bg=_VERDE, color_fg="#0D1117",
                    color_border=_VERDE, hover_bg="#FFF", hover_fg="#0D1117")
        b_ok.clicked.connect(self._validar)
        bl.addWidget(b_cancel); bl.addWidget(b_ok)
        ly.addLayout(bl)

    def _validar(self):
        pin = (self.inp_pin.text() or "").strip()
        if len(pin) != 4:
            self.lbl_err.setText(tr("tpv.staff_pin_len", default="El PIN debe tener 4 dígitos."))
            return
        try:
            from src.db.usuario import validar_pin_fichaje
            emp = validar_pin_fichaje(pin)
        except Exception:
            emp = None
        if not emp:
            _msg = tr("tpv.staff_pin_bad", default="PIN no válido.")
            self.lbl_err.setText(_msg)
            from assets.estilo_global import mostrar_mensaje as _mm
            _mm(self, tr("cfg.pin_wrong_title", default="PIN incorrecto"), _msg, "error")
            return
        if self._es_operador_actual(emp):
            self.lbl_err.setText(tr("tpv.staff_own_register",
                                    default="No puedes aplicar tu propio descuento en tu propia caja."))
            return
        self.empleado = emp
        self.accept()

    def _es_operador_actual(self, emp):
        op = getattr(self._tpv, "usuario", None) or {}
        if op.get("id") is not None and emp.get("id") is not None:
            return str(op.get("id")) == str(emp.get("id"))
        a = str(op.get("nombre") or op.get("usuario") or "").strip().lower()
        b = str(emp.get("nombre") or "").strip().lower()
        return bool(a) and a == b

    def showEvent(self, e):
        super().showEvent(e)
        self.inp_pin.setFocus()


class _AplicarDescuentoDialog(QDialog):
    """Aplica uno de los descuentos disponibles (10/15/20/25/30/50 %) al ÚLTIMO artículo escaneado de la
    compra en curso. Muestra a qué artículo se aplicará; si el carrito está vacío, lo indica."""

    OPCIONES = (10, 15, 20, 25, 30, 50)

    def __init__(self, tpv, parent=None):
        super().__init__(parent or tpv)
        self._tpv = tpv
        self.pct = None
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(600)
        main = QVBoxLayout(self); main.setContentsMargins(0, 0, 0, 0)
        cont = QFrame()
        cont.setStyleSheet(f"QFrame{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        main.addWidget(cont)
        ly = QVBoxLayout(cont); ly.setContentsMargins(28, 22, 28, 26); ly.setSpacing(14)
        cab = QHBoxLayout()
        cab.addWidget(_lbl(tr("tpv.apply_discount", default="Aplicar descuento"), bold=True, size=16,
                           color=_CIAN))
        cab.addStretch()
        bx = QPushButton("✕"); bx.setFixedSize(34, 34); bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet(f"QPushButton{{background:{_BG2};color:{_TEXT2};border:1px solid {_BORDE};"
                         f"border-radius:8px;font-weight:900;}}"
                         f"QPushButton:hover{{border-color:{_ROJO};color:{_ROJO};}}")
        bx.clicked.connect(self.reject)
        cab.addWidget(bx)
        ly.addLayout(cab)
        lineas = getattr(tpv, "_lineas", None) or []
        if not lineas:
            msg = _lbl(tr("tpv.disc_empty",
                          default="El carrito está vacío. Escanea un artículo antes de aplicar un descuento."),
                       size=12, color=_TEXT2)
            msg.setWordWrap(True)
            ly.addWidget(msg)
            return
        ult = lineas[-1]
        # Texto en Segoe UI Bold, +2pt (bold=True, size 14).
        info = _lbl(tr("tpv.disc_target", default="Se aplicará al último artículo: {n}",
                       n=str(ult.get("nombre") or ult.get("codigo") or "—")),
                    bold=True, size=14, color=_TEXT)
        info.setWordWrap(True)
        ly.addWidget(info)
        grid = QGridLayout(); grid.setSpacing(12)
        for c in range(3):
            grid.setColumnStretch(c, 1)
        for i, p in enumerate(self.OPCIONES):
            b = _btn(f"{p}%", color_fg=_CIAN, color_border=_CIAN, hover_bg=_CIAN, h=54)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)  # llena la celda (no solapa)
            b.clicked.connect(lambda _=False, pp=p: self._elegir(pp))
            grid.addWidget(b, i // 3, i % 3)
        ly.addLayout(grid)

    def _elegir(self, p):
        self.pct = p
        self.accept()


class _EditarDescuentoPersonalDialog(QDialog):
    """Define/edita el % de descuento de personal de la empresa (persistente). Solo admin/superadmin."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(430)
        try:
            from src.db.descuentos import obtener_descuento_personal
            actual = obtener_descuento_personal()
        except Exception:
            actual = 10.0
        main = QVBoxLayout(self); main.setContentsMargins(0, 0, 0, 0)
        cont = QFrame()
        cont.setStyleSheet(f"QFrame{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        main.addWidget(cont)
        ly = QVBoxLayout(cont); ly.setContentsMargins(24, 20, 24, 20); ly.setSpacing(10)
        ly.addWidget(_lbl(tr("tpv.edit_staff_discount", default="Editar % descuento personal"),
                          bold=True, size=16, color=_CIAN))
        ly.addWidget(_lbl(tr("tpv.edit_staff_sub",
                             default="Porcentaje de descuento que se aplica en la Compra personal (0–100)."),
                          size=11, color=_TEXT2))
        self.inp = QLineEdit(f"{float(actual):.2f}".rstrip("0").rstrip("."))
        self.inp.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};border-radius:8px;"
            f"padding:10px;font-size:16px;}}QLineEdit:focus{{border-color:{_CIAN};}}")
        ly.addWidget(self.inp)
        self.lbl_err = _lbl("", size=11, color=_ROJO); self.lbl_err.setWordWrap(True)
        ly.addWidget(self.lbl_err)
        bl = QHBoxLayout()
        b_cancel = _btn(tr("common.cancel", default="Cancelar"), color_fg=_ROJO, color_border=_ROJO,
                        hover_bg=_ROJO, hover_fg="#FFF")
        b_cancel.clicked.connect(self.reject)
        b_ok = _btn(tr("common.save", default="Guardar"), color_bg=_VERDE, color_fg="#0D1117",
                    color_border=_VERDE, hover_bg="#FFF", hover_fg="#0D1117")
        b_ok.clicked.connect(self._guardar)
        bl.addWidget(b_cancel); bl.addWidget(b_ok)
        ly.addLayout(bl)

    def _guardar(self):
        try:
            from src.db.descuentos import guardar_descuento_personal
            ok = guardar_descuento_personal(self.inp.text().strip())
        except Exception:
            ok = False
        if ok:
            self.accept()
        else:
            self.lbl_err.setText(tr("tpv.edit_staff_err",
                                    default="Introduce un porcentaje válido entre 0 y 100."))


class _AccionesAvanzadasDialog(QDialog):
    """Ventana emergente que agrupa las ACCIONES AVANZADAS del TPV (Precio bolsas, Devolución, Tickets,
    Venta online, Mostrar stock, Movimiento efectivo, Cambio cajero, Factura) para descargar el panel
    principal. Cada botón conserva EXACTAMENTE la misma lógica, flujo y diseño existentes: reutiliza
    `TPVWindow._btn_accion_card` y los mismos manejadores; solo cambia que ahora se lanzan desde aquí.
    La acción elegida se ejecuta tras cerrar esta ventana (evita anidar modales durante el cierre)."""

    def __init__(self, tpv, parent=None):
        super().__init__(parent or tpv)
        self._tpv = tpv
        self.accion_elegida = None
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(660)

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        cont = QFrame()
        cont.setStyleSheet(f"QFrame{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        main.addWidget(cont)
        ly = QVBoxLayout(cont)
        ly.setContentsMargins(20, 16, 20, 20)
        ly.setSpacing(12)

        cab = QHBoxLayout()
        cab.addWidget(_lbl(tr("tpv.adv_actions", default="Acciones avanzadas"), bold=True, size=16,
                           color=_CIAN))
        cab.addStretch()
        bx = QPushButton("✕"); bx.setFixedSize(34, 34); bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet(f"QPushButton{{background:{_BG2};color:{_TEXT2};border:1px solid {_BORDE};"
                         f"border-radius:8px;font-weight:900;}}"
                         f"QPushButton:hover{{border-color:{_ROJO};color:{_ROJO};}}")
        bx.clicked.connect(self.reject)
        cab.addWidget(bx)
        ly.addLayout(cab)

        grid = QGridLayout(); grid.setSpacing(8)
        for c in range(3):
            grid.setColumnStretch(c, 1)
        # Segmentación por edición: en Bakery el TPV se simplifica → sin Devolución ni Venta almacén.
        try:
            from src.services import verticales as _V
            _ver_devol = _V.visible("tpv.devolucion")
            _ver_valm = _V.visible("tpv.venta_almacen")
        except Exception:
            _ver_devol = _ver_valm = True
        # (icono, texto, manejador ORIGINAL del TPV). "Precio bolsas" con el icono del dólar.
        acciones = [
            ("👤", tr("tpv.staff_purchase", default="Compra personal"), tpv._compra_personal),
            ("🏷", tr("tpv.apply_discount", default="Aplicar descuento"), tpv._aplicar_descuento_ultimo),
            ("💲", tr("tpv.price_bags", default="Precio bolsas"), tpv._abrir_precio_bolsas),
        ]
        if _ver_devol:
            acciones.append(("↩", tr("tpv.refund", default="Devolución"), tpv._abrir_devolucion))
        acciones.append(("🔎", tr("tpv.tickets", default="Tickets"), tpv._abrir_buscar_tickets))
        if _ver_valm:
            acciones.append(("🌐", tr("tpv.acc_venta_almacen", default="Venta almacén"),
                             tpv._abrir_gestion_pedidos_online))
        acciones += [
            ("📦", tr("tpv.show_stock", default="Mostrar stock"), tpv._abrir_mostrar_stock),
            ("💶", tr("tpv.cash_move", default="Transferir efectivo"), tpv._abrir_movimiento_efectivo),
            ("🔁", tr("tpv.cashier_change", default="Cambio cajero"), tpv._abrir_cambio_cajero),
            ("🧾", tr("tpv.invoice", default="Factura"), tpv._abrir_factura),
        ]
        # Editar el % de descuento de personal: SOLO admin/superadmin.
        perfil = ((getattr(tpv, "usuario", None) or {}).get("perfil") or "").upper()
        if perfil in ("ADMINISTRADOR", "SUPERADMIN", "SUPER_ADMIN"):
            acciones.append(("✏", tr("tpv.edit_staff_discount", default="Editar % descuento personal"),
                             tpv._editar_descuento_personal))
        for i, (icono, txt, fn) in enumerate(acciones):
            btn, _ = tpv._btn_accion_card(icono, txt, _CIAN, lambda _=False, f=fn: self._lanzar(f))
            btn.setMinimumHeight(72)
            grid.addWidget(btn, i // 3, i % 3)
        ly.addLayout(grid)

    def _lanzar(self, fn):
        self.accion_elegida = fn
        self.accept()

    def showEvent(self, e):
        super().showEvent(e)
        try:
            pg = self._tpv.frameGeometry()
            self.move(pg.center().x() - self.width() // 2, pg.center().y() - self.height() // 2)
        except Exception:
            pass


# Emojis de comida y bebida para representar productos en el TPV táctil (selector al añadir/editar).
# Conjunto AMPLIO (hasta Unicode 12, soportado por Windows 10 22H2); solo se omiten los U13/U14 que
# más a menudo se ven como cuadrados en blanco.
_EMOJIS_COMIDA = [
    # Panadería / bollería / pan
    "🥐", "🍞", "🥖", "🥨", "🥯", "🥞", "🧇", "🧀",
    # Dulce
    "🍩", "🧁", "🍰", "🎂", "🍪", "🥧", "🍫", "🍬", "🍭", "🍮", "🍯", "🍦", "🍧", "🍨",
    # Salado / comidas
    "🥪", "🥙", "🌮", "🌯", "🧆", "🥗", "🍕", "🍔", "🌭", "🍟", "🥚", "🍳", "🥘", "🍲", "🥣",
    "🍿", "🧈", "🧂", "🥫", "🍖", "🍗", "🥩", "🥓",
    # Asiática / arroz / fideos
    "🍱", "🍘", "🍙", "🍚", "🍛", "🍜", "🍝", "🍠", "🍢", "🍣", "🍤", "🍥", "🥮", "🍡", "🥟", "🥠", "🥡",
    # Fruta y verdura
    "🍎", "🍏", "🍊", "🍋", "🍌", "🍉", "🍇", "🍓", "🍒", "🍑", "🥭", "🍍", "🥥", "🥝", "🍅", "🍆",
    "🥑", "🥔", "🥕", "🌽", "🌶", "🥒", "🥬", "🥦", "🧄", "🧅", "🍄", "🥜", "🌰",
    # Bebidas
    "☕", "🍵", "🧃", "🥤", "🍶", "🍾", "🍷", "🍸", "🍹", "🍺", "🍻", "🥂", "🥃", "🍼", "🥛", "💧",
]


def _nombre_boton_producto(nombre: str) -> str:
    """Nombre para el botón de la rejilla: quita el conector 'de'/'del' y capitaliza cada palabra.
    Ej.: 'Bocadillo de atún' → 'Bocadillo Atún'; 'Bocadillo de tortilla de patata' → 'Bocadillo Tortilla Patata'."""
    import re
    s = re.sub(r"\b(?:de|del)\b\s*", " ", nombre or "", flags=re.IGNORECASE)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s.title()


class _CantidadDialog(QDialog):
    """Pide la CANTIDAD (unidades) a añadir de un producto, con teclado numérico táctil. `cantidad`
    queda con el valor elegido tras aceptar."""

    def __init__(self, nombre, precio, parent=None):
        super().__init__(parent)
        self.cantidad = 0
        self._buffer = ""
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(360)
        main = QVBoxLayout(self); main.setContentsMargins(0, 0, 0, 0)
        cont = QFrame()
        cont.setStyleSheet(f"QFrame{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        main.addWidget(cont)
        ly = QVBoxLayout(cont); ly.setContentsMargins(18, 16, 18, 16); ly.setSpacing(10)
        ly.addWidget(_lbl(tr("tpv.qty_title", default="¿Cuántas unidades?"), bold=True, size=15, color=_CIAN))
        ly.addWidget(_lbl(f"{nombre} · {divisas.formatear(precio)}", size=12, color=_TEXT2))
        self._disp = _lbl("1", bold=True, size=34, color=_VERDE)
        self._disp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(self._disp)
        grid = QGridLayout(); grid.setSpacing(8)
        teclas = [("7", 0, 0), ("8", 0, 1), ("9", 0, 2), ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
                  ("1", 2, 0), ("2", 2, 1), ("3", 2, 2), ("C", 3, 0), ("0", 3, 1), ("⌫", 3, 2)]
        for t, r, c in teclas:
            b = QPushButton(t); b.setMinimumSize(90, 54); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"QPushButton{{background:{_BG2};color:{_TEXT};border:1px solid {_BORDE};"
                            f"border-radius:10px;font-size:18px;font-weight:800;}}"
                            f"QPushButton:hover{{border-color:{_CIAN};color:{_CIAN};}}")
            b.clicked.connect(lambda _=False, k=t: self._tecla(k))
            grid.addWidget(b, r, c)
        ly.addLayout(grid)
        fila = QHBoxLayout(); fila.setSpacing(8)
        bc = QPushButton(tr("common.cancel", default="Cancelar")); bc.setMinimumHeight(46)
        bc.setCursor(Qt.CursorShape.PointingHandCursor); bc.clicked.connect(self.reject)
        bc.setStyleSheet(f"QPushButton{{background:transparent;color:{_TEXT2};border:2px solid {_BORDE};"
                         f"border-radius:10px;font-weight:800;}}"
                         f"QPushButton:hover{{border-color:{_ROJO};color:{_ROJO};}}")
        ba = QPushButton("✔  " + tr("tpv.qty_add", default="Añadir")); ba.setMinimumHeight(46)
        ba.setCursor(Qt.CursorShape.PointingHandCursor); ba.clicked.connect(self._aceptar)
        ba.setStyleSheet(f"QPushButton{{background:{_VERDE};color:#0B1118;border:none;border-radius:10px;"
                         f"font-weight:900;}}QPushButton:hover{{background:#FFFFFF;}}")
        fila.addWidget(bc); fila.addWidget(ba)
        ly.addLayout(fila)

    def _valor(self) -> int:
        return int(self._buffer) if self._buffer else 1

    def _tecla(self, k):
        if k == "C":
            self._buffer = ""
        elif k == "⌫":
            self._buffer = self._buffer[:-1]
        elif k.isdigit() and len(self._buffer) < 4:
            self._buffer = (self._buffer + k).lstrip("0")
        self._disp.setText(str(self._valor()))

    def _aceptar(self):
        self.cantidad = self._valor()
        self.accept()

    def showEvent(self, e):
        super().showEvent(e)
        try:
            p = self.parent().frameGeometry()
            self.move(p.center().x() - self.width() // 2, p.center().y() - self.height() // 2)
        except Exception:
            pass


class _EmojiPickerPopup(QFrame):
    """Desplegable de emojis: rejilla de 4 columnas y 4 filas VISIBLES; el resto se navega con la scrollbar
    (estándar de la app). Mantiene TODOS los emojis sin abrirse a pantalla completa."""

    _COLS = 4
    _FILAS_VIS = 4
    _CELDA = 46

    def __init__(self, on_pick, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self._on_pick = on_pick
        self.setStyleSheet(f"QFrame{{background:{_BG};border:2px solid {_CIAN};border-radius:10px;}}")
        outer = QVBoxLayout(self); outer.setContentsMargins(6, 6, 6, 6); outer.setSpacing(0)
        from src.gui.foundation import tokens as _tok
        scroll = QScrollArea(); scroll.setWidgetResizable(False)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea{{background:{_BG};border:none;}}" + _tok.qss_scrollbar())
        # Rejilla DETERMINISTA: filas explícitas de 4 botones (no depende del auto-layout de IconMode).
        cont = QWidget(); cont.setStyleSheet(f"background:{_BG};")
        col = QVBoxLayout(cont); col.setContentsMargins(0, 0, 0, 0); col.setSpacing(2)
        items = [("", "—")] + [(e, e) for e in _EMOJIS_COMIDA]
        fila = None
        for i, (val, disp) in enumerate(items):
            if i % self._COLS == 0:
                fila = QHBoxLayout(); fila.setContentsMargins(0, 0, 0, 0); fila.setSpacing(2)
                _rw = QWidget(); _rw.setLayout(fila); col.addWidget(_rw)
            b = QPushButton(disp); b.setFixedSize(self._CELDA, self._CELDA)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            # min/max-width explícitos: el QSS global de QPushButton fija un min-width grande que si no se
            # anula ESTIRA los botones (se solapan) e ignora setFixedSize.
            b.setStyleSheet(f"QPushButton{{background:transparent;color:{_TEXT};border:none;border-radius:6px;"
                            f"font-size:22px;padding:0;margin:0;"
                            f"min-width:{self._CELDA}px;max-width:{self._CELDA}px;"
                            f"min-height:{self._CELDA}px;max-height:{self._CELDA}px;}}"
                            f"QPushButton:hover{{background:rgba(0,255,198,0.18);}}")
            b.clicked.connect(lambda _=False, v=val: self._pick(v))
            fila.addWidget(b)
        if fila is not None:                              # rellenar la última fila para mantener 4 columnas
            fila.addStretch()
        cont.setFixedWidth(self._COLS * self._CELDA + (self._COLS - 1) * 2)
        cont.adjustSize()
        scroll.setWidget(cont)
        scroll.setFixedHeight(self._FILAS_VIS * self._CELDA + (self._FILAS_VIS - 1) * 2 + 4)
        outer.addWidget(scroll)
        self.setFixedWidth(cont.width() + 16 + 12)        # contenido + scrollbar + márgenes
        self.adjustSize()

    def _pick(self, valor):
        try:
            self._on_pick(valor)
        finally:
            self.close()


class _EmojiCombo(QComboBox):
    """Selector de emoji con el aspecto estándar (triángulo turquesa, como el combo Familia). Al abrirlo NO
    muestra el desplegable nativo, sino el picker en rejilla 4×4 desplegado HACIA ARRIBA (para no salirse por
    abajo de la pantalla)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.addItem("—")
        self._pop = None

    def set_emoji(self, e):
        self.setItemText(0, e if e else "—")

    def emoji(self) -> str:
        t = self.itemText(0)
        return "" if t == "—" else t

    def showPopup(self):
        from PyQt6.QtCore import QPoint
        pop = _EmojiPickerPopup(self.set_emoji, parent=self)
        pop.adjustSize()
        gp = self.mapToGlobal(QPoint(0, 0))
        pop.move(gp.x(), gp.y() - pop.height() - 2)     # hacia ARRIBA
        pop.show()
        self._pop = pop

    def hidePopup(self):
        if self._pop is not None:
            self._pop.close(); self._pop = None
        super().hidePopup()


class _GestionProductosFamiliaDialog(QDialog):
    """Gestiona qué productos de la BD pertenecen a una FAMILIA del TPV bakery (Dulce/Salado/Bebidas).

    Muestra TODOS los artículos de la empresa en una tabla (NO AÑADIDOS ❌ · AÑADIDOS ✔️ · FAMILIA
    ASIGNADA · PRECIO). Al seleccionar un producto se puede: añadirlo a la familia actual (precio
    OBLIGATORIO), cambiar su precio y reasignar su familia. Reutiliza `db/familias` (asignar/listar) y
    `db/articulos.actualizar_precio` — sin lógica de negocio nueva."""

    def __init__(self, familia_actual, id_empresa, parent=None):
        super().__init__(parent)
        self._fam = familia_actual
        self._emp = id_empresa
        self._sel = None
        self._arts = []
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(940, 660)
        from src.db import familias as F
        self._famrows = F.listar_familias(self._emp, solo_activas=False)
        self._build()
        self._recargar()

    def _fam_id(self, nombre):
        for f in self._famrows:
            if str(f.get("nombre") or "").strip().lower() == str(nombre or "").strip().lower():
                return f.get("id")
        return None

    def _build(self):
        main = QVBoxLayout(self); main.setContentsMargins(0, 0, 0, 0)
        cont = QFrame()
        cont.setStyleSheet(f"QFrame{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        main.addWidget(cont)
        ly = QVBoxLayout(cont); ly.setContentsMargins(20, 16, 20, 16); ly.setSpacing(10)
        cab = QHBoxLayout()
        cab.addWidget(_lbl(tr("tpv.gp_title", default="Gestionar productos · {f}", f=self._fam),
                           bold=True, size=16, color=_CIAN))
        cab.addStretch()
        bx = QPushButton("✕"); bx.setFixedSize(34, 34); bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet(f"QPushButton{{background:{_BG2};color:{_TEXT2};border:1px solid {_BORDE};"
                         f"border-radius:8px;font-weight:900;}}"
                         f"QPushButton:hover{{border-color:{_ROJO};color:{_ROJO};}}")
        bx.clicked.connect(self.accept)
        cab.addWidget(bx)
        ly.addLayout(cab)
        ly.addWidget(_lbl(tr("tpv.gp_help",
                            default="Haz clic en un producto para seleccionarlo. Ajusta el precio y la "
                                    "familia y pulsa Guardar, o añádelo a «{f}» (precio obligatorio).",
                            f=self._fam), size=11, color=_TEXT2))

        # Plantilla ESTÁNDAR de tabla de la app (misma que Logística/Expediciones): el borde neón va en el
        # CONTENEDOR y la tabla es sin borde, con un CornerCover que redibuja las esquinas redondeadas por
        # encima (así el contorno no se corta por la scrollbar y no hay doble contorno en la cabecera).
        from assets.estilo_global import construir_tabla_estilizada
        cont_tabla, self.tabla = construir_tabla_estilizada(cont)
        if self.tabla is None:                       # fallback defensivo
            self.tabla = QTableWidget(); cont_tabla = self.tabla
        self.tabla.setColumnCount(4)
        self.tabla.setHorizontalHeaderLabels([
            tr("tpv.gp_col_no", default="NO AÑADIDOS ❌"),
            tr("tpv.gp_col_si", default="AÑADIDOS ✔️"),
            tr("tpv.gp_col_fam", default="FAMILIA ASIGNADA"),
            tr("tpv.gp_col_precio", default="PRECIO (€)")])
        _hh = self.tabla.horizontalHeader()
        _hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        _hh.setHighlightSections(False)              # sin doble contorno al seleccionar fila
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla.itemSelectionChanged.connect(self._on_sel)
        # Mismo estilo limpio que la tabla de referencia (Logística): tabla SIN borde, cabecera sin
        # border-bottom (evita el contorno duplicado) y con esquinas superiores redondeadas + hover. El
        # ÚNICO contorno neón lo dibuja el CornerCover del contenedor.
        self.tabla.setStyleSheet(
            "QTableWidget{border:none;background-color:transparent;outline:none;}"
            "QHeaderView{background-color:transparent;border:none;}"
            f"QHeaderView::section{{background-color:#1A1D23;color:{_CIAN};border:none;"
            "padding:10px 12px;font-weight:900;}"
            f"QHeaderView::section:hover{{background-color:{_CIAN};color:#0E1117;}}"
            "QHeaderView::section:first{border-top-left-radius:18px;}"
            "QHeaderView::section:last{border-top-right-radius:18px;}")
        ly.addWidget(cont_tabla, 1)

        # Fila de edición
        fila = QHBoxLayout(); fila.setSpacing(8)
        self.lbl_sel = _lbl(tr("tpv.gp_none", default="(ningún producto)"), bold=True, size=12, color=_TEXT)
        self.lbl_sel.setMinimumWidth(220)
        fila.addWidget(self.lbl_sel)
        fila.addWidget(_lbl(tr("tpv.gp_precio", default="Precio €"), size=12, color=_TEXT2))
        self.inp_precio = QLineEdit(); self.inp_precio.setFixedWidth(90)
        self.inp_precio.setStyleSheet(f"QLineEdit{{background:{_BG};color:{_TEXT};border:1px solid {_BORDE};"
                                      f"border-radius:8px;padding:6px;}}")
        fila.addWidget(self.inp_precio)
        fila.addWidget(_lbl(tr("tpv.gp_familia", default="Familia"), size=12, color=_TEXT2))
        self.cmb_fam = QComboBox(); self.cmb_fam.setMinimumWidth(150)
        self.cmb_fam.addItem(tr("tpv.gp_sin", default="(sin familia)"), None)
        for f in self._famrows:
            self.cmb_fam.addItem(str(f.get("nombre") or ""), f.get("id"))
        self.cmb_fam.setStyleSheet(f"QComboBox{{background:{_BG};color:{_TEXT};border:1px solid {_BORDE};"
                                   f"border-radius:8px;padding:4px 8px;}}")
        fila.addWidget(self.cmb_fam)
        fila.addWidget(_lbl(tr("tpv.gp_emoji", default="Emoji"), size=12, color=_TEXT2))
        # Selector de emoji: aspecto de combo (triángulo turquesa como Familia) que abre el picker 4×4 hacia arriba.
        self.cmb_emoji = _EmojiCombo(); self.cmb_emoji.setFixedWidth(80)
        self.cmb_emoji.setStyleSheet(f"QComboBox{{background:{_BG};color:{_TEXT};border:1px solid {_BORDE};"
                                     f"border-radius:8px;padding:4px 8px;font-size:16px;}}")
        fila.addWidget(self.cmb_emoji)
        fila.addStretch()
        ly.addLayout(fila)

        fila2 = QHBoxLayout(); fila2.setSpacing(8); fila2.addStretch()
        b_quitar = QPushButton("❌ " + tr("tpv.gp_quitar", default="Quitar de familia"))
        b_quitar.setMinimumHeight(42); b_quitar.clicked.connect(self._quitar)
        b_quitar.setStyleSheet(f"QPushButton{{background:transparent;color:{_TEXT2};border:2px solid {_BORDE};"
                               f"border-radius:10px;font-weight:800;padding:0 12px;}}"
                               f"QPushButton:hover{{border-color:{_ROJO};color:{_ROJO};}}")
        b_guardar = QPushButton("💾 " + tr("tpv.gp_guardar", default="Guardar cambios"))
        b_guardar.setMinimumHeight(42); b_guardar.clicked.connect(self._guardar)
        b_guardar.setStyleSheet(f"QPushButton{{background:{_BG2};color:{_CIAN};border:2px solid {_CIAN};"
                                f"border-radius:10px;font-weight:800;padding:0 12px;}}"
                                f"QPushButton:hover{{background:{_CIAN};color:#0B1118;}}")
        b_add = QPushButton("✔️ " + tr("tpv.gp_add", default="Añadir a «{f}»", f=self._fam))
        b_add.setMinimumHeight(42); b_add.clicked.connect(self._anadir_a_familia)
        b_add.setStyleSheet(f"QPushButton{{background:{_VERDE};color:#0B1118;border:none;border-radius:10px;"
                            f"font-weight:900;padding:0 14px;}}QPushButton:hover{{background:#FFFFFF;}}")
        for b in (b_quitar, b_guardar, b_add):
            b.setCursor(Qt.CursorShape.PointingHandCursor); fila2.addWidget(b)
        ly.addLayout(fila2)

    def _recargar(self):
        from src.db import familias as F
        self._arts = F.listar_articulos_con_familia(self._emp) or []
        fid = self._fam_id(self._fam)
        self.tabla.setRowCount(len(self._arts))
        for i, a in enumerate(self._arts):
            en_fam = (a.get("id_familia") == fid and fid is not None)
            nom = f"{a.get('emoji') or ''} {a.get('nombre') or ''}".strip()
            celdas = ["" if en_fam else nom,
                      nom if en_fam else "",
                      a.get("familia") or "—",
                      divisas.formatear(a.get("precio") or 0)]
            for j, txt in enumerate(celdas):
                it = QTableWidgetItem(txt)
                if j == 1 and en_fam:
                    it.setForeground(QColor(_VERDE))
                self.tabla.setItem(i, j, it)
        self._sel = None
        self.lbl_sel.setText(tr("tpv.gp_none", default="(ningún producto)"))
        self.inp_precio.clear()
        if hasattr(self, "cmb_emoji"):
            self.cmb_emoji.set_emoji("")

    def _on_sel(self):
        r = self.tabla.currentRow()
        if not (0 <= r < len(self._arts)):
            return
        a = self._arts[r]; self._sel = a.get("codigo")
        self.lbl_sel.setText(f"{a.get('nombre')}  ({a.get('codigo')})")
        self.inp_precio.setText(f"{float(a.get('precio') or 0):.2f}")
        idx = self.cmb_fam.findData(a.get("id_familia"))
        self.cmb_fam.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_emoji.set_emoji(str(a.get("emoji") or ""))

    def _precio_valido(self, obligatorio=True):
        try:
            v = float((self.inp_precio.text() or "").replace(",", "."))
        except ValueError:
            v = -1
        if obligatorio and v <= 0:
            from assets.estilo_global import mostrar_mensaje
            mostrar_mensaje(self, tr("tpv.gp_title2", default="Productos"),
                            tr("tpv.gp_precio_req", default="Indica un precio válido (> 0)."), "warning")
            return None
        return v

    def _aplicar(self, id_familia, obligatorio):
        if not self._sel:
            return
        v = self._precio_valido(obligatorio=obligatorio)
        if obligatorio and v is None:
            return
        from src.db import familias as F
        from src.db import articulos as A
        if v is not None and v > 0:
            A.actualizar_precio(self._sel, round(v, 2), id_empresa=self._emp)
        A.actualizar_emoji(self._sel, self.cmb_emoji.emoji(), id_empresa=self._emp)
        F.asignar_familia(self._sel, id_familia, id_empresa=self._emp)
        self._recargar()

    def _anadir_a_familia(self):
        # Añadir a la familia ACTUAL (precio obligatorio).
        self._aplicar(self._fam_id(self._fam), obligatorio=True)

    def _guardar(self):
        # Aplica el precio (si se indicó) y la familia elegida en el combo.
        self._aplicar(self.cmb_fam.currentData(), obligatorio=False)

    def _quitar(self):
        self._aplicar(None, obligatorio=False)

    def showEvent(self, e):
        super().showEvent(e)
        try:
            p = self.parent().frameGeometry()
            self.move(p.center().x() - self.width() // 2, p.center().y() - self.height() // 2)
        except Exception:
            pass


class _RejillaProductosBakery(QDialog):
    """TPV Bakery — venta rápida por UNIDAD. Rejilla de BOTONES GRANDES por producto, agrupados en 3
    familias (Dulce · Salado · Bebidas). Al pulsar un producto se añade al carrito del TPV (reutiliza
    `TPVWindow._add_extra`, sin lógica de venta paralela). Usa las familias REALES de la empresa
    (`db/familias`). Permanece abierta para encadenar varias pulsaciones (venta ágil de mostrador)."""

    _FAMILIAS = ("Dulce", "Salado", "Bebidas")

    def __init__(self, tpv, parent=None):
        super().__init__(parent or tpv)
        self._tpv = tpv
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(900, 640)
        self._fam_actual = self._FAMILIAS[0]
        self._por_familia = self._cargar()
        self._botones_fam = {}
        self._build()

    def _cargar(self) -> dict:
        """{familia: [{codigo,nombre,precio}]} usando las familias reales de la empresa."""
        out = {f: [] for f in self._FAMILIAS}
        try:
            from src.db import familias as F
            idx = {str(f.get("nombre") or "").strip().lower(): (f.get("id") or f.get("id_familia"))
                   for f in F.listar_familias()}
            for fam in self._FAMILIAS:
                fid = idx.get(fam.lower())
                if fid is not None:
                    out[fam] = F.articulos_de_familia(fid) or []
        except Exception as e:
            logger.error("rejilla bakery cargar: %s", e)
        return out

    def _build(self):
        main = QVBoxLayout(self); main.setContentsMargins(0, 0, 0, 0)
        cont = QFrame()
        cont.setStyleSheet(f"QFrame{{background:{_BG};border:2px solid {_CIAN};border-radius:16px;}}")
        main.addWidget(cont)
        ly = QVBoxLayout(cont); ly.setContentsMargins(20, 16, 20, 18); ly.setSpacing(12)

        cab = QHBoxLayout()
        cab.addWidget(_lbl(tr("tpv.bakery_grid_title", default="Productos"), bold=True, size=18, color=_CIAN))
        cab.addStretch()
        self._lbl_feedback = _lbl("", bold=True, size=13, color=_VERDE)
        cab.addWidget(self._lbl_feedback)
        cab.addStretch()
        # Gestionar/añadir productos de la familia actual (asignar productos de la BD, precio y familia).
        b_gestion = QPushButton("🛠️ " + tr("tpv.bakery_manage", default="Gestionar Productos"))
        b_gestion.setCursor(Qt.CursorShape.PointingHandCursor); b_gestion.setMinimumHeight(36)
        b_gestion.setStyleSheet(f"QPushButton{{background:{_BG2};color:{_CIAN};border:2px solid {_CIAN};"
                                f"border-radius:9px;font-weight:800;padding:0 14px;}}"
                                f"QPushButton:hover{{background:{_CIAN};color:#0B1118;}}")
        b_gestion.clicked.connect(self._abrir_gestion_productos)
        cab.addWidget(b_gestion)
        bx = QPushButton("✕"); bx.setFixedSize(36, 36); bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet(f"QPushButton{{background:{_BG2};color:{_TEXT2};border:1px solid {_BORDE};"
                         f"border-radius:8px;font-weight:900;}}"
                         f"QPushButton:hover{{border-color:{_ROJO};color:{_ROJO};}}")
        bx.clicked.connect(self.accept)
        cab.addWidget(bx)
        ly.addLayout(cab)

        # Selector de familia (3 botones grandes)
        fam_row = QHBoxLayout(); fam_row.setSpacing(10)
        for fam in self._FAMILIAS:
            b = QPushButton(fam.upper())
            b.setCursor(Qt.CursorShape.PointingHandCursor); b.setMinimumHeight(52)
            b.clicked.connect(lambda _=False, f=fam: self._sel_familia(f))
            self._botones_fam[fam] = b
            fam_row.addWidget(b)
        ly.addLayout(fam_row)

        # Rejilla de productos (scroll con scrollbar estándar; aparece cuando hay muchos productos).
        from src.gui.foundation import tokens as _tok
        self._scroll = QScrollArea(); self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"QScrollArea{{background:{_BG};border:none;}}" + _tok.qss_scrollbar())
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ly.addWidget(self._scroll, 1)
        self._sel_familia(self._fam_actual)

    def _sel_familia(self, fam):
        self._fam_actual = fam
        for f, b in self._botones_fam.items():
            activo = (f == fam)
            b.setStyleSheet(
                f"QPushButton{{background:{_CIAN if activo else _BG2};color:{'#0B1118' if activo else _TEXT};"
                f"border:2px solid {_CIAN};border-radius:10px;font-family:'Segoe UI';font-weight:900;"
                f"font-size:15px;}}QPushButton:hover{{background:{_CIAN};color:#0B1118;}}")
        self._render_productos()

    def _render_productos(self):
        cont = QWidget(); cont.setStyleSheet(f"background:{_BG};")
        grid = QGridLayout(cont); grid.setSpacing(10)
        grid.setContentsMargins(2, 2, 2, 2)
        prods = self._por_familia.get(self._fam_actual, [])
        if not prods:
            grid.addWidget(_lbl(tr("tpv.bakery_grid_empty",
                                   default="No hay productos en esta familia todavía."),
                                size=14, color=_TEXT2), 0, 0)
        cols = 4
        for i, p in enumerate(prods):
            grid.addWidget(self._btn_producto(p), i // cols, i % cols)
        for c in range(cols):
            grid.setColumnStretch(c, 1)
        self._scroll.setWidget(cont)

    def _btn_producto(self, p):
        nombre = str(p.get("nombre") or p.get("codigo") or "—")
        precio = float(p.get("precio") or 0)
        emoji = str(p.get("emoji") or "").strip()
        disp = _nombre_boton_producto(nombre)
        etiqueta = (f"{emoji}\n{disp}\n{divisas.formatear(precio)}" if emoji
                    else f"{disp}\n{divisas.formatear(precio)}")
        b = QPushButton(etiqueta)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setMinimumSize(190, 92)
        b.setStyleSheet(
            f"QPushButton{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};border-radius:12px;"
            f"font-family:'Segoe UI';font-weight:800;font-size:14px;padding:6px;}}"
            f"QPushButton:hover{{border-color:{_CIAN};color:{_CIAN};}}"
            f"QPushButton:pressed{{background:{_CIAN};color:#0B1118;}}")
        b.clicked.connect(lambda _=False, cod=p.get("codigo"), nom=nombre, pr=precio:
                          self._añadir(cod, nom, pr))
        return b

    def _abrir_gestion_productos(self):
        """Abre el gestor de productos de la familia ACTUAL (asignar productos de la BD, precio y familia).
        Al cerrar, recarga la rejilla para reflejar los cambios."""
        try:
            from src.db.empresa import empresa_actual_id
            emp = empresa_actual_id()
        except Exception:
            emp = None
        _GestionProductosFamiliaDialog(self._fam_actual, emp, parent=self).exec()
        self._por_familia = self._cargar()
        self._render_productos()

    def _añadir(self, codigo, nombre, precio):
        # Al pulsar un producto se pide la CANTIDAD (teclado táctil) antes de sumarlo a la compra.
        dlg = _CantidadDialog(nombre, precio, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.cantidad < 1:
            return
        try:
            self._tpv._add_extra(codigo, nombre, precio, seccion="BAKERY", cantidad=dlg.cantidad)
            self._lbl_feedback.setText(tr("tpv.bakery_added_n", default="Añadido: {n} ×{q}",
                                          n=nombre, q=dlg.cantidad))
        except Exception as e:
            logger.error("rejilla bakery añadir: %s", e)

    def showEvent(self, e):
        super().showEvent(e)
        try:
            pg = self._tpv.frameGeometry()
            self.move(pg.center().x() - self.width() // 2, pg.center().y() - self.height() // 2)
        except Exception:
            pass


class TPVWindow(QWidget):
    def __init__(
        self,
        empleado_id=None,
        main_window=None,
        callback_vuelta=None,
        usuario=None,
        main=None,
        parent=None,
    ):
        super().__init__(parent)
        self.empleado_id = empleado_id or (usuario or {}).get("id")
        self.main_window = main
        self._callback_vuelta = callback_vuelta
        self._lineas: list[dict] = []
        self._id_caja: str | None = None
        self._empleado_tpv: str = ""
        self._empleado_id_tpv = None
        self._cliente: dict | None = None  # None = cliente genérico
        self._auth_cancelled: bool = (
            False  # login cancelado → _abrir_tpv_en_stack no muestra el TPV
        )

        self._sidebar_visible = True
        self._compact_auto_sidebar = False

        self.setWindowTitle(tr("tpv.title"))
        self.setMinimumSize(360, 520)
        self.setStyleSheet(f"QWidget{{background:{_BG};}}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        # Responsive P2: el TPV (rejilla + carrito + acciones) tiene un ancho natural amplio; se
        # envuelve en un scroll para que quepa también en pantallas/terminales pequeñas sin cortar
        # información (scroll en lugar de forzar un ancho mínimo grande). No cambia proporciones.
        from PyQt6.QtWidgets import QScrollArea as _QScrollArea
        try:
            from src.gui.foundation import tokens as _T
            _sb = _T.qss_scrollbar()
        except Exception:
            _sb = ""
        self._scroll_root = _QScrollArea()
        self._scroll_root.setWidgetResizable(True)
        self._scroll_root.setFrameShape(_QScrollArea.Shape.NoFrame)
        self._scroll_root.setStyleSheet(f"QScrollArea{{background:{_BG};border:none;}}" + _sb)
        self._scroll_root.setWidget(self._stack)
        root.addWidget(self._scroll_root)

        # Pantalla bloqueada (índice 0)
        self._bloqueada = _PantallaBlockeada()
        self._bloqueada.btn_ir.clicked.connect(self._ir_gestion_caja)
        self._bloqueada.btn_reintentar.clicked.connect(self._verificar_caja)
        self._bloqueada.btn_menu.clicked.connect(self._volver_menu)
        self._stack.addWidget(self._bloqueada)

        # Pantalla TPV (índice 1)
        self._tpv_w = QWidget()
        self._tpv_w.setStyleSheet(f"QWidget{{background:{_BG};}}")
        self._stack.addWidget(self._tpv_w)
        self._build_tpv_ui()

        # Atajo DEL → borrar fila seleccionada
        sc = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        sc.activated.connect(self._borrar_seleccionada)

        # i18n: re-traducción en caliente + dirección RTL.
        self._caja_actual = None
        i18n.conectar_retraduccion(self, self._retraducir)

        # Reloj
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()

        self._verificar_caja()

        # Customer display (second screen only)
        self._cd_result_mode = False
        self._customer_display = None
        try:
            from PyQt6.QtGui import QGuiApplication as _QGA

            if len(_QGA.screens()) > 1:
                from src.gui.customer_display import get_customer_display

                self._customer_display = get_customer_display()
                if self._customer_display:
                    self._customer_display.show()
        except Exception:
            pass

    # ─────────────────── VERIFICACIÓN CAJA ───────────────────

    def _verificar_caja_directa(self, nombre_empleado: str, id_empleado=None):
        """Entra al TPV directamente sin mostrar el diálogo de login."""
        est = _leer_estado_caja()
        caja = _caja_activa(est, nombre_empleado, id_empleado)
        if caja:
            self._id_caja = caja.get("id", "CAJA-01")
            self._empleado_tpv = nombre_empleado
            self._stack.setCurrentIndex(1)
            self._refresh_caja_info(caja)
        else:
            self._id_caja = None
            self._empleado_tpv = ""
            # Sin caja propia → bloquear (no se permite usar la caja de otro).
            est_estado = est.get("estado", "SIN_APERTURA")
            if est_estado in ("PRIMERA_CAJA_ABIERTA", "OPERATIVA") and est.get(
                "cajas_activas"
            ):
                self._bloqueada.set_motivo(tr("bloq.reason_sin_asignar"))
            else:
                self._bloqueada.set_motivo(_motivo_bloqueo(est))
            self._stack.setCurrentIndex(0)

    def _verificar_caja(self):
        est = _leer_estado_caja()
        estado = est.get("estado", "SIN_APERTURA")

        # Sin cajas operativas → pantalla bloqueada directamente
        if estado not in ("PRIMERA_CAJA_ABIERTA", "OPERATIVA") or not est.get(
            "cajas_activas"
        ):
            self._id_caja = None
            self._empleado_tpv = ""
            self._bloqueada.set_motivo(_motivo_bloqueo(est))
            self._stack.setCurrentIndex(0)
            return

        # Hay cajas operativas → pedir login del empleado
        dlg = _LoginTPVDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            # Señal al llamador (_abrir_tpv_en_stack) para que no muestre el TPV
            self._auth_cancelled = True
            return

        nombre_empleado = dlg.get_nombre_empleado()
        id_empleado = dlg.get_id_empleado()
        cajas = _cajas_de_empleado(est, nombre_empleado, id_empleado)

        if not cajas:
            # El empleado no es responsable de ninguna caja → acceso denegado.
            self._id_caja = None
            self._empleado_tpv = ""
            self._empleado_id_tpv = None
            self._bloqueada.set_motivo(tr("bloq.reason_sin_asignar"))
            self._stack.setCurrentIndex(0)
            return

        if len(cajas) == 1:
            caja = cajas[0]
        else:
            sel_dlg = _SeleccionCajaDialog(cajas, parent=self)
            if sel_dlg.exec() != QDialog.DialogCode.Accepted:
                self._auth_cancelled = True
                return
            caja = sel_dlg.get_caja()

        self._id_caja = caja.get("id", "CAJA-01")
        self._empleado_tpv = nombre_empleado
        self._empleado_id_tpv = id_empleado
        self._stack.setCurrentIndex(1)
        self._refresh_caja_info(caja)

    def _tpv_refresh_logo(self):
        if os.path.exists(_LOGO_CORP_PATH):
            pix = QPixmap(_LOGO_CORP_PATH)
            if not pix.isNull():
                self.lbl_logo_tpv.setPixmap(
                    pix.scaled(
                        120,
                        42,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                return
        self.lbl_logo_tpv.setPixmap(QPixmap())

    def _volver_menu(self):
        # Si hay una venta en curso, avisar y no salir de golpe.
        if self._lineas:
            if not _confirmar(
                self,
                tr("tpv.exit_confirm_title"),
                tr("tpv.exit_confirm_msg"),
                txt_ok=tr("tpv.exit_confirm_ok"),
            ):
                return
        self._cd_result_mode = False
        customer_display_bridge.cart_cleared.emit()
        if self._customer_display:
            self._customer_display.hide()
        if self._callback_vuelta:
            self._callback_vuelta()
        else:
            self.hide()

    def _ir_gestion_caja(self, *, accion_inicial=None):
        self._cd_result_mode = False
        customer_display_bridge.cart_cleared.emit()
        if self._customer_display:
            self._customer_display.hide()
        if self._callback_vuelta:
            self._callback_vuelta()
        else:
            self.hide()
        # P4.1: Gestión de Caja en ventana propia (reutiliza la lógica existente).
        if self.main_window and hasattr(self.main_window, "abrir_gestion_caja"):
            QTimer.singleShot(200, lambda: self.main_window.abrir_gestion_caja(accion_inicial=accion_inicial))
        elif self.main_window and hasattr(self.main_window, "abrir_modulo_configuracion"):
            QTimer.singleShot(200, self.main_window.abrir_modulo_configuracion)

    # ── UX-TPV-01: accesos directos reutilizando ventanas/lógica existentes ────
    def _abrir_mostrar_stock(self):
        """P1 — Consulta de stock desde el TPV sin abandonar la venta. Abre la
        ventana de stock EXISTENTE (MostrarStockWindow) como ventana hija."""
        # Permiso (legacy-safe: si no hay RBAC asignado, permitido).
        try:
            from src.services import autorizacion
            if not autorizacion.puede("stock.consultar_desde_tpv"):
                QMessageBox.warning(self, tr("tpv.no_perm_title", default="Sin permiso"),
                                    tr("tpv.no_perm_stock", default="No tiene permiso para consultar stock."))
                return
        except Exception:
            pass
        # Auditoría.
        try:
            from src.db.conexion import log_auditoria
            log_auditoria(self._empleado_tpv or "TPV", "ABRIR_STOCK_DESDE_TPV", "stock",
                          f"caja={self._id_caja}")
        except Exception:
            pass
        try:
            from src.gui.mostrar_stock import MostrarStockWindow
            self._win_stock = MostrarStockWindow(
                callback_vuelta=lambda: self._cerrar_win_hija("_win_stock"),
                usuario=getattr(self, "usuario", None) or {})
            if hasattr(self._win_stock, "showMaximized"):
                self._win_stock.showMaximized()
            else:
                self._win_stock.show()
        except Exception as e:
            logger.error("_abrir_mostrar_stock: %s", e)
            QMessageBox.critical(self, tr("tpv.error", default="Error"), str(e))

    def _cerrar_win_hija(self, attr):
        w = getattr(self, attr, None)
        if w is not None:
            try:
                w.close(); w.deleteLater()
            except Exception:
                pass
            setattr(self, attr, None)
        self.raise_(); self.activateWindow()

    def _abrir_movimiento_efectivo(self):
        """P5 — Movimiento de efectivo: enruta a la Gestión de Caja existente y
        dispara la acción validada (misma lógica/permisos/auditoría)."""
        self._ir_gestion_caja(accion_inicial="movimiento")

    def _abrir_cambio_cajero(self):
        """P5.1 — Cambio de cajero: enruta a la Gestión de Caja existente y dispara
        la acción validada (misma autenticación/validación/auditoría)."""
        self._ir_gestion_caja(accion_inicial="cambio_cajero")

    def _abrir_factura(self):
        """Abre la ventana de Facturación: buscar ventas (asignadas o no), ver el
        ticket digital, asignar la venta a un cliente registrado y generar la factura."""
        try:
            from src.gui.factura_window import FacturaWindow
            self._win_factura = FacturaWindow(
                callback_vuelta=lambda: self._cerrar_win_hija("_win_factura"),
                usuario=getattr(self, "usuario", None) or {})
            if hasattr(self._win_factura, "showMaximized"):
                self._win_factura.showMaximized()
            else:
                self._win_factura.show()
        except Exception as e:
            logger.error("_abrir_factura: %s", e)
            QMessageBox.critical(self, tr("tpv.error", default="Error"), str(e))

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "_customer_display", None):
            self._customer_display.show()

    def _cd_clear_result_mode(self):
        self._cd_result_mode = False

    # ─────────────────── CONSTRUCCIÓN UI ─────────────────────

    def _build_tpv_ui(self):
        lay = QVBoxLayout(self._tpv_w)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)

        lay.addWidget(self._build_topbar())

        body = QHBoxLayout()
        self._body_layout = body
        body.setSpacing(10)
        body.addWidget(self._build_izq(), 6)
        self._panel_der = self._build_der()
        # Responsive (P2): el panel derecho (numpad/acciones) mantiene un mínimo usable
        # (teclado no se estruja) y un máximo (no domina en pantallas anchas; deja más
        # espacio al carrito). Entre medias, reparto proporcional 6:4.
        self._panel_der.setMinimumWidth(300)
        self._panel_der.setMaximumWidth(560)
        body.addWidget(self._panel_der, 4)
        lay.addLayout(body, 1)  # stretch=1 → ocupa todo el alto disponible

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(54)
        bar.setStyleSheet(
            f"QFrame{{background:{_BG2};border:none;"
            f"border-bottom:1px solid {_BORDE};border-radius:0px;}}"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 12, 0)

        self.lbl_logo_tpv = QLabel()
        self.lbl_logo_tpv.setFixedSize(56, 42)
        self.lbl_logo_tpv.setStyleSheet("background:transparent;border:none;")
        self.lbl_logo_tpv.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        )
        self._tpv_refresh_logo()
        lay.addWidget(self.lbl_logo_tpv)
        lay.addSpacing(2)

        self._lbl_titulo_tpv = _lbl(tr("tpv.title"), bold=True, size=15, color=_CIAN)
        lay.addWidget(self._lbl_titulo_tpv)
        lay.addStretch()

        self.lbl_caja_top = _lbl(
            tr("tpv.register_dash"), bold=True, size=14, color=_TEXT2
        )
        lay.addWidget(self.lbl_caja_top)

        lay.addSpacing(20)
        self.lbl_reloj = _lbl("", bold=True, size=14, color=_TEXT2)
        lay.addWidget(self.lbl_reloj)

        lay.addSpacing(16)
        self._btn_sidebar_toggle = btn_side = QPushButton(
            tr("tpv.hide_sidebar", default="OCULTAR")
        )
        btn_side.setFixedSize(112, 36)
        btn_side.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_side.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_side.setStyleSheet(
            f"QPushButton{{background:{_BG};color:{_CIAN};border:2px solid {_CIAN};"
            f"border-radius:8px;font-family:'{_FONT}';font-weight:900;font-size:11px;outline:0px;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0D1117;}}"
        )
        # clicked emite checked=False (botón no checkable); ignorarlo para que el
        # botón ALTERNE de verdad (OCULTAR ↔ ACCIONES) en vez de ocultar siempre.
        btn_side.clicked.connect(lambda *_: self._toggle_sidebar())
        lay.addWidget(btn_side)

        lay.addSpacing(8)
        self._btn_salir_tpv = btn_salir = QPushButton("✕")
        btn_salir.setFixedSize(48, 36)
        btn_salir.setToolTip(tr("tpv.exit"))
        btn_salir.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_salir.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_salir.setStyleSheet(
            f"QPushButton{{background:{_ROJO};color:#FFF;border:none;outline:0px;"
            f"border-radius:8px;font-family:'{_FONT}';font-weight:900;font-size:16px;}}"
            f"QPushButton:hover{{background:#CC0000;color:#FFF;}}"
            f"QPushButton:focus{{outline:0px;border:none;}}"
        )
        btn_salir.clicked.connect(self._volver_menu)
        lay.addWidget(btn_salir)
        return bar

    def _toggle_sidebar(self, visible: bool | None = None):
        if not hasattr(self, "_panel_der"):
            return
        self._sidebar_visible = (
            (not self._sidebar_visible) if visible is None else bool(visible)
        )
        self._panel_der.setVisible(self._sidebar_visible)
        if hasattr(self, "_btn_sidebar_toggle"):
            self._btn_sidebar_toggle.setText(
                tr("tpv.hide_sidebar", default="OCULTAR")
                if self._sidebar_visible
                else tr("tpv.show_sidebar", default="ACCIONES")
            )

    def _apply_responsive_layout(self):
        ancho = max(0, self.width())
        compacto = bool(ancho and ancho < 920)
        if compacto and self._sidebar_visible:
            self._compact_auto_sidebar = True
            self._toggle_sidebar(False)
        elif not compacto and self._compact_auto_sidebar:
            self._compact_auto_sidebar = False
            self._toggle_sidebar(True)

        # Responsive (P2): en pantallas estrechas, ocultar adornos de la barra superior
        # (logo + reloj) para que no desborden; se conservan título, info de caja y botones.
        for _attr in ("lbl_logo_tpv", "lbl_reloj"):
            _w = getattr(self, _attr, None)
            if _w is not None:
                _w.setVisible(not compacto)

        if hasattr(self, "tabla"):
            self.tabla.setColumnHidden(4, compacto)
            hh = self.tabla.horizontalHeader()
            if compacto:
                hh.resizeSection(0, 82)
                hh.resizeSection(2, 44)
                hh.resizeSection(3, 62)
                hh.resizeSection(5, 74)
                hh.resizeSection(6, 92)
            else:
                hh.resizeSection(0, 104)
                hh.resizeSection(2, 54)
                hh.resizeSection(3, 72)
                hh.resizeSection(4, 82)
                hh.resizeSection(5, 82)
                hh.resizeSection(6, 120)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _build_izq(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(self._build_busqueda())
        lay.addWidget(self._build_tabla(), 1)
        lay.addWidget(self._build_resumen_bar())  # resumen bajo la tabla (horizontal)
        return w

    def _build_resumen_bar(self) -> QFrame:
        """Resumen del pedido como barra horizontal bajo la tabla del carrito."""
        card = _card()
        cl = QHBoxLayout(card)
        cl.setContentsMargins(16, 10, 18, 10)
        cl.setSpacing(22)
        self._lbl_resumen = _lbl(tr("tpv.summary"), bold=True, size=14)
        self.lbl_n_items = _lbl(
            tr("tpv.items", n=0, uds=0), bold=True, size=14, color=_TEXT2
        )
        self.lbl_subtotal = _lbl(
            tr("tpv.subtotal", x="0,00"), bold=True, size=14, color=_TEXT2
        )
        self.lbl_dto = _lbl(tr("tpv.discount_zero"), bold=True, size=14, color=_TEXT2)
        cl.addWidget(self._lbl_resumen)
        cl.addSpacing(6)
        cl.addWidget(self.lbl_n_items)
        cl.addWidget(self.lbl_subtotal)
        cl.addWidget(self.lbl_dto)
        cl.addStretch()
        self.lbl_total = _lbl(
            tr("tpv.total", x="0,00"), bold=True, size=22, color=_CIAN
        )
        cl.addWidget(self.lbl_total)
        return card

    def _build_busqueda(self) -> QFrame:
        card = _card()
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)

        self.inp_sku = QLineEdit()
        self.inp_sku.setPlaceholderText(tr("tpv.search_placeholder"))
        self.inp_sku.setStyleSheet(
            f"QLineEdit{{background:{_BG};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:6px 12px;font-size:14px;font-family:'{_FONT}';}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}"
        )
        self.inp_sku.returnPressed.connect(self._agregar)
        lay.addWidget(self.inp_sku, 1)

        # Escáner universal (Bloque 8.3): wedge/USB/Bluetooth HID de cualquier fabricante,
        # captura global aunque el campo no tenga el foco. No intrusivo (no consume teclas).
        try:
            from src.gui.escaner_qt import instalar_escaner
            self._filtro_escaner = instalar_escaner(self, self._on_codigo_escaneado)
        except Exception:
            pass

        qty_frame = QFrame()
        qty_frame.setFixedWidth(82)
        qty_frame.setFixedHeight(38)
        qty_frame.setStyleSheet(
            f"QFrame{{background:{_BG};border:2px solid {_BORDE};border-radius:8px;}}"
        )
        qty_row = QHBoxLayout(qty_frame)
        qty_row.setContentsMargins(8, 0, 4, 0)
        qty_row.setSpacing(2)

        lbl_x = QLabel("×")
        lbl_x.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
        )
        lbl_x.setStyleSheet(
            f"color:{_TEXT2};font-size:15px;font-family:'{_FONT}';font-weight:900;"
            f"background:transparent;border:none;margin-bottom:1px;"
        )
        qty_row.addWidget(lbl_x)

        self.inp_qty = QLineEdit("1")
        self.inp_qty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inp_qty.setValidator(QIntValidator(1, 999, self))
        self.inp_qty.setStyleSheet(
            f"QLineEdit{{background:transparent;color:{_TEXT};border:none;padding:0;"
            f"font-size:15px;font-weight:900;font-family:'{_FONT}';}}"
        )
        qty_row.addWidget(self.inp_qty)

        lay.addWidget(qty_frame)

        self._btn_add = btn_add = _btn(
            tr("tpv.add"),
            color_bg=_CIAN,
            color_fg="#0D1117",
            color_border=_CIAN,
            hover_bg="#FFF",
            hover_fg="#0D1117",
            h=38,
        )
        btn_add.clicked.connect(self._agregar)
        lay.addWidget(btn_add)
        return card

    def _build_numpad(self) -> QFrame:
        card = _card()
        gl = QGridLayout(card)
        gl.setContentsMargins(8, 6, 8, 6)
        gl.setSpacing(6)

        # Botones grandes, cuadrados y con esquinas redondeadas (estilo TPV táctil).
        _ss_num = (
            f"QPushButton{{background:{_BG};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:16px;font-family:'{_FONT}';font-weight:900;font-size:24px;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0D1117;border-color:{_CIAN};}}"
            f"QPushButton:pressed{{background:{_CIAN};color:#0D1117;}}"
        )
        _ss_fn = (
            f"QPushButton{{background:{_BG2};color:{_TEXT2};border:2px solid {_BORDE};"
            f"border-radius:16px;font-family:'{_FONT}';font-weight:900;font-size:18px;}}"
            f"QPushButton:hover{{background:#30363D;color:{_TEXT};}}"
        )
        _ss_del = (
            f"QPushButton{{background:{_BG2};color:{_ROJO};border:2px solid {_ROJO};"
            f"border-radius:16px;font-family:'{_FONT}';font-weight:900;font-size:22px;}}"
            f"QPushButton:hover{{background:{_ROJO};color:#FFF;}}"
        )

        H = 44  # alto fijo → botones grandes; ajustado para que los números se vean completos
        layout_keys = [
            ("7", 0, 0, "num"),
            ("8", 0, 1, "num"),
            ("9", 0, 2, "num"),
            ("4", 1, 0, "num"),
            ("5", 1, 1, "num"),
            ("6", 1, 2, "num"),
            ("1", 2, 0, "num"),
            ("2", 2, 1, "num"),
            ("3", 2, 2, "num"),
            ("C", 3, 0, "fn"),
            ("0", 3, 1, "num"),
            ("⌫", 3, 2, "del"),
        ]
        for c in range(3):
            gl.setColumnStretch(c, 1)
        for txt, row, col, sk in layout_keys:
            b = QPushButton(txt)
            b.setFixedHeight(H)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setStyleSheet(
                _ss_num if sk == "num" else (_ss_del if sk == "del" else _ss_fn)
            )
            b.clicked.connect(lambda checked, t=txt: self._num_pulse(t))
            gl.addWidget(b, row, col)

        return card

    def _num_pulse(self, tecla: str):
        if tecla == "⌫":
            txt = self.inp_sku.text()
            self.inp_sku.setText(txt[:-1])
        elif tecla == "C":
            self.inp_sku.clear()
        else:
            self.inp_sku.setText(self.inp_sku.text() + tecla)
        self.inp_sku.setFocus()

    def _tpv_headers(self) -> list:
        return [
            tr("tpv.col_code"),
            tr("tpv.col_name"),
            tr("tpv.col_qty"),
            tr("tpv.col_unit"),
            tr("tpv.col_disc"),
            tr("tpv.col_subtotal"),
            tr("tpv.col_actions"),
        ]

    def _build_tabla(self) -> QFrame:
        card = _card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 0)

        self.tabla = QTableWidget()
        self.tabla.setColumnCount(7)
        self.tabla.setHorizontalHeaderLabels(self._tpv_headers())
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(56)  # papelera completa
        self.tabla.setStyleSheet(
            f"QTableWidget{{background:{_BG};color:{_TEXT};border:none;"
            f"font-family:'{_FONT}';font-size:12px;gridline-color:{_BORDE};}}"
            f"QTableWidget::item{{padding:4px 12px;}}"
            f"QTableWidget::item:selected{{background:#1C2128;color:{_CIAN};}}"
            f"QTableWidget::item:alternate{{background:#0B0F14;}}"
            f"QHeaderView::section{{background:{_BG2};color:{_TEXT2};"
            f"border:none;border-bottom:1px solid {_BORDE};"
            f"padding:6px 12px;font-weight:700;font-family:'{_FONT}';}}"
        )

        hh = self.tabla.horizontalHeader()
        for col, mode in [
            (0, QHeaderView.ResizeMode.Fixed),
            (1, QHeaderView.ResizeMode.Stretch),
            (2, QHeaderView.ResizeMode.Fixed),
            (3, QHeaderView.ResizeMode.Fixed),
            (4, QHeaderView.ResizeMode.Fixed),
            (5, QHeaderView.ResizeMode.Fixed),
            (6, QHeaderView.ResizeMode.Fixed),
        ]:
            hh.setSectionResizeMode(col, mode)
        hh.resizeSection(0, 104)
        hh.resizeSection(2, 54)
        hh.resizeSection(3, 72)
        hh.resizeSection(4, 82)  # Dto%: más ancho para que se vea el valor completo
        hh.resizeSection(5, 82)
        hh.resizeSection(
            6, 120
        )  # ACCIONES: editar (lápiz) + borrar (papelera) con su contorno
        hh.setMinimumSectionSize(40)

        self.tabla.doubleClicked.connect(self._editar_linea)
        lay.addWidget(self.tabla)
        return card

    @staticmethod
    def _icono_people(color: str) -> QIcon:
        """Icono SVG 'people' idéntico al de la tarjeta CLIENTES del menú principal."""
        svg = f"""
            <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
              <g fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="48" cy="44" r="16"/>
                <path d="M22 96c0-16 12-26 26-26s26 10 26 26"/>
                <circle cx="88" cy="50" r="12"/>
                <path d="M84 72c12 0 22 9 22 24"/>
              </g>
            </svg>
        """
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        pm = QPixmap(128, 128)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        renderer.render(p)
        p.end()
        return QIcon(pm)

    def _btn_cliente_card(self, on_click=None):
        """Tarjeta de cliente con el MISMO aspecto que el botón CLIENTES del menú
        principal (QToolButton, icono SVG 'people' sobre el texto, borde cian + glow),
        pero dimensionada como las tarjetas de acción (mismo tamaño que la rejilla)."""
        color = _CIAN
        b = QToolButton()
        b._icono_normal = self._icono_people(color)
        b._icono_hover = self._icono_people("#0B1118")
        b.setIcon(b._icono_normal)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        b.setIconSize(QSize(34, 34))   # icono acorde a las tarjetas de acción (x2 −15%)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setMinimumHeight(78)   # mismo tamaño que las tarjetas de acción (x2 −15%)
        b.setMaximumHeight(78)   # evita que crezca por encima del resto de botones
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        b.setStyleSheet(
            f"QToolButton{{background-color:{_BG2};color:{color};"
            f"border:2px solid {color};border-radius:14px;padding:2px;"
            f"font-family:'{_FONT}';font-size:14px;font-weight:900;outline:0px;}}"
            f"QToolButton:hover{{background-color:{color};color:#0B1118;border:2px solid {color};}}"
            f"QToolButton:pressed{{background-color:{color};color:#0B1118;border:2px solid {color};}}"
        )
        glow = QGraphicsDropShadowEffect(b)
        glow.setBlurRadius(8)
        glow.setColor(QColor(color))
        glow.setOffset(0, 0)
        b.setGraphicsEffect(glow)
        # Recolorea el icono al pasar el ratón (igual que MenuCardButton).
        b.enterEvent = lambda e, _b=b: (_b.setIcon(_b._icono_hover), QToolButton.enterEvent(_b, e))
        b.leaveEvent = lambda e, _b=b: (_b.setIcon(_b._icono_normal), QToolButton.leaveEvent(_b, e))
        if on_click:
            b.clicked.connect(on_click)
        return b

    def _btn_accion_card(
        self, icono: str, texto: str, color: str, on_click=None, danger=False, icon_px=18,
        grande=False
    ):
        """Botón de acción cuadrado: icono centrado arriba y texto debajo.
        Devuelve (boton, label_texto) para poder re-traducir el texto.
        `grande=True` duplica el alto del botón y escala icono y texto (panel de Acciones del TPV)."""
        col = _ROJO if danger else color
        # Panel de Acciones (grande): x2 en vertical reducido un 15% → alto 78, icono ×1.7, texto 14.
        alto = 78 if grande else 46
        if grande:
            icon_px = round(icon_px * 1.7)
        txt_px = 14 if grande else 11
        b = QPushButton()
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setMinimumHeight(alto)
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # Iconos algo más pequeños; texto +1 pt. Con HOVER SWAP (relleno del color + icono/texto oscuros).
        _dark = "#0B1118"
        _ss_normal = (f"QPushButton{{background:{_BG2};border:2px solid {col};border-radius:14px;outline:0px;}}"
                      f"QPushButton:disabled{{background:#161B22;border-color:#30363D;}}")
        b.setStyleSheet(_ss_normal)
        v = QVBoxLayout(b)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(3 if grande else 2)
        li = QLabel(icono)
        li.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _ss_ico = f"color:%s;font-family:'{_FONT}';font-size:{icon_px}px;background:transparent;border:none;"
        li.setStyleSheet(_ss_ico % col)
        lt = QLabel(_solo_texto(texto))
        lt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lt.setWordWrap(True)
        _ss_txt = f"color:%s;font-family:'{_FONT}';font-weight:900;font-size:{txt_px}px;background:transparent;border:none;"
        lt.setStyleSheet(_ss_txt % col)
        for l in (li, lt):
            l.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        v.addWidget(li)
        v.addWidget(lt)

        def _enter(e, _b=b, _li=li, _lt=lt):
            _b.setStyleSheet(f"QPushButton{{background:{col};border:2px solid {col};border-radius:14px;"
                             f"outline:0px;}}")
            _li.setStyleSheet(_ss_ico % _dark)
            _lt.setStyleSheet(_ss_txt % _dark)
            QPushButton.enterEvent(_b, e)

        def _leave(e, _b=b, _li=li, _lt=lt):
            _b.setStyleSheet(_ss_normal)
            _li.setStyleSheet(_ss_ico % col)
            _lt.setStyleSheet(_ss_txt % col)
            QPushButton.leaveEvent(_b, e)
        b.enterEvent = _enter
        b.leaveEvent = _leave
        if on_click:
            b.clicked.connect(on_click)
        return b, lt

    def _build_der(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # (El selector de cliente se ha movido abajo, junto a "Venta online",
        #  con el aspecto de la tarjeta CLIENTES del menú principal.)

        # Botón COBRAR
        self.btn_cobrar = QPushButton(tr("tpv.charge"))
        self.btn_cobrar.setFixedHeight(46)
        self.btn_cobrar.setEnabled(False)
        self.btn_cobrar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cobrar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_cobrar.setStyleSheet(
            f"QPushButton{{background:{_VERDE};color:#0D1117;border:2px solid {_VERDE};"
            f"border-radius:14px;font-family:'{_FONT}';font-weight:900;font-size:20px;outline:0px;}}"
            f"QPushButton:hover{{background:#FFF;color:#0D1117;}}"
            f"QPushButton:focus{{outline:0px;border:2px solid {_VERDE};}}"
            f"QPushButton:disabled{{background:#1C2128;color:#484F58;border-color:#30363D;}}"
        )
        self.btn_cobrar.clicked.connect(self._realizar_pago)

        # Teclado numérico (a la derecha, táctil)
        lay.addWidget(self._build_numpad())
        # Botón COBRAR justo debajo del teclado numérico
        lay.addWidget(self.btn_cobrar)

        # Acciones secundarias — tarjetas con icono centrado y texto debajo
        card_acc = _card()
        cl2 = QVBoxLayout(card_acc)
        cl2.setSpacing(6)
        cl2.setContentsMargins(10, 8, 10, 8)
        self._lbl_acciones = _lbl(tr("tpv.actions"), bold=True, size=12, color=_TEXT2)
        cl2.addWidget(self._lbl_acciones)

        grid_acc = QGridLayout()
        grid_acc.setSpacing(6)
        for c in range(3):
            grid_acc.setColumnStretch(c, 1)

        self._acc_labels = {}
        # Panel de Acciones con tarjetas x2 en vertical (grande=True): icono y texto escalados.
        self.btn_bascula, lb = self._btn_accion_card(
            "⚖", tr("tpv.granel", default="Granel"), _CIAN, self._abrir_bascula, grande=True
        )
        self.btn_retener, lr = self._btn_accion_card(
            "⏸", tr("tpv.hold"), _CIAN, self._retener, grande=True
        )
        self.btn_recuperar, lc = self._btn_accion_card(
            "📂", tr("tpv.recover"), _CIAN, self._recuperar, grande=True
        )
        self._btn_vaciar, lv = self._btn_accion_card(
            "🗑", tr("tpv.empty_cart"), _ROJO, self._vaciar, danger=True, icon_px=15, grande=True
        )
        # NOTA: el AUTOCOBRO NO se abre desde el TPV del cajero. Es un terminal independiente que arranca
        # por ROL de terminal (ver src/services/tpv/terminal_rol.py + src/main.py / src/autocobro_app.py).
        # Un TPV de cajero nunca debe transformarse en el kiosco de autoservicio.
        # Extras rápidos: bolsas / sobres de regalo / tarjeta regalo (se añaden solos al carrito).
        self.btn_bolsa_g, l_bg = self._btn_accion_card(
            "🛍", tr("tpv.bag_big", default="Bolsa grande"), _CIAN,
            lambda: self._add_extra_predef("BOLSA_GRANDE"), grande=True)
        self.btn_bolsa_p, l_bp = self._btn_accion_card(
            "👜", tr("tpv.bag_small", default="Bolsa pequeña"), _CIAN,
            lambda: self._add_extra_predef("BOLSA_PEQUENA"), grande=True)
        self.btn_sobre_p, l_sp = self._btn_accion_card(
            "🎁", tr("tpv.gift_small", default="Sobre regalo peq."), _CIAN,
            lambda: self._add_extra_predef("SOBRE_REGALO_PEQUENO"), grande=True)
        self.btn_sobre_g, l_sg = self._btn_accion_card(
            "🎀", tr("tpv.gift_big", default="Sobre regalo grande"), _CIAN,
            lambda: self._add_extra_predef("SOBRE_REGALO_GRANDE"), grande=True)
        self.btn_tarjeta, l_tr = self._btn_accion_card(
            "💳", tr("tpv.gift_card", default="Tarjeta regalo"), _CIAN, self._add_tarjeta_regalo,
            grande=True)
        # NUEVO: agrupa las acciones avanzadas en una ventana emergente (menos saturación del panel).
        self.btn_acciones_avz, l_aa = self._btn_accion_card(
            "⚙", tr("tpv.adv_actions", default="Acciones avanzadas"), _CIAN,
            self._abrir_acciones_avanzadas, grande=True)
        self._acc_labels = {
            "tpv.scale": lb,
            "tpv.hold": lr,
            "tpv.recover": lc,
            "tpv.empty_cart": lv,
            "tpv.bag_big": l_bg,
            "tpv.bag_small": l_bp,
            "tpv.gift_small": l_sp,
            "tpv.gift_big": l_sg,
            "tpv.gift_card": l_tr,
            "tpv.adv_actions": l_aa,
        }
        self.btn_retener.setEnabled(False)

        grid_acc.addWidget(self.btn_bascula, 0, 0)
        # Segmentación por edición: la báscula (venta a granel) solo aplica a supermercado;
        # en retail/farmacia/textil/bakery se oculta (en textil se sustituye por variantes talla/color).
        try:
            from src.services import verticales
            if not verticales.visible("tpv.bascula"):
                self.btn_bascula.setVisible(False)
                # Bakery: venta rápida por UNIDAD → en el hueco de la báscula, un lanzador de la rejilla de
                # productos con botones grandes por familia (Dulce/Salado/Bebidas).
                if verticales.edicion() == "BAKERY":
                    self.btn_prod_bakery, _lpb = self._btn_accion_card(
                        "🧁", tr("tpv.bakery_products", default="Productos"), _CIAN,
                        self._abrir_rejilla_bakery, grande=True)
                    grid_acc.addWidget(self.btn_prod_bakery, 0, 0)
        except Exception:
            pass
        grid_acc.addWidget(self.btn_retener, 0, 1)
        grid_acc.addWidget(self.btn_recuperar, 0, 2)
        grid_acc.addWidget(self.btn_bolsa_g, 1, 0)
        grid_acc.addWidget(self.btn_bolsa_p, 1, 1)
        grid_acc.addWidget(self.btn_sobre_p, 1, 2)
        grid_acc.addWidget(self.btn_sobre_g, 2, 0)
        grid_acc.addWidget(self.btn_tarjeta, 2, 1)
        # Segmentación por edición: la tarjeta regalo no se usa en panadería → se oculta en Bakery.
        try:
            from src.services import verticales
            if not verticales.visible("tpv.tarjeta_regalo"):
                self.btn_tarjeta.setVisible(False)
        except Exception:
            pass
        grid_acc.addWidget(self._btn_vaciar, 2, 2)
        cl2.addLayout(grid_acc)

        # Fila inferior: CLIENTES (tarjeta estilo menú principal) + ACCIONES AVANZADAS
        # (ventana emergente con Precio bolsas / Devolución / Tickets / Venta online /
        #  Mostrar stock / Movimiento efectivo / Cambio cajero / Factura).
        fila_inf = QHBoxLayout()
        fila_inf.setSpacing(8)
        self.btn_cliente = self._btn_cliente_card(self._seleccionar_cliente)
        fila_inf.addWidget(self.btn_cliente)
        fila_inf.addWidget(self.btn_acciones_avz)
        cl2.addLayout(fila_inf)

        lay.addWidget(card_acc)
        self._refrescar_cliente_btn()
        lay.addStretch()
        return w

    # ─────────────────── RELOJ / INFO CAJA ───────────────────

    def _tick(self):
        self.lbl_reloj.setText(datetime.datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))

    def _refresh_caja_info(self, caja: dict):
        cid = caja.get("id", "?")
        resp = caja.get("responsable", "?")
        fondo = caja.get("fondo", 0.0)
        self._caja_actual = caja  # guardado para re-traducción en caliente
        self.lbl_caja_top.setText(f"{cid}  ·  {resp}")
        self.inp_sku.setFocus()

    # ─────────────────── CARRITO ─────────────────────────────

    def _on_codigo_escaneado(self, codigo: str):
        """Escáner universal (Bloque 8.3): añade el artículo escaneado al ticket.

        Solo actúa si el campo SKU no tiene el foco (cuando lo tiene, el escaneo ya
        llega por la vía normal returnPressed -> _agregar, evitando doble alta).
        """
        try:
            if not codigo:
                return
            if hasattr(self, "inp_sku") and self.inp_sku.hasFocus():
                return
            self.inp_sku.setText(codigo)
            self._agregar()
        except Exception:
            pass

    def _agregar(self):
        codigo = self.inp_sku.text().strip()
        if not codigo:
            return

        articulo = obtener_articulo(codigo)
        if not articulo:
            QMessageBox.warning(
                self, tr("tpv.not_found_title"), tr("tpv.not_found_msg", codigo=codigo)
            )
            self.inp_sku.selectAll()
            return

        qty = max(1, int(self.inp_qty.text() or "1"))
        cod = articulo.get("codigo", codigo)
        precio = float(articulo.get("precio", 0) or 0)

        for linea in self._lineas:
            if linea["codigo"] == cod:
                linea["cantidad"] += qty
                linea["subtotal"] = round(
                    linea["cantidad"]
                    * linea["precio"]
                    * (1 - linea["descuento_pct"] / 100),
                    2,
                )
                self._refresh_tabla()
                self.inp_sku.clear()
                self.inp_qty.setText("1")
                self.inp_sku.setFocus()
                return

        self._lineas.append(
            {
                "codigo": cod,
                "nombre": articulo.get("nombre", "—"),
                "seccion": articulo.get("seccion", ""),
                "cantidad": qty,
                "precio": precio,
                "descuento_pct": 0.0,
                "subtotal": round(qty * precio, 2),
                "iva": float(articulo.get("iva", 21) or 21),  # tipo de IVA del artículo
            }
        )
        self._refresh_tabla()
        self.inp_sku.clear()
        self.inp_qty.setText("1")
        self.inp_sku.setFocus()

    # ── Extras rápidos (bolsas / sobres de regalo / tarjeta regalo) ──────────────────────────────
    def _add_extra(self, codigo, nombre, precio, iva=21, seccion="EXTRAS", cantidad=1):
        """Añade (o incrementa en `cantidad`) una línea de un extra/producto al carrito. Si existe un
        artículo con ese código, toma su nombre/precio/IVA (para que la tienda pueda configurarlo)."""
        cantidad = max(1, int(cantidad or 1))
        try:
            art = obtener_articulo(codigo)
            if art:
                nombre = art.get("nombre", nombre)
                precio = float(art.get("precio", precio) or precio)
                iva = float(art.get("iva", iva) or iva)
        except Exception:
            pass
        precio = round(float(precio), 2)
        for l in self._lineas:
            if l["codigo"] == codigo:
                l["cantidad"] += cantidad
                l["subtotal"] = round(l["cantidad"] * l["precio"] * (1 - l["descuento_pct"] / 100), 2)
                self._refresh_tabla()
                self.inp_sku.setFocus()
                return
        self._lineas.append({
            "codigo": codigo, "nombre": nombre, "seccion": seccion, "cantidad": cantidad,
            "precio": precio, "descuento_pct": 0.0, "subtotal": round(precio * cantidad, 2),
            "iva": float(iva)})
        self._refresh_tabla()
        self.inp_sku.setFocus()

    def _add_extra_predef(self, codigo):
        ic, nombre, precio, iva = _EXTRAS_TPV[codigo]
        try:
            from src.services.tpv import extras_precios
            precio = extras_precios.obtener(codigo)   # precio editable (ventana "Precio bolsas")
        except Exception:
            pass
        self._add_extra(codigo, tr(f"tpv.extra_{codigo.lower()}", default=nombre), precio, iva,
                        seccion="EXTRAS")

    def _add_tarjeta_regalo(self):
        """Vende una tarjeta regalo: 1) escanea el código de barras de la tarjeta, 2) pide el importe a
        cargar, 3) la añade al carrito (IVA 0: se aplica al canjear). El código identifica la tarjeta
        (línea propia, no se fusiona con otras) para su validación futura al canjearla."""
        scan = _EscanearTarjetaDialog(self)
        if scan.exec() != QDialog.DialogCode.Accepted or not scan.codigo:
            return
        dlg = _ImporteTarjetaDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.importe > 0:
            nombre = tr("tpv.gift_card", default="Tarjeta regalo") + f"  ({scan.codigo})"
            # Código único por tarjeta → cada tarjeta es una línea independiente en el ticket.
            self._add_extra(f"TARJETA_REGALO-{scan.codigo}", nombre, dlg.importe, iva=0,
                            seccion="TARJETA_REGALO")

    def _abrir_acciones_avanzadas(self):
        """Abre la ventana emergente de ACCIONES AVANZADAS y, tras cerrarla, ejecuta la acción elegida
        con su lógica/flujo/diseño originales (sin anidar modales durante el cierre)."""
        dlg = _AccionesAvanzadasDialog(self, parent=self)
        dlg.exec()
        if getattr(dlg, "accion_elegida", None):
            dlg.accion_elegida()

    def _compra_personal(self):
        """Compra personal: valida el PIN de un empleado (distinto del cajero de esta caja) y aplica su
        % de descuento de personal a TODA la compra en curso."""
        dlg = _PinEmpleadoDialog(self, parent=self)
        if not dlg.exec() or not getattr(dlg, "empleado", None):
            return
        try:
            from src.db.descuentos import obtener_descuento_personal
            pct = float(obtener_descuento_personal())
        except Exception:
            pct = 0.0
        if pct <= 0 or not self._lineas:
            return
        for l in self._lineas:
            l["descuento_pct"] = pct
            l["subtotal"] = round(l["cantidad"] * l["precio"] * (1 - pct / 100), 2)
        self._refresh_tabla()

    def _aplicar_descuento_ultimo(self):
        """Aplica el descuento elegido (10/15/20/25/30/50 %) al ÚLTIMO artículo escaneado de la compra."""
        dlg = _AplicarDescuentoDialog(self, parent=self)
        if not dlg.exec() or dlg.pct is None or not self._lineas:
            return
        l = self._lineas[-1]
        l["descuento_pct"] = float(dlg.pct)
        l["subtotal"] = round(l["cantidad"] * l["precio"] * (1 - float(dlg.pct) / 100), 2)
        self._refresh_tabla()

    def _editar_descuento_personal(self):
        """Edita el % de descuento de personal (persistente). Solo admin/superadmin (doble control:
        el botón ya se oculta para otros perfiles)."""
        perfil = ((getattr(self, "usuario", None) or {}).get("perfil") or "").upper()
        if perfil not in ("ADMINISTRADOR", "SUPERADMIN", "SUPER_ADMIN"):
            return
        _EditarDescuentoPersonalDialog(self).exec()

    def _abrir_precio_bolsas(self):
        """Ventana de ajuste de precios de bolsas/sobres. Requiere ADMINISTRADOR o SUPERADMIN
        (por sesión, o introduciendo las credenciales de uno)."""
        perfiles_ok = ("ADMINISTRADOR", "SUPERADMIN", "SUPER_ADMIN")
        try:
            perfil = ((sesion_global.usuario_actual or {}).get("perfil") or "").upper()
        except Exception:
            perfil = ""
        if perfil not in perfiles_ok:
            dlg = _AutorizacionAdminDialog(self)
            if not (dlg.exec() and dlg.autorizado):
                return
        _PreciosBolsasDialog(self).exec()

    def agregar_lineas_externas(self, lineas):
        """Vuelca líneas de un pedido online a la cesta del TPV, APÉNDANDOLAS a lo que ya haya (no reemplaza).
        Se puede llamar en cualquier momento de la compra (haya o no artículos en la cesta). Reutiliza el
        formato de línea del carrito y refresca la tabla."""
        for l in (lineas or []):
            cod = l.get("codigo")
            if not cod:
                continue
            try:
                cant = max(1, int(float(l.get("cantidad") or 1)))
            except (TypeError, ValueError):
                cant = 1
            precio = round(float(l.get("precio") or 0), 2)
            iva = l.get("iva")
            if iva is None:
                try:
                    art = obtener_articulo(cod)
                    iva = float(art.get("iva")) if art and art.get("iva") is not None else 21.0
                except Exception:
                    iva = 21.0
            existente = next((x for x in self._lineas if x.get("codigo") == cod), None)
            if existente:
                existente["cantidad"] += cant
                existente["subtotal"] = round(
                    existente["cantidad"] * existente["precio"]
                    * (1 - existente.get("descuento_pct", 0) / 100), 2)
            else:
                self._lineas.append({
                    "codigo": cod, "nombre": l.get("nombre") or cod, "seccion": "ONLINE",
                    "cantidad": cant, "precio": precio, "descuento_pct": 0.0,
                    "subtotal": round(cant * precio, 2), "iva": float(iva)})
        try:
            self._refresh_tabla()
        except Exception:
            pass

    def _refresh_tabla(self):
        self.tabla.setRowCount(len(self._lineas))
        center = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
        right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight

        for row, l in enumerate(self._lineas):

            def _cell(
                txt, align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            ):
                it = QTableWidgetItem(txt)
                it.setTextAlignment(align)
                it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                return it

            self.tabla.setItem(row, 0, _cell(str(l["codigo"])))
            self.tabla.setItem(row, 1, _cell(l["nombre"]))
            self.tabla.setItem(row, 2, _cell(str(l["cantidad"]), center))
            self.tabla.setItem(
                row, 3, _cell(f"{divisas.formatear(l['precio'])}", right)
            )
            dto_txt = f"{l['descuento_pct']:.1f}%" if l["descuento_pct"] > 0 else "—"
            self.tabla.setItem(row, 4, _cell(dto_txt, center))
            self.tabla.setItem(
                row, 5, _cell(f"{divisas.formatear(l['subtotal'])}", right)
            )

            codigo_fila = l["codigo"]
            # Iconos dibujados con QPainter (QIcon), independientes de las fuentes.
            # _IconButton intercambia el color del icono en hover (cian→negro,
            # rojo→blanco) para que contraste con el fondo del hover.

            # Botón EDITAR (lápiz, cian → icono negro en hover)
            btn_edit = _IconButton(_icono_lapiz, _CIAN, "#0D1117", 20)
            btn_edit.setFixedSize(40, 40)
            btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn_edit.setStyleSheet(
                f"QPushButton{{background:{_BG2};border:2px solid {_CIAN};"
                f"border-radius:8px;outline:0px;}}"
                f"QPushButton:hover{{background:{_CIAN};}}"
                f"QPushButton:pressed{{background:#00CCA0;}}"
            )
            btn_edit.clicked.connect(
                lambda _=False, c=codigo_fila: self._editar_por_codigo(c)
            )

            # Botón BORRAR (papelera, rojo → icono blanco en hover) + confirmación
            btn_del = _IconButton(_icono_papelera, _ROJO, "#FFFFFF", 20)
            btn_del.setFixedSize(40, 40)
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn_del.setStyleSheet(
                f"QPushButton{{background:{_BG2};border:2px solid {_ROJO};"
                f"border-radius:8px;outline:0px;}}"
                f"QPushButton:hover{{background:{_ROJO};}}"
                f"QPushButton:pressed{{background:#CC0000;}}"
            )
            btn_del.clicked.connect(
                lambda _=False, c=codigo_fila: self._borrar_por_codigo(c)
            )

            cont_acc = QWidget()
            cont_acc.setStyleSheet("background:transparent;")
            hl_acc = QHBoxLayout(cont_acc)
            hl_acc.setContentsMargins(2, 2, 2, 2)
            hl_acc.setSpacing(8)
            hl_acc.addWidget(btn_edit)
            hl_acc.addWidget(btn_del)
            hl_acc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setCellWidget(row, 6, cont_acc)

        self._refresh_totales()

    # ─────────────────── i18n (re-traducción en caliente) ───────────────────
    def _retraducir(self):
        """Re-traduce la pantalla principal del TPV al idioma activo."""
        try:
            self.setWindowTitle(tr("tpv.title"))
            pares = [
                ("_lbl_titulo_tpv", "tpv.title"),
                ("_btn_add", "tpv.add"),
                ("_lbl_resumen", "tpv.summary"),
                ("btn_cobrar", "tpv.charge"),
                ("_lbl_acciones", "tpv.actions"),
            ]
            for attr, clave in pares:
                w = getattr(self, attr, None)
                if w is not None:
                    w.setText(tr(clave))
            # Tarjetas de acción (icono + texto debajo): re-traducir el texto.
            for clave, lbl in getattr(self, "_acc_labels", {}).items():
                lbl.setText(_solo_texto(tr(clave)))
            # Tarjetas inferiores + selector de cliente + toggle de barra lateral.
            for _at, _clave, _def in (
                ("_lbl_online", "tpv.online", "Venta online"),
                ("_lbl_stock", "tpv.show_stock", "Mostrar stock"),
                ("_lbl_mov", "tpv.cash_move", "Mov. efectivo"),
                ("_lbl_cajero", "tpv.cashier_change", "Cambio cajero"),
            ):
                _w = getattr(self, _at, None)
                if _w is not None:
                    _w.setText(_solo_texto(tr(_clave, default=_def)))
            self._refrescar_cliente_btn()
            if hasattr(self, "_btn_sidebar_toggle"):
                self._btn_sidebar_toggle.setText(
                    tr("tpv.hide_sidebar", default="OCULTAR")
                    if getattr(self, "_sidebar_visible", True)
                    else tr("tpv.show_sidebar", default="ACCIONES"))
            if hasattr(self, "inp_sku"):
                self.inp_sku.setPlaceholderText(tr("tpv.search_placeholder"))
            if hasattr(self, "tabla"):
                self.tabla.setHorizontalHeaderLabels(self._tpv_headers())
            # Totales dinámicos: recomputar en el nuevo idioma.
            if hasattr(self, "lbl_total"):
                self._refresh_totales()
            # Info de caja.
            caja = getattr(self, "_caja_actual", None)
            if caja:
                cid = caja.get("id", "?")
                resp = caja.get("responsable", "?")
                self.lbl_caja_top.setText(f"{cid}  ·  {resp}")
            elif hasattr(self, "lbl_caja_top"):
                self.lbl_caja_top.setText(tr("tpv.register_dash"))
        except Exception:
            pass

    def _refresh_totales(self):
        n = len(self._lineas)
        uds = sum(l["cantidad"] for l in self._lineas)
        subtotal_b = sum(l["cantidad"] * l["precio"] for l in self._lineas)
        total = sum(l["subtotal"] for l in self._lineas)
        descuento = subtotal_b - total

        self.lbl_n_items.setText(tr("tpv.items", n=n, uds=uds))
        self.lbl_subtotal.setText(tr("tpv.subtotal", x=divisas.formatear(subtotal_b)))
        self.lbl_dto.setText(
            tr("tpv.discount", x=divisas.formatear(descuento))
            if descuento > 0.005
            else tr("tpv.discount_zero")
        )
        self.lbl_total.setText(tr("tpv.total", x=divisas.formatear(total)))

        tiene = n > 0
        self.btn_cobrar.setEnabled(tiene)
        self.btn_retener.setEnabled(tiene)

        if not self._cd_result_mode:
            try:
                customer_display_bridge.cart_updated.emit(
                    list(self._lineas), round(total, 2), round(descuento, 2)
                )
            except Exception:
                pass

    def _editar_linea(self, index):
        row = index.row()
        if 0 <= row < len(self._lineas):
            dlg = _LineaEditDialog(self._lineas[row], self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._lineas[row] = dlg.get_linea()
                self._refresh_tabla()

    def _borrar_linea(self, row: int):
        if 0 <= row < len(self._lineas):
            self._lineas.pop(row)
            self._refresh_tabla()

    def _borrar_por_codigo(self, codigo):
        """Elimina la línea por código (estable aunque cambien los índices),
        previa confirmación del usuario."""
        for i, l in enumerate(self._lineas):
            if l.get("codigo") == codigo:
                if _confirmar(
                    self,
                    tr("tpv.del_item_title"),
                    tr("tpv.del_item_msg", nombre=l.get("nombre", codigo)),
                    txt_ok=tr("tpv.del_item_ok"),
                ):
                    self._lineas.pop(i)
                    self._refresh_tabla()
                return

    def _editar_por_codigo(self, codigo):
        """Edita la línea (cantidad / precio / descuento) por código."""
        for i, l in enumerate(self._lineas):
            if l.get("codigo") == codigo:
                dlg = _LineaEditDialog(l, self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    self._lineas[i] = dlg.get_linea()
                    self._refresh_tabla()
                return

    def _borrar_seleccionada(self):
        rows = sorted({idx.row() for idx in self.tabla.selectedIndexes()}, reverse=True)
        for row in rows:
            self._borrar_linea(row)

    def _vaciar(self):
        if not self._lineas:
            return
        if _confirmar(
            self,
            tr("tpv.empty_cart"),
            tr("tpv.empty_cart_msg"),
            txt_ok=tr("tpv.empty_cart_ok"),
        ):
            self._lineas = []
            self._refresh_tabla()
            customer_display_bridge.cart_cleared.emit()

    # ─────────────────── RETENER / RECUPERAR ─────────────────

    def _retener(self):
        if not self._lineas:
            return
        total = round(sum(l["subtotal"] for l in self._lineas), 2)
        lst = _leer_retenidas()
        lst.append(
            {
                "fecha": datetime.datetime.now().isoformat(),
                "empleado_id": self.empleado_id,
                "id_caja": self._id_caja,
                "lineas": list(self._lineas),
                "total": total,
            }
        )
        _guardar_retenidas(lst)
        self._lineas = []
        self._refresh_tabla()
        # Feedback NO modal: un QMessageBox.information() estático bloquea el
        # bucle modal sobre una ventana frameless+translúcida (en Windows aparece
        # invisible y sólo se cierra con ESC). Lo mostramos no-modal y autocerrable
        # para devolver el control al usuario de inmediato.
        self._toast(tr("tpv.held_title"), tr("tpv.held_msg"))

    def _msg(self, titulo: str, mensaje: str, nivel: str = "info"):
        """Aviso modal que NO se congela sobre la ventana frameless siempre-encima
        (usa el diálogo propio; QMessageBox nativo queda oculto y bloquea)."""
        try:
            from assets.estilo_global import mostrar_mensaje as _mm

            _mm(self, titulo, mensaje, nivel)
        except Exception:
            QMessageBox.warning(self, titulo, mensaje)

    def _toast(self, titulo: str, mensaje: str, ms: int = 1800):
        """Aviso breve, no modal, que se cierra solo y no captura el foco."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(titulo)
        box.setText(mensaje)
        box.setStandardButtons(QMessageBox.StandardButton.NoButton)
        box.setWindowModality(Qt.WindowModality.NonModal)
        box.show()
        QTimer.singleShot(ms, box.close)
        self.inp_sku.setFocus()

    def _recuperar(self):
        accion = "reemplazar"
        if self._lineas:
            accion = _elegir_recuperar(
                self,
                tr("tpv.recover_title", default="Recuperar venta"),
                tr(
                    "tpv.recover_msg",
                    default="Ya hay artículos en el carrito. ¿Qué quieres hacer con la venta recuperada?",
                ),
                tr("tpv.recover_add", default="SUMAR ARTÍCULOS"),
                tr("tpv.recover_replace", default="REEMPLAZAR"),
            )
            if accion is None:
                return

        dlg = _RetenidasDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            rec = dlg.get_recuperada()
            if rec:
                nuevas = rec.get("lineas", [])
                if accion == "sumar":
                    self._lineas = (self._lineas or []) + nuevas
                else:
                    self._lineas = nuevas
                self._refresh_tabla()

    def _abrir_buscar_tickets(self):
        """Búsqueda/reimpresión de tickets (QR/código de barras/nº/fecha/importe)."""
        _BuscarTicketDialog(parent=self).exec()

    def _abrir_gestion_pedidos_online(self):
        """Router (Fase WEB-08): el TPV solo ABRE el Portal Web para empleados. La gestión de pedidos
        online (antes `_GestionPedidosOnlineDialog`) es ahora el núcleo del Portal Web (`PortalWebHome`),
        accesible desde su navegación interna. El TPV no conoce la implementación del Portal Web."""
        try:
            from src.gui.portal_web_gui import PortalWebWindow
            self._portal_web_win = PortalWebWindow(
                empleado=getattr(self, "_empleado_tpv", None) or "—",
                id_caja=getattr(self, "_id_caja", None) or "—",
                parent=self,
            )
            self._portal_web_win.setWindowFlag(Qt.WindowType.Window)
            self._portal_web_win.showMaximized()
        except Exception as e:
            from assets.estilo_global import mostrar_mensaje as _mm
            _mm(self, tr("tpv.online", default="Venta online"),
                tr("portalweb.open_err", default="No se pudo abrir el Portal Web: {e}", e=e), "warning")

    def _abrir_venta_online(self):
        """Venta online desde tienda (F2): consulta de disponibilidad multi-origen,
        captura de cliente/envío y generación de pedido online."""
        _VentaOnlineDialog(
            empleado=getattr(self, "_empleado_tpv", None) or "—",
            id_caja=getattr(self, "_id_caja", None) or "—",
            parent=self,
        ).exec()

    def _seleccionar_cliente(self):
        """Selecciona/da de alta el cliente de la venta (o genérico)."""
        dlg = _ClienteDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._cliente = dlg.get_cliente()  # None = genérico
            self._refrescar_cliente_btn()

    def _refrescar_cliente_btn(self):
        if not hasattr(self, "btn_cliente"):
            return
        cli = getattr(self, "_cliente", None)
        # La tarjeta usa icono SVG 'people'; el texto va debajo, sin emoji.
        if cli:
            self.btn_cliente.setText(cli.get("nombre", ""))
        else:
            self.btn_cliente.setText(tr("tpv.cli_generic_short", default="Clientes"))

    # ─────────────────── FUNCIONES ENTERPRISE ────────────────

    def _abrir_rejilla_bakery(self):
        """Bakery: abre la rejilla de productos (botones grandes por familia) para venta rápida por unidad."""
        _RejillaProductosBakery(self, parent=self).exec()

    def _abrir_bascula(self):
        """Abre la venta a granel y añade la línea pesada al carrito."""
        dlg = _BasculaDialog(
            caja_id=getattr(self, "_id_caja", None) or "—",
            cajero=getattr(self, "_empleado_tpv", None) or "—",
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            linea = dlg.get_linea()
            if linea:
                self._lineas.append(linea)
                self._refresh_tabla()
                self.inp_sku.setFocus()

    def _abrir_devolucion(self):
        """Abre el flujo de devolución de tickets."""
        _DevolucionDialog(
            empleado=getattr(self, "_empleado_tpv", None) or "—",
            id_caja=getattr(self, "_id_caja", None) or "—",
            parent=self,
        ).exec()

    # (El autocobro ya NO se abre desde el TPV del cajero: es un terminal independiente que arranca por
    #  ROL de terminal. Ver src/services/tpv/terminal_rol.py y src/main.py / src/autocobro_app.py.)

    # ─────────────────── PAGO ────────────────────────────────

    def _realizar_pago(self):
        if not self._lineas:
            return
        # Verificar que la caja sigue activa sin re-lanzar el login
        if not self._id_caja:
            self._msg(tr("tpv.no_register_title"), tr("tpv.no_register_msg"), "warning")
            return
        est = _leer_estado_caja()
        caja = _caja_activa(est, self._empleado_tpv, self._empleado_id_tpv)
        if not caja:
            self._msg(
                tr("tpv.register_closed_title"),
                tr("tpv.register_closed_msg"),
                "warning",
            )
            return

        total = round(sum(l["subtotal"] for l in self._lineas), 2)
        dlg = _PagoDialog(total, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        resultado = dlg.get_resultado()
        if resultado:
            self._procesar_venta(resultado)

    def _procesar_venta(self, pago: dict):
        fecha = datetime.datetime.now()
        total = pago["total"]
        forma_pago = pago["forma_pago"]
        lineas = list(self._lineas)  # snapshot antes de limpiar

        try:
            n_caja = int(self._id_caja.split("-")[-1])
        except Exception:
            n_caja = 1

        cli = getattr(self, "_cliente", None) or {}
        # Aislamiento por tenant: la venta se registra bajo la empresa y la tienda
        # ACTIVAS (multitienda, Fase 3b.1).
        from src.db.empresa import empresa_actual_id, tienda_actual_id

        _id_empresa = empresa_actual_id()
        _id_tienda = tienda_actual_id()
        venta_id = None
        try:
            # P0 — RUTA CANÓNICA ÚNICA: delega la persistencia (y todas las integraciones:
            # Verifactu, contabilidad, kárdex, FEFO, stock_almacen, política M4) en
            # registrar_venta_con_items. NO se decrementa stock aquí (lo hace la ruta canónica).
            from src.db.conexion import registrar_venta_con_items

            items = [
                {
                    "codigo_articulo": l["codigo"],
                    "nombre": l.get("nombre"),
                    "seccion": l.get("seccion", ""),
                    "cantidad": l["cantidad"],
                    "precio_unitario": l["precio"],
                    "subtotal": l["subtotal"],
                    "peso_vendido": l.get("peso_vendido"),
                    "precio_kg": l.get("precio_kg"),
                    "modo_venta": l.get("modo_venta", "UNIDAD"),
                }
                for l in lineas
            ]
            venta_id = registrar_venta_con_items(
                items,
                fecha=fecha.strftime("%Y-%m-%d %H:%M:%S"),
                forma_pago=forma_pago,
                empleado_id=self._empleado_tpv
                or (str(self.empleado_id) if self.empleado_id else None),
                cliente=cli,
                numero_caja=n_caja,
                total=total,
                id_empresa=_id_empresa,
                id_tienda=_id_tienda,
            )
            if not venta_id:
                raise RuntimeError("registro de venta no devolvió id")
        except Exception as e:
            self._msg(tr("tpv.db_error_title"), tr("tpv.db_error_msg", e=e), "error")
            return

        # Señales de stock (la ruta canónica ya emite; reforzamos para refresco inmediato de UI)
        for l in lineas:
            try:
                stock_signals.stock_actualizado.emit(str(l["codigo"]))
            except Exception:
                pass

        # Actualizar fondo caja
        efectivo_neto = pago.get("efectivo_neto", 0.0)
        if efectivo_neto > 0.005:
            self._actualizar_fondo_caja(efectivo_neto)

        # Ticket PDF
        self._generar_ticket(venta_id, fecha, pago, lineas)

        # Auditoría
        _log_auditoria(
            {
                "ts": fecha.isoformat(),
                "tipo": "VENTA",
                "venta_id": venta_id,
                "total": total,
                "forma_pago": forma_pago,
                "empleado": self._empleado_tpv
                or (str(self.empleado_id) if self.empleado_id else None),
                "id_caja": self._id_caja,
                "lineas_count": len(lineas),
            }
        )

        # Customer display: mostrar pantalla de resultado
        self._cd_result_mode = True
        try:
            customer_display_bridge.sale_completed.emit(
                forma_pago, round(pago.get("cambio", 0.0), 2)
            )
        except Exception:
            pass
        QTimer.singleShot(8000, self._cd_clear_result_mode)

        # Limpiar carrito y volver a cliente genérico para la siguiente venta
        self._lineas = []
        self._cliente = None
        self._refrescar_cliente_btn()
        self._refresh_tabla()
        self.inp_sku.setFocus()

        cambio = pago.get("cambio", 0.0)
        msg_cambio = (
            tr("tpv.change_suffix", x=divisas.formatear(cambio))
            if cambio > 0.005
            else ""
        )
        # Feedback NO modal (evita el bloqueo de QMessageBox sobre ventana frameless)
        self._toast(
            tr("tpv.sale_done_title"),
            tr(
                "tpv.sale_done_msg",
                id=venta_id,
                total=divisas.formatear(total),
                fp=forma_pago.capitalize(),
                cambio=msg_cambio,
            ),
            ms=2200,
        )

        # Revalidar sin re-pedir login; si la caja fue cerrada mostrará la pantalla bloqueada
        self._verificar_caja_directa(self._empleado_tpv, self._empleado_id_tpv)

    def _actualizar_fondo_caja(self, importe: float):
        try:
            est = _leer_estado_caja()
            for c in est.get("cajas_activas", []):
                if c.get("id") == self._id_caja:
                    c["fondo"] = round(c.get("fondo", 0.0) + importe, 2)
                    break
            _guardar_estado_caja(est)
            caja = _caja_activa(est)
            if caja:
                self._refresh_caja_info(caja)
        except Exception as e:
            logger.error(f"Error actualizando fondo caja: {e}")

    def _generar_ticket(
        self, venta_id: int, fecha: datetime.datetime, pago: dict, lineas: list[dict]
    ):
        try:
            os.makedirs(_TICKETS_DIR, exist_ok=True)
            archivo = os.path.join(
                _TICKETS_DIR, f"ticket_{fecha.strftime('%Y%m%d_%H%M%S')}_{venta_id}.pdf"
            )
            from src.utils.impresion import generar_ticket_pdf
            from src.utils.ticket_data import construir_datos_ticket

            empleado = self._empleado_tpv or (
                str(self.empleado_id) if self.empleado_id else "—"
            )
            datos = construir_datos_ticket(
                venta_id=venta_id,
                fecha=fecha,
                id_caja=self._id_caja,
                empleado=empleado,
                lineas=lineas,
                pago=pago,
                copia=False,
                cliente=getattr(self, "_cliente", None),
            )
            generar_ticket_pdf(datos, archivo)
            # Centro documental: registrar el ticket con metadatos completos.
            try:
                from src.db import documentos as _docreg

                cli = getattr(self, "_cliente", None) or {}
                _docreg.registrar_documento(
                    archivo,
                    tipo="ticket",
                    referencia=(datos.get("operacion") or {}).get("ticket_num"),
                    cliente=cli.get("nombre") if isinstance(cli, dict) else None,
                    trabajador=empleado,
                    importe=pago.get("total"),
                )
            except Exception as _e:
                logger.debug(
                    "No se pudo registrar el ticket en el centro documental: %s", _e
                )
        except Exception as e:
            logger.warning(f"No se pudo generar el ticket PDF: {e}")
