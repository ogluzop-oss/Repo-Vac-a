# src/gui/info_articulo.py
import os

import cv2
from PyQt6.QtCore import QStringListModel, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPixmap
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QCompleter,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
    obtener_conexion,
    ventas_semana,
)
from src.utils import i18n
from src.utils.i18n import tr

try:
    from assets.estilo_global import (
        aplicar_estilo_widget,
        construir_plantilla_camara,
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
# COMPONENTES AUXILIARES
# ---------------------------------------------------------------------------


def _get_completer_data():
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT codigo, nombre FROM articulos")
                rows = cur.fetchall()
                data = []
                for r in rows:
                    if r[0]:
                        data.append(str(r[0]))
                    if r[1]:
                        data.append(str(r[1]))
                return sorted(list(set(data)))
    except Exception:
        return []


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

        # Search area
        search_container = QHBoxLayout()
        search_container.setSpacing(10)  # Reduce el espacio entre la barra y el botón
        search_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(tr("info.search_ph", default="Introduce código o nombre del artículo..."))
        self.search_bar.setStyleSheet(_NEON_INPUT_SS)
        self.search_bar.setFixedWidth(500)  # Ajustar ancho a 500px
        self.search_bar.returnPressed.connect(self._buscar)

        self._btn_scan = btn_scan = QPushButton("📷 " + tr("info.scan", default="SCAN"))
        btn_scan.setFixedSize(110, 55)
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
        res_lyt.addWidget(self.lbl_foto)

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

        scroll.setWidget(info_widget)
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
        self.search_bar.textChanged.connect(self._update_suggestions)

    def _update_suggestions(self):
        if len(self.search_bar.text()) >= 2:
            data = _get_completer_data()
            self.completer_model.setStringList(data)

    def _retraducir(self):
        self.search_bar.setPlaceholderText(
            tr("info.search_ph", default="Introduce código o nombre del artículo...")
        )
        self._btn_scan.setText("📷 " + tr("info.scan", default="SCAN"))
        for key, ikey, text in self._fields_def:
            self._field_titles[key].setText(tr(ikey, default=text))

    def _abrir_escanner(self):
        self.main_window.abrir_escanner()

    def _buscar(self, code=None):
        q = code or self.search_bar.text().strip()
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
            self.labels["PRECIO"].setText(f"{precio:.2f} €")

            self.labels["U_TIENDA"].setText(fmt(art.get("ubicacion_tienda")))
            self.labels["U_ALMACEN"].setText(fmt(art.get("ubicacion_almacen")))

            self.labels["RECEPCION"].setText(fmt(art.get("siguiente_recepcion")))
            self.labels["VENTAS"].setText(str(ventas_semana(art.get("codigo"))))

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

            self.result_frame.setVisible(True)
            self.search_bar.clear()

        except Exception as e:
            print(f"Error búsqueda: {e}")


class _ImagenArticuloPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(30)

        layout.addStretch(1)
        self.lbl_icon = QLabel("📸")  # Icono de cámara de fotos
        self.lbl_icon.setStyleSheet("font-size: 160px;")
        self.lbl_icon.setFixedHeight(200)  # Aumentado para evitar recorte
        layout.addSpacing(20)  # Espacio adicional entre icono y siguiente elemento
        layout.addWidget(self.lbl_icon, alignment=Qt.AlignmentFlag.AlignCenter)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(
            tr("info.image_search_ph", default="Introduce código o nombre para actualizar imagen...")
        )
        self.search_bar.setStyleSheet(_NEON_INPUT_SS)  # Mantener estilo neón
        self.search_bar.setFixedWidth(500)
        layout.addWidget(self.search_bar, alignment=Qt.AlignmentFlag.AlignCenter)

        # Completer para la barra de búsqueda
        self.completer = QCompleter()
        self.completer_model = QStringListModel()
        self.completer.setModel(self.completer_model)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.search_bar.setCompleter(self.completer)
        self.search_bar.textChanged.connect(self._update_suggestions)

        self._btn = btn = QPushButton(tr("info.select_item", default="SELECCIONAR ARTÍCULO"))
        btn.setStyleSheet(_BTN_CIAN_SS)
        btn.setFixedSize(250, 55)
        _sombra_cian(btn)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)

    def _retraducir(self):
        self.search_bar.setPlaceholderText(
            tr("info.image_search_ph", default="Introduce código o nombre para actualizar imagen...")
        )
        self._btn.setText(tr("info.select_item", default="SELECCIONAR ARTÍCULO"))

    def _update_suggestions(self):
        if len(self.search_bar.text()) >= 2:
            data = _get_completer_data()
            self.completer_model.setStringList(data)


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
        self.search_bar.setFixedWidth(500)
        layout.addWidget(self.search_bar, alignment=Qt.AlignmentFlag.AlignCenter)

        self._btn = btn = QPushButton(tr("info.search_for_edit", default="BUSCAR PARA EDITAR"))
        btn.setStyleSheet(_BTN_CIAN_SS)
        btn.setFixedSize(250, 55)
        _sombra_cian(btn)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)

    def _retraducir(self):
        self.search_bar.setPlaceholderText(tr("info.edit_search_ph", default="Introduce código o nombre para editar..."))
        self._btn.setText(tr("info.search_for_edit", default="BUSCAR PARA EDITAR"))


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


# ============================================================
# BLOQUE VENTANA DE INFORMACIÓN DE ARTÍCULO
# ============================================================


class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(QImage)
    code_detected = pyqtSignal(str, object)

    def __init__(self, camera_index=0, parent=None):
        super().__init__(parent)
        self._run_flag = True
        self.camera_index = camera_index

    def try_decode(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        codes = decode(gray)
        if codes:
            return codes[0].data.decode("utf-8"), codes[0].type
        return None, None

    def run(self):
        cap = cv2.VideoCapture(
            self.camera_index, cv2.CAP_DSHOW if os.name == "nt" else 0
        )
        while self._run_flag:
            ret, frame = cap.read()
            if not ret:
                break
            text, tipo = self.try_decode(frame)
            if text:
                self.code_detected.emit(text, tipo)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qt_image = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
            self.change_pixmap_signal.emit(qt_image)
        cap.release()

    def stop(self):
        self._run_flag = False
        self.wait(2000)


class BarcodeScanner(QDialog):
    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self.callback = callback
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        plantilla = construir_plantilla_camara(
            self, titulo=tr("info.cam_title", default="VISIÓN - ARTÍCULO"), mostrar_boton_primario=False
        )
        self.lbl_video = plantilla["lbl_video"]
        plantilla["btn_cancelar"].clicked.connect(self.close)

        self.thread = VideoThread()
        self.thread.change_pixmap_signal.connect(self._update_image)
        self.thread.code_detected.connect(self.callback)
        self.thread.start()

    def _update_image(self, qt_image):
        pix = QPixmap.fromImage(qt_image).scaled(
            self.lbl_video.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.lbl_video.setPixmap(pix)

    def closeEvent(self, event):
        self.thread.stop()
        event.accept()


# ---------------------------------------------------------------------------
# VENTANA PRINCIPAL
# ---------------------------------------------------------------------------


class InfoArticuloWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, **kwargs):
        super().__init__()
        self.callback_vuelta = callback_vuelta
        self.usuario_actual = usuario

        self.setWindowTitle(tr("info.window_title", default="Información de Artículo"))
        self.setMinimumSize(1100, 750)
        self.setStyleSheet(f"background-color: {_FONDO}; color: white;")

        self.setup_ui()
        i18n.conectar_retraduccion(self, self._retraducir)

    def setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- SIDEBAR ----
        sidebar = QFrame()
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

        self._tab_keys = ["info.tab_search", "info.tab_image", "info.tab_edit"]
        _tab_def = ["BUSCAR ARTÍCULO", "IMAGEN ARTÍCULO", "EDITAR ARTÍCULO"]

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

        self._vistas.addWidget(self._page_buscar)
        self._vistas.addWidget(self._page_imagen)
        self._vistas.addWidget(self._page_editar)

        root.addWidget(self._vistas)
        self._ir_a(0)

    def _retraducir(self):
        self.setWindowTitle(tr("info.window_title", default="Información de Artículo"))
        _tab_def = ["BUSCAR ARTÍCULO", "IMAGEN ARTÍCULO", "EDITAR ARTÍCULO"]
        for i, btn in enumerate(self._nav_btns):
            btn.setText(tr(self._tab_keys[i], default=_tab_def[i]))
        self._btn_exit.setText(tr("info.exit", default="SALIR AL MENÚ"))
        for page in (self._page_buscar, self._page_imagen, self._page_editar):
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
