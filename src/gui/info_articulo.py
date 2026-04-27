import os
import sqlite3
import cv2
from pyzbar.pyzbar import decode
import numpy as np
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QMessageBox,
    QFormLayout,
    QGraphicsDropShadowEffect,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QScrollArea,
    QDialog,
)
from PyQt6.QtGui import QFont, QColor, QPixmap, QImage, QGuiApplication
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer

from src.db.conexion import ventas_semana
from src.db.conexion import stock_signals as global_stock_signals

# ---------------------------
# VideoThread.py
# ---------------------------
import cv2
import os
from pyzbar.pyzbar import decode
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage


class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(QImage)
    code_detected = pyqtSignal(str, object)  # emitimos código y tipo

    def __init__(self, camera_index=0, parent=None):
        super().__init__(parent)
        self._run_flag = True
        self.camera_index = camera_index

    def preprocesar_frame(self, frame):
        """Convierte a gris, ecualiza histograma y binariza adaptativamente"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        eq = cv2.equalizeHist(gray)
        binarizado = cv2.adaptiveThreshold(
            eq, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 25, 10
        )
        return binarizado

    def try_decode(self, frame):
        """Intenta decodificar con rotaciones clásicas y ±10° y devuelve tipo de código"""
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
                self.code_detected.emit(text, tipo)  # emitimos código y tipo

            rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            qt_image = QImage(rgb_image.data, w, h, ch * w, QImage.Format.Format_RGB888)
            self.change_pixmap_signal.emit(qt_image)

        cap.release()

    def stop(self):
        self._run_flag = False
        self.wait(timeout=2000)


# ---------------------------
# BarcodeScanner.py
# ---------------------------
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtCore import QUrl
import os

try:
    from assets.estilo_global import aplicar_estilo_widget, construir_plantilla_camara
except Exception:
    aplicar_estilo_widget = None
    construir_plantilla_camara = None


class BarcodeScanner(QDialog):
    """
    Ventana que muestra la cámara y detecta códigos 360°.
    Mensaje temporal de error "código no válido" sin bloquear la cámara.
    """

    def __init__(self, callback, camera_index=0, parent=None):
        super().__init__(parent)
        self.callback = callback
        self._codigo_presente = False  # activa solo si hay código frente a la cámara
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        if construir_plantilla_camara is not None:
            plantilla = construir_plantilla_camara(
                self,
                titulo="VISIÓN - ARTÍCULO",
                texto_video="",
                estado_inicial="ALINEE EL CÓDIGO CON EL SENSOR",
                texto_boton_primario="INICIAR ESCANEO",
                texto_boton_cancelar="ABORTAR OPERACIÓN",
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
            self.hint_label.setText(
                "APUNTA CON LA CÁMARA AL CÓDIGO DE BARRAS O QR"
            )
            self.error_label = QLabel("")
            self.error_label.setObjectName("lbl_info_scan")
            self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout.insertWidget(3, self.error_label)
            btn_cancel = plantilla["btn_cancelar"]
            btn_cancel.clicked.connect(self._on_cancel)
            if aplicar_estilo_widget is not None:
                aplicar_estilo_widget(self.video_label)
                aplicar_estilo_widget(self.hint_label)
                aplicar_estilo_widget(self.error_label)
                aplicar_estilo_widget(btn_cancel)
        else:
            self.setStyleSheet("background-color: #1A1D24; border-radius: 8px;")
            self.resize(600, 400)
            self.layout = QVBoxLayout(self)
            self.layout.setContentsMargins(8, 8, 8, 8)
            self.layout.setSpacing(6)
            self.video_label = QLabel()
            self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.video_label.setStyleSheet("background-color: black; border-radius: 6px;")
            self.layout.addWidget(self.video_label)
            self.hint_label = QLabel(
                "Apunta con la cámara al código de barras o QR. Se detectará automáticamente."
            )
            self.hint_label.setStyleSheet("color: white; padding: 4px;")
            self.layout.addWidget(self.hint_label)
            self.error_label = QLabel("")
            self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.error_label.setStyleSheet("color: red; font-weight: bold; padding: 4px;")
            self.layout.addWidget(self.error_label)
            btn_cancel = QPushButton("Cancelar")
            btn_cancel.clicked.connect(self._on_cancel)
            btn_cancel.setStyleSheet(
                """
                QPushButton { 
                    background-color: #FF4B4B; 
                    color: white; 
                    font-weight: bold; 
                    border-radius: 10px; 
                    padding: 8px;
                }
                QPushButton:hover { 
                    background-color: #FF2222; 
                }
            """
            )
            btn_cancel.setFont(QFont("Segoe UI", 10))
            btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
            self.layout.addWidget(btn_cancel, alignment=Qt.AlignmentFlag.AlignRight)

        # ----- SONIDO DE ERROR -----
        self.error_player = QMediaPlayer()
        self.error_audio = QAudioOutput()
        self.error_player.setAudioOutput(self.error_audio)

        sound_path = os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.dirname(__file__))
            ),  # subir dos niveles: /src -> /360-stock
            "assets",
            "error.wav",
        )

        self.error_player.setSource(QUrl.fromLocalFile(sound_path))
        self.error_audio.setVolume(0.9)

        print("Ruta sonido error:", sound_path)
        print("¿Existe el archivo?", os.path.exists(sound_path))

        # Hilo de cámara
        self.thread = VideoThread(camera_index=camera_index)
        self.thread.change_pixmap_signal.connect(self.update_image)

        # Conectar al callback externo
        self.thread.code_detected.connect(self.callback)

        self.thread.start()

    def update_image(self, qt_image):
        pix = QPixmap.fromImage(qt_image)
        if not pix.isNull():
            self.video_label.setPixmap(
                pix.scaled(
                    self.video_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def show_error(self, mensaje="Código no válido"):
        """Mostrar error temporal en la ventana del escáner y reproducir sonido"""
        self.error_label.setText(f"ERROR: {mensaje}")
        QTimer.singleShot(3000, lambda: self.error_label.clear())

        # Reproducir sonido
        if self.error_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.error_player.stop()  # reiniciar en caso de que estuviera reproduciendo
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


# ---------------------------
# InfoArticuloWindow.py
# ---------------------------
import os
import sqlite3
import cv2
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFormLayout,
    QFileDialog,
    QMessageBox,
    QInputDialog,
    QScrollArea,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtGui import QPixmap, QFont, QColor, QGuiApplication
from PyQt6.QtCore import Qt
from pyzbar.pyzbar import ZBarSymbol


# Ejemplo de función externa para obtener ventas de la semana
def ventas_semana(codigo):
    return 0  # Reemplazar con lógica real si aplica


class InfoArticuloWindow(QWidget):
    # Ajustamos para recibir callback_vuelta, usuario y el resto de argumentos
    def __init__(
        self, callback_vuelta=None, usuario=None, stock_signals=None, **kwargs
    ):
        super().__init__()

        # Guardamos las referencias necesarias
        self.callback_vuelta = callback_vuelta
        self.usuario_actual = usuario
        # Extraemos perfil si tus métodos internos lo usan
        if isinstance(usuario, dict):
            self.perfil = usuario.get("perfil", "OPERARIO")
        else:
            self.perfil = getattr(usuario, "perfil", "OPERARIO")

        self.current_codigo = None

        # Gestión de señales de stock
        self.stock_signals = stock_signals
        if self.stock_signals:
            try:
                self.stock_signals.stock_actualizado.connect(self.actualizar_stock)
            except Exception:
                pass

        self.setup_ui()

    # ---------------------------
    # UI
    # ---------------------------
    def setup_ui(self):
        self.setWindowTitle("Información del artículo")
        self.resize(700, 750)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        # BUSCADOR
        title = QLabel("Buscar artículo por código o nombre")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: white;")
        main_layout.addWidget(title)

        form = QFormLayout()
        self.input_buscar = QLineEdit()
        self.input_buscar.setPlaceholderText("Introduce código o nombre")
        form.addRow("Código/Nombre:", self.input_buscar)
        main_layout.addLayout(form)

        btn_buscar = QPushButton("Buscar")
        btn_buscar.clicked.connect(self.buscar)
        self.estilo_boton(btn_buscar)
        main_layout.addWidget(btn_buscar)

        # BOTONES FIJOS
        botones_layout = QHBoxLayout()
        botones_layout.setSpacing(8)

        self.btn_edit_nombre = QPushButton("Editar nombre")
        self.btn_edit_nombre.clicked.connect(self.editar_nombre)
        self.estilo_boton(self.btn_edit_nombre)
        botones_layout.addWidget(self.btn_edit_nombre)

        self.btn_edit_seccion = QPushButton("Editar sección")
        self.btn_edit_seccion.clicked.connect(self.editar_seccion)
        self.estilo_boton(self.btn_edit_seccion)
        botones_layout.addWidget(self.btn_edit_seccion)

        self.btn_edit_ub_tienda = QPushButton("Editar ubicación tienda")
        self.btn_edit_ub_tienda.clicked.connect(self.editar_ubicacion_tienda)
        self.estilo_boton(self.btn_edit_ub_tienda)
        botones_layout.addWidget(self.btn_edit_ub_tienda)

        self.btn_edit_ub_almacen = QPushButton("Editar ubicación almacén")
        self.btn_edit_ub_almacen.clicked.connect(self.editar_ubicacion_almacen)
        self.estilo_boton(self.btn_edit_ub_almacen)
        botones_layout.addWidget(self.btn_edit_ub_almacen)

        self.btn_img = QPushButton("Subir/Actualizar imagen")
        self.btn_img.clicked.connect(self.subir_imagen)
        self.estilo_boton(self.btn_img)
        botones_layout.addWidget(self.btn_img)

        self.btn_del_img = QPushButton("Eliminar imagen")
        self.btn_del_img.clicked.connect(self.eliminar_imagen)
        self.estilo_boton(self.btn_del_img, rojo=True)
        botones_layout.addWidget(self.btn_del_img)

        self.btn_scan = QPushButton("Escanear código")
        self.btn_scan.clicked.connect(self.abrir_escanner)
        self.estilo_boton(self.btn_scan)
        botones_layout.addWidget(self.btn_scan)

        self.btn_copy_codigo = QPushButton("Copiar código")
        self.btn_copy_codigo.clicked.connect(self.copiar_codigo)
        self.estilo_boton(self.btn_copy_codigo)
        botones_layout.addWidget(self.btn_copy_codigo)

        self.btn_copy_nombre = QPushButton("Copiar nombre")
        self.btn_copy_nombre.clicked.connect(self.copiar_nombre)
        self.estilo_boton(self.btn_copy_nombre)
        botones_layout.addWidget(self.btn_copy_nombre)

        main_layout.addLayout(botones_layout)

        # SCROLL AREA
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            """
            QScrollArea { background-color: #0E1117; border-radius: 12px; }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 12px 0 12px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.12);
                min-height: 30px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255,255,255,0.18);
            }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
            QScrollBar::add-page, QScrollBar::sub-page { background: none; }
        """
        )

        scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_widget)
        self.scroll_layout.setContentsMargins(20, 20, 20, 20)
        self.scroll_layout.setSpacing(12)

        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet("background-color: #1A1D24; border-radius: 8px;")
        self.img_label.setFixedHeight(240)
        self.scroll_layout.addWidget(self.img_label)

        self.lbl_result = QLabel("")
        self.lbl_result.setFont(QFont("Segoe UI", 11))
        self.lbl_result.setWordWrap(True)
        self.lbl_result.setStyleSheet("color: white;")
        self.scroll_layout.addWidget(self.lbl_result)

        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)

        btn_volver = QPushButton("Volver al menú principal")
        btn_volver.clicked.connect(self.volver_menu_principal)
        self.estilo_boton(btn_volver, rojo=True)
        main_layout.addWidget(btn_volver, alignment=Qt.AlignmentFlag.AlignRight)

        self.setStyleSheet("background-color: #0E1117;")

    # ---------------------------
    # Estilo de botones
    # ---------------------------
    def estilo_boton(self, btn, rojo=False):
        if rojo:
            base, hover, text_color, padding = "#FF4B4B", "#FF2222", "#FFFFFF", "10px"
        else:
            base, hover, text_color, padding = "#00FFC6", "#00DDAA", "#0E1117", "10px"
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {base};
                color: {text_color};
                font-weight: bold;
                border-radius: 10px;
                padding: {padding};
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
        """
        )
        btn.setFont(QFont("Segoe UI", 10))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(18)
        shadow.setColor(QColor(base))
        shadow.setOffset(0)
        btn.setGraphicsEffect(shadow)

    # ---------------------------
    # Buscar artículo (mejorada: búsqueda por fragmento de nombre)
    # ---------------------------
    def buscar(self):
        q = self.input_buscar.text().strip()
        if not q:
            QMessageBox.warning(self, "Aviso", "Introduce código o nombre.")
            return

        db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "database", "stock.db"
        )
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Buscar por código exacto o por nombre (LIKE + LOWER para insensibilidad)
        cur.execute(
            """
            SELECT codigo, nombre, Stock_total, Stock_tienda, precio,
                   capacidad_lineal, bloqueado, ultima_recepcion, siguiente_recepcion,
                   ubicacion_tienda, ubicacion_almacen, seccion,
                   promo_activa, precio_promo, promo_fin, imagen
            FROM articulos
            WHERE codigo = ? OR LOWER(nombre) LIKE LOWER(?)
            ORDER BY nombre ASC
        """,
            (q, f"%{q}%"),
        )

        row = cur.fetchone()
        conn.close()

        if not row:
            self.lbl_result.setText("No encontrado")
            self.img_label.clear()
            self.current_codigo = None
            return

        (
            codigo,
            nombre,
            stock_total,
            stock_tienda,
            precio,
            capacidad,
            bloqueado,
            ultima_recepcion,
            siguiente_recepcion,
            ubic_tienda,
            ubic_almacen,
            seccion,
            promo_activa,
            precio_promo,
            promo_fin,
            imagen,
        ) = row

        self.current_codigo = codigo
        ventas7 = ventas_semana(codigo)
        bloqueado_text = "Sí" if bloqueado else "No"

        txt = [
            f"<b>Código:</b> {codigo}",
            f"<b>Nombre:</b> {nombre}",
            f"<b>Sección:</b> {seccion or 'No asignada'}",
            f"<b>Precio normal:</b> {precio:.2f} €",
        ]

        if promo_activa:
            txt.append(f"<b>⚠ PRECIO PROMOCIONAL:</b> {precio_promo:.2f} €")
            txt.append(f"<b>Fin promoción:</b> {promo_fin or 'No especificada'}")

        txt += [
            f"<br><b>Stock almacén:</b> {stock_total}",
            f"<b>Stock tienda:</b> {stock_tienda}",
            f"<b>Ubicación tienda:</b> {ubic_tienda or 'No asignada'}",
            f"<b>Ubicación almacén:</b> {ubic_almacen or 'No asignada'}",
            f"<b>Bloqueado:</b> {bloqueado_text}",
            f"<b>Ventas últimos 7 días:</b> {ventas7}",
            f"<b>Última recepción:</b> {ultima_recepcion or '---'}",
            f"<b>Siguiente recepción:</b> {siguiente_recepcion or '---'}",
        ]

        self.lbl_result.setText("<br>".join(txt))

        if imagen and os.path.exists(imagen):
            pix = QPixmap(imagen)
            self.img_label.setPixmap(
                pix.scaled(
                    self.img_label.width(),
                    self.img_label.height(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.img_label.clear()

    # ---------------------------
    # Subir / eliminar imagen
    # ---------------------------
    def subir_imagen(self):
        if not self.current_codigo:
            QMessageBox.warning(self, "Aviso", "Busca un artículo primero.")
            return
        file, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar imagen", "", "Imágenes (*.png *.jpg *.jpeg)"
        )
        if not file:
            return
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "database", "stock.db"
        )
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "UPDATE articulos SET imagen = ? WHERE codigo = ?",
            (file, self.current_codigo),
        )
        conn.commit()
        conn.close()
        self.buscar()
        QMessageBox.information(
            self, "Imagen actualizada", "La imagen ha sido actualizada correctamente."
        )

    def eliminar_imagen(self):
        if not self.current_codigo:
            QMessageBox.warning(self, "Aviso", "Busca un artículo primero.")
            return
        respuesta = QMessageBox.question(
            self,
            "Confirmar",
            "¿Seguro que quieres eliminar la imagen del artículo?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "database", "stock.db"
        )
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "UPDATE articulos SET imagen = NULL WHERE codigo = ?",
            (self.current_codigo,),
        )
        conn.commit()
        conn.close()
        self.img_label.clear()
        self.buscar()
        QMessageBox.information(
            self,
            "Imagen eliminada",
            "La imagen del artículo ha sido eliminada correctamente.",
        )

    # ---------------------------
    # Copiar código / nombre
    # ---------------------------
    def copiar_codigo(self):
        if not self.current_codigo:
            QMessageBox.warning(self, "Aviso", "Busca un artículo primero.")
            return
        QGuiApplication.clipboard().setText(str(self.current_codigo))
        QMessageBox.information(self, "Copiado", "Código copiado al portapapeles.")

    def copiar_nombre(self):
        import re

        text = self.lbl_result.text()
        m = re.search(r"<b>Nombre:</b>\s*([^<\n]+)", text)
        nombre = m.group(1).strip() if m else ""
        if not nombre:
            QMessageBox.warning(self, "Aviso", "No hay nombre para copiar.")
            return
        QGuiApplication.clipboard().setText(nombre)
        QMessageBox.information(self, "Copiado", "Nombre copiado al portapapeles.")

    # ---------------------------
    # Editar nombre
    # ---------------------------
    def editar_nombre(self):
        if not self.current_codigo:
            QMessageBox.warning(self, "Aviso", "Primero busca un artículo.")
            return

        nuevo, ok = QInputDialog.getText(self, "Editar nombre", "Nuevo nombre:")
        if not ok or not nuevo.strip():
            return

        nuevo = nuevo.strip()
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "database", "stock.db"
        )

        # Guardar el nuevo nombre en la base de datos
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "UPDATE articulos SET nombre = ? WHERE codigo = ?",
            (nuevo, self.current_codigo),
        )
        conn.commit()
        conn.close()

        # Actualizar la barra de búsqueda con el nuevo nombre y recargar info
        self.input_buscar.setText(nuevo)
        self.buscar()

        QMessageBox.information(
            self, "Guardado", f"Nombre actualizado correctamente a:\n{nuevo}"
        )

    def editar_seccion(self):
        if not self.current_codigo:
            QMessageBox.warning(self, "Aviso", "Primero busca un artículo.")
            return
        nueva, ok = QInputDialog.getText(self, "Editar sección", "Nueva sección:")
        if not ok or not nueva.strip():
            return
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "database", "stock.db"
        )
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "UPDATE articulos SET seccion = ? WHERE codigo = ?",
            (nueva.strip(), self.current_codigo),
        )
        conn.commit()
        conn.close()
        self.buscar()
        QMessageBox.information(self, "Guardado", "Sección actualizada correctamente.")

    def editar_ubicacion_tienda(self):
        if not self.current_codigo:
            QMessageBox.warning(self, "Aviso", "Primero busca un artículo.")
            return
        nueva, ok = QInputDialog.getText(
            self, "Ubicación tienda", "Nueva ubicación en tienda:"
        )
        if not ok:
            return
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "database", "stock.db"
        )
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "UPDATE articulos SET ubicacion_tienda = ? WHERE codigo = ?",
            (nueva.strip(), self.current_codigo),
        )
        conn.commit()
        conn.close()
        self.buscar()
        QMessageBox.information(self, "Guardado", "Ubicación de tienda actualizada.")

    def editar_ubicacion_almacen(self):
        if not self.current_codigo:
            QMessageBox.warning(self, "Aviso", "Primero busca un artículo.")
            return
        nueva, ok = QInputDialog.getText(
            self, "Ubicación almacén", "Nueva ubicación en almacén:"
        )
        if not ok:
            return
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "database", "stock.db"
        )
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "UPDATE articulos SET ubicacion_almacen = ? WHERE codigo = ?",
            (nueva.strip(), self.current_codigo),
        )
        conn.commit()
        conn.close()
        self.buscar()
        QMessageBox.information(self, "Guardado", "Ubicación de almacén actualizada.")

    # ---------------------------
    # Abrir escáner
    # ---------------------------
    def abrir_escanner(self):
        try:
            _ = cv2.__version__
        except Exception:
            QMessageBox.critical(
                self,
                "Error",
                "OpenCV no está disponible. Instala opencv-python y pyzbar.",
            )
            return

        self.scanner = BarcodeScanner(self._codigo_detectado, parent=self)
        self.scanner.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        self.scanner.setModal(True)
        self.scanner.resize(600, 400)
        self.scanner.show()

    # ---------------------------
    # Callback código detectado
    # ---------------------------
    def _codigo_detectado(self, codigo, tipo=None):
        if not codigo:
            return

        codigo = codigo.strip()
        es_numerico = codigo.isdigit()

        # Normalizar código según tipo
        if tipo in (ZBarSymbol.EAN13, "EAN13"):
            if len(codigo) == 13 and es_numerico:
                codigo = codigo[:-1]
            codigo = str(int(codigo))
        elif tipo in (ZBarSymbol.UPCA, "UPC-A"):
            if len(codigo) == 12 and es_numerico:
                codigo = codigo[:-1]
            codigo = str(int(codigo))
        elif tipo in (ZBarSymbol.EAN8, "EAN8"):
            if es_numerico:
                codigo = str(int(codigo))
        else:
            codigo = codigo.upper()

        # --- Buscar en la base de datos ---
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "database", "stock.db"
        )
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM articulos WHERE codigo=?", (codigo,))
        existe = cur.fetchone() is not None
        conn.close()

        # --- Manejo de error ---
        if not existe:
            if hasattr(self, "scanner") and self.scanner:
                try:
                    self.scanner.show_error("Código no válido")
                except Exception:
                    pass
            return

        # --- Mostrar información ---
        self.input_buscar.setText(codigo)
        self.buscar()

        # Cerrar escáner si el código es válido
        if hasattr(self, "scanner") and self.scanner:
            self.scanner.close()

    # ---------------------------
    # Señales de stock
    # ---------------------------
    def actualizar_stock(self, codigo):
        if self.current_codigo == codigo:
            self.buscar()

    # ---------------------------
    # Volver al menú
    # ---------------------------
    def volver_menu_principal(self):
        """Cierra la ventana actual y vuelve al Menú Principal."""
        if self.callback_vuelta:
            self.callback_vuelta()
            self.close()
        else:
            self.close()
