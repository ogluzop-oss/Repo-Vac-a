import logging
import os

from PyQt6.QtCore import QByteArray, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPalette, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.db.conexion import obtener_referencias

# Importaciones de negocio y datos
from src.db.usuario import sesion_global
from src.utils import i18n
from src.utils.i18n import tr


def _resolver_logo():
    """Logo CORPORATIVO del cliente (subido en Configuración → Logo corporativo,
    guardado en documentos/logo_corporativo.png). Si no hay ninguno, cae al logo
    de la app como marca por defecto."""
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    corp = os.path.join(base, "documentos", "logo_corporativo.png")
    if os.path.exists(corp):
        return corp
    try:
        from src.utils import recursos

        app_logo = recursos.ruta_recurso("assets", "Logo Smart Manager.png")
        if os.path.exists(app_logo):
            return app_logo
    except Exception:
        pass
    return os.path.join(base, "assets", "Logo Smart Manager.png")


_LOGO_PATH = _resolver_logo()

try:
    from assets.estilo_global import (
        aplicar_estilo_widget,
        mostrar_confirmacion,
        mostrar_mensaje,
    )
except Exception:
    aplicar_estilo_widget = None
    mostrar_confirmacion = None
    mostrar_mensaje = None

logger = logging.getLogger(__name__)


# ============================================================
# BLOQUE SOMA — INDICADOR VISUAL
# ============================================================
class _SomaIndicator(QWidget):
    """
    Pill-shaped SOMA status indicator in the top bar.
    States: inactivo (grey) | escuchando (cyan dim pulse) | activado (cyan bright) | procesando (orange)
    """

    _COLORS = {
        "inactivo": ("#1e2530", "#4a5568", "SOMA"),
        "escuchando": ("#0d2a2a", "#00FFC6", "SOMA ●"),
        "activado": ("#00FFC6", "#001a15", "SOMA ◉"),
        "procesando": ("#2a1a00", "#ffaa00", "SOMA ···"),
        "error": ("#2a0000", "#ff4444", "SOMA ✕"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._estado = "inactivo"
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(800)
        self._pulse_timer.timeout.connect(self._toggle_pulse)
        self._pulse_on = False

        self._lbl = QLabel("SOMA", self)
        self._lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.addWidget(self._lbl)

        self.setFixedHeight(28)
        self.setMinimumWidth(72)
        self._apply_style()

    def soma_set_estado(self, estado: str):
        try:
            self._estado = estado
            self._pulse_timer.stop()
            self._pulse_on = False
            self._apply_style()
            if estado == "escuchando":
                self._pulse_timer.start()
            elif estado in ("activado", "procesando"):
                QTimer.singleShot(3000, lambda: self.soma_set_estado("escuchando"))
        except RuntimeError:
            pass  # C++ object already deleted during logout race

    def _toggle_pulse(self):
        self._pulse_on = not self._pulse_on
        self._apply_style()

    def _apply_style(self):
        bg, fg, txt = self._COLORS.get(self._estado, self._COLORS["inactivo"])
        if self._estado == "escuchando" and self._pulse_on:
            bg = "#0a2020"
        self._lbl.setText(txt)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
                border: 1.5px solid {fg};
                border-radius: 12px;
            }}
            QLabel {{
                color: {fg};
                background: transparent;
                border: none;
                font-size: 8px;
                font-weight: bold;
                letter-spacing: 1px;
            }}
        """)


# ============================================================
# BLOQUE COMPONENTES DE INTERFAZ (TARJETAS)
# ============================================================
class MenuCardButton(QToolButton):
    _HOVER_ZOOM = 1.15   # factor de acercamiento del icono al pasar el ratón (sin oscurecerlo)

    def __init__(self, texto, icono_normal, icono_hover, color="#00FFC6", parent=None):
        super().__init__(parent)
        self.color = color
        self._icono_normal = icono_normal
        self._icono_hover = icono_hover
        self._icon_base = None   # tamaño base del icono (se fija en el primer hover para el zoom)

        self.setText(texto)
        self.setIcon(self._icono_normal)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        # Botón (tarjeta) a su TAMAÑO ORIGINAL (110×88); el ICONO llena la caja (recortado) para
        # verse grande, con el nombre debajo en Segoe UI Bold 12.
        self.setIconSize(QSize(104, 64))
        self.setFixedSize(110, 88)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.setContentsMargins(0, 0, 0, 0)
        self.setStyleSheet(self._build_style(color))

        # Badge de actividad (circulo rojo con nº, estilo WhatsApp). Nace del Event Bus
        # (Fase 3): el numero lo calcula src.services.actividad, nunca se almacena aqui.
        self._badge = QLabel("", self)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setStyleSheet(
            "background-color:#FF3B30;color:#FFFFFF;border:2px solid #0B1118;"
            "border-radius:11px;font-family:'Segoe UI';font-weight:900;font-size:11px;")
        self._badge.hide()

    def set_badge(self, n):
        """Muestra/oculta el circulo rojo con el nº de eventos pendientes (n<=0 → oculto)."""
        try:
            n = int(n or 0)
        except (TypeError, ValueError):
            n = 0
        if n <= 0:
            self._badge.hide()
            return
        txt = "99+" if n > 99 else str(n)
        self._badge.setText(txt)
        w = 22 if len(txt) <= 2 else 30
        self._badge.setFixedSize(w, 22)
        self._badge.move(self.width() - w - 4, 4)
        self._badge.show()
        self._badge.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._badge.isVisible():
            self._badge.move(self.width() - self._badge.width() - 4, 4)

    def _build_style(self, color):
        # Sin contorno y con el MISMO fondo que el menú (#0B1118): las tarjetas se
        # integran con el fondo en reposo y mantienen el HOVER SWAP (fondo del color
        # + icono/texto oscuros al pasar el ratón).
        return f"""
            QToolButton {{
                background-color: #0B1118;
                color: #F3F6F9;
                border: none;
                border-radius: 14px;
                padding: 0px 1px 0px 1px;
                margin: 0;
                text-align: center;
                font-family: 'Segoe UI';
                font-size: 10pt;
                font-weight: bold;
            }}
            QToolButton:hover {{
                background-color: {color};
                color: #0B1118;
                border: none;
            }}
            QToolButton:pressed {{
                background-color: {color};
                color: #0B1118;
                border: none;
                padding-top: 2px;
            }}
        """

    def _aplicar_glow(self, color):
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(18)
        glow.setColor(QColor(color))
        glow.setOffset(0, 0)
        self.setGraphicsEffect(glow)

    def enterEvent(self, event):
        # En hover: FONDO turquesa (QSS) + HOVER-SWAP del icono (a su versión oscura, para que resalte
        # sobre el turquesa con los iconos de línea) + ZOOM (efecto de acercamiento).
        if self._icon_base is None:
            self._icon_base = self.iconSize()
        if self._icono_hover is not None:
            self.setIcon(self._icono_hover)
        b = self._icon_base
        self.setIconSize(QSize(int(b.width() * self._HOVER_ZOOM), int(b.height() * self._HOVER_ZOOM)))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(self._icono_normal)
        if self._icon_base is not None:
            self.setIconSize(self._icon_base)
        super().leaveEvent(event)


# ============================================================
# BLOQUE VENTANA PRINCIPAL DEL MENÚ
# ============================================================
class MenuPrincipal(QWidget):
    def __init__(self):
        super().__init__()

        usuario_actual = getattr(sesion_global, "usuario_actual", None) or {}
        raw_perfil = usuario_actual.get("perfil", "OPERARIO")
        self.perfil = str(raw_perfil).strip().upper()
        self.nombre_usuario = sesion_global.obtener_nombre() or "USUARIO"

        self.setWindowTitle(f"Smart Manager - [{self.perfil}]")
        self.setObjectName("panel_raiz")
        self._ventanas = {}
        self._cerrando = False
        # Registros para la re-traducción en caliente (i18n)
        self._cards = {}  # v_id -> MenuCardButton
        self._lock_lbls = []  # etiquetas de tarjetas bloqueadas

        # Mantener el comportamiento actual del ciclo de vida sin alterar diseño.
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self.setup_ui()

        # Timer de monitorización de DB
        self.timer_db = QTimer(self)
        self.timer_db.timeout.connect(self.actualizar_estado_db)
        self.timer_db.start(10000)
        self.actualizar_estado_db()

        # Verificación diferida para no alterar el arranque visual
        QTimer.singleShot(2000, self.verificar_stock_bajo)

        # Recordatorio de citas/eventos programados PARA HOY (notificación flotante).
        QTimer.singleShot(2600, self._comprobar_citas_hoy)

        # Pre-carga diferida del módulo de Configuración (su import tarda ~450 ms
        # la primera vez). Al calentarlo durante el reposo del menú, la primera
        # apertura de Configuración es prácticamente instantánea.
        QTimer.singleShot(1200, self._precargar_modulos_pesados)

        # i18n: re-traducción en caliente al cambiar el idioma + dirección RTL.
        i18n.conectar_retraduccion(self, self._retraducir)

        # Badges de actividad (Fase 3): circulos rojos en las tarjetas, calculados desde el
        # Event Bus. Primer calculo diferido + refresco periodico + al volver al menu.
        self._timer_badges = QTimer(self)
        self._timer_badges.timeout.connect(self._refrescar_badges)
        self._timer_badges.start(60000)
        QTimer.singleShot(900, self._refrescar_badges)

    def _refrescar_badges(self):
        """Pinta el circulo rojo con el nº de eventos pendientes de cada tarjeta (best-effort)."""
        try:
            from src.services import actividad
            usuario = getattr(sesion_global, "usuario_actual", None) or {}
            counts = actividad.contar(usuario=usuario, perfil=self.perfil)
        except Exception:
            counts = {}
        for v_id, btn in self._cards.items():
            try:
                btn.set_badge(counts.get(v_id, 0))
            except Exception:
                pass

    def showEvent(self, event):
        super().showEvent(event)
        # Aplicar EN CALIENTE un cambio de MODO PYME SIMPLE hecho en Configuración: si el flag cambió
        # desde la última construcción, reconstruye el menú al volver a mostrarlo.
        try:
            from src.services import onboarding
            actual = onboarding.modo_simple()
            if getattr(self, "_modo_simple_aplicado", None) is None:
                self._modo_simple_aplicado = actual
            elif actual != self._modo_simple_aplicado:
                self._modo_simple_aplicado = actual
                self.refrescar_menu()
                return
        except Exception:
            pass
        QTimer.singleShot(0, self._refrescar_badges)

    def _visible_en_menu(self, v_id) -> bool:
        """Filtro ADICIONAL (sobre perfil/edición): en MODO PYME SIMPLE solo se ven los módulos
        esenciales; fuera de modo simple, todo visible. Best-effort: ante error, visible."""
        try:
            from src.services import onboarding
            return (not onboarding.modo_simple()) or onboarding.esencial(v_id)
        except Exception:
            return True

    def refrescar_menu(self):
        """Reconstruye el menú (tarjetas) para aplicar en caliente un cambio de MODO PYME SIMPLE,
        sin reiniciar la app. Traspasa el layout actual a un widget desechable (se libera con sus
        hijos) y vuelve a construir la interfaz."""
        try:
            antiguo = self.layout()
            if antiguo is not None:
                QWidget().setLayout(antiguo)   # transfiere la propiedad → se destruye con sus hijos
            self._cards = {}
            self._lock_lbls = []
            self.setup_ui()
            try:
                from src.services import onboarding
                self._modo_simple_aplicado = onboarding.modo_simple()
            except Exception:
                pass
            self._refrescar_badges()
        except Exception as e:
            logging.getLogger("menu").error("refrescar_menu: %s", e)

    # ============================================================
    # BLOQUE CONSTRUCCIÓN DE INTERFAZ
    # ============================================================
    def setup_ui(self):
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#0B1118"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 4, 30, 10)
        main_layout.setSpacing(4)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)
        top_bar.setContentsMargins(0, 0, 0, 0)

        # ── LEFT side (stretch=1) — logo + ref, both hidden by default ──────
        left_panel = QWidget()
        left_panel.setStyleSheet("background: transparent; border: none;")
        left_hbox = QHBoxLayout(left_panel)
        left_hbox.setContentsMargins(0, 0, 0, 0)
        left_hbox.setSpacing(10)

        self.logo_label = QLabel()
        self.logo_label.setFixedHeight(76)
        self.logo_label.setStyleSheet("background: transparent; border: none;")
        self.logo_label.hide()
        left_hbox.addWidget(self.logo_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self.ref_label = QLabel("")
        self.ref_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Black))
        self.ref_label.setStyleSheet("""
            color: #00FF7A;
            background: transparent;
            border: none;
            letter-spacing: 1px;
            """)
        self.ref_label.hide()
        left_hbox.addWidget(self.ref_label, 0, Qt.AlignmentFlag.AlignVCenter)

        # ── Selector de tienda (multitienda, F1) — solo SUPERADMIN / ADMINISTRADOR.
        self.btn_tienda = None
        if self.perfil in ("SUPERADMIN", "ADMINISTRADOR"):
            self.btn_tienda = QPushButton("")
            self.btn_tienda.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_tienda.setStyleSheet(
                "QPushButton{background:#0E1117;color:#E6EDF3;border:2px solid #00FFC6;"
                "border-radius:10px;text-align:left;padding:5px 14px;font-family:'Segoe UI';"
                "font-weight:900;font-size:11px;letter-spacing:0.5px;}"
                "QPushButton:hover{background:#11312B;}"
            )
            self.btn_tienda.clicked.connect(self._abrir_selector_tienda)
            left_hbox.addWidget(self.btn_tienda, 0, Qt.AlignmentFlag.AlignVCenter)
            self._actualizar_chip_tienda()
        left_hbox.addStretch()

        top_bar.addWidget(left_panel, 1)  # stretch=1 → mirrors right side

        # ── CENTER (no stretch — stays perfectly centered) ─────────────────
        center_block = QWidget()
        center_block.setStyleSheet("background: transparent; border: none;")
        center_vbox = QVBoxLayout(center_block)
        center_vbox.setContentsMargins(0, 0, 0, 0)
        center_vbox.setSpacing(2)
        center_vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Título de la APLICACIÓN (marca del software, centrado).
        title = QLabel(tr("menu.smart_manager", default="SMART MANAGER"))
        title.setObjectName("titulo_principal")
        title.setFont(QFont("Segoe UI", 32, QFont.Weight.Black))
        title.setStyleSheet("""
            color: white;
            border: none;
            background: transparent;
            letter-spacing: 4px;
            """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._subtitle_lbl = subtitle = QLabel(tr("menu.subtitle"))
        subtitle.setObjectName("subtitulo_principal")
        subtitle.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        subtitle.setStyleSheet("""
            color: #00FFC6;
            border: none;
            background: transparent;
            letter-spacing: 2px;
            """)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        center_vbox.addWidget(title)
        center_vbox.addWidget(subtitle)
        top_bar.addWidget(center_block, 0, Qt.AlignmentFlag.AlignVCenter)

        # ── RIGHT side (stretch=1) — user info + SOMA indicator ───────────
        right_panel = QWidget()
        right_panel.setStyleSheet("background: transparent; border: none;")
        right_hbox = QHBoxLayout(right_panel)
        right_hbox.setContentsMargins(0, 0, 0, 0)
        right_hbox.setSpacing(12)
        right_hbox.addStretch()

        self._user_info_lbl = user_info = QLabel(
            tr(
                "menu.user_info",
                nombre=self.nombre_usuario.upper(),
                perfil=self._perfil_traducido(),
            )
        )
        user_info.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        user_info.setStyleSheet("""
            color: #00FFC6;
            background: transparent;
            border: none;
            letter-spacing: 1px;
            """)
        right_hbox.addWidget(user_info, 0, Qt.AlignmentFlag.AlignVCenter)

        self._soma_indicator = _SomaIndicator(self)
        right_hbox.addSpacing(14)
        right_hbox.addWidget(self._soma_indicator, 0, Qt.AlignmentFlag.AlignVCenter)
        # SOMA Copiloto IA — Fase 2: el botón/píldora SOMA se sustituye por el PERSONAJE (overlay
        # a nivel de app). Se oculta la píldora (se conserva el objeto para no romper referencias
        # como soma_set_estado, que actualiza un widget oculto sin efecto visual).
        self._soma_indicator.setVisible(False)

        top_bar.addWidget(right_panel, 1)  # stretch=1 → mirrors left side

        main_layout.addLayout(top_bar)

        menu_container = QFrame()
        menu_container.setStyleSheet("background: transparent; border: none;")
        menu_layout = QVBoxLayout(menu_container)
        menu_layout.setContentsMargins(0, 2, 0, 0)
        menu_layout.setSpacing(0)

        grid_container = QFrame()
        grid_container.setStyleSheet("background: transparent; border: none;")
        grid_layout = QGridLayout(grid_container)
        grid_layout.setHorizontalSpacing(8)
        grid_layout.setVerticalSpacing(6)
        grid_layout.setContentsMargins(0, 0, 0, 0)

        botones_principales = [
            ("TPV", "tpv", 0, 0, False, "#22F4E6", "cash_register"),
            ("Logística", "logistica", 0, 1, False, "#22F4E6", "truck"),
            ("Stock", "stock", 0, 2, False, "#22F4E6", "box"),
            ("Ubicación", "ubicacion", 0, 3, False, "#22F4E6", "search"),
            ("Artículo", "info", 0, 4, False, "#22F4E6", "hand_bag"),
            (
                "Documentos",
                "documentos",
                0,
                5,
                "ADMINISTRADOR|GERENTE|SUPERADMIN",
                "#22F4E6",
                "document",
            ),
            ("Correo", "correo", 1, 0, "ADMINISTRADOR|GERENTE", "#22F4E6", "mail"),
            ("Mermas", "mermas", 1, 1, False, "#22F4E6", "trash"),
            ("Etiquetas", "etiquetas", 1, 2, False, "#22F4E6", "tag"),
            ("Reposición", "reposicion", 1, 3, False, "#22F4E6", "box_refresh"),
            ("Ventas", "ventas", 1, 4, True, "#22F4E6", "line_chart"),
            (
                "Catálogo Web",
                "catalogo",
                1,
                5,
                "ADMINISTRADOR|GERENTE|SUPERADMIN",
                "#22F4E6",
                "shopping_bag",
            ),
        ]

        for texto, v_id, fila, col, solo_admin, color, icon_key in botones_principales:
            tiene_acceso = True
            if solo_admin:
                if isinstance(solo_admin, str):
                    allowed = [
                        p.strip().upper() for p in solo_admin.split("|") if p.strip()
                    ]
                    if self.perfil not in allowed:
                        tiene_acceso = False
                elif solo_admin is True:
                    if v_id == "ventas" and self.perfil not in [
                        "ADMINISTRADOR",
                        "GERENTE",
                    ]:
                        tiene_acceso = False

            if tiene_acceso:
                if not self._visible_en_menu(v_id):
                    continue   # modo pyme simple: ocultar módulo no esencial (celda vacía, sin candado)
                # Gating por EDICIÓN: Catálogo Web se oculta en Bakery (carta física en el local).
                if v_id == "catalogo":
                    try:
                        from src.services import verticales as _V
                        if not _V.visible("catalogo.web"):
                            continue
                    except Exception:
                        pass
                btn = self.crear_tarjeta_menu(texto, v_id, color, icon_key)
                grid_layout.addWidget(
                    btn, fila, col, alignment=Qt.AlignmentFlag.AlignCenter
                )
            else:
                self.crear_bloqueo_visual(grid_layout, fila, col)

        menu_layout.addWidget(grid_container, alignment=Qt.AlignmentFlag.AlignCenter)

        footer_container = QWidget()
        footer_container.setStyleSheet("background: transparent; border: none;")
        footer_layout = QVBoxLayout(footer_container)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(0)

        footer_grid = QGridLayout()
        footer_grid.setHorizontalSpacing(8)
        footer_grid.setVerticalSpacing(4)
        footer_grid.setContentsMargins(0, 0, 0, 0)

        footer_buttons = []

        # Configuración → esquina inferior IZQUIERDA (botón plano, fuera del grid).
        btn_config = None
        if self.perfil == "ADMINISTRADOR":
            btn_config = self._crear_boton_esquina(
                "Configuración", "configuracion", "#F1E55B", "gear"
            )

        if self.perfil in ("ADMINISTRADOR", "GERENTE", "SUPERADMIN"):
            # UX-TPV-01 (P4): acceso directo a la Gestión de Caja existente. Icono caja
            # fuerte en turquesa (color de tarjeta cian, no amarillo).
            btn_caja = self.crear_tarjeta_menu(
                "Gestión Caja", "gestion_caja", "#22F4E6", "safe"
            )
            footer_buttons.append(btn_caja)

        # NOTA: Correo, Documentos y Catálogo ya están en la rejilla superior; aquí
        # NO se duplican.

        if self.perfil in ("ADMINISTRADOR", "GERENTE", "SUPERADMIN"):
            # Proveedores (antes "Compras"). Compras avanzado vive como pestaña interna.
            btn_compras = self.crear_tarjeta_menu(
                "Proveedores", "compras", "#22F4E6", "delivery_clipboard"
            )
            footer_buttons.append(btn_compras)
            btn_clientes = self.crear_tarjeta_menu(
                "Clientes", "clientes_crm", "#22F4E6", "people"
            )
            footer_buttons.append(btn_clientes)

        if self.perfil in ("ADMINISTRADOR", "GERENTE", "SUPERADMIN"):
            btn_contab = self.crear_tarjeta_menu(
                "Contabilidad", "contabilidad", "#22F4E6", "calculator_coins"
            )
            footer_buttons.append(btn_contab)
            btn_tes = self.crear_tarjeta_menu(
                "Tesorería", "tesoreria", "#22F4E6", "bank_money"
            )
            footer_buttons.append(btn_tes)
            btn_bi = self.crear_tarjeta_menu(
                "Centro de Inteligencia", "bi", "#22F4E6", "dashboard"
            )
            footer_buttons.append(btn_bi)
            # Modelos AEAT migrado → Contabilidad (pestaña AEAT).

        if self.perfil in ("SUPERADMIN", "ADMINISTRADOR"):
            btn_seg = self.crear_tarjeta_menu(
                "Seguridad", "seguridad", "#22F4E6", "guard"
            )
            footer_buttons.append(btn_seg)

        btn_wf = self.crear_tarjeta_menu(
            "Aprobaciones", "workflow", "#22F4E6", "clipboard_check"
        )
        footer_buttons.append(btn_wf)

        # La tarjeta "Notificaciones" se retira del menu principal (el motor interno de
        # notificaciones sigue activo; el Centro de Actividad permanece accesible por ruta).

        if self.perfil in ("SUPERADMIN", "ADMINISTRADOR"):
            btn_saas = self.crear_tarjeta_menu("SaaS", "saas", "#22F4E6", "subscription")
            footer_buttons.append(btn_saas)

        # Multi-Tenant Cloud Manager (Fase V · Bloque 7): panel maestro de TODAS las empresas SaaS.
        # SOLO SUPERADMIN (ve datos de todas las empresas → nunca visible para un admin de empresa).
        if self.perfil == "SUPERADMIN":
            btn_cloud = self.crear_tarjeta_menu(
                "Cloud Manager", "cloud_manager", "#22F4E6", "cloud"
            )
            footer_buttons.append(btn_cloud)

        if self.perfil in ("ADMINISTRADOR", "GERENTE", "SUPERADMIN"):
            btn_rrhh = self.crear_tarjeta_menu("RRHH", "rrhh", "#22F4E6", "people_search")
            footer_buttons.append(btn_rrhh)

            btn_proy = self.crear_tarjeta_menu("Proyectos", "proyectos", "#22F4E6", "kanban")
            footer_buttons.append(btn_proy)

        btn_portal = self.crear_tarjeta_menu(
            "Portal del empleado", "portal", "#22F4E6", "monitor_search"
        )
        footer_buttons.append(btn_portal)

        if self.perfil in ("ADMINISTRADOR", "GERENTE", "SUPERADMIN"):
            # Kárdex, Inventario físico, Stock por almacén y Lotes migrados → Mostrar stock (pestañas).
            btn_gesalm = self.crear_tarjeta_menu(
                "Almacenes", "almacenes", "#22F4E6", "warehouse"
            )
            footer_buttons.append(btn_gesalm)

            # Producción / Fabricación (MRP): SIN tarjeta en el menú principal (retirada a propósito). El
            # cuadro de mando (`MRPDashboardWindow`, con pestañas Órdenes · Sugerencias · KPIs · BOM) se
            # accede EXCLUSIVAMENTE desde Almacenes · Operaciones → pestaña "MRP / Fabricación". Se evita la
            # doble entrada al mismo módulo. Toda la lógica sigue en `services.mrp` (sin cambios).

            # Calidad: SIN tarjeta en el menú principal (retirada a propósito). El módulo de Calidad
            # (`CalidadDashboardWindow`) y su servicio siguen intactos y se acceden EXCLUSIVAMENTE desde la
            # pestaña "Calidad" de Compras/Proveedores (`compras_gestion.py`), evitando una doble entrada al
            # mismo módulo. El enrutado por v_id "calidad" se conserva por compatibilidad (no crea tarjeta).

            # Mantenimiento (GMAO): SIN tarjeta en el menú principal (MIGRADO a "Soporte Posventa", que aloja
            # ahora sus 4 pestañas: Activos · Órdenes de trabajo · Planes preventivos · KPIs [unificados con
            # los de SAT]). Se evita la doble entrada. El enrutado v_id "gmao" se conserva (compatibilidad).

            # Posventa (SAT + GMAO): SIN tarjeta en el menú principal (retirada a propósito). El módulo de
            # soporte (`SATDashboardWindow`) se accede desde el dashboard de CRM, y GMAO/Mantenimiento desde
            # Almacenes · Operaciones → pestaña "GMAO / Mantenimiento". Se evita la doble entrada.

            # Fiscal: SIN tarjeta en el menú principal (MIGRADO a Contabilidad → pestaña AEAT, que aloja
            # ahora 3 apartados: Generar · Certificados · Registros Verifactu, reutilizando `FiscalPanels`).
            # Se evita la doble entrada al mismo módulo. El enrutado v_id "fiscal" se conserva (compatibilidad).

            btn_camaras = self.crear_tarjeta_menu(
                "Cámaras", "camaras", "#22F4E6", "security_camera"
            )
            footer_buttons.append(btn_camaras)

            btn_migracion = self.crear_tarjeta_menu(
                "Migrar datos", "migracion", "#22F4E6", "box_refresh"
            )
            footer_buttons.append(btn_migracion)

            # Edición PHARMACY: recetas y dispensación (tarjeta gateada por edición).
            try:
                from src.services import verticales
                if verticales.visible("pharmacy.recetas"):
                    btn_recetas = self.crear_tarjeta_menu("Recetas", "recetas", "#22F4E6", "document")
                    footer_buttons.append(btn_recetas)
                # Edición BAKERY: obrador / producción diaria (tarjeta gateada por edición).
                if verticales.visible("bakery.obrador"):
                    btn_obrador = self.crear_tarjeta_menu("Obrador", "obrador", "#22F4E6", "box_refresh")
                    footer_buttons.append(btn_obrador)
                # Reparto: FUNCIÓN BASE (no edición); flota y rutas de reparto, visible en las versiones que la incluyen.
                if verticales.visible("transporte.reparto"):
                    btn_transporte = self.crear_tarjeta_menu("Reparto", "transporte", "#22F4E6", "truck")
                    footer_buttons.append(btn_transporte)
                # Distribución B2B: FUNCIÓN BASE (no edición); visible en las versiones que la incluyen.
                if verticales.visible("distribucion.expedicion"):
                    btn_distri = self.crear_tarjeta_menu("Distribución", "distribucion", "#22F4E6",
                                                         "delivery_clipboard")
                    footer_buttons.append(btn_distri)
            except Exception:
                pass

            btn_market = self.crear_tarjeta_menu(
                "App Store", "marketplace", "#22F4E6", "marketplace"
            )
            footer_buttons.append(btn_market)

        # Salir → esquina inferior DERECHA (botón plano, fuera del grid).
        btn_salir = self._crear_boton_esquina("Salir", "logout", "#FF5C70", "logout")

        # Modo pyme simple: crear_tarjeta_menu devuelve None para los módulos no esenciales →
        # se descartan aquí (nunca se crean ni se colocan).
        footer_buttons = [b for b in footer_buttons if b is not None]

        columns = 6
        for index, widget in enumerate(footer_buttons):
            row = index // columns
            col = index % columns
            footer_grid.addWidget(
                widget, row, col, alignment=Qt.AlignmentFlag.AlignCenter
            )

        footer_layout.addLayout(footer_grid)
        menu_layout.addWidget(footer_container, alignment=Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(menu_container, alignment=Qt.AlignmentFlag.AlignCenter)
        main_layout.addStretch()

        # ── Barra inferior: Configuración (izq.) · versión (centro) · Salir (der.) ──
        self._version_lbl = version_lbl = QLabel(f"v2.4.0 - {tr('menu.powered_by')}")
        version_lbl.setStyleSheet(
            "color:#425061;font-size:10px;font-weight:800;border:none;background:transparent;"
        )
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(8, 0, 8, 2)
        if btn_config is not None:
            bottom_bar.addWidget(
                btn_config, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom
            )
        bottom_bar.addStretch()
        bottom_bar.addWidget(version_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        bottom_bar.addStretch()
        bottom_bar.addWidget(
            btn_salir, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom
        )
        main_layout.addLayout(bottom_bar)

        self._aplicar_refuerzo_global()
        # Re-aplica el estilo plano de las esquinas (por si el refuerzo global lo pisó).
        for _b, _c in getattr(self, "_corner_btns", []):
            self._estilar_boton_esquina(_b, _c)
            _b.setGraphicsEffect(None)

    def _aplicar_refuerzo_global(self):
        if aplicar_estilo_widget is None:
            return
        for widget in self.findChildren(QWidget):
            try:
                aplicar_estilo_widget(widget)
            except Exception:
                pass

    # ============================================================
    # BLOQUE INTERNACIONALIZACIÓN (i18n)
    # ============================================================
    def _retraducir(self):
        """Re-traduce el menú al idioma activo (en caliente)."""
        try:
            for v_id, btn in self._cards.items():
                key = self._MENU_CARD_KEYS.get(v_id)
                if key:
                    btn.setText(tr(key))
            if hasattr(self, "_subtitle_lbl"):
                self._subtitle_lbl.setText(tr("menu.subtitle"))
            if hasattr(self, "_user_info_lbl"):
                self._user_info_lbl.setText(
                    tr(
                        "menu.user_info",
                        nombre=self.nombre_usuario.upper(),
                        perfil=self._perfil_traducido(),
                    )
                )
            if hasattr(self, "_version_lbl"):
                self._version_lbl.setText(f"v2.4.0 - {tr('menu.powered_by')}")
            for lbl in self._lock_lbls:
                try:
                    lbl.setText("🔒\n" + tr("menu.restricted"))
                except Exception:
                    pass
        except Exception:
            pass

    # ============================================================
    # BLOQUE CREACIÓN DE BOTONES E ICONOS
    # ============================================================
    # Mapa v_id -> clave de traducción del texto de la tarjeta.
    # Módulos cuyo icono usa un PNG mejorado de assets/ (en vez del SVG). El icono se muestra a todo
    # color en reposo y, en HOVER, se conmuta a su silueta oscura (mismo swap que las tarjetas SVG:
    # el fondo pasa al color de acento y el icono se invierte a oscuro).
    _PNG_MODULOS = {
        "tpv": "TPV.png",
        "logistica": "Logistica.png",
        "stock": "Stock.png",
        "ubicacion": "Ubicacion.png",
        "info": "Articulo.png",
        "documentos": "Documentos.png",
        "correo": "Correo.png",
        "mermas": "Mermas.png",
        "etiquetas": "Etiquetas.png",
        "reposicion": "Reposición.png",
        "ventas": "Ventas.png",
        "catalogo": "Catálogo Web.png",
        "gestion_caja": "Gestión Caja.png",
        "compras": "Proveedores.png",
        "clientes_crm": "CRM.png",
        "contabilidad": "Contabilidad.png",
        "tesoreria": "Tesoreria.png",
        "bi": "Dashboard.png",
        "seguridad": "Roles_permisos.png",
        "workflow": "Tareas.png",
        "saas": "Suscripción.png",
        "rrhh": "RRHH.png",
        "proyectos": "Proyectos.png",
        "portal": "Portal_empleado.png",
        "almacenes": "Almacenes.png",
        "camaras": "Cámaras.png",
        "migracion": "Migrar datos.png",
        "obrador": "Obrador.png",
        "distribucion": "Distribucion.png",
        "transporte": "Reparto.png",
        "marketplace": "App_store.png",
    }

    # Iconos cuyo PNG viene en un turquesa más apagado: se RECOLOREAN al neón de acento del resto.
    # Iconos que se RECOLOREAN a neón (para uniformar los que venían en otro turquesa). Los PNG nuevos ya
    # traen sus colores propios, así que NO se tintan (se muestran con su color original). Solo se conserva
    # "catalogo" (Catálogo Web se mantiene igual, por decisión de producto).
    _PNG_TINT_NEON = {"catalogo"}

    # Iconos con el trazo un poco más grueso: se ADELGAZA su contorno (erosión) en vez de engrosarlo.
    _PNG_FINO = {"correo"}

    # Iconos de línea con el trazo más FINO que el resto: se engrosa más (radio 2) para igualarlos.
    _PNG_GRUESO = {"logistica", "ventas", "clientes_crm"}

    # Iconos que se muestran un poco más pequeños dentro de la caja (factor de escala, sin tocar trazo).
    _PNG_ESCALA = {"ventas": 0.82, "correo": 0.85}

    _MENU_CARD_KEYS = {
        "logistica": "menu.card_recepcion",
        "stock": "menu.card_stock",
        "ubicacion": "menu.card_ubicacion",
        "info": "menu.card_articulo",
        "mermas": "menu.card_mermas",
        "etiquetas": "menu.card_etiquetas",
        "reposicion": "menu.card_reposicion",
        "ventas": "menu.card_ventas",
        "configuracion": "menu.card_config",
        "correo": "menu.card_correo",
        "documentos": "menu.card_documentos",
        "catalogo": "menu.card_catalogo",
        "compras": "menu.card_compras",
        "compras_avanzado": "menu.card_compras_avanzado",
        "clientes_crm": "menu.card_clientes_crm",
        "contabilidad": "menu.card_contabilidad",
        "tesoreria": "menu.card_tesoreria",
        "bi": "menu.card_bi",
        "aeat": "menu.card_aeat",
        "seguridad": "menu.card_seguridad",
        "workflow": "menu.card_workflow",
        "notificaciones": "menu.card_notificaciones",
        "saas": "menu.card_saas",
        "rrhh": "menu.card_rrhh",
        "portal": "menu.card_portal",
        "kardex": "menu.card_kardex",
        "inventario_fisico": "menu.card_inventario_fisico",
        "lotes": "menu.card_lotes",
        "stock_almacen": "menu.card_stock_almacen",
        "almacenes": "menu.card_almacenes",
        "tpv": "menu.card_tpv",
        "logout": "menu.card_salir",
    }

    @staticmethod
    def _recortar_transparente(pm, umbral=12):
        """Recorta el margen TRANSPARENTE del PNG (deja un margen homogéneo pequeño) para que el
        dibujo LLENE la caja del icono. Muchos PNG traen mucho aire alrededor y por eso se ven
        pequeños; recortándolo, todos los iconos quedan grandes y del mismo tamaño visual."""
        try:
            import numpy as np
            img = pm.toImage().convertToFormat(QImage.Format.Format_ARGB32)
            w, h = img.width(), img.height()
            if w == 0 or h == 0:
                return pm
            ptr = img.constBits(); ptr.setsize(h * img.bytesPerLine())
            arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, img.bytesPerLine() // 4, 4))[:, :w, :]
            mask = arr[:, :, 3] > umbral                       # canal alfa (BGRA en memoria)
            if not mask.any():
                return pm
            ys = np.where(mask.any(axis=1))[0]
            xs = np.where(mask.any(axis=0))[0]
            y0, y1, x0, x1 = int(ys[0]), int(ys[-1]), int(xs[0]), int(xs[-1])
            pad = int(0.05 * max(x1 - x0, y1 - y0))
            x0 = max(0, x0 - pad); y0 = max(0, y0 - pad)
            x1 = min(w - 1, x1 + pad); y1 = min(h - 1, y1 + pad)
            return pm.copy(x0, y0, x1 - x0 + 1, y1 - y0 + 1)
        except Exception:
            return pm

    @staticmethod
    def _engrosar_pixmap(pm, radio=2):
        """Engrosa LEVEMENTE el trazo dilatando la silueta (unión de copias desplazadas en un disco
        de radio `radio`). Se aplica a resolución NATIVA (líneas bien separadas) para engrosar sin
        fusionar el detalle; amplía el lienzo `radio` px por lado para no recortar el borde."""
        try:
            offs = [(dx, dy) for dx in range(-radio, radio + 1) for dy in range(-radio, radio + 1)
                    if dx * dx + dy * dy <= radio * radio]
            res = QPixmap(pm.width() + 2 * radio, pm.height() + 2 * radio)
            res.fill(Qt.GlobalColor.transparent)
            p = QPainter(res)
            for dx, dy in offs:
                p.drawPixmap(radio + dx, radio + dy, pm)
            p.end()
            return res
        except Exception:
            return pm

    _png_cache = {}   # filename -> pixmap procesado (recortado + engrosado + escalado 256, a color)

    @staticmethod
    def _afinar_pixmap(pm, radio=2):
        """ADELGAZA el trazo (erosión de la silueta: mínimo del alfa en un disco de radio `radio`),
        para reducir el grosor del contorno de un icono concreto. A resolución nativa."""
        try:
            import numpy as np
            img = pm.toImage().convertToFormat(QImage.Format.Format_ARGB32)
            w, h = img.width(), img.height()
            if w == 0 or h == 0:
                return pm
            ptr = img.bits(); ptr.setsize(h * img.bytesPerLine())
            arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, img.bytesPerLine() // 4, 4))
            alpha = arr[:, :w, 3]
            base = alpha.astype(np.int16)
            padded = np.pad(base, radio, mode="constant", constant_values=0)
            er = base.copy()
            for dy in range(-radio, radio + 1):
                for dx in range(-radio, radio + 1):
                    if dx * dx + dy * dy <= radio * radio:
                        er = np.minimum(er, padded[radio + dy:radio + dy + h, radio + dx:radio + dx + w])
            alpha[:, :] = er.astype(np.uint8)            # escribe el alfa erosionado en la propia QImage
            return QPixmap.fromImage(img)
        except Exception:
            return pm

    @staticmethod
    def _reducir_pixmap(pm, escala):
        """Reduce el TAMAÑO del dibujo dejándolo centrado con margen transparente (no cambia el
        grosor del trazo, solo su escala dentro de la caja del icono)."""
        try:
            if not escala or escala >= 0.999:
                return pm
            w, h = pm.width(), pm.height()
            sw, sh = max(1, int(w * escala)), max(1, int(h * escala))
            scaled = pm.scaled(sw, sh, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            canvas = QPixmap(w, h)
            canvas.fill(Qt.GlobalColor.transparent)
            p = QPainter(canvas)
            p.drawPixmap((w - scaled.width()) // 2, (h - scaled.height()) // 2, scaled)
            p.end()
            return canvas
        except Exception:
            return pm

    def _icono_png_modulo(self, filename, dark=False, size=256, tint=None, ajuste=1, escala=1.0):
        """Carga un PNG mejorado de assets/ como QIcon: recorta el margen transparente (llena la
        caja), engrosa un poco el trazo a resolución nativa y lo renderiza a alta resolución (256).
        `dark=True` → SILUETA oscura (HOVER). `tint` (color) → recolorea el icono a ese color
        (para uniformar los que vienen en un turquesa distinto). El pixmap base se cachea."""
        try:
            clave = (filename, ajuste)
            pm = type(self)._png_cache.get(clave)
            if pm is None:
                from src.utils import recursos
                ruta = recursos.ruta_recurso("assets", filename)
                pm = QPixmap(ruta)
                if pm.isNull():
                    return None
                pm = self._recortar_transparente(pm)      # quitar margen transparente → llena la caja
                if ajuste > 0:
                    pm = self._engrosar_pixmap(pm, radio=ajuste)     # engrosar levemente
                elif ajuste < 0:
                    pm = self._afinar_pixmap(pm, radio=-ajuste)      # adelgazar el contorno
                if pm.width() > size or pm.height() > size:
                    pm = pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
                type(self)._png_cache[clave] = pm
            if escala and escala < 0.999:
                pm = self._reducir_pixmap(pm, escala)     # reducir tamaño (margen), sin tocar el trazo
            if dark:
                color = "#0B1118"
            elif tint:
                color = tint
            else:
                return QIcon(pm)                          # color nativo del PNG
            tinted = QPixmap(pm.size())
            tinted.fill(Qt.GlobalColor.transparent)
            p = QPainter(tinted)
            p.drawPixmap(0, 0, pm)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            p.fillRect(tinted.rect(), QColor(color))
            p.end()
            return QIcon(tinted)
        except Exception:
            return None

    def crear_tarjeta_menu(self, texto, v_id, color, icon_key):
        # MODO PYME SIMPLE: no crear (ni registrar) las tarjetas de módulos no esenciales.
        if not self._visible_en_menu(v_id):
            return None
        png = self._PNG_MODULOS.get(v_id)
        tint = color if v_id in self._PNG_TINT_NEON else None   # recolorear a neón los apagados
        ajuste = 2 if v_id in self._PNG_GRUESO else (-2 if v_id in self._PNG_FINO else 1)  # +2 engrosar / -2 afinar / 1 leve
        escala = self._PNG_ESCALA.get(v_id, 1.0)               # <1 = mostrar el icono más pequeño
        icono_normal = self._icono_png_modulo(png, dark=False, tint=tint, ajuste=ajuste, escala=escala) if png else None
        icono_hover = self._icono_png_modulo(png, dark=True, ajuste=ajuste, escala=escala) if png else None
        if icono_normal is None or icono_hover is None:   # sin PNG o carga fallida → SVG (fallback)
            icono_normal = self.crear_icono(icon_key, color)
            icono_hover = self.crear_icono(icon_key, "#0B1118")
        key = self._MENU_CARD_KEYS.get(v_id)
        display = tr(key) if key else texto
        btn = MenuCardButton(
            display, icono_normal, icono_hover, color=color, parent=self
        )

        if v_id == "logout":
            btn.clicked.connect(self.cerrar_sesion)
        elif v_id == "configuracion":
            btn.clicked.connect(self.abrir_modulo_configuracion)
        elif v_id == "gestion_caja":
            # P4.1: abre la Gestión de Caja en su ventana propia (GestionCajaWindow),
            # reutilizando la lógica/permisos existentes (ya no es pestaña de Configuración).
            btn.clicked.connect(lambda _=False: self.abrir_gestion_caja())
        else:
            btn.clicked.connect(lambda _, id_w=v_id: self.abrir_ventana_por_id(id_w))

        # Registro para re-traducción en caliente.
        self._cards[v_id] = btn
        return btn

    def _estilar_boton_esquina(self, btn, color):
        """Estilo PLANO para los botones de esquina (Config/Salir): en reposo, sin
        contorno ni fondo (integrado con el menú) y su color característico; en HOVER,
        swap completo → fondo del color + icono/texto oscuros (igual que las tarjetas)."""
        btn.setStyleSheet(
            f"QToolButton{{background:transparent;border:none;color:{color};"
            f"font-family:'Segoe UI';font-weight:900;font-size:11px;}}"
            f"QToolButton:hover{{background:{color};border:none;border-radius:12px;color:#0B1118;}}"
            f"QToolButton:pressed{{background:{color};border:none;border-radius:12px;color:#0B1118;}}"
        )

    def _crear_boton_esquina(self, texto, v_id, color, icon_key):
        """Crea Configuración/Salir como botón plano para las esquinas inferiores:
        ~25% más pequeño, sin fondo ni borde en reposo, con hover swap y su color."""
        btn = self.crear_tarjeta_menu(texto, v_id, color, icon_key)
        btn.setFixedSize(82, 72)
        btn.setIconSize(QSize(36, 36))
        # NO se sobrescribe _icono_hover: en hover se usa el icono oscuro (swap real).
        btn.setIcon(btn._icono_normal)
        btn.setGraphicsEffect(None)            # sin glow → se integra con el fondo
        self._estilar_boton_esquina(btn, color)
        if not hasattr(self, "_corner_btns"):
            self._corner_btns = []
        self._corner_btns.append((btn, color))
        return btn

    def crear_icono(self, icon_key, color):
        svg_map = {
            "cloud": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M40 92h48a20 20 0 0 0 4 -39 26 26 0 0 0 -50 -8 18 18 0 0 0 -2 47z"/>
                    <path d="M52 74l8 8 16 -16"/>
                  </g>
                </svg>
            """,
            "marketplace": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="26" y="26" width="32" height="32" rx="8"/>
                    <rect x="70" y="26" width="32" height="32" rx="8"/>
                    <rect x="26" y="70" width="32" height="32" rx="8"/>
                    <path d="M86 72v28M72 86h28"/>
                  </g>
                </svg>
            """,
            "security_camera": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M20 44l64 -16 6 22 -64 16z"/>
                    <path d="M24 50l9 20 12 -3 -7 -18"/>
                    <circle cx="60" cy="58" r="6"/>
                    <path d="M88 52l16 8"/>
                    <path d="M104 44v44"/>
                    <path d="M96 66h12"/>
                  </g>
                </svg>
            """,
            "truck": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="18" y="44" width="48" height="26" rx="4"/>
                    <path d="M66 52h16l10 12v6H66z"/>
                    <path d="M66 61h10"/>
                    <circle cx="32" cy="76" r="6"/>
                    <circle cx="78" cy="76" r="6"/>
                    <path d="M18 70h8M38 70h28M84 70h8"/>
                  </g>
                </svg>
            """,
            "box": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M64 18l34 18-34 18-34-18 34-18z"/>
                    <path d="M30 36v38l34 18 34-18V36"/>
                    <path d="M64 54v38"/>
                    <path d="M47 27l34 18"/>
                  </g>
                </svg>
            """,
            "people": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="48" cy="44" r="16"/>
                    <path d="M22 96c0-16 12-26 26-26s26 10 26 26"/>
                    <circle cx="88" cy="50" r="12"/>
                    <path d="M84 72c12 0 22 9 22 24"/>
                  </g>
                </svg>
            """,
            "kanban": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="20" y="24" width="88" height="80" rx="8"/>
                    <path d="M49 24v80"/>
                    <path d="M79 24v80"/>
                    <rect x="28" y="38" width="13" height="22" rx="2"/>
                    <rect x="57.5" y="38" width="13" height="34" rx="2"/>
                    <rect x="87" y="38" width="13" height="16" rx="2"/>
                  </g>
                </svg>
            """,
            "search": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="54" cy="54" r="26"/>
                    <path d="M74 74l24 24"/>
                  </g>
                </svg>
            """,
            "document": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M38 20h34l18 18v58a8 8 0 0 1-8 8H38a8 8 0 0 1-8-8V28a8 8 0 0 1 8-8z"/>
                    <path d="M72 20v18h18"/>
                    <path d="M46 56h28M46 70h28M46 84h20"/>
                  </g>
                </svg>
            """,
            "trash": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M42 32h44"/>
                    <path d="M50 32v-8h28v8"/>
                    <rect x="38" y="38" width="52" height="56" rx="8"/>
                    <path d="M54 50v30M64 50v30M74 50v30"/>
                  </g>
                </svg>
            """,
            "tag": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M28 58V34a8 8 0 0 1 8-8h24l40 40a10 10 0 0 1 0 14L78 102a10 10 0 0 1-14 0L28 66a11 11 0 0 1 0-8z"/>
                    <circle cx="48" cy="46" r="4"/>
                  </g>
                </svg>
            """,
            "bar_chart": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 96h84"/>
                    <rect x="28" y="68" width="14" height="28" rx="2"/>
                    <rect x="54" y="56" width="14" height="40" rx="2"/>
                    <rect x="80" y="42" width="14" height="54" rx="2"/>
                    <path d="M28 42c18 0 32-8 50-24"/>
                    <path d="M68 18h10v10"/>
                  </g>
                </svg>
            """,
            "line_chart": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="28" cy="82" r="4"/>
                    <circle cx="54" cy="64" r="4"/>
                    <circle cx="80" cy="72" r="4"/>
                    <path d="M32 79l18-12 24 6 22-22"/>
                    <path d="M86 51h12v12"/>
                  </g>
                </svg>
            """,
            "gear": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linejoin="round" stroke-linecap="round">
                    <path d="M52.1 19.6 L75.9 19.6 L73.9 28.3 L82.2 31.8 L87.0 24.2 L103.8 41.0 L96.2 45.8 L99.7 54.1 L108.4 52.1 L108.4 75.9 L99.7 73.9 L96.2 82.2 L103.8 87.0 L87.0 103.8 L82.2 96.2 L73.9 99.7 L75.9 108.4 L52.1 108.4 L54.1 99.7 L45.8 96.2 L41.0 103.8 L24.2 87.0 L31.8 82.2 L28.3 73.9 L19.6 75.9 L19.6 52.1 L28.3 54.1 L31.8 45.8 L24.2 41.0 L41.0 24.2 L45.8 31.8 L54.1 28.3 Z"/>
                    <circle cx="64" cy="64" r="16"/>
                  </g>
                </svg>
            """,
            "logout": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M52 28H34a8 8 0 0 0-8 8v56a8 8 0 0 0 8 8h18"/>
                    <path d="M68 44l24 20-24 20"/>
                    <path d="M40 64h50"/>
                  </g>
                </svg>
            """,
            "shopping_bag": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 46h84l-10 66H32L22 46z"/>
                    <path d="M46 46c0-14 8-24 18-24s18 10 18 24"/>
                  </g>
                </svg>
            """,
            "mail": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="20" y="32" width="88" height="64" rx="8"/>
                    <path d="M24 38l40 30 40-30"/>
                  </g>
                </svg>
            """,
            # ── Iconos dedicados (estilo línea, color dinámico) ──────────────
            "hand_bag": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M42 30l4-12h36l4 12z"/>
                    <rect x="40" y="30" width="48" height="32" rx="3"/>
                    <path d="M54 30c0-9 4.5-14 10-14s10 5 10 14"/>
                    <path d="M16 74c6-3 11-1 17 2l7 3h26c6 0 11 2 15 7"/>
                    <path d="M16 74c-3 7 1 14 9 18 6 3 12 4 19 4h21"/>
                    <path d="M52 79h14M52 87h12"/>
                  </g>
                </svg>
            """,
            "box_refresh": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M64 44l22 12v24L64 92 42 80V56z"/>
                    <path d="M64 44l22 12-22 12-22-12z"/>
                    <path d="M64 68v24"/>
                    <path d="M86 56l-22 12"/>
                    <path d="M28 50a38 38 0 0 1 58-13"/>
                    <path d="M84 22l5 16-17 2"/>
                    <path d="M100 78a38 38 0 0 1-58 13"/>
                    <path d="M44 106l-5-16 17-2"/>
                  </g>
                </svg>
            """,
            "people_search": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="56" cy="52" r="33"/>
                    <path d="M80 76l26 26"/>
                    <circle cx="56" cy="40" r="8"/>
                    <path d="M42 64c0-8 6-13 14-13s14 5 14 13"/>
                    <circle cx="34" cy="46" r="6"/>
                    <path d="M24 65c0-7 4-11 10-11"/>
                    <circle cx="78" cy="46" r="6"/>
                    <path d="M78 54c6 0 10 4 10 11"/>
                  </g>
                </svg>
            """,
            "calculator_coins": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="16" y="16" width="52" height="96" rx="7"/>
                    <rect x="24" y="24" width="36" height="18" rx="2"/>
                    <path d="M28 60h10M33 55v10"/>
                    <path d="M46 60h10"/>
                    <path d="M28 78l8 8M36 78l-8 8"/>
                    <path d="M46 78l10 10M47 79h0M55 87h0"/>
                    <path d="M28 100h10M46 100h10"/>
                    <ellipse cx="92" cy="58" rx="18" ry="8"/>
                    <path d="M74 58v34c0 4.5 8 8 18 8s18-3.5 18-8V58"/>
                    <path d="M74 70c0 4.5 8 8 18 8s18-3.5 18-8"/>
                    <path d="M74 82c0 4.5 8 8 18 8s18-3.5 18-8"/>
                  </g>
                </svg>
            """,
            "safe": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="18" y="22" width="92" height="82" rx="7"/>
                    <rect x="28" y="32" width="54" height="62" rx="4"/>
                    <circle cx="55" cy="63" r="15"/>
                    <circle cx="55" cy="63" r="3.5"/>
                    <path d="M55 48v8M55 70v8M40 63h8M62 63h8M44 52l5 5M66 74l-5-5M44 74l5-5M66 52l-5 5"/>
                    <path d="M94 54v18"/>
                    <path d="M28 104v8M100 104v8"/>
                  </g>
                </svg>
            """,
            "cash_register": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="26" y="20" width="22" height="28" rx="2"/>
                    <path d="M37 26v16M37 26c-3 0-5 1.5-5 4s2 4 5 4 5 1.5 5 4-2 4-5 4"/>
                    <rect x="54" y="28" width="44" height="20" rx="2"/>
                    <rect x="60" y="34" width="10" height="8" rx="1"/>
                    <path d="M24 92V58a6 6 0 0 1 6-6h66a6 6 0 0 1 6 6v34"/>
                    <rect x="60" y="58" width="38" height="28" rx="2"/>
                    <path d="M73 58v28M86 58v28M60 67.5h38M60 77h38"/>
                    <rect x="16" y="92" width="96" height="14" rx="3"/>
                  </g>
                </svg>
            """,
            "bank": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M30 42l34-22 34 22z"/>
                    <path d="M22 42h84"/>
                    <path d="M34 46v44M94 46v44"/>
                    <path d="M26 90h76M18 102h92"/>
                    <path d="M57 53c4-3 10-3 14 0"/>
                    <path d="M55 55c-7 9-8 22 0 30 5 5 13 5 18 0 8-8 7-21 0-30z"/>
                    <path d="M64 62v17M64 62c-4 0-6 1.5-6 4s2 4 6 4 6 1.5 6 4-2 4-6 4"/>
                  </g>
                </svg>
            """,
            "monitor_search": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="16" y="20" width="80" height="54" rx="5"/>
                    <path d="M46 74v9h20v-9"/>
                    <path d="M34 92h44"/>
                    <rect x="32" y="38" width="28" height="20" rx="2"/>
                    <path d="M40 38v-5h12v5"/>
                    <path d="M32 47h28"/>
                    <circle cx="86" cy="66" r="16"/>
                    <path d="M97 77l13 13"/>
                  </g>
                </svg>
            """,
            "worker_box": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M49 38c2-9 8-14 15-14s13 5 15 14"/>
                    <path d="M44 38h40"/>
                    <circle cx="64" cy="51" r="11"/>
                    <path d="M40 86c0-13 11-22 24-22s24 9 24 22"/>
                    <path d="M55 66v16M73 66v16"/>
                    <rect x="42" y="82" width="44" height="30" rx="2"/>
                    <path d="M64 82v30"/>
                    <path d="M52 94h24"/>
                  </g>
                </svg>
            """,
            "clipboard_check": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="28" y="26" width="72" height="84" rx="8"/>
                    <rect x="50" y="18" width="28" height="16" rx="4"/>
                    <path d="M40 52l6 6 11-12"/>
                    <path d="M68 54h24"/>
                    <path d="M40 74l6 6 11-12"/>
                    <path d="M68 76h24"/>
                    <path d="M40 96l6 6 11-12"/>
                    <path d="M68 98h24"/>
                  </g>
                </svg>
            """,
            "bell": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M64 22v8"/>
                    <path d="M40 88c-5 0-7-5-4-9 5-6 7-11 7-21a21 21 0 0 1 42 0c0 10 2 15 7 21 3 4 1 9-4 9z"/>
                    <path d="M53 96a11 11 0 0 0 22 0"/>
                  </g>
                </svg>
            """,
            "guard": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M38 50C38 30 49 22 64 22s26 8 26 28"/>
                    <path d="M64 30l6 3v7c0 4-3 6-6 7-3-1-6-3-6-7v-7z"/>
                    <path d="M34 50h60l-8 8H42z"/>
                    <path d="M44 58c2 14 10 22 20 22s18-8 20-22"/>
                    <path d="M26 106c0-18 17-26 38-26s38 8 38 26"/>
                    <path d="M54 82l10 14 10-14"/>
                    <path d="M64 96l-4 10M64 96l4 10"/>
                    <rect x="61" y="86" width="6" height="7" rx="1"/>
                    <path d="M40 90h8M80 90h8"/>
                  </g>
                </svg>
            """,
            "dashboard": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="18" y="24" width="92" height="80" rx="6"/>
                    <path d="M18 40h92"/>
                    <circle cx="45" cy="68" r="15"/>
                    <path d="M45 68V53M45 68l13 7"/>
                    <path d="M76 88V70M88 88V60M100 88V76"/>
                  </g>
                </svg>
            """,
            "bank_money": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M20 52L64 28l44 24"/>
                    <path d="M20 52h88"/>
                    <path d="M30 52v40M50 52v40M78 52v40M98 52v40"/>
                    <path d="M22 98h84"/>
                    <path d="M16 108h96"/>
                    <circle cx="64" cy="42" r="2.5"/>
                  </g>
                </svg>
            """,
            "warehouse": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M18 56L64 30l46 26"/>
                    <path d="M24 56v48h80V56"/>
                    <rect x="36" y="46" width="56" height="12" rx="2"/>
                    <rect x="50" y="74" width="28" height="30"/>
                    <rect x="34" y="88" width="18" height="16"/>
                    <rect x="76" y="88" width="18" height="16"/>
                  </g>
                </svg>
            """,
            "subscription": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M26 52a40 40 0 0 1 70-12"/>
                    <path d="M96 28v14h-14"/>
                    <path d="M102 76a40 40 0 0 1-70 12"/>
                    <path d="M32 100V86h14"/>
                    <rect x="44" y="42" width="40" height="38" rx="4"/>
                    <path d="M44 54h40"/>
                    <path d="M54 42v-6M74 42v-6"/>
                    <path d="M64 60v12M60 62h7a3 3 0 0 1 0 6h-5a3 3 0 0 0 0 6h7"/>
                  </g>
                </svg>
            """,
            "delivery_clipboard": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M46 98V42c0-9-5-14-12-13c-6 1-7 8-2 10"/>
                    <circle cx="50" cy="100" r="11"/>
                    <circle cx="50" cy="100" r="3.5"/>
                    <path d="M44 95h48l-4 8"/>
                    <rect x="58" y="56" width="40" height="39"/>
                    <path d="M58 69h40M78 56v13"/>
                    <rect x="64" y="30" width="28" height="26"/>
                    <path d="M64 41l14 4l14-4M78 45v11"/>
                  </g>
                </svg>
            """,
        }

        svg_data = svg_map.get(icon_key, svg_map["box"]).encode("utf-8")
        renderer = QSvgRenderer(QByteArray(svg_data))
        pixmap = QPixmap(128, 128)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)

    def crear_bloqueo_visual(self, layout, fila, col):
        lock_container = QFrame()
        lock_container.setFixedSize(170, 150)
        lock_container.setStyleSheet("""
            background-color: rgba(20, 28, 36, 0.90);
            border: 1px dashed #3E4C5C;
            border-radius: 24px;
            """)

        glow = QGraphicsDropShadowEffect(lock_container)
        glow.setBlurRadius(12)
        glow.setColor(QColor("#2A3440"))
        glow.setOffset(0, 0)
        lock_container.setGraphicsEffect(glow)

        l_layout = QVBoxLayout(lock_container)
        l_layout.setContentsMargins(18, 18, 18, 18)
        l_layout.setSpacing(8)

        spacer_top = QLabel("")
        spacer_top.setFixedHeight(28)
        l_layout.addWidget(spacer_top)

        lbl = QLabel("🔒\n" + tr("menu.restricted"))
        lbl.setStyleSheet("""
            color: #667586;
            font-weight: 900;
            font-size: 16px;
            border: none;
            background: transparent;
            """)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lock_lbls.append(lbl)
        l_layout.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(
            lock_container, fila, col, alignment=Qt.AlignmentFlag.AlignCenter
        )

    # ============================================================
    # BLOQUE ESTADO DE CONEXIÓN A BASE DE DATOS
    # ============================================================
    def actualizar_estado_db(self):
        # Cliente fino: la UI no abre conexiones a mano; usa el helper de estado de la capa de datos.
        from src.db.conexion import db_disponible
        if db_disponible():
            self._actualizar_ref_label()
        else:
            self.ref_label.hide()
        self._actualizar_logo_label()

    def _perfil_traducido(self):
        """Tipo de perfil traducido SOLO para mostrar (ADMINISTRADOR/GERENTE/OPERARIO →
        idioma activo). self.perfil se mantiene en español como valor de lógica
        (control de acceso por rol), por eso no se traduce esa variable."""
        return tr("roles." + self.perfil.lower(), default=self.perfil).upper()

    def _actualizar_logo_label(self):
        # Logo CORPORATIVO del cliente, a la IZQUIERDA junto a la referencia de
        # tienda/almacén. Resolución dinámica: refleja un logo recién subido.
        logo_path = _resolver_logo()
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path)
            if not pix.isNull():
                scaled = pix.scaledToHeight(
                    64, Qt.TransformationMode.SmoothTransformation
                )
                self.logo_label.setPixmap(scaled)
                self.logo_label.setFixedWidth(scaled.width())
                self.logo_label.show()
                return
        self.logo_label.hide()

    def _actualizar_ref_label(self):
        # En ADMINISTRADOR/SUPERADMIN la referencia se muestra en el chip de tienda;
        # el piloto verde queda solo para GERENTE/OPERARIO.
        if self.perfil in ("SUPERADMIN", "ADMINISTRADOR"):
            self.ref_label.hide()
            return
        try:
            # Deprecación «Asignar referencia»: se resuelve por la fachada de Identidad Operativa (IOC),
            # que prefiere el código estructurado de la terminal y cae a la referencia legada si no existe.
            from src.services.identidad import identidad as _ident
            texto = _ident.etiqueta_operativa()
            if texto:
                self.ref_label.setText(texto)
                self.ref_label.show()
            else:
                self.ref_label.hide()
        except Exception:
            self.ref_label.hide()

    # ============================================================
    # BLOQUE SOMA
    # ============================================================
    def soma_set_estado(self, estado: str):
        """Proxy so main.py can update the indicator without importing it directly."""
        if hasattr(self, "_soma_indicator"):
            self._soma_indicator.soma_set_estado(estado)

    # ============================================================
    # BLOQUE APERTURA DE MÓDULOS
    # ============================================================
    def abrir_ventana_por_id(self, v_id):
        try:
            kwargs = {
                "callback_vuelta": self.mostrar_menu_principal,
                "usuario": sesion_global.usuario_actual,
            }

            if v_id == "logistica":
                from src.gui.recepcion_pale import RecepcionPaleWindow

                self.manejar_apertura(v_id, RecepcionPaleWindow, **kwargs)
            elif v_id == "ventas":
                from src.gui.ventas import VentasAnaliticaWindow

                self.manejar_apertura(v_id, VentasAnaliticaWindow, **kwargs)
            elif v_id == "ubicacion":
                from src.gui.ubicacion_tienda import UbicacionTiendaWindow

                self.manejar_apertura(v_id, UbicacionTiendaWindow, **kwargs)
            elif v_id == "reposicion":
                from src.gui.informe_reposicion import InformeReposicionWindow

                self.manejar_apertura(v_id, InformeReposicionWindow, **kwargs)
            elif v_id == "stock":
                from src.gui.mostrar_stock import MostrarStockWindow

                self.manejar_apertura(v_id, MostrarStockWindow, **kwargs)
            elif v_id == "info":
                from src.gui.info_articulo import InfoArticuloWindow

                self.manejar_apertura(v_id, InfoArticuloWindow, **kwargs)
            elif v_id == "mermas":
                from src.gui.gestion_mermas import GestionMermasWindow

                self.manejar_apertura(v_id, GestionMermasWindow, **kwargs)
            elif v_id == "etiquetas":
                from src.gui.etiquetas_precios import EtiquetasPreciosWindow

                self.manejar_apertura(v_id, EtiquetasPreciosWindow, **kwargs)
            elif v_id == "correo":
                from src.gui.correo_corporativo import CorreoCorporativoWindow

                self.manejar_apertura(v_id, CorreoCorporativoWindow, **kwargs)
            elif v_id == "documentos":
                from src.gui.centro_documental import CentroDocumentalWindow

                self.manejar_apertura(v_id, CentroDocumentalWindow, **kwargs)
            elif v_id == "camaras":
                from src.gui.camaras_gui import CamarasWindow

                self.manejar_apertura(v_id, CamarasWindow, **kwargs)
            elif v_id == "migracion":
                from src.gui.migracion_gui import MigracionDatosWindow

                self.manejar_apertura(v_id, MigracionDatosWindow, **kwargs)
            elif v_id == "recetas":
                from src.gui.recetas_gui import RecetasWindow

                self.manejar_apertura(v_id, RecetasWindow, **kwargs)
            elif v_id == "obrador":
                from src.gui.obrador_gui import ObradorWindow

                self.manejar_apertura(v_id, ObradorWindow, **kwargs)
            elif v_id == "transporte":
                from src.gui.transporte_gui import TransporteWindow

                self.manejar_apertura(v_id, TransporteWindow, **kwargs)
            elif v_id == "distribucion":
                from src.gui.distribucion_gui import DistribucionWindow

                self.manejar_apertura(v_id, DistribucionWindow, **kwargs)
            elif v_id == "marketplace":
                from src.gui.marketplace_gui import MarketplaceWindow

                self.manejar_apertura(v_id, MarketplaceWindow, **kwargs)
            elif v_id == "cloud_manager":
                from src.gui.cloud_manager_gui import CloudManagerWindow

                self.manejar_apertura(v_id, CloudManagerWindow, **kwargs)
            elif v_id == "catalogo":
                from src.gui.catalogo_gestion import CatalogoWindow

                self.manejar_apertura(v_id, CatalogoWindow, **kwargs)
            elif v_id == "compras":
                from src.gui.compras_gestion import ComprasWindow

                self.manejar_apertura(v_id, ComprasWindow, **kwargs)
            elif v_id == "compras_avanzado":
                from src.gui.compras_avanzado_gui import ComprasAvanzadoWindow

                self.manejar_apertura(v_id, ComprasAvanzadoWindow, **kwargs)
            elif v_id == "clientes_crm":
                # Dominio CRM: la entrada es el Cuadro de mando Comercial (CRMDashboard), que hospeda
                # como pestañas la gestión de Clientes y el SAT/postventa. Reutiliza las ventanas
                # existentes (clientes_gui, sat) sin duplicarlas.
                from src.gui.crm_dashboard import CRMDashboardWindow

                self.manejar_apertura(v_id, CRMDashboardWindow, **kwargs)
            elif v_id == "rrhh":
                from src.gui.rrhh_gestion import RRHHWindow

                self.manejar_apertura(v_id, RRHHWindow, **kwargs)
            elif v_id == "portal":
                from src.gui.portal_empleado import PortalEmpleadoWindow

                self.manejar_apertura(v_id, PortalEmpleadoWindow, **kwargs)
            elif v_id == "kardex":
                from src.gui.kardex_visor import KardexVisorWindow

                self.manejar_apertura(v_id, KardexVisorWindow, **kwargs)
            elif v_id == "tesoreria":
                from src.gui.tesoreria_gui import TesoreriaWindow

                self.manejar_apertura(v_id, TesoreriaWindow, **kwargs)
            elif v_id == "bi":
                # Centro de Inteligencia Empresarial (Enterprise Shell): Dashboard Ejecutivo +
                # Centro de Actividad + Gemelo + Predicción + Simulador. v_id "bi" se conserva por
                # compatibilidad (SaaS-gate, badges, cache de ventanas).
                from src.gui.inteligencia_gui import InteligenciaWindow

                self.manejar_apertura(v_id, InteligenciaWindow, **kwargs)
            elif v_id == "aeat":
                from src.gui.aeat_gui import AEATWindow

                self.manejar_apertura(v_id, AEATWindow, **kwargs)
            elif v_id == "seguridad":
                from src.gui.seguridad_gui import SeguridadWindow

                self.manejar_apertura(v_id, SeguridadWindow, **kwargs)
            elif v_id == "workflow":
                from src.gui.workflow_gui import WorkflowWindow

                self.manejar_apertura(v_id, WorkflowWindow, **kwargs)
            elif v_id == "notificaciones":
                # Fase 3: "Notificaciones" evoluciona al Centro de Actividad Empresarial
                # (timeline del Event Bus + panel de sincronizacion + historial).
                from src.gui.centro_actividad import CentroActividadWindow

                self.manejar_apertura(v_id, CentroActividadWindow, **kwargs)
            elif v_id == "saas":
                from src.gui.saas_admin import SaaSAdminWindow

                self.manejar_apertura(v_id, SaaSAdminWindow, **kwargs)
            elif v_id == "inventario_fisico":
                from src.gui.inventario_fisico import InventarioFisicoWindow

                self.manejar_apertura(v_id, InventarioFisicoWindow, **kwargs)
            elif v_id == "lotes":
                from src.gui.lotes_caducidades import LotesWindow

                self.manejar_apertura(v_id, LotesWindow, **kwargs)
            elif v_id == "stock_almacen":
                from src.gui.stock_almacen_gui import StockAlmacenWindow

                self.manejar_apertura(v_id, StockAlmacenWindow, **kwargs)
            elif v_id == "almacenes":
                from src.gui.almacenes_gui import AlmacenesWindow

                self.manejar_apertura(v_id, AlmacenesWindow, **kwargs)
            elif v_id == "calidad":
                from src.gui.calidad_dashboard import CalidadDashboardWindow

                self.manejar_apertura(v_id, CalidadDashboardWindow, **kwargs)
            elif v_id == "gmao":
                from src.gui.gmao_dashboard import GMAODashboardWindow

                self.manejar_apertura(v_id, GMAODashboardWindow, **kwargs)
            elif v_id == "proyectos":
                from src.gui.proyectos_gui import ProyectosWindow

                self.manejar_apertura(v_id, ProyectosWindow, **kwargs)
            elif v_id == "fiscal":
                from src.gui.fiscal_gui import FiscalWindow

                self.manejar_apertura(v_id, FiscalWindow, **kwargs)
            elif v_id == "contabilidad":
                from src.gui.contabilidad_gestion import ContabilidadWindow

                self.manejar_apertura(v_id, ContabilidadWindow, **kwargs)
            elif v_id == "tpv":
                from src.gui.tpv import TPVWindow

                self._abrir_tpv_en_stack(TPVWindow)

        except Exception as e:
            logger.error(f"Error al abrir {v_id}: {e}", exc_info=True)
            _msg = tr("menu.error_module", modulo=v_id)
            if mostrar_mensaje is not None:
                mostrar_mensaje(self, tr("menu.error_title"), _msg, nivel="error")
            else:
                QMessageBox.critical(self, tr("menu.error_title"), _msg)
            self.mostrar_menu_principal()

    def _abrir_tpv_en_stack(self, TPVWindow):
        """Abre el TPV dentro del QStackedWidget raíz (SmartManagerApp).

        Toda la lógica de caja / login ocurre DENTRO de TPVWindow para evitar
        mostrar diálogos desde un widget embebido en un QStackedWidget frameless,
        lo cual provoca que aparezcan invisibles en Windows.
        Si el login es cancelado, TPVWindow.auth_cancelled será True y no se
        muestra el TPV.
        """
        smart_app = self.parent()

        if smart_app is None or not hasattr(smart_app, "setCurrentWidget"):
            self.manejar_apertura(
                "tpv",
                TPVWindow,
                callback_vuelta=self.mostrar_menu_principal,
                usuario=sesion_global.usuario_actual,
            )
            return

        # Cerrar instancia anterior si existe
        viejo = self._ventanas.pop("tpv", None)
        if viejo is not None:
            try:
                smart_app.removeWidget(viejo)
                viejo.deleteLater()
            except Exception:
                pass

        def volver_de_tpv():
            instancia = self._ventanas.pop("tpv", None)
            if instancia is not None:
                try:
                    smart_app.removeWidget(instancia)
                    instancia.deleteLater()
                except Exception:
                    pass
            smart_app.setCurrentWidget(self)
            self.show()

        tpv = TPVWindow(
            callback_vuelta=volver_de_tpv,
            usuario=sesion_global.usuario_actual,
            main=self,
        )

        # Si el empleado canceló el login, no mostrar el TPV
        if getattr(tpv, "_auth_cancelled", False):
            try:
                tpv.deleteLater()
            except Exception:
                pass
            return

        self._ventanas["tpv"] = tpv
        smart_app.addWidget(tpv)
        self.hide()
        smart_app.setCurrentWidget(tpv)

    def manejar_apertura(self, identificador, clase_ventana, **kwargs):
        # Gate SaaS (P0.1/P0.3): el plan y el estado de pago restringen el acceso a módulos.
        # Legacy (sin licencia) → siempre permitido. El portal SaaS nunca se bloquea.
        try:
            from src.services.saas import enforcement as _enf

            permitido, motivo = _enf.acceso_modulo(identificador)
            if not permitido:
                try:
                    from PyQt6.QtWidgets import QMessageBox

                    QMessageBox.warning(self, "Suscripción", motivo)
                except Exception:
                    pass
                return
        except Exception as _e:
            logging.getLogger("menu").debug("gate saas: %s", _e)
        # Fase 3: abrir un modulo lo marca como ATENDIDO → su badge se pone a cero.
        try:
            from src.services import actividad
            actividad.marcar_visto(identificador, getattr(sesion_global, "usuario_actual", None))
        except Exception:
            pass
        try:
            if identificador in self._ventanas:
                v_antigua = self._ventanas.pop(identificador, None)
                if v_antigua is not None:
                    try:
                        v_antigua.close()
                    except Exception:
                        pass
                    try:
                        v_antigua.deleteLater()
                    except Exception:
                        pass

            self.hide()
            kwargs["main"] = self

            nueva_v = clase_ventana(**kwargs)
            self._ventanas[identificador] = nueva_v

            if hasattr(nueva_v, "showMaximized"):
                nueva_v.showMaximized()
            else:
                nueva_v.show()

            QApplication.processEvents()

            if identificador == "ubicacion" and hasattr(
                nueva_v, "_forzar_reencuadre_diferido"
            ):
                try:
                    nueva_v._forzar_reencuadre_diferido(force=True)
                except Exception:
                    pass

            logger.info(
                f"Navegación: Entrada a módulo {identificador} con Sincronización de Escena."
            )

        except Exception as e:
            logger.error(
                f"Error en manejar_apertura para {identificador}: {e}", exc_info=True
            )
            self.mostrar_menu_principal()

    def mostrar_menu_principal(self):
        # Al volver al menú se CIERRAN los módulos abiertos para no acumular
        # ventanas en la barra de tareas de Windows. El cierre se DIFIERE (singleShot)
        # porque este método suele invocarse desde el propio botón "Volver" de la
        # ventana: destruirla dentro de su manejador de evento sería inseguro.
        ventanas = [v for v in self._ventanas.values() if v is not None]
        self._ventanas = {}

        if ventanas:
            def _cerrar_diferido(_ventanas=ventanas):
                for v in _ventanas:
                    try:
                        v.close()
                    except Exception:
                        pass
                    try:
                        v.deleteLater()
                    except Exception:
                        pass
            QTimer.singleShot(0, _cerrar_diferido)

        self.showMaximized()
        self.raise_()
        self.activateWindow()
        QApplication.processEvents()
        logger.info("Navegación: Regreso al menú principal confirmado.")

    # ============================================================
    # MULTITIENDA (F1) — selector / cambio de tienda en caliente
    # ============================================================
    def _actualizar_chip_tienda(self):
        """Refresca el texto del chip de la barra superior: empresa + tienda/código."""
        if not getattr(self, "btn_tienda", None):
            return
        try:
            from src.db import empresa as _emp
            from src.db import tiendas as _t

            e = _emp.obtener_empresa(_emp.empresa_actual_id()) or {}
            nombre_emp = (
                e.get("nombre_comercial")
                or e.get("razon_social")
                or e.get("nombre_empresa")
                or e.get("codigo_empresa")
                or "—"
            )
            linea2 = _t.etiqueta_tienda_actual() or tr(
                "menu.sin_tienda", default="Sin tienda activa"
            )
            self.btn_tienda.setText(f"🏪  {nombre_emp}\n{linea2}")
        except Exception:
            pass

    def _abrir_selector_tienda(self):
        """Abre el selector de tienda; si se cambia, recarga el contexto."""
        try:
            from src.gui.selector_tienda import SelectorTiendaDialog

            dlg = SelectorTiendaDialog(self)
            dlg.exec()
            if dlg.get_resultado():
                self._recargar_contexto_tienda()
        except Exception as e:
            logger.error("Error al abrir el selector de tienda: %s", e, exc_info=True)

    def _recargar_contexto_tienda(self):
        """Tras cambiar de tienda: cierra los módulos abiertos (se reabrirán con el
        nuevo contexto) y refresca la barra superior."""
        for _v_id, v in list(self._ventanas.items()):
            try:
                v.close()
                v.deleteLater()
            except Exception:
                pass
        self._ventanas = {}
        self._actualizar_chip_tienda()
        self.showMaximized()
        self.raise_()
        self.activateWindow()

    def cerrar_ventana_activa(self) -> bool:
        """
        Closes any currently-open module window and returns to the menu.
        Used by SOMA's "cierra <módulo>" voice command.
        Returns True if a window was actually closed, False if none was open.
        """
        cerro_alguna = False
        for v_id, v_instancia in list(self._ventanas.items()):
            try:
                if v_instancia is not None and v_instancia.isVisible():
                    cerro_alguna = True
                    try:
                        v_instancia.close()
                    except Exception:
                        pass
                    try:
                        v_instancia.deleteLater()
                    except Exception:
                        pass
                    self._ventanas.pop(v_id, None)
            except Exception:
                continue
        self.mostrar_menu_principal()
        return cerro_alguna

    def abrir_gestion_caja(self, accion_inicial=None):
        """P4/P4.1 — Abre la Gestión de Caja en su VENTANA PROPIA (GestionCajaWindow),
        reutilizando la lógica de caja existente. accion_inicial (opcional) dispara
        directamente movimiento/cambio de cajero (acceso rápido desde el TPV)."""
        try:
            from src.gui.gestion_usuarios import GestionCajaWindow

            kwargs = {
                "callback_vuelta": self.mostrar_menu_principal,
                "usuario": sesion_global.usuario_actual,
            }
            if accion_inicial is not None:
                kwargs["accion_inicial"] = accion_inicial
            self.manejar_apertura("gestion_caja", GestionCajaWindow, **kwargs)
        except Exception as e:
            logger.error(f"Error al abrir Gestión de Caja: {e}", exc_info=True)
            self.mostrar_menu_principal()

    def abrir_modulo_configuracion(self, tab_inicial=None, accion_inicial=None):
        try:
            from src.gui.gestion_usuarios import ConfiguracionWindow

            kwargs = {
                "callback_vuelta": self.mostrar_menu_principal,
                "usuario": sesion_global.usuario_actual,
            }
            if tab_inicial is not None:
                kwargs["tab_inicial"] = tab_inicial
            if accion_inicial is not None:
                kwargs["accion_inicial"] = accion_inicial

            logger.info(
                f"Navegación: Usuario '{self.nombre_usuario}' entrando a CONFIGURACIÓN."
            )

            self.manejar_apertura("configuracion", ConfiguracionWindow, **kwargs)

        except Exception as e:
            logger.error(f"Error crítico al abrir Configuración: {e}", exc_info=True)
            _det = tr("menu.error_module", modulo="configuración") + f"\n{str(e)}"
            if mostrar_mensaje is not None:
                mostrar_mensaje(
                    self, tr("menu.error_module_title"), _det, nivel="error"
                )
            else:
                QMessageBox.critical(self, tr("menu.error_module_title"), _det)
            self.mostrar_menu_principal()

    # ============================================================
    # BLOQUE RECORDATORIO DE CITAS (notificación flotante)
    # ============================================================
    def _comprobar_citas_hoy(self):
        """Si hay eventos programados PARA HOY aún no vistos, muestra una
        notificación flotante. Solo el día del evento; nunca antes."""
        if getattr(self, "_citas_aviso_mostrado", False):
            return  # ya se mostró en esta sesión
        try:
            from src.utils import citas

            fecha, pendientes = citas.pendientes_hoy()
        except Exception as e:
            logger.debug("No se pudieron comprobar las citas de hoy: %s", e)
            return
        if not pendientes:
            return
        self._citas_aviso_mostrado = True
        self._mostrar_notif_citas(fecha, pendientes)

    def _mostrar_notif_citas(self, fecha, eventos):
        self._cerrar_notif_citas()
        card = QFrame(self)
        card.setObjectName("notifCita")
        card.setStyleSheet(
            "QFrame#notifCita{background:#0E1117;border:2px solid #00FFC6;border-radius:16px;}"
        )
        sombra = QGraphicsDropShadowEffect(card)
        sombra.setBlurRadius(45)
        sombra.setColor(QColor(0, 255, 198, 150))
        sombra.setOffset(0, 0)
        card.setGraphicsEffect(sombra)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(10)

        titulo = QLabel("📅  " + tr("menu.cita_titulo", default="RECORDATORIO DE HOY"))
        titulo.setStyleSheet(
            "color:#00FFC6;font-family:'Segoe UI';font-weight:900;font-size:16px;"
            "background:transparent;border:none;"
        )
        lay.addWidget(titulo)

        sub = QLabel(
            tr("menu.cita_sub", default="Tienes eventos programados para hoy:")
        )
        sub.setStyleSheet(
            "color:#8B949E;font-family:'Segoe UI';font-size:12px;font-weight:700;"
            "background:transparent;border:none;"
        )
        lay.addWidget(sub)

        for ev in eventos[:6]:
            asunto = ev.get("asunto", "")
            hi = (ev.get("hora_inicio") or "").strip()
            hf = (ev.get("hora_fin") or "").strip()
            horas = f"{hi} – {hf}" if (hi or hf) else ""
            txt = f"•  <b>{asunto}</b>"
            if horas:
                txt += f"&nbsp;&nbsp;<span style='color:#8B949E;'>{horas}</span>"
            linea = QLabel(txt)
            linea.setTextFormat(Qt.TextFormat.RichText)
            linea.setWordWrap(True)
            linea.setStyleSheet(
                "color:#E6EDF3;font-family:'Segoe UI';font-size:13px;"
                "background:transparent;border:none;"
            )
            lay.addWidget(linea)

        fila = QHBoxLayout()
        fila.setSpacing(10)
        fila.addStretch()
        btn_ent = QPushButton(tr("menu.cita_entendido", default="ENTENDIDO"))
        btn_ent.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ent.setFixedHeight(40)
        btn_ent.setStyleSheet(
            "QPushButton{background:#0E1117;color:#00FFC6;border:2px solid #00FFC6;"
            "border-radius:10px;font-weight:900;font-size:12px;padding:0 18px;}"
            "QPushButton:hover{background:#00FFC6;color:#0E1117;}"
        )
        btn_ent.clicked.connect(self._notif_entendido)
        btn_ver = QPushButton(tr("menu.cita_ver", default="VER CITA"))
        btn_ver.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ver.setFixedHeight(40)
        btn_ver.setStyleSheet(
            "QPushButton{background:#0E1117;color:#00FFC6;border:2px solid #00FFC6;"
            "border-radius:10px;font-weight:900;font-size:12px;padding:0 22px;}"
            "QPushButton:hover{background:#00FFC6;color:#0E1117;}"
        )
        btn_ver.clicked.connect(self._notif_ver_cita)
        fila.addWidget(btn_ent)
        fila.addWidget(btn_ver)
        lay.addLayout(fila)

        self._notif_cita_widget = card
        self._notif_cita_fecha = fecha
        self._notif_cita_eventos = eventos

        card.adjustSize()
        card.setFixedWidth(max(440, card.sizeHint().width()))
        self._posicionar_notif_citas()
        card.show()
        card.raise_()

    def _posicionar_notif_citas(self):
        card = getattr(self, "_notif_cita_widget", None)
        if not card:
            return
        x = (self.width() - card.width()) // 2
        card.move(max(20, x), 24)

    def _notif_entendido(self):
        """ENTENDIDO: marca los eventos como vistos para no volver a avisar."""
        try:
            from src.utils import citas

            citas.marcar_vistos(
                getattr(self, "_notif_cita_fecha", ""),
                getattr(self, "_notif_cita_eventos", []),
            )
        except Exception as e:
            logger.debug("No se pudo marcar la cita como vista: %s", e)
        self._cerrar_notif_citas()

    def _notif_ver_cita(self):
        """VER CITA: abre Configuración directamente en PLANIFICAR CITAS (índice 6)."""
        self._cerrar_notif_citas()
        self.abrir_modulo_configuracion(tab_inicial=6)

    def _cerrar_notif_citas(self):
        card = getattr(self, "_notif_cita_widget", None)
        if card is not None:
            card.hide()
            card.deleteLater()
            self._notif_cita_widget = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._posicionar_notif_citas()

    # ============================================================
    # BLOQUE ALERTAS Y CIERRE DE SESIÓN
    # ============================================================
    def verificar_stock_bajo(self):
        try:
            from src.main import verificar_reposicion_y_alertar

            verificar_reposicion_y_alertar(self)
        except Exception as e:
            logger.error(f"Error en alerta de stock: {e}")

    def _precargar_modulos_pesados(self):
        """Pre-importa los módulos pesados en un hilo de fondo durante el reposo
        del menú, para que su primera apertura no pague el coste de import
        (gestion_usuarios ~450 ms, recepcion_pale ~1200 ms por cv2/reportlab/etc.).
        Estos módulos solo definen clases e importan librerías (no crean objetos
        Qt a nivel de módulo), por lo que es seguro importarlos fuera del hilo
        principal; el import nativo libera el GIL y la UI sigue fluida."""
        import threading

        def _worker():
            for mod in ("src.gui.gestion_usuarios", "src.gui.recepcion_pale"):
                try:
                    __import__(mod)
                except Exception as e:
                    logger.debug(f"Pre-carga de {mod} omitida: {e}")

        try:
            threading.Thread(target=_worker, daemon=True, name="preloader").start()
        except Exception as e:
            logger.debug(f"No se pudo iniciar la pre-carga de módulos: {e}")

    def cerrar_sesion(self):
        _titulo = tr("menu.logout_title")
        _msg = tr("menu.logout_msg")
        if mostrar_confirmacion is not None:
            confirm = mostrar_confirmacion(self, _titulo, _msg)
        else:
            confirm = (
                QMessageBox.question(
                    self,
                    _titulo,
                    _msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                == QMessageBox.StandardButton.Yes
            )

        if confirm:
            logger.info(f"Cerrando sesión para el usuario: {self.nombre_usuario}")
            self._cerrar_recursos()
            sesion_global.cerrar_sesion()
            self.close()

    def _cerrar_recursos(self):
        if self._cerrando:
            return
        self._cerrando = True

        try:
            if hasattr(self, "timer_db") and self.timer_db is not None:
                self.timer_db.stop()
        except Exception:
            pass

        for v_id in list(self._ventanas.keys()):
            ventana = self._ventanas.get(v_id)
            if ventana is None:
                continue
            try:
                ventana.close()
            except Exception:
                pass
            try:
                ventana.deleteLater()
            except Exception:
                pass
        self._ventanas.clear()

    def closeEvent(self, event):
        self._cerrar_recursos()
        super().closeEvent(event)
