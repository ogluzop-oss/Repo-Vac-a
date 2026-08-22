# src/gui/info_articulo.py
import os

import cv2

from src.utils import divisas
from PyQt6.QtCore import QSize, QStringListModel, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPixmap
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from pyzbar.pyzbar import decode

from src.db.conexion import (
    obtener_articulo,
    ventas_semana,
)
from src.utils import i18n
from src.utils.i18n import tr

try:
    from assets.estilo_global import (
        aplicar_estilo_widget,
        construir_plantilla_camara,
        estilizar_completer,
        mostrar_confirmacion,
        mostrar_mensaje,
        repolish_widget,
    )
except Exception:
    aplicar_estilo_widget = None
    construir_plantilla_camara = None
    repolish_widget = None
    mostrar_mensaje = None
    mostrar_confirmacion = None
    estilizar_completer = None

# ---------------------------------------------------------------------------
# CONSTANTES Y ESTILOS
# ---------------------------------------------------------------------------
_CIAN = "#00FFC6"
_FONDO = "#0E1117"
_PANEL_BG = "#161B22"
_BORDE = "#30363D"
_VERDE = "#2ECC71"
_ROJO = "#F85149"


def _ss_boton(color):
    """Estilo de botón con contorno de color y hover swap (relleno al pasar el ratón)."""
    return f"""
    QPushButton {{
        background-color: #0E1117;
        color: {color};
        font-weight: bold;
        border-radius: 14px;
        padding: 10px 20px;
        font-size: 13px;
        font-family: 'Segoe UI';
        border: 2px solid {color};
    }}
    QPushButton:hover {{
        background-color: {color};
        color: #0E1117;
        border: 2px solid {color};
    }}
    """

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

_NEON_COMBO_SS = f"""
QComboBox {{
    background-color: #161B22; color: #FFFFFF;
    border: 2px solid {_CIAN}; border-radius: 10px;
    padding: 6px 12px; font-size: 13px; font-weight: bold;
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: #161B22; color: #FFFFFF;
    border: 1px solid {_CIAN};
    selection-background-color: {_CIAN}; selection-color: #0E1117;
}}
"""

_LISTA_SS = f"""
QListWidget {{
    background-color: {_PANEL_BG}; color: #FFFFFF;
    border: 1px solid {_BORDE}; border-radius: 12px; font-size: 13px; font-weight: bold;
    outline: none; padding: 6px;
}}
QListWidget::item {{ padding: 9px 12px; border-radius: 9px; margin: 2px 2px; }}
QListWidget::item:hover {{ background-color: #1A2230; }}
QListWidget::item:selected {{ background-color: #1A2230; color: {_CIAN}; }}
"""

# ---------------------------------------------------------------------------
# COMPONENTES AUXILIARES
# ---------------------------------------------------------------------------


def _get_completer_data():
    """Sugerencias en formato único 'CÓDIGO – NOMBRE' (sin duplicar código y nombre)."""
    from src.db.articulos import listar_codigo_nombre
    data = []
    for cod, nom in listar_codigo_nombre():
        cod = str(cod or "").strip()
        nom = str(nom or "").strip()
        if cod or nom:
            data.append(f"{cod} – {nom}".strip(" –"))
    return data


def _sombra_cian(widget):
    fx = QGraphicsDropShadowEffect()
    fx.setBlurRadius(20)
    fx.setColor(QColor(_CIAN))
    fx.setOffset(0)
    widget.setGraphicsEffect(fx)


def _sombra_roja(widget):
    fx = QGraphicsDropShadowEffect()
    fx.setBlurRadius(20)
    fx.setColor(QColor("#F85149"))
    fx.setOffset(0)
    widget.setGraphicsEffect(fx)


# Icono '+' neón + botón que lo oscurece en hover: fuente única compartida (gui/iconos_neon).
from src.gui.iconos_neon import BotonMas as _BotonMas  # noqa: E402
from src.gui.iconos_neon import icono_mas as _icono_mas  # noqa: E402


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
        if repolish_widget:
            repolish_widget(self)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if repolish_widget:
            repolish_widget(self)


class _EditarNombreDialog(QDialog):
    def __init__(self, current_name, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(450)

        main_lyt = QVBoxLayout(self)
        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{ background-color: {_PANEL_BG}; border: 2px solid {_CIAN}; border-radius: 15px; }}
            QLabel {{ color: white; border: none; font-family: 'Segoe UI'; font-weight: bold; }}
        """)
        main_lyt.addWidget(container)

        ly = QVBoxLayout(container)
        ly.setContentsMargins(30, 30, 30, 30)
        ly.setSpacing(15)

        ly.addWidget(QLabel(tr("info.current_name_label", default="NOMBRE ACTUAL DEL ARTÍCULO:")))
        lbl_curr = QLabel(current_name.upper())
        lbl_curr.setStyleSheet(
            f"color: {_CIAN}; font-size: 14px; font-weight: 900; border: none;"
        )
        lbl_curr.setWordWrap(True)
        ly.addWidget(lbl_curr)

        self.input_new = QLineEdit()
        self.input_new.setPlaceholderText(tr("info.new_name_ph", default="Introduce el nuevo nombre..."))
        self.input_new.setText(current_name)
        self.input_new.setStyleSheet(_NEON_INPUT_SS)
        ly.addWidget(self.input_new)

        btn_lyt = QHBoxLayout()
        btn_save = QPushButton(tr("info.save_changes", default="GUARDAR CAMBIOS"))
        btn_save.setStyleSheet(_BTN_CIAN_SS)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self.accept)

        btn_cancel = QPushButton(tr("info.cancel", default="CANCELAR"))
        btn_cancel.setStyleSheet(
            "background-color: #30363D; color: white; border-radius: 10px; padding: 10px; font-weight: bold;"
        )
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)

        btn_lyt.addWidget(btn_save)
        btn_lyt.addWidget(btn_cancel)
        ly.addLayout(btn_lyt)

    def get_name(self):
        return self.input_new.text().strip()


# ---------------------------------------------------------------------------
# PÁGINAS DE CONTENIDO
# ---------------------------------------------------------------------------


class _BuscarArticuloPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        layout = QVBoxLayout(self)
        # Eliminado setContentsMargins para permitir el centrado vertical con stretches
        layout.setSpacing(30)

        layout.addStretch(1)  # Añadido stretch para centrar verticalmente

        # Nuevo icono de lupa para la pestaña "Buscar Artículo"
        self.lbl_icon = QLabel("🔍")
        self.lbl_icon.setStyleSheet("font-size: 160px;")
        self.lbl_icon.setFixedHeight(200)  # Tamaño consistente con otros iconos
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(20)  # Espacio adicional entre icono y siguiente elemento
        layout.addWidget(self.lbl_icon, alignment=Qt.AlignmentFlag.AlignCenter)

        # Espaciador superior colapsable: al mostrar un resultado, el icono de lupa se compacta para
        # que el panel de resultado suba (no quede pegado al suelo) y quede a una altura más centrada.

        # Search area
        search_container = QHBoxLayout()
        search_container.setSpacing(10)  # Reduce el espacio entre la barra y el botón
        search_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(tr("info.search_ph", default="Introduce código o nombre del artículo..."))
        self.search_bar.setStyleSheet(_NEON_INPUT_SS)
        self.search_bar.setMinimumWidth(280); self.search_bar.setMaximumWidth(560)  # responsive (P2)
        self.search_bar.returnPressed.connect(self._buscar)

        self._btn_scan = btn_scan = QPushButton("📷 " + tr("info.scan", default="SCAN"))
        btn_scan.setFixedSize(180, 55)
        btn_scan.setStyleSheet(_BTN_CIAN_SS)
        btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_scan.clicked.connect(self._abrir_escanner)

        search_container.addWidget(self.search_bar)
        search_container.addWidget(btn_scan)
        layout.addLayout(search_container)

        # Result area
        self.result_frame = QFrame()
        self.result_frame.setObjectName("result_panel")
        self.result_frame.setStyleSheet(
            f"QFrame#result_panel {{ background: {_PANEL_BG}; border: 1px solid {_BORDE}; border-radius: 20px; }}"
        )
        self.result_frame.setVisible(False)

        res_lyt = QHBoxLayout(self.result_frame)
        res_lyt.setContentsMargins(30, 30, 30, 30)
        res_lyt.setSpacing(40)

        # Photo
        self.lbl_foto = QLabel()
        self.lbl_foto.setFixedSize(320, 320)
        self.lbl_foto.setStyleSheet(
            f"background-color: {_FONDO}; border: 2px solid {_BORDE}; border-radius: 15px;"
        )
        self.lbl_foto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # El recuadro de la imagen se ancla ARRIBA en su propia columna: un stretch por debajo lo
        # empuja al tope del panel (que es más alto por la columna de datos), en vez de quedar
        # centrado verticalmente. Así queda a una altura alta con el espacio sobrante debajo.
        foto_col = QVBoxLayout()
        foto_col.setContentsMargins(0, 0, 0, 0)
        foto_col.addWidget(self.lbl_foto)
        foto_col.addStretch(1)
        res_lyt.addLayout(foto_col)

        # Info column
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        info_widget = QWidget()
        info_widget.setStyleSheet("background: transparent;")
        self.info_lyt = QVBoxLayout(info_widget)
        self.info_lyt.setSpacing(12)

        self.labels = {}
        self._field_titles = {}
        # (clave_dato, clave_i18n, texto_por_defecto)
        self._fields_def = [
            ("CODIGO", "info.f_code", "CÓDIGO SKU:"),
            ("NOMBRE", "info.f_desc", "DESCRIPCIÓN:"),
            ("S_LINEAL", "info.f_shelf", "STOCK LINEAL:"),
            ("S_ALMACEN", "info.f_warehouse", "STOCK ALMACÉN:"),
            ("S_CENTRAL", "info.f_central", "STOCK CENTRAL:"),
            ("PRECIO", "info.f_price", "P.V.P:"),
            ("U_TIENDA", "info.f_loc_store", "UBIC. TIENDA:"),
            ("U_ALMACEN", "info.f_loc_warehouse", "UBIC. ALMACÉN:"),
            ("RECEPCION", "info.f_reception", "PRÓX. ENTRADA:"),
            ("VENTAS", "info.f_sales", "VENTAS 7 DÍAS:"),
        ]

        for key, ikey, text in self._fields_def:
            row = QHBoxLayout()
            l_tit = QLabel(tr(ikey, default=text))
            l_tit.setStyleSheet(
                "color: #8B949E; font-size: 12px; font-weight: bold; border:none;"
            )
            l_tit.setFixedWidth(140)
            l_val = QLabel("-")
            l_val.setStyleSheet(
                "color: #FFFFFF; font-size: 14px; font-weight: 900; border:none;"
            )
            l_val.setWordWrap(True)
            row.addWidget(l_tit)
            row.addWidget(l_val, 1)
            self.info_lyt.addLayout(row)
            self.labels[key] = l_val
            self._field_titles[key] = l_tit

        # ── FAMILIA DEL ARTÍCULO (vínculo GLOBAL, asignación rápida) ──
        # Combo con las familias de la empresa; cambiar el valor asigna/quita la familia del artículo
        # cargado (se refleja en toda la app: se guarda en articulos.id_familia).
        self._art_codigo = None
        self._fam_cargando = False
        self.info_lyt.addSpacing(8)
        row_fam = QHBoxLayout()
        self._lbl_fam = QLabel(tr("info.f_familia", default="FAMILIA:"))
        self._lbl_fam.setStyleSheet("color:#8B949E;font-size:12px;font-weight:bold;border:none;")
        self._lbl_fam.setFixedWidth(140)
        self.cmb_familia = QComboBox()
        self.cmb_familia.setStyleSheet(_NEON_COMBO_SS)
        self.cmb_familia.setMinimumWidth(200)
        self.cmb_familia.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cmb_familia.currentIndexChanged.connect(self._cambiar_familia)
        row_fam.addWidget(self._lbl_fam)
        row_fam.addWidget(self.cmb_familia, 1)
        self.info_lyt.addLayout(row_fam)

        # ── FÍSICA DE SEGURIDAD DEL AUTOCOBRO (Capa 1): peso esperado + tolerancia por artículo ──
        # Master data que alimenta el control antifraude de las cajas de autocobro. Editable solo por
        # gerente/administrador. Vacío = usa los valores por defecto del motor.
        self.info_lyt.addSpacing(8)
        self._lbl_fisica = QLabel("⚖  " + tr("info.fisica_title", default="FÍSICA DE SEGURIDAD (AUTOCOBRO)"))
        self._lbl_fisica.setStyleSheet(f"color:{_CIAN};font-size:12px;font-weight:900;border:none;")
        self.info_lyt.addWidget(self._lbl_fisica)

        def _fila_fisica(lbl_txt):
            row = QHBoxLayout()
            t = QLabel(lbl_txt)
            t.setStyleSheet("color:#8B949E;font-size:12px;font-weight:bold;border:none;")
            t.setFixedWidth(140)
            inp = QLineEdit()
            inp.setStyleSheet(_NEON_INPUT_SS)
            inp.setMaximumWidth(160)
            inp.setPlaceholderText(tr("info.f_auto", default="auto"))
            row.addWidget(t)
            row.addWidget(inp)
            row.addStretch()
            self.info_lyt.addLayout(row)
            return inp, t

        self.inp_peso_unitario, self._lbl_pu = _fila_fisica(
            tr("info.f_peso_unit", default="PESO UNIT. (kg):"))
        self.inp_tolerancia, self._lbl_tp = _fila_fisica(
            tr("info.f_tolerancia", default="TOLERANCIA (kg):"))
        self._btn_guardar_fisica = QPushButton(tr("info.f_guardar", default="GUARDAR FÍSICA"))
        self._btn_guardar_fisica.setStyleSheet(_BTN_CIAN_SS)
        self._btn_guardar_fisica.setFixedHeight(40)
        self._btn_guardar_fisica.clicked.connect(self._guardar_fisica)
        self.info_lyt.addWidget(self._btn_guardar_fisica)

        # Edición TEXTIL: gestión de variantes talla/color del modelo seleccionado (gateado por edición).
        self._btn_variantes = QPushButton(tr("info.variantes", default="🎽 VARIANTES (TALLA/COLOR)"))
        self._btn_variantes.setStyleSheet(_BTN_CIAN_SS)
        self._btn_variantes.setFixedHeight(40)
        self._btn_variantes.clicked.connect(self._abrir_variantes)
        self.info_lyt.addWidget(self._btn_variantes)
        try:
            from src.services import verticales
            if not verticales.visible("productos.tallas"):
                self._btn_variantes.setVisible(False)
        except Exception:
            pass

        scroll.setWidget(info_widget)
        # La columna de datos (incluida FÍSICA DE SEGURIDAD) es más alta que el panel visible: se deja
        # que el QScrollArea muestre su barra de desplazamiento para poder acceder a todos los campos.
        self._info_scroll = scroll
        res_lyt.addWidget(scroll, 1)
        layout.addWidget(self.result_frame)
        layout.addStretch()
        layout.addStretch(1)  # Añadido stretch final para centrar verticalmente
        # Completer
        self.completer = QCompleter()
        self.completer_model = QStringListModel()
        self.completer.setModel(self.completer_model)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.search_bar.setCompleter(self.completer)
        if estilizar_completer:
            estilizar_completer(self.completer)
        self.completer_model.setStringList(_get_completer_data())   # precarga: sugerencias inmediatas
        self.search_bar.textChanged.connect(self._update_suggestions)

    def _update_suggestions(self):
        if len(self.search_bar.text()) >= 1 and not self.completer_model.stringList():
            self.completer_model.setStringList(_get_completer_data())

    def _retraducir(self):
        self.search_bar.setPlaceholderText(
            tr("info.search_ph", default="Introduce código o nombre del artículo...")
        )
        self._btn_scan.setText("📷 " + tr("info.scan", default="SCAN"))
        self._lbl_fam.setText(tr("info.f_familia", default="FAMILIA:"))
        for key, ikey, text in self._fields_def:
            self._field_titles[key].setText(tr(ikey, default=text))

    def _abrir_escanner(self):
        self.main_window.abrir_escanner()

    def _abrir_variantes(self):
        """Abre la gestión de variantes talla/color del modelo seleccionado (edición Textil)."""
        codigo = (getattr(self, "_art_sel", None) or {}).get("codigo") or getattr(self, "_art_codigo", None)
        if not codigo:
            return
        try:
            from src.gui.variantes_gui import VariantesDialog
            VariantesDialog(codigo_padre=codigo, usuario=getattr(self, "usuario", None), parent=self).exec()
        except Exception:
            pass

    def _guardar_fisica(self):
        """Guarda el peso esperado + tolerancia del artículo cargado (solo gerente/administrador)."""
        if not getattr(self, "_art_codigo", None):
            return
        try:
            from src.db.usuario import sesion_global
            perfil = ((sesion_global.usuario_actual or {}).get("perfil") or "").upper()
        except Exception:
            perfil = ""
        if perfil not in ("GERENTE", "ADMINISTRADOR"):
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("info.f_perm_title", default="Permiso denegado"),
                                tr("info.f_perm_msg",
                                   default="Solo un gerente o administrador puede editar la física de seguridad."),
                                nivel="warning")
            return
        from src.db.articulos import guardar_fisica_seguridad
        pu = self.inp_peso_unitario.text().strip().replace(",", ".") or None
        tp = self.inp_tolerancia.text().strip().replace(",", ".") or None
        ok, msg = guardar_fisica_seguridad(self._art_codigo, pu, tp)
        if mostrar_mensaje:
            mostrar_mensaje(self, tr("info.f_guardado_title", default="Física de seguridad"),
                            msg, nivel="success" if ok else "warning")

    def _recargar_familias(self, sel_id=None):
        """Rellena el combo de familias y selecciona la del artículo cargado (o 'Sin familia')."""
        from src.db.familias import listar_familias
        self._fam_cargando = True
        try:
            self.cmb_familia.clear()
            self.cmb_familia.addItem(tr("info.fam_none", default="— Sin familia —"), None)
            for f in listar_familias():
                self.cmb_familia.addItem(f["nombre"], f["id"])
            idx = self.cmb_familia.findData(sel_id) if sel_id is not None else 0
            self.cmb_familia.setCurrentIndex(idx if idx >= 0 else 0)
        finally:
            self._fam_cargando = False

    def _cambiar_familia(self):
        """Asigna (o quita) la familia del artículo cargado. Vínculo GLOBAL en articulos.id_familia."""
        if self._fam_cargando or not getattr(self, "_art_codigo", None):
            return
        from src.db.familias import asignar_familia
        # Asignación inmediata y silenciosa (el propio combo refleja el valor elegido).
        asignar_familia(self._art_codigo, self.cmb_familia.currentData())

    def _buscar(self, code=None):
        q = code or self.search_bar.text().strip()
        # Si viene del autocompletado "CÓDIGO – NOMBRE", usar solo el código.
        if q and "–" in q:
            q = q.split("–")[0].strip()
        if not q:
            return

        try:
            art = obtener_articulo(q)
            if not art:
                if mostrar_mensaje:
                    mostrar_mensaje(
                        self,
                        tr("info.not_found_title", default="No Encontrado"),
                        tr("info.not_found_msg", default="No se encontró información para: {q}", q=q),
                        nivel="warning",
                    )
                return

            def fmt(val):
                return str(val) if val is not None and str(val).strip() != "" else "-"

            self.labels["CODIGO"].setText(fmt(art.get("codigo")))
            self.labels["NOMBRE"].setText(fmt(art.get("nombre")).upper())
            self.labels["S_LINEAL"].setText(fmt(art.get("Stock_tienda")))
            self.labels["S_ALMACEN"].setText(fmt(art.get("Stock_total")))
            self.labels["S_CENTRAL"].setText(fmt(art.get("Stock_central")))

            precio = float(
                art.get("precio_promo")
                if art.get("promo_activa")
                else art.get("precio", 0)
            )
            self.labels["PRECIO"].setText(f"{divisas.formatear(precio)}")

            self.labels["U_TIENDA"].setText(fmt(art.get("ubicacion_tienda")))
            self.labels["U_ALMACEN"].setText(fmt(art.get("ubicacion_almacen")))

            self.labels["RECEPCION"].setText(fmt(art.get("siguiente_recepcion")))
            self.labels["VENTAS"].setText(str(ventas_semana(art.get("codigo"))))

            # Física de seguridad (autocobro): peso esperado + tolerancia del artículo.
            self._art_codigo = art.get("codigo")
            # Familia actual del artículo (vínculo global).
            try:
                from src.db.familias import familia_de_articulo
                fam = familia_de_articulo(self._art_codigo)
                self._recargar_familias(fam["id"] if fam else None)
            except Exception:
                pass
            pu, tp = art.get("peso_unitario"), art.get("tolerancia_peso")
            self.inp_peso_unitario.setText("" if pu in (None, "") else str(pu))
            self.inp_tolerancia.setText("" if tp in (None, "") else str(tp))

            # Photo
            img_path = art.get("imagen")
            if img_path and os.path.exists(img_path):
                pix = QPixmap(img_path).scaled(
                    300,
                    300,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.lbl_foto.setPixmap(pix)
                self.lbl_foto.setText("")
            else:
                self.lbl_foto.setPixmap(QPixmap())
                self.lbl_foto.setText(tr("info.no_image", default="SIN IMAGEN"))
                self.lbl_foto.setStyleSheet(
                    f"background-color: {_FONDO}; border: 2px solid {_BORDE}; border-radius: 15px; color: #8B949E; font-weight: 900; font-size: 14px;"
                )

            self._compactar_icono(True)
            self.result_frame.setVisible(True)
            self.search_bar.clear()

        except Exception as e:
            print(f"Error búsqueda: {e}")

    def _compactar_icono(self, compacto: bool):
        """Reduce el icono de lupa cuando hay un resultado en pantalla, para que el panel de resultado
        suba y no quede pegado al fondo de la ventana (queda a una altura más centrada)."""
        if compacto:
            self.lbl_icon.setFixedHeight(96)
            self.lbl_icon.setStyleSheet("font-size: 74px;")
        else:
            self.lbl_icon.setFixedHeight(200)
            self.lbl_icon.setStyleSheet("font-size: 160px;")


class _ImagenArticuloPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self._art_sel = None          # artículo seleccionado (dict)
        self._img_pendiente = None    # ruta de imagen elegida y pendiente de guardar

        # Todo el contenido va dentro de un QScrollArea para poder desplazarse cuando la vista previa
        # y los botones no caben (pantallas pequeñas / ventana reducida).
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("background: transparent; border: none;")
        cont = QWidget()
        cont.setStyleSheet("background: transparent;")
        self._scroll.setWidget(cont)
        root.addWidget(self._scroll)

        layout = QVBoxLayout(cont)
        layout.setSpacing(24)

        layout.addStretch(1)
        self.lbl_icon = QLabel("📸")  # Icono de cámara de fotos
        self.lbl_icon.setStyleSheet("font-size: 160px;")
        self.lbl_icon.setFixedHeight(200)  # Aumentado para evitar recorte
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(20)  # Espacio adicional entre icono y siguiente elemento
        layout.addWidget(self.lbl_icon, alignment=Qt.AlignmentFlag.AlignCenter)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(
            tr("info.image_search_ph", default="Introduce código o nombre para actualizar imagen...")
        )
        self.search_bar.setStyleSheet(_NEON_INPUT_SS)  # Mantener estilo neón
        self.search_bar.setMinimumWidth(280); self.search_bar.setMaximumWidth(560)  # responsive (P2)
        layout.addWidget(self.search_bar, alignment=Qt.AlignmentFlag.AlignCenter)

        # Completer para la barra de búsqueda
        self.completer = QCompleter()
        self.completer_model = QStringListModel()
        self.completer.setModel(self.completer_model)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.search_bar.setCompleter(self.completer)
        if estilizar_completer:
            estilizar_completer(self.completer)
        self.completer_model.setStringList(_get_completer_data())   # precarga: sugerencias inmediatas
        self.search_bar.textChanged.connect(self._update_suggestions)

        self._btn = btn = QPushButton(tr("info.select_item", default="SELECCIONAR ARTÍCULO"))
        btn.setStyleSheet(_BTN_CIAN_SS)
        btn.setFixedSize(250, 55)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._seleccionar_articulo)
        _sombra_cian(btn)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Vista previa de la imagen asociada (oculta hasta que se selecciona una).
        self.lbl_preview = QLabel()
        self.lbl_preview.setFixedSize(220, 220)
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setStyleSheet(
            f"background-color: {_FONDO}; border: 2px solid {_BORDE}; border-radius: 15px;"
        )
        self.lbl_preview.setVisible(False)
        layout.addWidget(self.lbl_preview, alignment=Qt.AlignmentFlag.AlignCenter)

        # Botones GUARDAR (verde) y BORRAR (rojo) — ocultos hasta seleccionar un artículo.
        botones = QHBoxLayout()
        botones.setSpacing(16)
        botones.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._btn_guardar = QPushButton(tr("info.img_save_btn", default="GUARDAR IMAGEN"))
        self._btn_guardar.setStyleSheet(_ss_boton(_VERDE))
        self._btn_guardar.setFixedSize(220, 52)
        self._btn_guardar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_guardar.clicked.connect(self._guardar_imagen)
        self._btn_borrar = QPushButton(tr("info.img_delete_btn", default="BORRAR IMAGEN"))
        self._btn_borrar.setStyleSheet(_ss_boton(_ROJO))
        self._btn_borrar.setFixedSize(220, 52)
        self._btn_borrar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_borrar.clicked.connect(self._borrar_imagen)
        botones.addWidget(self._btn_guardar)
        botones.addWidget(self._btn_borrar)
        self._cont_botones = QWidget()
        self._cont_botones.setLayout(botones)
        self._cont_botones.setVisible(False)
        layout.addWidget(self._cont_botones, alignment=Qt.AlignmentFlag.AlignCenter)

        # Mensaje en línea (éxito/error): se usa feedback inline en lugar de QMessageBox porque en el
        # proceso principal SOMA mantiene el audio activo y los modales pueden corromper el heap.
        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color:#8B949E;font-size:13px;font-weight:bold;border:none;")
        layout.addWidget(self.lbl_status, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch(1)

    def _status(self, texto, error=False, ok=False):
        color = "#F85149" if error else (_VERDE if ok else _CIAN)
        self.lbl_status.setStyleSheet(f"color:{color};font-size:13px;font-weight:bold;border:none;")
        self.lbl_status.setText(texto)

    def _resolver(self):
        """Resuelve el artículo escrito en el buscador (código, nombre o 'CÓDIGO – NOMBRE')."""
        q = self.search_bar.text().strip()
        if q and "–" in q:  # viene del autocompletado "CÓDIGO – NOMBRE"
            q = q.split("–")[0].strip()
        if not q:
            self._status(tr("info.img_need_code", default="Introduce el código o nombre de un artículo."),
                         error=True)
            return None
        try:
            art = obtener_articulo(q)
        except Exception as e:
            self._status(tr("info.img_db_error", default="Error al buscar el artículo: {e}", e=e), error=True)
            return None
        if not art:
            self._status(tr("info.img_not_found", default="No se encontró el artículo: {q}", q=q), error=True)
            return None
        return art

    def _mostrar_preview(self, ruta):
        pix = QPixmap(ruta) if ruta else QPixmap()
        if ruta and not pix.isNull():
            self.lbl_preview.setPixmap(pix.scaled(
                210, 210, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.lbl_preview.setVisible(True)
        else:
            self.lbl_preview.setPixmap(QPixmap())
            self.lbl_preview.setVisible(False)

    def _seleccionar_articulo(self):
        """Selecciona el artículo y abre el diálogo de Windows para elegir una imagen (no guarda aún):
        la imagen queda en vista previa hasta pulsar GUARDAR IMAGEN."""
        art = self._resolver()
        if not art:
            return
        self._art_sel = art
        codigo = art.get("codigo")
        nombre = (art.get("nombre") or "").upper()
        self._cont_botones.setVisible(True)

        from PyQt6.QtWidgets import QFileDialog
        ruta, _ = QFileDialog.getOpenFileName(
            self,
            tr("info.img_dialog_title", default="Seleccionar imagen del artículo"),
            "",
            "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif *.webp)",
        )
        if ruta:
            self._img_pendiente = ruta
            self._mostrar_preview(ruta)
            self._status(tr("info.img_pending",
                            default="Imagen lista. Pulsa GUARDAR IMAGEN para asociarla a {codigo} – {nombre}.",
                            codigo=codigo, nombre=nombre))
        else:
            # Sin imagen nueva: mostrar la imagen ya asociada (si existe) para poder borrarla.
            self._img_pendiente = None
            actual = art.get("imagen")
            self._mostrar_preview(actual if actual and os.path.exists(actual) else None)
            self._status(tr("info.img_selected",
                            default="Artículo {codigo} seleccionado. Elige una imagen o púlsa BORRAR IMAGEN.",
                            codigo=codigo))

    def _guardar_imagen(self):
        """Guarda (persiste) la imagen pendiente en el artículo seleccionado."""
        if not self._art_sel:
            self._status(tr("info.img_no_sel", default="Selecciona primero un artículo."), error=True)
            return
        if not self._img_pendiente:
            self._status(tr("info.img_no_pending",
                            default="Elige una imagen con SELECCIONAR ARTÍCULO antes de guardar."), error=True)
            return
        codigo = self._art_sel.get("codigo")
        nombre = (self._art_sel.get("nombre") or "").upper()
        try:
            import shutil
            raiz = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            destino_dir = os.path.join(raiz, "documentos", "imagenes_articulos")
            os.makedirs(destino_dir, exist_ok=True)
            ext = os.path.splitext(self._img_pendiente)[1].lower() or ".png"
            safe = "".join(c for c in str(codigo) if c.isalnum() or c in ("-", "_")) or "articulo"
            destino = os.path.join(destino_dir, f"{safe}{ext}")
            if os.path.abspath(self._img_pendiente) != os.path.abspath(destino):
                shutil.copy2(self._img_pendiente, destino)
            # Cliente fino (Fase 3): la escritura de imagen vive en la capa de datos.
            from src.db.articulos import actualizar_imagen
            actualizar_imagen(codigo, destino)
        except Exception as e:
            self._status(tr("info.img_save_error", default="No se pudo guardar la imagen: {e}", e=e), error=True)
            return
        self._art_sel["imagen"] = destino
        self._img_pendiente = None
        self._mostrar_preview(destino)
        self._status(tr("info.img_saved", default="Imagen guardada en {codigo} – {nombre}.",
                        codigo=codigo, nombre=nombre), ok=True)

    def _borrar_imagen(self):
        """Elimina la imagen asociada al artículo seleccionado (columna imagen a NULL + fichero)."""
        if not self._art_sel:
            self._status(tr("info.img_no_sel", default="Selecciona primero un artículo."), error=True)
            return
        codigo = self._art_sel.get("codigo")
        try:
            # Cliente fino (Fase 3): lectura/escritura de imagen en la capa de datos.
            from src.db.articulos import actualizar_imagen, obtener_imagen
            ruta_actual = obtener_imagen(codigo)
            actualizar_imagen(codigo, None)
            if ruta_actual and os.path.exists(ruta_actual):
                try:
                    os.remove(ruta_actual)
                except OSError:
                    pass
        except Exception as e:
            self._status(tr("info.img_del_error", default="No se pudo borrar la imagen: {e}", e=e), error=True)
            return
        self._art_sel["imagen"] = None
        self._img_pendiente = None
        self._mostrar_preview(None)
        self._status(tr("info.img_deleted", default="Imagen eliminada del artículo {codigo}.", codigo=codigo),
                     ok=True)

    def _retraducir(self):
        self.search_bar.setPlaceholderText(
            tr("info.image_search_ph", default="Introduce código o nombre para actualizar imagen...")
        )
        self._btn.setText(tr("info.select_item", default="SELECCIONAR ARTÍCULO"))
        self._btn_guardar.setText(tr("info.img_save_btn", default="GUARDAR IMAGEN"))
        self._btn_borrar.setText(tr("info.img_delete_btn", default="BORRAR IMAGEN"))

    def _update_suggestions(self):
        if len(self.search_bar.text()) >= 1 and not self.completer_model.stringList():
            self.completer_model.setStringList(_get_completer_data())


class _EditarArticuloPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(30)

        layout.addStretch(1)
        self.lbl_icon = QLabel("✏️")  # Icono de lápiz para editar
        self.lbl_icon.setStyleSheet("font-size: 160px;")
        self.lbl_icon.setFixedHeight(200)  # Aumentado para evitar recorte
        layout.addSpacing(20)  # Espacio adicional entre icono y siguiente elemento
        layout.addWidget(self.lbl_icon, alignment=Qt.AlignmentFlag.AlignCenter)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(tr("info.edit_search_ph", default="Introduce código o nombre para editar..."))
        self.search_bar.setStyleSheet(_NEON_INPUT_SS)
        self.search_bar.setMinimumWidth(280); self.search_bar.setMaximumWidth(560)  # responsive (P2)

        # Completer con sugerencias de artículos (igual que las otras pestañas).
        self.completer = QCompleter()
        self.completer_model = QStringListModel()
        self.completer.setModel(self.completer_model)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.search_bar.setCompleter(self.completer)
        if estilizar_completer:
            estilizar_completer(self.completer)
        self.completer_model.setStringList(_get_completer_data())
        self.search_bar.textChanged.connect(self._update_suggestions)

        layout.addWidget(self.search_bar, alignment=Qt.AlignmentFlag.AlignCenter)

        self._btn = btn = QPushButton(tr("info.search_for_edit", default="BUSCAR PARA EDITAR"))
        btn.setStyleSheet(_BTN_CIAN_SS)
        btn.setFixedSize(250, 55)
        _sombra_cian(btn)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)

    def _update_suggestions(self):
        if len(self.search_bar.text()) >= 1 and not self.completer_model.stringList():
            self.completer_model.setStringList(_get_completer_data())

    def _retraducir(self):
        self.search_bar.setPlaceholderText(tr("info.edit_search_ph", default="Introduce código o nombre para editar..."))
        self._btn.setText(tr("info.search_for_edit", default="BUSCAR PARA EDITAR"))


# ---------------------------------------------------------------------------
# FAMILIAS DE PRODUCTO — gestión (CRUD) + asignación de artículos
# ---------------------------------------------------------------------------
class _FamiliaDialog(QDialog):
    """Alta/edición de una familia (frameless, estilo de la app)."""

    def __init__(self, parent=None, familia=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(460)

        main_lyt = QVBoxLayout(self)
        cont = QFrame()
        cont.setStyleSheet(f"""
            QFrame {{ background-color: {_PANEL_BG}; border: 2px solid {_CIAN}; border-radius: 15px; }}
            QLabel {{ color: white; border: none; font-family: 'Segoe UI'; font-weight: bold; }}
        """)
        main_lyt.addWidget(cont)
        ly = QVBoxLayout(cont)
        ly.setContentsMargins(30, 30, 30, 30)
        ly.setSpacing(14)

        titulo = (tr("info.fam_edit", default="EDITAR FAMILIA") if familia
                  else tr("info.fam_new", default="NUEVA FAMILIA"))
        lbl_t = QLabel(titulo)
        lbl_t.setStyleSheet(f"color:{_CIAN};font-size:15px;font-weight:900;border:none;")
        ly.addWidget(lbl_t)

        ly.addWidget(QLabel(tr("info.fam_name", default="NOMBRE:")))
        self.in_nombre = QLineEdit((familia or {}).get("nombre", ""))
        self.in_nombre.setPlaceholderText(tr("info.fam_name_ph", default="Ej.: Bebidas, Lácteos, Limpieza..."))
        self.in_nombre.setStyleSheet(_NEON_INPUT_SS)
        ly.addWidget(self.in_nombre)

        ly.addWidget(QLabel(tr("info.fam_desc", default="DESCRIPCIÓN (opcional):")))
        self.in_desc = QLineEdit((familia or {}).get("descripcion") or "")
        self.in_desc.setStyleSheet(_NEON_INPUT_SS)
        ly.addWidget(self.in_desc)

        # Venta restringida (verificación de edad): la FAMILIA es la fuente única de categorización; el
        # autocobro usa este flag. El AUTOCOBRO es EXCLUSIVO de la edición Supermarket → el checkbox solo se
        # muestra ahí (`verticales.visible("tpv.autocobro")`). En otras ediciones se conserva el valor previo.
        self._restr_original = bool((familia or {}).get("restringida"))
        self.chk_restr = None
        try:
            from src.services import verticales as _vert
            _autocobro = _vert.visible("tpv.autocobro")
        except Exception:
            _autocobro = True
        if _autocobro:
            from PyQt6.QtWidgets import QCheckBox
            self.chk_restr = QCheckBox(tr("info.fam_restr", default="Venta restringida (verificación de edad)"))
            self.chk_restr.setChecked(self._restr_original)
            self.chk_restr.setStyleSheet("color:white;font-weight:bold;border:none;")
            ly.addWidget(self.chk_restr)

        btn_lyt = QHBoxLayout()
        btn_save = QPushButton(tr("info.save_changes", default="GUARDAR CAMBIOS"))
        btn_save.setStyleSheet(_BTN_CIAN_SS)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton(tr("info.cancel", default="CANCELAR"))
        btn_cancel.setStyleSheet(
            "background-color: #30363D; color: white; border-radius: 10px; padding: 10px; font-weight: bold;")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_lyt.addWidget(btn_save)
        btn_lyt.addWidget(btn_cancel)
        ly.addLayout(btn_lyt)

    def datos(self):
        return {
            "nombre": self.in_nombre.text().strip(),
            "descripcion": self.in_desc.text().strip() or None,
            # Si el checkbox no se muestra (ediciones sin autocobro), se conserva el valor previo.
            "restringida": self.chk_restr.isChecked() if self.chk_restr is not None else self._restr_original,
        }


class _PrecioMasivoDialog(QDialog):
    """Operación masiva de precio/IVA sobre todos los artículos de una familia."""

    # (etiqueta, modo, sufijo)
    _MODOS = [
        ("info.pm_pct", "Ajustar precio (%)", "pct", "%"),
        ("info.pm_fijo", "Fijar P.V.P.", "fijo", "€"),
        ("info.pm_iva", "Fijar IVA (%)", "iva", "%"),
    ]

    def __init__(self, parent=None, familia_nombre=""):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(460)

        main_lyt = QVBoxLayout(self)
        cont = QFrame()
        cont.setStyleSheet(f"""
            QFrame {{ background-color: {_PANEL_BG}; border: 2px solid {_CIAN}; border-radius: 15px; }}
            QLabel {{ color: white; border: none; font-family: 'Segoe UI'; font-weight: bold; }}
        """)
        main_lyt.addWidget(cont)
        ly = QVBoxLayout(cont)
        ly.setContentsMargins(30, 30, 30, 30)
        ly.setSpacing(14)

        lbl_t = QLabel(tr("info.pm_title", default="PRECIO / IVA MASIVO"))
        lbl_t.setStyleSheet(f"color:{_CIAN};font-size:15px;font-weight:900;border:none;")
        ly.addWidget(lbl_t)
        lbl_f = QLabel(tr("info.pm_family", default="Familia: {f}", f=familia_nombre))
        lbl_f.setStyleSheet("color:#8B949E;font-size:12px;border:none;")
        lbl_f.setWordWrap(True)
        ly.addWidget(lbl_f)

        ly.addWidget(QLabel(tr("info.pm_op", default="OPERACIÓN:")))
        self.cmb_modo = QComboBox()
        self.cmb_modo.setStyleSheet(_NEON_COMBO_SS)
        for ikey, txt, modo, _suf in self._MODOS:
            self.cmb_modo.addItem(tr(ikey, default=txt), modo)
        ly.addWidget(self.cmb_modo)

        ly.addWidget(QLabel(tr("info.pm_value", default="VALOR (usa negativo para bajar el %):")))
        self.in_valor = QLineEdit()
        self.in_valor.setPlaceholderText("Ej.: 10  /  -5  /  9.99")
        self.in_valor.setStyleSheet(_NEON_INPUT_SS)
        ly.addWidget(self.in_valor)

        btn_lyt = QHBoxLayout()
        btn_ok = QPushButton(tr("info.pm_apply", default="APLICAR"))
        btn_ok.setStyleSheet(_BTN_CIAN_SS); btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton(tr("info.cancel", default="CANCELAR"))
        btn_cancel.setStyleSheet(
            "background-color: #30363D; color: white; border-radius: 10px; padding: 10px; font-weight: bold;")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_lyt.addWidget(btn_ok); btn_lyt.addWidget(btn_cancel)
        ly.addLayout(btn_lyt)

    def datos(self):
        return self.cmb_modo.currentData(), self.in_valor.text().strip()


class _FamiliasPage(QWidget):
    """Gestión de familias: crear/editar/eliminar + asignar/quitar artículos de la familia."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self._cargado = False

        root = QHBoxLayout(self)
        root.setContentsMargins(30, 30, 30, 30)
        root.setSpacing(24)

        # ── Columna izquierda: lista de familias + acciones ──
        col_izq = QVBoxLayout()
        col_izq.setSpacing(12)
        lbl_fam = QLabel(tr("info.fam_families", default="FAMILIAS"))
        lbl_fam.setStyleSheet(f"color:{_CIAN};font-size:16px;font-weight:900;letter-spacing:2px;border:none;")
        col_izq.addWidget(lbl_fam)

        self.lista_fam = QListWidget()
        self.lista_fam.setStyleSheet(_LISTA_SS)
        self.lista_fam.setMinimumWidth(300)
        self.lista_fam.currentItemChanged.connect(lambda *_: self._cargar_articulos())
        col_izq.addWidget(self.lista_fam, 1)

        acc = QHBoxLayout(); acc.setSpacing(8)
        self.btn_nueva = _BotonMas(tr("info.fam_new", default="NUEVA"))
        self.btn_editar = QPushButton("✏️ " + tr("info.fam_edit", default="EDITAR"))
        self.btn_borrar = QPushButton("🗑 " + tr("info.fam_del", default="ELIMINAR"))
        for b in (self.btn_nueva, self.btn_editar):
            b.setStyleSheet(_BTN_CIAN_SS); b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_borrar.setStyleSheet(_ss_boton("#F85149")); self.btn_borrar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_nueva.clicked.connect(self._nueva)
        self.btn_editar.clicked.connect(self._editar)
        self.btn_borrar.clicked.connect(self._eliminar)
        acc.addWidget(self.btn_nueva); acc.addWidget(self.btn_editar); acc.addWidget(self.btn_borrar)
        col_izq.addLayout(acc)
        root.addLayout(col_izq, 1)

        # ── Columna derecha: artículos de la familia seleccionada ──
        col_der = QVBoxLayout()
        col_der.setSpacing(12)
        self.lbl_art = QLabel(tr("info.fam_articles", default="ARTÍCULOS DE LA FAMILIA"))
        self.lbl_art.setStyleSheet("color:#FFFFFF;font-size:16px;font-weight:900;letter-spacing:1px;border:none;")
        col_der.addWidget(self.lbl_art)

        add_row = QHBoxLayout(); add_row.setSpacing(8)
        self.in_add = QLineEdit()
        self.in_add.setPlaceholderText(tr("info.fam_add_ph", default="Código o nombre del artículo a añadir..."))
        self.in_add.setStyleSheet(_NEON_INPUT_SS)
        completer = QCompleter(); model = QStringListModel(); completer.setModel(model)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        if estilizar_completer:
            estilizar_completer(completer)
        model.setStringList(_get_completer_data())
        self.in_add.setCompleter(completer)
        self.in_add.returnPressed.connect(self._anadir)
        self.btn_add = _BotonMas(tr("info.fam_add", default="AÑADIR"))
        self.btn_add.setStyleSheet(_BTN_CIAN_SS); self.btn_add.setFixedWidth(150)
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(self._anadir)
        add_row.addWidget(self.in_add, 1); add_row.addWidget(self.btn_add)
        col_der.addLayout(add_row)

        self.lista_art = QListWidget()
        self.lista_art.setStyleSheet(_LISTA_SS)
        col_der.addWidget(self.lista_art, 1)

        fila_der = QHBoxLayout(); fila_der.setSpacing(8)
        self.btn_quitar = QPushButton("✕ " + tr("info.fam_remove", default="QUITAR DE LA FAMILIA"))
        self.btn_quitar.setStyleSheet(_ss_boton("#F85149")); self.btn_quitar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_quitar.clicked.connect(self._quitar)
        self.btn_masivo = QPushButton("💲 " + tr("info.pm_title", default="PRECIO / IVA MASIVO"))
        self.btn_masivo.setStyleSheet(_BTN_CIAN_SS); self.btn_masivo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_masivo.clicked.connect(self._precio_masivo)
        fila_der.addWidget(self.btn_quitar); fila_der.addWidget(self.btn_masivo)
        col_der.addLayout(fila_der)
        root.addLayout(col_der, 2)

    # ── datos ──
    def showEvent(self, e):
        super().showEvent(e)
        if not self._cargado:
            self._cargado = True
            self._cargar_familias()

    def _sel_familia_id(self):
        it = self.lista_fam.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _cargar_familias(self, sel_id=None):
        from src.db.familias import contar_por_familia, listar_familias
        self.lista_fam.blockSignals(True)
        self.lista_fam.clear()
        conteo = contar_por_familia()
        objetivo = None
        for f in listar_familias():
            n = conteo.get(f["id"], 0)
            it = QListWidgetItem(f"{f['nombre']}   ({n})")
            it.setData(Qt.ItemDataRole.UserRole, f["id"])
            self.lista_fam.addItem(it)
            if f["id"] == sel_id:
                objetivo = it
        self.lista_fam.blockSignals(False)
        if objetivo is not None:
            self.lista_fam.setCurrentItem(objetivo)
        elif self.lista_fam.count():
            self.lista_fam.setCurrentRow(0)
        else:
            self._cargar_articulos()

    def _cargar_articulos(self):
        from src.db.familias import articulos_de_familia
        self.lista_art.clear()
        fid = self._sel_familia_id()
        if fid is None:
            return
        for a in articulos_de_familia(fid):
            it = QListWidgetItem(f"{a['codigo']}   —   {a.get('nombre') or ''}")
            it.setData(Qt.ItemDataRole.UserRole, a["codigo"])
            self.lista_art.addItem(it)

    # ── CRUD familias ──
    def _nueva(self):
        from src.db.familias import crear_familia
        dlg = _FamiliaDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            d = dlg.datos()
            if not d["nombre"]:
                return
            fid = crear_familia(d["nombre"], descripcion=d["descripcion"],
                                restringida=d.get("restringida", False))
            self._cargar_familias(sel_id=fid)

    def _editar(self):
        from src.db.familias import actualizar_familia, obtener_familia
        fid = self._sel_familia_id()
        if fid is None:
            return
        dlg = _FamiliaDialog(self, familia=obtener_familia(fid))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            d = dlg.datos()
            if not d["nombre"]:
                return
            actualizar_familia(fid, nombre=d["nombre"], descripcion=d["descripcion"],
                               restringida=1 if d.get("restringida") else 0)
            self._cargar_familias(sel_id=fid)

    def _eliminar(self):
        from src.db.familias import eliminar_familia
        fid = self._sel_familia_id()
        if fid is None:
            return
        it = self.lista_fam.currentItem()
        if mostrar_confirmacion:
            ok = mostrar_confirmacion(
                self, tr("info.fam_del", default="ELIMINAR"),
                tr("info.fam_del_msg",
                   default="¿Eliminar la familia «{f}»? Los artículos quedarán SIN familia (no se borran).",
                   f=it.text() if it else ""))
            if not ok:
                return
        eliminar_familia(fid)
        self._cargar_familias()

    # ── asignación de artículos ──
    def _anadir(self):
        from src.db.conexion import obtener_articulo
        from src.db.familias import asignar_familia
        fid = self._sel_familia_id()
        if fid is None:
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("info.fam_families", default="FAMILIAS"),
                                tr("info.fam_pick", default="Selecciona primero una familia."), nivel="warning")
            return
        q = self.in_add.text().strip()
        if q and "–" in q:
            q = q.split("–")[0].strip()
        if not q:
            return
        art = obtener_articulo(q)
        if not art:
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("info.not_found_title", default="No Encontrado"),
                                tr("info.not_found_msg", default="No se encontró información para: {q}", q=q),
                                nivel="warning")
            return
        asignar_familia(art.get("codigo"), fid)
        self.in_add.clear()
        self._cargar_familias(sel_id=fid)

    def _quitar(self):
        from src.db.familias import asignar_familia
        fid = self._sel_familia_id()
        it = self.lista_art.currentItem()
        if fid is None or it is None:
            return
        if mostrar_confirmacion:
            ok = mostrar_confirmacion(
                self, tr("info.fam_remove", default="QUITAR DE LA FAMILIA"),
                tr("info.fam_remove_msg",
                   default="¿Quitar «{a}» de la familia? El artículo no se borra, solo deja de pertenecer a ella.",
                   a=it.text()))
            if not ok:
                return
        asignar_familia(it.data(Qt.ItemDataRole.UserRole), None)
        self._cargar_familias(sel_id=fid)

    def _precio_masivo(self):
        from src.db.familias import cambiar_precio_masivo
        fid = self._sel_familia_id()
        if fid is None:
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("info.pm_title", default="PRECIO / IVA MASIVO"),
                                tr("info.fam_pick", default="Selecciona primero una familia."), nivel="warning")
            return
        it = self.lista_fam.currentItem()
        dlg = _PrecioMasivoDialog(self, familia_nombre=it.text() if it else "")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        modo, valor = dlg.datos()
        if not valor:
            return
        n = cambiar_precio_masivo(fid, modo, valor)
        if mostrar_mensaje:
            mostrar_mensaje(self, tr("info.pm_title", default="PRECIO / IVA MASIVO"),
                            tr("info.pm_ok", default="Operación aplicada a {n} artículo(s).", n=n),
                            nivel="success" if n else "warning")
        self._cargar_articulos()

    def _retraducir(self):
        # Recarga de textos estáticos; el contenido dinámico se refresca al reentrar.
        pass


# ============================================================
# BLOQUE HILO DE VÍDEO Y DECODIFICACIÓN DE CÓDIGOS
# ============================================================


class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(QImage)
    code_detected = pyqtSignal(str, object)  # código y tipo

    def __init__(self, camera_index=0, parent=None):
        super().__init__(parent)
        self._run_flag = True
        self.camera_index = camera_index

    def preprocesar_frame(self, frame):
        """Convierte a gris, ecualiza histograma y binariza adaptativamente."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        eq = cv2.equalizeHist(gray)
        binarizado = cv2.adaptiveThreshold(
            eq, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 25, 10
        )
        return binarizado

    def try_decode(self, frame):
        """Intenta decodificar con rotaciones clásicas y ±10°. Devuelve (código, tipo)."""
        frame_proc = self.preprocesar_frame(frame)
        angles = [0, 10, -10, 90, 100, 80, 180, 190, 170, 270, 280, 260]

        for angle in angles:
            if angle != 0:
                h, w = frame_proc.shape
                M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1)
                rotated = cv2.warpAffine(frame_proc, M, (w, h))
            else:
                rotated = frame_proc

            try:
                codes = decode(rotated)
            except Exception:
                continue

            if codes:
                code_obj = codes[0]
                raw = code_obj.data
                tipo = code_obj.type
                for enc in ("utf-8", "cp1252", "latin-1"):
                    try:
                        return raw.decode(enc), tipo
                    except Exception:
                        pass
                return raw.decode("utf-8", errors="ignore"), tipo

        return None, None

    def run(self):
        cap = cv2.VideoCapture(
            self.camera_index, cv2.CAP_DSHOW if os.name == "nt" else 0
        )
        if not cap.isOpened():
            return

        while self._run_flag:
            ret, frame = cap.read()
            if not ret:
                break

            text, tipo = self.try_decode(frame)
            if text is not None:
                self.code_detected.emit(text, tipo)

            rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            qt_image = QImage(rgb_image.data, w, h, ch * w, QImage.Format.Format_RGB888)
            self.change_pixmap_signal.emit(qt_image)

        cap.release()

    def stop(self):
        self._run_flag = False
        self.wait(timeout=2000)


# ============================================================
# BLOQUE ESCÁNER DE CÓDIGO DE BARRAS (DIÁLOGO DE CÁMARA)
# ============================================================


class BarcodeScanner(QDialog):
    """Ventana que muestra la cámara y detecta códigos 360° con audio de error."""

    def __init__(self, callback, camera_index=0, parent=None):
        super().__init__(parent)
        self.callback = callback
        self._codigo_presente = False
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        if construir_plantilla_camara is not None:
            plantilla = construir_plantilla_camara(
                self,
                titulo=tr("info.cam_title", default="VISIÓN - ARTÍCULO"),
                texto_video="",
                estado_inicial=tr("info.cam_status", default="ALINEE EL CÓDIGO CON EL SENSOR"),
                texto_boton_primario=tr("info.cam_start", default="INICIAR ESCANEO"),
                texto_boton_cancelar=tr("info.cam_abort", default="ABORTAR OPERACIÓN"),
                ancho=600,
                alto=480,
                ancho_video=520,
                alto_video=280,
                mostrar_boton_primario=False,
                object_name_dialog="scanner_dialog",
                object_name_frame="cuerpo_ventana_scan",
            )
            self.layout = plantilla["layout"]
            self.video_label = plantilla["lbl_video"]
            self.video_label.setText("")
            self.hint_label = plantilla["lbl_status"]
            self.hint_label.setObjectName("lbl_info_scan")
            self.hint_label.setText(tr("info.cam_hint", default="APUNTA CON LA CÁMARA AL CÓDIGO DE BARRAS O QR"))
            self.error_label = QLabel("")
            self.error_label.setObjectName("lbl_info_scan")
            self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout.insertWidget(3, self.error_label)
            btn_cancel = plantilla["btn_cancelar"]
            btn_cancel.clicked.connect(self._on_cancel)
            if aplicar_estilo_widget is not None:
                for w in (
                    self.video_label,
                    self.hint_label,
                    self.error_label,
                    btn_cancel,
                ):
                    aplicar_estilo_widget(w)
        else:
            self.setStyleSheet("background-color: #1A1D24; border-radius: 8px;")
            self.resize(600, 400)
            self.layout = QVBoxLayout(self)
            self.layout.setContentsMargins(8, 8, 8, 8)
            self.layout.setSpacing(6)
            self.video_label = QLabel()
            self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.video_label.setStyleSheet(
                "background-color: black; border-radius: 6px;"
            )
            self.layout.addWidget(self.video_label)
            self.hint_label = QLabel(
                tr("info.cam_hint_long",
                   default="Apunta con la cámara al código de barras o QR. Se detectará automáticamente.")
            )
            self.hint_label.setStyleSheet("color: white; padding: 4px;")
            self.layout.addWidget(self.hint_label)
            self.error_label = QLabel("")
            self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.error_label.setStyleSheet(
                "color: red; font-weight: bold; padding: 4px;"
            )
            self.layout.addWidget(self.error_label)
            btn_cancel = QPushButton(tr("common.cancel", default="Cancelar"))
            btn_cancel.clicked.connect(self._on_cancel)
            btn_cancel.setStyleSheet("""
                QPushButton {
                    background-color: #FF4B4B; color: white; font-weight: bold;
                    border-radius: 10px; padding: 8px;
                }
                QPushButton:hover { background-color: #FF2222; }
            """)
            btn_cancel.setFont(QFont("Segoe UI", 10))
            btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
            self.layout.addWidget(btn_cancel, alignment=Qt.AlignmentFlag.AlignRight)

        # Sonido de error
        self.error_player = QMediaPlayer()
        self.error_audio = QAudioOutput()
        self.error_player.setAudioOutput(self.error_audio)
        sound_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "assets",
            "error.wav",
        )
        self.error_player.setSource(QUrl.fromLocalFile(sound_path))
        self.error_audio.setVolume(0.9)

        # Hilo de cámara
        self.thread = VideoThread(camera_index=camera_index)
        self.thread.change_pixmap_signal.connect(self.update_image)
        self.thread.code_detected.connect(self.callback)
        self.thread.start()

    def update_image(self, qt_image):
        pix = QPixmap.fromImage(qt_image)
        if not pix.isNull():
            scaled = pix.scaled(
                self.video_label.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (scaled.width() - self.video_label.width()) // 2
            y = (scaled.height() - self.video_label.height()) // 2
            self.video_label.setPixmap(
                scaled.copy(x, y, self.video_label.width(), self.video_label.height())
            )
            # Máscara redondeada para recortar esquinas del vídeo
            from PyQt6.QtGui import QPainterPath, QRegion

            p = QPainterPath()
            p.addRoundedRect(
                0.0,
                0.0,
                float(self.video_label.width()),
                float(self.video_label.height()),
                14.0,
                14.0,
            )
            self.video_label.setMask(QRegion(p.toFillPolygon().toPolygon()))

    def show_error(self, mensaje="Código no válido"):
        """Muestra error temporal y reproduce sonido de alerta."""
        self.error_label.setText(f"ERROR: {mensaje}")
        QTimer.singleShot(3000, lambda: self.error_label.clear())
        if self.error_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.error_player.stop()
            self.error_player.play()

    def _on_cancel(self):
        self.close()

    def closeEvent(self, event):
        try:
            if hasattr(self, "thread") and self.thread is not None:
                self.thread.stop()
        except Exception:
            pass
        event.accept()


# ---------------------------------------------------------------------------
# ALTA RÁPIDA Y GENERADOR EAN-13
# ---------------------------------------------------------------------------
class _AltaRapidaEANPage(QWidget):
    """Alta rápida de un artículo NUEVO con generador de EAN-13 válido y único. Da de alta en la tabla
    PERMANENTE `articulos` para que quede disponible al instante en el buscador de Pedidos (Proveedores)."""

    _UNIDADES = ["unidad", "kg", "caja", "saco", "palé", "litro", "docena"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._imagen_path = None
        cont = QVBoxLayout(self)
        cont.setContentsMargins(40, 34, 40, 34); cont.setSpacing(14)

        titulo = QLabel(tr("info.ean_titulo", default="⚡ Alta Rápida y Generador EAN-13"))
        titulo.setStyleSheet(f"color:{_CIAN};font-size:22px;font-weight:900;background:transparent;")
        cont.addWidget(titulo)
        sub = QLabel(tr("info.ean_sub", default="Crea un artículo nuevo y genera su código de barras "
                                                "EAN-13 único para negociarlo con nuevos distribuidores."))
        sub.setStyleSheet(f"color:#8B949E;font-size:12px;background:transparent;"); sub.setWordWrap(True)
        cont.addWidget(sub)

        def _lbl(txt):
            l = QLabel(txt); l.setStyleSheet("color:#8B949E;font-weight:700;font-size:12px;"
                                             "background:transparent;")
            return l

        self.in_nombre = QLineEdit(); self.in_nombre.setPlaceholderText(
            tr("info.ean_nombre", default="Nombre del artículo nuevo"))
        self.in_nombre.setStyleSheet(_NEON_INPUT_SS)
        self.cmb_familia = QComboBox(); self.cmb_familia.setStyleSheet(_NEON_COMBO_SS)
        self.cmb_unidad = QComboBox(); self.cmb_unidad.setStyleSheet(_NEON_COMBO_SS)
        self.cmb_unidad.addItems(self._UNIDADES)
        self.in_precio = QLineEdit(); self.in_precio.setPlaceholderText("0.00")
        self.in_precio.setStyleSheet(_NEON_INPUT_SS); self.in_precio.setFixedWidth(200)

        cont.addWidget(_lbl(tr("info.ean_nombre_lbl", default="Nombre del artículo *")))
        cont.addWidget(self.in_nombre)
        fila = QHBoxLayout()
        colf = QVBoxLayout(); colf.addWidget(_lbl(tr("info.ean_familia", default="Categoría / Familia")))
        colf.addWidget(self.cmb_familia)
        colu = QVBoxLayout(); colu.addWidget(_lbl(tr("info.ean_unidad", default="Unidad de medida")))
        colu.addWidget(self.cmb_unidad)
        colp = QVBoxLayout(); colp.addWidget(_lbl(tr("info.ean_precio", default="Precio de referencia (€)")))
        colp.addWidget(self.in_precio)
        fila.addLayout(colf, 2); fila.addLayout(colu, 1); fila.addLayout(colp, 1)
        cont.addLayout(fila)

        # Imagen opcional
        imgrow = QHBoxLayout()
        self.btn_img = QPushButton(tr("info.ean_img", default="🖼  Cargar imagen (opcional)"))
        self.btn_img.setStyleSheet(_BTN_CIAN_SS); self.btn_img.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_img.clicked.connect(self._elegir_imagen)
        self.lbl_img = _lbl("")
        imgrow.addWidget(self.btn_img); imgrow.addWidget(self.lbl_img, 1)
        cont.addLayout(imgrow)

        # EAN generado
        eanrow = QHBoxLayout()
        self.in_ean = QLineEdit(); self.in_ean.setReadOnly(True)
        self.in_ean.setPlaceholderText(tr("info.ean_ph", default="EAN-13 (pulsa Generar)"))
        self.in_ean.setStyleSheet(_NEON_INPUT_SS); self.in_ean.setFixedWidth(280)
        self.btn_gen = QPushButton(tr("info.ean_generar", default="⚡ Generar EAN-13 único"))
        self.btn_gen.setStyleSheet(_ss_boton(_VERDE)); self.btn_gen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_gen.clicked.connect(self._generar_ean)
        eanrow.addWidget(_lbl(tr("info.ean_lbl", default="Código EAN-13"))); eanrow.addWidget(self.in_ean)
        eanrow.addWidget(self.btn_gen); eanrow.addStretch(1)
        cont.addLayout(eanrow)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setStyleSheet("color:#8B949E;font-size:12px;background:transparent;")
        cont.addWidget(self.lbl_estado)

        self.btn_guardar = QPushButton(tr("info.ean_guardar", default="💾  Guardar artículo en catálogo"))
        self.btn_guardar.setStyleSheet(_BTN_CIAN_SS); self.btn_guardar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_guardar.clicked.connect(self._guardar)
        brow = QHBoxLayout(); brow.addWidget(self.btn_guardar); brow.addStretch(1)
        cont.addLayout(brow)
        cont.addStretch(1)
        self._cargar_familias()

    def showEvent(self, e):   # noqa: N802 (API Qt): refresca familias al mostrar
        super().showEvent(e)
        self._cargar_familias()

    def _cargar_familias(self):
        self.cmb_familia.clear()
        self.cmb_familia.addItem(tr("info.ean_sin_familia", default="— Sin familia —"), None)
        try:
            from src.db import familias
            for f in familias.listar_familias():
                self.cmb_familia.addItem(f.get("nombre"), f.get("id_familia"))
        except Exception:
            pass

    def _estado(self, txt, error=False, ok=False):
        col = _ROJO if error else (_VERDE if ok else "#8B949E")
        self.lbl_estado.setText(txt)
        self.lbl_estado.setStyleSheet(f"color:{col};font-size:12px;font-weight:700;background:transparent;")

    def _elegir_imagen(self):
        from PyQt6.QtWidgets import QFileDialog
        ruta, _ = QFileDialog.getOpenFileName(self, tr("info.ean_img", default="Cargar imagen"), "",
                                              "Imágenes (*.png *.jpg *.jpeg *.webp);;Todos (*)")
        if ruta:
            self._imagen_path = ruta
            self.lbl_img.setText(os.path.basename(ruta))

    def _generar_ean(self):
        from src.db import articulos as A
        from src.utils import ean
        codigo = ean.generar(existe_fn=lambda c: A.existe_codigo(c))
        if not codigo:
            self._estado(tr("info.ean_err_gen", default="No se pudo generar un EAN único. Reinténtalo."),
                         error=True)
            return
        self.in_ean.setText(codigo)
        self._estado(tr("info.ean_ok_gen", default="EAN-13 válido generado: {c}", c=codigo), ok=True)

    def _guardar(self):
        from src.db import articulos as A
        from src.utils import ean
        nombre = (self.in_nombre.text() or "").strip()
        if not nombre:
            self._estado(tr("info.ean_falta_nombre", default="El nombre es obligatorio."), error=True); return
        if A.existe_nombre(nombre):
            self._estado(tr("info.ean_dup_nombre", default="Ya existe un artículo con ese nombre."),
                         error=True); return
        codigo = (self.in_ean.text() or "").strip()
        if not ean.es_valido(codigo):
            self._estado(tr("info.ean_falta_ean", default="Genera primero un EAN-13 válido."), error=True)
            return
        if A.existe_codigo(codigo):
            self._estado(tr("info.ean_dup_ean", default="Ese EAN ya existe; genera otro."), error=True); return
        try:
            precio = float((self.in_precio.text() or "0").replace(",", "."))
        except ValueError:
            self._estado(tr("info.ean_precio_num", default="El precio debe ser numérico."), error=True); return
        id_fam = self.cmb_familia.currentData()
        categoria = self.cmb_familia.currentText() if id_fam else None
        ok = A.crear_articulo(codigo, nombre, precio=precio, categoria=categoria, id_familia=id_fam,
                              unidad=self.cmb_unidad.currentText(), imagen=self._imagen_path)
        if ok:
            self._estado(tr("info.ean_guardado",
                            default="Artículo «{n}» dado de alta con EAN {c}. Ya disponible en Pedidos.",
                            n=nombre, c=codigo), ok=True)
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("info.ean_titulo2", default="Alta de artículo"),
                                tr("info.ean_guardado2", default="Artículo creado correctamente."),
                                nivel="success")
            for w in (self.in_nombre, self.in_ean, self.in_precio):
                w.clear()
            self._imagen_path = None; self.lbl_img.setText("")
        else:
            self._estado(tr("info.ean_err_save", default="No se pudo dar de alta el artículo."), error=True)

    def _retraducir(self):
        pass


# ---------------------------------------------------------------------------
# VENTANA PRINCIPAL
# ---------------------------------------------------------------------------


class InfoArticuloWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, **kwargs):
        super().__init__()
        self.callback_vuelta = callback_vuelta
        self.usuario_actual = usuario

        self.setWindowTitle(tr("info.window_title", default="Información de Artículo"))
        self.setMinimumSize(1024, 680)  # responsive (P2): apto tablet (antes 1100x750)
        self.setStyleSheet(f"background-color: {_FONDO}; color: white;")

        self.setup_ui()
        i18n.conectar_retraduccion(self, self._retraducir)

        # P3 (UX-TPV-01): sidebar colapsable con persistencia por usuario.
        try:
            from src.gui.sidebar_colapsable import instalar_sidebar_colapsable
            if getattr(self, "sidebar", None) is not None:
                instalar_sidebar_colapsable(self, self.sidebar, usuario=self.usuario_actual, clave="info_articulo")
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

        lbl_m = QLabel(tr("info.smart_info", default="SMART INFO"))
        lbl_m.setStyleSheet(
            "color: #ffffff; font-size: 16px; font-weight: 900; margin-left: 30px; "
            "margin-bottom: 35px; letter-spacing: 2px; border: none; background: transparent;"
        )
        side_ly.addWidget(lbl_m)

        self._tab_keys = ["info.tab_search", "info.tab_image", "info.tab_edit", "info.tab_families",
                          "info.tab_ean"]
        _tab_def = ["BUSCAR ARTÍCULO", "IMAGEN ARTÍCULO", "EDITAR ARTÍCULO", "FAMILIAS",
                    "ALTA RÁPIDA · EAN-13"]

        self._nav_btns = []
        for idx, key in enumerate(self._tab_keys):
            btn = _SidebarBtn(tr(key, default=_tab_def[idx]))
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.clicked.connect(lambda _, i=idx: self._ir_a(i))
            side_ly.addWidget(btn)
            self._nav_btns.append(btn)

        side_ly.addStretch()

        self._btn_exit = btn_exit = _SidebarBtn(tr("info.exit", default="SALIR AL MENÚ"))
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
        self._page_buscar = _BuscarArticuloPage(self)
        self._page_imagen = _ImagenArticuloPage(self)
        self._page_editar = _EditarArticuloPage(self)
        self._page_familias = _FamiliasPage(self)
        self._page_ean = _AltaRapidaEANPage(self)

        self._vistas.addWidget(self._page_buscar)
        self._vistas.addWidget(self._page_imagen)
        self._vistas.addWidget(self._page_editar)
        self._vistas.addWidget(self._page_familias)
        self._vistas.addWidget(self._page_ean)

        root.addWidget(self._vistas)
        self._ir_a(0)

    def _retraducir(self):
        self.setWindowTitle(tr("info.window_title", default="Información de Artículo"))
        _tab_def = ["BUSCAR ARTÍCULO", "IMAGEN ARTÍCULO", "EDITAR ARTÍCULO", "FAMILIAS",
                    "ALTA RÁPIDA · EAN-13"]
        for i, btn in enumerate(self._nav_btns):
            btn.setText(tr(self._tab_keys[i], default=_tab_def[i]))
        self._btn_exit.setText(tr("info.exit", default="SALIR AL MENÚ"))
        for page in (self._page_buscar, self._page_imagen, self._page_editar, self._page_familias,
                     self._page_ean):
            if hasattr(page, "_retraducir"):
                page._retraducir()

    def _ir_a(self, index):
        self._vistas.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_btns):
            btn.setChecked(i == index)
            if repolish_widget:
                repolish_widget(btn)

    def abrir_escanner(self):
        try:
            _ = cv2.__version__  # Check if OpenCV is available
        except Exception:
            if mostrar_mensaje:
                mostrar_mensaje(
                    self,
                    tr("info.opencv_error_title", default="Error"),
                    tr("info.opencv_error_msg",
                       default="OpenCV no está disponible. Instala opencv-python y pyzbar."),
                    nivel="error",
                )
            return
        self.scanner = BarcodeScanner(self._on_barcode_detected, parent=self)
        self.scanner.exec()

    def _on_barcode_detected(self, code, tipo=None):
        if code:
            self.scanner.close()
            self._page_buscar._buscar(code)

    def volver_menu_principal(self):
        if self.callback_vuelta:
            self.callback_vuelta()
        self.close()
