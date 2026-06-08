# src/gui/tpv.py
"""Terminal Punto de Venta (TPV) — Enterprise Edition"""
from __future__ import annotations

import datetime
import json
import logging
import os

from PyQt6.QtCore import QPointF, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QIntValidator,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.db.conexion import obtener_articulo, obtener_conexion, stock_signals
from src.db.usuario import listar_usuarios, sesion_global, validar_login_empleado
from src.utils import divisas, i18n
from src.utils.customer_display_bridge import customer_display_bridge
from src.utils.i18n import tr

logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTES DE ESTILO
# ============================================================

_BG    = "#0E1117"
_BG2   = "#161B22"
_CIAN  = "#00FFC6"
_ROJO  = "#FF4C4C"
_VERDE = "#3FB950"
_BORDE = "#30363D"
_TEXT  = "#E6EDF3"
_TEXT2 = "#8B949E"
_FONT  = "Segoe UI"

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LOGO_CORP_PATH  = os.path.join(_ROOT, "documentos", "logo_corporativo.png")
_CAJA_STATE_FILE = os.path.join(_ROOT, "documentos", "estado_caja.json")
_RETENIDAS_FILE  = os.path.join(_ROOT, "documentos", "tpv_retenidas.json")
_AUDIT_FILE      = os.path.join(_ROOT, "documentos", "tpv_auditoria.json")
_TICKETS_DIR     = os.path.join(_ROOT, "documentos", "Tickets")


# ============================================================
# HELPERS DE ESTILO
# ============================================================

def _lbl(text: str, bold: bool = False, size: int = 12, color: str = _TEXT) -> QLabel:
    lb = QLabel(text)
    lb.setStyleSheet(
        f"color:{color};font-family:'{_FONT}';font-size:{size}px;"
        f"font-weight:{'900' if bold else '500'};background:transparent;"
    )
    return lb


def _btn(
    text: str,
    color_bg:     str = _BG2,
    color_fg:     str = _TEXT,
    color_border: str = _BORDE,
    hover_bg:     str = _CIAN,
    hover_fg:     str = "#0D1117",
    h:            int = 38,
    radius:       int = 10,
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
        f"QFrame{{background:{_BG2};border:1px solid {_BORDE};"
        f"border-radius:14px;}}"
    )
    return f


def _sep() -> QFrame:
    s = QFrame()
    s.setFrameShape(QFrame.Shape.HLine)
    s.setStyleSheet(f"QFrame{{color:{_BORDE};background:{_BORDE};max-height:1px;border:none;}}")
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

    def X(f): return W * f
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
    return QIcon(pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation))


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

    def X(f): return W * f
    # Lápiz diagonal centrado en el cuadro (centro ~0.50, 0.50).
    # Cuerpo (rectángulo girado 45°)
    body = QPainterPath()
    body.moveTo(X(0.28), X(0.62))   # esquina interior junto a la punta
    body.lineTo(X(0.64), X(0.26))   # hacia el cabezal
    body.lineTo(X(0.76), X(0.38))   # ancho del lápiz en el cabezal
    body.lineTo(X(0.40), X(0.74))   # vuelta a la zona de la punta
    body.closeSubpath()
    p.drawPath(body)
    # Banda que separa cuerpo y cabezal
    p.drawLine(QPointF(X(0.56), X(0.34)), QPointF(X(0.68), X(0.46)))
    # Punta de la mina (triángulo lleno en la esquina inferior-izquierda)
    tip = QPainterPath()
    tip.moveTo(X(0.28), X(0.62))
    tip.lineTo(X(0.40), X(0.74))
    tip.lineTo(X(0.20), X(0.82))   # vértice de la punta
    tip.closeSubpath()
    p.setBrush(c)
    p.drawPath(tip)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.end()
    return QIcon(pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation))


class _IconButton(QPushButton):
    """Botón de icono dibujado que intercambia el color del icono en hover
    (Qt no recolorea un QIcon vía QSS, así que lo hacemos en enter/leaveEvent)."""

    def __init__(self, draw_fn, color_base: str, color_hover: str,
                 icon_px: int = 20, parent=None):
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


def _confirmar(parent, titulo: str, mensaje: str,
               txt_ok: str = "ACEPTAR", txt_cancel: str = "CANCELAR") -> bool:
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
    msg = _lbl(mensaje, size=13, color=_TEXT)
    msg.setWordWrap(True)
    v.addWidget(msg)
    v.addSpacing(4)
    fila = QHBoxLayout()
    fila.setSpacing(12)
    b_cancel = _btn(txt_cancel, h=44)
    b_cancel.clicked.connect(dlg.reject)
    b_ok = _btn(txt_ok, color_bg=_ROJO, color_fg="#FFFFFF", color_border=_ROJO,
                hover_bg="#FFFFFF", hover_fg=_ROJO, h=44)
    b_ok.clicked.connect(dlg.accept)
    fila.addWidget(b_cancel)
    fila.addWidget(b_ok)
    v.addLayout(fila)
    return dlg.exec() == QDialog.DialogCode.Accepted


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
    v.addWidget(_lbl("⚠  " + titulo, bold=True, size=16, color="#F1C40F"))
    msg = _lbl(mensaje, bold=True, size=14, color=_TEXT)  # Segoe UI Bold, +1pt
    msg.setWordWrap(True)
    v.addWidget(msg)
    v.addSpacing(4)
    b_ok = _btn("ENTENDIDO", color_bg="#F1C40F", color_fg="#0D1117",
                color_border="#F1C40F", hover_bg="#FFFFFF", hover_fg="#0D1117", h=46)
    b_ok.clicked.connect(dlg.accept)
    v.addWidget(b_ok)
    # Centrar sobre la pantalla
    try:
        scr = QApplication.primaryScreen().availableGeometry()
        dlg.adjustSize()
        dlg.move(scr.center().x() - dlg.width() // 2,
                 scr.center().y() - dlg.height() // 2)
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


def _caja_activa(est: dict, nombre_empleado: str = "") -> dict | None:
    """Devuelve la caja del empleado activo (por responsable), o la primera disponible.
    Retorna None si el TPV debe bloquearse."""
    estado = est.get("estado", "SIN_APERTURA")
    if estado not in ("PRIMERA_CAJA_ABIERTA", "OPERATIVA"):
        return None
    cajas = est.get("cajas_activas", [])
    if not cajas:
        return None
    if nombre_empleado:
        for c in cajas:
            if c.get("responsable", "") == nombre_empleado:
                return c
    return cajas[0]


def _cajas_de_empleado(est: dict, nombre_empleado: str) -> list:
    """Devuelve todas las cajas activas asignadas al empleado.
    Si no tiene ninguna asignada específicamente, devuelve todas las activas."""
    estado = est.get("estado", "SIN_APERTURA")
    if estado not in ("PRIMERA_CAJA_ABIERTA", "OPERATIVA"):
        return []
    cajas = est.get("cajas_activas", [])
    if not cajas:
        return []
    if nombre_empleado:
        asignadas = [c for c in cajas if c.get("responsable", "") == nombre_empleado]
        if asignadas:
            return asignadas
    return cajas


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
            cid   = caja.get("id", "?")
            resp  = caja.get("responsable", "?")
            fondo = float(caja.get("fondo", 0.0))
            btn = QPushButton(tr("sel_caja.caja_btn", cid=cid, resp=resp, fondo=divisas.formatear(fondo)))
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

        # Cabecera
        h = QLabel(tr("login_tpv.header"))
        h.setStyleSheet(
            f"color:{_CIAN};font-family:'{_FONT}';font-weight:900;font-size:20px;"
        )
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(h)

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
        col_der.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter)

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
            d.setStyleSheet(
                f"color:#30363D;font-size:28px;font-family:'{_FONT}';"
            )
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
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2),
            ("⌫", 3, 0), ("0", 3, 1),
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

        # Botón volver
        btn_cancel = QPushButton(tr("login_tpv.back_menu"))
        btn_cancel.setFixedHeight(40)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(
            f"QPushButton{{background:{_BG};color:{_ROJO};border:2px solid {_ROJO};"
            f"border-radius:8px;font-family:'{_FONT}';font-weight:900;font-size:13px;}}"
            f"QPushButton:hover{{background:{_ROJO};color:#FFF;}}"
        )
        btn_cancel.clicked.connect(self.reject)
        ly.addWidget(btn_cancel)

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
                d.setStyleSheet(
                    f"color:{_CIAN};font-size:26px;font-family:'{_FONT}';"
                )
            else:
                d.setText("○")
                d.setStyleSheet(
                    f"color:#30363D;font-size:26px;font-family:'{_FONT}';"
                )

    def _confirmar(self):
        if not self._nombre_empleado or len(self._pin) != self._PIN_LEN:
            return
        resultado = validar_login_empleado(self._nombre_empleado, self._pin)
        if resultado:
            self._nombre_empleado = (resultado.get("nombre") or self._nombre_empleado).upper()
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
            size=13, color=_TEXT2,
        )
        self.lbl_motivo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_motivo)

        self.btn_ir = _btn(
            tr("bloq.go_caja"),
            color_bg=_CIAN, color_fg="#0D1117", color_border=_CIAN,
            hover_bg="#FFFFFF", hover_fg="#0D1117", h=46,
        )
        self.btn_ir.setFixedWidth(260)
        lay.addWidget(self.btn_ir, alignment=Qt.AlignmentFlag.AlignCenter)

        self.btn_reintentar = _btn(tr("bloq.retry"), h=38)
        self.btn_reintentar.setFixedWidth(260)
        lay.addWidget(self.btn_reintentar, alignment=Qt.AlignmentFlag.AlignCenter)

        self.btn_menu = _btn(
            tr("bloq.back_menu"),
            color_fg=_ROJO, color_border=_ROJO,
            hover_bg=_ROJO, hover_fg="#FFF", h=38,
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
        lay.addWidget(_lbl(linea.get("nombre", tr("linea.default_name")), bold=True, size=13, color=_TEXT2))
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
            h.addWidget(_lbl(label, size=12))
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
        btn_cancel = _btn(tr("common.cancel"), color_fg=_ROJO, color_border=_ROJO, hover_bg=_ROJO, hover_fg="#FFF")
        btn_ok     = _btn(tr("common.accept"), color_bg=_VERDE, color_fg="#0D1117", color_border=_VERDE, hover_bg="#FFF", hover_fg="#0D1117")
        br.addWidget(btn_cancel)
        br.addStretch()
        br.addWidget(btn_ok)
        lay.addLayout(br)

        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._aceptar)

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

    def _aceptar(self):
        try:
            precio = float(self.inp_precio.text().replace(",", "."))
            dto    = float(self.inp_dto.text().replace(",", "."))
            if precio < 0 or not (0 <= dto <= 100):
                raise ValueError
            self._linea["cantidad"]      = self.spin_qty.value()
            self._linea["precio"]        = round(precio, 2)
            self._linea["descuento_pct"] = round(dto, 2)
            self._linea["subtotal"]      = round(
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

        lay.addWidget(_lbl(tr("retenidas.title"), bold=True, size=16))
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

        btn_cerrar = _btn(tr("common.close"))
        btn_cerrar.clicked.connect(self.reject)
        lay.addWidget(btn_cerrar)

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
            total     = r.get("total", 0.0)
            lineas    = r.get("lineas", [])

            header = QHBoxLayout()
            header.addWidget(_lbl(f"#{i+1}  {fecha_str}", bold=True))
            header.addStretch()
            header.addWidget(_lbl(f"{divisas.formatear(total)}", bold=True, color=_CIAN))
            cl.addLayout(header)

            resumen = ", ".join(f"{l['nombre']} x{l['cantidad']}" for l in lineas[:3])
            if len(lineas) > 3:
                resumen += tr("retenidas.more", n=len(lineas)-3)
            cl.addWidget(_lbl(resumen, size=11, color=_TEXT2))

            fila_btns = QHBoxLayout()
            btn_rec = _btn(tr("retenidas.recover"), color_bg=_CIAN, color_fg="#0D1117", color_border=_CIAN,
                           hover_bg="#FFF", hover_fg="#0D1117", h=30)
            btn_del = _btn(tr("retenidas.delete"), color_bg=_BG, color_fg=_ROJO, color_border=_ROJO,
                           hover_bg=_ROJO, hover_fg="#FFF", h=30)
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

class _PagoDialog(QDialog):
    def __init__(self, total: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("pago.title"))
        self.setFixedWidth(560)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("dlg_cobrar")
        self._drag_pos = None
        self._total     = total
        self._resultado: dict | None = None

        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _cuerpo = QFrame()
        _cuerpo.setObjectName("cuerpo_cobrar")
        _cuerpo.setStyleSheet(
            f"QFrame#cuerpo_cobrar{{background:{_BG};border:2px solid {_CIAN};"
            f"border-radius:22px;}}"
        )
        _outer.addWidget(_cuerpo)
        lay = QVBoxLayout(_cuerpo)
        lay.setSpacing(14)
        lay.setContentsMargins(28, 24, 28, 24)

        lay.addWidget(_lbl(tr("pago.total_label", x=divisas.formatear(total)), bold=True, size=18, color=_CIAN))
        lay.addWidget(_sep())

        # Tabs forma de pago
        tabs = QHBoxLayout()
        tabs.setSpacing(6)
        self._tab_btns = []
        for label in (tr("pago.tab_cash"), tr("pago.tab_card"), tr("pago.tab_mixed")):
            b = _btn(label, h=36)
            tabs.addWidget(b)
            self._tab_btns.append(b)
        lay.addLayout(tabs)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background:transparent;")
        self._stack.addWidget(self._panel_efectivo())
        self._stack.addWidget(self._panel_tarjeta())
        self._stack.addWidget(self._panel_mixto())
        lay.addWidget(self._stack)

        lay.addWidget(_sep())

        br = QHBoxLayout()
        btn_cancelar = _btn(tr("pago.cancel"), color_fg=_ROJO, color_border=_ROJO,
                            hover_bg=_ROJO, hover_fg="#FFF", h=42)
        self.btn_cobrar = _btn(tr("pago.charge"), color_bg=_VERDE, color_fg="#0D1117",
                               color_border=_VERDE, hover_bg="#FFF", hover_fg="#0D1117", h=42)
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

    # --- arrastre de ventana frameless ---
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
            f"border-radius:8px;padding:6px 12px;font-size:16px;font-family:'{_FONT}';}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}"
        )

        lay.addWidget(_lbl(tr("pago.amount_given"), size=12))
        self.inp_ef = QLineEdit("0.00")
        self.inp_ef.setStyleSheet(_inp_ss)
        self.inp_ef.textChanged.connect(self._actualizar_cambio)
        lay.addWidget(self.inp_ef)

        grid = QGridLayout()
        grid.setSpacing(6)
        for i, val in enumerate([5, 10, 20, 50, 100, 200]):
            b = _btn(f"{divisas.formatear(val)}", h=32)
            b.clicked.connect(lambda checked, v=float(val): self.inp_ef.setText(f"{v:.2f}"))
            grid.addWidget(b, i // 3, i % 3)
        lay.addLayout(grid)

        self.lbl_cambio = _lbl(tr("pago.change", x="0,00"), bold=True, size=13, color=_VERDE)
        lay.addWidget(self.lbl_cambio)
        self._actualizar_cambio()
        return w

    def _actualizar_cambio(self):
        try:
            entregado = float(self.inp_ef.text().replace(",", "."))
            cambio = entregado - self._total
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
        lay.addWidget(_lbl(tr("pago.card_amount", x=divisas.formatear(self._total)), bold=True, size=14))
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

        lay.addWidget(_lbl(tr("pago.mixed_total", x=divisas.formatear(self._total)), bold=True, size=14))

        fila = QHBoxLayout()
        fila.addWidget(_lbl(tr("pago.mixed_cash"), size=12))
        self.inp_mx_ef = QLineEdit("0.00")
        self.inp_mx_ef.setStyleSheet(_inp_ss)
        self.inp_mx_ef.textChanged.connect(self._actualizar_mixto)
        fila.addWidget(self.inp_mx_ef)
        lay.addLayout(fila)

        self.lbl_mx_tj     = _lbl(tr("pago.mixed_card", x="0,00"), size=12, color=_TEXT2)
        self.lbl_mx_cambio = _lbl(tr("pago.mixed_change", x="0,00"), bold=True, color=_VERDE)
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
            self.lbl_mx_cambio.setText(tr("pago.mixed_change", x=divisas.formatear(cambio)))
        except ValueError:
            pass

    # --- cobrar ---

    def _cobrar(self):
        idx = self._stack.currentIndex()

        if idx == 0:  # efectivo
            try:
                entregado = float(self.inp_ef.text().replace(",", "."))
            except ValueError:
                QMessageBox.warning(self, tr("pago.err_invalid_title"), tr("pago.err_invalid_msg"))
                return
            if entregado < self._total - 0.005:
                QMessageBox.warning(
                    self, tr("pago.err_insufficient_title"),
                    tr("pago.err_insufficient_msg", e=divisas.formatear(entregado), t=divisas.formatear(self._total))
                )
                return
            self._resultado = {
                "forma_pago":    "efectivo",
                "total":         self._total,
                "entregado":     round(entregado, 2),
                "cambio":        round(entregado - self._total, 2),
                "efectivo_neto": round(self._total, 2),
            }

        elif idx == 1:  # tarjeta
            self._resultado = {
                "forma_pago":    "tarjeta",
                "total":         self._total,
                "entregado":     self._total,
                "cambio":        0.0,
                "efectivo_neto": 0.0,
            }

        else:  # mixto
            try:
                ef = float(self.inp_mx_ef.text().replace(",", "."))
            except ValueError:
                QMessageBox.warning(self, tr("pago.err_invalid_title"), tr("pago.err_cash_msg"))
                return
            if ef < 0 or ef > self._total + 0.005:
                QMessageBox.warning(self, tr("pago.err_invalid_title"),
                                    tr("pago.err_cash_over"))
                return
            tj     = round(max(0.0, self._total - ef), 2)
            cambio = round(max(0.0, ef - self._total), 2)
            self._resultado = {
                "forma_pago":    "mixto",
                "total":         self._total,
                "entregado":     round(ef + tj, 2),
                "cambio":        cambio,
                "efectivo_neto": round(ef, 2),
                "tarjeta":       tj,
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
    """Venta a granel: producto + peso (báscula/manual) + total en vivo."""

    def __init__(self, caja_id: str = "—", cajero: str = "—", parent=None):
        super().__init__(parent)
        self._caja_id = caja_id
        self._cajero  = cajero
        self._producto_sel: dict | None = None
        self._linea_resultado: dict | None = None
        from src.services.tpv.scale_service import get_scale_manager
        self._scale = get_scale_manager()
        try:
            self._scale.detect_and_connect()
        except Exception:
            pass
        self.setWindowTitle(tr("bascula.title"))
        self.setModal(True)
        self.setMinimumSize(900, 640)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("dlg_bascula")
        self._drag_pos = None
        self._build_ui()
        self._cargar_productos()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()
        if self._scale.has_hardware:
            self._scale.start_polling(self._on_peso_hardware, interval_ms=300)

    def _build_ui(self):
        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _cuerpo = QFrame()
        _cuerpo.setObjectName("cuerpo_ventana")
        _cuerpo.setStyleSheet(
            f"QFrame#cuerpo_ventana{{background:{_BG};border:2px solid {_CIAN};"
            f"border-radius:24px;}}"
        )
        _outer.addWidget(_cuerpo)
        root = QVBoxLayout(_cuerpo)
        root.setContentsMargins(16, 14, 16, 16)
        root.setSpacing(12)
        cab = QFrame()
        cab.setStyleSheet(f"QFrame{{background:{_BG2};border:1px solid {_BORDE};border-radius:12px;}}")
        cl = QHBoxLayout(cab)
        cl.setContentsMargins(18, 12, 18, 12)
        cl.addWidget(_lbl(tr("bascula.header"), bold=True, size=20, color=_CIAN))
        cl.addStretch()
        self.lbl_info = _lbl(tr("bascula.info", caja=self._caja_id, cajero=self._cajero), size=12, color=_TEXT2)
        cl.addWidget(self.lbl_info)
        cl.addSpacing(16)
        self.lbl_reloj = _lbl("", size=12, color=_TEXT2)
        cl.addWidget(self.lbl_reloj)
        cl.addSpacing(16)
        self.btn_cfg = QPushButton(tr("bascula.edit_prices"))
        self.btn_cfg.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cfg.setFixedHeight(34)
        self.btn_cfg.setStyleSheet(
            f"QPushButton{{background:{_BG};color:{_TEXT2};border:1px solid {_BORDE};"
            f"border-radius:8px;font-family:'{_FONT}';font-weight:700;font-size:13px;padding:0 12px;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0D1117;border-color:{_CIAN};}}"
        )
        self.btn_cfg.clicked.connect(self._abrir_gestion)
        cl.addWidget(self.btn_cfg)
        root.addWidget(cab)

        body = QHBoxLayout()
        body.setSpacing(12)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"QScrollArea{{background:{_BG};border:1px solid {_BORDE};border-radius:12px;}}")
        self._grid_host = QWidget()
        self._grid_host.setStyleSheet("background:transparent;")
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(12, 12, 12, 12)
        self._grid.setSpacing(10)
        self._scroll.setWidget(self._grid_host)
        body.addWidget(self._scroll, 7)

        panel = QFrame()
        panel.setStyleSheet(f"QFrame{{background:{_BG2};border:1px solid {_BORDE};border-radius:12px;}}")
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
        btn_cerrar = _btn(tr("bascula.close"), color_fg=_ROJO, color_border=_ROJO, hover_bg=_ROJO, hover_fg="#FFF", h=40)
        btn_cerrar.clicked.connect(self.reject)
        pl.addWidget(btn_cerrar)
        body.addWidget(panel, 3)
        root.addLayout(body, 1)
        self._refrescar_modo()

    def _refrescar_modo(self):
        if self._scale.has_hardware:
            self.lbl_modo.setText(tr("bascula.mode_auto"))
            self.lbl_modo.setStyleSheet(f"color:{_VERDE};font-family:'{_FONT}';font-weight:900;font-size:11px;background:transparent;")
            self.spin_peso.setReadOnly(True)
        else:
            self.lbl_modo.setText(tr("bascula.mode_manual"))
            self.lbl_modo.setStyleSheet(f"color:{_TEXT2};font-family:'{_FONT}';font-weight:900;font-size:11px;background:transparent;")
            self.spin_peso.setReadOnly(False)

    def _cargar_productos(self):
        from src.services.tpv import bulk_products_service as B
        while self._grid.count():
            it = self._grid.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        productos = B.listar_productos_activos()
        if not productos:
            self._grid.addWidget(_lbl(tr("bascula.no_products"), size=14, color=_TEXT2), 0, 0)
            return
        cols = 3
        for idx, p in enumerate(productos):
            self._grid.addWidget(self._crear_boton_producto(p), idx // cols, idx % cols)

    def _crear_boton_producto(self, p: dict) -> QPushButton:
        emoji = p.get("emoji", "🛒")
        nombre = p.get("nombre", "—")
        precio = float(p.get("precio_kg", 0) or 0)
        btn = QPushButton(f"{emoji}\n{nombre}\n{divisas.formatear(precio)}/kg")
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
        self.lbl_precio_kg.setText(tr("bascula.price", x=divisas.formatear(float(p.get('precio_kg',0)))))
        self.btn_add.setEnabled(True)
        if not self._scale.has_hardware:
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
            self._scale.tare()
        except Exception:
            pass
        self.spin_peso.setValue(0.0)

    def _recalcular(self):
        from src.services.tpv import bulk_products_service as B
        if not self._producto_sel:
            self.lbl_total.setText(tr("bascula.total", x="0,00"))
            return
        total = B.calcular_total(self.spin_peso.value(), float(self._producto_sel.get("precio_kg", 0) or 0))
        self.lbl_total.setText(tr("bascula.total", x=divisas.formatear(total)))

    def _aceptar(self):
        from src.services.tpv import bulk_products_service as B
        if not self._producto_sel:
            _aviso_modal(self, tr("bascula.sel_product_title"),
                         tr("bascula.sel_product_msg"))
            return
        peso = self.spin_peso.value()
        ok, msg = B.validar_peso(peso)
        if not ok:
            # Ventana centrada con botón ENTENDIDO (no congela la UI).
            if peso <= 0:
                _aviso_modal(self, tr("bascula.weight_missing_title"),
                             tr("bascula.weight_missing_msg"))
            else:
                _aviso_modal(self, tr("bascula.weight_invalid_title"), msg)
            return
        precio = float(self._producto_sel.get("precio_kg", 0) or 0)
        total = B.calcular_total(peso, precio)
        nombre = self._producto_sel.get("nombre", "Granel")
        codigo = self._producto_sel.get("codigo_interno") or f"GRANEL-{self._producto_sel.get('id','')}"
        self._linea_resultado = {
            "codigo": codigo,
            "nombre": tr("bascula.line_name", nombre=nombre, peso=f"{peso:.3f}", precio=divisas.formatear(precio)),
            "seccion": self._producto_sel.get("categoria", "GRANEL"),
            "cantidad": 1, "precio": total, "descuento_pct": 0.0, "subtotal": total,
            "peso": peso, "precio_kg": precio, "modo_venta": "PESO",
        }
        self.accept()

    def get_linea(self) -> dict | None:
        return self._linea_resultado

    def _abrir_gestion(self):
        if not _es_gerente_o_admin():
            QMessageBox.warning(self, tr("bascula.perm_denied_title"),
                                tr("bascula.perm_denied_msg"))
            return
        _GestionGranelDialog(self).exec()
        self._cargar_productos()

    def _tick(self):
        self.lbl_reloj.setText(datetime.datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))

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

    def closeEvent(self, e):
        try:
            self._scale.stop_polling()
        except Exception:
            pass
        super().closeEvent(e)


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
        btn_nuevo = _btn(tr("ges_granel.new"), color_bg=_CIAN, color_fg="#0D1117", color_border=_CIAN, hover_bg="#FFF", h=38)
        btn_nuevo.clicked.connect(self._nuevo)
        cab.addWidget(btn_nuevo)
        root.addLayout(cab)
        self.tabla = QTableWidget()
        self.tabla.setColumnCount(5)
        self.tabla.setHorizontalHeaderLabels([
            tr("ges_granel.col_product"), tr("ges_granel.col_category"), tr("ges_granel.col_price"),
            tr("ges_granel.col_status"), tr("ges_granel.col_actions"),
        ])
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
        hh.resizeSection(1, 140); hh.resizeSection(2, 90); hh.resizeSection(3, 100); hh.resizeSection(4, 300)
        root.addWidget(self.tabla, 1)
        btn_cerrar = _btn(tr("common.close"), color_fg=_ROJO, color_border=_ROJO,
                          hover_bg=_ROJO, hover_fg="#FFFFFF", h=40)
        btn_cerrar.clicked.connect(self.accept)
        root.addWidget(btn_cerrar)

    def _cargar(self):
        from src.services.tpv import bulk_products_service as B
        productos = B.listar_todos()
        self.tabla.setRowCount(len(productos))
        for row, p in enumerate(productos):
            emoji = p.get("emoji", "🛒")
            self.tabla.setItem(row, 0, QTableWidgetItem(f"{emoji}  {p.get('nombre','—')}"))
            self.tabla.setItem(row, 1, QTableWidgetItem(p.get("categoria", "—")))
            it_precio = QTableWidgetItem(f"{float(p.get('precio_kg',0)):.2f}")
            it_precio.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(row, 2, it_precio)
            activo = bool(p.get("activo", 1))
            it_estado = QTableWidgetItem(tr("ges_granel.active") if activo else tr("ges_granel.inactive"))
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
            b_tog = QPushButton(tr("ges_granel.deactivate") if activo else tr("ges_granel.activate"))
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
        self.setWindowTitle(tr("ed_granel.title_edit") if p else tr("ed_granel.title_new"))
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
        col2.addWidget(_lbl(tr("ed_granel.price"), bold=True, size=12, color=_TEXT2))
        self.spin_precio = QDoubleSpinBox()
        self.spin_precio.setDecimals(3)
        self.spin_precio.setRange(0.0, 9999.0)
        self.spin_precio.setValue(float(self._p.get("precio_kg", 0)) if self._p else 0.0)
        self.spin_precio.setStyleSheet(
            f"QDoubleSpinBox{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:8px;font-size:14px;font-weight:900;}}"
            f"QDoubleSpinBox:focus{{border-color:{_CIAN};}}"
        )
        col2.addWidget(self.spin_precio)
        row.addLayout(col2)
        root.addLayout(row)
        root.addWidget(_lbl(tr("ed_granel.category"), bold=True, size=12, color=_TEXT2))
        self.cmb_cat = _ComboMaxPopup(max_items=5, item_h=44)
        self.cmb_cat.setEditable(True)
        self.cmb_cat.addItems(["FRUTA", "VERDURA", "FRUTOS SECOS", "DULCES", "FRESCOS", "CARNE", "PESCADO", "GENERAL"])
        # Mostrar pocas categorías a la vez para forzar la scrollbar.
        self.cmb_cat.setMaxVisibleItems(5)
        # Marcamos el combo para que el filtro global de estilos lo IGNORE
        # (si no, renombra la vista a _sm_combo_view y reemplaza nuestro QSS,
        # perdiéndose el borde 6px y la scrollbar inset).
        self.cmb_cat.setProperty("horario_cb", True)
        if self._p:
            self.cmb_cat.setCurrentText(self._p.get("categoria", "GENERAL"))
        self.cmb_cat.setStyleSheet(
            f"QComboBox{{background:{_BG2};color:{_TEXT};border:3px solid {_BORDE};"
            f"border-radius:8px;padding:8px;font-size:13px;}}"
        )
        # Popup: borde neón fino (1px) + scrollbar SIEMPRE visible. Con popup
        # translúcido en Windows, ScrollBarAsNeeded a veces no pinta el handle;
        # ScrollBarAlwaysOn + groove con fondo visible garantiza que se vea.
        # El padding-derecho deja sitio para la barra sin solapar el contorno.
        _view = self.cmb_cat.view()
        _view.setObjectName("cat_popup_view")
        _view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        _view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Scroll por píxel: evita el hueco vacío bajo el último item cuando el
        # viewport no es múltiplo exacto de la altura de item (con scroll por
        # item, al final quedaba un slot vacío).
        _view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        _view.setStyleSheet(
            f"QListView#cat_popup_view{{background:{_BG};color:{_TEXT};"
            f"border:2px solid {_CIAN};border-radius:20px;"
            f"padding:10px 6px 10px 12px;outline:0px;}}"
            f"QListView#cat_popup_view::item{{padding:10px 14px;border-radius:8px;}}"
            f"QListView#cat_popup_view::item:hover,"
            f"QListView#cat_popup_view::item:selected{{background:{_CIAN};color:#0D1117;}}"
            f"QListView#cat_popup_view QScrollBar:vertical{{"
            f"background:transparent;width:12px;margin:2px 0px;}}"
            f"QListView#cat_popup_view QScrollBar::handle:vertical{{background:{_CIAN};"
            f"min-height:24px;border-radius:6px;}}"
            f"QListView#cat_popup_view QScrollBar::add-line:vertical,"
            f"QListView#cat_popup_view QScrollBar::sub-line:vertical{{"
            f"border:none;background:none;width:0px;height:0px;}}"
            f"QListView#cat_popup_view QScrollBar::add-page:vertical,"
            f"QListView#cat_popup_view QScrollBar::sub-page:vertical{{background:transparent;}}"
        )
        root.addWidget(self.cmb_cat)
        root.addSpacing(6)
        botones = QHBoxLayout()
        b_cancel = _btn(tr("common.cancel"), color_fg=_ROJO, color_border=_ROJO, hover_bg=_ROJO, hover_fg="#FFF")
        b_cancel.clicked.connect(self.reject)
        b_guardar = _btn(tr("common.save"), color_bg=_VERDE, color_fg="#0D1117", color_border=_VERDE, hover_bg="#FFF")
        b_guardar.clicked.connect(self._guardar)
        botones.addWidget(b_cancel)
        botones.addWidget(b_guardar)
        root.addLayout(botones)

    def _guardar(self):
        from src.services.tpv import bulk_products_service as B
        ok, msg = B.guardar_producto(
            nombre=self.inp_nombre.text().strip(),
            precio_kg=self.spin_precio.value(),
            emoji=self.inp_emoji.text().strip() or "🛒",
            categoria=self.cmb_cat.currentText().strip().upper() or "GENERAL",
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
        b_cancel = _btn(tr("common.cancel"), color_fg=_ROJO, color_border=_ROJO, hover_bg=_ROJO, hover_fg="#FFF")
        b_cancel.clicked.connect(self.reject)
        b_ok = _btn(tr("autoriz.authorize"), color_bg=_VERDE, color_fg="#0D1117", color_border=_VERDE, hover_bg="#FFF")
        b_ok.clicked.connect(self._validar)
        bl.addWidget(b_cancel)
        bl.addWidget(b_ok)
        root.addLayout(bl)

    def _validar(self):
        from src.services.tpv import refund_service as R
        ok, res = R.verificar_autorizacion(self.inp_user.text().strip(), self.inp_pin.text())
        if ok:
            self.autorizador = res
            self.accept()
        else:
            QMessageBox.warning(self, tr("autoriz.err_title"), res)


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
        self.setMinimumSize(760, 600)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("dlg_devolucion")
        self._drag_pos = None
        self._build_ui()

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
        _outer.setContentsMargins(0, 0, 0, 0)
        _cuerpo = QFrame()
        _cuerpo.setObjectName("cuerpo_devolucion")
        _cuerpo.setStyleSheet(
            f"QFrame#cuerpo_devolucion{{background:{_BG};border:2px solid {_CIAN};"
            f"border-radius:22px;}}"
        )
        _outer.addWidget(_cuerpo)
        root = QVBoxLayout(_cuerpo)
        root.setContentsMargins(16, 14, 16, 16)
        root.setSpacing(12)
        root.addWidget(_lbl(tr("devol.header"), bold=True, size=20, color=_CIAN))
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
        b_buscar = _btn(tr("devol.search"), color_bg=_CIAN, color_fg="#0D1117", color_border=_CIAN, hover_bg="#FFF", h=40)
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
        self.tabla.setHorizontalHeaderLabels([
            tr("devol.col_return"), tr("devol.col_article"), tr("devol.col_sold"),
            tr("devol.col_price"), tr("devol.col_subtotal"),
        ])
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setStyleSheet(
            f"QTableWidget{{background:{_BG};color:{_TEXT};border:1px solid {_BORDE};"
            f"font-family:'{_FONT}';font-size:13px;gridline-color:{_BORDE};}}"
            f"QHeaderView::section{{background:{_BG2};color:{_TEXT2};border:none;"
            f"border-bottom:1px solid {_BORDE};padding:8px;font-weight:700;}}"
        )
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in (2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(0, 90); hh.resizeSection(2, 90); hh.resizeSection(3, 90); hh.resizeSection(4, 100)
        root.addWidget(self.tabla, 1)
        fila = QHBoxLayout()
        col_m = QVBoxLayout()
        col_m.addWidget(_lbl(tr("devol.reason_label"), bold=True, size=12, color=_TEXT2))
        self.inp_motivo = QLineEdit()
        self.inp_motivo.setPlaceholderText(tr("devol.reason_placeholder"))
        self.inp_motivo.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:8px;font-size:13px;}}QLineEdit:focus{{border-color:{_CIAN};}}"
        )
        col_m.addWidget(self.inp_motivo)
        fila.addLayout(col_m, 2)
        col_r = QVBoxLayout()
        col_r.addWidget(_lbl(tr("devol.refund_method"), bold=True, size=12, color=_TEXT2))
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
        b_cancel = _btn(tr("devol.close"), color_fg=_ROJO, color_border=_ROJO, hover_bg=_ROJO, hover_fg="#FFF", h=46)
        b_cancel.clicked.connect(self.reject)
        self.btn_procesar = QPushButton(tr("devol.process"))
        self.btn_procesar.setFixedHeight(46)
        self.btn_procesar.setEnabled(False)
        self.btn_procesar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_procesar.setStyleSheet(
            f"QPushButton{{background:{_VERDE};color:#0D1117;border:none;border-radius:12px;"
            f"font-family:'{_FONT}';font-weight:900;font-size:15px;}}"
            f"QPushButton:hover{{background:#FFF;}}"
            f"QPushButton:disabled{{background:#1C2128;color:#484F58;}}"
        )
        self.btn_procesar.clicked.connect(self._procesar)
        bl.addWidget(b_cancel, 1)
        bl.addWidget(self.btn_procesar, 2)
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
            self.lbl_estado.setText("⚠  " + self._eval.get("mensaje", tr("devol.not_found")))
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
            self.lbl_estado.setText(tr(
                "devol.status_ok", id=venta['id'], total=divisas.formatear(venta['total']),
                fp=venta['forma_pago'], limite=self._eval['fecha_limite'],
            ))
            self.lbl_estado.setStyleSheet(
                f"color:{_VERDE};background:{_BG2};border:1px solid {_VERDE};"
                f"border-radius:10px;padding:10px;font-family:'{_FONT}';font-weight:700;"
            )
            self.btn_procesar.setEnabled(True)
        else:
            self._mostrar_alerta_caducado(venta)
        self._cargar_items(venta)

    def _mostrar_alerta_caducado(self, venta):
        self.lbl_estado.setText(tr(
            "devol.status_expired", msg=self._eval['mensaje'], id=venta['id'],
            total=divisas.formatear(venta['total']), fecha=venta['fecha'], limite=self._eval['fecha_limite'],
        ))
        self.lbl_estado.setStyleSheet(
            f"color:{_ROJO};background:{_BG2};border:2px solid {_ROJO};"
            f"border-radius:10px;padding:12px;font-family:'{_FONT}';font-weight:900;"
        )
        self.btn_procesar.setEnabled(False)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr("devol.expired_box_title"))
        box.setText(tr("devol.expired_box_text"))
        box.setInformativeText(tr(
            "devol.expired_box_info", total=divisas.formatear(venta['total']),
            fecha=venta['fecha'], limite=self._eval['fecha_limite'],
        ))
        box.addButton(tr("devol.btn_cancel"), QMessageBox.ButtonRole.RejectRole)
        btn_auth = box.addButton(tr("devol.btn_request_auth"), QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        if box.clickedButton() == btn_auth:
            self._solicitar_autorizacion()

    def _solicitar_autorizacion(self):
        dlg = _AutorizacionDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.autorizador:
            self._autorizador = dlg.autorizador
            self.lbl_estado.setText(self.lbl_estado.text() + "\n" + tr("devol.authorized_by", nombre=self._autorizador))
            self.lbl_estado.setStyleSheet(
                f"color:{_CIAN};background:{_BG2};border:2px solid {_CIAN};"
                f"border-radius:10px;padding:12px;font-family:'{_FONT}';font-weight:900;"
            )
            self.btn_procesar.setEnabled(True)

    def _cargar_items(self, venta):
        from PyQt6.QtWidgets import QCheckBox
        items = venta.get("items", [])
        self.tabla.setRowCount(len(items))
        self._checks = []
        for row, it in enumerate(items):
            chk = QCheckBox()
            chk.setChecked(True)
            self._checks.append(chk)
            cont = QWidget()
            cont.setStyleSheet("background:transparent;")
            hl = QHBoxLayout(cont)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.addWidget(chk)
            hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setCellWidget(row, 0, cont)
            self.tabla.setItem(row, 1, QTableWidgetItem(str(it.get("nombre", "—"))))
            it_cant = QTableWidgetItem(str(it.get("cantidad", 0)))
            it_cant.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(row, 2, it_cant)
            it_pre = QTableWidgetItem(f"{divisas.formatear(float(it.get('precio_unitario',0)))}")
            it_pre.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabla.setItem(row, 3, it_pre)
            it_sub = QTableWidgetItem(f"{divisas.formatear(float(it.get('subtotal',0)))}")
            it_sub.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabla.setItem(row, 4, it_sub)

    def _procesar(self):
        from src.services.tpv import refund_service as R
        if not self._eval or not self._eval.get("existe"):
            return
        venta = self._eval["venta"]
        motivo = self.inp_motivo.text().strip()
        if not motivo:
            QMessageBox.warning(self, tr("devol.reason_required_title"), tr("devol.reason_required_msg"))
            return
        items = venta.get("items", [])
        seleccion = [items[i] for i, chk in enumerate(self._checks) if chk.isChecked()]
        if not seleccion:
            QMessageBox.warning(self, tr("devol.no_selection_title"), tr("devol.no_selection_msg"))
            return
        forma_reembolso = self.cmb_reembolso.currentData() or self.cmb_reembolso.currentText()
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
                QMessageBox.critical(self, tr("devol.terminal_title"),
                                     tr("devol.terminal_rejected", msg=res.mensaje))
                return
        requirio = not self._eval["dentro_plazo"]
        ok, msg, dev_id = R.procesar_devolucion(
            venta_id=venta["id"], items_devolver=seleccion, forma_reembolso=forma_reembolso,
            forma_pago_original=forma_original, empleado=self._empleado, numero_caja=self._id_caja,
            motivo=motivo, autorizado_por=self._autorizador, requirio_autorizacion=requirio,
        )
        if ok:
            for it in seleccion:
                try:
                    stock_signals.stock_actualizado.emit(str(it.get("codigo_articulo", "")))
                except Exception:
                    pass
            QMessageBox.information(self, tr("devol.refund_done_title"), msg)
            self.accept()
        else:
            QMessageBox.critical(self, tr("devol.error_title"), msg)



# ============================================================
# BLOQUE — VENTANA PRINCIPAL TPV
# ============================================================

class TPVWindow(QWidget):
    def __init__(self, empleado_id=None, main_window=None,
                 callback_vuelta=None, usuario=None, main=None, parent=None):
        super().__init__(parent)
        self.empleado_id      = empleado_id or (usuario or {}).get("id")
        self.main_window      = main
        self._callback_vuelta = callback_vuelta
        self._lineas: list[dict] = []
        self._id_caja: str | None = None
        self._empleado_tpv: str = ""
        self._auth_cancelled: bool = False  # login cancelado → _abrir_tpv_en_stack no muestra el TPV

        self.setWindowTitle(tr("tpv.title"))
        self.setStyleSheet(f"QWidget{{background:{_BG};}}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

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
        self._cd_result_mode   = False
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

    def _verificar_caja_directa(self, nombre_empleado: str):
        """Entra al TPV directamente sin mostrar el diálogo de login."""
        est  = _leer_estado_caja()
        caja = _caja_activa(est, nombre_empleado)
        if caja:
            self._id_caja      = caja.get("id", "CAJA-01")
            self._empleado_tpv = nombre_empleado
            self._stack.setCurrentIndex(1)
            self._refresh_caja_info(caja)
        else:
            self._id_caja      = None
            self._empleado_tpv = ""
            self._bloqueada.set_motivo(_motivo_bloqueo(est))
            self._stack.setCurrentIndex(0)

    def _verificar_caja(self):
        est    = _leer_estado_caja()
        estado = est.get("estado", "SIN_APERTURA")

        # Sin cajas operativas → pantalla bloqueada directamente
        if estado not in ("PRIMERA_CAJA_ABIERTA", "OPERATIVA") or not est.get("cajas_activas"):
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
        cajas = _cajas_de_empleado(est, nombre_empleado)

        if not cajas:
            self._id_caja = None
            self._empleado_tpv = ""
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

        self._id_caja      = caja.get("id", "CAJA-01")
        self._empleado_tpv = nombre_empleado
        self._stack.setCurrentIndex(1)
        self._refresh_caja_info(caja)

    def _tpv_refresh_logo(self):
        if os.path.exists(_LOGO_CORP_PATH):
            pix = QPixmap(_LOGO_CORP_PATH)
            if not pix.isNull():
                self.lbl_logo_tpv.setPixmap(
                    pix.scaled(120, 42, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                )
                return
        self.lbl_logo_tpv.setPixmap(QPixmap())

    def _volver_menu(self):
        # Si hay una venta en curso, avisar y no salir de golpe.
        if self._lineas:
            if not _confirmar(
                self, tr("tpv.exit_confirm_title"),
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

    def _ir_gestion_caja(self):
        self._cd_result_mode = False
        customer_display_bridge.cart_cleared.emit()
        if self._customer_display:
            self._customer_display.hide()
        if self._callback_vuelta:
            self._callback_vuelta()
        else:
            self.hide()
        if self.main_window and hasattr(self.main_window, "abrir_modulo_configuracion"):
            QTimer.singleShot(200, self.main_window.abrir_modulo_configuracion)

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
        body.setSpacing(10)
        body.addWidget(self._build_izq(), 6)
        body.addWidget(self._build_der(), 4)
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
        self.lbl_logo_tpv.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self._tpv_refresh_logo()
        lay.addWidget(self.lbl_logo_tpv)
        lay.addSpacing(2)

        self._lbl_titulo_tpv = _lbl(tr("tpv.title"), bold=True, size=15, color=_CIAN)
        lay.addWidget(self._lbl_titulo_tpv)
        lay.addStretch()

        self.lbl_caja_top = _lbl(tr("tpv.register_dash"), size=12, color=_TEXT2)
        lay.addWidget(self.lbl_caja_top)

        lay.addSpacing(20)
        self.lbl_reloj = _lbl("", size=12, color=_TEXT2)
        lay.addWidget(self.lbl_reloj)

        lay.addSpacing(16)
        self._btn_salir_tpv = btn_salir = QPushButton(tr("tpv.exit"))
        btn_salir.setFixedSize(110, 36)
        btn_salir.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_salir.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_salir.setStyleSheet(
            f"QPushButton{{background:{_ROJO};color:#FFF;border:none;outline:0px;"
            f"border-radius:8px;font-family:'{_FONT}';font-weight:900;font-size:13px;}}"
            f"QPushButton:hover{{background:#CC0000;color:#FFF;}}"
            f"QPushButton:focus{{outline:0px;border:none;}}"
        )
        btn_salir.clicked.connect(self._volver_menu)
        lay.addWidget(btn_salir)
        return bar

    def _build_izq(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(self._build_busqueda())
        lay.addWidget(self._build_numpad())
        lay.addWidget(self._build_tabla(), 1)
        return w

    def _build_busqueda(self) -> QFrame:
        card = _card()
        lay  = QHBoxLayout(card)
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
        lbl_x.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter)
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

        self._btn_add = btn_add = _btn(tr("tpv.add"), color_bg=_CIAN, color_fg="#0D1117",
                       color_border=_CIAN, hover_bg="#FFF", hover_fg="#0D1117", h=38)
        btn_add.clicked.connect(self._agregar)
        lay.addWidget(btn_add)
        return card

    def _build_numpad(self) -> QFrame:
        card = _card()
        gl = QGridLayout(card)
        gl.setContentsMargins(10, 8, 10, 8)
        gl.setSpacing(6)

        _ss_num = (
            f"QPushButton{{background:{_BG};color:{_TEXT};border:1px solid {_BORDE};"
            f"border-radius:8px;font-family:'{_FONT}';font-weight:900;font-size:15px;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0D1117;border-color:{_CIAN};}}"
        )
        _ss_fn = (
            f"QPushButton{{background:{_BG2};color:{_TEXT2};border:1px solid {_BORDE};"
            f"border-radius:8px;font-family:'{_FONT}';font-weight:700;font-size:12px;}}"
            f"QPushButton:hover{{background:#30363D;color:{_TEXT};}}"
        )
        _ss_enter = (
            f"QPushButton{{background:{_CIAN};color:#0D1117;border:none;"
            f"border-radius:8px;font-family:'{_FONT}';font-weight:900;font-size:13px;}}"
            f"QPushButton:hover{{background:#FFFFFF;color:#0D1117;}}"
        )
        _ss_del = (
            f"QPushButton{{background:{_BG2};color:{_ROJO};border:1px solid {_ROJO};"
            f"border-radius:8px;font-family:'{_FONT}';font-weight:900;font-size:14px;}}"
            f"QPushButton:hover{{background:{_ROJO};color:#FFF;}}"
        )

        H = 36
        layout_keys = [
            # (texto, fila, col, colspan, estilo_key)
            ("7",   0, 0, 1, "num"), ("8",   0, 1, 1, "num"), ("9",   0, 2, 1, "num"), ("⌫",  0, 3, 1, "del"),
            ("4",   1, 0, 1, "num"), ("5",   1, 1, 1, "num"), ("6",   1, 2, 1, "num"), ("C",  1, 3, 1, "fn"),
            ("1",   2, 0, 1, "num"), ("2",   2, 1, 1, "num"), ("3",   2, 2, 1, "num"),
            ("0",   3, 0, 2, "num"), (".",   3, 2, 1, "num"),
        ]

        for txt, row, col, span, sk in layout_keys:
            b = QPushButton(txt)
            b.setFixedHeight(H)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if sk == "num":
                b.setStyleSheet(_ss_num)
            elif sk == "del":
                b.setStyleSheet(_ss_del)
            else:
                b.setStyleSheet(_ss_fn)
            b.clicked.connect(lambda checked, t=txt: self._num_pulse(t))
            gl.addWidget(b, row, col, 1, span)

        # ENTER ocupa filas 2-3 en col 3
        btn_enter = QPushButton(tr("tpv.agregar", default="AGREGAR"))
        btn_enter.setFixedHeight(H * 2 + 6)
        btn_enter.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_enter.setStyleSheet(_ss_enter)
        btn_enter.clicked.connect(self._agregar)
        gl.addWidget(btn_enter, 2, 3, 2, 1)

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
            tr("tpv.col_code"), tr("tpv.col_name"), tr("tpv.col_qty"),
            tr("tpv.col_unit"), tr("tpv.col_disc"), tr("tpv.col_subtotal"),
            tr("tpv.col_actions"),
        ]

    def _build_tabla(self) -> QFrame:
        card = _card()
        lay  = QVBoxLayout(card)
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
        hh.resizeSection(0, 115)
        hh.resizeSection(2, 60)
        hh.resizeSection(3, 78)
        hh.resizeSection(4, 58)
        hh.resizeSection(5, 88)
        hh.resizeSection(6, 116)  # ACCIONES: editar (lápiz) + borrar (papelera)
        hh.setMinimumSectionSize(40)

        self.tabla.doubleClicked.connect(self._editar_linea)
        lay.addWidget(self.tabla)
        return card

    def _build_der(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # Resumen pedido
        card_res = _card()
        cl = QVBoxLayout(card_res)
        cl.setSpacing(6)
        cl.setContentsMargins(16, 14, 16, 14)
        self._lbl_resumen = _lbl(tr("tpv.summary"), bold=True, size=14)
        cl.addWidget(self._lbl_resumen)
        cl.addWidget(_sep())
        self.lbl_n_items  = _lbl(tr("tpv.items", n=0, uds=0), bold=True, size=14, color=_TEXT2)
        self.lbl_subtotal = _lbl(tr("tpv.subtotal", x="0,00"), bold=True, size=14, color=_TEXT2)
        self.lbl_dto      = _lbl(tr("tpv.discount_zero"), bold=True, size=14, color=_TEXT2)
        cl.addWidget(self.lbl_n_items)
        cl.addWidget(self.lbl_subtotal)
        cl.addWidget(self.lbl_dto)
        cl.addWidget(_sep())
        self.lbl_total = _lbl(tr("tpv.total", x="0,00"), bold=True, size=20, color=_CIAN)
        self.lbl_total.setAlignment(Qt.AlignmentFlag.AlignRight)
        cl.addWidget(self.lbl_total)
        lay.addWidget(card_res)

        # Botón COBRAR
        self.btn_cobrar = QPushButton(tr("tpv.charge"))
        self.btn_cobrar.setFixedHeight(62)
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
        lay.addWidget(self.btn_cobrar)

        # Acciones secundarias
        card_acc = _card()
        cl2 = QVBoxLayout(card_acc)
        cl2.setSpacing(6)
        cl2.setContentsMargins(12, 10, 12, 10)
        self._lbl_acciones = _lbl(tr("tpv.actions"), bold=True, size=12, color=_TEXT2)
        cl2.addWidget(self._lbl_acciones)

        # Funciones enterprise: báscula / devolución / autocobro
        self.btn_bascula = QPushButton(tr("tpv.scale"))
        self.btn_bascula.setFixedHeight(42)
        self.btn_bascula.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bascula.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_bascula.setStyleSheet(
            f"QPushButton{{background:{_BG2};color:{_CIAN};border:2px solid {_CIAN};"
            f"border-radius:10px;font-family:'{_FONT}';font-weight:900;font-size:14px;outline:0px;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0D1117;}}"
            f"QPushButton:focus{{outline:0px;border:2px solid {_CIAN};}}"
        )
        self.btn_bascula.clicked.connect(self._abrir_bascula)
        cl2.addWidget(self.btn_bascula)

        # El autocobro es una terminal independiente para clientes
        # (python -m src.autocobro_app); no aparece en el TPV del cajero.
        self.btn_devolucion = _btn(tr("tpv.refund"), h=36)
        self.btn_devolucion.clicked.connect(self._abrir_devolucion)
        cl2.addWidget(self.btn_devolucion)

        self.btn_retener   = _btn(tr("tpv.hold"), h=36)
        self.btn_recuperar = _btn(tr("tpv.recover"), h=36)
        self._btn_vaciar = btn_vaciar = _btn(tr("tpv.empty_cart"), color_fg=_ROJO, color_border=_ROJO,
                          hover_bg=_ROJO, hover_fg="#FFF", h=36)

        self.btn_retener.setEnabled(False)
        self.btn_retener.clicked.connect(self._retener)
        self.btn_recuperar.clicked.connect(self._recuperar)
        btn_vaciar.clicked.connect(self._vaciar)
        cl2.addWidget(self.btn_retener)
        cl2.addWidget(self.btn_recuperar)
        cl2.addWidget(btn_vaciar)
        lay.addWidget(card_acc)

        # Info caja activa
        card_cj = _card()
        cl3 = QVBoxLayout(card_cj)
        cl3.setSpacing(3)
        cl3.setContentsMargins(12, 8, 12, 8)
        self.lbl_caja_id   = _lbl(tr("tpv.register_dash"), bold=True, size=13, color=_TEXT2)
        self.lbl_caja_fondo = _lbl(tr("tpv.fund_dash"), bold=True, size=13, color=_TEXT2)
        cl3.addWidget(self.lbl_caja_id)
        cl3.addWidget(self.lbl_caja_fondo)
        lay.addWidget(card_cj)

        lay.addStretch()
        return w

    # ─────────────────── RELOJ / INFO CAJA ───────────────────

    def _tick(self):
        self.lbl_reloj.setText(datetime.datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))

    def _refresh_caja_info(self, caja: dict):
        cid   = caja.get("id", "?")
        resp  = caja.get("responsable", "?")
        fondo = caja.get("fondo", 0.0)
        self._caja_actual = caja  # guardado para re-traducción en caliente
        self.lbl_caja_top.setText(f"{cid}  ·  {resp}")
        self.lbl_caja_id.setText(tr("tpv.register", cid=cid, resp=resp))
        self.lbl_caja_fondo.setText(tr("tpv.fund", x=divisas.formatear(fondo)))
        self.inp_sku.setFocus()

    # ─────────────────── CARRITO ─────────────────────────────

    def _agregar(self):
        codigo = self.inp_sku.text().strip()
        if not codigo:
            return

        articulo = obtener_articulo(codigo)
        if not articulo:
            QMessageBox.warning(self, tr("tpv.not_found_title"),
                                tr("tpv.not_found_msg", codigo=codigo))
            self.inp_sku.selectAll()
            return

        qty    = max(1, int(self.inp_qty.text() or "1"))
        cod    = articulo.get("codigo", codigo)
        precio = float(articulo.get("precio", 0) or 0)

        for linea in self._lineas:
            if linea["codigo"] == cod:
                linea["cantidad"] += qty
                linea["subtotal"]  = round(
                    linea["cantidad"] * linea["precio"] * (1 - linea["descuento_pct"] / 100), 2
                )
                self._refresh_tabla()
                self.inp_sku.clear()
                self.inp_qty.setText("1")
                self.inp_sku.setFocus()
                return

        self._lineas.append({
            "codigo":       cod,
            "nombre":       articulo.get("nombre", "—"),
            "seccion":      articulo.get("seccion", ""),
            "cantidad":     qty,
            "precio":       precio,
            "descuento_pct": 0.0,
            "subtotal":     round(qty * precio, 2),
        })
        self._refresh_tabla()
        self.inp_sku.clear()
        self.inp_qty.setText("1")
        self.inp_sku.setFocus()

    def _refresh_tabla(self):
        self.tabla.setRowCount(len(self._lineas))
        center = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
        right  = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight

        for row, l in enumerate(self._lineas):
            def _cell(txt, align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft):
                it = QTableWidgetItem(txt)
                it.setTextAlignment(align)
                it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                return it

            self.tabla.setItem(row, 0, _cell(str(l["codigo"])))
            self.tabla.setItem(row, 1, _cell(l["nombre"]))
            self.tabla.setItem(row, 2, _cell(str(l["cantidad"]), center))
            self.tabla.setItem(row, 3, _cell(f"{divisas.formatear(l['precio'])}", right))
            dto_txt = f"{l['descuento_pct']:.1f}%" if l["descuento_pct"] > 0 else "—"
            self.tabla.setItem(row, 4, _cell(dto_txt, center))
            self.tabla.setItem(row, 5, _cell(f"{divisas.formatear(l['subtotal'])}", right))

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
            btn_edit.clicked.connect(lambda _=False, c=codigo_fila: self._editar_por_codigo(c))

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
            btn_del.clicked.connect(lambda _=False, c=codigo_fila: self._borrar_por_codigo(c))

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
                ("_lbl_titulo_tpv", "tpv.title"), ("_btn_salir_tpv", "tpv.exit"),
                ("_btn_add", "tpv.add"), ("_lbl_resumen", "tpv.summary"),
                ("btn_cobrar", "tpv.charge"), ("_lbl_acciones", "tpv.actions"),
                ("btn_bascula", "tpv.scale"), ("btn_devolucion", "tpv.refund"),
                ("btn_retener", "tpv.hold"), ("btn_recuperar", "tpv.recover"),
                ("_btn_vaciar", "tpv.empty_cart"),
            ]
            for attr, clave in pares:
                w = getattr(self, attr, None)
                if w is not None:
                    w.setText(tr(clave))
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
                fondo = caja.get("fondo", 0.0)
                self.lbl_caja_top.setText(f"{cid}  ·  {resp}")
                self.lbl_caja_id.setText(tr("tpv.register", cid=cid, resp=resp))
                self.lbl_caja_fondo.setText(tr("tpv.fund", x=divisas.formatear(fondo)))
            else:
                if hasattr(self, "lbl_caja_top"):
                    self.lbl_caja_top.setText(tr("tpv.register_dash"))
                if hasattr(self, "lbl_caja_id"):
                    self.lbl_caja_id.setText(tr("tpv.register_dash"))
                if hasattr(self, "lbl_caja_fondo"):
                    self.lbl_caja_fondo.setText(tr("tpv.fund_dash"))
        except Exception:
            pass

    def _refresh_totales(self):
        n           = len(self._lineas)
        uds         = sum(l["cantidad"] for l in self._lineas)
        subtotal_b  = sum(l["cantidad"] * l["precio"] for l in self._lineas)
        total       = sum(l["subtotal"] for l in self._lineas)
        descuento   = subtotal_b - total

        self.lbl_n_items.setText(tr("tpv.items", n=n, uds=uds))
        self.lbl_subtotal.setText(tr("tpv.subtotal", x=divisas.formatear(subtotal_b)))
        self.lbl_dto.setText(
            tr("tpv.discount", x=divisas.formatear(descuento)) if descuento > 0.005
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
                    self, tr("tpv.del_item_title"),
                    tr("tpv.del_item_msg", nombre=l.get('nombre', codigo)),
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
        if _confirmar(self, tr("tpv.empty_cart"),
                      tr("tpv.empty_cart_msg"),
                      txt_ok=tr("tpv.empty_cart_ok")):
            self._lineas = []
            self._refresh_tabla()
            customer_display_bridge.cart_cleared.emit()

    # ─────────────────── RETENER / RECUPERAR ─────────────────

    def _retener(self):
        if not self._lineas:
            return
        total = round(sum(l["subtotal"] for l in self._lineas), 2)
        lst   = _leer_retenidas()
        lst.append({
            "fecha":       datetime.datetime.now().isoformat(),
            "empleado_id": self.empleado_id,
            "id_caja":     self._id_caja,
            "lineas":      list(self._lineas),
            "total":       total,
        })
        _guardar_retenidas(lst)
        self._lineas = []
        self._refresh_tabla()
        # Feedback NO modal: un QMessageBox.information() estático bloquea el
        # bucle modal sobre una ventana frameless+translúcida (en Windows aparece
        # invisible y sólo se cierra con ESC). Lo mostramos no-modal y autocerrable
        # para devolver el control al usuario de inmediato.
        self._toast(tr("tpv.held_title"), tr("tpv.held_msg"))

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
        if self._lineas:
            if not _confirmar(
                self, "Recuperar venta",
                "Hay artículos en el carrito. ¿Deseas reemplazarlos?",
                txt_ok="REEMPLAZAR",
            ):
                return

        dlg = _RetenidasDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            rec = dlg.get_recuperada()
            if rec:
                self._lineas = rec.get("lineas", [])
                self._refresh_tabla()

    # ─────────────────── FUNCIONES ENTERPRISE ────────────────

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

    # ─────────────────── PAGO ────────────────────────────────

    def _realizar_pago(self):
        if not self._lineas:
            return
        # Verificar que la caja sigue activa sin re-lanzar el login
        if not self._id_caja:
            QMessageBox.warning(self, tr("tpv.no_register_title"),
                                tr("tpv.no_register_msg"))
            return
        est  = _leer_estado_caja()
        caja = _caja_activa(est, self._empleado_tpv)
        if not caja:
            QMessageBox.warning(self, tr("tpv.register_closed_title"),
                                tr("tpv.register_closed_msg"))
            return

        total = round(sum(l["subtotal"] for l in self._lineas), 2)
        dlg   = _PagoDialog(total, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        resultado = dlg.get_resultado()
        if resultado:
            self._procesar_venta(resultado)

    def _procesar_venta(self, pago: dict):
        fecha      = datetime.datetime.now()
        total      = pago["total"]
        forma_pago = pago["forma_pago"]
        lineas     = list(self._lineas)  # snapshot antes de limpiar

        try:
            n_caja = int(self._id_caja.split("-")[-1])
        except Exception:
            n_caja = 1

        venta_id = None
        try:
            with obtener_conexion() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO ventas (fecha, total, forma_pago, empleado, numero_caja) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (
                            fecha.strftime("%Y-%m-%d %H:%M:%S"),
                            total,
                            forma_pago,
                            self._empleado_tpv or (str(self.empleado_id) if self.empleado_id else None),
                            n_caja,
                        ),
                    )
                    venta_id = cur.lastrowid

                    for l in lineas:
                        cur.execute(
                            "INSERT INTO venta_items "
                            "(venta_id, codigo_articulo, nombre, seccion, cantidad, precio_unitario, subtotal) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            (venta_id, l["codigo"], l["nombre"], l.get("seccion", ""),
                             l["cantidad"], l["precio"], l["subtotal"]),
                        )

                    for l in lineas:
                        cur.execute(
                            "UPDATE articulos "
                            "SET Stock_tienda = GREATEST(0, Stock_tienda - %s) "
                            "WHERE codigo = %s",
                            (l["cantidad"], l["codigo"]),
                        )

                conn.commit()

        except Exception as e:
            QMessageBox.critical(self, tr("tpv.db_error_title"),
                                 tr("tpv.db_error_msg", e=e))
            return

        # Señales de stock
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
        _log_auditoria({
            "ts":           fecha.isoformat(),
            "tipo":         "VENTA",
            "venta_id":     venta_id,
            "total":        total,
            "forma_pago":   forma_pago,
            "empleado":     self._empleado_tpv or (str(self.empleado_id) if self.empleado_id else None),
            "id_caja":      self._id_caja,
            "lineas_count": len(lineas),
        })

        # Customer display: mostrar pantalla de resultado
        self._cd_result_mode = True
        try:
            customer_display_bridge.sale_completed.emit(
                forma_pago, round(pago.get("cambio", 0.0), 2)
            )
        except Exception:
            pass
        QTimer.singleShot(8000, self._cd_clear_result_mode)

        # Limpiar carrito
        self._lineas = []
        self._refresh_tabla()
        self.inp_sku.setFocus()

        cambio = pago.get("cambio", 0.0)
        msg_cambio = tr("tpv.change_suffix", x=divisas.formatear(cambio)) if cambio > 0.005 else ""
        # Feedback NO modal (evita el bloqueo de QMessageBox sobre ventana frameless)
        self._toast(
            tr("tpv.sale_done_title"),
            tr("tpv.sale_done_msg", id=venta_id, total=divisas.formatear(total),
               fp=forma_pago.capitalize(), cambio=msg_cambio),
            ms=2200,
        )

        # Revalidar sin re-pedir login; si la caja fue cerrada mostrará la pantalla bloqueada
        self._verificar_caja_directa(self._empleado_tpv)

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

    def _generar_ticket(self, venta_id: int, fecha: datetime.datetime,
                        pago: dict, lineas: list[dict]):
        try:
            os.makedirs(_TICKETS_DIR, exist_ok=True)
            archivo = os.path.join(
                _TICKETS_DIR,
                f"ticket_{fecha.strftime('%Y%m%d_%H%M%S')}_{venta_id}.pdf"
            )
            from src.utils.impresion import generar_ticket_pdf
            datos = {
                "fecha":      fecha.strftime("%d/%m/%Y %H:%M:%S"),
                "venta_id":   venta_id,
                "caja":       self._id_caja,
                "empleado":   str(self.empleado_id) if self.empleado_id else "—",
                "forma_pago": pago["forma_pago"].capitalize(),
                "items":      [
                    {"nombre": l["nombre"], "cantidad": l["cantidad"],
                     "precio": l["precio"], "subtotal": l["subtotal"]}
                    for l in lineas
                ],
                "total":  pago["total"],
                "cambio": pago.get("cambio", 0.0),
            }
            generar_ticket_pdf(datos, archivo)
        except Exception as e:
            logger.warning(f"No se pudo generar el ticket PDF: {e}")
