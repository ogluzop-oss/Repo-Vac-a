# --- Bootstrap de entorno (debe ir lo PRIMERO, antes de leer rutas/.env) ---
from src.utils import recursos

recursos.preparar_entorno()

# --- Logging centralizado (captura errores y excepciones no controladas) ---
from src.utils.logger import configurar_logging

configurar_logging()

import matplotlib

from src.utils import pil_compat  # noqa: F401 — restaura ImageFont.getsize (Pillow>=10)

matplotlib.use("Agg")  # Fuerza el modo sin interfaz para evitar bloqueos
import logging
import os
import subprocess
import sys
import warnings

import pandas as pd

from assets.estilo_global import aplicar_estilo_app, mostrar_mensaje

# --- PARCHE 1: SILENCIAR AVISOS Y ERRORES DE GEOMETRÍA ---
warnings.filterwarnings("ignore", category=UserWarning, module="pandas")
os.environ["QT_LOGGING_RULES"] = "qt.qpa.gl=false"

# Intentar importar Prophet
try:
    from prophet import Prophet
except ImportError:
    Prophet = None

from PyQt6.QtCore import QEvent, QObject, QPropertyAnimation, Qt, QTimer, QUrl
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

# Importaciones internas
from src.db.conexion import init_db, obtener_conexion
from src.db.usuario import sesion_global, validar_login_empleado
from src.gui.login import LoginWindow
from src.gui.menu_principal import MenuPrincipal

# SOMA voice assistant (lazy — worker only starts after login)
try:
    from src.utils.soma_engine import (
        ACCION_A_MODULO,
        NOMBRE_MODULO,
        RESPUESTAS_AYUDA,
        parsear_comando,
    )
    from src.utils.soma_tts import SomaTTS
    from src.utils.soma_worker import (
        ESTADO_ACTIVADO,
        ESTADO_ESCUCHANDO,
        ESTADO_INACTIVO,
        ESTADO_PROCESANDO,
        SomaWorker,
    )

    _SOMA_DISPONIBLE = True
except ImportError:
    _SOMA_DISPONIBLE = False

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# BLOQUE UTILIDADES DE SEÑALES / SLOTS
# ============================================================
def conectar_senal_segura(signal, slot):
    """Conecta una señal sin duplicarla ni forzar disconnect() inseguros.

    El warning de terminal:
    QObject::disconnect: Unexpected nullptr parameter
    suele aparecer cuando se intenta desconectar una señal de forma ciega.
    Para evitarlo, aquí solo conectamos una vez por pareja señal/slot.
    """
    try:
        signal.connect(slot)
    except TypeError:
        # Ya estaba conectada o Qt rechazó una conexión duplicada.
        pass
    except RuntimeError:
        # El objeto puede haber sido destruido o no estar disponible.
        pass


# ============================================================
# BLOQUE BACKEND
# ============================================================
def iniciar_backend():
    """Inicia el backend API si no está corriendo."""
    # En modo empaquetado (.exe) sys.executable ES el propio ejecutable: relanzarlo
    # con un script como argumento abriría la aplicación completa otra vez, en bucle
    # infinito. Por eso NO se lanza el backend externo cuando la app está congelada.
    if getattr(sys, "frozen", False):
        logger.info("Modo empaquetado: backend externo deshabilitado.")
        return
    try:
        import socket

        # El backend es opcional y puede no existir todavía: si no está, se omite.
        backend_script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "backend", "app.py",
        )
        if not os.path.exists(backend_script):
            logger.info("Backend no encontrado (%s); se omite.", backend_script)
            return

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(("127.0.0.1", 5000))
        sock.close()
        if result != 0:
            logger.info("Iniciando backend API...")
            subprocess.Popen(
                [sys.executable, backend_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        else:
            logger.info("Backend ya está corriendo.")
    except Exception as e:
        logger.error(f"Error iniciando backend: {e}")


# ============================================================
# BLOQUE FUNCIÓN PUENTE (BRIDGE) PARA ALERTAS
# ============================================================
def verificar_reposicion_y_alertar(parent_window=None):
    """Llama al método de verificación de IA en la instancia global del manager."""
    global manager
    if "manager" in globals() and manager is not None:
        manager.verificar_ia_reposicion()


# ============================================================
# BLOQUE NOTIFICACIÓN FLOTANTE (IA)
# ============================================================
class FloatingNotification(QWidget):
    def __init__(self, mensaje, on_click_callback=None):
        super().__init__()
        self.on_click_callback = on_click_callback
        self.anim = None
        self.opacity_anim = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(360, 90)

        self.label = QLabel(mensaje, self)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("""
            background-color: rgba(26, 29, 35, 245);
            color: #00FFC6; border-radius: 15px; border: 2px solid #00FFC6;
            font-family: 'Segoe UI'; font-size: 13px; padding: 15px;
        """)
        self.label.setGeometry(0, 0, 360, 90)

        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(800)
        self.opacity_anim.setStartValue(0)
        self.opacity_anim.setEndValue(1)
        self.opacity_anim.start()

        QTimer.singleShot(8000, self.close_with_fade)

    def close_with_fade(self):
        if not self.isVisible():
            return
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(500)
        self.anim.setStartValue(1)
        self.anim.setEndValue(0)
        self.anim.finished.connect(self.close)
        self.anim.start()

    def mousePressEvent(self, event):
        if self.on_click_callback:
            self.on_click_callback()
        self.close()
        super().mousePressEvent(event)


# ============================================================
# SOMA — FILTRO GLOBAL CANCELAR CON CLIC
# ============================================================
class _SomaCancelFilter(QObject):
    """
    Installed on QApplication.
    Any mouse button press cancels SOMA speech if it is currently speaking.
    The click itself is NOT consumed — it still reaches its target widget.
    """

    def __init__(self, get_tts, parent=None):
        super().__init__(parent)
        self._get_tts = get_tts  # callable → SomaTTS | None

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            tts = self._get_tts()
            if tts and tts.hablando:
                tts.detener()
        return False  # always pass event through


# ============================================================
# BLOQUE CONTROLADOR CENTRAL (SMART MANAGER)
# ============================================================
class SmartManagerApp(QStackedWidget):
    def __init__(self):
        super().__init__()

        # --- 0. MULTIMEDIA (Intro) ---
        self.intro_player = QMediaPlayer()
        self.intro_audio = QAudioOutput()
        self.intro_player.setAudioOutput(self.intro_audio)
        ruta_musica = os.path.join(os.getcwd(), "assets", "startup.wav")
        if os.path.exists(ruta_musica):
            self.intro_player.setSource(QUrl.fromLocalFile(ruta_musica))
            self.intro_audio.setVolume(0.6)

        # --- 1. CONFIGURACIÓN BÁSICA ---
        self._articulos_notificados = set()
        self._rfid_signals_connected = False
        self.menu_principal = None
        self.notificacion = None

        # SOMA voice assistant (TTS init delayed until after first login sound plays)
        self.asistente_nombre = "SOMA"
        self._soma_worker = None
        self._soma_thread = None
        self._soma_tts = None  # initialized lazily in _iniciar_soma()

        self.setWindowTitle(tr("app.smart_manager_sistema_de_con", default="Smart Manager - Sistema de Control Logistico"))
        self.setMinimumSize(1200, 800)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)

        # --- 2. GESTIÓN DE ESTADOS Y HARDWARE ---
        self.gestion_activos = {"estanterias_sesion": {}}

        from PyQt6.QtCore import QThread

        from src.utils.rfid_worker import RFIDWorker

        if hasattr(self, "lector_rfid"):
            self.worker_rfid = RFIDWorker(self.lector_rfid)
            self.hilo_rfid = QThread(self)
            self.worker_rfid.moveToThread(self.hilo_rfid)
        else:
            self.worker_rfid = None
            self.hilo_rfid = None

        # --- 3. INICIALIZAR COMPONENTES DE INTERFAZ ---
        self.ventana_login = LoginWindow()
        self.setup_spinner()

        # --- 4. CONEXIÓN DE SEÑALES ---
        # No tocar el diseño del login ni del menú. Solo robustecemos la lógica.
        conectar_senal_segura(
            self.ventana_login.btn_login.clicked, self.iniciar_proceso_login
        )
        conectar_senal_segura(
            self.ventana_login.txt_password.returnPressed, self.iniciar_proceso_login
        )

        # --- 5. GESTIÓN DE VISTAS (StackedWidget) ---
        self.addWidget(self.ventana_login)
        self.setCurrentWidget(self.ventana_login)

    # ============================================================
    # BLOQUE CAPA DE CARGA LOGIN
    # ============================================================
    def setup_spinner(self):
        """Capa de carga que bloquea la interacción durante el login."""
        self.overlay = QWidget(self.ventana_login)
        self.overlay.hide()
        self.overlay.setGeometry(self.ventana_login.rect())
        self.overlay.setStyleSheet("background-color: rgba(14, 17, 23, 200);")

        from src.utils.i18n import tr
        from PyQt6.QtGui import QPixmap

        layout = QVBoxLayout(self.overlay)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(5)

        # Logo de la APLICACIÓN, centrado y visiblemente grande (no invasivo).
        self.loading_logo = QLabel()
        self.loading_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_logo.setStyleSheet("background: transparent; border: none;")
        try:
            from src.utils import recursos
            _lp = recursos.ruta_recurso("assets", "Logo Smart Manager.png")
            _pix = QPixmap(_lp)
            if not _pix.isNull():
                self.loading_logo.setPixmap(
                    _pix.scaled(
                        230, 230,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        except Exception:
            pass
        layout.addWidget(self.loading_logo, 0, Qt.AlignmentFlag.AlignCenter)

        # Texto justo debajo del logo (cerca de él).
        layout.addSpacing(14)
        self.loading_label = QLabel(
            tr("login.loading_ai", default="⚡ INICIANDO IA Y SINCRONIZANDO...")
        )
        self.loading_label.setStyleSheet("""
            color: #00FFC6; font-family: 'Segoe UI'; font-size: 16px;
            font-weight: bold; letter-spacing: 2px;
        """)
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.loading_label, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addStretch(4)

    # ============================================================
    # BLOQUE RFID
    # ============================================================
    def configurar_monitorizacion_rfid(self):
        """Configura las señales del worker RFID y arranca el hilo una sola vez."""
        if not self.worker_rfid or not self.hilo_rfid:
            print("[!] Abortando monitorización: Hardware no inicializado.")
            return

        if not self._rfid_signals_connected:
            conectar_senal_segura(self.hilo_rfid.started, self.worker_rfid.run)
            conectar_senal_segura(
                self.worker_rfid.tag_leido, self.reaccionar_a_tag_detectado
            )
            conectar_senal_segura(
                self.worker_rfid.error_ocurrido,
                lambda e: print(f"[HARDWARE ERROR] {e}"),
            )
            self._rfid_signals_connected = True

        if not self.hilo_rfid.isRunning():
            self.hilo_rfid.start()
            print("[SISTEMA] Monitorización RFID activa en segundo plano.")

    def reaccionar_a_tag_detectado(self, epc):
        """Procesa el EPC detectado por el vigilante y actúa en consecuencia."""
        epc = epc.strip().upper()
        estanterias = self.gestion_activos.get("estanterias_sesion", {})

        if epc in estanterias:
            datos = estanterias[epc]
            nombre = datos.get("nombre", "Desconocido")
            coords = datos.get("coords", (0, 0))
            rel_x, rel_y = coords

            if hasattr(self, "mostrar_mensaje_temporal"):
                self.mostrar_mensaje_temporal(f"PROXIMIDAD DETECTADA: {nombre}", 3500)

            if hasattr(self, "visor_admin") and self.visor_admin:
                self.visor_admin.centrar_en_coordenadas_reales(rel_x, rel_y)

            print(f"[SISTEMA] Detección de proximidad: {nombre} | Coords: {coords}")
        else:
            print(f"[SCAN] Tag desconocido detectado en el área: {epc}")

    # ============================================================
    # BLOQUE EVENTOS DE VENTANA
    # ============================================================
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "overlay") and self.overlay is not None:
            self.overlay.setGeometry(self.ventana_login.rect())

    def closeEvent(self, event):
        """Cierre ordenado para evitar objetos Qt colgando."""
        try:
            if self._soma_tts:
                self._soma_tts.detener()
                self._soma_tts.shutdown()
            self._detener_soma()
        except Exception:
            pass
        try:
            app = QApplication.instance()
            if app and hasattr(self, "_soma_cancel_filter"):
                app.removeEventFilter(self._soma_cancel_filter)
        except Exception:
            pass
        try:
            if self.hilo_rfid and self.hilo_rfid.isRunning():
                self.hilo_rfid.quit()
                self.hilo_rfid.wait(1500)
        except Exception as e:
            logger.warning(f"No se pudo cerrar el hilo RFID limpiamente: {e}")
        super().closeEvent(event)

    # ============================================================
    # BLOQUE LOGIN
    # ============================================================
    def iniciar_proceso_login(self):
        """Activa el spinner y valida tras un delay."""
        # Refresca el texto al idioma seleccionado en el login antes de mostrarlo.
        try:
            from src.utils.i18n import tr
            self.loading_label.setText(
                tr("login.loading_ai", default="⚡ INICIANDO IA Y SINCRONIZANDO...")
            )
        except Exception:
            pass
        self.overlay.setGeometry(self.ventana_login.rect())
        self.overlay.show()
        self.overlay.raise_()
        self.configurar_monitorizacion_rfid()
        QApplication.processEvents()
        QTimer.singleShot(800, self.ejecutar_login)

    def ejecutar_login(self):
        """Procesa las credenciales y gestiona el cambio de pantalla."""
        nombre = self.ventana_login.txt_nombre.text().strip()
        password = self.ventana_login.txt_password.text()
        user_data = validar_login_empleado(nombre, password)

        if user_data:
            sesion_global.iniciar_sesion(user_data)
            self.abrir_menu_principal()
            self.ventana_login.txt_password.clear()
            self.overlay.hide()
            # Reproducir el tono al iniciar la sesión
            # stop()+setPosition(0) ensures clean replay after a previous login
            self.intro_player.stop()
            self.intro_player.setPosition(0)
            if self.intro_player.source().isValid():
                self.intro_player.play()
            # Arrancar SOMA DIFERIDO: dejamos que el menú principal se pinte y sea
            # interactivo ANTES de inicializar el asistente de voz. Antes se
            # llamaba aquí en línea y el arranque de SOMA congelaba los botones del
            # menú durante 1-3 s. Con el retardo, la UI responde de inmediato.
            QTimer.singleShot(350, self._iniciar_soma)
        else:
            self.overlay.hide()
            mostrar_mensaje(
                self,
                "Acceso Denegado",
                "Credenciales incorrectas.",
                nivel="error",
            )
            self.ventana_login.txt_password.clear()
            self.ventana_login.txt_password.setFocus()

    # ============================================================
    # BLOQUE IA / PREDICCIÓN
    # ============================================================
    def predecir_ventas_semanales(self):
        """IA Prophet para predecir demanda."""
        if not Prophet:
            return {}
        try:
            with obtener_conexion() as conn:
                df = pd.read_sql_query(
                    "SELECT fecha, codigo, cantidad FROM ventas", conn
                )

            if df.empty or len(df) < 5:
                return {}

            df["fecha"] = pd.to_datetime(df["fecha"])
            df["ds"] = df["fecha"].dt.to_period("W").apply(lambda r: r.start_time)

            preds = {}
            for cod in df["codigo"].unique():
                df_p = (
                    df[df["codigo"] == cod]
                    .groupby("ds")["cantidad"]
                    .sum()
                    .reset_index()
                )
                df_p.columns = ["ds", "y"]
                if len(df_p) >= 2:
                    m = Prophet(
                        weekly_seasonality=True,
                        daily_seasonality=False,
                        yearly_seasonality=False,
                    )
                    m.fit(df_p)
                    future = m.make_future_dataframe(periods=1, freq="W")
                    forecast = m.predict(future)
                    preds[cod] = max(0, round(forecast.iloc[-1]["yhat"]))
            return preds
        except Exception as e:
            logger.error(f"Error IA: {e}")
            return {}

    def verificar_ia_reposicion(self):
        """Compara stock vs IA y lanza notificación."""
        try:
            preds = self.predecir_ventas_semanales()
            with obtener_conexion() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT codigo, descripcion, Stock_tienda FROM articulos"
                    )
                    articulos = cursor.fetchall()

            bajos = []
            for item in articulos:
                cod = item[0]
                desc = item[1]
                stock_raw = item[2]

                if cod in self._articulos_notificados:
                    continue

                try:
                    stock = int(stock_raw) if stock_raw is not None else 0
                except Exception:
                    stock = 0

                if stock < 3 or (preds.get(cod, 0) > stock):
                    bajos.append(str(desc) if desc else f"Cod: {cod}")
                    self._articulos_notificados.add(cod)

            if bajos:
                msg = (
                    f"Smart Manager: Stock critico detectado en: "
                    f"{', '.join(bajos[:2])}"
                )
                self.notificacion = FloatingNotification(
                    msg,
                    on_click_callback=lambda: self.menu_principal.abrir_ventana_por_id(
                        "reposicion"
                    ),
                )

                screen = QApplication.primaryScreen().availableGeometry()
                self.notificacion.move(screen.width() - 380, screen.height() - 120)
                self.notificacion.show()
        except Exception as e:
            logger.error(f"Error en verificación: {e}")

    # ============================================================
    # BLOQUE SOMA — ASISTENTE DE VOZ
    # ============================================================
    def _iniciar_soma(self):
        """Starts the SOMA voice worker in a background QThread after login.
        TTS is initialized with a 1.5s delay so startup.wav plays first (COM conflict avoidance).
        """
        if not _SOMA_DISPONIBLE:
            return
        # Initialize TTS lazily — delayed 800ms so QMediaPlayer startup sound plays
        # cleanly. (Antes 1500 ms: el TTS tardaba en estar listo y las primeras
        # invocaciones de "Ey SOMA" detectaban la wake pero no sonaba el saludo.)
        if self._soma_tts is None:
            QTimer.singleShot(800, self._init_soma_tts)
        # Avoid double-starting the worker across re-logins
        if self._soma_thread and self._soma_thread.isRunning():
            return
        from PyQt6.QtCore import QThread

        self._soma_worker = SomaWorker()
        if not self._soma_worker.disponible:
            logger.warning("SOMA: worker no disponible (faltan dependencias).")
            return
        self._soma_thread = QThread(self)
        # Debug mode: set env SOMA_DEBUG=1 to log STT transcripts + timing
        try:
            self._soma_worker.set_debug(os.environ.get("SOMA_DEBUG", "") == "1")
        except Exception:
            pass
        self._soma_worker.moveToThread(self._soma_thread)
        self._soma_thread.started.connect(self._soma_worker.start)
        self._soma_worker.soma_activado.connect(self._soma_on_activado)
        self._soma_worker.comando_detectado.connect(self._soma_on_comando)
        self._soma_worker.estado_cambiado.connect(self._soma_on_estado)
        self._soma_worker.error_ocurrido.connect(
            lambda e: logger.error(f"SOMA error: {e}")
        )
        self._soma_thread.start()
        logger.info("SOMA: worker iniciado en hilo secundario.")

    def _init_soma_tts(self):
        """Inicializa el TTS de SOMA SIN bloquear la interfaz.

        SomaTTS.__init__ espera hasta 6 s a que pygame.mixer arranque; si eso se
        ejecuta en el hilo principal, CONGELA el menú nada más hacer login (era la
        causa del lag de botones que persistía). Por eso lo construimos en un hilo
        de fondo y asignamos self._soma_tts cuando esté listo."""
        if self._soma_tts is not None or not _SOMA_DISPONIBLE:
            return
        # El filtro de cancelación (clic para callar a SOMA) se instala YA en el
        # hilo principal; lee self._soma_tts de forma perezosa (tolera None).
        app = QApplication.instance()
        if app and getattr(self, "_soma_cancel_filter", None) is None:
            self._soma_cancel_filter = _SomaCancelFilter(lambda: self._soma_tts)
            app.installEventFilter(self._soma_cancel_filter)

        import threading

        def _construir_tts():
            try:
                tts = SomaTTS()  # bloquea ~hasta 6 s, pero en ESTE hilo de fondo
                self._soma_tts = tts
                logger.info("SOMA TTS inicializado (en segundo plano).")
            except Exception as e:
                logger.error(f"SOMA TTS: fallo al inicializar: {e}")

        threading.Thread(target=_construir_tts, daemon=True, name="SomaTTSInit").start()

    def _detener_soma(self):
        if self._soma_worker:
            self._soma_worker.stop()
        if self._soma_thread and self._soma_thread.isRunning():
            self._soma_thread.quit()
            self._soma_thread.wait(2000)
        self._soma_worker = None
        self._soma_thread = None

    def _soma_on_activado(self, tiene_comando_inline: bool):
        """
        Called in main thread when wake word is detected.
        tiene_comando_inline=True  → inline command follows; _soma_on_comando plays
                                     the action message — no confirmation needed here.
        tiene_comando_inline=False → wake-word only; play confirmation so user
                                     knows SOMA is listening before they speak.
        """
        logger.info(f"SOMA activado (inline={tiene_comando_inline})")
        if self._soma_tts and not tiene_comando_inline:
            self._soma_tts.confirmar_activacion()
        # Visual indicator
        mp = self.menu_principal
        if mp is not None:
            try:
                mp.soma_set_estado("activado")
            except RuntimeError:
                self.menu_principal = None

    def _soma_on_estado(self, estado: str):
        mp = self.menu_principal
        if mp is None:
            return
        try:
            if hasattr(mp, "soma_set_estado"):
                mp.soma_set_estado(estado)
        except RuntimeError:
            self.menu_principal = None

    def _soma_on_comando(self, texto: str):
        """Called in main thread when a command is transcribed."""
        # Prioridad Absoluta: Si entra un comando, silenciamos el TTS anterior (el "Dime")
        if self._soma_tts:
            self._soma_tts.detener()

        logger.info(f"SOMA comando: '{texto}'")
        # Comprensión multiidioma: el motor de comandos razona en español. Si la
        # app está en otro idioma, traducimos el comando reconocido al español
        # canónico (vía IA, dominio 'soma') antes de parsear. Así SOMA entiende
        # los 20 idiomas sin tablas de palabras clave por idioma. Sin proveedor
        # de IA registrado es un no-op (el español sigue funcionando).
        texto_canonico = texto
        try:
            from src.utils import i18n
            if i18n.current_language() != "es":
                texto_canonico = i18n.ai_translate(texto, "es", dominio="soma")
        except Exception:
            texto_canonico = texto
        accion, params = parsear_comando(texto_canonico)

        # ── Eco del propio saludo de SOMA: ignorar en silencio ─────────────
        if accion == "ignorar":
            logger.info("SOMA: eco de saludo ignorado.")
            return

        # ── Cerrar módulo activo ("cierra X" / "cierra la ventana") ────────
        if accion == "cerrar_modulo":
            self._soma_cerrar_modulo(params)
            return

        # ── Desconocido ────────────────────────────────────────────────────
        if accion == "desconocido":
            if self._soma_tts:
                self._soma_tts.decir_desconocido(texto)
            return

        # ── Ayuda ──────────────────────────────────────────────────────────
        if accion == "mostrar_ayuda":
            if self._soma_tts:
                self._soma_tts.decir(RESPUESTAS_AYUDA)
            return

        # ── Ayuda específica por módulo ────────────────────────────────────
        if accion.startswith("help_"):
            from src.utils.soma_engine import RESPUESTAS_COMANDOS_MODULO

            # accion = "help_<modulo>"; the dict is keyed by "<modulo>".
            modulo = params.get("modulo") or accion[len("help_"):]
            msg = RESPUESTAS_COMANDOS_MODULO.get(
                modulo, "No tengo información detallada sobre esa función."
            )
            if self._soma_tts:
                self._soma_tts.decir(msg)
            return

        # ── Cerrar sesión ──────────────────────────────────────────────────
        if accion == "cerrar_sesion":
            if self._soma_tts:
                self._soma_tts.decir("Cerrando sesión. Hasta pronto.")
            # Replicamos el cierre de sesión del botón (sin diálogo): limpiamos la
            # sesión y cerramos el menú. Su señal 'destroyed' dispara detectar_logout,
            # que al ver la sesión vacía VUELVE AL LOGIN. IMPORTANTE: antes se llamaba
            # a detectar_logout SIN limpiar la sesión (con 1,5 s de espera), lo que
            # hacía que _procesar_retorno_o_cierre cayera en el 'else' y CERRARA LA
            # APP entera. Ahora es correcto e instantáneo.
            mp = self.menu_principal
            try:
                if mp is not None and hasattr(mp, "_cerrar_recursos"):
                    mp._cerrar_recursos()
            except Exception:
                pass
            try:
                sesion_global.cerrar_sesion()
            except Exception:
                sesion_global.usuario_actual = None
            if mp is not None:
                mp.close()  # WA_DeleteOnClose → destroyed → detectar_logout → LOGIN
            else:
                QTimer.singleShot(120, self.detectar_logout)
            return

        # ── Volver al menú ─────────────────────────────────────────────────
        if accion == "nav_menu":
            if self.menu_principal:
                # Detectar si el usuario pidi? cerrar algo espec?fico para responder mejor
                texto_upper = texto.upper()
                respuesta = "Volviendo al men? principal."
                for kw in ["CIERRA", "CERRAR", "QUITA", "QUITAR", "SALIR"]:
                    if kw in texto_upper:
                        # Si hay m?s texto tras el comando de cierre, lo mencionamos
                        respuesta = "Cerrando funci?n y volviendo al men?."
                        break
                if self._soma_tts:
                    self._soma_tts.decir(respuesta)
                self.setCurrentWidget(self.menu_principal)
            return

        # ── Consultas en tiempo real (responden en voz, sin abrir pantallas) ─
        if accion in (
            "query_stock",
            "query_criticos",
            "query_ventas_hoy",
            "query_traspasos",
            "query_mermas",
            "info_usuario",
            "info_hora",
        ):
            self._soma_ejecutar_query(accion, params)
            return

        # ── Acciones directas con mensaje contextual ────────────────────────
        if accion == "accion_nueva_merma":
            if self._soma_tts:
                self._soma_tts.decir(
                    "He abierto mermas. Pulsa el botón Nueva Merma para registrar la pérdida."
                )
            self._soma_navegar("mermas")
            return

        if accion == "accion_nuevo_traspaso":
            if self._soma_tts:
                self._soma_tts.decir(
                    "He abierto el módulo de logística. Pulsa Iniciar Traspaso para comenzar."
                )
            self._soma_navegar("logistica")
            return

        if accion == "accion_buscar_articulo":
            articulo = params.get("articulo", "")
            if self._soma_tts:
                if articulo:
                    self._soma_tts.decir(f"Buscando el artículo {articulo}.")
                else:
                    self._soma_tts.decir("He abierto información de artículo.")
            self._soma_navegar("info")
            return

        # ── Navegación estándar ────────────────────────────────────────────
        modulo = ACCION_A_MODULO.get(accion)
        if modulo:
            # Asegurar apertura de configuraci?n por alias comunes
            if modulo == "configuracion" and self.menu_principal:
                modulo = "configuracion"  # O "ajustes" si falla
            nombre_hablado = NOMBRE_MODULO.get(accion, modulo)
            if self._soma_tts:
                self._soma_tts.decir(f"Abriendo {nombre_hablado}.")
            self._soma_navegar(modulo)

    def _soma_navegar(self, modulo_id: str):
        """Navigate to a module via menu_principal.
        Most modules go through abrir_ventana_por_id; configuración and usuarios
        have their own openers, so they are routed explicitly.
        Records the open module so SOMA can later close it correctly.
        """
        mp = self.menu_principal
        if not mp:
            return
        try:
            if modulo_id == "configuracion" and hasattr(mp, "abrir_modulo_configuracion"):
                mp.abrir_modulo_configuracion()
            elif modulo_id == "usuarios" and hasattr(mp, "abrir_gestion_usuarios"):
                mp.abrir_gestion_usuarios()
            else:
                mp.abrir_ventana_por_id(modulo_id)
            self._soma_modulo_activo = modulo_id
        except Exception as e:
            logger.error(f"SOMA nav error: {e}")

    # Spoken module name for SOMA's close responses.
    _SOMA_NOMBRE_MODULO = {
        "tpv": "el TPV", "ventas": "ventas", "stock": "stock",
        "logistica": "logística", "mermas": "mermas", "etiquetas": "etiquetas",
        "reposicion": "reposición", "ubicacion": "ubicación", "info": "artículo",
        "configuracion": "configuración", "usuarios": "usuarios",
    }

    def _soma_cerrar_modulo(self, params: dict):
        """
        Close the open module and return to the menu, with validation:
          * Nothing open                  → inform the worker.
          * Asked module ≠ the open one   → inform (can't close what isn't open).
          * Match / generic "cierra la ventana" → actually close + return to menu.
        """
        mp = self.menu_principal
        if not mp:
            return
        nombre = self._SOMA_NOMBRE_MODULO
        abierto = getattr(self, "_soma_modulo_activo", None)
        pedido = (params or {}).get("modulo")  # None for "cierra la ventana"

        if not abierto:
            if self._soma_tts:
                self._soma_tts.decir(
                    "No hay ninguna función abierta. Ya estás en el menú principal."
                )
            return

        if pedido and pedido != abierto:
            if self._soma_tts:
                ped_n = nombre.get(pedido, pedido)
                abi_n = nombre.get(abierto, abierto)
                self._soma_tts.decir(
                    f"No puedo cerrar {ped_n} porque no está abierta. "
                    f"Ahora mismo tienes abierta {abi_n}."
                )
            return

        abi_n = nombre.get(abierto, abierto)
        # Cerramos PRIMERO (ejecución inmediata) y confirmamos por voz DESPUÉS, con
        # una frase corta para que se perciba rápido. El TTS es asíncrono, así que
        # la función se cierra al instante sin esperar a la voz.
        try:
            if hasattr(mp, "cerrar_ventana_activa"):
                mp.cerrar_ventana_activa()
            elif hasattr(mp, "mostrar_menu_principal"):
                mp.mostrar_menu_principal()
        except Exception as e:
            logger.error(f"SOMA cerrar módulo error: {e}")
        self._soma_modulo_activo = None
        if self._soma_tts:
            self._soma_tts.decir(f"Cerrando {abi_n}.")

    def _soma_ejecutar_query(self, accion: str, params: dict):
        """Run a DB query in a background thread, then speak the result."""
        import threading

        from src.utils import soma_queries as Q

        def _run():
            try:
                if accion == "query_stock":
                    articulo = params.get("articulo", "").strip()
                    respuesta = Q.stock_articulo(articulo)
                elif accion == "query_criticos":
                    respuesta = Q.articulos_criticos()
                elif accion == "query_ventas_hoy":
                    respuesta = Q.ventas_hoy()
                elif accion == "query_traspasos":
                    respuesta = Q.traspasos_pendientes()
                elif accion == "query_mermas":
                    respuesta = Q.mermas_mes()
                elif accion == "info_usuario":
                    respuesta = Q.info_usuario_actual()
                elif accion == "info_hora":
                    respuesta = Q.info_hora_fecha()
                else:
                    respuesta = "Consulta no disponible."

                logger.info(f"SOMA query result: {respuesta}")
                if self._soma_tts:
                    self._soma_tts.decir(respuesta)
            except Exception as e:
                logger.error(f"SOMA query error: {e}")
                if self._soma_tts:
                    self._soma_tts.decir("Ha ocurrido un error al consultar los datos.")

        threading.Thread(target=_run, daemon=True).start()

    # ============================================================
    # BLOQUE NAVEGACIÓN PRINCIPAL
    # ============================================================
    def abrir_menu_principal(self):
        """Carga el Menú Principal y gestiona la transición desde el Login."""
        try:
            for i in range(self.count() - 1, -1, -1):
                widget = self.widget(i)
                if isinstance(widget, MenuPrincipal):
                    self.removeWidget(widget)
                    widget.deleteLater()

            self.menu_principal = MenuPrincipal()

            # No se toca el diseño del menú; solo se robustece el flujo.
            self.menu_principal.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            conectar_senal_segura(self.menu_principal.destroyed, self.detectar_logout)

            index = self.addWidget(self.menu_principal)
            self.setCurrentIndex(index)
            self.showMaximized()
            self.menu_principal.setFocus()

            logger.info(
                f"Navegación: Menú Principal cargado para {sesion_global.obtener_nombre()}"
            )
        except Exception as e:
            logger.error(f"Error crítico al abrir el menú: {e}")
            sesion_global.usuario_actual = None
            self.detectar_logout()

    def detectar_logout(self):
        """Gestiona el retorno al login o el cierre total de la aplicación."""
        QTimer.singleShot(50, self._procesar_retorno_o_cierre)

    def _procesar_retorno_o_cierre(self):
        """Gestiona el regreso al Login manteniendo la fluidez visual."""
        if sesion_global.usuario_actual is None:
            logger.info("Estado: Logout detectado. Transición fluida al Login...")
            self.menu_principal = (
                None  # nullify BEFORE switch so SOMA signals find nothing
            )
            self.setCurrentIndex(0)

            if hasattr(self.ventana_login, "txt_password"):
                self.ventana_login.txt_nombre.clear()
                self.ventana_login.txt_password.clear()
                self.ventana_login.txt_nombre.setFocus()

            self._articulos_notificados.clear()
            self.showMaximized()
            self.raise_()
            self.activateWindow()
        else:
            logger.info("Estado: Cierre de ventana detectado. Finalizando proceso...")
            QApplication.quit()

    def _forzar_maximizacion_final(self):
        """Mantiene la ventana en pantalla completa y fuerza el redibujado."""
        if not self.isMaximized():
            self.showMaximized()

        self.updateGeometry()
        QApplication.processEvents()


if __name__ == "__main__":
    # Obligatorio en apps congeladas (PyInstaller): evita que cualquier subproceso
    # creado por multiprocessing (p. ej. Prophet/cmdstanpy) relance la GUI completa.
    import multiprocessing
    multiprocessing.freeze_support()

    # Windows: identidad explícita de la app para que la barra de tareas use
    # NUESTRO icono (y no el del intérprete de Python) y agrupe las ventanas.
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "SmartManagerAI.Desktop.1"
            )
        except Exception:
            pass

    iniciar_backend()
    init_db()

    # Traducción por IA (Nivel 2): enchufa el proveedor en i18n. Se activa solo
    # si hay backend LLM disponible (ANTHROPIC_API_KEY + paquete 'anthropic');
    # en caso contrario, degrada con elegancia (contenido dinámico sin traducir).
    try:
        from src.utils import ai_translator
        ai_translator.registrar_proveedor()
    except Exception as _e:
        logger.debug(f"AI translator no registrado: {_e}")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    aplicar_estilo_app(app)
    app.setQuitOnLastWindowClosed(False)

    # Icono de la aplicación (ventanas + barra de tareas).
    try:
        from PyQt6.QtGui import QIcon
        from src.utils import recursos
        _icon_path = recursos.ruta_recurso("assets", "app_icon.png")
        if not os.path.exists(_icon_path):
            _icon_path = recursos.ruta_recurso("assets", "icono.ico")
        app.setWindowIcon(QIcon(_icon_path))
    except Exception as _e:
        logger.debug(f"No se pudo fijar el icono de la app: {_e}")

    global manager
    manager = SmartManagerApp()
    manager.showMaximized()

    app.aboutToQuit.connect(
        lambda: logger.info("Sistema Smart Manager finalizado. Terminal liberada.")
    )

    exit_code = app.exec()
    logger.info(f"Proceso finalizado con código: {exit_code}")
    sys.exit(exit_code)
