import logging
from PyQt6.QtWidgets import (
    QWidget,
    QMessageBox,
    QApplication,
    QVBoxLayout,
    QLabel,
    QGridLayout,
    QGraphicsDropShadowEffect,
    QFrame,
    QHBoxLayout,
    QToolButton,
)
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon, QPixmap, QPainter
from PyQt6.QtCore import Qt, QTimer, QSize, QByteArray
from PyQt6.QtSvg import QSvgRenderer

# Importaciones de negocio y datos
from src.db.usuario import sesion_global
from src.db.conexion import obtener_conexion

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


# =========================================================
# TARJETAS DEL MENÚ PRINCIPAL
# =========================================================
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


# =========================================================
# MENÚ PRINCIPAL
# =========================================================
class MenuPrincipal(QWidget):
    def __init__(self):
        super().__init__()

        usuario_actual = getattr(sesion_global, "usuario_actual", None) or {}
        raw_perfil = usuario_actual.get("perfil", "OPERARIO")
        self.perfil = str(raw_perfil).strip().upper()
        self.nombre_usuario = sesion_global.obtener_nombre() or "USUARIO"

        self.setWindowTitle(f"Smart Manager AI - [{self.perfil}]")
        self.setObjectName("panel_raiz")
        self._ventanas = {}
        self._cerrando = False

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

    # =========================================================
    # CONSTRUCCIÓN DE INTERFAZ
    # =========================================================
    def setup_ui(self):
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#0B1118"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 18, 30, 20)
        main_layout.setSpacing(10)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        self.db_status_led = QLabel("● DB")
        self.db_status_led.setFont(QFont("Segoe UI", 10, QFont.Weight.Black))
        self.db_status_led.setStyleSheet(
            """
            color: gray;
            background: transparent;
            border: none;
            letter-spacing: 1px;
            """
        )
        top_bar.addWidget(self.db_status_led)
        top_bar.addStretch()

        user_info = QLabel(f"👤 {self.nombre_usuario.upper()} | {self.perfil}")
        user_info.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        user_info.setStyleSheet(
            """
            color: #00FFC6;
            background: transparent;
            border: none;
            letter-spacing: 1px;
            """
        )
        top_bar.addWidget(user_info)
        main_layout.addLayout(top_bar)

        header_container = QFrame()
        header_container.setStyleSheet("background: transparent; border: none;")
        header_layout = QVBoxLayout(header_container)
        header_layout.setContentsMargins(0, 4, 0, 0)
        header_layout.setSpacing(4)

        title = QLabel("SMART MANAGER AI")
        title.setObjectName("titulo_principal")
        title.setFont(QFont("Segoe UI", 32, QFont.Weight.Black))
        title.setStyleSheet(
            """
            color: white;
            border: none;
            background: transparent;
            letter-spacing: 4px;
            """
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("CENTRO DE CONTROL LOGÍSTICO")
        subtitle.setObjectName("subtitulo_principal")
        subtitle.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        subtitle.setStyleSheet(
            """
            color: #00FFC6;
            border: none;
            background: transparent;
            letter-spacing: 2px;
            """
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        main_layout.addWidget(header_container)

        menu_container = QFrame()
        menu_container.setStyleSheet("background: transparent; border: none;")
        menu_layout = QVBoxLayout(menu_container)
        menu_layout.setContentsMargins(0, 10, 0, 0)
        menu_layout.setSpacing(18)

        grid_container = QFrame()
        grid_container.setStyleSheet("background: transparent; border: none;")
        grid_layout = QGridLayout(grid_container)
        grid_layout.setHorizontalSpacing(22)
        grid_layout.setVerticalSpacing(20)
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
            if solo_admin and v_id == "ventas" and self.perfil not in ["ADMINISTRADOR", "GERENTE"]:
                tiene_acceso = False

            if tiene_acceso:
                btn = self.crear_tarjeta_menu(texto, v_id, color, icon_key)
                grid_layout.addWidget(btn, fila, col, alignment=Qt.AlignmentFlag.AlignCenter)
            else:
                self.crear_bloqueo_visual(grid_layout, fila, col)

        menu_layout.addWidget(grid_container, alignment=Qt.AlignmentFlag.AlignCenter)

        footer_actions = QHBoxLayout()
        footer_actions.setContentsMargins(0, 0, 0, 0)
        footer_actions.setSpacing(0)

        if self.perfil == "ADMINISTRADOR":
            btn_usuarios = self.crear_tarjeta_menu("Usuarios", "usuarios", "#F1E55B", "gear")
            footer_actions.addWidget(btn_usuarios, alignment=Qt.AlignmentFlag.AlignLeft)
        else:
            footer_actions.addSpacing(210)

        footer_actions.addStretch()

        btn_salir = self.crear_tarjeta_menu("Salir", "logout", "#FF5C70", "logout")
        footer_actions.addWidget(btn_salir, alignment=Qt.AlignmentFlag.AlignRight)

        menu_layout.addLayout(footer_actions)
        main_layout.addWidget(menu_container, alignment=Qt.AlignmentFlag.AlignCenter)
        main_layout.addStretch()

        version_lbl = QLabel("v2.4.0 - Powered by Smart Manager AI")
        version_lbl.setStyleSheet(
            """
            color: #425061;
            font-size: 10px;
            font-weight: 800;
            border: none;
            background: transparent;
            """
        )
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

    # =========================================================
    # CREACIÓN DE BOTONES E ICONOS
    # =========================================================
    def crear_tarjeta_menu(self, texto, v_id, color, icon_key):
        icono_normal = self.crear_icono(icon_key, color)
        icono_hover = self.crear_icono(icon_key, "#0B1118")
        btn = MenuCardButton(texto, icono_normal, icono_hover, color=color, parent=self)

        if v_id == "logout":
            btn.clicked.connect(self.cerrar_sesion)
        elif v_id == "usuarios":
            btn.clicked.connect(self.abrir_gestion_usuarios)
        else:
            btn.clicked.connect(lambda _, id_w=v_id: self.abrir_ventana_por_id(id_w))

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
        lock_container.setStyleSheet(
            """
            background-color: rgba(20, 28, 36, 0.90);
            border: 1px dashed #3E4C5C;
            border-radius: 28px;
            """
        )

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

        lbl = QLabel("🔒\nRESTRINGIDO")
        lbl.setStyleSheet(
            """
            color: #667586;
            font-weight: 900;
            font-size: 16px;
            border: none;
            background: transparent;
            """
        )
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l_layout.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lock_container, fila, col, alignment=Qt.AlignmentFlag.AlignCenter)

    # =========================================================
    # ESTADO DE CONEXIÓN
    # =========================================================
    def actualizar_estado_db(self):
        try:
            with obtener_conexion() as conn:
                self.db_status_led.setText("● ONLINE")
                self.db_status_led.setStyleSheet(
                    """
                    color: #00FF7A;
                    font-weight: 900;
                    margin-right: 15px;
                    background: transparent;
                    border: none;
                    """
                )
        except Exception:
            self.db_status_led.setText("● OFFLINE")
            self.db_status_led.setStyleSheet(
                """
                color: #FF5C70;
                font-weight: 900;
                margin-right: 15px;
                background: transparent;
                border: none;
                """
            )

    # =========================================================
    # APERTURA DE MÓDULOS
    # =========================================================
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
                from src.gui.ventas import VentasWindow
                self.manejar_apertura(v_id, VentasWindow, **kwargs)
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

        except Exception as e:
            logger.error(f"Error al abrir {v_id}: {e}", exc_info=True)
            if mostrar_mensaje is not None:
                mostrar_mensaje(
                    self, "Error", f"No se pudo cargar el módulo {v_id}", nivel="error"
                )
            else:
                QMessageBox.critical(self, "Error", f"No se pudo cargar el módulo {v_id}")
            self.mostrar_menu_principal()

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

            if identificador == "ubicacion" and hasattr(nueva_v, "_forzar_reencuadre_diferido"):
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

    def abrir_gestion_usuarios(self):
        try:
            from src.gui.gestion_usuarios import GestionUsuariosView

            kwargs = {
                "callback_vuelta": self.mostrar_menu_principal,
                "usuario": sesion_global.usuario_actual,
            }

            logger.info(
                f"Navegación: Usuario '{self.nombre_usuario}' solicitando acceso a Gestión de Usuarios."
            )

            self.manejar_apertura("usuarios", GestionUsuariosView, **kwargs)

        except Exception as e:
            logger.error(
                f"Error crítico al abrir gestión de usuarios: {e}", exc_info=True
            )
            if mostrar_mensaje is not None:
                mostrar_mensaje(
                    self,
                    "Error de Módulo",
                    f"No se pudo cargar el panel de usuarios.\nDetalle: {str(e)}",
                    nivel="error",
                )
            else:
                QMessageBox.critical(
                    self,
                    "Error de Módulo",
                    f"No se pudo cargar el panel de usuarios.\nDetalle: {str(e)}",
                )
            self.mostrar_menu_principal()

    # =========================================================
    # ALERTAS Y CIERRE DE SESIÓN
    # =========================================================
    def verificar_stock_bajo(self):
        try:
            from src.main import verificar_reposicion_y_alertar
            verificar_reposicion_y_alertar(self)
        except Exception as e:
            logger.error(f"Error en alerta de stock: {e}")

    def cerrar_sesion(self):
        if mostrar_confirmacion is not None:
            confirm = mostrar_confirmacion(
                self,
                "Cerrar Sesión",
                "¿Desea salir del sistema?",
            )
        else:
            confirm = (
                QMessageBox.question(
                    self,
                    "Cerrar Sesión",
                    "¿Desea salir del sistema?",
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

