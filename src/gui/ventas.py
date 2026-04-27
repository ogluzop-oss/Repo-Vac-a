# src/gui/ventas.py — PARTE 1/4

import os
import io
import json
import threading
import webbrowser
import sqlite3
import logging
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QGraphicsDropShadowEffect,
    QApplication,
    QInputDialog,
    QDialog,
    QHeaderView,
    QDateEdit,
    QComboBox,
    QMainWindow,
)
from PyQt6.QtGui import QFont, QColor, QDesktopServices
from PyQt6.QtCore import Qt, QTimer, QUrl
from reportlab.pdfgen import canvas
from prophet import Prophet
from openpyxl import load_workbook, Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from collections import defaultdict
import io as _io
import subprocess

# Optional: watchdog for efficient file system events.
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    WATCHDOG_AVAILABLE = True
except Exception:
    WATCHDOG_AVAILABLE = False

# Google Drive / OAuth libs (optional)
try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
    from googleapiclient.errors import HttpError

    GOOGLE_API_AVAILABLE = True
except Exception:
    GOOGLE_API_AVAILABLE = False

# obtener_conexion: función del proyecto que devuelve conexión sqlite3
from src.db.conexion import obtener_conexion

import os

# -----------------------------
# Paths and project root
# -----------------------------

THIS_FILE = os.path.abspath(__file__)
SRC_DIR = os.path.dirname(os.path.dirname(THIS_FILE))
PROJECT_ROOT = os.path.normpath(os.path.join(SRC_DIR, ".."))

# Bases de datos
DB_DEFAULT_PATH = os.path.join(SRC_DIR, "database", "stock.db")

# Carpeta documentos (dentro del proyecto)
DOCUMENTS_DIR = os.path.join(PROJECT_ROOT, "documentos")

# Subcarpetas dentro de documentos
PDF_OUTPUT_DIR = os.path.join(DOCUMENTS_DIR, "facturacion")
RESUMENES_DIR = os.path.join(DOCUMENTS_DIR, "resúmenes de ventas")

# Carpeta de logs
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")

# ⚠️ Solo crear las carpetas base necesarias al iniciar el programa
# (nada más: no se crean subcarpetas hasta que se necesiten)
os.makedirs(DOCUMENTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# -----------------------------
# Logging
# -----------------------------
LOG_FILE = os.path.join(LOGS_DIR, "ventas.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# -----------------------------
# Configuración / Rutas (editable en ~/.360stock/config.json)
# -----------------------------
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]
CLIENT_SECRETS_FILE = os.path.join(
    os.path.dirname(__file__), "client_secrets.json"
)  # Opcional

HOME = os.path.expanduser("~")
TOKEN_DIR = os.path.join(HOME, "src.database.stock")
os.makedirs(TOKEN_DIR, exist_ok=True)
TOKEN_PATH = os.path.join(TOKEN_DIR, "token.json")
CONFIG_PATH = os.path.join(TOKEN_DIR, "config.json")

# Si ya tienes la URL del Excel de predicción en Drive, pégala aquí:
# (puedes sustituirla por la real; si está vacía, se subirá/creará el archivo en Drive)
DRIVE_PREDICTION_URL = (
    "https://drive.google.com/drive/folders/18WhYrCrpwGZdi9BHpC0w_9ddJN4KWb5W"
)

DEFAULT_CONFIG = {
    "empresa": "MiEmpresa",
    "tienda": "Tienda01",
    "responsables": [],
    "carpeta_formato": "ventas-{AÑO}-{EMPRESA}-{TIENDA}",
    "archivo_formato": "ventas-{AÑO}.xlsx",
    "abrir_en_navegador": True,
    "watch_paths": {
        "Promociones": r"\\SERVIDOR\Central\Promociones",
        "Visuales_Tienda": r"\\SERVIDOR\Central\Visuales_Tienda",
        "Catalogos": r"\\SERVIDOR\Central\Catalogos",
        "Articulos_Nuevos": r"\\SERVIDOR\Central\Articulos_Nuevos",
        "Rankings_Tiendas": r"\\SERVIDOR\Central\Rankings_Tiendas",
        "Cambios_Precios": r"\\SERVIDOR\Central\Cambios_Precios",
    },
    "last_prediccion_run": None,
}

MONTH_NAMES_ES = [
    "",
    "ENERO",
    "FEBRERO",
    "MARZO",
    "ABRIL",
    "MAYO",
    "JUNIO",
    "JULIO",
    "AGOSTO",
    "SEPTIEMBRE",
    "OCTUBRE",
    "NOVIEMBRE",
    "DICIEMBRE",
]


# -----------------------------
# Helpers: config, google drive helpers
# -----------------------------
def load_config():
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # rellenar con faltantes del default
        for k, v in DEFAULT_CONFIG.items():
            if k not in cfg:
                cfg[k] = v
        return cfg
    except Exception:
        logging.exception("load_config fallo")
        return DEFAULT_CONFIG.copy()


def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        logging.exception("No se pudo guardar config")


def save_token(creds):
    try:
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    except Exception:
        logging.exception("No se pudo guardar token")


def get_credentials(parent_widget=None):
    if not GOOGLE_API_AVAILABLE:
        raise RuntimeError("Google API libraries no están disponibles.")
    creds = None
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception:
            creds = None
    if (
        creds
        and getattr(creds, "expired", False)
        and getattr(creds, "refresh_token", None)
    ):
        try:
            creds.refresh(Request())
            save_token(creds)
            return creds
        except Exception:
            creds = None
    if not creds or not getattr(creds, "valid", False):
        if not os.path.exists(CLIENT_SECRETS_FILE):
            mostrar_alerta_automatica(
                parent_widget,
                "No se encontró 'client_secrets.json' junto a ventas.py.\n"
                "Coloca el archivo descargado desde Google Cloud en la misma carpeta",
                "error",
            )
            raise FileNotFoundError("client_secrets.json no encontrado")
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)
        save_token(creds)
    return creds


def ensure_drive_folder(service, folder_name):
    safe = folder_name.replace("'", "\\'")
    query = f"name = '{safe}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    try:
        resp = (
            service.files()
            .list(q=query, spaces="drive", fields="files(id, name)")
            .execute()
        )
        files = resp.get("files", [])
        if files:
            return files[0]["id"], False
        metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        created = service.files().create(body=metadata, fields="id").execute()
        return created.get("id"), True
    except HttpError:
        logging.exception("Error ensure_drive_folder")
        raise


def find_file_in_folder(service, folder_id, file_name):
    safe = file_name.replace("'", "\\'")
    q = f"name = '{safe}' and '{folder_id}' in parents and trashed = false"
    resp = service.files().list(q=q, spaces="drive", fields="files(id, name)").execute()
    files = resp.get("files", [])
    return files[0]["id"] if files else None


def download_drive_file_bytes(service, file_id):
    fh = _io.BytesIO()
    request = service.files().get_media(fileId=file_id)
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return fh.read()


def upload_drive_bytes(
    service,
    folder_id,
    file_name,
    file_bytes,
    mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    existing_file_id=None,
):
    fh = _io.BytesIO(file_bytes)
    media = MediaIoBaseUpload(fh, mimetype=mime_type, resumable=True)
    if existing_file_id:
        updated = (
            service.files().update(fileId=existing_file_id, media_body=media).execute()
        )
        return updated.get("id")
    else:
        metadata = {"name": file_name, "parents": [folder_id]}
        created = (
            service.files()
            .create(body=metadata, media_body=media, fields="id")
            .execute()
        )
        return created.get("id")


# -----------------------------
# UI helper: mensajes informativos no bloqueantes
# -----------------------------
from PyQt6.QtWidgets import QMessageBox, QWidget


def mostrar_alerta_automatica(parent_widget, mensaje, tipo="info"):
    """
    Muestra un cuadro de mensaje automático (información, advertencia o error).
    parent_widget puede ser None o un QWidget válido. Si recibe un valor no válido,
    se usa None por defecto.
    """
    try:
        # Validar tipo de parent
        if not isinstance(parent_widget, QWidget):
            parent = None
        else:
            parent = parent_widget

        msg = QMessageBox(parent)

        if tipo == "error":
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("Error")
        elif tipo == "warning":
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Advertencia")
        else:
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("Información")

        msg.setText(mensaje)
        msg.exec()

    except Exception as e:
        # Si incluso esto falla, imprime en consola (para debugging)
        print(f"[mostrar_alerta_automatica] Error al mostrar mensaje: {e}")
        print(f"Mensaje original: {mensaje}")


def ensure_db_schema():
    """
    Asegura que existan las tablas y columnas necesarias usando el context manager.
    """
    try:
        # IMPORTANTE: Usamos 'with' para extraer la conexión del generador
        with obtener_conexion() as conn:
            cur = conn.cursor()

            # Crear tablas si no existen
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ventas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo_ticket TEXT UNIQUE,
                    fecha TEXT NOT NULL,
                    empleado TEXT,
                    numero_caja INTEGER,
                    total_efectivo REAL DEFAULT 0,
                    total_tarjeta REAL DEFAULT 0,
                    total REAL DEFAULT 0,
                    forma_pago TEXT,
                    empresa TEXT,
                    tienda TEXT
                )
            """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS venta_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    venta_id INTEGER NOT NULL,
                    codigo_articulo TEXT,
                    descripcion TEXT,
                    cantidad REAL,
                    precio_unitario REAL,
                    total_item REAL,
                    seccion_tienda TEXT,
                    FOREIGN KEY (venta_id) REFERENCES ventas(id)
                )
            """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS documentos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    carpeta TEXT NOT NULL,
                    nombre_archivo TEXT NOT NULL,
                    ruta_archivo TEXT NOT NULL,
                    tipo_archivo TEXT,
                    fecha_recepcion TEXT DEFAULT (datetime('now')),
                    abierto INTEGER DEFAULT 0
                )
            """
            )

            # Verificación de columnas (PRAGMA)
            cur.execute("PRAGMA table_info(ventas)")
            cols = [r[1] for r in cur.fetchall()]
            required_columns = {
                "codigo_ticket": "TEXT UNIQUE",
                "fecha": "TEXT NOT NULL",
                "empleado": "TEXT",
                "numero_caja": "INTEGER",
                "total_efectivo": "REAL DEFAULT 0",
                "total_tarjeta": "REAL DEFAULT 0",
                "total": "REAL DEFAULT 0",
                "forma_pago": "TEXT",
                "empresa": "TEXT",
                "tienda": "TEXT",
            }

            for col_name, col_def in required_columns.items():
                if col_name not in cols:
                    try:
                        cur.execute(
                            f"ALTER TABLE ventas ADD COLUMN {col_name} {col_def}"
                        )
                        logging.info("Añadida columna a ventas: %s", col_name)
                    except Exception:
                        logging.exception("No se pudo añadir columna %s", col_name)

            conn.commit()
            # No hace falta conn.close() manual, el 'with' lo gestiona al terminar el bloque

    except Exception as e:
        logging.exception("Error al asegurar esquema DB: %s", e)
        raise


# -----------------------------
# Floating notification (clicable, auto-close)
# -----------------------------
class FloatingNotification(QMessageBox):
    def __init__(self, title, text, file_path=None, timeout_ms=5000, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.file_path = file_path
        self.setText(text)
        self.setStandardButtons(QMessageBox.StandardButton.Ok)
        self.setWindowFlag(Qt.WindowType.Tool)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setIcon(QMessageBox.Icon.Information)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.close)
        self.timer.start(timeout_ms)
        self.buttonClicked.connect(self._on_click)

    def _on_click(self, _):
        if self.file_path:
            try:
                open_file_with_default_app(self.file_path)
            except Exception:
                try:
                    folder = os.path.dirname(self.file_path)
                    open_file_with_default_app(folder)
                except Exception:
                    pass
        self.close()


def open_file_with_default_app(path):
    try:
        if os.name == "nt":
            os.startfile(path)
        else:
            # linux / mac
            # try xdg-open, fallback to open (mac)
            try:
                if subprocess.call(["xdg-open", path]) != 0:
                    subprocess.call(["open", path])
            except Exception:
                # final fallback: open in browser
                webbrowser.open(path)
    except Exception:
        try:
            webbrowser.open(path)
        except Exception:
            logging.exception("No se pudo abrir archivo: %s", path)


# -----------------------------
# Watcher (polling, simple threaded)
# - No Qt signals here: callback(carpeta_name, filename, fullpath, parent_window_opt)
# - Inicializa 'seen' con ficheros presentes para evitar notificar al inicio
# -----------------------------
class FolderWatcher:
    def __init__(
        self,
        carpeta_path: str,
        carpeta_name: str,
        callback=None,
        poll_interval=3000,
        use_watchdog=False,
    ):
        self.carpeta_path = carpeta_path
        self.carpeta_name = carpeta_name
        self.callback = callback
        self.poll_interval = max(1, poll_interval) / 1000.0
        self.use_watchdog = use_watchdog and WATCHDOG_AVAILABLE
        self._seen = set()
        self._running = False
        self._thread = None
        # Inicializar seen con contenido existente para no notificar archivos antiguos
        try:
            p = Path(self.carpeta_path)
            if p.exists() and p.is_dir():
                self._seen = set([f.name for f in p.iterdir() if f.is_file()])
            else:
                self._seen = set()
        except Exception:
            self._seen = set()

    def _poll_loop(self):
        import time

        self._running = True
        while self._running:
            try:
                p = Path(self.carpeta_path)
                if p.exists() and p.is_dir():
                    current = set([f.name for f in p.iterdir() if f.is_file()])
                    new = current - self._seen
                    for filename in sorted(new):
                        full = str(p / filename)
                        try:
                            if self.callback:
                                # callback expects (carpeta, filename, fullpath, parent_window_opt)
                                self.callback(self.carpeta_name, filename, full)
                        except Exception:
                            logging.exception("Callback watcher fallo")
                    self._seen = current
            except Exception:
                logging.exception("Watcher poll error")
            time.sleep(self.poll_interval)

    def start(self):
        if self.use_watchdog:
            # prefer watchdog if available - omitted complexity for now
            pass
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            try:
                self._thread.join(timeout=0.5)
            except Exception:
                pass


# -----------------------------
# Registrar archivo en DB y notificar
# -----------------------------
def register_document_in_db(carpeta, filename, fullpath):
    try:
        conn = obtener_conexion()
        cur = conn.cursor()
        tipo = Path(filename).suffix.lower().replace(".", "")
        cur.execute(
            """
            INSERT INTO documentos (carpeta, nombre_archivo, ruta_archivo, tipo_archivo)
            VALUES (?, ?, ?, ?)
        """,
            (carpeta, filename, fullpath, tipo),
        )
        conn.commit()
        conn.close()
        logging.info("Documento registrado: %s / %s", carpeta, filename)
    except Exception:
        logging.exception("No se pudo registrar documento en DB")


# -----------------------------
# Detect expected/real columns in Excel (robust)
# -----------------------------
def detect_expected_real_columns(ws):
    """
    Lee las primeras filas buscando encabezados internacionales que indiquen
    columna de 'esperadas' y 'reales'. Devuelve (expected_idx, real_idx) (1-based).
    Fallbacks sensibles si no se detectan.
    """
    for r in range(1, min(ws.max_row, 6) + 1):
        row_vals = [
            (
                str(ws.cell(row=r, column=c).value).strip()
                if ws.cell(row=r, column=c).value is not None
                else ""
            )
            for c in range(1, ws.max_column + 1)
        ]
        expected_idx = None
        real_idx = None
        for idx, val in enumerate(row_vals, start=1):
            v = val.lower()
            if any(
                k in v
                for k in [
                    "esperad",
                    "expected",
                    "previsto",
                    "forecast",
                    "pronóstic",
                    "predicción",
                    "predic",
                ]
            ):
                expected_idx = idx
            if any(
                k in v
                for k in [
                    "real",
                    "actual",
                    "facturado",
                    "realizado",
                    "reales",
                    "ventas reales",
                ]
            ):
                real_idx = idx
        if expected_idx or real_idx:
            return expected_idx, real_idx
    if ws.max_column >= 3:
        return 2, 3
    elif ws.max_column >= 2:
        return 2, None
    else:
        return None, None


from PyQt6.QtCore import Qt, QDate, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QDateEdit,
    QTableWidget,
    QHeaderView,
    QTableWidgetItem,
    QMessageBox,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtGui import QColor, QFont
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
import sqlite3, os, logging, subprocess
from datetime import datetime
from src.db.conexion import obtener_conexion

# Configuración global
DOCUMENTS_DIR = os.path.expanduser("documentos")
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = {"empresa": "Mi Empresa", "tienda": "Tienda 1"}


class HistorialFacturacionDiaria(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📄 Historial de Facturación Diaria")
        self.setMinimumSize(950, 600)
        self.setStyleSheet(
            """
            QDialog { background-color: #121212; color: #E0E0E0; font-family: 'Segoe UI', Arial; font-size: 11pt; }
            QLabel { color: #E0E0E0; }
            QLineEdit, QDateEdit, QComboBox { background-color: #1E1E1E; color: #E0E0E0; border: 1px solid #333; border-radius: 6px; padding: 4px; }
            QPushButton { border-radius: 6px; padding: 8px 14px; font-weight: bold; }
            QPushButton#btnFiltrar { background-color: #00F0C8; color: black; }
            QPushButton#btnFiltrar:hover { background-color: #1DE9B6; }
            QPushButton#btnExportar { background-color: #00F0C8; color: black; font-weight: bold; }
            QPushButton#btnExportar:hover { background-color: #1DE9B6; }
            QPushButton#btnVolver { background-color: #E53935; color: white; }
            QPushButton#btnVolver:hover { background-color: #D32F2F; }
            QTableWidget { background-color: #1E1E1E; color: #E0E0E0; gridline-color: #333; selection-background-color: #00F0C8; selection-color: black; border: 1px solid #333; border-radius: 6px; }
            QHeaderView::section { background-color: #2C2C2C; color: #E0E0E0; padding: 6px; border: none; font-weight: bold; }
        """
        )

        layout = QVBoxLayout(self)

        # ------------------ Filtros superiores ------------------
        filtros_layout = QHBoxLayout()
        filtros_layout.addWidget(QLabel("Fecha"))
        self.fecha_filtro = QDateEdit(QDate.currentDate())
        self.fecha_filtro.setCalendarPopup(True)
        filtros_layout.addWidget(self.fecha_filtro)

        filtros_layout.addWidget(QLabel("Responsable"))
        self.input_responsable = QLineEdit()
        filtros_layout.addWidget(self.input_responsable)

        self.btn_filtrar = QPushButton("🔍 Filtrar")
        self.estilo_boton(self.btn_filtrar)
        self.btn_filtrar.clicked.connect(self.filtrar)
        filtros_layout.addWidget(self.btn_filtrar)

        layout.addLayout(filtros_layout)

        # ------------------ Tabla principal ------------------
        self.tabla = QTableWidget()
        self.tabla.setColumnCount(10)
        self.tabla.setHorizontalHeaderLabels(
            [
                "Fecha",
                "Empresa",
                "Tienda",
                "Responsable",
                "Efectivo (€)",
                "Tarjeta (€)",
                "Total (€)",
                "Ruta PDF",
                "Abrir PDF",
                "Eliminar",
            ]
        )
        self.tabla.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        # 🔥 Ajuste correcto de tamaño para los botones
        self.tabla.setColumnWidth(8, 200)  # Abrir PDF
        self.tabla.setColumnWidth(9, 200)  # Eliminar

        layout.addWidget(self.tabla)

        # ------------------ Botones inferiores ------------------
        botones_layout = QHBoxLayout()

        self.btn_exportar = QPushButton("📘 Exportar facturación diaria")
        self.estilo_boton(self.btn_exportar)

        # 🔥 Integración del mensaje dentro del click
        self.btn_exportar.clicked.connect(lambda: self._accion_exportar_facturacion())

        botones_layout.addWidget(self.btn_exportar)
        botones_layout.addStretch()

        self.btn_volver = QPushButton("Volver atrás")
        self.estilo_boton(self.btn_volver, rojo=True)
        self.btn_volver.clicked.connect(self.close)
        botones_layout.addWidget(self.btn_volver)

        layout.addLayout(botones_layout)

        # Cargar registros iniciales
        self.cargar_historial()

        # ------------------ Timer de sincronización con TPV ------------------
        self.timer = QTimer()
        self.timer.timeout.connect(self.cargar_historial)
        self.timer.start(5000)  # Actualiza cada 5 segundos

    # ------------------ EXPORTAR PDF SINCRONIZADO ------------------
    def exportar_facturacion_actual(
        self, empresa=None, tienda=None, carpeta_dest=None, responsable=""
    ):
        try:
            conn = obtener_conexion()
            cur = conn.cursor()

            # Crear tabla log si no existe
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS facturacion_diaria_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha TEXT,
                    empresa TEXT,
                    tienda TEXT,
                    responsable TEXT,
                    total_efectivo REAL,
                    total_tarjeta REAL,
                    total REAL,
                    ruta_pdf TEXT
                )
            """
            )

            # Tabla de registro de IVA diario
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS iva (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    venta_id INTEGER,
                    porcentaje REAL NOT NULL,
                    importe REAL NOT NULL,
                    FOREIGN KEY (venta_id) REFERENCES ventas(id) ON DELETE CASCADE
                )
            """
            )

            # Tabla de devoluciones
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS devoluciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    venta_id INTEGER,
                    motivo TEXT,
                    importe REAL NOT NULL,
                    fecha TEXT,
                    FOREIGN KEY (venta_id) REFERENCES ventas(id) ON DELETE CASCADE
                )
            """
            )

            # Tabla de descuentos
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS descuentos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    venta_id INTEGER,
                    tipo TEXT,
                    importe REAL NOT NULL,
                    fecha TEXT,
                    FOREIGN KEY (venta_id) REFERENCES ventas(id) ON DELETE CASCADE
                )
            """
            )

            # Totales del día en tiempo real
            cur.execute(
                """
                SELECT
                    COALESCE(SUM(total_efectivo),0),
                    COALESCE(SUM(total_tarjeta),0),
                    COALESCE(SUM(total),0),
                    COALESCE(SUM(iva),0),
                    COALESCE(SUM(devoluciones),0),
                    COALESCE(SUM(descuentos),0)
                FROM ventas
                WHERE date(fecha) = date('now')
                AND (? IS NULL OR empresa = ?)
                AND (? IS NULL OR tienda = ?)
            """,
                (empresa, empresa, tienda, tienda),
            )
            total_efectivo, total_tarjeta, total, iva, devoluciones, descuentos = (
                cur.fetchone() or (0, 0, 0, 0, 0, 0)
            )

            cur.execute(
                """
                SELECT GROUP_CONCAT(nota, '; ') 
                FROM ventas
                WHERE date(fecha) = date('now') AND nota IS NOT NULL AND nota != ''
            """
            )
            notas = cur.fetchone()[0] or "Sin incidencias ni promociones."
            conn.close()

            # Carpeta y archivo PDF
            if carpeta_dest is None:
                carpeta_dest = os.path.join(DOCUMENTS_DIR, "facturacion")
            os.makedirs(carpeta_dest, exist_ok=True)
            fecha_actual = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            nombre_pdf = f"facturacion_diaria_{fecha_actual}.pdf"
            ruta_pdf = os.path.join(carpeta_dest, nombre_pdf)

            # ------------------ Crear PDF ------------------
            c = canvas.Canvas(ruta_pdf, pagesize=A4)
            w, h = A4
            margin = 50
            y = h - margin

            logo_path = os.path.join(
                PROJECT_ROOT, "assets", "logo_360 Smart Manager.png"
            )
            if os.path.exists(logo_path):
                logo = ImageReader(logo_path)
                c.drawImage(logo, w - 150, h - 100, width=50, height=50, mask="auto")

            # Encabezado
            c.setFont("Helvetica-Bold", 18)
            c.setFillColor(colors.darkblue)
            c.drawCentredString(
                w / 2,
                y,
                f"{empresa or DEFAULT_CONFIG['empresa']} — {tienda or DEFAULT_CONFIG['tienda']}",
            )
            y -= 30
            c.setFont("Helvetica", 14)
            c.setFillColor(colors.black)
            c.drawCentredString(w / 2, y, "FACTURACIÓN DIARIA")
            y -= 40

            # Datos generales
            c.setFont("Helvetica", 11)
            c.setFillColor(colors.black)
            c.drawString(
                margin,
                y,
                f"Fecha de emisión: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            )
            y -= 20
            if responsable:
                c.drawString(margin, y, f"Responsable de cierre: {responsable}")
                y -= 20
            c.drawString(margin, y, f"Total efectivo: {total_efectivo:.2f} €")
            y -= 16
            c.drawString(margin, y, f"Total tarjeta: {total_tarjeta:.2f} €")
            y -= 16
            c.drawString(margin, y, f"Total facturado: {total:.2f} €")
            y -= 16
            c.drawString(margin, y, f"IVA: {iva:.2f} €")
            y -= 16
            c.drawString(margin, y, f"Devoluciones: {devoluciones:.2f} €")
            y -= 16
            c.drawString(margin, y, f"Descuentos: {descuentos:.2f} €")
            y -= 20
            c.drawString(margin, y, f"Notas: {notas}")
            y -= 40

            # Línea divisoria
            c.setStrokeColor(colors.darkgrey)
            c.line(margin, y, w - margin, y)
            y -= 40

            # Espacio para firma
            c.setStrokeColor(colors.black)
            c.line(margin, 165, margin + 170, 165)
            c.setFont("Helvetica-Oblique", 10)
            c.drawString(margin, 170, "Firma del responsable")

            # Pie
            c.setFont("Helvetica-Oblique", 9)
            c.setFillColor(colors.grey)
            c.drawCentredString(
                w / 2, 60, "Generado automáticamente por 360-STOCK © 2025"
            )
            c.setFillColor(colors.darkgrey)
            c.drawCentredString(w / 2, 47, "Sistema de gestión inteligente de ventas")
            c.save()

            # Guardar en BD
            conn = obtener_conexion()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO facturacion_diaria_log
                (fecha, empresa, tienda, responsable, total_efectivo, total_tarjeta, total, ruta_pdf)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    empresa,
                    tienda,
                    responsable,
                    total_efectivo,
                    total_tarjeta,
                    total,
                    ruta_pdf,
                ),
            )
            conn.commit()
            conn.close()

            logging.info(
                "✅ Facturación diaria registrada y PDF generado: %s", ruta_pdf
            )
            self.cargar_historial()
            return ruta_pdf

        except Exception as e:
            logging.exception("❌ Error al generar facturación diaria")
            QMessageBox.critical(
                self, "Error", f"No se pudo generar facturación diaria.\n{e}"
            )
            return None

    # ------------------ FILTRADO ------------------
    def filtrar(self):
        conn = obtener_conexion()
        cur = conn.cursor()

        query = """
            SELECT fecha, empresa, tienda, responsable, total_efectivo, total_tarjeta, total, ruta_pdf
            FROM facturacion_diaria_log
            WHERE 1=1
        """
        params = []

        if self.fecha_filtro.date():
            fecha = self.fecha_filtro.date().toString("yyyy-MM-dd")
            query += " AND date(fecha) = ?"
            params.append(fecha)

        responsable = self.input_responsable.text().strip()
        if responsable:
            query += " AND responsable LIKE ?"
            params.append(f"%{responsable}%")

        cur.execute(query, params)
        registros = cur.fetchall()
        conn.close()

        self.mostrar_registros(registros)

    # ------------------ CARGAR HISTORIAL ------------------
    def cargar_historial(self):
        conn = obtener_conexion()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT fecha, empresa, tienda, responsable, total_efectivo, total_tarjeta, total, ruta_pdf
            FROM facturacion_diaria_log
            ORDER BY fecha DESC
        """
        )
        registros = cur.fetchall()
        conn.close()
        self.mostrar_registros(registros)

    # ------------------ MOSTRAR EN TABLA ------------------
    def mostrar_registros(self, registros):
        self.tabla.setRowCount(0)
        for row, r in enumerate(registros):
            self.tabla.insertRow(row)
            for col, value in enumerate(r):
                self.tabla.setItem(row, col, QTableWidgetItem(str(value)))

            # Botón abrir PDF
            btn_abrir = QPushButton("Abrir PDF")
            btn_abrir.setFont(QFont("Segoe UI", 10))  # Ajusta tamaño de fuente
            btn_abrir.setStyleSheet(
                """
                QPushButton {
                    background-color: #00FFC6;
                    color: #000000;
                    border-radius: 10px;
                    padding: 6px 12px;
                }
                QPushButton:hover {
                    background-color: #00DDAA;
                }
            """
            )
            btn_abrir.clicked.connect(lambda _, path=r[7]: self.abrir_pdf(path))
            self.tabla.setCellWidget(row, 8, btn_abrir)

            # Botón eliminar
            btn_eliminar = QPushButton(" Eliminar")
            btn_eliminar.setFont(QFont("Segoe UI", 10))  # Ajusta tamaño de fuente
            btn_eliminar.setStyleSheet(
                """
                QPushButton {
                    background-color: #FF4B4B;
                    color: #FFFFFF;
                    border-radius: 10px;
                    padding: 6px 12px;
                }
                QPushButton:hover {
                    background-color: #FF2222;
                }
            """
            )
            btn_eliminar.clicked.connect(
                lambda _, path=r[7]: self.eliminar_registro(path)
            )
            self.tabla.setCellWidget(row, 9, btn_eliminar)

    # ------------------ ABRIR PDF ------------------
    def abrir_pdf(self, ruta):
        if os.path.exists(ruta):
            try:
                if os.name == "nt":
                    os.startfile(ruta)
                else:
                    subprocess.Popen(["xdg-open", ruta])
            except Exception as e:
                QMessageBox.warning(self, "Error", f"No se pudo abrir el PDF:\n{e}")
        else:
            QMessageBox.warning(
                self, "Archivo no encontrado", f"No se encuentra el archivo:\n{ruta}"
            )

    # ------------------ ELIMINAR REGISTRO ------------------
    def eliminar_registro(self, ruta):
        conn = obtener_conexion()
        cur = conn.cursor()
        cur.execute("DELETE FROM facturacion_diaria_log WHERE ruta_pdf = ?", (ruta,))
        conn.commit()
        conn.close()
        if os.path.exists(ruta):
            os.remove(ruta)
        self.cargar_historial()

    # ------------------ ESTILO DE BOTONES ------------------
    def estilo_boton(self, btn, rojo=False):
        if rojo:
            base, hover, text_color, padding = "#FF4B4B", "#FF2222", "#FFFFFF", "12px"
        else:
            base, hover, text_color, padding = "#00FFC6", "#00DDAA", "#0E1117", "20px"

        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {base};
                color: {text_color};
                font-weight: bold;
                border-radius: 15px;
                padding: {padding};
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
        """
        )
        btn.setFont(QFont("Segoe UI", 11))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(base))
        shadow.setOffset(0)
        btn.setGraphicsEffect(shadow)

    def _accion_exportar_facturacion(self):
        try:
            self.exportar_facturacion_actual(responsable=self.input_responsable.text())

            QMessageBox.information(
                self,
                "Exportación correcta",
                "La facturación diaria se ha exportado correctamente.",
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error al exportar",
                f"Ocurrió un error durante la exportación:\n{str(e)}",
            )


# -----------------------------
# Predicción simple (wrapper): entrena Prophet con ventas diarias y devuelve resumen
# -----------------------------
def get_simple_prediction_summary(parent=None, empresa=None, tienda=None):
    """
    Entrena Prophet con el histórico de 'total' de la tabla ventas y devuelve
    un resumen corto (primeras 3 filas) para mostrar en PDFs/plantillas.
    """
    conn = obtener_conexion()
    cur = conn.cursor()
    fecha_inicio = (datetime.now().date() - timedelta(days=365)).isoformat()
    query = """
        SELECT date(fecha) as d, COALESCE(SUM(total),0) as total
        FROM ventas
        WHERE date(fecha) BETWEEN date(?) AND date('now')
    """
    params = [fecha_inicio]
    if empresa:
        query += " AND empresa = ?"
        params.append(empresa)
    if tienda:
        query += " AND tienda = ?"
        params.append(tienda)
    query += " GROUP BY d ORDER BY d"
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    if not rows:
        raise RuntimeError("No hay datos suficientes para entrenar predicción.")
    df = pd.DataFrame(rows, columns=["ds", "y"])
    df["ds"] = pd.to_datetime(df["ds"])
    model = Prophet(daily_seasonality=True)
    model.fit(df)
    future = pd.DataFrame(
        {"ds": [datetime.now().date() + timedelta(days=i) for i in range(7)]}
    )
    forecast = model.predict(future)
    preds = [
        f"{row['ds'].strftime('%Y-%m-%d')}: {round(row['yhat'],2)}€"
        for _, row in forecast.head(3).iterrows()
    ]
    return "; ".join(preds)


# -----------------------------
# Registrar venta recibida desde TPV
# -----------------------------
def register_sale_from_tpv(sale: dict):
    """
    Inserta en tablas ventas y venta_items.
    sale (dict) = {
      "codigo_ticket": "T-...",
      "fecha": "ISO datetime",
      "empleado": "...",
      "numero_caja": 1,
      "items": [{codigo, descripcion, cantidad, precio_unitario, seccion}],
      "total_efectivo": float,
      "total_tarjeta": float,
      "total": float,  # opcional (se calcula si falta)
      "forma_pago": "...",
      "empresa": "...",
      "tienda": "..."
    }
    Devuelve (True, venta_id) o (False, error_str)
    """
    try:
        conn = obtener_conexion()
        cur = conn.cursor()
        codigo_ticket = (
            sale.get("codigo_ticket") or f"T-{int(datetime.now().timestamp())}"
        )
        # Si el TPV envía una fecha → se usa tal cual
        # Si no la envía → se genera con hora automática
        fecha = sale.get("fecha")
        if not fecha:
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            # Si el TPV envía un ISO con "T", lo convertimos al formato correcto
            try:
                fecha = datetime.fromisoformat(fecha).strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass  # Si ya viene en formato correcto, no hacemos nada

        empleado = sale.get("empleado")
        numero_caja = sale.get("numero_caja")
        total_efectivo = float(sale.get("total_efectivo") or 0.0)
        total_tarjeta = float(sale.get("total_tarjeta") or 0.0)
        total = sale.get("total")
        try:
            total = (
                float(total) if total is not None else (total_efectivo + total_tarjeta)
            )
        except Exception:
            total = total_efectivo + total_tarjeta
        forma_pago = sale.get("forma_pago") or (
            "Tarjeta" if total_tarjeta > 0 else "Efectivo"
        )
        empresa = sale.get("empresa")
        tienda = sale.get("tienda")

        # Insert or ignore to avoid duplicates; if exists, we fetch existing id
        cur.execute(
            """
            INSERT OR IGNORE INTO ventas (codigo_ticket, fecha, empleado, numero_caja, total_efectivo, total_tarjeta, total, forma_pago, empresa, tienda)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                codigo_ticket,
                fecha,
                empleado,
                numero_caja,
                total_efectivo,
                total_tarjeta,
                total,
                forma_pago,
                empresa,
                tienda,
            ),
        )
        conn.commit()

        cur.execute("SELECT id FROM ventas WHERE codigo_ticket = ?", (codigo_ticket,))
        row = cur.fetchone()
        if not row:
            conn.close()
            logging.error("No se pudo crear la venta (ticket: %s)", codigo_ticket)
            return False, "No se pudo crear la venta"
        venta_id = row[0]

        items = sale.get("items", [])
        for it in items:
            codigo_art = it.get("codigo")
            descripcion = it.get("descripcion") or ""
            try:
                cantidad = float(it.get("cantidad") or 0)
            except Exception:
                cantidad = 0.0
            try:
                precio_unit = float(it.get("precio_unitario") or 0)
            except Exception:
                precio_unit = 0.0
            total_item = round(cantidad * precio_unit, 2)
            seccion = it.get("seccion") or None
            cur.execute(
                """
                INSERT INTO venta_items (venta_id, codigo_articulo, descripcion, cantidad, precio_unitario, total_item, seccion_tienda)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    venta_id,
                    codigo_art,
                    descripcion,
                    cantidad,
                    precio_unit,
                    total_item,
                    seccion,
                ),
            )

        conn.commit()
        conn.close()
        logging.info(
            "Venta registrada: ticket=%s id=%s total=%.2f",
            codigo_ticket,
            venta_id,
            float(total or 0.0),
        )
        return True, venta_id
    except Exception as e:
        logging.exception("Error register_sale_from_tpv")
        return False, str(e)


# Asegúrate de tener definido el directorio donde se guardan los PDFs
RESUMENES_DIR = os.path.join("documentos", "resúmenes de ventas")
import os
import io
import random
from datetime import date, datetime

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QDateEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QSizePolicy,
    QMessageBox,
    QGraphicsDropShadowEffect,
    QWidget,
    QScrollArea,
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor, QFont

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
)
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

# Funciones externas
from src.db.conexion import obtener_ventas_por_hora  # ya existente en tu proyecto


class VentanaResumenVentas(QDialog):
    """
    Ventana resumen de ventas:
    - Filtros: periodo, empleado, ventas online, horas.
    - Tabla con totales y producto más vendido.
    - Panel de estadísticas generales.
    - Gráfica lineal por horas (día único) o gráfica de barras (rango).
    - Exportación a PDF con la gráfica visible en pantalla.
    - Fallback a datos simulados si no hay ventas reales.
    """

    def __init__(self, parent=None, volver_callback=None):
        super().__init__(parent)
        self.setWindowTitle("📊 Resumen de Ventas - 360 STOCK")
        self.resize(1100, 650)
        self.logo_path = os.path.join(
            os.getcwd(), "assets", "logo_360 Smart Manager.png"
        )
        self.volver_callback = volver_callback

        # Estado actual de la gráfica mostrada: 'none'|'hours'|'sections'
        self.current_chart = "none"

        # Estilo de botones centralizado
        self.button_base_color = "#00FFC6"
        self.button_hover_color = "#00E0AA"
        self.button_text_color = "#0E1111"
        self.button_font = QFont("Segoe UI", 10, QFont.Weight.Bold)

        # Layout principal
        self.layout_principal = QVBoxLayout()
        self.setLayout(self.layout_principal)

        # Figuras y canvas
        self.fig = Figure(figsize=(6, 3))
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self.fig_horas = Figure(figsize=(6, 3))
        self.canvas_horas = FigureCanvas(self.fig_horas)
        self.canvas_horas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # Ocultar canvases al inicio
        self.canvas.hide()
        self.canvas_horas.hide()

        # Estilo general
        self.setStyleSheet(
            """
            QWidget { background-color: #121212; color: white; }
            QLineEdit, QComboBox, QDateEdit {
                background-color: #1E1E1E;
                border: 1px solid #30363d;
                color: white;
                padding:6px;
                border-radius:6px;
            }
            QTableWidget {
                background-color: #121212;
                color: white;
                gridline-color: #30363d;
            }
            QLabel { color: white; }
        """
        )

        # Construir componentes
        self._construir_filtros()
        self._construir_resumen_estadistico()
        self._construir_contenido()

        # Footer
        footer = QLabel("<i>© 2025 360 STOCK | Gestión inteligente de ventas</i>")
        footer.setAlignment(Qt.AlignmentFlag.AlignRight)
        footer.setStyleSheet("color: gray; font-size: 11px; margin-top: 10px;")
        self.layout_principal.addWidget(footer)

    # --------------------------
    # Filtros
    # --------------------------
    def _construir_filtros(self):
        layout = QHBoxLayout()

        # Fechas
        layout.addWidget(QLabel("Desde"))
        self.fecha_from = QDateEdit()
        self.fecha_from.setDate(QDate.currentDate().addDays(-7))
        self.fecha_from.setCalendarPopup(True)
        layout.addWidget(self.fecha_from)

        layout.addWidget(QLabel("Hasta"))
        self.fecha_to = QDateEdit()
        self.fecha_to.setDate(QDate.currentDate())
        self.fecha_to.setCalendarPopup(True)
        layout.addWidget(self.fecha_to)

        # Horas
        horas = [f"{h}:00" for h in range(8, 23)]
        layout.addWidget(QLabel("Hora inicio"))
        self.combo_hora_inicio = QComboBox()
        self.combo_hora_inicio.addItems(horas)
        self.combo_hora_inicio.setCurrentIndex(0)
        layout.addWidget(self.combo_hora_inicio)

        layout.addWidget(QLabel("Hora fin"))
        self.combo_hora_fin = QComboBox()
        self.combo_hora_fin.addItems(horas)
        self.combo_hora_fin.setCurrentIndex(len(horas) - 1)
        layout.addWidget(self.combo_hora_fin)

        # Empleado
        layout.addWidget(QLabel("Empleado"))
        self.combo_empleado = QComboBox()
        self.combo_empleado.addItems(["Todos", "E001", "E002", "E003"])
        layout.addWidget(self.combo_empleado)

        # Ventas Online
        layout.addWidget(QLabel("Ventas Online"))
        self.combo_online = QComboBox()
        self.combo_online.addItems(["Todas", "Sí", "No"])
        layout.addWidget(self.combo_online)

        # Botones
        self.btn_generar = QPushButton("📊 Generar resumen")
        self.estilo_boton(self.btn_generar)
        self.btn_generar.clicked.connect(self.generar_resumen)
        layout.addWidget(self.btn_generar)

        self.btn_exportar = QPushButton("📘 Exportar PDF")
        self.estilo_boton(self.btn_exportar)
        self.btn_exportar.clicked.connect(self._exportar_pdf)
        layout.addWidget(self.btn_exportar)

        self.btn_volver = QPushButton("Volver atrás")
        self.estilo_boton(self.btn_volver, rojo=True)
        self.btn_volver.clicked.connect(self._volver_menu)
        layout.addWidget(self.btn_volver)

        self.layout_principal.addLayout(layout)

    # --------------------------
    # Resumen estadístico
    # --------------------------
    def _construir_resumen_estadistico(self):
        # Contenedor principal de KPIs
        self.widget_stats = QWidget()
        layout_container = QHBoxLayout()
        layout_container.setContentsMargins(0, 0, 0, 2)  # margen inferior reducido
        layout_container.setSpacing(5)  # espacio entre indicadores
        self.widget_stats.setLayout(layout_container)

        self.labels_stats = {}
        stats = [
            "Total Ventas (€)",
            "Beneficio Neto (€)",
            "Unidades Vendidas",
            "Ticket Medio (€)",
        ]
        for s in stats:
            box = QVBoxLayout()
            lbl_title = QLabel(f"<b>{s}</b>")
            lbl_val = QLabel("—")
            lbl_val.setStyleSheet("font-size:18px; font-weight:bold; color:#00FFC6;")
            lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(lbl_title)
            box.addWidget(lbl_val)
            layout_container.addLayout(box)
            self.labels_stats[s] = lbl_val

        # ScrollArea para contener la tabla de KPIs
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.widget_stats)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setMinimumHeight(70)  # ajusta según tamaño deseado de KPIs
        scroll.setMaximumHeight(
            100
        )  # limita altura, si hay más indicadores se activa scroll

        self.layout_principal.addWidget(scroll)

    # --------------------------
    # Contenido principal
    # --------------------------
    def _construir_contenido(self):
        self.tabla = QTableWidget()
        self.tabla.setColumnCount(3)
        self.tabla.setHorizontalHeaderLabels(
            ["Sección", "Total (€)", "Producto más vendido"]
        )
        self.tabla.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.layout_principal.addWidget(self.tabla)

        # Placeholder
        self.placeholder = QLabel("Genera un resumen para ver estadísticas")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet("color: gray; font-size: 14px; padding: 40px;")
        self.layout_principal.addWidget(self.placeholder)

        # Gráfica por horas (líneas)
        self.layout_principal.addWidget(self.canvas_horas)

        # Gráfica principal (secciones)
        self.layout_principal.addWidget(self.canvas)

        # Label con resumen por sección debajo de la gráfica
        self.label_detalle_secciones = QLabel("")
        self.label_detalle_secciones.setWordWrap(True)
        self.label_detalle_secciones.setStyleSheet("color: #00FFC6; font-weight: bold;")
        self.layout_principal.addWidget(self.label_detalle_secciones)

    # --------------------------
    # Generar resumen
    # --------------------------
    def generar_resumen(self):
        try:
            fecha_from_str = self.fecha_from.date().toString("yyyy-MM-dd")
            fecha_to_str = self.fecha_to.date().toString("yyyy-MM-dd")

            empleado = self.combo_empleado.currentText()
            ventas_online = self.combo_online.currentText()
            hora_inicio = int(self.combo_hora_inicio.currentText().split(":")[0])
            hora_fin = int(self.combo_hora_fin.currentText().split(":")[0])

            # Llamada segura a resumen_ventas (si existe)
            if resumen_ventas:
                try:
                    datos = resumen_ventas(
                        fecha_from_str,
                        fecha_to_str,
                        empleado,
                        ventas_online,
                        hora_inicio=hora_inicio,
                        hora_fin=hora_fin,
                    )
                except TypeError:
                    datos = resumen_ventas(
                        fecha_from_str, fecha_to_str, empleado, ventas_online
                    )
            else:
                datos = {}

            totales = datos.get("totales", {}) or {}
            top = datos.get("top", {}) or {}
            if not totales:
                secciones_sim = ["Ropa", "Calzado", "Accesorios", "Suplementos"]
                totales = {s: float(random.randint(300, 2000)) for s in secciones_sim}
                top = {
                    s: {
                        "descripcion": random.choice(["Item A", "Item B", "Item C"]),
                        "total_venta": float(random.randint(50, 500)),
                    }
                    for s in secciones_sim
                }
                datos["total_general"] = sum(totales.values())
                datos["ticket_medio"] = round(
                    (datos["total_general"] / max(1, random.randint(50, 200))), 2
                )
                datos["unidades"] = sum(
                    int(v.get("total_venta", 0)) for v in top.values()
                )

            total_general = float(
                datos.get("total_general", sum(totales.values()) or 0.0) or 0.0
            )
            unidades = int(datos.get("unidades", 0) or 0)
            ticket_medio = float(datos.get("ticket_medio", 0) or 0.0)
            beneficio = total_general * 0.3

            stats = {
                "total_ventas": total_general,
                "beneficio": beneficio,
                "unidades": unidades,
                "ticket_medio": ticket_medio,
            }

            # actualizar UI
            self._actualizar_stats(stats)
            self._actualizar_tabla({"totales": totales, "top": top})

            es_un_dia = fecha_from_str == fecha_to_str
            self.placeholder.hide()

            if es_un_dia:
                fecha_py = self.fecha_from.date().toPyDate()
                self.actualizar_grafica_horas(
                    fecha_py, hora_inicio, hora_fin, totales_por_seccion=totales
                )
                self.canvas_horas.show()
                self.canvas.hide()
                self.current_chart = "hours"
            else:
                self._actualizar_grafica(totales)
                self.canvas.show()
                self.canvas_horas.hide()
                self.current_chart = "sections"

            QMessageBox.information(
                self, "Resumen generado", "Resumen generado correctamente."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error generando resumen: {e}")

    # --------------------------
    # Métodos auxiliares
    # --------------------------
    def _actualizar_tabla(self, data):
        totales = data.get("totales", {})
        top = data.get("top", {})
        self.tabla.setRowCount(len(totales))
        for i, (sec, total) in enumerate(totales.items()):
            self.tabla.setItem(i, 0, QTableWidgetItem(sec))
            self.tabla.setItem(i, 1, QTableWidgetItem(f"{total:.2f} €"))
            self.tabla.setItem(
                i, 2, QTableWidgetItem(top.get(sec, {}).get("descripcion", "—"))
            )

    def _actualizar_stats(self, stats):
        total = float(stats.get("total_ventas", 0) or 0)
        beneficio = float(stats.get("beneficio", 0) or 0)
        unidades = int(stats.get("unidades", 0) or 0)
        ticket = float(stats.get("ticket_medio", 0) or 0)

        self.labels_stats["Total Ventas (€)"].setText(f"{total:.2f}")
        self.labels_stats["Beneficio Neto (€)"].setText(f"{beneficio:.2f}")
        self.labels_stats["Unidades Vendidas"].setText(str(unidades))
        self.labels_stats["Ticket Medio (€)"].setText(f"{ticket:.2f}")

    def actualizar_grafica_horas(
        self, fecha: date, hora_inicio=8, hora_fin=22, totales_por_seccion=None
    ):
        from matplotlib.animation import FuncAnimation

        if hasattr(self, "layout_stats_container"):
            for i in range(self.layout_stats_container.count()):
                item = self.layout_stats_container.itemAt(i)
                if item.widget():
                    item.widget().show()

        try:
            horas_dict = obtener_ventas_por_hora(fecha.strftime("%Y-%m-%d"))
            datos = [
                (h, int(horas_dict.get(h, 0))) for h in range(hora_inicio, hora_fin + 1)
            ]
            if sum(v for (_, v) in datos) == 0:
                raise ValueError
        except:
            datos = [
                (h, random.randint(0, 200)) for h in range(hora_inicio, hora_fin + 1)
            ]

        horas_labels = [f"{h}h" for (h, _) in datos]
        ventas = [v for (_, v) in datos]
        x = list(range(len(ventas)))

        self.fig_horas.clf()
        ax = self.fig_horas.add_subplot(111)

        (line,) = ax.plot(
            x, ventas, marker="o", linewidth=2, color="#00FFC6", alpha=0.0
        )

        original_y = ventas.copy()
        start_offset = -(max(ventas) - min(ventas)) * 1.2

        texts = []
        text_y_final = []
        for i, v in enumerate(ventas):
            ty = v + max(1, max(ventas) * 0.01)
            t = ax.text(
                i, ty, str(v), ha="center", color="white", fontsize=9, alpha=0.0
            )
            texts.append(t)
            text_y_final.append(ty)

        ax.set_xticks(x)
        ax.set_xticklabels(horas_labels, color="white", rotation=45, ha="right")

        ax.set_title(
            f"Ventas por horas - {fecha.strftime('%Y-%m-%d')}",
            color="white",
            fontsize=12,
            fontweight="bold",
            pad=20,
        )
        ax.set_xlabel("Hora", color="white")
        ax.set_ylabel("Unidades / Ventas", color="white")
        ax.grid(True, linestyle="--", alpha=0.3)

        ax.tick_params(axis="y", colors="white")

        ax.set_facecolor("#121212")
        self.fig_horas.patch.set_facecolor("#121212")

        # 🔥 Aumentamos margen inferior para evitar solapamientos
        self.fig_horas.subplots_adjust(top=0.85, bottom=0.22)

        total_frames = 60

        def update(frame):
            t = frame / (total_frames - 1)
            ease = 1 - (1 - t) ** 3

            alpha = ease
            offset = start_offset * (1 - ease)

            line.set_alpha(alpha)
            line.set_ydata([oy + offset for oy in original_y])

            for i, text in enumerate(texts):
                text.set_alpha(alpha)
                text.set_y(text_y_final[i] + offset)

            return [line] + texts

        self.anim_horas = FuncAnimation(
            self.fig_horas,
            update,
            frames=total_frames,
            interval=16,
            blit=True,
            repeat=False,
        )

        self.canvas_horas.draw_idle()

    def _actualizar_grafica(self, totales):
        from matplotlib.animation import FuncAnimation

        self.widget_stats.setVisible(True)

        self.fig.clf()
        ax = self.fig.add_subplot(111)

        secciones = list(totales.keys())
        valores = list(totales.values())
        colores_varios = [
            "#00FFC6",
            "#00DDAA",
            "#FF8A65",
            "#42A5F5",
            "#FFD54F",
            "#BA68C8",
        ]

        x = list(range(len(secciones)))

        bars = ax.bar(x, valores, color=colores_varios[: len(secciones)], alpha=0.0)

        total_general = max(sum(valores), 1)
        texts = []

        start_offset = -(max(valores) - min(valores)) * 1.2

        text_y_final = []
        for i, val in enumerate(valores):
            pct = (val / total_general) * 100
            ty = val + max(valores) * 0.02  # Separación mínima dinámica

            text = ax.text(
                x[i],
                ty,
                f"{val:.2f} € ({pct:.1f}%)",
                ha="center",
                va="bottom",
                color="white",
                fontsize=9,
                alpha=0.0,
            )
            texts.append(text)
            text_y_final.append(ty)

        ax.set_xticks(x)
        ax.set_xticklabels(secciones, color="white")
        ax.set_ylabel("€ facturados", color="white")
        ax.set_title("Resumen de ventas por sección", color="white", pad=25)

        ax.tick_params(axis="y", colors="white")
        ax.set_facecolor("#121212")
        self.fig.patch.set_facecolor("#121212")

        # 🔥 Ajustar margen superior dinámicamente según la barra más alta
        top_margin = 0.90 - (max(valores) / (max(valores) * 3.5))
        top_margin = max(0.80, min(0.92, top_margin))

        self.fig.subplots_adjust(top=top_margin, bottom=0.15)

        total_frames = 60

        def update(frame):
            t = frame / (total_frames - 1)
            ease = 1 - (1 - t) ** 3

            alpha = ease
            offset = start_offset * (1 - ease)

            for i, b in enumerate(bars):
                b.set_alpha(alpha)
                b.set_y(offset)  # Comienza desde fuera y sube

            for i, text in enumerate(texts):
                text.set_alpha(alpha)
                text.set_y(text_y_final[i] + offset)

            return list(bars) + texts

        self.anim_ventas = FuncAnimation(
            self.fig, update, frames=total_frames, interval=16, blit=True, repeat=False
        )

        self.canvas.draw_idle()

    def estilo_boton(self, btn, rojo=False):
        if rojo:
            base, hover, text_color, padding = "#FF4B4B", "#FF2222", "#FFFFFF", "12px"
        else:
            base, hover, text_color, padding = "#00FFC6", "#00DDAA", "#0E1117", "20px"
        btn.setStyleSheet(
            f"""
            QPushButton {{ background-color: {base}; color: {text_color}; font-weight: bold; border-radius: 15px; padding: {padding}; }}
            QPushButton:hover {{ background-color: {hover}; }}
        """
        )
        btn.setFont(QFont("Segoe UI", 11))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(base))
        shadow.setOffset(0)
        btn.setGraphicsEffect(shadow)

    def _exportar_pdf(self):
        try:
            os.makedirs(RESUMENES_DIR, exist_ok=True)
            fecha_actual = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            path = os.path.join(RESUMENES_DIR, f"resumen_ventas_{fecha_actual}.pdf")
            doc = SimpleDocTemplate(path, pagesize=A4)
            elementos = []

            estilos_base = getSampleStyleSheet()
            estilo_encabezado = ParagraphStyle(
                name="Encabezado",
                parent=estilos_base["Normal"],
                fontSize=16,
                leading=18,
                spaceAfter=10,
            )
            estilo_subtitulo = ParagraphStyle(
                name="Subtitulo",
                parent=estilos_base["Normal"],
                fontSize=12,
                leading=14,
                spaceAfter=6,
            )
            estilo_normal = ParagraphStyle(
                name="NormalCuerpo",
                parent=estilos_base["Normal"],
                fontSize=10,
                leading=12,
                spaceAfter=4,
            )

            # Cabecera
            periodo_from = self.fecha_from.date().toString("yyyy-MM-dd")
            periodo_to = self.fecha_to.date().toString("yyyy-MM-dd")
            empleado = self.combo_empleado.currentText()
            ventas_online = self.combo_online.currentText()
            codigo_informe = f"RSV-{datetime.now().strftime('%Y%m%d%H%M%S')}"

            encabezado = f"""
            <b>360 STOCK / Tienda XYZ S.L.</b><br/>
            Periodo: {periodo_from} → {periodo_to}<br/>
            Empleado: {empleado}<br/>
            Tipo de venta: {ventas_online}<br/>
            Fecha y hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}<br/>
            Código de informe: {codigo_informe}
            """
            elementos.append(Paragraph(encabezado, estilo_encabezado))
            elementos.append(Spacer(1, 12))

            # KPIs
            total_ventas = self.labels_stats["Total Ventas (€)"].text()
            beneficio = self.labels_stats["Beneficio Neto (€)"].text()
            unidades = self.labels_stats["Unidades Vendidas"].text()
            ticket_medio = self.labels_stats["Ticket Medio (€)"].text()

            kpi_data = [
                ["Indicador", "Valor"],
                ["Total Facturado (€)", total_ventas],
                ["Beneficio Neto (€)", beneficio],
                ["Unidades Vendidas", unidades],
                ["Ticket Medio (€)", ticket_medio],
            ]
            tabla_kpi = Table(kpi_data, hAlign="LEFT", colWidths=[8 * cm, 6 * cm])
            tabla_kpi.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00FFC6")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ]
                )
            )
            elementos.append(tabla_kpi)
            elementos.append(Spacer(1, 12))

            # Tabla por secciones
            secciones = []
            for row in range(self.tabla.rowCount()):
                sec_item = self.tabla.item(row, 0)
                total_item = self.tabla.item(row, 1)
                prod_item = self.tabla.item(row, 2)
                sec = sec_item.text() if sec_item else ""
                total = total_item.text() if total_item else ""
                prod_top = prod_item.text() if prod_item else ""
                secciones.append([sec, total, prod_top])

            tabla_secciones = Table(
                [["Sección", "Total Ventas (€)", "Producto Más Vendido"]] + secciones,
                colWidths=[5 * cm, 4 * cm, 5 * cm],
            )
            tabla_secciones.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00FFC6")),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ]
                )
            )
            elementos.append(Paragraph("Resumen por sección:", estilo_subtitulo))
            elementos.append(tabla_secciones)
            elementos.append(Spacer(1, 12))

            # Observaciones
            observaciones = ""
            for row in secciones:
                seccion, total, producto = row
                observaciones += f"📈 La sección {seccion} generó {total}, producto más vendido: {producto}.\n"
            elementos.append(Paragraph("Observaciones:", estilo_subtitulo))
            elementos.append(
                Paragraph(observaciones.replace("\n", "<br/>"), estilo_normal)
            )
            elementos.append(Spacer(1, 12))

            # Gráfica actual
            img_buf = io.BytesIO()
            if self.current_chart == "hours":
                self.fig_horas.savefig(
                    img_buf, format="PNG", dpi=150, bbox_inches="tight"
                )
            else:
                self.fig.savefig(img_buf, format="PNG", dpi=150, bbox_inches="tight")
            img_buf.seek(0)
            elementos.append(Image(img_buf, width=16 * cm, height=8 * cm))
            elementos.append(Spacer(1, 8))

            # Detalle por secciones en texto
            detalle_text = self.label_detalle_secciones.text()
            if detalle_text:
                elementos.append(
                    Paragraph("<b>Detalle por secciones:</b>", estilo_subtitulo)
                )
                elementos.append(
                    Paragraph(detalle_text.replace(" | ", "<br/>"), estilo_normal)
                )
                elementos.append(Spacer(1, 8))

            # Logo opcional
            if os.path.exists(self.logo_path):
                elementos.append(Image(self.logo_path, width=4 * cm, height=4 * cm))

            # Generar PDF
            doc.build(elementos)
            QMessageBox.information(self, "PDF generado", f"PDF guardado en {path}")
        except Exception as e:
            QMessageBox.critical(
                self, "Error exportando PDF", f"No se pudo exportar PDF: {e}"
            )


# -----------------------------
# Resumen de ventas
# -----------------------------
import os
import logging
from datetime import datetime, timedelta
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import A4
from src.db.conexion import obtener_conexion  # adapta si tu import es distinto


def resumen_ventas(
    periodo_from: str,
    periodo_to: str,
    empleado: str = None,
    ventas_online: str = None,
    hora_inicio: int = 8,
    hora_fin: int = 22,
):
    """
    Devuelve un dict con:
      - Totales por sección
      - Top por sección
      - Ticket medio
      - Comparativa con media semanal anterior
      - Filtrado opcional por hora
    """
    conn = obtener_conexion()
    cur = conn.cursor()

    params = [periodo_from, periodo_to]
    query = """
        SELECT vi.seccion_tienda, vi.codigo_articulo, vi.descripcion,
               SUM(vi.total_item) AS total_venta, SUM(vi.cantidad) AS total_cant,
               v.empleado, v.canal, strftime('%H', v.fecha) AS hora
        FROM venta_items vi
        JOIN ventas v ON vi.venta_id = v.id
        WHERE date(v.fecha) BETWEEN date(?) AND date(?)
    """

    # Filtros dinámicos
    if empleado and empleado.lower() not in ["todos", "ninguno"]:
        query += " AND v.empleado = ?"
        params.append(empleado)
    if ventas_online and ventas_online.lower() in ["sí", "si", "no"]:
        query += " AND v.canal = ?"
        params.append(1 if ventas_online.lower() in ["sí", "si"] else 0)

    # Filtro por hora
    query += " AND CAST(strftime('%H', v.fecha) AS INTEGER) BETWEEN ? AND ?"
    params.extend([hora_inicio, hora_fin])

    query += " GROUP BY vi.seccion_tienda, vi.codigo_articulo, vi.descripcion ORDER BY vi.seccion_tienda, total_venta DESC"

    cur.execute(query, params)
    rows = cur.fetchall()

    # -----------------------------
    # Calcular totales y top por sección
    # -----------------------------
    totals_by_section = {}
    top_by_section = {}
    total_general = 0
    total_items = 0

    for sec, codigo, desc, total_v, total_c, _, _, _ in rows:
        sec = sec or "Sin sección"
        totals_by_section.setdefault(sec, 0.0)
        totals_by_section[sec] += total_v or 0.0
        total_general += total_v or 0.0
        total_items += total_c or 0
        if sec not in top_by_section:
            top_by_section[sec] = {
                "codigo": codigo,
                "descripcion": desc,
                "total_venta": total_v,
            }

    # Ticket medio
    ticket_medio = total_general / total_items if total_items > 0 else 0.0

    # Comparativa con media semanal anterior
    cur.execute(
        """
        SELECT AVG(total_dia) FROM (
            SELECT date(v.fecha) AS dia, SUM(v.total) AS total_dia
            FROM ventas v
            WHERE date(v.fecha) BETWEEN date(?, '-7 day') AND date(?)
            GROUP BY date(v.fecha)
        )
    """,
        (periodo_from, periodo_from),
    )
    media_semana_anterior = cur.fetchone()[0] or 0.0
    conn.close()

    comparativa = (
        ((total_general - media_semana_anterior) / media_semana_anterior * 100)
        if media_semana_anterior
        else 0.0
    )

    return {
        "totales": totals_by_section,
        "top": top_by_section,
        "total_general": total_general,
        "ticket_medio": ticket_medio,
        "comparativa_semana_anterior": comparativa,
    }


# -----------------------------
# Watcher handler: registro DB + notificación flotante
# -----------------------------
def handle_new_file(carpeta, filename, fullpath, parent_window=None):
    """
    Callback invocado por FolderWatcher cuando aparece un nuevo fichero.
    Registra en DB y muestra FloatingNotification (si parent_window dado).
    """
    try:
        # Registrar documento en la DB
        register_document_in_db(carpeta, filename, fullpath)

        # Mostrar notificación flotante
        if parent_window:
            notif = FloatingNotification(
                title=f"Nuevo archivo en {carpeta}",
                message=filename,
                file_path=fullpath,
                timeout_ms=5000,
                parent=parent_window,
            )
            notif.show()
    except Exception:
        logging.exception("Error mostrando notificación de nuevo archivo")


import sys
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class MatplotlibCanvas(QWidget):
    """
    Widget de Matplotlib integrado en PyQt6.
    Permite crear gráficos dinámicos y actualizables.
    """

    def __init__(self, parent=None, ancho=6, alto=4, dpi=100):
        super().__init__(parent)
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Crear figura y canvas
        self.fig = Figure(figsize=(ancho, alto), dpi=dpi)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.canvas.updateGeometry()
        self.layout.addWidget(self.canvas)

        # Configuración inicial del estilo
        self.fig.patch.set_facecolor("#121212")  # fondo general
        self.axes = self.fig.add_subplot(111)
        self.axes.set_facecolor("#121212")
        self.axes.tick_params(axis="x", colors="white")
        self.axes.tick_params(axis="y", colors="white")
        self.axes.title.set_color("white")
        self.axes.xaxis.label.set_color("white")
        self.axes.yaxis.label.set_color("white")

    # --------------------------
    # Método: actualizar gráfico de barras
    # --------------------------
    def actualizar_barra(
        self, etiquetas, valores, titulo="Gráfico de barras", color="#00FFC6"
    ):
        self.fig.clear()
        self.axes = self.fig.add_subplot(111)
        self.axes.bar(etiquetas, valores, color=color)
        self.axes.set_title(titulo, color="white", fontsize=12, fontweight="bold")
        self.axes.set_ylabel("Valores", color="white")
        self.axes.set_xlabel("Categorías", color="white")
        self.axes.tick_params(axis="x", colors="white")
        self.axes.tick_params(axis="y", colors="white")
        self.axes.set_facecolor("#121212")
        self.fig.patch.set_facecolor("#121212")
        self.canvas.draw()

    # --------------------------
    # Método: actualizar gráfico de líneas
    # --------------------------
    def actualizar_linea(
        self, x, y, titulo="Gráfico de líneas", color="#00FFC6", marcador="o"
    ):
        self.fig.clear()
        self.axes = self.fig.add_subplot(111)
        self.axes.plot(x, y, marker=marcador, linewidth=2, color=color)
        self.axes.set_title(titulo, color="white", fontsize=12, fontweight="bold")
        self.axes.set_xlabel("Eje X", color="white")
        self.axes.set_ylabel("Eje Y", color="white")
        self.axes.tick_params(axis="x", colors="white")
        self.axes.tick_params(axis="y", colors="white")
        self.axes.grid(True, linestyle="--", alpha=0.3)
        self.axes.set_facecolor("#121212")
        self.fig.patch.set_facecolor("#121212")
        self.canvas.draw()


# -----------------------------
# Buscador Avanzado (QDialog autocontenido) — VERSIÓN CORREGIDA
# -----------------------------
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QDateEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QGraphicsDropShadowEffect,
    QMessageBox,
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt
import os, logging
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.barcode import code128

# NOTE: no usamos Drawing.add() para barcode; usamos barcode.drawOn()

from src.db.conexion import obtener_conexion

# Ruta por defecto donde se guardan los PDFs (raíz/Documentos/Tickets)
DEFAULT_PDF_DIR = os.path.join(os.getcwd(), "Documentos", "Tickets")
# Ruta de la fuente dentro de Assets
COURIER_TTF_PATH = os.path.join(os.getcwd(), "Assets", "Courier.ttf")


class BusquedaAvanzada(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Búsqueda avanzada de tickets")
        self.setStyleSheet(
            """
            QWidget { background-color: #121212; color: white; }
            QLineEdit, QComboBox, QDateEdit { background-color: #1E1E1E; border: 1px solid #30363d; color: white; padding: 6px; border-radius: 6px; }
            QPushButton { background-color: #00FFC6; color: #0E1111; font-weight: bold; padding: 8px 12px; border-radius: 10px; }
            QPushButton:hover { background-color: #00E0AA; }
            QTableWidget { background-color: #121212; color: white; gridline-color: #30363d; }
            QLabel { color: white; }
        """
        )
        self.resize(1000, 620)
        self._build_ui()
        self._populate_dropdowns()

    def estilo_boton(self, btn, rojo=False):
        if rojo:
            base, hover, text_color, padding = "#FF4B4B", "#FF2222", "#FFFFFF", "12px"
        else:
            base, hover, text_color, padding = "#00FFC6", "#00DDAA", "#0E1117", "20px"
        btn.setStyleSheet(
            f"""
            QPushButton {{ background-color: {base}; color: {text_color}; font-weight: bold; border-radius: 15px; padding: {padding}; }}
            QPushButton:hover {{ background-color: {hover}; }}
        """
        )
        btn.setFont(QFont("Segoe UI", 11))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(base))
        shadow.setOffset(0)
        btn.setGraphicsEffect(shadow)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("🔎 Búsqueda avanzada de tickets")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # Filtros
        row1 = QHBoxLayout()
        self.input_ticket = QLineEdit()
        self.input_ticket.setPlaceholderText("Código ticket")
        self.input_articulo = QLineEdit()
        self.input_articulo.setPlaceholderText("Código artículo")
        row1.addWidget(self.input_ticket)
        row1.addWidget(self.input_articulo)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.fecha_desde = QDateEdit()
        self.fecha_desde.setCalendarPopup(True)
        self.fecha_desde.setDisplayFormat("yyyy-MM-dd")
        self.fecha_hasta = QDateEdit()
        self.fecha_hasta.setCalendarPopup(True)
        self.fecha_hasta.setDisplayFormat("yyyy-MM-dd")
        # inicializar fechas a hoy
        self.fecha_desde.setDate(datetime.now().date())
        self.fecha_hasta.setDate(datetime.now().date())
        self.hora_desde = QLineEdit()
        self.hora_desde.setPlaceholderText("HH:MM (opcional)")
        self.hora_hasta = QLineEdit()
        self.hora_hasta.setPlaceholderText("HH:MM (opcional)")
        row2.addWidget(QLabel("Desde:"))
        row2.addWidget(self.fecha_desde)
        row2.addWidget(QLabel("Hasta:"))
        row2.addWidget(self.fecha_hasta)
        row2.addWidget(QLabel("Hora desde:"))
        row2.addWidget(self.hora_desde)
        row2.addWidget(QLabel("Hora hasta:"))
        row2.addWidget(self.hora_hasta)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        self.combo_empleado = QComboBox()
        self.combo_empleado.addItem("Todos")
        self.combo_caja = QComboBox()
        self.combo_caja.addItem("Todas")
        self.combo_forma = QComboBox()
        self.combo_forma.addItems(
            ["Todos", "Efectivo", "Tarjeta", "Cupón", "Tarjeta Regalo"]
        )
        row3.addWidget(QLabel("Empleado:"))
        row3.addWidget(self.combo_empleado)
        row3.addWidget(QLabel("Caja:"))
        row3.addWidget(self.combo_caja)
        row3.addWidget(QLabel("Forma pago:"))
        row3.addWidget(self.combo_forma)
        layout.addLayout(row3)

        row4 = QHBoxLayout()
        self.input_min = QLineEdit()
        self.input_min.setPlaceholderText("Importe mínimo (€)")
        self.input_max = QLineEdit()
        self.input_max.setPlaceholderText("Importe máximo (€)")
        row4.addWidget(self.input_min)
        row4.addWidget(self.input_max)
        layout.addLayout(row4)

        rowb = QHBoxLayout()
        self.btn_buscar = QPushButton("Buscar")
        self.btn_limpiar = QPushButton("Limpiar")
        self.btn_export = QPushButton("Exportar ticket (PDF)")
        self.estilo_boton(self.btn_buscar)
        self.estilo_boton(self.btn_limpiar)
        self.estilo_boton(self.btn_export)
        rowb.addWidget(self.btn_buscar)
        rowb.addWidget(self.btn_limpiar)
        rowb.addWidget(self.btn_export)
        layout.addLayout(rowb)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Ticket", "Fecha", "Empleado", "Caja", "Total (€)"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, stretch=1)

        bottom = QHBoxLayout()
        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet("color: #A0A0A0;")
        bottom.addWidget(self.lbl_info, stretch=1)
        self.btn_volver = QPushButton("Volver atrás")
        self.estilo_boton(self.btn_volver, rojo=True)
        self.btn_volver.setFixedWidth(180)
        bottom.addWidget(self.btn_volver, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(bottom)

        # Connections
        self.btn_buscar.clicked.connect(self._on_buscar)
        self.btn_limpiar.clicked.connect(self._on_limpiar)
        self.btn_export.clicked.connect(self._on_export_clicked)
        self.btn_volver.clicked.connect(self._on_volver)
        self.table.cellDoubleClicked.connect(self._on_table_double_click)

    def _populate_dropdowns(self):
        try:
            conn = obtener_conexion()
            cur = conn.cursor()
            cur.execute(
                "SELECT DISTINCT empleado FROM ventas WHERE empleado IS NOT NULL AND empleado <> ''"
            )
            for (e,) in cur.fetchall():
                if e not in [
                    self.combo_empleado.itemText(i)
                    for i in range(self.combo_empleado.count())
                ]:
                    self.combo_empleado.addItem(e)
            cur.execute(
                "SELECT DISTINCT numero_caja FROM ventas WHERE numero_caja IS NOT NULL"
            )
            for (n,) in cur.fetchall():
                ns = str(n)
                if ns not in [
                    self.combo_caja.itemText(i) for i in range(self.combo_caja.count())
                ]:
                    self.combo_caja.addItem(ns)
            cur.execute(
                "SELECT DISTINCT forma_pago FROM ventas WHERE forma_pago IS NOT NULL"
            )
            for (f,) in cur.fetchall():
                if f not in [
                    self.combo_forma.itemText(i)
                    for i in range(self.combo_forma.count())
                ]:
                    self.combo_forma.addItem(f)
            conn.close()
        except Exception:
            logging.exception("Error poblando dropdowns buscador")

    def _on_limpiar(self):
        self.input_ticket.clear()
        self.input_articulo.clear()
        self.combo_empleado.setCurrentIndex(0)
        self.combo_caja.setCurrentIndex(0)
        self.combo_forma.setCurrentIndex(0)
        self.input_min.clear()
        self.input_max.clear()
        self.fecha_desde.setDate(datetime.now().date())
        self.fecha_hasta.setDate(datetime.now().date())
        self.table.setRowCount(0)
        self.lbl_info.setText("")

    def _on_buscar(self):
        # construir filtros
        filters = {
            "codigo_ticket": self.input_ticket.text().strip() or None,
            "codigo_articulo": self.input_articulo.text().strip() or None,
            "fecha_from": self.fecha_desde.date().toString("yyyy-MM-dd"),
            "fecha_to": self.fecha_hasta.date().toString("yyyy-MM-dd"),
            "hora_from": self.hora_desde.text().strip() or None,
            "hora_to": self.hora_hasta.text().strip() or None,
            "empleado": self.combo_empleado.currentText(),
            "numero_caja": self.combo_caja.currentText(),
            "forma_pago": self.combo_forma.currentText(),
            "min_total": self.input_min.text().strip() or None,
            "max_total": self.input_max.text().strip() or None,
        }

        logging.info("Busqueda avanzada - filtros: %s", filters)
        try:
            results = self.search_tickets(filters)
            # cargar en tabla y actualizar información
            self._load_results_into_table(results)
            self.lbl_info.setText(f"{len(results)} resultados")
        except Exception as e:
            logging.exception("Error en busqueda avanzada")
            mostrar_alerta_automatica(self, f"Error al buscar: {e}", "error")

    def _load_results_into_table(self, results):
        # limpia e inserta filas (evita problemas de primera búsqueda)
        self.table.setRowCount(0)
        for r in results:
            rowpos = self.table.rowCount()
            self.table.insertRow(rowpos)
            self.table.setItem(rowpos, 0, QTableWidgetItem(str(r["id"])))
            self.table.setItem(rowpos, 1, QTableWidgetItem(str(r["codigo_ticket"])))
            self.table.setItem(rowpos, 2, QTableWidgetItem(str(r["fecha"])))
            self.table.setItem(rowpos, 3, QTableWidgetItem(str(r["empleado"])))
            self.table.setItem(rowpos, 4, QTableWidgetItem(str(r["numero_caja"])))
            self.table.setItem(rowpos, 5, QTableWidgetItem(f"{float(r['total']):.2f}"))

    def _on_table_double_click(self, row, col):
        # exportar la fila doble clicada
        self._on_export_clicked()

    def _on_export_clicked(self):
        fila = self.table.currentRow()
        if fila < 0:
            QMessageBox.warning(self, "Atención", "Seleccione un ticket primero")
            return
        venta_id_item = self.table.item(fila, 0)
        if not venta_id_item:
            QMessageBox.warning(self, "Atención", "No se pudo leer el ID del ticket")
            return
        try:
            venta_id = int(venta_id_item.text())
        except ValueError:
            QMessageBox.warning(self, "Atención", "ID de ticket inválido")
            return

        # Llamada a la función de exportación integrada en la clase
        path = self.export_ticket_pdf(venta_id, parent=self)
        if path:
            # aviso y abrir con la app por defecto
            mostrar_alerta_automatica(self, f"Ticket exportado: {path}", "success")
            try:
                open_file_with_default_app(path)
            except Exception:
                logging.exception("No se pudo abrir el PDF automáticamente")
        else:
            mostrar_alerta_automatica(self, "No se pudo exportar el ticket.", "error")

    def export_ticket_pdf(self, venta_id, carpeta_dest=None, parent=None):
        """
        Exporta un ticket (venta_id) a PDF en carpeta_dest.
        Devuelve ruta del PDF o None.
        Muestra notificaciones de éxito o error (mostrar_alerta_automatica).
        """
        conn = None
        try:
            # ==================== OBTENER DATOS ====================
            conn = obtener_conexion()
            cur = conn.cursor()

            cur.execute(
                """
                SELECT codigo_ticket, fecha, empleado, numero_caja, 
                       total_efectivo, total_tarjeta, total, forma_pago, empresa, tienda
                FROM ventas WHERE id = ?
            """,
                (venta_id,),
            )

            r = cur.fetchone()

            if not r:
                mostrar_alerta_automatica(
                    self, "No se encontró la venta seleccionada.", "error"
                )
                return None

            venta = {
                "codigo_ticket": r[0] or "",
                "fecha": r[1] or "",
                "empleado": r[2] or "",
                "numero_caja": r[3] or "",
                "total_efectivo": r[4] or 0.0,
                "total_tarjeta": r[5] or 0.0,
                "total": r[6] or 0.0,
                "forma_pago": r[7] or "",
                "empresa": r[8] or "",
                "tienda": r[9] or "",
                "items": [],
            }

            # --- ITEMS ---
            cur.execute(
                """
                SELECT codigo_articulo, descripcion, cantidad, precio_unitario, total_item
                FROM venta_items WHERE venta_id = ?
            """,
                (venta_id,),
            )

            for it in cur.fetchall():
                venta["items"].append(
                    {
                        "codigo_articulo": it[0] or "",
                        "descripcion": it[1] or "",
                        "cantidad": it[2] or 0,
                        "precio_unitario": it[3] or 0.0,
                        "total_item": it[4] or 0.0,
                    }
                )
        except Exception:
            logging.exception("Error leyendo datos de la venta")
            mostrar_alerta_automatica(
                parent or self, "Error al leer los datos de la venta.", "error"
            )
            if conn:
                conn.close()
            return None
        finally:
            # cerrar conexión si queda abierta
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

        # ==================== CREAR CARPETA ====================
        try:
            if carpeta_dest is None:
                carpeta_dest = DEFAULT_PDF_DIR
            os.makedirs(carpeta_dest, exist_ok=True)
        except Exception:
            logging.exception("No se pudo crear la carpeta de destino")
            mostrar_alerta_automatica(
                parent or self, "No se pudo crear la carpeta de destino.", "error"
            )
            return None

        filename = f"ticket_{venta['codigo_ticket'] or 'sin_codigo'}.pdf"
        path = os.path.join(carpeta_dest, filename)

        # ==================== Registrar fuente (si existe) ====================
        try:
            if os.path.isfile(COURIER_TTF_PATH):
                pdfmetrics.registerFont(TTFont("Mono", COURIER_TTF_PATH))
                font_main = "Mono"
            else:
                font_main = "Helvetica"
        except Exception:
            logging.exception("No se pudo registrar la fuente TTF")
            font_main = "Helvetica"

        # ==================== GENERAR PDF ====================
        try:
            c = canvas.Canvas(path, pagesize=(250, 600))
            x = 10
            y = 580

            # --- Cabecera ---
            c.setFont(font_main, 13)
            c.drawCentredString(125, y, f"{venta['empresa'] or ''}")
            y -= 16
            c.setFont(font_main, 11)
            c.drawCentredString(125, y, f"{venta['tienda'] or ''}")
            y -= 20

            c.setFont(font_main, 9)
            c.drawString(x, y, f"Ticket: {venta['codigo_ticket']}")
            y -= 12
            c.drawString(x, y, f"Fecha: {venta['fecha']}")
            y -= 12
            c.drawString(x, y, f"Empleado: {venta['empleado']}")
            y -= 12
            c.drawString(x, y, f"Caja: {venta['numero_caja']}")
            y -= 18

            c.line(x, y, 240, y)
            y -= 14

            # --- Items del ticket ---
            c.setFont(font_main, 9)
            for it in venta["items"]:
                desc = (it["descripcion"] or "")[:32]
                # multi-line simple
                while len(desc) > 32:
                    c.drawString(x, y, desc[:32])
                    desc = desc[32:]
                    y -= 12
                c.drawString(x, y, desc)
                y -= 12

                linea_precio = f"{it['cantidad']} x {it['precio_unitario']:.2f}€"
                importe = f"{it['total_item']:.2f}€"
                c.drawString(x, y, linea_precio)
                c.drawRightString(240, y, importe)
                y -= 16

                if y < 120:  # dejar espacio para pie
                    c.showPage()
                    c = canvas.Canvas(path, pagesize=(250, 600))
                    x = 10
                    y = 580
                    c.setFont(font_main, 9)

            y -= 6
            c.line(x, y, 240, y)
            y -= 16

            # --- Totales ---
            c.setFont(font_main, 10)
            c.drawString(x, y, f"Total efectivo:")
            c.drawRightString(240, y, f"{venta['total_efectivo']:.2f}€")
            y -= 14

            c.drawString(x, y, f"Total tarjeta:")
            c.drawRightString(240, y, f"{venta['total_tarjeta']:.2f}€")
            y -= 14

            c.setFont(font_main, 12)
            c.drawString(x, y, "TOTAL:")
            c.drawRightString(240, y, f"{venta['total']:.2f}€")
            y -= 22

            # --- Pie de ticket (info legal y contacto) ---
            c.setFont(font_main, 7)
            c.drawCentredString(125, y, "Devoluciones hasta 14 días con ticket")
            y -= 10
            c.drawCentredString(125, y, "Garantía 2 años en productos electrónicos")
            y -= 10
            c.drawCentredString(125, y, "Este ticket sirve como comprobante fiscal")
            y -= 10
            c.drawCentredString(
                125, y, "Tel: 900 123 456 | Email: contacto@empresa.com"
            )
            y -= 10
            c.drawCentredString(125, y, "www.empresa.com | Dirección de tienda ABC")
            y -= 12
            c.drawCentredString(125, y, "Gracias por confiar en nosotros")
            y -= 12

            # --- Código de barras (usa codigo_ticket, fallback si None) ---
            ticket_codigo = venta["codigo_ticket"] or "SIN_CODIGO"
            try:
                barcode = code128.Code128(
                    str(ticket_codigo), barHeight=40, barWidth=1.2
                )
                # centrar barcode respecto al ancho 250 -> posicion x = (250 - barcode.width)/2
                barcode_x = (250 - barcode.width) / 2
                barcode_y = y - 50
                barcode.drawOn(c, barcode_x, barcode_y)
                y = barcode_y - 10
            except Exception:
                logging.exception("Error generando código de barras (se omite)")

            c.save()

            logging.info("Ticket exportado correctamente: %s", path)
            mostrar_alerta_automatica(
                parent or self, f"Ticket exportado correctamente:\n{path}", "success"
            )
            return path

        except Exception:
            logging.exception("Error export_ticket_pdf")
            mostrar_alerta_automatica(
                parent or self, "Ocurrió un error al generar el PDF.", "error"
            )
            return None

    # -----------------------------
    # Buscar tickets con filtros
    # -----------------------------
    def search_tickets(self, filters: dict):
        """
        Busca tickets en la BD aplicando filtros pasados en el dict.
        Filtros aceptados (típicos):
          - codigo_ticket, fecha_from, fecha_to, hora_from, hora_to,
          - codigo_articulo, empleado, numero_caja, forma_pago,
          - min_total, max_total
        Devuelve lista de dicts con items incluidos.
        """
        conn = None
        try:
            conn = obtener_conexion()
            cur = conn.cursor()
            base_q = (
                "SELECT id, codigo_ticket, fecha, empleado, numero_caja, "
                "total_efectivo, total_tarjeta, total, forma_pago, empresa, tienda "
                "FROM ventas WHERE 1=1"
            )
            params = []
            if filters.get("codigo_ticket"):
                base_q += " AND codigo_ticket = ?"
                params.append(filters["codigo_ticket"])
            if filters.get("fecha_from"):
                base_q += " AND date(fecha) >= date(?)"
                params.append(filters["fecha_from"])
            if filters.get("fecha_to"):
                base_q += " AND date(fecha) <= date(?)"
                params.append(filters["fecha_to"])
            if filters.get("hora_from"):
                base_q += " AND time(fecha) >= time(?)"
                params.append(filters["hora_from"])
            if filters.get("hora_to"):
                base_q += " AND time(fecha) <= time(?)"
                params.append(filters["hora_to"])
            if filters.get("empleado") and filters["empleado"] not in ("Todos", ""):
                base_q += " AND empleado = ?"
                params.append(filters["empleado"])
            if filters.get("numero_caja") and filters["numero_caja"] not in (
                "Todas",
                "",
            ):
                try:
                    base_q += " AND numero_caja = ?"
                    params.append(int(filters["numero_caja"]))
                except Exception:
                    pass
            if filters.get("forma_pago") and filters["forma_pago"] not in ("Todos", ""):
                base_q += " AND forma_pago = ?"
                params.append(filters["forma_pago"])
            if filters.get("min_total") not in (None, ""):
                try:
                    base_q += " AND total >= ?"
                    params.append(float(filters["min_total"]))
                except Exception:
                    pass
            if filters.get("max_total") not in (None, ""):
                try:
                    base_q += " AND total <= ?"
                    params.append(float(filters["max_total"]))
                except Exception:
                    pass

            cur.execute(base_q, params)
            ventas = []
            rows = cur.fetchall()
            for r in rows:
                venta = {
                    "id": r[0],
                    "codigo_ticket": r[1],
                    "fecha": r[2],
                    "empleado": r[3],
                    "numero_caja": r[4],
                    "total_efectivo": r[5],
                    "total_tarjeta": r[6],
                    "total": r[7],
                    "forma_pago": r[8],
                    "empresa": r[9],
                    "tienda": r[10],
                    "items": [],
                }
                cur.execute(
                    "SELECT codigo_articulo, descripcion, cantidad, precio_unitario, total_item, seccion_tienda FROM venta_items WHERE venta_id = ?",
                    (venta["id"],),
                )
                items = cur.fetchall()
                for it in items:
                    venta["items"].append(
                        {
                            "codigo_articulo": it[0],
                            "descripcion": it[1],
                            "cantidad": it[2],
                            "precio_unitario": it[3],
                            "total_item": it[4],
                            "seccion": it[5],
                        }
                    )
                # filtro por código de artículo (si pedido)
                if filters.get("codigo_articulo"):
                    found = any(
                        it["codigo_articulo"] == filters["codigo_articulo"]
                        for it in venta["items"]
                    )
                    if not found:
                        continue
                ventas.append(venta)
            return ventas
        except Exception:
            logging.exception("Error en search_tickets")
            return []
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

    def _on_volver(self):
        self.close()


# Helper externo
def abrir_busqueda_avanzada_desde_ventas(parent_window):
    try:
        dlg = BusquedaAvanzada(parent=parent_window)
        dlg.exec()
    except Exception:
        logging.exception("No se pudo abrir BusquedaAvanzada")


class VentasWindow(QMainWindow):
    # Ajustado para ser compatible con el sistema de navegación global
    def __init__(self, callback_vuelta=None, usuario=None, **kwargs):
        super().__init__()

        # Estandarizamos referencias
        self.callback_vuelta = callback_vuelta
        self.usuario_actual = usuario

        # Mantenemos 'self.perfil' extrayéndolo del objeto usuario para no romper la lógica interna
        if isinstance(usuario, dict):
            self.perfil = usuario.get("perfil", "OPERARIO")
        else:
            self.perfil = getattr(usuario, "perfil", "OPERARIO")

        self.setWindowTitle("Gestión de Ventas")
        self.setGeometry(100, 100, 1200, 700)

        # 🔹 Inicialización de UI y datos
        self._build_ui()
        self._load_data_initial()
        self._init_watchers()
        self._check_auto_prediction()

    # -----------------------------
    # Construcción de la interfaz
    # -----------------------------
    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        title = QLabel("🧾 Panel de gestión de ventas")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        layout.addWidget(title)

        # --- BOTÓN VOLVER AL MENÚ PRINCIPAL ---
        btn_volver_menu = QPushButton("Volver al menú principal")
        self.estilo_boton(btn_volver_menu, rojo=True)
        btn_volver_menu.setFixedWidth(220)
        btn_volver_menu.clicked.connect(self.volver_al_menu)

        layout.addStretch()
        layout.addWidget(btn_volver_menu, alignment=Qt.AlignmentFlag.AlignRight)

        # Barra superior de botones
        btn_bar = QHBoxLayout()
        self.btn_busqueda = QPushButton("🔎 Búsqueda avanzada")
        self.btn_resumen = QPushButton("📈 Resumen de ventas")
        self.btn_prediccion = QPushButton("📊 Predicción ventas anual")
        self.btn_sync = QPushButton("🔁 Sincronizar con Drive")
        self.btn_facturacion_diaria = QPushButton("📄 Facturación diaria")

        for b in [
            self.btn_busqueda,
            self.btn_resumen,
            self.btn_prediccion,
            self.btn_sync,
            self.btn_facturacion_diaria,
        ]:
            self.estilo_boton(b)
            btn_bar.addWidget(b)

        layout.addLayout(btn_bar)

        # Tabla de ventas recientes
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Ticket", "Fecha", "Empleado", "Caja", "Total (€)", "Forma Pago"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table, stretch=1)

        # Footer
        self.lbl_status = QLabel("Listo.")
        self.lbl_status.setStyleSheet("color: #A0A0A0;")
        layout.addWidget(self.lbl_status)

        self.setCentralWidget(container)

        # Conexiones
        self.btn_busqueda.clicked.connect(
            lambda: abrir_busqueda_avanzada_desde_ventas(self)
        )
        self.btn_prediccion.clicked.connect(self.exportar_prediccion_ventas_drive)
        self.btn_resumen.clicked.connect(self.abrir_resumen_ventas)
        self.btn_sync.clicked.connect(self._sincronizar_con_drive)
        self.btn_facturacion_diaria.clicked.connect(self.abrir_historial_facturacion)

        self.table.cellDoubleClicked.connect(self._abrir_ticket_desde_tabla)

    def volver_al_menu(self):
        """
        Cierra la ventana de ventas y regresa al menú principal
        usando la referencia de callback actualizada.
        """
        # Comprobamos si existe la referencia estandarizada callback_vuelta
        if hasattr(self, "callback_vuelta") and self.callback_vuelta:
            self.callback_vuelta()
        # Fallback por si aún se usa el nombre antiguo en alguna parte
        elif hasattr(self, "volver_callback") and self.volver_callback:
            self.volver_callback()

        self.close()

    # -----------------------------
    # Helpers UI
    # -----------------------------
    def estilo_boton(self, btn, rojo=False):
        if rojo:
            base, hover, text_color, padding = "#FF4B4B", "#FF2222", "#FFFFFF", "12px"
        else:
            base, hover, text_color, padding = "#00FFC6", "#00DDAA", "#0E1117", "20px"

        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {base};
                color: {text_color};
                font-weight: bold;
                border-radius: 15px;
                padding: {padding};
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
        """
        )
        btn.setFont(QFont("Segoe UI", 11))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(base))
        shadow.setOffset(0)
        btn.setGraphicsEffect(shadow)

        self.setStyleSheet(
            """
            QMainWindow { background-color: #0E1117; color: white; }
            QPushButton {
                background-color: #00FFC6; color: #0E1111;
                border-radius: 15px; padding: 12px 18px; font-weight: bold;
            }
            QPushButton:hover { background-color: #00E0AA; }
            QLabel { color: white; }
        """
        )

    def _abrir_ticket_desde_tabla(self, row, col):
        item = self.table.item(row, 0)
        if not item:
            return
        try:
            venta_id = int(item.text())
            path = self.export_ticket_pdf(venta_id)
            if path:
                open_file_with_default_app(path)
        except Exception:
            logging.exception("Error al abrir ticket desde tabla")

    def mostrar_alerta_automatica(parent, mensaje, tipo="info"):
        from PyQt6.QtCore import Qt as _Qt

        if parent is None:
            parent = QApplication.activeWindow()
        msg = QMessageBox(parent)
        if tipo == "error":
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("Error")
        elif tipo == "warning":
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Alerta")
        else:
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("Información")
        msg.setTextFormat(_Qt.TextFormat.RichText)
        msg.setText(mensaje)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.setWindowModality(Qt.WindowModality.NonModal)
        msg.setWindowFlag(Qt.WindowType.Tool, True)
        msg.show()
        try:
            if parent is not None:
                geo = parent.geometry()
                msg_rect = msg.frameGeometry()
                center_point = geo.center()
                msg_rect.moveCenter(center_point)
                msg.move(msg_rect.topLeft())
        except Exception:
            pass

    # -----------------------------
    # Carga inicial de datos
    # -----------------------------
    def _load_data_initial(self):
        try:
            # Usamos 'with' para gestionar la conexión del generador obtener_conexion()
            with obtener_conexion() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, codigo_ticket, fecha, empleado, numero_caja, total, forma_pago "
                    "FROM ventas ORDER BY fecha DESC LIMIT 100"
                )
                rows = cur.fetchall()

            # Al salir del bloque 'with', la conexión se libera automáticamente

            self.table.setRowCount(0)
            for r in rows:
                row = self.table.rowCount()
                self.table.insertRow(row)
                for c, val in enumerate(r):
                    item = QTableWidgetItem(str(val))
                    item.setForeground(
                        QColor("white")
                    )  # Mantiene el texto legible en fondo oscuro
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.table.setItem(row, c, item)

            self.lbl_status.setText(f"Mostrando {len(rows)} ventas recientes.")
            self.lbl_status.setStyleSheet(
                "color: #00FFC6; font-weight: bold;"
            )  # Toque neón al status

        except Exception:
            logging.exception("Error cargando ventas iniciales")

    # -----------------------------
    # Watchers (carpetas monitorizadas)
    # -----------------------------
    def _init_watchers(self):
        try:
            self.watcher_docs = FolderWatcher(
                os.path.join(os.getcwd(), "documentos"),
                "documentos",
                callback=lambda c, f, p: handle_new_file(c, f, p, parent_window=self),
            )
            self.watcher_docs.start()
        except Exception:
            logging.exception("Error iniciando watchers")

    # -----------------------------
    # Exportar predicción ventas (Drive) - versión final diaria
    # -----------------------------
    def exportar_prediccion_ventas_drive(self, parent_widget=None):
        try:
            if not GOOGLE_API_AVAILABLE:
                mostrar_alerta_automatica(
                    parent_widget, "Google API no disponible en este entorno.", "error"
                )
                return None

            cfg = load_config()
            hoy = datetime.now().date()
            year = hoy.year

            carpeta_name = (
                cfg.get("carpeta_formato" or "{EMPRESA}-{TIENDA}-{AÑO}")
                .format(
                    AÑO=year,
                    AÑO_STR=str(year),
                    EMPRESA=cfg.get("empresa", "MiEmpresa"),
                    TIENDA=cfg.get("tienda", "Tienda01"),
                )
                .replace(" ", "-")
            )
            archivo_name = (
                cfg.get("archivo_formato" or "Prediccion_Ventas_{AÑO}.xlsx")
                .format(AÑO=year)
                .replace(" ", "-")
            )

            # Credenciales y servicio Drive
            creds = get_credentials(parent_widget=parent_widget)
            service = build("drive", "v3", credentials=creds, cache_discovery=False)

            # Carpeta anual y archivo existente
            folder_id, _ = ensure_drive_folder(service, carpeta_name)
            existing_file_id = find_file_in_folder(service, folder_id, archivo_name)

            # Leer archivo existente para preservar manuales
            existing = {}
            if existing_file_id:
                try:
                    bts = download_drive_file_bytes(service, existing_file_id)
                    fh = _io.BytesIO(bts)
                    wb_old = load_workbook(fh, data_only=True)
                    ws_old = wb_old.active

                    def detect_expected_real_columns(ws):
                        exp_col, real_col = None, None
                        header_row = 1
                        for col in range(1, ws.max_column + 1):
                            val = ws.cell(header_row, col).value
                            if val and "esperadas" in str(val).lower():
                                exp_col = col
                            if val and "reales" in str(val).lower():
                                real_col = col
                        return exp_col, real_col

                    exp_col, real_col = detect_expected_real_columns(ws_old)
                    for r in range(2, ws_old.max_row + 1):
                        cell_fecha = ws_old.cell(r, 1).value
                        if not cell_fecha:
                            continue
                        try:
                            date_obj = pd.to_datetime(cell_fecha).date()
                        except:
                            try:
                                date_obj = datetime.strptime(
                                    str(cell_fecha)[:10], "%Y-%m-%d"
                                ).date()
                            except:
                                continue

                        def norm(x):
                            if x is None:
                                return None
                            try:
                                s = str(x).replace("€", "").replace(",", ".").strip()
                                return float(s)
                            except:
                                try:
                                    return float(x)
                                except:
                                    return None

                        exp_val = (
                            norm(ws_old.cell(r, exp_col).value) if exp_col else None
                        )
                        real_val = (
                            norm(ws_old.cell(r, real_col).value) if real_col else None
                        )
                        existing[date_obj] = {"expected": exp_val, "real": real_val}

                except Exception:
                    logging.exception(
                        "No se pudo leer fichero existente en Drive; se generará desde BD"
                    )

            # Histórico últimos 365 días
            conn = obtener_conexion()
            cur = conn.cursor()
            fecha_inicio = (hoy - timedelta(days=365)).isoformat()
            cur.execute(
                """
                SELECT date(fecha) as d, COALESCE(SUM(total),0) as total
                FROM ventas
                WHERE date(fecha) BETWEEN date(?) AND date('now')
                GROUP BY d
                ORDER BY d
            """,
                (fecha_inicio,),
            )
            rows = cur.fetchall()
            conn.close()

            hist_by_date = {}
            for r in rows:
                try:
                    ds = pd.to_datetime(r[0]).date()
                    hist_by_date[ds] = float(r[1] or 0.0)
                except:
                    continue

            # Merge valores 'real' manuales
            for d, v in existing.items():
                if v.get("real") is not None:
                    hist_by_date[d] = v["real"]

            if not hist_by_date and not existing:
                mostrar_alerta_automatica(
                    parent_widget,
                    "No hay historial suficiente para generar predicción.",
                    "error",
                )
                return None

            # DataFrame para Prophet
            df_hist = pd.DataFrame(
                [(d, y) for d, y in hist_by_date.items()], columns=["ds", "y"]
            )
            df_hist["ds"] = pd.to_datetime(df_hist["ds"])
            df_hist = df_hist.sort_values("ds")

            # Entrenamiento
            model = Prophet(daily_seasonality=True)
            model.fit(df_hist)

            # -----------------------------
            # Construir lista completa de fechas: 3 meses anteriores, mes actual, mes siguiente
            # -----------------------------
            from dateutil.relativedelta import relativedelta

            months_to_show = []

            # Tres meses anteriores
            for i in range(3, 0, -1):
                months_to_show.append(hoy.replace(day=1) - relativedelta(months=i))

            # Mes actual
            months_to_show.append(hoy.replace(day=1))

            # Mes siguiente
            months_to_show.append(hoy.replace(day=1) + relativedelta(months=1))

            # Construir lista completa de fechas
            all_dates = []
            for m in months_to_show:
                primer_dia = m
                if m.month == 12:
                    ultimo_dia = datetime(m.year, 12, 31).date()
                else:
                    ultimo_dia = (
                        datetime(m.year, m.month + 1, 1) - timedelta(days=1)
                    ).date()
                all_dates.extend(
                    [
                        primer_dia + timedelta(days=i)
                        for i in range((ultimo_dia - primer_dia).days + 1)
                    ]
                )

            # Rellenar 0 si no hay datos
            for d in all_dates:
                if d not in hist_by_date:
                    hist_by_date[d] = 0.0

            # Fechas futuras para predicción
            start_pred = min(all_dates)
            end_pred = max(all_dates)
            future_dates = [
                start_pred + timedelta(days=i)
                for i in range((end_pred - start_pred).days + 1)
            ]
            future_df = pd.DataFrame({"ds": future_dates})
            forecast = model.predict(future_df)
            forecast["yhat"] = forecast["yhat"].apply(lambda x: max(x, 0.0))

            # -----------------------------
            # Workbook Excel
            # -----------------------------
            wb = Workbook()
            ws = wb.active
            ws.title = "Predicción Ventas"

            # Estilos
            dark_bg = "1E1E1E"
            white_font = "FFFFFF"
            yellow_fill = "FFFF00"
            blue_fill = "ADD8E6"
            thin = Side(border_style="thin", color="808080")
            bd = Border(top=thin, left=thin, right=thin, bottom=thin)

            # Encabezados
            ws.append(
                ["Fecha", "Ventas esperadas (€)", "Ventas reales (€)", "Diferencia (€)"]
            )
            for col in range(1, 5):
                cell = ws.cell(row=1, column=col)
                cell.font = Font(bold=True, color=white_font)
                cell.fill = PatternFill("solid", fgColor=dark_bg)
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.border = bd

            # Agrupar fechas por mes
            MONTH_NAMES_ES = [
                "Enero",
                "Febrero",
                "Marzo",
                "Abril",
                "Mayo",
                "Junio",
                "Julio",
                "Agosto",
                "Septiembre",
                "Octubre",
                "Noviembre",
                "Diciembre",
            ]

            months = {}
            for d in all_dates:
                months.setdefault((d.year, d.month), []).append(d)

            # Rellenar Excel
            for yr, m in sorted(months.keys()):
                dates_in_month = sorted(months[(yr, m)])
                header_row_index = ws.max_row + 1
                ws.append([f"{MONTH_NAMES_ES[m - 1]} {yr}", "", "", ""])
                ws.merge_cells(
                    start_row=header_row_index,
                    start_column=1,
                    end_row=header_row_index,
                    end_column=4,
                )
                cell = ws.cell(header_row_index, 1)
                cell.fill = PatternFill("solid", fgColor=dark_bg)
                cell.font = Font(color=white_font, bold=True, size=12)
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.border = bd

                week_rows = []
                weekly_total_rows = []

                for idx, d in enumerate(dates_in_month):
                    expected_val = existing.get(d, {}).get("expected") or round(
                        float(forecast[forecast["ds"].dt.date == d]["yhat"].iloc[0]), 2
                    )
                    real_val = existing.get(d, {}).get("real") or hist_by_date.get(
                        d, 0.0
                    )
                    ws.append([d.strftime("%Y-%m-%d"), expected_val, real_val, None])
                    fila = ws.max_row
                    ws.cell(row=fila, column=4).value = (
                        f'=IF(AND(ISNUMBER(B{fila}),ISNUMBER(C{fila})),ROUND(C{fila}-B{fila},2),"")'
                    )

                    for c in range(1, 5):
                        cell = ws.cell(fila, c)
                        cell.fill = PatternFill("solid", fgColor=dark_bg)
                        if c in (2, 3, 4):
                            cell.number_format = "#,##0.00 €"
                            cell.font = Font(color=white_font)
                        else:
                            cell.font = Font(color=white_font)
                        cell.alignment = Alignment(
                            horizontal="center", vertical="center"
                        )
                        cell.border = bd
                    week_rows.append(fila)

                    # Cierre de semana
                    is_sunday = d.weekday() == 6
                    is_last_of_month = idx == len(dates_in_month) - 1
                    if is_sunday or is_last_of_month:
                        start = week_rows[0]
                        end = week_rows[-1]
                        ws.append(
                            [
                                "Total semana",
                                f"=SUM(B{start}:B{end})",
                                f"=SUM(C{start}:C{end})",
                                f"=ROUND(SUM(D{start}:D{end}),2)",
                            ]
                        )
                        fila_total_sem = ws.max_row
                        weekly_total_rows.append(fila_total_sem)
                        for c in range(1, 5):
                            cell = ws.cell(fila_total_sem, c)
                            cell.fill = PatternFill("solid", fgColor=yellow_fill)
                            cell.font = Font(color="000000", bold=True)
                            cell.alignment = Alignment(
                                horizontal="center", vertical="center"
                            )
                            cell.border = bd
                            if c in (2, 3, 4):
                                cell.number_format = "#,##0.00 €"
                        week_rows = []

                # Total mes
                if weekly_total_rows:
                    refs_B = ",".join([f"B{r}" for r in weekly_total_rows])
                    refs_C = ",".join([f"C{r}" for r in weekly_total_rows])
                    refs_D = ",".join([f"D{r}" for r in weekly_total_rows])
                    ws.append(
                        [
                            "Total mes",
                            f"=SUM({refs_B})",
                            f"=SUM({refs_C})",
                            f"=ROUND(SUM({refs_D}),2)",
                        ]
                    )
                    fila_total_mes = ws.max_row
                    for c in range(1, 5):
                        cell = ws.cell(fila_total_mes, c)
                        cell.fill = PatternFill("solid", fgColor=blue_fill)
                        cell.font = Font(color="000000", bold=True)
                        cell.alignment = Alignment(
                            horizontal="center", vertical="center"
                        )
                        cell.border = bd
                        if c in (2, 3, 4):
                            cell.number_format = "#,##0.00 €"

            # Anchos de columna
            ws.column_dimensions["A"].width = 15
            ws.column_dimensions["B"].width = 22
            ws.column_dimensions["C"].width = 22
            ws.column_dimensions["D"].width = 22

            # Guardar y subir
            fbytes = _io.BytesIO()
            wb.save(fbytes)
            fbytes.seek(0)
            bytes_content = fbytes.read()

            try:
                existing_id = find_file_in_folder(service, folder_id, archivo_name)
                uploaded_id = upload_drive_bytes(
                    service,
                    folder_id,
                    archivo_name,
                    bytes_content,
                    existing_file_id=existing_id,
                )
                file_url = f"https://drive.google.com/file/d/{uploaded_id}/view"
                cfg["drive_pred_url"] = file_url
                cfg["last_prediccion_run"] = datetime.now().isoformat()
                save_config(cfg)
                mostrar_alerta_automatica(
                    parent_widget,
                    "✅ Predicción subida/actualizada en Drive correctamente.",
                    "info",
                )
                if cfg.get("abrir_en_navegador", True):
                    try:
                        QDesktopServices.openUrl(QUrl(file_url))
                    except:
                        webbrowser.open(file_url)
                return file_url
            except Exception as e:
                logging.exception("Error subiendo predicción a Drive: %s", e)
                mostrar_alerta_automatica(
                    parent_widget, f"No se pudo subir el archivo a Drive: {e}", "error"
                )
                return None

        except Exception as e:
            logging.exception("Error exportar_prediccion_ventas_drive")
            mostrar_alerta_automatica(
                parent_widget, f"No se pudo exportar la predicción: {e}", "error"
            )
            return None

    # -----------------------------
    # Generar predicción anual por mes
    # -----------------------------
    def _generar_prediccion_y_subir(self):
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from io import BytesIO

        year = datetime.now().year
        nombre_excel = f"Prediccion_Ventas_{year}.xlsx"
        ruta_excel = os.path.join(PDF_OUTPUT_DIR, "predicciones", nombre_excel)
        os.makedirs(os.path.dirname(ruta_excel), exist_ok=True)

        # Datos año actual corregidos para MariaDB
        try:
            with obtener_conexion() as conn:
                cur = conn.cursor()
                # Ajuste: DATE_FORMAT con %% para escapar el % en Python
                # Ajuste: Marcador %s en lugar de ? para compatibilidad con MariaDB
                cur.execute(
                    """
                    SELECT DATE_FORMAT(fecha, '%%m') as mes, SUM(total) 
                    FROM ventas 
                    WHERE DATE_FORMAT(fecha, '%%Y') = %s 
                    GROUP BY mes
                    """,
                    (str(year),),
                )
                data = cur.fetchall()
        except Exception as e:
            logging.error(f"Error en la consulta de base de datos (MariaDB): {e}")
            raise

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Predicción anual"

        # Estilos encabezados
        headers = ["Mes", "Total ventas (€)", "Predicción siguiente mes (€)"]
        ws.append(headers)
        for col in "ABC":
            ws[f"{col}1"].font = Font(bold=True, color="FFFFFF")
            ws[f"{col}1"].fill = PatternFill(
                start_color="00FFC6", end_color="00FFC6", fill_type="solid"
            )
            ws[f"{col}1"].alignment = Alignment(horizontal="center", vertical="center")

        meses = [
            "Enero",
            "Febrero",
            "Marzo",
            "Abril",
            "Mayo",
            "Junio",
            "Julio",
            "Agosto",
            "Septiembre",
            "Octubre",
            "Noviembre",
            "Diciembre",
        ]

        # Convertir resultados a diccionario asegurando que el mes sea entero
        ventas_dict = {int(m): float(v) for m, v in data}
        for i, nombre_mes in enumerate(meses, start=1):
            total = ventas_dict.get(i, 0)
            ws.append([nombre_mes, total, ""])

        # Fórmula: promedio últimos 3 meses (a partir del mes 4)
        for r in range(4, 15):
            if r >= 5:
                ws[f"C{r}"] = f"=AVERAGE(B{r-1}:B{r-3})"

        # Ajuste ancho columnas
        for col in ["A", "B", "C"]:
            ws.column_dimensions[col].width = 25

        wb.save(ruta_excel)

        # Subir a Drive
        folder_drive = "Predicciones_Ventas"
        file_id = find_file_in_folder(folder_drive, nombre_excel)
        if file_id:
            logging.info("Archivo de predicción ya existe en Drive: %s", nombre_excel)
            return ruta_excel, f"https://drive.google.com/file/d/{file_id}/view"

        # Subir nuevo archivo
        with open(ruta_excel, "rb") as f:
            file_id = upload_drive_bytes(
                f.read(),
                folder_drive,
                nombre_excel,
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        if file_id:
            url = f"https://drive.google.com/file/d/{file_id}/view"
            logging.info("Predicción subida correctamente a Drive: %s", url)
            return ruta_excel, url

        return ruta_excel, None

    # -----------------------------
    # Auto-predicción mensual (si es 1 del mes)
    # -----------------------------
    def _check_auto_prediction(self):
        hoy = datetime.now()
        if hoy.day == 1 and hoy.hour >= 0:
            try:
                logging.info("Ejecución automática de predicción mensual detectada.")
                ruta, url = self._generar_prediccion_y_subir()
                msg = f"Predicción mensual ({hoy.strftime('%B %Y')}) generada automáticamente."
                notif = FloatingNotification(
                    "Predicción mensual", msg, timeout_ms=6000, parent=self
                )
                notif.show()
                if url:
                    QDesktopServices.openUrl(QUrl(url))
            except Exception:
                logging.exception("Error generando predicción automática")

    # -----------------------------
    # Otros botones
    # -----------------------------
    def abrir_resumen_ventas(self):
        """
        Abre la ventana de resumen de ventas desde el menú principal.
        """
        try:
            # Importar aquí evita problemas de importación circular
            from src.gui.ventas import VentanaResumenVentas

            # Pasamos 'self' como padre, no 'self.perfil'
            self.ventana_ventas = VentanaResumenVentas(self, volver_callback=self.show)

            # Mostramos la ventana de ventas
            self.ventana_ventas.show()
            self.hide()

        except Exception as e:
            print("❌ Error al abrir la ventana de ventas:", e)

    def _sincronizar_con_drive(self):
        try:
            mostrar_alerta_automatica(
                self, "Sincronizando datos con Google Drive...", "info"
            )
            # Aquí se sincronizarían los PDF y registros (placeholder)
            time.sleep(1)
            mostrar_alerta_automatica(self, "Sincronización completada.", "success")
        except Exception:
            logging.exception("Error en sincronización Drive")
            mostrar_alerta_automatica(self, "Error al sincronizar.", "error")

    def abrir_historial_facturacion(self):
        """
        Abre la ventana emergente de historial de facturación diaria.
        Desde ella se puede exportar el día actual o consultar registros previos.
        """
        try:
            ventana_historial = HistorialFacturacionDiaria(self)
            ventana_historial.exec()
        except Exception as e:
            logging.exception("Error al abrir historial de facturación diaria")
            QMessageBox.critical(
                self, "Error", f"No se pudo abrir el historial de facturación.\n{e}"
            )

    def _volver_menu(self):
        """Regresa al menú principal de forma segura."""
        if self.callback_vuelta:
            try:
                self.callback_vuelta()
            finally:
                self.close()
        else:
            self.close()


# Fin PARTE 3/4
# -----------------------------
# PARTE 4/4 - Helpers finales, cierre limpio y utilidades
# -----------------------------

import time


# -----------------------------
# Helper para detener watchers de una lista (uso al cerrar)
# -----------------------------
def stop_watchers_list(watchers):
    for w in getattr(watchers, "__iter__", lambda: [])():
        try:
            if hasattr(w, "stop"):
                w.stop()
        except Exception:
            try:
                # trazas de seguridad para distintos tipos de watcher
                if hasattr(w, "_running"):
                    w._running = False
            except Exception:
                pass


# -----------------------------
# Extiende VentasWindow con cierre limpio
# -----------------------------
def _ventaswindow_close_event(self, event):
    """
    Handler para cerrar la ventana: detiene watchers y cierra recursos.
    Se asigna dinámicamente a VentasWindow.closeEvent al importar esta parte.
    """
    try:
        # detiene watchers si existen
        for w in getattr(self, "watchers", []) + getattr(self, "watcher_list", []):
            try:
                if hasattr(w, "stop"):
                    w.stop()
            except Exception:
                logging.exception("Error al detener watcher al cerrar VentasWindow")
        # también detener watcher_docs si existe (parche por si se creó por separado)
        try:
            if hasattr(self, "watcher_docs") and self.watcher_docs:
                self.watcher_docs.stop()
        except Exception:
            pass
    except Exception:
        logging.exception("Error en closeEvent de VentasWindow")
    # Llamar al comportamiento por defecto (si existe)
    try:
        super(VentasWindow, self).closeEvent(event)
    except Exception:
        event.accept()


# Asignar closeEvent dinámicamente si la clase VentasWindow ya está definida
try:
    if "VentasWindow" in globals():
        VentasWindow.closeEvent = _ventaswindow_close_event
except Exception:
    pass


# -----------------------------
# Compatibilidad: pequeña utilidad para abrir URLs/paths (ya usada en otras partes)
# -----------------------------
def safe_open_path_or_url(path_or_url):
    try:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            QDesktopServices.openUrl(QUrl(path_or_url))
        else:
            open_file_with_default_app(path_or_url)
    except Exception:
        try:
            webbrowser.open(path_or_url)
        except Exception:
            logging.exception("No se pudo abrir path/url: %s", path_or_url)


# -----------------------------
# Extra: función utilitaria para asegurar la estructura de documentos
# -----------------------------
def ensure_local_document_subdirs():
    """
    Asegura la estructura local solicitada:
      <PROJECT_ROOT>/documentos/
        - facturacion/
        - predicciones/
        - resúmenes de ventas/
        - tickets/
    """
    base = DOCUMENTS_DIR  # ✅ Se corrige: ahora apunta a 'documentos', no 'facturacion'
    subdirs = ["facturacion", "predicciones", "resúmenes de ventas", "tickets"]
    try:
        for s in subdirs:
            os.makedirs(os.path.join(base, s), exist_ok=True)
    except Exception:
        logging.exception("No se pudo crear subcarpetas en documentos")


# ❌ Eliminar esta parte (no ejecutarla al importar)
# try:
#     ensure_local_document_subdirs()
# except Exception:
#     pass
