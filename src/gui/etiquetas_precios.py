import os
from datetime import datetime

from src.utils import divisas

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from reportlab.graphics.barcode import code128
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from assets.estilo_global import (
    repolish_widget,
)
from src.db.conexion import obtener_conexion
from src.utils import i18n
from src.utils.i18n import tr

# ---------------------------------------------------------------------------
# CONSTANTES Y ESTILOS
# ---------------------------------------------------------------------------
_CIAN = "#00FFC6"
_FONDO = "#0E1117"
_PANEL_BG = "#161B22"
_BORDE = "#30363D"

_NEON_INPUT_SS = f"""
QLineEdit {{
    background-color: #161B22;
    color: #FFFFFF;
    border: 2px solid {_CIAN};
    border-radius: 12px;
    padding: 12px 20px;
    font-size: 16px;
    font-family: 'Segoe UI';
    font-weight: bold;
}}
QLineEdit:focus {{
    border: 2px solid {_CIAN};
    background-color: #1A2230;
}}
"""

_BTN_CIAN_SS = f"""
QPushButton {{
    background-color: #0E1117;
    color: {_CIAN};
    font-weight: bold;
    border-radius: 14px;
    padding: 12px 24px;
    font-size: 13px;
    font-family: 'Segoe UI';
    border: 2px solid {_CIAN};
}}
QPushButton:hover {{
    background-color: {_CIAN};
    color: #0E1117;
    border: 2px solid {_CIAN};
}}
"""

# ---------------------------------------------------------------------------
# COMPONENTES DE INTERFAZ
# ---------------------------------------------------------------------------


class _SidebarBtn(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("btn_sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedHeight(55)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: #FFFFFF;
                border: none;
                border-left: 4px solid transparent;
                border-radius: 0px;
                font-size: 12px;
                font-family: 'Segoe UI';
                font-weight: 900;
                text-align: left;
                padding-left: 28px;
            }}
            QPushButton:hover {{
                background-color: #FFFFFF;
                color: #0E1117;
            }}
            QPushButton:checked {{
                background-color: #1A2230;
                border-left: 4px solid {_CIAN};
                color: {_CIAN};
            }}
        """)

    def enterEvent(self, event):
        super().enterEvent(event)
        repolish_widget(self)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        repolish_widget(self)


def _sombra_cian(widget):
    fx = QGraphicsDropShadowEffect()
    fx.setBlurRadius(22)
    fx.setColor(QColor(_CIAN))
    fx.setOffset(0)
    widget.setGraphicsEffect(fx)


# ---------------------------------------------------------------------------
# MOTOR DE ETIQUETAS (Lógica de estilo profesional)
# ---------------------------------------------------------------------------
class GeneradorEtiquetas:
    TAMANOS = {
        "40x26": (40, 26),
        "65x35": (65, 35),
        "70x35": (70, 35),
        "95x35": (95, 35),
        "100x70": (100, 70),
        "148x70": (148, 70),
    }

    @staticmethod
    def generar(codigo, nombre, precio, formato="70x35"):
        w_mm, h_mm = GeneradorEtiquetas.TAMANOS.get(formato, (70, 35))

        folder = os.path.join(os.getcwd(), "documentos", "etiquetas")
        os.makedirs(folder, exist_ok=True)

        filename = f"ETQ_{codigo}_{datetime.now().strftime('%H%M%S')}.pdf"
        path = os.path.join(folder, filename)

        c = canvas.Canvas(path, pagesize=(w_mm * mm, h_mm * mm))

        # Fondo blanco limpio
        c.setFillColor(colors.white)
        c.rect(0, 0, w_mm * mm, h_mm * mm, fill=1)

        # Nombre del producto (Arriba)
        c.setFont("Helvetica-Bold", 10 if h_mm < 30 else 14)
        c.setFillColor(colors.black)
        c.drawString(4 * mm, (h_mm - 8) * mm, nombre[:30].upper())

        # Precio destacado (Centro-Derecha)
        precio_str = f"{divisas.formatear(float(precio))}"
        c.setFont("Helvetica-Bold", 24 if h_mm < 40 else 42)
        c.drawRightString((w_mm - 5) * mm, (h_mm / 2 - 4) * mm, precio_str)

        # Código de barras (Abajo)
        try:
            bc = code128.Code128(
                str(codigo), barHeight=5 * mm if h_mm < 30 else 10 * mm, barWidth=0.4
            )
            bc.drawOn(c, 4 * mm, 3 * mm)
        except:
            pass

        c.setFont("Helvetica", 7)
        c.drawString(4 * mm, 1 * mm, f"REF: {codigo}")

        c.save()
        return path


# ---------------------------------------------------------------------------
# PÁGINAS DE CONTENIDO
# ---------------------------------------------------------------------------


class _CambiarPrecioPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(30)

        layout.addStretch(1)
        lbl_icon = QLabel("🏷️")  # Icono de etiqueta
        lbl_icon.setStyleSheet("font-size: 160px;")
        lbl_icon.setFixedHeight(200)  # Aumentado para evitar recorte
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(20)  # Espacio adicional entre icono y siguiente elemento
        layout.addWidget(lbl_icon)

        self._lbl_tit = QLabel(tr("etiq.price_title", default="GESTIÓN DE PRECIOS"))
        self._lbl_tit.setStyleSheet(f"color: {_CIAN}; font-size: 24px; font-weight: bold;")
        self._lbl_tit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._lbl_tit)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(
            tr("etiq.search_ph", default="Introduce código o nombre del artículo...")
        )
        self.search_bar.setStyleSheet(_NEON_INPUT_SS)
        self.search_bar.setMinimumWidth(280); self.search_bar.setMaximumWidth(560)  # responsive (P2)
        self.search_bar.returnPressed.connect(self._buscar_y_editar)
        layout.addWidget(self.search_bar, alignment=Qt.AlignmentFlag.AlignCenter)

        self._btn_buscar = QPushButton(tr("etiq.search_btn", default="BUSCAR ARTÍCULO"))
        self._btn_buscar.setStyleSheet(_BTN_CIAN_SS)
        self._btn_buscar.setFixedSize(220, 55)
        self._btn_buscar.clicked.connect(self._buscar_y_editar)
        _sombra_cian(self._btn_buscar)
        layout.addWidget(self._btn_buscar, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch(1)

    def _retraducir(self):
        self._lbl_tit.setText(tr("etiq.price_title", default="GESTIÓN DE PRECIOS"))
        self.search_bar.setPlaceholderText(
            tr("etiq.search_ph", default="Introduce código o nombre del artículo...")
        )
        self._btn_buscar.setText(tr("etiq.search_btn", default="BUSCAR ARTÍCULO"))

    def _buscar_y_editar(self):
        termino = self.search_bar.text().strip()
        if not termino:
            return

        try:
            with obtener_conexion() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT codigo, nombre, precio FROM articulos WHERE codigo=%s OR nombre LIKE %s",
                    (termino, f"%{termino}%"),
                )
                res = cur.fetchone()

            if res:
                self._abrir_dialogo_edicion(res[0], res[1], res[2])
            else:
                QMessageBox.warning(
                    self,
                    tr("etiq.not_found_title", default="No encontrado"),
                    tr("etiq.not_found_msg",
                       default="No se encontró el artículo: {termino}", termino=termino),
                )
        except Exception as e:
            print(f"Error búsqueda: {e}")

    def _abrir_dialogo_edicion(self, codigo, nombre, precio_actual):
        diag = QDialog(self)
        diag.setWindowTitle(tr("etiq.update_title", default="Actualizar Precio"))
        diag.setFixedWidth(400)
        diag.setStyleSheet(
            f"background-color: {_PANEL_BG}; border: 1px solid {_BORDE}; border-radius: 15px;"
        )

        ly = QVBoxLayout(diag)
        ly.setContentsMargins(25, 25, 25, 25)
        ly.setSpacing(15)

        lbl_n = QLabel(nombre.upper())
        lbl_n.setStyleSheet(
            "color: white; font-size: 16px; font-weight: bold; border:none;"
        )
        lbl_n.setWordWrap(True)

        lbl_p = QLabel(
            tr("etiq.current_price", default="Precio Actual: {precio}",
               precio=divisas.formatear(float(precio_actual)))
        )
        lbl_p.setStyleSheet("color: #8B949E; font-size: 13px; border:none;")

        self.inp_new = QLineEdit()
        self.inp_new.setPlaceholderText(
            tr("etiq.new_price_ph", default="Nuevo precio (ej: 12.50)")
        )
        self.inp_new.setStyleSheet(_NEON_INPUT_SS.replace("500", "300"))

        ly.addWidget(lbl_n)
        ly.addWidget(lbl_p)
        ly.addWidget(
            QLabel(
                tr("etiq.new_price_lbl", default="NUEVO PRECIO:"),
                styleSheet="color: white; font-size: 11px; border:none;",
            )
        )
        ly.addWidget(self.inp_new)

        # Selector de tamaño
        self.combo_size = QComboBox()
        self.combo_size.addItems(
            ["70x35", "40x26", "65x35", "95x35", "100x70", "148x70"]
        )
        self.combo_size.setStyleSheet(
            "background: #0D1117; color: white; padding: 8px; border-radius: 8px;"
        )
        ly.addWidget(
            QLabel(
                tr("etiq.size_lbl", default="TAMAÑO ETIQUETA:"),
                styleSheet="color: white; font-size: 11px; border:none;",
            )
        )
        ly.addWidget(self.combo_size)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton(tr("etiq.ok", default="ACEPTAR"))
        btn_ok.setStyleSheet(_BTN_CIAN_SS)
        btn_ok.clicked.connect(diag.accept)

        btn_can = QPushButton(tr("etiq.cancel", default="CANCELAR"))
        btn_can.setStyleSheet(
            "background: #30363D; color: white; padding: 10px; border-radius: 10px;"
        )
        btn_can.clicked.connect(diag.reject)

        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_can)
        ly.addLayout(btn_row)

        if diag.exec() == QDialog.DialogCode.Accepted:
            try:
                nuevo_p = float(self.inp_new.text().replace(",", "."))
                with obtener_conexion() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE articulos SET precio=%s WHERE codigo=%s",
                        (nuevo_p, codigo),
                    )
                    conn.commit()

                # Generar etiqueta automáticamente
                GeneradorEtiquetas.generar(
                    codigo, nombre, nuevo_p, self.combo_size.currentText()
                )

                QMessageBox.information(
                    self,
                    tr("etiq.success_title", default="Éxito"),
                    tr("etiq.success_msg",
                       default="Precio actualizado y etiqueta generada en /documentos/etiquetas"),
                )
                self.search_bar.clear()
            except ValueError:
                QMessageBox.critical(
                    self,
                    tr("etiq.error_title", default="Error"),
                    tr("etiq.invalid_price", default="Introduce un precio válido."),
                )


class _CarpetaEtiquetasPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(25)

        layout.addStretch(1)
        lbl_icon = QLabel("📂")  # Icono de carpeta
        lbl_icon.setStyleSheet("font-size: 160px;")
        lbl_icon.setFixedHeight(200)  # Aumentado para evitar recorte
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(20)  # Espacio adicional entre icono y siguiente elemento
        layout.addWidget(lbl_icon)

        self._btn = QPushButton(tr("etiq.open_folder_btn", default="ABRIR CARPETA DE ETIQUETAS"))
        self._btn.setStyleSheet(_BTN_CIAN_SS)
        self._btn.setMinimumSize(220, 60); self._btn.setMaximumWidth(360)  # responsive (P2)
        self._btn.clicked.connect(self._abrir)
        _sombra_cian(self._btn)
        layout.addWidget(self._btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)

    def _retraducir(self):
        self._btn.setText(tr("etiq.open_folder_btn", default="ABRIR CARPETA DE ETIQUETAS"))

    def _abrir(self):
        path = os.path.join(os.getcwd(), "documentos", "etiquetas")
        os.makedirs(path, exist_ok=True)
        os.startfile(path)


class _PreciosNuevosPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(25)

        layout.addStretch(1)
        lbl_icon = QLabel("☁️")  # Icono de nube
        lbl_icon.setStyleSheet("font-size: 160px;")
        lbl_icon.setFixedHeight(200)  # Aumentado para evitar recorte
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(20)  # Espacio adicional entre icono y siguiente elemento
        layout.addWidget(lbl_icon)

        self._btn = QPushButton(tr("etiq.view_new_btn", default="VER PRECIOS NUEVOS (CENTRAL)"))
        self._btn.setStyleSheet(_BTN_CIAN_SS)
        self._btn.setMinimumSize(220, 60); self._btn.setMaximumWidth(360)  # responsive (P2)
        self._btn.clicked.connect(self._abrir_nube)
        _sombra_cian(self._btn)
        layout.addWidget(self._btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)

    def _retraducir(self):
        self._btn.setText(tr("etiq.view_new_btn", default="VER PRECIOS NUEVOS (CENTRAL)"))

    def _abrir_nube(self):
        import webbrowser

        webbrowser.open("https://drive.google.com")  # Ajustar a ruta real


class _PromocionesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(25)

        layout.addStretch(1)
        lbl_icon = QLabel("🎁")  # Icono de regalo
        lbl_icon.setStyleSheet("font-size: 160px;")
        lbl_icon.setFixedHeight(200)  # Aumentado para evitar recorte
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(20)  # Espacio adicional entre icono y siguiente elemento
        layout.addWidget(lbl_icon)

        self._btn = QPushButton(tr("etiq.view_promo_btn", default="VER PROMOCIONES / OFERTAS"))
        self._btn.setStyleSheet(_BTN_CIAN_SS)
        self._btn.setMinimumSize(220, 60); self._btn.setMaximumWidth(360)  # responsive (P2)
        self._btn.clicked.connect(self._abrir_promos)
        _sombra_cian(self._btn)
        layout.addWidget(self._btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)

    def _retraducir(self):
        self._btn.setText(tr("etiq.view_promo_btn", default="VER PROMOCIONES / OFERTAS"))

    def _abrir_promos(self):
        import webbrowser

        webbrowser.open("https://drive.google.com")  # Ajustar a ruta real


# ---------------------------------------------------------------------------
# VENTANA PRINCIPAL (REESTRUCTURADA)
# ---------------------------------------------------------------------------
class EtiquetasPreciosWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, **kwargs):
        super().__init__()
        self.callback_vuelta = callback_vuelta
        self.usuario_actual = usuario

        self.setWindowTitle(tr("etiq.window_title", default="Etiquetas de Precio"))
        self.setMinimumSize(1024, 680)  # responsive (P2): apto tablet (antes 1100x750)
        self.setStyleSheet(f"background-color: {_FONDO}; color: white;")

        self.setup_ui()
        i18n.conectar_retraduccion(self, self._retraducir)

        # P3 (UX-TPV-01): sidebar colapsable con persistencia por usuario.
        try:
            from src.gui.sidebar_colapsable import instalar_sidebar_colapsable
            if getattr(self, "sidebar", None) is not None:
                instalar_sidebar_colapsable(self, self.sidebar, usuario=self.usuario_actual, clave="etiquetas")
        except Exception:
            pass

    def setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- SIDEBAR ----
        sidebar = QFrame()
        self.sidebar = sidebar  # P3: referencia para el toggle colapsable
        sidebar.setFixedWidth(280)
        sidebar.setStyleSheet(
            f"background-color: {_PANEL_BG}; border-right: 1px solid {_BORDE};"
        )

        side_ly = QVBoxLayout(sidebar)
        side_ly.setContentsMargins(0, 40, 0, 20)
        side_ly.setSpacing(0)

        lbl_m = QLabel(tr("etiq.smart_tags", default="SMART TAGS"))
        lbl_m.setStyleSheet(
            "color: #ffffff; font-size: 16px; font-weight: 900; margin-left: 30px; "
            "margin-bottom: 35px; letter-spacing: 2px; border: none; background: transparent;"
        )
        side_ly.addWidget(lbl_m)

        self._tab_keys = ["etiq.tab_price", "etiq.tab_folder", "etiq.tab_new", "etiq.tab_promo"]
        _tab_def = ["CAMBIAR PRECIO", "CARPETA ETIQUETAS", "AJUSTE DE PRECIOS", "PROMOCIONES / OFERTAS"]

        self._nav_btns = []
        for idx, key in enumerate(self._tab_keys):
            btn = _SidebarBtn(tr(key, default=_tab_def[idx]))
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.clicked.connect(lambda _, i=idx: self._ir_a(i))
            side_ly.addWidget(btn)
            self._nav_btns.append(btn)

        side_ly.addStretch()

        self._btn_exit = btn_exit = _SidebarBtn(tr("etiq.exit", default="SALIR AL MENÚ"))
        btn_exit.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #F85149;
                border: none;
                border-left: 4px solid transparent;
                border-radius: 0px;
                font-size: 12px;
                font-family: 'Segoe UI';
                font-weight: 900;
                text-align: left;
                padding-left: 28px;
            }
            QPushButton:hover {
                background-color: #F85149;
                color: #0E1117;
            }
        """)
        btn_exit.clicked.connect(self.volver_menu_principal)
        side_ly.addWidget(btn_exit)

        root.addWidget(sidebar)

        # ---- CONTENT AREA ----
        self._vistas = QStackedWidget()
        self._page_precio = _CambiarPrecioPage()
        self._page_folder = _CarpetaEtiquetasPage()
        self._page_cloud = _PreciosNuevosPage()
        self._page_promo = _PromocionesPage()

        for p in (
            self._page_precio,
            self._page_folder,
            self._page_cloud,
            self._page_promo,
        ):
            self._vistas.addWidget(p)

        root.addWidget(self._vistas)
        self._ir_a(0)

    def _retraducir(self):
        self.setWindowTitle(tr("etiq.window_title", default="Etiquetas de Precio"))
        _tab_def = ["CAMBIAR PRECIO", "CARPETA ETIQUETAS", "AJUSTE DE PRECIOS", "PROMOCIONES / OFERTAS"]
        for i, btn in enumerate(self._nav_btns):
            btn.setText(tr(self._tab_keys[i], default=_tab_def[i]))
        self._btn_exit.setText(tr("etiq.exit", default="SALIR AL MENÚ"))
        for page in (self._page_precio, self._page_folder, self._page_cloud, self._page_promo):
            if hasattr(page, "_retraducir"):
                page._retraducir()

    def _ir_a(self, index):
        self._vistas.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_btns):
            btn.setChecked(i == index)
            repolish_widget(btn)

    def volver_menu_principal(self):
        if self.callback_vuelta:
            self.callback_vuelta()
        self.close()
