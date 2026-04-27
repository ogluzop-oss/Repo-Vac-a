from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QComboBox,
    QListView,
    QPushButton,
    QGraphicsDropShadowEffect,
    QFrame,
    QAbstractItemView,
    QHBoxLayout,
    QToolButton,
)
from PyQt6.QtGui import QFont, QColor, QPalette, QPainter, QPen, QIcon, QPixmap
from PyQt6.QtCore import Qt, QPropertyAnimation, QSize

try:
    from assets.estilo_global import aplicar_estilo_widget
except Exception:
    aplicar_estilo_widget = None

import requests
from src.utils.api_client import api_client


# ============================================================
# BLOQUE COMPONENTES DE INTERFAZ PERSONALIZADOS
# ============================================================

class DarkComboListView(QListView):
    """Popup del selector de perfiles, oscuro y sin artefactos del sistema."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("combo_popup_view")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSpacing(6)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setContentsMargins(0, 0, 0, 0)

        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor("#0B1118"))
        pal.setColor(QPalette.ColorRole.Window, QColor("#0B1118"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#FFFFFF"))
        self.setPalette(pal)

        self.viewport().setAutoFillBackground(True)
        self.viewport().setPalette(pal)

        self.setStyleSheet(
            """
            QListView#combo_popup_view {
                background-color: #0E1117;
                border: 2px solid #00FFC6;
                border-radius: 18px;
                padding: 6px 6px;
                outline: none;
            }
            QListView#combo_popup_view::item {
                min-height: 46px;
                padding: 12px 18px;
                margin: 6px 6px;
                background-color: #091521;
                color: #FFFFFF;
                border: none;
                border-radius: 18px;
            }
            QListView#combo_popup_view::item:hover,
            QListView#combo_popup_view::item:selected {
                background-color: #00FFC6;
                color: #0E1117;
                border: none;
                border-radius: 18px;
            }
            QListView#combo_popup_view::viewport {
                background-color: #0E1117;
                border: none;
                border-radius: 18px;
            }
            """
        )

    def showEvent(self, event):
        super().showEvent(event)
        try:
            popup = self.window()
            if popup is not None:
                popup.setObjectName("combo_popup_container")
                popup.setWindowFlags(
                    popup.windowFlags() | Qt.WindowType.FramelessWindowHint
                )
                popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                popup.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                popup.setAutoFillBackground(False)
                pal = popup.palette()
                pal.setColor(QPalette.ColorRole.Window, QColor("#0B1117"))
                popup.setPalette(pal)
                popup.setStyleSheet(
                    """
                    background-color: #0E1117;
                    border: 2px solid #00FFC6;
                    border-radius: 18px;
                    """
                )

            self.viewport().setStyleSheet(
                """
                background-color: transparent;
                border: none;
                """
            )
        except Exception:
            pass


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
        self.setWindowTitle("Smart Manager AI - Acceso al Sistema")
        self.setMinimumSize(450, 600)
        self.setObjectName("panel_raiz")

        self._password_visible = False
        self._popup_shown = False
        self.setup_ui()

        self.btn_login.clicked.connect(self.handle_login)
        self.txt_password.returnPressed.connect(self.handle_login)

        self._reforzar_estilo_global()

    def setup_ui(self):
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#0E1117"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 12, 40, 40)
        main_layout.setSpacing(0)

        main_layout.addSpacing(56)

        header_box = QVBoxLayout()
        header_box.setSpacing(18)

        title = QLabel("SMART MANAGER AI")
        title.setObjectName("titulo_principal")
        title.setFont(QFont("Segoe UI", 42, QFont.Weight.Black))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("SISTEMA DE GESTIÓN LOGÍSTICA")
        subtitle.setObjectName("subtitulo_principal")
        subtitle.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header_box.addWidget(title)
        header_box.addWidget(subtitle)

        main_layout.addLayout(header_box)
        main_layout.addSpacing(20)
        main_layout.addStretch(1)

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

        lbl_perfil = QLabel("PERFIL DE ACCESO")
        lbl_perfil.setObjectName("login_section_title")
        lbl_perfil.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        self.combo_perfil = QComboBox()
        self.combo_perfil.setObjectName("login_combo_perfil")
        self.combo_perfil.addItems(["OPERARIO", "GERENTE", "ADMINISTRADOR"])
        self.combo_perfil.setMaxVisibleItems(3)
        self.combo_perfil.setFixedHeight(56)
        self.combo_perfil.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo_perfil.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.combo_perfil.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo_perfil.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )

        self.combo_view = DarkComboListView(self.combo_perfil)
        self.combo_view.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.combo_view.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo_perfil.setView(self.combo_view)

        lbl_password = QLabel("CONTRASEÑA")
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

        self.btn_login = QPushButton("ACCEDER AL SISTEMA")
        self.btn_login.setObjectName("btn_primario")
        self.btn_login.setFixedHeight(55)
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.setFont(QFont("Segoe UI", 11, QFont.Weight.Black))

        inner_layout.addWidget(lbl_perfil)
        inner_layout.addWidget(self.combo_perfil)
        inner_layout.addWidget(lbl_password)
        inner_layout.addWidget(self.password_frame)
        inner_layout.addSpacing(18)
        inner_layout.addWidget(self.btn_login)

        main_layout.addWidget(self.login_box, 0, Qt.AlignmentFlag.AlignCenter)
        main_layout.addStretch(1)

        self.animate_glow(self.shadow)

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_popup_shown", False):
            self._popup_shown = True
            try:
                self.combo_perfil.showPopup()
            except Exception:
                pass

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
            self.combo_perfil,
            self.combo_view,
            self.txt_password,
            self.btn_login,
            self.btn_toggle_password,
            self.password_frame,
        ]
        for widget in widgets:
            try:
                aplicar_estilo_widget(widget)
            except Exception:
                pass

    # ============================================================
    # BLOQUE AUTENTICACIÓN
    # ============================================================

    def handle_login(self):
        usuario = self.combo_perfil.currentText()
        password = self.txt_password.text()

        if not usuario or not password:
            print("Usuario y contraseña requeridos")
            return

        data = api_client.login(usuario, password)
        if data:
            perfil = data["perfil"]
            print(f"Login exitoso como {perfil}")
            self.close()
        else:
            print("Credenciales inválidas o error de conexión")
            self._login_fallback(usuario, password)

    def _login_fallback(self, usuario, password):
        """Login directo como fallback cuando el backend no está disponible."""
        try:
            from src.db.conexion import obtener_conexion
            from src.db.usuario import encriptar_password

            password_hash = encriptar_password(password)

            with obtener_conexion() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT perfil FROM usuarios WHERE nombre = %s AND password = %s AND activo = 1",
                        (usuario, password_hash),
                    )
                    result = cur.fetchone()
                    if result:
                        perfil = result[0]
                        print(f"Login exitoso (fallback) como {perfil}")
                        self.close()
                    else:
                        print("Credenciales inválidas")
        except Exception as e:
            print(f"Error en fallback: {e}")
