# --- Diagnóstico de crashes nativos (segfault/abort de Qt/C++): imprime el stack Python
# en el momento del fallo. Barato y siempre útil; escribe a stderr (terminal) y a un log. ---
import faulthandler as _faulthandler
import os as _os

try:
    _os.makedirs("logs", exist_ok=True)
    _fh_log = open("logs/faulthandler.log", "a", encoding="utf-8")  # noqa: SIM115
    _faulthandler.enable(file=_fh_log, all_threads=True)
except Exception:
    _faulthandler.enable(all_threads=True)

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
from src.db.usuario import sesion_global, validar_login_usuario
from src.gui.login import LoginWindow
from src.gui.menu_principal import MenuPrincipal
from src.utils.i18n import tr

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
# Handle del backend lanzado por ESTA instancia, para cerrarlo al salir (evita huérfanos acumulados).
_backend_proc = None


def _puerto_backend() -> int:
    """Puerto REAL del backend (mismos defaults que src/backend/app.py)."""
    return int(os.environ.get("BACKEND_PORT", os.environ.get("PORT", "8090")))


def detener_backend():
    """Termina el backend lanzado por esta instancia. Idempotente. Se registra en atexit/aboutToQuit
    para que NO queden procesos `backend/app.py` huérfanos acumulándose en cada arranque."""
    global _backend_proc
    p, _backend_proc = _backend_proc, None
    if p is None:
        return
    try:
        if p.poll() is None:            # sigue vivo
            p.terminate()
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()
        logger.info("Backend API detenido.")
    except Exception as e:
        logger.debug("Al detener backend: %s", e)


def iniciar_backend():
    """Inicia el backend API si no está corriendo, y lo deja registrado para cerrarlo al salir."""
    global _backend_proc
    # En modo empaquetado (.exe) sys.executable ES el propio ejecutable: relanzarlo
    # con un script como argumento abriría la aplicación completa otra vez, en bucle
    # infinito. Por eso NO se lanza el backend externo cuando la app está congelada.
    if getattr(sys, "frozen", False):
        logger.info("Modo empaquetado: backend externo deshabilitado.")
        return
    try:
        import atexit
        import socket

        # El backend es opcional y puede no existir todavía: si no está, se omite.
        backend_script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "backend", "app.py",
        )
        if not os.path.exists(backend_script):
            logger.info("Backend no encontrado (%s); se omite.", backend_script)
            return

        # Comprobar el puerto REAL del backend (8090), no 5000. Con el puerto equivocado la guarda
        # "ya está corriendo" nunca saltaba y se lanzaba un backend NUEVO en cada arranque → huérfanos.
        port = _puerto_backend()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        if result == 0:
            logger.info("Backend ya está corriendo (puerto %s).", port)
            return
        logger.info("Iniciando backend API (puerto %s)...", port)
        _backend_proc = subprocess.Popen(
            [sys.executable, backend_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        atexit.register(detener_backend)   # red de seguridad: cerrar el backend al terminar el proceso
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
# SOMA — Navegador (fast-path del kernel: abrir/cerrar módulos reutilizando la navegación existente)
# ============================================================
class _SomaNavegador:
    """Adaptador que el SomaKernel usa para navegar por el ERP sin duplicar lógica: reutiliza la
    navegación ya existente (menu_principal.abrir_ventana_por_id / setCurrentWidget / cierre)."""

    def __init__(self, app):
        self._app = app

    def puede(self, accion) -> bool:
        return bool(accion) and (str(accion).startswith("nav_") or accion in ("cerrar_modulo",))

    def ejecutar(self, accion, params, texto) -> dict:
        app = self._app
        try:
            if accion == "nav_menu":
                mp = getattr(app, "menu_principal", None)
                if mp is not None:
                    app.setCurrentWidget(mp)
                return {"mensaje": "Vuelvo al menú principal.", "repliega": True}
            if accion == "cerrar_modulo":
                if hasattr(app, "_soma_cerrar_modulo"):
                    app._soma_cerrar_modulo(params or {})
                return {"mensaje": "Cierro la función.", "repliega": True}
            if str(accion).startswith("nav_"):
                vid = accion[len("nav_"):]
                mp = getattr(app, "menu_principal", None)
                if mp is not None and hasattr(mp, "abrir_ventana_por_id"):
                    mp.abrir_ventana_por_id(vid)
                    return {"mensaje": f"Abriendo {vid.replace('_', ' ')}.", "repliega": True}
            return {}
        except Exception as e:
            logger.debug("navegador SOMA: %s", e)
            return {"mensaje": "No he podido completar esa acción.", "repliega": False}


# ============================================================
# BLOQUE CONTROLADOR CENTRAL (SMART MANAGER)
# ============================================================
class SmartManagerApp(QStackedWidget):
    def __init__(self):
        super().__init__()
        # Fondo oscuro desde el primer frame (ventana SIN marco): evita el destello blanco al mostrarse antes
        # de aplicar el stylesheet/maximizar.
        self.setAutoFillBackground(True)
        self.setStyleSheet("QStackedWidget{background:#0E1117;}")

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

        # El nombre incluye la EDICIÓN por tipo de comercio (p. ej. "Smart Manager Supermarket").
        try:
            from src.services import verticales
            _titulo_app = f"{verticales.nombre_edicion()} — {tr('app.subtitulo', default='Sistema de Control Logístico')}"
        except Exception:
            _titulo_app = tr("app.smart_manager_sistema_de_con",
                             default="Smart Manager - Sistema de Control Logistico")
        self.setWindowTitle(_titulo_app)
        # Datos por defecto de la EDICIÓN (versión por comercio) para la empresa por defecto. Idempotente y
        # best-effort: en un build dedicado (SMART_MANAGER_EDITION) siembra las familias típicas del comercio.
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            from src.services import verticales
            verticales.aplicar_datos_por_defecto(EMPRESA_DEFAULT_ID)
        except Exception:
            pass
        # Suelo por debajo del área de trabajo más pequeña habitual (1366×768 → ~728 px útiles): un mínimo
        # mayor que el área de trabajo forzaría la ventana MÁS ALTA que el escritorio y taparía la barra de
        # tareas. La app se usa siempre maximizada, así que este valor solo es un piso de seguridad.
        self.setMinimumSize(1024, 640)
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

        # Selector de perfil PREVIO al login (perfiles de la empresa activa; aislamiento estricto).
        from src.gui.selector_perfil import SelectorPerfilWindow
        self.ventana_selector = SelectorPerfilWindow()

        # --- 4. CONEXIÓN DE SEÑALES ---
        # No tocar el diseño del login ni del menú. Solo robustecemos la lógica.
        conectar_senal_segura(
            self.ventana_login.btn_login.clicked, self.iniciar_proceso_login
        )
        conectar_senal_segura(
            self.ventana_login.txt_password.returnPressed, self.iniciar_proceso_login
        )
        conectar_senal_segura(
            self.ventana_selector.perfil_elegido, self._on_perfil_elegido
        )
        conectar_senal_segura(
            self.ventana_login.volver_a_selector, self._volver_al_selector
        )

        # --- 5. GESTIÓN DE VISTAS (StackedWidget) ---
        # ORDEN IMPORTANTE: se añade LOGIN y DESPUÉS el SELECTOR de perfiles. Al cerrar sesión, el menú (última
        # página) se elimina del stack y Qt selecciona automáticamente como fallback la página de índice
        # inmediatamente inferior; queremos que ese fallback sea el SELECTOR (no el Login), para que el cierre de
        # sesión lleve DIRECTAMENTE al selector de perfiles sin que el Login parpadee como intermediario.
        self.addWidget(self.ventana_login)      # índice 0
        self.addWidget(self.ventana_selector)   # índice 1 → fallback natural del stack al cerrar el menú

        # ONBOARDING de EDICIÓN (Vía B): en la PRIMERA ejecución de una instalación sin edición definida se
        # pregunta el tipo de comercio y se persiste (per-install). Si ya está definida (entorno/SaaS o elección
        # previa), esta pantalla NO aparece y se sigue el flujo normal (selector de perfil / login).
        self.ventana_edicion = None
        try:
            from src.services import verticales as _vert
            if not _vert.edicion_definida():
                from src.gui.selector_edicion import SelectorEdicionWindow
                self.ventana_edicion = SelectorEdicionWindow()
                conectar_senal_segura(self.ventana_edicion.edicion_elegida, self._on_edicion_elegida)
                self.addWidget(self.ventana_edicion)
        except Exception:
            self.ventana_edicion = None

        if self.ventana_edicion is not None:
            self.setCurrentWidget(self.ventana_edicion)
        # Si hay perfiles registrados, se muestra primero el SELECTOR; si no, el login directo.
        elif self.ventana_selector.tiene_perfiles():
            self.setCurrentWidget(self.ventana_selector)
        else:
            self.setCurrentWidget(self.ventana_login)

    def _on_edicion_elegida(self, codigo):
        """Onboarding: el negocio eligió su tipo de comercio → persistido por `verticales.fijar_edicion`. Se
        reaplica el nombre de la app y los datos por defecto de la edición, y se continúa al flujo normal."""
        try:
            from src.services import verticales
            self.setWindowTitle(f"{verticales.nombre_edicion()} — "
                                f"{tr('app.subtitulo', default='Sistema de Control Logístico')}")
        except Exception:
            pass
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            from src.services import verticales
            verticales.aplicar_datos_por_defecto(EMPRESA_DEFAULT_ID)
        except Exception:
            pass
        if self.ventana_selector.tiene_perfiles():
            self.setCurrentWidget(self.ventana_selector)
        else:
            self.setCurrentWidget(self.ventana_login)
        # El onboarding es de un solo uso: se saca del stack para que no quede como fallback al cerrar sesión
        # (así el orden LOGIN(0)/SELECTOR(1) se mantiene y el fallback sigue siendo el selector).
        if getattr(self, "ventana_edicion", None) is not None:
            try:
                self.removeWidget(self.ventana_edicion)
                self.ventana_edicion.deleteLater()
            except Exception:
                pass
            self.ventana_edicion = None

    def _on_perfil_elegido(self, nombre):
        """Perfil elegido en el selector → ir al login con el nombre pre-rellenado y BLOQUEADO."""
        self.ventana_login.fijar_perfil(nombre)
        self.setCurrentWidget(self.ventana_login)

    def _volver_al_selector(self):
        """Botón «atrás» del login → desbloquear el nombre y volver al selector de perfil."""
        self.ventana_login.liberar_perfil()
        try:
            self.ventana_selector.cargar_perfiles()   # refresca por si cambiaron los perfiles
            self.ventana_selector.buscador.clear()
        except Exception:
            pass
        self.setCurrentWidget(self.ventana_selector)

    # ============================================================
    # BLOQUE CAPA DE CARGA LOGIN
    # ============================================================
    def setup_spinner(self):
        """Capa de carga que bloquea la interacción durante el login."""
        self.overlay = QWidget(self.ventana_login)
        self.overlay.hide()
        self.overlay.setGeometry(self.ventana_login.rect())
        self.overlay.setStyleSheet("background-color: rgba(14, 17, 23, 200);")

        layout = QVBoxLayout(self.overlay)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(5)

        # Elemento central de carga. SIN TEXTO y SIN LOGO estático (ambos retirados a petición).
        # Si existe un CLIP de animación en assets (gif/webp/apng animado, o vídeo mp4/webm), se reproduce
        # como animación de carga; si no lo hay todavía, la pantalla de carga es solo el atenuado que
        # bloquea la interacción (nada en el centro).
        self.loading_logo = QLabel()
        self.loading_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_logo.setStyleSheet("background: transparent; border: none;")
        self._loading_movie = None   # QMovie (gif/webp/apng)
        self._loading_video = None   # QMediaPlayer (mp4/webm)

        self._montar_clip_carga(layout)

        layout.addStretch(4)

    def _montar_clip_carga(self, layout) -> bool:
        """Busca un clip de animación de carga en `assets/` y lo monta en `layout`. Acepta animación
        (gif/webp/apng → QMovie, ideal: soporta transparencia y bucle) o vídeo (mp4/webm/mov →
        QVideoWidget). Nombres admitidos: carga/cargando/loading/loader/spinner/animacion_carga. Devuelve
        True si montó un clip; False si no hay ninguno (se usa el logo estático)."""
        import os
        try:
            from src.utils import recursos
        except Exception:
            return False
        bases = ("carga", "cargando", "loading", "loader", "spinner",
                 "animacion_carga", "loading_animation")
        anim_ext = ("gif", "webp", "apng", "mng")
        video_ext = ("mp4", "webm", "mov", "m4v")
        ruta, tipo = None, None
        for b in bases:
            for ext in anim_ext:
                p = recursos.ruta_recurso("assets", f"{b}.{ext}")
                if p and os.path.exists(p):
                    ruta, tipo = p, "anim"; break
            if ruta:
                break
        if ruta is None:
            for b in bases:
                for ext in video_ext:
                    p = recursos.ruta_recurso("assets", f"{b}.{ext}")
                    if p and os.path.exists(p):
                        ruta, tipo = p, "video"; break
                if ruta:
                    break
        if ruta is None:
            return False
        try:
            if tipo == "anim":
                from PyQt6.QtGui import QMovie
                mov = QMovie(ruta)
                if not mov.isValid():
                    return False
                self.loading_logo.setMovie(mov)
                self._loading_movie = mov
                # NO se arranca aquí: la animación solo corre mientras se ve la pantalla de carga, y
                # siempre desde el frame 0 (se lanza en iniciar_proceso_login). Precargamos el 1er frame.
                mov.jumpToFrame(0)
                # Tamaño A PANTALLA COMPLETA: lo fija _ajustar_tamano_clip según la pantalla.
                self._ajustar_tamano_clip()
                layout.addWidget(self.loading_logo, 0, Qt.AlignmentFlag.AlignCenter)
                return True
            from PyQt6.QtCore import QUrl
            from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PyQt6.QtMultimediaWidgets import QVideoWidget
            vw = QVideoWidget()
            self._loading_video_widget = vw
            player = QMediaPlayer(self)
            self._loading_audio = QAudioOutput(self)
            self._loading_audio.setMuted(True)          # la animación de carga no debe sonar
            player.setAudioOutput(self._loading_audio)
            player.setVideoOutput(vw)
            player.setSource(QUrl.fromLocalFile(ruta))
            try:
                player.setLoops(QMediaPlayer.Loops.Infinite)   # Qt ≥ 6.4
            except Exception:
                player.mediaStatusChanged.connect(
                    lambda s, p=player: (p.setPosition(0), p.play())
                    if s == QMediaPlayer.MediaStatus.EndOfMedia else None)
            self._loading_video = player
            # No se reproduce aquí: arranca desde 0 en iniciar_proceso_login (nunca reanuda).
            self._ajustar_tamano_clip()
            layout.addWidget(vw, 0, Qt.AlignmentFlag.AlignCenter)
            return True
        except Exception:
            return False

    def _detener_clip_carga(self):
        """Detiene la animación de carga (al ocultar la pantalla) para que no siga corriendo en segundo
        plano; la próxima vez se relanzará desde el frame 0."""
        try:
            mov = getattr(self, "_loading_movie", None)
            if mov is not None:
                mov.stop()
                mov.jumpToFrame(0)
            vid = getattr(self, "_loading_video", None)
            if vid is not None:
                vid.stop()
                vid.setPosition(0)
        except Exception:
            pass

    def _ajustar_tamano_clip(self):
        """Escala la animación de carga A PANTALLA COMPLETA: un cuadrado tan grande como la dimensión
        MENOR de la pantalla (cabe entero, centrado). Se llama al montar, al mostrar el overlay y al
        redimensionar la ventana."""
        try:
            from PyQt6.QtCore import QSize
            from PyQt6.QtWidgets import QApplication
            r = self.overlay.rect() if getattr(self, "overlay", None) is not None else None
            w = r.width() if r and r.width() > 0 else 0
            h = r.height() if r and r.height() > 0 else 0
            if w <= 0 or h <= 0:
                scr = QApplication.primaryScreen()
                g = scr.availableGeometry() if scr else None
                w, h = (g.width(), g.height()) if g else (1280, 800)
            lado = max(320, min(w, h))   # cuadrado = dimensión menor → cabe completo a pantalla completa
            if getattr(self, "_loading_movie", None) is not None:
                self._loading_movie.setScaledSize(QSize(lado, lado))
            if getattr(self, "_loading_video_widget", None) is not None:
                self._loading_video_widget.setFixedSize(lado, lado)
        except Exception:
            pass

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
            self._ajustar_tamano_clip()   # mantener la animación de carga a pantalla completa

    def closeEvent(self, event):
        """Cierre ordenado para evitar objetos Qt colgando."""
        try:
            if self._soma_tts:
                self._soma_tts.detener()
                self._soma_tts.shutdown()
            self._detener_soma()
        except Exception:
            pass
        # SOMA Copiloto IA — apagado ordenado del kernel + cierre del overlay (que es una ventana
        # top-level: hay que cerrarla explícitamente para que no quede flotando).
        try:
            from src.gui.soma import overlay as _soma_ov
            _ov = _soma_ov()
            if _ov is not None:
                _ov.close()
        except Exception:
            pass
        try:
            from src.soma import kernel as _soma_kernel
            _soma_kernel().shutdown()
        except Exception:
            pass
        # Videovigilancia: detener el grabador continuo (cierre ordenado de la terminal).
        try:
            from src.services.camaras import grabacion as _camrec
            _camrec.detener_automatico()
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
        # La animación de carga SIEMPRE arranca desde el principio (frame 0), nunca se reanuda desde el
        # último punto: se detiene, se rebobina y se vuelve a lanzar cada vez que aparece la pantalla.
        try:
            mov = getattr(self, "_loading_movie", None)
            if mov is not None:
                mov.stop()                              # → estado NotRunning
                mov.jumpToFrame(0)                      # rebobina al primer fotograma
                mov.start()                             # reproduce desde el principio
            vid = getattr(self, "_loading_video", None)
            if vid is not None:
                vid.stop()
                vid.setPosition(0)
                vid.play()
        except Exception:
            pass
        self.overlay.setGeometry(self.ventana_login.rect())
        self._ajustar_tamano_clip()   # animación de carga a pantalla completa (tamaño real ya conocido)
        self.overlay.show()
        self.overlay.raise_()
        self.configurar_monitorizacion_rfid()
        QApplication.processEvents()
        QTimer.singleShot(800, self.ejecutar_login)

    # NOTA: la verificación en dos pasos (MFA/TOTP) fue RETIRADA del login por decisión de producto.
    # Los antiguos helpers de reto (`_reto_mfa`) y de enrolamiento obligatorio (`_enrolar_mfa_obligatorio`)
    # se eliminaron: el login ya no exige ni fuerza 2º factor. El subsistema MFA sigue intacto para el
    # step-up de acciones críticas y para la gestión desde Configuración.

    def ejecutar_login(self):
        """Procesa las credenciales y gestiona el cambio de pantalla."""
        nombre = self.ventana_login.txt_nombre.text().strip()
        password = self.ventana_login.txt_password.text()
        # E1.2: login OFICIAL nominal por usuario (nombre o email), con Argon2id,
        # lockout y trazabilidad individual. (El login por perfil compartido queda
        # como modo legacy desactivado por defecto.)
        user_data = validar_login_usuario(nombre, password)

        if user_data:
            # NOTA (por decisión de producto): la verificación en dos pasos (MFA/TOTP) se RETIRA del
            # LOGIN. El acceso al sistema NO exige 2º factor ni fuerza enrolamiento obligatorio: todo
            # usuario con contraseña válida entra directamente. El resto del subsistema MFA sigue INTACTO
            # y operativo — el step-up (`pedir_step_up`/`step_up_sesion`) continúa protegiendo las acciones
            # críticas de negocio, y el panel de Configuración permite activar/gestionar el 2º factor.
            # Al no registrarse MFA reciente en el login, la 1ª acción crítica pedirá step-up con normalidad.
            try:
                from src.utils.observabilidad import registrar_evento
                registrar_evento("login", "acceso concedido", usuario=user_data.get("nombre"),
                                 perfil=user_data.get("perfil"))
            except Exception:
                pass
            sesion_global.iniciar_sesion(user_data)
            # UX-TPV-01: cargar y aplicar el perfil táctil guardado del usuario.
            try:
                from PyQt6.QtWidgets import QApplication

                from assets.estilo_global import aplicar_estilo_app
                from src.utils import perfil_tactil
                perfil_tactil.cargar_desde_preferencias(user_data.get("id"))
                aplicar_estilo_app(QApplication.instance())
            except Exception:
                pass
            self.abrir_menu_principal()
            self.ventana_login.txt_password.clear()
            self.overlay.hide()
            self._detener_clip_carga()
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
            try:
                from src.utils.observabilidad import registrar_evento
                registrar_evento("login", "acceso denegado", nivel="warning", usuario=nombre)
            except Exception:
                pass
            self.overlay.hide()
            self._detener_clip_carga()
            mostrar_mensaje(
                self,
                tr("login.denied_title", default="Acceso Denegado"),
                tr("login.denied_msg", default="Credenciales incorrectas."),
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
            # B7: usa la fuente canónica (empresa activa + ventana temporal), en vez de
            # un SELECT global de toda la tabla. Mismo esquema (fecha, codigo, cantidad).
            from src.db.conexion import obtener_ventas_ia
            df = obtener_ventas_ia()

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
        # Ajustes de SOMA definidos por el usuario (Configuración → SOMA). A prueba de fallos.
        try:
            from src.utils import tema as _tema_ui
            _cfg_soma = _tema_ui.cargar()
            _soma_activo = bool(_cfg_soma.get("soma_activo", True))
            _soma_voz = bool(_cfg_soma.get("soma_voz", True))
        except Exception:
            _soma_activo, _soma_voz = True, True

        # SOMA Copiloto IA — Fase 1: arranque del KERNEL residente (independiente de la voz).
        # Aditivo y a prueba de fallos: nunca rompe el arranque del ERP. Reutiliza worker/tts en vivo.
        # Si el usuario desactivó SOMA por completo, no se arranca el kernel ni el overlay.
        if _soma_activo:
            try:
                from src.soma import kernel as _soma_kernel
                _k = _soma_kernel()
                _k.iniciar(self)
                # Fase 3: navegador (fast-path de acciones) reutilizando la navegación existente.
                _k.set_navegador(_SomaNavegador(self))
                # Fase 2: instala el overlay/personaje (una sola vez) sobre la app, ya en reposo.
                from src.gui.soma import instalar_overlay as _soma_overlay
                QTimer.singleShot(400, lambda: _soma_overlay(self))
                # Fase 8: memoria/continuidad empresarial (aditivo; no toca ningún motor de SOMA).
                # Aprende hábitos en el Scheduler existente y saluda con continuidad por el camino
                # proactivo del kernel (kernel.intervenir). A prueba de fallos.
                try:
                    from src.soma import empresa as _soma_empresa
                    _soma_empresa.al_iniciar_sesion(_k)
                except Exception as _e2:
                    logger.debug(f"SOMA memoria empresarial no iniciada: {_e2}")
            except Exception as _e:
                logger.debug(f"SOMA kernel/overlay no iniciado: {_e}")
        # Videovigilancia (Fase 1 endurecimiento): arranque supervisado del grabador continuo de las
        # cámaras REALES de esta terminal (fuente RTSP/ONVIF; las simuladas de demo no se graban 24/7).
        # Diferido y a prueba de fallos: nunca rompe ni ralentiza el arranque.
        try:
            from src.services.camaras import grabacion as _camrec
            QTimer.singleShot(1500, _camrec.arrancar_automatico)
        except Exception as _e:
            logger.debug(f"Videovigilancia no iniciada: {_e}")
        # Scheduler Enterprise: registra (idempotente, en segundo plano) los jobs por defecto y los
        # selectivos Enterprise (SLA SAT, preventivo GMAO, automatización CRM, snapshots BI, ratios
        # financieros), de modo que queden PROGRAMADOS y visibles. NO se ejecutan pendientes aquí, a
        # propósito, para no generar carga en el arranque (decisión documentada).
        try:
            import threading as _th

            def _reg_jobs():
                try:
                    # Bloque 1 (Jobs Opt-In): sincroniza el CATÁLOGO completo — registra todos los
                    # callables Enterprise (ligeros + pesados) y aplica la política opt-in (pesados
                    # deshabilitados por defecto), respetando lo configurado por el usuario. No ejecuta.
                    from src.services import scheduler_registry as _reg
                    _reg.sincronizar()
                    logger.info("Scheduler: catálogo de jobs sincronizado (opt-in; sin ejecutar).")
                except Exception as _e4:
                    logger.debug(f"sincronización de jobs scheduler: {_e4}")

            _th.Thread(target=_reg_jobs, daemon=True, name="scheduler-registro").start()
        except Exception as _ej:
            logger.debug(f"registro de jobs scheduler no lanzado: {_ej}")
        # Voz de SOMA (escuchar por micro + hablar por TTS). Si el usuario la desactivó, SOMA sigue
        # disponible SOLO por chat de texto (ni escucha ni responde en voz alta).
        if not (_soma_activo and _soma_voz) or not _SOMA_DISPONIBLE:
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

    # ── SOMA Copiloto IA (Fase 2): puentes voz → kernel/overlay (aditivos) ────
    def _soma_kernel(self):
        """Devuelve el SomaKernel residente si está vivo (o None). A prueba de fallos."""
        try:
            from src.soma import kernel
            k = kernel()
            return k if k.esta_vivo() else None
        except Exception:
            return None

    def _soma_overlay_mensaje_usuario(self, texto):
        """Muestra en el overlay el texto reconocido por voz (best-effort)."""
        try:
            from src.gui.soma import overlay as _ov
            ov = _ov()
            if ov is not None:
                ov.mostrar_mensaje_usuario(texto)
        except Exception:
            pass

    def _soma_pose_por_accion(self, accion):
        """Fija la pose del personaje según el tipo de acción de voz y programa el asentado."""
        from PyQt6.QtCore import QTimer
        k = self._soma_kernel()
        if not k:
            return
        try:
            if accion in ("desconocido",):
                # No se fija pose aquí: la consulta se enruta al CEREBRO real (CopilotService),
                # que conducirá pensando → hablando → feliz (ver rama 'desconocido').
                return
            elif accion.startswith("nav_") or accion in ("cerrar_modulo", "cerrar_sesion"):
                # Navegar/ejecutar → procesando; después SOMA se aparta (repliega a reposo).
                k.al_procesar()
                QTimer.singleShot(1100, k.ocultar)
            else:
                # Consultas/ayuda → responde (EXPLICANDO) y se MANTIENE hasta que termina la voz.
                k.al_responder()
                self._soma_seguir_tts()
        except Exception:
            pass

    def _soma_seguir_tts(self):
        """Mantiene la pose EXPLICANDO mientras el TTS habla y vuelve a FELIZ al terminar el discurso.
        Sondea `SomaTTS.hablando` (no hay señal de fin), con arranque tolerante y tope de seguridad."""
        from PyQt6.QtCore import QTimer
        estado = {"empezo": False, "ticks": 0}

        def _tick():
            k = self._soma_kernel()
            tts = self._soma_tts
            if not k or not tts:
                return
            estado["ticks"] += 1
            try:
                hablando = bool(tts.hablando)
            except Exception:
                hablando = False
            if hablando:
                estado["empezo"] = True
                if k.estado != "HABLANDO":
                    k.al_responder()   # reafirma EXPLICANDO por si algo lo cambió
            else:
                if estado["empezo"]:
                    k.en_espera()      # terminó el discurso → FELIZ
                    return
                if estado["ticks"] > 24:  # ~3,6 s sin empezar a hablar → asumir que no habla
                    k.en_espera()
                    return
            if estado["ticks"] < 400:      # tope de seguridad (~60 s)
                QTimer.singleShot(150, _tick)

        QTimer.singleShot(150, _tick)

    def _soma_on_activado(self, tiene_comando_inline: bool):
        """
        Called in main thread when wake word is detected.
        tiene_comando_inline=True  → inline command follows; _soma_on_comando plays
                                     the action message — no confirmation needed here.
        tiene_comando_inline=False → wake-word only; play confirmation so user
                                     knows SOMA is listening before they speak.
        """
        logger.info(f"SOMA activado (inline={tiene_comando_inline})")
        # SOMA Copiloto IA — Fase 2: la wake word MUESTRA el overlay/personaje y pone a SOMA en
        # ESCUCHANDO (mismo flujo que pulsar el personaje). Aditivo y a prueba de fallos.
        k = self._soma_kernel()
        if k:
            try:
                k.activar(motivo="wake_word")
            except Exception:
                pass
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
        # SOMA Copiloto IA — Fase 2: el trabajador ha terminado de hablar → SOMA "piensa" mientras
        # entiende el comando (pose pensando). El pose final por acción se fija tras parsear.
        _k = self._soma_kernel()
        if _k:
            try:
                _k.al_pensar()
                self._soma_overlay_mensaje_usuario(texto)
            except Exception:
                pass
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
        # Pose final según la acción (procesando para navegar/ejecutar, explicando para responder,
        # error si no la entiende). El overlay lo representa; el kernel decide.
        self._soma_pose_por_accion(accion)

        # ── Eco del propio saludo de SOMA: ignorar en silencio ─────────────
        if accion == "ignorar":
            logger.info("SOMA: eco de saludo ignorado.")
            return

        # ── Cerrar módulo activo ("cierra X" / "cierra la ventana") ────────
        if accion == "cerrar_modulo":
            self._soma_cerrar_modulo(params)
            return

        # ── Desconocido → CEREBRO REAL (CopilotService + Especialistas IA) ──
        if accion == "desconocido":
            k = self._soma_kernel()
            if k:
                # Conversación real: el kernel delega en CopilotService, muestra la respuesta en el
                # overlay y la dice por voz (manteniendo la pose de explicando hasta terminar).
                k.procesar(texto_canonico, origen="voz")
            elif self._soma_tts:
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
            self._maximizar_a_area_trabajo()
            self.menu_principal.setFocus()

            # R1: en el PRIMER inicio (asistente no completado y datos de empresa aún básicos), lanzar
            # el asistente de PRIMEROS PASOS. Diferido para que el menú pinte antes; best-effort.
            QTimer.singleShot(500, self._lanzar_asistente_onboarding)

            logger.info(
                f"Navegación: Menú Principal cargado para {sesion_global.obtener_nombre()}"
            )
        except Exception as e:
            logger.error(f"Error crítico al abrir el menú: {e}")
            sesion_global.usuario_actual = None
            self.detectar_logout()

    def _lanzar_asistente_onboarding(self):
        """R1: muestra el asistente de PRIMEROS PASOS solo en el primer inicio real (no completado y
        empresa aún sin datos básicos). Si el asistente activa el modo simple, refresca el menú.
        Best-effort: cualquier fallo no rompe el arranque."""
        try:
            from src.services import onboarding
            if onboarding.completado() or not onboarding.datos_empresa_incompletos():
                return
            simple_antes = onboarding.modo_simple()
            from src.gui.onboarding_wizard import OnboardingWizard
            OnboardingWizard(self.menu_principal or self).exec()
            if self.menu_principal is not None and onboarding.modo_simple() != simple_antes:
                self.menu_principal.refrescar_menu()
        except Exception as e:
            logger.error("asistente onboarding: %s", e)

    def detectar_logout(self):
        """Gestiona el retorno al login o el cierre total de la aplicación."""
        # Al eliminarse el menú del QStackedWidget, Qt selecciona automáticamente el LOGIN como fallback; el
        # `singleShot` de abajo dejaba un hueco de ~50 ms en el que ese Login se PINTABA (el "flash" antes del
        # selector). Como `destroyed` se emite en la MISMA pila de llamada que el borrado (aún sin repintado),
        # conmutamos AQUÍ y de forma SÍNCRONA al selector de perfiles: el Login intermedio nunca llega a verse.
        if sesion_global.usuario_actual is None and getattr(self, "ventana_selector", None) is not None \
                and self.ventana_selector.tiene_perfiles():
            try:
                self.ventana_selector.cargar_perfiles()
                self.ventana_selector.buscador.clear()
            except Exception:
                pass
            self.setCurrentWidget(self.ventana_selector)
        QTimer.singleShot(50, self._procesar_retorno_o_cierre)

    def _procesar_retorno_o_cierre(self):
        """Gestiona el regreso al Login manteniendo la fluidez visual."""
        if sesion_global.usuario_actual is None:
            logger.info("Estado: Logout detectado. Transición fluida al Login...")
            self.menu_principal = (
                None  # nullify BEFORE switch so SOMA signals find nothing
            )
            # SOMA está ligado a la SESIÓN: al cerrar sesión, el personaje debe DESAPARECER (nunca debe
            # verse en el login) y la escucha por voz debe detenerse. En el próximo login, `_iniciar_soma`
            # reactiva el gate de sesión del overlay y rearranca el worker.
            try:
                from src.gui.soma import overlay as _soma_ov
                _ov = _soma_ov()
                if _ov is not None:
                    _ov.set_sesion_activa(False)
            except Exception:
                pass
            try:
                self._detener_soma()
            except Exception:
                pass
            # Al cerrar sesión se libera el perfil bloqueado y se vuelve al SELECTOR de perfil
            # (o al login directo si no hay perfiles registrados).
            try:
                self.ventana_login.liberar_perfil()
            except Exception:
                if hasattr(self.ventana_login, "txt_password"):
                    self.ventana_login.txt_nombre.clear()
                    self.ventana_login.txt_password.clear()
            try:
                self.ventana_selector.cargar_perfiles()
                self.ventana_selector.buscador.clear()
            except Exception:
                pass
            if getattr(self, "ventana_selector", None) is not None and \
                    self.ventana_selector.tiene_perfiles():
                self.setCurrentWidget(self.ventana_selector)
            else:
                self.setCurrentWidget(self.ventana_login)
                self.ventana_login.txt_nombre.setFocus()

            self._articulos_notificados.clear()
            self._maximizar_a_area_trabajo()
            self.raise_()
            self.activateWindow()
        else:
            logger.info("Estado: Cierre de ventana detectado. Finalizando proceso...")
            QApplication.quit()

    def _maximizar_a_area_trabajo(self):
        """Maximiza la ventana RESPETANDO la barra de tareas (`showMaximized()` respeta el área de trabajo,
        incluso sin marco). Antes de la PRIMERA aparición fija la geometría al área de trabajo para que la
        ventana SIN marco no DESTELLE un instante a tamaño pequeño mientras se crea y se maximiza."""
        try:
            if not self.isVisible():
                scr = self.screen() or QApplication.primaryScreen()
                if scr is not None:
                    self.setGeometry(scr.availableGeometry())
        except Exception:
            pass
        self.showMaximized()

    def _forzar_maximizacion_final(self):
        """Mantiene la ventana ajustada al área de trabajo (sin tapar la barra de tareas) y redibuja."""
        self._maximizar_a_area_trabajo()
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

        # Oculta la VENTANA DE CONSOLA negra que aparece al arrancar si la app se lanza con `python.exe`
        # (doble clic / acceso directo). Solo se oculta si ESTE proceso es el ÚNICO dueño de la consola: así,
        # si se ejecuta desde un terminal (que tiene más procesos adjuntos), NO se toca la terminal del usuario.
        # Lo ideal en producción es lanzar con `pythonw.exe` o el .exe congelado (sin consola); esto es la red
        # de seguridad para el resto de casos.
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            hwnd = k32.GetConsoleWindow()
            if hwnd:
                arr = (ctypes.c_uint * 4)()
                if k32.GetConsoleProcessList(arr, 4) == 1:      # somos el único proceso → consola propia
                    ctypes.windll.user32.ShowWindow(hwnd, 0)    # SW_HIDE
        except Exception:
            pass

    iniciar_backend()
    init_db()
    try:
        from src.utils.observabilidad import registrar_evento
        registrar_evento("arranque", "aplicación iniciada e init_db OK")
    except Exception:
        pass

    # ── Endurecimiento de producción al arranque (best-effort, no bloquea el inicio) ──
    # H7: backup programado (diario) si corresponde. H1: recuperación de ventas con
    # integración incompleta (re-dispara hooks idempotentes). H6: procesa la cola contable
    # pendiente (asientos) sin depender de abrir la pantalla de contabilidad.
    try:
        from src.db import backup as _bk
        _bk.backup_si_corresponde(intervalo_horas=24, motivo="programado")
    except Exception as _e:
        logger.debug(f"backup arranque: {_e}")
    try:
        from src.db import reconciliacion as _rec
        _r = _rec.reparar_ventas_pendientes(aplicar=True)
        if _r.get("reintegradas"):
            logger.warning("Recuperación arranque: %s ventas reintegradas", _r["reintegradas"])
    except Exception as _e:
        logger.debug(f"reconciliación arranque: {_e}")
    try:
        from src.services.contabilidad.posting import procesar_cola as _pc
        _pc()
    except Exception as _e:
        logger.debug(f"procesar_cola arranque: {_e}")
    try:
        from src.services.tesoreria import contabilidad as _tc
        _rt = _tc.reparar_tesoreria_pendiente(aplicar=True)
        if _rt.get("reparados"):
            logger.warning("Recuperación arranque: %s movimientos de tesorería contabilizados",
                           _rt["reparados"])
    except Exception as _e:
        logger.debug(f"reparar tesorería arranque: {_e}")

    # Traducción por IA (Nivel 2): enchufa el proveedor en i18n. Se activa solo
    # si hay backend LLM disponible (ANTHROPIC_API_KEY + paquete 'anthropic');
    # en caso contrario, degrada con elegancia (contenido dinámico sin traducir).
    try:
        from src.utils import ai_translator
        ai_translator.registrar_proveedor()
    except Exception as _e:
        logger.debug(f"AI translator no registrado: {_e}")

    # P2 (UX-TPV-01) — Escalado High-DPI fluido. En Qt6 el high-DPI está activo por
    # defecto; la política de redondeo PassThrough permite factores fraccionarios
    # (125/150/175 %) sin "saltar" a 100/200 %, evitando layouts rotos en tablets/4K.
    # Debe fijarse ANTES de crear el QApplication.
    try:
        from PyQt6.QtGui import QGuiApplication
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception as _e:
        logger.debug(f"High-DPI rounding policy no aplicada: {_e}")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    aplicar_estilo_app(app)
    app.setQuitOnLastWindowClosed(False)

    # Evita el "cuadrado blanco" que parpadea al arrancar: una ventana (sobre todo si es sin marco) pinta su
    # fondo con el color Window de la PALETA en el PRIMER frame, antes de aplicar el stylesheet. Si la paleta es
    # clara por defecto, se ve un flash blanco. Fijamos el fondo oscuro del tema en la paleta global → el primer
    # pintado ya es oscuro (sin flash).
    try:
        from PyQt6.QtGui import QColor, QPalette
        _pal = app.palette()
        _oscuro = QColor("#0E1117")
        for _rol in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
            _pal.setColor(_rol, _oscuro)
        app.setPalette(_pal)
    except Exception as _e:
        logger.debug(f"Paleta oscura global no aplicada: {_e}")

    # UX: suprime TODOS los mensajes flotantes (tooltips) en cualquier parte de la app.
    try:
        from PyQt6.QtCore import QEvent, QObject

        class _SinTooltips(QObject):
            def eventFilter(self, _obj, ev):
                return ev.type() == QEvent.Type.ToolTip   # True = consume el tooltip

        app._sin_tooltips = _SinTooltips()
        app.installEventFilter(app._sin_tooltips)
    except Exception as _e:
        logger.debug(f"Supresor de tooltips no instalado: {_e}")

    # Cursores personalizados (flecha/mano/texto) desde assets/cursores/ — DEGRADABLE (si no hay ficheros,
    # se usan los del sistema). El resto de estados del cursor no se tocan.
    try:
        from src.utils import cursores as _cursores
        _cursores.instalar(app)
    except Exception as _e:
        logger.debug(f"Cursores personalizados no instalados: {_e}")

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

    # ── ROL DEL TERMINAL ────────────────────────────────────────────────────────
    # Esta máquina arranca como CAJERO (ERP + TPV) o como AUTOCOBRO (kiosco de cliente) según la
    # CONFIGURACIÓN DEL ENTORNO (TERMINAL_ROL / ioc_terminales), nunca según un botón. Así el TPV del
    # cajero y el terminal de autoservicio quedan desacoplados, compartiendo el mismo motor lógico.
    try:
        from src.services.tpv.terminal_rol import descriptor as _rol_desc, es_autocobro as _es_autocobro
        logger.info(f"Rol de terminal: {_rol_desc()}")
        _autocobro = _es_autocobro()
    except Exception as _e:
        logger.warning(f"No se pudo resolver el rol de terminal (por defecto TPV): {_e}")
        _autocobro = False

    if _autocobro:
        from src.gui.autocobro import AutocobroWindow
        from src.services.tpv.terminal_rol import id_caja as _id_caja
        app.setQuitOnLastWindowClosed(True)   # kiosco: al cerrar el terminal, termina el proceso
        manager = AutocobroWindow(id_caja=_id_caja())
        manager.showFullScreen()
        app.aboutToQuit.connect(lambda: logger.info("Terminal de autocobro finalizado."))
        exit_code = app.exec()
        logger.info(f"Proceso (autocobro) finalizado con código: {exit_code}")
        sys.exit(exit_code)

    manager = SmartManagerApp()
    manager._maximizar_a_area_trabajo()

    app.aboutToQuit.connect(detener_backend)   # cierra el backend al salir (no deja huérfanos)
    app.aboutToQuit.connect(
        lambda: logger.info("Sistema Smart Manager finalizado. Terminal liberada.")
    )

    exit_code = app.exec()
    logger.info(f"Proceso finalizado con código: {exit_code}")
    sys.exit(exit_code)
