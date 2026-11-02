# --- Diagnóstico de crashes nativos (segfault/abort de Qt/C++): vuelca el stack de Python
# (de TODOS los hilos) en el momento del fallo — un crash nativo (p. ej. 0xc0000005 en
# Qt6Widgets.dll) mata el proceso antes de que `sys.excepthook` pueda hacer nada, así que esto
# es la ÚNICA vía para ver dónde estaba realmente el código Python en ese instante. Escribe a
# `logs/faulthandler.log` (persistente — sobrevive a que la terminal se cierre con el proceso;
# `faulthandler` necesita un descriptor de fichero real y no puede escribir a la vez en la
# terminal, así que para verlo EN VIVO mientras se prueba, en otra terminal:
#   Get-Content logs\faulthandler.log -Wait -Tail 0        (PowerShell)
# o usar `tools/ultimo_crash.py` después del cierre para ver solo el último volcado, ya
# recortado). Cada arranque escribe una marca con fecha/hora para poder ubicar qué volcados
# pertenecen a qué sesión de pruebas.
import faulthandler as _faulthandler
import os as _os

try:
    _os.makedirs("logs", exist_ok=True)
    _fh_log = open("logs/faulthandler.log", "a", encoding="utf-8")  # noqa: SIM115
    import datetime as _dt_fh
    _fh_log.write(f"\n===== ARRANQUE {_dt_fh.datetime.now().isoformat(timespec='seconds')} =====\n")
    _fh_log.flush()
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


def _silenciar_log_nativo_ffmpeg():
    """Qt Multimedia (backend FFmpeg, usado para `assets/startup.wav`/`assets/carga.mp4`) escribe
    DIRECTAMENTE a stdout/stderr el volcado de cada fichero que abre («Input #0, ...», sondeos de
    codecs de hardware de Windows como MFT) — es diagnóstico interno de FFmpeg, no pasa por el
    logger de Qt ni por `configurar_logging()`, así que no hay forma de silenciarlo desde ahí (bug
    real reportado: "sigue apareciendo mucho texto" en la terminal en cada arranque).

    Se silencia llamando a `av_log_set_level` de `avutil` — la MISMA DLL que PyQt6 ya trae
    incluida (`PyQt6/Qt6/bin/avutil-*.dll`), cargada aquí vía `ctypes` ANTES de crear el primer
    `QMediaPlayer` (ver `SmartManagerApp.__init__`). `av_log_set_level` es estado GLOBAL de esa
    librería dentro del proceso — a Windows le basta con que sea el mismo fichero en disco para
    reutilizar el mismo módulo ya cargado (no una copia aparte), así que afecta igual al backend
    de Qt use esta DLL antes o después. Se baja a solo errores reales (no se silencia del todo:
    un fallo real de códec se seguiría viendo). Best-effort/silencioso: si la DLL no está donde se
    espera (versión de Qt futura con otro nombre), no se silencia — nunca bloquea el arranque."""
    try:
        import ctypes
        import glob

        import PyQt6
        base = os.path.join(os.path.dirname(PyQt6.__file__), "Qt6", "bin")
        candidatos = glob.glob(os.path.join(base, "avutil-*.dll"))
        if not candidatos:
            return
        avutil = ctypes.CDLL(candidatos[0])
        AV_LOG_ERROR = 16
        avutil.av_log_set_level(ctypes.c_int(AV_LOG_ERROR))
    except Exception:
        pass


if os.name == "nt":
    _silenciar_log_nativo_ffmpeg()

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
from src.db.usuario import puede_iniciar_sesion, sesion_global, validar_login_usuario
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


def _backend_remoto_info(port: int, timeout: float = 1.5) -> dict | None:
    """Consulta `/salud` del backend que responde en `port`. None si no responde o no es un
    backend de Smart Manager identificable (no toca nada que no podamos reconocer con certeza)."""
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/salud", timeout=timeout) as r:
            datos = json.loads(r.read().decode("utf-8"))
        return datos if datos.get("servicio") == "smart-manager-backend" else None
    except Exception:
        return None


def _pid_escuchando_en_puerto(port: int) -> int | None:
    """PID del proceso en escucha en `port` (Windows, vía `netstat`) — solo se usa para matar un
    backend propio ya identificado como obsoleto, nunca a ciegas."""
    try:
        salida = subprocess.check_output(
            ["netstat", "-ano", "-p", "TCP"], text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        for linea in salida.splitlines():
            partes = linea.split()
            if len(partes) >= 5 and partes[1].endswith(f":{port}") and partes[3] == "LISTENING":
                return int(partes[-1])
    except Exception as e:
        logger.debug("_pid_escuchando_en_puerto(%s): %s", port, e)
    return None


def _matar_backend_obsoleto(port: int) -> bool:
    """Mata el proceso que ocupa `port`, YA CONFIRMADO como un backend de Smart Manager más viejo
    que el código actual (ver `iniciar_backend`). Devuelve True si el puerto queda libre."""
    pid = _pid_escuchando_en_puerto(port)
    if not pid:
        logger.warning("Backend obsoleto detectado en el puerto %s pero no se pudo identificar su "
                       "PID; no se toca.", port)
        return False
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        logger.info("Backend obsoleto (PID %s) detenido — se relanza con el código actual.", pid)
    except Exception as e:
        logger.warning("No se pudo detener el backend obsoleto (PID %s): %s", pid, e)
        return False
    import socket
    import time
    for _ in range(20):   # hasta ~2s a que el SO libere el puerto
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        libre = s.connect_ex(("127.0.0.1", port)) != 0
        s.close()
        if libre:
            return True
        time.sleep(0.1)
    return False


def detener_backend():
    """Termina el backend lanzado por esta instancia. Idempotente.

    YA NO se registra automáticamente en atexit/aboutToQuit (bug real reportado: "no quiero que
    se cierren los procesos antiguos y se reabran desde cero en cada arranque de la app" — con el
    backend muriendo al cerrar la app de escritorio, CADA arranque pagaba de nuevo todo su coste
    de inicio, aunque el código del backend no hubiera cambiado un ápice). El backend ahora
    persiste entre cierres/arranques de la app de escritorio a propósito: `iniciar_backend()` lo
    REUTILIZA si sigue vivo y no está desactualizado (ver `_codigo_propio_desactualizado` en
    `src/backend/app.py`, que el propio backend se autodiagnostica); solo se mata+relanza cuando
    de verdad hace falta. No hay riesgo de huérfanos acumulándose: solo hay UN backend por puerto
    en todo momento, nunca se lanza uno nuevo mientras otro siga sirviendo ese puerto.

    Esta función se conserva (Strangler Pattern — no se borra código que funciona) como utilidad
    manual para quien necesite forzar un apagado completo explícito."""
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
    """Inicia el backend API si no está corriendo, o REUTILIZA el que ya esté escuchando en su
    puerto si sigue vigente — a propósito NO se registra para matarlo al salir (ver
    `detener_backend`): persiste entre cierres/arranques de la app de escritorio, así que un
    arranque con un backend ya corriendo y vigente se ahorra por completo su coste de inicio
    (bootstrap de BD, registro de rutas, etc. — varios segundos reales medidos)."""
    global _backend_proc
    # En modo empaquetado (.exe) sys.executable ES el propio ejecutable: relanzarlo
    # con un script como argumento abriría la aplicación completa otra vez, en bucle
    # infinito. Por eso NO se lanza el backend externo cuando la app está congelada.
    if getattr(sys, "frozen", False):
        logger.info("Modo empaquetado: backend externo deshabilitado.")
        return
    try:
        import socket

        # El backend es opcional y puede no existir todavía: si no está, se omite.
        proyecto_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        backend_script = os.path.join(proyecto_raiz, "src", "backend", "app.py")
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
            # Ya hay algo en el puerto — persistido de un arranque anterior (a propósito, ver
            # docstring) o huérfano de una sesión de desarrollo. Reutilizarlo a ciegas sirve
            # endpoints obsoletos sin ningún aviso si el código SÍ cambió — así se pasaron varias
            # rondas de cambios sin verse reflejados en el navegador. El propio backend se
            # autodiagnostica (`codigo_desactualizado` en `/salud`, ver `_codigo_propio_
            # desactualizado` en `src/backend/app.py`): compara, de sus PROPIOS módulos ya
            # cargados bajo `src/`, si alguno se modificó en disco después de que él arrancara —
            # a diferencia del chequeo anterior (cualquier `.py` de TODO `src/`, incluido código
            # que el backend ni siquiera importa, como `src/gui/*`), esto ya no invalida un
            # backend sano solo porque se tocó un fichero de la GUI. Si es identificable como
            # backend de Smart Manager y SÍ está desactualizado, se sustituye por uno nuevo; si no
            # se puede identificar con certeza, se deja intacto (podría ser otra instancia de
            # Smart Manager compartiendo backend a propósito).
            info = _backend_remoto_info(port)
            if info is not None and info.get("codigo_desactualizado"):
                logger.info("Backend en el puerto %s tiene código desactualizado; sustituyendo.", port)
                if not _matar_backend_obsoleto(port):
                    logger.warning("No se pudo liberar el puerto %s del backend obsoleto; se deja "
                                   "el existente.", port)
                    return
            else:
                logger.info("Backend ya está corriendo y vigente (puerto %s) — reutilizado.", port)
                return
        logger.info("Iniciando backend API (puerto %s)...", port)
        # Se lanza con `-m src.backend.app` (NO con la ruta directa al .py): ejecutar el script
        # directamente deja `sys.path` sin la raíz del proyecto, así que TODOS los imports
        # `from src.xxx import ...` fallan dentro del subproceso (Storefront/Portal Proveedor/
        # Portal Empresa B2B/API REST quedan sin registrar, 404 en todas sus rutas) — bug
        # detectado al probar "Entrar al portal B2B" desde el escritorio empaquetado. `-m` con
        # `cwd=proyecto_raiz` reproduce exactamente cómo se arranca en desarrollo/tests.
        _backend_proc = subprocess.Popen(
            [sys.executable, "-m", "src.backend.app"],
            cwd=proyecto_raiz,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        # Deliberadamente SIN `atexit.register(detener_backend)`: debe persistir al cerrar la app
        # de escritorio (ver docstring). `detener_backend()` sigue disponible para un apagado
        # manual explícito.
    except Exception as e:
        logger.error(f"Error iniciando backend: {e}")


# NOTA: el portal web externo del proveedor (hilo daemon en el puerto 8099) se RETIRÓ en la
# refactorización del módulo Proveedores (Fase 1). El aprovisionamiento pasa a conectores B2B externos.


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
        # NOTA: el stack PRINCIPAL (login/selector/vídeo de carga/menú) NO se anima a propósito, para no
        # deslizar la pantalla del vídeo de carga previa al menú. La transición se aplica DENTRO de cada
        # módulo al abrirse (menu_principal → instalar_transiciones_en).

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
        # Marca de agua de la última llamada MCP externa YA avisada (ver `_tick_mcp_actividad`) —
        # None hasta la primera comprobación, para no avisar de actividad histórica previa al
        # arranque de esta sesión de escritorio.
        self._mcp_ultima_fecha_vista = None
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

        # Latido de sesión de escritorio (control de sesión única salvo SUPERADMIN, ver
        # src/db/sesiones_desktop.py): mientras haya un usuario logueado, refresca su fila cada
        # 30 s para que no expire por TTL; no hace nada si no hay sesión de escritorio registrada.
        self._timer_latido_sesion = QTimer(self)
        self._timer_latido_sesion.timeout.connect(self._latido_sesion_desktop)
        self._timer_latido_sesion.start(30_000)

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
        # ONBOARDING del primer perfil SUPERADMIN: instalación nueva (sin edición aún O sin ningún
        # perfil todavía, p. ej. edición fijada por entorno/SaaS pero BD vacía). Los perfiles SUPERADMIN
        # son los únicos que pueden dar de alta al resto de perfiles de empleado más adelante, así que
        # sin este paso una instalación nueva no tendría forma de crear su primer usuario.
        self.ventana_primer_admin = None
        try:
            if not self.ventana_selector.tiene_perfiles():
                from src.gui.primer_superadmin_wizard import PrimerSuperadminWindow
                self.ventana_primer_admin = PrimerSuperadminWindow()
                conectar_senal_segura(self.ventana_primer_admin.cuenta_creada, self._on_primer_admin_creado)
                self.addWidget(self.ventana_primer_admin)
        except Exception:
            self.ventana_primer_admin = None

        # ONBOARDING de ACTIVACIÓN de licencia central (Fase 3, licenciamiento central): solo
        # aparece si esta instalación usa un servidor central (`SMART_MANAGER_LICENCIA_URL`
        # configurada) y todavía no se ha activado. Instalaciones sin esa variable de entorno
        # (el caso de la inmensa mayoría hoy, comportamiento legacy) nunca ven esta pantalla.
        self.ventana_activacion_licencia = None
        try:
            import os as _os
            if _os.getenv("SMART_MANAGER_LICENCIA_URL"):
                from src.services.licencia_central import identidad as _lic_id
                if not _lic_id.activado():
                    from src.gui.activacion_licencia_wizard import ActivacionLicenciaWindow
                    self.ventana_activacion_licencia = ActivacionLicenciaWindow()
                    conectar_senal_segura(self.ventana_activacion_licencia.activada, self._on_licencia_activada)
                    self.addWidget(self.ventana_activacion_licencia)
        except Exception:
            self.ventana_activacion_licencia = None

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
        elif self.ventana_primer_admin is not None:
            self.setCurrentWidget(self.ventana_primer_admin)
        elif self.ventana_activacion_licencia is not None:
            self.setCurrentWidget(self.ventana_activacion_licencia)
        # Si hay perfiles registrados, se muestra primero el SELECTOR; si no, el login directo.
        elif self.ventana_selector.tiene_perfiles():
            self.setCurrentWidget(self.ventana_selector)
        else:
            self.setCurrentWidget(self.ventana_login)

    def _on_edicion_elegida(self, codigo):
        """Onboarding: el negocio eligió su tipo de comercio → persistido por `verticales.fijar_edicion`. Se
        reaplica el nombre de la app y los datos por defecto de la edición, y se continúa al flujo normal
        (alta del primer SUPERADMIN si aún no hay ningún perfil, si no, selector/login)."""
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
        if getattr(self, "ventana_primer_admin", None) is not None:
            self.setCurrentWidget(self.ventana_primer_admin)
        elif getattr(self, "ventana_activacion_licencia", None) is not None:
            self.setCurrentWidget(self.ventana_activacion_licencia)
        elif self.ventana_selector.tiene_perfiles():
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

    def _on_primer_admin_creado(self, nombre):
        """Onboarding: se creó el primer perfil SUPERADMIN → login con el nombre pre-rellenado
        (mismo patrón que `_on_perfil_elegido`) y se saca el asistente del stack (uso único)."""
        try:
            self.ventana_selector.cargar_perfiles()
        except Exception:
            pass
        self.ventana_login.fijar_perfil(nombre)
        if getattr(self, "ventana_activacion_licencia", None) is not None:
            self.setCurrentWidget(self.ventana_activacion_licencia)
        else:
            self.setCurrentWidget(self.ventana_login)
        if getattr(self, "ventana_primer_admin", None) is not None:
            try:
                self.removeWidget(self.ventana_primer_admin)
                self.ventana_primer_admin.deleteLater()
            except Exception:
                pass
            self.ventana_primer_admin = None

    def _on_licencia_activada(self):
        """Onboarding: paso de activación de licencia central terminado (con éxito u omitido) →
        continúa al login/selector y se saca el asistente del stack (uso único), mismo patrón que
        `_on_primer_admin_creado`."""
        self.setCurrentWidget(self.ventana_login)
        if getattr(self, "ventana_activacion_licencia", None) is not None:
            try:
                self.removeWidget(self.ventana_activacion_licencia)
                self.ventana_activacion_licencia.deleteLater()
            except Exception:
                pass
            self.ventana_activacion_licencia = None

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
        # Se crea CON PADRE (self.overlay). Sin padre sería un top-level huérfano: al fijarle el QMovie y
        # hacer jumpToFrame(0) ANTES de añadirlo al layout, Qt le crea en Windows una ventana NATIVA
        # decorada (con el icono de la app) que PARPADEA un instante en el centro durante el arranque.
        # Dándole padre desde el inicio se evita (addWidget no lo reparenta porque ya es hijo del overlay).
        self.loading_logo = QLabel(self.overlay)
        self.loading_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_logo.setStyleSheet("background: transparent; border: none;")
        self._loading_movie = None   # QMovie (gif/webp/apng)
        self._loading_video = None   # QMediaPlayer (mp4/webm)

        self._montar_clip_carga(layout)

        layout.addStretch(4)

    def _montar_clip_carga(self, layout) -> bool:
        """Busca un clip de animación de carga en `assets/` y lo monta en `layout`. Acepta animación
        (gif/webp/apng → QMovie, ideal: soporta transparencia y bucle) o vídeo (mp4/webm/mov →
        `QVideoSink`, fotograma a fotograma vía `_on_frame_video_carga` — permite croma key real,
        cosa que una superficie de vídeo nativa `QVideoWidget` no admite). Nombres admitidos:
        carga/cargando/loading/loader/spinner/animacion_carga. Devuelve True si montó un clip; False
        si no hay ninguno (se usa el logo estático)."""
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
                # Render NATIVO de Qt (`setMovie`), sin interceptar fotogramas en Python — rápido
                # (decodificación + escalado en C++, sin una vuelta por numpy 24 veces/segundo).
                #
                # Esto SOLO es seguro porque `assets/carga.webp` ya tiene el canal alfa REAL y
                # limpio (horneado por `tools/generar_animacion_carga.py` desde el vídeo con croma,
                # ver ese script para el porqué: el croma key EN TIEMPO REAL —ver
                # `_on_frame_video_carga` más abajo— obligaba a elegir entre fluidez y calidad en
                # cada fotograma; hornearlo una sola vez, sin presupuesto de tiempo, resuelve ambas
                # a la vez). Un `carga.webp` ANTERIOR, de otro origen, tenía un defecto real (alfa
                # parcial de fábrica, ~185-197/255, no solo en el borde antialiasado) que SÍ
                # necesitaba una corrección por fotograma — si un futuro asset volviera a traer ese
                # mismo defecto, la corrección es volver a exportarlo bien (como aquí), no
                # reintroducir una pasada de numpy en el camino caliente de cada fotograma.
                self.loading_logo.setMovie(mov)
                self._loading_movie = mov
                # NO se arranca aquí ni se hace jumpToFrame/escalado: renderizar un frame durante __init__
                # (cuando la ventana de login aún NO está mostrada) fuerza a Qt a materializar el overlay
                # como ventana NATIVA suelta → PARPADEO de un marco vacío en el arranque. Tanto el
                # jumpToFrame(0) como el escalado ya se hacen al MOSTRAR el spinner (iniciar_proceso_login).
                layout.addWidget(self.loading_logo, 0, Qt.AlignmentFlag.AlignCenter)
                return True
            from PyQt6.QtCore import QUrl
            from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
            # Se renuncia a `QVideoWidget` (superficie de vídeo NATIVA, opaca — no admite
            # transparencia/alpha real) a favor de `QVideoSink`: entrega cada fotograma como
            # `QVideoFrame`, que se procesa a mano (croma key, ver `_on_frame_video_carga`) y se
            # pinta en `self.loading_logo` (el mismo `QLabel` ya usado para gif/webp) — mismo
            # criterio que el alfa reforzado del webp (`_on_frame_carga`): procesar fotograma a
            # fotograma con numpy en vez de depender de lo que el propio backend de vídeo soporte.
            sink = QVideoSink(self)
            sink.videoFrameChanged.connect(self._on_frame_video_carga)
            self._loading_video_sink = sink
            player = QMediaPlayer(self)
            self._loading_audio = QAudioOutput(self)
            self._loading_audio.setMuted(True)          # la animación de carga no debe sonar
            player.setAudioOutput(self._loading_audio)
            player.setVideoSink(sink)
            player.setSource(QUrl.fromLocalFile(ruta))
            try:
                player.setLoops(QMediaPlayer.Loops.Infinite)   # Qt ≥ 6.4
            except Exception:
                player.mediaStatusChanged.connect(
                    lambda s, p=player: (p.setPosition(0), p.play())
                    if s == QMediaPlayer.MediaStatus.EndOfMedia else None)
            self._loading_video = player
            # No se reproduce ni se escala aquí (arranca/escala en iniciar_proceso_login): evitar
            # realizar el widget durante __init__ para no provocar el parpadeo del overlay en el arranque.
            layout.addWidget(self.loading_logo, 0, Qt.AlignmentFlag.AlignCenter)
            return True
        except Exception:
            return False

    def _on_frame_video_carga(self, frame):
        """Croma key en tiempo real sobre `assets/carga.mp4`: el usuario sustituyó el fondo del
        clip por un VERDE croma para poder retirarlo e integrar la animación con el fondo real de
        la app — `QVideoSink` entrega cada fotograma como `QVideoFrame` (sin pasar por una
        superficie de vídeo nativa opaca), se convierte a `QImage` y se procesa con numpy (mismo
        criterio que `_on_frame_carga` para el alfa del webp): el canal G muy por encima de R y B
        se vuelve transparente, con una RAMPA de transición (no un corte binario duro) para que el
        contorno del sujeto no quede dentado, más una atenuación barata del verde residual del
        borde (spill) para evitar un halo verdoso al componer sobre el fondo oscuro de la app.

        RENDIMIENTO (bug real, reportado como "la animación se corta muchísimo" tras el primer
        intento): procesar con numpy a la resolución NATIVA del clip (1280×720) tardaba ~95-110ms/
        fotograma medido — muy por encima del presupuesto de 41.7ms a 24fps, así que la mayoría de
        fotogramas llegaban tarde y Qt los descartaba (de ahí el "corte": no es un recorte visual,
        es la animación congelándose/saltando fotogramas). Fix: el numpy se hace sobre el
        fotograma reducido a MITAD de tamaño (menos bytes que mover en cada paso) y la matemática
        del croma en sí se fusiona en menos pasos/arrays temporales (evita la promoción a float64
        de numpy en operaciones de punto flotante que no la necesitaban) — medido en ~25ms/fotograma.

        CALIDAD (bug real, 2º reporte tras el fix de rendimiento anterior: "contorno verde croma" +
        "pixelado"): la 1ª versión de este fix usaba `FastTransformation` (vecino más próximo, SIN
        interpolar) para los dos reescalados (reducir antes del numpy, ampliar después) — con
        pantallas más grandes que la mitad de la resolución del clip, el reescalado final amplificaba
        cada píxel en un bloque visible (de ahí el "pixelado"), y la atenuación de verde residual
        (spill) solo quitaba la MITAD del exceso de verde en los píxeles semitransparentes del borde,
        dejando un tinte verdoso que esa ampliación por bloques volvía claramente visible como un
        "contorno" (antes, a resolución nativa con reescalado suave, era demasiado sutil para
        notarse). Fix: `SmoothTransformation` (bilineal) en AMBOS reescalados — interpola en vez de
        repetir píxeles, sigue costando ~25ms/fotograma, medido — y el de-spill ahora quita el
        exceso de verde POR COMPLETO (`min(verde, max(rojo,azul))`, no la mitad), así ningún píxel
        del borde conserva tinte verdoso, se vea ampliado o no.

        Degrada con honestidad: si algo falla, se pinta el fotograma original (nunca una pantalla
        en blanco), sin croma — un vídeo con fondo verde visible en vez de uno transparente roto."""
        if frame is None or not frame.isValid():
            return
        img = frame.toImage()
        if img.isNull():
            return
        try:
            import numpy as np
            from PyQt6.QtGui import QImage, QPixmap
            # Downscale a mitad de tamaño ANTES de tocar numpy (hecho en Qt/C++, barato) — todo el
            # procesado de croma ocurre sobre la mitad de píxeles, no sobre el fotograma nativo.
            # SmoothTransformation (bilineal, no vecino-más-próximo): evita bloques de píxel visibles
            # tanto aquí como en la ampliación final.
            w0, h0 = img.width(), img.height()
            proc_w, proc_h = max(1, w0 // 2), max(1, h0 // 2)
            img = img.scaled(proc_w, proc_h, Qt.AspectRatioMode.IgnoreAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
            img = img.convertToFormat(QImage.Format.Format_RGBA8888)
            w, h = img.width(), img.height()
            ptr = img.bits(); ptr.setsize(img.sizeInBytes())
            arr = np.frombuffer(ptr, np.uint8).reshape((h, w, 4)).copy()
            r = arr[..., 0].astype(np.int16)
            g0 = arr[..., 1].astype(np.int16)
            b = arr[..., 2].astype(np.int16)
            maxrb = np.maximum(r, b)
            exceso = g0 - maxrb   # cuánto "se sale" el verde sobre el resto de canales
            # exceso<=40 → opaco (sujeto real); exceso>=80 → transparente (fondo croma); rampa lineal
            # entre medias (evita un borde recortado a tijera alrededor del sujeto). float32, no
            # float64 (la precisión doble no aporta nada aquí y numpy la usa por defecto si no se
            # especifica, duplicando el trabajo de memoria en el paso más caro de la cadena).
            alpha = np.clip((80 - exceso) * np.float32(1.0 / 40.0), 0.0, 1.0)
            # Realce de opacidad del sujeto (petición explícita, mismo criterio que
            # `tools/generar_animacion_carga.py::_croma_key`, mantenido en sincronía): gamma 0.6
            # SOLO sobre el alpha ya calculado — un píxel de fondo puro (alpha==0) se queda en 0,
            # nunca gana opacidad el croma verde, solo el sujeto ya parcialmente opaco.
            alpha = np.power(alpha, 0.6, dtype=np.float32)
            arr[..., 3] = (alpha * 255).astype(np.uint8)
            # De-spill TOTAL (no parcial): capa el verde al máximo de rojo/azul — elimina el exceso
            # de verde del todo, en vez de solo atenuarlo a la mitad (eso dejaba un tinte verdoso en
            # los píxeles semitransparentes del borde, visible como "contorno verde").
            arr[..., 1] = np.minimum(g0, maxrb).astype(np.uint8)
            out = QImage(arr.tobytes(), w, h, QImage.Format.Format_RGBA8888).copy()
            destino = getattr(self, "_video_tam_destino", None) or (w, h)
            pm = QPixmap.fromImage(out).scaled(
                destino[0], destino[1],
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            self.loading_logo.setPixmap(pm)
        except Exception:
            from PyQt6.QtGui import QPixmap
            self.loading_logo.setPixmap(QPixmap.fromImage(img))

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
        """Escala la animación de carga. Dos criterios DISTINTOS a propósito, según el tipo de
        clip:

        - GIF/WEBP/APNG (`QMovie`, `assets/carga.webp`): SIN escalar — a su tamaño NATIVO/original
          (bug real, 2ª vuelta: a pantalla completa `QMovie.setScaledSize()` se veía "pixelada" —
          la estrella es un PNG/WebP de detalle fino, y el reescalado interno de `QMovie` por
          fotograma, pensado para ir barato en cada tick de la animación, no es tan nítido como un
          `QImage.scaled(..., SmoothTransformation)` puntual; ampliarlo a toda la pantalla hacía el
          efecto mucho más visible que a tamaño pequeño/nativo). Sin `setScaledSize`, `QMovie`
          pinta cada fotograma 1:1 — la nitidez máxima posible, sin ningún reescalado de por medio.
        - Vídeo (`QVideoSink`, solo si algún día se usa un clip que no exista como webp): pantalla
          COMPLETA real, sin recorte a cuadrado — el croma key en tiempo real (`_on_frame_video_
          carga`) ya hace su propio reescalado con `SmoothTransformation`, así que ahí sí tiene
          sentido pedir una cobertura total.
        Se llama al montar, al mostrar el overlay y al redimensionar la ventana."""
        try:
            from PyQt6.QtWidgets import QApplication
            if getattr(self, "_loading_movie", None) is not None:
                self.loading_logo.setFixedSize(self.loading_logo.sizeHint())
            if getattr(self, "_loading_video_sink", None) is not None:
                r = self.overlay.rect() if getattr(self, "overlay", None) is not None else None
                w = r.width() if r and r.width() > 0 else 0
                h = r.height() if r and r.height() > 0 else 0
                if w <= 0 or h <= 0:
                    scr = QApplication.primaryScreen()
                    g = scr.availableGeometry() if scr else None
                    w, h = (g.width(), g.height()) if g else (1280, 800)
                w, h = max(1, w), max(1, h)
                self._video_tam_destino = (w, h)
                self.loading_logo.setFixedSize(w, h)
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

    def _latido_sesion_desktop(self):
        """Refresca el latido de la sesión de escritorio activa (ver `_timer_latido_sesion`)."""
        id_sesion = getattr(sesion_global, "id_sesion_desktop", None)
        if not id_sesion:
            return
        try:
            from src.db import sesiones_desktop
            sesiones_desktop.actualizar_latido(id_sesion)
        except Exception:
            pass

    def _tick_mcp_actividad(self):
        """Avisa (FloatingNotification, mismo patrón que el aviso de stock bajo en
        `verificar_ia_reposicion`) cuando una app externa (ChatGPT/Claude Desktop) hace una llamada
        MCP real (`tools/call`) contra `/mcp`. El backend (mismo proceso, puerto 8090) y el
        escritorio son procesos SEPARADOS que comparten la misma base de datos — la señal
        desktop↔backend es la traza mínima que `mcp_server.transport._registrar_actividad_tool_call`
        deja en `auditoria_logs` (tabla='mcp'), leída aquí vía `db.auditoria.listar_por_tabla` (ya
        existente, cliente fino de auditoría) — sin tabla/endpoint nuevos. Cadencia de 15s, mismo
        mecanismo de `QTimer` que `_timer_ic_sync_canales` (2 min) usa para su propio latido."""
        try:
            from src.db.auditoria import listar_por_tabla
            from src.db.empresa import empresa_actual_id
            id_empresa = empresa_actual_id()
            filas = listar_por_tabla(["mcp"], id_empresa=id_empresa, limite=5)
        except Exception as e:
            logger.debug(f"SOMA MCP: comprobación de actividad fallida: {e}")
            return
        if not filas:
            return
        ultima = filas[0]
        if not str(ultima.get("accion") or "").startswith("MCP_TOOL_CALL"):
            return
        fecha = ultima.get("fecha")
        if self._mcp_ultima_fecha_vista is None:
            # Primera comprobación de la sesión: solo fija la marca de agua, nunca notifica
            # actividad que ya existía antes de que esta ventana arrancara.
            self._mcp_ultima_fecha_vista = fecha
            return
        if not fecha or (self._mcp_ultima_fecha_vista and fecha <= self._mcp_ultima_fecha_vista):
            return
        self._mcp_ultima_fecha_vista = fecha
        detalle = str(ultima.get("detalles") or "").strip()
        msg = (f"SOMA: Petición MCP externa procesada con éxito ({detalle})" if detalle
               else "SOMA: Petición MCP externa procesada con éxito.")
        try:
            self.notificacion_mcp = FloatingNotification(msg)
            screen = QApplication.primaryScreen().availableGeometry()
            self.notificacion_mcp.move(screen.width() - 380, screen.height() - 120)
            self.notificacion_mcp.show()
        except Exception as e:
            logger.debug(f"SOMA MCP: no se pudo mostrar la notificación: {e}")

    def closeEvent(self, event):
        """Cierre ordenado para evitar objetos Qt colgando."""
        try:
            if sesion_global.usuario_actual:
                sesion_global.cerrar_sesion()
        except Exception:
            pass
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

        if user_data and not puede_iniciar_sesion(user_data.get("id"), user_data.get("perfil")):
            self.overlay.hide()
            self._detener_clip_carga()
            mostrar_mensaje(
                self,
                tr("login.multisesion_title", default="Sesión ya activa"),
                tr(
                    "login.multisesion_msg",
                    default="Este usuario ya tiene una sesión activa en otro equipo. Solo los perfiles "
                    "SUPERADMIN pueden iniciar sesión en varios equipos a la vez.",
                ),
                nivel="error",
            )
            self.ventana_login.txt_password.clear()
            self.ventana_login.txt_password.setFocus()
            return

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
            # Centro OBLIGATORIO para SUPERADMIN (pedido explícito), SIN bloquear el login: antes el
            # diálogo modal se abría ANTES de ocultar el overlay de carga, solapándose con su
            # animación. Ahora el SUPERADMIN entra directo al Menú Principal y, una vez pintado, se
            # abre solo (diferido, mismo criterio que SOMA arriba) el selector "Cambiar de Centro"
            # si todavía no hay un centro activo — ver `_abrir_selector_centro_tras_login`.
            if (user_data.get("perfil") or "").upper() == "SUPERADMIN":
                QTimer.singleShot(
                    400, lambda ud=user_data: self._abrir_selector_centro_tras_login(ud))
            # Licenciamiento central (Fase 3, ver plan): primera verificación diferida (mismo
            # motivo que SOMA arriba) + repetición cada 24h mientras la app esté abierta. Nunca
            # bloquea el login ni el arranque — sin servidor configurado o sin conexión, es un
            # no-op silencioso (ver `services.licencia_central.sincronizacion`).
            QTimer.singleShot(1500, self._verificar_licencia_central)
            if not hasattr(self, "_timer_licencia_central"):
                self._timer_licencia_central = QTimer(self)
                self._timer_licencia_central.timeout.connect(self._verificar_licencia_central)
                self._timer_licencia_central.start(24 * 60 * 60 * 1000)
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

    def _abrir_selector_centro_tras_login(self, user_data):
        """Centro OBLIGATORIO para SUPERADMIN (pedido explícito) — SIN bloquear el login ni tapar
        la animación de carga del overlay (el diálogo modal antiguo se abría ANTES de ocultarlo).
        El SUPERADMIN ya está viendo el Menú Principal cuando esto se dispara (diferido 400 ms);
        si todavía no hay un centro activo, se abre automáticamente el MISMO selector "Cambiar de
        Centro" del chip de la esquina superior izquierda (`MenuPrincipal._abrir_selector_centro`,
        reutilizado con `es_login=True` para que cerrarlo sin elegir redirija al selector de
        perfil — ver `menu_principal.py`). Degradación honesta: instalación nueva sin NINGÚN
        centro dado de alta → no se exige nada (sería una elección imposible)."""
        try:
            from src.db.empresa import empresa_actual_id, tienda_actual_id
            if tienda_actual_id():
                return
            from src.db import centros as centros_db
            id_empresa = empresa_actual_id()
            uid = user_data.get("id")
            if not centros_db.listar_centros(id_empresa, creado_por_id=uid):
                return
            if self.menu_principal is not None:
                self.menu_principal._abrir_selector_centro(es_login=True)
        except Exception as e:
            logger.error(f"Error abriendo selector de centro tras login: {e}")

    # ============================================================
    # BLOQUE IA / PREDICCIÓN
    # ============================================================
    def predecir_ventas_semanales(self):
        """IA Prophet para predecir demanda.

        Import PEREZOSO (dentro del método, no a nivel de módulo): importar `prophet` tarda
        ~3.3s en frío (mide su propio backend cmdstan/Stan) — pagar ese coste en CADA arranque de
        la app, se use o no esta pantalla en la sesión, es puro despilfarro. Se difiere al primer
        uso real (bug real reportado: "la app tarda en abrirse", confirmado con `time.perf_counter`
        que este import por sí solo eran ~3.3 de los segundos de retraso)."""
        try:
            from prophet import Prophet
        except ImportError:
            Prophet = None
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
    def _verificar_licencia_central(self):
        """Lanza `services.licencia_central.sincronizacion.ejecutar_verificacion()` en un hilo en
        segundo plano — la llamada HTTP no debe bloquear nunca el hilo de la interfaz, igual que
        SOMA (ver `_iniciar_soma`). Best-effort: cualquier fallo queda dentro del propio hilo."""
        import threading
        from src.services.licencia_central import sincronizacion
        threading.Thread(target=sincronizacion.ejecutar_verificacion, daemon=True).start()

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

        # SOMA restringido a SUPERADMIN: se gatea aquí, en el ÚNICO punto de arranque real (kernel +
        # overlay + worker de voz + TTS cuelgan todos de `_soma_activo` más abajo), en vez de ocultar
        # solo el icono — así ningún perfil no-SUPERADMIN llega a tener kernel/overlay/escucha activos,
        # ni aunque cambie el ajuste `soma_activo` de la empresa. Mismo criterio que la restricción de
        # "Proveedores"/"GENERAR PERFIL EMPLEADO" a SUPERADMIN (gate en el origen, no solo en la UI).
        _soma_activo = _soma_activo and sesion_global.es_superadmin()

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
                try:
                    # Delegación de tareas repetitivas a SOMA: suscribe al Event Bus los tipos del
                    # catálogo que reaccionan a un evento (p. ej. CORREO_RECIBIDO/CENTRO_CREADO) —
                    # idempotente, no ejecuta nada hasta que ocurra el evento real.
                    from src.services.soma_delegacion import wiring as _soma_deleg_wiring
                    _soma_deleg_wiring.registrar_suscripciones()
                    logger.info("Delegación SOMA: suscripciones al Event Bus registradas.")
                except Exception as _e5:
                    logger.debug(f"suscripciones de delegación SOMA no registradas: {_e5}")

            _th.Thread(target=_reg_jobs, daemon=True, name="scheduler-registro").start()
        except Exception as _ej:
            logger.debug(f"registro de jobs scheduler no lanzado: {_ej}")
        # Integraciones Comerciales: worker que drena la cola local de exportación de stock encolada
        # tras cada venta (VENTA_REGISTRADA -> sync_venta_listener -> cola_jobs -> sync_worker). El
        # checkout solo ENCOLA (nunca llama a la API externa en línea), así que algo tiene que drenar
        # esa cola periódicamente o los trabajos se quedan en "pendiente" para siempre. El job queda
        # registrado en el Scheduler (intervalo_horas=1, la granularidad mínima que admite la columna
        # INT) para auditoría/panel, pero el drenado REAL cada pocos minutos lo activa este latido —
        # MISMO patrón exacto que soma/observador.SomaObserver._tick_scheduler (90 s) usa para activar
        # "soma_observacion" llamando a scheduler.ejecutar_job directamente, sin esperar a
        # scheduler.ejecutar_pendientes()/intervalo_horas. 2 minutos: rápido para que el stock llegue a
        # los canales minutos después de la venta, sin generar carga perceptible en segundo plano.
        try:
            if not hasattr(self, "_timer_ic_sync_canales"):
                from src.services.marketplace.integraciones_comerciales import \
                    sync_worker as _icsw
                _icsw.registrar_jobs_sync_canales()
                # Carritos B2B abandonados (Smart Suppliers): misma razón exacta que ic_sync_canales
                # — scheduler_jobs.intervalo_horas es INT (mínimo 1h) pero el umbral de abandono es de
                # 2h y hace falta comprobarlo con más frecuencia que una vez por hora para que el
                # aviso "Reanudar Pedido"/la oferta del proveedor aparezcan poco después de cumplirse
                # el umbral. Reutiliza el MISMO latido de 2 min en vez de crear un segundo QTimer.
                try:
                    from src.services.compras import b2b_carrito_abandono as _icab
                    _icab.registrar_jobs_abandono()
                except Exception as _eicab:
                    logger.debug(f"b2b_carrito_abandono: registro de job no lanzado: {_eicab}")
                # Carritos del STOREFRONT PÚBLICO abandonados (Motor de Alta Conversión e-Commerce):
                # misma razón exacta que el bloque B2B de arriba — umbral de 30 min, más fino que la
                # granularidad horaria del Scheduler, reutiliza este mismo latido de 2 min.
                try:
                    from src.services.comercio_digital import carrito_abandono as _cdab
                    _cdab.registrar_jobs_abandono()
                except Exception as _ecdab:
                    logger.debug(f"cd_carrito_abandono: registro de job no lanzado: {_ecdab}")
                # Click & Collect (Generador de Apps Móviles PWA, Fase 4): caducidad automática a
                # 24h de las reservas de recogida no recogidas (libera stock, reembolsa, notifica —
                # motor YA COMPLETO en `comercio_digital.pickup.expirar_vencidas`, hasta ahora nunca
                # invocado). Misma razón que los dos bloques de arriba: el umbral es más fino que la
                # granularidad horaria del Scheduler clásico, así que se reutiliza este mismo latido
                # de 2 min en vez de crear un tercer QTimer.
                try:
                    from src.services.comercio_digital import pickup as _cdpk
                    _cdpk.registrar_job()
                except Exception as _ecdpk:
                    logger.debug(f"cd_pickup_expirar: registro de job no lanzado: {_ecdpk}")

                def _tick_ic_sync_canales():
                    try:
                        from src.services import scheduler as _sch
                        _sch.ejecutar_job("ic_sync_canales")
                    except Exception as _eick:
                        logger.debug(f"ic_sync_canales tick: {_eick}")
                    try:
                        from src.services import scheduler as _sch
                        _sch.ejecutar_job("b2b_carrito_abandono")
                    except Exception as _eicab2:
                        logger.debug(f"b2b_carrito_abandono tick: {_eicab2}")
                    try:
                        from src.services import scheduler as _sch
                        _sch.ejecutar_job("cd_carrito_abandono")
                    except Exception as _ecdab2:
                        logger.debug(f"cd_carrito_abandono tick: {_ecdab2}")
                    try:
                        from src.services.comercio_digital import pickup as _cdpk2
                        _cdpk2.expirar_vencidas()
                    except Exception as _ecdpk2:
                        logger.debug(f"cd_pickup_expirar tick: {_ecdpk2}")

                self._timer_ic_sync_canales = QTimer(self)
                self._timer_ic_sync_canales.timeout.connect(_tick_ic_sync_canales)
                self._timer_ic_sync_canales.start(120_000)   # 2 minutos
        except Exception as _eicsw:
            logger.debug(f"Integraciones comerciales: worker de exportación no iniciado: {_eicsw}")
        # SOMA Conectores Externos (MCP): aviso casi en vivo de actividad MCP real (ver
        # `_tick_mcp_actividad`). Cadencia corta (15s, no 2 min como el latido de arriba) porque es
        # un aviso al usuario, no un job de sincronización en segundo plano.
        try:
            if not hasattr(self, "_timer_mcp_actividad"):
                self._timer_mcp_actividad = QTimer(self)
                self._timer_mcp_actividad.timeout.connect(self._tick_mcp_actividad)
                self._timer_mcp_actividad.start(15_000)
        except Exception as _emcp:
            logger.debug(f"SOMA MCP: aviso de actividad no iniciado: {_emcp}")
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

            logger.info(
                f"Navegación: Menú Principal cargado para {sesion_global.obtener_nombre()}"
            )
        except Exception as e:
            logger.error(f"Error crítico al abrir el menú: {e}")
            sesion_global.usuario_actual = None
            self.detectar_logout()

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

    # Deliberadamente SIN `app.aboutToQuit.connect(detener_backend)`: el backend debe PERSISTIR al
    # cerrar la app de escritorio (petición explícita — ver docstring de `iniciar_backend`/
    # `detener_backend`), para que el siguiente arranque lo reutilice en vez de pagar de nuevo
    # todo su coste de inicio.
    app.aboutToQuit.connect(
        lambda: logger.info("Sistema Smart Manager finalizado. Terminal liberada.")
    )

    exit_code = app.exec()
    logger.info(f"Proceso finalizado con código: {exit_code}")
    sys.exit(exit_code)
