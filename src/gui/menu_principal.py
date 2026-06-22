import logging
import os

from PyQt6.QtCore import QByteArray, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPixmap
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

from src.db.conexion import obtener_conexion, obtener_referencias

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
        "inactivo":    ("#1e2530", "#4a5568", "SOMA"),
        "escuchando":  ("#0d2a2a", "#00FFC6", "SOMA ●"),
        "activado":    ("#00FFC6", "#001a15", "SOMA ◉"),
        "procesando":  ("#2a1a00", "#ffaa00", "SOMA ···"),
        "error":       ("#2a0000", "#ff4444", "SOMA ✕"),
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
    def __init__(self, texto, icono_normal, icono_hover, color="#00FFC6", parent=None):
        super().__init__(parent)
        self.color = color
        self._icono_normal = icono_normal
        self._icono_hover = icono_hover

        self.setText(texto)
        self.setIcon(self._icono_normal)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(82, 82))
        self.setFixedSize(210, 170)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(QFont("Segoe UI", 14, QFont.Weight.Black))
        self.setStyleSheet(self._build_style(color))
        self._aplicar_glow(color)

    def _build_style(self, color):
        return f"""
            QToolButton {{
                background-color: rgba(25, 34, 44, 0.88);
                color: #F3F6F9;
                border: 1px solid rgba(0, 255, 198, 0.10);
                border-radius: 28px;
                padding: 12px 12px 12px 12px;
                text-align: center;
                font-family: 'Segoe UI';
                font-size: 14px;
                font-weight: 900;
            }}
            QToolButton:hover {{
                background-color: {color};
                color: #0B1118;
                border: 1px solid {color};
            }}
            QToolButton:pressed {{
                background-color: {color};
                color: #0B1118;
                border: 1px solid {color};
                padding-top: 15px;
            }}
        """

    def _aplicar_glow(self, color):
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(18)
        glow.setColor(QColor(color))
        glow.setOffset(0, 0)
        self.setGraphicsEffect(glow)

    def enterEvent(self, event):
        self.setIcon(self._icono_hover)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(self._icono_normal)
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
        self._cards = {}          # v_id -> MenuCardButton
        self._lock_lbls = []      # etiquetas de tarjetas bloqueadas

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

    # ============================================================
    # BLOQUE CONSTRUCCIÓN DE INTERFAZ
    # ============================================================
    def setup_ui(self):
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#0B1118"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 4, 30, 6)
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
        self.logo_label.setFixedHeight(108)
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
                "QPushButton:hover{background:#11312B;}")
            self.btn_tienda.clicked.connect(self._abrir_selector_tienda)
            left_hbox.addWidget(self.btn_tienda, 0, Qt.AlignmentFlag.AlignVCenter)
            self._actualizar_chip_tienda()
        left_hbox.addStretch()

        top_bar.addWidget(left_panel, 1)   # stretch=1 → mirrors right side

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
            tr("menu.user_info", nombre=self.nombre_usuario.upper(),
               perfil=self._perfil_traducido())
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

        top_bar.addWidget(right_panel, 1)  # stretch=1 → mirrors left side

        main_layout.addLayout(top_bar)

        menu_container = QFrame()
        menu_container.setStyleSheet("background: transparent; border: none;")
        menu_layout = QVBoxLayout(menu_container)
        menu_layout.setContentsMargins(0, 2, 0, 0)
        menu_layout.setSpacing(10)

        grid_container = QFrame()
        grid_container.setStyleSheet("background: transparent; border: none;")
        grid_layout = QGridLayout(grid_container)
        grid_layout.setHorizontalSpacing(22)
        grid_layout.setVerticalSpacing(14)
        grid_layout.setContentsMargins(0, 0, 0, 0)

        botones_principales = [
            ("Recepción", "logistica", 0, 0, False, "#22F4E6", "truck"),
            ("Stock", "stock", 0, 1, False, "#22F4E6", "box"),
            ("Ubicación", "ubicacion", 0, 2, False, "#22F4E6", "search"),
            ("Artículo", "info", 0, 3, False, "#22F4E6", "document"),
            ("Mermas", "mermas", 1, 0, False, "#22F4E6", "trash"),
            ("Etiquetas", "etiquetas", 1, 1, False, "#22F4E6", "tag"),
            ("Reposición", "reposicion", 1, 2, False, "#22F4E6", "bar_chart"),
            ("Ventas", "ventas", 1, 3, True, "#22F4E6", "line_chart"),
        ]

        for texto, v_id, fila, col, solo_admin, color, icon_key in botones_principales:
            tiene_acceso = True
            if (
                solo_admin
                and v_id == "ventas"
                and self.perfil not in ["ADMINISTRADOR", "GERENTE"]
            ):
                tiene_acceso = False

            if tiene_acceso:
                btn = self.crear_tarjeta_menu(texto, v_id, color, icon_key)
                grid_layout.addWidget(
                    btn, fila, col, alignment=Qt.AlignmentFlag.AlignCenter
                )
            else:
                self.crear_bloqueo_visual(grid_layout, fila, col)

        menu_layout.addWidget(grid_container, alignment=Qt.AlignmentFlag.AlignCenter)

        footer_actions = QHBoxLayout()
        footer_actions.setContentsMargins(0, 0, 0, 0)
        footer_actions.setSpacing(0)

        if self.perfil == "ADMINISTRADOR":
            btn_config = self.crear_tarjeta_menu(
                "Configuración", "configuracion", "#F1E55B", "gear"
            )
            footer_actions.addWidget(btn_config, alignment=Qt.AlignmentFlag.AlignLeft)
        else:
            footer_actions.addSpacing(210)

        # Correo corporativo (multiempresa) — solo ADMINISTRADOR / GERENTE.
        if self.perfil in ("ADMINISTRADOR", "GERENTE"):
            btn_correo = self.crear_tarjeta_menu("Correo", "correo", "#22F4E6", "mail")
            footer_actions.addWidget(btn_correo, alignment=Qt.AlignmentFlag.AlignLeft)

        # Centro documental unificado — ADMINISTRADOR / GERENTE (incluye SUPERADMIN).
        if self.perfil in ("ADMINISTRADOR", "GERENTE", "SUPERADMIN"):
            btn_docs = self.crear_tarjeta_menu("Documentos", "documentos", "#22F4E6", "document")
            footer_actions.addWidget(btn_docs, alignment=Qt.AlignmentFlag.AlignLeft)

        # Gestión del catálogo online — ADMINISTRADOR / GERENTE / SUPERADMIN.
        if self.perfil in ("ADMINISTRADOR", "GERENTE", "SUPERADMIN"):
            btn_cat = self.crear_tarjeta_menu("Catálogo", "catalogo", "#22F4E6", "shopping_bag")
            footer_actions.addWidget(btn_cat, alignment=Qt.AlignmentFlag.AlignLeft)

        # Compras y proveedores — ADMINISTRADOR / GERENTE / SUPERADMIN (back-office).
        if self.perfil in ("ADMINISTRADOR", "GERENTE", "SUPERADMIN"):
            btn_compras = self.crear_tarjeta_menu("Compras", "compras", "#22F4E6", "truck")
            footer_actions.addWidget(btn_compras, alignment=Qt.AlignmentFlag.AlignLeft)
            btn_compras_av = self.crear_tarjeta_menu("Compras avanzado", "compras_avanzado",
                                                     "#22F4E6", "truck")
            footer_actions.addWidget(btn_compras_av, alignment=Qt.AlignmentFlag.AlignLeft)
            btn_clientes = self.crear_tarjeta_menu("Clientes", "clientes_crm", "#22F4E6", "people")
            footer_actions.addWidget(btn_clientes, alignment=Qt.AlignmentFlag.AlignLeft)

        # Contabilidad — ADMINISTRADOR / GERENTE / SUPERADMIN (control financiero).
        if self.perfil in ("ADMINISTRADOR", "GERENTE", "SUPERADMIN"):
            btn_contab = self.crear_tarjeta_menu("Contabilidad", "contabilidad", "#22F4E6", "bar_chart")
            footer_actions.addWidget(btn_contab, alignment=Qt.AlignmentFlag.AlignLeft)

            # Tesorería / Bancos / SEPA — control financiero operativo.
            btn_tes = self.crear_tarjeta_menu("Tesorería", "tesoreria", "#22F4E6", "bar_chart")
            footer_actions.addWidget(btn_tes, alignment=Qt.AlignmentFlag.AlignLeft)

        # RRHH — ADMINISTRADOR / GERENTE / SUPERADMIN (expediente y empleados).
        if self.perfil in ("ADMINISTRADOR", "GERENTE", "SUPERADMIN"):
            btn_rrhh = self.crear_tarjeta_menu("RRHH", "rrhh", "#22F4E6", "people")
            footer_actions.addWidget(btn_rrhh, alignment=Qt.AlignmentFlag.AlignLeft)

        # Portal del Empleado — disponible para cualquier perfil (autoconsulta).
        btn_portal = self.crear_tarjeta_menu("Portal del empleado", "portal", "#22F4E6", "people")
        footer_actions.addWidget(btn_portal, alignment=Qt.AlignmentFlag.AlignLeft)

        # Kárdex de inventario — ADMINISTRADOR / GERENTE / SUPERADMIN.
        if self.perfil in ("ADMINISTRADOR", "GERENTE", "SUPERADMIN"):
            btn_kardex = self.crear_tarjeta_menu("Kárdex", "kardex", "#22F4E6", "box")
            footer_actions.addWidget(btn_kardex, alignment=Qt.AlignmentFlag.AlignLeft)
            btn_invf = self.crear_tarjeta_menu("Inventario físico", "inventario_fisico",
                                               "#22F4E6", "box")
            footer_actions.addWidget(btn_invf, alignment=Qt.AlignmentFlag.AlignLeft)
            btn_lotes = self.crear_tarjeta_menu("Lotes", "lotes", "#22F4E6", "box")
            footer_actions.addWidget(btn_lotes, alignment=Qt.AlignmentFlag.AlignLeft)
            btn_alm = self.crear_tarjeta_menu("Stock por almacén", "stock_almacen", "#22F4E6", "box")
            footer_actions.addWidget(btn_alm, alignment=Qt.AlignmentFlag.AlignLeft)
            btn_gesalm = self.crear_tarjeta_menu("Almacenes", "almacenes", "#22F4E6", "box")
            footer_actions.addWidget(btn_gesalm, alignment=Qt.AlignmentFlag.AlignLeft)

        footer_actions.addStretch()

        btn_tpv = self.crear_tarjeta_menu("TPV", "tpv", "#22F4E6", "shopping_bag")
        footer_actions.addWidget(btn_tpv, alignment=Qt.AlignmentFlag.AlignCenter)

        footer_actions.addStretch()

        btn_salir = self.crear_tarjeta_menu("Salir", "logout", "#FF5C70", "logout")
        footer_actions.addWidget(btn_salir, alignment=Qt.AlignmentFlag.AlignRight)

        menu_layout.addLayout(footer_actions)
        main_layout.addWidget(menu_container, alignment=Qt.AlignmentFlag.AlignCenter)
        main_layout.addStretch()

        self._version_lbl = version_lbl = QLabel(f"v2.4.0 - {tr('menu.powered_by')}")
        version_lbl.setStyleSheet("""
            color: #425061;
            font-size: 10px;
            font-weight: 800;
            border: none;
            background: transparent;
            """)
        main_layout.addWidget(version_lbl, alignment=Qt.AlignmentFlag.AlignRight)

        self._aplicar_refuerzo_global()

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
                    tr("menu.user_info",
                       nombre=self.nombre_usuario.upper(), perfil=self._perfil_traducido())
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

    def crear_tarjeta_menu(self, texto, v_id, color, icon_key):
        icono_normal = self.crear_icono(icon_key, color)
        icono_hover = self.crear_icono(icon_key, "#0B1118")
        key = self._MENU_CARD_KEYS.get(v_id)
        display = tr(key) if key else texto
        btn = MenuCardButton(display, icono_normal, icono_hover, color=color, parent=self)

        if v_id == "logout":
            btn.clicked.connect(self.cerrar_sesion)
        elif v_id == "configuracion":
            btn.clicked.connect(self.abrir_modulo_configuracion)
        else:
            btn.clicked.connect(lambda _, id_w=v_id: self.abrir_ventana_por_id(id_w))

        # Registro para re-traducción en caliente.
        self._cards[v_id] = btn
        return btn

    def crear_icono(self, icon_key, color):
        svg_map = {
            "truck": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">
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
                  <g fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M64 18l34 18-34 18-34-18 34-18z"/>
                    <path d="M30 36v38l34 18 34-18V36"/>
                    <path d="M64 54v38"/>
                    <path d="M47 27l34 18"/>
                  </g>
                </svg>
            """,
            "people": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="48" cy="44" r="16"/>
                    <path d="M22 96c0-16 12-26 26-26s26 10 26 26"/>
                    <circle cx="88" cy="50" r="12"/>
                    <path d="M84 72c12 0 22 9 22 24"/>
                  </g>
                </svg>
            """,
            "search": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="54" cy="54" r="26"/>
                    <path d="M74 74l24 24"/>
                  </g>
                </svg>
            """,
            "document": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M38 20h34l18 18v58a8 8 0 0 1-8 8H38a8 8 0 0 1-8-8V28a8 8 0 0 1 8-8z"/>
                    <path d="M72 20v18h18"/>
                    <path d="M46 56h28M46 70h28M46 84h20"/>
                  </g>
                </svg>
            """,
            "trash": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M42 32h44"/>
                    <path d="M50 32v-8h28v8"/>
                    <rect x="38" y="38" width="52" height="56" rx="8"/>
                    <path d="M54 50v30M64 50v30M74 50v30"/>
                  </g>
                </svg>
            """,
            "tag": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M28 58V34a8 8 0 0 1 8-8h24l40 40a10 10 0 0 1 0 14L78 102a10 10 0 0 1-14 0L28 66a11 11 0 0 1 0-8z"/>
                    <circle cx="48" cy="46" r="4"/>
                  </g>
                </svg>
            """,
            "bar_chart": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">
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
                  <g fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">
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
                  <g fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="64" cy="64" r="12"/>
                    <path d="M64 24v10M64 94v10M24 64h10M94 64h10"/>
                    <path d="M36 36l7 7M85 85l7 7M92 36l-7 7M43 85l-7 7"/>
                    <circle cx="64" cy="64" r="28"/>
                  </g>
                </svg>
            """,
            "logout": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M52 28H34a8 8 0 0 0-8 8v56a8 8 0 0 0 8 8h18"/>
                    <path d="M68 44l24 20-24 20"/>
                    <path d="M40 64h50"/>
                  </g>
                </svg>
            """,
            "shopping_bag": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 46h84l-10 66H32L22 46z"/>
                    <path d="M46 46c0-14 8-24 18-24s18 10 18 24"/>
                  </g>
                </svg>
            """,
            "mail": f"""
                <svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
                  <g fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="20" y="32" width="88" height="64" rx="8"/>
                    <path d="M24 38l40 30 40-30"/>
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
        lock_container.setFixedSize(210, 170)
        lock_container.setStyleSheet("""
            background-color: rgba(20, 28, 36, 0.90);
            border: 1px dashed #3E4C5C;
            border-radius: 28px;
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
        try:
            with obtener_conexion() as conn:
                self._actualizar_ref_label()
        except Exception:
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
                scaled = pix.scaledToHeight(64, Qt.TransformationMode.SmoothTransformation)
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
            refs = obtener_referencias()
            partes = []
            if refs.get("ref_tienda"):
                partes.append(f"T-{refs['ref_tienda']}")
            if refs.get("ref_almacen"):
                partes.append(f"A-{refs['ref_almacen']}")
            if partes:
                self.ref_label.setText("  ·  ".join(partes))
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
                from src.gui.clientes_gui import ClientesWindow

                self.manejar_apertura(v_id, ClientesWindow, **kwargs)
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
            self.manejar_apertura("tpv", TPVWindow,
                                  callback_vuelta=self.mostrar_menu_principal,
                                  usuario=sesion_global.usuario_actual)
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
        v_activas = {}
        for v_id, v_instancia in list(self._ventanas.items()):
            try:
                if v_instancia is not None and v_instancia.isVisible():
                    v_activas[v_id] = v_instancia
            except Exception:
                continue
        self._ventanas = v_activas

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
            nombre_emp = (e.get("nombre_comercial") or e.get("razon_social")
                          or e.get("nombre_empresa") or e.get("codigo_empresa") or "—")
            linea2 = _t.etiqueta_tienda_actual() or tr("menu.sin_tienda", default="Sin tienda activa")
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
                v.close(); v.deleteLater()
            except Exception:
                pass
        self._ventanas = {}
        self._actualizar_chip_tienda()
        self.showMaximized(); self.raise_(); self.activateWindow()

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

    def abrir_modulo_configuracion(self, tab_inicial=None):
        try:
            from src.gui.gestion_usuarios import ConfiguracionWindow

            kwargs = {
                "callback_vuelta": self.mostrar_menu_principal,
                "usuario": sesion_global.usuario_actual,
            }
            if tab_inicial is not None:
                kwargs["tab_inicial"] = tab_inicial

            logger.info(
                f"Navegación: Usuario '{self.nombre_usuario}' entrando a CONFIGURACIÓN."
            )

            self.manejar_apertura("configuracion", ConfiguracionWindow, **kwargs)

        except Exception as e:
            logger.error(f"Error crítico al abrir Configuración: {e}", exc_info=True)
            _det = tr("menu.error_module", modulo="configuración") + f"\n{str(e)}"
            if mostrar_mensaje is not None:
                mostrar_mensaje(self, tr("menu.error_module_title"), _det, nivel="error")
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

        sub = QLabel(tr("menu.cita_sub", default="Tienes eventos programados para hoy:"))
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
