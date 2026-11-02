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
        self._warn_btn: "QToolButton | None" = None
        self._warn_msg: "str | None" = None
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

    # ── aviso de descanso mínimo (Fase E, punto 4) ───────────────────────────
    def set_warning(self, mensaje: "str | None"):
        """Muestra (mensaje no vacío) u oculta (None) un icono "!" rojo en la esquina de la
        celda — clicable, abre `assets.estilo_global.mostrar_mensaje` con el motivo exacto."""
        self._warn_msg = mensaje
        if mensaje:
            if self._warn_btn is None:
                btn = QToolButton(self)
                btn.setText("!")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setFixedSize(14, 14)
                btn.setStyleSheet(
                    "QToolButton{background:#EF4444;color:#FFFFFF;border:none;"
                    "border-radius:7px;font-family:'Segoe UI';font-weight:bold;font-size:10px;}"
                    "QToolButton:hover{background:#FF6B6B;}"
                )
                btn.clicked.connect(self._mostrar_warning)
                self._warn_btn = btn
            self._warn_btn.move(max(0, self.width() - 16), 2)
            self._warn_btn.show()
            self._warn_btn.raise_()
        elif self._warn_btn is not None:
            self._warn_btn.hide()

    def _mostrar_warning(self):
        from assets.estilo_global import mostrar_mensaje
        mostrar_mensaje(self, tr("rrhh.descanso_warn_title", default="Aviso de descanso"),
                        self._warn_msg or "", "warning")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._warn_btn is not None and self._warn_btn.isVisible():
            self._warn_btn.move(max(0, self.width() - 16), 2)


class _EmpSelectCell(QWidget):
    """Employee SELECTOR cell (RRHH Fase E — sustituye al antiguo campo de texto libre, del que
    conserva el botón de color por empleado sin cambios). `QComboBox` poblado por la tabla
    contenedora (`_HorarioTable.refrescar_opciones_dropdowns`) con los empleados del centro que
    aún no estén elegidos en OTRA fila de la MISMA tabla (exclusión mutua)."""

    idChanged = pyqtSignal(object)   # id_empleado (int) o None
    textChanged = pyqtSignal(str)    # compat: nombre visible de la selección actual

    PLACEHOLDER = "— Selecciona empleado —"

    def __init__(self, row_bg: str, parent=None):
        super().__init__(parent)
        self._row_bg = row_bg
        self.setObjectName("empNameOuter")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Color propio del empleado (None = sin color; se pinta el fondo de esta celda). El gestor de
        # unicidad (la tabla) inyecta `solicitar_color` para validar que cada color sea único.
        self._color: "str | None" = None
        self.solicitar_color = None
        self._current_id = None
        self._current_label = ""
        self._warn_btn: "QToolButton | None" = None
        self._warn_msg: "str | None" = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._combo = _HorarioComboBox(self)
        self._combo.setObjectName("empSelectCombo")
        self._combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._combo.installEventFilter(self)
        self._combo.currentIndexChanged.connect(self._on_index_changed)
        lay.addWidget(self._combo, 1)

        # Botón PINCEL (solo emoji, sin texto): abre el selector de color estándar de la app para asignar
        # un color propio al empleado. Va a la derecha; la columna EMPLEADO se ensancha (_W_EMP) para que
        # el botón NUNCA tape el nombre.
        self._btn_color = QToolButton(self)
        self._btn_color.setObjectName("empColorBtn")
        self._btn_color.setText("🖌️")
        self._btn_color.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_color.setFixedSize(24, 24)
        self._btn_color.setToolTip(tr("cfg.emp_color_tip", default="Color del empleado"))
        self._btn_color.setStyleSheet(
            "QToolButton#empColorBtn{background:transparent;border:none;border-radius:6px;"
            "font-size:13px;padding:0;}"
            "QToolButton#empColorBtn:hover{background:rgba(0,255,198,40);}"
        )
        self._btn_color.clicked.connect(self._on_brush_clicked)
        lay.addWidget(self._btn_color, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addSpacing(4)

        self.setFocusProxy(self._combo)
        self._aplicar_color_texto(self._row_bg)
        self._set_style(focused=False)

    def _set_style(self, focused: bool):
        border = f"1px solid {_CIAN}" if focused else "1px solid transparent"
        bg = self._color or self._row_bg
        self.setStyleSheet(
            f"QWidget#empNameOuter {{background:{bg}; border:{border};}}"
        )
        # Mantener el nombre LEGIBLE sobre el color elegido (texto oscuro sobre fondo claro y viceversa).
        self._aplicar_color_texto(bg)

    def _aplicar_color_texto(self, bg_hex: str):
        try:
            c = QColor(bg_hex)
            lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
            fg = "#0D1117" if lum > 140 else "#D0DCE8"
        except Exception:
            fg = "#D0DCE8"
        self._combo.setStyleSheet(
            "QComboBox#empSelectCombo {"
            f" background: transparent; border: none; color: {fg};"
            " font-family: 'Segoe UI'; font-size: 12px; padding: 0 8px;"
            "}"
            "QComboBox#empSelectCombo::drop-down { border: none; width: 16px; }"
        )

    # ── Color propio del empleado ─────────────────────────────────────────────
    def _on_brush_clicked(self):
        if callable(self.solicitar_color):
            self.solicitar_color(self)   # la tabla valida unicidad y aplica
            return
        # Fallback autónomo (sin gestor): abre el selector igualmente.
        try:
            from src.gui.color_picker import seleccionar_color
        except Exception:
            return
        hexcol = seleccionar_color(self, inicial=self._color or "#00FFC6",
                                   titulo=tr("cfg.emp_color_title", default="Color del empleado"))
        if hexcol:
            self.setColor(hexcol)

    def color(self) -> "str | None":
        return self._color

    def setColor(self, hexcol):
        self._color = hexcol or None
        self._set_style(focused=False)

    def avisar_color_duplicado(self):
        from PyQt6.QtWidgets import QToolTip
        QToolTip.showText(
            self._btn_color.mapToGlobal(self._btn_color.rect().bottomLeft()),
            tr("cfg.emp_color_dup", default="Ese color ya está asignado a otro empleado."),
            self._btn_color,
        )

    def eventFilter(self, obj, event):
        if obj is self._combo:
            t = event.type()
            if t == QEvent.Type.FocusIn:
                self._set_style(focused=True)
            elif t == QEvent.Type.FocusOut:
                self._set_style(focused=False)
        return super().eventFilter(obj, event)

    # ── selección / exclusión mutua (gestionada por la tabla contenedora) ─────

    def cargar_opciones(self, opciones: list):
        """`opciones`: `[(id_empleado, label), ...]` YA filtradas por
        `_HorarioTable.refrescar_opciones_dropdowns` (incluye siempre la selección ACTUAL de esta
        fila, aunque esté "tomada" en otra, para no perder el dato al repintar)."""
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItem(self.PLACEHOLDER, None)
        sel_idx = 0
        for i, (eid, label) in enumerate(opciones, start=1):
            self._combo.addItem(label or "", eid)
            if eid is not None and eid == self._current_id:
                sel_idx = i
        self._combo.setCurrentIndex(sel_idx)
        self._current_label = self._combo.itemText(sel_idx) if sel_idx > 0 else ""
        self._combo.blockSignals(False)

    def _on_index_changed(self, idx):
        self._current_id = self._combo.currentData()
        self._current_label = self._combo.currentText() if idx > 0 else ""
        self.idChanged.emit(self._current_id)
        self.textChanged.emit(self._current_label)

    def get_id(self):
        return self._current_id

    def set_id(self, id_empleado):
        """Fija el id seleccionado SIN repoblar el combo — usar antes de
        `cargar_opciones`/`refrescar_opciones_dropdowns` (p. ej. al restaurar desde disco)."""
        self._current_id = id_empleado

    # ── compat con el antiguo `_EmpNameEdit` (AUSENCIA, impresión, guardado) ──

    def text(self) -> str:
        return self._current_label

    def setText(self, t: str):
        # Compat: si se invoca con un id_empleado numérico, se interpreta como tal; con texto
        # libre no hay forma de mapear a un id real (ver `horarios_vinculo_empleado.py`), se
        # ignora — el llamador debe usar `set_id` para datos ya normalizados.
        pass

    def setPlaceholderText(self, t: str):
        pass  # compat no-op: el combo ya tiene su propio placeholder fijo (PLACEHOLDER)

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self._combo.setEnabled(enabled)
        self._btn_color.setEnabled(enabled)

    # ── aviso de descanso semanal (Fase E, punto 4) ───────────────────────────
    def set_warning(self, mensaje: "str | None"):
        self._warn_msg = mensaje
        if mensaje:
            if self._warn_btn is None:
                btn = QToolButton(self)
                btn.setText("!")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setFixedSize(14, 14)
                btn.setStyleSheet(
                    "QToolButton{background:#EF4444;color:#FFFFFF;border:none;"
                    "border-radius:7px;font-family:'Segoe UI';font-weight:bold;font-size:10px;}"
                    "QToolButton:hover{background:#FF6B6B;}"
                )
                btn.clicked.connect(self._mostrar_warning)
                self._warn_btn = btn
            self._warn_btn.move(2, 2)
            self._warn_btn.show()
            self._warn_btn.raise_()
        elif self._warn_btn is not None:
            self._warn_btn.hide()

    def _mostrar_warning(self):
        from assets.estilo_global import mostrar_mensaje
        mostrar_mensaje(self, tr("rrhh.descanso_warn_title", default="Aviso de descanso"),
                        self._warn_msg or "", "warning")


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
    # EMPLEADO se ensancha (145→184→360→270): a 184px el combo (`_EmpSelectCell`) solo tenía ≈124px
    # reales para el texto tras restar el botón pincel (24px) + su espaciado (4px) + el padding
    # interno del combo (16px) + la flecha del drop-down (16px) — insuficiente incluso para el
    # propio placeholder ("— Selecciona empleado —", ≈276px a 12px). 360px dejaba ≈300px de texto
    # (suficiente incluso para "Nombre Apellido1 Apellido2"), pero resultó demasiado ancho a ojo del
    # usuario, que pidió reducirlo un 25% (360×0.75=270) de forma explícita. A 270px quedan ≈210px
    # reales de texto: el placeholder y nombres cortos (1-2 palabras) siguen sin recortarse, pero un
    # nombre real de "Nombre Apellido1 Apellido2" (frecuente en España) SÍ hace elipsis — riesgo
    # conocido y aceptado a petición explícita del usuario; comportamiento normal de QComboBox
    # (tooltip/hover no muestran el texto completo salvo que se añada explícitamente).
    _W_EMP  = 270   # EMPLEADO column (nombre + botón de color)
    _W_TOT  = 145   # TOTAL SEMANA column
    _ROW_H0 = 32    # day header row
    _ROW_H1 = 30    # sub-header row
    _ROW_EMP = 44   # employee row
    _ROW_TOT = 36   # TOTAL DIARIO row

    def __init__(self, n_emp: int = 1, parent=None):
        super().__init__(parent)
        self._n_emp = max(1, n_emp)
        self._names: list[str] = [""] * self._n_emp
        self._colors: list[str] = [""] * self._n_emp   # color propio por empleado ("" = sin color)
        self._emp_ids: list = [None] * self._n_emp     # id_empleado real por fila (Fase E)
        self._empleados_cache: "list | None" = None    # [(id, "Nombre Apellidos"), ...] del centro
        self._solo_lectura = False                     # OPERARIO: rejilla no editable (Fase E)
        self._cells: list = []        # [emp][day] = (ini_w, fin_w)
        self._name_edits: list = []   # instancias de `_EmpSelectCell` (una por fila)
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

        # Construcción SÍNCRONA de todas las filas: la tabla aparece COMPLETA de una sola vez (todas las
        # filas, columnas y empleados) y más ágil, sin ceder al bucle de eventos entre filas (que añadía
        # un tick por empleado y hacía que se viera "a medias"). El filtro global sigue suspendido durante
        # el build y se restaura en _finalize_build; el diseño, la lógica y el contenido son idénticos.
        for e in range(n):
            if tbl is not self._tbl:   # un _build_table más reciente tomó el relevo
                return
            self._build_emp_row(tbl, e, n)
        self._finalize_build(tbl)

    def _build_emp_row(self, tbl: "QTableWidget", e: int, n: int):
        """Build one employee row (la iteración la conduce el bucle síncrono de _build_table)."""
        if tbl is not self._tbl:   # stale — a newer _build_table was called
            return

        row = 2 + e
        row_bg = "#0D1117" if e % 2 == 0 else "#0A0F14"

        name_w = _EmpSelectCell(row_bg)
        if e < len(self._emp_ids):
            name_w.set_id(self._emp_ids[e])
        name_w.solicitar_color = self._solicitar_color_para
        if e < len(self._colors) and self._colors[e]:
            name_w.setColor(self._colors[e])
        name_w.textChanged.connect(lambda t, idx=e: self._on_name_changed(idx, t))
        name_w.idChanged.connect(lambda eid, idx=e: self._on_emp_id_changed(idx, eid))
        name_w.setEnabled(not self._solo_lectura)
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
            ini_w.setEnabled(not self._solo_lectura)
            fin_w.setEnabled(not self._solo_lectura)
            day_cells.append((ini_w, fin_w))

        it_sem = QTableWidgetItem("0h 00min")
        it_sem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it_sem.setForeground(QColor(_CIAN))
        it_sem.setBackground(QColor(row_bg))
        fs = it_sem.font(); fs.setFamily("Segoe UI"); fs.setBold(True); fs.setPointSize(10)
        it_sem.setFont(fs)
        tbl.setItem(row, 22, it_sem)
        self._cells.append(day_cells)
        # La siguiente fila la construye el bucle síncrono de _build_table (ya no se auto-programa por
        # timer): así la tabla se completa de golpe, sin medias tintas.

    def _finalize_build(self, tbl: "QTableWidget"):
        """Called after all employee rows are populated."""
        if tbl is not self._tbl:   # stale
            return
        self._apply_all_absences()
        self.refrescar_opciones_dropdowns()
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

    def _solicitar_color_para(self, cell: "_EmpSelectCell"):
        """Abre el selector de color estándar para `cell` y aplica el color SOLO si es único (cada
        empleado un color distinto). Punto único que conoce todos los colores en uso."""
        from src.gui.color_picker import seleccionar_color
        usados = {(c.color() or "").lower() for c in self._name_edits
                  if c is not cell and c.color()}
        hexcol = seleccionar_color(cell, inicial=cell.color() or _CIAN,
                                   titulo=tr("cfg.emp_color_title", default="Color del empleado"))
        if not hexcol:
            return
        if hexcol.lower() in usados:
            cell.avisar_color_duplicado()
            return
        cell.setColor(hexcol)

    # ── desplegable de empleados: exclusión mutua (Fase E, punto 1) ───────────

    def _empleados_disponibles(self) -> list:
        """`[(id_empleado, "Nombre Apellidos"), ...]` del centro actual (empresa activa vía
        `db.empresa.empresa_actual_id`, resuelta dentro de `listar_empleados`), cacheado por
        instancia de tabla. Sin filtrar por `estado`: un empleado ya de baja debe poder seguir
        apareciendo en una fila que YA lo tuviera asignado (mismo criterio que
        `horarios_vinculo_empleado._mapa_empleados`)."""
        if self._empleados_cache is None:
            try:
                from src.rrhh.db.empleados import listar_empleados
                empleados = listar_empleados() or []
            except Exception:
                empleados = []
            opciones = []
            for e in empleados:
                eid = e.get("id")
                if not eid:
                    continue
                nombre = (e.get("nombre") or "").strip()
                apellidos = (e.get("apellidos") or "").strip()
                label = f"{nombre} {apellidos}".strip() if apellidos else nombre
                opciones.append((eid, label or f"Empleado {eid}"))
            self._empleados_cache = opciones
        return self._empleados_cache

    def refrescar_opciones_dropdowns(self):
        """Recalcula, para CADA fila, la lista de empleados que puede ofrecer su desplegable:
        todos los del centro MENOS los ya elegidos en OTRA fila de esta misma tabla (exclusión
        mutua) — la propia selección de la fila siempre se incluye, para no perderla al repintar.
        Se invoca cada vez que cambia la selección de cualquier fila."""
        if not self._name_edits:
            return
        todos = self._empleados_disponibles()
        ocupados = {cell.get_id() for cell in self._name_edits if cell.get_id() is not None}
        for cell in self._name_edits:
            propio = cell.get_id()
            disponibles = [(eid, label) for eid, label in todos
                           if eid not in ocupados or eid == propio]
            cell.cargar_opciones(disponibles)

    def _on_emp_id_changed(self, idx: int, id_empleado):
        if idx < len(self._emp_ids):
            self._emp_ids[idx] = id_empleado
        self.refrescar_opciones_dropdowns()

    def get_id_label_pairs(self) -> list:
        """`[(id_empleado, label), ...]` de las filas con un empleado real asignado — usado por el
        botón "Bolsa de horas" para ofrecer el selector de empleado (Fase E, punto 3)."""
        return [(cell.get_id(), cell.text()) for cell in self._name_edits if cell.get_id()]

    # ── solo lectura por rol (Fase E, punto 2) ────────────────────────────────

    def set_solo_lectura(self, solo_lectura: bool):
        """OPERARIO: ninguna celda de esta tabla es editable (ni el desplegable de empleado ni los
        turnos). Se puede llamar ANTES de que la tabla termine de construirse (`_finalize_build`
        vuelve a aplicar el estado guardado sobre las filas ya creadas)."""
        self._solo_lectura = solo_lectura
        self._aplicar_solo_lectura()

    def _aplicar_solo_lectura(self):
        editable = not self._solo_lectura
        for cell in self._name_edits:
            cell.setEnabled(editable)
        for row in self._cells:
            for ini_w, fin_w in row:
                ini_w.setEnabled(editable)
                fin_w.setEnabled(editable)

    # ── avisos de descanso mínimo (Fase E, punto 4) ───────────────────────────

    def aplicar_avisos_descanso(self) -> dict:
        """Recalcula, para cada fila con empleado, las violaciones de descanso mínimo (diario 12h
        / semanal 1,5 días) a partir de los propios datos de inicio/fin ya guardados en la
        rejilla (`src.rrhh.descansos.verificar_descansos_semana`, función pura) y refresca los
        iconos "!" de aviso. Se invoca al GUARDAR la rejilla (`horarios_gui.py`). Devuelve
        `{emp_idx: [violaciones]}` (uso interno/tests)."""
        from src.rrhh.descansos import verificar_descansos_semana
        resumen: dict = {}
        for e in range(len(self._cells)):
            turnos = []
            for d in range(7):
                if (e, d) in self._absences:
                    turnos.append(None)
                    continue
                ini_w, fin_w = self._cells[e][d]
                ini_s, fin_s = ini_w.get_state(), fin_w.get_state()
                if ini_s.get("modo") == "normal" and fin_s.get("modo") == "normal":
                    ini_min = ini_s["h"] * 60 + ini_s["m"]
                    fin_min = fin_s["h"] * 60 + fin_s["m"]
                    # `_TurnoCelda.get_state()` no distingue "celda nunca tocada" de "00:00" real
                    # (el combo de horas no tiene opción en blanco) — una duración de 0 minutos
                    # (ini==fin, típicamente 00:00-00:00 en una fila recién creada) se interpreta
                    # como "sin turno ese día", no como un turno real de duración cero; evita avisos
                    # de descanso falsos sobre filas todavía sin rellenar.
                    turnos.append({"ini_min": ini_min, "fin_min": fin_min}
                                  if fin_min > ini_min else None)
                else:
                    turnos.append(None)

            # limpia avisos previos de la fila antes de recalcular
            for d in range(7):
                if (e, d) in self._absences:
                    continue
                ini_w, fin_w = self._cells[e][d]
                ini_w.set_warning(None)
                fin_w.set_warning(None)
            if e < len(self._name_edits):
                self._name_edits[e].set_warning(None)

            violaciones = verificar_descansos_semana(turnos)
            for v in violaciones:
                if v["tipo"] == "diario":
                    da, db = v["dia_a"], v["dia_b"]
                    if (e, da) not in self._absences:
                        self._cells[e][da][1].set_warning(v["mensaje"])
                    if (e, db) not in self._absences:
                        self._cells[e][db][0].set_warning(v["mensaje"])
                elif v["tipo"] == "semanal" and e < len(self._name_edits):
                    self._name_edits[e].set_warning(v["mensaje"])
            resumen[e] = violaciones
        return resumen

    # ── row management ───────────────────────────────────────────────────────

    def add_row(self):
        """Add one employee row incrementally — no full table rebuild."""
        if self._tbl is None:
            # Table not yet built; just bump count and let the pending build handle it.
            self._n_emp += 1
            self._names = [""] * self._n_emp
            self._colors = [""] * self._n_emp
            self._emp_ids = [None] * self._n_emp
            return

        e = self._n_emp
        self._names = [ed.text() for ed in self._name_edits] + [""]
        self._colors = [(ed.color() or "") for ed in self._name_edits] + [""]
        self._emp_ids = [ed.get_id() for ed in self._name_edits] + [None]
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

        name_w = _EmpSelectCell(row_bg)
        name_w.solicitar_color = self._solicitar_color_para
        name_w.textChanged.connect(lambda t, idx=e: self._on_name_changed(idx, t))
        name_w.idChanged.connect(lambda eid, idx=e: self._on_emp_id_changed(idx, eid))
        name_w.setEnabled(not self._solo_lectura)
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
            ini_w.setEnabled(not self._solo_lectura)
            fin_w.setEnabled(not self._solo_lectura)
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
        self.refrescar_opciones_dropdowns()

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
        ids = [e.get_id() for e in self._name_edits]
        colors = [(e.color() or "") for e in self._name_edits]
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
        # "ids" (Fase E) es la fuente de verdad de "qué empleado real es esta fila"; "names" se
        # conserva como texto de respaldo (visualización / migración desde datos antiguos), ver
        # `rrhh/horarios_vinculo_empleado.py`.
        return {"names": names, "ids": ids, "colors": colors, "schedule": schedule, "absences": absences}

    def set_state(self, data: dict):
        names = data.get("names", [])
        ids = data.get("ids", [])
        colors = data.get("colors", [])
        n_new = max(self._n_emp, len(names), len(ids))
        names_padded = list(names) + [""] * (n_new - len(names))
        ids_padded = list(ids) + [None] * (n_new - len(ids))
        colors_padded = list(colors) + [""] * (n_new - len(colors))
        self._colors = colors_padded
        self._emp_ids = ids_padded
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
            # Same employee count — refresh names, colors, restore schedule, apply absences.
            self._names = names_padded
            for i, edit in enumerate(self._name_edits):
                if i < len(ids_padded):
                    edit.set_id(ids_padded[i])
                edit.setColor(colors_padded[i] if i < len(colors_padded) else None)
            self.refrescar_opciones_dropdowns()
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

    def __init__(self, n_emp: int = 1, parent=None, usuario: dict = None):
        super().__init__(parent)
        # RRHH Fase E: rol del usuario en sesión (dict de `sesion_global.usuario_actual`) — decide
        # el modo solo lectura de OPERARIO y qué puede ver/hacer el botón "Bolsa de horas".
        self._usuario = usuario or {}
        self._perfil = str(self._usuario.get("perfil") or "").upper()
        self._es_operario = self._perfil == "OPERARIO"
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
                background: #11181D; border: 1px solid white;
                border-radius: 8px; color: white;
                font-family: 'Segoe UI'; font-weight: bold; font-size: 13px;
                padding: 0 14px;
            }
            QPushButton:hover { background: white; color: #0E1117; }
        """)
        btn_ausencia.clicked.connect(self._show_ausencia)
        self._move_icon = _MoveIcon(self._start_drag)

        # "Bolsa de horas" (RRHH Fase E, punto 3): visible para TODOS los roles, pero con reglas
        # distintas — ver `_on_bolsa_horas`. Es el ÚNICO botón que OPERARIO ve en toda la ventana.
        btn_bolsa = QPushButton(tr("rrhh.bolsa_horas_btn", default="BOLSA DE HORAS"))
        btn_bolsa.setFixedHeight(36)
        btn_bolsa.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_bolsa.setStyleSheet(f"""
            QPushButton {{
                background: #11181D; border: 1px solid {_CIAN};
                border-radius: 8px; color: {_CIAN};
                font-family: 'Segoe UI'; font-weight: bold; font-size: 13px;
                padding: 0 16px;
            }}
            QPushButton:hover {{ background: {_CIAN}; color: #0E1117; }}
        """)
        btn_bolsa.clicked.connect(self._on_bolsa_horas)
        self._btn_bolsa = btn_bolsa

        title_row.addWidget(self._title_edit, 1)
        title_row.addWidget(btn_print)
        title_row.addWidget(btn_del)
        title_row.addWidget(btn_ausencia)
        title_row.addWidget(btn_bolsa)
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

        # RRHH Fase E, punto 2: OPERARIO ve la rejilla en modo SOLO LECTURA, sin ningún botón de
        # edición — el ÚNICO botón visible para él es "Bolsa de horas" (y solo si tiene
        # `horas_diarias` ya definidas, ver `_operario_tiene_bolsa_definida`).
        if self._es_operario:
            btn_print.setVisible(False)
            btn_del.setVisible(False)
            btn_ausencia.setVisible(False)
            btn_add.setVisible(False)
            self._move_icon.setVisible(False)
            self._title_edit.setReadOnly(True)
            self._grid.set_solo_lectura(True)
            btn_bolsa.setVisible(self._operario_tiene_bolsa_definida())
        else:
            btn_bolsa.setVisible(True)

    def _sync_scroll_height(self):
        self._hscroll.setFixedHeight(self._grid.height() + 14)

    def _add_row(self):
        self._grid.add_row()
        self._hscroll.setFixedHeight(self._grid.height() + 14)

    # ── "Bolsa de horas" (RRHH Fase E, punto 3) ───────────────────────────────

    def _resolver_id_empleado_propio(self) -> "int | None":
        """`id_empleado` de la cuenta de usuario en sesión (vínculo `rrhh_empleados.id_usuario`) —
        usado por OPERARIO, que solo puede consultar su PROPIA bolsa de horas."""
        id_usuario = self._usuario.get("id")
        if not id_usuario:
            return None
        try:
            from src.rrhh.db.empleados import obtener_por_usuario
            emp = obtener_por_usuario(id_usuario)
            return (emp or {}).get("id")
        except Exception:
            return None

    def _operario_tiene_bolsa_definida(self) -> bool:
        id_emp = self._resolver_id_empleado_propio()
        if not id_emp:
            return False
        try:
            from src.rrhh.bolsa_horas import obtener_bolsa_horas
            bolsa = obtener_bolsa_horas(id_emp)
            return bool(bolsa) and bolsa.get("horas_diarias") is not None
        except Exception:
            return False

    def _on_bolsa_horas(self):
        from src.rrhh.gui.bolsa_horas_dialog import abrir_bolsa_horas, elegir_empleado_dialog

        if self._es_operario:
            id_emp = self._resolver_id_empleado_propio()
            if not id_emp:
                mostrar_mensaje(
                    self, tr("rrhh.bolsa_titulo_corto", default="Bolsa de horas"),
                    tr("rrhh.bolsa_sin_ficha", default="No se pudo identificar tu ficha de empleado."),
                    "warning")
                return
            nombre = self._usuario.get("nombre") or self._usuario.get("usuario") or ""
            abrir_bolsa_horas(self, id_emp, nombre, puede_definir=False)
            return

        # ADMINISTRADOR/SUPERADMIN: eligen entre los empleados presentes en ESTA tabla.
        pares = self._grid.get_id_label_pairs()
        if not pares:
            mostrar_mensaje(
                self, tr("rrhh.bolsa_titulo_corto", default="Bolsa de horas"),
                tr("rrhh.bolsa_sin_empleados", default="No hay empleados en esta tabla para consultar."),
                "warning")
            return
        if len(pares) == 1:
            id_emp, nombre = pares[0]
        else:
            id_emp = elegir_empleado_dialog(self, pares)
            if id_emp is None:
                return
            nombre = next((lbl for eid, lbl in pares if eid == id_emp), "")
        abrir_bolsa_horas(self, id_emp, nombre, puede_definir=True)

    # ── avisos de descanso mínimo (Fase E, punto 4) ───────────────────────────

    def aplicar_avisos_descanso(self) -> dict:
        return self._grid.aplicar_avisos_descanso()

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
        # Sin argumento de forma: `grabMouse(QCursor)` fuerza el cursor NATIVO del sistema durante
        # el grab (bypassa setCursor()/CursorChange), perdiendo el cursor de 4 flechas personalizado
        # de assets/cursores justo al empezar a arrastrar. Se fija el cursor en ESTE widget (el que
        # recibe el grab, no el icono de arrastre que lo disparó) para que el remapeo global de
        # `utils.cursores` lo sustituya por el PNG propio, y `grabMouse()` a secas lo conserva
        # durante todo el arrastre en vez de forzar el de sistema.
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.grabMouse()

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
        self.unsetCursor()  # revierte el cursor de 4 flechas fijado en begin_drag al soltar


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
