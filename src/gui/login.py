import os

from PyQt6.QtCore import QPropertyAnimation, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPen, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

_LOGO_CORP_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "documentos", "logo_corporativo.png"
))

try:
    from assets.estilo_global import aplicar_estilo_widget
except Exception:
    aplicar_estilo_widget = None

from src.utils import i18n
from src.utils.i18n import tr


class NeonEyeButton(QToolButton):
    """Icono de ojo con brillo sutil y fondo discreto al pasar el ratón."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_password_visible = False
        self._is_hovered = False
        self._icon_open_cyan = QIcon()
        self._icon_closed_cyan = QIcon()
        self._icon_open_bright = QIcon()
        self._icon_closed_bright = QIcon()
        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setBlurRadius(14)
        self._glow.setColor(QColor(0, 255, 198, 70))
        self._glow.setOffset(0, 0)
        self.setGraphicsEffect(self._glow)
        self.setStyleSheet(
            """
            QToolButton {
                background: transparent;
                border: none;
                border-radius: 15px;
                padding: 0px;
            }
            QToolButton:hover {
                background-color: #101317;
                border: none;
                border-radius: 15px;
            }
            """
        )

    def set_icons(self, open_cyan, closed_cyan, open_bright, closed_bright):
        self._icon_open_cyan = open_cyan
        self._icon_closed_cyan = closed_cyan
        self._icon_open_bright = open_bright
        self._icon_closed_bright = closed_bright
        self.refresh_icon()

    def set_password_visible_state(self, visible):
        self._is_password_visible = visible
        self.refresh_icon()

    def enterEvent(self, event):
        self._is_hovered = True
        self.refresh_icon()
        self._glow.setBlurRadius(24)
        self._glow.setColor(QColor(0, 255, 198, 135))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.refresh_icon()
        self._glow.setBlurRadius(14)
        self._glow.setColor(QColor(0, 255, 198, 70))
        super().leaveEvent(event)

    def refresh_icon(self):
        if self._is_password_visible:
            self.setIcon(
                self._icon_open_bright if self._is_hovered else self._icon_open_cyan
            )
        else:
            self.setIcon(
                self._icon_closed_bright if self._is_hovered else self._icon_closed_cyan
            )


# ============================================================
# BLOQUE VENTANA DE LOGIN
# ============================================================

class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Smart Manager - {tr('login.window_title')}")
        self.setMinimumSize(450, 600)
        self.setObjectName("panel_raiz")

        self._password_visible = False
        self._popup_shown = False
        self.setup_ui()

        self.btn_login.clicked.connect(self.handle_login)
        self.txt_nombre.returnPressed.connect(lambda: self.txt_password.setFocus())
        self.txt_password.returnPressed.connect(self.handle_login)

        self._reforzar_estilo_global()

        # Re-traducción en caliente: al cambiar el idioma desde el selector (o
        # desde cualquier parte de la app) esta ventana se actualiza sola.
        try:
            i18n.gestor().idioma_cambiado.connect(self._retraducir)
        except Exception:
            pass
        self._aplicar_direccion_rtl()

    def setup_ui(self):
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#0E1117"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(0)

        # ── Barra superior: selector de idioma (esquina superior derecha) ──
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.addStretch(1)
        top_bar.addWidget(self._build_language_selector())
        main_layout.addLayout(top_bar)

        main_layout.addStretch(1)

        # Logo corporativo centrado (~1/9 del área de la ventana)
        self.lbl_logo_login = QLabel()
        self.lbl_logo_login.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_logo_login.setStyleSheet("background:transparent;border:none;")
        main_layout.addWidget(self.lbl_logo_login, 0, Qt.AlignmentFlag.AlignCenter)

        main_layout.addSpacing(32)

        self.login_box = QWidget()
        self.login_box.setObjectName("card_neon")
        self.login_box.setFixedWidth(400)

        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(35)
        self.shadow.setColor(QColor(0, 255, 198, 150))
        self.shadow.setOffset(0, 0)
        self.login_box.setGraphicsEffect(self.shadow)

        inner_layout = QVBoxLayout(self.login_box)
        inner_layout.setSpacing(18)
        inner_layout.setContentsMargins(40, 42, 40, 42)

        self.lbl_perfil = lbl_perfil = QLabel(tr("login.user_label"))
        lbl_perfil.setObjectName("login_section_title")
        lbl_perfil.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        self.nombre_frame = QFrame()
        self.nombre_frame.setObjectName("password_frame")
        self.nombre_frame.setFixedHeight(50)

        nombre_row = QHBoxLayout(self.nombre_frame)
        nombre_row.setContentsMargins(14, 0, 8, 0)
        nombre_row.setSpacing(4)

        self.txt_nombre = QLineEdit()
        self.txt_nombre.setObjectName("txt_password")
        self.txt_nombre.setPlaceholderText(tr("login.user_placeholder"))
        self.txt_nombre.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.txt_nombre.setFrame(False)
        nombre_row.addWidget(self.txt_nombre)

        self.lbl_password = lbl_password = QLabel(tr("login.password_label"))
        lbl_password.setObjectName("login_section_title")
        lbl_password.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        self.password_frame = QFrame()
        self.password_frame.setObjectName("password_frame")
        self.password_frame.setFixedHeight(50)

        password_row = QHBoxLayout(self.password_frame)
        password_row.setContentsMargins(14, 0, 8, 0)
        password_row.setSpacing(4)

        self.txt_password = QLineEdit()
        self.txt_password.setObjectName("txt_password")
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.setPlaceholderText("••••••••")
        self.txt_password.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.txt_password.setFrame(False)
        password_row.addWidget(self.txt_password)

        self.btn_toggle_password = NeonEyeButton()
        self.btn_toggle_password.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_password.setFixedSize(30, 30)
        self.btn_toggle_password.setIconSize(QSize(22, 22))

        self._icon_eye_open = self._create_eye_icon(False, "#00FFC6")
        self._icon_eye_closed = self._create_eye_icon(True, "#00FFC6")
        self._icon_eye_open_bright = self._create_eye_icon(False, "#7AFFF0")
        self._icon_eye_closed_bright = self._create_eye_icon(True, "#7AFFF0")
        self.btn_toggle_password.set_icons(
            self._icon_eye_open,
            self._icon_eye_closed,
            self._icon_eye_open_bright,
            self._icon_eye_closed_bright,
        )
        self.btn_toggle_password.set_password_visible_state(False)
        self.btn_toggle_password.clicked.connect(self.toggle_password_visibility)
        password_row.addWidget(
            self.btn_toggle_password,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        self.btn_login = QPushButton(tr("login.access_button"))
        self.btn_login.setObjectName("btn_primario")
        self.btn_login.setFixedHeight(55)
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.setFont(QFont("Segoe UI", 11, QFont.Weight.Black))

        inner_layout.addWidget(lbl_perfil)
        inner_layout.addWidget(self.nombre_frame)
        inner_layout.addWidget(lbl_password)
        inner_layout.addWidget(self.password_frame)
        inner_layout.addSpacing(18)
        inner_layout.addWidget(self.btn_login)

        main_layout.addWidget(self.login_box, 0, Qt.AlignmentFlag.AlignCenter)
        main_layout.addStretch(1)

        self.animate_glow(self.shadow)

    def _login_refresh_logo(self):
        w = max(self.width(), 450)
        h = max(self.height(), 600)
        # card ~390px + spacing 32px + márgenes top+bottom 80px
        available_h = h - 80 - 390 - 32
        side = max(100, min(available_h, w // 3, 280))
        self.lbl_logo_login.setFixedSize(side, side)
        if os.path.exists(_LOGO_CORP_PATH):
            pix = QPixmap(_LOGO_CORP_PATH)
            if not pix.isNull():
                self.lbl_logo_login.setPixmap(
                    pix.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                )
                return
        self.lbl_logo_login.setPixmap(QPixmap())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._login_refresh_logo()

    def showEvent(self, event):
        super().showEvent(event)
        self._login_refresh_logo()
        self.txt_nombre.setFocus()


# ============================================================
# BLOQUE GENERACIÓN DE ICONOS
# ============================================================

    def _create_eye_icon(self, crossed=False, color="#00FFC6"):
        pix = QPixmap(28, 28)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawArc(5, 8, 18, 12, 0, 180 * 16)
        painter.drawArc(5, 8, 18, 12, 180 * 16, 180 * 16)
        painter.drawEllipse(11, 11, 6, 6)
        if crossed:
            painter.drawLine(6, 22, 22, 6)
        painter.end()
        return QIcon(pix)


# ============================================================
# BLOQUE ANIMACIONES Y EFECTOS VISUALES
# ============================================================

    def animate_glow(self, shadow):
        self.anim = QPropertyAnimation(shadow, b"blurRadius")
        self.anim.setDuration(2500)
        self.anim.setStartValue(25)
        self.anim.setEndValue(50)
        self.anim.setLoopCount(-1)
        self.anim.start()

    def toggle_password_visibility(self):
        self._password_visible = not self._password_visible
        if self._password_visible:
            self.txt_password.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.btn_toggle_password.set_password_visible_state(self._password_visible)

    def _reforzar_estilo_global(self):
        if aplicar_estilo_widget is None:
            return

        widgets = [
            self,
            self.login_box,
            self.txt_nombre,
            self.txt_password,
            self.btn_login,
            self.btn_toggle_password,
            self.nombre_frame,
            self.password_frame,
        ]
        for widget in widgets:
            try:
                aplicar_estilo_widget(widget)
            except Exception:
                pass


# ============================================================
# BLOQUE INTERNACIONALIZACIÓN (i18n)
# ============================================================

    def _build_language_selector(self):
        """Selector de idioma (esquina superior derecha): contorno neón, esquinas
        redondeadas, dark mode, Segoe UI Bold. Muestra el nombre nativo + bandera."""
        combo = QComboBox()
        combo.setObjectName("login_lang_combo")
        combo.setCursor(Qt.CursorShape.PointingHandCursor)
        combo.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        combo.setFixedHeight(38)
        combo.setMinimumWidth(180)
        combo.setToolTip(tr("login.language_tooltip"))

        actual = i18n.current_language()
        idx_actual = 0
        for i, (code, info) in enumerate(i18n.LANGUAGES.items()):
            etiqueta = f"{info.get('flag', '')}  {info.get('native', code)}".strip()
            combo.addItem(etiqueta, code)
            if code == actual:
                idx_actual = i
        combo.setCurrentIndex(idx_actual)

        combo.setStyleSheet(
            "QComboBox#login_lang_combo{"
            "background:#0D1117;color:#E6EDF3;border:2px solid #00FFC6;"
            "border-radius:12px;padding:4px 14px;font-family:'Segoe UI';font-weight:700;}"
            "QComboBox#login_lang_combo:hover{background:#11181D;}"
            "QComboBox#login_lang_combo::drop-down{border:none;width:22px;}"
        )
        combo.currentIndexChanged.connect(self._on_language_changed)
        self.combo_idioma = combo
        return combo

    def _on_language_changed(self, _idx):
        code = self.combo_idioma.currentData()
        if code:
            # set_language persiste la preferencia y emite idioma_cambiado, lo que
            # dispara _retraducir aquí y en cualquier otra ventana conectada.
            i18n.set_language(code)

    def _retraducir(self, *_):
        """Re-traduce todos los textos de la ventana al idioma activo (en caliente)."""
        try:
            self.setWindowTitle(f"Smart Manager - {tr('login.window_title')}")
            self.lbl_perfil.setText(tr("login.user_label"))
            self.lbl_password.setText(tr("login.password_label"))
            self.txt_nombre.setPlaceholderText(tr("login.user_placeholder"))
            self.btn_login.setText(tr("login.access_button"))
            if hasattr(self, "combo_idioma"):
                self.combo_idioma.setToolTip(tr("login.language_tooltip"))
        except Exception:
            pass
        self._aplicar_direccion_rtl()

    def _aplicar_direccion_rtl(self):
        """Aplica dirección RTL (árabe...) o LTR según el idioma activo."""
        try:
            direccion = (
                Qt.LayoutDirection.RightToLeft if i18n.is_rtl()
                else Qt.LayoutDirection.LeftToRight
            )
            self.setLayoutDirection(direccion)
        except Exception:
            pass


# ============================================================
# BLOQUE AUTENTICACIÓN
# ============================================================

    def handle_login(self):
        nombre = self.txt_nombre.text().strip()
        password = self.txt_password.text()

        if not nombre or not password:
            return
