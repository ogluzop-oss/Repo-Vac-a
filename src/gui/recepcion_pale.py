import os
import sys
import json
import time
import logging
import platform
import subprocess
import traceback
import tempfile
from io import BytesIO
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)
import cv2
import pandas as pd
import qrcode
from PIL import Image as PILImage
from pyzbar import pyzbar
from pyzbar.pyzbar import decode
from barcode import Code128
from barcode.writer import ImageWriter
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QDialog,
    QMainWindow,
    QFrame,
    QStackedWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QFormLayout,
    QScrollArea,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QDateEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QListWidget,
    QGroupBox,
    QMessageBox,
    QFileDialog,
    QInputDialog,
    QProgressDialog,
    QAbstractItemView,
    QGraphicsDropShadowEffect,
    QSizePolicy,
)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    PageTemplate,
    Frame,
    Image,
)
from src.db.conexion import (
    obtener_conexion,
    obtener_articulo,
    obtener_configuracion,
    descontar_stock,
    registrar_pale,
    obtener_destinos_traspaso,
    formatear_nombre_centro,
)
from src.db.logistica import (
    obtener_historial_traspasos,
    obtener_items_pale_traspaso,
    generar_id_traspaso,
    guardar_traspaso_logistico,
)
from src.db.operaciones import guardar_traspaso_db
from reportlab.graphics.barcode import code128
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QUrl, QThread, QDate, QTimer, QEvent
from PyQt6.QtGui import (
    QDesktopServices,
    QFont,
    QColor,
    QImage,
    QPixmap,
    QIcon,
    QRegion,
    QPainterPath,
)

# Clase SidebarButton: garantiza hover-swap mediante eventos de entrada/salida
try:
    from assets.estilo_global import (
        COLOR_FONDO_SIDEBAR,
        COLOR_CIAN,
        COLOR_FONDO_APP,
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
    import os, platform, subprocess

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


# --- CLASE SCANNER (DISEÑO MANTENIDO) ---


class ScannerDialog(QDialog):
    # --- SEÑALES ---
    codigo_leido = pyqtSignal(str)
    confirmar_recepcion = pyqtSignal(str, list)

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Escáner Inteligente - Smart Manager AI")

        # Punto 3 unificado: Usamos self.usuario de forma consistente
        self.usuario = usuario
        self.cap = None
        self.codigo_detectado = None

        if construir_plantilla_camara is not None:
            plantilla = construir_plantilla_camara(
                self,
                titulo="VISIÓN - LOGÍSTICA",
                texto_video="",
                estado_inicial="ALINEE EL CÓDIGO CON EL SENSOR",
                texto_boton_primario="🚀 INICIAR ESCANEO",
                texto_boton_cancelar="ABORTAR OPERACIÓN",
                ancho=650,
                alto=600,
                ancho_video=580,
                alto_video=330,
                mostrar_boton_primario=False,
                object_name_dialog="scanner_dialog",
                object_name_frame="cuerpo_ventana_scan",
            )
            self.main_frame = plantilla["main_frame"]
            self.layout = plantilla["layout"]
            self.lbl_titulo = plantilla["lbl_titulo"]
            self.lbl_video = plantilla["lbl_video"]
            self.lbl_status = plantilla["lbl_status"]
            self.btn_iniciar = plantilla["btn_primario"]
            self.btn_cancelar = plantilla["btn_cancelar"]
            self.lbl_status.setObjectName("lbl_info_scan")
            if aplicar_estilo_widget is not None:
                aplicar_estilo_widget(self.lbl_status)
        else:
            self.setFixedSize(650, 600)
            self.setObjectName("scanner_dialog")
            self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.main_frame = QFrame(self)
            self.main_frame.setObjectName("cuerpo_ventana_scan")
            self.main_frame.setGeometry(0, 0, 650, 600)
            self.layout = QVBoxLayout(self.main_frame)
            self.layout.setContentsMargins(30, 30, 30, 30)
            self.layout.setSpacing(15)
            self.lbl_titulo = QLabel("VISIÓN - LOGÍSTICA")
            self.lbl_titulo.setObjectName("titulo_scan")
            self.lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout.addWidget(self.lbl_titulo)
            self.lbl_video = QLabel("")
            self.lbl_video.setObjectName("feed_video")
            self.lbl_video.setProperty("activo", False)
            self.lbl_video.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl_video.setFixedSize(580, 330)
            self.layout.addWidget(self.lbl_video, alignment=Qt.AlignmentFlag.AlignCenter)
            self.lbl_status = QLabel("ALINEE EL CÓDIGO CON EL SENSOR")
            self.lbl_status.setObjectName("lbl_info_scan")
            self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout.addWidget(self.lbl_status)
            self.btn_iniciar = QPushButton("🚀 INICIAR ESCANEO")
            self.btn_iniciar.setObjectName("btn_primario")
            self.btn_iniciar.setFixedHeight(55)
            self.btn_iniciar.setVisible(False)
            self.layout.addWidget(self.btn_iniciar)
            self.btn_cancelar = QPushButton("ABORTAR OPERACIÓN")
            self.btn_cancelar.setObjectName("btn_abortar_scan")
            self.btn_cancelar.setFixedHeight(45)
            self.layout.addWidget(self.btn_cancelar)

        self.btn_iniciar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_iniciar.clicked.connect(self.inicializar_hardware_camara)
        self.btn_cancelar.clicked.connect(self.reject)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        QTimer.singleShot(0, self.inicializar_hardware_camara)

    def aplicar_mascara_redondeada(self):
        """Crea una máscara para que el video respete los bordes redondeados del label."""
        path = QPainterPath()
        # Definimos un rectángulo ligeramente menor al label para que no pise el borde neón
        rect = self.lbl_video.rect()
        path.addRoundedRect(
            float(rect.x()),
            float(rect.y()),
            float(rect.width()),
            float(rect.height()),
            20,
            20,
        )
        region = QRegion(path.toFillPolygon().toPolygon())
        self.lbl_video.setMask(region)

    def inicializar_hardware_camara(self):
        self.btn_iniciar.setEnabled(False)
        self.btn_iniciar.setText(
            "⌛ CONECTANDO..."
        )  # Cambiado para mostrar el estado de conexión
        QApplication.processEvents()

        self.liberar_recursos()
        # Priorizamos DirectShow para rapidez en Windows
        backends = [cv2.CAP_DSHOW, cv2.CAP_ANY]
        camara_encontrada = False

        for backend in backends:
            for index in [0, 1]:
                self.cap = cv2.VideoCapture(index, backend)
                if self.cap.isOpened():
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    camara_encontrada = True
                    break
            if camara_encontrada:
                break

        if camara_encontrada:
            self.lbl_video.setProperty("activo", True)
            if aplicar_estilo_widget is not None:
                aplicar_estilo_widget(self.lbl_video)
            # Aplicamos la máscara justo después de que la cámara se activa
            self.aplicar_mascara_redondeada()
            self.lbl_status.setText("ALINEE EL CÓDIGO CON EL SENSOR")
            self.btn_iniciar.hide()
            self.timer.start(30)
        else:
            self.mostrar_error_camara()
            self.btn_iniciar.setEnabled(True)
            self.btn_iniciar.setText("🚀 REINTENTAR INICIO")
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

            # Renderizado en el QLabel con escalado suave
            rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w
            qt_image = QImage(
                rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888
            )

            pixmap = QPixmap.fromImage(qt_image).scaled(
                self.lbl_video.width(),
                self.lbl_video.height(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.lbl_video.setPixmap(pixmap)

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
                self.lbl_status.setText("PALÉ SIN STOCK O NO EXISTE")
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
        self.lbl_video.setText("ERROR DE HARDWARE\n\nCámara ocupada o no detectada")
        self.lbl_video.setProperty("activo", False)
        self.lbl_status.setText("ERROR DE HARDWARE")
        if aplicar_estilo_widget is not None:
            aplicar_estilo_widget(self.lbl_video)

    def liberar_recursos(self):
        self.timer.stop()
        if self.cap:
            self.cap.release()
            self.cap = None


class SelectorLogisticoExtras(QDialog):
    """Ventana emergente con botones grandes para añadir bultos vacíos o jaulas."""

    item_seleccionado = pyqtSignal(str)  # Devuelve el nombre del ítem

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Añadir Equipamiento Logístico")
        self.setObjectName("scanner_dialog")
        self.setFixedSize(
            500, 450
        )  # Incrementado ligeramente para mejor aire entre elementos
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )  # Para permitir bordes redondeados limpios

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)

        body = QFrame()
        body.setObjectName("panel_dialogo_logistico")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(25, 25, 25, 25)
        body_layout.setSpacing(15)
        layout.addWidget(body)

        titulo = QLabel("¿Añadir bulto extra al traspaso?")
        titulo.setObjectName("titulo_cian")
        body_layout.addWidget(
            titulo,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )

        grid = QGridLayout()
        grid.setSpacing(10)

        # Definimos los botones basados en tus 'opciones_especiales'
        botones = [
            ("PALÉ VACÍO", "📦"),
            ("JAULA METÁLICA", "⛓️"),
            ("PALÉ PLÁSTICO", "🟦"),
            ("PALÉ CARTÓN", "📝"),
            ("CONTENEDOR", "🗑️"),
            ("PALÉ REMONTADO", "🔝"),
        ]

        row, col = 0, 0
        for nombre, icono in botones:
            btn = QPushButton(f"{icono}\n{nombre}")
            btn.setObjectName("btn_secundario")
            btn.setFixedSize(140, 90)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            # Mantenemos tu lógica de conexión original
            btn.clicked.connect(lambda checked, n=nombre: self.finalizar(n))
            grid.addWidget(btn, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1

        body_layout.addLayout(grid)

        btn_cancelar = QPushButton("CANCELAR / FINALIZAR")
        btn_cancelar.setObjectName("btn_peligro")
        btn_cancelar.setFixedHeight(45)
        btn_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancelar.clicked.connect(self.reject)
        body_layout.addWidget(btn_cancelar)

    def finalizar(self, nombre):
        self.item_seleccionado.emit(nombre)
        self.accept()


# --- CLASE MAESTRA RECEPCIÓN (DEFINTIVA) ---


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
        """Ejecuta el proceso de generación en el hilo secundario."""
        if self._pdf_generado:
            return
        self._pdf_generado = True

        try:
            import os

            terminos = self._get_terminos()

            # 1. Estructura de carpetas
            base_path = os.path.abspath(os.getcwd())
            folder_pdf = os.path.join(base_path, "documentos", "albaranes")
            os.makedirs(folder_pdf, exist_ok=True)

            folder_etiquetas = os.path.join(base_path, "documentos", "etiquetas_pales")
            os.makedirs(folder_etiquetas, exist_ok=True)

            # 2. Construir data agrupada
            data = self._construir_data_agrupada()

            # 3. Generación del Albarán
            # Pasamos 'data' directamente como 'traspaso_data'
            ruta_albaran = self.generar_pdf_traspaso(traspaso_data=data)

            # 4. Generación de Etiquetas (Solo en Traspasos)
            rutas_etiquetas = []
            if self.tipo_operacion == "traspaso":
                # Enviamos la lista completa de pales procesados en data['pales']
                ruta_etq = self.generar_etiqueta_pdf(
                    lista_pales=data["pales"],
                    origen=self.origen,
                    destino=self.destino,
                    secuencial_traspaso=self.id_traspaso,
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
                Paragraph("<b>Smart Manager AI</b>", styles["Heading1"]),
                "",
                Image(qr_path, 20 * mm, 20 * mm),
            ]
        ]
        head_tab = Table(head_data, colWidths=[10 * cm, 4 * cm, 5 * cm])
        story.append(head_tab)
        story.append(Spacer(1, 10))

        # --- TABLA DE CONTENIDO ---
        data_table = [
            [
                Paragraph("<b>PALÉ</b>", style_b),
                Paragraph("<b>CÓDIGO</b>", style_b),
                Paragraph("<b>ARTÍCULO</b>", style_b),
                Paragraph("<b>UDS</b>", style_b),
            ]
        ]

        for p in traspaso_data.get("pales", []):
            arts = p.get("articulos", [])
            peso_val = p.get("peso_pale")
            texto_peso = f"{peso_val} KG" if peso_val is not None else "_______ KG"

            for i, a in enumerate(arts):
                # Punto 4: Resaltado de Jaulas y Logística
                nombre = a.get("nombre", "")
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
                    Paragraph("<b>Peso declarado:</b>", style_n),
                    Paragraph(f"<b>{texto_peso}</b>", style_n),
                ]
            )
            data_table.append(
                [
                    "",
                    "",
                    Paragraph("Total unidades bulto:", style_n),
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
                "SISTEMA LOGÍSTICO - 360 SMART MANAGER",
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

        self.lbl_titulo = QLabel("CENTRO DE RECEPCIÓN LOGÍSTICA")
        self.lbl_titulo.setObjectName("titulo_cian")
        self.lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_info = QLabel(
            "Presione el botón para abrir el escáner y\nvalidar la entrada de palés o artículos."
        )
        self.lbl_info.setObjectName("texto_auxiliar")
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Botón Central de Acción (Estilo Global Neón)
        self.btn_iniciar = QPushButton("🚀  INICIAR ESCANEO")
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

        # Contenedor del Feed de Vídeo
        self.lbl_video = QLabel("Iniciando cámara...")
        self.lbl_video.setObjectName("feed_video")
        self.lbl_video.setProperty("activo", True)
        self.lbl_video.setFixedSize(640, 480)
        self.lbl_video.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Input Manual (Debajo de la cámara, como en tus capturas)
        self.input_manual = QLineEdit()
        self.input_manual.setObjectName("input_buscador")
        self.input_manual.setPlaceholderText(
            "O escriba el código manualmente y pulse Enter..."
        )
        self.input_manual.setFixedHeight(45)
        self.input_manual.returnPressed.connect(self.procesar_entrada_manual)

        # Botón Volver/Cancelar
        self.btn_cancelar_cam = QPushButton("⬅ CANCELAR Y VOLVER")
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
                A4[0] / 2, 1.2 * cm, "360 SMART MANAGER - SISTEMA DE GESTIÓN LOGÍSTICA"
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

        title = QLabel("Historial de Traspasos")
        title.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
        title.setObjectName("titulo_cian")

        subtitle = QLabel("Consulta, trazabilidad y gestión de envíos realizados.")
        subtitle.setObjectName("subtitulo_muted")

        title_container.addWidget(title)
        title_container.addWidget(subtitle)

        # Punto 4: Unificado a self.btn_actualizar con estilo corporativo
        self.btn_actualizar = QPushButton("🔄 ACTUALIZAR")
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
            "🔍 Filtrar por ID, Palé, Artículo, EAN, Destino o Fecha..."
        )
        self.input_busqueda.setFixedHeight(50)

        # ELIMINAR SUGERENCIAS LOGÍSTICAS (QCompleter)
        self.input_busqueda.setCompleter(None)

        self.input_busqueda.textChanged.connect(self.cargar_datos)

        self.btn_camara = QPushButton("📷 SCAN")
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
        columnas = ["ID TRASPASO", "FECHA / HORA", "DESTINO", "ESTADO", "ACCIONES"]
        self.tabla.setColumnCount(len(columnas))
        self.tabla.setHorizontalHeaderLabels(columnas)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setShowGrid(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.tabla.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

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
                    rows = [dict(zip(columnas, row)) for row in cur.fetchall()]

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
        btn = QPushButton("📄 VER ALBARÁN")
        btn.setObjectName("btn_secundario")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(130, 32)
        btn.clicked.connect(lambda: self.ver_pdf(id_doc))

        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(btn)
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

            self.btn_actualizar.setText("⏳ Generando...")
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
        self.btn_actualizar.setText("⌛ CARGANDO...")
        QApplication.processEvents()
        QTimer.singleShot(300, self.finalizar_carga)

    def finalizar_carga(self):
        self.cargar_datos()
        self.btn_actualizar.setEnabled(True)
        self.btn_actualizar.setText("🔄 ACTUALIZAR")


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
        self.lbl_info = QLabel("RECEPCIÓN DE MERCANCÍA")
        self.lbl_info.setObjectName("titulo_cian")
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Botón Central - Estilo Global Neón
        self.btn_iniciar = QPushButton("🚀  ABRIR ESCÁNER DE ENTRADA")
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
            f"Smart Manager AI - Gestión Logística [{self.codigo_local}]"
        )
        self.setMinimumSize(1200, 800)

        # Atributo crítico para la limpieza de memoria
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

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

        lbl_m = QLabel("OPERACIONES")
        lbl_m.setObjectName("sidebar_title")
        side_ly.addWidget(lbl_m)

        # Botones de navegación
        self.btn_nav_scan = self.crear_boton_nav("Scanner Entrada", True)
        self.btn_nav_traspasar = self.crear_boton_nav("Nuevo Traspaso")
        self.btn_nav_hist_trasp = self.crear_boton_nav("Historial Traspasos")
        self.btn_nav_hist_recep = self.crear_boton_nav("Historial Recepción")

        self.lista_botones_nav = [
            self.btn_nav_scan,
            self.btn_nav_traspasar,
            self.btn_nav_hist_trasp,
            self.btn_nav_hist_recep,
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

        # --- ÁREA DE CONTENIDO (QStackedWidget) ---
        self.vistas = QStackedWidget()
        self.vistas.setObjectName("contenido_logistica")

        self.vista_landing_scanner = LandingScannerPage()
        self.vista_traspaso = TraspasoStockPage(
            usuario=self.usuario, codigo_local=self.codigo_local
        )
        self.vista_hist_trasp = HistorialTraspasosPage(
            usuario=self.usuario, codigo_local=self.codigo_local
        )
        self.vista_hist_recep = HistorialRecepcionesPage(
            usuario=self.usuario, codigo_local=self.codigo_local
        )

        self.vistas.addWidget(self.vista_landing_scanner)  # Index 0
        self.vistas.addWidget(self.vista_traspaso)  # Index 1
        self.vistas.addWidget(self.vista_hist_trasp)  # Index 2
        self.vistas.addWidget(self.vista_hist_recep)  # Index 3

        self.main_layout.addWidget(self.vistas)


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
        # 1. Botones de la Sidebar (Navegación)
        # Para los botones de navegación no solemos desconectar porque se definen una vez en setup_ui
        self.btn_nav_scan.clicked.connect(
            lambda: self.cambiar_vista(0, self.btn_nav_scan)
        )
        self.btn_nav_traspasar.clicked.connect(
            lambda: self.cambiar_vista(1, self.btn_nav_traspasar)
        )
        self.btn_nav_hist_trasp.clicked.connect(
            lambda: self.cambiar_vista(2, self.btn_nav_hist_trasp)
        )
        self.btn_nav_hist_recep.clicked.connect(
            lambda: self.cambiar_vista(3, self.btn_nav_hist_recep)
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

        # 3. PUENTE CRÍTICO: Solución al error de la "Ventana Doble"
        # Forzamos la desconexión antes de conectar para asegurar que solo exista UN vínculo activo.
        if hasattr(self.vista_traspaso, "btn_lanzar_dialogo"):
            try:
                # Si el botón ya tenía una función conectada, la eliminamos
                self.vista_traspaso.btn_lanzar_dialogo.clicked.disconnect()
            except (TypeError, RuntimeError):
                # Si no había conexión previa, Qt lanza un error que ignoramos
                pass

            # Conectamos de forma limpia
            self.vista_traspaso.btn_lanzar_dialogo.clicked.connect(
                self.abrir_dialogo_traspaso_final
            )

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
                # Si el diálogo terminó en éxito, refrescamos el historial
                if hasattr(self.vista_hist_trasp, "cargar_datos"):
                    self.vista_hist_trasp.cargar_datos()

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
        # 1. Cambiar el índice del StackedWidget
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
                    registro = dict(zip(cols, r))
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

            # 5. FEEDBACK FINAL
            resumen = f"Stock actualizado: {count_actualizados} productos."
            if articulos_no_encontrados:
                resumen += f"\n\nAtención: {len(articulos_no_encontrados)} códigos no existen en la base de datos."

            _mensaje_ui(self, "Recepción Exitosa", resumen, "success")

            # Si hay artículos nuevos, abrir diálogo de creación rápida
            if articulos_no_encontrados:

                dialogo = DialogoNuevosArticulos(articulos_no_encontrados, self)
                dialogo.exec()

            # Redirigir automáticamente al Historial de Entradas (Vista Index 3)
            self.cambiar_vista(3, self.btn_nav_hist_recep)

        except Exception as e:
            _mensaje_ui(
                self, "Error de Base de Datos", f"Fallo crítico: {str(e)}", "error"
            )


class DialogoNuevosArticulos(QDialog):

    def __init__(self, items_nuevos, parent=None):
        """
        items_nuevos: Lista de diccionarios [{'ean':..., 'nombre':..., 'cantidad':...}]
        """
        super().__init__(parent)
        self.items_nuevos = items_nuevos

        self.setWindowTitle("Gestión de Artículos Nuevos")
        self.setMinimumSize(700, 500)  # Ligeramente más grande para comodidad visual
        self.setObjectName("panel_contenido")

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)

        # Encabezado informativo con acento neón
        lbl = QLabel("⚠️ Se han detectado códigos EAN no registrados")
        lbl.setObjectName("titulo_cian")
        layout.addWidget(lbl)

        sub_lbl = QLabel(
            "Los artículos listados a continuación se darán de alta con stock inicial."
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

        self.btn_cancelar = QPushButton("❌ Cancelar Registro")
        self.btn_cancelar.setObjectName("btn_peligro")
        self.btn_cancelar.setFixedHeight(45)
        self.btn_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancelar.clicked.connect(self.reject)

        self.btn_confirmar = QPushButton("✅ Registrar y Finalizar")
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


# --- ARCHIVO: src/gui/recepcion_pale.py ---
# --- CLASE PRINCIPAL: RecepcionPaleWindow ---


class TraspasoDialog(QDialog):

    def __init__(
        self,
        usuario=None,
        tipo: str = "enviar",
        codigo_local="ALMC",
        payload_items: Optional[List[dict]] = None,
        pale_codigo: Optional[str] = None,
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
        self.items_widgets: List[dict] = []
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
        lbl_titulo = QLabel("SALIDA LOGÍSTICA")
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
            "Escanee EAN o Código de Artículo..."
        )
        self.input_codigo_manual.setFixedHeight(55)
        self.input_codigo_manual.setCompleter(None)  # Blindaje
        self.input_codigo_manual.returnPressed.connect(self.agregar_articulo_manual)

        btn_cam = QPushButton("📷")
        btn_cam.setObjectName("btn_icono")
        btn_cam.setFixedSize(55, 55)
        btn_cam.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cam.clicked.connect(lambda: self.abrir_escaner_camara())

        self.btn_add_manual = QPushButton("AÑADIR")
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

        self.global_pale_selector = QComboBox()
        self.global_pale_selector.addItems(
            ["Palé Logístico"] + [f"Palé {i:02d}" for i in range(1, 21)]
        )
        self.global_pale_selector.setFixedSize(220, 40)

        lbl_cargar = QLabel("CARGAR EN:")
        lbl_cargar.setObjectName("etiqueta_secundaria")

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
        self.btn_confirmar = QPushButton("PASO 1: VALIDAR ARTÍCULOS")
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
        pale_actual = "PALÉ 1"
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
        self.input_codigo_manual.setPlaceholderText("Listo para siguiente escaneo...")

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
                self.btn_confirmar.setText("PASO 1: VALIDAR ARTÍCULOS")
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

            input_dialog = QInputDialog(self)
            input_dialog.setWindowTitle(f"PESAJE: {pale}")
            input_dialog.setLabelText(
                f"Peso para {tipo_bulto} {pale}\n(Dejar vacío si no se puede pesar ahora):"
            )
            input_dialog.setTextValue("")  # Vacío por defecto

            if aplicar_estilo_widget is not None:
                aplicar_estilo_widget(input_dialog)

            ok = input_dialog.exec()
            peso_str = input_dialog.textValue().strip()

            if ok:
                if not peso_str:
                    # Si el operario no pone nada, guardamos None para imprimir "___ KG"
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
            else:
                return False  # El usuario canceló el proceso completo
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
        diag.setObjectName("panel_dialogo_logistico")
        diag.setWindowTitle("FINALIZAR ENVÍO LOGÍSTICO")
        diag.setFixedWidth(450)

        ly = QVBoxLayout(diag)
        ly.setSpacing(12)
        ly.setContentsMargins(30, 20, 30, 20)

        # ORIGEN (Solo lectura)
        ly.addWidget(QLabel("CENTRO ORIGEN"))
        self.combo_origen_diag = QComboBox()
        nombre_origen = getattr(self, "tienda_id_formateado", "ALMC")
        self.combo_origen_diag.addItem(nombre_origen)
        self.combo_origen_diag.setEnabled(False)
        self.combo_origen_diag.setFixedHeight(40)
        ly.addWidget(self.combo_origen_diag)

        # DESTINO
        ly.addWidget(QLabel("CENTRO DESTINO"))
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
        ly.addWidget(QLabel("OBSERVACIONES"))
        self.input_obs_diag = QTextEdit()
        self.input_obs_diag.setPlaceholderText("Notas sobre la carga...")
        self.input_obs_diag.setFixedHeight(70)
        ly.addWidget(self.input_obs_diag)

        btn_final = QPushButton("REGISTRAR Y GENERAR DOCUMENTACIÓN")
        btn_final.setObjectName("btn_primario")
        btn_final.setFixedHeight(50)
        btn_final.clicked.connect(diag.accept)
        ly.addWidget(btn_final)

        if aplicar_estilo_widget is not None:
            aplicar_estilo_widget(diag)

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

                    # Abrir PDF automáticamente
                    id_doc = getattr(self, "ultimo_id_doc", "")
                    ruta_alb = os.path.join(
                        os.getcwd(), "documentos", "albaranes", f"ALB_{id_doc}.pdf"
                    )
                    if os.path.exists(ruta_alb):
                        os.startfile(ruta_alb)

                    _mensaje_ui(
                        self, "Éxito", f"Traspaso {id_doc} finalizado.", "success"
                    )
                    self.accept()

                except Exception as e:
                    _mensaje_ui(self, "Error", f"Error al generar documentos: {e}", "error")

    def abrir_seleccion_logistica(self):
        """Muestra el selector de ítems logísticos y los añade al traspaso."""
        dialogo = SelectorLogisticoExtras(self)

        # Conectamos la señal para procesar la selección
        def al_seleccionar(nombre_item):
            # Simulamos un "escaneo" de este item especial
            # Buscamos el nombre completo en nuestras opciones_especiales
            match = next(
                (s for s in self.opciones_especiales if nombre_item in s), nombre_item
            )

            # Lo añadimos directamente como un item logístico
            self.procesar_insercion_item(codigo=match, cantidad=1, es_logistico=True)
            # Opcional: Mostrar un aviso de que se ha añadido
            print(f"Logística: {match} añadido al traspaso.")

        dialogo.item_seleccionado.connect(al_seleccionar)
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

            # Solicitar cantidad con UI intuitiva
            cant, ok = QInputDialog.getInt(
                self,
                "Entrada Manual",
                f"Producto: {nombre}\nStock disponible: {stock_disp}\n\nCantidad a traspasar:",
                1,
                1,
                9999,
            )

            if ok:
                self.procesar_insercion_item(
                    codigo, cant, nombre=nombre, es_logistico=False
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
        opciones_bulto = (
            ["CAJA LOG."]
            + [f"PALÉ {i:02}" for i in range(1, 21)]
            + ["JAULA 01", "JAULA 02"]
        )
        cb_p.addItems(opciones_bulto)
        cb_p.setCompleter(None)
        cb_p.setEditable(False)
        cb_p.setCurrentText(pale_def)
        cb_p.setFixedWidth(135)
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
                        "Código añadido. Escanee otro..."
                    )
                else:
                    self.input_codigo_manual.setPlaceholderText(
                        "No se detectó contenido."
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

        self.lbl_titulo = QLabel("GESTIÓN DE TRASPASOS")
        self.lbl_titulo.setObjectName("titulo_cian")
        self.lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_info = QLabel(
            f"Sede actual: {self.codigo_local}\n\nInicie un nuevo envío de stock entre almacenes."
        )
        self.lbl_info.setObjectName("texto_auxiliar")
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # BOTÓN CRÍTICO: neón + texto e icono centrados (btn_traspaso_land en estilo_global)
        self.btn_lanzar_dialogo = QPushButton("🚀 INICIAR TRASPASO")
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
                    historial = padre.widget(
                        2
                    )  # Índice 2 es HistorialTraspasosPage según tu setup
                    if hasattr(historial, "cargar_datos"):
                        historial.cargar_datos()

            dialogo.deleteLater()

        except Exception as e:
            import logging

            logging.error(f"Error en TraspasoStockPage: {e}", exc_info=True)

            _mensaje_ui(self, "Error", f"No se pudo iniciar el flujo: {e}", "error")


# --- ARCHIVO: src/gui/recepcion_pale.py ---
# --- BLOQUE: CLASE HistorialRecepcionesPage ---


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
        self.btn_back_level = QPushButton("⬅ VOLVER")
        self.btn_back_level.setObjectName("btn_secundario")
        self.btn_back_level.setFixedSize(130, 45)
        self.btn_back_level.setVisible(False)
        self.btn_back_level.setCursor(Qt.CursorShape.PointingHandCursor)

        # BOTÓN ACTUALIZAR: Unificado con el resto del sistema
        btn_refresh = QPushButton("🔄 ACTUALIZAR")
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
            "🔍 Filtrar por ID, Palé, Artículo, EAN, Origen o Fecha..."
        )
        self.input_busqueda.setFixedHeight(50)

        self.btn_camara_filtro = QPushButton("📷 SCAN")
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
        self.btn_refresh.setText("⌛ CARGANDO...")

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
        self.btn_refresh.setText("🔄 ACTUALIZAR")

    # MÉTODO 5: Configuración Tabla Nivel 1 (Documentos)
    # MÉTODO 5: Configuración Tabla Nivel 1 (Documentos de Traspaso)
    def configurar_tabla_nivel_1(self):
        """Prepara la vista principal de documentos de recepción."""
        self.btn_back_level.setVisible(False)
        self.lbl_titulo.setText("Historial de Recepciones")

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
                            dict(zip(columnas, row)) for row in cursor.fetchall()
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
        lay = QHBoxLayout(container)
        lay.setContentsMargins(5, 4, 5, 4)
        lay.setSpacing(8)

        # Botón para profundizar al Nivel 2 (Palés)
        btn_ver = self.crear_boton_estilizado("🔍 DETALLES", "#21262D", "#00FFC6")
        # Botón para abrir el albarán (PDF)
        btn_pdf = self.crear_boton_estilizado("📄 PDF", "#21262D", "#F0A500")

        # Conexiones con clausura para evitar errores de referencia en bucles
        btn_ver.clicked.connect(lambda: self.ir_a_nivel_2(id_doc_str))
        btn_pdf.clicked.connect(lambda: self.abrir_albaran_existente(id_doc_str))

        lay.addWidget(btn_ver)
        lay.addWidget(btn_pdf)
        self.tabla.setCellWidget(fila, 4, container)

    # MÉTODO 11: Botones Nivel 2 (Ver Contenido de Palé)
    def agregar_botones_nivel_2(self, fila, id_pale):
        """Inserta botón para ver los artículos dentro de un palé específico."""

        id_pale_str = str(id_pale)
        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(5, 4, 5, 4)

        btn_items = self.crear_boton_estilizado(
            "📦 VER CONTENIDO", "#21262D", "#00FFC6"
        )
        btn_items.clicked.connect(lambda: self.ir_a_nivel_3(id_pale_str))

        lay.addWidget(btn_items)
        self.tabla.setCellWidget(fila, 3, container)

    # MÉTODO 12: Generador de Botones Estilizados (GitHub Dark Style)
    def crear_boton_estilizado(self, texto, bg, color_neon):
        """Crea un QPushButton con bordes redondeados y efecto hover industrial."""

        btn = QPushButton(texto)
        btn.setObjectName("btn_secundario")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(32)
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
            self.lbl_titulo.setText("⌛ RECONSTRUYENDO PDF...")
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

