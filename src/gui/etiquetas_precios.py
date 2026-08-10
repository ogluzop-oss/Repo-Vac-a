import json
import logging
import os
from datetime import datetime

from src.utils import divisas

logger = logging.getLogger("gui.etiquetas")

from PyQt6.QtCore import Qt, QStringListModel, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from reportlab.graphics.barcode import code128
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from assets.estilo_global import (
    construir_tabla_estilizada,
    estilizar_completer,
    mostrar_mensaje,
    repolish_widget,
)
from src.db.conexion import obtener_conexion
from src.gui.iconos_neon import BotonMas
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

    # Tipos de etiqueta: color del marco/banda y rótulo. "normal" = blanco (aspecto actual).
    TIPOS = {
        "normal":   {"color": "#111111", "banda": None,       "rotulo": None},
        "rebajado": {"color": "#F5871F", "banda": "#F5871F",  "rotulo": "REBAJADO"},
        "nuevo":    {"color": "#2FBF71", "banda": "#2FBF71",  "rotulo": "NUEVO"},
    }

    @staticmethod
    def generar(codigo, nombre, precio, formato="70x35", tipo="normal"):
        w_mm, h_mm = GeneradorEtiquetas.TAMANOS.get(formato, (70, 35))
        cfg_tipo = GeneradorEtiquetas.TIPOS.get(tipo, GeneradorEtiquetas.TIPOS["normal"])

        folder = os.path.join(os.getcwd(), "documentos", "etiquetas")
        os.makedirs(folder, exist_ok=True)

        filename = f"ETQ_{codigo}_{datetime.now().strftime('%H%M%S')}.pdf"
        path = os.path.join(folder, filename)

        W, H = w_mm * mm, h_mm * mm
        c = canvas.Canvas(path, pagesize=(W, H))

        grande = h_mm >= 55          # 100x70 · 148x70
        peque = h_mm < 30            # 40x26
        pad = 3.2 * mm

        # Fondo blanco + marco redondeado (color según el tipo de etiqueta).
        c.setFillColor(colors.white); c.rect(0, 0, W, H, fill=1, stroke=0)
        inset = 1.3 * mm
        _es_normal = cfg_tipo.get("rotulo") is None
        c.setStrokeColor(colors.HexColor(cfg_tipo["color"]))
        c.setLineWidth(1.1 if _es_normal else 2.2)
        c.roundRect(inset, inset, W - 2 * inset, H - 2 * inset,
                    min(3 * mm, H * 0.09), stroke=1, fill=0)

        # Rótulo de tipo (REBAJADO / NUEVO): pastilla de color en la esquina superior derecha.
        if cfg_tipo.get("banda") and cfg_tipo.get("rotulo"):
            fs_tag = 8 if h_mm >= 55 else (5 if h_mm < 30 else 6.5)
            tag = cfg_tipo["rotulo"]
            tag_pad = 1.6 * mm
            tag_w = c.stringWidth(tag, "Helvetica-Bold", fs_tag) + 2 * tag_pad
            tag_h = fs_tag * 0.9 + 1.4 * mm
            tag_x = W - inset - 1.1 * mm - tag_w
            tag_y = H - inset - 1.1 * mm - tag_h
            c.setFillColor(colors.HexColor(cfg_tipo["banda"]))
            c.roundRect(tag_x, tag_y, tag_w, tag_h, tag_h * 0.35, stroke=0, fill=1)
            c.setFillColor(colors.white); c.setFont("Helvetica-Bold", fs_tag)
            c.drawString(tag_x + tag_pad, tag_y + (tag_h - fs_tag * 0.72) / 2, tag)

        # ── Nombre del producto (arriba, izq.) — truncado al ancho disponible ──
        fs_nom = 16 if grande else (8 if peque else 11)
        nom = (nombre or "").upper()
        max_w = W - 2 * pad
        while nom and c.stringWidth(nom, "Helvetica-Bold", fs_nom) > max_w:
            nom = nom[:-1]
        c.setFillColor(colors.black); c.setFont("Helvetica-Bold", fs_nom)
        nom_baseline = H - inset - pad * 0.6 - fs_nom * 0.8
        c.drawString(pad, nom_baseline, nom)

        # ── Separador fino ──
        sep_y = nom_baseline - fs_nom * 0.45
        c.setLineWidth(0.7); c.setStrokeColor(colors.HexColor("#CCCCCC"))
        c.line(pad, sep_y, W - pad, sep_y)

        # ── Código de barras (abajo, izq.) + REF debajo ──
        bc_h = (13 if grande else (4.5 if peque else 6.5)) * mm
        bar_w = 0.5 if grande else (0.3 if peque else 0.38)
        fs_ref = 9 if grande else (5.5 if peque else 6.5)
        ref_baseline = inset + 1.6 * mm
        bc_y = ref_baseline + fs_ref * 0.5 + 1.0 * mm
        try:
            bc = code128.Code128(str(codigo), barHeight=bc_h, barWidth=bar_w)
            bc.drawOn(c, pad, bc_y)
        except Exception:
            pass
        c.setFillColor(colors.HexColor("#333333")); c.setFont("Helvetica", fs_ref)
        c.drawString(pad, ref_baseline, f"REF: {codigo}")

        # ── Precio destacado (derecha, banda media) ──
        precio_str = divisas.formatear(float(precio))
        fs_precio = 42 if grande else (18 if peque else 28)
        ancho_max = W - 2 * pad - 2.5 * mm          # margen extra para que el símbolo no roce el marco
        while fs_precio > 8 and c.stringWidth(precio_str, "Helvetica-Bold", fs_precio) > ancho_max:
            fs_precio -= 1
        zona_top, zona_bot = sep_y, bc_y + bc_h
        precio_baseline = (zona_top + zona_bot) / 2 - fs_precio * 0.34
        c.setFillColor(colors.black); c.setFont("Helvetica-Bold", fs_precio)
        c.drawRightString(W - pad - 1.5 * mm, precio_baseline, precio_str)

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
        # Sugerencias de artículos al escribir (igual que en "Registrar merma").
        self._completer_model = QStringListModel()
        completer = QCompleter(self._completer_model, self.search_bar)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.search_bar.setCompleter(completer)
        estilizar_completer(completer)
        self.search_bar.textChanged.connect(self._on_search_text_changed)
        layout.addWidget(self.search_bar, alignment=Qt.AlignmentFlag.AlignCenter)
        self._cargar_completer()

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

    def _cargar_completer(self):
        try:
            from src.db.conexion import _get_todos_articulos_para_completer
            articulos = _get_todos_articulos_para_completer()
            self._completer_model.setStringList([f"{c} – {n}" for c, n in articulos])
        except Exception:
            pass

    def _on_search_text_changed(self, text):
        if len(text) >= 2 and not self._completer_model.stringList():
            self._cargar_completer()

    def cargar_datos(self):
        """Refresca el autocompletado al entrar en la pestaña."""
        self._cargar_completer()

    def _buscar_y_editar(self):
        termino = self.search_bar.text().strip()
        # Extrae el código del formato "CÓDIGO – NOMBRE" del autocompletado.
        if "–" in termino:
            termino = termino.split("–")[0].strip()
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
                mostrar_mensaje(
                    self,
                    tr("etiq.not_found_title", default="No encontrado"),
                    tr("etiq.not_found_msg",
                       default="No se encontró el artículo: {termino}", termino=termino),
                    nivel="warning",
                )
        except Exception as e:
            print(f"Error búsqueda: {e}")

    def _abrir_dialogo_edicion(self, codigo, nombre, precio_actual):
        diag = QDialog(self)
        diag.setWindowTitle(tr("etiq.update_title", default="Actualizar Precio"))
        diag.setFixedWidth(420)
        # Sin barra de Windows + contorno neón con esquinas redondeadas.
        diag.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        diag.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        outer = QVBoxLayout(diag)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            f"QFrame#card{{background-color:{_PANEL_BG};border:2px solid {_CIAN};"
            f"border-radius:16px;}}"
        )
        outer.addWidget(card)

        ly = QVBoxLayout(card)
        ly.setContentsMargins(25, 25, 25, 25)
        ly.setSpacing(15)

        lbl_n = QLabel(nombre.upper())
        lbl_n.setStyleSheet(
            "color: white; font-size: 16px; font-weight: bold; border:none; background: transparent;"
        )
        lbl_n.setWordWrap(True)

        lbl_p = QLabel(
            tr("etiq.current_price", default="Precio Actual: {precio}",
               precio=divisas.formatear(float(precio_actual)))
        )
        lbl_p.setStyleSheet("color: #8B949E; font-size: 13px; border:none; background: transparent;")

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
                styleSheet="color: white; font-size: 11px; border:none; background: transparent;",
            )
        )
        ly.addWidget(self.inp_new)

        # Selector de TIPO de etiqueta (color): normal (blanco) · rebajado (naranja) · nuevo (verde).
        self.combo_tipo = QComboBox()
        self._tipo_keys = ["normal", "rebajado", "nuevo"]
        self.combo_tipo.addItem(tr("etiq.type_normal", default="Precio normal (blanco)"), "normal")
        self.combo_tipo.addItem(tr("etiq.type_sale", default="Precio rebajado (naranja)"), "rebajado")
        self.combo_tipo.addItem(tr("etiq.type_new", default="Artículo nuevo (verde)"), "nuevo")
        self.combo_tipo.setStyleSheet(
            "background: #0D1117; color: white; padding: 8px; border-radius: 8px;"
        )
        ly.addWidget(
            QLabel(
                tr("etiq.type_lbl", default="TIPO ETIQUETA:"),
                styleSheet="color: white; font-size: 11px; border:none; background: transparent;",
            )
        )
        ly.addWidget(self.combo_tipo)

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
                styleSheet="color: white; font-size: 11px; border:none; background: transparent;",
            )
        )
        ly.addWidget(self.combo_size)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton(tr("etiq.ok", default="ACEPTAR"))
        btn_ok.setStyleSheet(_BTN_CIAN_SS)
        btn_ok.clicked.connect(diag.accept)

        btn_can = QPushButton(tr("etiq.cancel", default="CANCELAR"))
        btn_can.setStyleSheet(
            "QPushButton { background: #30363D; color: white; padding: 10px; border-radius: 10px; "
            "font-weight: bold; border: 2px solid #30363D; }"
            "QPushButton:hover { background: #F85149; color: #0E1117; border: 2px solid #F85149; }"
        )
        btn_can.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_can.clicked.connect(diag.reject)

        # CANCELAR a la izquierda, ACEPTAR a la derecha (posiciones intercambiadas).
        btn_row.addWidget(btn_can)
        btn_row.addWidget(btn_ok)
        ly.addLayout(btn_row)

        # CENTRAR el diálogo sobre la ventana principal: al ser frameless/translúcido, el
        # gestor de ventanas lo dejaba fuera de vista y la app parecía congelada (se cerraba
        # con ESC). Se recoloca en cuanto se muestra, dentro del bucle de exec().
        def _centrar():
            try:
                win = self.window()
                geo = diag.frameGeometry()
                geo.moveCenter(win.mapToGlobal(win.rect().center()))
                diag.move(geo.topLeft())
                diag.raise_(); diag.activateWindow()
            except Exception:
                pass
        QTimer.singleShot(0, _centrar)
        self.inp_new.setFocus()

        if diag.exec() != QDialog.DialogCode.Accepted:
            return
        # Validación del precio (mensaje no bloqueante, no cierra la app).
        try:
            nuevo_p = float((self.inp_new.text() or "").replace(",", ".").strip())
            if nuevo_p < 0:
                raise ValueError
        except ValueError:
            mostrar_mensaje(self, tr("etiq.error_title", default="Error"),
                            tr("etiq.invalid_price", default="Introduce un precio válido."),
                            nivel="warning")
            return
        try:
            try:                                     # PK compuesta (migr 0181): filtra por empresa de la sesión
                from src.db.empresa import empresa_actual_id as _eai
                _emp = _eai()
            except Exception:
                _emp = None
            with obtener_conexion() as conn:
                cur = conn.cursor()
                cur.execute("UPDATE articulos SET precio=%s WHERE codigo=%s AND (%s IS NULL OR id_empresa=%s)",
                            (nuevo_p, codigo, _emp, _emp))
                conn.commit()
            # Etiqueta generada con el PRECIO NUEVO ya confirmado y el TIPO (color) elegido.
            _tipo_sel = self.combo_tipo.currentData() or "normal"
            ruta = GeneradorEtiquetas.generar(codigo, nombre, nuevo_p,
                                              self.combo_size.currentText(), tipo=_tipo_sel)
            try:
                from src.db.documentos import registrar_documento
                registrar_documento(ruta, tipo="etiqueta",
                                    nombre=os.path.basename(ruta), referencia=str(codigo))
            except Exception:
                pass
            # Fase 1 (motor de eventos): publicacion OBSERVACIONAL, aditiva y bulletproof.
            try:
                from src.services import eventos as _EV
                _EV.publicar("PRECIO_ACTUALIZADO", origen="etiquetas",
                             ref_entidad="articulo", ref_id=codigo,
                             payload={"codigo": codigo, "nombre": nombre, "precio": nuevo_p})
            except Exception:
                pass
            self.search_bar.clear()
            mostrar_mensaje(
                self, tr("etiq.success_title", default="Éxito"),
                tr("etiq.success_msg2",
                   default="Precio actualizado a {p}. Etiqueta generada en /documentos/etiquetas.",
                   p=divisas.formatear(nuevo_p)),
                nivel="success")
        except Exception as e:
            logger.error("actualizar precio/etiqueta: %s", e)
            mostrar_mensaje(self, tr("etiq.error_title", default="Error"),
                            tr("etiq.save_error", default="No se pudo actualizar el precio."),
                            nivel="error")


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
        from src.utils import plataforma
        plataforma.abrir_carpeta(path)


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
_COMBO_SS = f"""
QComboBox {{ background:{_PANEL_BG}; color:#FFFFFF; border:2px solid {_CIAN}; border-radius:10px;
    padding:8px 12px; font-size:13px; font-weight:bold; }}
QComboBox::drop-down {{ border:none; width:22px; }}
QComboBox QAbstractItemView {{ background:{_PANEL_BG}; color:#FFFFFF; border:1px solid {_CIAN};
    selection-background-color:{_CIAN}; selection-color:#0E1117; }}
"""

_TABLA_SS = f"""
QTableWidget {{ background:{_PANEL_BG}; color:#FFFFFF; border:1px solid {_BORDE}; border-radius:12px;
    gridline-color:{_BORDE}; font-size:13px; }}
QTableWidget::item {{ padding:6px 8px; }}
QTableWidget::item:selected {{ background:#1A2230; color:{_CIAN}; }}
QHeaderView::section {{ background:#0E1117; color:#8B949E; font-weight:900; border:none;
    border-bottom:1px solid {_BORDE}; padding:8px; }}
"""

_ESTADO_COLOR = {"ACTUALIZADA": "#2ECC71", "PENDIENTE": "#F5A623", "ERROR": "#F85149"}

# Cabecera estándar de la app (misma que Smart Stock): barra continua, texto cian, hover de celda completa,
# esquinas superiores redondeadas. Se usa junto a `construir_tabla_estilizada` (contorno neón + redondeo).
_HEADER_STD_SS = f"""
QTableWidget {{ border:none; background-color:transparent; outline:none; }}
QHeaderView {{ background-color:transparent; border:none; }}
QHeaderView::section {{ background-color:#1A1D23; color:{_CIAN}; border:none; padding:10px; font-weight:900; }}
QHeaderView::section:hover {{ background-color:{_CIAN}; color:#0E1117; }}
QHeaderView::section:first {{ border-top-left-radius:18px; }}
QHeaderView::section:last {{ border-top-right-radius:18px; }}
"""

# Checkbox coherente con el tema (fondo transparente + indicador CIAN). Un setStyleSheet parcial rompe el
# estilo global del indicador y cae al render nativo (verde en Windows); por eso se define completo.
_CHECK_SS = f"""
QCheckBox {{ background: transparent; color:#FFFFFF; font-weight:bold; spacing:10px; border:none; }}
QCheckBox::indicator {{ width:18px; height:18px; border-radius:9px; }}
QCheckBox::indicator:unchecked {{ border:1px solid {_BORDE}; background:{_PANEL_BG}; }}
QCheckBox::indicator:checked {{ border:1px solid {_CIAN}; background:{_CIAN}; }}
"""


def _articulos_completer():
    """Sugerencias 'CÓDIGO – NOMBRE' para vincular etiquetas."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo, nombre FROM articulos ORDER BY nombre")
            return [f"{str(c or '').strip()} – {str(n or '').strip()}".strip(" –")
                    for c, n in cur.fetchall()]
    except Exception:
        return []


class _ESLConfigDialog(QDialog):
    """Configuración del proveedor ESL (esl.admin). La credencial se guarda cifrada; nunca se muestra."""

    _PROVEEDORES = ["simulado", "rest_generico", "imagotag", "solum", "pricer", "hanshow"]

    def __init__(self, parent=None, cfg=None):
        super().__init__(parent)
        cfg = cfg or {}
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(500)

        main_lyt = QVBoxLayout(self)
        cont = QFrame()
        cont.setStyleSheet(f"""
            QFrame {{ background-color: {_PANEL_BG}; border: 2px solid {_CIAN}; border-radius: 15px; }}
            QLabel {{ color: white; border: none; font-family: 'Segoe UI'; font-weight: bold; }}
        """)
        main_lyt.addWidget(cont)
        ly = QVBoxLayout(cont); ly.setContentsMargins(30, 30, 30, 30); ly.setSpacing(12)

        lbl_t = QLabel(tr("esl.cfg_title", default="CONFIGURACIÓN ESL"))
        lbl_t.setStyleSheet(f"color:{_CIAN};font-size:15px;font-weight:900;border:none;")
        ly.addWidget(lbl_t)

        ly.addWidget(QLabel(tr("esl.cfg_prov", default="PROVEEDOR:")))
        self.cmb_prov = QComboBox(); self.cmb_prov.setStyleSheet(_COMBO_SS)
        self.cmb_prov.addItems(self._PROVEEDORES)
        prov = (cfg.get("proveedor") or "simulado")
        if prov in self._PROVEEDORES:
            self.cmb_prov.setCurrentText(prov)
        ly.addWidget(self.cmb_prov)

        ly.addWidget(QLabel(tr("esl.cfg_endpoint", default="ENDPOINT (URL de la API del proveedor):")))
        self.in_endpoint = QLineEdit(cfg.get("endpoint") or ""); self.in_endpoint.setStyleSheet(_NEON_INPUT_SS)
        self.in_endpoint.setPlaceholderText("https://api.proveedor.com/v1")
        ly.addWidget(self.in_endpoint)

        ly.addWidget(QLabel(tr("esl.cfg_store", default="STORE ID (identificador de la tienda):")))
        self.in_store = QLineEdit(cfg.get("store_id") or ""); self.in_store.setStyleSheet(_NEON_INPUT_SS)
        ly.addWidget(self.in_store)

        cred_lbl = tr("esl.cfg_cred", default="CREDENCIAL / API KEY:")
        if cfg.get("tiene_credencial"):
            cred_lbl += tr("esl.cfg_cred_set", default="  (ya guardada — deja en blanco para conservarla)")
        ly.addWidget(QLabel(cred_lbl))
        self.in_cred = QLineEdit(); self.in_cred.setStyleSheet(_NEON_INPUT_SS)
        self.in_cred.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_cred.setPlaceholderText("••••••••")
        ly.addWidget(self.in_cred)

        self.chk_sim = QCheckBox(tr("esl.cfg_sim", default="Modo simulado (sin enviar a etiquetas reales)"))
        self.chk_sim.setStyleSheet(_CHECK_SS)
        self.chk_sim.setChecked(bool(cfg.get("modo_simulado", 1)))
        ly.addWidget(self.chk_sim)

        btn_lyt = QHBoxLayout()
        btn_ok = QPushButton(tr("esl.save", default="GUARDAR")); btn_ok.setStyleSheet(_BTN_CIAN_SS)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor); btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton(tr("etiq.cancel", default="CANCELAR"))
        btn_cancel.setStyleSheet("background-color:#30363D;color:white;border-radius:10px;padding:10px;font-weight:bold;")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor); btn_cancel.clicked.connect(self.reject)
        btn_lyt.addWidget(btn_ok); btn_lyt.addWidget(btn_cancel)
        ly.addLayout(btn_lyt)

    def datos(self):
        return {
            "proveedor": self.cmb_prov.currentText(),
            "endpoint": self.in_endpoint.text().strip() or None,
            "store_id": self.in_store.text().strip() or None,
            "credencial": self.in_cred.text().strip() or None,
            "modo_simulado": self.chk_sim.isChecked(),
        }


class _EtiquetasElectronicasPage(QWidget):
    """Panel operativo de etiquetas electrónicas (ESL): vincular, ver estado, sincronizar (push MANUAL),
    localizar y configurar. Solo orquesta; toda la lógica vive en services/esl."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self._cargado = False

        root = QVBoxLayout(self); root.setContentsMargins(24, 24, 24, 16); root.setSpacing(14)

        # ── cabecera ──
        cab = QHBoxLayout()
        self._lbl_t = QLabel(tr("esl.title", default="ETIQUETAS ELECTRÓNICAS"))
        self._lbl_t.setStyleSheet(f"color:{_CIAN};font-size:18px;font-weight:900;")
        cab.addWidget(self._lbl_t)
        self._lbl_modo = QLabel("")
        self._lbl_modo.setStyleSheet("color:#8B949E;font-size:12px;font-weight:bold;")
        cab.addSpacing(12); cab.addWidget(self._lbl_modo)
        cab.addStretch()
        self._btn_cfg = QPushButton("⚙  " + tr("esl.config", default="CONFIGURAR"))
        self._btn_cfg.setStyleSheet(_BTN_CIAN_SS); self._btn_cfg.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cfg.clicked.connect(self._configurar)
        cab.addWidget(self._btn_cfg)
        root.addLayout(cab)

        # ── alta (vincular) ──
        alta = QHBoxLayout(); alta.setSpacing(10)
        self.in_cod = QLineEdit(); self.in_cod.setStyleSheet(_NEON_INPUT_SS); self.in_cod.setFixedHeight(44)
        self.in_cod.setPlaceholderText(tr("esl.art_ph", default="Código o nombre del artículo…"))
        comp = QCompleter(); mdl = QStringListModel(); comp.setModel(mdl)
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        comp.setFilterMode(Qt.MatchFlag.MatchContains)
        if estilizar_completer:
            estilizar_completer(comp)
        mdl.setStringList(_articulos_completer()); self.in_cod.setCompleter(comp)
        self.in_label = QLineEdit(); self.in_label.setStyleSheet(_NEON_INPUT_SS); self.in_label.setFixedHeight(44)
        self.in_label.setPlaceholderText(tr("esl.label_ph", default="ID de la etiqueta…"))
        self.in_label.setMaximumWidth(240)
        self.in_label.returnPressed.connect(self._vincular)
        self._btn_vinc = QPushButton("🔗 " + tr("esl.link", default="VINCULAR"))
        self._btn_vinc.setStyleSheet(_BTN_CIAN_SS); self._btn_vinc.setFixedHeight(44)
        self._btn_vinc.setCursor(Qt.CursorShape.PointingHandCursor); self._btn_vinc.clicked.connect(self._vincular)
        alta.addWidget(self.in_cod, 1); alta.addWidget(self.in_label); alta.addWidget(self._btn_vinc)
        root.addLayout(alta)

        # ── barra de acciones ──
        tb = QHBoxLayout(); tb.setSpacing(10)
        self._btn_refrescar = QPushButton("🔄 " + tr("esl.refresh", default="ACTUALIZAR"))
        self._btn_sync = QPushButton("⬆ " + tr("esl.sync", default="SINCRONIZAR PENDIENTES"))
        self._btn_loc = QPushButton("📍 " + tr("esl.locate", default="LOCALIZAR"))
        self._btn_unlink = QPushButton("✕ " + tr("esl.unlink", default="DESVINCULAR"))
        for b in (self._btn_refrescar, self._btn_sync, self._btn_loc):
            b.setStyleSheet(_BTN_CIAN_SS); b.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_unlink.setStyleSheet(f"""
            QPushButton {{ background:#0E1117; color:#F85149; font-weight:bold; border-radius:14px;
                padding:12px 24px; font-size:13px; border:2px solid #F85149; }}
            QPushButton:hover {{ background:#F85149; color:#0E1117; }}""")
        self._btn_unlink.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_refrescar.clicked.connect(self._cargar)
        self._btn_sync.clicked.connect(self._sincronizar)
        self._btn_loc.clicked.connect(self._localizar)
        self._btn_unlink.clicked.connect(self._desvincular)
        tb.addWidget(self._btn_refrescar); tb.addWidget(self._btn_sync); tb.addWidget(self._btn_loc)
        tb.addStretch(); tb.addWidget(self._btn_unlink)
        root.addLayout(tb)

        # ── tabla ──
        self.tabla = QTableWidget(0, 5); self.tabla.setStyleSheet(_TABLA_SS)
        self.tabla.setHorizontalHeaderLabels([
            tr("esl.c_art", default="Artículo"), tr("esl.c_label", default="Etiqueta (ID)"),
            tr("esl.c_precio", default="Precio actual"), tr("esl.c_sync", default="Sincronizado"),
            tr("esl.c_estado", default="Estado")])
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.tabla, 1)

        self._lbl_estado = QLabel(""); self._lbl_estado.setStyleSheet("color:#8B949E;font-size:12px;")
        root.addWidget(self._lbl_estado)

        self._aplicar_permisos()

    # ── permisos / contexto ──
    def _usuario(self):
        return getattr(self.main_window, "usuario_actual", None)

    def _puede(self, permiso):
        try:
            from src.services.autorizacion import puede
            return puede(self._usuario(), permiso)
        except Exception:
            return True

    def _aplicar_permisos(self):
        self._btn_vinc.setEnabled(self._puede("esl.vincular"))
        self._btn_unlink.setEnabled(self._puede("esl.vincular"))
        self._btn_sync.setEnabled(self._puede("esl.sincronizar"))
        self._btn_loc.setEnabled(self._puede("esl.sincronizar"))
        self._btn_cfg.setEnabled(self._puede("esl.admin"))

    # ── datos ──
    def showEvent(self, e):
        super().showEvent(e)
        if not self._cargado:
            self._cargado = True
            self._cargar()

    def _cargar(self):
        from src.services.esl import config, registro, sync
        cfg = config.obtener_config()
        if cfg and not cfg.get("modo_simulado", 1) and cfg.get("endpoint"):
            self._lbl_modo.setText(tr("esl.mode_real", default="● Proveedor: {p}", p=cfg.get("proveedor")))
            self._lbl_modo.setStyleSheet("color:#2ECC71;font-size:12px;font-weight:bold;")
        else:
            self._lbl_modo.setText(tr("esl.mode_sim", default="● Modo simulado"))
            self._lbl_modo.setStyleSheet("color:#8B949E;font-size:12px;font-weight:bold;")

        labels = registro.listar()
        pend_ids = {p["label_id"] for p in sync.pendientes()}
        self.tabla.setRowCount(len(labels))
        for r, lab in enumerate(labels):
            pe = sync.precio_efectivo(lab["codigo_articulo"])
            ps = lab.get("precio_sincronizado")
            estado = "PENDIENTE" if lab["label_id"] in pend_ids else lab.get("estado", "")
            vals = [
                lab["codigo_articulo"], lab["label_id"],
                divisas.formatear(float(pe)) if pe is not None else "-",
                divisas.formatear(float(ps)) if ps is not None else "-",
                estado,
            ]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c == 4:
                    it.setForeground(QColor(_ESTADO_COLOR.get(estado, "#8B949E")))
                if c == 1:
                    it.setData(Qt.ItemDataRole.UserRole, lab["label_id"])
                self.tabla.setItem(r, c, it)
        n_pend = len(pend_ids)
        self._btn_sync.setText(f"⬆ {tr('esl.sync', default='SINCRONIZAR PENDIENTES')} ({n_pend})")

    def _sel_label(self):
        row = self.tabla.currentRow()
        if row < 0:
            return None
        it = self.tabla.item(row, 1)
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    # ── acciones ──
    def _vincular(self):
        from src.services.esl import registro
        cod = self.in_cod.text().strip()
        if "–" in cod:
            cod = cod.split("–")[0].strip()
        label = self.in_label.text().strip()
        if not cod or not label:
            return
        if registro.vincular(cod, label):
            self.in_cod.clear(); self.in_label.clear()
            self._cargar()
        elif mostrar_mensaje:
            mostrar_mensaje(self, tr("esl.title", default="ETIQUETAS ELECTRÓNICAS"),
                            tr("esl.link_err", default="No se pudo vincular. ¿Existe el artículo «{c}»?", c=cod),
                            nivel="warning")

    def _sincronizar(self):
        from src.services.esl import sync
        r = sync.sincronizar()
        self._cargar()
        if mostrar_mensaje:
            nivel = "success" if r["error"] == 0 else "warning"
            mostrar_mensaje(self, tr("esl.sync", default="SINCRONIZAR"),
                            tr("esl.sync_res", default="{ok}/{total} etiquetas actualizadas ({err} con error).",
                               ok=r["ok"], total=r["total"], err=r["error"]),
                            nivel=nivel if r["total"] else "info")

    def _localizar(self):
        from src.services.esl import sync
        label = self._sel_label()
        if not label:
            return
        r = sync.localizar(label)
        if mostrar_mensaje:
            mostrar_mensaje(self, tr("esl.locate", default="LOCALIZAR"),
                            tr("esl.locate_ok", default="Solicitado el parpadeo de la etiqueta {l}.", l=label)
                            if r.get("ok") else
                            tr("esl.locate_err", default="No se pudo localizar la etiqueta {l}.", l=label),
                            nivel="success" if r.get("ok") else "warning")

    def _desvincular(self):
        from src.services.esl import registro
        label = self._sel_label()
        if not label:
            return
        try:
            from assets.estilo_global import mostrar_confirmacion
        except Exception:
            mostrar_confirmacion = None
        if mostrar_confirmacion and not mostrar_confirmacion(
                self, tr("esl.unlink", default="DESVINCULAR"),
                tr("esl.unlink_msg", default="¿Desvincular la etiqueta {l}? El artículo no se ve afectado.", l=label)):
            return
        registro.desvincular(label)
        self._cargar()

    def _configurar(self):
        from src.services.esl import config
        dlg = _ESLConfigDialog(self, cfg=config.obtener_config() or {})
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.datos()
        config.guardar_config(**d)
        self._cargar()
        if mostrar_mensaje:
            mostrar_mensaje(self, tr("esl.config", default="CONFIGURAR"),
                            tr("esl.cfg_ok", default="Configuración ESL guardada."), nivel="success")

    def _retraducir(self):
        self._lbl_t.setText(tr("esl.title", default="ETIQUETAS ELECTRÓNICAS"))


def _desc_condicion(tipo, p):
    if tipo == "horario":
        base = f"{p.get('desde', '--')}–{p.get('hasta', '--')}"
        return base + (f"  (días {','.join(str(d) for d in p['dias'])})" if p.get("dias") else "")
    if tipo == "stock":
        return f"{p.get('campo', 'Stock_tienda')} {p.get('op', '>')} {p.get('umbral', 0)}"
    if tipo == "caducidad":
        return f"≤ {p.get('dias', 7)} días para caducar"
    return ""


def _desc_ajuste(tipo_aj, valor):
    try:
        v = float(valor)
    except (TypeError, ValueError):
        v = 0
    if tipo_aj == "pct":
        return f"{'+' if v >= 0 else ''}{v:g}%"
    return divisas.formatear(v)


class _ReglaPrecioDialog(QDialog):
    """Alta/edición de una regla de precio dinámico (campos de condición según el tipo)."""

    _TIPOS = [("horario", "Por horario (happy hour)"), ("stock", "Por stock"),
              ("caducidad", "Por caducidad")]
    _CAMPOS = ["Stock_tienda", "Stock_total", "Stock_central"]
    _OPS = [">", ">=", "<", "<="]

    def __init__(self, parent=None, regla=None):
        super().__init__(parent)
        regla = regla or {}
        params = {}
        if regla.get("params"):
            try:
                params = json.loads(regla["params"])
            except Exception:
                params = {}
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(520)

        main_lyt = QVBoxLayout(self)
        cont = QFrame()
        cont.setStyleSheet(f"""
            QFrame {{ background-color: {_PANEL_BG}; border: 2px solid {_CIAN}; border-radius: 15px; }}
            QLabel {{ color: white; border: none; font-family: 'Segoe UI'; font-weight: bold; }}
        """)
        main_lyt.addWidget(cont)
        ly = QVBoxLayout(cont); ly.setContentsMargins(28, 26, 28, 26); ly.setSpacing(11)

        lbl_t = QLabel(tr("pd.edit", default="EDITAR REGLA") if regla else tr("pd.new", default="NUEVA REGLA"))
        lbl_t.setStyleSheet(f"color:{_CIAN};font-size:15px;font-weight:900;border:none;")
        ly.addWidget(lbl_t)

        ly.addWidget(QLabel(tr("pd.name", default="NOMBRE:")))
        self.in_nombre = QLineEdit(regla.get("nombre", "")); self.in_nombre.setStyleSheet(_NEON_INPUT_SS)
        ly.addWidget(self.in_nombre)

        ly.addWidget(QLabel(tr("pd.type", default="TIPO DE REGLA:")))
        self.cmb_tipo = QComboBox(); self.cmb_tipo.setStyleSheet(_COMBO_SS)
        for code, txt in self._TIPOS:
            self.cmb_tipo.addItem(txt, code)
        if regla.get("tipo"):
            i = self.cmb_tipo.findData(regla["tipo"])
            if i >= 0:
                self.cmb_tipo.setCurrentIndex(i)
        self.cmb_tipo.currentIndexChanged.connect(self._vis)
        ly.addWidget(self.cmb_tipo)

        # grupo horario
        self.g_hor = QWidget(); gh = QHBoxLayout(self.g_hor); gh.setContentsMargins(0, 0, 0, 0); gh.setSpacing(8)
        self.in_desde = QLineEdit(params.get("desde", "")); self.in_desde.setStyleSheet(_NEON_INPUT_SS)
        self.in_desde.setPlaceholderText("desde HH:MM")
        self.in_hasta = QLineEdit(params.get("hasta", "")); self.in_hasta.setStyleSheet(_NEON_INPUT_SS)
        self.in_hasta.setPlaceholderText("hasta HH:MM")
        self.in_dias = QLineEdit(",".join(str(d) for d in params.get("dias", []))); self.in_dias.setStyleSheet(_NEON_INPUT_SS)
        self.in_dias.setPlaceholderText("días 0-6 (opc, L=0)")
        gh.addWidget(self.in_desde); gh.addWidget(self.in_hasta); gh.addWidget(self.in_dias)
        ly.addWidget(self.g_hor)

        # grupo stock
        self.g_stk = QWidget(); gs = QHBoxLayout(self.g_stk); gs.setContentsMargins(0, 0, 0, 0); gs.setSpacing(8)
        self.cmb_campo = QComboBox(); self.cmb_campo.setStyleSheet(_COMBO_SS); self.cmb_campo.addItems(self._CAMPOS)
        if params.get("campo") in self._CAMPOS:
            self.cmb_campo.setCurrentText(params["campo"])
        self.cmb_op = QComboBox(); self.cmb_op.setStyleSheet(_COMBO_SS); self.cmb_op.addItems(self._OPS)
        if params.get("op") in self._OPS:
            self.cmb_op.setCurrentText(params["op"])
        self.in_umbral = QLineEdit(str(params.get("umbral", ""))); self.in_umbral.setStyleSheet(_NEON_INPUT_SS)
        self.in_umbral.setPlaceholderText("umbral")
        gs.addWidget(self.cmb_campo); gs.addWidget(self.cmb_op); gs.addWidget(self.in_umbral)
        ly.addWidget(self.g_stk)

        # grupo caducidad
        self.g_cad = QWidget(); gc = QHBoxLayout(self.g_cad); gc.setContentsMargins(0, 0, 0, 0); gc.setSpacing(8)
        gc.addWidget(QLabel(tr("pd.days", default="Días para caducar ≤")))
        self.in_dias_cad = QLineEdit(str(params.get("dias", 7))); self.in_dias_cad.setStyleSheet(_NEON_INPUT_SS)
        self.in_dias_cad.setMaximumWidth(120)
        gc.addWidget(self.in_dias_cad); gc.addStretch()
        ly.addWidget(self.g_cad)

        # ajuste (fila propia para que el desplegable tenga anchura de sobra)
        aj = QHBoxLayout(); aj.setSpacing(8)
        aj.addWidget(QLabel(tr("pd.adjust", default="AJUSTE:")))
        self.cmb_aj = QComboBox(); self.cmb_aj.setStyleSheet(_COMBO_SS)
        self.cmb_aj.setMinimumWidth(190)   # que no se corten "Porcentaje (%)" / "Precio fijo (€)"
        self.cmb_aj.addItem(tr("pd.aj_pct", default="Porcentaje (%)"), "pct")
        self.cmb_aj.addItem(tr("pd.aj_fijo", default="Precio fijo (€)"), "fijo")
        self.cmb_aj.view().setMinimumWidth(200)   # el popup muestra el texto de cada opción completo
        if regla.get("ajuste_tipo"):
            i = self.cmb_aj.findData(regla["ajuste_tipo"])
            if i >= 0:
                self.cmb_aj.setCurrentIndex(i)
        self.in_valor = QLineEdit(str(regla.get("ajuste_valor", "")) if regla else "")
        self.in_valor.setStyleSheet(_NEON_INPUT_SS); self.in_valor.setPlaceholderText("valor (-10 / 4.99)")
        aj.addWidget(self.cmb_aj); aj.addWidget(self.in_valor, 1)
        ly.addLayout(aj)

        # prioridad en su propia fila (evita apretar la fila de ajuste)
        pr = QHBoxLayout(); pr.setSpacing(8)
        pr.addWidget(QLabel(tr("pd.prio", default="Prioridad:")))
        self.in_prio = QLineEdit(str(regla.get("prioridad", 0))); self.in_prio.setStyleSheet(_NEON_INPUT_SS)
        self.in_prio.setMaximumWidth(100)
        pr.addWidget(self.in_prio); pr.addStretch()
        ly.addLayout(pr)

        self.chk_activo = QCheckBox(tr("pd.active", default="Regla activa"))
        self.chk_activo.setStyleSheet(_CHECK_SS)
        self.chk_activo.setChecked(bool(regla.get("activo", 1)))
        ly.addWidget(self.chk_activo)

        btn_lyt = QHBoxLayout()
        btn_ok = QPushButton(tr("esl.save", default="GUARDAR")); btn_ok.setStyleSheet(_BTN_CIAN_SS)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor); btn_ok.clicked.connect(self._guardar)
        btn_cancel = QPushButton(tr("etiq.cancel", default="CANCELAR"))
        btn_cancel.setStyleSheet("background-color:#30363D;color:white;border-radius:10px;padding:10px;font-weight:bold;")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor); btn_cancel.clicked.connect(self.reject)
        btn_lyt.addWidget(btn_ok); btn_lyt.addWidget(btn_cancel)
        ly.addLayout(btn_lyt)

        # Los contenedores de grupo son QWidget → toman el fondo global de la app (más oscuro). Se hacen
        # transparentes para que muestren el color del panel (los QLineEdit hijos conservan su propio estilo).
        for g in (self.g_hor, self.g_stk, self.g_cad):
            g.setStyleSheet("background: transparent;")

        self._vis()

    def _vis(self):
        t = self.cmb_tipo.currentData()
        self.g_hor.setVisible(t == "horario")
        self.g_stk.setVisible(t == "stock")
        self.g_cad.setVisible(t == "caducidad")

    def datos(self):
        t = self.cmb_tipo.currentData()
        if t == "horario":
            dias = [int(x) for x in self.in_dias.text().replace(" ", "").split(",") if x.strip().isdigit()]
            params = {"desde": self.in_desde.text().strip(), "hasta": self.in_hasta.text().strip()}
            if dias:
                params["dias"] = dias
        elif t == "stock":
            try:
                umbral = float(self.in_umbral.text().replace(",", "."))
            except ValueError:
                umbral = 0
            params = {"campo": self.cmb_campo.currentText(), "op": self.cmb_op.currentText(), "umbral": umbral}
        else:
            try:
                dias = int(self.in_dias_cad.text())
            except ValueError:
                dias = 7
            params = {"dias": dias}
        try:
            valor = float(self.in_valor.text().replace(",", "."))
        except ValueError:
            valor = 0
        try:
            prio = int(self.in_prio.text())
        except ValueError:
            prio = 0
        return {"nombre": self.in_nombre.text().strip(), "tipo": t, "params": params,
                "ajuste_tipo": self.cmb_aj.currentData(), "ajuste_valor": valor,
                "prioridad": prio, "activo": 1 if self.chk_activo.isChecked() else 0}

    def _campos_faltantes(self) -> list:
        """Lista de campos OBLIGATORIOS que están vacíos (según el tipo de regla). Vacía = todo correcto."""
        faltan = []
        if not self.in_nombre.text().strip():
            faltan.append(tr("pd.f_nombre", default="Nombre"))
        t = self.cmb_tipo.currentData()
        if t == "horario":
            if not self.in_desde.text().strip():
                faltan.append(tr("pd.f_desde", default="Desde (HH:MM)"))
            if not self.in_hasta.text().strip():
                faltan.append(tr("pd.f_hasta", default="Hasta (HH:MM)"))
        elif t == "stock":
            if not self.in_umbral.text().strip():
                faltan.append(tr("pd.f_umbral", default="Umbral de stock"))
        else:  # caducidad
            if not self.in_dias_cad.text().strip():
                faltan.append(tr("pd.f_dias_cad", default="Días de caducidad"))
        if not self.in_valor.text().strip():
            faltan.append(tr("pd.f_valor", default="Valor del ajuste"))
        return faltan

    def _guardar(self):
        """Valida los campos OBLIGATORIOS antes de cerrar: si faltan, informa y NO guarda."""
        faltan = self._campos_faltantes()
        if faltan:
            detalle = "\n".join(f"  •  {c}" for c in faltan)
            msg = tr("pd.faltan_campos",
                     default="Para poder guardar y aplicar los cambios, primero debes rellenar los campos "
                             "obligatorios de la ventana.\n\nFaltan por completar:\n{campos}", campos=detalle)
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("pd.faltan_titulo", default="Faltan campos por rellenar"), msg, "warning")
            else:  # pragma: no cover
                QMessageBox.warning(self, tr("pd.faltan_titulo", default="Faltan campos por rellenar"), msg)
            return
        self.accept()


class _PrecioDinamicoPage(QWidget):
    """Gestión de reglas de precio dinámico + aplicación. Solo orquesta (lógica en services/precio_dinamico)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self._cargado = False

        root = QVBoxLayout(self); root.setContentsMargins(24, 24, 24, 16); root.setSpacing(14)

        cab = QHBoxLayout()
        self._lbl_t = QLabel(tr("pd.title", default="PRECIO DINÁMICO"))
        self._lbl_t.setStyleSheet(f"color:{_CIAN};font-size:18px;font-weight:900;")
        cab.addWidget(self._lbl_t); cab.addStretch()
        self._btn_prev = QPushButton("👁 " + tr("pd.preview", default="PREVISUALIZAR"))
        self._btn_aplicar = QPushButton("⚡ " + tr("pd.apply", default="APLICAR AHORA"))
        for b in (self._btn_prev, self._btn_aplicar):
            b.setStyleSheet(_BTN_CIAN_SS); b.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_prev.clicked.connect(self._previsualizar)
        self._btn_aplicar.clicked.connect(self._aplicar)
        cab.addWidget(self._btn_prev); cab.addWidget(self._btn_aplicar)
        root.addLayout(cab)

        sub = QLabel(tr("pd.sub", default="Las reglas recalculan el precio (sobre el precio base). "
                        "Tras aplicar, las etiquetas afectadas quedan PENDIENTES de sincronizar."))
        sub.setStyleSheet("color:#8B949E;font-size:12px;"); sub.setWordWrap(True)
        root.addWidget(sub)

        contenedor, self.tabla = construir_tabla_estilizada(self)   # contorno neón + esquinas (estándar app)
        self.tabla.setStyleSheet(_HEADER_STD_SS)
        self.tabla.setColumnCount(6)
        self.tabla.setHorizontalHeaderLabels([
            tr("pd.c_name", default="Nombre"), tr("pd.c_type", default="Tipo"),
            tr("pd.c_cond", default="Condición"), tr("pd.c_adj", default="Ajuste"),
            tr("pd.c_prio", default="Prioridad"), tr("pd.c_active", default="Activa")])
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        hh = self.tabla.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        hh.setHighlightSections(True)   # hover swap de las cabeceras
        for c in range(6):              # columnas equitativas (misma anchura → todo centrado)
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        root.addWidget(contenedor, 1)

        acc = QHBoxLayout(); acc.setSpacing(10)
        self._btn_nueva = BotonMas(tr("pd.new", default="NUEVA REGLA"))
        self._btn_editar = QPushButton("✏️ " + tr("pd.edit", default="EDITAR"))
        self._btn_borrar = QPushButton("🗑 " + tr("pd.del", default="ELIMINAR"))
        for b in (self._btn_nueva, self._btn_editar):
            b.setStyleSheet(_BTN_CIAN_SS); b.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_borrar.setStyleSheet(f"""
            QPushButton {{ background:#0E1117; color:#F85149; font-weight:bold; border-radius:14px;
                padding:12px 24px; font-size:13px; border:2px solid #F85149; }}
            QPushButton:hover {{ background:#F85149; color:#0E1117; }}""")
        self._btn_borrar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_nueva.clicked.connect(self._nueva)
        self._btn_editar.clicked.connect(self._editar)
        self._btn_borrar.clicked.connect(self._eliminar)
        acc.addWidget(self._btn_nueva); acc.addWidget(self._btn_editar); acc.addStretch()
        acc.addWidget(self._btn_borrar)
        root.addLayout(acc)

        self._aplicar_permisos()

    def _usuario(self):
        return getattr(self.main_window, "usuario_actual", None)

    def _puede(self, permiso):
        try:
            from src.services.autorizacion import puede
            return puede(self._usuario(), permiso)
        except Exception:
            return True

    def _aplicar_permisos(self):
        gest = self._puede("precio_dinamico.gestionar")
        for b in (self._btn_nueva, self._btn_editar, self._btn_borrar):
            b.setEnabled(gest)
        self._btn_aplicar.setEnabled(self._puede("precio_dinamico.aplicar"))

    def showEvent(self, e):
        super().showEvent(e)
        if not self._cargado:
            self._cargado = True
            self._cargar()

    def _cargar(self):
        from src.services.precio_dinamico import reglas as R
        filas = R.listar_reglas()
        tipos = {"horario": tr("pd.t_hor", default="Horario"), "stock": tr("pd.t_stk", default="Stock"),
                 "caducidad": tr("pd.t_cad", default="Caducidad")}
        self.tabla.setRowCount(len(filas))
        for r, reg in enumerate(filas):
            try:
                p = json.loads(reg.get("params") or "{}")
            except Exception:
                p = {}
            vals = [reg.get("nombre"), tipos.get(reg["tipo"], reg["tipo"]),
                    _desc_condicion(reg["tipo"], p), _desc_ajuste(reg["ajuste_tipo"], reg["ajuste_valor"]),
                    str(reg.get("prioridad", 0)),
                    "✓" if reg.get("activo") else "—"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 0:
                    it.setData(Qt.ItemDataRole.UserRole, reg["id"])
                if c == 5 and not reg.get("activo"):
                    it.setForeground(QColor("#8B949E"))
                self.tabla.setItem(r, c, it)

    def _sel_id(self):
        row = self.tabla.currentRow()
        if row < 0:
            return None
        it = self.tabla.item(row, 0)
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _nueva(self):
        from src.services.precio_dinamico import reglas as R
        dlg = _ReglaPrecioDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.datos()
        if not d["nombre"]:
            return
        R.crear_regla(d["nombre"], d["tipo"], d["params"], d["ajuste_tipo"], d["ajuste_valor"],
                      prioridad=d["prioridad"])
        self._cargar()

    def _editar(self):
        from src.services.precio_dinamico import reglas as R
        rid = self._sel_id()
        if rid is None:
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("pd.edit", default="EDITAR"),
                                tr("pd.sel_edit", default="Selecciona antes una regla de la tabla para editarla."),
                                nivel="info")
            return
        dlg = _ReglaPrecioDialog(self, regla=R.obtener_regla(rid))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.datos()
        R.actualizar_regla(rid, nombre=d["nombre"], tipo=d["tipo"], params=d["params"],
                           ajuste_tipo=d["ajuste_tipo"], ajuste_valor=d["ajuste_valor"],
                           prioridad=d["prioridad"], activo=d["activo"])
        self._cargar()

    def _eliminar(self):
        from src.services.precio_dinamico import reglas as R
        rid = self._sel_id()
        if rid is None:
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("pd.del", default="ELIMINAR"),
                                tr("pd.sel_del", default="Selecciona antes una regla de la tabla para eliminarla."),
                                nivel="info")
            return
        try:
            from assets.estilo_global import mostrar_confirmacion
        except Exception:
            mostrar_confirmacion = None
        it = self.tabla.item(self.tabla.currentRow(), 0)
        if mostrar_confirmacion and not mostrar_confirmacion(
                self, tr("pd.del", default="ELIMINAR"),
                tr("pd.del_msg", default="¿Eliminar la regla «{r}»?", r=it.text() if it else "")):
            return
        R.eliminar_regla(rid)
        self._cargar()

    def _previsualizar(self):
        from src.services.precio_dinamico import motor as M
        cambios = M.previsualizar()
        if not mostrar_mensaje:
            return
        if not cambios:
            mostrar_mensaje(self, tr("pd.preview", default="PREVISUALIZAR"),
                            tr("pd.no_changes", default="Ninguna regla cambia precios ahora mismo."),
                            nivel="info")
            return
        top = cambios[:15]
        lineas = [f"• {c['codigo']}  {c['precio_actual']:.2f} → {c['precio_nuevo']:.2f}  ({c['regla']})"
                  for c in top]
        extra = f"\n… y {len(cambios) - 15} más." if len(cambios) > 15 else ""
        mostrar_mensaje(self, tr("pd.preview", default="PREVISUALIZAR"),
                        tr("pd.preview_res", default="{n} artículo(s) cambiarían de precio:", n=len(cambios))
                        + "\n\n" + "\n".join(lineas) + extra, nivel="info")

    def _aplicar(self):
        from src.services.precio_dinamico import motor as M
        try:
            from assets.estilo_global import mostrar_confirmacion
        except Exception:
            mostrar_confirmacion = None
        if mostrar_confirmacion and not mostrar_confirmacion(
                self, tr("pd.apply", default="APLICAR AHORA"),
                tr("pd.apply_msg", default="¿Recalcular los precios según las reglas activas? "
                   "Las etiquetas afectadas quedarán pendientes de sincronizar.")):
            return
        r = M.aplicar()
        if mostrar_mensaje:
            mostrar_mensaje(self, tr("pd.apply", default="APLICAR AHORA"),
                            tr("pd.apply_res", default="{c} precio(s) actualizados de {e} evaluados "
                               "({n} reglas activas).", c=r["cambiados"], e=r["evaluados"], n=r["reglas"]),
                            nivel="success" if r["cambiados"] else "info")

    def _retraducir(self):
        self._lbl_t.setText(tr("pd.title", default="PRECIO DINÁMICO"))


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

        # Solo "Cambiar precio": Carpeta etiquetas se sustituye por Documentos centralizados;
        # Ajuste de precios y Promociones/Ofertas pasan al flujo de Tareas (Workflow/BPM).
        self._tab_keys = ["etiq.tab_price", "etiq.tab_esl", "etiq.tab_precdyn"]
        _tab_def = ["CAMBIAR PRECIO", "ETIQUETAS ELECTRÓNICAS", "PRECIO DINÁMICO"]

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
        self._page_esl = _EtiquetasElectronicasPage(self)
        self._page_precdyn = _PrecioDinamicoPage(self)
        self._vistas.addWidget(self._page_precio)
        self._vistas.addWidget(self._page_esl)
        self._vistas.addWidget(self._page_precdyn)

        root.addWidget(self._vistas)
        self._ir_a(0)

    def _retraducir(self):
        self.setWindowTitle(tr("etiq.window_title", default="Etiquetas de Precio"))
        _tab_def = ["CAMBIAR PRECIO", "ETIQUETAS ELECTRÓNICAS", "PRECIO DINÁMICO"]
        for i, btn in enumerate(self._nav_btns):
            btn.setText(tr(self._tab_keys[i], default=_tab_def[i]))
        self._btn_exit.setText(tr("etiq.exit", default="SALIR AL MENÚ"))
        for page in (self._page_precio, self._page_esl, self._page_precdyn):
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
