"""
Smart Manager AI - Global style system

Search keywords:
- SECTION TOKENS
- SECTION HELPERS
- SECTION FEEDBACK HELPERS
- SECTION FILTERS
- SECTION PUBLIC API
- SECTION QSS ROOT
- SECTION QSS SIDEBAR
- SECTION QSS LOGIN
- SECTION QSS INPUTS
- SECTION QSS BUTTONS
- SECTION QSS TABLES
- SECTION QSS DIALOGS
- SECTION QSS SCANNER
"""

import ctypes
import re
import sys

try:
    from PyQt6.QtCore import QEvent, QObject, Qt
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import (
        QAbstractButton,
        QAbstractItemView,
        QAbstractSpinBox,
        QCheckBox,
        QComboBox,
        QDateEdit,
        QDialog,
        QDialogButtonBox,
        QFrame,
        QGroupBox,
        QGraphicsDropShadowEffect,
        QHeaderView,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListView,
        QListWidget,
        QMenu,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QRadioButton,
        QScrollArea,
        QSlider,
        QTabBar,
        QTableView,
        QTableWidget,
        QTextEdit,
        QTimeEdit,
        QToolButton,
        QTreeView,
        QTreeWidget,
        QVBoxLayout,
        QWidget,
    )
except Exception:  # pragma: no cover
    QEvent = None
    QObject = object
    Qt = None
    QFont = None
    QAbstractButton = None
    QAbstractItemView = None
    QAbstractSpinBox = None
    QCheckBox = None
    QComboBox = None
    QDateEdit = None
    QDialog = None
    QDialogButtonBox = None
    QFrame = None
    QGroupBox = None
    QGraphicsDropShadowEffect = None
    QHeaderView = None
    QHBoxLayout = None
    QLabel = None
    QLineEdit = None
    QListView = None
    QListWidget = None
    QMenu = None
    QMessageBox = None
    QPlainTextEdit = None
    QPushButton = None
    QRadioButton = None
    QScrollArea = None
    QSlider = None
    QTabBar = None
    QTableView = None
    QTableWidget = None
    QTextEdit = None
    QTimeEdit = None
    QToolButton = None
    QTreeView = None
    QTreeWidget = None
    QVBoxLayout = None
    QWidget = None


# =========================================================
# SECTION TOKENS
# =========================================================
FUENTE_APP = "Segoe UI"
COLOR_CIAN = "#00FFC6"
COLOR_CIAN_HOVER = "#00E6B2"
COLOR_CIAN_PRESION = "#00C79A"
COLOR_VERDE_OK = "#1ED760"
COLOR_VERDE_OK_HOVER = "#16C955"
COLOR_VERDE_OK_PRESION = "#12A845"
COLOR_FONDO_APP = "#0E1117"
COLOR_FONDO_APP_SECUNDARIO = "#10151C"
COLOR_FONDO_SIDEBAR = "#111418"
COLOR_FONDO_WIDGET = "#161B22"
COLOR_GRIS_PANEL = "#1A1D23"
COLOR_GRIS_HOVER = "#21262D"
COLOR_GRIS_SUAVE = "#2A313C"
COLOR_GRIS_NEUTRO = "#5B6470"
COLOR_GRIS_NEUTRO_HOVER = "#6D7785"
COLOR_GRIS_NEUTRO_PRESION = "#4C5460"
COLOR_NEGRO_PANEL = "#05070A"
COLOR_BORDE = "#30363D"
COLOR_BORDE_SIDEBAR = "#1C2128"
COLOR_TEXTO_PRINCIPAL = "#FFFFFF"
COLOR_TEXTO_SECUNDARIO = "#8B949E"
COLOR_TEXTO_MUTED = "#4B5563"
COLOR_ROJO_ERROR = "#F85149"
COLOR_ROJO_HOVER = "#FF6E67"
COLOR_ROJO_PRESION = "#D63F38"
COLOR_AMBAR = "#F1C40F"
RADIO_XS = "8px"
RADIO_SM = "10px"
RADIO_MD = "12px"
RADIO_LG = "16px"
RADIO_XL = "20px"
RADIO_XXL = "24px"
RADIO_SCANNER = "30px"
RADIO_TABLAS = "20px"

_APP_FILTER = None


# =========================================================
# SECTION HELPERS
# =========================================================
def _safe_instance(widget, klass):
    return klass is not None and widget is not None and isinstance(widget, klass)


def _normalize_text(value):
    text = str(value or "").strip().lower()
    replacements = str.maketrans(
        {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n"}
    )
    return text.translate(replacements)


def _repolish(widget):
    if widget is None:
        return
    try:
        style = widget.style()
        if style is not None:
            style.unpolish(widget)
            style.polish(widget)
        widget.update()
    except Exception:
        pass


# =========================================================
# SECTION FEEDBACK HELPERS
# (escaneo, suma de ítems; propiedades flashHighlight / tituloProcesando en QSS)
# =========================================================


def repolish_widget(widget):
    """Fuerza reaplicación de QSS tras cambiar propiedades dinámicas (p. ej. flashHighlight)."""
    _repolish(widget)


def feedback_lineedit_exito(widget, duracion_ms=1200):
    """Resalta temporalmente un QLineEdit con borde neón (p. ej. tras escaneo). Requiere objectName input_buscador."""
    if widget is None:
        return
    try:
        from PyQt6.QtCore import QTimer
    except Exception:
        return

    widget.setProperty("flashHighlight", True)
    _repolish(widget)

    def _limpiar():
        widget.setProperty("flashHighlight", False)
        _repolish(widget)

    QTimer.singleShot(int(duracion_ms), _limpiar)


def feedback_frame_item_resaltado(frame, duracion_ms=500):
    """Borde neón temporal en filas item_frame_articulo / item_frame_logistico."""
    if frame is None:
        return
    try:
        from PyQt6.QtCore import QTimer
    except Exception:
        return

    frame.setProperty("flashHighlight", True)
    _repolish(frame)

    def _limpiar():
        frame.setProperty("flashHighlight", False)
        _repolish(frame)

    QTimer.singleShot(int(duracion_ms), _limpiar)


def construir_plantilla_camara(
    dialogo,
    *,
    titulo="VISIÓN - ESCÁNER",
    texto_video="PANEL DE ESCANEO\n\nPulse 'INICIAR' para activar la cámara",
    estado_inicial="Estado: En espera de acción",
    texto_boton_primario="INICIAR ESCANEO",
    texto_boton_cancelar="ABORTAR OPERACIÓN",
    ancho=650,
    alto=600,
    ancho_video=580,
    alto_video=330,
    mostrar_boton_primario=True,
    object_name_dialog="scanner_dialog",
    object_name_frame="cuerpo_ventana_scan",
):
    """
    Plantilla universal para ventanas de cámara.
    Devuelve referencias a widgets para que cada módulo personalice su lógica.
    """
    if dialogo is None or Qt is None:
        return {}

    dialogo.setObjectName(object_name_dialog)
    dialogo.setFixedSize(int(ancho), int(alto))
    dialogo.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
    dialogo.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    main_frame = QFrame(dialogo)
    main_frame.setObjectName(object_name_frame)
    main_frame.setGeometry(0, 0, int(ancho), int(alto))

    layout = QVBoxLayout(main_frame)
    layout.setContentsMargins(30, 30, 30, 30)
    layout.setSpacing(15)

    lbl_titulo = QLabel(str(titulo))
    lbl_titulo.setObjectName("titulo_scan")
    lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(lbl_titulo)

    lbl_video = QLabel(str(texto_video))
    lbl_video.setObjectName("feed_video")
    lbl_video.setProperty("activo", False)
    lbl_video.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl_video.setFixedSize(int(ancho_video), int(alto_video))
    layout.addWidget(lbl_video, alignment=Qt.AlignmentFlag.AlignCenter)

    lbl_status = QLabel(str(estado_inicial))
    lbl_status.setObjectName("scanner_status")
    lbl_status.setProperty("estado", "idle")
    lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(lbl_status)

    btn_primario = QPushButton(str(texto_boton_primario))
    btn_primario.setObjectName("btn_primario")
    btn_primario.setFixedHeight(55)
    btn_primario.setVisible(bool(mostrar_boton_primario))
    layout.addWidget(btn_primario)

    btn_cancelar = QPushButton(str(texto_boton_cancelar))
    btn_cancelar.setObjectName("btn_abortar_scan")
    btn_cancelar.setFixedHeight(45)
    layout.addWidget(btn_cancelar)

    for widget in (lbl_titulo, lbl_video, lbl_status, btn_primario, btn_cancelar):
        _set_widget_cursor(widget)
        _apply_font(widget)
        _set_widget_background_flag(widget)
        _repolish(widget)

    return {
        "main_frame": main_frame,
        "layout": layout,
        "lbl_titulo": lbl_titulo,
        "lbl_video": lbl_video,
        "lbl_status": lbl_status,
        "btn_primario": btn_primario,
        "btn_cancelar": btn_cancelar,
    }


def construir_tabla_estilizada(parent=None):
    """
    Plantilla visual universal para tablas Smart Manager AI.
    Devuelve (contenedor, tabla) y deja filas/columnas al módulo consumidor.
    """
    if QFrame is None or QVBoxLayout is None or QTableWidget is None:
        return None, None

    contenedor = QFrame(parent)
    contenedor.setObjectName("contenedor_tabla_estandar")

    layout = QVBoxLayout(contenedor)
    layout.setContentsMargins(2, 2, 2, 2)
    layout.setSpacing(0)

    tabla = QTableWidget(contenedor)
    tabla.setObjectName("tabla_estandar_smart")
    tabla.verticalHeader().setVisible(False)
    tabla.setAlternatingRowColors(True)
    tabla.setShowGrid(False)
    tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tabla.setFrameShape(QFrame.Shape.NoFrame)
    tabla.setCornerButtonEnabled(False)

    layout.addWidget(tabla)

    _set_widget_background_flag(contenedor)
    _set_widget_background_flag(tabla)
    _repolish(contenedor)
    _repolish(tabla)
    return contenedor, tabla


def _apply_font(widget):
    if widget is None or QFont is None or not hasattr(widget, "font"):
        return
    try:
        font = widget.font()
        font.setFamily(FUENTE_APP)
        font.setWeight(QFont.Weight.Bold)
        widget.setFont(font)
    except Exception:
        pass


def _set_widget_background_flag(widget):
    if widget is None:
        return
    try:
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    except Exception:
        pass


def _set_widget_cursor(widget):
    if widget is None or Qt is None:
        return
    try:
        if any(_safe_instance(widget, klass) for klass in (QLineEdit, QTextEdit, QPlainTextEdit)):
            widget.setCursor(Qt.CursorShape.IBeamCursor)
            return
        clickable = (
            QAbstractButton,
            QComboBox,
            QAbstractItemView,
            QHeaderView,
            QTabBar,
            QMenu,
            QSlider,
            QScrollArea,
            QDateEdit,
            QTimeEdit,
            QAbstractSpinBox,
        )
        if any(_safe_instance(widget, klass) for klass in clickable):
            widget.setCursor(Qt.CursorShape.PointingHandCursor)
    except Exception:
        pass


def _button_role_from_name_or_text(widget):
    if widget is None:
        return None
    object_name = _normalize_text(getattr(widget, "objectName", lambda: "")())
    text_value = _normalize_text(widget.text() if hasattr(widget, "text") else "")
    words = set(re.findall(r"[a-z0-9_]+", f"{object_name} {text_value}".strip()))

    if object_name in {"btn_primario", "btn_secundario", "btn_neon", "btn_sidebar"}:
        return None
    if object_name in {"btn_peligro", "btn_sidebar_exit"}:
        return "danger"

    danger_words = {"salir", "cerrar", "eliminar", "borrar", "abortar", "exit", "delete"}
    neutral_words = {"cancelar", "cancel", "volver", "no", "omitir", "skip"}
    success_words = {"aceptar", "continuar", "confirmar", "guardar", "aplicar", "iniciar", "si", "yes", "save", "ok", "confirm", "continue"}

    if words & danger_words:
        return "danger"
    if words & neutral_words:
        return "neutral"
    if words & success_words:
        return "success"
    return None


def _apply_button_role(widget):
    if widget is None or not _safe_instance(widget, QAbstractButton):
        return
    role = _button_role_from_name_or_text(widget)
    if role is None:
        return
    try:
        if widget.property("semanticRole") != role:
            widget.setProperty("semanticRole", role)
            _repolish(widget)
    except Exception:
        pass


def _apply_combo_extras(widget):
    if widget is None or not _safe_instance(widget, QComboBox):
        return
    try:
        view = widget.view()
        if view is not None:
            _apply_font(view)
            _set_widget_cursor(view)
            if hasattr(view, "objectName") and not view.objectName():
                view.setObjectName("combo_popup_generic")
    except Exception:
        pass


def _apply_dialog_semantics(widget):
    if widget is None:
        return
    try:
        if _safe_instance(widget, QMessageBox):
            widget.setObjectName("smart_message_box")
            for button in widget.buttons():
                _apply_font(button)
                _set_widget_cursor(button)
                _apply_button_role(button)
        elif _safe_instance(widget, QDialogButtonBox):
            for button in widget.buttons():
                _apply_font(button)
                _set_widget_cursor(button)
                _apply_button_role(button)
    except Exception:
        pass


def _apply_native_dialog_chrome(widget):
    """Quita la barra de título nativa clásica en QMessageBox / QInputDialog (estilo app)."""
    if widget is None or Qt is None:
        return
    try:
        if not hasattr(widget, "isWindow") or not widget.isWindow():
            return
        flags = widget.windowFlags()
        widget.setWindowFlags(
            flags
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
        )
    except Exception:
        pass


def _apply_windows_dark_title_bar(widget):
    if widget is None or sys.platform != "win32":
        return

    try:
        if not hasattr(widget, "isWindow") or not widget.isWindow():
            return

        hwnd = int(widget.winId())
        if not hwnd:
            return

        DWMWA_USE_IMMERSIVE_DARK_MODE_FALLBACK = 19
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)

        for attr in (
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            DWMWA_USE_IMMERSIVE_DARK_MODE_FALLBACK,
        ):
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)
                )
            except Exception:
                continue
    except Exception:
        pass


# =========================================================
# SECTION FILTERS
# =========================================================
class _SmartGlobalFilter(QObject):
    def eventFilter(self, watched, event):
        if watched is None or event is None or Qt is None or QEvent is None:
            return super().eventFilter(watched, event)
        try:
            if event.type() == QEvent.Type.Show and (
                _safe_instance(watched, QMessageBox)
                or _safe_instance(watched, QInputDialog)
            ):
                _apply_native_dialog_chrome(watched)
            if event.type() in {
                QEvent.Type.Show,
                QEvent.Type.Polish,
                QEvent.Type.EnabledChange,
                QEvent.Type.DynamicPropertyChange,
            }:
                aplicar_estilo_widget(watched)
        except Exception:
            pass
        return super().eventFilter(watched, event)


class SmartMessageDialog(QDialog):
    ROLE_TO_RESULT = {
        "ok": 1,
        "yes": 2,
        "no": 3,
        "cancel": 4,
    }

    LEVEL_COLORS = {
        "info": COLOR_CIAN,
        "warning": COLOR_AMBAR,
        "error": COLOR_ROJO_ERROR,
        "question": "#2D8CFF",
        "success": COLOR_VERDE_OK,
    }

    LEVEL_SYMBOLS = {
        "info": "i",
        "warning": "!",
        "error": "×",
        "question": "?",
        "success": "✓",
    }

    def __init__(self, parent=None, title="", message="", level="info", buttons=None):
        super().__init__(parent)
        self.dialog_result = 0
        self.level = str(level or "info").lower()
        self.buttons = list(buttons or ["ok"])

        self.setObjectName("smart_message_dialog")
        self.setWindowTitle(title or "Smart Manager AI")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)

        self.panel = QFrame(self)
        self.panel.setObjectName("smart_message_panel")
        outer.addWidget(self.panel)
        self.panel.setMinimumWidth(320)

        if QGraphicsDropShadowEffect is not None:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(34)
            shadow.setOffset(0, 0)
            shadow.setColor(self._to_qcolor(self.LEVEL_COLORS.get(self.level, COLOR_CIAN), 180))
            self.panel.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(16)

        row = QHBoxLayout()
        row.setSpacing(14)

        self.icon_label = QLabel(self.LEVEL_SYMBOLS.get(self.level, "i"))
        self.icon_label.setObjectName("smart_message_icon")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setFixedSize(46, 46)
        row.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(6)

        self.title_label = QLabel(str(title or "Sistema"))
        self.title_label.setObjectName("smart_message_title")
        self.title_label.setWordWrap(True)
        text_col.addWidget(self.title_label)

        self.message_label = QLabel(str(message or ""))
        self.message_label.setObjectName("smart_message_text")
        self.message_label.setWordWrap(True)
        text_col.addWidget(self.message_label)

        row.addLayout(text_col, 1)
        layout.addLayout(row)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        for btn_role in self.buttons:
            button = QPushButton(self._button_text(btn_role))
            button.setMinimumWidth(132)
            button.setProperty("semanticRole", self._semantic_role(btn_role))
            button.clicked.connect(
                lambda _checked=False, role=btn_role: self._finish(role)
            )
            aplicar_estilo_widget(button)
            button_row.addWidget(button)

        layout.addLayout(button_row)

        self._apply_inline_visuals()

    def _to_qcolor(self, hex_color, alpha=255):
        from PyQt6.QtGui import QColor

        color = QColor(hex_color)
        color.setAlpha(alpha)
        return color

    def _button_text(self, role):
        mapping = {
            "ok": "OK",
            "yes": "Sí",
            "no": "No",
            "cancel": "Cancelar",
        }
        return mapping.get(str(role).lower(), str(role).upper())

    def _semantic_role(self, role):
        role = str(role).lower()
        if role in {"yes", "ok"}:
            return "success"
        if role in {"no", "cancel"}:
            return "neutral"
        return "success"

    def _finish(self, role):
        self.dialog_result = self.ROLE_TO_RESULT.get(str(role).lower(), 0)
        self.accept()

    def _apply_inline_visuals(self):
        accent = self.LEVEL_COLORS.get(self.level, COLOR_CIAN)
        self.panel.setStyleSheet(
            f"""
            QFrame#smart_message_panel {{
                background-color: {COLOR_NEGRO_PANEL};
                border: 2px solid {accent};
                border-radius: {RADIO_XL};
            }}
            QLabel#smart_message_icon {{
                background-color: {accent};
                color: {COLOR_FONDO_APP};
                border-radius: 23px;
                font-family: '{FUENTE_APP}';
                font-size: 26px;
                font-weight: 900;
            }}
            QLabel#smart_message_title {{
                color: {COLOR_TEXTO_PRINCIPAL};
                background: transparent;
                border: none;
                font-family: '{FUENTE_APP}';
                font-size: 15px;
                font-weight: 900;
            }}
            QLabel#smart_message_text {{
                color: {COLOR_TEXTO_PRINCIPAL};
                background: transparent;
                border: none;
                font-family: '{FUENTE_APP}';
                font-size: 13px;
                font-weight: 900;
            }}
            """
        )

    def showEvent(self, event):
        super().showEvent(event)
        try:
            _apply_windows_dark_title_bar(self)
            parent = self.parentWidget()
            if parent is not None:
                center = parent.frameGeometry().center()
                frame = self.frameGeometry()
                frame.moveCenter(center)
                self.move(frame.topLeft())
        except Exception:
            pass


# =========================================================
# SECTION PUBLIC API
# =========================================================
def aplicar_estilo_app(app):
    global _APP_FILTER

    if app is None:
        return

    if QFont is not None:
        app.setFont(QFont(FUENTE_APP, 10, QFont.Weight.Bold))

    app.setStyleSheet(ESTILO_GLOBAL)

    if _APP_FILTER is None and QObject is not object:
        _APP_FILTER = _SmartGlobalFilter(app)
        app.installEventFilter(_APP_FILTER)

    for widget in getattr(app, "allWidgets", lambda: [])():
        try:
            aplicar_estilo_widget(widget)
        except Exception:
            pass


def aplicar_estilo_widget(widget):
    if widget is None or Qt is None:
        return

    _set_widget_background_flag(widget)
    _apply_font(widget)
    _set_widget_cursor(widget)
    _apply_button_role(widget)
    _apply_combo_extras(widget)
    _apply_dialog_semantics(widget)
    _apply_windows_dark_title_bar(widget)

    try:
        object_name = widget.objectName() if hasattr(widget, "objectName") else ""
    except Exception:
        object_name = ""

    if object_name in {
        "btn_sidebar",
        "btn_sidebar_exit",
        "btn_primario",
        "btn_traspaso_land",
        "btn_secundario",
        "btn_peligro",
        "btn_neon",
        "btn_icono",
        "btn_icono_peligro",
        "login_combo_perfil",
        "combo_popup_view",
        "combo_popup_container",
        "password_frame",
        "card_neon",
        "titulo_cian",
        "titulo_logistico",
        "subtitulo_muted",
        "texto_auxiliar",
        "panel_bienvenida",
        "panel_neon_soft",
        "panel_dialogo_logistico",
        "contenido_logistica",
        "input_buscador",
        "item_frame_articulo",
        "item_frame_logistico",
        "scanner_status",
        "feed_video",
        "contenedor_tabla_estandar",
        "tabla_estandar_smart",
    }:
        _repolish(widget)


def mostrar_mensaje(parent, titulo, mensaje, nivel="info", botones=None):
    dialogo = SmartMessageDialog(
        parent=parent,
        title=titulo,
        message=mensaje,
        level=nivel,
        buttons=botones or ["ok"],
    )
    aplicar_estilo_widget(dialogo)
    dialogo.exec()
    return dialogo.dialog_result


def mostrar_confirmacion(parent, titulo, mensaje):
    resultado = mostrar_mensaje(
        parent=parent,
        titulo=titulo,
        mensaje=mensaje,
        nivel="question",
        botones=["yes", "no"],
    )
    return resultado == SmartMessageDialog.ROLE_TO_RESULT["yes"]


QSS_ROOT = f"""
/* =====================================================
   SECTION QSS ROOT
   ===================================================== */

QMainWindow, QDialog, QWidget {{
    background-color: {COLOR_FONDO_APP};
    color: {COLOR_TEXTO_PRINCIPAL};
    font-family: '{FUENTE_APP}';
    font-size: 13px;
    font-weight: 900;
    selection-background-color: {COLOR_GRIS_HOVER};
    selection-color: {COLOR_CIAN};
}}

QWidget#panel_raiz,
QWidget#panel_contenido,
QFrame#panel_raiz,
QFrame#panel_contenido {{
    background-color: transparent;
    border: none;
}}

QLabel, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox,
QDateEdit, QTimeEdit, QTableWidget, QTableView, QListWidget, QListView, QTreeWidget,
QTreeView, QGroupBox, QCheckBox, QRadioButton, QTabBar, QMenu, QHeaderView,
QPushButton, QToolButton {{
    font-family: '{FUENTE_APP}';
    font-weight: 900;
}}

QToolTip {{
    background-color: {COLOR_NEGRO_PANEL};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_MD};
    padding: 8px 12px;
}}

QFrame#panel_oscuro,
QFrame#card,
QFrame#card_neon,
QFrame#contenedor_neon,
QWidget#card,
QWidget#card_neon,
QWidget#panel_neon,
QFrame#panel_neon,
QWidget#dialogo_neon,
QFrame#dialogo_neon {{
    background-color: {COLOR_GRIS_PANEL};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_XL};
}}

QWidget#panel_neon_soft,
QFrame#panel_neon_soft,
QWidget#panel_bienvenida,
QFrame#panel_bienvenida,
QWidget#panel_dialogo_logistico,
QFrame#panel_dialogo_logistico {{
    background-color: {COLOR_GRIS_PANEL};
    border: 1px solid {COLOR_BORDE};
    border-radius: {RADIO_XL};
}}

QStackedWidget#contenido_logistica,
QScrollArea#scroll_transparente,
QWidget#scroll_transparente {{
    background-color: transparent;
    border: none;
}}

QLabel#titulo_principal {{
    color: {COLOR_TEXTO_PRINCIPAL};
    font-size: 26px;
    font-weight: 900;
    letter-spacing: 2px;
    background: transparent;
    border: none;
}}

QLabel#subtitulo_principal {{
    color: {COLOR_CIAN};
    font-size: 11px;
    font-weight: 900;
    letter-spacing: 2px;
    background: transparent;
    border: none;
}}

QLabel#titulo_cian,
QLabel#titulo_logistico {{
    color: {COLOR_CIAN};
    font-size: 24px;
    font-weight: 900;
    letter-spacing: 1px;
    background: transparent;
    border: none;
}}

QLabel#titulo_cian[tituloProcesando="true"],
QLabel#titulo_logistico[tituloProcesando="true"] {{
    color: {COLOR_AMBAR};
    font-size: 24px;
    font-weight: 900;
    background: transparent;
    border: none;
}}

QLabel#subtitulo_muted,
QLabel#texto_auxiliar,
QLabel#origen_info {{
    color: {COLOR_TEXTO_SECUNDARIO};
    font-size: 14px;
    font-weight: 900;
    background: transparent;
    border: none;
}}

QLabel#icono_hero,
QLabel#icono_modulo,
QLabel#icono_logistico {{
    color: {COLOR_TEXTO_PRINCIPAL};
    font-size: 96px;
    background: transparent;
    border: none;
}}

QLabel#item_codigo {{
    color: {COLOR_CIAN};
    font-size: 10px;
    font-weight: 900;
    background: transparent;
    border: none;
}}

QLabel#item_nombre {{
    color: {COLOR_TEXTO_PRINCIPAL};
    font-size: 13px;
    font-weight: 900;
    background: transparent;
    border: none;
}}

QLabel#etiqueta_secundaria,
QLabel#campo_label,
QLabel#login_section_title {{
    color: {COLOR_TEXTO_PRINCIPAL};
    font-size: 11px;
    font-weight: 900;
    letter-spacing: 1px;
    border: none;
    background: transparent;
}}

QLabel#mensaje_neon,
QLabel#estado_neon,
QLabel#badge_neon {{
    color: {COLOR_CIAN};
    background-color: rgba(0, 255, 198, 0.06);
    border: 1px solid rgba(0, 255, 198, 0.30);
    border-radius: {RADIO_MD};
    padding: 8px 12px;
}}

QLabel#scanner_status {{
    color: {COLOR_TEXTO_SECUNDARIO};
    font-size: 13px;
    font-weight: 900;
    background: transparent;
    border: none;
}}

QLabel#scanner_status[estado="ok"] {{
    color: {COLOR_CIAN};
}}

QLabel#scanner_status[estado="error"] {{
    color: {COLOR_ROJO_ERROR};
}}
"""

QSS_SIDEBAR = f"""
/* =====================================================
   SECTION QSS SIDEBAR
   ===================================================== */

QFrame#sidebar,
QFrame#sidebar_admin,
QFrame#sidebar_logistica,
QFrame#sidebar_modulo {{
    background-color: {COLOR_FONDO_SIDEBAR};
    border-right: 1px solid {COLOR_BORDE_SIDEBAR};
    border-radius: 0px;
}}

QLabel#sidebar_title,
QLabel#lbl_sidebar_titulo,
QLabel#lbl_modulo_sidebar {{
    color: {COLOR_TEXTO_PRINCIPAL};
    font-size: 16px;
    font-weight: 900;
    margin-left: 30px;
    margin-bottom: 35px;
    letter-spacing: 2px;
    border: none;
    background: transparent;
}}

QPushButton#btn_sidebar {{
    text-align: left;
    padding: 6px 8px 6px 28px;
    color: {COLOR_TEXTO_SECUNDARIO};
    background-color: transparent;
    border: none;
    border-radius: 0px;
    font-size: 12px;
    font-weight: 900;
    letter-spacing: 0.5px;
    margin: 0px;
}}

QPushButton#btn_sidebar:hover {{
    background-color: #FFFFFF;
    color: {COLOR_FONDO_SIDEBAR};
}}

QPushButton#btn_sidebar:checked {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
    border: none;
}}

QPushButton#btn_sidebar_exit {{
    text-align: left;
    padding: 6px 8px 6px 28px;
    color: {COLOR_ROJO_ERROR};
    background-color: transparent;
    border: none;
    border-radius: 0px;
    font-size: 12px;
    font-weight: 900;
    letter-spacing: 0.5px;
}}

QPushButton#btn_sidebar_exit:hover {{
    background-color: {COLOR_ROJO_ERROR};
    color: {COLOR_FONDO_APP};
}}
"""

QSS_LOGIN = f"""
/* =====================================================
   SECTION QSS LOGIN
   Do not change visual identity of login.
   ===================================================== */

QWidget#card_neon,
QFrame#card_neon {{
    background-color: {COLOR_GRIS_PANEL};
    border: 1px solid {COLOR_BORDE};
    border-radius: {RADIO_XXL};
}}

QFrame#password_frame {{
    background-color: {COLOR_GRIS_PANEL};
    border: 2px solid {COLOR_CIAN};
    border-radius: 16px;
}}

QFrame#password_frame:hover {{
    background-color: {COLOR_GRIS_SUAVE};
    border: 2px solid {COLOR_CIAN};
}}

QLineEdit#txt_password {{
    background-color: transparent;
    color: {COLOR_TEXTO_PRINCIPAL};
    border: none;
    padding: 0px;
}}

QComboBox#login_combo_perfil {{
    background-color: {COLOR_FONDO_APP_SECUNDARIO};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_CIAN};
    border-radius: 18px;
    padding: 0px 16px;
    min-height: 56px;
    font-size: 13px;
    font-weight: 900;
    selection-background-color: {COLOR_FONDO_APP_SECUNDARIO};
    selection-color: {COLOR_TEXTO_PRINCIPAL};
    outline: none;
}}

QComboBox#login_combo_perfil:hover,
QComboBox#login_combo_perfil:focus,
QComboBox#login_combo_perfil:on {{
    background-color: {COLOR_FONDO_WIDGET};
    border: 2px solid {COLOR_CIAN};
    color: {COLOR_TEXTO_PRINCIPAL};
}}

QComboBox#login_combo_perfil::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 0px;
    border: none;
    background: transparent;
}}

QComboBox#login_combo_perfil::down-arrow {{
    image: none;
    width: 0px;
    height: 0px;
    border: none;
    margin: 0px;
}}

QComboBox#login_combo_perfil QAbstractItemView,
QListView#combo_popup_view {{
    background-color: {COLOR_FONDO_APP};
    alternate-background-color: {COLOR_FONDO_APP};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_CIAN};
    border-radius: 18px;
    padding: 8px 8px;
    margin: 0px;
    outline: 0px;
    selection-background-color: transparent;
    selection-color: {COLOR_TEXTO_PRINCIPAL};
    show-decoration-selected: 0;
}}

QComboBox#login_combo_perfil QAbstractItemView::viewport,
QListView#combo_popup_view::viewport {{
    background-color: {COLOR_FONDO_APP};
    border: none;
    border-radius: 18px;
}}

QComboBox#login_combo_perfil QAbstractItemView::item,
QListView#combo_popup_view::item {{
    min-height: 46px;
    padding: 10px 18px;
    margin: 6px 8px;
    background-color: #091521;
    color: {COLOR_TEXTO_PRINCIPAL};
    border: none;
    border-radius: 18px;
}}

QComboBox#login_combo_perfil QAbstractItemView::item:hover,
QComboBox#login_combo_perfil QAbstractItemView::item:selected,
QListView#combo_popup_view::item:hover,
QListView#combo_popup_view::item:selected {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
    border: none;
    border-radius: 14px;
}}

QListView#combo_popup_view,
QListView#combo_popup_view QWidget,
QListView#combo_popup_view QFrame,
QListView#combo_popup_view QAbstractScrollArea {{
    background-color: {COLOR_FONDO_APP_SECUNDARIO};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: none;
    border-radius: 18px;
}}

#combo_popup_container,
QWidget#combo_popup_container,
QFrame#combo_popup_container,
QDialog#combo_popup_container {{
    background-color: transparent;
    border: 2px solid {COLOR_CIAN};
    border-radius: 18px;
}}
"""
QSS_INPUTS = f"""
/* =====================================================
   SECTION QSS INPUTS
   ===================================================== */

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox,
QDateEdit, QTimeEdit {{
    background-color: {COLOR_GRIS_PANEL};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_LG};
    padding: 10px 12px;
    font-size: 14px;
    selection-background-color: {COLOR_CIAN};
    selection-color: {COLOR_FONDO_APP};
}}

QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover,
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover,
QDateEdit:hover, QTimeEdit:hover {{
    background-color: {COLOR_FONDO_WIDGET};
    color: {COLOR_CIAN};
    border: 2px solid {COLOR_CIAN};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QDateEdit:focus, QTimeEdit:focus {{
    background-color: {COLOR_FONDO_WIDGET};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_CIAN};
}}

QLineEdit#input_buscador[flashHighlight="true"] {{
    background-color: {COLOR_FONDO_WIDGET};
    color: {COLOR_CIAN};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_LG};
    padding: 10px 12px 10px 20px;
}}

QLineEdit[readOnly="true"], QTextEdit[readOnly="true"], QPlainTextEdit[readOnly="true"] {{
    background-color: #131820;
    color: {COLOR_TEXTO_SECUNDARIO};
}}

QLineEdit::placeholder, QTextEdit::placeholder, QPlainTextEdit::placeholder {{
    color: {COLOR_TEXTO_MUTED};
}}

QComboBox {{
    padding-right: 38px;
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 34px;
    border: none;
    background: transparent;
}}

QComboBox::down-arrow {{
    image: none;
    width: 0px;
    height: 0px;
    border-left: 6px solid transparent;
    border-right: 6px solid transparent;
    border-top: 8px solid {COLOR_CIAN};
    margin-right: 14px;
}}

QComboBox QAbstractItemView,
QListView#combo_popup_generic,
QMenu {{
    background-color: {COLOR_FONDO_APP};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_XL};
    padding: 6px 0px;
    outline: 0px;
    selection-background-color: {COLOR_CIAN};
    selection-color: {COLOR_FONDO_APP};
}}

QComboBox QAbstractItemView::item,
QListView#combo_popup_generic::item,
QMenu::item {{
    min-height: 30px;
    padding: 8px 14px;
    margin: 2px 6px;
    background-color: {COLOR_FONDO_APP};
    border: none;
    border-radius: {RADIO_LG};
}}

QComboBox QAbstractItemView::item:hover,
QComboBox QAbstractItemView::item:selected,
QListView#combo_popup_generic::item:hover,
QListView#combo_popup_generic::item:selected,
QMenu::item:selected {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
}}
"""

QSS_BUTTONS = f"""
/* =====================================================
   SECTION QSS BUTTONS
   ===================================================== */

QPushButton {{
    font-size: 13px;
    font-weight: 900;
    border-radius: {RADIO_MD};
    padding: 10px 16px;
    background-color: transparent;
    color: {COLOR_CIAN};
    border: 2px solid {COLOR_CIAN};
}}

QPushButton:hover {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
}}

QPushButton:pressed {{
    background-color: {COLOR_CIAN_PRESION};
    color: {COLOR_FONDO_APP};
}}

QPushButton#btn_primario {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
    border: 2px solid {COLOR_CIAN};
}}

QPushButton#btn_primario:hover {{
    background-color: {COLOR_FONDO_APP};
    color: {COLOR_CIAN};
    border: 2px solid {COLOR_CIAN};
}}

QPushButton#btn_primario:pressed {{
    background-color: {COLOR_CIAN_PRESION};
    color: {COLOR_FONDO_APP};
}}

QPushButton#btn_traspaso_land {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
    border: 2px solid {COLOR_CIAN};
    text-align: center;
    padding: 10px 0px 10px 12px;
}}

QPushButton#btn_traspaso_land:hover {{
    background-color: {COLOR_FONDO_APP};
    color: {COLOR_CIAN};
    border: 2px solid {COLOR_CIAN};
}}

QPushButton#btn_traspaso_land:pressed {{
    background-color: {COLOR_CIAN_PRESION};
    color: {COLOR_FONDO_APP};
}}

QPushButton#btn_secundario {{
    background-color: {COLOR_GRIS_PANEL};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_CIAN};
}}

QPushButton#btn_secundario:hover {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
    border: 2px solid {COLOR_CIAN};
}}

QPushButton#btn_secundario:pressed {{
    background-color: {COLOR_CIAN_PRESION};
    color: {COLOR_FONDO_APP};
}}

QPushButton#btn_peligro {{
    background-color: {COLOR_ROJO_ERROR};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_ROJO_ERROR};
}}

QPushButton#btn_peligro:hover {{
    background-color: {COLOR_FONDO_APP};
    color: {COLOR_ROJO_ERROR};
    border: 2px solid {COLOR_ROJO_ERROR};
}}

QPushButton#btn_peligro:pressed {{
    background-color: {COLOR_ROJO_PRESION};
    color: {COLOR_TEXTO_PRINCIPAL};
}}

QPushButton#btn_icono {{
    background-color: {COLOR_GRIS_PANEL};
    color: {COLOR_CIAN};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_LG};
    padding: 8px;
}}

QPushButton#btn_icono:hover {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
    border: 2px solid {COLOR_CIAN};
}}

QPushButton#btn_icono:pressed {{
    background-color: {COLOR_CIAN_PRESION};
    color: {COLOR_FONDO_APP};
}}

QPushButton#btn_icono_peligro {{
    background-color: transparent;
    color: {COLOR_ROJO_ERROR};
    border: 2px solid {COLOR_ROJO_ERROR};
    border-radius: 20px;
    padding: 6px;
}}

QPushButton#btn_icono_peligro:hover {{
    background-color: {COLOR_ROJO_ERROR};
    color: {COLOR_FONDO_APP};
}}

QPushButton#btn_icono_peligro:pressed {{
    background-color: {COLOR_ROJO_PRESION};
    color: {COLOR_TEXTO_PRINCIPAL};
}}

QPushButton[semanticRole="success"],
QToolButton[semanticRole="success"] {{
    background-color: {COLOR_VERDE_OK};
    color: {COLOR_FONDO_APP};
    border: 2px solid {COLOR_VERDE_OK};
    border-radius: {RADIO_MD};
}}

QPushButton[semanticRole="success"]:hover,
QToolButton[semanticRole="success"]:hover {{
    background-color: {COLOR_FONDO_APP};
    color: {COLOR_VERDE_OK};
    border: 2px solid {COLOR_VERDE_OK};
}}

QPushButton[semanticRole="success"]:pressed,
QToolButton[semanticRole="success"]:pressed {{
    background-color: {COLOR_VERDE_OK_PRESION};
    color: {COLOR_FONDO_APP};
}}

QPushButton[semanticRole="neutral"],
QToolButton[semanticRole="neutral"] {{
    background-color: {COLOR_GRIS_NEUTRO};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_GRIS_NEUTRO};
    border-radius: {RADIO_MD};
}}

QPushButton[semanticRole="neutral"]:hover,
QToolButton[semanticRole="neutral"]:hover {{
    background-color: {COLOR_FONDO_APP};
    color: {COLOR_GRIS_NEUTRO_HOVER};
    border: 2px solid {COLOR_GRIS_NEUTRO_HOVER};
}}

QPushButton[semanticRole="neutral"]:pressed,
QToolButton[semanticRole="neutral"]:pressed {{
    background-color: {COLOR_GRIS_NEUTRO_PRESION};
    color: {COLOR_TEXTO_PRINCIPAL};
}}

QPushButton[semanticRole="danger"],
QToolButton[semanticRole="danger"] {{
    background-color: {COLOR_ROJO_ERROR};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_ROJO_ERROR};
    border-radius: {RADIO_MD};
}}

QPushButton[semanticRole="danger"]:hover,
QToolButton[semanticRole="danger"]:hover {{
    background-color: {COLOR_FONDO_APP};
    color: {COLOR_ROJO_ERROR};
    border: 2px solid {COLOR_ROJO_ERROR};
}}

QPushButton[semanticRole="danger"]:pressed,
QToolButton[semanticRole="danger"]:pressed {{
    background-color: {COLOR_ROJO_PRESION};
    color: {COLOR_TEXTO_PRINCIPAL};
}}

QToolButton {{
    border-radius: {RADIO_MD};
    color: {COLOR_CIAN};
    background-color: transparent;
    border: 2px solid transparent;
}}

QToolButton:hover {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
    border: 2px solid {COLOR_CIAN};
}}

QToolButton:pressed {{
    background-color: {COLOR_CIAN_PRESION};
    color: {COLOR_FONDO_APP};
}}

QPushButton:disabled,
QToolButton:disabled {{
    background-color: #161B22;
    color: #6B7280;
    border: 2px solid #2B3440;
}}

QCheckBox, QRadioButton {{
    spacing: 10px;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px;
    height: 18px;
}}

QCheckBox::indicator:unchecked,
QRadioButton::indicator:unchecked {{
    border: 1px solid {COLOR_BORDE};
    background: {COLOR_GRIS_PANEL};
    border-radius: 9px;
}}

QCheckBox::indicator:checked,
QRadioButton::indicator:checked {{
    border: 1px solid {COLOR_CIAN};
    background: {COLOR_CIAN};
    border-radius: 9px;
}}
"""

QSS_TABS = f"""
/* =====================================================
   SECTION QSS TABS
   ===================================================== */

QTabWidget::pane {{
    border: 1px solid {COLOR_BORDE};
    background: {COLOR_GRIS_PANEL};
    border-radius: {RADIO_LG};
    top: -1px;
}}

QTabBar::tab {{
    background: {COLOR_FONDO_APP};
    color: {COLOR_TEXTO_SECUNDARIO};
    padding: 12px 20px;
    font-weight: 900;
    border-top-left-radius: {RADIO_SM};
    border-top-right-radius: {RADIO_SM};
    margin-right: 2px;
}}

QTabBar::tab:hover {{
    background: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
}}

QTabBar::tab:selected {{
    background: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
    border-bottom: 2px solid {COLOR_CIAN};
}}
"""
QSS_TABLES = f"""
/* =====================================================
   SECTION QSS TABLES
   ===================================================== */

QTableWidget, QTableView, QTreeWidget, QTreeView, QListWidget, QListView {{
    background-color: {COLOR_GRIS_PANEL};
    alternate-background-color: {COLOR_FONDO_APP};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_TABLAS};
    color: {COLOR_TEXTO_PRINCIPAL};
    gridline-color: transparent;
    selection-background-color: {COLOR_GRIS_HOVER};
    selection-color: {COLOR_CIAN};
    font-size: 13px;
    font-weight: 900;
    outline: 0;
}}

QTableWidget::item, QTableView::item, QTreeWidget::item, QTreeView::item,
QListWidget::item, QListView::item {{
    padding: 8px;
    border: none;
}}

QTableWidget::item:hover, QTableView::item:hover, QTreeWidget::item:hover,
QTreeView::item:hover, QListWidget::item:hover, QListView::item:hover {{
    background-color: rgba(0, 255, 198, 0.10);
}}

QTableWidget::item:selected, QTableView::item:selected, QTreeWidget::item:selected,
QTreeView::item:selected, QListWidget::item:selected, QListView::item:selected {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
}}

QHeaderView::section {{
    background-color: {COLOR_GRIS_PANEL};
    color: {COLOR_CIAN};
    padding: 10px 12px;
    border: none;
    border-bottom: 1px solid {COLOR_BORDE};
    font-weight: 900;
}}

QHeaderView::section:hover {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
}}

QHeaderView::section:horizontal:first {{
    border-top-left-radius: {RADIO_LG};
}}

QHeaderView::section:horizontal:last {{
    border-top-right-radius: {RADIO_LG};
}}

QTableCornerButton::section {{
    background-color: {COLOR_GRIS_PANEL};
    border: none;
    border-top-left-radius: {RADIO_LG};
}}

QFrame#item_frame_articulo,
QFrame#item_frame_logistico {{
    background-color: {COLOR_GRIS_PANEL};
    border-radius: 15px;
    padding: 2px;
}}

QFrame#item_frame_articulo {{
    border: 1px solid {COLOR_BORDE};
}}

QFrame#item_frame_logistico {{
    border: 1px solid #3498DB;
}}

QFrame#item_frame_articulo:hover,
QFrame#item_frame_logistico:hover {{
    border: 1px solid {COLOR_CIAN};
}}

QFrame#item_frame_articulo[flashHighlight="true"],
QFrame#item_frame_logistico[flashHighlight="true"] {{
    border: 2px solid {COLOR_CIAN};
}}

/* Plantilla universal de tabla Smart Manager AI */
QFrame#contenedor_tabla_estandar,
QFrame#frame_tabla_neon_logistica {{
    background-color: {COLOR_GRIS_PANEL};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_TABLAS};
}}

QFrame#contenedor_tabla_estandar QTableWidget,
QFrame#contenedor_tabla_estandar QTableView,
QFrame#frame_tabla_neon_logistica QTableWidget,
QFrame#frame_tabla_neon_logistica QTableView {{
    border: none;
    border-radius: {RADIO_TABLAS};
    outline: none;
    background: transparent;
    alternate-background-color: {COLOR_FONDO_APP};
}}

QTableWidget#tabla_estandar_smart,
QTableView#tabla_estandar_smart {{
    border: none;
    border-radius: {RADIO_TABLAS};
    background: transparent;
}}

QFrame#contenedor_tabla_estandar QHeaderView,
QFrame#frame_tabla_neon_logistica QHeaderView {{
    border: none;
    background: transparent;
}}

QFrame#contenedor_tabla_estandar QHeaderView::section,
QFrame#frame_tabla_neon_logistica QHeaderView::section {{
    background-color: {COLOR_GRIS_PANEL};
    color: {COLOR_CIAN};
    padding: 10px 12px;
    border: none;
    border-bottom: 1px solid {COLOR_BORDE};
    font-weight: 900;
}}

QFrame#contenedor_tabla_estandar QHeaderView::section:hover,
QFrame#frame_tabla_neon_logistica QHeaderView::section:hover {{
    background-color: {COLOR_CIAN};
    color: {COLOR_FONDO_APP};
}}

QFrame#contenedor_tabla_estandar QHeaderView::section:horizontal:first,
QFrame#frame_tabla_neon_logistica QHeaderView::section:horizontal:first {{
    border-top-left-radius: {RADIO_TABLAS};
}}

QFrame#contenedor_tabla_estandar QHeaderView::section:horizontal:last,
QFrame#frame_tabla_neon_logistica QHeaderView::section:horizontal:last {{
    border-top-right-radius: {RADIO_TABLAS};
}}

QFrame#contenedor_tabla_estandar QTableCornerButton::section,
QFrame#frame_tabla_neon_logistica QTableCornerButton::section {{
    background: transparent;
    border: none;
}}
"""

QSS_SCROLLBARS = f"""
/* =====================================================
   SECTION QSS SCROLLBARS
   ===================================================== */

QScrollBar:vertical {{
    background: transparent;
    width: 14px;
    margin: 12px 0 12px 0;
}}

QScrollBar::handle:vertical {{
    background: {COLOR_GRIS_SUAVE};
    min-height: 40px;
    border-radius: 7px;
}}

QScrollBar::handle:vertical:hover {{
    background: {COLOR_CIAN};
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 14px;
    margin: 0 12px 0 12px;
}}

QScrollBar::handle:horizontal {{
    background: {COLOR_GRIS_SUAVE};
    min-width: 40px;
    border-radius: 7px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {COLOR_CIAN};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    border: none;
    background: none;
    width: 0px;
    height: 0px;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}
"""

QSS_DIALOGS = f"""
/* =====================================================
   SECTION QSS DIALOGS
   ===================================================== */

QDialog, QInputDialog, QMessageBox {{
    background-color: {COLOR_NEGRO_PANEL};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_XL};
}}

QMessageBox#smart_message_box {{
    background-color: {COLOR_NEGRO_PANEL};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_XL};
}}

QDialog QLabel,
QInputDialog QLabel,
QMessageBox QLabel {{
    color: {COLOR_TEXTO_PRINCIPAL};
    background: transparent;
    font-size: 13px;
    font-weight: 900;
    padding: 4px 2px;
}}

QDialog QPushButton,
QInputDialog QPushButton,
QMessageBox QPushButton {{
    min-width: 120px;
    border-radius: {RADIO_MD};
    font-family: '{FUENTE_APP}';
    font-weight: 900;
}}

QMessageBox QLabel {{
    font-family: '{FUENTE_APP}';
    font-weight: 900;
}}

QInputDialog QLabel,
QInputDialog QLineEdit,
QInputDialog QComboBox {{
    font-family: '{FUENTE_APP}';
    font-weight: 900;
}}
"""

QSS_SCANNER = f"""
/* =====================================================
   SECTION QSS SCANNER
   ===================================================== */

QDialog#dlg_scan,
QDialog#dlg_camara,
QDialog#scanner_dialog {{
    background: transparent;
    border: none;
}}

QFrame#cuerpo_ventana,
QFrame#cuerpo_ventana_scan,
QFrame#cuerpo_ventana_camara,
QFrame#dialogo_scan {{
    background-color: {COLOR_NEGRO_PANEL};
    border: 2px solid {COLOR_CIAN};
    border-radius: {RADIO_SCANNER};
}}

QLabel#lbl_titulo_scan,
QLabel#titulo_scan,
QLabel#titulo_contexto_scan {{
    color: {COLOR_CIAN};
    font-size: 15px;
    font-weight: 900;
    letter-spacing: 4px;
    border: none;
    background: transparent;
}}

QLabel#feed_video,
QLabel#lbl_video {{
    background-color: #000000;
    border: 1px solid {COLOR_BORDE_SIDEBAR};
    border-radius: {RADIO_SM};
}}

QLabel#feed_video[activo="true"],
QLabel#lbl_video[activo="true"] {{
    border: 2px solid {COLOR_CIAN};
}}

QLabel#info_scan,
QLabel#lbl_info_scan {{
    color: {COLOR_TEXTO_MUTED};
    font-size: 10px;
    font-weight: 800;
    border: none;
    background: transparent;
}}

QPushButton#btn_abortar_scan,
QPushButton#btn_cerrar_scan,
QPushButton#btn_cerrar {{
    background-color: {COLOR_ROJO_ERROR};
    color: {COLOR_TEXTO_PRINCIPAL};
    border: 2px solid {COLOR_ROJO_ERROR};
    border-radius: 15px;
    font-weight: 900;
}}

QPushButton#btn_abortar_scan:hover,
QPushButton#btn_cerrar_scan:hover,
QPushButton#btn_cerrar:hover {{
    background-color: {COLOR_FONDO_APP};
    color: {COLOR_ROJO_ERROR};
    border: 2px solid {COLOR_ROJO_ERROR};
}}
"""

ESTILO_GLOBAL = (
    QSS_ROOT
    + QSS_SIDEBAR
    + QSS_LOGIN
    + QSS_INPUTS
    + QSS_BUTTONS
    + QSS_TABS
    + QSS_TABLES
    + QSS_SCROLLBARS
    + QSS_DIALOGS
    + QSS_SCANNER
)


__all__ = [
    "FUENTE_APP",
    "COLOR_CIAN",
    "COLOR_CIAN_HOVER",
    "COLOR_CIAN_PRESION",
    "COLOR_VERDE_OK",
    "COLOR_VERDE_OK_HOVER",
    "COLOR_VERDE_OK_PRESION",
    "COLOR_FONDO_APP",
    "COLOR_FONDO_APP_SECUNDARIO",
    "COLOR_FONDO_SIDEBAR",
    "COLOR_FONDO_WIDGET",
    "COLOR_GRIS_PANEL",
    "COLOR_GRIS_HOVER",
    "COLOR_GRIS_SUAVE",
    "COLOR_BORDE",
    "COLOR_BORDE_SIDEBAR",
    "COLOR_TEXTO_PRINCIPAL",
    "COLOR_TEXTO_SECUNDARIO",
    "COLOR_TEXTO_MUTED",
    "COLOR_ROJO_ERROR",
    "COLOR_ROJO_HOVER",
    "COLOR_ROJO_PRESION",
    "COLOR_AMBAR",
    "RADIO_TABLAS",
    "ESTILO_GLOBAL",
    "aplicar_estilo_app",
    "aplicar_estilo_widget",
    "mostrar_confirmacion",
    "mostrar_mensaje",
    "repolish_widget",
    "feedback_lineedit_exito",
    "feedback_frame_item_resaltado",
    "construir_plantilla_camara",
    "construir_tabla_estilizada",
]
