"""Customer Display — Pantalla orientada al cliente para el TPV."""
from __future__ import annotations
from src.utils import divisas
from src.utils.i18n import tr

import os
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QColor, QGuiApplication, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.utils.customer_display_bridge import customer_display_bridge

_ROOT      = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_LOGO_PATH = os.path.join(_ROOT, "documentos", "logo_corporativo.png")

_BG   = "#080B10"
_BG2  = "#0E1117"
_BG3  = "#161B22"
_CIAN = "#00FFC6"
_TEXT = "#E6EDF3"
_DIM  = "#8B949E"
_GRDN = "#3FB950"
_LINE = "#21262D"
_FONT = "Segoe UI"

_MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

_WELCOME_MSGS = [
    "Bienvenido a nuestra tienda",
    "Gracias por elegirnos",
    "Transparencia total en cada compra",
    "Tu compra, actualizada en tiempo real",
    "Comprando con confianza",
]


def _fmt_date(dt: datetime) -> str:
    return f"{_DIAS[dt.weekday()].capitalize()}, {dt.day} de {_MESES[dt.month - 1]} de {dt.year}"


def _lbl(text: str = "", size: int = 14, bold: bool = False,
         color: str = _TEXT, align=Qt.AlignmentFlag.AlignLeft) -> QLabel:
    lb = QLabel(text)
    lb.setStyleSheet(
        f"color:{color};font-family:'{_FONT}';font-size:{size}px;"
        f"{'font-weight:900;' if bold else ''}background:transparent;"
    )
    lb.setAlignment(align)
    return lb


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: CustomerDisplayWindow | None = None


def get_customer_display() -> CustomerDisplayWindow | None:
    """Returns the singleton CustomerDisplayWindow only when a secondary screen exists."""
    global _instance
    screens = QGuiApplication.screens()
    if len(screens) < 2:
        return None
    if _instance is None:
        _instance = CustomerDisplayWindow()
    return _instance


# ── Window ─────────────────────────────────────────────────────────────────────

class CustomerDisplayWindow(QWidget):
    """Ventana fullscreen orientada al cliente, actualizada en tiempo real desde el TPV."""

    def __init__(self) -> None:
        super().__init__()
        self._msg_idx    = 0
        self._last_total = 0.0

        self._setup_window()
        self._build_ui()
        self._connect_bridge()

        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick_clock)
        self._clock.start(1000)
        self._tick_clock()

        self._msg_timer = QTimer(self)
        self._msg_timer.timeout.connect(self._rotate_message)
        self._msg_timer.start(6000)

        self._show_idle()

    # ── Window setup ───────────────────────────────────────────────────────────

    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setStyleSheet(f"QWidget{{background:{_BG};}}")

        screens = QGuiApplication.screens()
        primary = QGuiApplication.primaryScreen()
        target  = next((s for s in screens if s != primary), primary)
        self.setGeometry(target.geometry())

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("QStackedWidget{background:transparent;}")
        root.addWidget(self._stack)

        self._stack.addWidget(self._build_idle_page())    # 0
        self._stack.addWidget(self._build_sale_page())    # 1
        self._stack.addWidget(self._build_result_page())  # 2

    # ── IDLE PAGE ──────────────────────────────────────────────────────────────

    def _build_idle_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background:{_BG};")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        center = QVBoxLayout()
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.setSpacing(18)

        self._idle_logo = QLabel()
        self._idle_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._idle_logo.setStyleSheet("background:transparent;")
        self._idle_logo.setFixedSize(210, 210)
        self._load_logo(self._idle_logo, 210)
        center.addWidget(self._idle_logo)

        center.addWidget(_lbl(
            "SMART MANAGER", size=40, bold=True, color=_CIAN,
            align=Qt.AlignmentFlag.AlignCenter,
        ))

        center.addSpacing(6)
        sep_row = QHBoxLayout()
        sep_row.addStretch()
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedWidth(360)
        sep.setStyleSheet(f"background:{_LINE};max-height:1px;border:none;")
        sep_row.addWidget(sep)
        sep_row.addStretch()
        center.addLayout(sep_row)
        center.addSpacing(6)

        self._idle_clock = _lbl("", size=72, bold=True, color=_TEXT,
                                 align=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(self._idle_clock)

        self._idle_date = _lbl("", size=20, color=_DIM,
                                align=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(self._idle_date)

        center.addSpacing(14)
        self._idle_msg = _lbl(_WELCOME_MSGS[0], size=22, color=_DIM,
                               align=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(self._idle_msg)

        lay.addStretch(1)
        lay.addLayout(center)
        lay.addStretch(1)

        bottom = QWidget()
        bottom.setFixedHeight(52)
        bottom.setStyleSheet(f"background:{_BG2};border-top:1px solid {_LINE};")
        b_lay = QHBoxLayout(bottom)
        b_lay.setContentsMargins(32, 0, 32, 0)
        b_lay.addWidget(_lbl("Escanea tus artículos en la caja", size=15, color=_DIM))
        b_lay.addStretch()
        self._idle_btm_clock = _lbl("", size=15, color=_DIM,
                                    align=Qt.AlignmentFlag.AlignRight)
        b_lay.addWidget(self._idle_btm_clock)
        lay.addWidget(bottom)

        return page

    # ── SALE PAGE ──────────────────────────────────────────────────────────────

    def _build_sale_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background:{_BG};")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._build_sale_header())
        self._table = self._build_table()
        lay.addWidget(self._table, 1)
        lay.addWidget(self._build_summary())
        lay.addWidget(self._build_statusbar())

        return page

    def _build_sale_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setFixedHeight(82)
        hdr.setStyleSheet(f"background:{_BG2};border-bottom:2px solid {_CIAN};")
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(24, 10, 24, 10)
        lay.setSpacing(18)

        self._hdr_logo = QLabel()
        self._hdr_logo.setFixedSize(58, 58)
        self._hdr_logo.setStyleSheet("background:transparent;")
        self._load_logo(self._hdr_logo, 58)
        lay.addWidget(self._hdr_logo)

        lay.addWidget(
            _lbl("SMART MANAGER", size=22, bold=True, color=_CIAN,
                 align=Qt.AlignmentFlag.AlignCenter),
            1,
        )

        right = QVBoxLayout()
        right.setSpacing(2)
        right.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self._hdr_time = _lbl("", size=24, bold=True, color=_TEXT,
                               align=Qt.AlignmentFlag.AlignRight)
        self._hdr_date = _lbl("", size=13, color=_DIM,
                               align=Qt.AlignmentFlag.AlignRight)
        right.addWidget(self._hdr_time)
        right.addWidget(self._hdr_date)
        lay.addLayout(right)

        return hdr

    def _build_table(self) -> QTableWidget:
        tbl = QTableWidget()
        tbl.setColumnCount(4)
        tbl.setHorizontalHeaderLabels(["ARTÍCULO", "UDS.", "P. UNIT.", "SUBTOTAL"])
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tbl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tbl.verticalHeader().setVisible(False)
        tbl.setShowGrid(False)
        tbl.setAlternatingRowColors(True)

        hdr = tbl.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        tbl.setColumnWidth(1, 90)
        tbl.setColumnWidth(2, 130)
        tbl.setColumnWidth(3, 150)
        tbl.verticalHeader().setDefaultSectionSize(58)

        tbl.setStyleSheet(f"""
            QTableWidget {{
                background:{_BG};
                alternate-background-color:{_BG3};
                color:{_TEXT};
                font-family:'{_FONT}';
                font-size:19px;
                border:none;
                gridline-color:transparent;
            }}
            QHeaderView::section {{
                background:{_BG2};
                color:{_CIAN};
                font-family:'{_FONT}';
                font-size:14px;
                font-weight:900;
                border:none;
                border-bottom:2px solid {_LINE};
                padding:12px 14px;
            }}
            QTableWidget::item {{
                padding:0 14px;
                border-bottom:1px solid {_LINE};
            }}
        """)
        return tbl

    def _build_summary(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(148)
        w.setStyleSheet(f"background:{_BG2};border-top:2px solid {_LINE};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(32, 20, 32, 20)
        lay.setSpacing(0)

        left = QVBoxLayout()
        left.setSpacing(10)
        self._lbl_subtotal = _lbl("Subtotal: —", size=18, color=_DIM)
        self._lbl_dto      = _lbl("Descuento: —", size=18, color=_DIM)
        left.addWidget(self._lbl_subtotal)
        left.addWidget(self._lbl_dto)
        left.addStretch()
        lay.addLayout(left, 1)

        vsep = QFrame()
        vsep.setFrameShape(QFrame.Shape.VLine)
        vsep.setStyleSheet(f"color:{_LINE};background:{_LINE};max-width:1px;")
        lay.addWidget(vsep)
        lay.addSpacing(32)

        right = QVBoxLayout()
        right.setSpacing(2)
        right.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        right.addWidget(
            _lbl("TOTAL", size=15, bold=True, color=_DIM,
                 align=Qt.AlignmentFlag.AlignRight)
        )
        self._lbl_total = _lbl(divisas.formatear(0), size=52, bold=True, color=_CIAN,
                                align=Qt.AlignmentFlag.AlignRight)
        right.addWidget(self._lbl_total)
        lay.addLayout(right)

        return w

    def _build_statusbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(50)
        bar.setStyleSheet(f"background:{_BG2};border-top:1px solid {_LINE};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(32, 0, 32, 0)
        self._lbl_status = _lbl("Escanea un artículo para comenzar", size=14, color=_DIM)
        lay.addWidget(self._lbl_status)
        lay.addStretch()
        self._sale_btm_clock = _lbl("", size=14, color=_DIM,
                                    align=Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self._sale_btm_clock)
        return bar

    # ── RESULT PAGE ────────────────────────────────────────────────────────────

    def _build_result_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background:{_BG};")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        center = QVBoxLayout()
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.setSpacing(18)

        self._res_icon = _lbl("✓", size=110, bold=True, color=_GRDN,
                               align=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(self._res_icon)

        self._res_msg = _lbl("GRACIAS POR SU COMPRA", size=42, bold=True, color=_TEXT,
                              align=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(self._res_msg)

        center.addSpacing(10)

        self._res_total = _lbl("", size=28, color=_DIM,
                                align=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(self._res_total)

        self._res_cambio = _lbl("", size=38, bold=True, color=_CIAN,
                                 align=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(self._res_cambio)

        self._res_method = _lbl("", size=20, color=_DIM,
                                 align=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(self._res_method)

        lay.addStretch(1)
        lay.addLayout(center)
        lay.addStretch(1)

        bottom = QWidget()
        bottom.setFixedHeight(52)
        bottom.setStyleSheet(f"background:{_BG2};border-top:1px solid {_LINE};")
        b_lay = QHBoxLayout(bottom)
        b_lay.setContentsMargins(32, 0, 32, 0)
        b_lay.addStretch()
        b_lay.addWidget(_lbl("Hasta pronto · Smart Manager", size=15, color=_DIM,
                             align=Qt.AlignmentFlag.AlignCenter))
        b_lay.addStretch()
        lay.addWidget(bottom)

        return page

    # ── Bridge slots ───────────────────────────────────────────────────────────

    def _connect_bridge(self) -> None:
        customer_display_bridge.cart_updated.connect(self._on_cart_updated)
        customer_display_bridge.cart_cleared.connect(self._on_cart_cleared)
        customer_display_bridge.sale_completed.connect(self._on_sale_completed)
        customer_display_bridge.status_changed.connect(self._on_status_changed)

    @pyqtSlot(list, float, float)
    def _on_cart_updated(self, items: list, total: float, discount: float) -> None:
        self._last_total = total
        self._populate_table(items)

        subtotal = sum(l["cantidad"] * l["precio"] for l in items)
        self._lbl_subtotal.setText(f"Subtotal: {divisas.formatear(subtotal)}")

        if discount > 0.005:
            self._lbl_dto.setText(f"Ahorro: -{divisas.formatear(discount)}")
            self._lbl_dto.setStyleSheet(
                f"color:{_GRDN};font-family:'{_FONT}';font-size:18px;background:transparent;"
            )
        else:
            self._lbl_dto.setText(tr("cdisplay.descuento", default="Descuento: —"))
            self._lbl_dto.setStyleSheet(
                f"color:{_DIM};font-family:'{_FONT}';font-size:18px;background:transparent;"
            )

        self._lbl_total.setText(f"{divisas.formatear(total)}")
        n   = len(items)
        uds = sum(l["cantidad"] for l in items)
        self._lbl_status.setText(
            f"{n} artículo{'s' if n != 1 else ''}  ·  {uds} unidad{'es' if uds != 1 else ''}"
        )
        self._lbl_status.setStyleSheet(
            f"color:{_DIM};font-family:'{_FONT}';font-size:14px;background:transparent;"
        )
        self._stack.setCurrentIndex(1)

    @pyqtSlot()
    def _on_cart_cleared(self) -> None:
        self._last_total = 0.0
        self._table.setRowCount(0)
        self._show_idle()

    @pyqtSlot(str, float)
    def _on_sale_completed(self, forma_pago: str, cambio: float) -> None:
        self._show_result(forma_pago, cambio)
        QTimer.singleShot(7000, self._show_idle)

    @pyqtSlot(str, str)
    def _on_status_changed(self, message: str, level: str) -> None:
        colors = {"info": _DIM, "ok": _GRDN, "warn": "#E3B341", "error": "#FF4C4C"}
        self._lbl_status.setStyleSheet(
            f"color:{colors.get(level, _DIM)};font-family:'{_FONT}';"
            f"font-size:14px;background:transparent;"
        )
        self._lbl_status.setText(message)

    # ── Table population ───────────────────────────────────────────────────────

    def _populate_table(self, items: list) -> None:
        self._table.setRowCount(len(items))
        right  = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        center = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
        left   = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft

        for row, l in enumerate(items):
            def _cell(txt: str, align=left, bold: bool = False, color: str = _TEXT):
                it = QTableWidgetItem(txt)
                it.setTextAlignment(align)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                f = it.font()
                f.setFamily(_FONT)
                f.setPixelSize(19)
                f.setBold(bold)
                it.setFont(f)
                it.setForeground(QColor(color))
                return it

            self._table.setItem(row, 0, _cell(l["nombre"]))
            self._table.setItem(row, 1, _cell(str(l["cantidad"]), center, bold=True))
            self._table.setItem(row, 2, _cell(f"{divisas.formatear(l['precio'])}", right))
            dto_pct   = l.get("descuento_pct", 0)
            sub_color = _CIAN if dto_pct > 0 else _TEXT
            self._table.setItem(row, 3, _cell(f"{divisas.formatear(l['subtotal'])}", right, True, sub_color))

        if items:
            last = len(items) - 1
            for col in range(4):
                it = self._table.item(last, col)
                if it:
                    it.setBackground(QColor(0, 255, 198, 28))
            QTimer.singleShot(1800, lambda r=last: self._clear_row_bg(r))
            self._table.scrollToBottom()

    def _clear_row_bg(self, row: int) -> None:
        if row < self._table.rowCount():
            for col in range(4):
                it = self._table.item(row, col)
                if it:
                    it.setBackground(QColor(0, 0, 0, 0))

    # ── Result screen ──────────────────────────────────────────────────────────

    def _show_result(self, forma_pago: str, cambio: float) -> None:
        methods = {
            "efectivo": "Pago en efectivo",
            "tarjeta":  "Pago con tarjeta",
            "mixto":    "Pago mixto (efectivo + tarjeta)",
        }
        if forma_pago.lower() == "tarjeta":
            self._res_icon.setText("💳")
            self._res_icon.setStyleSheet(
                f"color:{_CIAN};font-size:96px;background:transparent;font-family:'{_FONT}';"
            )
        else:
            self._res_icon.setText("✓")
            self._res_icon.setStyleSheet(
                f"color:{_GRDN};font-size:110px;font-weight:900;background:transparent;"
                f"font-family:'{_FONT}';"
            )

        self._res_total.setText(f"Total: {divisas.formatear(self._last_total)}")
        if cambio > 0.005:
            self._res_cambio.setText(f"Cambio: {divisas.formatear(cambio)}")
            self._res_cambio.setVisible(True)
        else:
            self._res_cambio.setVisible(False)
        self._res_method.setText(methods.get(forma_pago.lower(), forma_pago.capitalize()))
        self._stack.setCurrentIndex(2)

    # ── Clock & carousel ───────────────────────────────────────────────────────

    def _tick_clock(self) -> None:
        now = datetime.now()
        t   = now.strftime("%H:%M:%S")

        self._idle_clock.setText(t)
        self._idle_date.setText(_fmt_date(now))
        self._idle_btm_clock.setText(t)

        if hasattr(self, "_hdr_time"):
            self._hdr_time.setText(now.strftime("%H:%M"))
            self._hdr_date.setText(now.strftime("%d/%m/%Y"))
        if hasattr(self, "_sale_btm_clock"):
            self._sale_btm_clock.setText(t)

    def _rotate_message(self) -> None:
        self._msg_idx = (self._msg_idx + 1) % len(_WELCOME_MSGS)
        self._idle_msg.setText(_WELCOME_MSGS[self._msg_idx])

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _show_idle(self) -> None:
        self._table.setRowCount(0)
        self._lbl_total.setText(divisas.formatear(0))
        self._lbl_subtotal.setText(tr("cdisplay.subtotal", default="Subtotal: —"))
        self._lbl_dto.setText(tr("cdisplay.descuento_2", default="Descuento: —"))
        self._lbl_dto.setStyleSheet(
            f"color:{_DIM};font-family:'{_FONT}';font-size:18px;background:transparent;"
        )
        self._lbl_status.setText(tr("cdisplay.escanea_un_articulo_para_com", default="Escanea un artículo para comenzar"))
        self._lbl_status.setStyleSheet(
            f"color:{_DIM};font-family:'{_FONT}';font-size:14px;background:transparent;"
        )
        self._stack.setCurrentIndex(0)

    def _load_logo(self, label: QLabel, size: int) -> None:
        if os.path.exists(_LOGO_PATH):
            pix = QPixmap(_LOGO_PATH)
            if not pix.isNull():
                label.setPixmap(
                    pix.scaled(size, size,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                )

    def keyPressEvent(self, event) -> None:
        pass  # Block all keyboard interaction on the customer display
