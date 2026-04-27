import matplotlib
from src.utils.rfid_gateway import LectorZebraGateway

matplotlib.use("Agg")  # Fuerza el modo sin interfaz para evitar bloqueos
import matplotlib.pyplot as plt
import sys
import os
import pandas as pd
import logging
from datetime import datetime
import warnings
import subprocess
from assets.estilo_global import aplicar_estilo_app, mostrar_mensaje

# --- PARCHE 1: SILENCIAR AVISOS Y ERRORES DE GEOMETRÍA ---
warnings.filterwarnings("ignore", category=UserWarning, module="pandas")
os.environ["QT_LOGGING_RULES"] = "qt.qpa.gl=false"

# Intentar importar Prophet
try:
    from prophet import Prophet
except ImportError:
    Prophet = None

from PyQt6.QtWidgets import (
    QApplication,
    QStackedWidget,
    QMessageBox,
    QWidget,
    QLabel,
    QVBoxLayout,
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QRect
from PyQt6.QtGui import QColor

# Importaciones internas
from src.db.conexion import init_db, obtener_conexion
from src.db.usuario import validar_login, sesion_global
from src.gui.login import LoginWindow
from src.gui.menu_principal import MenuPrincipal

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =========================================================
# UTILIDADES DE SEÑALES / SLOTS
# =========================================================
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


# =========================================================
# BACKEND
# =========================================================
def iniciar_backend():
    """Inicia el backend API si no está corriendo."""
    try:
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(("127.0.0.1", 5000))
        sock.close()
        if result != 0:
            logger.info("Iniciando backend API...")
            subprocess.Popen(
                [sys.executable, "src/backend/app.py"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        else:
            logger.info("Backend ya está corriendo.")
    except Exception as e:
        logger.error(f"Error iniciando backend: {e}")


# =========================================================
# FUNCIÓN PUENTE (BRIDGE) PARA ALERTAS
# =========================================================
def verificar_reposicion_y_alertar(parent_window=None):
    """Llama al método de verificación de IA en la instancia global del manager."""
    global manager
    if "manager" in globals() and manager is not None:
        manager.verificar_ia_reposicion()


# =========================================================
# NOTIFICACIÓN FLOTANTE (IA)
# =========================================================
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
        self.label.setStyleSheet(
            """
            background-color: rgba(26, 29, 35, 245);
            color: #00FFC6; border-radius: 15px; border: 2px solid #00FFC6;
            font-family: 'Segoe UI'; font-size: 13px; padding: 15px;
        """
        )
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


# =========================================================
# CONTROLADOR CENTRAL (SMART MANAGER)
# =========================================================
class SmartManagerApp(QStackedWidget):
    def __init__(self):
        super().__init__()

        # --- 1. CONFIGURACIÓN BÁSICA ---
        self._articulos_notificados = set()
        self._rfid_signals_connected = False
        self.menu_principal = None
        self.notificacion = None

        self.setWindowTitle("Smart Manager AI - Sistema de Control Logistico")
        self.setMinimumSize(1200, 800)
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        )

        # --- 2. GESTIÓN DE ESTADOS Y HARDWARE ---
        self.gestion_activos = {"estanterias_sesion": {}}

        from src.utils.rfid_worker import RFIDWorker
        from PyQt6.QtCore import QThread

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

    # =========================================================
    # CAPA DE CARGA LOGIN
    # =========================================================
    def setup_spinner(self):
        """Capa de carga que bloquea la interacción durante el login."""
        self.overlay = QWidget(self.ventana_login)
        self.overlay.hide()
        self.overlay.setGeometry(self.ventana_login.rect())
        self.overlay.setStyleSheet("background-color: rgba(14, 17, 23, 200);")

        layout = QVBoxLayout(self.overlay)
        self.loading_label = QLabel("⚡ INICIANDO IA Y SINCRONIZANDO...")
        self.loading_label.setStyleSheet(
            """
            color: #00FFC6; font-family: 'Segoe UI'; font-size: 16px;
            font-weight: bold; letter-spacing: 2px;
        """
        )
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.loading_label)

    # =========================================================
    # RFID
    # =========================================================
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

    # =========================================================
    # EVENTOS DE VENTANA
    # =========================================================
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "overlay") and self.overlay is not None:
            self.overlay.setGeometry(self.ventana_login.rect())

    def closeEvent(self, event):
        """Cierre ordenado para evitar objetos Qt colgando."""
        try:
            if self.hilo_rfid and self.hilo_rfid.isRunning():
                self.hilo_rfid.quit()
                self.hilo_rfid.wait(1500)
        except Exception as e:
            logger.warning(f"No se pudo cerrar el hilo RFID limpiamente: {e}")
        super().closeEvent(event)

    # =========================================================
    # LOGIN
    # =========================================================
    def iniciar_proceso_login(self):
        """Activa el spinner y valida tras un delay."""
        self.overlay.setGeometry(self.ventana_login.rect())
        self.overlay.show()
        self.overlay.raise_()
        self.configurar_monitorizacion_rfid()
        QApplication.processEvents()
        QTimer.singleShot(800, self.ejecutar_login)

    def ejecutar_login(self):
        """Procesa las credenciales y gestiona el cambio de pantalla."""
        perfil = self.ventana_login.combo_perfil.currentText()
        password = self.ventana_login.txt_password.text()
        user_data = validar_login(perfil, password)

        if user_data:
            sesion_global.iniciar_sesion(user_data)
            self.abrir_menu_principal()
            self.ventana_login.txt_password.clear()
            self.overlay.hide()
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

    # =========================================================
    # IA / PREDICCIÓN
    # =========================================================
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
                    f"Smart Manager AI: Stock critico detectado en: "
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

    # =========================================================
    # NAVEGACIÓN PRINCIPAL
    # =========================================================
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
            self.menu_principal.setAttribute(
                Qt.WidgetAttribute.WA_DeleteOnClose, True
            )
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
            self.setCurrentIndex(0)

            if hasattr(self.ventana_login, "txt_password"):
                self.ventana_login.txt_password.clear()
                self.ventana_login.combo_perfil.setCurrentIndex(0)
                self.ventana_login.txt_password.setFocus()

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
    iniciar_backend()
    init_db()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    aplicar_estilo_app(app)
    app.setQuitOnLastWindowClosed(False)

    global manager
    manager = SmartManagerApp()
    manager.showMaximized()

    app.aboutToQuit.connect(
        lambda: logger.info("Sistema Smart Manager AI finalizado. Terminal liberada.")
    )

    exit_code = app.exec()
    logger.info(f"Proceso finalizado con código: {exit_code}")
    sys.exit(exit_code)
