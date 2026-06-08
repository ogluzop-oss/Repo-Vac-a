import logging
import os
import platform
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
import cv2
import qrcode
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleFactory,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from pyzbar import pyzbar
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Pre-importar reportlab con alias para el generador de PDF de reabastecimiento
try:
    from reportlab.lib import colors as _RL_COLORS
    from reportlab.lib.pagesizes import A4 as _RL_A4
    from reportlab.lib.styles import ParagraphStyle as _RL_PARASTYLE
    from reportlab.lib.styles import getSampleStyleSheet as _RL_STYLES
    from reportlab.lib.units import cm as _RL_CM
    from reportlab.platypus import (
        Paragraph as _RL_PARA,
    )
    from reportlab.platypus import (
        SimpleDocTemplate as _RL_DOC,
    )
    from reportlab.platypus import (
        Spacer as _RL_SPACER,
    )
    from reportlab.platypus import (
        Table as _RL_TABLE,
    )
    from reportlab.platypus import (
        TableStyle as _RL_TABLESTYLE,
    )
    _REPORTLAB_REAB_OK = True
except ImportError:
    _REPORTLAB_REAB_OK = False
from src.utils.i18n import tr
from src.db.conexion import (
    formatear_nombre_centro,
    obtener_articulo,
    obtener_conexion,
    obtener_configuracion,
    obtener_destinos_traspaso,
)
from src.db.logistica import (
    generar_id_traspaso,
    obtener_items_pale_traspaso,
)

try:
    from src.db.reabastecimiento import (
        cambiar_estado_propuesta as _reab_cambiar_estado_propuesta,
    )
    from src.db.reabastecimiento import (
        cargar_schedule as _reab_cargar_schedule,
    )
    from src.db.reabastecimiento import (
        crear_propuesta as _reab_crear_propuesta,
    )
    from src.db.reabastecimiento import (
        eliminar_config as _reab_eliminar_config,
    )
    from src.db.reabastecimiento import (
        guardar_schedule as _reab_guardar_schedule,
    )
    from src.db.reabastecimiento import (
        listar_config as _reab_listar_config,
    )
    from src.db.reabastecimiento import (
        listar_propuestas as _reab_listar_propuestas,
    )
    from src.db.reabastecimiento import (
        marcar_articulos_recibidos as _reab_marcar_articulos_recibidos,
    )
    from src.db.reabastecimiento import (
        marcar_envio_hoy as _reab_marcar_envio_hoy,
    )
    from src.db.reabastecimiento import (
        obtener_config as _reab_obtener_config,
    )
    from src.db.reabastecimiento import (
        obtener_propuesta as _reab_obtener_propuesta,
    )
    from src.db.reabastecimiento import (
        propuesta_pendiente_existe as _reab_propuesta_pendiente_existe,
    )
    from src.db.reabastecimiento import (
        upsert_config as _reab_upsert_config,
    )
    _REAB_DB_OK = True
except ImportError:
    _REAB_DB_OK = False
    def _reab_listar_config(): return []
    def _reab_upsert_config(*a, **kw): pass
    def _reab_eliminar_config(*a): pass
    def _reab_obtener_config(*a): return None
    def _reab_crear_propuesta(*a, **kw): return None
    def _reab_listar_propuestas(*a, **kw): return []
    def _reab_cambiar_estado_propuesta(*a): pass
    def _reab_propuesta_pendiente_existe(*a): return False
    def _reab_marcar_articulos_recibidos(*a): return 0
    def _reab_obtener_propuesta(*a): return None
    def _reab_cargar_schedule(): return {}
    def _reab_guardar_schedule(*a): return False
    def _reab_marcar_envio_hoy(): pass
from PyQt6.QtCore import QObject, QPoint, QRectF, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPixmap,
    QRegion,
)
from reportlab.graphics.barcode import code128

# Clase SidebarButton: garantiza hover-swap mediante eventos de entrada/salida
try:
    from assets.estilo_global import (
        COLOR_CIAN,
        COLOR_FONDO_APP,
        COLOR_FONDO_SIDEBAR,
        COLOR_ROJO_ERROR,
        aplicar_estilo_widget,
        construir_plantilla_camara,
        construir_tabla_estilizada,
        feedback_frame_item_resaltado,
        feedback_lineedit_exito,
        mostrar_confirmacion,
        mostrar_mensaje,
        repolish_widget,
    )
except Exception:
    COLOR_FONDO_SIDEBAR = "#111418"
    COLOR_CIAN = "#00FFC6"
    COLOR_FONDO_APP = "#0E1117"
    COLOR_ROJO_ERROR = "#F85149"
    aplicar_estilo_widget = None
    construir_plantilla_camara = None
    construir_tabla_estilizada = None
    feedback_frame_item_resaltado = None
    feedback_lineedit_exito = None
    mostrar_confirmacion = None
    mostrar_mensaje = None
    repolish_widget = None


# ============================================================
# BLOQUE UTILIDADES DE INTERFAZ
# ============================================================

def _mensaje_ui(parent, titulo, texto, nivel="info"):
    if mostrar_mensaje is not None:
        mostrar_mensaje(parent, titulo, texto, nivel=nivel)
    elif nivel == "error":
        QMessageBox.critical(parent, titulo, texto)
    elif nivel == "warning":
        QMessageBox.warning(parent, titulo, texto)
    else:
        QMessageBox.information(parent, titulo, texto)


def _confirmar_ui(parent, titulo, texto):
    if mostrar_confirmacion is not None:
        return mostrar_confirmacion(parent, titulo, texto)
    ret = QMessageBox.question(
        parent,
        titulo,
        texto,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    return ret == QMessageBox.StandardButton.Yes


class SidebarButton(QPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setObjectName("btn_sidebar")
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            self.setMouseTracking(True)
        except Exception:
            pass
        try:
            if aplicar_estilo_widget is not None:
                aplicar_estilo_widget(self)
        except Exception:
            pass


class _SidebarFrameFilter(QObject):
    def eventFilter(self, watched, event):
        return super().eventFilter(watched, event)


def abrir_pdf(ruta_pdf):
    """Abre un archivo PDF con el visor predeterminado de forma multiplataforma."""
    import os

    if not ruta_pdf or not os.path.exists(ruta_pdf):
        return False

    try:
        if platform.system() == "Windows":
            os.startfile(ruta_pdf)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", ruta_pdf])
        else:
            subprocess.Popen(["xdg-open", ruta_pdf])
        return True
    except Exception as e:
        print(f"Error al abrir PDF: {e}")
        return False


# ============================================================
# BLOQUE ESCÁNER DE CÓDIGOS DE BARRAS
# ============================================================


class ScannerDialog(QDialog):
    # --- SEÑALES ---
    codigo_leido = pyqtSignal(str)
    confirmar_recepcion = pyqtSignal(str, list)

    def __init__(self, usuario, parent=None):
        # Pass flags at construction time to avoid native-window recreation
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setObjectName("scanner_dialog")
        self.setFixedSize(650, 600)
        self.setWindowTitle(tr("recep.escaner_inteligente_smart_ma", default="Escáner Inteligente - Smart Manager"))
        self.usuario = usuario
        self.cap = None
        self.codigo_detectado = None

        # Visual background frame
        self.main_frame = QFrame(self)
        self.main_frame.setObjectName("cuerpo_ventana_scan")
        self.main_frame.setGeometry(0, 0, 650, 600)

        # Layout manages title / status / buttons only.
        # lbl_video is positioned manually so it is always exactly centred.
        content_layout = QVBoxLayout(self.main_frame)
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(12)

        self.lbl_titulo = QLabel(tr("recep.vision_logistica", default="VISIÓN - LOGÍSTICA"))
        self.lbl_titulo.setObjectName("titulo_scan")
        self.lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.lbl_titulo)

        # Reserve vertical space for the video label (300 px + two 12 px gaps)
        content_layout.addSpacing(324)

        self.lbl_status = QLabel(tr("recep.alinee_el_codigo_con_el_sens", default="ALINEE EL CÓDIGO CON EL SENSOR"))
        self.lbl_status.setObjectName("lbl_info_scan")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.lbl_status)

        self.btn_iniciar = QPushButton(tr("recep.iniciar_escaneo", default="🚀 INICIAR ESCANEO"))
        self.btn_iniciar.setObjectName("btn_primario")
        self.btn_iniciar.setFixedHeight(50)
        self.btn_iniciar.setVisible(False)
        content_layout.addWidget(self.btn_iniciar)

        self.btn_cancelar = QPushButton(tr("recep.abortar_operacion", default="ABORTAR OPERACIÓN"))
        self.btn_cancelar.setObjectName("btn_abortar_scan")
        self.btn_cancelar.setFixedHeight(45)
        content_layout.addWidget(self.btn_cancelar)

        # Video label: child of main_frame but NOT in the layout.
        # Centred with setGeometry once the title has been laid out.
        self.lbl_video = QLabel("", self.main_frame)
        self.lbl_video.setObjectName("feed_video")
        self.lbl_video.setProperty("activo", False)
        self.lbl_video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_video.setFixedSize(540, 300)
        self.lbl_video.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.lbl_video.setScaledContents(False)

        if aplicar_estilo_widget is not None:
            for _w in (self.lbl_titulo, self.lbl_video, self.lbl_status,
                       self.btn_iniciar, self.btn_cancelar):
                aplicar_estilo_widget(_w)

        self.btn_iniciar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_iniciar.clicked.connect(self.inicializar_hardware_camara)
        self.btn_cancelar.clicked.connect(self.reject)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)

        # Set initial video position (centered horizontally, below title).
        # 80 = 30 top-margin + ~38px title + 12 gap — refined in showEvent.
        _x0 = (self.main_frame.width() - self.lbl_video.width()) // 2
        self.lbl_video.setGeometry(_x0, 80, self.lbl_video.width(), self.lbl_video.height())
        self.lbl_video.raise_()
        self.lbl_video.show()

        QTimer.singleShot(0, self.inicializar_hardware_camara)

        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2,
        )

    def showEvent(self, event):
        super().showEvent(event)
        self._posicionar_video()

    def _posicionar_video(self):
        """Centra lbl_video con la geometría real del título (disponible en showEvent)."""
        x = (self.main_frame.width() - self.lbl_video.width()) // 2
        y_bottom = self.lbl_titulo.geometry().bottom()
        y = (y_bottom + 12) if y_bottom > 0 else 80
        self.lbl_video.setGeometry(x, y, self.lbl_video.width(), self.lbl_video.height())
        self.lbl_video.raise_()

    def get_codigo(self):
        return self.codigo_detectado

    def aplicar_mascara_redondeada(self):
        """Crea una máscara para que el video respete los bordes redondeados del label."""
        path = QPainterPath()
        rect = self.lbl_video.rect()
        path.addRoundedRect(
            float(rect.x()),
            float(rect.y()),
            float(rect.width()),
            float(rect.height()),
            14,
            14,
        )
        region = QRegion(path.toFillPolygon().toPolygon())
        self.lbl_video.setMask(region)

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def inicializar_hardware_camara(self):
        self.btn_iniciar.setEnabled(False)
        self.btn_iniciar.setText(
            tr("recep.conectando", default="⌛ CONECTANDO...")
        )  # Cambiado para mostrar el estado de conexión
        QApplication.processEvents()

        self.liberar_recursos()
        camara_encontrada = False
        for index in [0, 1]:
            self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                camara_encontrada = True
                break

        if camara_encontrada:
            self.lbl_video.setProperty("activo", True)
            if aplicar_estilo_widget is not None:
                aplicar_estilo_widget(self.lbl_video)
            self.lbl_status.setText(tr("recep.alinee_el_codigo_con_el_sens_2", default="ALINEE EL CÓDIGO CON EL SENSOR"))
            self.btn_iniciar.hide()
            self.timer.start(30)
        else:
            self.mostrar_error_camara()
            self.btn_iniciar.setEnabled(True)
            self.btn_iniciar.setText(tr("recep.reintentar_inicio", default="🚀 REINTENTAR INICIO"))
            self.btn_iniciar.show()

    def update_frame(self):
        if self.cap is None or not self.cap.isOpened():
            return

        ret, frame = self.cap.read()
        if ret:
            frame = cv2.flip(frame, 1)
            # Detección de códigos
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            barcodes = pyzbar.decode(gray)

            for barcode in barcodes:
                self.codigo_detectado = barcode.data.decode("utf-8")
                if self.codigo_detectado:
                    self.lbl_status.setText(f"CÓDIGO DETECTADO: {self.codigo_detectado}")
                    self.timer.stop()
                    QTimer.singleShot(300, self.finalizar_y_cerrar_con_exito)
                    return

            # Renderizado en el QLabel con esquinas redondeadas y sin deformación
            rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w
            qt_image = QImage(
                rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888
            )

            tw = self.lbl_video.width()
            th = self.lbl_video.height()
            if tw > 0 and th > 0:
                B = 4  # border inset: outer half on dark fill, inner half on video
                iw, ih = tw - 2 * B, th - 2 * B
                src = QPixmap.fromImage(qt_image)
                scaled = src.scaled(
                    iw, ih,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                ox = (scaled.width() - iw) // 2
                oy = (scaled.height() - ih) // 2
                cropped = scaled.copy(ox, oy, iw, ih)
                result = QPixmap(tw, th)
                result.fill(QColor("#05070A"))
                painter = QPainter(result)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                clip = QPainterPath()
                clip.addRoundedRect(QRectF(B, B, iw, ih), 12, 12)
                painter.setClipPath(clip)
                painter.drawPixmap(B, B, cropped)
                painter.setClipping(False)
                from PyQt6.QtGui import QPen
                _pen = QPen(QColor(0, 255, 198, 255), B * 2)
                _pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(QRectF(B, B, iw, ih), 12, 12)
                painter.end()
                self.lbl_video.setPixmap(result)

    def finalizar_y_cerrar_con_exito(self):
        """
        Recupera el contenido del palé y cierra la cámara de forma segura.
        """
        id_pale = self.codigo_detectado
        items_recuperados = []

        try:

            # Usamos un bloque with para asegurar que la conexión se cierra
            with obtener_conexion() as conn:
                if conn:
                    cursor = conn.cursor()
                    # Cambiamos a una consulta que busque el contenido actual del palé
                    query = """
                        SELECT codigo, nombre, cantidad 
                        FROM stock_pales 
                        WHERE id_pale = %s AND cantidad > 0
                    """
                    cursor.execute(query, (id_pale,))
                    rows = cursor.fetchall()

                    for r in rows:
                        items_recuperados.append([r[0], r[1], r[2]])

            if not items_recuperados:
                self.lbl_status.setText(tr("recep.pale_sin_stock_o_no_existe", default="PALÉ SIN STOCK O NO EXISTE"))
                # Damos margen para que el usuario vea el error antes de reanudar
                QTimer.singleShot(2000, lambda: self.timer.start(30))
                return

            # ÉXITO: Liberamos cámara ANTES de emitir para evitar lag
            self.liberar_recursos()
            self.confirmar_recepcion.emit(id_pale, items_recuperados)
            self.accept()

        except Exception as e:
            print(f"Error crítico en Scanner: {e}")
            self.liberar_recursos()
            self.reject()

    def mostrar_error_camara(self):
        self.lbl_video.setText(tr("recep.error_de_hardware_camara_ocu", default="ERROR DE HARDWARE\n\nCámara ocupada o no detectada"))
        self.lbl_video.setProperty("activo", False)
        self.lbl_status.setText(tr("recep.error_de_hardware", default="ERROR DE HARDWARE"))
        if aplicar_estilo_widget is not None:
            aplicar_estilo_widget(self.lbl_video)

    def liberar_recursos(self):
        self.timer.stop()
        if self.cap:
            self.cap.release()
            self.cap = None


# ============================================================
# BLOQUE SELECCIÓN LOGÍSTICA
# ============================================================

class SelectorLogisticoExtras(QDialog):
    """Ventana emergente con botones toggle para añadir bultos extra al traspaso (multi-select)."""

    items_confirmados = pyqtSignal(list)  # Lista de nombres confirmados

    _BULTOS = [
        ("BASE PALÉ",       "🪵"),
        ("JAULA REMONTADA", "🔼"),
        ("JAULA PLÁSTICO",  "🧺"),
        ("JAULA CARTÓN",    "📦"),
        ("JAULA METÁLICA",  "⚙️"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("recep.anadir_equipamiento_logistic", default="Añadir Equipamiento Logístico"))
        self.setObjectName("dlg_incidencia")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(460)
        self._drag_pos = None
        self._seleccionados: set = set()
        self._btns: dict = {}
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("cuerpo_ventana")
        outer.addWidget(frame)

        ly = QVBoxLayout(frame)
        ly.setContentsMargins(28, 24, 28, 24)
        ly.setSpacing(18)

        titulo = QLabel(tr("recep.anadir_bulto_extra_al_traspa", default="¿AÑADIR BULTO EXTRA AL TRASPASO?"))
        titulo.setObjectName("titulo_cian")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(titulo)

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setContentsMargins(0, 0, 0, 0)

        for idx, (nombre, icono) in enumerate(self._BULTOS):
            btn = QPushButton(f"{icono}\n{nombre}")
            btn.setObjectName("btn_secundario")
            btn.setFixedSize(160, 80)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, n=nombre: self._toggle(n))
            self._btns[nombre] = btn
            grid.addWidget(btn, idx // 3, idx % 3)

        ly.addLayout(grid)

        h_btns = QHBoxLayout()
        h_btns.setSpacing(12)

        self.btn_skip = QPushButton(tr("recep.seguir_sin_bultos_extra", default="SEGUIR SIN BULTOS EXTRA"))
        self.btn_skip.setObjectName("btn_secundario")
        self.btn_skip.setFixedHeight(46)
        self.btn_skip.setStyleSheet(
            "QPushButton#btn_secundario { color: #4FC3F7; border-color: #4FC3F7; }"
            "QPushButton#btn_secundario:hover { background-color: rgba(79,195,247,0.15); }"
        )
        self.btn_skip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_skip.clicked.connect(self.reject)

        self.btn_aceptar = QPushButton(tr("recep.aceptar", default="ACEPTAR"))
        self.btn_aceptar.setObjectName("btn_primario")
        self.btn_aceptar.setFixedHeight(46)
        self.btn_aceptar.setEnabled(False)
        self.btn_aceptar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_aceptar.clicked.connect(self._confirmar)

        h_btns.addWidget(self.btn_skip, 3)
        h_btns.addWidget(self.btn_aceptar, 2)
        ly.addLayout(h_btns)

    def _toggle(self, nombre):
        if nombre in self._seleccionados:
            self._seleccionados.discard(nombre)
            self._btns[nombre].setChecked(False)
            self._btns[nombre].setStyleSheet("")
        else:
            self._seleccionados.add(nombre)
            self._btns[nombre].setChecked(True)
            self._btns[nombre].setStyleSheet(
                "QPushButton { border-color: #00FFC6; color: #00FFC6;"
                "  background-color: rgba(0,255,198,0.12); }"
            )
        self.btn_aceptar.setEnabled(bool(self._seleccionados))

    def _confirmar(self):
        self.items_confirmados.emit(sorted(self._seleccionados))
        self.accept()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._center_on_parent)

    def _center_on_parent(self):
        parent = self.parentWidget()
        ref = parent.window().frameGeometry() if parent else None
        if ref is None:
            return
        self.move(
            ref.x() + (ref.width() - self.width()) // 2,
            ref.y() + (ref.height() - self.height()) // 2,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


# ============================================================
# BLOQUE GENERACIÓN DE DOCUMENTOS PDF
# ============================================================


class PdfWorker(QObject):
    """
    Coordina la generación de documentos (Albaranes y Etiquetas).
    Versión unificada y autónoma con soporte para Recepciones y Traspasos.
    """

    finished = pyqtSignal(tuple)  # (ruta_albaran, [rutas_etiquetas], id_traspaso)
    error = pyqtSignal(str)

    def __init__(self):
        """
        Constructor limpio para evitar errores de argumentos posicionales.
        Se inicializan los atributos vacíos para ser llenados con configurar().
        """
        super().__init__()
        self.pale_items = []
        self.origen = ""
        self.destino = ""
        self.observaciones = ""
        self.agencia_transporte = ""
        self.usuario = ""
        self.datos_logisticos = {}
        self.id_traspaso = ""
        self.tipo_operacion = "traspaso"
        self._pdf_generado = False

    def configurar(
        self,
        pale_items,
        origen,
        destino,
        observaciones,
        agencia_transporte,
        usuario,
        id_traspaso,
        datos_logisticos=None,
        tipo_operacion="traspaso",
    ):
        """Asigna los datos necesarios justo antes de ejecutar la generación."""
        self.pale_items = pale_items
        self.origen = origen
        self.destino = destino
        self.observaciones = observaciones
        self.agencia_transporte = agencia_transporte
        self.usuario = usuario
        self.id_traspaso = id_traspaso
        self.datos_logisticos = datos_logisticos or {}
        self.tipo_operacion = tipo_operacion.lower()
        self._pdf_generado = False

    def _get_terminos(self):
        """Devuelve los términos correctos según el tipo de operación para el PDF."""
        if self.tipo_operacion == "recepcion":
            return {
                "titulo": "ALBARÁN DE RECEPCIÓN",
                "id_label": "ID RECEPCIÓN:",
                "firma_emisor": "FIRMA PROVEEDOR / SALIDA",
                "firma_receptor": "FIRMA RECEPCIÓN TIENDA",
                "subfolder": "albaranes",
                "prefijo_archivo": "REC",
            }
        else:
            return {
                "titulo": "ALBARÁN DE TRASPASO",
                "id_label": "ID TRASPASO:",
                "firma_emisor": "FIRMA EMISIÓN TIENDA",
                "firma_receptor": "FIRMA RECEPTOR / AGENCIA",
                "subfolder": "albaranes",
                "prefijo_archivo": "ALB",
            }

    def run(self):
        """Ejecuta el proceso de generación — delega en los servicios enterprise."""
        if self._pdf_generado:
            return
        self._pdf_generado = True

        try:
            from src.services.logistics.logistics_pdf_service import generar_albaran_traspaso
            from src.services.logistics.pallet_label_service import generar_etiquetas_pales

            data = self._construir_data_agrupada()

            # Albarán enterprise
            ruta_albaran = generar_albaran_traspaso(data)

            # Etiquetas de palés (solo en traspasos)
            rutas_etiquetas = []
            if self.tipo_operacion == "traspaso" and data.get("pales"):
                ruta_etq = generar_etiquetas_pales(
                    lista_pales=data["pales"],
                    origen=self.origen,
                    destino=self.destino,
                    id_traspaso=self.id_traspaso,
                )
                rutas_etiquetas.append(ruta_etq)

            self.finished.emit((str(ruta_albaran), rutas_etiquetas, self.id_traspaso))

        except Exception as e:
            import traceback
            print(f"DEBUG PDF ERROR: {traceback.format_exc()}")
            self.error.emit(f"Error en el proceso de documentación: {str(e)}")

    def _construir_data_agrupada(self) -> dict:
        """
        Organiza los artículos por palé, calcula pesos totales y
        gestiona los valores nulos/pendientes para el PDF.
        """

        pales_dict = {}
        # Recuperamos pesos desde datos_logisticos
        pesos_pales = self.datos_logisticos.get("peso_bulto", {})
        peso_total_acumulado = 0.0
        total_referencias = 0

        for it in self.pale_items:
            # Identificación de estructura de datos (Dict o List)
            if isinstance(it, dict):
                pale_id_full = it.get("pale_codigo") or it.get("id_visual_pale")
                codigo = it.get("codigo", "LOGISTICA")
                nombre = it.get("nombre", "Sin nombre")
                cantidad = it.get("cantidad", 0)
                es_logistico = it.get("es_logistico", False)
            else:
                pale_id_full = "PAL-GENERAL"
                codigo, nombre, cantidad = it[0], it[1], it[2]
                es_logistico = False

            if not pale_id_full:
                continue

            # Si es la primera vez que vemos este palé, inicializamos su entrada
            if pale_id_full not in pales_dict:
                peso_raw = pesos_pales.get(pale_id_full)

                # Gestión de pesos opcionales (Punto 2)
                if peso_raw in [None, "", "None", 0, 0.0]:
                    peso_v = None  # Se imprimirá como "___ KG"
                else:
                    try:
                        peso_v = float(str(peso_raw).replace(",", "."))
                        peso_total_acumulado += peso_v
                    except (ValueError, TypeError):
                        peso_v = None

                pales_dict[pale_id_full] = {
                    "pale_codigo": pale_id_full,
                    "id_visual": pale_id_full,
                    "peso_pale": peso_v,
                    "articulos": [],
                }

            # Añadimos el artículo al palé correspondiente
            pales_dict[pale_id_full]["articulos"].append(
                {
                    "codigo": codigo,
                    "nombre": nombre,
                    "cantidad": int(cantidad),
                    "es_logistico": es_logistico,
                }
            )
            total_referencias += 1

        return {
            "id_traspaso": self.id_traspaso,
            "tipo_documento": self._get_terminos()["titulo"],
            "origen": self.origen,
            "destino": self.destino,
            "observaciones": self.observaciones,
            "agencia_transporte": self.agencia_transporte,
            "usuario": self.usuario,
            "fecha_envio": self.datos_logisticos.get(
                "fecha_envio", datetime.now().strftime("%d/%m/%Y")
            ),
            "pales": list(pales_dict.values()),
            "peso_total": (
                f"{peso_total_acumulado:.2f}" if peso_total_acumulado > 0 else "Pte."
            ),
            "total_referencias": total_referencias,
            "terminos": self._get_terminos(),
        }

    def generar_pdf_traspaso(self, *, traspaso_data: dict):
        """
        Genera el PDF del Albarán con soporte para pesos opcionales
        y distinción visual de artículos logísticos.
        """

        id_doc = traspaso_data.get("id_traspaso", "TRA-000")
        ruta_pdf = os.path.join(
            os.getcwd(), "documentos", "albaranes", f"ALB_{id_doc}.pdf"
        )
        os.makedirs(os.path.dirname(ruta_pdf), exist_ok=True)

        # --- i18n: etiquetas fijas (tr) + nombres de artículo por IA (lote) ---
        from src.utils import ai_translator, i18n
        lang = i18n.current_language()

        def L(clave, defecto):
            return i18n.tr(f"albaran.{clave}", default=defecto)

        # Nivel 2: traducir TODOS los nombres de artículo en UNA sola llamada
        # (dominio logístico), respetando el orden de ideración de la tabla.
        _nombres_raw = [
            a.get("nombre", "")
            for p in traspaso_data.get("pales", [])
            for a in p.get("articulos", [])
        ]
        try:
            _nombres_tr = ai_translator.traducir_lote(_nombres_raw, lang, dominio="logistico")
        except Exception:
            _nombres_tr = _nombres_raw
        _nombres_iter = iter(_nombres_tr)

        styles = getSampleStyleSheet()
        style_n = ParagraphStyle("Normal", fontName="Helvetica", fontSize=8, leading=10)
        style_b = ParagraphStyle(
            "Bold", fontName="Helvetica-Bold", fontSize=8, leading=10
        )
        style_log = ParagraphStyle(
            "Logistico", fontName="Helvetica-Bold", fontSize=8, textColor=colors.grey
        )

        story = []

        # --- CABECERA Y QR ---
        qr = qrcode.make(id_doc)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            qr.save(tmp.name)
            qr_path = tmp.name

        head_data = [
            [
                Paragraph("<b>Smart Manager</b>", styles["Heading1"]),
                "",
                Image(qr_path, 20 * mm, 20 * mm),
            ]
        ]
        head_tab = Table(head_data, colWidths=[10 * cm, 4 * cm, 5 * cm])
        story.append(head_tab)
        story.append(Paragraph(f"<b>{L('doc_title', 'ALBARÁN DE TRASPASO')}</b>", style_b))
        story.append(Spacer(1, 10))

        # --- TABLA DE CONTENIDO ---
        data_table = [
            [
                Paragraph(f"<b>{L('col_pale', 'PALÉ')}</b>", style_b),
                Paragraph(f"<b>{L('col_code', 'CÓDIGO')}</b>", style_b),
                Paragraph(f"<b>{L('col_article', 'ARTÍCULO')}</b>", style_b),
                Paragraph(f"<b>{L('col_units', 'UDS')}</b>", style_b),
            ]
        ]

        for p in traspaso_data.get("pales", []):
            arts = p.get("articulos", [])
            peso_val = p.get("peso_pale")
            texto_peso = f"{peso_val} KG" if peso_val is not None else "_______ KG"

            for i, a in enumerate(arts):
                # Punto 4: Resaltado de Jaulas y Logística
                # Nombre traducido por IA (mismo orden que el lote).
                nombre = next(_nombres_iter, a.get("nombre", ""))
                current_style = style_n
                if a.get("es_logistico"):
                    nombre = f"[LOG] {nombre}"
                    current_style = style_log

                data_table.append(
                    [
                        Paragraph(p.get("pale_codigo", "")) if i == 0 else "",
                        Paragraph(str(a.get("codigo", ""))),
                        Paragraph(nombre, current_style),
                        Paragraph(str(a.get("cantidad", 0))),
                    ]
                )

            # Fila de resumen de bulto (Punto 2)
            data_table.append(
                [
                    "",
                    "",
                    Paragraph(f"<b>{L('declared_weight', 'Peso declarado:')}</b>", style_n),
                    Paragraph(f"<b>{texto_peso}</b>", style_n),
                ]
            )
            data_table.append(
                [
                    "",
                    "",
                    Paragraph(L("total_units", "Total unidades bulto:"), style_n),
                    Paragraph(str(sum(x["cantidad"] for x in arts))),
                ]
            )

        table_art = Table(
            data_table, colWidths=[3.5 * cm, 3.5 * cm, 9.5 * cm, 2.5 * cm]
        )
        table_art.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ]
            )
        )
        story.append(table_art)

        # Generación final
        doc = SimpleDocTemplate(ruta_pdf, pagesize=A4)
        doc.build(story)
        if os.path.exists(qr_path):
            os.remove(qr_path)
        return ruta_pdf

    def generar_etiqueta_pdf(
        self, lista_pales, origen, destino, secuencial_traspaso
    ) -> str:
        """
        Genera etiquetas de palés (4 por A4) EXACTAMENTE iguales al modelo.
        Formato ID: PAL-[Sigla]-[Secuencial]-[Origen]
        Nomenclatura Archivo: ETIS_[Origen]_[Secuencial]_[Destino]_[Año].pdf
        """

        # 1. Configuración de Identificadores
        anio = datetime.now().year
        # Limpiamos el secuencial para que solo sea el número (ej: 001)
        sec_str = str(secuencial_traspaso).split("-")[-1].zfill(3)
        orig_clean = str(origen).strip().upper().replace(" ", "_").replace("/", "-")
        dest_clean = str(destino).strip().upper().replace(" ", "_").replace("/", "-")

        # ID Maestro del Traspaso para referencia
        id_maestro = f"TRA-{orig_clean}-{sec_str}-{anio}"
        nombre_archivo = f"ETIS_{orig_clean}_{sec_str}_{dest_clean}_{anio}.pdf"

        # Gestión de rutas absoluta para robustez en Windows
        base_path = Path(os.getcwd())
        out_dir = base_path / "documentos" / "etiquetas_pales"
        out_dir.mkdir(parents=True, exist_ok=True)
        ruta_pdf = str(out_dir / nombre_archivo)

        c = canvas.Canvas(ruta_pdf, pagesize=A4)
        width_a4, height_a4 = A4

        # Coordenadas para 4 etiquetas por página
        posiciones = [
            (0, height_a4 / 2),  # Superior Izquierda
            (width_a4 / 2, height_a4 / 2),  # Superior Derecha
            (0, 0),  # Inferior Izquierda
            (width_a4 / 2, 0),  # Inferior Derecha
        ]

        def dibujar_etiqueta(canv, x_off, y_off, pale_data):
            w_eti = width_a4 / 2
            h_eti = height_a4 / 2

            # --- MARCO PERIMETRAL ---
            canv.setStrokeColorRGB(0, 0, 0)
            canv.setLineWidth(0.2)
            canv.rect(x_off + 5 * mm, y_off + 5 * mm, w_eti - 10 * mm, h_eti - 10 * mm)

            # --- 1. CÓDIGO DE BARRAS (Superior) ---
            sigla = str(pale_data.get("id_visual", "PAL")).upper().replace(" ", "")
            # ID según modelo: PAL-PALE1-001-TRA-ORIGEN
            id_etiqueta = f"PAL-{sigla}-{sec_str}-TRA-{orig_clean}"

            # Generación de código de barras Code128
            barcode = code128.Code128(id_etiqueta, barHeight=25 * mm, barWidth=1.2)
            barcode.drawOn(
                canv, x_off + (w_eti - barcode.width) / 2, y_off + h_eti - 35 * mm
            )

            # --- 2. RUTA ---
            canv.setFont("Helvetica-Bold", 16)
            canv.drawCentredString(
                x_off + w_eti / 2,
                y_off + h_eti - 45 * mm,
                f"{orig_clean} >> {dest_clean}",
            )

            # --- 3. ID DE ETIQUETA Y PESO ---
            canv.setFont("Helvetica-Bold", 14)
            canv.drawCentredString(
                x_off + w_eti / 2, y_off + h_eti - 55 * mm, id_etiqueta
            )

            # Recuadro para el Peso (Destacado)
            peso_val = f"{pale_data.get('peso', 0.0)} KG"
            canv.setFont("Helvetica-Bold", 20)
            canv.rect(
                x_off + w_eti / 2 - 30 * mm,
                y_off + 35 * mm,
                60 * mm,
                12 * mm,
                stroke=1,
                fill=0,
            )
            canv.drawCentredString(x_off + w_eti / 2, y_off + 38 * mm, peso_val)

            # --- 4. REFERENCIA MAESTRA Y SISTEMA ---
            canv.setFont("Helvetica", 9)
            canv.drawCentredString(
                x_off + w_eti / 2, y_off + 25 * mm, f"REF ALBARÁN: {id_maestro}"
            )

            canv.setFont("Helvetica-Bold", 8)
            canv.drawCentredString(
                x_off + w_eti / 2,
                y_off + 15 * mm,
                "SISTEMA LOGÍSTICO - SMART MANAGER",
            )

            canv.setFont("Helvetica", 7)
            canv.drawCentredString(
                x_off + w_eti / 2,
                y_off + 10 * mm,
                f"GEN: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            )

        # Generar las etiquetas solicitadas
        for i, pale in enumerate(lista_pales):
            dibujar_etiqueta(c, posiciones[i % 4][0], posiciones[i % 4][1], pale)
            # Si llenamos una página (4 etiquetas) y hay más, creamos página nueva
            if (i + 1) % 4 == 0 and (i + 1) < len(lista_pales):
                c.showPage()

        c.save()
        return ruta_pdf


# ============================================================
# BLOQUE RECEPCIÓN DE MERCANCÍA
# ============================================================

class RecepcionStockPage(QWidget):

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        # Punto 3: Unificación de variable de usuario
        self.usuario = usuario
        self.setup_ui()

    def setup_ui(self):
        """Configura la interfaz principal de recepción con estilo GitHub Dark."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.setObjectName("panel_contenido")

        # --- PANEL DE BIENVENIDA (ÚNICA VISTA) ---
        self.vista_inicio = QFrame()
        layout_inicio = QVBoxLayout(self.vista_inicio)
        layout_inicio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_inicio.setSpacing(20)

        # Contenedor Central Estilizado (Siguiendo estilo_global.py)
        container = QFrame()
        container.setObjectName("panel_bienvenida")
        container.setFixedWidth(550)  # Ligeramente más ancho para mejor legibilidad
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(40, 40, 40, 40)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.setSpacing(15)

        # Icono distintivo de Recepción
        self.lbl_icono = QLabel("📥")
        self.lbl_icono.setObjectName("icono_hero")
        self.lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_titulo = QLabel(tr("recep.centro_de_recepcion_logistic", default="CENTRO DE RECEPCIÓN LOGÍSTICA"))
        self.lbl_titulo.setObjectName("titulo_cian")
        self.lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_info = QLabel(
            tr("recep.presione_el_boton_para_abrir", default="Presione el botón para abrir el escáner y\nvalidar la entrada de palés o artículos.")
        )
        self.lbl_info.setObjectName("texto_auxiliar")
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Botón Central de Acción (Estilo Global Neón)
        self.btn_iniciar = QPushButton(tr("recep.iniciar_escaneo_2", default="🚀  INICIAR ESCANEO"))
        self.btn_iniciar.setObjectName("btn_primario")
        self.btn_iniciar.setFixedWidth(320)
        self.btn_iniciar.setFixedHeight(60)
        self.btn_iniciar.setCursor(Qt.CursorShape.PointingHandCursor)

        # Mantenemos tu conexión lógica intacta
        self.btn_iniciar.clicked.connect(self.abrir_flujo_recepcion)

        # Montaje de la UI
        container_layout.addWidget(self.lbl_icono)
        container_layout.addWidget(self.lbl_titulo)
        container_layout.addWidget(self.lbl_info)
        container_layout.addSpacing(25)
        container_layout.addWidget(self.btn_iniciar)

        layout_inicio.addWidget(container)
        self.main_layout.addWidget(self.vista_inicio)

    def abrir_flujo_recepcion(self):
        """Abre el diálogo de escaneo externo y procesa el resultado."""

        dialogo = ScannerDialog(self.usuario, parent=self)

        # Si el diálogo se cierra con Aceptar (código detectado)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            # ScannerDialog debería tener un atributo 'ultimo_codigo'
            codigo_detectado = getattr(dialogo, "ultimo_codigo", None)
            if codigo_detectado:
                self.procesar_codigo_escaneado(codigo_detectado)

    def procesar_codigo_escaneado(self, codigo):
        """
        Busca el Palé Impersonal en MariaDB y recupera su contenido.
        """
        codigo = str(codigo).strip().upper()
        if not codigo:
            return

        # 1. SI ES UN PALÉ (ID Impersonal: PAL-XXX-YYY-TRP-...)
        if codigo.startswith("PAL"):

            # Esta función debe buscar en 'traspasos_detalle' filtrando por id_pale
            items = obtener_items_pale_traspaso(codigo)

            if items:
                # 'items' será una lista de diccionarios con: codigo, nombre, cantidad, origen, etc.
                # Lanzamos el diálogo de confirmación que mostrará el contenido del palé
                self.abrir_confirmacion_recepcion(codigo, items)
            else:
                _mensaje_ui(
                    self,
                    "No Encontrado",
                    f"El palé {codigo} no existe, ya fue recibido o no está asignado a este centro.",
                    "warning",
                )

        # 2. SI ES UN ARTÍCULO INDIVIDUAL (EAN/REF)
        else:

            art = obtener_articulo(codigo)

            if art:
                self.procesar_entrada_individual(art)
            else:
                _mensaje_ui(
                    self,
                    "Error",
                    f"El artículo {codigo} no está registrado en el maestro.",
                    "error",
                )

    def procesar_entrada_individual(self, art):
        """
        Procesa el artículo obtenido de la DB y lo añade a la tabla de la interfaz.
        'art' es un diccionario devuelto por MariaDB (DictCursor).
        """

        if not art:
            _mensaje_ui(
                self, "Error", "El artículo no existe en la base de datos.", "warning"
            )
            return

        # Extraemos los datos del diccionario (Claves exactas de MariaDB)
        codigo = str(art.get("codigo", "---"))
        nombre = str(art.get("nombre", "Artículo Desconocido"))

        # Priorizamos 'Stock_central' que es la columna que acabamos de crear
        stock_actual = art.get("Stock_central", art.get("Stock_total", 0))

        # Buscamos si el artículo ya está en la tabla para sumar cantidad
        encontrado = False
        # self.tabla_items debe estar definida en tu setup_ui o clase
        for row in range(self.tabla_items.rowCount()):
            item_codigo_tabla = self.tabla_items.item(row, 0)
            if item_codigo_tabla and item_codigo_tabla.text() == codigo:
                # Si ya existe, sumamos 1 a la cantidad (Columna 2)
                item_cant = self.tabla_items.item(row, 2)
                if item_cant:
                    nueva_cant = int(item_cant.text()) + 1
                    item_cant.setText(str(nueva_cant))
                encontrado = True
                break

        if not encontrado:
            # Si es nuevo, añadimos una fila nueva a la tabla
            row_pos = self.tabla_items.rowCount()
            self.tabla_items.insertRow(row_pos)

            self.tabla_items.setItem(row_pos, 0, QTableWidgetItem(codigo))
            self.tabla_items.setItem(row_pos, 1, QTableWidgetItem(nombre))
            self.tabla_items.setItem(
                row_pos, 2, QTableWidgetItem("1")
            )  # Cantidad inicial
            self.tabla_items.setItem(row_pos, 3, QTableWidgetItem(str(stock_actual)))

        # Limpiamos el campo de entrada (Ajustado a tu nombre de widget: input_codigo_manual)
        if hasattr(self, "input_codigo_manual"):
            self.input_codigo_manual.clear()
            self.input_codigo_manual.setFocus()
        elif hasattr(self, "input_codigo"):
            self.input_codigo.clear()
            self.input_codigo.setFocus()

    def procesar_entrada_manual(self):
        """Maneja el texto escrito en el QLineEdit y pulsado Enter."""
        codigo = self.input_manual.text().strip().upper()
        if codigo:
            self.procesar_codigo_escaneado(codigo)
            self.input_manual.clear()

    def setup_interfaz_camara(self):
        """Crea los widgets necesarios para ver la cámara y el input manual."""
        layout_cam = QVBoxLayout(self.vista_scanner)
        layout_cam.setContentsMargins(20, 20, 20, 20)
        layout_cam.setSpacing(15)

        # Contenedor del Feed de Vídeo — con parent explícito para evitar ventana flotante
        self.lbl_video = QLabel(self.vista_scanner)
        self.lbl_video.setObjectName("feed_video")
        self.lbl_video.setProperty("activo", True)
        self.lbl_video.setFixedSize(640, 480)
        self.lbl_video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_video.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Input Manual (Debajo de la cámara, como en tus capturas)
        self.input_manual = QLineEdit()
        self.input_manual.setObjectName("input_buscador")
        self.input_manual.setPlaceholderText(
            tr("recep.o_escriba_el_codigo_manualme", default="O escriba el código manualmente y pulse Enter...")
        )
        self.input_manual.setFixedHeight(45)
        self.input_manual.returnPressed.connect(self.procesar_entrada_manual)

        # Botón Volver/Cancelar
        self.btn_cancelar_cam = QPushButton(tr("recep.cancelar_y_volver", default="⬅ CANCELAR Y VOLVER"))
        self.btn_cancelar_cam.setObjectName("btn_peligro")
        self.btn_cancelar_cam.setFixedWidth(200)
        self.btn_cancelar_cam.clicked.connect(self.detener_camara)

        # Organizar en el layout
        layout_cam.addWidget(self.lbl_video, 0, Qt.AlignmentFlag.AlignCenter)
        layout_cam.addWidget(self.input_manual)
        layout_cam.addWidget(self.btn_cancelar_cam, 0, Qt.AlignmentFlag.AlignCenter)

    def actualizar_frame(self, image):
        """Dibuja cada frame de la cámara en el QLabel."""
        self.lbl_video.setPixmap(QPixmap.fromImage(image))

    def detener_camara(self):
        """Detiene el hilo y vuelve al panel de inicio."""
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.stop()
        self.stack.setCurrentIndex(0)


# ============================================================
# BLOQUE UTILIDADES PDF
# ============================================================

class NumberedCanvasWithLastPage(canvas.Canvas):
    """
    Añade numeración 'Página X de Y' y firmas solo en la última página.
    """

    def __init__(self, *args, on_last_page=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self._on_last_page = on_last_page

    def showPage(self):
        self._saved_page_states.append(self.__dict__.copy())
        super().showPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for page_num, state in enumerate(self._saved_page_states, start=1):
            self.__dict__.update(state)
            self.saveState()

            # Pie de página corporativo
            self.setFont("Helvetica-Oblique", 8)
            self.setFillColor(colors.grey)
            self.drawCentredString(
                A4[0] / 2, 1.2 * cm, "SMART MANAGER - SISTEMA DE GESTIÓN LOGÍSTICA"
            )

            # Numeración
            self.setFont("Helvetica", 8)
            self.drawRightString(
                A4[0] - 1.5 * cm, 1.2 * cm, f"Página {page_num} de {total_pages}"
            )

            # Firmas en la última página
            if page_num == total_pages and callable(self._on_last_page):
                self._on_last_page(self)

            self.restoreState()
            super().showPage()
        super().save()


# ============================================================
# BLOQUE HISTORIAL DE TRASPASOS
# ============================================================

class HistorialTraspasosPage(QWidget):

    def __init__(self, usuario, codigo_local="ALMC"):
        super().__init__()
        self.codigo_local = codigo_local
        # Punto 3: Unificación de variable de usuario
        self.usuario = usuario
        self.setup_ui()
        self.cargar_datos()

    def setup_ui(self):
        """Configura la interfaz visual completa con estilo GitHub Dark."""
        self.setObjectName("panel_contenido")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(25)

        # --- CABECERA ---
        header = QHBoxLayout()
        title_container = QVBoxLayout()

        title = QLabel(tr("recep.historial_de_traspasos", default="Historial de Traspasos"))
        title.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
        title.setObjectName("titulo_cian")

        subtitle = QLabel(tr("recep.consulta_trazabilidad_y_gest", default="Consulta, trazabilidad y gestión de envíos realizados."))
        subtitle.setObjectName("subtitulo_muted")

        title_container.addWidget(title)
        title_container.addWidget(subtitle)

        # Punto 4: Unificado a self.btn_actualizar con estilo corporativo
        self.btn_actualizar = QPushButton(tr("recep.actualizar", default="🔄 ACTUALIZAR"))
        self.btn_actualizar.setObjectName("btn_primario")
        self.btn_actualizar.setFixedSize(180, 45)
        self.btn_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_actualizar.clicked.connect(self.ejecutar_actualizacion)

        header.addLayout(title_container)
        header.addStretch()
        header.addWidget(self.btn_actualizar)
        layout.addLayout(header)

        # --- BUSCADOR HÍBRIDO ---
        h_buscador_layout = QHBoxLayout()
        h_buscador_layout.setSpacing(10)

        self.input_busqueda = QLineEdit()
        self.input_busqueda.setObjectName("input_buscador")
        self.input_busqueda.setPlaceholderText(
            tr("recep.filtrar_por_id_pale_articulo", default="🔍 Filtrar por ID, Palé, Artículo, EAN, Destino o Fecha...")
        )
        self.input_busqueda.setFixedHeight(50)

        # ELIMINAR SUGERENCIAS LOGÍSTICAS (QCompleter)
        self.input_busqueda.setCompleter(None)

        self.input_busqueda.textChanged.connect(self.cargar_datos)

        self.btn_camara = QPushButton(tr("recep.scan", default="📷 SCAN"))
        self.btn_camara.setObjectName("btn_secundario")
        self.btn_camara.setFixedSize(110, 50)
        self.btn_camara.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_camara.clicked.connect(self.abrir_camara_filtro)

        h_buscador_layout.addWidget(self.input_busqueda)
        h_buscador_layout.addWidget(self.btn_camara)
        layout.addLayout(h_buscador_layout)

        # --- TABLA (plantilla visual global reutilizable) ---
        if construir_tabla_estilizada is not None:
            wrap_tabla, self.tabla = construir_tabla_estilizada()
        else:
            wrap_tabla = QFrame()
            wrap_tabla.setObjectName("contenedor_tabla_estandar")
            wrap_layout = QVBoxLayout(wrap_tabla)
            wrap_layout.setContentsMargins(2, 2, 2, 2)
            wrap_layout.setSpacing(0)
            self.tabla = QTableWidget()
            wrap_layout.addWidget(self.tabla)
        self.setup_tabla_estilo()
        layout.addWidget(wrap_tabla)

    def setup_tabla_estilo(self):
        columnas = ["ID TRASPASO", "FECHA ENVÍO", "DESTINO", "ESTADO", "ACCIONES"]
        self.tabla.setColumnCount(len(columnas))
        self.tabla.setHorizontalHeaderLabels(columnas)
        self.tabla.verticalHeader().setVisible(False)
        # Altura de fila suficiente para que el botón de ACCIONES (32px + glow
        # de neón) no se vea cortado; cada traspaso tiene su espacio vital.
        self.tabla.verticalHeader().setDefaultSectionSize(60)
        # Sin padding vertical en las celdas: el padding global (8px) empujaba el
        # cell widget hacia abajo y descentraba el botón. Se mantiene el padding
        # horizontal para el texto de las columnas.
        self.tabla.setStyleSheet("QTableWidget::item { padding: 0px 8px; }")
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setShowGrid(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def cargar_datos(self):
        """Consulta la DB y renderiza los traspasos del origen local con feedback visual."""

        busqueda_texto = self.input_busqueda.text().strip()
        busqueda_param = f"%{busqueda_texto}%"

        # 1. Indicar espera por operación larga usando cursor (sin diálogo modal)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        try:

            with obtener_conexion() as conn:
                with conn.cursor() as cur:
                    query = """
                        SELECT DISTINCT h.id_documento, h.fecha_envio, h.destino, h.estado 
                        FROM documentos_logisticos h
                        LEFT JOIN documentos_logisticos_lineas d ON h.id_documento = d.id_documento
                        WHERE (h.origen = %s OR h.origen LIKE %s)
                          AND (h.id_documento LIKE %s OR h.destino LIKE %s OR h.fecha_envio LIKE %s 
                               OR d.nombre_articulo LIKE %s OR d.codigo_articulo LIKE %s OR d.id_pale LIKE %s)
                        ORDER BY h.fecha_envio DESC
                    """
                    params = (
                        self.codigo_local,
                        f"%{self.codigo_local}%",
                        *(busqueda_param,) * 6,
                    )
                    cur.execute(query, params)

                    # Convertimos a lista de diccionarios para compatibilidad total
                    columnas = [desc[0] for desc in cur.description]
                    rows = [dict(zip(columnas, row, strict=False)) for row in cur.fetchall()]

                    self.tabla.setRowCount(0)

                    for i, row in enumerate(rows):
                        self.tabla.insertRow(i)
                        id_doc = str(row["id_documento"])

                        # Celdas básicas
                        self.tabla.setItem(i, 0, QTableWidgetItem(id_doc))
                        self.tabla.setItem(
                            i, 1, QTableWidgetItem(str(row["fecha_envio"] or "-"))
                        )
                        self.tabla.setItem(
                            i, 2, QTableWidgetItem(str(row["destino"] or "N/D"))
                        )

                        # Estado con colores neón
                        texto_estado = str(row["estado"] or "DESCONOCIDO").upper()
                        item_estado = QTableWidgetItem(texto_estado)
                        item_estado.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        item_estado.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))

                        # Lógica de colores unificada
                        if texto_estado in [
                            "FINALIZADO",
                            "RECIBIDO",
                            "ENTREGADO",
                            "PROCESADO",
                        ]:
                            color = "#00FFC6"  # Cian Neón
                        elif texto_estado in ["PENDIENTE", "EN TRANSITO", "EN CAMINO"]:
                            color = "#F1C40F"  # Amarillo
                        else:
                            color = "#FF4B4B"  # Rojo/Error

                        item_estado.setForeground(QColor(color))
                        self.tabla.setItem(i, 3, item_estado)

                        # Método para añadir el botón de PDF en la fila
                        if hasattr(self, "agregar_boton_pdf"):
                            self.agregar_boton_pdf(i, id_doc)

        except Exception as e:
            import logging

            logging.error(f"Error cargando historial de traspasos: {e}")

            _mensaje_ui(
                self, "Error de Carga", f"No se pudo obtener el historial:\n{e}", "warning"
            )

        finally:
            # 2. Cerrar aviso siempre
            QApplication.restoreOverrideCursor()

    def ver_pdf(self, id_documento):
        """Abre el PDF existente o inicia la regeneración si falta."""

        base_path = os.getcwd()
        ruta_carpeta = os.path.join(base_path, "documentos", "albaranes")

        # Probar variantes de nombre
        rutas = [
            os.path.join(ruta_carpeta, f"ALB_{id_documento}.pdf"),
            os.path.join(ruta_carpeta, f"{id_documento}.pdf"),
        ]

        for ruta in rutas:
            if os.path.exists(ruta):
                abrir_pdf(ruta)
                return

        # Fallback: Regenerar
        if _confirmar_ui(
            self,
            "Documento no encontrado",
            f"¿Desea regenerar el PDF de {id_documento} desde la DB?",
        ):
            self.regenerar_pdf_desde_historial(id_documento)

    def agregar_boton_pdf(self, fila, id_doc):
        btn = QPushButton(tr("recep.ver_albaran", default="📄 VER ALBARÁN"))
        btn.setObjectName("btn_secundario")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Altura 44px: el QSS añade padding 10px + borde 2px (24px de chrome
        # vertical); con 32px el texto quedaba cortado.
        btn.setFixedSize(150, 44)
        # Hover swap explícito: relleno cian + texto oscuro al pasar el cursor.
        btn.setStyleSheet(
            "QPushButton{background:#161B22;color:#E6EDF3;border:2px solid #00FFC6;"
            "border-radius:10px;font-family:'Segoe UI';font-weight:700;font-size:13px;}"
            "QPushButton:hover{background:#00FFC6;color:#0D1117;}"
            "QPushButton:pressed{background:#00E0AE;color:#0D1117;}"
        )
        btn.clicked.connect(lambda: self.ver_pdf(id_doc))

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        # El contenedor debe llenar la fila para no recortar el glow del botón
        # (si no, queda en su sizeHint ~44px y corta el botón por abajo).
        container.setMinimumHeight(60)
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        # AlignHCenter|AlignVCenter centra el botón exactamente en la celda.
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self.tabla.setCellWidget(fila, 4, container)

    def abrir_camara_filtro(self):
        """
        Lanza el escáner de cámara para filtrar el historial.
        Implementa feedback visual en el buscador tras una lectura exitosa.
        """
        try:
            # Importación local para evitar dependencias circulares

            # Instanciamos el diálogo (ScannerDialog ya maneja el look PDA)
            dialogo = ScannerDialog(parent=self, usuario=self.usuario)

            # Conectamos la señal personalizada para aplicar el filtro dinámicamente
            dialogo.codigo_leido.connect(self.aplicar_filtro_escaneado)

            dialogo.exec()

        except Exception as e:
            # Notificación de error con estilo oscuro si fuera posible,
            # o el estándar de la plataforma por seguridad
            _mensaje_ui(
                self,
                "Error de Hardware",
                f"No se pudo inicializar la cámara o el diálogo: {str(e)}",
                "error",
            )

    def aplicar_filtro_escaneado(self, codigo):
        """
        Slot encargado de recibir el código del escáner y actualizar la UI.
        """
        if codigo:
            codigo_limpio = str(codigo).strip()
            self.input_busqueda.setText(codigo_limpio)

            if feedback_lineedit_exito is not None:
                feedback_lineedit_exito(self.input_busqueda, 1200)

            # Ejecutamos la carga con el nuevo filtro
            self.cargar_datos()

    def regenerar_pdf_desde_historial(self, id_traspaso):
        """Inicia el PdfWorker para reconstruir el documento."""
        try:

            usuario_actual = getattr(self, "usuario", "SISTEMA")

            self.worker = PdfWorker(
                id_traspaso=id_traspaso,
                pales_data=[],  # El worker buscará el detalle en DB
                origen=self.codigo_local,
                destino="",
                usuario=usuario_actual,
                tipo_operacion="traspaso",
            )
            self.worker.finished.connect(self.on_pdf_regenerado)
            self.worker.error.connect(
                lambda e: _mensaje_ui(self, "Error", str(e), "error")
            )

            self.btn_actualizar.setText(tr("recep.generando", default="⏳ Generando..."))
            self.btn_actualizar.setEnabled(False)
            self.worker.start()
        except Exception as e:
            _mensaje_ui(self, "Error", f"Fallo al iniciar regeneración: {e}", "error")

    def on_pdf_regenerado(self, resultado):
        """Callback tras finalizar el PdfWorker."""

        ruta_albaran, _, _ = resultado
        self.finalizar_carga()
        abrir_pdf(ruta_albaran)
        _mensaje_ui(self, "Éxito", "Documento regenerado correctamente.", "success")

    def ejecutar_actualizacion(self):
        """
        Inicia la animación de sincronización con el icono de carga y
        actualiza los datos de la base de datos.
        """
        self.btn_actualizar.setEnabled(False)
        self.btn_actualizar.setText(tr("recep.cargando", default="⌛ CARGANDO..."))
        QApplication.processEvents()
        QTimer.singleShot(300, self.finalizar_carga)

    def finalizar_carga(self):
        self.cargar_datos()
        self.btn_actualizar.setEnabled(True)
        self.btn_actualizar.setText(tr("recep.actualizar_2", default="🔄 ACTUALIZAR"))


# ============================================================
# BLOQUE PANTALLA DE INICIO
# ============================================================

class LandingScannerPage(QWidget):
    """Página de inicio para la sección de Scanner con estilo moderno."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Aplicamos el fondo general para asegurar consistencia
        self.setObjectName("panel_contenido")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        # Icono de Recepción Logística (📥) - Estilo limpio
        self.lbl_icono = QLabel("📥")
        self.lbl_icono.setObjectName("icono_hero")
        self.lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Texto Informativo - Neón Corporativo
        self.lbl_info = QLabel(tr("recep.recepcion_de_mercancia", default="RECEPCIÓN DE MERCANCÍA"))
        self.lbl_info.setObjectName("titulo_cian")
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Botón Central - Estilo Global Neón
        self.btn_iniciar = QPushButton(tr("recep.abrir_escaner_de_entrada", default="🚀  ABRIR ESCÁNER DE ENTRADA"))
        self.btn_iniciar.setObjectName("btn_primario")
        self.btn_iniciar.setFixedSize(
            320, 65
        )  # Ligeramente más grande para mejor impacto
        self.btn_iniciar.setCursor(Qt.CursorShape.PointingHandCursor)

        layout.addStretch()
        layout.addWidget(self.lbl_icono)
        layout.addWidget(self.lbl_info)
        layout.addSpacing(15)
        layout.addWidget(self.btn_iniciar, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()


# ============================================================
# BLOQUE REABASTECIMIENTO — constantes, helpers y clases
# ============================================================

_REAB_CIAN = "#00FFC6"
_REAB_FONDO = "#0E1117"
_REAB_PANEL_BG = "#161B22"
_REAB_GRIS_PANEL = "#1A1D23"
_REAB_BORDE = "#30363D"

_SPIN_SS = f"""
QSpinBox {{
    background-color: #161B22;
    color: #FFFFFF;
    border: 2px solid {_REAB_CIAN};
    border-radius: 10px;
    padding: 6px 10px;
    font-size: 13px;
    font-family: 'Segoe UI';
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 18px;
    border: none;
    background: #1A2230;
}}
"""

_COMBO_SS = f"""
QComboBox {{
    background-color: #161B22;
    color: #FFFFFF;
    border: 2px solid {_REAB_CIAN};
    border-radius: 10px;
    padding: 6px 10px;
    font-size: 13px;
    font-family: 'Segoe UI';
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background-color: #161B22;
    color: #FFFFFF;
    selection-background-color: {_REAB_CIAN};
    selection-color: #0E1117;
    border: 1px solid {_REAB_CIAN};
}}
"""

_CFG_INPUT_SS = f"""
QLineEdit {{
    background-color: #161B22;
    color: #FFFFFF;
    border: 2px solid {_REAB_CIAN};
    border-radius: 10px;
    padding: 4px 8px;
    font-size: 13px;
    font-family: 'Segoe UI';
}}
QLineEdit:focus {{
    border: 2px solid #00E6B2;
    background-color: #1A2230;
    outline: none;
}}
"""

_REAB_NEON_INPUT_SS = f"""
QLineEdit {{
    background-color: #161B22;
    color: #FFFFFF;
    border: 2px solid {_REAB_CIAN};
    border-radius: 12px;
    padding: 8px 14px;
    font-size: 13px;
    font-family: 'Segoe UI';
}}
QLineEdit:focus {{
    border: 2px solid #00E6B2;
    background-color: #1A2230;
    outline: none;
}}
"""

_REAB_BTN_CIAN_SS = f"""
QPushButton {{
    background-color: #0E1117;
    color: {_REAB_CIAN};
    font-weight: bold;
    border-radius: 14px;
    padding: 12px 24px;
    font-size: 13px;
    font-family: 'Segoe UI';
    border: 2px solid {_REAB_CIAN};
    outline: none;
}}
QPushButton:hover {{
    background-color: {_REAB_CIAN};
    color: #0E1117;
    border: 2px solid {_REAB_CIAN};
}}
QPushButton:pressed {{
    background-color: #00C79A;
    color: #0E1117;
}}
QPushButton:focus {{
    outline: none;
}}
"""

_REAB_BTN_ROJO_SS = """
QPushButton {
    background-color: #0E1117;
    color: #FF4B4B;
    font-weight: bold;
    border-radius: 14px;
    padding: 10px 20px;
    font-size: 12px;
    font-family: 'Segoe UI';
    border: 2px solid #FF4B4B;
    outline: none;
}
QPushButton:hover {
    background-color: #FF4B4B;
    color: #0E1117;
    border: 2px solid #FF4B4B;
}
QPushButton:focus {
    outline: none;
}
"""

_TAB_BTN_SS = f"""
QPushButton {{
    background-color: {_REAB_FONDO};
    color: {_REAB_CIAN};
    border: 2px solid {_REAB_CIAN};
    border-radius: 22px;
    font-size: 13px;
    font-weight: bold;
    font-family: 'Segoe UI';
    padding: 10px 20px;
    outline: none;
}}
QPushButton:hover {{
    background-color: rgba(0,255,198,0.12);
    border: 2px solid {_REAB_CIAN};
}}
"""

_TAB_BTN_ACTIVO_SS = f"""
QPushButton {{
    background-color: {_REAB_CIAN};
    color: {_REAB_FONDO};
    border: 2px solid {_REAB_CIAN};
    border-radius: 22px;
    font-size: 13px;
    font-weight: bold;
    font-family: 'Segoe UI';
    padding: 10px 20px;
    outline: none;
}}
QPushButton:hover {{
    background-color: #00E6B2;
    border: 2px solid #00E6B2;
}}
"""

_ACT_BTN_SS = f"""
QPushButton {{
    background-color: {_REAB_FONDO};
    color: {_REAB_CIAN};
    border: 2px solid {_REAB_CIAN};
    border-radius: 22px;
    font-size: 14px;
    font-weight: bold;
    font-family: 'Segoe UI';
    padding: 10px 22px;
    outline: none;
}}
QPushButton:hover {{
    background-color: {_REAB_CIAN};
    color: {_REAB_FONDO};
}}
QPushButton:pressed {{
    background-color: #00C79A;
    color: {_REAB_FONDO};
}}
"""

_DIA_BTN_SS = f"""
QPushButton {{
    background-color: {_REAB_FONDO};
    color: #8B949E;
    border: 2px solid #8B949E;
    border-radius: 10px;
    font-size: 13px;
    font-weight: bold;
    font-family: 'Segoe UI';
    padding: 6px 0px;
    outline: none;
}}
QPushButton:hover {{
    border-color: {_REAB_CIAN};
    color: {_REAB_CIAN};
}}
QPushButton:checked {{
    background-color: {_REAB_CIAN};
    color: #0E1117;
    border: 2px solid {_REAB_CIAN};
}}
"""

_CMB_HORA_SS = f"""
QComboBox {{
    background-color: #161B22;
    color: #FFFFFF;
    border: 2px solid {_REAB_CIAN};
    border-radius: 10px;
    padding: 6px 10px;
    font-size: 13px;
    font-weight: bold;
    font-family: 'Segoe UI';
    outline: none;
}}
QComboBox::drop-down {{
    width: 0px;
    border: none;
}}
QComboBox::down-arrow {{
    image: none;
    width: 0px;
    height: 0px;
}}
"""

_SAVE_BTN_SS = """
QPushButton {
    background-color: #1ED760;
    color: #0E1117;
    border: 2px solid #1ED760;
    border-radius: 10px;
    font-size: 14px;
    font-weight: bold;
    font-family: 'Segoe UI';
    padding: 10px 26px;
    outline: none;
}
QPushButton:hover {
    background-color: #FFFFFF;
    color: #0E1117;
    border: 2px solid #1ED760;
}
QPushButton:pressed {
    background-color: #12A845;
    color: #0E1117;
    border: 2px solid #12A845;
}
"""

_EMAIL_INPUT_SS = f"""
QLineEdit {{
    background-color: #161B22;
    color: #FFFFFF;
    border: 2px solid {_REAB_CIAN};
    border-radius: 10px;
    padding: 6px 14px;
    font-size: 13px;
    font-family: 'Segoe UI';
}}
QLineEdit:focus {{
    border: 2px solid #00E6B2;
    background-color: #1A2230;
    outline: none;
}}
"""

_ESTADO_COLORES = {
    "pendiente": ("#FFC857", "#0E1117"),
    "aprobado":  (_REAB_CIAN, "#0E1117"),
    "enviado":   ("#58A6FF", "#FFFFFF"),
    "recibido":  ("#00FF87", "#0E1117"),
    "cancelado": ("#FF4B4B", "#FFFFFF"),
}


def _sombra_cian_reab(widget):
    fx = QGraphicsDropShadowEffect()
    fx.setBlurRadius(22)
    fx.setColor(QColor(_REAB_CIAN))
    fx.setOffset(0)
    widget.setGraphicsEffect(fx)


def _crear_tabla_reab(parent, cols):
    cont, tabla = construir_tabla_estilizada(parent)
    tabla.setStyleSheet(f"""
        QTableWidget {{
            border: none;
            background-color: transparent;
            outline: none;
        }}
        QHeaderView {{
            background-color: transparent;
            border: none;
        }}
        QHeaderView::section {{
            background-color: #1A1D23;
            color: {_REAB_CIAN};
            border: none;
        }}
        QHeaderView::section:hover {{
            background-color: {_REAB_CIAN};
            color: #0E1117;
        }}
        QHeaderView::section:first {{
            border-top-left-radius: 18px;
        }}
        QHeaderView::section:last {{
            border-top-right-radius: 18px;
        }}
    """)
    cont.layout().setContentsMargins(2, 2, 2, 2)
    tabla.setColumnCount(len(cols))
    tabla.setHorizontalHeaderLabels(cols)
    tabla.horizontalHeader().setStretchLastSection(True)
    tabla.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    tabla.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    tabla.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return cont, tabla


def _reab_buscar_articulos(query: str):
    try:
        like = f"%{query}%"
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT codigo, nombre,
                           COALESCE(Stock_tienda, 0),
                           COALESCE(Stock_total, 0),
                           COALESCE(Stock_central, 0)
                    FROM articulos
                    WHERE codigo LIKE %s OR nombre LIKE %s
                    ORDER BY nombre ASC
                    LIMIT 200
                    """,
                    (like, like),
                )
                return cur.fetchall()
    except Exception:
        return []


def _reab_get_todos_articulos():
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT codigo, nombre FROM articulos ORDER BY nombre ASC")
                return cur.fetchall()
    except Exception:
        return []


def _reab_get_articulo_stock(codigo: str):
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT nombre, COALESCE(Stock_tienda,0), COALESCE(Stock_total,0), "
                    "COALESCE(Stock_central,0), COALESCE(Stock_esperado,0) "
                    "FROM articulos WHERE codigo=%s",
                    (codigo,),
                )
                row = cur.fetchone()
        if row:
            return {
                "nombre": row[0],
                "lineal": row[1],
                "almacen": row[2],
                "central": row[3],
                "esperado": row[4],
            }
        return None
    except Exception:
        return None


def _reab_obtener_info_empresa() -> dict:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT nombre_empresa, codigo_local FROM configuraciones LIMIT 1"
                )
                r = cur.fetchone()
                if r:
                    return {"nombre": r[0] or "SMART MANAGER", "codigo": r[1] or ""}
    except Exception:
        pass
    return {"nombre": "SMART MANAGER", "codigo": ""}


def _reab_enviar_email_pdf_impl(email_destino: str, ruta_pdf: str,
                                smtp_user: str = "", smtp_pass: str = "",
                                props: list = None, solo_prueba: bool = False) -> bool:
    import smtplib
    from email import encoders as _enc
    from email.mime.base import MIMEBase
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    from src.utils.reab_webhook import generar_urls
    if not smtp_user:
        smtp_user = os.environ.get("SMTP_USER", "")
    if not smtp_pass:
        smtp_pass = os.environ.get("SMTP_PASSWORD", "")
    if not smtp_user or not smtp_pass:
        import logging
        logging.getLogger("reabastecimiento").warning(
            "SMTP no configurado. Configura el correo remitente en RESPONSABLE LOGÍSTICA."
        )
        return False
    domain = smtp_user.split("@")[-1].lower() if "@" in smtp_user else ""
    if domain == "gmail.com":
        smtp_host, smtp_port = "smtp.gmail.com", 587
    elif domain in ("hotmail.com", "outlook.com", "live.com", "msn.com", "office365.com"):
        smtp_host, smtp_port = "smtp.office365.com", 587
    else:
        smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))

    fecha = datetime.now().strftime("%d/%m/%Y")
    filas_html = ""
    if props:
        for p in props:
            url_ap, url_de = generar_urls(p["id"])
            filas_html += f"""
            <tr>
              <td style="padding:12px 16px;border-bottom:1px solid #30363D;">{p.get('codigo','')}</td>
              <td style="padding:12px 16px;border-bottom:1px solid #30363D;">{p.get('nombre','')}</td>
              <td style="padding:12px 16px;border-bottom:1px solid #30363D;text-align:center;">{p.get('cantidad','')}</td>
              <td style="padding:12px 16px;border-bottom:1px solid #30363D;text-align:center;">
                <a href="{url_ap}" style="display:inline-block;background:#00FFC6;color:#0E1117;
                   font-weight:bold;padding:8px 18px;border-radius:8px;text-decoration:none;
                   margin-right:8px;">APROBAR</a>
                <a href="{url_de}" style="display:inline-block;background:#FF4B4B;color:#fff;
                   font-weight:bold;padding:8px 18px;border-radius:8px;text-decoration:none;">
                   DENEGAR</a>
              </td>
            </tr>"""

    html_body = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0E1117;font-family:Arial,sans-serif;color:#fff;">
  <div style="max-width:700px;margin:32px auto;background:#161B22;border-radius:16px;
              border:1px solid #30363D;overflow:hidden;">
    <div style="background:#00FFC6;padding:24px 32px;">
      <h1 style="margin:0;color:#0E1117;font-size:20px;">Smart Manager</h1>
      <p style="margin:4px 0 0;color:#0a3d2e;font-size:14px;">
        Informe de Reabastecimiento — {fecha}
      </p>
    </div>
    <div style="padding:32px;">
      <p style="color:#8B949E;margin-top:0;">
        Estimado responsable de logística, adjunto encontrará el informe PDF con las
        propuestas de reabastecimiento pendientes. Puede aprobar o denegar cada propuesta
        directamente desde este correo:
      </p>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead>
          <tr style="background:#21262D;">
            <th style="padding:10px 16px;text-align:left;color:#8B949E;">EAN</th>
            <th style="padding:10px 16px;text-align:left;color:#8B949E;">ARTÍCULO</th>
            <th style="padding:10px 16px;text-align:center;color:#8B949E;">CANTIDAD</th>
            <th style="padding:10px 16px;text-align:center;color:#8B949E;">ACCIÓN</th>
          </tr>
        </thead>
        <tbody>{filas_html}</tbody>
      </table>
      <p style="color:#8B949E;font-size:12px;margin-top:24px;">
        Los botones funcionan mientras la aplicación Smart Manager esté en ejecución en la
        tienda. El estado se actualizará automáticamente al hacer clic.
      </p>
    </div>
  </div>
</body></html>"""

    try:
        asunto = ("✉ Prueba de configuración SMTP — Smart Manager" if solo_prueba
                  else f"Informe de Reabastecimiento — {fecha}")
        msg = MIMEMultipart("alternative")
        msg["From"] = smtp_user
        msg["To"] = email_destino
        msg["Subject"] = asunto
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        if not solo_prueba and ruta_pdf:
            with open(ruta_pdf, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            _enc.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={os.path.basename(ruta_pdf)}",
            )
            msg.attach(part)
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, email_destino, msg.as_string())
        return True
    except Exception as exc:
        import logging
        logging.getLogger("reabastecimiento").error(f"Error enviando email: {exc}")
        return False


def _reab_generar_pdf(propuestas: list) -> str:
    if not _REPORTLAB_REAB_OK:
        return "ERROR: reportlab no está instalado"
    try:
        empresa = _reab_obtener_info_empresa()
        out_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../documentos/pedidos_reabastecimiento")
        )
        os.makedirs(out_dir, exist_ok=True)
        fname = f"Reabastecimiento_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        ruta = os.path.join(out_dir, fname)

        doc = _RL_DOC(ruta, pagesize=_RL_A4,
                      leftMargin=1.8*_RL_CM, rightMargin=1.8*_RL_CM,
                      topMargin=2*_RL_CM, bottomMargin=2.2*_RL_CM)

        styles = _RL_STYLES()
        negro = _RL_COLORS.black
        gris_oscuro = _RL_COLORS.HexColor("#333333")
        gris_medio = _RL_COLORS.HexColor("#666666")
        gris_claro = _RL_COLORS.HexColor("#F4F4F4")
        gris_linea = _RL_COLORS.HexColor("#CCCCCC")

        title_st = _RL_PARASTYLE("t_title", parent=styles["Normal"],
                                 fontSize=22, leading=28, fontName="Helvetica-Bold",
                                 textColor=negro, spaceAfter=3)
        sub_st = _RL_PARASTYLE("t_sub", parent=styles["Normal"],
                                fontSize=13, leading=17, fontName="Helvetica",
                                textColor=gris_oscuro, spaceAfter=2)
        ref_st = _RL_PARASTYLE("t_ref", parent=styles["Normal"],
                                fontSize=10, leading=14, fontName="Helvetica-Bold",
                                textColor=negro, spaceAfter=2)
        meta_st = _RL_PARASTYLE("t_meta", parent=styles["Normal"],
                                 fontSize=9, leading=13, fontName="Helvetica",
                                 textColor=gris_medio, spaceAfter=0)
        section_st = _RL_PARASTYLE("t_sec", parent=styles["Normal"],
                                   fontSize=10, leading=14, fontName="Helvetica-Bold",
                                   textColor=negro, spaceBefore=10, spaceAfter=5)
        footer_st = _RL_PARASTYLE("t_foot", parent=styles["Normal"],
                                   fontSize=8, leading=11, fontName="Helvetica",
                                   textColor=gris_medio, alignment=1)

        sep = _RL_TABLE([[""]], colWidths=[17.4*_RL_CM])
        sep.setStyle(_RL_TABLESTYLE([
            ("LINEBELOW",     (0, 0), (-1, -1), 1.2, negro),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))

        col_widths = [2.2*_RL_CM, 7.0*_RL_CM, 2.0*_RL_CM, 3.1*_RL_CM, 3.1*_RL_CM]
        header_row = [["CÓDIGO", "ARTÍCULO", "CANTIDAD", "STOCK ACTUAL", "STOCK OBJ."]]
        data_rows = [
            [p["codigo"], p["nombre"], str(p["cantidad"]),
             str(p["stock_actual"]), str(p["stock_objetivo"])]
            for p in propuestas
        ]
        tbl = _RL_TABLE(header_row + data_rows, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(_RL_TABLESTYLE([
            ("BACKGROUND",    (0, 0), (-1, 0),  negro),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  _RL_COLORS.white),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0),  9),
            ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [_RL_COLORS.white, gris_claro]),
            ("TEXTCOLOR",     (0, 1), (-1, -1), negro),
            ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",      (0, 1), (-1, -1), 9),
            ("ALIGN",         (0, 1), (-1, -1), "CENTER"),
            ("ALIGN",         (1, 1), (1, -1),  "LEFT"),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            ("GRID",          (0, 0), (-1, -1), 0.4, gris_linea),
            ("LINEABOVE",     (0, 0), (-1, 0),  1.5, negro),
            ("LINEBELOW",     (0, 0), (-1, 0),  1.0, negro),
            ("LINEBELOW",     (0, -1), (-1, -1), 1.0, negro),
        ]))

        now_str = datetime.now().strftime("%d/%m/%Y  %H:%M")
        ref_line = empresa["nombre"]
        if empresa["codigo"]:
            ref_line += f"  ·  Ref. tienda: {empresa['codigo']}"

        story = [
            _RL_PARA(empresa["nombre"].upper(), title_st),
            _RL_PARA("Propuesta de Reabastecimiento — Artículos Pendientes", sub_st),
            _RL_PARA(f"Referencia: {empresa['codigo'] or '—'}", ref_st),
            _RL_PARA(
                f"Fecha de emisión: {now_str}  ·  Artículos pendientes: {len(propuestas)}",
                meta_st,
            ),
            _RL_SPACER(1, 0.3*_RL_CM),
            sep,
            _RL_SPACER(1, 0.4*_RL_CM),
            _RL_PARA("ARTÍCULOS PENDIENTES DE REABASTECIMIENTO", section_st),
            tbl,
            _RL_SPACER(1, 0.6*_RL_CM),
            sep,
            _RL_SPACER(1, 0.2*_RL_CM),
            _RL_PARA(
                f"Documento generado automáticamente por Smart Manager  ·  {now_str}",
                footer_st,
            ),
        ]
        doc.build(story)
        return ruta
    except Exception as e:
        return f"ERROR: {e}"


class StockReplenishmentEngine(QObject):
    propuesta_creada = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

    def evaluate(self, codigo: str):
        cfg = _reab_obtener_config(codigo)
        if not cfg or not cfg["automatico"]:
            return
        art = _reab_get_articulo_stock(codigo)
        if not art:
            return
        stock_actual = art["lineal"] + art["almacen"]
        if stock_actual > cfg["umbral_min"]:
            return
        if _reab_propuesta_pendiente_existe(codigo):
            return
        cantidad = max(0, cfg["stock_objetivo"] - stock_actual)
        if cantidad <= 0:
            return
        origen = "ALMACÉN CENTRAL" if art.get("central", 0) > 0 else "PROVEEDOR"
        pid = _reab_crear_propuesta(
            codigo, art["nombre"], cantidad,
            origen, stock_actual, cfg["stock_objetivo"]
        )
        if pid:
            self.propuesta_creada.emit({
                "id": pid, "codigo": codigo, "nombre": art["nombre"],
                "cantidad": cantidad, "origen": origen,
            })

    def evaluate_all(self):
        for item in _reab_listar_config():
            self.evaluate(item["codigo"])


class _BuscarArticuloDialogReab(QDialog):
    articulo_seleccionado = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos = None
        self._resultado = None
        self._articulos = []
        self._build_ui()
        self.resize(600, 480)
        if parent:
            pg = parent.geometry()
            self.move(
                pg.center().x() - 300,
                pg.center().y() - 240,
            )

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #0D1117;
                border: 2px solid {_REAB_CIAN};
                border-radius: 18px;
            }}
        """)
        card.mousePressEvent = self._card_press
        card.mouseMoveEvent = self._card_move
        card.mouseReleaseEvent = lambda e: setattr(self, '_drag_pos', None)
        outer.addWidget(card)

        ly = QVBoxLayout(card)
        ly.setContentsMargins(24, 20, 24, 20)
        ly.setSpacing(14)

        title = QLabel(tr("recep.anadir_articulo_al_control", default="AÑADIR ARTÍCULO AL CONTROL"))
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_REAB_CIAN}; background: transparent; border: none;")
        ly.addWidget(title)

        self.buscador = QLineEdit()
        self.buscador.setPlaceholderText(tr("recep.buscar_por_codigo_o_nombre", default="Buscar por código o nombre…"))
        self.buscador.setStyleSheet(_REAB_NEON_INPUT_SS)
        self.buscador.setFixedHeight(44)
        self.buscador.textChanged.connect(self._filtrar)
        ly.addWidget(self.buscador)

        self.lista = QTableWidget(0, 2)
        self.lista.setHorizontalHeaderLabels(["Código", "Nombre"])
        self.lista.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.lista.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.lista.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.lista.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.lista.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.lista.setStyleSheet(f"""
            QTableWidget {{ background: #161B22; color: #FFF; border: 1px solid {_REAB_BORDE}; border-radius: 10px; }}
            QHeaderView::section {{ background: #1A1D23; color: {_REAB_CIAN}; border: none; padding: 6px; }}
            QTableWidget::item:selected {{ background: {_REAB_CIAN}44; color: #FFF; }}
        """)
        self.lista.setFixedHeight(180)
        self.lista.itemDoubleClicked.connect(self._seleccionar_fila)
        ly.addWidget(self.lista)

        cfg_frame = QFrame()
        cfg_frame.setStyleSheet(f"background: #161B22; border: 1px solid {_REAB_BORDE}; border-radius: 12px;")
        cfg_ly = QVBoxLayout(cfg_frame)
        cfg_ly.setContentsMargins(16, 12, 16, 12)
        cfg_ly.setSpacing(10)

        def _row(label, widget):
            r = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #8B949E; font-size: 13px; background: transparent; border: none;")
            lbl.setFixedWidth(160)
            r.addWidget(lbl)
            r.addWidget(widget)
            cfg_ly.addLayout(r)

        self.spin_umbral = QSpinBox()
        self.spin_umbral.setRange(0, 9999)
        self.spin_umbral.setValue(5)
        self.spin_umbral.setStyleSheet(_SPIN_SS)
        self.spin_umbral.setFixedHeight(38)
        _row("Umbral mínimo:", self.spin_umbral)

        self.spin_objetivo = QSpinBox()
        self.spin_objetivo.setRange(0, 9999)
        self.spin_objetivo.setValue(20)
        self.spin_objetivo.setStyleSheet(_SPIN_SS)
        self.spin_objetivo.setFixedHeight(38)
        _row("Stock objetivo:", self.spin_objetivo)

        self.combo_origen = QComboBox()
        self.combo_origen.addItems(["ALMACÉN CENTRAL", "PROVEEDOR"])
        self.combo_origen.setStyleSheet(_COMBO_SS)
        self.combo_origen.setFixedHeight(38)
        _row("Origen de reposición:", self.combo_origen)

        self.chk_auto = QCheckBox(tr("recep.activar_reposicion_automatic", default="Activar reposición automática"))
        self.chk_auto.setChecked(True)
        self.chk_auto.setStyleSheet("color: #FFF; font-size: 13px; background: transparent; border: none;")
        cfg_ly.addWidget(self.chk_auto)

        ly.addWidget(cfg_frame)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_ok = QPushButton(tr("recep.anadir", default="AÑADIR"))
        btn_ok.setStyleSheet(_REAB_BTN_CIAN_SS)
        btn_ok.setFixedHeight(44)
        btn_ok.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_ok.clicked.connect(self._confirmar)
        btn_cancel = QPushButton(tr("recep.cancelar", default="CANCELAR"))
        btn_cancel.setStyleSheet(_REAB_BTN_ROJO_SS)
        btn_cancel.setFixedHeight(44)
        btn_cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        ly.addLayout(btn_row)

        self._cargar_articulos()

    def _cargar_articulos(self):
        self._articulos = _reab_get_todos_articulos()
        self._mostrar(self._articulos)

    def _filtrar(self, texto):
        t = texto.lower().strip()
        if not t:
            self._mostrar(self._articulos)
        else:
            self._mostrar([a for a in self._articulos if t in a[0].lower() or t in a[1].lower()])

    def _mostrar(self, rows):
        self.lista.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, v in enumerate([str(row[0]), str(row[1])]):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.lista.setItem(r, c, item)

    def _seleccionar_fila(self, item):
        row = item.row()
        codigo_item = self.lista.item(row, 0)
        if codigo_item:
            self.buscador.setText(codigo_item.text())

    def _confirmar(self):
        rows = self.lista.selectedItems()
        if not rows:
            texto = self.buscador.text().strip()
            if not texto:
                return
            codigo = texto.split("–")[0].split("-")[0].strip()
        else:
            row = rows[0].row()
            codigo = self.lista.item(row, 0).text()
        art = _reab_get_articulo_stock(codigo)
        if not art:
            QMessageBox.warning(self, "Error", "Artículo no encontrado.")
            return
        _reab_upsert_config(
            codigo,
            self.spin_umbral.value(),
            self.spin_objetivo.value(),
            self.combo_origen.currentText(),
            self.chk_auto.isChecked(),
        )
        self.articulo_seleccionado.emit({"codigo": codigo, "nombre": art["nombre"]})
        self.accept()

    def _card_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _card_move(self, event):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)


class _EditarConfigDialogReab(QDialog):
    def __init__(self, codigo: str, nombre: str, cfg: dict, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos = None
        self.codigo = codigo
        self._build_ui(nombre, cfg)
        self.resize(480, 360)
        if parent:
            pg = parent.geometry()
            self.move(pg.center().x() - 240, pg.center().y() - 180)

    def _build_ui(self, nombre, cfg):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setStyleSheet(f"QFrame {{ background: #0D1117; border: 2px solid {_REAB_CIAN}; border-radius: 18px; }}")
        card.mousePressEvent = lambda e: setattr(self, '_drag_pos', e.globalPosition().toPoint() - self.frameGeometry().topLeft()) if e.button() == Qt.MouseButton.LeftButton else None
        card.mouseMoveEvent = lambda e: self.move(e.globalPosition().toPoint() - self._drag_pos) if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton else None
        card.mouseReleaseEvent = lambda e: setattr(self, '_drag_pos', None)
        outer.addWidget(card)

        ly = QVBoxLayout(card)
        ly.setContentsMargins(24, 20, 24, 20)
        ly.setSpacing(14)

        title = QLabel(tr("recep.editar_configuracion", default="EDITAR CONFIGURACIÓN"))
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_REAB_CIAN}; background: transparent; border: none;")
        ly.addWidget(title)

        lbl_art = QLabel(f"{nombre}  ({self.codigo})")
        lbl_art.setStyleSheet("color: #8B949E; font-size: 12px; background: transparent; border: none;")
        ly.addWidget(lbl_art)

        def _row(label, widget):
            r = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #8B949E; font-size: 13px; background: transparent; border: none;")
            lbl.setFixedWidth(160)
            r.addWidget(lbl)
            r.addWidget(widget)
            ly.addLayout(r)

        self.spin_umbral = QSpinBox()
        self.spin_umbral.setRange(0, 9999)
        self.spin_umbral.setValue(cfg.get("umbral_min", 5))
        self.spin_umbral.setStyleSheet(_SPIN_SS)
        self.spin_umbral.setFixedHeight(38)
        _row("Umbral mínimo:", self.spin_umbral)

        self.spin_objetivo = QSpinBox()
        self.spin_objetivo.setRange(0, 9999)
        self.spin_objetivo.setValue(cfg.get("stock_objetivo", 20))
        self.spin_objetivo.setStyleSheet(_SPIN_SS)
        self.spin_objetivo.setFixedHeight(38)
        _row("Stock objetivo:", self.spin_objetivo)

        self.combo_origen = QComboBox()
        self.combo_origen.addItems(["ALMACÉN CENTRAL", "PROVEEDOR"])
        self.combo_origen.setCurrentText(cfg.get("origen", "ALMACÉN CENTRAL"))
        self.combo_origen.setStyleSheet(_COMBO_SS)
        self.combo_origen.setFixedHeight(38)
        _row("Origen:", self.combo_origen)

        self.chk_auto = QCheckBox(tr("recep.reposicion_automatica", default="Reposición automática"))
        self.chk_auto.setChecked(cfg.get("automatico", True))
        self.chk_auto.setStyleSheet("color: #FFF; font-size: 13px; background: transparent; border: none;")
        ly.addWidget(self.chk_auto)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_ok = QPushButton(tr("recep.guardar", default="GUARDAR"))
        btn_ok.setStyleSheet(_REAB_BTN_CIAN_SS)
        btn_ok.setFixedHeight(44)
        btn_ok.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_ok.clicked.connect(self._guardar)
        btn_cancel = QPushButton(tr("recep.cancelar_2", default="CANCELAR"))
        btn_cancel.setStyleSheet(_REAB_BTN_ROJO_SS)
        btn_cancel.setFixedHeight(44)
        btn_cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        ly.addLayout(btn_row)

    def _guardar(self):
        _reab_upsert_config(
            self.codigo,
            self.spin_umbral.value(),
            self.spin_objetivo.value(),
            self.combo_origen.currentText(),
            self.chk_auto.isChecked(),
        )
        self.accept()


class _HistorialDialogReab(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos = None
        self._build_ui()
        self.resize(900, 540)
        if parent:
            pg = parent.geometry()
            self.move(pg.center().x() - 450, pg.center().y() - 270)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setStyleSheet(f"QFrame {{ background: #0D1117; border: 2px solid {_REAB_CIAN}; border-radius: 18px; }}")
        card.mousePressEvent = lambda e: setattr(self, '_drag_pos', e.globalPosition().toPoint() - self.frameGeometry().topLeft()) if e.button() == Qt.MouseButton.LeftButton else None
        card.mouseMoveEvent = lambda e: self.move(e.globalPosition().toPoint() - self._drag_pos) if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton else None
        card.mouseReleaseEvent = lambda e: setattr(self, '_drag_pos', None)
        outer.addWidget(card)

        ly = QVBoxLayout(card)
        ly.setContentsMargins(24, 20, 24, 20)
        ly.setSpacing(14)

        title = QLabel(tr("recep.historial_de_propuestas", default="HISTORIAL DE PROPUESTAS"))
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_REAB_CIAN}; background: transparent; border: none;")
        ly.addWidget(title)

        cols = ["ID", "ARTÍCULO", "CANTIDAD", "ORIGEN", "ESTADO", "CREACIÓN", "ACCIÓN"]
        self.tabla = QTableWidget(0, len(cols))
        self.tabla.setHorizontalHeaderLabels(cols)
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tabla.setStyleSheet(f"""
            QTableWidget {{ background: #161B22; color: #FFF; border: 1px solid {_REAB_BORDE}; border-radius: 10px; outline: none; }}
            QHeaderView::section {{ background: #1A1D23; color: {_REAB_CIAN}; border: none; padding: 6px; font-size: 13px; font-weight: bold; }}
            QHeaderView::section:hover {{ background: {_REAB_CIAN}; color: #0E1117; }}
            QTableWidget::item:selected {{ background: {_REAB_CIAN}22; }}
        """)
        ly.addWidget(self.tabla)

        btn_cerrar = QPushButton(tr("recep.cerrar", default="CERRAR"))
        btn_cerrar.setStyleSheet(_REAB_BTN_ROJO_SS)
        btn_cerrar.setFixedHeight(44)
        btn_cerrar.setFixedWidth(160)
        btn_cerrar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_cerrar.clicked.connect(self.accept)
        ly.addWidget(btn_cerrar, alignment=Qt.AlignmentFlag.AlignRight)

        self._cargar()

    def _cargar(self):
        props = _reab_listar_propuestas()
        self.tabla.setRowCount(len(props))
        for r, p in enumerate(props):
            estado = p["estado"]
            bg, fg = _ESTADO_COLORES.get(estado, ("#8B949E", "#FFF"))
            vals = [
                str(p["id"]),
                p["nombre"],
                str(p["cantidad"]),
                p["origen"],
                estado.upper(),
                str(p["fecha_creacion"])[:16] if p["fecha_creacion"] else "—",
                str(p["fecha_accion"])[:16] if p["fecha_accion"] else "—",
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 4:
                    item.setBackground(QColor(bg))
                    item.setForeground(QColor(fg))
                self.tabla.setItem(r, c, item)


class _ReabItemDelegateReab(QStyledItemDelegate):
    """Rounded-corner item delegate for _ReabComboBoxReab popups."""

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        is_sel   = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        rect = QRectF(option.rect).adjusted(4, 2, -4, -2)
        path = QPainterPath()
        path.addRoundedRect(rect, 6, 6)
        if is_sel or is_hover:
            painter.fillPath(path, QColor(_REAB_CIAN))
        txt_color = QColor("#0E1117") if (is_sel or is_hover) else QColor("#FFFFFF")
        painter.setPen(txt_color)
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(
            option.rect.adjusted(14, 0, -14, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            index.data() or "",
        )
        painter.restore()

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        sh.setHeight(38)
        return sh


class _ReabComboBoxReab(QComboBox):
    """QComboBox styled for the RESPONSABLE LOGÍSTICA page."""

    _fusion_style = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_ready = False
        if _ReabComboBoxReab._fusion_style is None:
            _ReabComboBoxReab._fusion_style = QStyleFactory.create("Fusion")
        self.setStyle(_ReabComboBoxReab._fusion_style)
        self.setMaxVisibleItems(5)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(2, 2, self.width() - 4, self.height() - 4), 8, 8)
        p.setClipPath(clip)
        p.fillRect(self.width() - 30, 2, 28, self.height() - 4, QColor("#161B22"))
        p.end()

    def showPopup(self):
        if not self._popup_ready:
            self._popup_ready = True
            view = self.view()
            vp = view.viewport()
            vp.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            vp.setStyleSheet("background:#1A1D23;")
            view.setFrameShape(QFrame.Shape.NoFrame)
            view.setItemDelegate(_ReabItemDelegateReab(self))
            container = view.parent()
            if isinstance(container, QWidget) and container is not self:
                container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                container.setWindowFlags(
                    container.windowFlags()
                    | Qt.WindowType.FramelessWindowHint
                    | Qt.WindowType.NoDropShadowWindowHint
                )
        super().showPopup()
        _v = self.view()
        if _v is not None:
            _p = _v.window()
            if _p is not self:
                _p.setWindowOpacity(0.0)
        QTimer.singleShot(0, self._fix_popup)

    def _fix_popup(self):
        view = self.view()
        if view is None:
            return
        popup = view.window()
        if popup is self:
            return
        if hasattr(popup, "setFrameShape"):
            popup.setFrameShape(QFrame.Shape.NoFrame)
            popup.setLineWidth(0)
            popup.setMidLineWidth(0)
        popup.setAutoFillBackground(False)
        popup.setStyleSheet("background: transparent;")
        popup.setContentsMargins(0, 0, 0, 0)
        if popup.layout() is not None:
            popup.layout().setContentsMargins(0, 0, 0, 0)
            popup.layout().setSpacing(0)
        for _child in popup.children():
            if isinstance(_child, QWidget) and _child is not view:
                _child.setFixedSize(0, 0)
                _child.hide()
        view.setStyleSheet(
            f"QAbstractItemView{{background:#1A1D23;border:2px solid {_REAB_CIAN};"
            f"border-radius:10px;outline:none;}}"
            f"QScrollBar:vertical{{background:transparent;width:12px;margin:2px 0px;}}"
            f"QScrollBar::handle:vertical{{background:{_REAB_CIAN};min-height:24px;border-radius:6px;}}"
            f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{"
            f"border:none;background:none;width:0px;height:0px;}}"
            f"QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{{background:transparent;}}"
        )
        view.setAutoScroll(False)
        _item_h = view.sizeHintForRow(0) if self.count() > 0 else 38
        _max_view_h = 5 * _item_h + 4
        if view.height() > _max_view_h or self.count() > 5:
            view.setFixedHeight(_max_view_h)
            popup.resize(popup.width(), _max_view_h)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        # Scroll por píxel: sin hueco vacío bajo el último item.
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        sb = view.verticalScrollBar()
        if sb is not None:
            sb.show()
        global_bottom = self.mapToGlobal(QPoint(0, self.height()))
        popup.move(global_bottom.x(), global_bottom.y())
        sz = popup.size()
        if sz.width() > 0 and sz.height() > 0:
            _ = popup.winId()
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, sz.width(), sz.height()), 10, 10)
            popup.setMask(QRegion(path.toFillPolygon().toPolygon()))
        popup.setWindowOpacity(1.0)


class _ReabastecimientoPage(QWidget):
    _sig_prueba_ok = pyqtSignal()
    _sig_prueba_err = pyqtSignal()

    def __init__(self, engine: StockReplenishmentEngine, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._engine.propuesta_creada.connect(self._on_propuesta_auto)
        try:
            from src.db.conexion import stock_signals as _db_signals
            _db_signals.stock_actualizado.connect(self._on_stock_cambio)
            _db_signals.propuestas_actualizadas.connect(self._cargar_config)
            _db_signals.propuestas_actualizadas.connect(self._cargar_propuestas)
            _db_signals.propuestas_actualizadas.connect(self._cargar_historial)
        except Exception:
            pass
        self._build_ui()
        self._sig_prueba_ok.connect(self._on_prueba_ok)
        self._sig_prueba_err.connect(self._on_prueba_err)
        self._schedule_timer = QTimer(self)
        self._schedule_timer.setInterval(60_000)
        self._schedule_timer.timeout.connect(self._check_schedule)
        self._schedule_timer.start()
        try:
            from src.utils import reab_webhook as _wh
            _wh.iniciar_servidor()
            if _wh.webhook_signals is not None:
                _wh.webhook_signals.propuesta_actualizada.connect(
                    self._recargar_desde_webhook)
        except Exception:
            pass

    def _act_btn_loading(self, label, fn):
        btn = QPushButton(label)
        btn.setStyleSheet(_ACT_BTN_SS)
        btn.setFixedHeight(44)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.clicked.connect(lambda: self._with_loading(btn, fn))
        return btn

    def _with_loading(self, btn: QPushButton, fn):
        if not btn.isEnabled():
            return
        from PyQt6.QtWidgets import QApplication
        original = btn.text()
        btn.setText(tr("recep.cargando_2", default="⟳  Cargando..."))
        btn.setEnabled(False)
        QApplication.processEvents()
        try:
            fn()
        finally:
            btn.setText(original)
            btn.setEnabled(True)

    def _ir_tab(self, idx: int):
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._tab_btns):
            btn.setStyleSheet(_TAB_BTN_ACTIVO_SS if i == idx else _TAB_BTN_SS)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 16)
        root.setSpacing(14)

        lbl = QLabel(tr("recep.reabastecimiento", default="Reabastecimiento"))
        lbl.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {_REAB_CIAN};")
        root.addWidget(lbl)

        nav_row = QHBoxLayout()
        nav_row.setSpacing(12)
        nav_row.setContentsMargins(0, 0, 0, 0)

        tab_labels = [
            "ARTÍCULOS MONITORIZADOS",
            "PROPUESTAS ACTIVAS",
            "HISTORIAL COMPLETO",
            "RESPONSABLE LOGÍSTICA",
        ]
        self._tab_btns = []
        for i, label in enumerate(tab_labels):
            btn = QPushButton(label)
            btn.setFixedHeight(44)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _, idx=i: self._ir_tab(idx))
            nav_row.addWidget(btn)
            self._tab_btns.append(btn)

        root.addLayout(nav_row)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background: {_REAB_FONDO};")

        # Page 0: ARTÍCULOS MONITORIZADOS
        page0 = QWidget()
        page0.setStyleSheet(f"background: {_REAB_FONDO};")
        p0_ly = QVBoxLayout(page0)
        p0_ly.setContentsMargins(0, 8, 0, 0)
        p0_ly.setSpacing(8)

        p0_hdr = QHBoxLayout()
        btn_guardar_cfg = QPushButton(tr("recep.guardar_2", default="GUARDAR"))
        btn_guardar_cfg.setStyleSheet(_SAVE_BTN_SS)
        btn_guardar_cfg.setFixedHeight(46)
        btn_guardar_cfg.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_guardar_cfg.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_guardar_cfg.clicked.connect(self._guardar_config)
        p0_hdr.addWidget(btn_guardar_cfg)
        p0_hdr.addStretch()
        p0_hdr.addWidget(self._act_btn_loading("⟳  ACTUALIZAR", self._cargar_config))
        p0_ly.addLayout(p0_hdr)

        cols_cfg = ["EAN", "ARTÍCULO", "STOCK TIENDA", "STOCK CENTRAL", "UMBRAL MÍN", "STOCK OBJETIVO"]
        self._cont_cfg, self._tbl_cfg = _crear_tabla_reab(self, cols_cfg)
        hh = self._tbl_cfg.horizontalHeader()
        hh.setStretchLastSection(False)
        for i in range(len(cols_cfg)):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        self._tbl_cfg.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tbl_cfg.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl_cfg.verticalHeader().setVisible(False)
        p0_ly.addWidget(self._cont_cfg)
        self._stack.addWidget(page0)

        # Page 1: PROPUESTAS ACTIVAS
        page1 = QWidget()
        page1.setStyleSheet(f"background: {_REAB_FONDO};")
        p1_ly = QVBoxLayout(page1)
        p1_ly.setContentsMargins(0, 8, 0, 0)
        p1_ly.setSpacing(8)

        p1_hdr = QHBoxLayout()
        p1_hdr.addStretch()
        p1_hdr.addWidget(self._act_btn_loading("⟳  ACTUALIZAR", self._verificar_y_crear_propuestas))
        p1_ly.addLayout(p1_hdr)

        cols_prop = ["EAN", "ARTÍCULO", "CANTIDAD", "ESTADO", "FECHA"]
        self._cont_prop, self._tbl_prop = _crear_tabla_reab(self, cols_prop)
        ph = self._tbl_prop.horizontalHeader()
        ph.setStretchLastSection(False)
        ph.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        ph.resizeSection(0, 160)
        ph.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        ph.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        ph.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        ph.resizeSection(3, 200)
        ph.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._tbl_prop.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tbl_prop.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl_prop.verticalHeader().setVisible(False)
        p1_ly.addWidget(self._cont_prop)
        self._stack.addWidget(page1)

        # Page 2: HISTORIAL COMPLETO
        page2 = QWidget()
        page2.setStyleSheet(f"background: {_REAB_FONDO};")
        p2_ly = QVBoxLayout(page2)
        p2_ly.setContentsMargins(0, 8, 0, 0)
        p2_ly.setSpacing(8)

        p2_hdr = QHBoxLayout()
        p2_hdr.addStretch()
        p2_hdr.addWidget(self._act_btn_loading("⟳  ACTUALIZAR", self._cargar_historial))
        p2_ly.addLayout(p2_hdr)

        cols_hist = ["ID", "ARTÍCULO", "CANTIDAD", "ESTADO", "FECHA"]
        self._cont_hist, self._tbl_hist = _crear_tabla_reab(self, cols_hist)
        hh_h = self._tbl_hist.horizontalHeader()
        hh_h.setStretchLastSection(False)
        hh_h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh_h.resizeSection(0, 240)
        hh_h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh_h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh_h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hh_h.resizeSection(3, 160)
        hh_h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._tbl_hist.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tbl_hist.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl_hist.verticalHeader().setVisible(False)
        p2_ly.addWidget(self._cont_hist)
        self._stack.addWidget(page2)

        # Page 3: RESPONSABLE LOGÍSTICA
        page3 = QWidget()
        page3.setStyleSheet(f"background: {_REAB_FONDO};")
        p3_ly = QVBoxLayout(page3)
        p3_ly.setContentsMargins(32, 20, 32, 20)
        p3_ly.setSpacing(0)

        lbl_sec1 = QLabel(tr("recep.correo_electronico_del_respo", default="Correo electrónico del responsable de logística"))
        lbl_sec1.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_sec1.setStyleSheet(f"color: {_REAB_CIAN}; margin-bottom: 4px;")
        p3_ly.addWidget(lbl_sec1)

        lbl_sec1_desc = QLabel(
            tr("recep.se_enviaran_automaticamente_", default="Se enviarán automáticamente los informes de artículos pendientes de reabastecimiento "
            "a esta dirección según la programación definida a continuación.")
        )
        lbl_sec1_desc.setWordWrap(True)
        lbl_sec1_desc.setStyleSheet("color: #8B949E; font-size: 11px; margin-bottom: 10px;")
        p3_ly.addWidget(lbl_sec1_desc)

        self._inp_email = QLineEdit()
        self._inp_email.setPlaceholderText(tr("recep.logistica_miempresa_com", default="logistica@miempresa.com"))
        self._inp_email.setFixedHeight(46)
        self._inp_email.setStyleSheet(_EMAIL_INPUT_SS)
        p3_ly.addWidget(self._inp_email)

        p3_ly.addSpacing(24)

        lbl_smtp = QLabel(tr("recep.correo_remitente_cuenta_que_", default="Correo remitente (cuenta que envía los informes)"))
        lbl_smtp.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_smtp.setStyleSheet(f"color: {_REAB_CIAN}; margin-bottom: 4px;")
        p3_ly.addWidget(lbl_smtp)

        smtp_row = QHBoxLayout()
        smtp_row.setSpacing(12)
        smtp_row.setContentsMargins(0, 0, 0, 0)

        self._inp_smtp_user = QLineEdit()
        self._inp_smtp_user.setPlaceholderText(tr("recep.remitente_gmail_com", default="remitente@gmail.com"))
        self._inp_smtp_user.setFixedHeight(46)
        self._inp_smtp_user.setStyleSheet(_EMAIL_INPUT_SS)
        smtp_row.addWidget(self._inp_smtp_user, 1, Qt.AlignmentFlag.AlignTop)

        pass_col = QVBoxLayout()
        pass_col.setSpacing(3)
        pass_col.setContentsMargins(0, 0, 0, 0)

        self._inp_smtp_pass = QLineEdit()
        self._inp_smtp_pass.setPlaceholderText(tr("recep.contrasena_de_aplicacion_16_", default="Contraseña de aplicación (16 caracteres)"))
        self._inp_smtp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._inp_smtp_pass.setFixedHeight(46)
        self._inp_smtp_pass.setStyleSheet(_EMAIL_INPUT_SS)
        pass_col.addWidget(self._inp_smtp_pass)

        self._lbl_pass_saved = QLabel("")
        self._lbl_pass_saved.setFixedHeight(16)
        self._lbl_pass_saved.setStyleSheet(
            "color: #1ED760; font-size: 10px; background: transparent;"
        )
        pass_col.addWidget(self._lbl_pass_saved)

        smtp_row.addLayout(pass_col, 1)
        p3_ly.addLayout(smtp_row)

        p3_ly.addSpacing(8)

        lbl_sec2 = QLabel(tr("recep.dias_de_envio_puede_seleccio", default="Días de envío (puede seleccionar varios)"))
        lbl_sec2.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_sec2.setStyleSheet(f"color: {_REAB_CIAN}; margin-bottom: 10px;")
        p3_ly.addWidget(lbl_sec2)

        dias_row = QHBoxLayout()
        dias_row.setSpacing(10)
        dias_row.setContentsMargins(0, 0, 0, 0)
        dias_nombres = ["LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB", "DOM"]
        self._dia_btns = []
        for nombre in dias_nombres:
            btn = QPushButton(nombre)
            btn.setCheckable(True)
            btn.setFixedSize(66, 46)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setStyleSheet(_DIA_BTN_SS)
            dias_row.addWidget(btn)
            self._dia_btns.append(btn)
        dias_row.addStretch()
        p3_ly.addLayout(dias_row)

        p3_ly.addSpacing(24)

        lbl_sec3 = QLabel(tr("recep.hora_de_envio", default="Hora de envío"))
        lbl_sec3.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_sec3.setStyleSheet(f"color: {_REAB_CIAN}; margin-bottom: 10px;")
        p3_ly.addWidget(lbl_sec3)

        hora_row = QHBoxLayout()
        hora_row.setSpacing(8)
        hora_row.setContentsMargins(0, 0, 0, 0)

        self._cmb_hora = _ReabComboBoxReab()
        for h in range(24):
            self._cmb_hora.addItem(f"{h:02d}h")
        self._cmb_hora.setFixedWidth(100)
        self._cmb_hora.setFixedHeight(46)
        self._cmb_hora.setStyleSheet(_CMB_HORA_SS)
        hora_row.addWidget(self._cmb_hora)

        lbl_sep_hora = QLabel(":")
        lbl_sep_hora.setStyleSheet(f"color: {_REAB_CIAN}; font-size: 22px; font-weight: bold;")
        lbl_sep_hora.setFixedWidth(18)
        hora_row.addWidget(lbl_sep_hora)

        self._cmb_min = _ReabComboBoxReab()
        for m in range(0, 60, 5):
            self._cmb_min.addItem(f"{m:02d}min")
        self._cmb_min.setFixedWidth(110)
        self._cmb_min.setFixedHeight(46)
        self._cmb_min.setStyleSheet(_CMB_HORA_SS)
        hora_row.addWidget(self._cmb_min)
        hora_row.addStretch()
        p3_ly.addLayout(hora_row)

        p3_ly.addStretch()

        self._lbl_save_ok = QLabel("")
        self._lbl_save_ok.setStyleSheet(
            "color: #1ED760; font-size: 13px; font-weight: bold; background: transparent;"
        )
        self._lbl_save_ok.setVisible(False)

        save_row = QHBoxLayout()
        save_row.addStretch()
        save_row.addWidget(self._lbl_save_ok)
        save_row.addSpacing(20)
        btn_test = QPushButton(tr("recep.probar_envio", default="PROBAR ENVÍO"))
        btn_test.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {_REAB_CIAN}; border: 2px solid {_REAB_CIAN};"
            f" border-radius: 10px; font-size: 13px; font-weight: bold; padding: 0 18px; outline: none; }}"
            f"QPushButton:hover {{ background: {_REAB_CIAN}; color: #0E1117; }}"
        )
        btn_test.setFixedHeight(46)
        btn_test.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_test.clicked.connect(self._probar_envio)
        save_row.addWidget(btn_test)
        save_row.addSpacing(12)
        btn_save = QPushButton(tr("recep.guardar_3", default="GUARDAR"))
        btn_save.setStyleSheet(_SAVE_BTN_SS)
        btn_save.setFixedHeight(46)
        btn_save.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_save.clicked.connect(self._guardar_schedule_ui)
        save_row.addWidget(btn_save)
        p3_ly.addLayout(save_row)

        self._stack.addWidget(page3)

        root.addWidget(self._stack)
        self._ir_tab(0)
        self.cargar()

    def cargar(self):
        self._cargar_config()
        self._cargar_propuestas()
        self._cargar_historial()
        self._cargar_schedule_ui()

    def _cargar_config(self):
        try:
            with obtener_conexion() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT a.codigo, a.nombre,
                               COALESCE(a.Stock_tienda, 0) + COALESCE(a.Stock_total, 0),
                               COALESCE(a.Stock_central, 0),
                               rc.umbral_min, rc.stock_objetivo
                        FROM articulos a
                        LEFT JOIN reab_config rc ON rc.codigo = a.codigo
                        ORDER BY a.nombre ASC
                    """)
                    rows = cur.fetchall()
        except Exception:
            rows = []

        self._tbl_cfg.setRowCount(len(rows))
        for r, row in enumerate(rows):
            codigo = row[0]
            nombre = row[1]
            st_tienda = row[2]
            st_central = row[3]
            tiene_cfg = row[4] is not None
            umbral = int(row[4]) if tiene_cfg else 5
            objetivo = int(row[5]) if tiene_cfg else 20

            self._tbl_cfg.setRowHeight(r, 48)

            ean_item = QTableWidgetItem(codigo)
            ean_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            ean_item.setFlags(ean_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if not tiene_cfg:
                ean_item.setForeground(QColor("#8B949E"))
            self._tbl_cfg.setItem(r, 0, ean_item)

            art_item = QTableWidgetItem(nombre)
            art_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            art_item.setFlags(art_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if not tiene_cfg:
                art_item.setForeground(QColor("#8B949E"))
            self._tbl_cfg.setItem(r, 1, art_item)

            for ci, val in enumerate([st_tienda, st_central], start=2):
                it = QTableWidgetItem(str(val))
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._tbl_cfg.setItem(r, ci, it)

            inp_u = QLineEdit(str(umbral))
            inp_u.setStyleSheet(_CFG_INPUT_SS)
            inp_u.setAlignment(Qt.AlignmentFlag.AlignCenter)
            inp_u.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            w_u = QWidget()
            w_u.setStyleSheet("background: transparent;")
            ly_u = QHBoxLayout(w_u)
            ly_u.setContentsMargins(4, 2, 4, 2)
            ly_u.addWidget(inp_u)
            self._tbl_cfg.setCellWidget(r, 4, w_u)

            inp_o = QLineEdit(str(objetivo))
            inp_o.setStyleSheet(_CFG_INPUT_SS)
            inp_o.setAlignment(Qt.AlignmentFlag.AlignCenter)
            inp_o.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            w_o = QWidget()
            w_o.setStyleSheet("background: transparent;")
            ly_o = QHBoxLayout(w_o)
            ly_o.setContentsMargins(4, 2, 4, 2)
            ly_o.addWidget(inp_o)
            self._tbl_cfg.setCellWidget(r, 5, w_o)

            inp_u.editingFinished.connect(
                lambda c=codigo, iu=inp_u, io=inp_o: self._auto_guardar_cfg(c, iu, io)
            )
            inp_o.editingFinished.connect(
                lambda c=codigo, iu=inp_u, io=inp_o: self._auto_guardar_cfg(c, iu, io)
            )

    def _cargar_propuestas(self):
        props = _reab_listar_propuestas(estados=("pendiente", "aprobado", "enviado"))
        self._tbl_prop.setRowCount(len(props))
        for r, p in enumerate(props):
            self._tbl_prop.setRowHeight(r, 44)
            estado = p["estado"]
            bg, fg = _ESTADO_COLORES.get(estado, ("#8B949E", "#FFF"))

            for c, v in enumerate([p["codigo"], p["nombre"], str(p["cantidad"])]):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._tbl_prop.setItem(r, c, item)

            w_estado = QWidget()
            w_estado.setStyleSheet("background: transparent;")
            ly_estado = QHBoxLayout(w_estado)
            ly_estado.setContentsMargins(6, 4, 6, 4)
            ly_estado.setSpacing(6)

            lbl_e = QLabel(estado.upper())
            lbl_e.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_e.setStyleSheet(
                f"background:{bg}; color:{fg}; border-radius:6px; "
                f"font-size:13px; font-weight:bold; padding:2px 8px;"
            )
            ly_estado.addWidget(lbl_e, 1)

            if estado == "pendiente":
                btn_x = QPushButton("✕")
                btn_x.setFixedWidth(36)
                btn_x.setSizePolicy(
                    QSizePolicy.Policy.Fixed,
                    QSizePolicy.Policy.Expanding,
                )
                btn_x.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                btn_x.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_x.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
                btn_x.setStyleSheet(
                    "QPushButton {"
                    "  background: #F85149;"
                    "  color: #FFFFFF;"
                    "  border: none;"
                    "  border-radius: 6px;"
                    "  font-size: 20px;"
                    "  font-weight: 900;"
                    "  padding: 0px 0px 4px 0px;"
                    "  margin: 0px;"
                    "}"
                    "QPushButton:hover {"
                    "  background: #FFFFFF;"
                    "  color: #F85149;"
                    "}"
                    "QPushButton:pressed {"
                    "  background: #F85149;"
                    "  color: #FFFFFF;"
                    "}"
                )
                btn_x.clicked.connect(
                    lambda checked, pid=p["id"]: self._accion_propuesta(pid, "cancelado")
                )
                ly_estado.addWidget(btn_x, 0)

            self._tbl_prop.setCellWidget(r, 3, w_estado)

            fecha_item = QTableWidgetItem(
                str(p["fecha_creacion"])[:16] if p["fecha_creacion"] else "—"
            )
            fecha_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            fecha_item.setFlags(fecha_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._tbl_prop.setItem(r, 4, fecha_item)

    def _cargar_historial(self):
        props = _reab_listar_propuestas()
        self._tbl_hist.setRowCount(len(props))
        for r, p in enumerate(props):
            self._tbl_hist.setRowHeight(r, 44)
            estado = p["estado"]
            bg, fg = _ESTADO_COLORES.get(estado, ("#8B949E", "#FFFFFF"))

            for c, v in enumerate([str(p["id"]), p["nombre"], str(p["cantidad"])]):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._tbl_hist.setItem(r, c, item)

            w_e = QWidget()
            w_e.setStyleSheet("background: transparent;")
            ly_e = QHBoxLayout(w_e)
            ly_e.setContentsMargins(8, 4, 8, 4)
            lbl_e = QLabel(estado.upper())
            lbl_e.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_e.setStyleSheet(
                f"background:{bg}; color:{fg}; border-radius:8px; "
                f"font-size:13px; font-weight:bold; padding:2px 10px;"
            )
            ly_e.addWidget(lbl_e)
            self._tbl_hist.setCellWidget(r, 3, w_e)

            fecha_item = QTableWidgetItem(
                str(p["fecha_creacion"])[:16] if p["fecha_creacion"] else "—"
            )
            fecha_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            fecha_item.setFlags(fecha_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._tbl_hist.setItem(r, 4, fecha_item)

    def _auto_guardar_cfg(self, codigo: str, inp_umbral: QLineEdit, inp_obj: QLineEdit):
        try:
            umbral = max(0, int(inp_umbral.text().strip() or "0"))
            objetivo = max(0, int(inp_obj.text().strip() or "0"))
        except ValueError:
            return
        _reab_upsert_config(codigo, umbral, objetivo, automatico=True)
        self._on_stock_cambio(codigo)

    def _guardar_config(self):
        codigos_guardados = []
        for r in range(self._tbl_cfg.rowCount()):
            ean_item = self._tbl_cfg.item(r, 0)
            if not ean_item:
                continue
            codigo = ean_item.text().strip()
            if not codigo:
                continue
            w_u = self._tbl_cfg.cellWidget(r, 4)
            w_o = self._tbl_cfg.cellWidget(r, 5)
            if w_u is None or w_o is None:
                continue
            inp_u = w_u.layout().itemAt(0).widget()
            inp_o = w_o.layout().itemAt(0).widget()
            try:
                umbral = max(0, int(inp_u.text().strip() or "0"))
                objetivo = max(0, int(inp_o.text().strip() or "0"))
            except ValueError:
                continue
            _reab_upsert_config(codigo, umbral, objetivo)
            codigos_guardados.append(codigo)
            inp_u.deselect()
            inp_o.deselect()
        self._tbl_cfg.clearSelection()
        self._tbl_cfg.setFocus()
        for codigo in codigos_guardados:
            self._crear_propuesta_si_bajo_umbral(codigo)
        self._cargar_propuestas()

    def _verificar_y_crear_propuestas(self):
        try:
            with obtener_conexion() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT rc.codigo, a.nombre,
                               COALESCE(a.Stock_tienda, 0) + COALESCE(a.Stock_total, 0),
                               rc.stock_objetivo, rc.origen,
                               COALESCE(a.Stock_central, 0)
                        FROM reab_config rc
                        JOIN articulos a ON a.codigo = rc.codigo
                        WHERE (COALESCE(a.Stock_tienda, 0) + COALESCE(a.Stock_total, 0)) < rc.umbral_min
                          AND NOT EXISTS (
                              SELECT 1 FROM reab_propuestas rp
                              WHERE rp.codigo = rc.codigo
                                AND rp.estado IN ('pendiente', 'aprobado', 'enviado')
                          )
                    """)
                    candidatos = cur.fetchall()
        except Exception:
            candidatos = []

        for codigo, nombre, stock_actual, stock_objetivo, origen, stock_central in candidatos:
            cantidad = max(1, (stock_objetivo or 0) - (stock_actual or 0))
            origen_final = origen or ("ALMACÉN CENTRAL" if (stock_central or 0) > 0 else "PROVEEDOR")
            _reab_crear_propuesta(
                codigo, nombre, cantidad, origen_final,
                stock_actual or 0, stock_objetivo or 0
            )
        self._cargar_propuestas()

    def _crear_propuesta_si_bajo_umbral(self, codigo: str) -> bool:
        """Crea una propuesta si el stock está bajo el umbral y no existe ya una activa.
        Devuelve True si se creó una propuesta."""
        try:
            with obtener_conexion() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT rc.codigo, a.nombre,
                               COALESCE(a.Stock_tienda, 0) + COALESCE(a.Stock_total, 0),
                               rc.stock_objetivo, rc.origen,
                               COALESCE(a.Stock_central, 0)
                        FROM reab_config rc
                        JOIN articulos a ON a.codigo = rc.codigo
                        WHERE rc.codigo = %s
                          AND (COALESCE(a.Stock_tienda, 0) + COALESCE(a.Stock_total, 0)) < rc.umbral_min
                          AND NOT EXISTS (
                              SELECT 1 FROM reab_propuestas rp
                              WHERE rp.codigo = rc.codigo
                                AND rp.estado IN ('pendiente', 'aprobado', 'enviado')
                          )
                    """, (codigo,))
                    row = cur.fetchone()
        except Exception:
            row = None

        if row:
            cod, nombre, stock_actual, stock_objetivo, origen, stock_central = row
            cantidad = max(1, (stock_objetivo or 0) - (stock_actual or 0))
            origen_final = origen or ("ALMACÉN CENTRAL" if (stock_central or 0) > 0 else "PROVEEDOR")
            _reab_crear_propuesta(
                cod, nombre, cantidad, origen_final,
                stock_actual or 0, stock_objetivo or 0
            )
            return True
        return False

    def _actualizar_stock_en_cfg(self, codigo: str):
        """Actualiza solo las celdas de stock del artículo en ARTÍCULOS MONITORIZADOS."""
        try:
            with obtener_conexion() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT COALESCE(Stock_tienda, 0) + COALESCE(Stock_total, 0),
                               COALESCE(Stock_central, 0)
                        FROM articulos WHERE codigo = %s
                    """, (codigo,))
                    row = cur.fetchone()
        except Exception:
            row = None

        if not row:
            return

        st_tienda, st_central = int(row[0] or 0), int(row[1] or 0)
        for r in range(self._tbl_cfg.rowCount()):
            ean_item = self._tbl_cfg.item(r, 0)
            if ean_item and ean_item.text() == codigo:
                for ci, val in enumerate([st_tienda, st_central], start=2):
                    it = self._tbl_cfg.item(r, ci)
                    if it:
                        it.setText(str(val))
                break

    def _on_stock_cambio(self, codigo: str):
        self._actualizar_stock_en_cfg(codigo)
        if self._crear_propuesta_si_bajo_umbral(codigo):
            self._cargar_propuestas()

    def _eliminar_config(self, codigo: str):
        _reab_eliminar_config(codigo)
        self._cargar_config()

    def _accion_propuesta(self, pid: int, estado: str):
        _reab_cambiar_estado_propuesta(pid, estado)
        self._cargar_propuestas()
        self._cargar_historial()

    def _generar_pdf_global(self):
        props = _reab_listar_propuestas(estados=("pendiente",))
        if not props:
            QMessageBox.information(
                self.window(), "Sin propuestas",
                "No hay propuestas en estado PENDIENTE para generar el informe.",
            )
            return

        def _do_generate():
            ruta = _reab_generar_pdf(props)
            self._on_pdf_done(ruta)

        QTimer.singleShot(0, _do_generate)

    def _on_pdf_done(self, ruta: str):
        if ruta.startswith("ERROR"):
            QMessageBox.critical(self.window(), "Error PDF", ruta)
        else:
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(ruta))

    def _on_propuesta_auto(self, info: dict):
        self._cargar_propuestas()
        self._cargar_historial()

    def _cargar_schedule_ui(self):
        cfg = _reab_cargar_schedule()
        self._inp_email.setText(cfg.get("email", ""))
        self._inp_smtp_user.setText(cfg.get("smtp_user", ""))
        self._inp_smtp_pass.clear()
        has_pass = bool(cfg.get("smtp_pass", ""))
        self._lbl_pass_saved.setText(
            "✓  Contraseña guardada (déjalo vacío para conservarla)" if has_pass else ""
        )
        dias_activos = set(cfg.get("dias", "").split(",")) if cfg.get("dias") else set()
        for i, btn in enumerate(self._dia_btns):
            btn.setChecked(str(i) in dias_activos)
        hora = cfg.get("hora", 8)
        minuto = cfg.get("minuto", 0)
        self._cmb_hora.setCurrentIndex(max(0, min(hora, 23)))
        closest = min(range(0, 60, 5), key=lambda m: abs(m - minuto))
        self._cmb_min.setCurrentIndex(closest // 5)

    def _guardar_schedule_ui(self):
        email = self._inp_email.text().strip()
        smtp_user = self._inp_smtp_user.text().strip()
        smtp_pass = self._inp_smtp_pass.text().strip()
        if not smtp_pass:
            smtp_pass = _reab_cargar_schedule().get("smtp_pass", "")
        dias_str = ",".join(str(i) for i, btn in enumerate(self._dia_btns) if btn.isChecked())
        hora = int(self._cmb_hora.currentText().replace("h", "").strip())
        minuto = int(self._cmb_min.currentText().replace("min", "").strip())
        if _reab_guardar_schedule(email, dias_str, hora, minuto, smtp_user, smtp_pass):
            self._inp_smtp_pass.clear()
            self._lbl_pass_saved.setText(
                "✓  Contraseña guardada (déjalo vacío para conservarla)" if smtp_pass else ""
            )
            self._lbl_save_ok.setText(tr("recep.configuracion_guardada_corre", default="✓ Configuración guardada correctamente"))
            self._lbl_save_ok.setStyleSheet(
                "color: #1ED760; font-size: 13px; font-weight: bold; background: transparent;"
            )
            self._lbl_save_ok.setVisible(True)
            QTimer.singleShot(3000, self._hide_save_ok)
        else:
            self._lbl_save_ok.setText(tr("recep.error_al_guardar_la_configur", default="✕ Error al guardar la configuración"))
            self._lbl_save_ok.setStyleSheet(
                "color: #FF4B4B; font-size: 13px; font-weight: bold; background: transparent;"
            )
            self._lbl_save_ok.setVisible(True)
            QTimer.singleShot(4000, self._hide_save_ok)

    def _probar_envio(self):
        cfg = _reab_cargar_schedule()
        email = cfg.get("email", "")
        smtp_user = cfg.get("smtp_user", "")
        smtp_pass = cfg.get("smtp_pass", "")
        if not email or not smtp_user or not smtp_pass:
            self._lbl_save_ok.setText(tr("recep.completa_y_guarda_email_remi", default="✕ Completa y guarda email, remitente y contraseña antes de probar"))
            self._lbl_save_ok.setStyleSheet(
                "color: #FF4B4B; font-size: 12px; font-weight: bold; background: transparent;"
            )
            self._lbl_save_ok.setVisible(True)
            QTimer.singleShot(5000, self._hide_save_ok)
            return
        props = _reab_listar_propuestas(estados=("pendiente",))
        if not props:
            self._lbl_save_ok.setText(tr("recep.no_hay_propuestas_pendientes", default="⚠ No hay propuestas pendientes — se envía un artículo de ejemplo para verificar SMTP"))
            self._lbl_save_ok.setStyleSheet(
                "color: #E3B341; font-size: 11px; font-weight: bold; background: transparent;"
            )
            self._lbl_save_ok.setVisible(True)
            props = [{"id": 0, "codigo": "EJEMPLO", "nombre": "Sin propuestas pendientes — prueba SMTP",
                      "cantidad": 0}]
        else:
            self._lbl_save_ok.setText(f"⏳ Enviando {len(props)} propuesta(s) pendiente(s)…")
            self._lbl_save_ok.setStyleSheet(
                "color: #E3B341; font-size: 13px; font-weight: bold; background: transparent;"
            )
            self._lbl_save_ok.setVisible(True)
        import threading
        def _bg():
            ok = _reab_enviar_email_pdf_impl(email, "", smtp_user, smtp_pass, props,
                                             solo_prueba=True)
            if ok:
                self._sig_prueba_ok.emit()
            else:
                self._sig_prueba_err.emit()
        threading.Thread(target=_bg, daemon=True).start()

    def _on_prueba_ok(self):
        self._lbl_save_ok.setText(tr("recep.correo_de_prueba_enviado_rev", default="✓ Correo de prueba enviado — revisa tu bandeja de entrada"))
        self._lbl_save_ok.setStyleSheet(
            "color: #1ED760; font-size: 13px; font-weight: bold; background: transparent;"
        )
        QTimer.singleShot(6000, self._hide_save_ok)

    def _on_prueba_err(self):
        self._lbl_save_ok.setText(
            tr("recep.error_al_enviar_gmail_usa_co", default="✕ Error al enviar. Gmail: usa Contraseña de Aplicación (no tu clave normal)"))
        self._lbl_save_ok.setStyleSheet(
            "color: #FF4B4B; font-size: 12px; font-weight: bold; background: transparent;"
        )
        QTimer.singleShot(8000, self._hide_save_ok)

    def _recargar_desde_webhook(self):
        self._cargar_propuestas()
        self._cargar_historial()

    def _hide_save_ok(self):
        try:
            self._lbl_save_ok.setVisible(False)
        except RuntimeError:
            pass

    def _check_schedule(self):
        from datetime import date as _date
        cfg = _reab_cargar_schedule()
        if not cfg.get("email") or not cfg.get("dias"):
            return
        smtp_user = cfg.get("smtp_user", "")
        smtp_pass = cfg.get("smtp_pass", "")
        if not smtp_user or not smtp_pass:
            return
        now = datetime.now()
        dias = [int(d) for d in cfg["dias"].split(",") if d.strip().isdigit()]
        if now.weekday() not in dias:
            return
        target_mins = cfg["hora"] * 60 + cfg["minuto"]
        current_mins = now.hour * 60 + now.minute
        if abs(current_mins - target_mins) > 1:
            return
        today = _date.today()
        if cfg.get("ultima_envio") == today:
            return
        props = _reab_listar_propuestas(estados=("pendiente",))
        if not props:
            return
        import threading
        def _send_bg():
            ruta = _reab_generar_pdf(props)
            if not ruta.startswith("ERROR"):
                if _reab_enviar_email_pdf_impl(cfg["email"], ruta, smtp_user, smtp_pass, props):
                    _reab_marcar_envio_hoy()
        threading.Thread(target=_send_bg, daemon=True).start()


# ============================================================
# CONSTANTES ENTERPRISE — ESTADOS LOGÍSTICOS
# ============================================================

_ESTADO_COLORES_LOG = {
    "PENDIENTE":          "#F59E0B",
    "EN PREPARACIÓN":     "#3B82F6",
    "EN PREPARACION":     "#3B82F6",
    "PREPARADO":          "#00FFC6",
    "EXPEDIDO":           "#8B5CF6",
    "EN TRÁNSITO":        "#60A5FA",
    "EN TRANSITO":        "#60A5FA",
    "RECEPCIÓN PARCIAL":  "#F97316",
    "RECEPCION PARCIAL":  "#F97316",
    "RECIBIDO":           "#22C55E",
    "INCIDENCIA":         "#EF4444",
    "CANCELADO":          "#6B7280",
    "ABIERTA":            "#EF4444",
    "CERRADA":            "#22C55E",
}


def _color_estado_log(estado: str) -> str:
    return _ESTADO_COLORES_LOG.get((estado or "").upper().strip(), "#6B7280")


def _tabla_item_centrado(texto):
    it = QTableWidgetItem(str(texto) if texto is not None else "—")
    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return it


def _query_docs_por_estado(estados: tuple) -> list:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                ph = ",".join(["%s"] * len(estados))
                cur.execute(
                    f"SELECT id_documento, tipo_documento, origen, destino, "
                    f"estado, usuario_emisor, fecha_creacion, observaciones "
                    f"FROM documentos_logisticos WHERE estado IN ({ph}) "
                    f"ORDER BY fecha_creacion DESC",
                    estados,
                )
                return [
                    {"id": r[0], "tipo": r[1], "origen": r[2], "destino": r[3],
                     "estado": r[4], "emisor": r[5], "fecha": r[6], "obs": r[7]}
                    for r in cur.fetchall()
                ]
    except Exception as e:
        logger.error(f"_query_docs_por_estado: {e}")
        return []


def _query_incidencias(estado_filtro=None) -> list:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                if estado_filtro and estado_filtro != "TODAS":
                    cur.execute(
                        "SELECT id, id_documento, id_pale, codigo_articulo, tipo, "
                        "descripcion, cantidad_afectada, usuario, estado, "
                        "fecha_creacion, fecha_cierre "
                        "FROM incidencias_logisticas WHERE estado=%s "
                        "ORDER BY fecha_creacion DESC",
                        (estado_filtro,),
                    )
                else:
                    cur.execute(
                        "SELECT id, id_documento, id_pale, codigo_articulo, tipo, "
                        "descripcion, cantidad_afectada, usuario, estado, "
                        "fecha_creacion, fecha_cierre "
                        "FROM incidencias_logisticas ORDER BY fecha_creacion DESC"
                    )
                return [
                    {"id": r[0], "id_documento": r[1], "id_pale": r[2],
                     "codigo": r[3], "tipo": r[4], "descripcion": r[5],
                     "cantidad": r[6], "usuario": r[7], "estado": r[8],
                     "fecha_creacion": r[9], "fecha_cierre": r[10]}
                    for r in cur.fetchall()
                ]
    except Exception as e:
        logger.error(f"_query_incidencias: {e}")
        return []


def _registrar_incidencia_db(id_documento, tipo, descripcion, usuario,
                              id_pale=None, codigo=None, cantidad=0):
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO incidencias_logisticas "
                    "(id_documento, id_pale, codigo_articulo, tipo, "
                    "descripcion, cantidad_afectada, usuario, estado) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, 'ABIERTA')",
                    (id_documento, id_pale, codigo, tipo,
                     descripcion, cantidad, usuario),
                )
                iid = cur.lastrowid
            conn.commit()
            return iid
    except Exception as e:
        logger.error(f"_registrar_incidencia_db: {e}")
        return None


def _cerrar_incidencia_db(inc_id: int) -> bool:
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE incidencias_logisticas "
                    "SET estado='CERRADA', fecha_cierre=NOW() WHERE id=%s",
                    (inc_id,),
                )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"_cerrar_incidencia_db: {e}")
        return False


# ============================================================
# PÁGINA PREPARACIÓN
# ============================================================

class PreparacionPage(QWidget):
    """Documentos logísticos en estado EN PREPARACIÓN / PREPARADO."""

    _ESTADOS = ("EN PREPARACIÓN", "EN PREPARACION", "PREPARADO")

    def __init__(self, usuario=None, codigo_local="ALMC", parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.codigo_local = codigo_local
        self.setObjectName("panel_contenido")
        self._datos = []
        self._setup_ui()
        self.cargar_datos()

    def _setup_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(30, 30, 30, 30)
        ly.setSpacing(20)

        hdr = QHBoxLayout()
        vc = QVBoxLayout()
        t = QLabel(tr("recep.preparacion_de_envios", default="Preparación de Envíos"))
        t.setObjectName("titulo_cian")
        s = QLabel(tr("recep.documentos_en_preparacion_ac", default="Documentos en preparación activa y listos para expedir"))
        s.setObjectName("subtitulo_muted")
        vc.addWidget(t)
        vc.addWidget(s)
        hdr.addLayout(vc)
        hdr.addStretch()
        self.btn_actualizar = QPushButton(tr("recep.actualizar_3", default="🔄 ACTUALIZAR"))
        self.btn_actualizar.setObjectName("btn_primario")
        self.btn_actualizar.setFixedSize(180, 45)
        self.btn_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_actualizar.clicked.connect(self.ejecutar_actualizacion)
        hdr.addWidget(self.btn_actualizar)
        ly.addLayout(hdr)

        self.input_busqueda = QLineEdit()
        self.input_busqueda.setObjectName("input_buscador")
        self.input_busqueda.setPlaceholderText(
            tr("recep.filtrar_por_id_origen_destin", default="🔍 Filtrar por ID, Origen, Destino o Estado...")
        )
        self.input_busqueda.setFixedHeight(50)
        self.input_busqueda.textChanged.connect(self._filtrar)
        ly.addWidget(self.input_busqueda)

        if construir_tabla_estilizada:
            self._cont, self.tabla = construir_tabla_estilizada(self)
        else:
            self._cont = QFrame(self)
            self.tabla = QTableWidget(self._cont)
            QVBoxLayout(self._cont).addWidget(self.tabla)

        cols = ["ID", "TIPO", "ORIGEN", "DESTINO", "ESTADO", "EMISOR", "FECHA CREACIÓN"]
        self.tabla.setColumnCount(len(cols))
        self.tabla.setHorizontalHeaderLabels(cols)
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        ly.addWidget(self._cont)

    def cargar_datos(self):
        self._datos = _query_docs_por_estado(self._ESTADOS)
        self._filtrar()

    def ejecutar_actualizacion(self):
        self.btn_actualizar.setEnabled(False)
        self.btn_actualizar.setText(tr("recep.actualizando", default="⌛ ACTUALIZANDO..."))
        self.btn_actualizar.repaint()
        QApplication.processEvents()
        try:
            self.cargar_datos()
        finally:
            self.btn_actualizar.setEnabled(True)
            self.btn_actualizar.setText(tr("recep.actualizar_4", default="🔄 ACTUALIZAR"))

    def _filtrar(self):
        txt = (
            self.input_busqueda.text() if hasattr(self, "input_busqueda") else ""
        ).strip().lower()
        filas = [d for d in self._datos if not txt or any(
            txt in str(v).lower() for v in d.values()
        )]
        self.tabla.setRowCount(len(filas))
        for i, d in enumerate(filas):
            self.tabla.setItem(i, 0, _tabla_item_centrado(d["id"]))
            self.tabla.setItem(i, 1, _tabla_item_centrado(d["tipo"]))
            self.tabla.setItem(i, 2, _tabla_item_centrado(d["origen"]))
            self.tabla.setItem(i, 3, _tabla_item_centrado(d["destino"]))
            ei = _tabla_item_centrado(d["estado"])
            ei.setForeground(QColor(_color_estado_log(d["estado"])))
            ei.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            self.tabla.setItem(i, 4, ei)
            self.tabla.setItem(i, 5, _tabla_item_centrado(d["emisor"]))
            fc = d["fecha"]
            self.tabla.setItem(i, 6, _tabla_item_centrado(str(fc)[:16] if fc else "—"))
        self.tabla.resizeRowsToContents()


# ============================================================
# PÁGINA EXPEDICIONES
# ============================================================

class ExpedicionesPage(QWidget):
    """Documentos logísticos en estado EXPEDIDO / EN TRÁNSITO / RECEPCIÓN PARCIAL."""

    _ESTADOS = (
        "EXPEDIDO", "EN TRÁNSITO", "EN TRANSITO",
        "RECEPCIÓN PARCIAL", "RECEPCION PARCIAL",
    )

    def __init__(self, usuario=None, codigo_local="ALMC", parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.codigo_local = codigo_local
        self.setObjectName("panel_contenido")
        self._datos = []
        self._setup_ui()
        self.cargar_datos()

    def _setup_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(30, 30, 30, 30)
        ly.setSpacing(20)

        hdr = QHBoxLayout()
        vc = QVBoxLayout()
        t = QLabel(tr("recep.expediciones_y_transito", default="Expediciones y Tránsito"))
        t.setObjectName("titulo_cian")
        s = QLabel(tr("recep.seguimiento_de_envios_expedi", default="Seguimiento de envíos expedidos y en tránsito hacia destino"))
        s.setObjectName("subtitulo_muted")
        vc.addWidget(t)
        vc.addWidget(s)
        hdr.addLayout(vc)
        hdr.addStretch()
        self.btn_actualizar = QPushButton(tr("recep.actualizar_5", default="🔄 ACTUALIZAR"))
        self.btn_actualizar.setObjectName("btn_primario")
        self.btn_actualizar.setFixedSize(180, 45)
        self.btn_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_actualizar.clicked.connect(self.ejecutar_actualizacion)
        hdr.addWidget(self.btn_actualizar)
        ly.addLayout(hdr)

        self.input_busqueda = QLineEdit()
        self.input_busqueda.setObjectName("input_buscador")
        self.input_busqueda.setPlaceholderText(
            tr("recep.filtrar_por_id_origen_destin_2", default="🔍 Filtrar por ID, Origen, Destino o Estado...")
        )
        self.input_busqueda.setFixedHeight(50)
        self.input_busqueda.textChanged.connect(self._filtrar)
        ly.addWidget(self.input_busqueda)

        if construir_tabla_estilizada:
            self._cont, self.tabla = construir_tabla_estilizada(self)
        else:
            self._cont = QFrame(self)
            self.tabla = QTableWidget(self._cont)
            QVBoxLayout(self._cont).addWidget(self.tabla)

        cols = ["ID", "TIPO", "ORIGEN", "DESTINO", "ESTADO", "EMISOR", "FECHA CREACIÓN"]
        self.tabla.setColumnCount(len(cols))
        self.tabla.setHorizontalHeaderLabels(cols)
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        ly.addWidget(self._cont)

    def cargar_datos(self):
        self._datos = _query_docs_por_estado(self._ESTADOS)
        self._filtrar()

    def ejecutar_actualizacion(self):
        self.btn_actualizar.setEnabled(False)
        self.btn_actualizar.setText(tr("recep.actualizando_2", default="⌛ ACTUALIZANDO..."))
        self.btn_actualizar.repaint()
        QApplication.processEvents()
        try:
            self.cargar_datos()
        finally:
            self.btn_actualizar.setEnabled(True)
            self.btn_actualizar.setText(tr("recep.actualizar_6", default="🔄 ACTUALIZAR"))

    def _filtrar(self):
        txt = (
            self.input_busqueda.text() if hasattr(self, "input_busqueda") else ""
        ).strip().lower()
        filas = [d for d in self._datos if not txt or any(
            txt in str(v).lower() for v in d.values()
        )]
        self.tabla.setRowCount(len(filas))
        for i, d in enumerate(filas):
            self.tabla.setItem(i, 0, _tabla_item_centrado(d["id"]))
            self.tabla.setItem(i, 1, _tabla_item_centrado(d["tipo"]))
            self.tabla.setItem(i, 2, _tabla_item_centrado(d["origen"]))
            self.tabla.setItem(i, 3, _tabla_item_centrado(d["destino"]))
            ei = _tabla_item_centrado(d["estado"])
            ei.setForeground(QColor(_color_estado_log(d["estado"])))
            ei.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            self.tabla.setItem(i, 4, ei)
            self.tabla.setItem(i, 5, _tabla_item_centrado(d["emisor"]))
            fc = d["fecha"]
            self.tabla.setItem(i, 6, _tabla_item_centrado(str(fc)[:16] if fc else "—"))
        self.tabla.resizeRowsToContents()


# ============================================================
# PÁGINA INCIDENCIAS
# ============================================================

_TIPOS_INCIDENCIA = [
    "ROTURA", "FALTANTE", "EXCESO", "MERCANCÍA INCORRECTA",
    "PALÉ DAÑADO", "CAJA DAÑADA", "HUMEDAD", "ERROR ETIQUETADO",
]


class _NuevaIncidenciaDialog(QDialog):

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        if isinstance(usuario, dict):
            self._usuario_str = usuario.get("nombre", "Usuario")
        else:
            self._usuario_str = str(usuario or "Usuario")
        self.setWindowTitle(tr("recep.registrar_incidencia_logisti", default="Registrar Incidencia Logística"))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("dlg_incidencia")
        self.setMinimumWidth(500)
        self._drag_pos = None
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("cuerpo_ventana")
        outer.addWidget(frame)

        ly = QVBoxLayout(frame)
        ly.setContentsMargins(30, 25, 30, 25)
        ly.setSpacing(16)

        lbl = QLabel(tr("recep.nueva_incidencia_logistica", default="NUEVA INCIDENCIA LOGÍSTICA"))
        lbl.setObjectName("titulo_cian")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(lbl)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.inp_doc = QLineEdit()
        self.inp_doc.setObjectName("input_buscador")
        self.inp_doc.setPlaceholderText(tr("recep.ej_doc_2024_001", default="ej. DOC-2024-001"))
        form.addRow("ID Documento *:", self.inp_doc)

        self.cmb_tipo = QComboBox()
        self.cmb_tipo.addItems(_TIPOS_INCIDENCIA)
        form.addRow("Tipo *:", self.cmb_tipo)

        self.inp_pale = QLineEdit()
        self.inp_pale.setObjectName("input_buscador")
        self.inp_pale.setPlaceholderText(tr("recep.opcional", default="Opcional"))
        form.addRow("ID Palé:", self.inp_pale)

        self.inp_codigo = QLineEdit()
        self.inp_codigo.setObjectName("input_buscador")
        self.inp_codigo.setPlaceholderText(tr("recep.opcional_2", default="Opcional"))
        form.addRow("Código Artículo:", self.inp_codigo)

        self.spin_cant = QSpinBox()
        self.spin_cant.setRange(0, 9999)
        form.addRow("Cantidad Afectada:", self.spin_cant)

        self.txt_desc = QTextEdit()
        self.txt_desc.setPlaceholderText(tr("recep.descripcion_detallada_de_la_", default="Descripción detallada de la incidencia..."))
        self.txt_desc.setFixedHeight(90)
        form.addRow("Descripción:", self.txt_desc)

        ly.addLayout(form)

        btns = QHBoxLayout()
        btns.setSpacing(12)
        btn_cancel = QPushButton(tr("recep.cancelar_3", default="CANCELAR"))
        btn_cancel.setObjectName("btn_secundario")
        btn_cancel.setFixedHeight(45)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton(tr("recep.registrar", default="✅  REGISTRAR"))
        btn_ok.setObjectName("btn_primario")
        btn_ok.setFixedHeight(45)
        btn_ok.clicked.connect(self._registrar)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        ly.addLayout(btns)

    def _registrar(self):
        id_doc = self.inp_doc.text().strip()
        tipo = self.cmb_tipo.currentText()
        desc = self.txt_desc.toPlainText().strip()
        if not id_doc:
            _mensaje_ui(
                self, "Campo obligatorio",
                "Debes indicar el ID del documento.", "warning"
            )
            return
        iid = _registrar_incidencia_db(
            id_documento=id_doc,
            tipo=tipo,
            descripcion=desc,
            usuario=self._usuario_str,
            id_pale=self.inp_pale.text().strip() or None,
            codigo=self.inp_codigo.text().strip() or None,
            cantidad=self.spin_cant.value(),
        )
        if iid:
            self.accept()
        else:
            _mensaje_ui(self, "Error", "No se pudo registrar la incidencia.", "error")

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._center_on_parent)

    def _center_on_parent(self):
        parent = self.parentWidget()
        ref = parent.window().frameGeometry() if parent else None
        if ref is None:
            return
        self.move(
            ref.x() + (ref.width() - self.width()) // 2,
            ref.y() + (ref.height() - self.height()) // 2,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class IncidenciasPage(QWidget):
    """Gestión de incidencias logísticas."""

    def __init__(self, usuario=None, codigo_local="ALMC", parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.codigo_local = codigo_local
        self.setObjectName("panel_contenido")
        self._datos = []
        self._setup_ui()
        self.cargar_datos()

    def _setup_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(30, 30, 30, 30)
        ly.setSpacing(20)

        hdr = QHBoxLayout()
        vc = QVBoxLayout()
        t = QLabel(tr("recep.incidencias_logisticas", default="Incidencias Logísticas"))
        t.setObjectName("titulo_cian")
        s = QLabel(tr("recep.registro_y_seguimiento_de_in", default="Registro y seguimiento de incidencias durante el proceso logístico"))
        s.setObjectName("subtitulo_muted")
        vc.addWidget(t)
        vc.addWidget(s)
        hdr.addLayout(vc)
        hdr.addStretch()
        btn_nueva = QPushButton(tr("recep.nueva_incidencia", default="⚠️  NUEVA INCIDENCIA"))
        btn_nueva.setObjectName("btn_primario")
        btn_nueva.setFixedHeight(45)
        btn_nueva.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_nueva.clicked.connect(self._abrir_nueva)
        hdr.addWidget(btn_nueva)
        hdr.addSpacing(8)
        self.btn_actualizar = QPushButton(tr("recep.actualizar_7", default="🔄 ACTUALIZAR"))
        self.btn_actualizar.setObjectName("btn_secundario")
        self.btn_actualizar.setFixedSize(150, 45)
        self.btn_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_actualizar.clicked.connect(self.ejecutar_actualizacion)
        hdr.addWidget(self.btn_actualizar)
        ly.addLayout(hdr)

        fil = QHBoxLayout()
        fil.setSpacing(12)
        lbl_f = QLabel(tr("recep.estado", default="Estado:"))
        lbl_f.setObjectName("label_campo")
        self.cmb_estado = QComboBox()
        self.cmb_estado.addItems(["TODAS", "ABIERTA", "CERRADA"])
        self.cmb_estado.setFixedWidth(160)
        self.cmb_estado.currentTextChanged.connect(self.cargar_datos)
        self.input_busqueda = QLineEdit()
        self.input_busqueda.setObjectName("input_buscador")
        self.input_busqueda.setPlaceholderText(
            tr("recep.filtrar_por_id_documento_tip", default="🔍 Filtrar por ID, Documento, Tipo o Usuario...")
        )
        self.input_busqueda.setFixedHeight(50)
        self.input_busqueda.textChanged.connect(self._filtrar)
        fil.addWidget(lbl_f)
        fil.addWidget(self.cmb_estado)
        fil.addWidget(self.input_busqueda)
        ly.addLayout(fil)

        if construir_tabla_estilizada:
            self._cont, self.tabla = construir_tabla_estilizada(self)
        else:
            self._cont = QFrame(self)
            self.tabla = QTableWidget(self._cont)
            QVBoxLayout(self._cont).addWidget(self.tabla)

        cols = [
            "ID", "TIPO", "DESCRIPCIÓN",
            "PALÉ", "ARTÍCULO", "CANT.", "USUARIO", "ESTADO", "FECHA",
        ]
        self.tabla.setColumnCount(len(cols))
        self.tabla.setHorizontalHeaderLabels(cols)
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.doubleClicked.connect(self._accion_cerrar)
        ly.addWidget(self._cont)

        hint = QLabel(tr("recep.doble_clic_sobre_una_inciden", default="Doble clic sobre una incidencia ABIERTA para cerrarla."))
        hint.setObjectName("subtitulo_muted")
        ly.addWidget(hint)

    def cargar_datos(self):
        filtro = (
            self.cmb_estado.currentText()
            if hasattr(self, "cmb_estado") else "TODAS"
        )
        self._datos = _query_incidencias(None if filtro == "TODAS" else filtro)
        self._filtrar()

    def ejecutar_actualizacion(self):
        self.btn_actualizar.setEnabled(False)
        self.btn_actualizar.setText(tr("recep.actualizando_3", default="⌛ ACTUALIZANDO..."))
        self.btn_actualizar.repaint()
        QApplication.processEvents()
        try:
            self.cargar_datos()
        finally:
            self.btn_actualizar.setEnabled(True)
            self.btn_actualizar.setText(tr("recep.actualizar_8", default="🔄 ACTUALIZAR"))

    def _filtrar(self):
        txt = (
            self.input_busqueda.text() if hasattr(self, "input_busqueda") else ""
        ).strip().lower()
        filas = [d for d in self._datos if not txt or any(
            txt in str(v).lower() for v in d.values()
        )]
        self.tabla.setRowCount(len(filas))
        for i, d in enumerate(filas):
            # Col 0: ID DOC. — shows document reference, UserRole holds incidence id for close action
            item_id = _tabla_item_centrado(str(d["id_documento"] or "—"))
            item_id.setData(Qt.ItemDataRole.UserRole, d["id"])
            self.tabla.setItem(i, 0, item_id)
            it_tipo = _tabla_item_centrado(d["tipo"])
            it_tipo.setForeground(QColor("#F97316"))
            it_tipo.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            self.tabla.setItem(i, 1, it_tipo)
            self.tabla.setItem(i, 2, _tabla_item_centrado(d["descripcion"]))
            self.tabla.setItem(i, 3, _tabla_item_centrado(d["id_pale"]))
            self.tabla.setItem(i, 4, _tabla_item_centrado(d["codigo"]))
            self.tabla.setItem(i, 5, _tabla_item_centrado(d["cantidad"]))
            self.tabla.setItem(i, 6, _tabla_item_centrado(d["usuario"]))
            ei = _tabla_item_centrado(d["estado"])
            ei.setForeground(QColor(_color_estado_log(d["estado"])))
            ei.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            self.tabla.setItem(i, 7, ei)
            fc = d["fecha_creacion"]
            self.tabla.setItem(i, 8, _tabla_item_centrado(str(fc)[:16] if fc else "—"))
        self.tabla.resizeRowsToContents()

    def _abrir_nueva(self):
        dlg = _NuevaIncidenciaDialog(self.usuario, parent=self)
        if dlg.exec():
            self.cargar_datos()
            _mensaje_ui(
                self, "Registrada",
                "La incidencia ha sido registrada correctamente.", "info"
            )

    def _accion_cerrar(self):
        fila = self.tabla.currentRow()
        if fila < 0:
            return
        estado_item = self.tabla.item(fila, 7)  # ESTADO is now col 7
        if not estado_item or estado_item.text() != "ABIERTA":
            return
        id_item = self.tabla.item(fila, 0)
        if not id_item:
            return
        try:
            inc_id = id_item.data(Qt.ItemDataRole.UserRole)  # incidence id stored in UserRole
            if inc_id is None:
                return
            inc_id = int(inc_id)
        except (ValueError, TypeError):
            return
        if not _confirmar_ui(
            self, "Cerrar incidencia",
            f"¿Confirmas el cierre de la incidencia #{inc_id}?"
        ):
            return
        if _cerrar_incidencia_db(inc_id):
            self.cargar_datos()
        else:
            _mensaje_ui(self, "Error", "No se pudo cerrar la incidencia.", "error")


# ============================================================
# HISTORIAL UNIFICADO (switch Recepciones / Traspasos)
# ============================================================

class HistorialUnificadoPage(QWidget):
    """Pestaña HISTORIAL con selector entre Recepciones y Traspasos."""

    def __init__(self, usuario=None, codigo_local="ALMC", parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.codigo_local = codigo_local
        self.setObjectName("panel_contenido")
        self._setup_ui()

    # Inline stylesheets for the pill segmented switch
    _SS_PILL_ACTIVE = (
        "QPushButton {"
        "  background-color: #00FFC6;"
        "  color: #0D1117;"
        "  border: 1px solid #00FFC6;"
        "  font-family: 'Segoe UI';"
        "  font-size: 13px;"
        "  font-weight: 700;"
        "  padding: 0 20px;"
        "}"
        "QPushButton:hover {"
        "  background-color: #00E5B3;"
        "}"
    )
    _SS_PILL_IZQUIERDO_ACTIVE = (
        _SS_PILL_ACTIVE
        + "QPushButton { border-top-left-radius: 22px; border-bottom-left-radius: 22px;"
        "  border-top-right-radius: 0px; border-bottom-right-radius: 0px; border-right: none; }"
    )
    _SS_PILL_DERECHO_ACTIVE = (
        _SS_PILL_ACTIVE
        + "QPushButton { border-top-right-radius: 22px; border-bottom-right-radius: 22px;"
        "  border-top-left-radius: 0px; border-bottom-left-radius: 0px; border-left: none; }"
    )
    _SS_PILL_INACTIVE = (
        "QPushButton {"
        "  background-color: transparent;"
        "  color: #00FFC6;"
        "  border: 1px solid #00FFC6;"
        "  font-family: 'Segoe UI';"
        "  font-size: 14px;"
        "  font-weight: 700;"
        "  padding: 0 20px;"
        "}"
        "QPushButton:hover {"
        "  background-color: rgba(0, 255, 198, 0.12);"
        "}"
    )
    _SS_PILL_IZQUIERDO_INACTIVE = (
        _SS_PILL_INACTIVE
        + "QPushButton { border-top-left-radius: 22px; border-bottom-left-radius: 22px;"
        "  border-top-right-radius: 0px; border-bottom-right-radius: 0px; border-right: none; }"
    )
    _SS_PILL_DERECHO_INACTIVE = (
        _SS_PILL_INACTIVE
        + "QPushButton { border-top-right-radius: 22px; border-bottom-right-radius: 22px;"
        "  border-top-left-radius: 0px; border-bottom-left-radius: 0px; border-left: none; }"
    )

    def _setup_ui(self):
        ly = QVBoxLayout(self)
        ly.setContentsMargins(30, 30, 30, 30)
        ly.setSpacing(20)

        # Header row: title/subtitle left, refresh button right
        hdr = QHBoxLayout()
        vc = QVBoxLayout()
        t = QLabel(tr("recep.historial_logistico", default="Historial Logístico"))
        t.setObjectName("titulo_cian")
        s = QLabel(tr("recep.consulta_el_historial_de_rec", default="Consulta el historial de recepciones de palés y traspasos de stock"))
        s.setObjectName("subtitulo_muted")
        vc.addWidget(t)
        vc.addWidget(s)
        hdr.addLayout(vc)
        hdr.addStretch()
        self.btn_refresh = QPushButton(tr("recep.actualizar_9", default="🔄 ACTUALIZAR"))
        self.btn_refresh.setObjectName("btn_primario")
        self.btn_refresh.setFixedSize(180, 45)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self._actualizar)
        hdr.addWidget(self.btn_refresh)
        ly.addLayout(hdr)

        # Pill segmented switch — inline, no wrapper frame
        pill_row = QHBoxLayout()
        pill_row.setSpacing(0)

        self.btn_rec = QPushButton(tr("recep.historial_recepciones", default="📥  HISTORIAL RECEPCIONES"))
        self.btn_rec.setFixedHeight(44)
        self.btn_rec.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_rec.clicked.connect(lambda: self._cambiar(0))

        # Divider pixel — 1 px separator between the two halves
        div = QFrame()
        div.setFixedWidth(1)
        div.setFixedHeight(44)
        div.setStyleSheet("background-color: #00FFC6;")

        self.btn_tras = QPushButton(tr("recep.historial_traspasos", default="🚚  HISTORIAL TRASPASOS"))
        self.btn_tras.setFixedHeight(44)
        self.btn_tras.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tras.clicked.connect(lambda: self._cambiar(1))

        pill_row.addStretch()
        pill_row.addWidget(self.btn_rec)
        pill_row.addWidget(div)
        pill_row.addWidget(self.btn_tras)
        pill_row.addStretch()
        ly.addLayout(pill_row)

        # Sub-pages embedded directly
        self._stack = QStackedWidget()
        self.pag_recepciones = HistorialRecepcionesPage(
            codigo_local=self.codigo_local, usuario=self.usuario
        )
        self.pag_traspasos = HistorialTraspasosPage(
            usuario=self.usuario, codigo_local=self.codigo_local
        )
        self._stack.addWidget(self.pag_recepciones)  # index 0
        self._stack.addWidget(self.pag_traspasos)    # index 1
        ly.addWidget(self._stack)

        # Hide sub-page internal headers (would duplicate our own title/refresh)
        self._ocultar_cabecera_subpagina(self.pag_recepciones)
        self._ocultar_cabecera_subpagina(self.pag_traspasos)

        # Set initial active state
        self._aplicar_estilos_pill(0)

    def _ocultar_cabecera_subpagina(self, pag):
        # HistorialRecepcionesPage wraps content in page_widget; HistorialTraspasosPage uses self directly
        target_widget = getattr(pag, 'page_widget', pag)
        target_ly = target_widget.layout() if target_widget is not None else None
        if target_ly is None:
            return
        if target_ly.count() > 0:
            target_ly.takeAt(0)
            target_ly.setContentsMargins(0, 0, 0, 0)
        # Hide any label children that were orphaned from the removed layout item
        try:
            for lbl in target_widget.findChildren(QLabel):
                if lbl.objectName() in ("titulo_cian", "subtitulo_muted"):
                    lbl.hide()
        except Exception:
            pass
        # Hide known header buttons that remain as self attributes (camera/search buttons stay visible)
        for attr in ("btn_refresh", "btn_back_level", "btn_actualizar"):
            w = getattr(pag, attr, None)
            if w is not None:
                w.hide()

    def _aplicar_estilos_pill(self, idx: int):
        if idx == 0:
            self.btn_rec.setStyleSheet(self._SS_PILL_IZQUIERDO_ACTIVE)
            self.btn_tras.setStyleSheet(self._SS_PILL_DERECHO_INACTIVE)
        else:
            self.btn_rec.setStyleSheet(self._SS_PILL_IZQUIERDO_INACTIVE)
            self.btn_tras.setStyleSheet(self._SS_PILL_DERECHO_ACTIVE)

    def _cambiar(self, idx: int):
        self._stack.setCurrentIndex(idx)
        self._aplicar_estilos_pill(idx)
        pag = self._stack.currentWidget()
        if hasattr(pag, "cargar_datos"):
            pag.cargar_datos()

    def _actualizar(self):
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText(tr("recep.actualizando_4", default="⌛ ACTUALIZANDO..."))
        self.btn_refresh.repaint()
        QApplication.processEvents()
        try:
            self.cargar_datos()
        finally:
            self.btn_refresh.setEnabled(True)
            self.btn_refresh.setText(tr("recep.actualizar_10", default="🔄 ACTUALIZAR"))

    def cargar_datos(self):
        pag = self._stack.currentWidget()
        if hasattr(pag, "cargar_datos"):
            pag.cargar_datos()


# ============================================================
# BLOQUE VENTANA PRINCIPAL DE RECEPCIÓN
# ============================================================

class RecepcionPaleWindow(QWidget):

    def __init__(self, usuario, callback_vuelta=None, codigo_local="T001", **kwargs):
        super().__init__()
        # Normalizamos el nombre del usuario (Punto 3 de coherencia)
        self.usuario = usuario
        self.callback_vuelta = callback_vuelta
        self.codigo_local = codigo_local

        self.datos_pale_actual = None
        self.hilo_pdf = None

        self.setWindowTitle(
            f"Smart Manager - Gestión Logística [{self.codigo_local}]"
        )
        self.setMinimumSize(1200, 800)

        # Atributo crítico para la limpieza de memoria
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # Motor de reabastecimiento
        self._engine = StockReplenishmentEngine(self)

        self.setup_ui()
        self.conectar_eventos_paginas()
        self.showMaximized()

    def setup_ui(self):
        # Layout Principal Horizontal
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # --- SIDEBAR ---
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar_logistica")
        self.sidebar.setFixedWidth(280)

        side_ly = QVBoxLayout(self.sidebar)
        side_ly.setContentsMargins(0, 40, 0, 20)
        side_ly.setSpacing(0)

        lbl_m = QLabel(tr("recep.logistica", default="LOGÍSTICA"))
        lbl_m.setObjectName("sidebar_title")
        side_ly.addWidget(lbl_m)

        # Botones de navegación — 7 pestañas enterprise
        self.btn_nav_scan      = self.crear_boton_nav("Recepción", True)
        self.btn_nav_traspasar = self.crear_boton_nav("Traspasos")
        self.btn_nav_prep      = self.crear_boton_nav("Preparación")
        self.btn_nav_expedir   = self.crear_boton_nav("Expediciones")
        self.btn_nav_incid     = self.crear_boton_nav("Incidencias")
        self.btn_nav_historial = self.crear_boton_nav("Historial")
        self.btn_nav_reab      = self.crear_boton_nav("Reabastecimiento")

        self.lista_botones_nav = [
            self.btn_nav_scan,
            self.btn_nav_traspasar,
            self.btn_nav_prep,
            self.btn_nav_expedir,
            self.btn_nav_incid,
            self.btn_nav_historial,
            self.btn_nav_reab,
        ]

        for btn in self.lista_botones_nav:
            btn.setFixedHeight(55)
            try:
                btn.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
                )
            except Exception:
                pass
            side_ly.addWidget(btn)

        side_ly.addStretch()

        # Botón salir
        self.btn_sidebar_exit_widget = SidebarButton("SALIR AL MENÚ")
        self.btn_sidebar_exit_widget.setObjectName("btn_sidebar_exit")
        self.btn_sidebar_exit_widget.setFixedHeight(55)
        self.btn_sidebar_exit_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sidebar_exit_widget.clicked.connect(self.ejecutar_volver)
        try:
            self.btn_sidebar_exit_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
        except Exception:
            pass
        side_ly.addWidget(self.btn_sidebar_exit_widget)

        self.main_layout.addWidget(self.sidebar)

        # --- ÁREA DE CONTENIDO (QStackedWidget) — 7 páginas enterprise ---
        # Lazy load: construir las 7 sub-páginas en el __init__ hacía la apertura
        # lenta (~850 ms; cada página hace consultas y construye UI pesada). Ahora
        # solo se construye la inicial (RECEPCIÓN, ligera); el resto se crean la
        # primera vez que se visitan.
        self.vistas = QStackedWidget()
        self.vistas.setObjectName("contenido_logistica")

        self.vista_landing_scanner = LandingScannerPage()                       # 0 RECEPCIÓN (eager)
        self.vistas.addWidget(self.vista_landing_scanner)

        self._vista_factories = {
            1: lambda: TraspasoStockPage(usuario=self.usuario, codigo_local=self.codigo_local),
            2: lambda: PreparacionPage(usuario=self.usuario, codigo_local=self.codigo_local),
            3: lambda: ExpedicionesPage(usuario=self.usuario, codigo_local=self.codigo_local),
            4: lambda: IncidenciasPage(usuario=self.usuario, codigo_local=self.codigo_local),
            5: lambda: HistorialUnificadoPage(usuario=self.usuario, codigo_local=self.codigo_local),
            6: lambda: _ReabastecimientoPage(self._engine),
        }
        self._vista_attr = {
            1: "vista_traspaso", 2: "vista_preparacion", 3: "vista_expediciones",
            4: "vista_incidencias", 5: "vista_historial", 6: "vista_reabastecimiento",
        }
        self._vista_built = {0: True}
        # Placeholders (y atributos a None) para los índices 1..6.
        for i in range(1, 7):
            setattr(self, self._vista_attr[i], None)
            self.vistas.addWidget(QWidget())

        self.main_layout.addWidget(self.vistas)

    def _ensure_vista(self, index):
        """Construye la sub-página `index` la primera vez que se visita."""
        if self._vista_built.get(index):
            return
        factory = self._vista_factories.get(index)
        if factory is None:
            return
        page = factory()
        old = self.vistas.widget(index)
        self.vistas.insertWidget(index, page)
        self.vistas.removeWidget(old)
        old.deleteLater()
        setattr(self, self._vista_attr[index], page)
        self._vista_built[index] = True
        self._wire_vista(index, page)

    def _wire_vista(self, index, page):
        """Conecta las señales propias de cada sub-página al construirla (lazy)."""
        if index == 1 and hasattr(page, "btn_lanzar_dialogo"):
            try:
                page.btn_lanzar_dialogo.clicked.disconnect()
            except (TypeError, RuntimeError):
                pass
            page.btn_lanzar_dialogo.clicked.connect(self.abrir_dialogo_traspaso_final)


    def crear_boton_nav(self, txt, active=False):
        """Crea botones de sidebar ocupando todo el ancho usando el estilo global."""
        btn = SidebarButton(txt.upper())
        btn.setObjectName("btn_sidebar")
        btn.setFixedHeight(55)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setCheckable(True)
        btn.setChecked(bool(active))
        btn.setAutoExclusive(True)
        btn.setFlat(True)

        try:
            btn.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            btn.setMouseTracking(True)
        except Exception:
            pass

        try:
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        except Exception:
            pass

        try:
            btn.setMinimumWidth(0)
        except Exception:
            pass

        try:
            from assets.estilo_global import aplicar_estilo_widget

            aplicar_estilo_widget(btn)
        except Exception:
            pass

        return btn

    def conectar_eventos_paginas(self):
        """
        Conecta clics de botones y eventos de las sub-páginas y diálogos.
        Implementa desconexión de seguridad para evitar duplicidad de ventanas.
        """
        # 1. Botones de la Sidebar — 7 pestañas enterprise
        self.btn_nav_scan.clicked.connect(
            lambda: self.cambiar_vista(0, self.btn_nav_scan)
        )
        self.btn_nav_traspasar.clicked.connect(
            lambda: self.cambiar_vista(1, self.btn_nav_traspasar)
        )
        self.btn_nav_prep.clicked.connect(
            lambda: self.cambiar_vista(2, self.btn_nav_prep)
        )
        self.btn_nav_expedir.clicked.connect(
            lambda: self.cambiar_vista(3, self.btn_nav_expedir)
        )
        self.btn_nav_incid.clicked.connect(
            lambda: self.cambiar_vista(4, self.btn_nav_incid)
        )
        self.btn_nav_historial.clicked.connect(
            lambda: self.cambiar_vista(5, self.btn_nav_historial)
        )
        self.btn_nav_reab.clicked.connect(
            lambda: self.cambiar_vista(6, self.btn_nav_reab)
        )

        # 2. Acción del botón central de la Landing Page
        if hasattr(self.vista_landing_scanner, "btn_iniciar"):
            try:
                self.vista_landing_scanner.btn_iniciar.clicked.disconnect()
            except (TypeError, RuntimeError):
                pass
            self.vista_landing_scanner.btn_iniciar.clicked.connect(
                self.abrir_escaner_recepcion
            )

        # 3. PUENTE CRÍTICO ("Ventana Doble"): la página de Traspasos ahora se
        # construye de forma diferida (lazy), así que su señal btn_lanzar_dialogo
        # se conecta en _wire_vista(1) cuando la página se crea por primera vez.

    def abrir_dialogo_traspaso_final(self):
        """Lanza el TraspasoDialog de forma modal, controlada y sin duplicidad."""

        # 1. Seguro de reentrada: Evita abrir si ya hay uno intentando abrirse
        if hasattr(self, "_bloqueo_dialogo") and self._bloqueo_dialogo:
            return

        self._bloqueo_dialogo = True

        try:
            # 2. Instanciamos el diálogo
            dialogo = TraspasoDialog(parent=self, tienda_id=self.codigo_local)

            # 3. Ejecución modal (bloquea el resto de la app)
            resultado = dialogo.exec()

            # 4. Al cerrar, evaluamos el resultado
            if resultado:
                # Si el diálogo terminó en éxito, refrescamos el historial (solo
                # si ya se ha construido — es lazy).
                hist = getattr(self, "vista_historial", None)
                if hist is not None and hasattr(hist, "cargar_datos"):
                    hist.cargar_datos()

            # 5. Limpieza explícita del objeto en memoria
            dialogo.deleteLater()

        except Exception as e:
            import logging

            logging.error(f"Error al abrir el diálogo de traspaso: {e}")

        finally:
            # 6. Liberamos el bloqueo siempre, pase lo que pase
            self._bloqueo_dialogo = False

    def abrir_escaner_recepcion(self):
        """Lanza el diálogo de cámara para iniciar la recepción."""

        dialogo = ScannerDialog(parent=self, usuario=self.usuario)

        # Conexión de la señal del Scanner con el procesador de DB de esta ventana
        dialogo.confirmar_recepcion.connect(self.procesar_confirmacion_recepcion)

        dialogo.exec()

    def cambiar_vista(self, index, boton_activo):
        """
        Gestiona el cambio de página en el QStackedWidget y
        actualiza visualmente el botón seleccionado con feedback inmediato.
        """
        # 1. Construir la sub-página si aún no existe (lazy) y cambiar el índice
        self._ensure_vista(index)
        self.vistas.setCurrentIndex(index)

        # 2. Resetear el estado checked de todos los botones (delegar estilo al CSS global)
        for btn in self.lista_botones_nav:
            try:
                btn.setChecked(False)
            except Exception:
                pass

        # 3. Marcar el botón activo para que el selector CSS `:checked` lo pinte
        try:
            boton_activo.setChecked(True)
        except Exception:
            pass

        # 4. Refresco automático y Gestión de estado "En blanco"
        pagina_actual = self.vistas.currentWidget()

        if hasattr(pagina_actual, "cargar_datos"):
            # Si la página tiene buscador, limpiamos el filtro para mostrar todo al entrar
            if hasattr(pagina_actual, "input_busqueda"):
                pagina_actual.input_busqueda.clear()

            # Forzamos la carga de datos
            pagina_actual.cargar_datos()

        # 5. Foco automático: Si es la página de traspaso o scanner, ponemos el foco en el input
        # para que el usuario pueda empezar a disparar con el lector láser de inmediato.
        if hasattr(pagina_actual, "input_codigo_manual"):
            pagina_actual.input_codigo_manual.setFocus()

    def ejecutar_volver(self):
        """Regresa al menú principal despertando la ventana anterior y limpiando la actual."""
        try:
            # Buscamos la ruta de retorno
            callback = getattr(self, "callback_vuelta", None)

            if callback:
                # 1. Ocultamos primero para dar sensación de velocidad
                self.hide()

                # 2. Ejecutamos el retorno al padre (MenuPrincipal.mostrar_menu_principal)
                callback()

                # 3. Forzamos limpieza de la cola de eventos para evitar el WARNING de navegación

                QApplication.processEvents()

                # 4. Cerramos definitivamente
                self.close()
            else:
                logger.warning(
                    "Navegación: No se detectó callback_vuelta. Forzando cierre seguro."
                )
                self.close()

        except Exception as e:
            logger.error(f"Error crítico en navegación de retorno: {e}")
            self.close()

    def procesar_confirmacion_recepcion(self, id_pale_escaneado, items_a_recibir):
        """
        Procesa la entrada de mercancía extrayendo el ID de movimiento
        del ID de palé impersonal escaneado y actualizando stock.
        """
        if not id_pale_escaneado or not items_a_recibir:
            _mensaje_ui(self, "Error", "No hay datos válidos para recibir.", "warning")
            return

        # 1. PARSEAR ID IMPERSONAL (PAL-SIGLA-ORIGEN-SEC-DESTINO)
        partes = id_pale_escaneado.split("-")
        if len(partes) < 5:
            _mensaje_ui(
                self, "Error", "Formato de etiqueta de palé no reconocido.", "error"
            )
            return

        # Reconstruimos el ID de movimiento maestro (TRA-ORIGEN-SEC-DESTINO-AÑO)
        origen_id, sec_id, destino_id = partes[2], partes[3], partes[4]
        anio_actual = datetime.now().year
        id_movimiento_maestro = f"TRA-{origen_id}-{sec_id}-{destino_id}-{anio_actual}"

        CODIGOS_IGNORAR = ["LOGISTICA", "PALE", "CARTON", "PLASTICO", "VACIO", "BULTO"]
        articulos_no_encontrados = []
        count_actualizados = 0

        try:

            conn = obtener_conexion()
            cursor = conn.cursor()

            # 2. VALIDACIÓN: ¿Existe el movimiento y es para esta tienda?
            cursor.execute(
                "SELECT estado, destino FROM documentos_logisticos WHERE id_documento = %s",
                (id_movimiento_maestro,),
            )
            registro = None
            r = cursor.fetchone()
            if isinstance(r, dict):
                registro = r
            elif r:
                # Cursor may return tuple; map to keys if available
                # Try to fetch column names from cursor.description
                try:
                    cols = [c[0] for c in cursor.description]
                    registro = dict(zip(cols, r, strict=False))
                except Exception:
                    registro = None

            if not registro:
                _mensaje_ui(
                    self,
                    "Error",
                    f"No existe el registro maestro: {id_movimiento_maestro}",
                    "error",
                )
                return

            if (registro is None) or (registro.get("destino") != self.codigo_local):
                _mensaje_ui(
                    self,
                    "Destino Incorrecto",
                    f"Este palé está destinado a {registro['destino']}. No puede recibirlo en {self.codigo_local}.",
                    "error",
                )
                return

            # 3. PROCESAMIENTO DE ARTÍCULOS
            for item in items_a_recibir:
                cod = str(item[0]).strip().upper()
                nombre = item[1]
                cant = item[2]

                if any(x in cod for x in CODIGOS_IGNORAR):
                    continue

                    # Verificar si el artículo existe en el maestro global
                    cursor.execute(
                        "SELECT codigo FROM articulos WHERE codigo = %s", (cod,)
                    )
                    if cursor.fetchone():
                        # ACTUALIZACIÓN DE STOCK (Centralizado)
                        cursor.execute(
                            """UPDATE articulos 
                           SET Stock_total = Stock_total + %s, 
                               Stock_tienda = Stock_tienda + %s 
                           WHERE codigo = %s""",
                            (cant, cant, cod),
                        )
                    count_actualizados += 1
                else:
                    # El artículo es nuevo para el sistema
                    articulos_no_encontrados.append(
                        {"ean": cod, "nombre": nombre, "cantidad": cant}
                    )

            # 4. ACTUALIZAR ESTADOS DE TRAZABILIDAD
            # Marcamos el documento maestro como RECIBIDO
            cursor.execute(
                """UPDATE documentos_logisticos 
                   SET estado = 'RECIBIDO', 
                       fecha_recepcion = NOW(), 
                       usuario_receptor = %s 
                   WHERE id_documento = %s""",
                (self.usuario, id_movimiento_maestro),
            )

            # Marcamos el palé específico como verificado en la tabla de pales
            cursor.execute(
                "UPDATE documentos_logisticos_pales SET estado = 'VERIFICADO' WHERE id_pale = %s AND id_documento = %s",
                (id_pale_escaneado, id_movimiento_maestro),
            )

            conn.commit()
            conn.close()

            # Marcar propuestas activas de los artículos recibidos como RECIBIDO
            codigos_recibidos = [
                str(item[0]).strip().upper()
                for item in items_a_recibir
                if not any(x in str(item[0]).upper() for x in CODIGOS_IGNORAR)
            ]
            if codigos_recibidos:
                _reab_marcar_articulos_recibidos(codigos_recibidos)
                try:
                    from src.db.conexion import stock_signals as _db_signals
                    _db_signals.propuestas_actualizadas.emit()
                except Exception:
                    pass

            # 5. FEEDBACK FINAL
            resumen = f"Stock actualizado: {count_actualizados} productos."
            if articulos_no_encontrados:
                resumen += f"\n\nAtención: {len(articulos_no_encontrados)} códigos no existen en la base de datos."

            _mensaje_ui(self, "Recepción Exitosa", resumen, "success")

            # Si hay artículos nuevos, abrir diálogo de creación rápida
            if articulos_no_encontrados:

                dialogo = DialogoNuevosArticulos(articulos_no_encontrados, self)
                dialogo.exec()

            # Redirigir automáticamente al Historial (Vista Index 5)
            self.cambiar_vista(5, self.btn_nav_historial)

        except Exception as e:
            _mensaje_ui(
                self, "Error de Base de Datos", f"Fallo crítico: {str(e)}", "error"
            )


# ============================================================
# BLOQUE DIÁLOGOS DE GESTIÓN DE ARTÍCULOS
# ============================================================

class DialogoNuevosArticulos(QDialog):

    def __init__(self, items_nuevos, parent=None):
        """
        items_nuevos: Lista de diccionarios [{'ean':..., 'nombre':..., 'cantidad':...}]
        """
        super().__init__(parent)
        self.items_nuevos = items_nuevos

        self.setWindowTitle(tr("recep.gestion_de_articulos_nuevos", default="Gestión de Artículos Nuevos"))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("dlg_entrada_cantidad")
        self.setMinimumSize(700, 500)

        self.setup_ui()

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("cuerpo_ventana")
        outer.addWidget(frame)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)

        # Encabezado informativo con acento neón
        lbl = QLabel(tr("recep.se_han_detectado_codigos_ean", default="⚠️ Se han detectado códigos EAN no registrados"))
        lbl.setObjectName("titulo_cian")
        layout.addWidget(lbl)

        sub_lbl = QLabel(
            tr("recep.los_articulos_listados_a_con", default="Los artículos listados a continuación se darán de alta con stock inicial.")
        )
        sub_lbl.setObjectName("subtitulo_muted")
        layout.addWidget(sub_lbl)

        # Configuración de la Tabla (Estilo Global)
        self.tabla = QTableWidget(len(self.items_nuevos), 3)
        self.tabla.setHorizontalHeaderLabels(
            ["CÓDIGO EAN", "DESCRIPCIÓN SUGERIDA", "CANTIDAD RECIBIDA"]
        )

        # Estética de la tabla (Sincronizada con el resto de módulos)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setShowGrid(False)  # Estilo más limpio

        header = self.tabla.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # Llenado de datos (Lógica original intacta)
        for i, item in enumerate(self.items_nuevos):
            # EAN
            it_ean = QTableWidgetItem(str(item["ean"]))
            it_ean.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(i, 0, it_ean)

            # NOMBRE
            it_nombre = QTableWidgetItem(str(item["nombre"]))
            self.tabla.setItem(i, 1, it_nombre)

            # CANTIDAD
            it_cant = QTableWidgetItem(str(item["cantidad"]))
            it_cant.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(i, 2, it_cant)

        layout.addWidget(self.tabla)

        # Botonera
        btns_layout = QHBoxLayout()
        btns_layout.setSpacing(15)

        self.btn_cancelar = QPushButton(tr("recep.cancelar_registro", default="❌ Cancelar Registro"))
        self.btn_cancelar.setObjectName("btn_peligro")
        self.btn_cancelar.setFixedHeight(45)
        self.btn_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancelar.clicked.connect(self.reject)

        self.btn_confirmar = QPushButton(tr("recep.registrar_y_finalizar", default="✅ Registrar y Finalizar"))
        self.btn_confirmar.setObjectName("btn_primario")
        self.btn_confirmar.setFixedHeight(45)
        self.btn_confirmar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirmar.clicked.connect(self.procesar_altas_db)

        btns_layout.addWidget(self.btn_cancelar)
        btns_layout.addWidget(self.btn_confirmar)
        layout.addLayout(btns_layout)

    def procesar_altas_db(self):
        """Inserta los artículos nuevos en la base de datos."""
        exitos = 0
        try:

            with obtener_conexion() as conn:
                cursor = conn.cursor()
                for item in self.items_nuevos:
                    # Insertamos en la tabla maestra 'articulos'
                    # Se asume que precio=0.0 y estado='activo' para nuevos registros logísticos
                    cursor.execute(
                        """
                        INSERT INTO articulos (codigo, nombre, stock_total, stock_tienda, precio, estado)
                        VALUES (?, ?, ?, ?, 0.0, 'activo')
                        """,
                        (
                            item["ean"],
                            item["nombre"],
                            item["cantidad"],
                            item["cantidad"],
                        ),
                    )
                    exitos += 1
                conn.commit()

            _mensaje_ui(
                self,
                "Éxito",
                f"Se han registrado {exitos} nuevos productos correctamente.",
                "success",
            )
            self.accept()

        except Exception as e:
            _mensaje_ui(
                self, "Error", f"No se pudieron registrar los artículos: {str(e)}", "error"
            )


# ============================================================
# BLOQUE DIÁLOGO DE TRASPASO
# ============================================================


class _PesoDialog(QDialog):
    """Diálogo frameless para capturar el peso de un bulto (texto libre)."""

    def __init__(self, titulo: str, texto: str, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("dlg_entrada_cantidad")
        self.setMinimumWidth(400)
        self._drag_pos = None
        self._valor: str = ""
        self._build_ui(titulo, texto)

    def _build_ui(self, titulo, texto):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("cuerpo_ventana")
        outer.addWidget(frame)
        ly = QVBoxLayout(frame)
        ly.setContentsMargins(28, 22, 28, 22)
        ly.setSpacing(14)

        lbl_titulo = QLabel(titulo.upper())
        lbl_titulo.setObjectName("titulo_cian")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(lbl_titulo)

        lbl_texto = QLabel(texto)
        lbl_texto.setWordWrap(True)
        ly.addWidget(lbl_texto)

        self.input = QLineEdit()
        self.input.setPlaceholderText(tr("recep.ej_18_5", default="Ej: 18.5"))
        self.input.setFixedHeight(46)
        self.input.returnPressed.connect(self._aceptar)
        ly.addWidget(self.input)

        h = QHBoxLayout()
        h.setSpacing(12)
        btn_skip = QPushButton(tr("recep.dejar_pendiente", default="DEJAR PENDIENTE"))
        btn_skip.setObjectName("btn_secundario")
        btn_skip.setFixedHeight(44)
        btn_skip.clicked.connect(self.accept)
        btn_ok = QPushButton(tr("recep.guardar_peso", default="GUARDAR PESO"))
        btn_ok.setObjectName("btn_primario")
        btn_ok.setFixedHeight(44)
        btn_ok.clicked.connect(self._aceptar)
        h.addWidget(btn_skip)
        h.addWidget(btn_ok)
        ly.addLayout(h)

    def _aceptar(self):
        self._valor = self.input.text().strip()
        self.accept()

    def get_value(self) -> str:
        return self._valor

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._center_on_parent)

    def _center_on_parent(self):
        parent = self.parentWidget()
        ref = parent.window().frameGeometry() if parent else None
        if ref is None:
            return
        self.move(
            ref.x() + (ref.width() - self.width()) // 2,
            ref.y() + (ref.height() - self.height()) // 2,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class _EntradaCantidadDialog(QDialog):
    """Frameless quantity-input dialog replacing QInputDialog.getInt."""

    def __init__(self, titulo, texto, valor_min=1, valor_max=9999, valor_defecto=1, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("dlg_entrada_cantidad")
        self.setMinimumWidth(380)
        self._drag_pos = None
        self._valor = valor_defecto
        self._build_ui(titulo, texto, valor_min, valor_max, valor_defecto)

    def _build_ui(self, titulo, texto, valor_min, valor_max, valor_defecto):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("cuerpo_ventana")
        outer.addWidget(frame)

        ly = QVBoxLayout(frame)
        ly.setContentsMargins(28, 22, 28, 22)
        ly.setSpacing(14)

        lbl_titulo = QLabel(titulo.upper())
        lbl_titulo.setObjectName("titulo_cian")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(lbl_titulo)

        lbl_texto = QLabel(texto)
        lbl_texto.setWordWrap(True)
        ly.addWidget(lbl_texto)

        self.spin = QSpinBox()
        self.spin.setRange(valor_min, valor_max)
        self.spin.setValue(valor_defecto)
        self.spin.setFixedHeight(46)
        ly.addWidget(self.spin)

        btns = QHBoxLayout()
        btns.setSpacing(12)
        btn_cancel = QPushButton(tr("recep.cancelar_4", default="CANCELAR"))
        btn_cancel.setObjectName("btn_secundario")
        btn_cancel.setFixedHeight(44)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton(tr("recep.aceptar_2", default="ACEPTAR"))
        btn_ok.setObjectName("btn_primario")
        btn_ok.setFixedHeight(44)
        btn_ok.clicked.connect(self._aceptar)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        ly.addLayout(btns)

    def _aceptar(self):
        self._valor = self.spin.value()
        self.accept()

    def get_value(self):
        return self._valor

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._center_on_parent)

    def _center_on_parent(self):
        parent = self.parentWidget()
        ref = parent.window().frameGeometry() if parent else None
        if ref is None:
            return
        self.move(
            ref.x() + (ref.width() - self.width()) // 2,
            ref.y() + (ref.height() - self.height()) // 2,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class TraspasoDialog(QDialog):

    def __init__(
        self,
        usuario=None,
        tipo: str = "enviar",
        codigo_local="ALMC",
        payload_items: list[dict] | None = None,
        pale_codigo: str | None = None,
        parent=None,
        **kwargs,
    ):
        super().__init__(parent)

        # 1. ATRIBUTOS DE SESIÓN Y ESTADO (Punto 3: Normalización)
        self.usuario = usuario
        self.nombre_usuario = usuario
        # Si recibimos 'tienda_id' vía kwargs, lo priorizamos sobre codigo_local
        self.codigo_local = kwargs.get("tienda_id", codigo_local)
        self.tipo = tipo
        self.payload_items = payload_items or []
        self.pale_codigo = pale_codigo

        # 2. TRABAJO EN SEGUNDO PLANO
        try:
            self.pdf_worker = PdfWorker()
        except Exception:
            self.pdf_worker = None

        # 3. CONFIGURACIÓN DE VENTANA (Look PDA)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 4. VARIABLES DE FLUJO
        self.origen_final = ""
        self.destino_final = ""
        self.agencia_final = ""
        self.observaciones_final = ""
        self.items_widgets: list[dict] = []
        self.peso_bulto = {}
        self.lista_pales_final = []

        self.opciones_especiales = [
            "PALÉ VACÍO (LOGÍSTICO)",
            "PALÉ REMONTADO",
            "PALÉ CARTÓN",
            "PALÉ PLÁSTICO",
            "JAULA METÁLICA (JAU)",
            "CONTENEDOR METÁLICO",
        ]

        # 5. CONFIGURACIÓN DE SEDE (Punto 5: Imports movidos a cabecera en el archivo final)
        try:

            config = obtener_configuracion()
            tienda_cfg = (
                self.codigo_local
                if self.codigo_local
                else config.get("tienda_codigo", "ALMC")
            )
            self.tienda_id_formateado = formatear_nombre_centro(str(tienda_cfg))
            self.tienda_codigo = str(tienda_cfg)
        except Exception:
            self.tienda_id_formateado = "ALMACÉN CENTRAL"
            self.tienda_codigo = "ALMC"

        # 6. INICIALIZAR INTERFAZ
        self.setup_ui()

        # AJUSTE DE GEOMETRÍA SEGURO
        if parent:
            self.setGeometry(parent.geometry())
        else:
            self.setMinimumSize(1200, 800)

        # 7. CARGA DE ITEMS PREVIOS
        if self.payload_items:
            for item in self.payload_items:
                if hasattr(self, "procesar_insercion_item"):
                    self.procesar_insercion_item(
                        item.get("codigo"),
                        item.get("cantidad", 1),
                        es_logistico=False,
                    )

    def setup_ui(self):
        """Configura la interfaz de Salida Logística con estética GitHub Dark."""
        # Contenedor principal para permitir bordes redondeados en Frameless
        self.main_frame = QFrame(self)
        self.main_frame.setObjectName("panel_dialogo_logistico")

        main_layout_container = QVBoxLayout(self)
        main_layout_container.setContentsMargins(0, 0, 0, 0)
        main_layout_container.addWidget(self.main_frame)

        layout_principal = QVBoxLayout(self.main_frame)
        layout_principal.setContentsMargins(30, 30, 30, 30)
        layout_principal.setSpacing(20)

        # --- CABECERA ---
        header = QHBoxLayout()
        lbl_titulo = QLabel(tr("recep.salida_logistica", default="SALIDA LOGÍSTICA"))
        lbl_titulo.setObjectName("titulo_cian")

        self.btn_back = QPushButton("✕")
        self.btn_back.setObjectName("btn_icono_peligro")
        self.btn_back.setFixedSize(40, 40)
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.clicked.connect(self.ejecutar_volver)

        header.addWidget(lbl_titulo)
        header.addStretch()
        header.addWidget(self.btn_back)
        layout_principal.addLayout(header)

        # --- SECCIÓN DE ENTRADA ---
        input_group = QVBoxLayout()
        lbl_origen_info = QLabel(f"ORIGEN: {self.tienda_id_formateado}")
        lbl_origen_info.setObjectName("origen_info")

        h_input = QHBoxLayout()
        h_input.setSpacing(10)

        self.input_codigo_manual = QLineEdit()
        self.input_codigo_manual.setObjectName("input_buscador")
        self.input_codigo_manual.setPlaceholderText(
            tr("recep.escanee_ean_o_codigo_de_arti", default="Escanee EAN o Código de Artículo...")
        )
        self.input_codigo_manual.setFixedHeight(55)
        self.input_codigo_manual.setCompleter(None)  # Blindaje
        self.input_codigo_manual.returnPressed.connect(self.agregar_articulo_manual)

        btn_cam = QPushButton(tr("recep.scan_2", default="📷 SCAN"))
        btn_cam.setObjectName("btn_secundario")
        btn_cam.setFixedSize(110, 55)
        btn_cam.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cam.clicked.connect(lambda: self.abrir_escaner_camara())

        self.btn_add_manual = QPushButton(tr("recep.anadir_2", default="AÑADIR"))
        self.btn_add_manual.setObjectName("btn_primario")
        self.btn_add_manual.setFixedSize(110, 55)
        self.btn_add_manual.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_manual.clicked.connect(self.agregar_articulo_manual)

        h_input.addWidget(self.input_codigo_manual)
        h_input.addWidget(btn_cam)
        h_input.addWidget(self.btn_add_manual)
        input_group.addWidget(lbl_origen_info)
        input_group.addLayout(h_input)
        layout_principal.addLayout(input_group)

        # --- SELECTOR DE PALÉ ---
        h_asignar = QHBoxLayout()
        h_asignar.setSpacing(10)

        _OPCIONES_PALE = [f"PALÉ {i:02d}" for i in range(1, 21)]
        self._opciones_pale = _OPCIONES_PALE

        self.global_pale_selector = QComboBox()
        self.global_pale_selector.addItems(_OPCIONES_PALE)
        self.global_pale_selector.setFixedSize(220, 46)

        lbl_cargar = QLabel(tr("recep.cargar_en", default="CARGAR EN:"))
        lbl_cargar.setObjectName("etiqueta_secundaria")
        lbl_cargar.setStyleSheet("font-size: 12px; font-weight: 900;")

        h_asignar.addWidget(lbl_cargar)
        h_asignar.addWidget(self.global_pale_selector)
        h_asignar.addStretch()
        layout_principal.addLayout(h_asignar)

        # --- ÁREA DE LISTADO ---
        self.scroll_container = QWidget()
        self.scroll_container.setObjectName("scroll_transparente")
        self.scroll_layout = QVBoxLayout(self.scroll_container)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setObjectName("scroll_transparente")
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.scroll_container)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout_principal.addWidget(scroll)

        # --- BOTÓN DE VALIDACIÓN (Paso 1) ---
        self.btn_confirmar = QPushButton(tr("recep.paso_1_validar_articulos", default="PASO 1: VALIDAR ARTÍCULOS"))
        self.btn_confirmar.setObjectName("btn_secundario")
        self.btn_confirmar.setFixedHeight(65)
        self.btn_confirmar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirmar.clicked.connect(self.gestionar_confirmacion_final)
        layout_principal.addWidget(self.btn_confirmar)

    def procesar_insercion_item(
        self, codigo, cantidad, nombre=None, stock_max=999, es_logistico=False
    ):
        """
        Procesa la lógica de añadir un ítem.
        Busca duplicados en el palé actual para sumar cantidades o crea una fila nueva.
        """
        codigo_str = str(codigo).strip().upper()
        nombre_str = str(nombre if nombre else codigo).strip()

        # Seguridad: Si el selector no existe o no tiene texto, usamos un valor por defecto
        pale_actual = "PALÉ 01"
        if hasattr(self, "global_pale_selector"):
            pale_actual = self.global_pale_selector.currentText()

        # 1. Verificar si el artículo ya existe en el MISMO palé para sumar cantidad
        for item in self.items_widgets:
            if (
                item["codigo"] == codigo_str
                and item["pale"].currentText() == pale_actual
            ):
                try:
                    cant_int = int(cantidad)
                    nueva_cantidad = item["spinbox"].value() + cant_int
                    item["spinbox"].setValue(min(nueva_cantidad, stock_max))

                    if feedback_frame_item_resaltado is not None:
                        feedback_frame_item_resaltado(item["frame"], 500)

                    self._limpiar_buscador_tras_accion()
                    return
                except ValueError:
                    continue

        # 2. Si es un ítem nuevo, crear la fila visual
        try:
            # Aseguramos que cantidad sea entero antes de pasar a la UI
            cant_final = int(cantidad)

            self._agregar_item_a_layout(
                codigo_str,
                nombre_str,
                stock_max,
                cant_final,
                pale_actual,
                es_logistico,
            )

            # Matamos cualquier rastro de autocompletado fantasma
            self._limpiar_buscador_tras_accion()

        except Exception as e:
            import logging

            logging.error(f"Error al insertar item {codigo_str}: {e}")

            _mensaje_ui(
                self, "Error de Inserción", f"No se pudo añadir el artículo: {e}", "warning"
            )

    def _limpiar_buscador_tras_accion(self):
        """
        Método de soporte para asegurar que el buscador queda ciego y limpio.
        Resetea el completer, limpia el texto y fuerza el foco limpio.
        """
        # Desactiva el motor de autocompletado radicalmente
        self.input_codigo_manual.setCompleter(None)

        # Limpia el contenido
        self.input_codigo_manual.clear()

        # Rompe el foco y lo recupera para resetear el estado del input en el SO
        self.input_codigo_manual.clearFocus()
        self.input_codigo_manual.setFocus()

        # Feedback visual opcional en el placeholder
        self.input_codigo_manual.setPlaceholderText(tr("recep.listo_para_siguiente_escaneo", default="Listo para siguiente escaneo..."))

    def eliminar_widget(self, frame_item, codigo):
        """
        Elimina un artículo de la lista visual y del registro interno.
        Asegura la limpieza de memoria y actualiza el estado del botón principal.
        """
        try:
            # 1. Filtrar la lista interna de control
            # Usamos una lista nueva para evitar problemas de mutación durante la iteración
            self.items_widgets = [
                i for i in self.items_widgets if i["frame"] != frame_item
            ]

            # 2. Borrado físico del widget
            if frame_item:
                frame_item.setParent(None)
                frame_item.deleteLater()

            # 3. Gestión del estado del botón de confirmación
            if not self.items_widgets:
                # Si no hay ítems, el botón vuelve a su estado inicial de "Paso 1"
                self.btn_confirmar.setText(tr("recep.paso_1_validar_articulos_2", default="PASO 1: VALIDAR ARTÍCULOS"))
                self.btn_confirmar.setEnabled(True)
                self.btn_confirmar.setStyleSheet("")
                if aplicar_estilo_widget is not None:
                    aplicar_estilo_widget(self.btn_confirmar)

                # Limpieza de variables de pesaje acumulado
                if hasattr(self, "peso_bulto"):
                    self.peso_bulto = {}

            # 4. Mantenimiento del flujo: Devolver foco al buscador principal
            # Esto es vital para que el usuario pueda seguir escaneando sin tocar la pantalla
            if hasattr(self, "input_codigo_manual"):
                self.input_codigo_manual.setFocus()
                self.input_codigo_manual.selectAll()

        except Exception as e:
            import logging

            logging.error(f"Error al eliminar widget del artículo {codigo}: {e}")

    def solicitar_pesos_pales(self):
        """
        PUNTO 2: Captura de pesos opcionales.
        Si se deja vacío, se asume peso pendiente (None).
        """

        # Identificar bultos únicos (Palés o Jaulas)
        pales_usados = sorted(
            list(
                set(
                    iw["pale"].currentText().strip().upper().replace(" ", "")
                    for iw in self.items_widgets
                    if iw["pale"].currentText().strip()
                )
            )
        )

        self.peso_bulto = {}

        for pale in pales_usados:
            # Personalizamos el mensaje según si es una Jaula o un Palé
            tipo_bulto = "la JAULA" if "JAU" in pale or "JAULA" in pale else "el PALÉ"

            dlg_peso = _PesoDialog(
                f"PESAJE: {pale}",
                f"Peso para {tipo_bulto} {pale}\n(Dejar vacío si no se puede pesar ahora):",
                parent=self,
            )
            dlg_peso.exec()
            peso_str = dlg_peso.get_value()

            if not peso_str:
                self.peso_bulto[pale] = None
            else:
                try:
                    valor = float(peso_str.replace(",", "."))
                    self.peso_bulto[pale] = round(valor, 2)
                except ValueError:
                    _mensaje_ui(
                        self,
                        "Error",
                        f"Formato inválido en {pale}. Se marcará como pendiente.",
                        "warning",
                    )
                    self.peso_bulto[pale] = None
        return True

    def gestionar_confirmacion_final(self):
        """
        Flujo de Cierre:
        1. Selección de Extras (Jaulas/Palés vacíos).
        2. Solicitar Pesos (Opcionales).
        3. Configurar Ruta y Guardar.
        """

        # --- VALIDACIÓN INICIAL ---
        if not self.items_widgets:
            _mensaje_ui(self, "Aviso", "No hay artículos ni bultos en la lista.", "warning")
            return

        # --- PASO 0: SELECCIÓN LOGÍSTICA EXTRA (Puntos 4 y 5) ---
        # Permite añadir Jaulas o Palés vacíos antes de pedir pesos
        self.abrir_seleccion_logistica()

        # --- PASO 1: SOLICITAR PESOS ---
        if not self.solicitar_pesos_pales():
            return

        # --- PASO 2: DIÁLOGO DE CONFIGURACIÓN DE ENVÍO ---
        diag = QDialog(self)
        diag.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        diag.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        diag.setObjectName("dlg_entrada_cantidad")
        diag.setWindowTitle(tr("recep.finalizar_envio_logistico", default="FINALIZAR ENVÍO LOGÍSTICO"))
        diag.setFixedWidth(480)
        _diag_outer = QVBoxLayout(diag)
        _diag_outer.setContentsMargins(0, 0, 0, 0)
        _diag_frame = QFrame()
        _diag_frame.setObjectName("cuerpo_ventana")
        _diag_outer.addWidget(_diag_frame)

        ly = QVBoxLayout(_diag_frame)
        ly.setSpacing(12)
        ly.setContentsMargins(30, 20, 30, 20)

        # ORIGEN (Solo lectura)
        ly.addWidget(QLabel(tr("recep.centro_origen", default="CENTRO ORIGEN")))
        self.combo_origen_diag = QComboBox()
        nombre_origen = getattr(self, "tienda_id_formateado", "ALMC")
        self.combo_origen_diag.addItem(nombre_origen)
        self.combo_origen_diag.setEnabled(False)
        self.combo_origen_diag.setFixedHeight(40)
        ly.addWidget(self.combo_origen_diag)

        # DESTINO
        ly.addWidget(QLabel(tr("recep.centro_destino", default="CENTRO DESTINO")))
        self.combo_destino_diag = QComboBox()
        self.combo_destino_diag.setEditable(True)
        self.combo_destino_diag.setFixedHeight(40)

        try:

            destinos = obtener_destinos_traspaso()
            self.combo_destino_diag.addItems(
                [d for d in destinos if d != nombre_origen]
            )
        except:
            self.combo_destino_diag.addItems(["ALMACEN CENTRAL", "KIK VIC", "KIK TONA"])
        ly.addWidget(self.combo_destino_diag)

        # AGENCIA
        ly.addWidget(QLabel("AGENCIA / TRANSPORTE"))
        self.combo_agencia_diag = QComboBox()
        self.combo_agencia_diag.setEditable(True)
        self.combo_agencia_diag.addItems(["TXERPA LOGÍSTICA", "INTERNO", "DHL", "SEUR"])
        self.combo_agencia_diag.setFixedHeight(40)
        ly.addWidget(self.combo_agencia_diag)

        # OBSERVACIONES
        ly.addWidget(QLabel(tr("recep.observaciones", default="OBSERVACIONES")))
        self.input_obs_diag = QTextEdit()
        self.input_obs_diag.setPlaceholderText(tr("recep.notas_sobre_la_carga", default="Notas sobre la carga..."))
        self.input_obs_diag.setFixedHeight(70)
        ly.addWidget(self.input_obs_diag)

        btn_final = QPushButton(tr("recep.registrar_y_generar_document", default="REGISTRAR Y GENERAR DOCUMENTACIÓN"))
        btn_final.setObjectName("btn_primario")
        btn_final.setFixedHeight(50)
        btn_final.clicked.connect(diag.accept)
        ly.addWidget(btn_final)

        if aplicar_estilo_widget is not None:
            aplicar_estilo_widget(diag)

        # Centrar y habilitar arrastre
        diag.adjustSize()
        _ref = self.window().frameGeometry()
        diag.move(
            _ref.x() + (_ref.width() - diag.width()) // 2,
            _ref.y() + (_ref.height() - diag.height()) // 2,
        )
        _diag_drag: list = [None]

        def _diag_mouse_press(ev):
            if ev.button() == Qt.MouseButton.LeftButton:
                _diag_drag[0] = ev.globalPosition().toPoint() - diag.pos()

        def _diag_mouse_move(ev):
            if ev.buttons() == Qt.MouseButton.LeftButton and _diag_drag[0] is not None:
                diag.move(ev.globalPosition().toPoint() - _diag_drag[0])

        def _diag_mouse_release(ev):
            _diag_drag[0] = None

        diag.mousePressEvent = _diag_mouse_press
        diag.mouseMoveEvent = _diag_mouse_move
        diag.mouseReleaseEvent = _diag_mouse_release

        # --- PROCESAR RESULTADO Y GENERAR PDF ---
        if diag.exec() == QDialog.DialogCode.Accepted:
            self.destino_final = self.combo_destino_diag.currentText().strip().upper()
            self.agencia_final = self.combo_agencia_diag.currentText().strip().upper()
            self.observaciones_final = self.input_obs_diag.toPlainText().strip()

            if self.confirmar_traspaso():
                try:
                    # Mapeo de items para el Worker
                    items_para_worker = []
                    for iw in self.items_widgets:
                        items_para_worker.append(
                            {
                                "codigo": iw["codigo"],
                                "nombre": iw["nombre"],
                                "cantidad": iw["spinbox"].value(),
                                "pale_codigo": iw["pale"]
                                .currentText()
                                .upper()
                                .replace(" ", ""),
                                "es_logistico": iw.get("es_logistico", False),
                            }
                        )

                    # Lanzar el Worker
                    self.pdf_worker.configurar(
                        pale_items=items_para_worker,
                        origen=nombre_origen,
                        destino=self.destino_final,
                        observaciones=self.observaciones_final,
                        agencia_transporte=self.agencia_final,
                        usuario=getattr(self, "nombre_usuario", "Usuario"),
                        id_traspaso=getattr(self, "ultimo_id_doc", "TRA-ERR"),
                        datos_logisticos={"peso_bulto": self.peso_bulto},
                    )
                    self.pdf_worker.run()

                    # Abrir PDFs automáticamente
                    id_doc = getattr(self, "ultimo_id_doc", "")
                    ruta_alb = os.path.join(
                        os.getcwd(), "documentos", "albaranes", f"ALB_{id_doc}.pdf"
                    )
                    if os.path.exists(ruta_alb):
                        os.startfile(ruta_alb)

                    # Abrir etiquetas de palés si se generaron
                    from pathlib import Path as _Path
                    etiq_dir = _Path(os.getcwd()) / "documentos" / "etiquetas_pales"
                    if etiq_dir.exists():
                        etiq_files = sorted(etiq_dir.glob("ETIQ_*.pdf"), key=lambda f: f.stat().st_mtime, reverse=True)
                        if etiq_files:
                            os.startfile(str(etiq_files[0]))

                    _mensaje_ui(
                        self, "Éxito", f"Traspaso {id_doc} finalizado.", "success"
                    )
                    self.accept()

                except Exception as e:
                    _mensaje_ui(self, "Error", f"Error al generar documentos: {e}", "error")

    def abrir_seleccion_logistica(self):
        """Muestra el selector de ítems logísticos y los añade al traspaso."""
        dialogo = SelectorLogisticoExtras(self)

        def al_confirmar(nombres: list):
            for nombre_item in nombres:
                match = next(
                    (s for s in self.opciones_especiales if nombre_item in s), nombre_item
                )
                self.procesar_insercion_item(codigo=match, cantidad=1, es_logistico=True)

        dialogo.items_confirmados.connect(al_confirmar)
        dialogo.exec()

    def confirmar_traspaso(self) -> bool:
        """
        Registra la transacción en MariaDB.
        Maneja pesos opcionales y asegura la integridad referencial.
        """

        try:
            # 1. Recuperar metadatos de la sesión
            origen = str(getattr(self, "tienda_id_formateado", "ALMC"))
            destino = str(getattr(self, "destino_final", "DEST"))
            user_ref = str(getattr(self, "nombre_usuario", "Usuario"))
            agencia = str(getattr(self, "agencia_final", "PROPIA"))
            obs = str(getattr(self, "observaciones_final", ""))

            # Generar ID de documento único (ALMC-DEST-2026-0001)
            id_doc, num_sec, tienda_id, anio = generar_id_traspaso(origen, destino)
            self.ultimo_id_doc = id_doc

            # 2. Agrupar y preparar datos
            info_pales_agrupados = {}
            resumen_txt = []

            for iw in self.items_widgets:
                id_v = iw["pale"].currentText().upper().replace(" ", "").strip()

                if id_v not in info_pales_agrupados:
                    # Recuperar peso (puede ser None o float)
                    peso_p = getattr(self, "peso_bulto", {}).get(id_v)
                    info_pales_agrupados[id_v] = {
                        "id_visual": id_v,
                        "peso": peso_p,
                        "articulos": [],
                    }

                cant = int(iw["spinbox"].value())
                cod = str(iw["codigo"]).strip()
                nom = str(iw["nombre"]).strip()

                info_pales_agrupados[id_v]["articulos"].append(
                    {"codigo": cod, "nombre": nom, "cantidad": cant}
                )
                resumen_txt.append(f"{cant}x {nom}")

            # 3. Operación Atómica en Base de Datos
            with obtener_conexion() as conn:
                with conn.cursor() as cur:
                    # A. Insertar Cabecera
                    sql_cab = """
                        INSERT INTO documentos_logisticos 
                        (id_documento, origen, destino, fecha_envio, estado, usuario_emisor, resumen, agencia, observaciones)
                        VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s, %s)
                    """
                    cur.execute(
                        sql_cab,
                        (
                            id_doc,
                            origen,
                            destino,
                            "EN TRANSITO",
                            user_ref,
                            ", ".join(resumen_txt)[:250],
                            agencia,
                            obs,
                        ),
                    )

                    # B. Insertar Detalles
                    sql_det = """
                        INSERT INTO documentos_logisticos_lineas 
                        (id_documento, id_pale, id_visual, codigo_articulo, nombre_articulo, cantidad_enviada, peso_bulto)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """
                    for id_v, data in info_pales_agrupados.items():
                        # Creamos el ID único del palé (Trazabilidad 360)
                        id_pale_db = f"PAL-{str(tienda_id).zfill(3)}-{str(num_sec).zfill(3)}-{id_v}"

                        for art in data["articulos"]:
                            cur.execute(
                                sql_det,
                                (
                                    id_doc,
                                    id_pale_db,
                                    id_v,
                                    art["codigo"],
                                    art["nombre"],
                                    art["cantidad"],
                                    data["peso"],
                                ),
                            )

                conn.commit()  # Todo o nada
            return True

        except Exception as e:
            print(f"CRITICAL DB ERROR: {e}")
            _mensaje_ui(
                self, "Error de Grabación", f"No se pudo guardar: {str(e)}", "error"
            )
            return False

    def agregar_articulo_manual(self):
        """
        PUNTO 1: Filtro de exclusión y limpieza de sugerencias.
        Evita que el usuario añada palés como productos y elimina radicalmente el autocompletado.
        """

        codigo = self.input_codigo_manual.text().strip().upper()
        if not codigo:
            return

        # FUERZA BRUTA CONTRA EL CUADRO BLANCO
        self.input_codigo_manual.setCompleter(None)  # Desactiva el motor
        self.input_codigo_manual.setAttribute(
            Qt.WidgetAttribute.WA_InputMethodEnabled, False
        )  # Bloquea predicción del SO
        self.input_codigo_manual.clearFocus()  # Rompe el foco actual para resetear el popup
        self.input_codigo_manual.setFocus()  # Devuelve el foco limpio

        try:
            # --- FILTRO DE SEGURIDAD LOGÍSTICA ---
            opciones_log_clean = [
                opt.upper() for opt in getattr(self, "opciones_especiales", [])
            ]

            # Detecta si es un código de transporte (PAL-, JAULA, etc.)
            es_logistico = any(
                opt in codigo for opt in opciones_log_clean
            ) or codigo.startswith("PAL-")

            if es_logistico:
                _mensaje_ui(
                    self,
                    "Uso Incorrecto",
                    f"El código '{codigo}' es un elemento de transporte (Jaula/Palé).\n\n"
                    "Para añadir bultos vacíos, use el botón de 'Validar Artículos' al finalizar.",
                    "warning",
                )
                return

            # --- BÚSQUEDA EN CATÁLOGO COMERCIAL ---
            art = obtener_articulo(codigo)

            if not art:
                _mensaje_ui(
                    self,
                    "No Encontrado",
                    f"El código [{codigo}] no existe en el catálogo comercial.",
                    "error",
                )
                return

            nombre = art.get("descripcion", art.get("nombre", "Artículo"))

            # Buscamos stock en las posibles columnas de la DB
            stock_disp = 0
            for col in ["stock_central", "stock_actual", "Stock_total"]:
                if art.get(col) is not None:
                    stock_disp = int(art[col])
                    break

            # Solicitar cantidad con diálogo personalizado (evita QInputDialog.getInt
            # que causa un bucle de geometría con FramelessWindowHint en Qt/Windows).
            dlg_cant = _EntradaCantidadDialog(
                "Entrada Manual",
                f"Producto: {nombre}\nStock disponible: {stock_disp}\n\nCantidad a traspasar:",
                1, 9999, 1, parent=self,
            )
            if dlg_cant.exec() == QDialog.DialogCode.Accepted:
                self.procesar_insercion_item(
                    codigo, dlg_cant.get_value(), nombre=nombre, es_logistico=False
                )

        except Exception as e:
            print(f"Error al procesar entrada manual: {e}")

        finally:
            # Aseguramos que el campo quede limpio, sin foco de autocompletado y listo para el siguiente
            self.input_codigo_manual.setCompleter(None)  # Doble seguridad
            self.input_codigo_manual.blockSignals(False)
            self.input_codigo_manual.clear()
            self.input_codigo_manual.setFocus()

    def _agregar_item_a_layout(
        self, codigo, nombre, stock_max, value, pale_def, es_logistico
    ):
        """Crea la fila visual con bordes redondeados, sin autocompletado y gestión de eventos limpia."""

        frame = QFrame()
        frame.setObjectName(
            "item_frame_logistico" if es_logistico else "item_frame_articulo"
        )

        ly = QHBoxLayout(frame)
        ly.setContentsMargins(15, 8, 15, 8)

        # 1. Info del Producto
        v_info = QVBoxLayout()
        lbl_cod = QLabel(f"{' [LOG] ' if es_logistico else ''}{codigo}")
        lbl_cod.setObjectName("item_codigo")

        # Truncado de nombre más seguro
        nombre_display = (nombre[:47] + "...") if len(nombre) > 50 else nombre
        lbl_nom = QLabel(nombre_display)
        lbl_nom.setObjectName("item_nombre")

        v_info.addWidget(lbl_cod)
        v_info.addWidget(lbl_nom)
        ly.addLayout(v_info, 4)

        # 2. Selector de Bulto (Mantenemos tu lógica sin completer)
        cb_p = QComboBox()
        _opciones_bulto = getattr(self, "_opciones_pale", None) or (
            [f"PALÉ {i:02d}" for i in range(1, 21)]
            + ["BASE PALÉ", "JAULA REMONTADA", "JAULA CARTÓN", "JAULA PLÁSTICO"]
        )
        cb_p.addItems(_opciones_bulto)
        cb_p.setCompleter(None)
        cb_p.setEditable(False)
        cb_p.setCurrentText(pale_def)
        cb_p.setFixedWidth(175)
        cb_p.setCursor(Qt.CursorShape.PointingHandCursor)
        ly.addWidget(cb_p)

        # 3. Cantidad (SpinBox)
        sp = QSpinBox()
        sp.setRange(1, 9999)
        sp.setValue(value)
        sp.setFixedWidth(75)
        sp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sp.setButtonSymbols(
            QSpinBox.ButtonSymbols.NoButtons
        )  # Opcional: más limpio para PDA
        ly.addWidget(sp)

        # 4. Botón Borrar (Usando clausura de variable explícita)
        btn_del = QPushButton("✕")
        btn_del.setObjectName("btn_icono_peligro")
        btn_del.setFixedSize(32, 32)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)

        # El truco f=frame, c=codigo asegura que la lambda capture los valores actuales de la iteración
        btn_del.clicked.connect(
            lambda checked, f=frame, c=codigo: self.eliminar_widget(f, c)
        )
        ly.addWidget(btn_del)

        # Insertamos al principio para que lo último escaneado aparezca arriba
        self.scroll_layout.insertWidget(0, frame)

        # Registro en la lista de control
        self.items_widgets.append(
            {
                "frame": frame,
                "codigo": codigo,
                "nombre": nombre,
                "spinbox": sp,
                "pale": cb_p,
                "es_logistico": es_logistico,
            }
        )

    def _lanzar_pdf_worker(self, seleccionados, id_traspaso, pesos, datos_maestro=None):
        """Inicia el hilo secundario para generar PDF y etiquetas."""

        # 1. Indicar espera por operación larga usando cursor (sin diálogo modal)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        # 2. Preparación de Metadatos
        if datos_maestro:
            # Flujo de regeneración (datos de base de datos)
            orig = datos_maestro.get("origen", "ALMC")
            dest = datos_maestro.get("destino", "N/D")
            obs = datos_maestro.get("observaciones", "")
            agencia = datos_maestro.get("agencia", "PROPIA")
            user_doc = datos_maestro.get("usuario", "Sistema")
        else:
            # Flujo de Traspaso Nuevo (datos de la UI confirmada)
            orig = str(getattr(self, "tienda_id_formateado", "ALMC"))
            dest = str(getattr(self, "destino_final", "DESTINO"))
            obs = str(getattr(self, "observaciones_final", ""))
            agencia = str(getattr(self, "agencia_final", "PROPIA"))
            user_doc = str(getattr(self, "nombre_usuario", "Usuario"))

        # 3. Inicialización del Worker y el Thread
        self.pdf_thread = QThread()
        self.pdf_worker = PdfWorker(
            pale_items=seleccionados,
            origen=orig,
            destino=dest,
            observaciones=obs,
            agencia_transporte=agencia,
            usuario=user_doc,
            datos_logisticos={"peso_bulto": pesos},
            id_traspaso=str(id_traspaso),
        )

        self.pdf_worker.moveToThread(self.pdf_thread)

        # Conexiones lógicas
        self.pdf_thread.started.connect(self.pdf_worker.run)
        self.pdf_worker.finished.connect(self.pdf_thread.quit)
        self.pdf_worker.finished.connect(self.pdf_worker.deleteLater)
        self.pdf_thread.finished.connect(self.pdf_thread.deleteLater)

        # Conexiones de UI: restaurar cursor al terminar/error
        self.pdf_worker.finished.connect(QApplication.restoreOverrideCursor)
        self.pdf_worker.error.connect(QApplication.restoreOverrideCursor)

        # Callback de éxito/error (asegúrate de tener estos métodos definidos)
        if hasattr(self, "_on_pdf_ok"):
            self.pdf_worker.finished.connect(self._on_pdf_ok)
        if hasattr(self, "_on_pdf_error"):
            self.pdf_worker.error.connect(self._on_pdf_error)

        self.pdf_thread.start()

    def _on_pdf_ok(self, result):
        """Maneja el éxito de la generación del PDF."""
        QApplication.restoreOverrideCursor()

        # Intentamos abrir el PDF generado automáticamente para que el usuario lo imprima
        if result and isinstance(result, str) and os.path.exists(result):

            abrir_pdf(result)

        _mensaje_ui(
            self,
            "Traspaso Exitoso",
            "El registro se ha guardado en la base de datos y la documentación está lista.",
            "success",
        )
        self.accept()

    def _on_pdf_error(self, msg):
        """Maneja fallos en el hilo del PDF sin perder los datos guardados en DB."""
        QApplication.restoreOverrideCursor()

        if hasattr(self, "btn_confirmar"):
            self.btn_confirmar.setEnabled(True)

        _mensaje_ui(
            self,
            "Error de Documentación",
            f"Los datos se guardaron correctamente, pero no se pudo generar el PDF:\n{msg}\n\n"
            "Puede intentar regenerarlo desde el Historial Logístico.",
            "warning",
        )

    def abrir_escaner_camara(self):
        """
        Lanza el diálogo de cámara y procesa el código detectado.
        Optimizado para evitar bloqueos de hardware.
        """

        user_ref = getattr(self, "nombre_usuario", "Operario")

        try:
            # 1. Instanciamos el escáner (Modal)
            escaner = ScannerDialog(usuario=user_ref, parent=self)

            # 2. Si el usuario escanea algo con éxito (self.accept() en ScannerDialog)
            if escaner.exec() == QDialog.DialogCode.Accepted:
                # Recuperamos el código que el diálogo guardó antes de cerrarse
                codigo = getattr(escaner, "codigo_detectado", None)

                if codigo:
                    codigo_limpio = str(codigo).strip().upper()

                    # Insertamos en el campo visual y disparamos la búsqueda
                    self.input_codigo_manual.setText(codigo_limpio)
                    self.agregar_articulo_manual()

                    # Feedback visual en el placeholder por si añade más
                    self.input_codigo_manual.setPlaceholderText(
                        tr("recep.codigo_anadido_escanee_otro", default="Código añadido. Escanee otro...")
                    )
                else:
                    self.input_codigo_manual.setPlaceholderText(
                        tr("recep.no_se_detecto_contenido", default="No se detectó contenido.")
                    )

            # 3. Aseguramos el foco de vuelta al input principal
            self.input_codigo_manual.setFocus()

        except Exception as e:
            print(f"Error crítico en interfaz de cámara: {e}")
            _mensaje_ui(
                self,
                "Fallo de Hardware",
                f"No se pudo inicializar la cámara o el decodificador:\n{str(e)}",
                "error",
            )
            self.input_codigo_manual.setFocus()

    def ejecutar_volver(self):
        """
        Cierra el diálogo de traspaso y vuelve a la pantalla de escaneo.
        Utiliza reject() para notificar la navegación de retorno al controlador principal.
        """

        try:
            # Si hay artículos cargados, prevenimos el cierre accidental
            if hasattr(self, "items_widgets") and self.items_widgets:
                if not _confirmar_ui(
                    self,
                    "Confirmar Salida",
                    "Hay artículos en la lista. ¿Seguro que desea volver?\nLos cambios se perderán.",
                ):
                    return

            # REJECT es la clave: cierra el diálogo y devuelve QDialog.DialogCode.Rejected (0)
            # Esto permite que el controlador de navegación detecte la ruta de retorno.
            self.reject()

        except Exception as e:
            print(f"Error al cerrar diálogo: {e}")
            # Fallback de seguridad en caso de error crítico
            self.reject()


# ============================================================
# BLOQUE TRASPASO DE STOCK
# ============================================================

class TraspasoStockPage(QWidget):

    def __init__(self, usuario=None, codigo_local="ALMC"):
        super().__init__()
        # Punto 3: Unificación de referencia de usuario
        self.usuario = usuario
        self.codigo_local = codigo_local

        # Configuración de interfaz
        self.setup_ui()

    def setup_ui(self):
        """Configura la interfaz visual con el diseño de bienvenida centralizado estilo GitHub Dark."""

        # Layout principal de la página
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.setObjectName("panel_contenido")

        # --- PANEL DE BIENVENIDA ---
        self.vista_inicio = QFrame()
        layout_inicio = QVBoxLayout(self.vista_inicio)
        layout_inicio.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Contenedor Central Estilizado (Siguiendo estilo_global.py)
        container = QFrame()
        container.setObjectName("panel_bienvenida")
        container.setFixedWidth(550)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(40, 40, 40, 40)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.setSpacing(5)

        # Icono, Título e Info
        self.lbl_icono = QLabel("🚚")
        self.lbl_icono.setObjectName("icono_hero")
        self.lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_titulo = QLabel(tr("recep.gestion_de_traspasos", default="GESTIÓN DE TRASPASOS"))
        self.lbl_titulo.setObjectName("titulo_cian")
        self.lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_info = QLabel(
            f"Sede actual: {self.codigo_local}\n\nInicie un nuevo envío de stock entre almacenes."
        )
        self.lbl_info.setObjectName("texto_auxiliar")
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # BOTÓN CRÍTICO: neón + texto e icono centrados (btn_traspaso_land en estilo_global)
        self.btn_lanzar_dialogo = QPushButton(tr("recep.iniciar_traspaso", default="🚀 INICIAR TRASPASO"))
        self.btn_lanzar_dialogo.setObjectName("btn_traspaso_land")
        self.btn_lanzar_dialogo.setFixedSize(320, 60)
        self.btn_lanzar_dialogo.setCursor(Qt.CursorShape.PointingHandCursor)

        # Conexión lógica
        self.btn_lanzar_dialogo.clicked.connect(self.abrir_flujo_traspaso)

        # Montaje de widgets en el contenedor
        container_layout.addWidget(self.lbl_icono)
        container_layout.addWidget(self.lbl_titulo)
        container_layout.addWidget(self.lbl_info)
        container_layout.addSpacing(10)
        container_layout.addWidget(self.btn_lanzar_dialogo)

        layout_inicio.addWidget(container)
        self.main_layout.addWidget(self.vista_inicio)

    def abrir_flujo_traspaso(self):
        """
        Lanza el diálogo de trabajo de traspaso.
        Nota: Este método es llamado si el botón es presionado directamente.
        """
        try:

            # Creamos el diálogo
            # Usamos self.window() para asegurar que el parent sea la ventana principal (RecepcionPaleWindow)
            dialogo = TraspasoDialog(
                usuario=self.usuario, tienda_id=self.codigo_local, parent=self.window()
            )

            # Ejecución modal
            resultado = dialogo.exec()

            if resultado:
                # Si se completó el traspaso, intentamos refrescar el historial
                # buscando la página vecina en el QStackedWidget
                padre = self.parentWidget()  # QStackedWidget
                if padre and hasattr(padre, "widget"):
                    historial = padre.widget(5)  # Índice 5 es HistorialUnificadoPage
                    if hasattr(historial, "cargar_datos"):
                        historial.cargar_datos()

            dialogo.deleteLater()

        except Exception as e:
            import logging

            logging.error(f"Error en TraspasoStockPage: {e}", exc_info=True)

            _mensaje_ui(self, "Error", f"No se pudo iniciar el flujo: {e}", "error")


# ============================================================
# BLOQUE HISTORIAL DE RECEPCIONES
# ============================================================


class HistorialRecepcionesPage(QWidget):

    def __init__(self, codigo_local="ALMC", usuario=None):
        super().__init__()
        self.codigo_local = codigo_local

        # 1. Gestión de identidad de usuario (Punto 3: Normalización)
        if isinstance(usuario, dict):
            self.usuario = usuario.get("nombre", "Usuario")
        else:
            self.usuario = usuario or "Usuario"

        # Mantenemos nombre_usuario por compatibilidad con métodos existentes
        self.nombre_usuario = self.usuario

        self.nivel_actual = 1  # 1: Documentos, 2: Palés, 3: Artículos
        self.filtro_id_documento = None
        self.filtro_id_pale = None

        # 2. UI Initialization
        (
            self.page_widget,
            self.tabla,
            self.input_busqueda,
            self.btn_refresh,
            self.btn_back_level,
        ) = self.setup_ui_historial(
            "Historial de Recepciones",
            "Consulta y trazabilidad de entradas de mercancía",
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.page_widget)

        # 3. Conexiones
        self.btn_refresh.clicked.connect(self.ejecutar_actualizacion)
        self.btn_back_level.clicked.connect(self.retroceder_nivel)
        self.input_busqueda.textChanged.connect(self.cargar_datos)

        self.cargar_datos()

    # MÉTODO 1: Configuración de Interfaz Principal
    def setup_ui_historial(self, titulo_texto, subtitulo_texto):
        page = QWidget()
        page.setObjectName("panel_contenido")
        ly_principal = QVBoxLayout(page)
        ly_principal.setContentsMargins(30, 30, 30, 30)
        ly_principal.setSpacing(25)

        # --- CABECERA ---
        header_layout = QHBoxLayout()
        title_container = QVBoxLayout()

        self.lbl_titulo = QLabel(titulo_texto)
        self.lbl_titulo.setObjectName("titulo_cian")

        lbl_subtitulo = QLabel(subtitulo_texto)
        lbl_subtitulo.setObjectName("subtitulo_muted")

        title_container.addWidget(self.lbl_titulo)
        title_container.addWidget(lbl_subtitulo)

        header_layout.addLayout(title_container)
        header_layout.addStretch()

        # Botón Volver de nivel
        self.btn_back_level = QPushButton(tr("recep.volver", default="⬅ VOLVER"))
        self.btn_back_level.setObjectName("btn_secundario")
        self.btn_back_level.setFixedSize(130, 45)
        self.btn_back_level.setVisible(False)
        self.btn_back_level.setCursor(Qt.CursorShape.PointingHandCursor)

        # BOTÓN ACTUALIZAR: Unificado con el resto del sistema
        btn_refresh = QPushButton(tr("recep.actualizar_11", default="🔄 ACTUALIZAR"))
        btn_refresh.setObjectName("btn_primario")
        btn_refresh.setFixedSize(180, 45)
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)

        header_layout.addWidget(self.btn_back_level)
        header_layout.addSpacing(10)
        header_layout.addWidget(btn_refresh)
        ly_principal.addLayout(header_layout)

        # --- BUSCADOR ---
        search_layout = QHBoxLayout()
        search_layout.setSpacing(10)

        self.input_busqueda = QLineEdit()
        self.input_busqueda.setObjectName("input_buscador")
        self.input_busqueda.setPlaceholderText(
            tr("recep.filtrar_por_id_pale_articulo_2", default="🔍 Filtrar por ID, Palé, Artículo, EAN, Origen o Fecha...")
        )
        self.input_busqueda.setFixedHeight(50)

        self.btn_camara_filtro = QPushButton(tr("recep.scan_3", default="📷 SCAN"))
        self.btn_camara_filtro.setObjectName("btn_secundario")
        self.btn_camara_filtro.setFixedSize(110, 50)
        self.btn_camara_filtro.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_camara_filtro.clicked.connect(self.abrir_camara_filtro)

        search_layout.addWidget(self.input_busqueda)
        search_layout.addWidget(self.btn_camara_filtro)
        ly_principal.addLayout(search_layout)

        # --- TABLA (plantilla visual global reutilizable) ---
        if construir_tabla_estilizada is not None:
            wrap_tabla, self.tabla = construir_tabla_estilizada()
        else:
            wrap_tabla = QFrame()
            wrap_tabla.setObjectName("contenedor_tabla_estandar")
            wrap_layout = QVBoxLayout(wrap_tabla)
            wrap_layout.setContentsMargins(2, 2, 2, 2)
            wrap_layout.setSpacing(0)
            self.tabla = QTableWidget()
            wrap_layout.addWidget(self.tabla)

        header = self.tabla.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # Altura de fila suficiente para que los botones de ACCIONES (32px + glow
        # de neón) no se vean cortados; cada recepción tiene su espacio vital.
        self.tabla.verticalHeader().setDefaultSectionSize(60)
        # Sin padding vertical en las celdas (el global de 8px descentraba los
        # cell widgets hacia abajo); se mantiene el horizontal para el texto.
        self.tabla.setStyleSheet("QTableWidget::item { padding: 0px 8px; }")

        ly_principal.addWidget(wrap_tabla)

        return page, self.tabla, self.input_busqueda, btn_refresh, self.btn_back_level

    # MÉTODO 2: Apertura de Escáner
    def abrir_camara_filtro(self):
        """
        Lanza el escáner de cámara para filtrar el historial mediante códigos de barras o QR.
        """
        # Priorizamos self.usuario (normalizado) sobre self.nombre_usuario
        user_ref = getattr(self, "usuario", getattr(self, "nombre_usuario", "Operario"))

        # Instanciamos el diálogo del escáner (Estilo PDA)
        dialogo = ScannerDialog(parent=self, usuario=user_ref)

        # Si el escaneo es exitoso (Accepted)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            codigo = dialogo.get_codigo()
            if codigo:
                # Limpiamos el código por seguridad y lo aplicamos al filtro
                codigo_limpio = str(codigo).strip()
                self.input_busqueda.setText(codigo_limpio)

                if feedback_lineedit_exito is not None:
                    feedback_lineedit_exito(self.input_busqueda, 1500)

                # Forzamos la recarga de datos con el nuevo filtro
                self.cargar_datos()

    # MÉTODO 3: Gestión de Refresco
    def ejecutar_actualizacion(self):
        """
        Inicia el proceso de recarga de datos con retroalimentación visual inmediata.
        """
        # Deshabilitamos para evitar colisiones de hilos o múltiples clics
        self.btn_refresh.setEnabled(False)

        # Estado visual de carga (Look industrial: fondo oscuro, borde neón)
        self.btn_refresh.setText(tr("recep.cargando_3", default="⌛ CARGANDO..."))

        # Forzamos a Qt a procesar el cambio de estilo antes de la carga pesada
        QApplication.processEvents()

        try:
            # Ejecutamos la lógica de consulta a la base de datos
            self.cargar_datos()
        except Exception as e:
            logging.error(f"Error en recarga de historial: {e}")

        # Pequeño delay de cortesía visual antes de restaurar el botón
        QTimer.singleShot(600, self.restaurar_boton_refresh)

    def restaurar_boton_refresh(self):
        """
        Devuelve el botón de actualización a su estado original neón.
        """
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText(tr("recep.actualizar_12", default="🔄 ACTUALIZAR"))

    # MÉTODO 5: Configuración Tabla Nivel 1 (Documentos)
    # MÉTODO 5: Configuración Tabla Nivel 1 (Documentos de Traspaso)
    def configurar_tabla_nivel_1(self):
        """Prepara la vista principal de documentos de recepción."""
        self.btn_back_level.setVisible(False)
        self.lbl_titulo.setText(tr("recep.historial_de_recepciones", default="Historial de Recepciones"))

        # Estética de cabecera para nivel raíz
        self.tabla.setColumnCount(5)
        self.tabla.setHorizontalHeaderLabels(
            ["ID TRASPASO", "FECHA ENVÍO", "ORIGEN", "ESTADO", "ACCIONES"]
        )

        # Ajuste de ancho específico para acciones
        self.tabla.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Fixed
        )
        self.tabla.setColumnWidth(4, 150)

    # MÉTODO 6: Configuración Tabla Nivel 2 (Palés dentro de un traspaso)
    def configurar_tabla_nivel_2(self):
        """Prepara la vista detallada de palés para un documento específico."""
        self.btn_back_level.setVisible(True)
        # Usamos un color neón para resaltar el ID en el título
        self.lbl_titulo.setText(
            f"Palés en Traspaso: <span style='color:#00FFC6;'>{self.filtro_id_documento}</span>"
        )

        self.tabla.setColumnCount(4)
        self.tabla.setHorizontalHeaderLabels(
            ["CÓDIGO PALÉ", "TIPO / ORIGEN", "FECHA RECEPCIÓN", "ACCIONES"]
        )

        self.tabla.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Fixed
        )
        self.tabla.setColumnWidth(3, 120)

    # MÉTODO 7: Configuración Tabla Nivel 3 (Artículos dentro de un palé)
    def configurar_tabla_nivel_3(self):
        """Prepara la vista final de artículos y cantidades."""
        self.btn_back_level.setVisible(True)
        self.lbl_titulo.setText(
            f"Contenido Palé: <span style='color:#00FFC6;'>{self.filtro_id_pale}</span>"
        )

        self.tabla.setColumnCount(3)
        self.tabla.setHorizontalHeaderLabels(
            ["EAN / CÓDIGO", "DESCRIPCIÓN ARTÍCULO", "CANTIDAD"]
        )

        # En nivel 3, la descripción suele ser larga, le damos prioridad de stretch
        header = self.tabla.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

    # MÉTODO 8: Carga de Datos (Lógica Principal de DB)
    def cargar_datos(self):
        """
        Carga los datos del historial con gestión de niveles y estética GitHub Dark.
        """

        busqueda_texto = self.input_busqueda.text().strip()
        busqueda_param = f"%{busqueda_texto}%"
        local_ref = str(self.codigo_local)

        # 1. Indicar espera por operación larga usando cursor (sin diálogo modal)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        try:

            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    # NIVEL 1: Lista de Documentos
                    if self.nivel_actual == 1:
                        self.configurar_tabla_nivel_1()
                        query = """
                            SELECT id_documento, fecha_envio, origen, estado 
                            FROM documentos_logisticos 
                            WHERE destino = %s 
                              AND (id_documento LIKE %s OR origen LIKE %s OR estado LIKE %s)
                            ORDER BY fecha_envio DESC
                        """
                        cursor.execute(
                            query,
                            (local_ref, busqueda_param, busqueda_param, busqueda_param),
                        )

                    # NIVEL 2: Palés del Documento
                    elif self.nivel_actual == 2:
                        self.configurar_tabla_nivel_2()
                        query = """
                            SELECT DISTINCT d.id_pale, h.origen, h.fecha_envio
                            FROM documentos_logisticos_lineas d
                            JOIN documentos_logisticos h ON d.id_documento = h.id_documento
                            WHERE d.id_documento = %s AND (d.id_pale LIKE %s)
                            ORDER BY d.id_pale ASC
                        """
                        cursor.execute(
                            query, (self.filtro_id_documento, busqueda_param)
                        )

                    # NIVEL 3: Contenido del Palé
                    elif self.nivel_actual == 3:
                        self.configurar_tabla_nivel_3()
                        query = """
                            SELECT codigo_articulo AS codigo, nombre_articulo AS nombre, cantidad_enviada AS cantidad
                            FROM documentos_logisticos_lineas
                            WHERE id_pale = %s AND (nombre_articulo LIKE %s OR codigo_articulo LIKE %s)
                        """
                        cursor.execute(
                            query, (self.filtro_id_pale, busqueda_param, busqueda_param)
                        )

                    # PROCESAMIENTO
                    if cursor.description:
                        columnas = [desc[0] for desc in cursor.description]
                        resultados = [
                            dict(zip(columnas, row, strict=False)) for row in cursor.fetchall()
                        ]
                        self.renderizar_filas(resultados)
                    else:
                        self.tabla.setRowCount(0)

        except Exception as e:
            import logging

            logging.error(f"Error crítico en carga de datos: {e}")
            _mensaje_ui(
                self,
                "Error de Conexión",
                f"No se pudo sincronizar con el servidor.\n\nDetalle: {e}",
                "error",
            )

        finally:
            QApplication.restoreOverrideCursor()

    # MÉTODO 9: Renderizado de Filas con Estilo Semántico
    def renderizar_filas(self, rows):

        self.tabla.setRowCount(0)
        if not rows:
            return
        self.tabla.setRowCount(len(rows))

        for i, row in enumerate(rows):
            if self.nivel_actual == 1:
                vals = [
                    row["id_documento"],
                    str(row["fecha_envio"]),
                    row["origen"],
                    row["estado"].upper(),
                ]
                self.agregar_botones_nivel_1(i, row["id_documento"])
            elif self.nivel_actual == 2:
                vals = [row["id_pale"], row["origen"], str(row["fecha_envio"])]
                self.agregar_botones_nivel_2(i, row["id_pale"])
            else:
                vals = [row["codigo"], row["nombre"], str(row["cantidad"])]

            for j, val in enumerate(vals):
                item = QTableWidgetItem(str(val) if val else "-")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                # --- LÓGICA DE COLORES DE ESTADO (Nivel 1) ---
                if self.nivel_actual == 1 and j == 3:
                    estado = str(val).upper()
                    # Paleta GitHub: Neón (Éxito), Ámbar (Pendiente), Coral (Error)
                    if estado == "RECIBIDO":
                        color = "#00FFC6"
                    elif estado == "PENDIENTE":
                        color = "#F1C40F"
                    elif "ERROR" in estado or "CANCELADO" in estado:
                        color = "#FF6B6B"
                    else:
                        color = "#8B949E"

                    item.setForeground(QColor(color))
                    font = QFont("Segoe UI", 9, QFont.Weight.Bold)
                    item.setFont(font)

                # Colores suaves para códigos en Nivel 2 y 3
                elif j == 0:
                    item.setForeground(QColor("#58A6FF"))  # Azul suave GitHub para IDs

                self.tabla.setItem(i, j, item)

    # MÉTODO 10: Botones Nivel 1 (Ver Palés / PDF)
    # MÉTODO 10: Botones Nivel 1 (Navegación y PDF)
    def agregar_botones_nivel_1(self, fila, id_doc):
        """Inserta botones de visualización y exportación para cada documento."""

        id_doc_str = str(id_doc)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setMinimumHeight(60)  # llenar la fila → no recortar el glow
        lay = QHBoxLayout(container)
        lay.setContentsMargins(5, 4, 5, 4)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Botón para profundizar al Nivel 2 (Palés)
        btn_ver = self.crear_boton_estilizado("🔍 DETALLES", "#21262D", "#00FFC6")
        # Botón para abrir el albarán (PDF)
        btn_pdf = self.crear_boton_estilizado("📄 PDF", "#21262D", "#F0A500")

        # Conexiones con clausura para evitar errores de referencia en bucles
        btn_ver.clicked.connect(lambda: self.ir_a_nivel_2(id_doc_str))
        btn_pdf.clicked.connect(lambda: self.abrir_albaran_existente(id_doc_str))

        lay.addWidget(btn_ver, alignment=Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(btn_pdf, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.tabla.setCellWidget(fila, 4, container)

    # MÉTODO 11: Botones Nivel 2 (Ver Contenido de Palé)
    def agregar_botones_nivel_2(self, fila, id_pale):
        """Inserta botón para ver los artículos dentro de un palé específico."""

        id_pale_str = str(id_pale)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setMinimumHeight(60)  # llenar la fila → no recortar el glow
        lay = QHBoxLayout(container)
        lay.setContentsMargins(5, 4, 5, 4)

        btn_items = self.crear_boton_estilizado(
            "📦 VER CONTENIDO", "#21262D", "#00FFC6"
        )
        btn_items.clicked.connect(lambda: self.ir_a_nivel_3(id_pale_str))

        lay.addWidget(btn_items, alignment=Qt.AlignmentFlag.AlignCenter)
        self.tabla.setCellWidget(fila, 3, container)

    # MÉTODO 12: Generador de Botones Estilizados (GitHub Dark Style)
    def crear_boton_estilizado(self, texto, bg, color_neon):
        """Crea un QPushButton con bordes redondeados y efecto hover industrial."""

        btn = QPushButton(texto)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Altura 44px: el QSS añade 24px de chrome vertical (padding+borde); con
        # 32px el texto quedaba cortado.
        btn.setFixedHeight(44)
        # Hover swap por color: relleno del color del botón + texto oscuro.
        btn.setStyleSheet(
            f"QPushButton{{background:{bg};color:{color_neon};"
            f"border:2px solid {color_neon};border-radius:10px;"
            f"font-family:'Segoe UI';font-weight:700;font-size:12px;padding:0px 14px;}}"
            f"QPushButton:hover{{background:{color_neon};color:#0D1117;}}"
            f"QPushButton:pressed{{background:{color_neon};color:#0D1117;}}"
        )
        return btn

    # MÉTODO 13: Apertura de PDF Albarán
    def abrir_albaran_existente(self, id_documento):
        """Localiza el archivo PDF en el servidor local o lo regenera si falta."""

        nombre_archivo = f"ALB_{id_documento}.pdf"
        ruta_pdf = os.path.abspath(
            os.path.join("documentos", "albaranes", nombre_archivo)
        )

        if os.path.exists(ruta_pdf):
            abrir_pdf(ruta_pdf)
        else:
            # Notificación visual de proceso de reconstrucción
            original_title = self.lbl_titulo.text()
            self.lbl_titulo.setText(tr("recep.reconstruyendo_pdf", default="⌛ RECONSTRUYENDO PDF..."))
            self.lbl_titulo.setProperty("tituloProcesando", True)
            if repolish_widget is not None:
                repolish_widget(self.lbl_titulo)

            # Llamamos a la lógica de generación (proceso pesado)
            QApplication.processEvents()
            self.generar_albaran_recepcion(id_documento)

            def _restaurar_titulo():
                self.lbl_titulo.setText(original_title)
                self.lbl_titulo.setProperty("tituloProcesando", False)
                if repolish_widget is not None:
                    repolish_widget(self.lbl_titulo)

            QTimer.singleShot(2000, _restaurar_titulo)

    # MÉTODO 14: Lógica de Reconstrucción de Albarán (Nube -> PDF)
    def generar_albaran_recepcion(self, id_documento):
        try:

            with obtener_conexion() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT * FROM documentos_logisticos WHERE id_documento = %s",
                        (id_documento,),
                    )
                    maestro = cur.fetchone()
                    cur.execute(
                        "SELECT * FROM documentos_logisticos_lineas WHERE id_documento = %s",
                        (id_documento,),
                    )
                    detalles = cur.fetchall()

            if not maestro or not detalles:
                _mensaje_ui(
                    self, "Error", "No hay datos en la nube para este documento.", "warning"
                )
                return

            items_formateados = []
            pesos_pales = {}
            for d in detalles:
                id_v = (
                    d["id_pale"].split("-")[-1] if "-" in d["id_pale"] else d["id_pale"]
                )
                pesos_pales[id_v] = float(d["peso_bulto"] or 0.0)
                items_formateados.append(
                    {
                        "codigo": d["codigo"],
                        "nombre": d["nombre"],
                        "cantidad": d["cantidad"],
                        "id_visual_pale": id_v,
                    }
                )

            self._lanzar_pdf_worker(
                items_formateados, id_documento, pesos_pales, maestro
            )
        except Exception as e:
            _mensaje_ui(self, "Error", f"Error al procesar: {str(e)}", "error")

    # MÉTODO 15: Lanzador de Worker PDF (Asíncrono)
    def _lanzar_pdf_worker(self, seleccionados, id_traspaso, pesos, datos_maestro):
        # Aquí se instanciaría tu PDFWorker existente

        self.worker = PdfWorker(
            seleccionados,
            id_traspaso,
            pesos,
            self.nombre_usuario,
            datos_maestro,
            is_recepcion=True,
        )
        self.worker.finished.connect(self.on_pdf_recepcion_listo)
        self.worker.start()

    # MÉTODO 16: Callback PDF Listo
    def on_pdf_recepcion_listo(self, resultado):
        ruta_pdf = resultado[0]
        self.restaurar_boton_refresh()
        abrir_pdf(ruta_pdf)

    # MÉTODO 17: Navegación Nivel 2
    # MÉTODO 17: Navegación a Nivel 2 (Vista de Palés)
    def ir_a_nivel_2(self, id_doc):
        """
        Filtra la vista para mostrar exclusivamente los palés asociados
        a un documento de traspaso.
        """
        self.filtro_id_documento = id_doc
        self.nivel_actual = 2

        # Limpiamos el buscador para que el operario pueda buscar palés específicos
        self.input_busqueda.clear()

        # Reiniciamos el scroll al principio de la tabla
        self.tabla.scrollToTop()

        # Recargamos con la configuración de nivel 2
        self.cargar_datos()

    # MÉTODO 18: Navegación a Nivel 3 (Vista de Artículos)
    def ir_a_nivel_3(self, id_pale):
        """
        Filtra la vista para mostrar el contenido detallado (SKUs)
        de un palé seleccionado.
        """
        self.filtro_id_pale = id_pale
        self.nivel_actual = 3

        self.input_busqueda.clear()
        self.tabla.scrollToTop()

        # Recargamos con la configuración de nivel 3
        self.cargar_datos()

    # MÉTODO 19: Lógica de Retroceso (Navegación Breadcrumbs)
    def retroceder_nivel(self):
        """
        Gestiona el retorno a la vista anterior en la jerarquía logística.
        """
        if self.nivel_actual == 3:
            # Si estamos viendo artículos, volvemos a la lista de palés del documento
            self.nivel_actual = 2
            self.filtro_id_pale = None
        elif self.nivel_actual == 2:
            # Si estamos en palés, volvemos al historial general
            self.nivel_actual = 1
            self.filtro_id_documento = None

        # Limpiamos filtros de búsqueda al cambiar de contexto
        self.input_busqueda.clear()

        # Forzamos la actualización de la UI
        self.cargar_datos()

