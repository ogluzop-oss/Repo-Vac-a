import heapq
import json
import math
import os
import shutil
import zlib
from datetime import datetime

import cv2
import numpy as np
import qrcode
from PyQt6.QtCore import QDateTime, QEvent, QLineF, QPointF, Qt, QTimer
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QCursor,
    QFont,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QCompleter,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)
from pyzbar import pyzbar
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

# Busca tus imports y añade este:
from src.db.conexion import obtener_conexion
from src.utils import i18n
from src.utils.i18n import tr

try:
    from assets.estilo_global import aplicar_estilo_widget, construir_plantilla_camara
except Exception:
    aplicar_estilo_widget = None
    construir_plantilla_camara = None


class _NeonZoomBtn(QPushButton):
    """Zoom button that paints — or + with neon cyan strokes, like _NeonSymbolButton."""

    def __init__(self, symbol, parent=None):
        super().__init__("", parent)
        self._symbol = symbol
        self.setFixedSize(55, 38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QPushButton { background-color: #0D1117; border: 2px solid #00FFC6; border-radius: 8px; }"
            " QPushButton:hover { background-color: #00FFC6; }"
        )

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        clr = QColor("#0D1117") if self.underMouse() else QColor("#00FFC6")
        p.setPen(QPen(clr, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        cx, cy = self.width() // 2, self.height() // 2
        arm = 8
        p.drawLine(cx - arm, cy, cx + arm, cy)
        if self._symbol == "+":
            p.drawLine(cx, cy - arm, cx, cy + arm)
        p.end()


# ============================================================
# BLOQUE VENTANA PRINCIPAL DE UBICACIÓN
# ============================================================

class UbicacionTiendaWindow(QMainWindow):

    def __init__(self, main, callback_vuelta=None, usuario=None, **kwargs):
        """
        Constructor Quirúrgico: Centralización de Escena y Estética Neón.
        Se asegura de que la matriz y la escena compartida estén vinculadas antes del render.
        """
        super().__init__()

        # 1. REFERENCIAS BÁSICAS Y ESTADO
        self.main_window = main
        self.callback_vuelta = callback_vuelta
        self.usuario_actual = usuario
        self.articulo_seleccionado = None
        self.coordenadas_destino = None
        self.destino_gps_activo = None
        self.planta_actual = 0
        self.cambios_sin_guardar = False
        self._startup_complete = False
        self._bloqueo_navegacion = False
        self._historial_por_planta = {}
        self._snapshot_pre_calibracion = None
        self._restaurando_historial = False
        self._labels_planta = []
        self._input_gps_dialog_activo = None
        self._dialogo_ruta_gps_activo = None
        self._opciones_destino_busqueda = []
        self._articulo_busqueda_actual = {}

        # --- 2. INICIALIZACIÓN DE DATOS CRÍTICOS (Anti-Crash) ---
        # Inicializamos atributos que los visores buscarán al pintar el Foreground
        self.celda_size = 20
        self.matriz_obstaculos = None
        self.ratio_px_m_h = 1.0
        self.ratio_px_m_v = 1.0
        self.pixmap_item = None  # Referencia única del fondo para ambos visores

        from PyQt6.QtCore import Qt, QTimer
        from PyQt6.QtWidgets import QGraphicsScene

        # 3. ESCENA ÚNICA (Sincronización Total)
        self.escena_compartida = QGraphicsScene()
        # Fijamos un área mínima inicial para que los visores no nazcan "ciegos"
        self.escena_compartida.setSceneRect(0, 0, 1000, 1000)
        self.escena_compartida.setBackgroundBrush(Qt.GlobalColor.transparent)

        # 4. INICIALIZAR VISORES (Espejos de la misma realidad)
        # Pasamos self como main para que los visores accedan a la matriz compartida
        self.visor_admin = VistaMapa(main=self, modo_admin=True)
        self.visor_admin.setScene(self.escena_compartida)

        self.visor_mapa = VistaMapa(main=self, modo_admin=False)
        self.visor_mapa.setScene(self.escena_compartida)

        # 5. CONSTRUIR INTERFAZ
        self.setup_ui()

        # P3 (UX-TPV-01): sidebar de navegación colapsable con persistencia por usuario.
        try:
            from src.gui.sidebar_colapsable import instalar_sidebar_colapsable
            if getattr(self, "sidebar", None) is not None:
                instalar_sidebar_colapsable(self, self.sidebar, usuario=self.usuario_actual, clave="ubicacion")
        except Exception:
            pass

        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

        # 6. ESTÉTICA PREMIUM NEÓN
        estilo_neon_accion = """
            QPushButton {
                background-color: #0A0A0A; 
                color: #00F5FF; 
                border: 1px solid #00F5FF;
                padding: 10px 20px; 
                border-radius: 8px; 
                font-family: 'Segoe UI'; 
                font-weight: 900;
                font-size: 12px;
                letter-spacing: 1px;
            }
            QPushButton:hover { 
                background-color: #00F5FF; 
                color: #000000; 
                border: 1px solid #FFFFFF;
            }
        """

        if hasattr(self, "btn_exportar_pdf"):
            self.btn_exportar_pdf.setStyleSheet(estilo_neon_accion)
            self.btn_exportar_pdf.clicked.connect(self.exportar_qrs_desde_mapa)

        # 7. PRODUCTIVIDAD Y SHORTCUTS
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.shortcut_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.shortcut_undo.activated.connect(self.gestionar_deshacer_muro)

        # 8. ESTADO DE CALIBRACIÓN
        self.calibracion_completada = False

        # 9. CARGA AUTOMÁTICA DEL PLANO GUARDADO (Arranque)
        # Delay amplio para que los visores tengan tamaño real antes del primer fitInView
        QTimer.singleShot(500, self._cargar_primera_planta_disponible)

    # ============================================================
    # BLOQUE UTILIDADES INTERNAS Y HELPERS
    # ============================================================

    def _estado_planta(self, planta_idx=None):
        planta_idx = self.planta_actual if planta_idx is None else planta_idx
        return self._historial_por_planta.setdefault(
            planta_idx, {"undo": [], "redo": []}
        )

    def _reiniciar_historial_planta(self, planta_idx=None):
        estado = self._estado_planta(planta_idx)
        estado["undo"].clear()
        estado["redo"].clear()
        self._actualizar_botones_historial()

    def _registrar_label_planta(self, label):
        if label and label not in self._labels_planta:
            self._labels_planta.append(label)
        self._actualizar_labels_planta()

    def _cargar_primera_planta_disponible(self):
        """On startup, always reset to plant 0 so the calibration button state is clean."""
        self._startup_complete = False
        self.planta_actual = 0
        self._actualizar_labels_planta()
        self.cargar_infraestructura_registrada()
        # Mark startup window closed after 2 s so the debug trace stops firing
        from PyQt6.QtCore import QTimer as _QT3
        _QT3.singleShot(2000, lambda: setattr(self, "_startup_complete", True))

    def _actualizar_labels_planta(self):
        p_idx = getattr(self, "planta_actual", 0)
        display = tr("ubic.no_plan", default="SIN PLANO")
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COALESCE(tipo,'LOCAL'), titulo_plano "
                        "FROM configuracion_mapa WHERE planta_index=%s",
                        (p_idx,),
                    )
                    row = cur.fetchone()
            if row:
                tipo = (row[0] or "LOCAL").upper()
                titulo = (row[1] or "").strip()
                display = f"{tipo}: {titulo}" if titulo else tipo
        except Exception:
            pass

        texto = f"📍 {display}"
        for label in list(self._labels_planta):
            try:
                label.setText(texto)
            except RuntimeError:
                self._labels_planta.remove(label)

        for attr in ("lbl_planta_actual", "lbl_planta_actual_gps"):
            lbl = getattr(self, attr, None)
            if lbl:
                try:
                    lbl.setText(texto)
                except RuntimeError:
                    pass

    def _pedir_tipo_plano(self):
        """Dialog to choose LOCAL or ALMACÉN for a new plan. Returns 'LOCAL', 'ALMACÉN', or None."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QDialog,
            QFrame,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QVBoxLayout,
        )

        diag = QDialog(self)
        diag.setFixedSize(420, 210)
        diag.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        diag.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        ml = QVBoxLayout(diag)
        ml.setContentsMargins(0, 0, 0, 0)

        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background-color: #0D1117; border: 2px solid #00FFC6; border-radius: 18px; }"
            " QLabel { color: #E6EDF3; border: none; background: transparent; }"
        )
        il = QVBoxLayout(frame)
        il.setContentsMargins(28, 22, 28, 22)
        il.setSpacing(14)

        lbl_t = QLabel(tr("ubic.floor_type_q", default="¿QUÉ TIPO DE PLANTA ES?"))
        lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_t.setStyleSheet(
            "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900;"
            " font-size: 16px; letter-spacing: 1px; border: none; background: transparent;"
        )

        lbl_m = QLabel(tr("ubic.floor_type_msg", default="Seleccione si el plano corresponde a\nel LOCAL (tienda) o al ALMACÉN."))
        lbl_m.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_m.setWordWrap(True)
        lbl_m.setStyleSheet(
            "color: #C9D1D9; font-family: 'Segoe UI'; font-weight: 700;"
            " font-size: 13px; border: none; background: transparent;"
        )

        br = QHBoxLayout()
        br.setSpacing(12)

        self._tipo_elegido = None

        def elegir(tipo):
            self._tipo_elegido = tipo
            diag.accept()

        btn_local = QPushButton(tr("ubic.btn_local", default="LOCAL"))
        btn_local.setFixedHeight(42)
        btn_local.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_local.setStyleSheet(
            "QPushButton { background-color: #0D1117; color: #00FFC6; border: 2px solid #00FFC6;"
            " border-radius: 10px; font-family: 'Segoe UI'; font-weight: 900; font-size: 14px; }"
            " QPushButton:hover { background-color: #00FFC6; color: #0D1117; border: 2px solid #00FFC6; }"
        )
        btn_local.clicked.connect(lambda: elegir("LOCAL"))

        btn_alm = QPushButton(tr("ubic.btn_warehouse", default="ALMACÉN"))
        btn_alm.setFixedHeight(42)
        btn_alm.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_alm.setStyleSheet(
            "QPushButton { background-color: #1F6FEB; color: #FFFFFF; border: none;"
            " border-radius: 10px; font-family: 'Segoe UI'; font-weight: 900; font-size: 14px; }"
            " QPushButton:hover { background-color: #FFFFFF; color: #1F6FEB; }"
        )
        btn_alm.clicked.connect(lambda: elegir("ALMACÉN"))

        br.addWidget(btn_local)
        br.addWidget(btn_alm)
        il.addWidget(lbl_t)
        il.addWidget(lbl_m)
        il.addStretch()
        il.addLayout(br)
        ml.addWidget(frame)

        if diag.exec() != QDialog.DialogCode.Accepted:
            return None
        return self._tipo_elegido

    def _pedir_altura_planta(self):
        """
        Neon dialog asking for the floor's real height in metres.
        Called after X/Y calibration is saved. Stores the value in configuracion_mapa.
        Returns the entered value (float) or None if skipped.
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QDoubleValidator
        from PyQt6.QtWidgets import (
            QDialog,
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QVBoxLayout,
        )

        from src.db.conexion import obtener_conexion

        p_idx = getattr(self, "planta_actual", 0)

        diag = QDialog(self)
        diag.setFixedSize(440, 255)
        diag.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        diag.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        ml = QVBoxLayout(diag)
        ml.setContentsMargins(0, 0, 0, 0)

        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background-color: #0D1117; border: 2px solid #00FFC6; border-radius: 18px; }"
            " QLabel { color: #E6EDF3; border: none; background: transparent; }"
        )
        il = QVBoxLayout(frame)
        il.setContentsMargins(28, 22, 28, 22)
        il.setSpacing(14)

        lbl_t = QLabel("📐  " + tr("ubic.height_title", default="ALTURA DE LA PLANTA"))
        lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_t.setStyleSheet(
            "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900;"
            " font-size: 16px; letter-spacing: 1px; border: none; background: transparent;"
        )

        lbl_m = QLabel(tr("ubic.height_q", default="¿Cuántos metros de altura mide esta planta?"))
        lbl_m.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_m.setStyleSheet(
            "color: #C9D1D9; font-family: 'Segoe UI'; font-weight: 700;"
            " font-size: 13px; border: none; background: transparent;"
        )

        inp = QLineEdit()
        inp.setPlaceholderText(tr("ubic.height_ph", default="Ej: 3.5"))
        inp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inp.setValidator(QDoubleValidator(0.1, 99.0, 2, inp))
        inp.setFixedHeight(44)
        inp.setStyleSheet(
            "QLineEdit {"
            "  background-color: #161B22;"
            "  color: #E6EDF3;"
            "  border: 2px solid #00FFC6;"
            "  border-radius: 10px;"
            "  font-family: 'Segoe UI'; font-weight: 700; font-size: 17px;"
            "  padding: 0 12px;"
            "}"
            "QLineEdit:focus { border-color: #FFFFFF; }"
        )

        br = QHBoxLayout()
        br.setSpacing(12)

        btn_skip = QPushButton(tr("ubic.btn_skip", default="Ahora no"))
        btn_skip.setFixedHeight(40)
        btn_skip.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_skip.setStyleSheet(
            "QPushButton { background-color: #21262D; color: #8B949E;"
            " border: 1px solid #30363D; border-radius: 10px;"
            " font-family: 'Segoe UI'; font-weight: 900; font-size: 13px; }"
            " QPushButton:hover { background-color: #FFFFFF; color: #0D1117; border: 1px solid #FFFFFF; }"
        )
        btn_skip.clicked.connect(diag.reject)

        btn_ok = QPushButton(tr("ubic.save", default="GUARDAR"))
        btn_ok.setFixedHeight(40)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setStyleSheet(
            "QPushButton { background-color: #0D1117; color: #00FFC6; border: 2px solid #00FFC6;"
            " border-radius: 10px; font-family: 'Segoe UI'; font-weight: 900; font-size: 13px; }"
            " QPushButton:hover { background-color: #00FFC6; color: #0D1117; border: 2px solid #00FFC6; }"
        )
        btn_ok.clicked.connect(diag.accept)
        inp.returnPressed.connect(diag.accept)

        br.addWidget(btn_skip)
        br.addWidget(btn_ok)
        il.addWidget(lbl_t)
        il.addWidget(lbl_m)
        il.addWidget(inp)
        il.addStretch()
        il.addLayout(br)
        ml.addWidget(frame)

        inp.setFocus()

        if diag.exec() != QDialog.DialogCode.Accepted:
            return None

        texto = inp.text().strip().replace(",", ".")
        try:
            metros = float(texto)
            if metros <= 0:
                return None
        except ValueError:
            return None

        try:
            with obtener_conexion() as conn:
                with conn.cursor() as cur:
                    try:
                        cur.execute(
                            "ALTER TABLE configuracion_mapa "
                            "ADD COLUMN IF NOT EXISTS altura_metros DOUBLE DEFAULT NULL"
                        )
                    except Exception:
                        pass
                    cur.execute(
                        "UPDATE configuracion_mapa SET altura_metros=%s WHERE planta_index=%s",
                        (metros, p_idx),
                    )
                conn.commit()
        except Exception as e:
            print(f"⚠️ Error guardando altura: {e}")

        return metros

    def _crear_fuente_segoe(self, size=10):
        return QFont("Segoe UI", size, QFont.Weight.Bold)

    def _aplicar_fuente_segoe(self, widget):
        if not widget:
            return
        widget.setFont(
            self._crear_fuente_segoe(
                widget.font().pointSize() if widget.font().pointSize() > 0 else 10
            )
        )
        for hijo in [widget, *widget.findChildren(QWidget)]:
            if isinstance(
                hijo,
                (
                    QLabel,
                    QPushButton,
                    QLineEdit,
                    QTextEdit,
                    QComboBox,
                    QListWidget,
                    QTreeWidget,
                ),
            ):
                size = hijo.font().pointSize() if hijo.font().pointSize() > 0 else 10
                hijo.setFont(self._crear_fuente_segoe(size))
            if isinstance(hijo, QPushButton):
                hijo.setCursor(Qt.CursorShape.PointingHandCursor)

    def _forzar_reencuadre_diferido(self, force=True):
        # Cuatro pasadas con delays crecientes para garantizar que el widget
        # ya tiene su tamaño final cuando se ejecuta fitInView
        for delay in (0, 150, 350, 650):
            QTimer.singleShot(delay, lambda f=force: self.reencuadrar_plano(force=f))

    # ============================================================
    # BLOQUE ESTILOS Y TEMAS VISUALES
    # ============================================================

    def _estilo_boton_neon(
        self,
        bg="#161B22",
        fg="#00F5FF",
        border="#00F5FF",
        hover_bg=None,
        hover_fg=None,
        radius=10,
        padding="10px 18px",
        font_size=11,
    ):
        hover_bg = hover_bg or fg
        hover_fg = hover_fg or bg
        return f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: {radius}px;
                padding: {padding};
                font-family: 'Segoe UI';
                font-weight: 900;
                font-size: {font_size}px;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                color: {hover_fg};
                border: 1px solid {border};
            }}
        """

    def _estilo_dialogo_neon(self, border_color="#00FFC6"):
        return f"""
            QFrame {{
                background-color: #0D1117;
                border: 2px solid {border_color};
                border-radius: 18px;
            }}
            QLabel {{
                color: #E6EDF3;
                font-family: 'Segoe UI';
                font-weight: 900;
                border: none;
                background: transparent;
            }}
            QPushButton {{
                background-color: {border_color};
                color: #0D1117;
                border: 1px solid {border_color};
                border-radius: 10px;
                padding: 10px 18px;
                font-family: 'Segoe UI';
                font-weight: 900;
            }}
            QPushButton:hover {{
                background-color: #0D1117;
                color: {border_color};
                border: 1px solid {border_color};
            }}
        """

    def _estilo_piloto_rastreo(self, activo=False):
        borde = "#00FFC6" if activo else "#30363D"
        fondo = "rgba(0, 255, 198, 0.08)" if activo else "#12161C"
        texto = "#00FFC6" if activo else "#8B949E"
        led = "#00FFC6" if activo else "#3A424C"
        brillo = "0 0 14px #00FFC6" if activo else "none"
        return {
            "panel": f"""
                QFrame {{
                    background-color: {fondo};
                    border: 1px solid {borde};
                    border-radius: 14px;
                }}
            """,
            "led": f"""
                QLabel {{
                    color: {led};
                    font-family: 'Segoe UI';
                    font-weight: 900;
                    font-size: 22px;
                    border: none;
                    background: transparent;
                }}
            """,
            "titulo": f"""
                QLabel {{
                    color: {texto};
                    font-family: 'Segoe UI';
                    font-weight: 900;
                    font-size: 11px;
                    letter-spacing: 1px;
                    border: none;
                    background: transparent;
                }}
            """,
            "estado": f"""
                QLabel {{
                    color: {texto};
                    font-family: 'Segoe UI';
                    font-weight: 900;
                    font-size: 12px;
                    border: none;
                    background: transparent;
                }}
            """,
            "activo": activo,
            "texto": "ON" if activo else "OFF",
            "brillo": brillo,
        }

    # ============================================================
    # BLOQUE GPS Y NAVEGACIÓN
    # ============================================================

    def _actualizar_piloto_rastreo(self, activo, texto_extra=None):
        estilos = self._estilo_piloto_rastreo(activo)
        panel = getattr(self, "panel_rastreo_gps", None)
        led = getattr(self, "led_rastreo_gps", None)
        titulo = getattr(self, "lbl_titulo_rastreo_gps", None)
        estado = getattr(self, "lbl_estado_rastreo_gps", None)

        if panel:
            panel.setStyleSheet(estilos["panel"])
        if led:
            led.setText("●")
            led.setStyleSheet(estilos["led"])
            led.setToolTip("")
        if titulo:
            titulo.setStyleSheet(estilos["titulo"])
        if estado:
            sufijo = f" · {texto_extra}" if texto_extra else ""
            estado.setText(f"{tr('ubic.tracking', default='RASTREO')} {estilos['texto']}{sufijo}")
            estado.setStyleSheet(estilos["estado"])

        visor = getattr(self, "visor_mapa", None)
        if visor:
            visor.rastreo_en_vivo_activo = bool(activo)
        self.rastreo_activo = bool(activo)

    def _resetear_navegacion_gps(self, limpiar_operario=False):
        self.coordenadas_destino = None
        self.destino_gps_activo = None
        self._actualizar_piloto_rastreo(False)

        visor = getattr(self, "visor_mapa", None)
        if not visor:
            return

        if hasattr(visor, "limpiar_ruta"):
            visor.limpiar_ruta()

        if limpiar_operario:
            escena = QGraphicsView.scene(visor)
            if escena and getattr(visor, "icono_operario", None):
                try:
                    if visor.icono_operario.scene() == escena:
                        escena.removeItem(visor.icono_operario)
                except (RuntimeError, AttributeError):
                    pass
            visor.icono_operario = None
            visor.pos_operario = None
            visor.pos_objetivo_operario = None
            if (
                hasattr(visor, "timer_animacion_operario")
                and visor.timer_animacion_operario
            ):
                visor.timer_animacion_operario.stop()

    def _vaciar_plano_en_visores(self):
        escena = getattr(self, "escena_compartida", None)
        if escena:
            escena.clear()
            escena.setSceneRect(0, 0, 1, 1)
            escena.invalidate(escena.sceneRect(), QGraphicsScene.SceneLayer.AllLayers)

        self._limpiar_capas_editables()
        self._resetear_navegacion_gps(limpiar_operario=True)
        self.ruta_actual = ""
        self.ultimo_plano_cargado = ""
        self.pixmap_item = None

        for visor in [
            getattr(self, "visor_admin", None),
            getattr(self, "visor_mapa", None),
        ]:
            if not visor:
                continue
            visor.pixmap_item = None
            visor.ruta_actual = ""
            visor._zoom_manual_activo = False
            visor.matriz_obstaculos = None
            visor.resetTransform()
            visor.setSceneRect(0, 0, 1, 1)
            visor.centerOn(0, 0)
            if hasattr(visor, "historial_muros"):
                visor.historial_muros.clear()
            if visor.viewport():
                visor.viewport().update()

        self.actualizar_estado_bloqueo()
        self._actualizar_botones_historial()
        self._actualizar_labels_planta()

    def _distancia_real_metros(self, punto_a, punto_b, visor=None):
        if punto_a is None or punto_b is None:
            return None
        visor = (
            visor
            or getattr(self, "visor_mapa", None)
            or getattr(self, "visor_admin", None)
        )
        ratio = max(float(getattr(visor, "ratio_px_m_h", 1.0) or 1.0), 0.001)
        return math.hypot(punto_a.x() - punto_b.x(), punto_a.y() - punto_b.y()) / ratio

    def _seleccionar_mejor_destino_gps(self, opciones):
        disponibles = [
            op
            for op in (opciones or [])
            if op and op.get("disponible") and op.get("coords") is not None
        ]
        if not disponibles:
            return None
        return sorted(
            disponibles,
            key=lambda op: (
                op.get("distancia_m") is None,
                (
                    op.get("distancia_m")
                    if op.get("distancia_m") is not None
                    else float("inf")
                ),
                (
                    0
                    if op.get("tipo") == "LINEAL"
                    else 1 if op.get("tipo") == "ALMACEN" else 2
                ),
                op.get("ubicacion", ""),
            ),
        )[0]

    def _preparar_destino_gps(
        self, opcion, navegar_a_gps=False, activar_piloto=False, enfocar=False
    ):
        if not opcion or opcion.get("coords") is None:
            return False

        self.destino_gps_activo = dict(opcion)
        self.coordenadas_destino = opcion["coords"]

        visor = getattr(self, "visor_mapa", None)
        if visor and hasattr(visor, "set_punto_destino"):
            visor.set_punto_destino(opcion["coords"].x(), opcion["coords"].y())

        if navegar_a_gps and hasattr(self, "stack"):
            self.stack.setCurrentIndex(3)
            if hasattr(self, "actualizar_estado_menu") and hasattr(self, "btn_nav_gps"):
                self.actualizar_estado_menu(self.btn_nav_gps)

        if enfocar and visor:
            visor._zoom_manual_activo = False
            self._forzar_reencuadre_diferido(force=True)
            QTimer.singleShot(220, lambda p=opcion["coords"]: visor.centerOn(p))

        self._actualizar_piloto_rastreo(
            bool(activar_piloto), opcion.get("ubicacion") if activar_piloto else None
        )
        return True

    def _resolver_coordenadas_ubicacion(self, pasillo, estanteria):
        if not pasillo or not estanteria:
            return None
        try:
            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT mapa_x, mapa_y
                        FROM ubicaciones
                        WHERE pasillo = %s AND estanteria = %s
                          AND mapa_x IS NOT NULL AND mapa_y IS NOT NULL
                          AND (mapa_x != 0 OR mapa_y != 0)
                        ORDER BY (codigo_articulo IS NULL OR codigo_articulo = '') DESC,
                                 verificado DESC,
                                 id DESC
                        LIMIT 1
                        """,
                        (pasillo, estanteria),
                    )
                    res = cursor.fetchone()
            if not res:
                return None
            return QPointF(float(res[0]), float(res[1]))
        except Exception:
            return None

    def _obtener_opciones_destino_gps(self, termino):
        termino = (termino or "").strip().upper()
        if not termino:
            return []

        opciones = []
        try:
            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT codigo, nombre, ubicacion_tienda, pasillo, estanteria,
                               ubicacion_almacen, pasillo_almacen, estanteria_almacen
                        FROM articulos
                        WHERE codigo = %s OR nombre LIKE %s
                        ORDER BY CASE WHEN codigo = %s THEN 0 ELSE 1 END, nombre ASC
                        LIMIT 1
                        """,
                        (termino, f"%{termino}%", termino),
                    )
                    art = cursor.fetchone()

                    if art:
                        (
                            codigo,
                            nombre,
                            ubi_lin,
                            pas_lin,
                            est_lin,
                            ubi_alm,
                            pas_alm,
                            est_alm,
                        ) = art
                        for tipo, ubicacion_txt, pasillo, estanteria in [
                            ("LINEAL", ubi_lin, pas_lin, est_lin),
                            ("ALMACEN", ubi_alm, pas_alm, est_alm),
                        ]:
                            if not ubicacion_txt or not pasillo or not estanteria:
                                continue
                            punto = self._resolver_coordenadas_ubicacion(
                                pasillo, estanteria
                            )
                            opciones.append(
                                {
                                    "tipo": tipo,
                                    "nombre": str(nombre).upper(),
                                    "codigo": str(codigo).upper(),
                                    "ubicacion": str(ubicacion_txt).upper(),
                                    "coords": punto,
                                    "disponible": punto is not None,
                                }
                            )

                    if not opciones:
                        like_term = f"%{termino}%"
                        cursor.execute(
                            """
                            SELECT CONCAT_WS(' ', pasillo, estanteria, balda) AS nombre_ubicacion,
                                   mapa_x, mapa_y
                            FROM ubicaciones
                            WHERE (
                                CONCAT_WS(' ', pasillo, estanteria, balda) LIKE %s
                                OR CONCAT_WS('-', pasillo, estanteria, balda) LIKE %s
                                OR pasillo LIKE %s
                                OR estanteria LIKE %s
                            )
                              AND mapa_x IS NOT NULL AND mapa_y IS NOT NULL
                              AND (mapa_x != 0 OR mapa_y != 0)
                            ORDER BY verificado DESC, id DESC
                            LIMIT 6
                            """,
                            (like_term, like_term, like_term, like_term),
                        )
                        for nombre_ubi, mapa_x, mapa_y in cursor.fetchall():
                            opciones.append(
                                {
                                    "tipo": "UBICACION",
                                    "nombre": str(nombre_ubi).upper(),
                                    "codigo": "",
                                    "ubicacion": str(nombre_ubi).upper(),
                                    "coords": QPointF(float(mapa_x), float(mapa_y)),
                                    "disponible": True,
                                }
                            )
        except Exception as e:
            print(f"Error al resolver destinos GPS: {e}")

        pos_operario = getattr(getattr(self, "visor_mapa", None), "pos_operario", None)
        for opcion in opciones:
            opcion["distancia_m"] = (
                self._distancia_real_metros(pos_operario, opcion.get("coords"))
                if opcion.get("coords") is not None and pos_operario is not None
                else None
            )
        return opciones

    def _mostrar_selector_destino_gps(self, opciones):
        opciones = [op for op in (opciones or []) if op]
        if not opciones:
            return None
        if len(opciones) == 1 and opciones[0].get("disponible"):
            return opciones[0]

        dialogo = QDialog(self)
        dialogo.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        dialogo.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialogo.setModal(True)

        marco = QFrame(dialogo)
        marco.setObjectName("panel_selector_gps")
        marco.setStyleSheet(self._estilo_dialogo_neon("#00FFC6"))

        base = QVBoxLayout(dialogo)
        base.setContentsMargins(0, 0, 0, 0)
        base.addWidget(marco)

        layout = QVBoxLayout(marco)
        layout.setContentsMargins(26, 26, 26, 26)
        layout.setSpacing(14)

        titulo = QLabel(tr("ubic.route_dest_title", default="SELECCIONE EL DESTINO DE RUTA"))
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titulo.setFont(self._crear_fuente_segoe(12))
        titulo.setStyleSheet("color: #00FFC6; border: none;")
        layout.addWidget(titulo)

        subtitulo = QLabel(
            tr("ubic.route_dest_subtitle",
               default="El sistema muestra las ubicaciones disponibles del artículo para que el operario elija la ruta.")
        )
        subtitulo.setWordWrap(True)
        subtitulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitulo.setFont(self._crear_fuente_segoe(9))
        subtitulo.setStyleSheet("color: #C9D1D9; border: none;")
        layout.addWidget(subtitulo)

        seleccion = {"valor": None}

        for opcion in opciones:
            distancia = opcion.get("distancia_m")
            distancia_txt = (
                f"{distancia:.2f} m"
                if distancia is not None
                else tr("ubic.dist_after_locate", default="Distancia disponible tras localizar al operario")
            )
            estado_txt = (
                "" if opcion.get("disponible") else tr("ubic.no_coords", default=" · SIN COORDENADAS DISPONIBLES")
            )
            boton = QPushButton(
                f"{opcion['tipo']} · {opcion['ubicacion']}\n{distancia_txt}{estado_txt}"
            )
            boton.setMinimumHeight(62)
            boton.setCursor(Qt.CursorShape.PointingHandCursor)
            boton.setFont(self._crear_fuente_segoe(10))
            boton.setEnabled(bool(opcion.get("disponible")))
            boton.setStyleSheet(
                self._estilo_boton_neon(
                    bg="#161B22",
                    fg="#00FFC6" if opcion.get("disponible") else "#6E7681",
                    border="#00FFC6" if opcion.get("disponible") else "#30363D",
                    hover_bg="#00FFC6" if opcion.get("disponible") else "#161B22",
                    hover_fg="#0D1117" if opcion.get("disponible") else "#6E7681",
                    radius=12,
                    padding="12px 14px",
                    font_size=10,
                )
            )
            boton.clicked.connect(
                lambda _=False, op=opcion: (
                    seleccion.__setitem__("valor", op),
                    dialogo.accept(),
                )
            )
            layout.addWidget(boton)

        btn_cancelar = QPushButton(tr("ubic.cancel", default="CANCELAR"))
        btn_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancelar.setFont(self._crear_fuente_segoe(10))
        btn_cancelar.setStyleSheet(
            self._estilo_boton_neon(
                bg="#30363D",
                fg="#FFFFFF",
                border="#8B949E",
                hover_bg="#FFFFFF",
                hover_fg="#30363D",
            )
        )
        btn_cancelar.clicked.connect(dialogo.reject)
        layout.addWidget(btn_cancelar)

        self._aplicar_fuente_segoe(dialogo)
        dialogo.resize(560, max(280, 220 + (len(opciones) * 78)))
        return (
            seleccion["valor"]
            if dialogo.exec() == QDialog.DialogCode.Accepted
            else None
        )

    def _seleccionar_planta_borrado(self):
        try:
            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT planta_index
                        FROM configuracion_mapa
                        WHERE ruta_imagen IS NOT NULL AND ruta_imagen != ''
                        GROUP BY planta_index
                        ORDER BY planta_index ASC
                        """
                    )
                    plantas = [int(row[0]) for row in cursor.fetchall()]
        except Exception:
            plantas = []

        if not plantas:
            return None
        if len(plantas) == 1:
            return plantas[0]

        dialogo = QDialog(self)
        dialogo.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        dialogo.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialogo.setModal(True)

        marco = QFrame(dialogo)
        marco.setStyleSheet(self._estilo_dialogo_neon("#00F5FF"))
        base = QVBoxLayout(dialogo)
        base.setContentsMargins(0, 0, 0, 0)
        base.addWidget(marco)

        layout = QVBoxLayout(marco)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        titulo = QLabel(tr("ubic.select_floor_delete", default="SELECCIONE LA PLANTA A ELIMINAR"))
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titulo.setFont(self._crear_fuente_segoe(12))
        titulo.setStyleSheet("color: #00F5FF; border: none;")
        layout.addWidget(titulo)

        combo = QComboBox()
        combo.setFont(self._crear_fuente_segoe(10))
        combo.setCursor(Qt.CursorShape.PointingHandCursor)
        combo.addItems([tr("ubic.floor_label", default="PLANTA {n}", n=planta) for planta in plantas])
        combo.setStyleSheet(
            """
            QComboBox {
                background-color: #161B22;
                color: #E6EDF3;
                border: 1px solid #00F5FF;
                border-radius: 10px;
                padding: 10px 12px;
                font-family: 'Segoe UI';
                font-weight: 900;
            }
            QComboBox QAbstractItemView {
                background-color: #0D1117;
                color: #E6EDF3;
                border: 1px solid #00F5FF;
                selection-background-color: #00F5FF;
                selection-color: #0D1117;
                font-family: 'Segoe UI';
                font-weight: 900;
            }
            """
        )
        layout.addWidget(combo)

        fila = QHBoxLayout()
        btn_cancelar = QPushButton(tr("ubic.cancel", default="CANCELAR"))
        btn_confirmar = QPushButton(tr("ubic.continue", default="CONTINUAR"))
        for boton, color in [(btn_cancelar, "#8B949E"), (btn_confirmar, "#00F5FF")]:
            boton.setCursor(Qt.CursorShape.PointingHandCursor)
            boton.setFont(self._crear_fuente_segoe(10))
            boton.setStyleSheet(
                self._estilo_boton_neon(
                    bg="#161B22" if boton is btn_confirmar else "#30363D",
                    fg=color,
                    border=color,
                    hover_bg=color,
                    hover_fg="#0D1117" if boton is btn_confirmar else "#30363D",
                )
            )
            fila.addWidget(boton)
        layout.addLayout(fila)

        btn_cancelar.clicked.connect(dialogo.reject)
        btn_confirmar.clicked.connect(dialogo.accept)
        self._aplicar_fuente_segoe(dialogo)
        dialogo.resize(420, 210)

        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return None
        return plantas[combo.currentIndex()]

    def _blindar_popup_widget(self, widget):
        if not widget or getattr(widget, "_segui_popup_blindado", False):
            return
        widget._segui_popup_blindado = True
        self._aplicar_fuente_segoe(widget)

        estilo_extra = """
            QLabel {
                font-family: 'Segoe UI';
                font-weight: 900;
            }
            QPushButton {
                font-family: 'Segoe UI';
                font-weight: 900;
                border-radius: 10px;
            }
            QLineEdit, QTextEdit, QComboBox {
                font-family: 'Segoe UI';
                font-weight: 900;
                border-radius: 10px;
            }
            QListWidget, QTreeWidget {
                font-family: 'Segoe UI';
                font-weight: 900;
            }
        """

        if isinstance(widget, QMessageBox):
            widget.setWindowFlags(
                widget.windowFlags() | Qt.WindowType.FramelessWindowHint
            )
            widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            estilo_extra += """
                QMessageBox {
                    background-color: rgba(0, 0, 0, 0);
                    border: none;
                }
                QMessageBox QLabel {
                    color: #E6EDF3;
                    font-family: 'Segoe UI';
                    font-weight: 900;
                }
                QMessageBox QPushButton {
                    background-color: #161B22;
                    color: #00FFC6;
                    border: 1px solid #00FFC6;
                    border-radius: 10px;
                    padding: 8px 18px;
                }
                QMessageBox QPushButton:hover {
                    background-color: #00FFC6;
                    color: #0D1117;
                }
            """
        else:
            estilo_extra += """
                QDialog {
                    background-color: transparent;
                }
            """

        widget.setStyleSheet(f"{widget.styleSheet()}\n{estilo_extra}")

    def eventFilter(self, obj, event):
        try:
            if isinstance(obj, (QDialog, QMessageBox)) and event.type() in {
                QEvent.Type.Polish,
                QEvent.Type.Show,
            }:
                self._blindar_popup_widget(obj)
        except Exception:
            pass
        return super().eventFilter(obj, event)

    # ============================================================
    # BLOQUE SERIALIZACIÓN Y SNAPSHOTS DEL MAPA
    # ============================================================

    def _serializar_punto(self, punto):
        if punto is None:
            return None
        return {"x": round(float(punto.x()), 3), "y": round(float(punto.y()), 3)}

    def _deserializar_punto(self, data):
        if data is None:
            return None
        return QPointF(float(data["x"]), float(data["y"]))

    def _extraer_muros_vectores(self):
        visor = getattr(self, "visor_admin", None)
        if not visor:
            return []
        muros = []
        escena = QGraphicsView.scene(visor)
        for item in getattr(visor, "historial_muros", []):
            try:
                if item and item.scene() == escena and hasattr(item, "line"):
                    linea = item.line()
                    muros.append(
                        {
                            "x1": round(linea.x1(), 2),
                            "y1": round(linea.y1(), 2),
                            "x2": round(linea.x2(), 2),
                            "y2": round(linea.y2(), 2),
                        }
                    )
            except (AttributeError, RuntimeError):
                continue
        return muros

    def _snapshot_calibracion_actual(self):
        puntos = {
            "p_y_inicio": self._serializar_punto(getattr(self, "p_y_inicio", None)),
            "p_y_fin": self._serializar_punto(getattr(self, "p_y_fin", None)),
            "p_x_inicio": self._serializar_punto(getattr(self, "p_x_inicio", None)),
            "p_x_fin": self._serializar_punto(getattr(self, "p_x_fin", None)),
            "ratio_h": round(float(getattr(self.visor_admin, "ratio_px_m_h", 1.0)), 6),
            "ratio_v": round(float(getattr(self.visor_admin, "ratio_px_m_v", 1.0)), 6),
        }
        if any(puntos[k] for k in ("p_y_inicio", "p_y_fin", "p_x_inicio", "p_x_fin")):
            return puntos
        if puntos["ratio_h"] != 1.0 or puntos["ratio_v"] != 1.0:
            return puntos
        return None

    def _obtener_snapshot_mapa(self):
        visor = getattr(self, "visor_admin", None)
        return {
            "muros_vectores": self._extraer_muros_vectores(),
            "ancla": self._serializar_punto(getattr(visor, "punto_ancla", None)),
            "calibracion": self._snapshot_calibracion_actual(),
        }

    def _apilar_accion_mapa(self, tipo, before_state, after_state):
        if self._restaurando_historial or before_state == after_state:
            return
        estado = self._estado_planta()
        estado["undo"].append(
            {"tipo": tipo, "before": before_state, "after": after_state}
        )
        estado["redo"].clear()
        self._actualizar_botones_historial()

    def _actualizar_botones_historial(self):
        estado = self._estado_planta()
        btn_undo = getattr(self, "btn_deshacer_muro", None)
        btn_redo = getattr(self, "btn_rehacer_muro", None)
        if btn_undo:
            btn_undo.setEnabled(True)
            btn_undo.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_undo.setStyleSheet(
                self._estilo_boton_neon(
                    bg="#21262D" if estado["undo"] else "#161B22",
                    fg="#C9D1D9" if estado["undo"] else "#6E7681",
                    border="#30363D",
                    hover_bg="#C9D1D9" if estado["undo"] else "#30363D",
                    hover_fg="#21262D" if estado["undo"] else "#E6EDF3",
                )
            )
        if btn_redo:
            btn_redo.setEnabled(True)
            btn_redo.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_redo.setStyleSheet(
                self._estilo_boton_neon(
                    bg="#21262D" if estado["redo"] else "#161B22",
                    fg="#C9D1D9" if estado["redo"] else "#6E7681",
                    border="#30363D",
                    hover_bg="#C9D1D9" if estado["redo"] else "#30363D",
                    hover_fg="#21262D" if estado["redo"] else "#E6EDF3",
                )
            )

    def _limpiar_capas_editables(self):
        visor = getattr(self, "visor_admin", None)
        if not visor:
            return
        escena = QGraphicsView.scene(visor)
        if not escena:
            return

        for item in list(escena.items()):
            try:
                if str(item.data(0)) in {
                    "MURO_TECNICO",
                    "PIN_ORIGEN",
                    "CALIB_MARKER",
                    "CALIB_LINE",
                    "CALIB_PREVIEW",
                }:
                    escena.removeItem(item)
            except (RuntimeError, AttributeError):
                continue

        visor.historial_muros = []
        visor.linea_temporal_muro = None
        visor.linea_temporal_cal = None
        visor.punto_inicio_muro = None
        visor.punto_ancla = None
        visor.item_ancla = None
        visor.item_texto_ancla = None
        visor.grupo_marca_origen = []
        visor.linea_x = visor.linea_y = None
        visor.m_x1 = visor.m_x2 = visor.m_y1 = visor.m_y2 = None
        self.p_y_inicio = self.p_y_fin = None
        self.p_x_inicio = self.p_x_fin = None

    def _restaurar_calibracion_visual(self, calibracion):
        visor = getattr(self, "visor_admin", None)
        if not visor or not calibracion:
            return
        escena = QGraphicsView.scene(visor)
        if not escena:
            return

        color_y = QColor("#00F0FF")
        color_x = QColor("#FFEA00")
        radius = 6

        self.p_y_inicio = self._deserializar_punto(calibracion.get("p_y_inicio"))
        self.p_y_fin = self._deserializar_punto(calibracion.get("p_y_fin"))
        self.p_x_inicio = self._deserializar_punto(calibracion.get("p_x_inicio"))
        self.p_x_fin = self._deserializar_punto(calibracion.get("p_x_fin"))

        visor.ratio_px_m_h = float(
            calibracion.get("ratio_h", getattr(visor, "ratio_px_m_h", 1.0))
        )
        visor.ratio_px_m_v = float(
            calibracion.get("ratio_v", getattr(visor, "ratio_px_m_v", 1.0))
        )
        self.ratio_px_m_h = visor.ratio_px_m_h
        self.ratio_px_m_v = visor.ratio_px_m_v
        if hasattr(self, "visor_mapa") and self.visor_mapa:
            self.visor_mapa.ratio_px_m_h = visor.ratio_px_m_h
            self.visor_mapa.ratio_px_m_v = visor.ratio_px_m_v

        def crear_marcador(punto, color):
            item = escena.addEllipse(
                punto.x() - radius,
                punto.y() - radius,
                12,
                12,
                QPen(color, 2),
                QBrush(color),
            )
            item.setData(0, "CALIB_MARKER")
            item.setZValue(2200)
            return item

        def crear_linea(p1, p2, color):
            pen = QPen(color, 2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            item = escena.addLine(QLineF(p1, p2), pen)
            item.setData(0, "CALIB_LINE")
            item.setZValue(2100)
            return item

        if self.p_y_inicio:
            visor.m_y1 = crear_marcador(self.p_y_inicio, color_y)
        if self.p_y_fin:
            visor.m_y2 = crear_marcador(self.p_y_fin, color_y)
        if self.p_y_inicio and self.p_y_fin:
            visor.linea_y = crear_linea(self.p_y_inicio, self.p_y_fin, color_y)

        if self.p_x_inicio:
            visor.m_x1 = crear_marcador(self.p_x_inicio, color_x)
        if self.p_x_fin:
            visor.m_x2 = crear_marcador(self.p_x_fin, color_x)
        if self.p_x_inicio and self.p_x_fin:
            visor.linea_x = crear_linea(self.p_x_inicio, self.p_x_fin, color_x)

    def _reconstruir_muros_desde_vectores(self, muros_vectores):
        visor = getattr(self, "visor_admin", None)
        if not visor:
            return
        escena = QGraphicsView.scene(visor)
        if not escena:
            return
        pen = QPen(QColor("#FF4B4B"), 3, Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setCosmetic(True)
        visor.historial_muros = []
        for muro in muros_vectores or []:
            linea = escena.addLine(
                float(muro["x1"]),
                float(muro["y1"]),
                float(muro["x2"]),
                float(muro["y2"]),
                pen,
            )
            linea.setData(0, "MURO_TECNICO")
            linea.setZValue(180)
            linea.setVisible(bool(getattr(visor, "modo_pintar", False)))
            visor.historial_muros.append(linea)

    def _reconstruir_matriz_desde_historial(self):
        visor = getattr(self, "visor_admin", None)
        if not visor:
            return
        pixmap_item = getattr(visor, "pixmap_item", None) or getattr(
            self, "pixmap_item", None
        )
        if not pixmap_item:
            return
        rect = pixmap_item.boundingRect()
        size = max(1, int(getattr(visor, "celda_size", 20)))
        rows = max(1, int(rect.height() // size) + 1)
        cols = max(1, int(rect.width() // size) + 1)
        visor.matriz_obstaculos = np.zeros((rows, cols), dtype=np.uint8)
        for item in getattr(visor, "historial_muros", []):
            try:
                visor.marcar_muro_en_matriz(
                    item.line().p1(), item.line().p2(), es_muro_preciso=True
                )
            except (AttributeError, RuntimeError):
                continue
        if hasattr(self, "visor_mapa") and self.visor_mapa:
            self.visor_mapa.matriz_obstaculos = (
                None
                if visor.matriz_obstaculos is None
                else visor.matriz_obstaculos.copy()
            )

    # ============================================================
    # BLOQUE RECONSTRUCCIÓN Y SINCRONIZACIÓN DEL MAPA
    # ============================================================

    def reconstruir_estado_mapa_actual(self, estado=None, recuadrar=False):
        visor = getattr(self, "visor_admin", None)
        if not visor:
            return
        estado = estado or self._obtener_snapshot_mapa()
        self._restaurando_historial = True
        try:
            self._limpiar_capas_editables()
            self._restaurar_calibracion_visual(estado.get("calibracion"))
            ancla = self._deserializar_punto(estado.get("ancla"))
            if ancla:
                visor.dibujar_marca_origen(
                    ancla, registrar_historial=False, mostrar_guia=False
                )
            self._reconstruir_muros_desde_vectores(estado.get("muros_vectores", []))
            self._reconstruir_matriz_desde_historial()
        finally:
            self._restaurando_historial = False
        self.actualizar_estado_bloqueo()
        self._actualizar_botones_historial()
        if recuadrar:
            self.reencuadrar_plano(force=True)

    def reencuadrar_plano(self, force=False):
        """
        MÉTODO DE VENTANA (Director):
        Delega la responsabilidad del encuadre a los visores internos.
        """
        visores_activos = [
            getattr(self, "visor_admin", None),
            getattr(self, "visor_mapa", None),
        ]

        for visor in visores_activos:
            if visor is None:
                continue
            if hasattr(visor, "reencuadrar_plano"):
                try:
                    visor.reencuadrar_plano(force=force)
                except Exception as e:
                    print(f"⚠️ Error al reencuadrar un visor: {e}")
            else:
                # Fallback directo si el visor no tiene su propio método
                try:
                    escena = QGraphicsView.scene(visor)
                    if not escena:
                        continue
                    rect = escena.itemsBoundingRect()
                    if rect.isNull() or rect.isEmpty():
                        continue
                    visor.setSceneRect(rect)
                    visor.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
                    visor.centerOn(rect.center())
                    if visor.viewport():
                        visor.viewport().update()
                except Exception as e:
                    print(f"⚠️ Error en fallback reencuadre: {e}")

    # ============================================================
    # BLOQUE CONSTRUCCIÓN DE INTERFAZ
    # ============================================================

    def setup_ui(self):
        """Configuración de interfaz: Premium Dark y Navegación Sincronizada."""
        self.setWindowTitle(tr("ubic.window_title", default="SISTEMA DE UBICACIÓN Y GPS INTERNO - Smart Manager"))
        # Responsive (P2): mínimo apto para tablets landscape (antes 1280x850 bloqueaba
        # su uso en pantallas <1280). El editor sigue siendo una herramienta de escritorio/tablet.
        self.setMinimumSize(1024, 700)
        self.setFont(self._crear_fuente_segoe(10))

        # --- ESTILO RAÍZ ---
        self.setStyleSheet(
            """
            QWidget {
                font-family: 'Segoe UI';
                font-weight: 900;
            }
            QMainWindow, QWidget#fondo_principal, QStackedWidget#stack_principal {
                background-color: #0D1117;
            }
            QInputDialog, QMessageBox {
                background-color: #161B22;
                color: white;
                font-family: 'Segoe UI';
                font-weight: 900;
            }
            QLabel, QPushButton, QLineEdit, QTextEdit, QComboBox {
                font-family: 'Segoe UI';
                font-weight: 900;
            }
            QLineEdit, QTextEdit, QComboBox {
                background-color: #0D1117;
                border: 1px solid #30363D;
                border-radius: 10px;
                color: white;
                padding: 5px;
            }
            QStatusBar {
                background-color: #0D1117;
                color: #00FFC6;
                font-family: 'Segoe UI';
                font-weight: 900;
            }
            """
        )

        container = QWidget()
        container.setObjectName("fondo_principal")
        self.setCentralWidget(container)
        self.main_layout = QHBoxLayout(container)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # --- SIDEBAR ---
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar_logistica")
        self.sidebar.setFixedWidth(280)

        lyt_sidebar = QVBoxLayout(self.sidebar)
        lyt_sidebar.setContentsMargins(0, 40, 0, 40)
        lyt_sidebar.setSpacing(5)

        lbl_modulo = QLabel(tr("ubic.smart_logistics", default="Smart LOGISTICS"))
        lbl_modulo.setStyleSheet(
            "color: #ffffff; font-size: 16px; font-weight: 900; margin-left: 30px; "
            "margin-bottom: 35px; letter-spacing: 2px; border:none; background: transparent;"
        )
        lyt_sidebar.addWidget(lbl_modulo)

        # Botones de navegación
        self.btn_nav_lineal = QPushButton(tr("ubic.nav_lineal", default="ASIGNAR UBICACIÓN LINEAL"))
        self.btn_nav_almacen = QPushButton(tr("ubic.nav_almacen", default="ASIGNAR UBICACIÓN ALMACÉN"))
        self.btn_nav_busqueda = QPushButton(tr("ubic.nav_busqueda", default="BUSCAR PRODUCTO"))
        self.btn_nav_gps = QPushButton(tr("ubic.nav_gps", default="GPS INTERNO"))
        self.btn_nav_admin = QPushButton(tr("ubic.nav_admin", default="GESTIÓN ESTRUCTURA"))

        self.menu_botones = [
            self.btn_nav_lineal,
            self.btn_nav_almacen,
            self.btn_nav_busqueda,
            self.btn_nav_gps,
            self.btn_nav_admin,
        ]

        for btn in self.menu_botones:
            btn.setObjectName("btn_sidebar")
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(55)
            # CORRECCIÓN: Conectamos cada botón individual al método cambiar_seccion
            btn.clicked.connect(self.cambiar_seccion)
            lyt_sidebar.addWidget(btn)

        # Visibilidad por perfil
        perfil = (
            self.usuario_actual.get("perfil", "OPERARIO")
            if isinstance(self.usuario_actual, dict)
            else getattr(self.usuario_actual, "perfil", "OPERARIO")
        )
        self.btn_nav_admin.setVisible(perfil in ["ADMINISTRADOR", "GERENTE"])

        lyt_sidebar.addStretch()

        self.btn_volver = QPushButton(tr("ubic.exit", default="SALIR AL MENÚ"))
        self.btn_volver.setObjectName("btn_sidebar_exit")
        self.btn_volver.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_volver.setFixedHeight(55)
        self.btn_volver.clicked.connect(self.volver_menu_principal)
        lyt_sidebar.addWidget(self.btn_volver)

        # --- CONTENEDOR DE VISTAS ---
        self.stack = QStackedWidget()
        self.stack.setObjectName("stack_principal")

        # Inyectamos las vistas
        # IMPORTANTE: Estos métodos deben asegurar que self.btn_escala se inicialice internamente
        self.stack.addWidget(self.crear_vista_asignacion("LINEAL"))  # Index 0
        self.stack.addWidget(self.crear_vista_asignacion("ALMACÉN"))  # Index 1
        self.stack.addWidget(self.crear_vista_busqueda())  # Index 2
        self.stack.addWidget(self.crear_vista_gps())  # Index 3
        self.stack.addWidget(self.crear_vista_gestion_estructura())  # Index 4

        self.main_layout.addWidget(self.sidebar)
        self.main_layout.addWidget(self.stack)

        # Estado inicial
        self.btn_nav_lineal.setChecked(True)
        self._aplicar_fuente_segoe(container)
        self._actualizar_labels_planta()
        i18n.conectar_retraduccion(self, self._retraducir_ubic)

    def _retraducir_ubic(self):
        """Re-traduce el chrome de ventana y la navegación al cambiar de idioma.
        (Las vistas internas se irán añadiendo por fases.)"""
        self.setWindowTitle(tr("ubic.window_title", default="SISTEMA DE UBICACIÓN Y GPS INTERNO - Smart Manager"))
        self.btn_nav_lineal.setText(tr("ubic.nav_lineal", default="ASIGNAR UBICACIÓN LINEAL"))
        self.btn_nav_almacen.setText(tr("ubic.nav_almacen", default="ASIGNAR UBICACIÓN ALMACÉN"))
        self.btn_nav_busqueda.setText(tr("ubic.nav_busqueda", default="BUSCAR PRODUCTO"))
        self.btn_nav_gps.setText(tr("ubic.nav_gps", default="GPS INTERNO"))
        self.btn_nav_admin.setText(tr("ubic.nav_admin", default="GESTIÓN ESTRUCTURA"))
        self.btn_volver.setText(tr("ubic.exit", default="SALIR AL MENÚ"))

        # --- Panel GPS ---
        if hasattr(self, "lbl_gps_title"):
            self.lbl_gps_title.setText(tr("ubic.gps_title", default="SISTEMA DE POSICIONAMIENTO"))
        if hasattr(self, "btn_borrar_plano_gps"):
            self.btn_borrar_plano_gps.setText("🗑️ " + tr("ubic.btn_delete", default="BORRAR"))
        if hasattr(self, "btn_cargar_plano_gps"):
            self.btn_cargar_plano_gps.setText("📁 " + tr("ubic.btn_load", default="CARGAR"))
        if hasattr(self, "lbl_titulo_rastreo_gps"):
            self.lbl_titulo_rastreo_gps.setText(tr("ubic.pilot", default="PILOTO DE NAVEGACION"))
        if hasattr(self, "btn_iniciar_ruta"):
            self.btn_iniciar_ruta.setText("🚀 " + tr("ubic.start_route", default="INICIAR RUTA"))

        # --- Panel UBICAR ACTIVOS ---
        if hasattr(self, "lbl_repo"):
            self.lbl_repo.setText(tr("ubic.locate_assets", default="UBICAR ACTIVOS"))
        if hasattr(self, "btn_ubicar_activo"):
            self.btn_ubicar_activo.setText("📍 " + tr("ubic.btn_locate_shelf", default="UBICAR\nESTANTERÍA"))
        if hasattr(self, "btn_crear_satelite"):
            self.btn_crear_satelite.setText("🛰️ " + tr("ubic.btn_install_sat", default="INSTALAR\nSATÉLITE"))
        if hasattr(self, "btn_ver_qrs"):
            self.btn_ver_qrs.setText("📂 " + tr("ubic.btn_view_qr", default="VER\nCÓDIGOS QR"))
        if hasattr(self, "btn_guardar"):
            self.btn_guardar.setText("✅ " + tr("ubic.save_finish", default="FINALIZAR Y GUARDAR"))

        # Refrescar textos dinámicos (planta actual / estado de rastreo)
        try:
            self._actualizar_labels_planta()
        except Exception:
            pass
        try:
            self._actualizar_piloto_rastreo(getattr(self.visor_mapa, "rastreo_en_vivo_activo", False)
                                            if hasattr(self, "visor_mapa") and self.visor_mapa else False)
        except Exception:
            pass

    # ============================================================
    # BLOQUE CARGA Y GESTIÓN DE PLANOS
    # ============================================================

    def _pedir_titulo_plano(self):
        """Neon-styled dialog for entering a plan title. Returns the string or None if cancelled."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QDialog,
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QVBoxLayout,
        )

        diag = QDialog(self)
        diag.setFixedSize(480, 230)
        diag.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        diag.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        ml = QVBoxLayout(diag)
        ml.setContentsMargins(0, 0, 0, 0)

        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background-color: #0D1117; border: 2px solid #00FFC6; border-radius: 18px; }"
            " QLabel { color: #E6EDF3; border: none; background: transparent; }"
        )
        il = QVBoxLayout(frame)
        il.setContentsMargins(30, 24, 30, 24)
        il.setSpacing(14)

        lbl_t = QLabel(tr("ubic.plan_title_q", default="Por favor, introduzca un título para el plano"))
        lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_t.setWordWrap(True)
        lbl_t.setStyleSheet(
            "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900;"
            " font-size: 17px; letter-spacing: 1px; border: none; background: transparent;"
        )

        inp = QLineEdit()
        inp.setPlaceholderText(tr("ubic.plan_title_ph", default="Ej: Planta 1, Almacén Central..."))
        inp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inp.setFixedHeight(44)
        inp.setStyleSheet(
            "QLineEdit { background-color: #161B22; color: #E6EDF3;"
            " border: 2px solid #00FFC6; border-radius: 10px;"
            " font-family: 'Segoe UI'; font-weight: 700; font-size: 17px; padding: 0 12px; }"
            " QLineEdit:focus { border: 2px solid #00FFE0; background-color: #1C2128; }"
        )

        br = QHBoxLayout()
        br.setSpacing(12)

        btn_c = QPushButton(tr("common.cancel", default="Cancelar"))
        btn_c.setFixedHeight(40)
        btn_c.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_c.setStyleSheet(
            "QPushButton { background-color: #21262D; color: #8B949E;"
            " border: 1px solid #30363D; border-radius: 10px;"
            " font-family: 'Segoe UI'; font-weight: 900; font-size: 16px; }"
            " QPushButton:hover { background-color: #FFFFFF; color: #0D1117; border: 1px solid #FFFFFF; }"
        )
        btn_c.clicked.connect(diag.reject)

        btn_ok = QPushButton(tr("common.accept", default="Aceptar"))
        btn_ok.setFixedHeight(40)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setStyleSheet(
            "QPushButton { background-color: #0D1117; color: #00FFC6;"
            " border: 2px solid #00FFC6; border-radius: 10px;"
            " font-family: 'Segoe UI'; font-weight: 900; font-size: 16px; }"
            " QPushButton:hover { background-color: #00FFC6; color: #0D1117; border: 2px solid #00FFC6; }"
        )
        btn_ok.clicked.connect(diag.accept)
        inp.returnPressed.connect(diag.accept)

        br.addWidget(btn_c)
        br.addWidget(btn_ok)
        il.addWidget(lbl_t)
        il.addWidget(inp)
        il.addStretch()
        il.addLayout(br)
        ml.addWidget(frame)

        if diag.exec() == QDialog.DialogCode.Accepted:
            titulo = inp.text().strip()
            return titulo if titulo else tr("ubic.untitled", default="Sin título")
        return None

    def _esta_calibrado_planta(self, planta_idx):
        """Returns True if the given planta_index has a calibration (escala_px_metro > 0) in DB."""
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT escala_px_metro FROM configuracion_mapa WHERE planta_index = %s",
                        (planta_idx,),
                    )
                    row = cursor.fetchone()
                    return row is not None and float(row[0] or 0) > 0
        except Exception:
            return False

    def _clic_boton_escala(self):
        """Stateless calibration button handler — delegates based on current plan's DB state."""
        if self._esta_calibrado_planta(getattr(self, "planta_actual", 0)):
            self._mostrar_dialogo_reset_calibracion()
        else:
            self.iniciar_calibracion_escala()

    def _mostrar_dialogo_reset_calibracion(self):
        """Window-level reset dialog (replaces the VistaMapa closure)."""
        from PyQt6 import sip
        from PyQt6.QtCore import Qt as _Qt
        from PyQt6.QtWidgets import (
            QDialog,
            QFrame,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QVBoxLayout,
        )

        from src.db.conexion import obtener_conexion

        diag = QDialog(self)
        diag.setFixedSize(460, 220)
        diag.setWindowFlags(_Qt.WindowType.FramelessWindowHint | _Qt.WindowType.Dialog)
        diag.setAttribute(_Qt.WidgetAttribute.WA_TranslucentBackground)

        ml = QVBoxLayout(diag)
        ml.setContentsMargins(0, 0, 0, 0)

        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background-color: #0D1117; border: 2px solid #FF7B72; border-radius: 18px; }"
            " QLabel { color: #E6EDF3; border: none; background: transparent; }"
        )
        il = QVBoxLayout(frame)
        il.setContentsMargins(30, 24, 30, 24)
        il.setSpacing(12)

        lbl_t = QLabel("⚠️  " + tr("ubic.undo_calib_title", default="DESHACER CALIBRACIÓN"))
        lbl_t.setAlignment(_Qt.AlignmentFlag.AlignCenter)
        lbl_t.setStyleSheet(
            "color: #FF7B72; font-family: 'Segoe UI'; font-weight: 900;"
            " font-size: 16px; letter-spacing: 1px; border: none; background: transparent;"
        )

        lbl_m = QLabel(
            tr("ubic.undo_calib_msg",
               default="¿Desea deshacer la calibración de este plano?\nSe borrarán: escala, origen y muros.")
        )
        lbl_m.setAlignment(_Qt.AlignmentFlag.AlignCenter)
        lbl_m.setWordWrap(True)
        lbl_m.setStyleSheet(
            "color: #C9D1D9; font-family: 'Segoe UI'; font-weight: 700;"
            " font-size: 14px; border: none; background: transparent;"
        )

        br = QHBoxLayout()
        br.setSpacing(12)

        btn_no = QPushButton(tr("common.cancel", default="Cancelar"))
        btn_no.setFixedHeight(40)
        btn_no.setCursor(_Qt.CursorShape.PointingHandCursor)
        btn_no.setStyleSheet(
            "QPushButton { background-color: #21262D; color: #8B949E;"
            " border: 1px solid #30363D; border-radius: 10px;"
            " font-family: 'Segoe UI'; font-weight: 900; font-size: 14px; }"
            " QPushButton:hover { background-color: #FFFFFF; color: #0D1117; border: 1px solid #FFFFFF; }"
        )
        btn_no.clicked.connect(diag.reject)

        btn_si = QPushButton(tr("common.accept", default="Aceptar"))
        btn_si.setFixedHeight(40)
        btn_si.setCursor(_Qt.CursorShape.PointingHandCursor)
        btn_si.setStyleSheet(
            "QPushButton { background-color: #FF7B72; color: #0D1117;"
            " border: none; border-radius: 10px;"
            " font-family: 'Segoe UI'; font-weight: 900; font-size: 14px; }"
            " QPushButton:hover { background-color: #FFFFFF; color: #0D1117; }"
        )
        btn_si.clicked.connect(diag.accept)

        br.addWidget(btn_no)
        br.addWidget(btn_si)
        il.addWidget(lbl_t)
        il.addWidget(lbl_m)
        il.addStretch()
        il.addLayout(br)
        ml.addWidget(frame)

        if diag.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            p_idx = getattr(self, "planta_actual", 0)
            with obtener_conexion() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE configuracion_mapa "
                        "SET escala_px_metro=0, ancla_x=0, ancla_y=0, "
                        "    matriz_binaria=NULL, muros_vectoriales='[]' "
                        "WHERE planta_index=%s",
                        (p_idx,),
                    )
                    conn.commit()

            self.paso_calibracion = 1
            for v in [getattr(self, "visor_admin", None), getattr(self, "visor_mapa", None)]:
                if v:
                    v.ratio_px_m_h = v.ratio_px_m_v = 1.0
                    v.punto_ancla = None

            escena = getattr(self, "escena_compartida", None)
            if escena:
                for item in list(escena.items()):
                    try:
                        if not sip.isdeleted(item) and str(item.data(0)) in ["MURO_TECNICO", "PIN_ORIGEN"]:
                            escena.removeItem(item)
                    except Exception:
                        pass

            btn = getattr(self, "btn_escala", None)
            if btn:
                btn.setText("📏 " + tr("ubic.calib_scale", default="CALIBRAR ESCALA"))
                btn.setStyleSheet(
                    "QPushButton { background-color: #2EA043; color: white;"
                    " font-weight: 900; border-radius: 8px; border: 1px solid #3FB950;"
                    " padding: 8px; font-family: 'Segoe UI'; font-size: 12px; }"
                    " QPushButton:hover { background-color: #3FB950; }"
                )

            if self.statusBar():
                self.statusBar().showMessage("🔄 " + tr("ubic.calib_reset_status", default="Calibración reseteada."), 3000)

        except Exception as e:
            print(f"❌ Error en reset calibración: {e}")

    def _dialogo_neon_info(self, titulo, mensaje, color="#00FFC6", ancho=460, alto=200):
        """Simple neon info dialog with a single ACEPTAR button."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QDialog,
            QFrame,
            QLabel,
            QPushButton,
            QVBoxLayout,
        )

        diag = QDialog(self)
        diag.setFixedSize(ancho, alto)
        diag.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        diag.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        ml = QVBoxLayout(diag)
        ml.setContentsMargins(0, 0, 0, 0)

        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background-color: #0D1117; border: 2px solid {color}; border-radius: 18px; }}"
            " QLabel { color: #E6EDF3; border: none; background: transparent; }"
        )
        il = QVBoxLayout(frame)
        il.setContentsMargins(30, 24, 30, 24)
        il.setSpacing(12)

        lbl_t = QLabel(titulo)
        lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_t.setStyleSheet(
            f"color: {color}; font-family: 'Segoe UI'; font-weight: 900;"
            " font-size: 16px; letter-spacing: 1px; border: none; background: transparent;"
        )

        lbl_m = QLabel(mensaje)
        lbl_m.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_m.setWordWrap(True)
        lbl_m.setTextFormat(Qt.TextFormat.RichText)
        lbl_m.setStyleSheet(
            "color: #C9D1D9; font-family: 'Segoe UI'; font-weight: 700;"
            " font-size: 14px; border: none; background: transparent;"
        )

        btn_ok = QPushButton(tr("common.accept", default="Aceptar"))
        btn_ok.setFixedHeight(40)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setStyleSheet(
            f"QPushButton {{ background-color: {color}; color: #0D1117;"
            " border: none; border-radius: 10px;"
            " font-family: 'Segoe UI'; font-weight: 900; font-size: 14px; }"
            " QPushButton:hover { background-color: #FFFFFF; color: #0D1117; }"
        )
        btn_ok.clicked.connect(diag.accept)

        il.addWidget(lbl_t)
        il.addWidget(lbl_m)
        il.addStretch()
        il.addWidget(btn_ok, alignment=Qt.AlignmentFlag.AlignCenter)
        ml.addWidget(frame)

        diag.exec()

    def _dialogo_neon_pregunta(self, titulo, mensaje, btn_ok_txt="Añadir", btn_cancel_txt="Cancelar", color="#00FFC6", ancho=480, alto=210):
        """Neon two-button confirmation dialog. Returns True if confirmed."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QDialog,
            QFrame,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QVBoxLayout,
        )

        diag = QDialog(self)
        diag.setFixedSize(ancho, alto)
        diag.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        diag.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        ml = QVBoxLayout(diag)
        ml.setContentsMargins(0, 0, 0, 0)

        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background-color: #0D1117; border: 2px solid {color}; border-radius: 18px; }}"
            " QLabel { color: #E6EDF3; border: none; background: transparent; }"
        )
        il = QVBoxLayout(frame)
        il.setContentsMargins(30, 24, 30, 24)
        il.setSpacing(12)

        lbl_t = QLabel(titulo)
        lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_t.setStyleSheet(
            f"color: {color}; font-family: 'Segoe UI'; font-weight: 900;"
            " font-size: 16px; letter-spacing: 1px; border: none; background: transparent;"
        )

        lbl_m = QLabel(mensaje)
        lbl_m.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_m.setWordWrap(True)
        lbl_m.setStyleSheet(
            "color: #C9D1D9; font-family: 'Segoe UI'; font-weight: 700;"
            " font-size: 14px; border: none; background: transparent;"
        )

        br = QHBoxLayout()
        br.setSpacing(12)

        btn_c = QPushButton(btn_cancel_txt)
        btn_c.setFixedHeight(40)
        btn_c.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_c.setStyleSheet(
            "QPushButton { background-color: #21262D; color: #8B949E;"
            " border: 1px solid #30363D; border-radius: 10px;"
            " font-family: 'Segoe UI'; font-weight: 900; font-size: 14px; }"
            " QPushButton:hover { background-color: #FFFFFF; color: #0D1117; border: 1px solid #FFFFFF; }"
        )
        btn_c.clicked.connect(diag.reject)

        btn_ok = QPushButton(btn_ok_txt)
        btn_ok.setFixedHeight(40)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setStyleSheet(
            f"QPushButton {{ background-color: {color}; color: #0D1117;"
            " border: none; border-radius: 10px;"
            " font-family: 'Segoe UI'; font-weight: 900; font-size: 14px; }"
            " QPushButton:hover { background-color: #FFFFFF; color: #0D1117; }"
        )
        btn_ok.clicked.connect(diag.accept)

        br.addWidget(btn_c)
        br.addWidget(btn_ok)
        il.addWidget(lbl_t)
        il.addWidget(lbl_m)
        il.addStretch()
        il.addLayout(br)
        ml.addWidget(frame)

        return diag.exec() == QDialog.DialogCode.Accepted

    def cargar_plano(self, ruta_directa=None):
        """
        UNIFICADO: Orquestador integral de carga de infraestructura.
        Corrige: Apertura de carpeta raíz y encuadre total del visor.
        """
        import os
        import tempfile

        from PyQt6.QtCore import Qt, QTimer
        from PyQt6.QtWidgets import (
            QApplication,
            QGraphicsPixmapItem,
            QGraphicsView,
        )

        from src.db.conexion import obtener_conexion

        # --- 0. PRE-CHECKS before opening the OS file picker ---
        titulo_plano = None
        planta_idx_destino = getattr(self, "planta_actual", 0)

        if not ruta_directa:
            # Find the last loaded plan index
            _max_cargado = None
            try:
                with obtener_conexion() as _conn:
                    with _conn.cursor() as _cur:
                        _cur.execute(
                            "SELECT MAX(planta_index) FROM configuracion_mapa "
                            "WHERE ruta_imagen IS NOT NULL AND ruta_imagen != ''"
                        )
                        _row = _cur.fetchone()
                        _max_cargado = _row[0] if _row and _row[0] is not None else None
            except Exception:
                pass

            if _max_cargado is not None:
                # Block immediately if the last loaded plan is not yet calibrated
                if not self._esta_calibrado_planta(_max_cargado):
                    self._dialogo_neon_info(
                        "ℹ️  CALIBRACIÓN PENDIENTE",
                        "Antes debe calibrar las dimensiones del último plano cargado.",
                        color="#00B4D8",
                        alto=190,
                    )
                    return

                # Ask whether to add another floor
                if not self._dialogo_neon_pregunta(
                    "PLANO YA CARGADO",
                    "Ya hay un plano cargado.\n¿Desea añadir otra planta o los planos del almacén?",
                    btn_ok_txt="Añadir",
                    btn_cancel_txt="Cancelar",
                    color="#00FFC6",
                ):
                    return

                planta_idx_destino = _max_cargado + 1

        # --- 1. SELECCIÓN DE ARCHIVO (Corrección de Carpeta) ---
        ruta_seleccionada = ruta_directa
        if not ruta_seleccionada:
            # Aseguramos la ruta absoluta desde la raíz del proyecto
            base_dir = os.path.abspath(os.getcwd())
            directorio_planos = os.path.join(base_dir, "documentos", "planos")
            os.makedirs(directorio_planos, exist_ok=True)

            file_dialog = QFileDialog(self)
            file_dialog.setWindowTitle(tr("ubic.select_infra", default="SELECCIONAR INFRAESTRUCTURA"))
            # Forzamos a QFileDialog a abrir la carpeta específica
            file_dialog.setDirectory(directorio_planos)
            file_dialog.setNameFilters(["Planos (*.png *.jpg *.jpeg *.pdf)"])
            file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)

            if file_dialog.exec():
                rutas = file_dialog.selectedFiles()
                if rutas:
                    ruta_seleccionada = rutas[0]

        if not ruta_seleccionada or not os.path.exists(ruta_seleccionada):
            return

        # --- TITLE + TYPE (after file selection, before loading) ---
        tipo_plano = "LOCAL"
        if not ruta_directa:
            titulo_plano = self._pedir_titulo_plano()
            if titulo_plano is None:
                return
            tipo_plano = self._pedir_tipo_plano()
            if tipo_plano is None:
                return

        self._resetear_navegacion_gps(limpiar_operario=True)

        # --- 2. PROCESAMIENTO PDF -> PNG ---
        ext = os.path.splitext(ruta_seleccionada)[1].lower()
        ruta_final_proceso = ruta_seleccionada
        if ext == ".pdf":
            try:
                import fitz

                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                doc = fitz.open(ruta_seleccionada)
                # 300 DPI (Matrix 3,3) para no perder calidad técnica
                pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(3, 3))
                ruta_temp = os.path.join(
                    tempfile.gettempdir(), f"plano_conv_{os.getpid()}.png"
                )
                pix.save(ruta_temp)
                ruta_final_proceso = ruta_temp
                doc.close()
            except Exception as e:
                print(f"❌ Error PDF: {e}")
                return
            finally:
                QApplication.restoreOverrideCursor()

        # --- 3. LIMPIEZA Y PREPARACIÓN DE ESCENA ---
        escena = getattr(self, "escena_compartida", None)
        if not escena:
            return
        p_idx = planta_idx_destino
        self.planta_actual = p_idx

        escena.clear()
        escena.invalidate(escena.sceneRect(), QGraphicsScene.SceneLayer.AllLayers)

        # --- 4. PERSISTENCIA Y RENDERIZADO ---
        nombre_archivo = os.path.basename(
            ruta_seleccionada if ext != ".pdf" else ruta_final_proceso
        )
        ruta_dest_final = os.path.join(
            os.getcwd(), "documentos", "planos", nombre_archivo
        )

        try:
            if os.path.abspath(ruta_final_proceso) != os.path.abspath(ruta_dest_final):
                shutil.copy2(ruta_final_proceso, ruta_dest_final)
        except:
            pass

        pixmap = QPixmap(ruta_dest_final)
        if pixmap.isNull():
            print("❌ Error: Pixmap nulo. La imagen no se pudo cargar.")
            return

        self.ruta_actual = ruta_dest_final
        self.ultimo_plano_cargado = ruta_dest_final
        item_fondo = QGraphicsPixmapItem(pixmap)
        item_fondo.setData(0, "FONDO_MAPA")
        item_fondo.setZValue(-10000)
        item_fondo.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        escena.addItem(item_fondo)

        # --- 5. SINCRONIZACIÓN DE VISORES ---
        for v in [self.visor_admin, self.visor_mapa]:
            if v:
                v.pixmap_item = item_fondo
                v.ruta_actual = ruta_dest_final
                v._zoom_manual_activo = False
                v.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
                v.setInteractive(True)
                # Eliminar barras de desplazamiento para evitar recortes visuales
                v.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                v.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # --- 6. AJUSTE DE ESCENA Y AUTO-ZOOM (Corrección de plano cortado) ---
        # Definimos el área de la escena EXACTAMENTE igual al tamaño del plano
        rect_plano = item_fondo.boundingRect()
        escena.setSceneRect(rect_plano)

        # Sincronizar DB
        try:
            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    # Ensure titulo_plano and tipo columns exist (idempotent for existing DBs)
                    for _alter in (
                        "ALTER TABLE configuracion_mapa ADD COLUMN IF NOT EXISTS titulo_plano VARCHAR(255) DEFAULT NULL",
                        "ALTER TABLE configuracion_mapa ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) DEFAULT 'LOCAL'",
                    ):
                        try:
                            cursor.execute(_alter)
                        except Exception:
                            pass
                    cursor.execute(
                        """
                        INSERT INTO configuracion_mapa
                            (planta_index, ruta_imagen, titulo_plano, tipo, escala_px_metro, fecha_actualizacion)
                        VALUES (%s, %s, %s, %s, 0, NOW())
                        ON DUPLICATE KEY UPDATE
                            ruta_imagen = VALUES(ruta_imagen),
                            titulo_plano = COALESCE(VALUES(titulo_plano), titulo_plano),
                            tipo = COALESCE(VALUES(tipo), tipo),
                            escala_px_metro = 0
                    """,
                        (p_idx, nombre_archivo, titulo_plano, tipo_plano),
                    )
                conn.commit()
        except Exception as e:
            print(f"❌ DB Error: {e}")

        # Función de encuadre quirúrgico
        def aplicar_encuadre_perfecto():
            self.reencuadrar_plano(force=True)

        # Múltiples pasadas con delays crecientes para cubrir layouts tardíos
        self._forzar_reencuadre_diferido(force=True)
        for _d in (100, 400, 800, 1200, 2000):
            QTimer.singleShot(_d, aplicar_encuadre_perfecto)

        # Feedback HUD
        if hasattr(self, "lbl_planta_actual"):
            self.lbl_planta_actual.raise_()

        self._actualizar_labels_planta()
        self.mostrar_mensaje_temporal(tr("ubic.map_adjusted", default="MAPA AJUSTADO AL 100%: {archivo}", archivo=nombre_archivo))

        # Success message only for user-initiated loads
        if not ruta_directa:
            self._dialogo_neon_info(
                "✅  PLANO CARGADO",
                "El plano ha sido cargado correctamente.<br><br>"
                "Ahora calibre las dimensiones del plano en la pestaña "
                "<b>Gestión Estructura</b>.",
                color="#2EA043",
                ancho=480,
                alto=215,
            )

    def ajustar_zoom(self, factor):
        """
        Zoom controlado por software (botones +/-).
        AJUSTE: Validación de escena y anclaje central para evitar 'saltos' visuales.
        """
        from PyQt6.QtWidgets import QGraphicsView

        if hasattr(self, "visor_admin") and self.visor_admin:
            # 1. Verificamos que haya contenido que escalar
            escena = QGraphicsView.scene(self.visor_admin)
            if not escena or escena.itemsBoundingRect().isNull():
                return

            # 2. Fijamos el anclaje al centro para mantener la referencia visual
            self.visor_admin.setTransformationAnchor(
                QGraphicsView.ViewportAnchor.AnchorViewCenter
            )

            # 3. Aplicamos la transformación
            self.visor_admin.scale(factor, factor)

            # 4. Refresco forzado del viewport
            if self.visor_admin.viewport():
                self.visor_admin.viewport().update()

    def reposicionar_flechas(self):
        """
        Ajusta la posición de las flechas si se usaran coordenadas absolutas.
        AJUSTE QUIRÚRGICO: Eliminación de self.ui y adaptación a referencias directas.
        """
        # Verificamos que existan las flechas y al menos el visor de admin
        if (
            hasattr(self, "btn_planta_prev")
            and hasattr(self, "visor_admin")
            and self.visor_admin
        ):
            try:
                # Usamos directamente self.visor_admin (ya no self.ui.visor_admin)
                ancho_v = self.visor_admin.width()
                alto_v = self.visor_admin.height()
                alto_btn = self.btn_planta_prev.height()

                # NOTA: Al usar Layouts, el método .move() suele ser ignorado por Qt,
                # pero mantenemos la lógica por compatibilidad si cambias el contenedor.

                # Izquierda: margen de 10px, centrado vertical
                self.btn_planta_prev.move(10, (alto_v // 2) - (alto_btn // 2))

                # Derecha: margen de 10px desde el borde derecho, centrado vertical
                # Ajustado a 45 para el ancho de tus nuevos botones
                self.btn_planta_next.move(ancho_v - 45, (alto_v // 2) - (alto_btn // 2))

            except Exception as e:
                print(
                    f"DEBUG: Error menor al reposicionar flechas (probablemente layout activo): {e}"
                )

    def ajustar_zoom(self, factor):
        """
        Zoom sincronizado para ambos visores.
        Prioriza la navegación manual y evita que el auto-encuadre lo pise.
        """
        from PyQt6.QtWidgets import QGraphicsView

        for visor in [
            getattr(self, "visor_admin", None),
            getattr(self, "visor_mapa", None),
        ]:
            if not visor:
                continue
            escena = QGraphicsView.scene(visor)
            if not escena or escena.itemsBoundingRect().isNull():
                continue
            visor.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
            visor._zoom_manual_activo = True
            visor.scale(factor, factor)
            if visor.viewport():
                visor.viewport().update()

    def borrar_plano_actual(self):
        """
        Limpia la escena, elimina el registro en MariaDB y resetea la persistencia.
        AJUSTE FINAL: Limpieza total de visor, esquinas redondeadas y SQL planta_index.
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QMessageBox

        from src.db.conexion import obtener_conexion

        # 1. IDENTIFICAR PLANTA ACTUAL
        planta_idx = getattr(self, "planta_actual", 0)

        # 2. CONSTRUCCIÓN DEL DIÁLOGO PREMIUM
        msg = QMessageBox(self)
        # IMPORTANTE: FramelessWindowHint permite que las esquinas se vean redondeadas
        msg.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText(
            f"⚠️ ¿ELIMINAR PERMANENTEMENTE PLANTA {planta_idx}?\n\n"
            "ESTA ACCIÓN BORRARÁ EL PLANO, LOS MUROS TÉCNICOS Y LAS MATRICES DE NAVEGACIÓN."
        )

        # Estilo Neón Turquesa con Bordes Redondeados Reales
        msg.setStyleSheet(
            """
            QMessageBox {
                background-color: #0A0A0A;
                border: 2px solid #00F5FF;
                border-radius: 20px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI';
                font-weight: 900;
                font-size: 14px;
                padding: 15px;
            }
            QPushButton {
                background-color: #1A1A1A;
                color: #00F5FF;
                border: 1px solid #00F5FF;
                border-radius: 8px;
                padding: 10px 20px;
                font-family: 'Segoe UI';
                font-weight: 900;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #00F5FF;
                color: #000000;
            }
        """
        )

        btn_si = msg.addButton(tr("ubic.yes_delete", default="SÍ, ELIMINAR"), QMessageBox.ButtonRole.YesRole)
        btn_no = msg.addButton(tr("ubic.cancel", default="CANCELAR"), QMessageBox.ButtonRole.NoRole)
        btn_si.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_no.setCursor(Qt.CursorShape.PointingHandCursor)

        msg.exec()

        if msg.clickedButton() == btn_si:
            try:
                # 3. ELIMINACIÓN EN DB (Usando planta_index)
                with obtener_conexion() as conn:
                    with conn.cursor() as cursor:
                        query = "DELETE FROM configuracion_mapa WHERE planta_index = %s"
                        cursor.execute(query, (planta_idx,))
                        conn.commit()

                # 4. LIMPIEZA RADICAL DE ESCENA (Lo que ves en pantalla)
                # Buscamos el visor ya sea en self o en self.visor_admin
                visor = getattr(self, "visor_admin", self)
                escena = QGraphicsView.scene(visor)

                if escena:
                    escena.clear()  # Borra todos los items (plano, muros, etc)
                    escena.setSceneRect(
                        0, 0, 1, 1
                    )  # Reduce el área de scroll al mínimo

                # 5. RESETEO DE ESTADO EN MEMORIA
                visores = []
                if hasattr(self, "visor_admin"):
                    visores.append(self.visor_admin)
                if hasattr(self, "visor_mapa"):
                    visores.append(self.visor_mapa)

                for v in visores:
                    if v:
                        v.ruta_actual = ""
                        v.matriz_obstaculos = None
                        if hasattr(v, "historial_muros"):
                            v.historial_muros.clear()
                        # Forzar refresco visual a negro/vacío
                        if v.viewport():
                            v.viewport().update()

                # 6. RETORNO O REFRESCO
                if planta_idx != 0:
                    self.planta_actual = 0
                    self._actualizar_labels_planta()
                    self.mostrar_mensaje_temporal(
                        "☢️ " + tr("ubic.purge_complete", default="PURGA COMPLETA — VISOR LIMPIO")
                    )
                    if hasattr(self, "cargar_infraestructura_registrada"):
                        self.cargar_infraestructura_registrada()
                else:
                    self.mostrar_mensaje_temporal(
                        "✅ " + tr("ubic.base_map_deleted", default="MAPA BASE ELIMINADO Y VISOR LIMPIO")
                    )

            except Exception as e:
                print(f"❌ Error en purga de datos: {e}")

    def crear_vista_gps(self):
        """
        Vista GPS Operario: Sistema de navegación de alto rendimiento.
        AJUSTE: Estética neón unificada, cursores de mano y navegación multi-planta.
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QFrame,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QVBoxLayout,
            QWidget,
        )

        vista = QWidget()
        layout = QVBoxLayout(vista)
        layout.setContentsMargins(30, 20, 30, 30)
        layout.setSpacing(25)

        # --- 1. HEADER (Título + Planta Dinámica) ---
        header_container = QFrame()
        header_container.setStyleSheet("background: transparent; border: none;")
        header_lyt = QHBoxLayout(header_container)
        header_lyt.setContentsMargins(0, 0, 0, 0)

        # Título Principal
        self.lbl_gps_title = header_title = QLabel(tr("ubic.gps_title", default="SISTEMA DE POSICIONAMIENTO"))
        header_title.setStyleSheet(
            """
            color: #FFFFFF; 
            font-family: 'Segoe UI'; 
            font-size: 20px; 
            font-weight: 900; 
            letter-spacing: 1px;
        """
        )

        # Label de Planta (El "GPS" del operario)
        idx_p = getattr(self, "planta_actual", 0)
        self.lbl_planta_actual_gps = QLabel("📍 " + tr("ubic.no_plan", default="SIN PLANO"))
        self.lbl_planta_actual_gps.setStyleSheet(
            """
            color: #00F5FF; 
            font-family: 'Segoe UI'; 
            font-weight: 900; 
            font-size: 16px; 
            margin-left: 15px;
            padding: 4px 12px;
            background: rgba(0, 245, 255, 0.1);
            border-radius: 6px;
        """
        )
        self._registrar_label_planta(self.lbl_planta_actual_gps)

        header_lyt.addWidget(header_title)
        header_lyt.addWidget(self.lbl_planta_actual_gps)
        header_lyt.addStretch()

        # --- 2. BOTONES DE GESTIÓN (Arriba Derecha) ---
        btn_estilo_secundario = """
            QPushButton {
                background-color: #1A1A1A; color: #8B949E; border: 1px solid #30363D;
                border-radius: 8px; font-weight: 900; font-family: 'Segoe UI'; font-size: 11px;
            }
            QPushButton:hover { background-color: #21262D; color: #FFFFFF; border-color: #00F5FF; }
        """

        self.btn_borrar_plano_gps = QPushButton("🗑️ " + tr("ubic.btn_delete", default="BORRAR"))
        self.btn_borrar_plano_gps.setFixedSize(110, 35)
        self.btn_borrar_plano_gps.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_borrar_plano_gps.setFont(self._crear_fuente_segoe(9))
        self.btn_borrar_plano_gps.setStyleSheet(
            self._estilo_boton_neon(
                bg="#161B22",
                fg="#FF7B72",
                border="#FF7B72",
                hover_bg="#FF7B72",
                hover_fg="#0D1117",
                radius=10,
                padding="8px 14px",
                font_size=11,
            )
        )
        self.btn_borrar_plano_gps.clicked.connect(self.borrar_plano_actual)

        self.btn_cargar_plano_gps = QPushButton("📁 " + tr("ubic.btn_load", default="CARGAR"))
        self.btn_cargar_plano_gps.setFixedSize(110, 35)
        self.btn_cargar_plano_gps.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cargar_plano_gps.setFont(self._crear_fuente_segoe(9))
        self.btn_cargar_plano_gps.setStyleSheet(
            self._estilo_boton_neon(
                bg="#161B22",
                fg="#FFCC66",
                border="#FFCC66",
                hover_bg="#FFCC66",
                hover_fg="#0D1117",
                radius=10,
                padding="8px 14px",
                font_size=11,
            )
        )
        self.btn_cargar_plano_gps.clicked.connect(self.cargar_plano)

        header_lyt.addWidget(self.btn_borrar_plano_gps)
        header_lyt.addSpacing(10)
        header_lyt.addWidget(self.btn_cargar_plano_gps)

        layout.addWidget(header_container)

        # --- 3. CONTENEDOR CENTRAL (Flechas + Mapa) ---
        lyt_visor_central = QHBoxLayout()
        lyt_visor_central.setSpacing(15)

        estilo_flecha = """
            QPushButton {
                background-color: #0A0A0A; color: #00F5FF; border: 1px solid #1C2128;
                border-radius: 12px; font-weight: 900; font-size: 22px; font-family: 'Segoe UI';
            }
            QPushButton:hover { background-color: #00F5FF; border-color: #00F5FF; color: #0D1117; }
            QPushButton:pressed { background-color: #FFFFFF; color: #0D1117; border-color: #FFFFFF; }
        """

        self.btn_planta_prev_gps = QPushButton("<")
        self.btn_planta_prev_gps.setFixedSize(45, 140)
        self.btn_planta_prev_gps.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_planta_prev_gps.setStyleSheet(estilo_flecha)
        self.btn_planta_prev_gps.clicked.connect(lambda: self.navegar_planta(-1))

        # Marco del Mapa con efecto Neón sutil
        self.map_container = QFrame()
        self.map_container.setObjectName("marco_mapa")
        self.map_container.setStyleSheet(
            """
            QFrame#marco_mapa { 
                background-color: #050505; 
                border: 2px solid #1C2128; 
                border-radius: 20px; 
            }
        """
        )
        map_layout = QVBoxLayout(self.map_container)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.setSpacing(0)

        if hasattr(self, "visor_mapa") and self.visor_mapa:
            self.visor_mapa.setStyleSheet(
                "QGraphicsView { border: 2px solid #00FFC6; background: #050505; border-radius: 18px; }"
            )
            self.visor_mapa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.visor_mapa.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            map_layout.addWidget(self.visor_mapa)

        self.btn_planta_next_gps = QPushButton(">")
        self.btn_planta_next_gps.setFixedSize(45, 140)
        self.btn_planta_next_gps.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_planta_next_gps.setStyleSheet(estilo_flecha)
        self.btn_planta_next_gps.clicked.connect(lambda: self.navegar_planta(1))

        lyt_visor_central.addWidget(self.btn_planta_prev_gps)
        lyt_visor_central.addWidget(self.map_container, 1)  # El mapa toma el espacio
        lyt_visor_central.addWidget(self.btn_planta_next_gps)

        layout.addLayout(lyt_visor_central)

        # --- 4. BARRA DE CONTROLES INFERIOR ---
        controles = QHBoxLayout()
        controles.setContentsMargins(0, 10, 0, 0)

        # Botón Rastreo (Toggle Neón)
        self.panel_rastreo_gps = QFrame()
        self.panel_rastreo_gps.setFixedSize(240, 55)
        piloto_layout = QHBoxLayout(self.panel_rastreo_gps)
        piloto_layout.setContentsMargins(14, 8, 14, 8)
        piloto_layout.setSpacing(10)

        self.led_rastreo_gps = QLabel("●")
        self.led_rastreo_gps.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.led_rastreo_gps.setFixedWidth(18)

        bloque_texto_rastreo = QVBoxLayout()
        bloque_texto_rastreo.setContentsMargins(0, 0, 0, 0)
        bloque_texto_rastreo.setSpacing(0)
        self.lbl_titulo_rastreo_gps = QLabel(tr("ubic.pilot", default="PILOTO DE NAVEGACION"))
        self.lbl_estado_rastreo_gps = QLabel(tr("ubic.tracking", default="RASTREO") + " OFF")
        self.lbl_titulo_rastreo_gps.setFont(self._crear_fuente_segoe(8))
        self.lbl_estado_rastreo_gps.setFont(self._crear_fuente_segoe(10))
        bloque_texto_rastreo.addWidget(self.lbl_titulo_rastreo_gps)
        bloque_texto_rastreo.addWidget(self.lbl_estado_rastreo_gps)

        piloto_layout.addWidget(self.led_rastreo_gps)
        piloto_layout.addLayout(bloque_texto_rastreo)
        piloto_layout.addStretch()

        # Botón Iniciar Ruta (Call to Action)
        self.btn_iniciar_ruta = QPushButton("🚀 " + tr("ubic.start_route", default="INICIAR RUTA"))
        self.btn_iniciar_ruta.setFixedSize(240, 55)
        self.btn_iniciar_ruta.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_iniciar_ruta.setFont(self._crear_fuente_segoe(10))
        self.btn_iniciar_ruta.setStyleSheet(
            self._estilo_boton_neon(
                bg="#0D1117",
                fg="#00FFC6",
                border="#00FFC6",
                hover_bg="#00FFC6",
                hover_fg="#0D1117",
                radius=14,
                padding="12px 18px",
                font_size=13,
            )
        )

        self.btn_iniciar_ruta.clicked.connect(self.flujo_inicio_ruta_gps)

        controles.addWidget(self.panel_rastreo_gps)
        controles.addStretch()
        controles.addWidget(self.btn_iniciar_ruta)

        layout.addLayout(controles)
        self._actualizar_piloto_rastreo(False)
        self._aplicar_fuente_segoe(vista)

        return vista

    # ============================================================
    # BLOQUE ESCANEO DE CÓDIGOS DE BARRAS
    # ============================================================

    def procesar_escaneo_barcode(self, codigo):
        """
        Cerebro lógico del escaneo:
        1. Si es un QR de ubicación, posiciona al operario (GPS) con salto brusco.
        2. Si es un código de producto, gestiona la búsqueda o traza la ruta.
        """
        from PyQt6.QtCore import QPointF

        idx_actual = self.stack.currentIndex()
        codigo = codigo.strip().upper()
        # Identificador del operario actual (Asegúrate de tener esta variable definida)
        epc_operario = getattr(self, "epc_actual", "OPERARIO_01")

        # --- FASE 1: POSICIONAMIENTO GPS (Prioridad) ---
        try:
            with obtener_conexion() as conn:
                if conn:
                    cursor = conn.cursor()
                    # Consultamos si el código escaneado es un punto de ubicación
                    cursor.execute(
                        """SELECT mapa_x, mapa_y, verificado, pasillo, estanteria 
                           FROM ubicaciones WHERE codigo_articulo = %s""",
                        (codigo,),
                    )
                    res_ubi = cursor.fetchone()

            if res_ubi:
                mx, my, verificado, pas, est = res_ubi
                # Si tiene coordenadas asignadas en el mapa
                if mx != 0 or my != 0:
                    pos_real = QPointF(mx, my)

                    # A. ACTUALIZACIÓN VISUAL: Forzamos el salto brusco al QR
                    if hasattr(self, "visor_mapa") and self.visor_mapa:
                        self.visor_mapa.marcar_operario(pos_real, salto_brusco=True)

                        # Si el rastreo está activo, centramos la cámara de inmediato
                        if getattr(self.visor_mapa, "rastreo_en_vivo_activo", False):
                            self.visor_mapa.centerOn(self.visor_mapa.icono_operario)

                    # B. ACTUALIZACIÓN PERSISTENTE: Sincronizamos con MariaDB
                    self.actualizar_coordenada_db(epc_operario, pos_real)

                    # C. VALIDACIÓN FÍSICA: Si es la primera vez que se escanea
                    if verificado == 0 and hasattr(
                        self, "confirmar_verificacion_fisica_db"
                    ):
                        self.confirmar_verificacion_fisica_db(codigo)

                    # D. RECALCULO DE RUTA: Si ya había un destino, actualizamos el camino desde el QR
                    if (
                        hasattr(self, "coordenadas_destino")
                        and self.coordenadas_destino
                    ):
                        self.procesar_ruta_gps()

                    if self.window().statusBar():
                        self.window().statusBar().showMessage(
                            f"📍 POSICIÓN CALIBRADA: Pasillo {pas} - {est}", 5000
                        )
                    return  # Finalizamos aquí si fue un QR de ubicación

        except Exception as e:
            print(f"Error en escaneo de ubicación: {e}")

        # --- FASE 2: REDIRECCIÓN INTELIGENTE SEGÚN PANEL ---
        target_input = None
        if idx_actual in [0, 1]:  # Asignación/Registro
            target_input = getattr(self, "input_scan", None)
        elif idx_actual == 2:  # Búsqueda Global
            target_input = getattr(self, "input_search", None)
        elif idx_actual == 3:  # Panel GPS (Buscar destino)
            target_input = getattr(self, "_input_gps_dialog_activo", None) or getattr(
                self, "txt_buscar_gps", None
            )
        elif idx_actual == 4:  # Panel Administrador
            target_input = getattr(self, "txt_buscar_admin", None)

        if target_input:
            target_input.setText(codigo)

        # --- FASE 3: AUTOMATIZACIONES POST-ESCANEO ---
        # A. Recepción/Salida
        if idx_actual in [0, 1] and hasattr(self, "validar_articulo"):
            tipo = "LINEAL" if idx_actual == 0 else "ALMACÉN"
            self.validar_articulo(tipo)

        # B. Búsqueda Global
        elif idx_actual == 2 and hasattr(self, "ejecutar_busqueda"):
            self.ejecutar_busqueda()

        # C. Mapa GPS: Si escaneamos un PRODUCTO, lo marcamos como destino
        elif idx_actual == 3:
            try:
                opciones = [
                    op
                    for op in self._obtener_opciones_destino_gps(codigo)
                    if op.get("disponible")
                ]
                if opciones:
                    seleccion = (
                        self._mostrar_selector_destino_gps(opciones)
                        if len(opciones) > 1
                        else opciones[0]
                    )
                    if seleccion:
                        self.destino_gps_activo = seleccion
                        self.coordenadas_destino = seleccion["coords"]

                        if hasattr(self, "visor_mapa") and self.visor_mapa:
                            self.visor_mapa.set_punto_destino(
                                seleccion["coords"].x(),
                                seleccion["coords"].y(),
                            )
                            if self.visor_mapa.pos_operario:
                                self.procesar_ruta_gps()

                        self._actualizar_piloto_rastreo(
                            True, seleccion.get("ubicacion")
                        )
                        dlg_ruta = getattr(self, "_dialogo_ruta_gps_activo", None)
                        if dlg_ruta and dlg_ruta.isVisible():
                            dlg_ruta.accept()
                        if self.window().statusBar():
                            self.window().statusBar().showMessage(
                                f"DESTINO FIJADO: {seleccion.get('ubicacion', '').upper()}",
                                5000,
                            )
                        return

                with obtener_conexion() as conn:
                    if conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT nombre, mapa_x, mapa_y FROM ubicaciones WHERE codigo_articulo = %s",
                            (codigo,),
                        )
                        res_prod = cursor.fetchone()

                if res_prod and res_prod[1] != 0:
                    nombre_art, dest_x, dest_y = res_prod
                    self.coordenadas_destino = QPointF(dest_x, dest_y)

                    if hasattr(self, "visor_mapa") and self.visor_mapa:
                        # Marcamos el punto en el mapa (esto activa el radar)
                        self.visor_mapa.set_punto_destino(dest_x, dest_y)

                        # Trazamos la ruta desde donde esté el operario ahora mismo
                        if self.visor_mapa.pos_operario:
                            self.procesar_ruta_gps()

                    if self.window().statusBar():
                        self.window().statusBar().showMessage(
                            f"🎯 DESTINO FIJADO: {nombre_art.upper()}", 5000
                        )
            except Exception as e:
                print(f"Error en búsqueda logística de producto: {e}")

    # ============================================================
    # BLOQUE NAVEGACIÓN ENTRE SECCIONES
    # ============================================================

    def cambiar_seccion(self):
        """
        Maneja la navegación entre pestañas solicitando guardado si hay cambios.
        Sincroniza visores y evita errores de renderizado en mapas.
        """

        # 1. BLOQUEO DE SEGURIDAD
        if getattr(self, "_bloqueo_navegacion", False):
            return
        self._bloqueo_navegacion = True

        try:
            btn = self.sender()
            if not btn:
                return

            indice_actual = self.stack.currentIndex()
            mapa_indices = self._mapeo_botones_indices()
            target_index = mapa_indices.get(btn)

            if target_index is None or target_index == indice_actual:
                return

            # --- A. CONTROL DE CAMBIOS CENTRALIZADO ---
            # Si salimos de Gestión (4) o cualquier zona con cambios pendientes
            hay_cambios = getattr(self, "cambios_sin_guardar", False)

            if hay_cambios:
                # Llamamos al orquestador Neón que creamos en el paso anterior
                # Si devuelve False, es que el usuario pulsó 'CANCELAR'
                if not self.advertir_cambios_pendientes():
                    self._restaurar_estado_botones(indice_actual)
                    return

            # --- B. LIMPIEZA DE MODOS DE EDICIÓN ---
            if indice_actual == 4 and target_index != 4:
                if (
                    hasattr(self, "btn_modo_pintar")
                    and self.btn_modo_pintar.isChecked()
                ):
                    self.btn_modo_pintar.setChecked(False)
                    if hasattr(self, "alternar_modo_pintado"):
                        self.alternar_modo_pintado()

            # --- C. PRE-CARGA DE PLANTA 0 ANTES DE MOSTRAR LA PESTAÑA ---
            # Si vamos a Gestión Estructura (4) y el plano actual no es el 0, lo
            # cargamos ANTES de que setCurrentIndex lo haga visible. Así el usuario
            # nunca llega a ver el plano anterior parpadear.
            if target_index == 4 and getattr(self, "planta_actual", 0) != 0:
                self.planta_actual = 0
                self.cargar_infraestructura_registrada()

            # --- D. EJECUCIÓN DEL CAMBIO ---
            # Sincronizamos visualmente el Sidebar
            for b in self.menu_botones:
                b.blockSignals(True)
                b.setChecked(b == btn)
                b.blockSignals(False)

            self.stack.setCurrentIndex(target_index)

            # --- E. SINCRONIZACIÓN VISUAL (Evitar Pantalla Negra) ---
            if target_index in [3, 4]:
                visor = getattr(
                    self, "visor_mapa" if target_index == 3 else "visor_admin", None
                )

                if visor:
                    # Actualizar label de planta (delegado a _actualizar_labels_planta)
                    self._actualizar_labels_planta()

                    from PyQt6.QtWidgets import QGraphicsView as _GV
                    escena = _GV.scene(visor)

                    if escena:
                        rect = escena.itemsBoundingRect()
                        if not rect.isEmpty():
                            visor.setSceneRect(rect)
                            # No llamar fitInView aquí directamente: el widget
                            # aún no tiene su tamaño final. Se delega al diferido.
                        if visor.viewport():
                            visor.viewport().update()

            if target_index in [3, 4]:
                self._actualizar_labels_planta()
                # Reencuadre diferido con delays suficientes para que el
                # QStackedWidget haya completado el resize del widget visible
                self._forzar_reencuadre_diferido(force=True)

        finally:
            self._bloqueo_navegacion = False

    def _restaurar_estado_botones(self, indice_objetivo):
        """Devuelve el estado 'Checked' al botón correcto si se aborta la navegación."""
        mapa = self._mapeo_botones_indices()
        for b, idx in mapa.items():
            b.blockSignals(True)
            b.setChecked(idx == indice_objetivo)
            b.blockSignals(False)
        self._bloqueo_navegacion = False

    def _mapeo_botones_indices(self):
        """Mapeo centralizado de la arquitectura del Stack."""
        # Asegúrate de que estos nombres coincidan con tus objetos QPushButton
        return {
            getattr(self, "btn_nav_lineal", None): 0,
            getattr(self, "btn_nav_almacen", None): 1,
            getattr(self, "btn_nav_busqueda", None): 2,
            getattr(self, "btn_nav_gps", None): 3,
            getattr(self, "btn_nav_admin", None): 4,
        }

    # ============================================================
    # BLOQUE GESTIÓN DE UBICACIONES Y ACTIVOS
    # ============================================================

    def gestionar_ubicacion_epc(
        self, nombre_ref, epc_generado, pos_clic, real_x=None, real_y=None
    ):
        """
        Lógica de Persistencia y Visualización:
        1. Sincroniza telemetría (m) y coordenadas de mapa (px).
        2. Persistencia en MariaDB (Insert/Update).
        3. Renderizado de marcador persistente en el mapa.
        4. Generación de QR físico con coordenadas exactas.
        """

        from PyQt6.QtCore import QPointF
        from PyQt6.QtWidgets import QMessageBox

        try:
            # --- 1. PREPARACIÓN DE DATOS ---
            nombre_limpio = nombre_ref.strip().upper()
            epc_final = epc_generado.strip()

            if not isinstance(pos_clic, QPointF):
                pos_clic = QPointF(pos_clic)

            # --- 2. CÁLCULO DE TELEMETRÍA (METROS REALES) ---
            # Estas son las "coordenadas exactas" que irán al QR y a la DB
            ancla = getattr(self.visor_admin, "punto_ancla", None)
            r_x = getattr(self.visor_admin, "ratio_px_m_h", 0)
            r_y = getattr(self.visor_admin, "ratio_px_m_v", 0)

            if ancla and r_x > 0 and r_y > 0:
                m_x = round((pos_clic.x() - ancla.x()) / r_x, 3)
                m_y = round((ancla.y() - pos_clic.y()) / r_y, 3)
            else:
                # Usamos la nueva nomenclatura 'real_x' y 'real_y'
                m_x = round(real_x, 3) if real_x is not None else 0.0
                m_y = round(real_y, 3) if real_y is not None else 0.0

            # --- 3. CLASIFICACIÓN Y RENDERIZADO VISUAL ---
            es_satelite = any(
                x in nombre_limpio for x in ["SAT", "SATELLITE", "SBT", "ANTENNA"]
            )
            tipo_label = "SATÉLITE" if es_satelite else "ESTANTERÍA"
            color_marcador = "#00F0FF" if es_satelite else "#FFB300"

            if hasattr(self.visor_admin, "colocar_marcador_3d"):
                self.visor_admin.colocar_marcador_3d(
                    pos=pos_clic,
                    tipo=tipo_label,
                    nombre=nombre_limpio,
                    color=color_marcador,
                    epc=epc_final,
                )

            # --- 4. COLA DE GUARDADO DIFERIDO ---
            # La escritura a DB (ubicaciones + configuracion_mapa) se realiza únicamente
            # al pulsar "FINALIZAR Y GUARDAR", para que el aviso de cambios pendientes
            # funcione correctamente y el usuario controle cuándo se persiste el estado.
            if not hasattr(self, "_iconos_pendientes"):
                self._iconos_pendientes = []
            # Remove any prior entry for the same EPC so repeated moves don't duplicate
            self._iconos_pendientes = [
                p for p in self._iconos_pendientes if p.get("epc") != epc_final
            ]
            self._iconos_pendientes.append({
                "epc": epc_final,
                "pasillo": "ZONA_ADMIN",
                "estanteria": nombre_limpio,
                "mapa_x": int(pos_clic.x()),
                "mapa_y": int(pos_clic.y()),
                "real_x": m_x,
                "real_y": m_y,
            })
            self.cambios_sin_guardar = True

            # --- 5. GENERACIÓN DE QR FÍSICO (Exportación a carpeta) ---
            # Pasamos nombre, x e y directamente
            if hasattr(self, "generar_qr_estanteria"):
                self.generar_qr_estanteria(epc_final, nombre_limpio, m_x, m_y)

            # --- 6. FEEDBACK EN BARRA DE ESTADO ---
            sb = self.window().statusBar()
            if sb:
                sb.setStyleSheet(
                    "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900; background: #0D1117;"
                )
                sb.showMessage(
                    f"VINCULACIÓN OK: {tipo_label} {nombre_limpio} | EPC: {epc_final} | POS: {m_x}m, {m_y}m",
                    6000,
                )

            return True

        except Exception as e:
            print(f"CRITICAL ERROR [gestionar_ubicacion_epc]: {e}")
            QMessageBox.critical(
                self,
                "Fallo de Persistencia",
                f"No se pudo registrar el activo en el sistema.\n\nDetalle: {str(e)}",
            )
            return False

    def abrir_formulario_ubicacion_estanteria(
        self, epc_existente=None, nombre_existente=None, permiso_clic=False
    ):
        import hashlib
        import time

        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QDialog,
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QVBoxLayout,
        )

        is_edit = epc_existente is not None

        # --- ESTILOS VISUALES (GitHub Dark Style) ---
        estilo_botones = """
            QPushButton { 
                border-radius: 8px; font-family: 'Segoe UI'; font-weight: 900; 
                font-size: 11px; padding: 10px 20px; border: none; 
            }
            QPushButton#btnOk { background-color: #238636; color: #0E1117; }
            QPushButton#btnOk:hover { background-color: #FFFFFF; color: #0E1117; }
            QPushButton#btnCan { background-color: #30363D; color: #8B949E; }
            QPushButton#btnCan:hover { background-color: #4B535D; color: white; }
            QPushButton#btnSave { background-color: #0047AB; color: white; } 
            QPushButton#btnSave:hover { background-color: #005FB8; }
            QPushButton#btnContinue { background-color: #0078D4; color: white; border: 1px solid #005FB8;}
            QPushButton#btnContinue:hover { background-color: #005FB8; }
        """

        # --- FASE 1: DIÁLOGO DE INSTRUCCIONES (MODO UBICACIÓN) ---
        if not is_edit and not permiso_clic:
            self.visor_admin.ultimo_click_escena = None  # Limpieza preventiva

            aviso = QDialog(self)
            aviso.setFixedSize(480, 290)
            aviso.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
            )
            aviso.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

            lyt_base = QVBoxLayout(aviso)
            lyt_base.setContentsMargins(0, 0, 0, 0)
            frm = QFrame()
            frm.setStyleSheet(
                "QFrame { background-color: #0D1117; border: 2px solid #00FFC6; border-radius: 18px; }"
                " QLabel { color: #E6EDF3; border: none; background: transparent; }"
            )

            fl = QVBoxLayout(frm)
            fl.setContentsMargins(30, 26, 30, 26)
            fl.setSpacing(14)

            tit = QLabel("📍  " + tr("ubic.mode_locate_title", default="MODO UBICACIÓN"))
            tit.setStyleSheet(
                "color: #00FFC6; font-family: 'Segoe UI'; font-size: 16px; font-weight: 900;"
                " letter-spacing: 1px; border: none; background: transparent;"
            )
            tit.setAlignment(Qt.AlignmentFlag.AlignCenter)

            msg = QLabel(
                tr("ubic.mode_locate_msg",
                   default="Para vincular un activo, primero debe marcar una ubicación exacta en el mapa plano.<br><br>¿Desea activar el puntero de ubicación?")
            )
            msg.setStyleSheet(
                "color: #C9D1D9; font-family: 'Segoe UI'; font-size: 13px; font-weight: 700;"
                " border: none; background: transparent;"
            )
            msg.setWordWrap(True)
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)

            btn_h = QHBoxLayout()
            btn_h.setSpacing(12)

            btn_cancel = QPushButton(tr("ubic.cancel", default="CANCELAR"))
            btn_cancel.setFixedHeight(42)
            btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_cancel.setStyleSheet(
                "QPushButton { background-color: #21262D; color: #8B949E;"
                " border: 1px solid #30363D; border-radius: 10px;"
                " font-family: 'Segoe UI'; font-weight: 900; font-size: 14px; }"
                " QPushButton:hover { background-color: #FFFFFF; color: #0D1117; }"
            )
            btn_cancel.clicked.connect(aviso.reject)

            btn_cont = QPushButton(tr("ubic.continue", default="CONTINUAR"))
            btn_cont.setFixedHeight(42)
            btn_cont.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_cont.setStyleSheet(
                "QPushButton { background-color: #1ED760; color: #0D1117;"
                " border: 2px solid #1ED760; border-radius: 10px;"
                " font-family: 'Segoe UI'; font-weight: 900; font-size: 14px; }"
                " QPushButton:hover { background-color: transparent; color: #1ED760;"
                " border: 2px solid #1ED760; }"
            )
            btn_cont.clicked.connect(aviso.accept)

            btn_h.addWidget(btn_cancel)
            btn_h.addWidget(btn_cont)
            fl.addWidget(tit)
            fl.addWidget(msg)
            fl.addStretch()
            fl.addLayout(btn_h)
            lyt_base.addWidget(frm)

            if aviso.exec() == QDialog.DialogCode.Accepted:
                self.esperando_ubicacion_estanteria = True
                if hasattr(self.visor_admin, "configurar_modo"):
                    self.visor_admin.configurar_modo("UBICAR_ESTANTERIA")
                if hasattr(self, "mostrar_mensaje_temporal"):
                    self.mostrar_mensaje_temporal(
                        tr("ubic.click_to_place", default="Haga clic en el mapa para situar la estantería")
                    )
            return

        # --- FASE 2: FORMULARIO DE DATOS (YA HAY CLIC) ---
        pos_clic = getattr(self.visor_admin, "ultimo_click_escena", None)
        if not is_edit and pos_clic is None:
            return

        self.esperando_ubicacion_estanteria = False
        if hasattr(self.visor_admin, "configurar_modo"):
            self.visor_admin.configurar_modo("NAVEGACION")

        dialogo = QDialog(self)
        dialogo.setFixedSize(400, 480)
        dialogo.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        dialogo.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        container = QFrame()
        container.setStyleSheet(
            f"""
            QFrame {{ background-color: #0D1117; border: 1.5px solid #30363D; border-radius: 20px; }}
            QLabel {{ color: #8B949E; font-family: 'Segoe UI'; font-weight: 900; font-size: 11px; border: none; }}
            QLineEdit {{ background-color: #161B22; color: white; border: 1px solid #30363D; border-radius: 8px; padding: 12px; }}
            {estilo_botones}
        """
        )

        layout = QVBoxLayout(container)
        layout.setContentsMargins(35, 30, 35, 30)
        layout.setSpacing(15)

        lbl_head = QLabel(tr("ubic.asset_edit_head", default="EDICIÓN DE ACTIVO") if is_edit else tr("ubic.asset_link_head", default="VINCULACIÓN DE ACTIVO"))
        lbl_head.setStyleSheet(
            "color: white; font-family: 'Segoe UI'; font-size: 15px; font-weight: 900;"
        )
        layout.addWidget(lbl_head)

        layout.addWidget(QLabel(tr("ubic.name_ref", default="NOMBRE / REFERENCIA:")))
        input_ref = QLineEdit()
        nombre_def = (
            nombre_existente
            if is_edit
            else (
                self.lista_articulos_admin.currentItem().text()
                if hasattr(self, "lista_articulos_admin")
                and self.lista_articulos_admin.currentItem()
                else ""
            )
        )
        input_ref.setText(nombre_def)
        layout.addWidget(input_ref)
        layout.addStretch()

        # Botones de Acción
        btn_vincular = QPushButton(tr("ubic.btn_update", default="ACTUALIZAR") if is_edit else tr("ubic.btn_locate_finish", default="UBICAR Y FINALIZAR"))
        btn_vincular.setObjectName("btnSave")
        btn_vincular.setCursor(
            Qt.CursorShape.PointingHandCursor
        )  # <--- Añadido hover manita
        layout.addWidget(btn_vincular)

        btn_seguir = None
        if not is_edit:
            btn_seguir = QPushButton(tr("ubic.btn_keep_locating", default="SEGUIR UBICANDO"))
            btn_seguir.setObjectName("btnContinue")
            btn_seguir.setCursor(
                Qt.CursorShape.PointingHandCursor
            )  # <--- Añadido hover manita
            layout.addWidget(btn_seguir)

        btn_cancel_form = QPushButton(tr("ubic.cancel", default="CANCELAR"))
        btn_cancel_form.setObjectName("btnCan")
        btn_cancel_form.setCursor(
            Qt.CursorShape.PointingHandCursor
        )  # <--- Añadido hover manita
        btn_cancel_form.clicked.connect(dialogo.reject)
        layout.addWidget(btn_cancel_form)

        # --- LÓGICA DE PROCESAMIENTO UNIFICADA ---
        def procesar_vinculacion(seguir_ubicando=False):
            ref = input_ref.text().strip().upper()
            if not ref:
                return

            ancla = getattr(self.visor_admin, "punto_ancla", None)
            if not ancla:
                return

            # Coordenadas relativas
            r_x = getattr(self.visor_admin, "ratio_px_m_h", 1.0)
            r_y = getattr(self.visor_admin, "ratio_px_m_v", 1.0)
            rel_x = (pos_clic.x() - ancla.x()) / r_x
            rel_y = (ancla.y() - pos_clic.y()) / r_y

            # EPC
            epc_final = (
                epc_existente
                if is_edit
                else f"3G0-EST-{hashlib.sha256(f'{ref}{time.time()}'.encode()).hexdigest()[:16]}".upper()
            )

            # 1. Escritura RFID Física
            if hasattr(self, "lector_rfid") and not self.lector_rfid.escribir_tag(
                epc_final
            ):
                if hasattr(self, "mostrar_mensaje_temporal"):
                    self.mostrar_mensaje_temporal(
                        tr("ubic.hw_fail", default="FALLO DE HARDWARE: Acerque el tag"), 5000
                    )
                return

            # 2. Persistencia Lógica (DB + Chincheta)
            registro_ok = False
            if hasattr(self, "gestionar_ubicacion_epc"):
                registro_ok = bool(
                    self.gestionar_ubicacion_epc(ref, epc_final, pos_clic, rel_x, rel_y)
                )

            # 3. [DE TU SEGUNDA VERSIÓN] Memoria de sesión
            if registro_ok and hasattr(self, "gestion_activos"):
                self.gestion_activos["estanterias_sesion"][epc_final] = {
                    "nombre": ref,
                    "coords": (rel_x, rel_y),
                    "timestamp": time.time(),
                }

            # 4. QR
            if registro_ok and hasattr(self, "generar_qr_estanteria"):
                self.generar_qr_estanteria(
                    epc=epc_final, nombre=ref, pos_x=rel_x, pos_y=rel_y
                )

            self.visor_admin.ultimo_click_escena = None
            dialogo.accept()

            if seguir_ubicando:
                self.abrir_formulario_ubicacion_estanteria(permiso_clic=False)

        # --- CONEXIÓN DE SEÑALES (LO QUE HACÍA QUE NO FUNCIONARAN LOS BOTONES) ---
        btn_vincular.clicked.connect(
            lambda: procesar_vinculacion(seguir_ubicando=False)
        )
        if btn_seguir:
            btn_seguir.clicked.connect(
                lambda: procesar_vinculacion(seguir_ubicando=True)
            )

        main_lyt = QVBoxLayout(dialogo)
        main_lyt.setContentsMargins(0, 0, 0, 0)
        main_lyt.addWidget(container)
        dialogo.exec()

    def registrar_satelite_db(self, permiso_clic=False, pos=None):
        """
        Registra un Satélite:
        1. Captura el clic.
        2. Abre diálogo para pedir NOMBRE (Opaco y Segoe UI Bold).
        3. Guarda en DB y genera QR.
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import (
            QDialog,
            QFrame,
            QLabel,
            QLineEdit,
            QPushButton,
            QVBoxLayout,
        )

        if not permiso_clic or pos is None:
            return

        try:
            # --- 1. DIÁLOGO PARA CAPTURAR EL NOMBRE ---
            diag_nom = QDialog(self)
            diag_nom.setFixedSize(350, 220)
            diag_nom.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
            )
            diag_nom.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

            # Fuente Unificada
            fuente_segoe = QFont("Segoe UI", 10, QFont.Weight.Bold)
            diag_nom.setFont(fuente_segoe)

            container = QFrame()
            # ESTILO: Ahora usa #0D1117 para ser consistente con las otras ventanas
            container.setStyleSheet(
                """
                QFrame { 
                    background-color: #0D1117; 
                    border: 2px solid #00FFC6; 
                    border-radius: 15px; 
                }
                QLabel { 
                    color: #00FFC6; 
                    border: none; 
                    font-family: 'Segoe UI'; 
                    font-weight: 900; 
                    font-size: 14px;
                }
                QLineEdit { 
                    background-color: #1C2128; 
                    color: white; 
                    border: 1px solid #30363D; 
                    border-radius: 8px; 
                    padding: 10px; 
                    font-family: 'Segoe UI';
                    font-weight: 900;
                }
                QPushButton { 
                    background-color: #1C2128; 
                    color: #00FFC6; 
                    font-family: 'Segoe UI'; 
                    font-weight: 900; 
                    border: 1px solid #00FFC6;
                    border-radius: 8px; 
                    padding: 10px; 
                }
                QPushButton:hover { 
                    background-color: #00FFC6; 
                    color: #0D1117; 
                }
                """
            )

            layout = QVBoxLayout(container)
            lbl = QLabel(tr("ubic.sat_id", default="IDENTIFICADOR DEL SATÉLITE:"))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            input_nom = QLineEdit()
            input_nom.setPlaceholderText(tr("ubic.sat_id_ph", default="Ej: SAT-NORTE-01"))

            btn_guardar = QPushButton(tr("ubic.sat_confirm", default="CONFIRMAR E INSTALAR"))
            # Forzamos la fuente bold también vía objeto por si el CSS tiene herencia débil
            btn_guardar.setFont(fuente_segoe)
            btn_guardar.setCursor(Qt.CursorShape.PointingHandCursor)  # Cursor Manita
            btn_guardar.clicked.connect(diag_nom.accept)

            layout.addWidget(lbl)
            layout.addWidget(input_nom)
            layout.addStretch()
            layout.addWidget(btn_guardar)

            main_lyt = QVBoxLayout(diag_nom)
            main_lyt.addWidget(container)

            if diag_nom.exec() != QDialog.DialogCode.Accepted:
                return

            # Limpiamos el nombre (por si acaso el usuario pega algo con coordenadas)
            import re

            raw_nom = input_nom.text().strip().upper()
            nombre_sat = re.sub(
                r"\s*-?\d+(\.\d+)?M,?\s*-?\d+(\.\d+)?M", "", raw_nom
            ).strip()

            if not nombre_sat:
                nombre_sat = f"SAT_{int(pos.x())}_{int(pos.y())}"

            # --- 2. CÁLCULO DE COORDENADAS ---
            ancla = getattr(self.visor_admin, "punto_ancla", pos)
            r_x = getattr(self.visor_admin, "ratio_x", 1.0)
            r_y = getattr(self.visor_admin, "ratio_y", 1.0)

            real_x = (pos.x() - ancla.x()) / r_x
            real_y = (pos.y() - ancla.y()) / r_y
            sat_id = f"SAT_{int(pos.x())}_{int(pos.y())}"

            # --- 3. GUARDAR EN MARIADB ---
            with obtener_conexion() as conn:
                cursor = conn.cursor()
                query = """
                    INSERT INTO ubicaciones 
                    (epc, pasillo, estanteria, mapa_x, mapa_y, real_x, real_y, verificado) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
                    ON DUPLICATE KEY UPDATE estanteria=%s, real_x=%s, real_y=%s, mapa_x=%s, mapa_y=%s
                """
                valores = (
                    sat_id,
                    "SISTEMA",
                    nombre_sat,
                    pos.x(),
                    pos.y(),
                    real_x,
                    real_y,
                    nombre_sat,
                    real_x,
                    real_y,
                    pos.x(),
                    pos.y(),
                )
                cursor.execute(query, valores)
                conn.commit()

            # --- 4. QR ---
            if hasattr(self, "generar_qr_estanteria"):
                self.generar_qr_estanteria(
                    epc=sat_id,
                    nombre=nombre_sat,
                    pos_x=real_x,
                    pos_y=real_y,
                    es_satelite=True,
                )

            # --- 5. FEEDBACK VISUAL ---
            if hasattr(self.visor_admin, "colocar_marcador_3d"):
                self.visor_admin.colocar_marcador_3d(
                    pos,
                    "SATÉLITE",
                    nombre_sat,
                    color="#00FFC6",
                    epc=sat_id,
                )

            # --- 6. PERSISTENCIA EN configuracion_mapa (puntos_infraestructura) ---
            # Needed so the satellite survives plan navigation and session restarts.
            try:
                import json as _json_mod
                _planta_idx = getattr(self, "planta_actual", 0)
                with obtener_conexion() as _conn2:
                    _cur2 = _conn2.cursor()
                    _cur2.execute(
                        "SELECT puntos_infraestructura FROM configuracion_mapa WHERE planta_index = %s",
                        (_planta_idx,),
                    )
                    _row2 = _cur2.fetchone()
                    _lista_infra = []
                    if _row2 and _row2[0]:
                        try:
                            _lista_infra = _json_mod.loads(_row2[0])
                        except Exception:
                            _lista_infra = []
                    _lista_infra = [p for p in _lista_infra if p.get("epc") != sat_id]
                    _lista_infra.append({
                        "tipo": "SATÉLITE",
                        "x": pos.x(),
                        "y": pos.y(),
                        "nombre": nombre_sat,
                        "epc": sat_id,
                    })
                    _infra_json_new = _json_mod.dumps(_lista_infra)
                    if _row2:
                        _cur2.execute(
                            "UPDATE configuracion_mapa SET puntos_infraestructura = %s WHERE planta_index = %s",
                            (_infra_json_new, _planta_idx),
                        )
                    else:
                        _cur2.execute(
                            "INSERT INTO configuracion_mapa (planta_index, puntos_infraestructura) VALUES (%s, %s)",
                            (_planta_idx, _infra_json_new),
                        )
                    _conn2.commit()
            except Exception as _e2:
                print(f"⚠️ Error al persistir satélite en configuracion_mapa: {_e2}")

            if self.window() and hasattr(self.window(), "statusBar"):
                sb = self.window().statusBar()
                sb.setStyleSheet(
                    "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900;"
                )
                sb.showMessage(tr("ubic.sat_installed", default="SATÉLITE '{nombre}' INSTALADO CORRECTAMENTE", nombre=nombre_sat), 4000)

        except Exception as e:
            print(f"Error crítico en registro de satélite: {e}")

    def activar_modo_satelite(self):
        """
        FASE 1: Inicia el flujo de instalación de satélites.
        Muestra el aviso legal/instrucciones y activa la cruceta en el visor.
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QDialog,
            QFrame,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QVBoxLayout,
        )

        if not self.visor_admin:
            return

        diag = QDialog(self)
        diag.setFixedSize(500, 310)
        diag.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        diag.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        container = QFrame()
        container.setStyleSheet(
            "QFrame { background-color: #0D1117; border: 2px solid #00FFC6; border-radius: 18px; }"
            " QLabel { color: #E6EDF3; border: none; background: transparent; }"
        )

        lyt = QVBoxLayout(container)
        lyt.setContentsMargins(30, 26, 30, 26)
        lyt.setSpacing(14)

        titulo_label = QLabel("📡  " + tr("ubic.sat_install_title", default="MODO INSTALACIÓN DE SATÉLITES"))
        titulo_label.setStyleSheet(
            "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900;"
            " font-size: 16px; letter-spacing: 1px; border: none; background: transparent;"
        )
        titulo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lyt.addWidget(titulo_label)

        texto_guia = QLabel(
            tr("ubic.sat_install_guide",
               default="Para generar los códigos QR vinculados a coordenadas exactas, debe seleccionar el punto de instalación sobre el mapa.<br><br>1. Pulse <b>Continuar</b> para activar la cruceta.<br>2. Haga clic en el mapa para marcar la ubicación.<br>3. Se le pedirá un <b>Nombre</b> para el satélite tras el clic.")
        )
        texto_guia.setStyleSheet(
            "color: #C9D1D9; font-family: 'Segoe UI'; font-weight: 700;"
            " font-size: 13px; border: none; background: transparent;"
        )
        texto_guia.setTextFormat(Qt.TextFormat.RichText)
        texto_guia.setAlignment(Qt.AlignmentFlag.AlignCenter)
        texto_guia.setWordWrap(True)
        lyt.addWidget(texto_guia)

        btn_lyt = QHBoxLayout()
        btn_lyt.setSpacing(12)

        btn_cancelar = QPushButton(tr("ubic.cancel", default="CANCELAR"))
        btn_cancelar.setFixedHeight(42)
        btn_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancelar.setStyleSheet(
            "QPushButton { background-color: #21262D; color: #8B949E;"
            " border: 1px solid #30363D; border-radius: 10px;"
            " font-family: 'Segoe UI'; font-weight: 900; font-size: 14px; }"
            " QPushButton:hover { background-color: #FFFFFF; color: #0D1117; }"
        )

        btn_continuar = QPushButton(tr("ubic.continue", default="CONTINUAR"))
        btn_continuar.setFixedHeight(42)
        btn_continuar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_continuar.setStyleSheet(
            "QPushButton { background-color: #1ED760; color: #0D1117;"
            " border: 2px solid #1ED760; border-radius: 10px;"
            " font-family: 'Segoe UI'; font-weight: 900; font-size: 14px; }"
            " QPushButton:hover { background-color: transparent; color: #1ED760;"
            " border: 2px solid #1ED760; }"
        )

        btn_lyt.addWidget(btn_cancelar)
        btn_lyt.addWidget(btn_continuar)
        lyt.addStretch()
        lyt.addLayout(btn_lyt)

        main_lyt = QVBoxLayout(diag)
        main_lyt.setContentsMargins(0, 0, 0, 0)
        main_lyt.addWidget(container)

        btn_cancelar.clicked.connect(diag.reject)
        btn_continuar.clicked.connect(diag.accept)

        # 4. EJECUCIÓN Y CAMBIO DE CURSOR EN EL VISOR
        if diag.exec() == QDialog.DialogCode.Accepted:
            # ACTIVACIÓN DEL ESTADO
            self.visor_admin.modo_satelite = True
            self.visor_admin.modo_calibrar = False
            self.visor_admin.modo_pintar = False
            self.visor_admin.satelites_instalados_sesion = 0

            # FORZADO DE CURSOR EN EL MAPA (Cruceta de precisión)
            self.visor_admin.setFocus()
            self.visor_admin.setCursor(Qt.CursorShape.CrossCursor)
            for item in getattr(self.visor_admin, "historial_muros", []):
                try:
                    item.setVisible(True)
                except Exception:
                    continue
            if hasattr(self.visor_admin, "viewport"):
                self.visor_admin.viewport().setCursor(Qt.CursorShape.CrossCursor)
                self.visor_admin.viewport().update()

            sb = self.window().statusBar()
            if sb:
                sb.showMessage("📡 MODO SATÉLITE — Seleccione ubicación en el mapa", 0)

            if hasattr(self, "btn_modo_pintar"):
                self.btn_modo_pintar.setChecked(False)
        else:
            # SI CANCELA: Volvemos al cursor normal
            self.visor_admin.modo_satelite = False
            self.visor_admin.setCursor(Qt.CursorShape.ArrowCursor)
            if self.window().statusBar():
                self.window().statusBar().clearMessage()

    def finalizar_grabacion_logistica(self, pasillo, estanteria, qr_id, pos_clic=None):
        """
        MOTOR UNIFICADO DE REGISTRO:
        1. Persistencia SQL en tabla 'ubicaciones'.
        2. Registro de Nodo (JSON) para el motor de navegación.
        3. Sincronización visual y guardado automático del mapa.
        """
        from datetime import datetime

        from PyQt6.QtWidgets import QMessageBox

        # Estilo unificado para los mensajes (Dark Tech / Bold)
        estilo_base_msg = """
            QMessageBox { 
                background-color: #0D1117; 
                border-radius: 15px; 
                font-family: 'Segoe UI';
            }
            QMessageBox QLabel { 
                color: #C9D1D9; 
                font-weight: 900; 
                font-size: 12px; 
            }
            QMessageBox QPushButton { 
                background-color: #21262D; 
                color: white; 
                border-radius: 8px; 
                padding: 6px 20px; 
                font-weight: 900; 
                font-size: 11px;
                border: 1px solid #30363D;
            }
            QMessageBox QPushButton:hover { 
                background-color: #30363D; 
                border-color: #8B949E; 
            }
        """

        # 1. Recuperación de Coordenadas
        if pos_clic is None:
            pos_clic = getattr(self.visor_admin, "ultimo_click_escena", None)

        if pos_clic is None:
            msg = QMessageBox(self)
            msg.setWindowTitle("⚠️ " + tr("ubic.err_coords_title", default="ERROR DE COORDENADAS"))
            msg.setText(
                tr("ubic.no_se_detecto_un_punto_de_an", default="No se detectó un punto de anclaje válido en el mapa.\nPor favor, marque la ubicación primero.")
            )
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setStyleSheet(
                estilo_base_msg + "QMessageBox { border: 2px solid #F85149; }"
            )
            msg.exec()
            return

        try:
            # --- FASE 1: PERSISTENCIA SQL (MariaDB) ---
            query_sql = """
                INSERT INTO ubicaciones 
                (codigo_articulo, pasillo, estanteria, balda, mapa_x, mapa_y, verificado)
                VALUES (%s, %s, %s, '0', %s, %s, 1)
                ON DUPLICATE KEY UPDATE 
                mapa_x=VALUES(mapa_x), mapa_y=VALUES(mapa_y), verificado=1
            """
            params = (qr_id, pasillo, estanteria, pos_clic.x(), pos_clic.y())

            # Se asume la existencia de obtener_conexion() en el scope global
            with obtener_conexion() as conn:
                cursor = conn.cursor()
                cursor.execute(query_sql, params)
                conn.commit()

            # --- FASE 2: REGISTRO DE NODO LOGÍSTICO (Motor A*) ---
            nombre_nodo = f"{pasillo} | {estanteria}"
            nuevo_nodo = {
                "id_qr": qr_id,
                "etiqueta": nombre_nodo,
                "x": round(pos_clic.x(), 2),
                "y": round(pos_clic.y(), 2),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            if not hasattr(self.visor_admin, "puntos_interes"):
                self.visor_admin.puntos_interes = []

            # Evitamos duplicados en la lista de nodos local
            self.visor_admin.puntos_interes = [
                p for p in self.visor_admin.puntos_interes if p["id_qr"] != qr_id
            ]
            self.visor_admin.puntos_interes.append(nuevo_nodo)

            # --- FASE 3: REPRESENTACIÓN VISUAL Y PERSISTENCIA ---
            if hasattr(self.visor_admin, "colocar_marcador_3d"):
                # Coloca el pin visual en la escena
                self.visor_admin.colocar_marcador_3d(pos_clic, nombre_nodo)

            if hasattr(self, "guardar_configuracion_gps"):
                # Persistencia en el JSON del mapa
                self.guardar_configuracion_gps()

            # --- FASE 4: FEEDBACK TÉCNICO (Status Bar) ---
            if self.window().statusBar():
                self.window().statusBar().setStyleSheet(
                    """
                    QStatusBar { background: #0D1117; color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900; font-size: 10px; }
                """
                )
                self.window().statusBar().showMessage(
                    f"💾 REGISTRO COMPLETADO: {nombre_nodo} | EPC: {qr_id} | POS: {nuevo_nodo['x']},{nuevo_nodo['y']}",
                    7000,
                )

        except Exception as e:
            print(f"Error en finalizar_grabacion_logistica: {e}")
            msg = QMessageBox(self)
            msg.setWindowTitle("🛑 " + tr("ubic.err_critical_title", default="ERROR CRÍTICO"))
            msg.setText(f"Fallo en la cadena de registro SQL/JSON:\n{str(e)}")
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setStyleSheet(
                estilo_base_msg + "QMessageBox { border: 2px solid #F85149; }"
            )
            msg.exec()

    # ============================================================
    # BLOQUE GENERACIÓN DE CÓDIGOS QR
    # ============================================================

    def generar_qr_estanteria(self, epc, nombre, pos_x, pos_y, es_satelite=False):
        """
        Generador Universal de Etiquetas QR con Pie de Foto.
        MANTIENE: Lógica de limpieza, rutas y JSON original.
        AÑADE: Nombre visual debajo del QR (Primera letra mayúscula).
        """
        import glob
        import json
        import os
        import re
        from datetime import datetime

        from PIL import Image, ImageDraw, ImageFont  # Necesario para el pie de foto

        try:
            # --- LIMPIEZA DE NOMBRE (QUITAR COORDENADAS EXTRAÑAS) ---
            nombre_real = re.sub(
                r"\s*-?\d+(\.\d+)?M,?\s*-?\d+(\.\d+)?M", "", nombre
            ).strip()

            # 1. Definición de Prefijos y Tipos
            prefijo_archivo = "qr_satelite" if es_satelite else "QR_ESTANTERIA"
            tipo_entidad = "SATELITE" if es_satelite else "ESTANTERIA"
            color_feedback = "#00FFC6"

            # 2. Sincronización de Carpeta
            carpeta_qrs = os.path.join("documentos", "qr_ubicaciones")
            if not os.path.exists(carpeta_qrs):
                os.makedirs(carpeta_qrs)

            # Limpieza de nombre para el archivo
            nombre_limpio = nombre_real.replace(" ", "_").upper()

            # --- 3. LIMPIEZA DE VERSIONES PREVIAS ---
            patron_antiguo = os.path.join(
                carpeta_qrs, f"{prefijo_archivo}_{nombre_limpio}_*.png"
            )
            for archivo_viejo in glob.glob(patron_antiguo):
                try:
                    os.remove(archivo_viejo)
                except:
                    pass

            # --- 4. GENERACIÓN DE LA TRAMA DE DATOS (JSON) ---
            datos_qr = {
                "tipo": tipo_entidad,
                "nombre": nombre_real,
                "epc": epc,
                "coords": {"x": round(pos_x, 2), "y": round(pos_y, 2)},
                "fecha_gen": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            trama_datos = json.dumps(datos_qr)

            # --- 5. CONFIGURACIÓN TÉCNICA DEL QR ---
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=4,
            )
            qr.add_data(trama_datos)
            qr.make(fit=True)

            # --- 6. RENDERIZADO CON PIE DE FOTO (USANDO PILLOW) ---
            # Generamos la imagen base del QR
            img_qr = qr.make_image(fill_color="black", back_color="white").convert(
                "RGB"
            )

            # Calculamos espacio extra para el texto (alto original + 50px aprox)
            ancho, alto = img_qr.size
            espacio_texto = 60
            nueva_img = Image.new("RGB", (ancho, alto + espacio_texto), "white")
            nueva_img.paste(img_qr, (0, 0))

            # Dibujamos el texto (Nombre con Capitalize)
            draw = ImageDraw.Draw(nueva_img)

            # Intentamos cargar Segoe UI Bold, si no, usa la fuente por defecto
            try:
                fuente = ImageFont.truetype("segoebl.ttf", 25)  # Bold
            except:
                try:
                    fuente = ImageFont.truetype("arialbd.ttf", 25)
                except:
                    fuente = ImageFont.load_default()

            texto_pie = nombre_real.capitalize()

            # Centrar el texto
            bbox = draw.textbbox((0, 0), texto_pie, font=fuente)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(
                ((ancho - tw) / 2, alto - 10), texto_pie, fill="black", font=fuente
            )

            # --- 7. GUARDADO FINAL ---
            marca_tiempo = datetime.now().strftime("%H%M%S")
            nombre_archivo = f"{prefijo_archivo}_{nombre_limpio}_{marca_tiempo}.png"
            ruta_completa = os.path.join(carpeta_qrs, nombre_archivo)

            nueva_img.save(ruta_completa)
            print(f"[OK] QR {tipo_entidad} con Nombre Generado: {ruta_completa}")

            # --- 8. FEEDBACK VISUAL EN STATUS BAR ---
            if self.window() and self.window().statusBar():
                sb = self.window().statusBar()
                sb.setStyleSheet(
                    f"background-color: {color_feedback}; color: #0D1117; font-weight: 900; font-family: 'Segoe UI';"
                )
                sb.showMessage(tr("ubic.qr_exported", default="QR {tipo} EXPORTADO: {archivo}", tipo=tipo_entidad, archivo=nombre_archivo), 5000)

            return ruta_completa

        except Exception as e:
            print(f"[ERROR] Generando QR: {e}")
            if hasattr(self, "mostrar_mensaje_error"):
                self.mostrar_mensaje_error(
                    tr("ubic.err_qr_gen", default="Error al generar QR {tipo}", tipo=tipo_entidad), str(e)
                )
            return None

    def mostrar_mensaje_error(self, titulo, mensaje):
        from PyQt6.QtWidgets import QMessageBox

        msg = QMessageBox(self)
        msg.setWindowTitle(titulo)
        msg.setText(mensaje)
        msg.setStyleSheet(
            "QMessageBox { background-color: #0D1117; } QLabel { color: white; }"
        )
        msg.exec()

    # ============================================================
    # BLOQUE GUARDADO DE DATOS DE UBICACIÓN
    # ============================================================

    def finalizar_ubicacion(self, contexto):
        """
        Procesa los datos del formulario, actualiza MariaDB y sincroniza con el mapa.
        'contexto' define si se actualiza la ubicacion de tienda (LINEAL) o de bodega (ALMACEN).
        """
        from PyQt6.QtWidgets import QMessageBox

        # 1. Recoleccion de datos
        codigo_art = getattr(self, "articulo_seleccionado", None)
        pasillo = self.input_pasillo.text().strip().upper()
        estanteria = self.input_estanteria.text().strip().upper()
        nivel = self.input_nivel.text().strip().upper()

        if not codigo_art or not pasillo or not estanteria or not nivel:
            QMessageBox.warning(
                self,
                "DATOS INCOMPLETOS",
                "Asegurese de seleccionar un articulo y completar Pasillo, Estante y Nivel.",
            )
            return

        coord_mapa = None

        try:
            with obtener_conexion() as conn:
                cursor = conn.cursor()

                ubicacion_legible = f"{pasillo}-{estanteria}-{nivel}"
                es_lineal = bool(contexto and "LINEAL" in contexto.upper())

                # 2. Actualizacion principal de ubicacion comercial
                if es_lineal:
                    sql = """
                        UPDATE articulos 
                        SET pasillo = %s, estanteria = %s, nivel = %s,
                            ubicacion_tienda = %s,
                            incidencia_ubicacion = 0, ultima_actualizacion = NOW()
                        WHERE codigo = %s
                    """
                else:
                    sql = """
                        UPDATE articulos 
                        SET pasillo_almacen = %s, estanteria_almacen = %s, nivel_almacen = %s,
                            ubicacion_almacen = %s,
                            incidencia_ubicacion = 0, ultima_actualizacion = NOW()
                        WHERE codigo = %s
                    """

                cursor.execute(
                    sql, (pasillo, estanteria, nivel, ubicacion_legible, codigo_art)
                )

                # 3. Buscar coordenadas de la estanteria en infraestructura
                cursor.execute(
                    """
                    SELECT mapa_x, mapa_y
                    FROM ubicaciones
                    WHERE pasillo = %s AND estanteria = %s
                      AND mapa_x IS NOT NULL AND mapa_y IS NOT NULL
                      AND (mapa_x != 0 OR mapa_y != 0)
                    ORDER BY (codigo_articulo IS NULL OR codigo_articulo = '') DESC,
                             verificado DESC,
                             id DESC
                    LIMIT 1
                    """,
                    (pasillo, estanteria),
                )
                coord_mapa = cursor.fetchone()
                mapa_x = float(coord_mapa[0]) if coord_mapa else None
                mapa_y = float(coord_mapa[1]) if coord_mapa else None

                # 4. Upsert del articulo en la tabla tecnica de ubicaciones
                cursor.execute(
                    """
                    INSERT INTO ubicaciones
                    (codigo_articulo, pasillo, estanteria, balda, mapa_x, mapa_y, verificado)
                    VALUES (%s, %s, %s, %s, %s, %s, 1)
                    ON DUPLICATE KEY UPDATE
                        pasillo = VALUES(pasillo),
                        estanteria = VALUES(estanteria),
                        balda = VALUES(balda),
                        mapa_x = COALESCE(VALUES(mapa_x), mapa_x),
                        mapa_y = COALESCE(VALUES(mapa_y), mapa_y),
                        verificado = IF(
                            COALESCE(VALUES(mapa_x), mapa_x) IS NULL
                            AND COALESCE(VALUES(mapa_y), mapa_y) IS NULL,
                            verificado,
                            1
                        )
                    """,
                    (codigo_art, pasillo, estanteria, nivel, mapa_x, mapa_y),
                )

                # 5. Si tenemos coordenadas, sincronizamos tambien en articulos
                if coord_mapa:
                    cursor.execute(
                        """
                        UPDATE articulos
                        SET mapa_x = %s, mapa_y = %s
                        WHERE codigo = %s
                        """,
                        (mapa_x, mapa_y, codigo_art),
                    )

                conn.commit()

            # 6. Feedback visual y reset
            if hasattr(self, "mostrar_notificacion_temporal"):
                self.mostrar_notificacion_temporal(
                    f"[OK] ASIGNADO: {pasillo}-{estanteria}-{nivel}"
                )

            if not coord_mapa and self.window().statusBar():
                self.window().statusBar().setStyleSheet(
                    "color: #FFB86C; font-family: 'Segoe UI'; font-weight: 900;"
                )
                self.window().statusBar().showMessage(
                    "Ubicacion textual guardada, pero la estanteria aun no tiene coordenadas en el mapa.",
                    5000,
                )

            # Limpiamos inputs y variables temporales
            self.resetear_formulario_asignacion()

            # Si tienes una lista de articulos lateral, la refrescamos
            if hasattr(self, "cargar_lista_articulos_admin"):
                self.cargar_lista_articulos_admin()

        except Exception as e:
            QMessageBox.critical(
                self, "ERROR DE PERSISTENCIA", f"Error al guardar: {e}"
            )

    def resetear_formulario_asignacion(self):
        """
        Limpia todos los campos y prepara la UI para un nuevo escaneo.
        Añade feedback visual de 'limpieza' para flujo continuo.
        """
        from PyQt6.QtCore import QTimer

        # 1. Limpiar inputs de identificación
        self.input_scan.setEnabled(True)
        self.input_scan.clear()
        self.input_scan.setFocus()  # Vital para escaneo continuo sin ratón

        self.btn_validar.setEnabled(True)

        # 2. Limpiar formulario de ubicación y bloquear hasta nueva validación
        for field in [self.input_pasillo, self.input_estanteria, self.input_nivel]:
            field.clear()
            field.setEnabled(False)
            field.setStyleSheet(
                "background-color: #0D1117; color: #484F58; border: 1px solid #30363D;"
            )

        # 3. Resetear etiquetas de estado
        self.info_art.setText(tr("ubic.waiting_scan", default="Icono ESPERANDO ESCANEO O CÓDIGO..."))
        self.info_art.setStyleSheet(
            "color: #8B949E; font-family: 'Segoe UI'; font-size: 12px; font-weight: 900;"
        )
        self.btn_guardar_final.setEnabled(False)

        # 4. Feedback Visual: "Destello de preparación"
        # Cambiamos el borde a turquesa brevemente para confirmar el reset
        estilo_reset = "QFrame#panel_oscuro { background-color: #161B22; border: 2px solid #00F0FF; border-radius: 12px; }"
        estilo_normal = "QFrame#panel_oscuro { background-color: #161B22; border: 1px solid #30363D; border-radius: 12px; }"

        self.panel_search.setStyleSheet(estilo_reset)
        # Volvemos al estado neutro tras 400ms
        QTimer.singleShot(400, lambda: self.panel_search.setStyleSheet(estilo_normal))

        # 5. Gestión de memoria
        if hasattr(self, "articulo_seleccionado"):
            self.articulo_seleccionado = (
                None  # Mejor que 'del' para evitar errores de referencia posteriores
            )

        # Opcional: Si tienes una imagen del artículo anterior, límpiala aquí también
        if hasattr(self, "lbl_foto_articulo"):
            self.lbl_foto_articulo.clear()
            self.lbl_foto_articulo.setText(tr("ubic.no_image_icon", default="Icono SIN IMAGEN"))

    def actualizar_incidencia_gps(self, codigo_art):
        """
        Registra una discrepancia logística. Si el operario no encuentra el
        producto en la ruta trazada, este método marca el error en MariaDB.
        """
        # 1. Confirmación de seguridad para evitar reportes accidentales
        confirmacion = QMessageBox.question(
            self,
            "REPORTAR INCIDENCIA",
            f"¿Confirmas que el artí­culo {codigo_art} NO se encuentra en la ubicación indicada?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if confirmacion == QMessageBox.StandardButton.No:
            return

        try:

            with obtener_conexion() as conn:
                cursor = conn.cursor()

                # 2. Marcamos 'incidencia_ubicacion' como 1
                # Esto hará que aparezca en ROJO en la lista del administrador
                sql = """
                    UPDATE articulos 
                    SET incidencia_ubicacion = 1, 
                        ultima_actualizacion = NOW() 
                    WHERE codigo = %s
                """
                cursor.execute(sql, (codigo_art,))
                conn.commit()

            # 3. Feedback Visual e Interfaz
            if self.window().statusBar():
                self.window().statusBar().setStyleSheet(
                    "color: #F85149; font-family: 'Segoe UI'; font-weight: 900;"
                )
                self.window().statusBar().showMessage(
                    f"Icono INCIDENCIA REPORTADA PARA EL ARTÍCULO {codigo_art}",
                    7000,
                )

            # 4. Limpieza del mapa: Borramos la ruta actual ya que el destino es erróneo
            if hasattr(self, "visor_mapa"):
                self.visor_mapa.limpiar_ruta()
                # Opcional: Volver a la lista de búsqueda
                # self.stack.setCurrentIndex(2)

        except Exception as e:
            print(f"Error al reportar incidencia: {e}")
            QMessageBox.critical(
                self,
                "ERROR",
                "No se pudo conectar con la base de datos para reportar la incidencia.",
            )

    def crear_vista_gestion_estructura(self):
        """
        Interfaz de Gestión de Estructura:
        - REESTRUCTURACIÓN: Eliminación de QListWidget y expansión de botonería.
        - ESTÉTICA: Título "UBICAR ACTIVOS" en Segoe UI 900.
        - VISOR: Sincronización de calidad visual con GPS Interno y Botones de Zoom.
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QPainter
        from PyQt6.QtWidgets import (
            QFrame,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QSizePolicy,
            QVBoxLayout,
            QWidget,
        )

        vista = QWidget()
        layout = QHBoxLayout(vista)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # --- PANEL IZQUIERDO: CONTROL DE ACTIVOS ---
        panel_izquierdo = QFrame()
        # Responsive (P2): puede encoger en pantallas pequeñas (antes fijo 300).
        panel_izquierdo.setMinimumWidth(240)
        panel_izquierdo.setMaximumWidth(300)
        panel_izquierdo.setStyleSheet(
            "QFrame { background-color: #05070A; border-radius: 18px; border: 1.5px solid #1C2128; }"
        )
        lyt_izq = QVBoxLayout(panel_izquierdo)
        lyt_izq.setContentsMargins(20, 25, 20, 25)
        lyt_izq.setSpacing(15)

        # AJUSTE QUIRÚRGICO: Título estilizado sin recuadro
        self.lbl_repo = QLabel(tr("ubic.locate_assets", default="UBICAR ACTIVOS"))
        self.lbl_repo.setStyleSheet(
            """
            color: #00F0FF; 
            font-family: 'Segoe UI'; 
            font-weight: 900; 
            font-size: 14px; 
            letter-spacing: 1.5px; 
            border: none;
            background: transparent;
            """
        )
        self.lbl_repo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lyt_izq.addWidget(self.lbl_repo)

        # Estilo base para los botones gigantes
        estilo_botones_gigantes = """
            QPushButton { 
                background-color: #0F141A; 
                color: #00F5FF; 
                border: 1.5px solid #00F5FF; 
                border-radius: 14px; 
                font-family: 'Segoe UI'; 
                font-weight: 900; 
                font-size: 13px;
            }
            QPushButton:hover { 
                background-color: #00F5FF; 
                border-color: #00F5FF; 
                color: #0D1117; 
            }
            QPushButton:pressed {
                background-color: #FFFFFF;
                color: #0D1117;
            }
        """

        # Botón 1: Ubicar
        def _iniciar_proceso_ubicacion():
            self.abrir_formulario_ubicacion_estanteria(permiso_clic=False)

        self.btn_ubicar_activo = QPushButton("📍 " + tr("ubic.btn_locate_shelf", default="UBICAR\nESTANTERÍA"))
        self.btn_ubicar_activo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.btn_ubicar_activo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ubicar_activo.setStyleSheet(estilo_botones_gigantes)
        self.btn_ubicar_activo.clicked.connect(_iniciar_proceso_ubicacion)
        lyt_izq.addWidget(self.btn_ubicar_activo, stretch=1)

        # Botón 2: Satélite
        self.btn_crear_satelite = QPushButton("🛰️ " + tr("ubic.btn_install_sat", default="INSTALAR\nSATÉLITE"))
        self.btn_crear_satelite.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.btn_crear_satelite.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_crear_satelite.setStyleSheet(estilo_botones_gigantes)
        self.btn_crear_satelite.clicked.connect(self.activar_modo_satelite)
        lyt_izq.addWidget(self.btn_crear_satelite, stretch=1)

        # Botón 3: QRs
        self.btn_ver_qrs = QPushButton("📂 " + tr("ubic.btn_view_qr", default="VER\nCÓDIGOS QR"))
        self.btn_ver_qrs.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.btn_ver_qrs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ver_qrs.setStyleSheet(estilo_botones_gigantes)
        self.btn_ver_qrs.clicked.connect(self.abrir_carpeta_qrs)
        lyt_izq.addWidget(self.btn_ver_qrs, stretch=1)

        # --- PANEL DERECHO: WORKSPACE DE INGENIERÍA ---
        panel_derecho = QWidget()
        panel_derecho.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        lyt_der = QVBoxLayout(panel_derecho)
        lyt_der.setContentsMargins(0, 0, 0, 0)
        lyt_der.setSpacing(10)

        # NIVEL 1: MODOS DE EDICIÓN
        n1_frame = QFrame()
        lyt_n1 = QHBoxLayout(n1_frame)
        lyt_n1.setContentsMargins(0, 0, 0, 5)

        self.btn_modo_pintar = QPushButton("🖌️ " + tr("ubic.paint_off", default="MODO PINTADO: OFF"))
        self.btn_modo_pintar.setCheckable(True)
        self.btn_modo_pintar.setFixedSize(190, 42)
        self.btn_modo_pintar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_modo_pintar.setStyleSheet(
            """
            QPushButton { 
                background-color: #161B22; color: #8B949E; border: 1px solid #30363D; border-radius: 10px; 
                font-family: 'Segoe UI'; font-weight: 900; font-size: 11px;
            }
            QPushButton:hover { background-color: #FFFFFF; color: #161B22; border: 1px solid #FFFFFF; }
            QPushButton:checked { background-color: #F85149; color: white; border: 1.5px solid #FF7B72; }
            """
        )
        self.btn_modo_pintar.clicked.connect(self.alternar_modo_pintado)

        self.btn_guardar = QPushButton("✅ " + tr("ubic.save_finish", default="FINALIZAR Y GUARDAR"))
        self.btn_guardar.setFixedSize(220, 42)
        self.btn_guardar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_guardar.setStyleSheet(
            self._estilo_boton_neon(
                bg="#238636",
                fg="#0E1117",
                border="#00FFC6",
                hover_bg="#FFFFFF",
                hover_fg="#0E1117",
            )
        )
        self.btn_guardar.setFont(self._crear_fuente_segoe(9))
        self.btn_guardar.clicked.connect(self.guardar_configuracion_gps)

        lyt_n1.addWidget(self.btn_modo_pintar)
        lyt_n1.addStretch()

        # LABEL DE PLANTA ACTUAL
        planta_idx = getattr(self, "planta_actual", 0)
        self.lbl_planta_actual = QLabel("📍 " + tr("ubic.no_plan", default="SIN PLANO"))
        self.lbl_planta_actual.setStyleSheet(
            "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900; font-size: 14px; letter-spacing: 2px;"
        )
        self._registrar_label_planta(self.lbl_planta_actual)
        lyt_n1.addWidget(self.lbl_planta_actual)
        lyt_n1.addStretch()
        lyt_n1.addWidget(self.btn_guardar)

        # NIVEL 2: TELEMETRÍA Y CONTROLES DE CÁMARA
        n2_frame = QFrame()
        n2_frame.setStyleSheet(
            "background-color: #05070A; border-radius: 14px; border: 1px solid #1C2128;"
        )
        lyt_n2 = QHBoxLayout(n2_frame)
        lyt_n2.setContentsMargins(10, 8, 10, 8)

        self.btn_escala = QPushButton("📏 " + tr("ubic.start_calib", default="INICIAR CALIBRACIÓN"))
        self.btn_escala.setFixedSize(200, 38)
        self.btn_escala.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_escala.setFont(self._crear_fuente_segoe(12))
        self.btn_escala.setStyleSheet(
            self._estilo_boton_neon(
                bg="#2EA043",
                fg="#FFFFFF",
                border="#3FB950",
                hover_bg="#FFFFFF",
                hover_fg="#2EA043",
                radius=8,
                padding="8px 12px",
                font_size=12,
            )
        )
        self.btn_escala.clicked.connect(self._clic_boton_escala)

        self.btn_deshacer_muro = QPushButton("↩️ " + tr("ubic.undo", default="DESHACER"))
        self.btn_deshacer_muro.setEnabled(False)
        self.btn_deshacer_muro.setFixedSize(125, 38)
        self.btn_deshacer_muro.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_deshacer_muro.setStyleSheet(
            self._estilo_boton_neon(
                bg="#21262D",
                fg="#C9D1D9",
                border="#30363D",
                hover_bg="#C9D1D9",
                hover_fg="#21262D",
            )
        )
        self.btn_deshacer_muro.clicked.connect(self.gestionar_deshacer_muro)
        self.btn_deshacer_muro.setFont(self._crear_fuente_segoe(9))

        self.btn_rehacer_muro = QPushButton("↪️ " + tr("ubic.redo", default="REHACER"))
        self.btn_rehacer_muro.setEnabled(False)
        self.btn_rehacer_muro.setFixedSize(110, 38)
        self.btn_rehacer_muro.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_rehacer_muro.setStyleSheet(
            self._estilo_boton_neon(
                bg="#21262D",
                fg="#C9D1D9",
                border="#30363D",
                hover_bg="#C9D1D9",
                hover_fg="#21262D",
            )
        )
        self.btn_rehacer_muro.clicked.connect(self.gestionar_rehacer_muro)
        self.btn_rehacer_muro.setFont(self._crear_fuente_segoe(9))

        self.btn_ver_matriz = QPushButton("👁️ " + tr("ubic.matrix_off", default="MATRIZ: OFF"))
        self.btn_ver_matriz.setCheckable(True)
        self.btn_ver_matriz.setFixedSize(130, 38)
        self.btn_ver_matriz.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ver_matriz.setFixedSize(130, 38)
        self.btn_ver_matriz.setFont(self._crear_fuente_segoe(11))
        self.btn_ver_matriz.setStyleSheet(
            self._estilo_boton_neon(
                bg="#21262D",
                fg="#C9D1D9",
                border="#30363D",
                hover_bg="#C9D1D9",
                hover_fg="#21262D",
                font_size=11,
            )
        )
        self.btn_ver_matriz.clicked.connect(self.alternar_visibilidad_matriz)

        # Controles de Zoom para el mapa
        self.btn_zoom_out = _NeonZoomBtn("—")
        self.btn_zoom_out.clicked.connect(lambda: self.ajustar_zoom(0.8))

        self.btn_zoom_in = _NeonZoomBtn("+")
        self.btn_zoom_in.clicked.connect(lambda: self.ajustar_zoom(1.25))

        lyt_n2.addWidget(self.btn_escala)
        lyt_n2.addWidget(self.btn_deshacer_muro)
        lyt_n2.addWidget(self.btn_rehacer_muro)
        lyt_n2.addWidget(self.btn_ver_matriz)
        lyt_n2.addStretch()  # Empuja el zoom a la derecha
        lyt_n2.addWidget(self.btn_zoom_out)
        lyt_n2.addWidget(self.btn_zoom_in)

        # VISOR PRINCIPAL: SINCRO CON GPS INTERNO
        self.visor_admin.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.visor_admin.setStyleSheet(
            "QGraphicsView { border: 2px solid #00FFC6; background-color: #050505; border-radius: 20px; }"
        )
        self.visor_admin.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.visor_admin.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.visor_admin.setViewportUpdateMode(
            self.visor_admin.ViewportUpdateMode.FullViewportUpdate
        )

        # CONTENEDOR DE VISOR Y FLECHAS
        lyt_visor_container = QHBoxLayout()
        lyt_visor_container.setSpacing(8)

        estilo_flecha = """
            QPushButton {
                background-color: #161B22; color: #8B949E; border: 1px solid #30363D;
                border-radius: 12px; font-family: 'Segoe UI'; font-weight: 900; font-size: 20px;
            }
            QPushButton:hover { background-color: #00F0FF; color: #0D1117; border-color: #00F0FF; }
        """

        self.btn_planta_prev = QPushButton("<")
        self.btn_planta_prev.setFixedSize(50, 120)
        self.btn_planta_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_planta_prev.setStyleSheet(estilo_flecha)
        self.btn_planta_prev.clicked.connect(lambda: self.navegar_planta(-1))

        self.btn_planta_next = QPushButton(">")
        self.btn_planta_next.setFixedSize(50, 120)
        self.btn_planta_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_planta_next.setStyleSheet(estilo_flecha)
        self.btn_planta_next.clicked.connect(lambda: self.navegar_planta(1))

        lyt_visor_container.addWidget(self.btn_planta_prev)
        lyt_visor_container.addWidget(self.visor_admin)
        lyt_visor_container.addWidget(self.btn_planta_next)

        lyt_der.addWidget(n1_frame)
        lyt_der.addWidget(n2_frame)
        lyt_der.addLayout(lyt_visor_container)

        layout.addWidget(panel_izquierdo)
        layout.addWidget(panel_derecho)

        self.actualizar_estado_bloqueo(bloquear=True)
        self._actualizar_botones_historial()
        self._aplicar_fuente_segoe(vista)
        return vista

    def alternar_visibilidad_matriz(self):
        """
        Alterna la visibilidad de la matriz A* con feedback visual dinámico.
        Estilo unificado con el resto de la aplicación y cursor interactivo.
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication

        if not hasattr(self, "visor_admin") or not self.visor_admin:
            return

        # 1. ACTUALIZAR ESTADO (Sincronizado con el renderizador)
        estado = self.btn_ver_matriz.isChecked()
        self.visor_admin.mostrar_matriz = estado
        self.visor_admin.mostrando_matriz = estado
        if hasattr(self, "visor_mapa") and self.visor_mapa:
            self.visor_mapa.mostrar_matriz = estado
            self.visor_mapa.mostrando_matriz = estado

        # 2. ESTILO VISUAL DEL BOTÓN
        base_style = """
            QPushButton { 
                font-family: 'Segoe UI', sans-serif;
                font-weight: 900; 
                font-size: 11px;
                border-radius: 8px; 
                padding: 8px 12px;
                border: 1px solid #30363D;
            }
        """

        if estado:
            # --- ESTADO: ON ---
            self.btn_ver_matriz.setText("👁️ " + tr("ubic.matrix_on", default="MATRIZ: ON"))
            self.btn_ver_matriz.setStyleSheet(
                base_style
                + """
                QPushButton { background-color: #D29922; color: #0D1117; }
                QPushButton:hover { background-color: #0D1117; color: #D29922; border: 1px solid #D29922; }
            """
            )
        else:
            # --- ESTADO: OFF ---
            self.btn_ver_matriz.setText("🙈 " + tr("ubic.matrix_off", default="MATRIZ: OFF"))
            self.btn_ver_matriz.setStyleSheet(
                base_style
                + """
                QPushButton { background-color: #161B22; color: #8B949E; }
                QPushButton:hover { background-color: #FFFFFF; color: #161B22; border: 1px solid #FFFFFF; }
            """
            )

        # 3. INTERACCIÓN Y REFRESCO CRÍTICO
        self.btn_ver_matriz.setCursor(Qt.CursorShape.PointingHandCursor)

        # Forzamos la ejecución del renderizado para limpiar o mostrar la capa roja
        if hasattr(self.visor_admin, "actualizar_mapa_calor"):
            self.visor_admin.actualizar_mapa_calor()

        # Refrescos de seguridad
        if hasattr(self.visor_admin, "viewport") and self.visor_admin.viewport():
            self.visor_admin.viewport().update()
            for item in getattr(self.visor_admin, "historial_muros", []):
                try:
                    item.setVisible(False)
                except Exception:
                    continue
            self.visor_admin.modo_pintar = False
            if hasattr(self, "btn_modo_pintar"):
                self.btn_modo_pintar.setChecked(False)
                self.btn_modo_pintar.setText(tr("ubic.paint_walls", default="PINTAR MUROS"))

        QApplication.processEvents()

    def actualizar_estado_bloqueo(self, bloquear=None):
        """
        Gestión de desbloqueo en CASCADA (Fases 1, 2 y 3):
        1. Escala: Siempre activa (Inmunidad).
        2. Muros: Se activan tras calibrar Escala.
        3. Herramientas: Se activan tras detectar Muros o Matriz.
        """
        import numpy as np
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QGraphicsOpacityEffect

        # --- 1. DETECCIÓN DE ESTADOS (Banderas de progreso) ---
        # Fase 1: ¿Tenemos escala?
        escala_ok = (
            hasattr(self.visor_admin, "punto_ancla")
            and self.visor_admin.punto_ancla is not None
        )

        # Fase 2: ¿Hay muros dibujados o cargados?
        from PyQt6.QtWidgets import QGraphicsView as _QGV
        escena = _QGV.scene(self.visor_admin)

        muros_en_escena = (
            any(item.data(0) == "MURO_TECNICO" for item in escena.items())
            if escena
            else False
        )

        matriz_en_memoria = (
            hasattr(self.visor_admin, "matriz_obstaculos")
            and self.visor_admin.matriz_obstaculos is not None
            and np.any(self.visor_admin.matriz_obstaculos == 1)
        )

        muros_ok = (
            getattr(self, "muros_completados", False)
            or muros_en_escena
            or matriz_en_memoria
        )

        # --- 2. DEFINICIÓN DE GRUPOS ---
        botones_fase_2 = ["btn_modo_pintar"]  # Requieren Escala
        botones_fase_3 = [  # Requieren Escala + Muros
            "btn_ubicar_activo",
            "btn_crear_satelite",
            "btn_ver_matriz",
            "btn_ver_qrs",
            "btn_guardar",
        ]

        # --- 3. PROCESAR CASCADA ---
        for nombre_btn in botones_fase_2 + botones_fase_3:
            btn = getattr(self, nombre_btn, None)
            if not btn:
                continue

            # Lógica de dependencia
            if nombre_btn in botones_fase_2:
                esta_desbloqueado = escala_ok
            else:
                esta_desbloqueado = escala_ok and muros_ok

            # Aplicar estado funcional
            btn.setEnabled(esta_desbloqueado)
            btn.setCursor(
                Qt.CursorShape.PointingHandCursor
                if esta_desbloqueado
                else Qt.CursorShape.ForbiddenCursor
            )

            # Gestión de Opacidad (Efecto Visual Ghosting)
            eff = btn.graphicsEffect()
            if not isinstance(eff, QGraphicsOpacityEffect):
                eff = QGraphicsOpacityEffect(btn)
                btn.setGraphicsEffect(eff)
            eff.setOpacity(1.0 if esta_desbloqueado else 0.3)

        # --- 4. GESTIÓN DEL BOTÓN ESCALA (INMUNE Y DINÁMICO) ---
        if hasattr(self, "btn_escala") and self.btn_escala:
            self.btn_escala.setEnabled(True)
            self.btn_escala.setCursor(Qt.CursorShape.PointingHandCursor)

            if not escala_ok:
                # Estilo Éxito Inicial (Verde — calibración pendiente pero disponible)
                self.btn_escala.setText("📏 " + tr("ubic.calib_scale", default="CALIBRAR ESCALA"))
                self.btn_escala.setStyleSheet(
                    """
                    QPushButton {
                        background-color: #2EA043; color: white; font-weight: 900;
                        border-radius: 8px; border: 1px solid #3FB950; padding: 8px;
                        font-family: 'Segoe UI'; font-size: 12px;
                    }
                    QPushButton:hover { background-color: #3FB950; }
                """
                )
            else:
                # Estilo Éxito Calibrado (Verde — escala establecida)
                self.btn_escala.setText("📐 " + tr("ubic.recalib_scale", default="RECALIBRAR ESCALA"))
                self.btn_escala.setStyleSheet(
                    """
                    QPushButton {
                        background-color: #2EA043; color: #FFFFFF; font-weight: 900;
                        border-radius: 8px; border: 1px solid #3FB950; padding: 8px;
                        font-family: 'Segoe UI'; font-size: 12px;
                    }
                    QPushButton:hover { background-color: #3FB950; }
                """
                )

        # --- 5. GESTIÓN DE DESHACER (SIEMPRE DISPONIBLE) ---
        btn_undo = getattr(self, "btn_deshacer_muro", None)
        if btn_undo:
            btn_undo.setEnabled(True)
            eff_undo = btn_undo.graphicsEffect()
            if not isinstance(eff_undo, QGraphicsOpacityEffect):
                eff_undo = QGraphicsOpacityEffect(btn_undo)
                btn_undo.setGraphicsEffect(eff_undo)
            eff_undo.setOpacity(1.0)

        # --- 6. FEEDBACK EN STATUS BAR ---
        win = self.window()
        if win and win.statusBar():
            sb = win.statusBar()
            if not escala_ok:
                sb.setStyleSheet(
                    "color: #F85149; font-family: 'Segoe UI'; font-weight: 900;"
                )
                sb.showMessage("SISTEMA BLOQUEADO: Se requiere Calibración de Escala.")
            elif not muros_ok:
                sb.setStyleSheet(
                    "color: #00F5FF; font-family: 'Segoe UI'; font-weight: 900;"
                )
                sb.showMessage(
                    "ESCALA OK: Defina los muros técnicos para habilitar herramientas."
                )
            else:
                sb.setStyleSheet(
                    "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900;"
                )
                sb.showMessage("SISTEMA TOTALMENTE OPERATIVO")

    # ============================================================
    # BLOQUE MODO PINTADO DE MUROS
    # ============================================================

    def alternar_modo_pintado(self):
        """
        Activa/Desactiva la brocha de muros.
        AJUSTE QUIRÚRGICO: Accesos seguros a escena/viewport y limpieza atómica de ítems.
        """
        if not hasattr(self, "visor_admin") or not self.visor_admin:
            return

        from PyQt6.QtCore import Qt

        # 1. Sincronización con el botón (Toggle)
        activo = self.btn_modo_pintar.isChecked()
        self.visor_admin.modo_pintar = activo

        # Aplicamos cursor de manita siempre (solicitado)
        self.btn_modo_pintar.setCursor(Qt.CursorShape.PointingHandCursor)

        if activo:
            # --- MODO ACTIVADO: EL BOTÓN SE CONVIERTE EN "GUARDAR" ---
            self.btn_modo_pintar.setText("✔ " + tr("ubic.paint_save", default="GUARDAR CAMBIOS"))
            self.btn_modo_pintar.setFont(self._crear_fuente_segoe(9))
            self.btn_modo_pintar.setStyleSheet(
                self._estilo_boton_neon(
                    bg="#238636",
                    fg="#0E1117",
                    border="#31AF50",
                    hover_bg="#FFFFFF",
                    hover_fg="#0E1117",
                    radius=8,
                    padding="8px 12px",
                    font_size=11,
                )
            )

            # EXCLUSIVIDAD: Desactivamos otros modos
            self.visor_admin.modo_calibrar = False
            self.visor_admin.esperando_ancla_0 = False

            # --- LIMPIEZA INMEDIATA DE CALIBRACIÓN (Safe Access) ---
            for attr in ["linea_x", "linea_y", "m_x1", "m_x2", "m_y1", "m_y2"]:
                item = getattr(self.visor_admin, attr, None)
                if item:
                    try:
                        item.setVisible(False)
                    except (RuntimeError, AttributeError):
                        setattr(self.visor_admin, attr, None)

            # Bloqueo estricto de botones
            botones_a_bloquear = [
                getattr(self, "btn_ubicar_activo", None),
                getattr(self, "btn_crear_satelite", None),
                getattr(self, "btn_escala", None),
            ]
            for btn in botones_a_bloquear:
                if btn:
                    btn.setEnabled(False)

            self.visor_admin.setCursor(Qt.CursorShape.CrossCursor)

            # --- ACTIVACIÓN DE LA BANDERA DE SEGURIDAD (Escalada Proactiva) ---
            target = self
            while target:
                if hasattr(target, "cambios_sin_guardar"):
                    target.cambios_sin_guardar = True
                target = (
                    target.parent()
                    if callable(getattr(target, "parent", None))
                    else getattr(target, "parentWidget", lambda: None)()
                )
                if not target:
                    break

            win = self.window()
            if win and win.statusBar():
                win.statusBar().setStyleSheet(
                    "color: #F85149; font-weight: 900; background: #161B22; font-family: 'Segoe UI';"
                )
                win.statusBar().showMessage(
                    tr("ubic.paint_status", default="MODO PINTADO: Traza las paredes y pulsa GUARDAR al terminar"), 0
                )

        else:
            # --- MODO DESACTIVADO (GATILLO DE GUARDADO Y OCULTACIÓN) ---
            # 1. OCULTACIÓN INMEDIATA DE LÍNEAS ROJAS (Safe Scene)
            escena = QGraphicsView.scene(self.visor_admin)

            if escena:
                # Obtenemos lista estática para evitar errores de mutación durante el borrado
                items_totales = escena.items()
                for itm in items_totales:
                    try:
                        if str(itm.data(0)) == "MURO_TECNICO":
                            itm.setVisible(False)
                    except (RuntimeError, AttributeError):
                        continue

            # 2. PROCESAR PERSISTENCIA
            self.muros_completados = True

            if hasattr(self, "guardar_configuracion_gps"):
                self.guardar_configuracion_gps()
            elif hasattr(self.visor_admin, "guardar_configuracion_gps"):
                self.visor_admin.guardar_configuracion_gps()

            # --- RESET DE LA BANDERA ---
            target = self
            while target:
                if hasattr(target, "cambios_sin_guardar"):
                    target.cambios_sin_guardar = False
                target = (
                    target.parent()
                    if callable(getattr(target, "parent", None))
                    else getattr(target, "parentWidget", lambda: None)()
                )
                if not target:
                    break

            # 3. RESTAURAR ASPECTO DEL BOTÓN
            self.btn_modo_pintar.setText(tr("ubic.paint_walls", default="PINTAR MUROS"))
            self.btn_modo_pintar.setFont(self._crear_fuente_segoe(9))
            self.btn_modo_pintar.setStyleSheet(
                self._estilo_boton_neon(
                    bg="#161B22",
                    fg="#F85149",
                    border="#F85149",
                    hover_bg="#F85149",
                    hover_fg="#0D1117",
                    radius=8,
                    padding="8px 12px",
                    font_size=11,
                )
            )

            self.visor_admin.setCursor(Qt.CursorShape.ArrowCursor)

            # Limpieza de trazos temporales
            self.visor_admin.punto_inicio_muro = None
            if getattr(self.visor_admin, "linea_temporal_muro", None):
                try:
                    if escena:
                        escena.removeItem(self.visor_admin.linea_temporal_muro)
                except:
                    pass
                self.visor_admin.linea_temporal_muro = None

            win = self.window()
            if win and win.statusBar():
                win.statusBar().setStyleSheet(
                    "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900;"
                )
                win.statusBar().showMessage(
                    "MUROS GUARDADOS: Sistema de navegación actualizado", 3000
                )

            if hasattr(self, "actualizar_estado_bloqueo"):
                self.actualizar_estado_bloqueo()

        # Refresco final seguro
        v_port = (
            self.visor_admin.viewport()
            if callable(self.visor_admin.viewport)
            else self.visor_admin.viewport
        )
        if v_port:
            v_port.update()

    # ============================================================
    # BLOQUE MENSAJES Y FEEDBACK VISUAL
    # ============================================================

    def mostrar_mensaje_temporal(self, mensaje, duracion=3000):
        """
        Muestra un mensaje en la barra de estado con estilo turquesa.
        """
        win = self.window()
        if win and win.statusBar():
            win.statusBar().setStyleSheet(
                "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900;"
            )
            win.statusBar().showMessage(mensaje, duracion)

    # ============================================================
    # BLOQUE NAVEGACIÓN Y CIERRE
    # ============================================================

    def volver_menu_principal(self):
        """Cierra la vista actual y regresa al menú de inicio."""
        try:
            # --- BLOQUEO DE SEGURIDAD FILTRADO (CAMBIOS SIN GUARDAR) ---
            # Solo disparamos la advertencia si el usuario sale desde GESTIÓN ESTRUCTURA (índice 4)
            indice_actual = self.stack.currentIndex()
            if indice_actual == 4:
                if hasattr(self, "advertir_cambios_pendientes"):
                    # Llamamos a advertir_cambios_pendientes. Si retorna False, abortamos la salida.
                    if not self.advertir_cambios_pendientes():
                        return  # El usuario canceló la salida
            # -----------------------------------------------------------

            if self.callback_vuelta:
                self.callback_vuelta()

            # Al llamar a self.close(), se disparará automáticamente el closeEvent.
            # Como ya advertimos arriba y la bandera se puso en False si aceptó,
            # el closeEvent dejará pasar el cierre limpiamente.
            self.close()
        except Exception as e:
            print(f"Error al volver: {e}")

    def closeEvent(self, event):
        """
        Versión blindada: Intercepta el cierre de la ventana para verificar
        cambios pendientes con el diálogo Dark Mode Neón.
        """
        # --- 1. DETECCIÓN MULTINIVEL DE CAMBIOS ---
        # Buscamos la bandera en el widget actual o en la ventana principal
        pendientes = getattr(self, "cambios_sin_guardar", False)
        if not pendientes and self.window():
            pendientes = getattr(self.window(), "cambios_sin_guardar", False)

        # --- 2. FLUJO DE DECISIÓN ---
        if pendientes:
            # Buscamos la función de advertencia (el diálogo neón que ya ajustamos)
            func_advertir = getattr(self, "advertir_cambios_pendientes", None)

            # Si no la encuentra aquí, la busca en el objeto GPS_Widget (si existe)
            if not func_advertir and hasattr(self, "gps_widget"):
                func_advertir = getattr(
                    self.gps_widget, "advertir_cambios_pendientes", None
                )

            if func_advertir:
                # Ejecutamos el diálogo. Si retorna True, el usuario terminó (guardó o ignoró)
                if func_advertir():
                    event.accept()
                else:
                    # El usuario pulsó CANCELAR en el diálogo neón
                    event.ignore()
            else:
                # Fallback de seguridad: si no encuentra la función neón,
                # al menos preguntamos de forma estándar para no perder datos.
                from PyQt6.QtWidgets import QMessageBox

                msg = QMessageBox.question(
                    self,
                    "Cambios sin guardar",
                    "Hay cambios pendientes. ¿Desea cerrar de todos modos?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if msg == QMessageBox.StandardButton.Yes:
                    event.accept()
                else:
                    event.ignore()
        else:
            # No hay cambios: Cierre limpio
            event.accept()

        # --- 3. LIMPIEZA POST-CIERRE (Opcional) ---
        # Si tienes hilos activos o conexiones, este es el lugar para cerrarlos

    def advertir_cambios_pendientes(self):
        """
        Lanza un diálogo estilo Dark Mode Neón si hay cambios sin guardar.
        Retorna True si la navegación puede continuar, False si se debe abortar.
        AJUSTE QUIRÚRGICO: Reseteo atómico de banderas para evitar doble mensaje.
        """
        # --- 1. COMPROBACIÓN DE ESTADO ---
        pendientes = getattr(self, "cambios_sin_guardar", False)
        if not pendientes and self.window():
            pendientes = getattr(self.window(), "cambios_sin_guardar", False)

        if not pendientes:
            return True

        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import (
            QDialog,
            QFrame,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QVBoxLayout,
        )

        diag = QDialog(self)
        diag.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        diag.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        container = QFrame()
        container.setStyleSheet(
            """
            QFrame {
                background-color: #0D1117;
                border: 2px solid #00FFC6;
                border-radius: 15px;
            }
        """
        )

        layout_maestro = QVBoxLayout(diag)
        layout_maestro.addWidget(container)

        layout_interno = QVBoxLayout(container)
        layout_interno.setContentsMargins(30, 25, 30, 25)
        layout_interno.setSpacing(15)

        fuente_segoe_bold = QFont("Segoe UI", 8, QFont.Weight.Bold)

        lbl_titulo = QLabel("ℹ️ " + tr("ubic.unsaved_title", default="ATENCIÓN: CAMBIOS SIN GUARDAR"))
        lbl_titulo.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_titulo.setStyleSheet(
            "color: #00FFC6; border: none; background: transparent;"
        )
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_interno.addWidget(lbl_titulo)

        lbl_msg = QLabel(
            tr("ubic.has_modificado_el_mapa_desea", default="Has modificado el mapa. ¿Deseas guardar los\ncambios antes de salir de esta sección?")
        )
        lbl_msg.setFont(fuente_segoe_bold)
        lbl_msg.setStyleSheet("color: #C9D1D9; border: none; background: transparent;")
        lbl_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_interno.addWidget(lbl_msg)

        layout_btns = QHBoxLayout()
        layout_btns.setSpacing(10)

        estilo_neutral = (
            "QPushButton { background-color: #21262D; color: #8B949E;"
            " border: 1px solid #30363D; padding: 10px 14px; border-radius: 10px;"
            " font-family: 'Segoe UI'; font-weight: 900; font-size: 13px; min-width: 115px; }"
            " QPushButton:hover { background-color: #FFFFFF; color: #0D1117; border: 1px solid #FFFFFF; }"
        )
        estilo_success = (
            "QPushButton { background-color: #1ED760; color: #0D1117;"
            " border: 2px solid #1ED760; padding: 10px 14px; border-radius: 10px;"
            " font-family: 'Segoe UI'; font-weight: 900; font-size: 13px; min-width: 115px; }"
            " QPushButton:hover { background-color: transparent; color: #1ED760; border: 2px solid #1ED760; }"
        )

        btn_no = QPushButton(tr("ubic.dont_save", default="NO GUARDAR"))
        btn_si = QPushButton(tr("ubic.do_save", default="SÍ, GUARDAR"))
        btn_cancelar = QPushButton(tr("ubic.cancel", default="CANCELAR"))

        btn_no.setStyleSheet(estilo_neutral)
        btn_si.setStyleSheet(estilo_success)
        btn_cancelar.setStyleSheet(estilo_neutral)

        for btn in [btn_no, btn_si, btn_cancelar]:
            btn.setFont(fuente_segoe_bold)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_si.clicked.connect(lambda: diag.done(1))
        btn_no.clicked.connect(lambda: diag.done(2))
        btn_cancelar.clicked.connect(lambda: diag.done(0))

        layout_btns.addWidget(btn_no)
        layout_btns.addWidget(btn_si)
        layout_btns.addWidget(btn_cancelar)
        layout_interno.addLayout(layout_btns)

        # --- 2. EJECUCIÓN Y REGISTRO DE RESPUESTA ---
        resultado = diag.exec()

        if resultado in [1, 2]:  # El usuario decidió SALIR (Guardando o no)
            # RESETEO PREVENTIVO: Apagamos las alarmas ANTES de cualquier otra acción
            self.cambios_sin_guardar = False
            if self.window():
                self.window().cambios_sin_guardar = False
            self._reiniciar_historial_planta()

            # Limpieza de historiales para evitar que un 'deshacer' fantasma reactive la bandera
            if hasattr(self, "visor_admin") and self.visor_admin:
                if hasattr(self.visor_admin, "historial_muros"):
                    self.visor_admin.historial_muros.clear()

            if resultado == 1:  # SÍ, GUARDAR
                if hasattr(self, "guardar_configuracion_gps"):
                    self.guardar_configuracion_gps()
                # Tras guardar, aseguramos que la bandera siga en False (re-confirmación)
                self.cambios_sin_guardar = False
                if self.window():
                    self.window().cambios_sin_guardar = False
            else:  # resultado == 2: SALIR SIN GUARDAR — descartar iconos pendientes
                self._iconos_pendientes = []

            return True

        else:  # CANCELAR (resultado 0)
            return False

    def ejecutar_busqueda(self):
        """
        Busca un artículo en la DB y despliega su información logística.
        Sincroniza el panel de resultados y prepara las coordenadas para el motor GPS.
        """
        termino = self.input_search.text().strip()
        if not termino:
            return
        self._opciones_destino_busqueda = []
        self._articulo_busqueda_actual = {}

        try:
            with obtener_conexion() as conn:
                cursor = conn.cursor()
                # Búsqueda optimizada por nombre (parcial) o código (exacto)
                # He añadido 'stock' a la consulta para alimentar la tercera tarjeta KPI
                sql = """
                    SELECT codigo, nombre, mapa_x, mapa_y, 
                           ubicacion_tienda, ubicacion_almacen, stock_total
                    FROM articulos 
                    WHERE nombre LIKE %s OR codigo = %s
                """
                cursor.execute(sql, (f"%{termino}%", termino))
                producto = cursor.fetchone()

            if producto:
                codigo, nombre, m_x, m_y, u_lin, u_alm, stock = producto
                self._articulo_busqueda_actual = {
                    "codigo": str(codigo).upper() if codigo else "",
                    "nombre": str(nombre).upper() if nombre else "",
                    "termino": termino.upper(),
                }
                opciones = self._obtener_opciones_destino_gps(str(codigo or termino))
                if not opciones and nombre:
                    opciones = self._obtener_opciones_destino_gps(str(nombre))
                self._opciones_destino_busqueda = opciones
                mejor_destino = self._seleccionar_mejor_destino_gps(opciones)
                lineal_opt = next(
                    (op for op in opciones if op.get("tipo") == "LINEAL"), None
                )
                almacen_opt = next(
                    (op for op in opciones if op.get("tipo") == "ALMACEN"), None
                )
                texto_lineal = (
                    lineal_opt.get("ubicacion")
                    if lineal_opt and lineal_opt.get("ubicacion")
                    else (u_lin if u_lin else tr("ubic.not_assigned", default="NO ASIGNADO"))
                )
                texto_almacen = (
                    almacen_opt.get("ubicacion")
                    if almacen_opt and almacen_opt.get("ubicacion")
                    else (u_alm if u_alm else tr("ubic.no_reserve", default="SIN RESERVA"))
                )

                # 1. ACTUALIZACIÓN DE IDENTIDAD VISUAL
                self.res_nombre.setText(nombre.upper())
                destinos_disponibles = len(
                    [
                        op
                        for op in opciones
                        if op.get("disponible") and op.get("coords") is not None
                    ]
                )
                sufijo_destinos = (
                    " · " + tr("ubic.gps_dest_suffix", default="{n} DESTINOS GPS", n=destinos_disponibles)
                    if destinos_disponibles
                    else " · " + tr("ubic.gps_no_dest", default="SIN DESTINO GPS")
                )
                self.res_codigo.setText(tr("ubic.sku_id", default="IDENTIFICADOR SKU: {codigo}", codigo=codigo) + sufijo_destinos)

                # 2. SINCRONIZACIÓN DE COORDENADAS GPS
                # Si el artículo tiene coordenadas, el motor de rutas A* podrá trazar el camino
                self.coordenadas_destino = (
                    mejor_destino["coords"] if mejor_destino else None
                )
                self.destino_gps_activo = mejor_destino if mejor_destino else None

                # 3. ACTUALIZACIÓN DE TARJETAS KPI (Telemetría de Producto)
                # Actualizamos las 3 tarjetas que definimos en la vista de búsqueda
                self.actualizar_tarjeta_kpi(self.card_lineal, texto_lineal)
                self.actualizar_tarjeta_kpi(self.card_almacen, texto_almacen)
                _uds = tr("ubic.unit_uds", default="UDS")
                self.actualizar_tarjeta_kpi(
                    self.card_stock, f"{stock} {_uds}" if stock is not None else f"0 {_uds}"
                )

                # Revelamos el panel con una transición visual (si se manejan animaciones)
                self.result_panel.setVisible(True)

                # 4. FEEDBACK EN BARRA DE ESTADO (HUD)
                if self.window().statusBar():
                    tipos_disponibles = {
                        op.get("tipo") for op in opciones if op.get("disponible")
                    }
                    detalle = (
                        " · " + tr("ubic.both_available", default="LINEAL Y ALMACÉN DISPONIBLES")
                        if {"LINEAL", "ALMACEN"}.issubset(tipos_disponibles)
                        else (
                            " · " + tr("ubic.gps_dest_available", default="DESTINO GPS DISPONIBLE")
                            if tipos_disponibles
                            else " · " + tr("ubic.no_map_coords", default="SIN COORDENADAS DE MAPA")
                        )
                    )
                    self.window().statusBar().setStyleSheet(
                        "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900;"
                    )
                    self.window().statusBar().showMessage(
                        "🎯 " + tr("ubic.product_located", default="PRODUCTO LOCALIZADO: {nombre}", nombre=nombre.upper()), 5000
                    )

            else:
                # Caso: No se encuentra el artículo
                self._opciones_destino_busqueda = []
                self._articulo_busqueda_actual = {}
                self.coordenadas_destino = None
                self.destino_gps_activo = None
                self.result_panel.setVisible(False)
                self.window().statusBar().setStyleSheet(
                    "color: #F85149; font-family: 'Segoe UI'; font-weight: 900;"
                )
                self.window().statusBar().showMessage(
                    "⚠️ " + tr("ubic.track_fail", default="FALLO DE RASTREO: '{termino}' NO EXISTE", termino=termino), 4000
                )

                # Feedback sonoro o visual más agresivo opcional:
                # QMessageBox.information(self, "SISTEMA", "Búsqueda sin resultados.")

        except Exception as e:
            print(f"CRITICAL ERROR (Search Engine): {e}")
            if self.window().statusBar():
                self.window().statusBar().showMessage(
                    "❌ ERROR DE CONEXIÓN CON LA MATRIZ DE DATOS", 5000
                )

    def _tipo_label(self, tipo_texto):
        """Etiqueta visible (traducida) para el valor lógico de tipo de ubicación."""
        if str(tipo_texto).upper() == "LINEAL":
            return tr("ubic.tipo_lineal", default="LINEAL")
        return tr("ubic.tipo_almacen", default="ALMACÉN")

    def crear_vista_asignacion(self, tipo_texto):
        """
        Interfaz de asignación con flujo jerárquico.
        El diseño se mantiene fiel a la estructura de habilitación por pasos.
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QVBoxLayout,
            QWidget,
        )

        vista = QWidget()
        layout = QVBoxLayout(vista)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(25)

        # --- HEADER DE SECCIÓN ---
        header = QLabel(tr("ubic.assign_header", default="SISTEMA DE UBICACIÓN > {tipo}", tipo=self._tipo_label(tipo_texto)))
        header.setStyleSheet(
            """
            color: #00FFC6; 
            font-family: 'Segoe UI';
            font-size: 24px; 
            font-weight: 900; 
            letter-spacing: 1.5px;
        """
        )
        layout.addWidget(header)

        # --- PANEL 1: IDENTIFICACIÓN (ENTRADA DE DATOS) ---
        self.panel_search = QFrame()
        self.panel_search.setObjectName("panel_oscuro")
        self.panel_search.setStyleSheet(
            """
            QFrame#panel_oscuro { 
                background-color: #161B22; 
                border: 1px solid #30363D; 
                border-radius: 12px; 
            }
        """
        )
        self.panel_search.setFixedHeight(100)

        search_lyt = QHBoxLayout(self.panel_search)
        search_lyt.setContentsMargins(20, 0, 20, 0)
        search_lyt.setSpacing(15)

        self.input_scan = QLineEdit()
        self.input_scan.setPlaceholderText(
            tr("ubic.assign_search_ph",
               default="INGRESE EL CÓDIGO O NOMBRE DE UN ARTÍCULO PARA ASIGNARLO AL {tipo}",
               tipo=self._tipo_label(tipo_texto))
        )
        self.input_scan.setStyleSheet(
            """
            QLineEdit { 
                border: 1px solid #30363D; 
                background-color: #0D1117; 
                border-radius: 8px; 
                padding-left: 15px; 
                font-family: 'Segoe UI';
                font-size: 14px; 
                font-weight: 900;
                color: white; 
            }
            QLineEdit:focus { border: 1px solid #00FFC6; }
            QLineEdit:disabled { color: #8B949E; background-color: #161B22; border: 1px solid #238636; }
        """
        )
        self.input_scan.setFixedHeight(50)

        # Botón de Cámara (Visión Artificial)
        btn_cam = QPushButton("📷")  # Restaurado icono visual
        btn_cam.setFixedSize(60, 50)
        btn_cam.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cam.setStyleSheet(
            """
            QPushButton { 
                background-color: #30363D; 
                color: white; 
                font-family: 'Segoe UI';
                font-weight: 900;
                font-size: 20px; 
                border-radius: 10px; 
                border: 1px solid #30363D;
            }
            QPushButton:hover { background-color: #FFFFFF; color: #0D1117; border: 1px solid #FFFFFF; }
        """
        )
        btn_cam.clicked.connect(
            lambda: self.abrir_escaner_camara(
                tr("ubic.cam_vision_title", default="VISIÓN - {tipo}", tipo=self._tipo_label(tipo_texto)),
                modo="BUSQUEDA")
        )

        self.btn_validar = QPushButton(tr("ubic.btn_search", default="BUSCAR"))
        self.btn_validar.setFixedSize(130, 50)
        self.btn_validar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_validar.setStyleSheet(
            """
            QPushButton {
                background-color: #0D1117;
                color: #00FFC6;
                border: 2px solid #00FFC6;
                font-family: 'Segoe UI';
                font-weight: 900;
                border-radius: 10px;
            }
            QPushButton:hover { background-color: #00FFC6; color: #0D1117; border: 2px solid #00FFC6; }
            QPushButton:disabled { background-color: #21262d; color: #484F58; border: 1px solid #484F58; }
        """
        )
        self.btn_validar.clicked.connect(lambda: self.validar_articulo(tipo_texto))

        search_lyt.addWidget(self.input_scan)
        search_lyt.addWidget(btn_cam)
        search_lyt.addWidget(self.btn_validar)
        layout.addWidget(self.panel_search)

        self.info_art = QLabel("ℹ️ " + tr("ubic.waiting_id", default="ESPERANDO IDENTIFICACIÓN DE ARTÍCULO..."))
        self.info_art.setStyleSheet(
            """
            color: #8B949E; 
            font-family: 'Segoe UI';
            font-size: 11px; 
            font-weight: 900; 
            padding-left: 5px;
        """
        )
        layout.addWidget(self.info_art)

        # --- PANEL 2: FORMULARIO DE UBICACIÓN (FLUJO EN CASCADA) ---
        self.container_ubicacion = QFrame()
        self.container_ubicacion.setEnabled(False)  # Bloqueado hasta validar artículo
        self.container_ubicacion.setObjectName("panel_oscuro_central")
        self.container_ubicacion.setStyleSheet(
            """
            QFrame#panel_oscuro_central { 
                background-color: #161B22; 
                border: 1px solid #30363D; 
                border-radius: 12px; 
            }
        """
        )

        ubi_layout = QVBoxLayout(self.container_ubicacion)
        ubi_layout.setContentsMargins(35, 35, 35, 35)
        ubi_layout.setSpacing(20)

        style_step = """
            QLineEdit { 
                background-color: #0D1117; 
                border: 1px solid #30363D; 
                border-radius: 10px; 
                color: white; 
                padding: 15px; 
                font-family: 'Segoe UI';
                font-size: 13px; 
                font-weight: 900;
            }
            QLineEdit:focus { border: 1px solid #00FFC6; background-color: #161B22; }
            QLineEdit:disabled { background-color: #0a0e12; color: #30363D; border: 1px solid #21262d; }
        """

        self.input_pasillo = QLineEdit()
        self.input_pasillo.setPlaceholderText(tr("ubic.step2_ph", default="PASO 2: DEFINIR PASILLO (EJ: P01)"))
        self.input_pasillo.setStyleSheet(style_step)

        self.input_estanteria = QLineEdit()
        self.input_estanteria.setPlaceholderText(tr("ubic.step3_ph", default="PASO 3: DEFINIR ESTANTERÍA (EJ: E05)"))
        self.input_estanteria.setStyleSheet(style_step)
        self.input_estanteria.setEnabled(False)

        self.input_nivel = QLineEdit()
        self.input_nivel.setPlaceholderText(tr("ubic.step4_ph", default="PASO 4: DEFINIR NIVEL / ALTURA (EJ: N1)"))
        self.input_nivel.setStyleSheet(style_step)
        self.input_nivel.setEnabled(False)

        ubi_layout.addWidget(self.input_pasillo)
        ubi_layout.addWidget(self.input_estanteria)
        ubi_layout.addWidget(self.input_nivel)
        layout.addWidget(self.container_ubicacion)

        # --- SECCIÓN 3: CONFIRMACIÓN FINAL ---
        self.btn_guardar_final = QPushButton(tr("ubic.btn_confirm_matrix", default="CONFIRMAR Y REGISTRAR EN MATRIZ"))
        self.btn_guardar_final.setFixedHeight(65)
        self.btn_guardar_final.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_guardar_final.setEnabled(False)
        self.btn_guardar_final.setStyleSheet(
            """
            QPushButton { 
                background-color: #1C2128; 
                border: 2px solid #30363D; 
                color: #484F58; 
                font-family: 'Segoe UI';
                font-size: 15px; 
                font-weight: 900; 
                border-radius: 12px; 
            }
            QPushButton:enabled { 
                border: 2px solid #00FFC6; 
                color: #00FFC6; 
                background-color: rgba(0, 255, 198, 0.05); 
            }
            QPushButton:hover:enabled { 
                background-color: #00FFC6; 
                color: #0D1117; 
            }
        """
        )

        self.btn_guardar_final.clicked.connect(
            lambda: self.finalizar_ubicacion(tipo_texto)
        )
        layout.addWidget(self.btn_guardar_final)

        # --- LÓGICA DE ENCADENAMIENTO REACTIVO ---
        self.input_pasillo.textChanged.connect(
            lambda t: self.input_estanteria.setEnabled(len(t.strip()) > 0)
        )
        self.input_estanteria.textChanged.connect(
            lambda t: self.input_nivel.setEnabled(len(t.strip()) > 0)
        )
        self.input_nivel.textChanged.connect(
            lambda t: self.btn_guardar_final.setEnabled(len(t.strip()) > 0)
        )

        layout.addStretch()
        return vista

    def validar_articulo(self, contexto="LINEAL"):
        """
        Busca el artículo en DB y desbloquea el flujo de entrada de datos.
        Aplica feedback visual inmediato (Verde = Éxito / Rojo = Error).
        """

        busqueda = self.input_scan.text().strip()
        if not busqueda:
            return

        try:
            with obtener_conexion() as conn:
                cursor = conn.cursor()
                # Búsqueda por código exacto primero; si no, por nombre parcial
                cursor.execute(
                    "SELECT codigo, nombre FROM articulos WHERE codigo = %s",
                    (busqueda,),
                )
                res = cursor.fetchone()
                if not res:
                    cursor.execute(
                        "SELECT codigo, nombre FROM articulos WHERE nombre LIKE %s LIMIT 1",
                        (f"%{busqueda}%",),
                    )
                    res = cursor.fetchone()

                if res:
                    # --- ESTADO: ARTÍCULO ENCONTRADO ---
                    self.articulo_seleccionado = res[0]
                    self.input_scan.setEnabled(False)
                    self.btn_validar.setEnabled(False)

                    # Feedback Visual: Panel en verde éxito
                    self.panel_search.setStyleSheet(
                        """
                        QFrame#panel_oscuro { 
                            background-color: #0D1117; 
                            border: 2px solid #238636; 
                            border-radius: 12px; 
                        }
                    """
                    )

                    self.info_art.setText("✅ " + tr("ubic.identified", default="IDENTIFICADO: {nombre}", nombre=res[1].upper()))
                    self.info_art.setStyleSheet(
                        """
                        color: #00FFC6; 
                        font-family: 'Segoe UI';
                        font-weight: 900; 
                        font-size: 11px;
                        letter-spacing: 1px;
                    """
                    )

                    # Desbloqueo del formulario jerárquico
                    self.container_ubicacion.setEnabled(True)
                    self.input_pasillo.setFocus()

                else:
                    # --- ESTADO: ERROR DE IDENTIFICACIÓN ---
                    self.info_art.setText("❌ " + tr("ubic.not_found_master", default="ERROR: ARTÍCULO NO ENCONTRADO EN MAESTRO"))
                    self.info_art.setStyleSheet(
                        """
                        color: #F85149; 
                        font-family: 'Segoe UI';
                        font-weight: 900; 
                        font-size: 11px;
                    """
                    )
                    self.input_scan.selectAll()
                    self.input_scan.setFocus()

        except Exception as e:
            print(f"Error crítico en validación: {e}")

    def reportar_discrepancia_actual(self):
        """
        Registra una incidencia de stock para auditoría.
        Útil cuando el operario detecta que el GPS marca una ubicación vacía o errónea.
        """
        from PyQt6.QtCore import QTimer

        if not getattr(self, "articulo_seleccionado", None):
            return

        try:
            with obtener_conexion() as conn:
                cursor = conn.cursor()
                # Marcamos flag de incidencia y estampamos el timestamp actual
                sql = """
                    UPDATE articulos 
                    SET incidencia_ubicacion = 1, 
                        ultima_incidencia = NOW() 
                    WHERE codigo = %s
                """
                cursor.execute(sql, (self.articulo_seleccionado,))
                conn.commit()

            # Feedback Visual: Alerta Naranja (Precaución)
            self.info_art.setText("⚠️ " + tr("ubic.discrepancy_reported", default="DISCREPANCIA REPORTADA A LOGÍSTICA"))
            self.info_art.setStyleSheet(
                """
                color: #FFA500; 
                font-family: 'Segoe UI';
                font-weight: 900; 
                font-size: 11px;
                letter-spacing: 0.5px;
            """
            )

            if self.window().statusBar():
                self.window().statusBar().showMessage(
                    f"ALERTA: INCIDENCIA REGISTRADA EN SKU {self.articulo_seleccionado}",
                    5000,
                )

            # Limpieza automática tras 2.5 segundos para no interrumpir el flujo
            QTimer.singleShot(2500, self.limpiar_interfaz_registro)

        except Exception as e:
            print(f"Error al reportar discrepancia: {e}")

    # --- 1. CAPTURADOR INTELIGENTE (HID SCANNER) ---

    # --- 2. ACTUALIZACIÓN DE KPI POR IDENTIFICADOR ---
    # --- 1. COMPONENTES DE TELEMETRÍA (KPIs) ---

    # ============================================================
    # BLOQUE COMPONENTES KPI Y TELEMETRÍA
    # ============================================================

    def crear_tarjeta_info(self, titulo, valor, color_neon="#00FFC6"):
        """
        Genera un componente KPI con diseño industrial, hover reactivo y
        capacidad de actualización dinámica mediante ID de objeto.
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

        card = QFrame()
        card.setObjectName("tarjeta_kpi")
        card.setCursor(Qt.CursorShape.PointingHandCursor)

        # Estilo HUD: Fondo oscuro, bordes técnicos y brillo neon al pasar el mouse
        card.setStyleSheet(
            f"""
            QFrame#tarjeta_kpi {{
                background-color: #161B22;
                border: 1px solid #30363D;
                border-radius: 12px;
            }}
            QFrame#tarjeta_kpi:hover {{
                border-color: {color_neon};
                background-color: #1C2128;
            }}
        """
        )

        lyt = QVBoxLayout(card)
        lyt.setContentsMargins(20, 20, 20, 20)
        lyt.setSpacing(8)

        # Etiqueta de Título (Metadato de sistema)
        lbl_tit = QLabel(titulo.upper())
        lbl_tit.setStyleSheet(
            """
            color: #8B949E; 
            font-family: 'Segoe UI';
            font-size: 10px; 
            font-weight: 900; 
            letter-spacing: 1.5px; 
            border: none; 
            background: transparent;
        """
        )

        # Etiqueta de Valor (Dato dinámico de telemetría)
        lbl_val = QLabel(str(valor))
        lbl_val.setObjectName("lbl_value")  # ID clave para actualización O(1)
        lbl_val.setStyleSheet(
            f"""
            color: {color_neon}; 
            font-family: 'Segoe UI';
            font-size: 26px; 
            font-weight: 900; 
            border: none; 
            background: transparent;
        """
        )
        lbl_val.setWordWrap(True)

        lyt.addWidget(lbl_tit)
        lyt.addWidget(lbl_val)
        lyt.addStretch()

        return card

    def actualizar_tarjeta_kpi(self, widget_tarjeta, nuevo_valor):
        """
        Busca el label de valor dentro de una tarjeta mediante su ID de objeto
        y actualiza su contenido de forma segura sin redibujar toda la UI.
        """
        from PyQt6.QtWidgets import QLabel

        # Búsqueda directa por ID de objeto (máxima eficiencia en Qt)
        target = widget_tarjeta.findChild(QLabel, "lbl_value")

        if target:
            target.setText(str(nuevo_valor))
        else:
            # Fallback: Si el ID se pierde, buscamos por jerarquía visual (fuente grande)
            for lbl in widget_tarjeta.findChildren(QLabel):
                if lbl.font().pointSize() >= 18:
                    lbl.setText(str(nuevo_valor))
                    break

    # --- 2. PERSISTENCIA Y CALIBRACIÓN ---

    def mostrar_feedback_calibracion(self, ratio):
        """
        Muestra un cuadro de diálogo de éxito con el lenguaje visual Dark.
        Informa sobre el factor de precisión calculado para el motor de rutas A*.
        """
        from PyQt6.QtWidgets import QMessageBox

        msg = QMessageBox(self)
        msg.setWindowTitle(tr("ubic.calib_title", default="SISTEMA CALIBRADO"))

        # Formateo del mensaje con el color corporativo turquesa
        msg.setText(
            "<b style='color: #00FFC6; font-family: 'Segoe UI'; font-size: 15px;'>"
            + tr("ubic.calib_success", default="CALIBRACIÓN EXITOSA")
            + "</b>"
        )

        msg.setInformativeText(
            "<p style='color: #C9D1D9; font-family: 'Segoe UI'; font-size: 12px; font-weight: 900;'>"
            + tr("ubic.calib_info",
                 default="Factor de conversión establecido: <b style=\"color: white;\">{ratio} px/m</b>.<br><br>El sistema de navegación A* ha recalculado las dimensiones reales para la optimización de rutas.",
                 ratio=f"{ratio:.2f}")
            + "</p>"
        )

        msg.setIcon(QMessageBox.Icon.Information)
        msg.setStyleSheet(
            """
            QMessageBox { 
                background-color: #0D1117; 
                border: 1px solid #30363D; 
            }
            QLabel { color: #8B949E; }
            QPushButton { 
                background-color: #1C2128; 
                color: #00FFC6; 
                font-family: 'Segoe UI';
                border: 1px solid #00FFC6; 
                border-radius: 6px; 
                padding: 10px; 
                min-width: 120px; 
                font-weight: 900;
                font-size: 11px;
            }
            QPushButton:hover { 
                background-color: #FFFFFF; 
                color: #0D1117; 
                border: 1px solid #FFFFFF;
            }
        """
        )
        msg.exec()

    # ============================================================
    # BLOQUE PERSISTENCIA DE CONFIGURACIÓN GPS
    # ============================================================

    def guardar_configuracion_gps(self):
        """
        Vuelca el estado del visor admin a la Base de Datos con persistencia robusta.
        CORRECCIÓN: Reactivación forzosa del motor de navegación post-guardado.
        """
        import json
        import os
        import pickle

        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication, QGraphicsView

        from src.db.conexion import obtener_conexion

        if not getattr(self, "visor_admin", None):
            return

        # 1. BLOQUEO SEGURO DE INTERFAZ
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.visor_admin.blockSignals(True)

        try:
            planta_idx = getattr(self, "planta_actual", 0)

            # 2. PROCESAMIENTO DE MATRIZ (Ghost Red)
            matriz_raw = getattr(self.visor_admin, "matriz_obstaculos", None)
            muros_blob = (
                zlib.compress(pickle.dumps(matriz_raw))
                if matriz_raw is not None
                else None
            )

            # 3. EXTRACCIÓN DE ELEMENTOS (Muros e Infraestructura)
            escena = QGraphicsView.scene(self.visor_admin)
            if not escena:
                raise ValueError("No se detectó la escena activa.")

            lista_muros = []
            lista_infra = []
            # Use punto_ancla (set by dibujar_marca_origen) as authoritative source.
            # Do NOT use item.scenePos() for PIN_ORIGEN — addEllipse items have scenePos()=(0,0)
            # because they encode position in the rect geometry, not in item.pos().
            _pa = getattr(self.visor_admin, "punto_ancla", None)
            if _pa is not None:
                ancla_x, ancla_y = _pa.x(), _pa.y()
            else:
                ancla_x = getattr(self.visor_admin, "coord_ancla_x", 0.0)
                ancla_y = getattr(self.visor_admin, "coord_ancla_y", 0.0)

            for item in escena.items():
                tag = str(item.data(0)) if item.data(0) is not None else ""
                tipo_meta = str(item.data(1)) if item.data(1) is not None else ""

                if tag == "PIN_ORIGEN":
                    continue  # Anchor already captured from punto_ancla attribute above

                if tag == "MURO_TECNICO" and hasattr(item, "line"):
                    linea = item.line()
                    lista_muros.append(
                        {
                            "x1": linea.x1(),
                            "y1": linea.y1(),
                            "x2": linea.x2(),
                            "y2": linea.y2(),
                        }
                    )
                elif (
                    tag.startswith("SAT_")
                    or tag.startswith("CHINCHETA_")
                    or tipo_meta != ""
                ):
                    # Filtro quirúrgico para no guardar al OPERARIO o elementos temporales
                    if tag == "OPERARIO_SISTEMA":
                        continue

                    pos = item.scenePos()
                    lista_infra.append(
                        {
                            "tipo": tipo_meta if tipo_meta else "ICONO",
                            "x": pos.x(),
                            "y": pos.y(),
                            "nombre": str(item.data(2)) if item.data(2) else "PUNTO",
                            "epc": tag,
                        }
                    )

            calibracion_data = self._snapshot_calibracion_actual()
            muros_json = json.dumps(
                {
                    "muros_vectores": lista_muros,
                    "calibracion": calibracion_data,
                    "ancla": (
                        {"x": ancla_x, "y": ancla_y}
                        if ancla_x is not None and ancla_y is not None
                        else None
                    ),
                }
            )
            infra_json = json.dumps(lista_infra)
            escala = getattr(self.visor_admin, "ratio_px_m_h", 1.0)

            # 4. PROTECCIÓN DE RUTA DE IMAGEN
            ruta_cruda = (
                getattr(self, "ruta_actual", "")
                or getattr(self.visor_admin, "ruta_actual", "")
                or getattr(self, "ultimo_plano_cargado", "")
            )

            ruta_plano_memoria = os.path.basename(ruta_cruda) if ruta_cruda else ""

            # 5. TRANSACCIÓN MARIADB
            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT ruta_imagen FROM configuracion_mapa WHERE planta_index = %s",
                        (planta_idx,),
                    )
                    registro = cursor.fetchone()

                    if not ruta_plano_memoria and registro and registro[0]:
                        ruta_plano_memoria = registro[0]

                    if registro:
                        sql_upd = """
                            UPDATE configuracion_mapa SET 
                                ruta_imagen=%s, matriz_binaria=%s, escala_px_metro=%s, 
                                muros_vectoriales=%s, puntos_infraestructura=%s, 
                                ancla_x=%s, ancla_y=%s, fecha_actualizacion=NOW()
                            WHERE planta_index=%s
                        """
                        cursor.execute(
                            sql_upd,
                            (
                                ruta_plano_memoria,
                                muros_blob,
                                escala,
                                muros_json,
                                infra_json,
                                ancla_x,
                                ancla_y,
                                planta_idx,
                            ),
                        )
                    else:
                        sql_ins = """
                            INSERT INTO configuracion_mapa 
                            (planta_index, ruta_imagen, matriz_binaria, escala_px_metro, 
                             muros_vectoriales, puntos_infraestructura, ancla_x, ancla_y, fecha_actualizacion)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        """
                        cursor.execute(
                            sql_ins,
                            (
                                planta_idx,
                                ruta_plano_memoria,
                                muros_blob,
                                escala,
                                muros_json,
                                infra_json,
                                ancla_x,
                                ancla_y,
                            ),
                        )

                conn.commit()

            # 5b. FLUSH DE ICONOS PENDIENTES → ubicaciones
            iconos_pendientes = getattr(self, "_iconos_pendientes", [])
            if iconos_pendientes:
                with obtener_conexion() as conn_ubi:
                    with conn_ubi.cursor() as cur_ubi:
                        for icono in iconos_pendientes:
                            cur_ubi.execute(
                                """
                                INSERT INTO ubicaciones
                                    (epc, pasillo, estanteria, mapa_x, mapa_y, real_x, real_y,
                                     verificado, fecha_actualizacion)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, 1, NOW())
                                ON DUPLICATE KEY UPDATE
                                    mapa_x = VALUES(mapa_x),
                                    mapa_y = VALUES(mapa_y),
                                    real_x = VALUES(real_x),
                                    real_y = VALUES(real_y),
                                    estanteria = VALUES(estanteria),
                                    fecha_actualizacion = NOW()
                                """,
                                (
                                    icono["epc"], icono["pasillo"], icono["estanteria"],
                                    icono["mapa_x"], icono["mapa_y"],
                                    icono["real_x"], icono["real_y"],
                                ),
                            )
                    conn_ubi.commit()
                self._iconos_pendientes = []

            # 6. SINCRONIZACIÓN Y REBLOQUEO DE SEGURIDAD
            self.cambios_sin_guardar = False

            # --- INYECCIÓN DE REACTIVIDAD (Soluciona el congelamiento) ---
            self.visor_admin.setInteractive(True)
            if hasattr(self.visor_admin, "setDragMode"):
                self.visor_admin.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

            # Forzar actualización de las "líneas invisibles" (Foreground)
            self.visor_admin.viewport().update()

            self._actualizar_botones_historial()

            # 7. FEEDBACK PREMIUM
            QApplication.restoreOverrideCursor()

            self._dialogo_neon_info(
                "✅  MUROS PINTADOS",
                "Los muros pintados se han guardado correctamente<br>como obstáculos para el GPS.",
                color="#00FFC6",
                ancho=460,
                alto=195,
            )

        except Exception as e:
            print(f"❌ Error crítico en guardado: {e}")
            QApplication.restoreOverrideCursor()
        finally:
            # Restauración absoluta del cursor y señales
            self.visor_admin.blockSignals(False)
            while QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()

            # Último intento de repintado para asegurar que las líneas aparezcan
            self.visor_admin.viewport().update()

        print(f"🛰️ Sincronización de Planta {planta_idx} finalizada.")

    # ============================================================
    # BLOQUE EDITOR DE MAPA
    # ============================================================

    def guardar_escala_db(self, ratio_x, ratio_y):
        """
        Guarda la escala y el Origen (0,0) en la BD y sincroniza ambos visores.
        CORRECCIÓN: Asegura la reactivación del ratón y el repintado del Foreground.
        """
        import os

        from PyQt6.QtCore import QPointF
        from PyQt6.QtWidgets import QApplication

        from src.db.conexion import obtener_conexion

        if not self.visor_admin:
            return

        # 1. BLOQUEO DE SEÑALES
        self.visor_admin.blockSignals(True)

        try:
            # 2. RECUPERACIÓN DE ANCLA (Origen 0,0)
            ancla_visual = getattr(self.visor_admin, "punto_ancla", None)
            if ancla_visual:
                ancla_x, ancla_y = ancla_visual.x(), ancla_visual.y()
            else:
                ancla_x = getattr(self.visor_admin, "coord_ancla_x", 0.0)
                ancla_y = getattr(self.visor_admin, "coord_ancla_y", 0.0)

            # 3. GESTIÓN DE RUTA Y PLANTA
            ruta_cruda = getattr(self, "ruta_actual", "") or getattr(
                self.visor_admin, "ruta_actual", ""
            )

            if ruta_cruda:
                # Normalización de ruta para DB
                if "documentos/planos" in ruta_cruda.replace("\\", "/").lower():
                    ruta_mapa = os.path.basename(ruta_cruda)
                else:
                    ruta_mapa = os.path.normpath(ruta_cruda).replace("\\", "/")
            else:
                ruta_mapa = ""

            planta_idx = getattr(self, "planta_actual", 0)

            # 4. PERSISTENCIA EN BASE DE DATOS
            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT id FROM configuracion_mapa WHERE planta_index = %s",
                        (planta_idx,),
                    )
                    existe = cursor.fetchone()

                    if existe:
                        query = """
                            UPDATE configuracion_mapa 
                            SET escala_px_metro = %s, ancla_x = %s, ancla_y = %s, ruta_imagen = %s, fecha_actualizacion = NOW()
                            WHERE planta_index = %s
                        """
                        cursor.execute(
                            query, (ratio_x, ancla_x, ancla_y, ruta_mapa, planta_idx)
                        )
                    else:
                        query = """
                            INSERT INTO configuracion_mapa 
                            (planta_index, escala_px_metro, ancla_x, ancla_y, ruta_imagen, fecha_actualizacion)
                            VALUES (%s, %s, %s, %s, %s, NOW())
                        """
                        cursor.execute(
                            query, (planta_idx, ratio_x, ancla_x, ancla_y, ruta_mapa)
                        )

                    conn.commit()

            # 5. SINCRONIZACIÓN EN CALIENTE
            for v in [self.visor_admin, getattr(self, "visor_mapa", None)]:
                if v:
                    v.ratio_px_m_h = float(ratio_x)
                    v.ratio_px_m_v = float(ratio_x)
                    v.coord_ancla_x = float(ancla_x)
                    v.coord_ancla_y = float(ancla_y)
                    v.punto_ancla = QPointF(float(ancla_x), float(ancla_y))

                    # --- RE-ACTIVACIÓN DE NAVEGACIÓN ---
                    v.setInteractive(True)
                    if hasattr(v, "setDragMode"):
                        from PyQt6.QtWidgets import QGraphicsView

                        v.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

            # 6. RESET DE MODOS (Evita que las líneas se queden pegadas)
            self.visor_admin.modo_calibrar = False
            self.visor_admin.esperando_ancla_0 = False
            snapshot_actual = self._obtener_snapshot_mapa()
            if hasattr(self, "limpiar_indicadores_calib"):
                self.limpiar_indicadores_calib()
                self.reconstruir_estado_mapa_actual(snapshot_actual, recuadrar=False)

            # 7. FEEDBACK UI
            win = self.window()
            if win and win.statusBar():
                win.statusBar().setStyleSheet(
                    "color: #00F5FF; font-family: 'Segoe UI'; font-weight: 900; background-color: #0A0A0A; border-top: 1px solid #00F5FF;"
                )
                win.statusBar().showMessage(
                    f"✅ ESCALA PLANTA {planta_idx} SINCRONIZADA: {ratio_x:.2f} px/m",
                    5000,
                )

        except Exception as e:
            print(f"❌ FALLO EN PERSISTENCIA DE ESCALA: {e}")
        finally:
            self.visor_admin.blockSignals(False)
            QApplication.processEvents()

            # Refresco final para asegurar que el Foreground se limpie
            if self.visor_admin.viewport():
                self.visor_admin.viewport().update()

        print(f"🛰️ Escala y Origen de Planta {planta_idx} actualizados correctamente.")

    def abrir_editor_mapa(self):
        """
        Transición al Modo Arquitecto: Sincroniza la navegación lateral
        y recalcula el encuadre del lienzo.
        """
        from PyQt6.QtCore import Qt, QTimer
        from PyQt6.QtWidgets import QMessageBox

        try:
            # 1. CAMBIO DE PANEL (Index 4: Editor de Infraestructura)
            if hasattr(self, "stack"):
                self.stack.setCurrentIndex(4)

            # 2. AJUSTE DE CÁMARA (Delay quirúrgico para permitir el render del Stack)
            if hasattr(self, "visor_admin") and self.visor_admin.scene():
                QTimer.singleShot(
                    100,
                    lambda: self.visor_admin.fitInView(
                        self.visor_admin.scene().itemsBoundingRect(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                    ),
                )

            # 3. SINCRONIZACIÓN DE SIDEBAR (Feedback visual de botón activo)
            if hasattr(self, "menu_botones"):
                for btn in self.menu_botones:
                    btn.setChecked(False)

                if hasattr(self, "btn_nav_admin") and self.btn_nav_admin:
                    self.btn_nav_admin.setChecked(True)

            # 4. NOTIFICACIÓN DE SEGURIDAD EN STATUS BAR
            win = self.window()
            if win and win.statusBar():
                win.statusBar().setStyleSheet("color: #FFB86C; font-weight: 900;")
                win.statusBar().showMessage(
                    "⚠️ MODO EDITOR: ACCESO A INFRAESTRUCTURA NIVEL 1", 4000
                )

        except Exception as e:
            print(f"❌ FALLO EN TRANSICIÓN DE UI: {e}")
            QMessageBox.critical(
                self, "Error de Interfaz", f"No se pudo abrir el editor: {e}"
            )

    # ============================================================
    # BLOQUE VISTA DE BÚSQUEDA
    # ============================================================

    def crear_vista_busqueda(self):
        """
        Consulta de producto con diseño HUD premium y barra de búsqueda
        tipo cápsula optimizada para escaneo rápido.
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QVBoxLayout,
            QWidget,
        )

        vista = QWidget()
        layout = QVBoxLayout(vista)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(25)

        # 1. ENCABEZADO TÉCNICO
        header_lyt = QHBoxLayout()
        self.lbl_titulo_busqueda = QLabel(tr("ubic.search_title", default="INTELIGENCIA DE PRODUCTO"))
        self.lbl_titulo_busqueda.setStyleSheet(
            """
            color: #00FFC6; 
            font-family: 'Segoe UI';
            font-size: 24px; 
            font-weight: 900; 
            letter-spacing: 2px;
        """
        )
        header_lyt.addWidget(self.lbl_titulo_busqueda)
        header_lyt.addStretch()
        layout.addLayout(header_lyt)

        # 2. BARRA DE BÚSQUEDA + BOTONES (Fila horizontal)
        search_row = QHBoxLayout()
        search_row.setSpacing(10)

        # Cápsula de búsqueda (solo icono + input)
        search_box = QFrame()
        search_box.setObjectName("search_capsule")
        search_box.setFixedHeight(52)
        search_box.setStyleSheet(
            """
            QFrame#search_capsule {
                background-color: #0D1117;
                border: 2px solid #00FFC6;
                border-radius: 15px;
            }
            QFrame#search_capsule:focus-within {
                border: 2px solid #00FFC6;
                background-color: #161B22;
            }
        """
        )

        search_layout = QHBoxLayout(search_box)
        search_layout.setContentsMargins(20, 6, 15, 6)
        search_layout.setSpacing(10)

        # Icono de búsqueda visual
        lbl_icon = QLabel("🔍")
        lbl_icon.setStyleSheet(
            "font-size: 18px; border: none; background: transparent;"
        )

        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText(
            tr("ubic.search_ph2", default="Escanee código o introduzca referencia...")
        )
        self.input_search.setStyleSheet(
            """
            QLineEdit {
                border: none;
                background: transparent;
                font-family: 'Segoe UI';
                font-size: 16px;
                color: white;
                font-weight: 900;
            }
        """
        )
        self.input_search.returnPressed.connect(self.ejecutar_busqueda)

        search_layout.addWidget(lbl_icon)
        search_layout.addWidget(self.input_search)

        # Botón Cámara — fuera de la cápsula, estilo app estándar
        btn_cam = QPushButton("📷")
        btn_cam.setFixedSize(70, 52)
        btn_cam.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cam.setStyleSheet(
            """
            QPushButton {
                background-color: #1C2128;
                color: #8B949E;
                font-family: 'Segoe UI';
                font-weight: 900;
                border-radius: 12px;
                font-size: 20px;
                border: 2px solid #30363D;
            }
            QPushButton:hover {
                background-color: #FFFFFF;
                border: 2px solid #FFFFFF;
                color: #0D1117;
            }
        """
        )
        btn_cam.clicked.connect(
            lambda: self.abrir_escaner_camara("BUSQUEDA", modo="LECTURA")
        )

        # Botón BUSCAR — fuera de la cápsula, estilo app estándar
        btn_go = QPushButton(tr("ubic.btn_search", default="BUSCAR"))
        btn_go.setFixedSize(120, 52)
        btn_go.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_go.setStyleSheet(
            """
            QPushButton {
                background-color: #0D1117;
                color: #00FFC6;
                border-radius: 12px;
                font-family: 'Segoe UI';
                font-weight: 900;
                font-size: 13px;
                letter-spacing: 1.5px;
                border: 2px solid #00FFC6;
            }
            QPushButton:hover { background-color: #00FFC6; color: #0D1117; border: 2px solid #00FFC6; }
        """
        )
        btn_go.clicked.connect(self.ejecutar_busqueda)

        search_row.addWidget(search_box)
        search_row.addWidget(btn_cam)
        search_row.addWidget(btn_go)
        layout.addLayout(search_row)

        # 3. PANEL DE RESULTADOS DINÁMICO
        self.result_panel = QFrame()
        self.result_panel.setVisible(False)  # Se activa tras ejecutar búsqueda
        self.result_panel.setObjectName("panel_resultado")
        self.result_panel.setStyleSheet(
            """
            QFrame#panel_resultado { 
                border: 1px solid #30363D; 
                border-radius: 20px; 
                background-color: #161B22;
            }
        """
        )

        res_layout = QVBoxLayout(self.result_panel)
        res_layout.setContentsMargins(35, 35, 35, 35)
        res_layout.setSpacing(30)

        # Fila Superior: Identidad y Acción GPS
        prod_info_lyt = QHBoxLayout()
        detalles_v = QVBoxLayout()

        self.res_nombre = QLabel(tr("ubic.product_name_ph", default="NOMBRE DEL PRODUCTO"))
        self.res_nombre.setStyleSheet(
            """
            font-family: 'Segoe UI';
            font-size: 28px; 
            font-weight: 900; 
            color: white; 
            border: none;
        """
        )

        self.res_codigo = QLabel(tr("ubic.sku_ph", default="SKU: 000000000000"))
        self.res_codigo.setStyleSheet(
            """
            color: #8B949E; 
            font-family: 'Segoe UI';
            font-size: 14px; 
            font-weight: 900;
            border: none;
        """
        )

        detalles_v.addWidget(self.res_nombre)
        detalles_v.addWidget(self.res_codigo)

        prod_info_lyt.addLayout(detalles_v)
        prod_info_lyt.addStretch()

        self.btn_ir_gps = QPushButton("🚀 " + tr("ubic.gps_route", default="RUTA GPS"))
        self.btn_ir_gps.setFixedSize(180, 50)
        self.btn_ir_gps.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ir_gps.setStyleSheet(
            """
            QPushButton { 
                background-color: transparent; 
                color: #00FFC6; 
                border: 2px solid #00FFC6; 
                border-radius: 12px; 
                font-family: 'Segoe UI';
                font-weight: 900; 
                font-size: 14px;
            }
            QPushButton:hover { 
                background-color: #00FFC6; 
                color: #0D1117; 
            }
        """
        )
        self.btn_ir_gps.clicked.connect(self.saltar_al_gps)
        prod_info_lyt.addWidget(self.btn_ir_gps)

        res_layout.addLayout(prod_info_lyt)

        # Sección de Telemetría (KPI Cards)
        grid_ubi = QHBoxLayout()
        grid_ubi.setSpacing(20)

        # Usamos el método crear_tarjeta_info actualizado anteriormente
        self.card_lineal = self.crear_tarjeta_info(tr("ubic.card_lineal", default="UBICACIÓN LINEAL"), "---", "#00FFC6")
        self.card_almacen = self.crear_tarjeta_info(tr("ubic.card_almacen", default="BODEGA / STOCK"), "---", "#58A6FF")
        self.card_stock = self.crear_tarjeta_info(tr("ubic.card_stock", default="UNIDADES TOTALES"), "0", "#FFA657")

        grid_ubi.addWidget(self.card_lineal)
        grid_ubi.addWidget(self.card_almacen)
        grid_ubi.addWidget(self.card_stock)

        res_layout.addLayout(grid_ubi)

        layout.addWidget(self.result_panel)
        layout.addStretch()

        return vista

    # ============================================================
    # BLOQUE ESCÁNER DE CÁMARA
    # ============================================================

    def abrir_escaner_camara(
        self,
        titulo_contexto="BUSQUEDA",
        modo="BUSQUEDA",
        extra_data=None,
    ):
        """
        Visor HUD con fondo ultra-oscuro y contorno azul neón.
        Se utiliza un Frame interno para asegurar que el diseño no se pierda al quitar la barra blanca.
        """
        from PyQt6.QtCore import Qt, QTimer
        from PyQt6.QtGui import QPixmap
        from PyQt6.QtWidgets import QDialog

        self.dlg_scan = QDialog(self)
        titulo_ui = str(titulo_contexto or "VISIÓN").upper()
        if not titulo_ui.startswith("VISIÓN"):
            titulo_ui = f"VISIÓN - {titulo_ui}"

        if construir_plantilla_camara is not None:
            plantilla = construir_plantilla_camara(
                self.dlg_scan,
                titulo=titulo_ui,
                texto_video="",
                estado_inicial=tr("ubic.cam_status", default="ALINEE EL CÓDIGO CON EL SENSOR"),
                texto_boton_primario=tr("ubic.cam_start", default="INICIAR ESCANEO"),
                texto_boton_cancelar=tr("ubic.cam_abort", default="ABORTAR OPERACIÓN"),
                ancho=500,
                alto=600,
                ancho_video=420,
                alto_video=320,
                mostrar_boton_primario=False,
                object_name_dialog="scanner_dialog",
                object_name_frame="cuerpo_ventana_scan",
            )
            self.cuerpo_ventana = plantilla["main_frame"]
            self.lbl_video = plantilla["lbl_video"]
            self.lbl_video.setText("")
            self.lbl_status = plantilla["lbl_status"]
            self.lbl_status.setObjectName("lbl_info_scan")
            self.lbl_status.setText(tr("ubic.cam_status", default="ALINEE EL CÓDIGO CON EL SENSOR"))
            btn_cerrar = plantilla["btn_cancelar"]
            btn_cerrar.clicked.connect(self.abortar_escaneo)
            if aplicar_estilo_widget is not None:
                aplicar_estilo_widget(self.lbl_video)
                aplicar_estilo_widget(self.lbl_status)
                aplicar_estilo_widget(btn_cerrar)
        else:
            self.dlg_scan.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
            )
            self.dlg_scan.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.dlg_scan.setFixedSize(500, 600)

        # --- Lógica de Hardware ---
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.timer_camara = QTimer(self)

        def update_frame():
            if not self.dlg_scan.isVisible():
                self.limpiar_recursos_camara()
                return

            ret, frame = self.cap.read()
            if ret:
                codes = pyzbar.decode(frame)
                for barcode in codes:
                    codigo_detectado = barcode.data.decode("utf-8")
                    if modo == "REGISTRO":
                        self.finalizar_grabacion_logistica(extra_data, codigo_detectado)
                    else:
                        self.procesar_escaneo_barcode(codigo_detectado)
                    self.limpiar_recursos_camara()
                    self.dlg_scan.accept()
                    return

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
                from PyQt6.QtCore import QRectF
                from PyQt6.QtGui import QPainter, QPainterPath
                tw = self.lbl_video.width()
                th = self.lbl_video.height()
                if tw > 0 and th > 0:
                    B = 4  # border inset
                    iw, ih = tw - 2 * B, th - 2 * B
                    src = QPixmap.fromImage(img)
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
                    _pen = QPen(QColor(0, 255, 198, 255), B * 2)
                    _pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                    painter.setPen(_pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRoundedRect(QRectF(B, B, iw, ih), 12, 12)
                    painter.end()
                    self.lbl_video.setPixmap(result)

        self.timer_camara.timeout.connect(update_frame)
        self.timer_camara.start(30)
        self.dlg_scan.finished.connect(self.limpiar_recursos_camara)
        self.dlg_scan.exec()

    def abortar_escaneo(self):
        """Cierra el diálogo y libera la cámara inmediatamente."""
        if hasattr(self, "dlg_scan"):
            self.dlg_scan.reject()
        self.limpiar_recursos_camara()

    def limpiar_recursos_camara(self):
        """Libera el sensor y detiene los hilos de procesamiento de video."""
        if hasattr(self, "timer_camara") and self.timer_camara.isActive():
            self.timer_camara.stop()
        if hasattr(self, "cap") and self.cap.isOpened():
            self.cap.release()
        print("DEBUG: Hardware de visión liberado.")

    # ============================================================
    # BLOQUE FLUJO DE RUTA GPS
    # ============================================================

    def saltar_al_gps(self):
        """
        MOTOR DE TRANSICIÓN: Activa el modo navegación con 'Target Lock'.
        Sincroniza el destino, ajusta el HUD y centra la cámara en el objetivo.
        """
        from PyQt6.QtCore import Qt, QTimer
        from PyQt6.QtWidgets import QMessageBox

        # --- 1. VALIDACIÓN DE COORDENADAS DE DESTINO ---
        coord_dest = getattr(self, "coordenadas_destino", None)
        # Destino activo (dict con coords/nombre/tipo/ubicacion) fijado por
        # _preparar_destino_gps. Se recupera aquí para reconfigurar la navegación.
        seleccion = getattr(self, "destino_gps_activo", None) or {}

        # Verificamos si las coordenadas son nulas o están en el origen (0,0)
        if not coord_dest or (coord_dest.x() == 0 and coord_dest.y() == 0):
            msg = QMessageBox(self)
            # Estética Cyberpunk para el diálogo de error
            msg.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle(tr("ubic.gps_err_title", default="ERROR GPS"))
            msg.setText(tr("ubic.gps_err_msg", default="EL ACTIVO NO TIENE COORDENADAS VÁLIDAS EN EL MAPA."))
            msg.setStyleSheet(
                """
                QMessageBox { 
                    background-color: #0A0A0A; 
                    border: 2px solid #FF5555; 
                    border-radius: 12px; 
                }
                QLabel { 
                    color: #FF5555; 
                    font-family: 'Segoe UI'; 
                    font-weight: 900; 
                    font-size: 13px;
                    padding: 10px; 
                }
                QPushButton { 
                    background-color: #1A1A1A; 
                    color: white; 
                    border: 1px solid #FF5555; 
                    border-radius: 5px; 
                    padding: 6px 15px; 
                    font-family: 'Segoe UI';
                    font-weight: 900; 
                }
                QPushButton:hover { background-color: #FFFFFF; color: #0D1117; border: 1px solid #FFFFFF; }
            """
            )
            msg.exec()
            return

        # --- 2. CAMBIO DE CONTEXTO VISUAL (Pantalla de Navegación) ---
        self._preparar_destino_gps(
            seleccion, navegar_a_gps=True, activar_piloto=False, enfocar=True
        )

        if hasattr(self, "stack"):
            # Cambiamos al índice 3 (donde reside el Visor de Navegación)
            self.stack.setCurrentIndex(3)

        if hasattr(self, "actualizar_estado_menu") and hasattr(self, "btn_nav_gps"):
            self.actualizar_estado_menu(self.btn_nav_gps)

        # --- 3. RESET DE RUTA Y FIJACIÓN DE OBJETIVO ---
        visor = getattr(self, "visor_mapa", None)
        if visor:
            # Limpiamos rastros de rutas anteriores
            if hasattr(visor, "limpiar_ruta"):
                visor.limpiar_ruta()

            # Marcamos el punto de destino en el motor interno del visor
            if hasattr(visor, "set_punto_destino"):
                visor.set_punto_destino(coord_dest.x(), coord_dest.y())

            # AUTO-CENTRADO: Centramos la vista en el objetivo con un ligero delay
            # para que la transición del stack termine primero.
            QTimer.singleShot(200, lambda: visor.centerOn(coord_dest))

        # --- 4. CONFIGURACIÓN DEL HUD (Estética Segoe UI Bold / Neón) ---
        nombre_prod = (
            f"{seleccion.get('nombre', '').upper()} · {seleccion.get('tipo', '')} · {seleccion.get('ubicacion', '')}"
        ).strip(" ·")
        if not nombre_prod:
            for attr in ["res_nombre", "lbl_resultado_nombre"]:
                obj = getattr(self, attr, None)
                if obj and hasattr(obj, "text") and obj.text():
                    nombre_prod = obj.text().upper()
                    break

        instruccion = (
            f"🎯 DESTINO: {nombre_prod}\n"
            f"📡 [ESCANEE QR DE PASILLO PARA CALIBRAR POSICIÓN]"
        )

        lbl_hud = getattr(self, "lbl_instrucciones_gps", None)
        if lbl_hud:
            lbl_hud.setText(instruccion)
            lbl_hud.setStyleSheet(
                """
                color: #00FFC6; 
                background: rgba(0, 255, 198, 0.08); 
                border-left: 6px solid #00FFC6;
                padding: 18px; 
                font-family: 'Segoe UI';
                font-weight: 900;
                font-size: 14px;
                letter-spacing: 0.8px;
                border-radius: 4px;
            """
            )

        # Feedback en la barra de estado inferior
        if self.statusBar():
            self.statusBar().setStyleSheet(
                "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900;"
            )
            self.statusBar().showMessage(tr("ubic.gps_dest_ready", default="DESTINO GPS PREPARADO: {nombre}", nombre=nombre_prod), 6000)

    def finalizar_flujo_gps(self, punto_a, punto_b, nombre_art):
        """
        Estabiliza la navegación y dispara el motor A* unificado.
        punto_a: QPointF (Operario) | punto_b: QPointF (Destino)
        """
        import math

        try:
            # 1. CIERRE DE ESCÁNER DE CALIBRACIÓN
            win_scan = getattr(self, "win_gps_scan", None)
            if win_scan and win_scan.isVisible():
                win_scan.accept()

            # 2. SINCRONIZACIÓN DE TELEMETRÍA
            visor = getattr(self, "visor_mapa", None)
            if visor:
                visor.pos_operario = punto_a
                self.coordenadas_destino = punto_b
                if hasattr(visor, "set_punto_destino"):
                    visor.set_punto_destino(punto_b.x(), punto_b.y())

            # 3. CÁLCULO DE PROXIMIDAD (Pitágoras)
            distancia = math.hypot(punto_a.x() - punto_b.x(), punto_a.y() - punto_b.y())

            # 4. GESTIÓN DE LLEGADA O CÁLCULO DE RUTA
            if distancia < 35:  # Umbral de llegada ajustado (px)
                if visor and hasattr(visor, "limpiar_ruta"):
                    visor.limpiar_ruta()
                self._actualizar_piloto_rastreo(False)

                self.statusBar().setStyleSheet(
                    "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900; background: #0D1117;"
                )
                self.statusBar().showMessage(
                    f"✅ LLEGADA CONFIRMADA: {nombre_art.upper()}", 10000
                )

                if hasattr(self, "mostrar_mensaje_status"):
                    self.mostrar_mensaje_status("📍 OBJETIVO ALCANZADO", "#00FFC6")
            else:
                # DISPARO DEL MOTOR A* UNIFICADO (El que creamos antes)
                # No pasamos término porque ya tenemos las coordenadas_destino fijadas
                if hasattr(self, "procesar_ruta_gps"):
                    self.procesar_ruta_gps()
                self._actualizar_piloto_rastreo(True, nombre_art.upper())

                self.statusBar().setStyleSheet(
                    "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900; background: #161B22;"
                )
                self.statusBar().showMessage(
                    f"🛰️ NAVEGACIÓN ACTIVA: {nombre_art.upper()}", 7000
                )

            # 5. ASEGURAR VISTA GPS
            if hasattr(self, "stack"):
                self.stack.setCurrentIndex(3)
            if hasattr(self, "btn_nav_gps"):
                self.btn_nav_gps.setChecked(True)

        except Exception as e:
            print(f"❌ Error crítico en estabilización GPS: {e}")

    def obtener_coordenadas_articulo(self, termino):
        """
        Motor Híbrido de Búsqueda: Infraestructura vs Stock.
        Garantiza el retorno de QPointF para compatibilidad con el motor A*.
        """
        from PyQt6.QtCore import QPointF

        from src.db.conexion import obtener_conexion

        try:
            termino = termino.strip().upper()
            if not termino:
                return None

            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    # 1. PRIORIDAD: INFRAESTRUCTURA (Ubicación fija o Pasillo)
                    sql_ubi = """
                        SELECT CONCAT('UBICACIÓN: ', pasillo, '-', estanteria), mapa_x, mapa_y 
                        FROM ubicaciones 
                        WHERE (codigo_articulo = %s OR pasillo = %s) 
                        AND mapa_x IS NOT NULL AND mapa_x != 0 
                        LIMIT 1
                    """
                    cursor.execute(sql_ubi, (termino, termino))
                    res = cursor.fetchone()

                    # 2. SEGUNDA OPCIÓN: STOCK COMERCIAL (Artículos volátiles)
                    if not res:
                        sql_art = """
                            SELECT nombre, mapa_x, mapa_y 
                            FROM articulos 
                            WHERE (nombre LIKE %s OR codigo = %s) 
                            AND mapa_x IS NOT NULL AND mapa_x != 0 
                            LIMIT 1
                        """
                        cursor.execute(sql_art, (f"%{termino}%", termino))
                        res = cursor.fetchone()

            # 3. PROCESAMIENTO DE COORDENADAS (Blindaje de precisión)
            if res:
                nombre_destino = res[0]
                try:
                    # Forzamos float para evitar errores en cálculos de distancia euclidiana
                    x = float(res[1])
                    y = float(res[2])

                    if x == 0 and y == 0:
                        return None

                    # Retornamos tupla limpia para el orquestador GPS
                    return nombre_destino, QPointF(x, y)
                except (ValueError, TypeError):
                    return None

            return None

        except Exception as e:
            print(f"❌ Error en Motor Híbrido de Coordenadas: {e}")
            return None

    def navegar_planta(self, direccion):
        """
        Selector de Nivel: Recarga infraestructura y LIMPIA rastreos activos
        para evitar rutas huérfanas entre plantas.
        """
        from src.db.conexion import obtener_conexion

        actual = getattr(self, "planta_actual", 0)
        nuevo_indice = actual + direccion

        if nuevo_indice < 0:
            if hasattr(self, "mostrar_mensaje_status"):
                self.mostrar_mensaje_status("ℹ️ YA ESTÁS EN LA PLANTA BASE", "#8B949E")
            return

        try:
            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(*) FROM configuracion_mapa WHERE planta_index = %s",
                        (nuevo_indice,),
                    )
                    existe = cursor.fetchone()[0] > 0

            if existe:
                # 1. ACTUALIZACIÓN DE ESTADO
                self._reiniciar_historial_planta(actual)
                self._reiniciar_historial_planta(nuevo_indice)
                self.planta_actual = nuevo_indice

                # 2. LIMPIEZA DE NAVEGACIÓN (Crucial al cambiar de planta)
                # Evitamos que la polilínea A* de la Planta 0 se vea en la Planta 1
                self._resetear_navegacion_gps(limpiar_operario=True)

                # 3. RECARGA DE INFRAESTRUCTURA (Muros, estanterías, QR)
                if hasattr(self, "cargar_infraestructura_registrada"):
                    self.cargar_infraestructura_registrada()

                # 4. FEEDBACK VISUAL (Segoe UI Bold)
                self._actualizar_labels_planta()
                if hasattr(self, "lbl_planta_actual"):
                    self.lbl_planta_actual.setStyleSheet(
                        "color: #00FFC6; font-weight: 900; font-family: 'Segoe UI';"
                    )

                if hasattr(self, "mostrar_mensaje_status"):
                    self.mostrar_mensaje_status(
                        f"🚚 DESPLEGANDO INFRAESTRUCTURA: PLANTA {self.planta_actual}",
                        "#00FFC6",
                    )

            else:
                if hasattr(self, "mostrar_mensaje_status"):
                    self.mostrar_mensaje_status(
                        "🚧 LÍMITE ALCANZADO: NO HAY MÁS PLANTAS", "#FFB86C"
                    )

        except Exception as e:
            print(f"❌ Error crítico en navegación de planta: {e}")
            if hasattr(self, "mostrar_mensaje_status"):
                self.mostrar_mensaje_status(
                    "❌ ERROR DE SINCRONIZACIÓN CON MARIADB", "#FF5555"
                )

    # ============================================================
    # BLOQUE INFRAESTRUCTURA Y MATRIZ
    # ============================================================

    def cargar_infraestructura_registrada(self):
        """
        RECONSTRUCTOR MAESTRO: Carga el entorno desde DB y ajusta el visor.
        Soluciona: Planos cortados, desincronización de matriz y visibilidad de iconos.
        """
        import json
        import os
        import traceback

        from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
        from PyQt6.QtWidgets import QGraphicsView

        from src.db.conexion import obtener_conexion

        # 1. VALIDACIÓN DE COMPONENTES
        visor_admin = getattr(self, "visor_admin", None)
        visor_mapa = getattr(self, "visor_mapa", None)
        escena = getattr(self, "escena_compartida", None)
        visores = [v for v in [visor_admin, visor_mapa] if v]

        if not escena or not visor_admin:
            return

        # No recargar mientras haya una calibración activa — evita borrar la escena y crashear
        if getattr(visor_admin, "modo_calibrar", False):
            return

        # Reset per-plan calibration state so flags don't bleed from one plan to another.
        # This allows the guide dialog to appear again when a new plan is calibrated,
        # and prevents a stale "calibration active" flag from the previous plan persisting.
        self.calibracion_en_curso_activa = False
        self.onboarding_muros_visto = False

        # Eagerly clear punto_ancla on all visores so the calibration button shows
        # "CALIBRAR ESCALA" immediately, even if cargar_infraestructura_registrada exits
        # early (image not found, no DB row, etc.).  The re-assert below will restore it
        # for plans that ARE calibrated once the DB row is read.
        for v in visores:
            v.punto_ancla = None
        if hasattr(self, "actualizar_estado_bloqueo"):
            self.actualizar_estado_bloqueo()

        # Congelar UI para evitar parpadeos durante el renderizado masivo
        for v in visores:
            v.setUpdatesEnabled(False)
            v.setInteractive(False)

        try:
            p_idx = getattr(self, "planta_actual", 0)

            # Temporary debug: trace unexpected non-zero plant loads so we can
            # identify and eliminate the root cause.
            if p_idx > 0 and not getattr(self, "_startup_complete", True):
                import traceback as _tb
                print(f"\n⚠️ [DEBUG] Carga inesperada de Planta {p_idx} durante arranque:")
                _tb.print_stack(limit=8)
                print()

            # --- 2. EXTRACCIÓN DE DATOS ---
            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    sql = """
                        SELECT ruta_imagen, escala_px_metro, ancla_x, ancla_y, 
                               muros_vectoriales, puntos_infraestructura 
                        FROM configuracion_mapa WHERE planta_index = %s 
                        ORDER BY id DESC LIMIT 1
                    """
                    cursor.execute(sql, (p_idx,))
                    config = cursor.fetchone()

            if not config:
                self._vaciar_plano_en_visores()
                return

            nombre_archivo, escala_val, a_x, a_y, muros_json, infra_json = config
            muros_data = {}
            if muros_json:
                try:
                    _parsed = json.loads(muros_json)
                    if isinstance(_parsed, dict):
                        muros_data = _parsed
                    elif isinstance(_parsed, list):
                        muros_data = {"muros_vectores": _parsed}
                except Exception:
                    muros_data = {}

            # --- 3. CARGA DEL FONDO (Cimiento visual y lógico) ---
            self._resetear_navegacion_gps(limpiar_operario=True)
            escena.clear()
            # historial_muros references are now dangling (escena.clear removes all items).
            # Wipe the lists so downstream code doesn't try to removeItem them again.
            for v in visores:
                if hasattr(v, "historial_muros"):
                    v.historial_muros = []
            escena.invalidate(escena.sceneRect(), QGraphicsScene.SceneLayer.AllLayers)
            # Ruta absoluta para evitar fallos de carga
            ruta_planos = os.path.join(os.getcwd(), "documentos", "planos")
            ruta_final = os.path.join(ruta_planos, str(nombre_archivo))

            pixmap = QPixmap(ruta_final)
            if not pixmap.isNull():
                self.ruta_actual = ruta_final
                self.ultimo_plano_cargado = ruta_final
                self.pixmap_item = QGraphicsPixmapItem(pixmap)
                self.pixmap_item.setZValue(-10000)  # Fondo absoluto
                self.pixmap_item.setData(0, "FONDO_MAPA")
                self.pixmap_item.setTransformationMode(
                    Qt.TransformationMode.SmoothTransformation
                )
                escena.addItem(self.pixmap_item)

                # Sincronizar dimensiones de la escena con el plano
                rect_plano = QRectF(pixmap.rect())
                escena.setSceneRect(rect_plano)
                escena.invalidate(rect_plano, QGraphicsScene.SceneLayer.AllLayers)

                # Asignar referencia de fondo a los visores para el cálculo de matriz
                for v in visores:
                    v.pixmap_item = self.pixmap_item
                    v.ruta_actual = ruta_final
                    v._zoom_manual_activo = False
                    # Ajuste de scroll para evitar recortes accidentales
                    v.setHorizontalScrollBarPolicy(
                        Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                    )
                    v.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            else:
                print(
                    f"❌ Error crítico: No se encuentra el archivo de imagen en {ruta_final}"
                )
                return

            # --- 4. RECONSTRUCCIÓN UNIFICADA (Muros + Matriz NumPy) ---
            if muros_json:
                # Este método ya gestiona la visualización Neón y la lógica A*
                self.cargar_matriz_serializada(muros_json)
                # Ensure the unlock flag is set when muros are restored from DB so
                # actualizar_estado_bloqueo() doesn't keep buttons locked after restart.
                if muros_data.get("muros_vectores"):
                    self.muros_completados = True

            # --- 5. RECONSTRUCCIÓN DE ICONOS ---
            if infra_json:
                try:
                    puntos = json.loads(infra_json)
                    for p in puntos:
                        visor_admin.colocar_marcador_3d(
                            QPointF(float(p.get("x", 0)), float(p.get("y", 0))),
                            p.get("tipo", "ICONO"),
                            p.get("nombre", "PUNTO"),
                            epc=p.get("epc"),
                            modo_carga=True,
                        )
                except Exception as e:
                    print(f"⚠️ Error cargando iconos: {e}")

            # --- 6. ESCALA Y ANCLA ---
            # If escala_val is 0 (plan loaded but not yet calibrated), fall back to 1.0
            # to avoid division-by-zero in navigation calculations.
            _ev = float(escala_val) if escala_val is not None else 0.0
            escala_f = _ev if _ev > 0 else 1.0
            _plan_calibrado = _ev > 0
            self.ratio_px_m_h = self.ratio_px_m_v = escala_f

            # Determine authoritative anchor from DB columns (more reliable than JSON).
            _ax_f = float(a_x) if a_x is not None else None
            _ay_f = float(a_y) if a_y is not None else None
            _ancla_db = {"x": _ax_f, "y": _ay_f} if (_plan_calibrado and _ax_f is not None) else None

            for v in visores:
                v.ratio_px_m_h = v.ratio_px_m_v = escala_f
                if _plan_calibrado and _ax_f is not None:
                    v.punto_ancla = QPointF(_ax_f, _ay_f)
                    v.coord_ancla_x = _ax_f
                    v.coord_ancla_y = _ay_f
                else:
                    # Clear anchor so the calibration button shows "CALIBRAR" not "RECALIBRAR"
                    v.punto_ancla = None

            # btn_escala is permanently connected to _clic_boton_escala (stateless handler)

            # Prefer DB-column anchor (always correct); use JSON as calibracion visual only.
            snapshot_cargado = {
                "muros_vectores": muros_data.get(
                    "muros_vectores", muros_data if isinstance(muros_data, list) else []
                ),
                "calibracion": muros_data.get("calibracion"),
                "ancla": _ancla_db,
            }
            self.reconstruir_estado_mapa_actual(snapshot_cargado, recuadrar=False)

            # reconstruir calls _limpiar_capas_editables which wipes punto_ancla.
            # Re-assert from DB values to guarantee escala_ok after restart.
            if _plan_calibrado and _ax_f is not None:
                for v in visores:
                    if v.punto_ancla is None:
                        v.punto_ancla = QPointF(_ax_f, _ay_f)
                        v.coord_ancla_x = _ax_f
                        v.coord_ancla_y = _ay_f
                if muros_data.get("muros_vectores"):
                    self.muros_completados = True

            self._actualizar_labels_planta()
            self._reiniciar_historial_planta(p_idx)

            # Refresh calibration button text (CALIBRAR vs RECALIBRAR) from DB state
            if hasattr(self, "actualizar_estado_bloqueo"):
                self.actualizar_estado_bloqueo()

            # --- 7. AJUSTE DE ENCUADRE (Auto-Zoom) ---
            QTimer.singleShot(150, lambda: self.reencuadrar_plano(force=True))
            self._forzar_reencuadre_diferido(force=True)

        except Exception:
            traceback.print_exc()

        finally:
            # Reactivar interacción y devolver el control al usuario
            for v in visores:
                v.setUpdatesEnabled(True)
                v.setInteractive(True)
                v.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
                v.viewport().update()

            print(f"✅ Infraestructura Planta {p_idx} cargada y encuadrada.")

    def generar_matriz_desde_vectores(self, muros_vectores):
        """
        Rasteriza los vectores de muros en una matriz NumPy.
        FIX: Uso de la escena compartida y validación de dimensiones.
        """
        import numpy as np
        from PyQt6.QtCore import QPointF

        try:
            escena = self.escena_compartida
            if not escena:
                return

            size = getattr(self, "celda_size", 20)
            rect = escena.sceneRect()

            # Dimensionamiento basado en el área real del plano
            cols = max(1, int(rect.width() // size) + 1)
            rows = max(1, int(rect.height() // size) + 1)

            # Crear matriz de ceros (Libre)
            self.matriz_obstaculos = np.zeros((rows, cols), dtype=np.uint8)

            if muros_vectores:
                for m in muros_vectores:
                    p1 = QPointF(float(m["x1"]), float(m["y1"]))
                    p2 = QPointF(float(m["x2"]), float(m["y2"]))

                    # Rasterización usando el método de trazado de líneas del visor
                    # Esto asegura que la matriz coincida visualmente con los muros
                    if hasattr(self.visor_admin, "marcar_muro_en_matriz"):
                        self.visor_admin.marcar_muro_en_matriz(
                            p1, p2, es_muro_preciso=True
                        )
                    else:
                        # Fallback: Bresenham simplificado o extremos
                        r1, c1 = int(p1.y() // size), int(p1.x() // size)
                        r2, c2 = int(p2.y() // size), int(p2.x() // size)
                        if 0 <= r1 < rows and 0 <= c1 < cols:
                            self.matriz_obstaculos[r1, c1] = 1
                        if 0 <= r2 < rows and 0 <= c2 < cols:
                            self.matriz_obstaculos[r2, c2] = 1

            # Sincronizar visores
            if hasattr(self, "visor_admin"):
                self.visor_admin.matriz_obstaculos = self.matriz_obstaculos
            if hasattr(self, "visor_mapa"):
                self.visor_mapa.matriz_obstaculos = self.matriz_obstaculos

            self.visor_admin.viewport().update()
            print(f"✅ Matriz regenerada: {self.matriz_obstaculos.shape}")

        except Exception as e:
            print(f"❌ Error matriz: {e}")

    # ============================================================
    # BLOQUE VERIFICACIÓN Y EXPORTACIÓN
    # ============================================================

    def confirmar_verificacion_fisica_db(self, qr_id):
        """
        Cambia el estado de 0 (Naranja) a 1 (Turquesa) en la tabla 'ubicaciones'.
        Garantiza persistencia visual y en DB tras el escaneo.
        """
        from src.db.conexion import obtener_conexion

        try:
            # Query optimizada: Solo actúa si el estado es 0
            query = """
                UPDATE ubicaciones 
                SET verificado = 1 
                WHERE codigo_articulo = %s AND verificado = 0
            """

            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (qr_id,))
                    conn.commit()
                    filas_afectadas = cursor.rowcount

            # 2. Feedback y Sincronización Visual
            if filas_afectadas > 0:
                print(f"LOGÍSTICA: Artículo {qr_id} verificado con éxito.")

                # Intentamos enviar mensaje a la StatusBar de forma segura
                main_w = self.window()
                if main_w and hasattr(main_w, "statusBar") and main_w.statusBar():
                    main_w.statusBar().showMessage(
                        f"✅ ARTÍCULO VERIFICADO: {qr_id}", 4000
                    )

                # IMPORTANTE: Si el objeto existe en la escena, podrías cambiarle el color aquí
                # para que el cambio de Naranja a Turquesa sea instantáneo.
                if hasattr(self, "actualizar_color_marcador_verificado"):
                    self.actualizar_color_marcador_verificado(qr_id)
            else:
                print(f"DEBUG: El artículo {qr_id} ya estaba verificado o no existe.")

        except Exception as e:
            print(f"❌ Error crítico en validación de DB (QR: {qr_id}): {e}")

    def exportar_qrs_desde_mapa(self):
        """
        Analiza los marcadores del mapa y genera un PDF con códigos QR
        listos para imprimir y pegar en las estanterías.
        """
        # 1. Validación de existencia de datos
        marcadores = getattr(self.visor_admin, "lista_marcadores", [])

        if not marcadores:
            QMessageBox.warning(
                self,
                "EXPORTACIÓN VACÍA",
                "No hay marcadores técnicos definidos en el mapa para generar etiquetas.",
            )
            return

        datos_para_pdf = []
        for m in marcadores:
            id_qr = m.get("id")
            if id_qr:
                # Limpiamos el nombre para que quepa bien en la etiqueta
                nombre = m.get("nombre", f"UBICACIÓN {id_qr}").upper()
                datos_para_pdf.append([str(id_qr), nombre])

        # 2. Llamada al motor de generación (Bloque 18 de tu lógica general)
        if datos_para_pdf:
            try:
                # Suponemos que ejecutar_generacion_pdf_final maneja la creación de los QR
                self.ejecutar_generacion_pdf_final(datos_para_pdf)
                self.statusBar().showMessage(
                    f"Se han enviado {len(datos_para_pdf)} etiquetas al motor PDF.",
                    5000,
                )
            except Exception as e:
                QMessageBox.critical(
                    self, "ERROR", f"Fallo al generar pliego de etiquetas: {e}"
                )

    def exportar_hoja_ruta_pasillos(self):
        """
        Genera un documento PDF profesional con la lista de stock
        ordenada por ubicación física para auditorías.
        """
        try:
            import os

            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import (
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )

            # 1. Configuración de Archivo
            ruta_docs = self.obtener_ruta_documentos()  # Helper que definimos antes
            nombre_archivo = (
                f"AUDITORIA_STOCK_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
            )
            dest_path = os.path.join(ruta_docs, nombre_archivo)

            doc = SimpleDocTemplate(dest_path, pagesize=A4)
            elementos = []
            estilos = getSampleStyleSheet()

            # 2. Encabezado del Reporte
            titulo = Paragraph(
                "<b>REPORTE DE AUDITORÍA DE STOCK</b>", estilos["Title"]
            )
            fecha = Paragraph(
                f"Fecha de generación: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                estilos["Normal"],
            )
            elementos.extend([titulo, fecha, Spacer(1, 20)])

            # 3. Preparación de Datos (Extracción de MariaDB)
            datos_tabla = [
                [
                    "CÓDIGO SKU",
                    "ARTÍCULO",
                    "PASILLO-ESTANTE-NIVEL",
                    "VERIF.",
                ]
            ]

            with obtener_conexion() as conn:
                cursor = conn.cursor()
                # Orden lógico de caminata: Pasillo -> Estantería -> Nivel
                sql = """
                    SELECT codigo, nombre, pasillo, estanteria, nivel 
                    FROM articulos 
                    WHERE pasillo IS NOT NULL AND pasillo != ''
                    ORDER BY pasillo ASC, CAST(estanteria AS UNSIGNED) ASC, CAST(nivel AS UNSIGNED) ASC
                """
                cursor.execute(sql)
                rows = cursor.fetchall()

                for r in rows:
                    ubicacion_str = f"{r[2]} - {r[3]} - {r[4]}"
                    # Truncamos nombre para que no rompa la tabla
                    nombre_corto = (r[1][:35] + "..") if len(r[1]) > 35 else r[1]
                    datos_tabla.append(
                        [r[0], nombre_corto.upper(), ubicacion_str, "[  ]"]
                    )

            # 4. Diseño de la Tabla (Estilo Industrial)
            tabla = Table(datos_tabla, colWidths=[90, 230, 130, 50])
            tabla.setStyle(
                TableStyle(
                    [
                        (
                            "BACKGROUND",
                            (0, 0),
                            (-1, 0),
                            colors.HexColor("#0D1117"),
                        ),  # Fondo oscuro
                        (
                            "TEXTCOLOR",
                            (0, 0),
                            (-1, 0),
                            colors.HexColor("#00FFC6"),
                        ),  # Texto turquesa
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        (
                            "ALIGN",
                            (1, 1),
                            (1, -1),
                            "LEFT",
                        ),  # Nombre alineado a la izquierda
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.whitesmoke, colors.white],
                        ),
                    ]
                )
            )

            elementos.append(tabla)
            doc.build(elementos)

            # 5. Apertura automática y Feedback
            os.startfile(dest_path)
            if self.window().statusBar():
                self.window().statusBar().showMessage(
                    f"Hoja de ruta generada en: {nombre_archivo}", 6000
                )

        except Exception as e:
            QMessageBox.critical(
                self, "ERROR DE REPORTE", f"No se pudo generar el PDF: {e}"
            )

    def obtener_ruta_documentos(self):
        """
        Garantiza la persistencia de la estructura de directorios del proyecto.
        Retorna la ruta absoluta hacia el repositorio de reportes PDF.
        """
        # Unificamos la ruta base para mantener orden en la raíz del proyecto
        ruta = os.path.abspath(os.path.join("360-stock", "documentos", "reportes"))

        try:
            if not os.path.exists(ruta):
                # exist_ok=True evita errores de concurrencia
                os.makedirs(ruta, exist_ok=True)
            return ruta
        except Exception as e:
            print(f"Error de sistema al crear directorios: {e}")
            # Fallback al directorio del usuario en caso de error de permisos en la carpeta raíz
            return os.path.join(os.path.expanduser("~"), "Documents")

    def abrir_carpeta_qrs(self):
        """
        Versión de ALTA COMPATIBILIDAD.
        Fuerza la apertura del explorador mediante comando de sistema 'start'.
        """
        import os
        import platform

        from PyQt6.QtWidgets import QMessageBox

        # 1. OBTENCIÓN DE RUTA ABSOLUTA REAL (Sincronizada con el terminal)
        try:
            # Obtenemos la raíz y garantizamos la ruta absoluta final
            base_raiz = os.path.abspath(os.getcwd())
            ruta_sin_normalizar = os.path.join(
                base_raiz, "documentos", "qr_ubicaciones"
            )
            ruta = os.path.abspath(ruta_sin_normalizar)
            ruta_relativa = os.path.join("documentos", "qr_ubicaciones")
        except Exception:
            ruta_relativa = os.path.join("documentos", "qr_ubicaciones")
            ruta = os.path.abspath(ruta_relativa)

        # DEBUG: Mira tu terminal cuando pulses el botón para confirmar esta ruta
        print(f"\n[DEBUG QR] Intentando abrir: {ruta}")

        # 2. Verificación de existencia
        if not os.path.exists(ruta):
            try:
                os.makedirs(ruta, exist_ok=True)
            except Exception as e:
                print(f"[ERROR] No se pudo crear la carpeta: {e}")
                return

        try:
            # 3. EJECUCIÓN POR COMANDO DE SISTEMA (Inmune a bloqueos de GUI)
            sistema = platform.system()
            ruta_limpia = os.path.normpath(ruta)

            if sistema == "Windows":
                # El comando 'start' es una orden directa al kernel de Windows
                # Las comillas vacías iniciales son obligatorias para el comando start
                os.system(f'start "" "{ruta_limpia}"')
            elif sistema == "Darwin":  # macOS
                os.system(f'open "{ruta_limpia}"')
            else:  # Linux
                os.system(f'xdg-open "{ruta_limpia}"')

            # 4. Feedback visual en la StatusBar
            if self.window().statusBar():
                self.window().statusBar().setStyleSheet(
                    "background-color: #00FFC6; color: #0D1117; font-family: 'Segoe UI'; font-weight: 900;"
                )
                self.window().statusBar().showMessage(
                    f"ORDEN DE APERTURA ENVIADA: {ruta_relativa}", 4000
                )

        except Exception as e:
            print(f"[ERROR] Fallo crítico al abrir explorador: {e}")
            msg_err = QMessageBox(self)
            msg_err.setWindowTitle(tr("ubic.sys_err_title", default="ERROR DE SISTEMA"))
            msg_err.setText(tr("ubic.explorer_err", default="Error al invocar el explorador nativo:<br>{e}", e=e))
            msg_err.setStyleSheet(
                """
                QMessageBox { background-color: #0D1117; border: 1px solid #F85149; }
                QLabel { color: #F85149; }
                QPushButton { background-color: #30363D; color: white; }
                """
            )
            msg_err.exec()

    def ejecutar_generacion_pdf_final(self):
        """
        Genera el PDF con las etiquetas PENDIENTES (impreso = 0).
        Incluye el código EPC en el QR y marca los registros como procesados en DB.
        """
        import os
        from datetime import datetime

        import qrcode

        # 1. OBTENER DATOS DE INFRAESTRUCTURA PENDIENTE
        try:
            with obtener_conexion() as conn:
                cursor = conn.cursor()
                # Seleccionamos las que aún no han pasado por la cola de impresión
                cursor.execute(
                    "SELECT epc, pasillo, estanteria FROM ubicaciones WHERE impreso = 0"
                )
                lista_pendientes = cursor.fetchall()

            if not lista_pendientes:
                QMessageBox.information(
                    self,
                    "PDF",
                    "No hay etiquetas nuevas en la cola de impresión.",
                )
                return

            # 2. Preparación de Entorno de Archivos
            ruta_carpeta = os.path.join("documentos", "etiquetas_rfid")
            if not os.path.exists(ruta_carpeta):
                os.makedirs(ruta_carpeta)

            nombre_archivo = (
                f"LOTE_ETIQUETAS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            )
            path_pdf = os.path.join(ruta_carpeta, nombre_archivo)

            c = canvas.Canvas(path_pdf, pagesize=A4)
            width, height = A4

            # Configuración de Rejilla (3x4 por página)
            col, fila = 0, 0
            ancho_cuadro, alto_cuadro = 6.5 * cm, 7.5 * cm
            epcs_procesados = []

            for epc, pasillo, estanteria in lista_pendientes:
                # TRAMA TÉCNICA: Esta es la que leerá el lector QR/RFID del operario
                trama_datos = f"EPC:{epc}|LOC:{pasillo}-{estanteria}"

                # Generar QR dinámico
                qr_img = qrcode.make(trama_datos)
                temp_path = f"temp_{epc}.png"
                qr_img.save(temp_path)

                # Cálculo de posición en el folio
                x = 1.0 * cm + (col * ancho_cuadro)
                y = height - 8.5 * cm - (fila * alto_cuadro)

                # --- DISEÑO DE LA ETIQUETA ---
                # 1. Dibujar el QR
                c.drawImage(
                    temp_path, x + 1.25 * cm, y + 2 * cm, width=4 * cm, height=4 * cm
                )

                # 2. Textos HUD (Identificación Visual)
                c.setFont("Helvetica-Bold", 10)
                c.setFillColorRGB(
                    0, 0, 0
                )  # Negro para impresión térmica/láser
                c.drawCentredString(x + 3.25 * cm, y + 1.2 * cm, f"PASILLO: {pasillo}")
                c.drawCentredString(
                    x + 3.25 * cm, y + 0.7 * cm, f"ESTANTE: {estanteria}"
                )

                c.setFont("Helvetica", 7)
                c.drawCentredString(x + 3.25 * cm, y + 0.2 * cm, f"ID EPC: {epc}")

                # 3. Marco de corte (Punteado estético)
                c.setDash(1, 2)
                c.setStrokeColorRGB(0.7, 0.7, 0.7)
                c.rect(x, y, 6.3 * cm, 7.3 * cm)

                # Limpieza de imagen temporal
                if os.path.exists(temp_path):
                    os.remove(temp_path)

                epcs_procesados.append(epc)

                # Gestión de saltos de página
                col += 1
                if col >= 3:
                    col = 0
                    fila += 1
                if fila >= 4:
                    c.showPage()
                    col, fila = 0, 0

            c.save()

            # 3. ACTUALIZACIÓN MASIVA EN BASE DE DATOS
            # Marcamos como impresas para que no salgan en el próximo PDF
            with obtener_conexion() as conn:
                cursor = conn.cursor()
                for epc_id in epcs_procesados:
                    cursor.execute(
                        "UPDATE ubicaciones SET impreso = 1 WHERE epc = %s", (epc_id,)
                    )
                conn.commit()

            # 4. Finalización y Apertura
            if self.window().statusBar():
                self.window().statusBar().showMessage(
                    f"PDF Generado: {len(epcs_procesados)} etiquetas listas.",
                    5000,
                )

            if os.name == "nt":
                os.startfile(ruta_carpeta)

        except Exception as e:
            QMessageBox.critical(
                self, "Error PDF", f"Fallo en la generación de pliegos: {e}"
            )

    # ============================================================
    # BLOQUE ADMINISTRACIÓN DE ARTÍCULOS
    # ============================================================

    def cargar_lista_articulos_admin(self, filtro=""):
        """
        Popula el panel lateral de búsqueda y conecta la lógica de radar/enfoque.
        ESTÉTICA: Segoe UI Bold y colores de estado.
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QColor, QFont

        from src.db.conexion import obtener_conexion

        if not hasattr(self, "lista_articulos_admin"):
            return

        # Limpieza de señales para evitar que un clic dispare múltiples eventos
        try:
            self.lista_articulos_admin.itemClicked.disconnect()
        except:
            pass

        self.lista_articulos_admin.clear()
        filtro = filtro.strip().upper()

        try:
            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    # Query con prioridad: Incidencias arriba
                    sql = """
                        SELECT codigo, nombre, incidencia_ubicacion 
                        FROM articulos 
                        WHERE nombre LIKE %s OR codigo LIKE %s
                        ORDER BY incidencia_ubicacion DESC, nombre ASC
                    """
                    term = f"%{filtro}%"
                    cursor.execute(sql, (term, term))
                    registros = cursor.fetchall()

            for cod, nom, inc in registros:
                icono = "⚠️" if inc else "📦"
                texto = f"{icono} {nom.upper()} | REF: {cod}"

                item = QListWidgetItem(texto)
                item.setData(Qt.ItemDataRole.UserRole, cod)

                # Aplicamos Segoe UI Bold a todos por directriz de diseño
                font = QFont("Segoe UI", 9, QFont.Weight.Bold)

                if inc:
                    item.setForeground(QColor("#FF5555"))  # Rojo Alerta
                    font.setWeight(QFont.Weight.Bold)
                else:
                    item.setForeground(QColor("#8B949E"))  # Gris estándar

                item.setFont(font)
                self.lista_articulos_admin.addItem(item)

            # Conexión segura al motor de enfoque
            self.lista_articulos_admin.itemClicked.connect(
                self.seleccionar_y_enfocar_articulo
            )

            if self.window().statusBar():
                self.window().statusBar().setStyleSheet(
                    "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900;"
                )
                self.window().statusBar().showMessage(
                    f"SISTEMA: {len(registros)} ARTÍCULOS SINCRONIZADOS", 4000
                )

        except Exception as e:
            print(f"❌ ERROR (Admin List): {e}")

    def seleccionar_y_enfocar_articulo(self, item):
        """
        Busca la ubicación espacial, centra cámara e inicia rastreo RTLS.
        FIX: Blindaje contra argumentos booleanos (AttributeError).
        """
        from PyQt6.QtCore import QPointF, Qt

        from src.db.conexion import obtener_conexion

        # --- VALIDACIÓN QUIRÚRGICA ANTI-CRASH ---
        if isinstance(item, bool) or item is None or not hasattr(item, "data"):
            return

        codigo_ref = item.data(Qt.ItemDataRole.UserRole)
        if not codigo_ref:
            return

        try:
            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT mapa_x, mapa_y FROM ubicaciones WHERE codigo_articulo = %s",
                        (codigo_ref,),
                    )
                    pos = cursor.fetchone()

            if pos:
                x_px, y_px = pos[0], pos[1]
                punto_f = QPointF(x_px, y_px)

                # 1. ENFOQUE DE CÁMARA
                if hasattr(self, "visor_admin"):
                    self.visor_admin.centerOn(punto_f)

                # 2. RADAR VISUAL NEÓN
                color_radar = "#FF5555" if "⚠️" in item.text() else "#00FFC6"
                if hasattr(self.visor_admin, "disparar_radar"):
                    self.visor_admin.disparar_radar(punto_f, color_radar)

                # 3. ACTIVACIÓN DE RASTREO RTLS
                self.rastreo_activo = True
                if hasattr(self, "receptor_rtls"):
                    self.receptor_rtls.fijar_objetivo(codigo_ref)

                # 4. FEEDBACK HUD (Segoe UI Bold)
                if self.window().statusBar():
                    self.window().statusBar().setStyleSheet(
                        f"color: {color_radar}; font-weight: 900; font-family: 'Segoe UI';"
                    )
                    self.window().statusBar().showMessage(
                        f"RASTREANDO EN VIVO: {item.text()}", 3000
                    )
            else:
                if self.window().statusBar():
                    self.window().statusBar().setStyleSheet(
                        "color: #FFB86C; font-weight: 900; font-family: 'Segoe UI';"
                    )
                    self.window().statusBar().showMessage(
                        "⚠️ ERROR: ARTÍCULO SIN COORDENADAS", 4000
                    )

        except Exception as e:
            print(f"❌ Error en enfoque/rastreo: {e}")

    # ============================================================
    # BLOQUE RUTA GPS AVANZADA
    # ============================================================

    def flujo_inicio_ruta_gps(self):
        """
        Orquestador de navegación inteligente con integración de RASTREO EN VIVO.
        ESTÉTICA: Segoe UI Bold, Neón y cursors de manita.
        """
        from PyQt6.QtCore import QPointF, Qt
        from PyQt6.QtWidgets import (
            QDialog,
            QFrame,
            QLabel,
            QLineEdit,
            QMessageBox,
            QPushButton,
            QVBoxLayout,
        )

        from src.db.conexion import obtener_conexion

        dialogo = QDialog(self)
        dialogo.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        dialogo.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialogo.setFixedSize(450, 420)

        cuerpo = QFrame(dialogo)
        cuerpo.setFixedSize(450, 420)
        cuerpo.setStyleSheet(
            "QFrame { background-color: #05070A; border: 2px solid #00FFC6; border-radius: 30px; }"
        )

        layout_base = QVBoxLayout(dialogo)
        layout_base.setContentsMargins(0, 0, 0, 0)
        layout_base.addWidget(cuerpo)

        lyt = QVBoxLayout(cuerpo)
        lyt.setContentsMargins(40, 40, 40, 40)
        lyt.setSpacing(15)

        lbl_head = QLabel(tr("ubic.goto_item_q", default="¿A QUÉ ARTÍCULO DESEA IR?"))
        lbl_head.setStyleSheet(
            "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900; font-size: 15px; border: none; background: transparent;"
        )
        lbl_head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lyt.addWidget(lbl_head)

        search_input = QLineEdit()
        search_input.setPlaceholderText(tr("ubic.goto_item_ph", default="Escriba el código de artículo..."))
        search_input.setStyleSheet(
            """
            QLineEdit { 
                background-color: #161B22; color: white; border: 1px solid #30363D; 
                border-radius: 10px; padding: 15px; font-size: 14px; font-family: 'Segoe UI'; font-weight: 900;
            }
            QLineEdit:focus { border: 1px solid #00FFC6; }
        """
        )

        # Carga de sugerencias
        try:
            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT codigo_articulo FROM ubicaciones WHERE mapa_x != 0"
                    )
                    lista_sugerencias = [row[0] for row in cursor.fetchall()]
                    completer = QCompleter(lista_sugerencias)
                    completer.setFilterMode(Qt.MatchFlag.MatchContains)
                    search_input.setCompleter(completer)
        except:
            pass

        lyt.addWidget(search_input)

        btn_cam = QPushButton(tr("ubic.scan_product", default="ESCANEAR CÓDIGO DE PRODUCTO"))
        btn_cam.setFixedHeight(45)
        btn_cam.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cam.setStyleSheet(
            """
            QPushButton { background-color: transparent; color: #8B949E; border: 1px solid #30363D; border-radius: 10px; font-family: 'Segoe UI'; font-weight: 900; }
            QPushButton:hover { border-color: #00FFC6; color: white; background-color: rgba(0, 255, 198, 0.05); }
        """
        )
        btn_cam.clicked.connect(
            lambda: self.abrir_escaner_camara("BUSCAR ARTÍCULO", "BÚSQUEDA")
        )
        lyt.addWidget(btn_cam)

        lyt.addStretch()

        ya_ubicado = (
            hasattr(self.visor_mapa, "pos_operario")
            and self.visor_mapa.pos_operario is not None
        )
        texto_confirmar = (
            "INICIAR RUTA AHORA" if ya_ubicado else "CONFIRMAR Y LOCALIZARME"
        )

        btn_confirmar = QPushButton(texto_confirmar)
        btn_confirmar.setFixedHeight(50)
        btn_confirmar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_confirmar.setStyleSheet(
            """
            QPushButton { background-color: #238636; color: #0E1117; font-family: 'Segoe UI'; font-weight: 900; border-radius: 12px; font-size: 13px; }
            QPushButton:hover { background-color: #FFFFFF; color: #0E1117; }
        """
        )

        def validar_destino():
            term = search_input.text().strip()
            if not term:
                return

            resultado = self.obtener_coordenadas_articulo(term)
            if resultado:
                nombre_real, coords = resultado
                dialogo.accept()

                # COMPENETRACIÓN: Al iniciar ruta, activamos rastreo igual que en selección manual
                self.rastreo_activo = True
                if hasattr(self, "receptor_rtls"):
                    self.receptor_rtls.fijar_objetivo(term)

                self.coordenadas_destino = QPointF(coords[0], coords[1])
                self.visor_mapa.set_punto_destino(coords[0], coords[1])

                if ya_ubicado:
                    self.procesar_ruta_gps()
                    self.statusBar().setStyleSheet(
                        "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900;"
                    )
                    self.statusBar().showMessage(
                        f"🚀 RUTA GENERADA HACIA {nombre_real}", 4000
                    )
                else:
                    self.statusBar().setStyleSheet(
                        "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900;"
                    )
                    self.statusBar().showMessage(
                        "📍 POR FAVOR, ESCANEE UN QR DE UBICACIÓN PARA EMPEZAR", 6000
                    )
                    self.abrir_escaner_camara(
                        "ESCANEE SU UBICACIÓN ACTUAL", "UBICACION"
                    )
            else:
                # Diálogo de error estilo neón para coherencia
                msg = QMessageBox(dialogo)
                msg.setIcon(QMessageBox.Icon.Critical)
                msg.setWindowTitle(tr("ubic.error_title", default="ERROR"))
                msg.setText(tr("ubic.no_coords_registered", default="El artículo no tiene coordenadas registradas."))
                msg.setStyleSheet(
                    "QMessageBox { background-color: #0A0A0A; border: 1px solid #FF5555; } QLabel { color: white; font-family: 'Segoe UI'; }"
                )
                msg.exec()

        btn_confirmar.clicked.connect(validar_destino)
        lyt.addWidget(btn_confirmar)

        btn_cancel = QPushButton(tr("ubic.cancel", default="CANCELAR"))
        btn_cancel.setFixedHeight(50)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(
            """
            QPushButton { background-color: #30363D; color: #8B949E; font-family: 'Segoe UI'; font-weight: 900; border-radius: 12px; font-size: 13px; border: none; }
            QPushButton:hover { background-color: #484f58; color: white; }
        """
        )
        btn_cancel.clicked.connect(dialogo.reject)
        lyt.addWidget(btn_cancel)

        dialogo.exec()

    def borrar_plano_actual(self):
        """
        Override estable: elimina planos por planta y limpia la interfaz al momento.
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QDialog,
            QFrame,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QVBoxLayout,
        )

        planta_idx = getattr(self, "planta_actual", 0)

        # Fetch plan name and check whether a plan actually exists for this index
        nombre_plano = f"PLANTA {planta_idx}"
        row = None
        try:
            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT COALESCE(tipo,'LOCAL'), titulo_plano, ruta_imagen "
                        "FROM configuracion_mapa WHERE planta_index=%s",
                        (planta_idx,),
                    )
                    row = cursor.fetchone()
        except Exception:
            pass

        # If no plan is loaded, show an informative message instead of the delete dialog
        plano_existe = row is not None and bool(row[2])  # ruta_imagen must be non-empty
        if not plano_existe:
            info = QDialog(self)
            info.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
            info.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            info.setModal(True)
            marco_i = QFrame(info)
            marco_i.setStyleSheet(self._estilo_dialogo_neon("#00FFC6"))
            base_i = QVBoxLayout(info)
            base_i.setContentsMargins(0, 0, 0, 0)
            base_i.addWidget(marco_i)
            lyt_i = QVBoxLayout(marco_i)
            lyt_i.setContentsMargins(28, 24, 28, 24)
            lyt_i.setSpacing(16)
            lbl_t = QLabel("ℹ️  " + tr("ubic.no_plan_loaded", default="SIN PLANO CARGADO"))
            lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_t.setFont(self._crear_fuente_segoe(13))
            lbl_t.setStyleSheet("color: #00FFC6; border: none;")
            lyt_i.addWidget(lbl_t)
            lbl_m = QLabel(
                tr("ubic.no_plan_loaded_msg",
                   default="No hay ningún plano cargado en este momento.\nCarga un plano con el botón CARGAR antes de intentar borrarlo.")
            )
            lbl_m.setWordWrap(True)
            lbl_m.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_m.setFont(self._crear_fuente_segoe(10))
            lbl_m.setStyleSheet("color: #E6EDF3; border: none;")
            lyt_i.addWidget(lbl_m)
            btn_ok = QPushButton(tr("ubic.understood", default="ENTENDIDO"))
            btn_ok.setFont(self._crear_fuente_segoe(10))
            btn_ok.setStyleSheet(
                self._estilo_boton_neon(bg="#00FFC6", fg="#0D1117", border="#00FFC6",
                                        hover_bg="#FFFFFF", hover_fg="#0D1117")
            )
            btn_ok.clicked.connect(info.accept)
            lyt_i.addWidget(btn_ok)
            info.exec()
            return

        if row:
            tipo = (row[0] or "LOCAL").upper()
            titulo = (row[1] or "").strip()
            nombre_plano = f"{tipo}: {titulo}" if titulo else tipo

        dialogo = QDialog(self)
        dialogo.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        dialogo.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialogo.setModal(True)

        marco = QFrame(dialogo)
        marco.setStyleSheet(self._estilo_dialogo_neon("#FF7B72"))
        base = QVBoxLayout(dialogo)
        base.setContentsMargins(0, 0, 0, 0)
        base.addWidget(marco)

        layout = QVBoxLayout(marco)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        lbl_titulo = QLabel(tr("ubic.eliminar_plano", default="🗑️  ELIMINAR PLANO"))
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_titulo.setFont(self._crear_fuente_segoe(13))
        lbl_titulo.setStyleSheet("color: #FF7B72; border: none;")
        layout.addWidget(lbl_titulo)

        lbl_msg = QLabel(
            f'¿Eliminar el plano "{nombre_plano}"?\n\n'
            "Esta acción borrará el plano, los muros técnicos\n"
            "y las matrices de navegación asociados."
        )
        lbl_msg.setWordWrap(True)
        lbl_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_msg.setFont(self._crear_fuente_segoe(10))
        lbl_msg.setStyleSheet("color: #E6EDF3; border: none;")
        layout.addWidget(lbl_msg)

        fila = QHBoxLayout()
        btn_eliminar = QPushButton(tr("ubic.yes_delete", default="SÍ, ELIMINAR"))
        btn_cancelar = QPushButton(tr("ubic.cancel", default="CANCELAR"))
        for boton, estilo in [
            (
                btn_eliminar,
                self._estilo_boton_neon(
                    bg="#FF7B72",
                    fg="#0D1117",
                    border="#FF7B72",
                    hover_bg="#FFFFFF",
                    hover_fg="#0D1117",
                ),
            ),
            (
                btn_cancelar,
                self._estilo_boton_neon(
                    bg="#30363D",
                    fg="#FFFFFF",
                    border="#8B949E",
                    hover_bg="#FFFFFF",
                    hover_fg="#30363D",
                ),
            ),
        ]:
            boton.setCursor(Qt.CursorShape.PointingHandCursor)
            boton.setFont(self._crear_fuente_segoe(10))
            boton.setStyleSheet(estilo)
            fila.addWidget(boton)
        layout.addLayout(fila)

        btn_cancelar.clicked.connect(dialogo.reject)
        btn_eliminar.clicked.connect(dialogo.accept)
        self._aplicar_fuente_segoe(dialogo)
        dialogo.resize(520, 260)

        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM configuracion_mapa WHERE planta_index = %s",
                        (planta_idx,),
                    )
                conn.commit()

            # Navigate to another available plan after deletion
            siguiente_idx = None
            try:
                with obtener_conexion() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT planta_index FROM configuracion_mapa "
                            "WHERE ruta_imagen IS NOT NULL AND ruta_imagen != '' "
                            "ORDER BY planta_index ASC LIMIT 1"
                        )
                        row2 = cursor.fetchone()
                siguiente_idx = int(row2[0]) if row2 else None
            except Exception:
                pass

            self._vaciar_plano_en_visores()
            self._reiniciar_historial_planta(planta_idx)

            if siguiente_idx is not None:
                self.planta_actual = siguiente_idx
                if hasattr(self, "cargar_infraestructura_registrada"):
                    self.cargar_infraestructura_registrada()
                self._actualizar_labels_planta()
                self.mostrar_mensaje_temporal(f'"{nombre_plano}" ELIMINADO')
                self._forzar_reencuadre_diferido(force=True)
            else:
                self.planta_actual = 0
                self._actualizar_labels_planta()
                self.mostrar_mensaje_temporal(tr("ubic.plan_deleted_none", default="PLANO ELIMINADO — NO HAY MÁS PLANOS"))

        except Exception as e:
            print(f"Error al eliminar plano: {e}")

    def obtener_coordenadas_articulo(self, termino):
        """
        Override estable: resuelve articulos y ubicaciones directas, priorizando destinos disponibles.
        """
        opciones = [
            op
            for op in self._obtener_opciones_destino_gps(termino)
            if op.get("disponible")
        ]
        if not opciones:
            return None

        opciones_ordenadas = sorted(
            opciones,
            key=lambda op: (
                op.get("distancia_m") is None,
                (
                    op.get("distancia_m")
                    if op.get("distancia_m") is not None
                    else float("inf")
                ),
                0 if op.get("tipo") == "LINEAL" else 1,
            ),
        )
        mejor = opciones_ordenadas[0]
        nombre = f"{mejor.get('nombre', '').upper()} - {mejor.get('ubicacion', '').upper()}".strip(
            " -"
        )
        return nombre, mejor["coords"]

    def flujo_inicio_ruta_gps(self):
        """
        Override estable: permite buscar por articulo o ubicacion y elegir la ruta de lineal/almacen.
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QDialog,
            QFrame,
            QLabel,
            QLineEdit,
            QPushButton,
            QVBoxLayout,
        )

        dialogo = QDialog(self)
        self._dialogo_ruta_gps_activo = dialogo
        dialogo.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        dialogo.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialogo.setModal(True)

        marco = QFrame(dialogo)
        marco.setStyleSheet(self._estilo_dialogo_neon("#00FFC6"))

        base = QVBoxLayout(dialogo)
        base.setContentsMargins(0, 0, 0, 0)
        base.addWidget(marco)

        lyt = QVBoxLayout(marco)
        lyt.setContentsMargins(34, 34, 34, 34)
        lyt.setSpacing(14)

        lbl_head = QLabel(tr("ubic.goto_item_loc_q", default="¿A QUÉ ARTÍCULO O UBICACIÓN DESEA IR?"))
        lbl_head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_head.setFont(self._crear_fuente_segoe(12))
        lbl_head.setStyleSheet("color: #00FFC6; border: none;")
        lyt.addWidget(lbl_head)

        lbl_info = QLabel(
            tr("ubic.introduzca_codigo_nombre_o_u", default="Introduzca codigo, nombre o ubicacion. Si el articulo existe en lineal y almacen, el sistema mostrara ambas opciones con su distancia real.")
        )
        lbl_info.setWordWrap(True)
        lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_info.setFont(self._crear_fuente_segoe(9))
        lbl_info.setStyleSheet("color: #C9D1D9; border: none;")
        lyt.addWidget(lbl_info)

        search_input = QLineEdit()
        search_input.setPlaceholderText(
            tr("ubic.codigo_nombre_o_ubicacion_ej", default="Codigo, nombre o ubicacion (ej: PASILLO BEBIDAS 09)")
        )
        search_input.setFont(self._crear_fuente_segoe(10))
        search_input.setStyleSheet(
            """
            QLineEdit {
                background-color: #161B22;
                color: #FFFFFF;
                border: 1px solid #00FFC6;
                border-radius: 10px;
                padding: 14px;
                font-family: 'Segoe UI';
                font-weight: 900;
            }
            QLineEdit:focus {
                border: 1px solid #FFFFFF;
            }
            """
        )
        lyt.addWidget(search_input)

        try:
            sugerencias = []
            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT codigo FROM articulos WHERE codigo IS NOT NULL AND codigo != ''
                        UNION
                        SELECT nombre FROM articulos WHERE nombre IS NOT NULL AND nombre != ''
                        UNION
                        SELECT CONCAT_WS(' ', pasillo, estanteria, balda) FROM ubicaciones
                        WHERE pasillo IS NOT NULL AND pasillo != ''
                        """
                    )
                    sugerencias = [
                        str(row[0]).upper()
                        for row in cursor.fetchall()
                        if row and row[0]
                    ]
            if sugerencias:
                completer = QCompleter(sorted(set(sugerencias)))
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
                search_input.setCompleter(completer)
        except Exception:
            pass

        btn_scan = QPushButton("📷 " + tr("ubic.scan_btn", default="SCAN"))
        btn_scan.setObjectName("btn_secundario")
        btn_scan.setFixedSize(110, 50)
        btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self._input_gps_dialog_activo = search_input
        btn_scan.clicked.connect(
            lambda: self.abrir_escaner_camara("BUSCAR ARTICULO", "BUSQUEDA")
        )
        lyt.addWidget(btn_scan)

        ya_ubicado = (
            getattr(getattr(self, "visor_mapa", None), "pos_operario", None) is not None
        )
        texto_confirmar = (
            "INICIAR RUTA AHORA" if ya_ubicado else "CONFIRMAR Y LOCALIZARME"
        )

        def validar_destino():
            termino = search_input.text().strip()
            if not termino:
                return

            opciones = self._obtener_opciones_destino_gps(termino)
            disponibles = [op for op in opciones if op.get("disponible")]
            if not disponibles:
                self.mostrar_mensaje_temporal(tr("ubic.dest_no_coords", default="DESTINO SIN COORDENADAS O NO ENCONTRADO"))
                return

            seleccion = self._mostrar_selector_destino_gps(disponibles)
            if not seleccion:
                return

            self.destino_gps_activo = seleccion
            self.coordenadas_destino = seleccion["coords"]
            if hasattr(self, "visor_mapa") and self.visor_mapa:
                self.visor_mapa.set_punto_destino(
                    seleccion["coords"].x(), seleccion["coords"].y()
                )

            self._actualizar_piloto_rastreo(True, seleccion.get("ubicacion"))
            dialogo.accept()

            nombre_destino = f"{seleccion.get('nombre', '')} - {seleccion.get('tipo', '')} - {seleccion.get('ubicacion', '')}".strip(
                " -"
            )
            if ya_ubicado:
                self.procesar_ruta_gps()
                self.statusBar().setStyleSheet(
                    "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900;"
                )
                self.statusBar().showMessage(
                    f"RUTA GENERADA HACIA {nombre_destino}", 5000
                )
            else:
                self.statusBar().setStyleSheet(
                    "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900;"
                )
                self.statusBar().showMessage(
                    "ESCANEE UN QR DE UBICACION PARA INICIAR LA NAVEGACION", 6000
                )
                self.abrir_escaner_camara("ESCANEE SU UBICACION ACTUAL", "UBICACION")

        btn_confirmar = QPushButton(texto_confirmar)
        btn_confirmar.setFixedHeight(50)
        btn_confirmar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_confirmar.setFont(self._crear_fuente_segoe(10))
        btn_confirmar.setStyleSheet(
            self._estilo_boton_neon(
                bg="#238636",
                fg="#0E1117",
                border="#238636",
                hover_bg="#FFFFFF",
                hover_fg="#0E1117",
                radius=12,
                padding="12px 18px",
                font_size=13,
            )
        )
        btn_confirmar.clicked.connect(validar_destino)
        search_input.returnPressed.connect(validar_destino)
        lyt.addWidget(btn_confirmar)

        btn_cancel = QPushButton(tr("ubic.cancel", default="CANCELAR"))
        btn_cancel.setFixedHeight(50)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setFont(self._crear_fuente_segoe(10))
        btn_cancel.setStyleSheet(
            self._estilo_boton_neon(
                bg="#4B5563",
                fg="#FFFFFF",
                border="#6B7280",
                hover_bg="#FFFFFF",
                hover_fg="#4B5563",
                radius=12,
                padding="12px 18px",
                font_size=13,
            )
        )
        btn_cancel.clicked.connect(dialogo.reject)
        lyt.addWidget(btn_cancel)

        self._aplicar_fuente_segoe(dialogo)
        dialogo.resize(500, 360)
        try:
            dialogo.exec()
        finally:
            if getattr(self, "_input_gps_dialog_activo", None) is search_input:
                self._input_gps_dialog_activo = None
            if getattr(self, "_dialogo_ruta_gps_activo", None) is dialogo:
                self._dialogo_ruta_gps_activo = None

    # ============================================================
    # BLOQUE MENÚ Y ESTADO
    # ============================================================

    def actualizar_estado_menu(self, boton_activo):
        """
        Gestiona la estética 'Dark Mode' del menú lateral.
        Solo el botón pulsado brilla en turquesa con borde izquierdo activo.
        """
        from PyQt6.QtCore import Qt

        # Lista exhaustiva de botones de navegación lateral
        botones = [
            getattr(self, "btn_recepcion", None),
            getattr(self, "btn_salida", None),
            getattr(self, "btn_busqueda", None),
            getattr(self, "btn_nav_gps", None),
            getattr(self, "btn_admin_mapa", None),
        ]

        estilo_activo = """
            QPushButton {
                background-color: #1F2937; 
                border-left: 5px solid #00FFC6; 
                color: #00FFC6; 
                text-align: left; 
                padding-left: 15px;
                font-family: 'Segoe UI';
                font-weight: 900;
                font-size: 12px;
            }
        """
        estilo_inactivo = """
            QPushButton {
                background-color: transparent; 
                border-left: 5px solid transparent; 
                color: #8B949E; 
                text-align: left; 
                padding-left: 15px;
                font-family: 'Segoe UI';
                font-weight: 900;
                font-size: 12px;
            }
            QPushButton:hover { 
                background-color: #161B22; 
                color: white; 
            }
        """

        for btn in botones:
            if btn:
                # Aplicamos estilo y cursor interactivo
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                if btn == boton_activo:
                    btn.setStyleSheet(estilo_activo)
                    # Bloqueamos señales temporalmente para evitar loops de refresco
                    btn.blockSignals(True)
                    btn.setChecked(True)
                    btn.blockSignals(False)
                else:
                    btn.setStyleSheet(estilo_inactivo)
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)

    # ============================================================
    # BLOQUE EXPORTACIONES PDF
    # ============================================================

    def exportar_maestro_ubicaciones_pdf(self):
        """
        Genera un reporte PDF técnico con la auditoría completa de coordenadas.
        Estilo 'Blueprint Industrial' con tipografía limpia y colores corporativos.
        """
        import os
        from datetime import datetime

        from PyQt6.QtWidgets import QMessageBox

        from src.db.conexion import obtener_conexion

        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.platypus import (
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )

            # 1. GESTIÓN DE RUTAS Y ARCHIVO
            ruta_base = os.path.join(
                os.path.expanduser("~"), "Documents", "Reportes_GPS"
            )
            if not os.path.exists(ruta_base):
                os.makedirs(ruta_base)

            nombre_archivo = (
                f"Maestro_Ubicaciones_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
            )
            dest_path = os.path.join(ruta_base, nombre_archivo)

            doc = SimpleDocTemplate(
                dest_path,
                pagesize=A4,
                rightMargin=30,
                leftMargin=30,
                topMargin=30,
                bottomMargin=18,
            )
            elementos = []
            estilos = getSampleStyleSheet()

            # 2. CABECERA ESTILO BLUEPRINT
            estilo_titulo = ParagraphStyle(
                "BlueprintTitle",
                parent=estilos["Title"],
                fontSize=18,
                textColor=colors.HexColor("#1A1D23"),
                fontName="Helvetica-Bold",
                spaceAfter=20,
            )

            titulo = Paragraph("REPORTE MAESTRO DE POSICIONAMIENTO", estilo_titulo)
            subtitulo = Paragraph(
                f"Auditoría de Coordenadas - Generado el: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                estilos["Normal"],
            )

            elementos.append(titulo)
            elementos.append(subtitulo)
            elementos.append(Spacer(1, 20))

            # 3. EXTRACCIÓN DE DATOS (Artículos con GPS)
            datos_tabla = [
                ["ID", "PRODUCTO", "CÓDIGO EPC", "EJE X (px)", "EJE Y (px)", "ESTADO"]
            ]

            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    # Buscamos artículos que tengan coordenadas asignadas
                    sql = """
                        SELECT codigo, nombre, mapa_x, mapa_y 
                        FROM articulos 
                        WHERE mapa_x IS NOT NULL 
                        ORDER BY nombre ASC
                    """
                    cursor.execute(sql)
                    rows = cursor.fetchall()

                    if not rows:
                        QMessageBox.warning(
                            self,
                            "AVISO",
                            "No hay artículos con coordenadas mapeadas para exportar.",
                        )
                        return

                    for i, f in enumerate(rows):
                        datos_tabla.append(
                            [
                                str(i + 1),
                                str(f[1])[
                                    :30
                                ].upper(),  # Nombre truncado para evitar desbordamiento
                                str(f[0]),
                                f"{float(f[2]):.1f}",
                                f"{float(f[3]):.1f}",
                                "MAPEADO",
                            ]
                        )

            # 4. DISEÑO DE TABLA 'INDUSTRIAL DARK'
            # Ancho de columnas optimizado para A4
            tabla = Table(datos_tabla, colWidths=[30, 190, 110, 60, 60, 70])

            estilo_tabla = TableStyle(
                [
                    # Encabezado
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A1D23")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#00FFC6")),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
                    # Cuerpo de tabla
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.whitesmoke, colors.white],
                    ),
                    ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#374151")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )

            tabla.setStyle(estilo_tabla)
            elementos.append(tabla)

            # 5. GENERACIÓN Y APERTURA
            doc.build(elementos)

            QMessageBox.information(
                self,
                "EXPORTACIÓN EXITOSA",
                f"Documento generado correctamente:\n{nombre_archivo}\n\nUbicación: Reportes_GPS",
            )

            # Abrir la carpeta contenedora automáticamente
            if os.name == "nt":  # Windows
                os.startfile(ruta_base)

        except Exception as e:
            print(f"Error en PDF: {e}")
            QMessageBox.critical(
                self, "ERROR CRÍTICO", f"No se pudo generar el reporte: {str(e)}"
            )

    def mostrar_mensaje_exito_final(self, qr, pas, est):
        """Ventana minimalista de confirmación final."""
        msg = QDialog(self)
        msg.setFixedSize(320, 200)
        msg.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        msg.setStyleSheet(
            "QDialog { background-color: #0D1117; border: 2px solid #238636; border-radius: 15px; }"
        )

        l = QVBoxLayout(msg)
        t1 = QLabel(tr("ubic.node_linked", default="NODO VINCULADO"))
        t1.setStyleSheet("color: #238636; font-weight: 900; font-size: 14px;")
        t1.setAlignment(Qt.AlignmentFlag.AlignCenter)

        t2 = QLabel(f"QR: {qr}\nUbicación: {pas} | {est}")
        t2.setStyleSheet("color: white; font-size: 11px;")
        t2.setAlignment(Qt.AlignmentFlag.AlignCenter)

        b = QPushButton(tr("common.close", default="CERRAR"))
        b.setStyleSheet(
            "background: #161B22; color: white; border: 1px solid #30363D; padding: 8px; border-radius: 5px;"
        )
        b.clicked.connect(msg.accept)

        l.addWidget(t1)
        l.addWidget(t2)
        l.addWidget(b)
        msg.exec()

    def _mostrar_feedback_pdf(self, archivo, ruta, cantidad):
        """Ventana modal personalizada con estética Dark."""
        msg = QMessageBox(self)
        msg.setWindowTitle(tr("ubic.labeling_system", default="SISTEMA DE ETIQUETADO"))
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("<b>" + tr("ubic.pdf_ok", default="PDF GENERADO CON ÉXITO") + "</b>")
        msg.setInformativeText(
            tr("ubic.labels_processed",
               default="Se han procesado {cantidad} etiquetas.<br><br>icono <b>Archivo:</b> {archivo}<br>icono <b>Carpeta:</b> {ruta}",
               cantidad=cantidad, archivo=archivo, ruta=ruta)
        )
        btn_abrir = msg.addButton(
            "icono " + tr("ubic.open_folder", default="Abrir Carpeta"), QMessageBox.ButtonRole.AcceptRole
        )
        msg.addButton(tr("common.close", default="Cerrar"), QMessageBox.ButtonRole.RejectRole)

        msg.setStyleSheet(
            """
            QMessageBox { background-color: #0D1117; border: 1px solid #00FFC6; }
            QLabel { color: white; }
            QPushButton { 
                background-color: #1C2128; color: #00FFC6; border: 1px solid #30363D; 
                border-radius: 5px; padding: 8px; min-width: 100px; font-family: 'Segoe UI'; font-weight: 900;
            }
            QPushButton:hover { background-color: #FFFFFF; color: #0D1117; border-color: #FFFFFF; }
        """
        )
        msg.exec()
        if msg.clickedButton() == btn_abrir:
            os.startfile(ruta)

    # ============================================================
    # BLOQUE CALIBRACIÓN DE ESCALA
    # ============================================================

    def iniciar_calibracion_escala(self):
        """
        Inicia el flujo guiado de telemetría dual.
        Mantiene la lógica original intacta. Solo actualiza el estilo de botones y textos.
        AJUSTE QUIRÚRGICO: Accesos seguros a la escena y al viewport.
        """
        if not hasattr(self, "visor_admin") or not self.visor_admin:
            return

        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont  # <--- Para blindar la fuente
        from PyQt6.QtWidgets import (
            QDialog,
            QFrame,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QVBoxLayout,
        )

        # --- CONFIGURACIÓN DE LA VENTANA ---
        diag_init = QDialog(self)
        diag_init.setFixedSize(440, 280)
        diag_init.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
        )
        diag_init.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # FUENTES BLINDADAS (Segoe UI Bold / Black)
        f_tit = QFont("Segoe UI", 16, QFont.Weight.Black)
        f_msg = QFont("Segoe UI", 11, QFont.Weight.Bold)
        f_btn = QFont("Segoe UI", 10, QFont.Weight.Bold)

        estilo_redondeado = """
            QFrame#MainContainer {
                background-color: #0D1117;
                border: 2px solid #00F0FF;
                border-radius: 20px;
            }
            QLabel { color: #E6EDF3; border: none; }
            
            /* Botón Principal (Verde) */
            QPushButton#btnIniciar {
                background-color: #238636;
                color: #0E1117;
                border-radius: 10px;
                padding: 10px;
                border: none;
                min-width: 120px;
            }
            QPushButton#btnIniciar:hover { background-color: #FFFFFF; color: #0E1117; }
            
            /* Botón Cancelar (Gris Claro) */
            QPushButton#btnCancelar { 
                background-color: #30363D; 
                color: #E6EDF3; 
                border-radius: 10px; 
                padding: 10px; 
                border: 1px solid #484F58; 
                min-width: 120px;
            }
            QPushButton#btnCancelar:hover { background-color: #484F58; }
        """

        main_lyt = QVBoxLayout(diag_init)
        container = QFrame()
        container.setObjectName("MainContainer")
        container.setStyleSheet(estilo_redondeado)

        inner_lyt = QVBoxLayout(container)
        inner_lyt.setContentsMargins(35, 30, 35, 30)
        inner_lyt.setSpacing(15)

        titulo = QLabel("📐 " + tr("ubic.calib_mode_title", default="MODO CALIBRACIÓN"))
        titulo.setFont(f_tit)  # Inyección directa
        titulo.setStyleSheet("color: #00F0FF; letter-spacing: 1.2px;")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Actualización de estilo: color azul turquesa para "pared VERTICAL"
        msg = QLabel(
            tr("ubic.calib_mode_msg",
               default="Se va a iniciar el sistema de telemetría.<br><br><b style='color: white;'>PASO 1:</b> Seleccione una <b style='color: #00F0FF;'>pared VERTICAL</b> del mapa haciendo clic en sus extremos (Inicio y Fin).")
        )
        msg.setFont(f_msg)  # Inyección directa
        msg.setStyleSheet("color: #BDC6CF;")
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # --- CONTENEDOR DE BOTONES ---
        btn_lyt = QHBoxLayout()
        btn_lyt.setSpacing(10)

        btn_cancelar = QPushButton(tr("ubic.cancel", default="CANCELAR"))
        btn_cancelar.setObjectName("btnCancelar")
        btn_cancelar.setFont(f_btn)
        btn_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancelar.clicked.connect(diag_init.reject)

        btn_cont = QPushButton(tr("ubic.start_protocol", default="INICIAR PROTOCOLO"))
        btn_cont.setObjectName("btnIniciar")
        btn_cont.setFont(f_btn)  # Inyección directa
        btn_cont.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cont.clicked.connect(diag_init.accept)

        btn_lyt.addWidget(btn_cancelar)
        btn_lyt.addWidget(btn_cont)

        inner_lyt.addWidget(titulo)
        inner_lyt.addWidget(msg)
        inner_lyt.addStretch()
        inner_lyt.addLayout(btn_lyt)

        main_lyt.addWidget(container)

        if diag_init.exec() != QDialog.DialogCode.Accepted:
            return

        # --- ACTIVACIÓN DE SESIÓN (NUEVO PARA CONTROL DE GUÍA) ---
        self.calibracion_en_curso_activa = True
        self._snapshot_pre_calibracion = self._obtener_snapshot_mapa()

        # --- LÓGICA ORIGINAL (SIN CAMBIOS) ---
        self.paso_calibracion = 1
        self.modo_calibrar = True
        self.esperando_ancla_0 = False

        self.p_y_inicio = self.p_y_fin = None
        self.p_x_inicio = self.p_x_fin = None

        self.actualizar_estado_bloqueo(bloquear=True)
        self.visor_admin.modo_calibrar = True
        self.visor_admin.modo_pintar = False

        if hasattr(self.visor_admin, "configurar_modo"):
            self.visor_admin.configurar_modo("CALIBRAR")
        else:
            self.visor_admin.setCursor(Qt.CursorShape.CrossCursor)

        if hasattr(self, "limpiar_indicadores_calib"):
            self.limpiar_indicadores_calib()

        # --- AJUSTE QUIRÚRGICO 1: Limpieza segura de la línea temporal ---
        if (
            hasattr(self.visor_admin, "linea_temporal_muro")
            and self.visor_admin.linea_temporal_muro
        ):
            try:
                # Extraemos la escena de forma segura
                escena = QGraphicsView.scene(self.visor_admin)

                # Verificamos que la línea pertenece a una escena antes de removerla
                item_escena = self.visor_admin.linea_temporal_muro.scene()

                if escena and item_escena == escena:
                    escena.removeItem(self.visor_admin.linea_temporal_muro)
            except Exception:
                pass
            finally:
                self.visor_admin.linea_temporal_muro = None

        if hasattr(self, "btn_modo_pintar"):
            self.btn_modo_pintar.setChecked(False)
            self.btn_modo_pintar.setText("🖌️ " + tr("ubic.paint_off", default="MODO PINTADO: OFF"))

        if hasattr(self, "btn_escala"):
            self.btn_escala.setText("⚠️ " + tr("ubic.calibrating", default="CALIBRANDO..."))
            self.btn_escala.setStyleSheet(
                "QPushButton { background-color: #FF7700; color: white; border-radius: 8px; "
                "font-family: 'Segoe UI'; font-weight: 900; font-size: 12px; padding: 8px; }"
            )

        status_bar = self.window().statusBar()
        if status_bar:
            status_bar.setStyleSheet(
                "QStatusBar { background-color: #F85149; color: white; font-family: 'Segoe UI'; "
                "font-weight: 900; font-size: 11px; }"
            )
            status_bar.showMessage(
                "📏 PASO [1/3]: Defina la longitud VERTICAL. Haga clic en el PUNTO INICIAL.",
                0,
            )

        # --- AJUSTE QUIRÚRGICO 2: Refresco de Viewport seguro ---
        try:
            v_port = (
                self.visor_admin.viewport()
                if callable(self.visor_admin.viewport)
                else self.visor_admin.viewport
            )
            if v_port:
                v_port.update()
        except Exception:
            pass

    # ============================================================
    # BLOQUE GESTIÓN DE MUROS
    # ============================================================

    def gestionar_deshacer_muro(self):
        """
        Elimina la ÚLTIMA acción (LIFO) con reconstrucción de matriz en caliente.
        Sincroniza el historial y regenera la matriz de ocupación para coherencia visual.
        AJUSTE QUIRÚRGICO: Corrección de crash por acceso a Scene y optimización de memoria.
        """
        if not hasattr(self, "visor_admin") or not self.visor_admin:
            return

        from PyQt6.QtCore import QPointF
        from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsPathItem

        visor = self.visor_admin

        # --- INCISIÓN QUIRÚRGICA: Acceso seguro a la escena (Fix TypeError) ---
        escena = QGraphicsView.scene(visor)
        if not escena:
            return

        # 1. SINCRONIZACIÓN DINÁMICA DEL HISTORIAL
        if not hasattr(visor, "historial_muros"):
            visor.historial_muros = []

        # Recuperación de muros si el historial se perdió
        if not visor.historial_muros:
            items_vivos = escena.items()
            muros_vivos = [
                item for item in items_vivos if item.data(0) == "MURO_TECNICO"
            ]
            muros_vivos.sort(key=lambda x: x.zValue())
            visor.historial_muros = muros_vivos

        # --- PRIORIDAD 1: CANCELAR DIBUJO ACTIVO ---
        if hasattr(visor, "linea_temporal_muro") and visor.linea_temporal_muro:
            try:
                # Verificación de escena del item de forma segura
                item_scene = (
                    visor.linea_temporal_muro.scene()
                )
                if item_scene == escena:
                    escena.removeItem(visor.linea_temporal_muro)
            except Exception:
                pass
            visor.linea_temporal_muro = None
            visor.punto_inicio_muro = None
            if hasattr(self, "mostrar_mensaje_temporal"):
                self.mostrar_mensaje_temporal(tr("ubic.stroke_cancelled", default="TRAZO CANCELADO"))
            return

        # --- PRIORIDAD 2: DESHACER MURO CONFIRMADO (LIFO) ---
        if visor.historial_muros:
            ultimo_muro = visor.historial_muros.pop()
            muro_eliminado = False

            try:
                item_scene = ultimo_muro.scene()
                if ultimo_muro and item_scene == escena:
                    escena.removeItem(ultimo_muro)
                    muro_eliminado = True
                    self.cambios_sin_guardar = True
            except (RuntimeError, Exception):
                pass

            # RECONSTRUCCIÓN SÍNCRONA DE LA MATRIZ A*
            if muro_eliminado and hasattr(visor, "matriz_obstaculos"):
                if visor.matriz_obstaculos is not None:
                    visor.matriz_obstaculos.fill(0)  # Reset total

                # Re-rasterizar los muros persistentes
                for item in visor.historial_muros:
                    try:
                        item_scene = item.scene()
                        if not item or item_scene != escena:
                            continue

                        if isinstance(item, QGraphicsLineItem):
                            visor.marcar_muro_en_matriz(
                                item.line().p1(), item.line().p2(), es_muro_preciso=True
                            )
                        elif isinstance(item, QGraphicsPathItem):
                            path = item.path()
                            for i in range(path.elementCount() - 1):
                                el1 = path.elementAt(i)
                                el2 = path.elementAt(i + 1)
                                visor.marcar_muro_en_matriz(
                                    QPointF(el1.x, el1.y),
                                    QPointF(el2.x, el2.y),
                                    es_muro_preciso=True,
                                )
                    except Exception as e:
                        print(f"⚠️ Error al re-mapear matriz: {e}")

                # Refrescar mapa de calor si es visible
                if hasattr(visor, "actualizar_mapa_calor"):
                    visor.actualizar_mapa_calor()

            if hasattr(self, "mostrar_mensaje_temporal"):
                self.mostrar_mensaje_temporal(tr("ubic.undone_wall", default="DESHECHO: MURO ELIMINADO"))

            # Refresco de los viewports
            for v in [visor, getattr(self, "visor_mapa", None)]:
                if v and v.viewport():
                    v.viewport().update()
            return

        # --- PRIORIDAD 3: ELIMINAR ANCLA/ORIGEN ---
        if hasattr(visor, "item_ancla") and visor.item_ancla:
            for attr in ["item_texto_ancla", "item_ancla"]:
                item = getattr(visor, attr, None)
                if item:
                    item_scene = item.scene()
                    if item_scene == escena:
                        escena.removeItem(item)
                    setattr(visor, attr, None)
            visor.punto_ancla = None
            self.cambios_sin_guardar = True
            if visor.viewport():
                visor.viewport().update()
            return

        if hasattr(self, "mostrar_mensaje_temporal"):
            self.mostrar_mensaje_temporal(tr("ubic.history_empty", default="HISTORIAL VACÍO"))

    def finalizar_calibracion_escala(self, pixeles_x, pixeles_y):
        """
        Orquesta la fase de recolección de métricas.
        Calcula ratios px/m y deja el sistema en estado de ESPERA
        para la ubicación del punto de origen (0,0).
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QDialog,
            QFrame,
            QLabel,
            QLineEdit,
            QPushButton,
            QVBoxLayout,
        )

        # Estilo base actualizado: Segoe UI Bold (700) y Black (900)
        estilo_base = """
            QFrame#MainContainer {{
                background-color: #0D1117;
                border: 2px solid {color_borde};
                border-radius: 20px;
            }}
            QLabel {{ 
                color: #E6EDF3; 
                font-family: 'Segoe UI'; 
                font-weight: 900;
                font-size: 14px; 
                border: none; 
                background: transparent;
            }}
            QLineEdit {{
                background-color: #161B22;
                color: {color_borde};
                border: 1px solid #30363D;
                border-radius: 8px;
                padding: 10px;
                font-family: 'Segoe UI';
                font-size: 18px;
                font-weight: 900;
            }}
            QPushButton#btnConfirmar {{
                background-color: #21262D;
                color: white;
                border: 1px solid #30363D;
                border-radius: 10px;
                font-family: 'Segoe UI';
                font-weight: 900;
                font-size: 12px;
                padding: 12px;
                min-width: 180px;
            }}
            QPushButton#btnConfirmar:hover {{ 
                background-color: {color_borde}; 
                color: #0D1117; 
            }}
        """

        def crear_dialogo(titulo, cuerpo, color_borde="#30363D", es_input=False, texto_btn="✅ CONFIRMAR Y SEGUIR", alto=300):
            diag = QDialog(self)
            diag.setFixedSize(440, alto)
            diag.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
            )
            diag.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

            main_layout = QVBoxLayout(diag)
            main_layout.setContentsMargins(0, 0, 0, 0)

            container = QFrame()
            container.setObjectName("MainContainer")
            container.setStyleSheet(estilo_base.format(color_borde=color_borde))

            lyt = QVBoxLayout(container)
            lyt.setContentsMargins(35, 30, 35, 30)
            lyt.setSpacing(15)

            lbl_tit = QLabel(titulo.upper())
            lbl_tit.setStyleSheet(
                f"color: {color_borde}; font-weight: 900; font-size: 15px; letter-spacing: 1.2px;"
            )
            lbl_tit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lyt.addWidget(lbl_tit)

            input_m = None
            if es_input:
                lbl_cuerpo = QLabel()
                lbl_cuerpo.setTextFormat(Qt.TextFormat.RichText)
                lbl_cuerpo.setText(f"<div style='text-align: center;'>{cuerpo}</div>")
                lbl_cuerpo.setStyleSheet(
                    "color: #8B949E; font-weight: 900; font-size: 13px;"
                )
                lbl_cuerpo.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl_cuerpo.setWordWrap(True)
                lyt.addWidget(lbl_cuerpo)

                input_m = QLineEdit("5.0")
                input_m.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lyt.addWidget(input_m)
            else:
                lbl_cuerpo = QLabel()
                lbl_cuerpo.setTextFormat(Qt.TextFormat.RichText)
                lbl_cuerpo.setText(
                    f"<div style='font-family: Segoe UI; font-weight: 900; text-align: center;'>{cuerpo}</div>"
                )
                lbl_cuerpo.setStyleSheet(
                    "color: #E6EDF3; font-size: 13px; background: transparent;"
                )
                lbl_cuerpo.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl_cuerpo.setWordWrap(True)
                lyt.addWidget(lbl_cuerpo)

            lyt.addStretch()

            btn = QPushButton(texto_btn)
            btn.setObjectName("btnConfirmar")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(diag.accept)
            lyt.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

            main_layout.addWidget(container)
            return diag, input_m

        # --- FASE 1: EJE VERTICAL (CIAN) ---
        cuerpo_v = "Introduzca la distancia real (metros) entre los puntos marcados en la <b style='color: #00F0FF;'>pared VERTICAL</b>:"
        d_y, in_y = crear_dialogo(
            "↕️ CALIBRACIÓN: EJE VERTICAL",
            cuerpo_v,
            "#00F0FF",
            True,
        )
        if d_y.exec() == QDialog.DialogCode.Accepted:
            try:
                val_y = float(in_y.text().replace(",", "."))
                self.visor_admin.ratio_px_m_v = pixeles_y / val_y
            except (ValueError, ZeroDivisionError):
                self.visor_admin.ratio_px_m_v = pixeles_y / 5.0
        else:
            self.cancelar_calibracion()
            return

        # --- FASE 2: EJE HORIZONTAL (AMARILLO) ---
        cuerpo_h = "Introduzca la distancia real (metros) entre los puntos marcados en la <b style='color: #FFEA00;'>pared HORIZONTAL</b>:"
        d_x, in_x = crear_dialogo(
            "↔️ CALIBRACIÓN: EJE HORIZONTAL",
            cuerpo_h,
            "#FFEA00",
            True,
        )
        if d_x.exec() == QDialog.DialogCode.Accepted:
            try:
                val_x = float(in_x.text().replace(",", "."))
                self.visor_admin.ratio_px_m_h = pixeles_x / val_x
            except (ValueError, ZeroDivisionError):
                self.visor_admin.ratio_px_m_h = pixeles_x / 5.0
        else:
            self.cancelar_calibracion()
            return

        # --- FASE 3: ÉXITO + RESUMEN TÉCNICO ---
        r_h = round(self.visor_admin.ratio_px_m_h, 2)
        r_v = round(self.visor_admin.ratio_px_m_v, 2)

        cuerpo_final = (
            f"<div style='line-height: 160%;'>"
            f"<b style='color: #00FFC6;'>MÉTRICAS CALCULADAS:</b><br>"
            f"<span style='color: #8B949E;'>Horizontal:</span> <b style='color: #FFEA00;'>{r_h} px/m</b><br>"
            f"<span style='color: #8B949E;'>Vertical:</span> <b style='color: #00F0FF;'>{r_v} px/m</b>"
            f"</div>"
        )

        d_final, _ = crear_dialogo(
            "📏 CALIBRACIÓN CALCULADA", cuerpo_final, "#FFB86C",
            texto_btn="ENTENDIDO", alto=220,
        )
        d_final.exec()

        # Instrucción de origen: diálogo aparte tras cerrar el resumen
        cuerpo_origen = (
            "Ahora debe establecer el <b style='color: #FFB86C;'>PUNTO DE ORIGEN (0,0)</b>.<br><br>"
            "Para establecer el punto de origen, haga clic en la "
            "<b style='color: white;'>puerta de entrada</b> del plano."
        )
        d_origen, _ = crear_dialogo(
            "📍 PUNTO DE ORIGEN", cuerpo_origen, "#FFB86C",
            texto_btn="ENTENDIDO", alto=220,
        )
        d_origen.exec()

        # --- FASE 4: ESTADO DE ESPERA (ANCLAJE) ---
        self.visor_admin.esperando_ancla_0 = True

        if hasattr(self.visor_admin, "configurar_modo"):
            self.visor_admin.configurar_modo("CALIBRAR")

        if self.window().statusBar():
            self.window().statusBar().setStyleSheet(
                "QStatusBar { background-color: #0D1117; color: #FFB86C; "
                "font-family: 'Segoe UI'; font-weight: 900; font-size: 12px; border-top: 1px solid #FFB86C; }"
            )
            self.window().statusBar().showMessage(
                "📍 MODO ANCLAJE: Haga clic para situar el origen (0,0)", 0
            )

        self.window().cambios_sin_guardar = True

        # --- LÓGICA DE INVISIBILIDAD AL INICIAR MODO PINTADO ---
        if hasattr(self, "btn_modo_pintar"):

            def ocultar_calibracion_al_pintar():
                # Forzamos procesado de eventos para evitar clics fantasma
                from PyQt6.QtWidgets import QApplication

                QApplication.processEvents()

                elementos = ["linea_x", "linea_y", "m_x1", "m_x2", "m_y1", "m_y2"]
                if not hasattr(self, "visor_admin") or self.visor_admin is None:
                    return

                for attr in elementos:
                    item = getattr(self.visor_admin, attr, None)
                    if item:
                        try:
                            # Blindaje contra objetos eliminados en C++ tras cambio de pestaña
                            # AJUSTE QUIRÚRGICO: Acceso seguro a la escena del item
                            if hasattr(item, "scene"):
                                escena_item = item.scene()
                                if escena_item:
                                    item.setVisible(False)
                        except (RuntimeError, AttributeError):
                            # Si el objeto ya no existe, limpiamos la referencia
                            setattr(self.visor_admin, attr, None)

            # --- AJUSTE QUIRÚRGICO: DESCONEXIÓN TOTAL ---
            try:
                # Limpiamos conexiones previas para evitar acumulación de funciones zombis
                self.btn_modo_pintar.clicked.disconnect()
            except:
                pass

            # Reconectamos la lógica base del modo pintado
            if hasattr(self, "alternar_modo_pintado"):
                self.btn_modo_pintar.clicked.connect(self.alternar_modo_pintado)

            # Conectamos el blindaje de invisibilidad
            self.btn_modo_pintar.clicked.connect(ocultar_calibracion_al_pintar)

    def mostrar_guia_muros(self, main_window=None):
        """
        Lanza el mensaje guía profesional para la fase de muros.
        Solo se muestra una vez por sesión tras completar la calibración con éxito
        y de forma manual (no durante la carga de base de datos).
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import QDialog, QFrame, QLabel, QPushButton, QVBoxLayout

        # Determinamos la ventana padre de forma segura
        target_win = main_window if main_window else self

        # --- 1. FILTRO DE SEGURIDAD (Capa Anti-Disparo Prematuro) ---
        # Si no hay ratios calculados, es que no hemos terminado la calibración.
        r_h = getattr(target_win.visor_admin, "ratio_px_m_h", None)
        r_v = getattr(target_win.visor_admin, "ratio_px_m_v", None)

        if not r_h or not r_v or r_h <= 0:
            return

        # Solo permitimos que salte si venimos de un proceso de calibración activo
        # Esto bloquea el mensaje cuando el módulo se acaba de abrir y carga la DB
        if not getattr(target_win, "calibracion_en_curso_activa", False):
            return

        # Si ya se mostró en esta sesión, ignoramos la llamada
        if getattr(target_win, "onboarding_muros_visto", False):
            return

        # --- 2. CONFIGURACIÓN DEL DIÁLOGO ---
        diag = QDialog(target_win)
        diag.setFixedSize(460, 320)
        diag.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        diag.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Contenedor con estética Dark High-Tech
        container = QFrame()
        container.setObjectName("OnboardingContainer")
        container.setStyleSheet(
            """
            QFrame#OnboardingContainer {
                background-color: #0D1117;
                border: 2px solid #00FFC6;
                border-radius: 20px;
            }
            """
        )

        layout_diag = QVBoxLayout(diag)
        layout_diag.setContentsMargins(10, 10, 10, 10)
        layout_diag.addWidget(container)

        interno = QVBoxLayout(container)
        interno.setContentsMargins(35, 30, 35, 30)
        interno.setSpacing(20)

        # --- 3. CONTENIDO (Título y Cuerpo) ---
        titulo = QLabel("🖌️ " + tr("ubic.env_config_title", default="CONFIGURACIÓN DE ENTORNO"))
        font_tit = QFont("Segoe UI", 13)
        font_tit.setWeight(QFont.Weight.Black)  # Peso 900
        titulo.setFont(font_tit)
        titulo.setStyleSheet(
            "color: #00FFC6; letter-spacing: 1.2px; background: transparent; border: none;"
        )
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        msg_cuerpo = QLabel()
        msg_cuerpo.setTextFormat(Qt.TextFormat.RichText)
        msg_cuerpo.setText(
            tr("ubic.env_config_msg",
               default="<div style='line-height: 150%; text-align: center;'>La escala y el origen (0,0) se han establecido correctamente.<br><br>Pulse el botón <b style='color: #00FFC6;'>🖌️ MODO PINTADO</b> para activar el modo de dibujo de muros.<br>Delimite las paredes y obstáculos del local: esto es vital para que el motor de rutas evite colisiones.</div>")
        )
        msg_cuerpo.setStyleSheet(
            """
            color: #E6EDF3; 
            font-size: 13px; 
            font-family: 'Segoe UI'; 
            font-weight: 900; 
            background: transparent; 
            border: none;
            """
        )
        msg_cuerpo.setWordWrap(True)

        # --- 4. BOTÓN DE ACCIÓN ---
        btn_entendido = QPushButton(tr("ubic.understood_start", default="ENTENDIDO, EMPEZAR"))
        btn_entendido.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_entendido.setFixedWidth(220)
        btn_entendido.setStyleSheet(
            """
            QPushButton {
                background-color: #161B22;
                color: #00FFC6;
                border: 1px solid #00FFC6;
                padding: 12px;
                border-radius: 10px;
                font-family: 'Segoe UI';
                font-weight: 900;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #00FFC6;
                color: #0D1117;
                border: 1px solid #00FFC6;
            }
            """
        )
        btn_entendido.clicked.connect(diag.accept)

        interno.addWidget(titulo)
        interno.addWidget(msg_cuerpo)
        interno.addStretch()
        interno.addWidget(btn_entendido, alignment=Qt.AlignmentFlag.AlignCenter)

        # --- 5. EJECUCIÓN Y BLOQUEO ---
        diag.exec()

        # Marcamos como visto y apagamos la bandera activa
        # para que no vuelva a saltar hasta que se haga otra calibración manual
        target_win.onboarding_muros_visto = True
        target_win.calibracion_en_curso_activa = False

        # Opcional: Si tienes un botón de "Modo Pintar", podemos darle un pequeño foco visual
        if hasattr(target_win, "btn_modo_pintar"):
            target_win.btn_modo_pintar.setFocus()

    def cancelar_calibracion(self):
        """Método de limpieza si el usuario cancela los diálogos"""
        self.modo_calibrar = False

        if hasattr(self.visor_admin, "configurar_modo"):
            self.visor_admin.configurar_modo("NAVEGACION")

        if hasattr(self, "limpiar_indicadores_calib"):
            self.limpiar_indicadores_calib()

        # Ocultar botón de cancelar si existe
        if hasattr(self, "btn_cancelar_calib"):
            self.btn_cancelar_calib.setVisible(False)

        if self.window().statusBar():
            self.window().statusBar().clearMessage()
            self.window().statusBar().setStyleSheet("")
            self.window().statusBar().showMessage("Calibración cancelada.", 3000)

        # Limpiar cualquier rastro de banderas de espera para evitar el Silent Crash
        if hasattr(self, "visor_admin") and self.visor_admin:
            self.visor_admin.esperando_ancla_0 = False

        # Refrescar visualmente para confirmar la limpieza
        if hasattr(self, "visor_admin") and self.visor_admin.viewport():
            self.visor_admin.viewport().update()

    def gestionar_deshacer_muro(self):
        visor = getattr(self, "visor_admin", None)
        if not visor:
            return

        if getattr(visor, "linea_temporal_muro", None):
            escena = QGraphicsView.scene(visor)
            try:
                if escena and visor.linea_temporal_muro.scene() == escena:
                    escena.removeItem(visor.linea_temporal_muro)
            except Exception:
                pass
            visor.linea_temporal_muro = None
            visor.punto_inicio_muro = None
            self.mostrar_mensaje_temporal(tr("ubic.stroke_cancelled", default="TRAZO CANCELADO"))
            return

        estado = self._estado_planta()
        if not estado["undo"]:
            self.mostrar_mensaje_temporal(tr("ubic.history_empty", default="HISTORIAL VACÍO"))
            self._actualizar_botones_historial()
            return

        accion = estado["undo"].pop()
        estado["redo"].append(accion)
        self.reconstruir_estado_mapa_actual(accion["before"], recuadrar=False)
        self.cambios_sin_guardar = True
        self._actualizar_botones_historial()
        self.mostrar_mensaje_temporal(tr("ubic.undone", default="DESHECHO"))

    def gestionar_rehacer_muro(self):
        estado = self._estado_planta()
        if not estado["redo"]:
            self.mostrar_mensaje_temporal(tr("ubic.nothing_redo", default="NO HAY ACCIONES PARA REHACER"))
            self._actualizar_botones_historial()
            return

        accion = estado["redo"].pop()
        estado["undo"].append(accion)
        self.reconstruir_estado_mapa_actual(accion["after"], recuadrar=False)
        self.cambios_sin_guardar = True
        self._actualizar_botones_historial()
        self.mostrar_mensaje_temporal(tr("ubic.redone", default="REHECHO"))

    def cargar_matriz_serializada(self, datos_muros):
        """
        UNIFICACIÓN TOTAL: Reconstruye la visualización Neón y la matriz lógica A*
        en un solo paso atómico.
        """
        import json

        import numpy as np
        from PyQt6.QtCore import QLineF, Qt
        from PyQt6.QtGui import QColor, QPen

        visor = getattr(self, "visor_admin", None)
        if not visor:
            return

        try:
            # --- 1. PREPARACIÓN Y LIMPIEZA ---
            # Parseo de datos
            if isinstance(datos_muros, str):
                try:
                    datos = json.loads(datos_muros)
                except:
                    return
            else:
                datos = datos_muros

            lista_vectores = (
                datos.get("muros_vectores", datos) if isinstance(datos, dict) else datos
            )
            escena = QGraphicsView.scene(visor)
            if not escena:
                return

            # Limpieza visual — only remove items still belonging to this scene
            if hasattr(visor, "historial_muros"):
                for item in visor.historial_muros[:]:
                    try:
                        if item and item.scene() == escena:
                            escena.removeItem(item)
                    except (RuntimeError, AttributeError):
                        pass
                visor.historial_muros.clear()
            else:
                visor.historial_muros = []

            # --- 2. INICIALIZACIÓN LÓGICA (Matriz A*) ---
            # Buscamos el fondo para saber las dimensiones
            pixmap_item = getattr(visor, "pixmap_item", None)
            if not pixmap_item:
                # Intento de rescate si no está referenciado
                for item in escena.items():
                    if "QGraphicsPixmapItem" in str(type(item)):
                        pixmap_item = item
                        visor.pixmap_item = item
                        break

            if pixmap_item:
                rect = pixmap_item.boundingRect()
                sz = max(1, getattr(visor, "celda_size", 20))
                grid_cols = int(rect.width() // sz) + 1
                grid_rows = int(rect.height() // sz) + 1
                # Creamos la matriz limpia (uint8 para ahorrar memoria)
                visor.matriz_obstaculos = np.zeros(
                    (grid_rows, grid_cols), dtype=np.uint8
                )
            else:
                print("⚠️ No se puede inicializar matriz: Mapa no encontrado.")
                return

            # --- 3. RECONSTRUCCIÓN DUAL (Visual + Lógica) ---
            pen_muro = QPen(QColor("#00F5FF"), 3, Qt.PenStyle.SolidLine)
            pen_muro.setCapStyle(Qt.PenCapStyle.RoundCap)

            muros_count = 0
            for m in lista_vectores:
                try:
                    p1 = QLineF(
                        float(m["x1"]), float(m["y1"]), float(m["x2"]), float(m["y2"])
                    ).p1()
                    p2 = QLineF(
                        float(m["x1"]), float(m["y1"]), float(m["x2"]), float(m["y2"])
                    ).p2()

                    # A. Parte Visual: Crear ítem Neón
                    item_muro = QGraphicsLineItem(QLineF(p1, p2))
                    item_muro.setPen(pen_muro)
                    item_muro.setZValue(180)
                    item_muro.setData(0, "MURO_TECNICO")
                    escena.addItem(item_muro)
                    visor.historial_muros.append(item_muro)

                    # B. Parte Lógica: Marcar en la matriz NumPy
                    # Usamos el método que ya tienes (es_muro_preciso=True para no inflar en carga)
                    if hasattr(visor, "marcar_muro_en_matriz"):
                        visor.marcar_muro_en_matriz(p1, p2, es_muro_preciso=True)

                    muros_count += 1
                except:
                    continue

            # --- 4. SINCRONIZACIÓN FINAL ---
            # Sincronizamos la matriz con el visor_mapa (el de usuario)
            if hasattr(self, "visor_mapa"):
                self.visor_mapa.matriz_obstaculos = visor.matriz_obstaculos

            if hasattr(self, "btn_deshacer_muro"):
                self.btn_deshacer_muro.setEnabled(len(visor.historial_muros) > 0)

            # Refresco de seguridad
            if visor.viewport():
                visor.viewport().update()

            print(f"✅ MATRIZ Y MUROS SINCRONIZADOS: {muros_count} vectores cargados.")

        except Exception as e:
            print(f"❌ Error en carga unificada: {e}")

    def limpiar_indicadores_calib(self):
        """
        Elimina de la escena todos los elementos visuales de la calibración.
        AJUSTE QUIRÚRGICO: Protección avanzada SIP y restauración de UI Neón.
        """
        from PyQt6 import sip  # Vital para manejar recolección de basura de Qt
        from PyQt6.QtCore import Qt

        if not hasattr(self, "visor_admin") or not self.visor_admin:
            return

        scene = QGraphicsView.scene(self.visor_admin)
        if not scene:
            return

        elementos = [
            "m_y1",
            "m_y2",
            "linea_y",
            "m_x1",
            "m_x2",
            "linea_x",
            "linea_temporal_cal",
        ]

        # 1. LIMPIEZA CON PROTECCIÓN "SIP"
        for contenedor in [self, self.visor_admin]:
            for attr in elementos:
                if hasattr(contenedor, attr):
                    obj = getattr(contenedor, attr)
                    if obj is not None:
                        try:
                            # SIP evita RuntimeError: wrapped C/C++ object has been deleted
                            if not sip.isdeleted(obj):
                                if hasattr(obj, "scene") and obj.scene() == scene:
                                    scene.removeItem(obj)
                        except (RuntimeError, ReferenceError, Exception):
                            pass
                    try:
                        setattr(contenedor, attr, None)
                    except:
                        pass

        # 2. GESTIÓN DE BOTONES (Estética Neón)
        btn = getattr(self, "btn_escala", getattr(self, "btn_calibrar_escala", None))
        if btn:
            btn.setText("📏 " + tr("ubic.recalib", default="RECALIBRAR"))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                """
                QPushButton { 
                    background-color: #00F5FF; color: #000000; border-radius: 8px; 
                    font-family: 'Segoe UI'; font-weight: 900; font-size: 11px;
                    border: none; padding: 10px;
                }
                QPushButton:hover { background-color: #FFFFFF; }
            """
            )

        if hasattr(self, "btn_cancelar_calib") and self.btn_cancelar_calib:
            self.btn_cancelar_calib.setVisible(False)

        # 3. STATUS BAR
        win = self.window()
        if win and win.statusBar():
            win.statusBar().setStyleSheet(
                "color: #00F5FF; font-family: 'Segoe UI'; font-weight: 900; font-size: 11px;"
            )
            win.statusBar().showMessage("✅ CALIBRACIÓN FINALIZADA O CANCELADA", 3000)

        if self.visor_admin.viewport():
            self.visor_admin.viewport().update()

    def actualizar_coordenada_db(
        self, epc, nueva_pos, metros_x=0.0, metros_y=0.0, forzar_update=False
    ):
        """
        Sincroniza el movimiento físico del icono con la tabla de DB.
        AJUSTE QUIRÚRGICO: Throttling de alta frecuencia y feedback visual en UI.
        """
        import time

        from src.db.conexion import obtener_conexion

        # 1. ESCUDO ANTI-SPAM (Throttling)
        # Evita colapsar la base de datos si el icono se arrastra muy rápido
        tiempo_actual = time.time()
        ultimo_update = getattr(self, "_ultimo_tiempo_db", 0)

        if (
            not forzar_update and (tiempo_actual - ultimo_update) < 1.0
        ):  # Reducido a 1.0s para más fluidez
            return
        self._ultimo_tiempo_db = tiempo_actual

        try:
            # 2. FORMATEO Y CÁLCULO DE ESCALA
            x_px = int(nueva_pos.x())
            y_px = int(nueva_pos.y())

            # Prioridad: Escala del Visor GPS -> Escala Admin -> Fallback 100
            if hasattr(self, "visor_mapa") and hasattr(self.visor_mapa, "ratio_px_m_h"):
                factor = self.visor_mapa.ratio_px_m_h
            else:
                factor = getattr(self, "escala_px_metro", 100.0)

            if metros_x == 0.0 and metros_y == 0.0:
                m_x = round(nueva_pos.x() / factor, 3)
                m_y = round(nueva_pos.y() / factor, 3)
            else:
                m_x = round(float(metros_x), 3)
                m_y = round(float(metros_y), 3)

            # 3. PERSISTENCIA EN MARIA DB
            with obtener_conexion() as conn:
                if conn:
                    with conn.cursor() as cursor:
                        query = """
                            UPDATE ubicaciones 
                            SET mapa_x = %s, mapa_y = %s, x_metros = %s, y_metros = %s, fecha_actualizacion = NOW()
                            WHERE epc = %s
                        """
                        cursor.execute(query, (x_px, y_px, m_x, m_y, epc))
                    conn.commit()
                else:
                    raise Exception("No se pudo obtener conexión del pool.")

            # 4. FEEDBACK VISUAL (Solo si se fuerza o se suelta el icono)
            if forzar_update:
                win = self.window()
                if win and win.statusBar():
                    win.statusBar().setStyleSheet(
                        "color: #00F5FF; font-family: 'Segoe UI'; font-weight: 900;"
                    )
                    win.statusBar().showMessage(
                        f"📡 POSICIÓN {epc} GUARDADA: [{m_x}m, {m_y}m]", 3000
                    )

        except Exception as e:
            print(f"❌ ERROR CRÍTICO DB: {e}")
            win = self.window()
            if win and win.statusBar():
                win.statusBar().setStyleSheet(
                    "color: #FF4B4B; font-family: 'Segoe UI'; font-weight: 900;"
                )
                win.statusBar().showMessage(
                    "⚠️ ERROR DE RED: POSICIÓN NO GUARDADA", 5000
                )


from PyQt6.QtCore import QPropertyAnimation, QRectF, pyqtProperty
from PyQt6.QtWidgets import QGraphicsEllipseItem

# ============================================================
# BLOQUE RADAR DE PROXIMIDAD
# ============================================================

class AroRadar(QGraphicsEllipseItem):
    def __init__(self, pos, color_hex):
        super().__init__(-1, -1, 2, 2)  # Inicia casi invisible
        self.setPos(pos)
        self.setPen(QPen(QColor(color_hex), 2))
        self.setZValue(150)
        self._radio = 0

    @pyqtProperty(float)
    def radio(self):
        return self._radio

    @radio.setter
    def radio(self, valor):
        self._radio = valor
        # Expandimos el rectángulo del elipse desde su centro
        self.setRect(-valor, -valor, valor * 2, valor * 2)
        # Efecto de desvanecimiento: a más radio, menos opacidad
        opacidad = max(0, 1.0 - (valor / 100.0))
        self.setOpacity(opacidad)


# ============================================================
# BLOQUE VISTA DE MAPA INTERACTIVO
# ============================================================

class VistaMapa(QGraphicsView):
    def __init__(self, main, modo_admin=False, parent=None):
        super().__init__(parent)
        from PyQt6.QtCore import QPointF, Qt
        from PyQt6.QtGui import QColor, QPainter
        from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

        # 1. ESCENA Y RENDERIZADO (Blindaje Visual)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        # AJUSTES QUIRÚRGICOS DE RENDERIZADO:
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setRenderHint(QPainter.RenderHint.LosslessImageRendering)

        # Evita que el movimiento del ratón deje "estelas" o borre el fondo accidentalmente
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

        self.setMouseTracking(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QColor("#050505"))
        self.setStyleSheet(
            "border: 2px solid #00FFC6; border-radius: 12px; background: #0D1117;"
        )
        if self.viewport():
            self.viewport().setStyleSheet("background: #050505; border-radius: 12px;")

        # 2. REFERENCIAS Y PERMISOS
        self.parent_window = parent
        self.main_window = main
        self.modo_admin = modo_admin
        self.satelites_instalados_sesion = 0

        # 3. GESTIÓN DE ESTADOS
        self.modo_pintar = False
        self.modo_calibrar = False
        self.estado_interaccion = "NAVEGACION"

        # Flag de control para optimizar el drawForeground (que arreglamos antes)
        self._bandera_cambios_notificada = False

        # 4. MOTOR DE GPS Y MOVIMIENTO
        self.pos_operario = QPointF(0, 0)
        self.pos_objetivo_operario = QPointF(0, 0)
        self.icono_operario = None
        self.timer_animacion_operario = None
        self.rastreo_en_vivo_activo = False

        # 5. PARÁMETROS TÉCNICOS
        self.pixmap_item = (
            None  # Inicializamos explícitamente para evitar errores de atributo
        )
        self.celda_size = 2
        self.ratio_px_m_h = 1.0
        self.ratio_px_m_v = 1.0
        self.punto_ancla = None
        self.matriz_obstaculos = None
        self.mostrar_matriz = False
        self.mostrando_matriz = False
        self.lineas_ruta = []
        self.puntos_interactivos = []
        self.datos_puntos_guardado = []
        self._zoom_manual_activo = False

        # 6. GESTIÓN DE MUROS Y CALIBRACIÓN
        self.historial_muros = []
        self.punto_inicio_muro = None
        self.linea_temporal_muro = None
        self.puntos_calibracion = []
        self.linea_temporal_cal = None

        # 7. INDICADORES DE TELEMETRÍA
        self.linea_x = self.linea_y = None
        self.m_x1 = self.m_x2 = self.m_y1 = self.m_y2 = None
        self.item_ancla = None
        self.item_texto_ancla = None
        self.grupo_marca_origen = []

        # 8. ARRANQUE DEL SISTEMA
        # Establecemos un área mínima inicial para que la cámara no nazca en el "limbo"
        self.setSceneRect(0, 0, 1, 1)
        self.configurar_modo("NAVEGACION")

    def mostrar_mensaje_final(self, total):
        """
        Muestra un resumen final de la sesión de trabajo.
        Se ejecuta tras hacer clic en 'CONFIRMAR Y FINALIZAR'.
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QDialog, QFrame, QLabel, QPushButton, QVBoxLayout

        diag = QDialog(self)
        diag.setFixedSize(350, 180)
        diag.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        diag.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        main_lyt = QVBoxLayout(diag)
        main_lyt.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setStyleSheet(
            """
            QFrame { 
                background-color: #0D1117; 
                border: 2px solid #58A6FF; 
                border-radius: 15px; 
            }
            QLabel { 
                color: #E6EDF3; 
                font-family: 'Segoe UI'; 
                font-weight: 900; 
                font-size: 14px; 
            }
            QPushButton { 
                background-color: #21262D; color: #58A6FF; border: 1px solid #58A6FF;
                border-radius: 8px; font-family: 'Segoe UI'; font-weight: 900; padding: 8px 20px; 
            }
            QPushButton:hover { background-color: #58A6FF; color: #0D1117; }
        """
        )

        lyt = QVBoxLayout(container)
        lyt.addWidget(
            QLabel(tr("ubic.operation_complete", default="¡OPERACIÓN COMPLETADA!"), alignment=Qt.AlignmentFlag.AlignCenter)
        )
        lyt.addWidget(
            QLabel(
                tr("ubic.sats_registered", default="Se han registrado {total} satélites.", total=total),
                alignment=Qt.AlignmentFlag.AlignCenter,
            )
        )

        btn_ok = QPushButton(tr("common.close", default="CERRAR"))
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.clicked.connect(diag.accept)
        lyt.addWidget(btn_ok, alignment=Qt.AlignmentFlag.AlignCenter)

        main_lyt.addWidget(container)
        diag.exec()

    def configurar_modo(self, modo="NAVEGACION"):
        """
        Cambia el comportamiento del visor entre navegación y modos de edición.
        Modos soportados: "NAVEGACION", "UBICAR_ESTANTERIA", "UBICAR_SATELITE", "CALIBRAR"
        """
        self.estado_interaccion = modo

        # 1. Configuración de Arrastre (DragMode)
        if modo == "NAVEGACION":
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        else:
            # En cualquier modo de edición, desactivamos el arrastre para capturar clics exactos
            self.setDragMode(QGraphicsView.DragMode.NoDrag)

        # 2. Configuración del Cursor
        if modo == "NAVEGACION":
            cursor = Qt.CursorShape.OpenHandCursor
        elif modo in ["UBICAR_ESTANTERIA", "UBICAR_SATELITE", "CALIBRAR"]:
            cursor = Qt.CursorShape.CrossCursor
        else:
            cursor = Qt.CursorShape.ArrowCursor
        self.setCursor(cursor)
        vp = self.viewport() if hasattr(self, "viewport") else None
        if vp:
            vp.setCursor(cursor)
            vp.update()

    def reencuadrar_plano(self, force=False):
        escena = QGraphicsView.scene(self)
        pixmap_item = getattr(self, "pixmap_item", None)

        if not escena:
            return
        # Skip fitInView when the widget is hidden — viewport size is 0 and would corrupt the
        # transform. showEvent already re-triggers reencuadrar_plano when the tab becomes visible.
        vp = self.viewport()
        if not self.isVisible() or (vp and vp.width() <= 1):
            return
        # Skip fitInView during active calibration — avoids shifting the view while the user draws.
        if getattr(self, "modo_calibrar", False):
            return
        if self._zoom_manual_activo and not force:
            return

        # Obtenemos el rectángulo del plano o de los ítems
        rect = (
            pixmap_item.sceneBoundingRect()
            if pixmap_item
            else escena.itemsBoundingRect()
        )

        if rect.isNull() or rect.width() < 5:  # Evitar cálculos sobre escenas vacías
            return

        margen = 8  # Margen mínimo para maximizar calidad visible

        # Bloqueamos actualizaciones para evitar parpadeo
        self.setUpdatesEnabled(False)

        # 1. Resetear cualquier transformación previa
        self.resetTransform()

        # 2. Ajustar la escena al rectángulo del plano exactamente
        escena.setSceneRect(rect)
        self.setSceneRect(rect)  # también en el visor para coherencia

        # 3. EL TRUCO: fitInView ya centra la imagen si se usa con KeepAspectRatio
        self.fitInView(
            rect.adjusted(-margen, -margen, margen, margen),
            Qt.AspectRatioMode.KeepAspectRatio,
        )

        # 4. Asegurar el centro por si el viewport es más grande que el plano
        self.centerOn(rect.center())

        # 5. Limpiamos el estado de zoom manual
        self._zoom_manual_activo = False

        # Reactivamos y refrescamos
        self.setUpdatesEnabled(True)
        if self.viewport():
            self.viewport().update()

    def _aplicar_mascara_viewport(self, radius=16):
        vp = self.viewport()
        if vp and vp.width() > 0 and vp.height() > 0:
            from PyQt6.QtCore import QRectF
            from PyQt6.QtGui import QPainterPath, QRegion
            path = QPainterPath()
            path.addRoundedRect(QRectF(vp.rect()), radius, radius)
            region = QRegion(path.toFillPolygon().toPolygon())
            vp.setMask(region)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, lambda: self.reencuadrar_plano(force=False))
        QTimer.singleShot(80, lambda: self.reencuadrar_plano(force=False))
        QTimer.singleShot(100, self._aplicar_mascara_viewport)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: self.reencuadrar_plano(force=True))
        QTimer.singleShot(120, lambda: self.reencuadrar_plano(force=True))

    def enterEvent(self, event):
        if (
            getattr(self, "modo_pintar", False)
            or getattr(self, "modo_calibrar", False)
            or getattr(self, "modo_satelite", False)
        ):
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif getattr(self, "estado_interaccion", "NAVEGACION") == "NAVEGACION":
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not (
            getattr(self, "modo_pintar", False)
            or getattr(self, "modo_calibrar", False)
            or getattr(self, "modo_satelite", False)
        ):
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        """
        CAPTURADOR UNIFICADO (VistaMapa):
        1. Gestión de Estados (ESC / Ctrl+Z).
        2. Discriminación de Escáner de Código de Barras vs Humano.
        """
        from datetime import datetime

        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QLineEdit

        # Referencia a la ventana principal para llamadas a métodos de lógica
        main = self.parent_window if hasattr(self, "parent_window") else self.window()

        # --- PARTE A: ATAJOS DE TECLADO (EDICIÓN) ---

        # Ctrl + Z: Deshacer último muro/trazo
        if (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
            and event.key() == Qt.Key.Key_Z
        ):
            if hasattr(main, "gestionar_deshacer_muro"):
                main.gestionar_deshacer_muro()
            return

        # ESC: Cancelar procesos activos o volver al menú
        elif event.key() == Qt.Key.Key_Escape:
            # Si estamos en un modo activo, lo cancelamos primero
            if getattr(self, "modo_pintar", False) or getattr(
                self, "modo_calibrar", False
            ):
                self.modo_pintar = False
                self.modo_calibrar = False
                self.setCursor(Qt.CursorShape.ArrowCursor)
                if main.window().statusBar():
                    main.window().statusBar().showMessage(
                        "❌ Acción cancelada", 2000
                    )
                return

            # Si no hay nada activo, volvemos al menú
            if hasattr(main, "volver_menu_principal"):
                main.volver_menu_principal()
            return

        # --- PARTE B: LÓGICA DE ESCÁNER DE HARDWARE (BUFFER) ---

        # Inicializamos el buffer en el objeto si no existe
        if not hasattr(self, "buffer_barcode"):
            self.buffer_barcode = ""
            self.last_key_time = datetime.now()

        ahora = datetime.now()
        # Calculamos diferencia de tiempo entre pulsaciones (ms)
        diff = (ahora - self.last_key_time).total_seconds() * 1000
        self.last_key_time = ahora

        # Si el escáner termina con un ENTER (Return/Enter)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.buffer_barcode:
                # Solo procesamos si el usuario NO está escribiendo en un cuadro de texto real
                if not isinstance(main.focusWidget(), QLineEdit):
                    if hasattr(main, "procesar_escaneo_barcode"):
                        main.procesar_escaneo_barcode(self.buffer_barcode)
                self.buffer_barcode = ""
        else:
            char = event.text()
            if char.isprintable() and char:
                # DISCRIMINADOR: Si el tiempo entre teclas es > 100ms, es un humano escribiendo.
                # Si es un humano, reseteamos el buffer para que no se mezcle con el escáner.
                if diff > 100:
                    self.buffer_barcode = char
                else:
                    self.buffer_barcode += char

        # Pasamos el evento al padre para no romper la navegación por defecto
        super().keyPressEvent(event)

    def mouseReleaseEvent(self, event):
        """
        Finaliza el arrastre y sincroniza la nueva posición métrica con la DB.
        Gestiona el cambio de cursor tras el arrastre.
        """
        from PyQt6.QtCore import Qt

        # 1. BÚSQUEDA DINÁMICA DEL OBJETO MAIN
        main = getattr(self, "parent_window", None) or self.parent()
        while (
            main
            and not hasattr(main, "abrir_formulario_ubicacion_estanteria")
            and hasattr(main, "parent")
        ):
            parent_obj = main.parent()
            if not parent_obj:
                break
            main = parent_obj

        # --- NUEVO: RESTAURAR CURSOR TRAS ARRASTRE ---
        if getattr(self, "estado_interaccion", "NAVEGACION") == "NAVEGACION":
            self.setCursor(Qt.CursorShape.OpenHandCursor)

        # 2. BLOQUEO DE SEGURIDAD
        is_busy = (
            getattr(self, "modo_pintar", False)
            or getattr(self, "modo_calibrar", False)
            or (main and getattr(main, "esperando_ubicacion_estanteria", False))
        )

        if is_busy:
            super().mouseReleaseEvent(event)
            return

        # 3. PROPAGACIÓN ESTÁNDAR
        super().mouseReleaseEvent(event)

        escena = QGraphicsView.scene(self)
        if not escena:
            return

        # 4. IDENTIFICACIÓN Y PERSISTENCIA
        items_seleccionados = escena.selectedItems()
        item_movido = items_seleccionados[0] if items_seleccionados else None

        if item_movido:
            epc_id = item_movido.data(0)
            tipo = item_movido.data(1) or "ACTIVO"

            if epc_id:
                nueva_pos_px = item_movido.scenePos()

                # 5. CONVERSIÓN A TELEMETRÍA REAL
                ancla = getattr(self, "punto_ancla", None)
                r_x = getattr(self, "ratio_px_m_h", 1.0)
                r_y = getattr(self, "ratio_px_m_v", 1.0)

                if ancla and r_x != 0 and r_y != 0:
                    rel_x = (nueva_pos_px.x() - ancla.x()) / r_x
                    rel_y = (ancla.y() - nueva_pos_px.y()) / r_y
                else:
                    rel_x, rel_y = 0.0, 0.0

                # 6. SINCRONIZACIÓN CON BACKEND
                if main and hasattr(main, "actualizar_coordenada_db"):
                    main.actualizar_coordenada_db(epc_id, nueva_pos_px, rel_x, rel_y)

                # 7. FEEDBACK EN STATUS BAR
                status_bar = (
                    main.window().statusBar() if hasattr(main, "window") else None
                )
                if status_bar:
                    status_bar.setStyleSheet(
                        "color: #00F0FF; font-family: 'Segoe UI'; font-weight: 900; background: #0D1117;"
                    )
                    msg = f"✓ {tipo} REUBICADO [{epc_id}] -> {rel_x:.2f}m, {rel_y:.2f}m"
                    status_bar.showMessage(msg, 4000)

    def ejecutar_radar_inditex(self, pos_actual, pos_destino):
        """
        Sistema de ecolocalización sonora y visual para búsqueda de precisión.
        Lógica mantenida: Verde (<1.5m), Naranja (1.5m-4m), Rojo (>4m).
        Distancia > 10m: Silencio total.
        """
        import math
        import time
        import winsound
        from threading import Thread

        from PyQt6.QtGui import QColor

        # 1. Cálculo de distancia real basado en escala horizontal
        distancia_px = math.hypot(
            pos_destino.x() - pos_actual.x(), pos_destino.y() - pos_actual.y()
        )
        ppm = getattr(self, "ratio_px_m_h", 1.0)
        distancia_m = distancia_px / ppm

        # 2. Umbral de desactivación (Fuera de rango de radar)
        if distancia_m > 10.0:
            return

        # 3. Mapeo de feedback según proximidad (Lógica original intacta)
        if distancia_m < 1.5:
            color_radar = "#00FFC6"  # VERDE: Objetivo localizado
            frecuencia = 2500  # Agudo
            intervalo_beep = 50  # Rápido
        elif distancia_m < 4.0:
            color_radar = "#FFA500"  # NARANJA: Aproximación
            frecuencia = 1500
            intervalo_beep = 300
        else:
            color_radar = "#F85149"  # ROJO: Lejos
            frecuencia = 800  # Grave
            intervalo_beep = 800  # Lento

        # 4. Control de persistencia sonora (Throttle)
        current_time = time.time() * 1000
        if not hasattr(self, "_ultimo_beep_time"):
            self._ultimo_beep_time = 0

        if current_time - self._ultimo_beep_time > intervalo_beep:
            # Duración: Feedback táctil sonoro (más largo al estar encima)
            duracion = 250 if distancia_m < 0.5 else 100

            # Ejecución en hilo para no congelar la UI de navegación
            Thread(
                target=lambda: winsound.Beep(frecuencia, duracion), daemon=True
            ).start()
            self._ultimo_beep_time = current_time

        # 5. Sincronización visual con el mapa
        if hasattr(self, "animar_marcador_proximidad"):
            self.animar_marcador_proximidad(distancia_m, color_radar)

        # Actualizar color del punto objetivo (si existe en escena)
        if hasattr(self, "punto_destino_item") and self.punto_destino_item:
            try:
                self.punto_destino_item.setBrush(QColor(color_radar))
            except Exception:
                pass

    def disparar_radar(self, pos, color="#00FFC6"):
        """
        Crea una onda expansiva de sonar en la posición indicada.
        Mantiene duración de 1.2s y expansión hasta 120.0 unidades.
        """
        from PyQt6.QtCore import QAbstractAnimation

        # 1. Instanciación del objeto visual (AroRadar)
        try:
            # Asumimos que la clase AroRadar está disponible en el espacio de nombres
            escena = QGraphicsView.scene(self)
            aro = AroRadar(pos, color)
            escena.addItem(aro)
        except (NameError, AttributeError) as e:
            print(f"[!] Error visual en radar: {e}")
            return

        # 2. Configuración de la Animación de Expansión
        anim = QPropertyAnimation(aro, b"radio")
        anim.setDuration(1200)  # 1.2 segundos originales
        anim.setStartValue(0.0)
        anim.setEndValue(120.0)  # Magnitud de onda

        # 3. Limpieza de memoria y escena al finalizar
        def finalizar_y_limpiar():
            try:
                if aro.scene():
                    escena.removeItem(aro)
            except:
                pass
            # Eliminamos la animación de la lista de seguimiento
            if hasattr(self, "_animaciones_radar") and anim in self._animaciones_radar:
                self._animaciones_radar.remove(anim)

        anim.finished.connect(finalizar_y_limpiar)

        # 4. Gestión de ciclo de vida de la animación
        if not hasattr(self, "_animaciones_radar"):
            self._animaciones_radar = []

        # Filtramos animaciones muertas antes de añadir la nueva
        self._animaciones_radar = [
            a
            for a in self._animaciones_radar
            if a.state() == QAbstractAnimation.State.Running
        ]

        self._animaciones_radar.append(anim)
        anim.start()

    def marcar_muro_en_matriz(self, p1, p2, es_muro_preciso=False):
        """
        Rasteriza una línea vectorial en la matriz de ocupación NumPy.
        FIX: Validación de límites estricta y sincronización de viewport.
        """
        # 1. ACCESO SEGURO A LA MATRIZ (Prioridad: Matriz de la clase principal)
        # Si el visor no la tiene, intentamos sacarla del padre (clase principal)
        matriz = getattr(self, "matriz_obstaculos", None)
        if matriz is None:
            if hasattr(self, "main") and hasattr(self.main, "matriz_obstaculos"):
                matriz = self.main.matriz_obstaculos
                self.matriz_obstaculos = matriz  # Sincronizamos referencia local
            else:
                return

        import math


        # 2. CÁLCULO DE MAGNITUDES Y ESCALA
        celda_sz = getattr(self, "celda_size", 20)
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        distancia = math.hypot(dx, dy)

        filas, columnas = matriz.shape

        # 3. LÓGICA DE INFLADO (Protección de colisión)
        # Si es carga de DB, usamos radio 0 (muro fino).
        # Si es dibujo manual, usamos el radio de seguridad.
        radio = 0 if es_muro_preciso else getattr(self, "radio_seguridad_muro", 1)

        # 4. RASTERIZACIÓN DINÁMICA
        if distancia == 0:
            pasos = 1
        else:
            # Muestreo denso: 4 muestras por celda para evitar "saltos" en diagonales rápidas
            pasos = max(int(distancia / (celda_sz / 4.0)), 1)

        for i in range(pasos + 1):
            t = i / pasos
            curr_x = p1.x() + dx * t
            curr_y = p1.y() + dy * t

            # Conversión a índices de matriz
            col = int(curr_x // celda_sz)
            row = int(curr_y // celda_sz)

            # Slicing con guardas de seguridad (Evita IndexError)
            r_min = max(0, row - radio)
            r_max = min(filas, row + radio + 1)
            c_min = max(0, col - radio)
            c_max = min(columnas, col + radio + 1)

            if r_min < r_max and c_min < c_max:
                matriz[r_min:r_max, c_min:c_max] = 1

        # 5. DISPARO DE RE-PINTADO (Refresco visual)
        # Forzamos al viewport a redibujar el Foreground (donde se ven los muros rojos)
        v_port = self.viewport() if callable(self.viewport) else self.viewport
        if v_port:
            v_port.update()

    def procesar_ruta_gps(self, termino=None):
        """
        MOTOR HÍBRIDO: Localiza el objetivo (DB) + Calcula ruta A* (Matriz).
        Unifica la búsqueda de coordenadas con el trazado de polilíneas neón.
        """
        import math


        # IMPORTANTE: Descomenta o ajusta esta ruta según la estructura real de tu proyecto
        try:
            from src.navigation.pathfinding import PathFinder as PathFinderEngine
        except ImportError:
            PathFinderEngine = PathFinder
            print(
                "❌ Error: No se pudo importar PathFinder. Revisa la ruta de importación."
            )
            return

        # --- 1. LOCALIZACIÓN DEL OBJETIVO ---
        if termino:
            # Asumo que esta función devuelve (nombre, QPointF)
            resultado = getattr(self, "obtener_coordenadas_articulo", lambda t: None)(
                termino
            )

            if resultado:
                nombre_dest, punto_destino = resultado
                self.coordenadas_destino = punto_destino
                if hasattr(self, "lbl_resultado_nombre"):
                    self.lbl_resultado_nombre.setText(nombre_dest.upper())
            else:
                # Usamos el sistema de mensajes HUD unificado en lugar de tocar el statusBar directamente
                if hasattr(self, "mostrar_mensaje_temporal"):
                    self.mostrar_mensaje_temporal("❌ " + tr("ubic.not_found2", default="NO ENCONTRADO: {termino}", termino=termino))
                return

        # --- 2. BARRERAS DE SEGURIDAD (Validación de Navegación) ---
        visor = getattr(self, "visor_mapa", None)
        coord_dest = getattr(self, "coordenadas_destino", None)

        if (
            not visor
            or not hasattr(visor, "pos_operario")
            or visor.pos_operario is None
        ):
            if hasattr(self, "mostrar_mensaje_temporal"):
                self.mostrar_mensaje_temporal(
                    "📍 " + tr("ubic.scan_qr_locate", default="ESCANEE UN QR PARA UBICAR SU POSICIÓN")
                )
            return

        if not coord_dest:
            return  # Nada que trazar aún

        # --- 3. VERIFICACIÓN DE INFRAESTRUCTURA LÓGICA (Matriz A*) ---
        # Si la matriz está vacía, intentamos forzar una recarga rápida
        if getattr(visor, "matriz_obstaculos", None) is None:
            print(
                "⚠️ Matriz no encontrada en el visor. Intentando recargar infraestructura..."
            )
            if hasattr(self, "cargar_infraestructura_registrada"):
                self.cargar_infraestructura_registrada()

            if getattr(visor, "matriz_obstaculos", None) is None:
                print("❌ Error crítico: Mapa de navegación (matriz A*) no disponible.")
                return

        # --- 4. TRADUCCIÓN AL ESPACIO MATRICIAL (Coordenadas -> Índices) ---
        pos_op = visor.pos_operario
        ratio_px_m = getattr(visor, "ratio_px_m_h", 1.0)

        # AJUSTE CRÍTICO: Debe coincidir con el tamaño de celda usado al crear la matriz (20)
        celda = getattr(visor, "celda_size", 20)
        matriz = visor.matriz_obstaculos

        # Compatibilidad con NumPy o listas estándar
        if hasattr(matriz, "shape"):
            filas, cols = matriz.shape
        else:
            filas = len(matriz)
            cols = len(matriz[0]) if filas > 0 else 0

        if filas == 0 or cols == 0:
            print("❌ Error: La matriz de obstáculos está vacía.")
            return

        # Snap-to-Grid: Ajuste magnético del inicio a nodos conocidos (opcional y útil para evitar colisiones iniciales)
        inicio_ajustado = pos_op
        nodos = getattr(self, "nodos_verificados", {})
        umbral_snap = 1.2 * ratio_px_m
        for coords in nodos.values():
            if (
                math.hypot(pos_op.x() - coords.x(), pos_op.y() - coords.y())
                < umbral_snap
            ):
                inicio_ajustado = coords
                break

        # Clamping: Previene desbordamientos forzando a que los índices entren en los límites de la matriz
        start_y = max(0, min(int(inicio_ajustado.y() // celda), filas - 1))
        start_x = max(0, min(int(inicio_ajustado.x() // celda), cols - 1))
        end_y = max(0, min(int(coord_dest.y() // celda), filas - 1))
        end_x = max(0, min(int(coord_dest.x() // celda), cols - 1))

        # --- 5. EJECUCIÓN DEL ALGORITMO A* Y RENDERIZADO ---
        try:
            finder = PathFinder(matriz)
            # El PathFinder suele recibir (fila, columna) -> (Y, X)
            camino = finder.get_path((start_y, start_x), (end_y, end_x))

            if camino:
                # Dibujar ruta neón en el visor de usuario
                if hasattr(visor, "dibujar_ruta"):
                    visor.dibujar_ruta(camino)

                # Cálculo de telemetría (Convertir celdas recorridas a metros reales)
                dist_grid = 0
                for i in range(len(camino) - 1):
                    p1, p2 = camino[i], camino[i + 1]
                    # math.hypot(dx, dy)
                    dist_grid += math.hypot(p2[1] - p1[1], p2[0] - p1[0])

                dist_metros = (dist_grid * celda) / ratio_px_m

                if hasattr(self, "mostrar_mensaje_temporal"):
                    self.mostrar_mensaje_temporal(
                        "🚀 " + tr("ubic.optimal_route", default="RUTA ÓPTIMA: {dist}m AL OBJETIVO", dist=f"{dist_metros:.2f}")
                    )
            else:
                if hasattr(self, "mostrar_mensaje_temporal"):
                    self.mostrar_mensaje_temporal(
                        "🚧 " + tr("ubic.area_blocked", default="ÁREA BLOQUEADA O DESTINO INACCESIBLE")
                    )

                # Opcional: Limpiar ruta anterior si la nueva falla
                if hasattr(visor, "limpiar_ruta_actual"):
                    visor.limpiar_ruta_actual()

        except Exception as e:
            print(f"❌ Fallo en el motor de navegación A*: {e}")
            import traceback

            traceback.print_exc()

    def procesar_ruta_gps(self, termino=None):
        """
        Versión estable del motor GPS con fallback al PathFinder local.
        """
        import math

        try:
            from src.navigation.pathfinding import PathFinder as PathFinderEngine
        except ImportError:
            PathFinderEngine = PathFinder

        if termino:
            resultado = getattr(self, "obtener_coordenadas_articulo", lambda t: None)(
                termino
            )
            if resultado:
                nombre_dest, punto_destino = resultado
                self.coordenadas_destino = punto_destino
                if hasattr(self, "lbl_resultado_nombre"):
                    self.lbl_resultado_nombre.setText(nombre_dest.upper())
            else:
                if hasattr(self, "mostrar_mensaje_temporal"):
                    self.mostrar_mensaje_temporal("❌ " + tr("ubic.not_found2", default="NO ENCONTRADO: {termino}", termino=termino))
                return

        visor = getattr(self, "visor_mapa", None)
        opciones = [
            op
            for op in getattr(self, "_opciones_destino_busqueda", [])
            if op.get("disponible") and op.get("coords") is not None
        ]
        if not opciones:
            ref_actual = (
                getattr(self, "_articulo_busqueda_actual", {}).get("codigo")
                or getattr(self, "_articulo_busqueda_actual", {}).get("nombre")
                or getattr(self, "_articulo_busqueda_actual", {}).get("termino")
                or getattr(
                    getattr(self, "input_search", None), "text", lambda: ""
                )().strip()
            )
            opciones = [
                op
                for op in self._obtener_opciones_destino_gps(ref_actual)
                if op.get("disponible") and op.get("coords") is not None
            ]
        seleccion = self._mostrar_selector_destino_gps(opciones) if opciones else None
        coord_dest = seleccion["coords"] if seleccion else None
        if not visor or getattr(visor, "pos_operario", None) is None:
            if hasattr(self, "mostrar_mensaje_temporal"):
                self.mostrar_mensaje_temporal(
                    "📍 " + tr("ubic.scan_qr_locate", default="ESCANEE UN QR PARA UBICAR SU POSICIÓN")
                )
            return
        if not coord_dest:
            return

        if getattr(visor, "matriz_obstaculos", None) is None and hasattr(
            self, "cargar_infraestructura_registrada"
        ):
            self.cargar_infraestructura_registrada()
        matriz = getattr(visor, "matriz_obstaculos", None)
        if matriz is None:
            if hasattr(self, "mostrar_mensaje_temporal"):
                self.mostrar_mensaje_temporal("🚧 " + tr("ubic.nav_map_unavailable", default="MAPA DE NAVEGACIÓN NO DISPONIBLE"))
            self._actualizar_piloto_rastreo(False)
            return

        filas, cols = (
            matriz.shape if hasattr(matriz, "shape") else (len(matriz), len(matriz[0]))
        )
        if filas == 0 or cols == 0:
            return

        celda = max(1, int(getattr(visor, "celda_size", 20)))
        inicio = visor.pos_operario
        start_y = max(0, min(int(inicio.y() // celda), filas - 1))
        start_x = max(0, min(int(inicio.x() // celda), cols - 1))
        end_y = max(0, min(int(coord_dest.y() // celda), filas - 1))
        end_x = max(0, min(int(coord_dest.x() // celda), cols - 1))

        try:
            camino = PathFinderEngine(matriz).get_path(
                (start_y, start_x), (end_y, end_x)
            )
        except Exception as e:
            print(f"❌ Fallo en el motor de navegación A*: {e}")
            return

        if not camino:
            if hasattr(visor, "limpiar_ruta"):
                visor.limpiar_ruta()
            if hasattr(self, "mostrar_mensaje_temporal"):
                self.mostrar_mensaje_temporal("🚧 " + tr("ubic.area_blocked", default="ÁREA BLOQUEADA O DESTINO INACCESIBLE"))
            self._actualizar_piloto_rastreo(False)
            return

        if hasattr(visor, "dibujar_ruta"):
            visor.dibujar_ruta(camino)

        dist_grid = 0.0
        for i in range(len(camino) - 1):
            p1, p2 = camino[i], camino[i + 1]
            dist_grid += math.hypot(p2[1] - p1[1], p2[0] - p1[0])

        ratio_px_m = max(float(getattr(visor, "ratio_px_m_h", 1.0) or 1.0), 0.001)
        dist_metros = (dist_grid * celda) / ratio_px_m
        destino_txt = getattr(self, "destino_gps_activo", {})
        destino_txt = (
            destino_txt.get("ubicacion") if isinstance(destino_txt, dict) else None
        )
        self._actualizar_piloto_rastreo(True, destino_txt)
        if hasattr(self, "mostrar_mensaje_temporal"):
            self.mostrar_mensaje_temporal(
                "🚀 " + tr("ubic.optimal_route", default="RUTA ÓPTIMA: {dist}m AL OBJETIVO", dist=f"{dist_metros:.2f}")
            )

    def mostrar_mensaje_status(self, mensaje, color):
        """Helper para limpiar el código de la StatusBar."""
        status_bar = self.statusBar() if hasattr(self, "statusBar") else None
        if status_bar:
            status_bar.setStyleSheet(
                f"color: {color}; font-weight: 900; background: #0D1117; font-family: 'Segoe UI';"
            )
            status_bar.showMessage(mensaje, 8000)

    def wheelEvent(self, event):
        """
        Control de Zoom mediante la rueda del ratón.
        El zoom se centra en la posición actual del cursor.
        """
        # 1. Definir factores de escala
        factor_zoom_in = 1.15
        factor_zoom_out = 0.85

        # 2. Configurar el anclaje del zoom al cursor
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._zoom_manual_activo = True

        # 3. Detectar dirección de la rueda
        if event.angleDelta().y() > 0:
            # Hacia arriba: Acercar
            self.scale(factor_zoom_in, factor_zoom_in)
        else:
            # Hacia abajo: Alejar
            self.scale(factor_zoom_out, factor_zoom_out)

        # 4. (Opcional) Emitir señal o actualizar viewport si es necesario
        self.viewport().update()

    def dibujar_punto(self, x, y, color="#FF4B4B"):
        """
        Dibuja el nodo de destino en la escena con un estilo de baliza.
        Retorna el objeto para manipulación externa (animaciones/radar).
        """
        radius = 8
        # Círculo principal con borde de alto contraste
        marcador = self.scene.addEllipse(
            x - radius,
            y - radius,
            radius * 2,
            radius * 2,
            QPen(QColor("#FFFFFF"), 2),
            QBrush(QColor(color)),
        )
        marcador.setZValue(150)  # Por encima de la ruta y muros

        # Efecto de halo estático (opcional, para mayor visibilidad)
        halo = self.scene.addEllipse(
            x - radius * 1.5,
            y - radius * 1.5,
            radius * 3,
            radius * 3,
            QPen(Qt.PenStyle.NoPen),
            QBrush(QColor(color[0:7] + "40")),  # Color con 25% de opacidad
        )
        halo.setZValue(149)
        halo.setParentItem(marcador)

        self.punto_destino_item = marcador
        return marcador

    def dibujar_ruta(self, puntos_camino):
        """
        Renderiza la trayectoria óptima usando un único PathItem para máximo rendimiento.
        Aplica un efecto de resplandor (Glow) y marca el destino final.
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QColor, QPainterPath, QPen

        # 1. LIMPIEZA PREVIA (Evita superposición de rutas viejas)
        self.limpiar_ruta()

        if not puntos_camino or len(puntos_camino) < 2:
            return

        # Ajuste de coordenadas al centro de la celda del Grid
        c_size = getattr(self, "celda_size", 10)
        half_cell = c_size / 2

        # 2. CONSTRUCCIÓN DE LA GEOMETRÍA (Path Único)
        # Usar un solo Path es 10x más rápido que añadir cientos de QGraphicsLineItem
        camino_geo = QPainterPath()

        # Punto inicial (Conversión de matriz a escena)
        start_x = puntos_camino[0][1] * c_size + half_cell
        start_y = puntos_camino[0][0] * c_size + half_cell
        camino_geo.moveTo(start_x, start_y)

        # Trazado del resto de nodos
        for fila, col in puntos_camino[1:]:
            px = col * c_size + half_cell
            py = fila * c_size + half_cell
            camino_geo.lineTo(px, py)

        # 3. RENDERIZADO ESTILO NEÓN (Capas Z)
        # Capa A: Resplandor (Glow) - Grueso y etéreo
        color_neon = QColor("#00FFC6")
        color_glow = QColor(0, 255, 198, 60)  # Mismo tono con transparencia (Alpha 60)

        pen_glow = QPen(
            color_glow,
            12,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        glow_item = self.scene().addPath(camino_geo, pen_glow)
        glow_item.setZValue(190)  # Capa alta para estar sobre el plano

        # Capa B: Núcleo (Core) - Fino y sólido
        pen_core = QPen(
            color_neon,
            4,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        core_item = self.scene().addPath(camino_geo, pen_core)
        core_item.setZValue(191)  # Siempre por encima de su propio resplandor

        # Guardamos referencias para la limpieza posterior
        self.lineas_ruta = [glow_item, core_item]

        # 4. BALIZA DE DESTINO FINAL
        ultimo = puntos_camino[-1]
        dest_x = ultimo[1] * c_size + half_cell
        dest_y = ultimo[0] * c_size + half_cell

        # Invocamos el marcador visual de destino
        if hasattr(self, "dibujar_punto"):
            self.dibujar_punto(dest_x, dest_y, color="#00FFC6")

        # Forzar actualización visual
        if self.viewport():
            self.viewport().update()

    def limpiar_ruta(self):
        """
        Elimina de la escena las trayectorias de neón y el marcador de destino.
        Garantiza una limpieza profunda para evitar fugas de memoria.
        """
        escena = self.scene
        if not escena:
            return

        # 1. LIMPIEZA DE TRAYECTORIAS (Glow + Core)
        if hasattr(self, "lineas_ruta") and self.lineas_ruta:
            for item in self.lineas_ruta:
                try:
                    # Verificación de existencia en escena (Prevención de Crash)
                    if item and item.scene() == escena:
                        escena.removeItem(item)
                except (RuntimeError, Exception):
                    pass
            self.lineas_ruta.clear()
        else:
            self.lineas_ruta = []

        # 2. LIMPIEZA DEL MARCADOR DE DESTINO
        if hasattr(self, "punto_destino_item") and self.punto_destino_item:
            try:
                if self.punto_destino_item.scene() == escena:
                    escena.removeItem(self.punto_destino_item)
            except (RuntimeError, Exception):
                pass
            finally:
                self.punto_destino_item = None

        # 3. LIMPIEZA DE ETIQUETAS DE DISTANCIA (Si existen)
        if hasattr(self, "label_distancia") and self.label_distancia:
            try:
                if self.label_distancia.scene() == escena:
                    escena.removeItem(self.label_distancia)
            except:
                pass
            finally:
                self.label_distancia = None

        # Refresco visual para borrar rastro de "ghosting"
        if self.viewport():
            self.viewport().update()

    # --- INICIO BLOQUE: SISTEMA DE POSICIONAMIENTO Y ANIMACIÓN UNIFICADO ---

    def animar_marcador_proximidad(self):
        """
        MOTOR DE RENDERIZADO (30 FPS):
        - Gestiona Movimiento Suave (Lerp)
        - Seguimiento de Cámara (Auto-Pan)
        - HUD de Proximidad y Animación de Destino
        """
        import math

        from PyQt6.QtCore import QPointF

        # 0. VALIDACIÓN DE INTEGRIDAD
        if not hasattr(self, "pos_objetivo_operario") or not self.icono_operario:
            if (
                hasattr(self, "timer_animacion_operario")
                and self.timer_animacion_operario
            ):
                self.timer_animacion_operario.stop()
            return

        # 1. LÓGICA DE MOVIMIENTO SUAVE (LERP)
        # Ecuación: P_nueva = P_actual + (P_destino - P_actual) * factor
        actual = self.icono_operario.pos()
        objetivo = self.pos_objetivo_operario
        dist_px = math.hypot(objetivo.x() - actual.x(), objetivo.y() - actual.y())

        if dist_px < 0.5:
            # Snap final para ahorrar CPU cuando la distancia es imperceptible
            self.icono_operario.setPos(objetivo)
            self.pos_operario = objetivo
        else:
            factor = 0.15  # Suavizado (menor es más lento/fluido)
            nueva_pos = QPointF(
                actual.x() + (objetivo.x() - actual.x()) * factor,
                actual.y() + (objetivo.y() - actual.y()) * factor,
            )
            self.icono_operario.setPos(nueva_pos)
            self.pos_operario = nueva_pos

        # 2. SEGUIMIENTO DE CÁMARA (AUTO-PAN)
        if getattr(self, "rastreo_en_vivo_activo", False):
            self.centerOn(self.icono_operario)

        # 3. HUD DE PROXIMIDAD (Si hay un destino fijado)
        if hasattr(self, "punto_destino_item") and self.punto_destino_item:
            ratio = getattr(self, "ratio_px_m_h", 100.0)

            # Calculamos distancia al destino desde la posición actual del icono
            dist_dest_px = math.hypot(
                self.punto_destino_item.pos().x() - self.pos_operario.x(),
                self.punto_destino_item.pos().y() - self.pos_operario.y(),
            )
            distancia_m = dist_dest_px / ratio

            # ANIMACIÓN DEL PIN: Escalado según cercanía (Efecto Radar)
            escala = max(1.0, min(2.5, 3.0 - (distancia_m / 5.0)))

            # Protección quirúrgica para gráficos que no soportan estas transformaciones
            if hasattr(self.punto_destino_item, "setTransformOriginPoint"):
                rect = self.punto_destino_item.boundingRect()
                self.punto_destino_item.setTransformOriginPoint(rect.center())

            if hasattr(self.punto_destino_item, "setScale"):
                self.punto_destino_item.setScale(escala)

            # ACTUALIZACIÓN DEL STATUS BAR (HUD)
            try:
                main_window = self.window()
                status_bar = getattr(main_window, "statusBar", lambda: None)()

                if status_bar:
                    base_style = "font-family: 'Segoe UI'; font-weight: 900; font-size: 11px; padding-left: 10px;"

                    if distancia_m < 1.2:  # DESTINO ALCANZADO
                        color_alerta = "#FF4B4B"  # Rojo Neón
                        status_bar.setStyleSheet(
                            f"background-color: #3D1010; color: {color_alerta}; {base_style}"
                        )
                        status_bar.showMessage(
                            f"🎯 DESTINO ALCANZADO: {distancia_m:.2f} m", 1000
                        )

                        # Efecto de parpadeo (Blink) al llegar
                        opacidad = (
                            0.3
                            if (int(QDateTime.currentMSecsSinceEpoch() / 200) % 2 == 0)
                            else 1.0
                        )
                        self.punto_destino_item.setOpacity(opacidad)
                        if hasattr(main_window, "_actualizar_piloto_rastreo"):
                            main_window._actualizar_piloto_rastreo(False)

                    elif distancia_m < 5.0:  # APROXIMACIÓN
                        status_bar.setStyleSheet(
                            f"background-color: #1A1A0D; color: #FFCC00; {base_style}"
                        )
                        status_bar.showMessage(
                            f"📡 APROXIMACIÓN FINAL: {distancia_m:.1f} m", 1000
                        )
                        self.punto_destino_item.setOpacity(1.0)

                    else:  # NAVEGACIÓN NORMAL
                        color_radar = "#00FFC6"
                        status_bar.setStyleSheet(
                            f"background-color: #0D1117; color: {color_radar}; {base_style}"
                        )
                        status_bar.showMessage(
                            f"🚀 NAVEGANDO: {distancia_m:.1f} m hasta el objetivo", 1000
                        )
                        self.punto_destino_item.setOpacity(1.0)
            except Exception:
                pass  # Evita errores si la ventana se cierra durante el timer

    def detener_radar(self):
        """Restaura la interfaz al estado base y limpia animaciones."""
        if hasattr(self, "punto_destino_item") and self.punto_destino_item:
            self.punto_destino_item.setScale(1.0)
            self.punto_destino_item.setOpacity(1.0)

        status_bar = self.window().statusBar()
        # Volvemos al estilo oscuro estándar de la app
        status_bar.setStyleSheet("background-color: #0D1117; color: #8B949E;")
        status_bar.clearMessage()

        if hasattr(self, "_ultimo_beep_time"):
            delattr(self, "_ultimo_beep_time")

    def obtener_muros_serializados(self):
        """
        Exporta la infraestructura a JSON y genera la matriz binaria de colisión.
        AJUSTE QUIRÚRGICO: Verificación estricta de escena y serialización NumPy.
        """
        from datetime import datetime

        import numpy as np

        # 1. EXTRACCIÓN SEGURA DE MUROS
        lista_muros = []
        # Recuperamos los muros directamente del historial del visor
        muros_items = getattr(self, "historial_muros", [])
        escena = QGraphicsView.scene(self)

        for m in muros_items:
            try:
                # Validamos que el ítem siga vivo y pertenezca a la escena actual
                if m and m.scene() == escena:
                    linea = m.line()
                    lista_muros.append(
                        {
                            "x1": round(linea.x1(), 2),
                            "y1": round(linea.y1(), 2),
                            "x2": round(linea.x2(), 2),
                            "y2": round(linea.y2(), 2),
                            "tipo": "MURO_TECNICO",
                        }
                    )
            except (AttributeError, RuntimeError):
                continue

        # 2. GESTIÓN DE LA MATRIZ DE COLISIÓN (A*)
        if hasattr(self, "matriz_obstaculos") and self.matriz_obstaculos is not None:
            # Convertimos a uint8 para asegurar que los valores sean 0 o 1
            matriz_final = self.matriz_obstaculos.astype(np.uint8)
        else:
            # Fallback si no hay matriz: crear una basada en el tamaño de la escena
            rect = (
                self.sceneRect()
                if callable(self.sceneRect)
                else getattr(self, "sceneRect", None)
            )
            ancho = int(rect.width()) if rect and rect.width() > 0 else 800
            alto = int(rect.height()) if rect and rect.height() > 0 else 600
            matriz_final = np.zeros((alto, ancho), dtype=np.uint8)

        # 3. EMPAQUETADO DE DATOS PARA PERSISTENCIA
        datos_mapa = {
            "muros_vectores": lista_muros,
            "matriz_colision": matriz_final.tolist(),  # Convertir a lista para JSON
            "escala_px_m": float(getattr(self, "ratio_px_m_h", 1.0)),
            "fecha_guardado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Actualizamos la referencia local por si otros módulos la consultan
        self.matriz_binaria = datos_mapa["matriz_colision"]

        return json.dumps(datos_mapa, ensure_ascii=False)

    def importar_datos_estructurales(self, json_datos):
        """
        Reconstruye el entorno físico (muros y nodos) desde la persistencia.
        AJUSTE QUIRÚRGICO: Limpieza protegida y reconstrucción del trazado A*.
        """
        from PyQt6.QtCore import QPointF, Qt
        from PyQt6.QtGui import QColor, QPen

        if not json_datos:
            return

        try:
            # Parseo adaptativo (acepta string o dict directamente)
            datos = (
                json.loads(json_datos) if isinstance(json_datos, str) else json_datos
            )
            escena = QGraphicsView.scene(self)

            # --- 1. LIMPIEZA RADICAL PROTEGIDA ---
            if escena:
                # CRÍTICO: list() crea una copia estática para que la eliminación
                # de ítems no rompa el iterador de la escena.
                for item in list(escena.items()):
                    if str(item.data(0)) == "MURO_TECNICO":
                        try:
                            escena.removeItem(item)
                        except RuntimeError:
                            continue

            if hasattr(self, "historial_muros"):
                self.historial_muros.clear()

            # Reset de la matriz de obstáculos antes de re-rasterizar
            if (
                hasattr(self, "matriz_obstaculos")
                and self.matriz_obstaculos is not None
            ):
                self.matriz_obstaculos.fill(0)

            # --- 2. RECONSTRUCCIÓN DE MUROS ---
            muros = datos.get("muros_vectores", datos.get("muros", []))

            # Pen con estética "Warning Red" para muros técnicos
            pen_muro = QPen(QColor("#F85149"), 3)
            pen_muro.setCapStyle(Qt.PenCapStyle.RoundCap)

            muros_reconstruidos = 0
            for m in muros:
                try:
                    x1, y1 = float(m["x1"]), float(m["y1"])
                    x2, y2 = float(m["x2"]), float(m["y2"])

                    if escena:
                        linea_item = escena.addLine(x1, y1, x2, y2, pen_muro)
                        linea_item.setData(0, "MURO_TECNICO")
                        linea_item.setZValue(5)  # Capa superior a la imagen de fondo

                        if hasattr(self, "historial_muros"):
                            self.historial_muros.append(linea_item)

                        # Rasterizado en la matriz de navegación A*
                        if hasattr(self, "marcar_muro_en_matriz"):
                            self.marcar_muro_en_matriz(
                                QPointF(x1, y1), QPointF(x2, y2), es_muro_preciso=True
                            )
                        muros_reconstruidos += 1
                except (KeyError, TypeError, ValueError):
                    continue

            # --- 3. RECONSTRUCCIÓN DE PUNTOS/NODOS ---
            puntos = datos.get("puntos_estructurales", [])
            for p in puntos:
                try:
                    if hasattr(self, "colocar_marcador_3d"):
                        self.colocar_marcador_3d(
                            QPointF(float(p["x"]), float(p["y"])),
                            p.get("tipo", "UBICACIÓN"),
                            str(p.get("nombre", "SN")).upper(),
                        )
                except (KeyError, TypeError, ValueError):
                    continue

            # --- 4. RESTAURACIÓN DE ESCALA ---
            escala_valor = float(datos.get("escala_px_m", 1.0))
            self.ratio_px_m_h = self.ratio_px_m_v = escala_valor
            if hasattr(self, "pixeles_por_metro"):
                self.pixeles_por_metro = escala_valor

            # Refresco final del área visible
            if hasattr(self, "viewport") and self.viewport():
                self.viewport().update()

            print(f"✅ IMPORTACIÓN EXITOSA: {muros_reconstruidos} muros procesados.")

        except Exception as e:
            print(f"❌ FALLO CRÍTICO EN IMPORTACIÓN: {e}")

    def confirmar_instalacion_satelite(self, pos, main):
        """
        Diálogo de confirmación final.
        Blindado con inyección de fuente directa (QFont) para saltar errores de CSS.
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QDialog, QFrame, QLabel, QPushButton, QVBoxLayout

        diag = QDialog(self)
        diag.setFixedSize(450, 280)
        diag.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        diag.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        main_lyt = QVBoxLayout(diag)
        main_lyt.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setStyleSheet(
            "QFrame { background-color: #0D1117; border: 2px solid #00FFC6; border-radius: 18px; }"
            " QLabel { color: #E6EDF3; border: none; background: transparent; }"
        )

        lyt = QVBoxLayout(container)
        lyt.setContentsMargins(28, 24, 28, 24)
        lyt.setSpacing(14)

        lbl_titulo = QLabel("📡  " + tr("ubic.confirm_sat_q", default="¿CONFIRMAR UBICACIÓN DEL SATÉLITE?"))
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_titulo.setWordWrap(True)
        lbl_titulo.setStyleSheet(
            "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900; font-size: 15px;"
        )
        lyt.addWidget(lbl_titulo)
        lyt.addStretch()

        btn_confirmar = QPushButton(tr("ubic.confirm_finish", default="CONFIRMAR Y FINALIZAR"))
        btn_seguir = QPushButton(tr("ubic.keep_installing", default="SEGUIR INSTALANDO"))
        btn_cancelar = QPushButton(tr("ubic.cancel_op", default="CANCELAR OPERACIÓN"))

        btn_confirmar.setStyleSheet(
            "QPushButton { background-color: #1ED760; color: #0D1117;"
            " border: 2px solid #1ED760; border-radius: 10px;"
            " font-family: 'Segoe UI'; font-weight: 900; font-size: 13px; padding: 10px 14px; }"
            " QPushButton:hover { background-color: transparent; color: #1ED760; border: 2px solid #1ED760; }"
        )
        btn_seguir.setStyleSheet(
            "QPushButton { background-color: transparent; color: #00FFC6;"
            " border: 2px solid #00FFC6; border-radius: 10px;"
            " font-family: 'Segoe UI'; font-weight: 900; font-size: 13px; padding: 10px 14px; }"
            " QPushButton:hover { background-color: #00FFC6; color: #0D1117; }"
        )
        btn_cancelar.setStyleSheet(
            "QPushButton { background-color: #21262D; color: #8B949E;"
            " border: 1px solid #30363D; border-radius: 10px;"
            " font-family: 'Segoe UI'; font-weight: 900; font-size: 13px; padding: 10px 14px; }"
            " QPushButton:hover { background-color: #FFFFFF; color: #0D1117; }"
        )

        for btn in [btn_confirmar, btn_seguir, btn_cancelar]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            lyt.addWidget(btn)

        main_lyt.addWidget(container)

        # Conexiones: 1=Finalizar, 2=Seguir, 0=Cancelar
        btn_confirmar.clicked.connect(lambda: diag.done(1))
        btn_seguir.clicked.connect(lambda: diag.done(2))
        btn_cancelar.clicked.connect(lambda: diag.done(0))

        resultado = diag.exec()

        # --- PROCESAMIENTO DE RESULTADOS ---
        if resultado == 0:  # CANCELAR
            self.modo_satelite = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if hasattr(self, "viewport"):
                self.viewport().update()

            if hasattr(self, "configurar_modo"):
                self.configurar_modo("NAVEGACION")

            if self.window().statusBar():
                self.window().statusBar().clearMessage()

        elif resultado == 1 or resultado == 2:
            # 1. Registrar el satélite en la base de datos
            if hasattr(main, "registrar_satelite_db"):
                main.registrar_satelite_db(permiso_clic=True, pos=pos)
                self.satelites_instalados_sesion = (
                    getattr(self, "satelites_instalados_sesion", 0) + 1
                )

            if resultado == 1:  # CONFIRMAR Y FINALIZAR
                self.modo_satelite = False
                self.setCursor(Qt.CursorShape.ArrowCursor)
                if hasattr(self, "viewport"):
                    self.viewport().update()

                if hasattr(self, "configurar_modo"):
                    self.configurar_modo("NAVEGACION")

                if hasattr(self, "mostrar_mensaje_final"):
                    self.mostrar_mensaje_final(self.satelites_instalados_sesion)

                self.satelites_instalados_sesion = 0  # Limpieza

                if self.window().statusBar():
                    self.window().statusBar().clearMessage()

            else:  # SEGUIR INSTALANDO (resultado == 2)
                # Re-forzado de modo y cursor cruceta
                self.modo_satelite = True
                self.setCursor(Qt.CursorShape.CrossCursor)
                if hasattr(self, "viewport"):
                    self.viewport().update()  # Vital para que no vuelva a flecha

    def mousePressEvent(self, event):
        """
        Cerebro de detección de clics coordinado con flujo de calibración,
        pintado de muros y ubicación de activos.
        Estilo Segoe UI Bold (900/800) y blindaje de cursor Crosshair.
        """
        from PyQt6.QtCore import QLineF, Qt
        from PyQt6.QtGui import QBrush, QColor, QFont, QPen
        from PyQt6.QtWidgets import QDialog, QFrame, QLabel, QPushButton, QVBoxLayout

        # 1. ACCESO SEGURO A LA ESCENA Y VENTANA MAIN
        escena = QGraphicsView.scene(self)
        if not escena:
            return

        # CAPTURA MAESTRA: Guardamos la posición del clic en la escena
        pos_escena = self.mapToScene(event.pos())
        self.ultimo_click_escena = pos_escena

        # Búsqueda dinámica del objeto Main para acceder a sus métodos
        main = getattr(self, "parent_window", None) or self.parent()
        while (
            main
            and not hasattr(main, "abrir_formulario_ubicacion_estanteria")
            and hasattr(main, "parent")
        ):
            parent_obj = main.parent()
            if not parent_obj:
                break
            main = parent_obj

        # --- FUNCIÓN AUXILIAR: DIÁLOGOS DE INSTRUCCIÓN (ESTILO CAPTURA 2) ---
        def mostrar_aviso_paso(titulo, mensaje, color_borde="#00FFFF"):
            diag = QDialog(main)
            diag.setFixedSize(440, 260)
            diag.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
            )
            diag.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

            # FUENTES FORZADAS (Segoe UI 900)
            f_tit = QFont("Segoe UI", 15, QFont.Weight.Black)
            f_msg = QFont("Segoe UI", 11, QFont.Weight.Bold)
            f_btn = QFont("Segoe UI", 12, QFont.Weight.Bold)

            main_lyt = QVBoxLayout(diag)
            main_lyt.setContentsMargins(0, 0, 0, 0)

            container = QFrame()
            container.setObjectName("MainContainer")
            container.setStyleSheet(
                f"""
                QFrame#MainContainer {{
                    background-color: #0D1117; 
                    border: 2px solid {color_borde}; 
                    border-radius: 20px;
                }}
                QLabel {{ color: #E6EDF3; border: none; }}
                QPushButton {{ 
                    background-color: #1E1E1E; 
                    color: {color_borde}; 
                    border: 1px solid {color_borde};
                    border-radius: 10px; 
                    padding: 12px 30px; 
                }}
                QPushButton:hover {{ 
                    background-color: {color_borde}; 
                    color: #0D1117; 
                }}
            """
            )

            inner_lyt = QVBoxLayout(container)
            inner_lyt.setContentsMargins(35, 25, 35, 25)
            inner_lyt.setSpacing(15)

            tit = QLabel(titulo.upper())
            tit.setFont(f_tit)
            tit.setStyleSheet(f"color: {color_borde}; letter-spacing: 1.5px;")
            tit.setAlignment(Qt.AlignmentFlag.AlignCenter)

            txt = QLabel(mensaje)
            txt.setFont(f_msg)
            txt.setTextFormat(Qt.TextFormat.RichText)
            txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            txt.setWordWrap(True)

            btn = QPushButton(tr("ubic.understood_continue", default="ENTENDIDO, CONTINUAR"))
            btn.setFont(f_btn)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(diag.accept)

            inner_lyt.addWidget(tit)
            inner_lyt.addWidget(txt)
            inner_lyt.addStretch()
            inner_lyt.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

            main_lyt.addWidget(container)
            diag.exec()

            # --- REFUERZO DE CURSOR TRAS CERRAR VENTANA ---
            if getattr(self, "modo_calibrar", False) or getattr(
                self, "modo_satelite", False
            ):
                self.setFocus()
                self.setCursor(Qt.CursorShape.CrossCursor)
                if hasattr(self, "viewport"):
                    self.viewport().setCursor(Qt.CursorShape.CrossCursor)

        if (
            event.button() == Qt.MouseButton.LeftButton
            and not getattr(self, "modo_calibrar", False)
            and not getattr(self, "modo_pintar", False)
            and not getattr(self, "modo_satelite", False)
            and getattr(self, "estado_interaccion", "NAVEGACION") == "NAVEGACION"
        ):
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            if hasattr(self, "viewport"):
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

        # --- A. CLIC DERECHO: MENÚ DE BORRADO ---
        if event.button() == Qt.MouseButton.RightButton:
            # Buscamos ítems bajo el cursor (usamos un radio de búsqueda pequeño para mayor tolerancia)
            items_en_clic = self.items(event.pos())

            for item in items_en_clic:
                # Obtenemos el tipo y lo normalizamos
                data_tipo = item.data(1)
                tipo_item = str(data_tipo or "").upper()

                # AMPLIACIÓN: Añadimos MARCADOR y UBICACIÓN a la lista de detección
                tipos_validos = [
                    "SATÉLITE",
                    "ESTANTERÍA",
                    "INFRAESTRUCTURA",
                    "PIN",
                    "MARCADOR",
                    "UBICACIÓN",
                ]

                if tipo_item in tipos_validos:
                    # Normalización: Si es cualquier tipo de pin, lo tratamos como ESTANTERÍA para el borrado
                    if tipo_item in ["PIN", "MARCADOR", "UBICACIÓN"]:
                        item.setData(1, "ESTANTERÍA")

                    if hasattr(self, "mostrar_menu_borrado"):
                        # Forzamos la captura del menú con la posición global del evento
                        self.mostrar_menu_borrado(
                            event.globalPosition().toPoint(), item, main
                        )
                        # Consumimos el evento para evitar que se propague al fondo
                        event.accept()
                        return
            return

        # --- B. PRIORIDAD CRÍTICA: MODO UBICACIÓN DE SATÉLITE ---
        if getattr(self, "modo_satelite", False):
            self.setCursor(Qt.CursorShape.CrossCursor)
            if hasattr(self, "viewport"):
                self.viewport().setCursor(Qt.CursorShape.CrossCursor)

            if hasattr(self, "confirmar_instalacion_satelite"):
                self.confirmar_instalacion_satelite(pos_escena, main)
                self.window().cambios_sin_guardar = True

            if getattr(self, "modo_satelite", False):
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                if hasattr(self, "viewport"):
                    self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            return

        # --- C. GESTIÓN DE CURSOR GENERAL ---
        if (
            getattr(self, "modo_calibrar", False)
            or getattr(self, "modo_pintar", False)
            or "UBICAR" in getattr(self, "estado_interaccion", "")
        ):
            self.setCursor(Qt.CursorShape.CrossCursor)
            if hasattr(self, "viewport"):
                self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            if hasattr(self, "viewport"):
                self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)

        # --- D. OTROS MODOS (Estantería, Ancla, Calibración, Pintar) ---
        if (
            getattr(main, "esperando_ubicacion_estanteria", False)
            or getattr(self, "estado_interaccion", "") == "UBICAR_ESTANTERIA"
        ):
            main.esperando_ubicacion_estanteria = False
            if hasattr(self, "configurar_modo"):
                self.configurar_modo("NAVEGACION")
            main.abrir_formulario_ubicacion_estanteria(permiso_clic=True)
            return

        if getattr(self, "esperando_ancla_0", False):
            snapshot_antes = main._snapshot_pre_calibracion or (
                main._obtener_snapshot_mapa()
                if hasattr(main, "_obtener_snapshot_mapa")
                else None
            )
            self.punto_ancla = pos_escena
            self.esperando_ancla_0 = False
            if hasattr(self, "configurar_modo"):
                self.configurar_modo("NAVEGACION")
            self.dibujar_marca_origen(pos_escena)
            if hasattr(main, "_apilar_accion_mapa"):
                snapshot_despues = main._obtener_snapshot_mapa()
                tipo_accion = (
                    "calibracion"
                    if getattr(main, "p_x_fin", None) and getattr(main, "p_y_fin", None)
                    else "origen"
                )
                main._apilar_accion_mapa(
                    tipo_accion, snapshot_antes or {}, snapshot_despues
                )
                main._snapshot_pre_calibracion = None
            if hasattr(main, "actualizar_estado_bloqueo"):
                main.actualizar_estado_bloqueo(False)
            return

        if getattr(self, "modo_calibrar", False):
            paso = getattr(main, "paso_calibracion", 1)
            radius = 6
            color_y, color_x = QColor("#00F0FF"), QColor("#FFEA00")

            if paso == 1:
                main.p_y_inicio = pos_escena
                self.m_y1 = escena.addEllipse(
                    pos_escena.x() - radius,
                    pos_escena.y() - radius,
                    12,
                    12,
                    QPen(color_y, 2),
                    QBrush(color_y),
                )
                self.m_y1.setData(0, "CALIB_MARKER")
                self.m_y1.setZValue(2200)
                main.paso_calibracion = 2
            elif paso == 2:
                main.p_y_fin = pos_escena
                self.m_y2 = escena.addEllipse(
                    pos_escena.x() - radius,
                    pos_escena.y() - radius,
                    12,
                    12,
                    QPen(color_y, 2),
                    QBrush(color_y),
                )
                self.m_y2.setData(0, "CALIB_MARKER")
                self.m_y2.setZValue(2200)
                self.linea_y = escena.addLine(
                    QLineF(main.p_y_inicio, main.p_y_fin),
                    QPen(color_y, 2, Qt.PenStyle.DashLine),
                )
                self.linea_y.setData(0, "CALIB_LINE")
                self.linea_y.setZValue(2100)
                mostrar_aviso_paso(
                    "↕️ EJE Y REGISTRADO",
                    "Seleccione ahora el punto de inicio de la <b style='color: #FFEA00;'>pared HORIZONTAL</b>.",
                    "#FFEA00",
                )
                main.paso_calibracion = 3
            elif paso == 3:
                main.p_x_inicio = pos_escena
                self.m_x1 = escena.addEllipse(
                    pos_escena.x() - radius,
                    pos_escena.y() - radius,
                    12,
                    12,
                    QPen(color_x, 2),
                    QBrush(color_x),
                )
                self.m_x1.setData(0, "CALIB_MARKER")
                self.m_x1.setZValue(2200)
                main.paso_calibracion = 4
            elif paso == 4:
                main.p_x_fin = pos_escena
                self.m_x2 = escena.addEllipse(
                    pos_escena.x() - radius,
                    pos_escena.y() - radius,
                    12,
                    12,
                    QPen(color_x, 2),
                    QBrush(color_x),
                )
                self.m_x2.setData(0, "CALIB_MARKER")
                self.m_x2.setZValue(2200)
                self.linea_x = escena.addLine(
                    QLineF(main.p_x_inicio, main.p_x_fin),
                    QPen(color_x, 2, Qt.PenStyle.DashLine),
                )
                self.linea_x.setData(0, "CALIB_LINE")
                self.linea_x.setZValue(2100)
                dist_x = QLineF(main.p_x_inicio, main.p_x_fin).length()
                dist_y = QLineF(main.p_y_inicio, main.p_y_fin).length()
                self.window().cambios_sin_guardar = True
                self.modo_calibrar = False
                main.finalizar_calibracion_escala(dist_x, dist_y)
            return

        if getattr(self, "modo_pintar", False):
            self.setCursor(Qt.CursorShape.CrossCursor)
            if hasattr(self, "viewport"):
                self.viewport().setCursor(Qt.CursorShape.CrossCursor)

            if not getattr(self, "punto_inicio_muro", None):
                self.punto_inicio_muro = pos_escena
            else:
                snapshot_antes = (
                    main._obtener_snapshot_mapa()
                    if hasattr(main, "_obtener_snapshot_mapa")
                    else None
                )
                pen = QPen(QColor("#FF4B4B"), 3, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                linea = escena.addLine(QLineF(self.punto_inicio_muro, pos_escena), pen)
                linea.setData(0, "MURO_TECNICO")
                self.window().cambios_sin_guardar = True

                if not hasattr(self, "historial_muros"):
                    self.historial_muros = []
                self.historial_muros.append(linea)

                if hasattr(self, "marcar_muro_en_matriz"):
                    self.marcar_muro_en_matriz(
                        self.punto_inicio_muro, pos_escena, es_muro_preciso=True
                    )
                if hasattr(main, "_apilar_accion_mapa"):
                    main._apilar_accion_mapa(
                        "muro",
                        snapshot_antes or {},
                        main._obtener_snapshot_mapa(),
                    )
                    main._actualizar_botones_historial()
                self.punto_inicio_muro = None
            return

        super().mousePressEvent(event)

    def colocar_marcador_3d(
        self, pos, tipo, nombre, color="#00FF00", epc=None, modo_carga=False
    ):
        """
        Despliega un pin interactivo con HUD de datos.
        Mantiene el diseño intacto y asegura el posicionamiento absoluto sobre el nuevo plano.
        """
        import re

        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
        from PyQt6.QtWidgets import QLabel

        # --- 1. TRATAMIENTO DE TEXTO E ICONOGRAFÍA ---
        # Limpia coordenadas antiguas que pudieran venir pegadas en el nombre
        nombre_limpio = re.sub(
            r"\s*-?\d+(\.\d+)?M,?\s*-?\d+(\.\d+)?M", "", nombre
        ).strip()
        tipo_up = tipo.upper() if tipo else "DESCONOCIDO"
        icono = "🛰️" if "SAT" in tipo_up or (epc and "SAT" in epc.upper()) else "📍"

        # --- 2. CLASE INTERNA PARA INTERACCIÓN (Clics y Menús) ---
        class PinClickeable(QLabel):
            def __init__(self, texto, visor, parent_proxy=None):
                super().__init__(texto)
                self.visor = visor
                self.parent_proxy = parent_proxy
                self.etiqueta_vinculada = None
                self.setCursor(Qt.CursorShape.PointingHandCursor)

            def mousePressEvent(self, event):
                # Botón Izquierdo: Alterna la visibilidad del HUD de coordenadas
                if (
                    event.button() == Qt.MouseButton.LeftButton
                    and self.etiqueta_vinculada
                ):
                    self.etiqueta_vinculada.setVisible(
                        not self.etiqueta_vinculada.isVisible()
                    )

                # Botón Derecho: Despliega el menú de edición/borrado
                elif event.button() == Qt.MouseButton.RightButton:
                    if hasattr(self.visor, "mostrar_menu_borrado"):
                        self.visor.mostrar_menu_borrado(
                            event.globalPosition().toPoint(),
                            self.parent_proxy,
                            self.visor,
                        )
                super().mousePressEvent(event)

        # --- 3. CONFIGURACIÓN DEL WIDGET DEL PIN ---
        label_pin = PinClickeable(icono, self)
        label_pin.setFixedSize(10, 10)
        label_pin.setStyleSheet("background: transparent; font-size: 7px;")
        label_pin.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Validación de la escena activa
        escena_obj = QGraphicsView.scene(self)
        if not escena_obj:
            print("⚠️ Error: No hay escena activa para colocar el marcador.")
            return None

        # --- 4. CREACIÓN DEL PROXY Y POSICIONAMIENTO EN EL MAPA ---
        proxy = escena_obj.addWidget(label_pin)
        label_pin.parent_proxy = proxy

        # Z-Value Extremo: Asegura que el pin NUNCA quede tapado por los muros (180) ni el plano (-10000)
        proxy.setZValue(10000)

        # False = El pin hará zoom junto con el plano. True = El pin mantendrá su tamaño en pantalla.
        proxy.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, False)

        # Centrado exacto: restamos la mitad del tamaño (10/2 = 5) a las coordenadas X e Y
        proxy.setPos(pos.x() - 5, pos.y() - 5)

        # Datos incrustados para persistencia y búsquedas futuras
        epc_final = epc if epc else f"ID_{int(pos.x())}_{int(pos.y())}"
        proxy.setData(0, epc_final)
        proxy.setData(1, tipo_up)
        proxy.setData(2, nombre_limpio)   # needed by mostrar_menu_borrado
        proxy.setData(10, "ICONO_INTERACTIVO")

        # --- 5. CREACIÓN DEL HUD (nativo QGraphicsItem — esquinas redondeadas reales) ---
        # QLabel/QGraphicsProxyWidget no puede clipar el fill al border-radius; un
        # QGraphicsItem con QPainterPath.addRoundedRect sí lo hace correctamente.
        factor = getattr(self, "ratio_px_m_h", 1.0)
        if factor <= 0:
            factor = 1.0

        str_x, str_y = f"{pos.x()/factor:.2f}", f"{pos.y()/factor:.2f}"
        hud_texto = f"{nombre_limpio.upper()}\n({str_x}m, {str_y}m)"

        class HUDItem(QGraphicsItem):
            def __init__(self_, texto):
                super().__init__()
                self_._texto = texto
                self_._font = QFont("Segoe UI", 5, QFont.Weight.Bold)
                fm = QFontMetrics(self_._font)
                lineas = texto.split("\n")
                w = max(fm.horizontalAdvance(l) for l in lineas) + 6
                h = fm.height() * len(lineas) + 4
                self_._rect = QRectF(0, 0, w, h)

            def boundingRect(self_):
                return self_._rect

            def paint(self_, painter, option, widget=None):
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                path = QPainterPath()
                path.addRoundedRect(self_._rect, 4, 4)
                painter.fillPath(path, QColor(13, 17, 23, 245))
                painter.setPen(QPen(QColor("#00FF00"), 1))
                painter.drawPath(path)
                painter.setFont(self_._font)
                painter.setPen(QColor("#00FF00"))
                painter.drawText(
                    self_._rect.adjusted(3, 2, -3, -2),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    self_._texto,
                )

        hud_item = HUDItem(hud_texto)
        hud_item.setParentItem(proxy)
        hud_item.setPos(12, -6)
        hud_item.setZValue(10001)
        hud_item.setVisible(False)

        # Vinculamos el HUD al pin para que el clic lo muestre/oculte
        label_pin.etiqueta_vinculada = hud_item

        # --- 6. REGISTRO EN MEMORIA ---
        if not hasattr(self, "puntos_interactivos"):
            self.puntos_interactivos = []
        self.puntos_interactivos.append({"pin": proxy, "epc": epc_final})

        if not modo_carga:
            self.cambios_sin_guardar = True

        return proxy

    def dibujar_marca_origen(self, pos, registrar_historial=True, mostrar_guia=True):
        """
        Dibuja la marca visual de Punto de Origen GPS (Areola Morada).
        Finaliza el flujo de calibración y activa la guía de muros.
        """
        from PyQt6 import sip
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QBrush, QColor, QFont, QPen

        escena = QGraphicsView.scene(self)
        if not escena:
            return

        # 1. LIMPIEZA TOTAL CON FILTRO DE SEGURIDAD
        if hasattr(self, "grupo_marca_origen") and self.grupo_marca_origen:
            for item in self.grupo_marca_origen:
                try:
                    if item and not sip.isdeleted(item):
                        if item.scene():
                            escena.removeItem(item)
                except:
                    continue

        self.grupo_marca_origen = []
        radio = 12
        color_morado = QColor("#BC13FE")

        # 2. ELEMENTOS VISUALES (Aura de precisión)
        areola = escena.addEllipse(
            pos.x() - radio,
            pos.y() - radio,
            radio * 2,
            radio * 2,
            QPen(color_morado, 2, Qt.PenStyle.DashLine),
            QBrush(QColor(188, 19, 254, 40)),
        )
        areola.setZValue(5000)  # Máxima prioridad visual
        areola.setData(0, "PIN_ORIGEN")

        centro = escena.addEllipse(
            pos.x() - 3,
            pos.y() - 3,
            6,
            6,
            QPen(Qt.GlobalColor.white, 1),
            QBrush(color_morado),
        )
        centro.setZValue(5001)
        centro.setData(0, "PIN_ORIGEN")

        # 3. ETIQUETA INTELIGENTE (No escala con el zoom)
        txt = escena.addText("ORIGEN GPS (0,0)m")
        txt.setDefaultTextColor(color_morado)
        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        txt.setFont(font)
        # Esto evita que el texto se deforme al hacer zoom al plano
        txt.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        txt.setPos(pos.x() + radio + 5, pos.y() - 15)
        txt.setZValue(5002)
        txt.setData(0, "PIN_ORIGEN")

        self.item_ancla = areola
        self.grupo_marca_origen.extend([areola, centro, txt])

        # 4. REGISTRO DE COORDENADAS
        self.punto_ancla = pos
        self.coord_ancla_x = pos.x()
        self.coord_ancla_y = pos.y()
        self.esperando_ancla_0 = False

        self.viewport().update()

        # 5. GATILLO DE UI Y RECALIBRACIÓN
        win = self.window()
        if not win:
            return

        # btn_escala is permanently connected to win._clic_boton_escala (stateless handler)
        if registrar_historial and hasattr(win, "guardar_escala_db"):
            try:
                win.guardar_escala_db(
                    float(getattr(self, "ratio_px_m_h", 1.0)),
                    float(getattr(self, "ratio_px_m_v", 1.0)),
                )
                # Ask for floor height, then show wall-painting guide
                if hasattr(win, "_pedir_altura_planta"):
                    win._pedir_altura_planta()
            except Exception:
                pass

        # Guide shows AFTER height dialog (only during active manual calibration)
        if mostrar_guia and hasattr(win, "mostrar_guia_muros"):
            win.mostrar_guia_muros()

        # Refresh button text from DB so it shows RECALIBRAR ESCALA correctly
        if hasattr(win, "actualizar_estado_bloqueo"):
            win.actualizar_estado_bloqueo()

        if win.statusBar():
            win.statusBar().showMessage("✅ CALIBRACIÓN COMPLETADA", 3000)

    def mouseMoveEvent(self, event):
        """
        Feedback visual 'Rubber-banding'.
        Dibuja líneas elásticas en tiempo real para Calibración y Muros.
        Incluye blindaje de cursor para evitar el cambio a mano abierta.
        """
        from PyQt6.QtCore import QLineF, Qt
        from PyQt6.QtGui import QColor, QPen

        # --- 1. BLINDAJE DE CURSOR EN MOVIMIENTO ---
        if (
            getattr(self, "modo_pintar", False)
            or getattr(self, "modo_calibrar", False)
            or getattr(self, "modo_satelite", False)
        ):
            self.setCursor(Qt.CursorShape.CrossCursor)
            if hasattr(self, "viewport"):
                self.viewport().setCursor(Qt.CursorShape.CrossCursor)

        pos_escena = self.mapToScene(event.pos())
        main = getattr(self, "parent_window", None) or self.parent()

        # Localizar main para acceder al paso_calibracion
        while (
            main and not hasattr(main, "paso_calibracion") and hasattr(main, "parent")
        ):
            parent_obj = main.parent()
            if not parent_obj:
                break
            main = parent_obj

        # Forzamos actualización visual del viewport
        if hasattr(self, "viewport"):
            self.viewport().update()

        escena = QGraphicsView.scene(self)
        if not escena:
            return

        # --- 2. PREVIEW CALIBRACIÓN (Turquesa para Y, Amarillo para X) ---
        if getattr(self, "modo_calibrar", False) and main:
            p_ref = None
            color_preview = QColor("#00F0FF")

            if getattr(main, "paso_calibracion", 0) == 2:
                p_ref = getattr(main, "p_y_inicio", None)
                color_preview = QColor("#00F0FF")
            elif getattr(main, "paso_calibracion", 0) == 4:
                p_ref = getattr(main, "p_x_inicio", None)
                color_preview = QColor("#FFEA00")

            if p_ref:
                # --- ACTIVACIÓN PROACTIVA (Watchdog) ---
                target = self
                while target:
                    if hasattr(target, "cambios_sin_guardar"):
                        target.cambios_sin_guardar = True
                    if hasattr(target, "parent") and callable(target.parent):
                        target = target.parent()
                    elif hasattr(target, "parentWidget") and callable(
                        target.parentWidget
                    ):
                        target = target.parentWidget()
                    else:
                        break

                pen = QPen(color_preview, 2, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                if (
                    not hasattr(self, "linea_temporal_cal")
                    or self.linea_temporal_cal is None
                ):
                    self.linea_temporal_cal = escena.addLine(
                        QLineF(p_ref, pos_escena), pen
                    )
                    self.linea_temporal_cal.setData(0, "CALIB_PREVIEW")
                    self.linea_temporal_cal.setZValue(2500)
                else:
                    self.linea_temporal_cal.setPen(pen)
                    self.linea_temporal_cal.setLine(QLineF(p_ref, pos_escena))
            return

        elif hasattr(self, "linea_temporal_cal") and self.linea_temporal_cal:
            escena.removeItem(self.linea_temporal_cal)
            self.linea_temporal_cal = None

        # --- 3. PREVIEW MUROS (Rojo Industrial, SIEMPRE DISCONTINUA) ---
        if getattr(self, "modo_pintar", False) and getattr(
            self, "punto_inicio_muro", None
        ):
            # --- ACTIVACIÓN PROACTIVA (Watchdog) ---
            target = self
            while target:
                if hasattr(target, "cambios_sin_guardar"):
                    target.cambios_sin_guardar = True
                if hasattr(target, "parent") and callable(target.parent):
                    target = target.parent()
                elif hasattr(target, "parentWidget") and callable(target.parentWidget):
                    target = target.parentWidget()
                else:
                    break

            p1 = self.punto_inicio_muro
            # Estilo consistente: Rojo, grosor 2, discontinua
            pen_muro = QPen(QColor("#FF4B4B"), 2, Qt.PenStyle.DashLine)
            pen_muro.setCosmetic(True)

            if (
                not hasattr(self, "linea_temporal_muro")
                or self.linea_temporal_muro is None
            ):
                self.linea_temporal_muro = escena.addLine(
                    QLineF(p1, pos_escena), pen_muro
                )
                self.linea_temporal_muro.setData(0, "CALIB_PREVIEW")
                self.linea_temporal_muro.setZValue(2400)
            else:
                self.linea_temporal_muro.setLine(QLineF(p1, pos_escena))
            return

        elif hasattr(self, "linea_temporal_muro") and self.linea_temporal_muro:
            # Limpiar si el modo se desactivó o no hay punto de inicio
            escena.removeItem(self.linea_temporal_muro)
            self.linea_temporal_muro = None

        super().mouseMoveEvent(event)

    # ==========================================
    # NUEVOS MÉTODOS PARA GESTIÓN DE BORRADO
    # ==========================================
    def mostrar_menu_borrado(self, pos_global, item, main):
        """
        Menú inteligente que extrae datos del ítem para Ver, Editar o Borrar.
        CORRECCIÓN: Ventana Detalles con cuerpo sólido #0D1117 y borde turquesa (estilo imagen).
        Botones con fuente Segoe UI Bold y hover turquesa (estilo app).
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import (
            QDialog,
            QFrame,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QVBoxLayout,
        )

        epc = item.data(0)
        tipo = item.data(1)
        nombre = item.data(2)

        menu = QMenu()
        menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        menu.setCursor(Qt.CursorShape.PointingHandCursor)

        fuente_segoe = QFont("Segoe UI", 10, QFont.Weight.Bold)
        menu.setFont(fuente_segoe)

        menu.setStyleSheet(
            """
            QMenu { 
                background-color: #0D1117; 
                color: #C9D1D9; 
                border: 2px solid #00FFC6; 
                border-radius: 10px; 
                padding: 5px; 
            }
            QMenu::item { 
                padding: 8px 25px; 
                border-radius: 6px; 
                background-color: transparent;
            }
            QMenu::item:selected { 
                background-color: #1C2128; 
                color: #00FFC6;
            }
            QMenu::separator {
                height: 1px;
                background: #30363D;
                margin: 5px 10px;
            }
            QAction#accion_borrar_id {
                color: #F85149;
            }
            """
        )

        accion_ver = QAction(f"👁️ Ver detalles de {nombre}", menu)
        accion_ver.setFont(fuente_segoe)
        menu.addAction(accion_ver)

        accion_edit = QAction(f"✏️ Editar {tipo}", menu)
        accion_edit.setFont(fuente_segoe)
        menu.addAction(accion_edit)

        menu.addSeparator()

        accion_del = QAction(tr("ubic.eliminar_permanentemente", default="🗑️ Eliminar permanentemente"), menu)
        accion_del.setObjectName("accion_borrar_id")
        accion_del.setFont(fuente_segoe)
        menu.addAction(accion_del)

        seleccionada = menu.exec(pos_global)

        if seleccionada == accion_ver:
            # --- VENTANA DE DETALLES (ESTILO SÓLIDO NEÓN) ---
            diag = QDialog(main)
            diag.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
            )
            diag.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

            # Contenedor que evita la transparencia
            container = QFrame()
            container.setStyleSheet(
                """
                QFrame {
                    background-color: #0D1117;
                    border: 2px solid #00FFC6;
                    border-radius: 15px;
                }
            """
            )

            layout_maestro = QVBoxLayout(diag)
            layout_maestro.addWidget(container)

            layout_interno = QVBoxLayout(container)
            layout_interno.setContentsMargins(25, 20, 25, 20)
            layout_interno.setSpacing(10)

            # Título de la ventana
            lbl_titulo = QLabel(tr("ubic.asset_details", default="DETALLES DEL ACTIVO"))
            lbl_titulo.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            lbl_titulo.setStyleSheet(
                "color: #00FFC6; border: none; background: transparent;"
            )
            lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout_interno.addWidget(lbl_titulo)

            # Información del activo
            info_texto = f"TIPO: {tipo}\nNOMBRE: {nombre}\nEPC/ID: {epc}"
            lbl_info = QLabel(info_texto)
            lbl_info.setFont(fuente_segoe)
            lbl_info.setStyleSheet(
                "color: #C9D1D9; border: none; background: transparent;"
            )
            lbl_info.setAlignment(Qt.AlignmentFlag.AlignLeft)
            layout_interno.addWidget(lbl_info)

            # Botón Aceptar con estilo unificado
            layout_btn = QHBoxLayout()
            btn_aceptar = QPushButton(tr("ubic.accept_upper", default="ACEPTAR"))
            btn_aceptar.setCursor(Qt.CursorShape.PointingHandCursor)

            # Aplicamos el estilo de botón con hover turquesa y Segoe Bold
            btn_aceptar.setStyleSheet(
                """
                QPushButton {
                    background-color: #1C2128;
                    color: #C9D1D9;
                    border: 1px solid #30363D;
                    padding: 8px 25px;
                    border-radius: 6px;
                    font-family: 'Segoe UI';
                    font-weight: 900;
                    font-size: 13px;
                    min-width: 100px;
                }
                QPushButton:hover {
                    background-color: #FFFFFF;
                    color: #0D1117;
                    border: 1px solid #FFFFFF;
                }
            """
            )
            btn_aceptar.clicked.connect(diag.accept)
            layout_btn.addStretch()
            layout_btn.addWidget(btn_aceptar)
            layout_btn.addStretch()
            layout_interno.addLayout(layout_btn)

            diag.exec()

        elif seleccionada == accion_edit:
            main.abrir_formulario_ubicacion_estanteria(
                epc_existente=epc, nombre_existente=nombre
            )

        elif seleccionada == accion_del:
            # Continuamos la cadena de mando hacia el borrado activo
            self.confirmar_borrado_activo(item, tipo, main)

    def confirmar_borrado_activo(self, item, tipo, main):
        """
        Elimina el ítem de la escena y lanza la petición de borrado a MariaDB.
        CORRECCIÓN: Botones con fuente Segoe UI Bold y hover turquesa (estilo app).
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import (
            QDialog,
            QFrame,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QVBoxLayout,
        )

        # Importación perezosa de la conexión
        try:
            from src.db.conexion import obtener_conexion
        except ImportError:
            pass

        activo_id = item.data(0)

        # 1. Configuración del Diálogo Estilo Neón
        diag = QDialog(main)
        diag.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        diag.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 2. Contenedor Maestro
        container = QFrame()
        container.setStyleSheet(
            """
            QFrame {
                background-color: #0D1117;
                border: 2px solid #00FFC6;
                border-radius: 15px;
            }
        """
        )

        layout_principal = QVBoxLayout(diag)
        layout_principal.addWidget(container)

        # 3. Layout y Componentes Internos
        layout_interno = QVBoxLayout(container)
        layout_interno.setContentsMargins(25, 20, 25, 20)
        layout_interno.setSpacing(15)

        fuente_segoe_bold = QFont("Segoe UI", 10, QFont.Weight.Bold)
        fuente_titulo = QFont("Segoe UI", 11, QFont.Weight.Bold)

        lbl_titulo = QLabel(tr("ubic.confirm_delete", default="CONFIRMAR ELIMINACIÓN"))
        lbl_titulo.setFont(fuente_titulo)
        lbl_titulo.setStyleSheet(
            "color: #00FFC6; border: none; background: transparent;"
        )
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_interno.addWidget(lbl_titulo)

        lbl_msg = QLabel(
            f"¿Estás seguro de eliminar este {tipo}?\n"
            "Esta acción lo borrará permanentemente de la base de datos."
        )
        lbl_msg.setFont(fuente_segoe_bold)
        lbl_msg.setStyleSheet("color: #C9D1D9; border: none; background: transparent;")
        lbl_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_msg.setWordWrap(True)
        layout_interno.addWidget(lbl_msg)

        # 4. Botonera
        layout_btns = QHBoxLayout()
        layout_btns.setSpacing(15)

        btn_si = QPushButton(tr("common.yes", default="SÍ"))
        btn_no = QPushButton(tr("common.no", default="NO"))

        estilo_base_boton = """
            QPushButton {
                background-color: #1C2128;
                color: #C9D1D9;
                border: 1px solid #30363D;
                padding: 10px 20px;
                border-radius: 8px;
                font-family: 'Segoe UI';
                font-weight: 900;
                font-size: 13px;
                min-width: 90px;
            }
            QPushButton:hover {
                background-color: #FFFFFF;
                border: 1px solid #FFFFFF;
                color: #0D1117;
            }
        """
        btn_si.setStyleSheet(estilo_base_boton)
        btn_no.setStyleSheet(estilo_base_boton)
        btn_si.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_no.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_si.clicked.connect(diag.accept)
        btn_no.clicked.connect(diag.reject)

        layout_btns.addWidget(btn_no)
        layout_btns.addWidget(btn_si)
        layout_interno.addLayout(layout_btns)

        # 5. Ejecución y Lógica de Borrado
        if diag.exec() == QDialog.DialogCode.Accepted:
            try:
                # A. Borrado en MariaDB
                with obtener_conexion() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "DELETE FROM ubicaciones WHERE epc = %s", (activo_id,)
                    )
                    conn.commit()

                # B. Sincronización de Lista Interna
                if hasattr(self, "puntos_interactivos"):
                    self.puntos_interactivos = [
                        p for p in self.puntos_interactivos if p["pin"] != item
                    ]

                # C. Limpieza de Escena (Detección de método o propiedad)
                escena = QGraphicsView.scene(self)
                if escena:
                    escena.removeItem(item)

                # D. Escalada de Seguridad para Bandera de Cambios
                target = main
                encontrado = False
                while target:
                    if target.__class__.__name__ == "UbicacionTiendaWindow":
                        target.cambios_sin_guardar = True
                        print(
                            f"✅ DEBUG: Bandera de cambios activada en: {target.__class__.__name__}"
                        )
                        encontrado = True
                        break

                    if hasattr(target, "parent") and callable(target.parent):
                        target = target.parent()
                    elif hasattr(target, "parentWidget") and callable(
                        target.parentWidget
                    ):
                        target = target.parentWidget()
                    else:
                        break

                if not encontrado:
                    print(
                        "⚠️ WARNING: No se localizó UbicacionTiendaWindow para marcar cambios."
                    )

                # E. Feedback Visual en Status Bar
                win = main.window()
                if win and win.statusBar():
                    win.statusBar().setStyleSheet(
                        "color: #00FFC6; font-family: 'Segoe UI'; font-weight: 900;"
                    )
                    win.statusBar().showMessage(
                        f"🗑️ {tipo.upper()} ELIMINADO CORRECTAMENTE.", 3000
                    )

            except Exception as e:
                print(f"❌ Error crítico en borrado: {e}")

    def drawForeground(self, painter, rect):
        """
        Renderizado de precisión:
        1. Ghost Red: Matriz de navegación A* optimizada por vista.
        2. Cruceta Técnica: Guía dinámica con colores de estado.
        """
        from PyQt6.QtCore import QPointF, Qt
        from PyQt6.QtGui import QBrush, QColor, QPen

        # --- 1. GHOST RED (AURA DE COLISIÓN) ---
        if (
            (
                getattr(self, "mostrar_matriz", False)
                or getattr(self, "mostrando_matriz", False)
            )
            and hasattr(self, "matriz_obstaculos")
            and self.matriz_obstaculos is not None
        ):
            painter.save()
            # Desactivamos suavizado para que los nodos se vean "pixel-perfect"
            painter.setRenderHint(painter.RenderHint.Antialiasing, False)

            color_aura = QColor(
                255, 75, 75, 120
            )  # Bajamos un poco el alpha para visibilidad
            painter.setBrush(QBrush(color_aura))
            painter.setPen(Qt.PenStyle.NoPen)

            rows, cols = self.matriz_obstaculos.shape
            size = getattr(self, "celda_size", 20)

            # Clipping: Solo iteramos sobre los nodos visibles en pantalla
            col_inicio = max(0, int(rect.left() // size))
            col_fin = min(cols, int(rect.right() // size) + 1)
            row_inicio = max(0, int(rect.top() // size))
            row_fin = min(rows, int(rect.bottom() // size) + 1)

            for r in range(row_inicio, row_fin):
                for c in range(col_inicio, col_fin):
                    if self.matriz_obstaculos[r, c] == 1:
                        painter.drawRect(
                            int(c * size), int(r * size), int(size), int(size)
                        )
            painter.restore()

        # --- 2. CRUCETA TÉCNICA DE PRECISIÓN ---
        if (
            getattr(self, "modo_pintar", False)
            or getattr(self, "modo_calibrar", False)
            or getattr(self, "esperando_ancla_0", False)
        ):
            painter.save()
            painter.setRenderHint(painter.RenderHint.Antialiasing, True)

            # Escalada de seguridad para cambios_sin_guardar
            target = self
            while target:
                if target.__class__.__name__ == "UbicacionTiendaWindow":
                    if not getattr(target, "cambios_sin_guardar", False):
                        target.cambios_sin_guardar = True
                    break
                target = target.parent() if hasattr(target, "parent") else None

            # Mapeo de posición del ratón
            pos_mouse = self.mapToScene(self.mapFromGlobal(QCursor.pos()))

            # Selección de color por modo
            if getattr(self, "esperando_ancla_0", False):
                color_cruz = QColor("#BC13FE")  # Morado
            elif getattr(self, "modo_pintar", False):
                color_cruz = QColor("#FF4B4B")  # Rojo
            else:
                color_cruz = QColor("#00FFC6")  # Turquesa

            color_cruz.setAlpha(180)

            estilo_lapiz = (
                Qt.PenStyle.DashLine
                if getattr(self, "modo_pintar", False)
                else Qt.PenStyle.SolidLine
            )

            # PEN COSMÉTICO: Clave para que no desaparezca con el zoom
            pen = QPen(color_cruz, 1, estilo_lapiz)
            pen.setCosmetic(True)
            painter.setPen(pen)

            # Ejes (Usando rect para asegurar que crucen toda la vista actual)
            painter.drawLine(
                QPointF(pos_mouse.x(), rect.top()),
                QPointF(pos_mouse.x(), rect.bottom()),
            )
            painter.drawLine(
                QPointF(rect.left(), pos_mouse.y()),
                QPointF(rect.right(), pos_mouse.y()),
            )

            # Mira telescópica
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(pos_mouse, 4, 4)
            painter.drawPoint(pos_mouse)

            painter.restore()

            # AUTO-REFRESCO: Forzamos repintado mientras el ratón se mueva en estos modos
            self.viewport().update()

    def marcar_operario(self, x_pos, y_pos, es_grid=True, salto_brusco=True):
        """
        Motor Unificado del Operario: Renderiza, inicializa y mueve el Blue Dot.
        Combina la creación del icono con el control de desplazamiento (Lerp o Salto),
        incluyendo blindaje de cámara, protección de límites y ZValue intocable.
        """
        from PyQt6.QtCore import QPointF, QTimer
        from PyQt6.QtGui import QBrush, QColor, QPen, QRadialGradient

        # --- 1. CONVERSIÓN DE COORDENADAS (Grid a Píxeles) ---
        size = getattr(self, "celda_size", 20)
        if isinstance(x_pos, QPointF):
            y_pos = x_pos.y()
            x_pos = x_pos.x()
            es_grid = False

        if es_grid:
            offset = size / 2
            # Nota: y_pos suele ser la columna (X) y x_pos la fila (Y) en la matriz
            final_x = y_pos * size + offset
            final_y = x_pos * size + offset
        else:
            final_x, final_y = x_pos, y_pos

        nueva_pos = QPointF(final_x, final_y)

        # --- 2. ACCESO SEGURO A LA ESCENA ---
        escena = QGraphicsView.scene(self)
        if not escena:
            print("⚠️ ERROR: No hay escena para marcar al operario.")
            return

        # --- 3. CREACIÓN DEL ICONO (Si es la primera vez) ---
        if not hasattr(self, "icono_operario") or not self.icono_operario:
            radius = 12
            gradient = QRadialGradient(QPointF(0, 0), radius)
            gradient.setColorAt(0.0, QColor(0, 255, 198, 255))  # Núcleo Turquesa Neón
            gradient.setColorAt(0.7, QColor(0, 255, 198, 180))  # Halo
            gradient.setColorAt(1.0, QColor(0, 255, 198, 0))  # Desvanecimiento

            self.icono_operario = escena.addEllipse(
                -radius,
                -radius,
                radius * 2,
                radius * 2,
                QPen(QColor(255, 255, 255, 100), 1.5),
                QBrush(gradient),
            )

            # PROTECCIÓN QUIRÚRGICA: Intocable por el ratón y siempre arriba
            self.icono_operario.setZValue(1000)
            self.icono_operario.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False
            )
            self.icono_operario.setData(0, "OPERARIO_SISTEMA")

            # Posición inicial forzada
            self.pos_operario = nueva_pos
            self.icono_operario.setPos(nueva_pos)

        # --- 4. CLAMPING: VALIDACIÓN DE LÍMITES DE ESCENA ---
        rect_escena = self.sceneRect()
        if not rect_escena.contains(nueva_pos):
            x_safe = max(rect_escena.left(), min(nueva_pos.x(), rect_escena.right()))
            y_safe = max(rect_escena.top(), min(nueva_pos.y(), rect_escena.bottom()))
            nueva_pos = QPointF(x_safe, y_safe)

        self.pos_objetivo_operario = nueva_pos

        # --- 5. LÓGICA DE MOVIMIENTO ---

        # CASO A: SALTO BRUSCO (Instantáneo - Teletransporte)
        if salto_brusco:
            # Apagamos motores de animación si estaban encendidos
            if (
                hasattr(self, "timer_animacion_operario")
                and self.timer_animacion_operario
                and self.timer_animacion_operario.isActive()
            ):
                self.timer_animacion_operario.stop()

            # Ejecutamos el salto
            self.icono_operario.setPos(nueva_pos)
            self.pos_operario = nueva_pos

            # Centrado de cámara si el seguimiento está vivo
            if getattr(self, "rastreo_en_vivo_activo", False):
                self.centerOn(self.icono_operario)

            # Refresco de Qt para evitar "efecto fantasma"
            if self.viewport():
                self.viewport().update()
            return

        # CASO B: MOVIMIENTO SUAVE (Animación Lerp)
        if (
            not hasattr(self, "timer_animacion_operario")
            or self.timer_animacion_operario is None
        ):
            self.timer_animacion_operario = QTimer(self)
            self.timer_animacion_operario.setInterval(
                33
            )  # Motor a ~30 FPS para fluidez

            if hasattr(self, "animar_marcador_proximidad"):
                self.timer_animacion_operario.timeout.connect(
                    self.animar_marcador_proximidad
                )

        if not self.timer_animacion_operario.isActive():
            self.timer_animacion_operario.start()


# ============================================================
# BLOQUE MOTOR DE CÁLCULO DE RUTAS A*
# ============================================================

class PathFinder:
    """
    Motor de cálculo de rutas A* de alta precisión.
    Optimizado para evitar colisiones perimetrales y cortes de esquina.
    """

    def __init__(self, matrix):
        self.matrix = matrix
        self.rows = len(matrix)
        self.cols = len(matrix[0]) if self.rows > 0 else 0

        # Definición estática de movimientos (dr, dc, costo)
        # 4 Ortogonales (1.0) + 4 Diagonales (1.414)
        self.neighbors_config = [
            (0, 1, 1.0),
            (0, -1, 1.0),
            (1, 0, 1.0),
            (-1, 0, 1.0),
            (1, 1, 1.414),
            (1, -1, 1.414),
            (-1, 1, 1.414),
            (-1, -1, 1.414),
        ]

    def heuristic(self, a, b):
        """Heurística Octil para movimiento en 8 direcciones."""
        dy = abs(a[0] - b[0])
        dx = abs(a[1] - b[1])
        return (dx + dy) + (1.41421356 - 2) * min(dx, dy)

    def get_path(self, start, end):
        """Calcula la ruta óptima evitando colisiones y cortes de vértice."""
        # 1. Limpieza de entrada
        try:
            start_node = (int(round(start[0])), int(round(start[1])))
            end_node = (int(round(end[0])), int(round(end[1])))
        except (TypeError, IndexError):
            return []

        # 2. Validaciones de frontera y obstáculos
        if not (0 <= start_node[0] < self.rows and 0 <= start_node[1] < self.cols):
            return []
        if not (0 <= end_node[0] < self.rows and 0 <= end_node[1] < self.cols):
            return []

        # Si el inicio o fin es un muro, buscamos el nodo libre más cercano (Opcional)
        # Por ahora, simplemente retornamos vacío si están bloqueados
        if (
            self.matrix[start_node[0]][start_node[1]] == 1
            or self.matrix[end_node[0]][end_node[1]] == 1
        ):
            return []

        # 3. Estructuras de control
        close_set = set()
        came_from = {}
        gscore = {start_node: 0.0}
        fscore = {start_node: self.heuristic(start_node, end_node)}
        oheap = []
        heapq.heappush(oheap, (fscore[start_node], start_node))
        open_set_hash = {start_node}

        while oheap:
            current = heapq.heappop(oheap)[1]

            if current == end_node:
                path = []
                while current in came_from:
                    path.append(current)
                    current = came_from[current]
                return path[::-1]

            open_set_hash.discard(current)
            close_set.add(current)

            for dr, dc, costo_paso in self.neighbors_config:
                neighbor = (current[0] + dr, current[1] + dc)

                # A. Límites de matriz
                if not (0 <= neighbor[0] < self.rows and 0 <= neighbor[1] < self.cols):
                    continue

                # B. Obstáculo o ya procesado
                if self.matrix[neighbor[0]][neighbor[1]] == 1 or neighbor in close_set:
                    continue

                # C. SEGURIDAD DIAGONAL ESTRICTA
                # No permite "raspar" la esquina de un muro.
                # Si vas a (1,1), verifica que (0,1) y (1,0) estén libres.
                if dr != 0 and dc != 0:
                    if (
                        self.matrix[current[0] + dr][current[1]] == 1
                        or self.matrix[current[0]][current[1] + dc] == 1
                    ):
                        continue

                tentative_g_score = gscore[current] + costo_paso

                if tentative_g_score < gscore.get(neighbor, float("inf")):
                    came_from[neighbor] = current
                    gscore[neighbor] = tentative_g_score
                    fscore[neighbor] = tentative_g_score + self.heuristic(
                        neighbor, end_node
                    )

                    if neighbor not in open_set_hash:
                        heapq.heappush(oheap, (fscore[neighbor], neighbor))
                        open_set_hash.add(neighbor)

        return []
