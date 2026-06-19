"""
Widgets RRHH de horarios, turnos y ausencias (F3.0.2).

Clases EXTRAÍDAS VERBATIM desde gui/gestion_usuarios.py (mover + shim): mismo
código, señales, estilos y nombres. Las dependencias compartidas (constantes,
helpers y widgets del módulo original) se importan de forma diferida al final
para romper el ciclo de imports sin duplicar lógica.
"""

import json
import math
import os
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBitmap,
    QColor,
    QCursor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCalendarWidget,  # Añadir QTimeEdit y QCalendarWidget (Ya estaban)
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,  # <-- ¡Añadir esta importación!
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProxyStyle,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedLayout,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleFactory,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from assets.estilo_global import (
    mostrar_confirmacion,
    mostrar_mensaje,
)
from src.db.conexion import guardar_referencia, obtener_referencias
from src.db.usuario import (
    cambiar_password_usuario,
    crear_perfil,
    eliminar_usuario,
    listar_fichajes,
    listar_usuarios,
    obtener_fichaje_abierto,
    registrar_entrada,
    registrar_salida,
    sesion_global,
    validar_pin_fichaje,
)
from src.db import devoluciones_baneados
from src.utils import divisas, i18n, pdf_fonts
from src.utils.i18n import tr
from src.utils.logger import LOG_DOCUMENTOS


class _HorarioComboBox(QComboBox):
    """QComboBox for HORARIO table cells.
    Defers ALL popup setup (view(), delegate, container fix) to first showPopup() call
    so that build time is not affected by expensive QListView creation."""

    # Class-level Fusion style — prevents GC (Qt does not take ownership).
    # Setting Fusion on the combo box makes Qt query SH_ComboBox_Popup → False,
    # so QComboBoxPrivateScroller (the ▲/▼ arrow button widgets) are never created.
    _fusion_style = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_ready = False
        self.setProperty("horario_cb", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if _HorarioComboBox._fusion_style is None:
            _HorarioComboBox._fusion_style = QStyleFactory.create("Fusion")
        self.setStyle(_HorarioComboBox._fusion_style)
        self.setMaxVisibleItems(7)

    def showPopup(self):
        if not self._popup_ready:
            self._popup_ready = True
            view = self.view()
            # Set viewport background explicitly — QAbstractScrollArea's viewport
            # is a plain QWidget that won't inherit background unless told to.
            vp = view.viewport()
            vp.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            vp.setStyleSheet("background:#0D1117;")
            view.setFrameShape(QFrame.Shape.NoFrame)
            view.setItemDelegate(_RoundedItemDelegate(self))
            container = view.parent()
            if isinstance(container, QWidget) and container is not self:
                container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                container.setWindowFlags(
                    container.windowFlags()
                    | Qt.WindowType.FramelessWindowHint
                    | Qt.WindowType.NoDropShadowWindowHint
                )
        super().showPopup()
        # Make the popup invisible (opacity=0) so Qt's default position (possibly
        # above the combo) never appears on screen. Unlike hide(), this keeps the
        # window in the compositor so layout/size calculations remain valid.
        # _fix_popup will reposition and restore opacity to 1.
        _v = self.view()
        if _v is not None:
            _p = _v.window()
            if _p is not self:
                _p.setWindowOpacity(0.0)
        QTimer.singleShot(0, self._fix_popup)

    def _fix_popup(self):
        view = self.view()
        if view is None:
            return
        popup = view.window()
        if popup is self:
            return
        # Remove the frame that QComboBoxPrivateContainer inherits from QFrame —
        # its lineWidth contributes a visual inset at top/bottom of the popup.
        if hasattr(popup, "setFrameShape"):
            popup.setFrameShape(QFrame.Shape.NoFrame)
            popup.setLineWidth(0)
            popup.setMidLineWidth(0)
        popup.setAutoFillBackground(False)
        popup.setStyleSheet("background: transparent;")
        popup.setContentsMargins(0, 0, 0, 0)
        if popup.layout() is not None:
            popup.layout().setContentsMargins(0, 0, 0, 0)
            popup.layout().setSpacing(0)
        # QComboBoxPrivateScroller is a plain QWidget (NOT QAbstractButton).
        # Iterate direct children of the container and zero-size / hide any widget
        # that is not the list view — these are the ▲/▼ scroller arrow widgets.
        for _child in popup.children():
            if isinstance(_child, QWidget) and _child is not view:
                _child.setFixedSize(0, 0)
                _child.hide()

        # Set the view's appearance directly so it doesn't inherit from the combobox
        # QAbstractItemView propagated rule (which would cause a double border at top).
        view.setStyleSheet(
            "QAbstractItemView{"
            "background:#0D1117;border:2px solid #00FFC6;"
            "border-radius:8px;outline:none;}"
            # Barra más fina (6px) porque estos popups (horas/min) son estrechos.
            "QScrollBar:vertical{background:transparent;width:6px;margin:2px 0px;}"
            "QScrollBar::handle:vertical{background:#00FFC6;min-height:20px;border-radius:3px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{"
            "border:none;background:none;width:0px;height:0px;}"
            "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}"
        )
        # Disable auto-scroll: prevents the list from scrolling when the cursor
        # hovers near the top/bottom edge of the popup.
        view.setAutoScroll(False)
        # Cap popup to 5 visible items; force scrollbar so the user can scroll.
        # _RoundedItemDelegate.sizeHint returns height=38 per item.
        # Add 4px for the view's 2px QSS border (top + bottom) so all 5 rows fit.
        _item_h = view.sizeHintForRow(0) if self.count() > 0 else 38
        _max_view_h = 5 * _item_h + 4
        if view.height() > _max_view_h or self.count() > 5:
            view.setFixedHeight(_max_view_h)
            popup.resize(popup.width(), _max_view_h)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        # Scroll por píxel: sin hueco vacío bajo el último item.
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        sb = view.verticalScrollBar()
        if sb is not None:
            sb.show()
        # Force popup to always appear below the combo, ignoring Qt's screen-edge flip.
        global_bottom = self.mapToGlobal(QPoint(0, self.height()))
        popup.move(global_bottom.x(), global_bottom.y())
        sz = popup.size()
        if sz.width() > 0 and sz.height() > 0:
            _ = popup.winId()
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, sz.width(), sz.height()), 8, 8)
            popup.setMask(QRegion(path.toFillPolygon().toPolygon()))
        # Restore opacity — popup appears at the correct position with no flash.
        popup.setWindowOpacity(1.0)


class _TurnoCelda(QWidget):
    """Hour+minute comboboxes for J. INICIO or J. FIN.
    special=True adds VACACIONES / BAJA options.
    Styling is applied by the ancestor _HorarioTable stylesheet — no per-widget overrides."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.setSpacing(2)

        self.cb_h = _HorarioComboBox()
        self.cb_h.setFixedWidth(68)

        self.cb_m = _HorarioComboBox()
        self.cb_m.setFixedWidth(68)

        self.cb_h.blockSignals(True)
        self.cb_h.addItems([f"{h:02d}h" for h in range(24)])
        self.cb_h.blockSignals(False)

        self.cb_m.blockSignals(True)
        self.cb_m.addItems([f"{m:02d}min" for m in range(0, 60, 5)])
        self.cb_m.blockSignals(False)

        lay.addWidget(self.cb_h)
        lay.addWidget(self.cb_m)

        self.cb_h.currentIndexChanged.connect(self.changed)
        self.cb_m.currentIndexChanged.connect(self.changed)

    def set_bg(self, color: str):
        """Set background without cascading to child comboboxes."""
        n = self.objectName()
        if n:
            self.setStyleSheet(f"QWidget#{n}{{background:{color};}}")
        else:
            self.setStyleSheet(f"background:{color};")

    def get_hour(self) -> int:
        t = self.cb_h.currentText()
        if t.endswith("h"):
            try:
                return int(t[:-1])
            except Exception:
                pass
        return -1

    def get_minute(self) -> int:
        t = self.cb_m.currentText()
        if t.endswith("min"):
            try:
                return int(t[:-3])
            except Exception:
                pass
        return 0

    def get_state(self) -> dict:
        h = self.get_hour()
        if h < 0:
            return {"modo": "libre"}
        return {"modo": "normal", "h": h, "m": self.get_minute()}

    def set_state(self, data: dict):
        modo = data.get("modo", "libre")
        self.cb_h.blockSignals(True)
        self.cb_m.blockSignals(True)
        if modo == "normal":
            idx = self.cb_h.findText(f"{data.get('h', 0):02d}h")
            if idx >= 0:
                self.cb_h.setCurrentIndex(idx)
            raw_m = data.get("m", 0)
            rounded_m = round(raw_m / 5) * 5 % 60
            idx2 = self.cb_m.findText(f"{rounded_m:02d}min")
            if idx2 >= 0:
                self.cb_m.setCurrentIndex(idx2)
        else:
            self.cb_h.setCurrentIndex(0)
        self.cb_h.blockSignals(False)
        self.cb_m.blockSignals(False)


class _EmpNameEdit(QWidget):
    """Employee name cell widget.

    Outer QWidget handles all mouse events; inner QLineEdit has
    WA_TransparentForMouseEvents=True, which prevents WA_UnderMouse from
    ever being set on it. This stops QLineEdit:hover from the global
    stylesheet from activating — no matter the specificity battle.
    """

    textChanged = pyqtSignal(str)

    def __init__(self, row_bg: str, parent=None):
        super().__init__(parent)
        self._row_bg = row_bg
        self.setObjectName("empNameOuter")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.IBeamCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._edit = QLineEdit(self)
        self._edit.setObjectName("empNameInner")
        # Mouse events pass through to the outer QWidget; WA_UnderMouse is
        # therefore never set on the inner QLineEdit → QLineEdit:hover cannot fire.
        self._edit.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._edit.setStyleSheet(
            "QLineEdit#empNameInner {"
            " background: transparent; border: none; color: #D0DCE8;"
            " font-family: 'Segoe UI'; font-size: 12px; padding: 0 8px;"
            "}"
            "QLineEdit#empNameInner:focus { background: transparent; border: none; }"
        )
        self._edit.textChanged.connect(self.textChanged)
        self._edit.installEventFilter(self)
        lay.addWidget(self._edit)

        self.setFocusProxy(self._edit)
        self._set_style(focused=False)

    def _set_style(self, focused: bool):
        border = f"1px solid {_CIAN}" if focused else "1px solid transparent"
        self.setStyleSheet(
            f"QWidget#empNameOuter {{background:{self._row_bg}; border:{border};}}"
        )

    def eventFilter(self, obj, event):
        if obj is self._edit:
            t = event.type()
            if t == QEvent.Type.FocusIn:
                self._set_style(focused=True)
            elif t == QEvent.Type.FocusOut:
                self._set_style(focused=False)
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        self._edit.setFocus(Qt.FocusReason.MouseFocusReason)
        pos = self._edit.mapFrom(self, event.position().toPoint())
        self._edit.setCursorPosition(self._edit.cursorPositionAt(pos))
        super().mousePressEvent(event)

    # ── QLineEdit API proxy ───────────────────────────────────────────────────

    def text(self) -> str:
        return self._edit.text()

    def setText(self, t: str):
        self._edit.setText(t)

    def setPlaceholderText(self, t: str):
        self._edit.setPlaceholderText(t)


class _HorarioLoadingWidget(QWidget):
    """Spinning arc + text shown while horario tables are building asynchronously."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self._angle = 0
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _tick(self):
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#0D1117"))
        cx = self.width() // 2
        cy = self.height() // 2
        r = 38
        arc_rect = QRectF(cx - r, cy - r - 22, r * 2, r * 2)
        pen = QPen(QColor("#00FFC6"), 6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(arc_rect, self._angle * 16, 270 * 16)
        p.setPen(QColor("#00FFC6"))
        p.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        text_y = cy + r - 8
        p.drawText(
            QRectF(0, text_y, self.width(), 32),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            tr("cfg.loading_horarios", default="CARGANDO TABLAS DE LOS HORARIOS..."),
        )
        p.end()


class _AusenciaDialog(QDialog):
    """Multi-step wizard: select employee → reason → days (→ duration for Retraso)."""

    # (label, cell-color) for every absence type
    REASONS = [
        ("VACACIONES",               "#F59E0B"),
        ("BAJA MÉDICA",              "#EF4444"),
        ("MATRIMONIO",               "#F472B6"),
        ("FALLECIMIENTO FAMILIAR",   "#C084FC"),
        ("HOSPITALIZACIÓN FAMILIAR", "#A78BFA"),
        ("MUDANZA",                  "#FB923C"),
        ("ASUNTOS PROPIOS",          "#34D399"),
        ("RETRASO",                  "#FBBF24"),
        ("AUSENCIA INJUSTIFICADA",   "#F87171"),
        ("FORMACIÓN",                "#60A5FA"),
        ("TELETRABAJO",              "#6EE7B7"),
        ("PERMISO SIN SUELDO",       "#94A3B8"),
        ("FESTIVO",                  "#FDE047"),
        ("DÍA LIBRE",                "#67E8F9"),
    ]

    def __init__(self, employee_names: list[str], parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        self._emp_names = employee_names
        self.result_emp_idx: int = 0
        self.result_days: list[int] = []
        self.result_text: str = ""
        self.result_color: str = ""
        self._reason_text: str = ""
        self._reason_color: str = ""
        self._day_btns: list[QPushButton] = []
        self._retraso_day_btns: list[QPushButton] = []
        self._retraso_day_idx: int = -1
        self._retraso_h: QSpinBox | None = None
        self._retraso_m: QSpinBox | None = None

        card = QFrame(self)
        card.setObjectName("acard")
        card.setStyleSheet(
            f"QFrame#acard{{background:#0D1117;border:2px solid {_CIAN};border-radius:14px;}}"
        )
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.addWidget(card)

        card_ly = QVBoxLayout(card)
        card_ly.setContentsMargins(28, 24, 28, 36)
        card_ly.setSpacing(16)

        self._stack = QStackedWidget()
        card_ly.addWidget(self._stack)
        # Stack indices:
        # 0 = employee selection
        # 1 = reason grid
        # 2 = day multi-selector (all types except Retraso)
        # 3 = retraso single-day selector
        # 4 = retraso duration input
        self._stack.addWidget(self._make_step1())
        self._stack.addWidget(self._make_step2())
        self._stack.addWidget(self._make_step_days())
        self._stack.addWidget(self._make_step_retraso_day())
        self._stack.addWidget(self._make_step_retraso_dur())
        self._stack.setCurrentIndex(0)
        self.setMinimumWidth(560)
        self.adjustSize()

    # ── shared helpers ───────────────────────────────────────────────────────

    def _title_lbl(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color:#E6EDF3;font-family:'Segoe UI';font-weight:bold;font-size:15px;"
            "background:transparent;border:none;"
        )
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return lbl

    def _cancel_btn(self) -> QPushButton:
        b = QPushButton(tr("cfg.cancel", default="CANCELAR"))
        b.setFixedHeight(36)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            "QPushButton{background:#11181D;border:1px solid #2A3A47;"
            "border-radius:8px;color:#6E7681;"
            "font-family:'Segoe UI';font-weight:bold;font-size:13px;padding:0 20px;}"
            f"QPushButton:hover{{background:{_CIAN};border-color:{_CIAN};color:#0E1117;}}"
        )
        b.clicked.connect(self.reject)
        return b

    def _confirm_btn(self, label: str = None) -> QPushButton:
        if label is None:
            label = tr("cfg.confirm", default="CONFIRMAR")
        b = QPushButton(label)
        b.setFixedHeight(36)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"QPushButton{{background:#11181D;border:2px solid {_CIAN};"
            f"border-radius:8px;color:{_CIAN};"
            "font-family:'Segoe UI';font-weight:bold;font-size:13px;padding:0 20px;}"
            f"QPushButton:hover{{background:{_CIAN};color:#0E1117;}}"
        )
        return b

    # ── step widgets ─────────────────────────────────────────────────────────

    def _make_step1(self) -> QWidget:
        w = QWidget()
        ly = QVBoxLayout(w)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(8)
        ly.addWidget(self._title_lbl(tr("cfg.who_absent", default="¿Quién está ausente?")))
        ly.addSpacing(4)
        for i, name in enumerate(self._emp_names):
            label = name.strip() or tr("cfg.employee_n", default="Empleado {n}", n=i + 1)
            btn = QPushButton(label)
            btn.setFixedHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton{background:#11181D;border:1px solid #2A3A47;"
                "border-radius:8px;color:#E6EDF3;"
                "font-family:'Segoe UI';font-weight:bold;font-size:13px;padding:0 16px;}"
                f"QPushButton:hover{{background:{_CIAN};border-color:{_CIAN};color:#0E1117;}}"
            )
            btn.clicked.connect(lambda _, idx=i: self._on_emp(idx))
            ly.addWidget(btn)
        ly.addSpacing(4)
        ly.addWidget(self._cancel_btn())
        return w

    def _on_emp(self, idx: int):
        self.result_emp_idx = idx
        self._stack.setCurrentIndex(1)
        self.adjustSize()

    def _make_step2(self) -> QWidget:
        """14-reason grid, 2 columns, each button half the dialog width."""
        w = QWidget()
        ly = QVBoxLayout(w)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(10)
        lbl = self._title_lbl(tr("cfg.absence_reason_q", default="¿Cuál es el motivo de la ausencia\ndel trabajador?"))
        lbl.setWordWrap(True)
        ly.addWidget(lbl)

        n_rows = (len(self.REASONS) + 1) // 2
        rows_ly = QVBoxLayout()
        rows_ly.setSpacing(6)
        for r in range(n_rows):
            hbox = QHBoxLayout()
            hbox.setSpacing(6)
            hbox.addSpacing(8)
            for c in range(2):
                idx = r * 2 + c
                if idx >= len(self.REASONS):
                    hbox.addStretch(1)
                    continue
                label, color = self.REASONS[idx]
                btn = QPushButton(label)
                btn.setFixedHeight(40)
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(
                    f"QPushButton{{background:{color};border:none;"
                    f"border-radius:8px;color:#000000;"
                    f"font-family:'Segoe UI';font-weight:bold;font-size:13px;}}"
                    f"QPushButton:hover{{background:white;}}"
                )
                btn.clicked.connect(lambda _, co=color, t=label: self._on_reason(co, t))
                hbox.addWidget(btn, 1)
            hbox.addSpacing(8)
            rows_ly.addLayout(hbox)
        ly.addLayout(rows_ly)
        ly.addSpacing(4)
        ly.addWidget(self._cancel_btn())
        return w

    def _on_reason(self, color: str, text: str):
        self._reason_color = color
        self._reason_text = text
        if text == "RETRASO":
            # Reset retraso state
            self._retraso_day_idx = -1
            for b in self._retraso_day_btns:
                b.setChecked(False)
            self._stack.setCurrentIndex(3)
        else:
            # Reset day checkboxes for reuse
            for b in self._day_btns:
                b.setChecked(False)
            self._stack.setCurrentIndex(2)
        self.adjustSize()

    def _make_step_days(self) -> QWidget:
        """Multi-day selector used for all absence types except Retraso."""
        _day_ss = (
            "QPushButton{background:#11181D;border:1px solid #2A3A47;"
            "border-radius:8px;color:#6E7681;"
            "font-family:'Segoe UI';font-weight:bold;font-size:13px;}"
            f"QPushButton:checked{{background:{_CIAN};border-color:{_CIAN};color:#0E1117;}}"
            "QPushButton:hover:!checked{background:#1A2230;color:#E6EDF3;}"
        )
        w = QWidget()
        ly = QVBoxLayout(w)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(8)
        ly.addWidget(self._title_lbl(tr("cfg.absence_days_q", default="¿En qué días estará ausente\nel trabajador?")))
        ly.addSpacing(4)
        self._day_btns = []
        for i, day in enumerate(_dias_lg()):
            btn = QPushButton(day[:3])
            btn.setFixedHeight(36)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_day_ss)
            self._day_btns.append(btn)
        # First 6 in a 2-column grid (3 rows)
        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        for i in range(6):
            grid.addWidget(self._day_btns[i], i // 2, i % 2)
        ly.addLayout(grid)
        # 7th button centred on its own row
        last_row = QHBoxLayout()
        last_row.setSpacing(4)
        last_row.addStretch(1)
        last_row.addWidget(self._day_btns[6], 1)
        last_row.addStretch(1)
        ly.addLayout(last_row)
        ly.addSpacing(4)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addWidget(self._cancel_btn())
        btn_ok = self._confirm_btn()
        btn_ok.clicked.connect(self._on_confirm)
        btn_row.addWidget(btn_ok)
        ly.addLayout(btn_row)
        return w

    def _on_confirm(self):
        days = [i for i, b in enumerate(self._day_btns) if b.isChecked()]
        if not days:
            return
        self.result_days = days
        self.result_text = self._reason_text
        self.result_color = self._reason_color
        self.accept()

    def _make_step_retraso_day(self) -> QWidget:
        """Single-day selector for Retraso (radio-button behaviour)."""
        _day_ss = (
            "QPushButton{background:#11181D;border:1px solid #2A3A47;"
            "border-radius:8px;color:#6E7681;"
            "font-family:'Segoe UI';font-weight:bold;font-size:13px;}"
            f"QPushButton:checked{{background:{_CIAN};border-color:{_CIAN};color:#0E1117;}}"
            "QPushButton:hover:!checked{background:#1A2230;color:#E6EDF3;}"
        )
        w = QWidget()
        ly = QVBoxLayout(w)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(8)
        ly.addWidget(self._title_lbl(tr("cfg.retraso_day_q", default="¿En qué día fue el retraso?")))
        ly.addSpacing(4)
        self._retraso_day_btns = []
        for i, day in enumerate(_dias_lg()):
            btn = QPushButton(day[:3])
            btn.setFixedHeight(36)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_day_ss)
            btn.clicked.connect(lambda _, idx=i: self._on_retraso_day_clicked(idx))
            self._retraso_day_btns.append(btn)
        # First 6 in a 2-column grid (3 rows)
        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        for i in range(6):
            grid.addWidget(self._retraso_day_btns[i], i // 2, i % 2)
        ly.addLayout(grid)
        # 7th button centred on its own row
        last_row = QHBoxLayout()
        last_row.setSpacing(4)
        last_row.addStretch(1)
        last_row.addWidget(self._retraso_day_btns[6], 1)
        last_row.addStretch(1)
        ly.addLayout(last_row)
        ly.addSpacing(4)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addWidget(self._cancel_btn())
        btn_next = self._confirm_btn(tr("cfg.next", default="SIGUIENTE"))
        btn_next.clicked.connect(self._on_retraso_day_next)
        btn_row.addWidget(btn_next)
        ly.addLayout(btn_row)
        return w

    def _on_retraso_day_clicked(self, idx: int):
        self._retraso_day_idx = idx
        for i, b in enumerate(self._retraso_day_btns):
            b.setChecked(i == idx)

    def _on_retraso_day_next(self):
        if self._retraso_day_idx < 0:
            return
        if self._retraso_h is not None:
            self._retraso_h.setValue(0)
        if self._retraso_m is not None:
            self._retraso_m.setValue(0)
        self._stack.setCurrentIndex(4)
        self.adjustSize()

    def _make_step_retraso_dur(self) -> QWidget:
        """Duration input for Retraso: H spinbox + M spinbox."""
        _spin_ss = (
            f"QSpinBox{{background:#11181D;border:2px solid {_CIAN};"
            "border-radius:8px;color:#E6EDF3;"
            "font-family:'Segoe UI';font-size:14px;padding:0 10px;min-width:90px;}"
            f"QSpinBox:focus{{border:2px solid {_CIAN};background:#1A2230;}}"
            "QSpinBox::up-button,QSpinBox::down-button{width:18px;}"
        )
        w = QWidget()
        ly = QVBoxLayout(w)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(12)
        ly.addWidget(self._title_lbl(tr("cfg.retraso_dur_q", default="¿Cuánto tiempo fue el retraso?")))
        ly.addSpacing(4)

        dur_row = QHBoxLayout()
        dur_row.setSpacing(12)
        dur_row.addStretch()

        lbl_h = QLabel(tr("cfg.hours", default="Horas"))
        lbl_h.setStyleSheet("color:#E6EDF3;font-family:'Segoe UI';font-size:13px;background:transparent;border:none;")
        self._retraso_h = QSpinBox()
        self._retraso_h.setRange(0, 12)
        self._retraso_h.setSuffix(" h")
        self._retraso_h.setFixedHeight(40)
        self._retraso_h.setStyleSheet(_spin_ss)

        lbl_m = QLabel(tr("cfg.minutes", default="Minutos"))
        lbl_m.setStyleSheet("color:#E6EDF3;font-family:'Segoe UI';font-size:13px;background:transparent;border:none;")
        self._retraso_m = QSpinBox()
        self._retraso_m.setRange(0, 59)
        self._retraso_m.setSingleStep(5)
        self._retraso_m.setSuffix(" min")
        self._retraso_m.setFixedHeight(40)
        self._retraso_m.setStyleSheet(_spin_ss)

        col_h = QVBoxLayout()
        col_h.setSpacing(4)
        col_h.addWidget(lbl_h)
        col_h.addWidget(self._retraso_h)
        col_m = QVBoxLayout()
        col_m.setSpacing(4)
        col_m.addWidget(lbl_m)
        col_m.addWidget(self._retraso_m)
        dur_row.addLayout(col_h)
        dur_row.addLayout(col_m)
        dur_row.addStretch()
        ly.addLayout(dur_row)

        ly.addSpacing(4)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addWidget(self._cancel_btn())
        btn_ok = self._confirm_btn()
        btn_ok.clicked.connect(self._on_retraso_confirm)
        btn_row.addWidget(btn_ok)
        ly.addLayout(btn_row)
        return w

    def _on_retraso_confirm(self):
        h = self._retraso_h.value() if self._retraso_h else 0
        m = self._retraso_m.value() if self._retraso_m else 0
        if h == 0 and m == 0:
            return
        parts = []
        if h:
            parts.append(f"{h}h")
        parts.append(f"{m:02d}min")
        dur_str = " ".join(parts)
        self.result_days = [self._retraso_day_idx]
        self.result_text = f"RETRASO {dur_str}"
        self.result_color = self._reason_color
        self.accept()


class _HorarioTable(QWidget):
    """QTableWidget-based weekly schedule grid with always-visible _TurnoCelda comboboxes."""

    build_complete = pyqtSignal()

    # Fixed column widths
    _W_EMP  = 145   # EMPLEADO column
    _W_TOT  = 145   # TOTAL SEMANA column
    _ROW_H0 = 32    # day header row
    _ROW_H1 = 30    # sub-header row
    _ROW_EMP = 44   # employee row
    _ROW_TOT = 36   # TOTAL DIARIO row

    def __init__(self, n_emp: int = 1, parent=None):
        super().__init__(parent)
        self._n_emp = max(1, n_emp)
        self._names: list[str] = [""] * self._n_emp
        self._cells: list = []        # [emp][day] = (ini_w, fin_w)
        self._name_edits: list[QLineEdit] = []
        self._absences: dict = {}     # {(emp_idx, day_idx): {"text": str, "color": str}}
        self._tbl: QTableWidget | None = None
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        # Set the final size immediately so the scroll area can calculate its height
        # before the table is built. The actual build is deferred to the next event
        # loop tick so the semana frame renders first (perceived faster load).
        total_w = self._W_EMP + 7 * (_H_COL_INI + _H_COL_FIN + _H_COL_TOT) + self._W_TOT
        total_h = self._ROW_H0 + self._ROW_H1 + self._n_emp * self._ROW_EMP + self._ROW_TOT
        self.setFixedSize(total_w, total_h)
        QTimer.singleShot(0, self._build_table)

    # ── build / rebuild ──────────────────────────────────────────────────────

    def _build_table(self):
        # Suspend global event filter: it calls widget.view() on every QComboBox Polish,
        # creating QListViews synchronously and freezing the UI.
        from assets import estilo_global as _eg
        _app = QApplication.instance()
        _filt = _eg._APP_FILTER
        if _filt is not None and _app is not None:
            _app.removeEventFilter(_filt)
        self._build_filt = _filt
        self._build_app  = _app

        if self._tbl is not None:
            self._lay.removeWidget(self._tbl)
            self._tbl.deleteLater()
            self._tbl = None

        n = self._n_emp
        tbl = QTableWidget(2 + n + 1, 23)   # 2 hdr + employees + total row; 23 cols
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.verticalHeader().setVisible(False)
        tbl.horizontalHeader().setVisible(False)
        tbl.setShowGrid(True)
        tbl.setAlternatingRowColors(False)
        tbl.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tbl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tbl.setStyleSheet(
            "QTableWidget{background:#0D1117;color:#E6EDF3;"
            "border:none;font-family:'Segoe UI';font-size:11px;"
            "gridline-color:#253040;}"
            "QTableWidget::item{border:none;padding:2px;}"
            "QTableWidget::item:hover{background:transparent;}"
            "QTableWidget::item:selected{background:transparent;}"
        )

        # Column widths
        tbl.setColumnWidth(0, self._W_EMP)
        for d in range(7):
            tbl.setColumnWidth(1 + d * 3, _H_COL_INI)
            tbl.setColumnWidth(2 + d * 3, _H_COL_FIN)
            tbl.setColumnWidth(3 + d * 3, _H_COL_TOT)
        tbl.setColumnWidth(22, self._W_TOT)

        # Row heights
        tbl.setRowHeight(0, self._ROW_H0)
        tbl.setRowHeight(1, self._ROW_H1)
        for r in range(2, 2 + n):
            tbl.setRowHeight(r, self._ROW_EMP)
        tbl.setRowHeight(2 + n, self._ROW_TOT)

        # ── Row 0: day name headers ──────────────────────────────────────────
        tbl.setSpan(0, 0, 2, 1)
        tbl.setItem(0, 0, self._hdr("EMPLEADO"))

        for d, day in enumerate(_dias_lg()):
            col = 1 + d * 3
            tbl.setSpan(0, col, 1, 3)
            bg = "#0E1A28" if d % 2 == 0 else "#0B1520"
            tbl.setItem(0, col, self._hdr(day, bg=bg))

        tbl.setSpan(0, 22, 2, 1)
        tbl.setItem(0, 22, self._hdr("TOTAL HORAS\nSEMANA"))

        # ── Row 1: sub-column headers ────────────────────────────────────────
        for d in range(7):
            bg = "#0E1A28" if d % 2 == 0 else "#0B1520"
            tbl.setItem(1, 1 + d * 3, self._hdr("JORNADA INICIO", bold=True, bg=bg, size=10))
            tbl.setItem(1, 2 + d * 3, self._hdr("JORNADA FIN",    bold=True, bg=bg, size=10))
            tbl.setItem(1, 3 + d * 3, self._hdr("TOTAL HORAS",    bold=True, bg=bg, size=10))

        # ── TOTAL DIARIO row (built upfront so skeleton is complete) ─────────
        tr = 2 + n
        it_lbl = QTableWidgetItem("TOTAL HORAS DÍA")
        it_lbl.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it_lbl.setForeground(QColor(_CIAN))
        it_lbl.setBackground(QColor("#0A0F14"))
        fl = it_lbl.font(); fl.setFamily("Segoe UI"); fl.setBold(True); fl.setPointSize(10)
        it_lbl.setFont(fl)
        tbl.setItem(tr, 0, it_lbl)
        for d in range(7):
            tbl.setSpan(tr, 1 + d * 3, 1, 3)
            it_d = QTableWidgetItem("0h 00min")
            it_d.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_d.setForeground(QColor(_CIAN))
            it_d.setBackground(QColor("#0A0F14"))
            fd = it_d.font(); fd.setFamily("Segoe UI"); fd.setBold(True); fd.setPointSize(10)
            it_d.setFont(fd)
            tbl.setItem(tr, 1 + d * 3, it_d)
        it_gs = QTableWidgetItem("")
        it_gs.setBackground(QColor("#0A0F14"))
        tbl.setItem(tr, 22, it_gs)

        self._cells = []
        self._name_edits = []
        self._tbl = tbl
        self._lay.addWidget(tbl)

        total_w = self._W_EMP + 7 * (_H_COL_INI + _H_COL_FIN + _H_COL_TOT) + self._W_TOT
        total_h = self._ROW_H0 + self._ROW_H1 + n * self._ROW_EMP + self._ROW_TOT
        self.setFixedSize(total_w, total_h)

        # Start incremental employee-row build — yields to event loop between rows
        # so headers paint immediately and each row appears as it's ready.
        if n > 0:
            QTimer.singleShot(0, lambda: self._build_emp_row(tbl, 0, n))
        else:
            self._finalize_build(tbl)

    def _build_emp_row(self, tbl: "QTableWidget", e: int, n: int):
        """Build one employee row and schedule the next via a 0-ms timer."""
        if tbl is not self._tbl:   # stale — a newer _build_table was called
            return

        row = 2 + e
        row_bg = "#0D1117" if e % 2 == 0 else "#0A0F14"

        name_w = _EmpNameEdit(row_bg)
        name_w.setPlaceholderText(tr("cfg.emp_placeholder", default="Empleado..."))
        if e < len(self._names):
            name_w.setText(self._names[e])
        name_w.textChanged.connect(lambda t, idx=e: self._on_name_changed(idx, t))
        tbl.setCellWidget(row, 0, name_w)
        self._name_edits.append(name_w)

        day_cells = []
        for d in range(7):
            ini_w = _TurnoCelda()
            fin_w = _TurnoCelda()
            ini_w.setObjectName(f"tc_ini_{row}_{d}")
            fin_w.setObjectName(f"tc_fin_{row}_{d}")
            ini_w.set_bg(row_bg)
            fin_w.set_bg(row_bg)
            tbl.setCellWidget(row, 1 + d * 3, ini_w)
            tbl.setCellWidget(row, 2 + d * 3, fin_w)

            it_tot = QTableWidgetItem("─")
            it_tot.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_tot.setForeground(QColor("#6E7681"))
            it_tot.setBackground(QColor(row_bg))
            f = it_tot.font(); f.setFamily("Segoe UI"); f.setBold(True); f.setPointSize(10)
            it_tot.setFont(f)
            tbl.setItem(row, 3 + d * 3, it_tot)

            ini_w.changed.connect(lambda _=None, ei=e, di=d: self._recalc(ei, di))
            fin_w.changed.connect(lambda _=None, ei=e, di=d: self._recalc(ei, di))
            for cb in (ini_w.cb_h, ini_w.cb_m, fin_w.cb_h, fin_w.cb_m):
                cb.setStyleSheet(_TURNO_CB_SS)
            day_cells.append((ini_w, fin_w))

        it_sem = QTableWidgetItem("0h 00min")
        it_sem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it_sem.setForeground(QColor(_CIAN))
        it_sem.setBackground(QColor(row_bg))
        fs = it_sem.font(); fs.setFamily("Segoe UI"); fs.setBold(True); fs.setPointSize(10)
        it_sem.setFont(fs)
        tbl.setItem(row, 22, it_sem)
        self._cells.append(day_cells)

        if e + 1 < n:
            QTimer.singleShot(0, lambda: self._build_emp_row(tbl, e + 1, n))
        else:
            self._finalize_build(tbl)

    def _finalize_build(self, tbl: "QTableWidget"):
        """Called after all employee rows are populated."""
        if tbl is not self._tbl:   # stale
            return
        self._apply_all_absences()
        _filt = getattr(self, "_build_filt", None)
        _app  = getattr(self, "_build_app",  None)
        if _filt is not None and _app is not None:
            _app.installEventFilter(_filt)
        self.build_complete.emit()

    def _hdr(self, text: str, bold: bool = True, bg: str = "#0D1117",
             fg: str | None = None, size: int = 10) -> QTableWidgetItem:
        if fg is None:
            fg = _CIAN
        it = QTableWidgetItem(text)
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it.setForeground(QColor(fg))
        it.setBackground(QColor(bg))
        f = it.font(); f.setFamily("Segoe UI"); f.setBold(bold); f.setPointSize(size)
        it.setFont(f)
        return it

    def _on_name_changed(self, idx: int, text: str):
        if idx < len(self._names):
            self._names[idx] = text

    # ── row management ───────────────────────────────────────────────────────

    def add_row(self):
        """Add one employee row incrementally — no full table rebuild."""
        if self._tbl is None:
            # Table not yet built; just bump count and let the pending build handle it.
            self._n_emp += 1
            self._names = [""] * self._n_emp
            return

        e = self._n_emp
        self._names = [ed.text() for ed in self._name_edits] + [""]
        self._n_emp += 1

        from assets import estilo_global as _eg
        _app = QApplication.instance()
        _filt = _eg._APP_FILTER
        if _app and _filt:
            _app.removeEventFilter(_filt)

        tbl = self._tbl
        tbl.setUpdatesEnabled(False)

        insert_pos = 2 + e   # row index — TOTAL DIARIO row gets shifted down
        tbl.insertRow(insert_pos)
        tbl.setRowHeight(insert_pos, self._ROW_EMP)

        row_bg = "#0D1117" if e % 2 == 0 else "#0A0F14"

        name_w = _EmpNameEdit(row_bg)
        name_w.setPlaceholderText(tr("cfg.emp_placeholder", default="Empleado..."))
        name_w.textChanged.connect(lambda t, idx=e: self._on_name_changed(idx, t))
        tbl.setCellWidget(insert_pos, 0, name_w)
        self._name_edits.append(name_w)

        day_cells = []
        for d in range(7):
            ini_w = _TurnoCelda()
            fin_w = _TurnoCelda()
            ini_w.setObjectName(f"tc_ini_{insert_pos}_{d}")
            fin_w.setObjectName(f"tc_fin_{insert_pos}_{d}")
            ini_w.set_bg(row_bg)
            fin_w.set_bg(row_bg)
            tbl.setCellWidget(insert_pos, 1 + d * 3, ini_w)
            tbl.setCellWidget(insert_pos, 2 + d * 3, fin_w)

            it_tot = QTableWidgetItem("─")
            it_tot.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_tot.setForeground(QColor("#6E7681"))
            it_tot.setBackground(QColor(row_bg))
            f = it_tot.font(); f.setFamily("Segoe UI"); f.setBold(True); f.setPointSize(10)
            it_tot.setFont(f)
            tbl.setItem(insert_pos, 3 + d * 3, it_tot)

            ini_w.changed.connect(lambda _=None, ei=e, di=d: self._recalc(ei, di))
            fin_w.changed.connect(lambda _=None, ei=e, di=d: self._recalc(ei, di))
            for cb in (ini_w.cb_h, ini_w.cb_m, fin_w.cb_h, fin_w.cb_m):
                cb.setStyleSheet(_TURNO_CB_SS)
            day_cells.append((ini_w, fin_w))

        it_sem = QTableWidgetItem("0h 00min")
        it_sem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it_sem.setForeground(QColor(_CIAN))
        it_sem.setBackground(QColor(row_bg))
        fs = it_sem.font(); fs.setFamily("Segoe UI"); fs.setBold(True); fs.setPointSize(10)
        it_sem.setFont(fs)
        tbl.setItem(insert_pos, 22, it_sem)

        self._cells.append(day_cells)
        tbl.setUpdatesEnabled(True)

        total_w = self._W_EMP + 7 * (_H_COL_INI + _H_COL_FIN + _H_COL_TOT) + self._W_TOT
        total_h = self._ROW_H0 + self._ROW_H1 + self._n_emp * self._ROW_EMP + self._ROW_TOT
        self.setFixedSize(total_w, total_h)

        if _app and _filt:
            _app.installEventFilter(_filt)

    # ── recalc ───────────────────────────────────────────────────────────────

    def _recalc(self, emp_idx: int, day_idx: int):
        if (emp_idx, day_idx) in self._absences:
            self._recalc_semana(emp_idx)
            self._recalc_diario(day_idx)
            return
        row    = 2 + emp_idx
        row_bg = "#0D1117" if emp_idx % 2 == 0 else "#0A0F14"
        if emp_idx >= len(self._cells) or day_idx >= len(self._cells[emp_idx]):
            return
        ini_w, fin_w = self._cells[emp_idx][day_idx]
        tot_col = 3 + day_idx * 3
        ini_w.set_bg(row_bg)
        fin_w.set_bg(row_bg)
        fin_w.setEnabled(True)
        h_ini = ini_w.get_hour()
        h_fin = fin_w.get_hour()
        it = self._tbl.item(row, tot_col)
        if it:
            it.setBackground(QColor(row_bg))
        if h_ini < 0 or h_fin < 0:
            if it:
                it.setText("─"); it.setForeground(QColor("#6E7681"))
        else:
            diff = (h_fin * 60 + fin_w.get_minute()) - (h_ini * 60 + ini_w.get_minute())
            if diff < 0:
                if it:
                    it.setText("!"); it.setForeground(QColor("#FF4C4C"))
            else:
                hh, mm = divmod(diff, 60)
                if it:
                    it.setText(f"{hh}h {mm:02d}min")
                    it.setForeground(QColor("#E6EDF3"))
        self._recalc_semana(emp_idx)
        self._recalc_diario(day_idx)

    def _recalc_semana(self, emp_idx: int):
        total_min = 0
        row = 2 + emp_idx
        for d in range(7):
            it = self._tbl.item(row, 3 + d * 3)
            if it:
                total_min += _h_parse_minutes(it.text())
        hh, mm = divmod(total_min, 60)
        it_sem = self._tbl.item(row, 22)
        if it_sem:
            it_sem.setText(f"{hh}h {mm:02d}min")

    def _recalc_diario(self, day_idx: int):
        total_min = 0
        for e in range(self._n_emp):
            it = self._tbl.item(2 + e, 3 + day_idx * 3)
            if it:
                total_min += _h_parse_minutes(it.text())
        hh, mm = divmod(total_min, 60)
        tr = 2 + self._n_emp
        it_d = self._tbl.item(tr, 1 + day_idx * 3)
        if it_d:
            it_d.setText(f"{hh}h {mm:02d}min")

    # ── absence management ───────────────────────────────────────────────────

    def get_employee_names(self) -> list[str]:
        return [e.text().strip() or f"Empleado {i + 1}" for i, e in enumerate(self._name_edits)]

    def apply_ausencia(self, emp_idx: int, days: list[int], text: str, color: str):
        for d in days:
            self._absences[(emp_idx, d)] = {"text": text, "color": color}
        if self._tbl is not None:
            for d in days:
                self._apply_single_ausencia(emp_idx, d)
                self._recalc_semana(emp_idx)
                self._recalc_diario(d)

    def _apply_all_absences(self):
        if self._tbl is None:
            return
        for (emp_idx, day_idx), info in list(self._absences.items()):
            if emp_idx < self._n_emp:
                self._apply_single_ausencia(emp_idx, day_idx)

    def _apply_single_ausencia(self, emp_idx: int, day_idx: int):
        if self._tbl is None or emp_idx >= self._n_emp:
            return
        info = self._absences.get((emp_idx, day_idx))
        if info is None:
            return
        row = 2 + emp_idx
        col_ini = 1 + day_idx * 3
        col_fin = 2 + day_idx * 3
        col_tot = 3 + day_idx * 3
        self._tbl.removeCellWidget(row, col_ini)
        self._tbl.removeCellWidget(row, col_fin)
        # Clear the old total item before spanning
        self._tbl.setItem(row, col_tot, QTableWidgetItem(""))
        self._tbl.setSpan(row, col_ini, 1, 3)
        # Use a QLabel cell widget — QTableWidgetItem.setBackground() is unreliable
        # when the table has a QSS stylesheet active (::item rule takes over painting).
        lbl = QLabel(info["text"])
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lbl.setStyleSheet(
            f"background:{info['color']};color:#000000;"
            "font-family:'Segoe UI';font-weight:bold;font-size:13px;border:none;"
        )
        self._tbl.setCellWidget(row, col_ini, lbl)

    # ── persistence ──────────────────────────────────────────────────────────

    def get_state(self) -> dict:
        names = [e.text() for e in self._name_edits]
        schedule: dict = {}
        for e_idx in range(len(self._cells)):
            day_data: dict = {}
            for d_idx in range(7):
                if (e_idx, d_idx) in self._absences:
                    day_data[str(d_idx)] = {"ini": {"modo": "libre"}, "fin": {"modo": "libre"}}
                else:
                    ini_w, fin_w = self._cells[e_idx][d_idx]
                    day_data[str(d_idx)] = {
                        "ini": ini_w.get_state(),
                        "fin": fin_w.get_state(),
                    }
            schedule[str(e_idx)] = day_data
        absences = {f"{k[0]},{k[1]}": v for k, v in self._absences.items()}
        return {"names": names, "schedule": schedule, "absences": absences}

    def set_state(self, data: dict):
        names = data.get("names", [])
        n_new = max(self._n_emp, len(names))
        names_padded = list(names) + [""] * (n_new - len(names))
        schedule = data.get("schedule", {})
        absences_raw = data.get("absences", {})
        self._absences = {
            (int(k.split(",")[0]), int(k.split(",")[1])): v
            for k, v in absences_raw.items()
        }
        if n_new != self._n_emp:
            # Employee count changed — rebuild; restore schedule + absences when done.
            self._n_emp = n_new
            self._names = names_padded
            def _on_ready(sch=schedule):
                self.build_complete.disconnect(_on_ready)
                self._restore_schedule(sch)
            self.build_complete.connect(_on_ready)
            self._build_table()
        else:
            # Same employee count — refresh names, restore schedule, apply absences.
            self._names = names_padded
            for i, edit in enumerate(self._name_edits):
                if i < len(names_padded):
                    edit.setText(names_padded[i])
            self._restore_schedule(schedule)
            self._apply_all_absences()

    def _restore_schedule(self, schedule: dict):
        for e_str, day_data in schedule.items():
            e = int(e_str)
            if e >= self._n_emp or e >= len(self._cells):
                continue
            for d_str, cell_data in day_data.items():
                d = int(d_str)
                if d >= 7:
                    continue
                ini_w, fin_w = self._cells[e][d]
                ini_w.set_state(cell_data.get("ini", {"modo": "libre"}))
                fin_w.set_state(cell_data.get("fin", {"modo": "libre"}))
                self._recalc(e, d)


class _HorarioSemana(QFrame):
    """One week's schedule: editable title + horizontally-scrollable table + add-row."""

    deleted = pyqtSignal(object)

    def __init__(self, n_emp: int = 1, parent=None):
        super().__init__(parent)
        self.setObjectName("horarioSemana")
        self.setStyleSheet(f"""
            QFrame#horarioSemana {{
                background: #0D1117;
                border: 2px solid {_CIAN};
                border-radius: 14px;
            }}
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText(tr("cfg.week_placeholder", default="Semana  DD/MM/AAAA – DD/MM/AAAA"))
        self._title_edit.setFixedHeight(36)
        self._title_edit.setStyleSheet(f"""
            QLineEdit {{
                background: #11181D; border: 1px solid #2A3A47;
                border-radius: 8px; color: #E6EDF3;
                font-family: 'Segoe UI'; font-weight: bold; font-size: 13px;
                padding: 0 12px;
            }}
            QLineEdit:focus {{ border-color: {_CIAN}; }}
        """)
        btn_print = QPushButton("🖨  " + tr("cfg.print", default="IMPRIMIR"))
        btn_print.setFixedHeight(36)
        btn_print.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_print.setStyleSheet(f"""
            QPushButton {{
                background: #11181D; border: 1px solid {_CIAN};
                border-radius: 8px; color: {_CIAN};
                font-family: 'Segoe UI'; font-weight: bold; font-size: 13px;
                padding: 0 16px;
            }}
            QPushButton:hover {{ background: {_CIAN}; color: #0E1117; }}
        """)
        btn_print.clicked.connect(self._imprimir)
        btn_del = QPushButton("✕  " + tr("cfg.delete", default="ELIMINAR"))
        btn_del.setFixedHeight(36)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setStyleSheet("""
            QPushButton {
                background: #11181D; border: 2px solid #EF4444;
                border-radius: 8px; color: #EF4444;
                font-family: 'Segoe UI'; font-weight: bold; font-size: 13px;
                padding: 0 14px;
            }
            QPushButton:hover { background: #EF4444; color: #0E1117; border: 2px solid #EF4444; }
        """)
        btn_del.clicked.connect(self._confirm_delete)
        btn_ausencia = QPushButton(tr("cfg.absence", default="AUSENCIA"))
        btn_ausencia.setFixedHeight(36)
        btn_ausencia.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ausencia.setStyleSheet("""
            QPushButton {
                background: white; border: 1px solid #cccccc;
                border-radius: 8px; color: black;
                font-family: 'Segoe UI'; font-weight: bold; font-size: 13px;
                padding: 0 14px;
            }
            QPushButton:hover { background: #f0f0f0; }
        """)
        btn_ausencia.clicked.connect(self._show_ausencia)
        self._move_icon = _MoveIcon(self._start_drag)
        title_row.addWidget(self._title_edit, 1)
        title_row.addWidget(btn_print)
        title_row.addWidget(btn_del)
        title_row.addWidget(btn_ausencia)
        title_row.addWidget(self._move_icon)
        outer.addLayout(title_row)
        self._hscroll = QScrollArea()
        self._hscroll.setWidgetResizable(False)
        self._hscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._hscroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._hscroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._grid = _HorarioTable(n_emp=n_emp)
        self._hscroll.setWidget(self._grid)
        self._hscroll.setFixedHeight(self._grid.height() + 14)
        self._grid.build_complete.connect(self._sync_scroll_height)
        outer.addWidget(self._hscroll)
        btn_add = QPushButton("＋  " + tr("cfg.add_employee", default="AÑADIR EMPLEADO"))
        btn_add.setFixedHeight(32)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {_CIAN};
                border-radius: 8px; color: {_CIAN};
                font-family: 'Segoe UI'; font-size: 11px;
            }}
            QPushButton:hover {{ background: rgba(0,255,198,0.10); }}
        """)
        btn_add.clicked.connect(self._add_row)
        outer.addWidget(btn_add)

    def _sync_scroll_height(self):
        self._hscroll.setFixedHeight(self._grid.height() + 14)

    def _add_row(self):
        self._grid.add_row()
        self._hscroll.setFixedHeight(self._grid.height() + 14)

    def _confirm_delete(self):
        dlg = QDialog(self)
        dlg.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dlg.setStyleSheet("background: transparent;")
        card = QFrame(dlg)
        card.setObjectName("dlg_card")
        card.setStyleSheet(f"""
            QFrame#dlg_card {{
                background: #0D1117;
                border: 2px solid {_CIAN};
                border-radius: 14px;
            }}
        """)
        dlg_root = QVBoxLayout(dlg)
        dlg_root.setContentsMargins(0, 0, 0, 0)
        dlg_root.addWidget(card)
        ly = QVBoxLayout(card)
        ly.setContentsMargins(28, 24, 28, 24)
        ly.setSpacing(20)
        lbl = QLabel(tr("cfg.del_table_confirm", default="¿Eliminar esta tabla de horario?"))
        lbl.setStyleSheet(
            "color: #E6EDF3; font-family: 'Segoe UI'; font-weight: bold; font-size: 15px;"
        )
        ly.addWidget(lbl)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_no = QPushButton(tr("cfg.cancel", default="CANCELAR"))
        btn_no.setFixedHeight(38)
        btn_no.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_no.setStyleSheet(f"""
            QPushButton {{
                background: #11181D; border: 1px solid #2A3A47;
                border-radius: 8px; color: #6E7681;
                font-family: 'Segoe UI'; font-weight: bold; font-size: 13px; padding: 0 20px;
            }}
            QPushButton:hover {{ background: {_CIAN}; border-color: {_CIAN}; color: #0E1117; }}
        """)
        btn_no.clicked.connect(dlg.reject)
        btn_yes = QPushButton(tr("cfg.delete", default="ELIMINAR"))
        btn_yes.setFixedHeight(38)
        btn_yes.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_yes.setStyleSheet("""
            QPushButton {
                background: #11181D; border: 2px solid #EF4444;
                border-radius: 8px; color: #EF4444;
                font-family: 'Segoe UI'; font-weight: bold; font-size: 13px; padding: 0 20px;
            }
            QPushButton:hover { background: #EF4444; color: #0E1117; }
        """)
        btn_yes.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_no)
        btn_row.addWidget(btn_yes)
        ly.addLayout(btn_row)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.deleted.emit(self)

    def _show_ausencia(self):
        names = self._grid.get_employee_names()
        dlg = _AusenciaDialog(names, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._grid.apply_ausencia(
                dlg.result_emp_idx, dlg.result_days, dlg.result_text, dlg.result_color
            )

    def _start_drag(self, global_pos: QPoint):
        container = getattr(self, "_container", None)
        if container is not None:
            container.begin_drag(self, global_pos)

    def _imprimir(self):
        try:
            from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            dlg = QPrintDialog(printer, self)
            if dlg.exec():
                p = QPainter()
                p.begin(printer)
                pr = printer.pageRect(QPrinter.Unit.DevicePixel).toRect()
                gw, gh = self._grid.width(), self._grid.height()
                scale = min(pr.width() / gw, pr.height() / gh)
                p.scale(scale, scale)
                title = self._title_edit.text() or "Horario semanal"
                p.setPen(QColor(_CIAN))
                p.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
                p.drawText(QRect(0, 0, gw, 40), Qt.AlignmentFlag.AlignCenter, title)
                p.translate(0, 40)
                self._grid.render(p, QPoint(0, 0))
                p.end()
        except Exception as exc:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"), tr("cfg.print_err", default="No se pudo imprimir: {exc}", exc=exc), "error")

    def get_state(self) -> dict:
        return {"title": self._title_edit.text(), "grid": self._grid.get_state()}

    def set_state(self, data: dict):
        self._title_edit.setText(data.get("title", ""))
        self._grid.set_state(data.get("grid", {}))
        self._hscroll.setFixedHeight(self._grid.height() + 14)


class _HorarioContainer(QWidget):
    """Vertical list of _HorarioSemana widgets; phone-like drag-to-reorder."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._semanas: list[_HorarioSemana] = []
        self._ly = QVBoxLayout(self)
        self._ly.setContentsMargins(0, 0, 8, 12)
        self._ly.setSpacing(12)
        self._ly.addStretch()
        self._drag_semana: _HorarioSemana | None = None
        self._drag_ghost: QLabel | None = None
        self._drag_placeholder: QFrame | None = None
        self._drag_offset = QPoint(0, 0)
        self._drag_ph_idx: int = 0
        self._drag_semana_h: int = 0
        self._scroll_area = None
        self._scroll_speed: int = 0
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(25)
        self._scroll_timer.timeout.connect(self._do_autoscroll)

    def add_semana(self, s: _HorarioSemana):
        s._container = self
        s.deleted.connect(self._on_semana_deleted)
        self._ly.insertWidget(self._ly.count() - 1, s)
        self._semanas.append(s)

    def _on_semana_deleted(self, semana):
        if semana in self._semanas:
            self._semanas.remove(semana)
            self._ly.removeWidget(semana)
            semana.deleteLater()

    def begin_drag(self, semana: _HorarioSemana, global_pos: QPoint):
        if self._drag_semana is not None:
            return
        self._drag_semana = semana
        semana_tl = semana.mapToGlobal(QPoint(0, 0))
        self._drag_offset = global_pos - semana_tl
        self._drag_semana_h = semana.height()
        visible = [s for s in self._semanas if s is not semana]
        self._drag_ph_idx = min(self._semanas.index(semana), len(visible))
        ph = QFrame(self)
        ph.setFixedHeight(self._drag_semana_h)
        ph.setStyleSheet(
            f"border: 2px dashed {_CIAN}; border-radius: 10px; background: #0D1117;"
        )
        self._drag_placeholder = ph
        self._ly.replaceWidget(semana, ph)
        ph.show()
        semana.hide()
        pix = semana.grab()
        ghost = QLabel()
        ghost.setWindowFlags(
            Qt.WindowType.Tool |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        ghost.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        ghost.setPixmap(pix)
        ghost.resize(pix.size())
        ghost.move(semana_tl)
        ghost.setWindowOpacity(0.90)
        ghost.show()
        self._drag_ghost = ghost
        self.grabMouse(Qt.CursorShape.SizeAllCursor)

    def mouseMoveEvent(self, ev):
        if self._drag_semana is None:
            super().mouseMoveEvent(ev)
            return
        gp = ev.globalPosition().toPoint()
        if self._drag_ghost:
            self._drag_ghost.move(gp - self._drag_offset)
        self._update_placeholder(gp)
        self._update_autoscroll(gp)

    def mouseReleaseEvent(self, ev):
        if self._drag_semana is not None and ev.button() == Qt.MouseButton.LeftButton:
            self.releaseMouse()
            self._end_drag()
        else:
            super().mouseReleaseEvent(ev)

    def _update_autoscroll(self, global_pos: QPoint):
        if not self._scroll_area:
            return
        vp = self._scroll_area.viewport()
        local_y = vp.mapFromGlobal(global_pos).y()
        h = vp.height()
        ZONE = 70
        if local_y < ZONE:
            self._scroll_speed = -max(6, int((ZONE - local_y) * 0.35))
        elif local_y > h - ZONE:
            self._scroll_speed = max(6, int((local_y - (h - ZONE)) * 0.35))
        else:
            self._scroll_speed = 0
        if self._scroll_speed != 0:
            if not self._scroll_timer.isActive():
                self._scroll_timer.start()
        else:
            self._scroll_timer.stop()

    def _do_autoscroll(self):
        if self._drag_semana is None or not self._scroll_area:
            self._scroll_timer.stop()
            return
        sb = self._scroll_area.verticalScrollBar()
        sb.setValue(sb.value() + self._scroll_speed)
        self._update_placeholder(QCursor.pos())

    def _update_placeholder(self, global_pos: QPoint):
        local_y = self.mapFromGlobal(global_pos).y()
        visible = [s for s in self._semanas if s is not self._drag_semana]
        ph = self._drag_placeholder
        if ph is None:
            return
        spacing = self._ly.spacing()
        top_margin = self._ly.contentsMargins().top()
        current = list(visible)
        current.insert(self._drag_ph_idx, ph)
        y = top_margin
        tops: dict[int, int] = {}
        for w in current:
            tops[id(w)] = y
            h = self._drag_semana_h if w is ph else w.height()
            y += h + spacing
        new_idx = len(visible)
        for i, s in enumerate(visible):
            mid = tops[id(s)] + s.height() // 2
            if local_y < mid:
                new_idx = i
                break
        if new_idx == self._drag_ph_idx:
            return
        self._drag_ph_idx = new_idx
        for s in visible:
            self._ly.removeWidget(s)
        self._ly.removeWidget(ph)
        ordered = list(visible)
        ordered.insert(new_idx, ph)
        for i, w in enumerate(ordered):
            self._ly.insertWidget(i, w)

    def _end_drag(self):
        self._scroll_timer.stop()
        self._scroll_speed = 0
        semana = self._drag_semana
        ph = self._drag_placeholder
        if ph:
            self._ly.removeWidget(ph)
            ph.deleteLater()
            self._drag_placeholder = None
        semana.show()
        visible = [s for s in self._semanas if s is not semana]
        new_idx = min(self._drag_ph_idx, len(visible))
        visible.insert(new_idx, semana)
        self._semanas = visible
        for s in self._semanas:
            self._ly.removeWidget(s)
        for i, s in enumerate(self._semanas):
            self._ly.insertWidget(i, s)
        self._drag_semana = None
        self._drag_ph_idx = 0
        if self._drag_ghost:
            self._drag_ghost.close()
            self._drag_ghost = None


# ── GESTIÓN CAJA — Dialog helpers ─────────────────────────────────────────────



# ── Dependencias compartidas del módulo original (import diferido: uso en
# runtime; rompe el ciclo de imports con gui/gestion_usuarios sin duplicar). ──
from src.gui.gestion_usuarios import (  # noqa: E402,F401
    _CIAN,
    _H_COL_INI,
    _H_COL_FIN,
    _H_COL_TOT,
    _TURNO_CB_SS,
    _MoveIcon,
    _RoundedItemDelegate,
    _dias_lg,
    _h_parse_minutes,
)
