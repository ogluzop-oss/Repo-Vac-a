# src/utils/sincronizar_ventas.py
import os
from datetime import datetime, timedelta
from threading import Thread
from time import sleep

import pandas as pd
import requests

from src.db.conexion import obtener_conexion
from src.utils.logger import LOG_SYNC
from src.utils.registro_venta import registrar_venta

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    WATCHDOG_ENABLED = True
except ImportError:
    WATCHDOG_ENABLED = False
    print("⚠️ Para usar monitor en tiempo real, instala watchdog: pip install watchdog")

try:
    import pyodbc
    SQL_ENABLED = True
except ImportError:
    SQL_ENABLED = False


# ============================================================
# BLOQUE GESTIÓN DE ERRORES DE SINCRONIZACIÓN
# ============================================================

def crear_tabla_errores():
    """Crea la tabla ventas_errores en MariaDB si no existe."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ventas_errores (
                        id       INT AUTO_INCREMENT PRIMARY KEY,
                        codigo   VARCHAR(50),
                        cantidad INT,
                        fecha    DATETIME,
                        motivo   TEXT
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
            conn.commit()
    except Exception:
        LOG_SYNC.exception("Error creando tabla ventas_errores")


def registrar_error(codigo, cantidad, fecha, motivo):
    """Guarda un error de sincronización en ventas_errores."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO ventas_errores (codigo, cantidad, fecha, motivo) VALUES (%s, %s, %s, %s)",
                    (codigo, cantidad, fecha, motivo),
                )
            conn.commit()
    except Exception:
        LOG_SYNC.exception("Error registrando error de venta")


# ============================================================
# BLOQUE SINCRONIZACIÓN DESDE ARCHIVO (EXCEL / CSV)
# ============================================================

def sincronizar_desde_archivo(origen):
    """Sincroniza ventas desde un archivo Excel o CSV."""
    if not os.path.exists(origen):
        LOG_SYNC.error("No se encontró la fuente de datos: %s", origen)
        return

    if origen.endswith((".xlsx", ".xls")):
        df = pd.read_excel(origen)
    elif origen.endswith(".csv"):
        df = pd.read_csv(origen)
    else:
        LOG_SYNC.error("Formato de archivo no soportado.")
        return

    df.columns = [col.strip().lower() for col in df.columns]
    mapeo_columnas = {
        "codigo":   ["codigo", "id_articulo", "sku", "product_id"],
        "cantidad": ["cantidad", "qty", "units"],
        "fecha":    ["fecha", "date", "datetime", "timestamp"],
    }

    columnas_finales = {}
    for clave, posibles in mapeo_columnas.items():
        for col in posibles:
            if col in df.columns:
                columnas_finales[clave] = col
                break
        if clave not in columnas_finales:
            LOG_SYNC.error("No se encontró columna válida para %r.", clave)
            return

    for _, row in df.iterrows():
        codigo   = str(row[columnas_finales["codigo"]])
        cantidad = int(row[columnas_finales["cantidad"]])
        fecha    = row.get(
            columnas_finales.get("fecha"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        exito = registrar_venta(codigo, cantidad)
        if exito:
            LOG_SYNC.info("Venta registrada: %s uds de %r", cantidad, codigo)
        else:
            motivo = "Artículo inexistente o stock insuficiente"
            LOG_SYNC.warning("Venta ignorada: %s uds de %r -> %s", cantidad, codigo, motivo)
            registrar_error(codigo, cantidad, fecha, motivo)


# ============================================================
# BLOQUE SINCRONIZACIÓN DESDE API TPV
# ============================================================

def sincronizar_desde_api(url_api, token, fecha_desde=None):
    """Sincroniza ventas desde una API TPV externa."""
    headers = {"Authorization": f"Bearer {token}"}
    params  = {}
    if fecha_desde:
        params["desde"] = fecha_desde.strftime("%Y-%m-%d")

    try:
        response = requests.get(url_api, headers=headers, params=params)
        response.raise_for_status()
        ventas = response.json()
    except Exception:
        LOG_SYNC.exception("Error al consultar API")
        return

    for venta in ventas:
        codigo   = str(venta["codigo"])
        cantidad = int(venta["cantidad"])
        fecha    = venta.get("fecha", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        exito    = registrar_venta(codigo, cantidad)
        if exito:
            LOG_SYNC.info("Venta registrada: %s uds de %r desde API TPV", cantidad, codigo)
        else:
            motivo = "Artículo inexistente o stock insuficiente"
            LOG_SYNC.warning("Venta ignorada: %s uds de %r -> %s", cantidad, codigo, motivo)
            registrar_error(codigo, cantidad, fecha, motivo)


# ============================================================
# BLOQUE SINCRONIZACIÓN DESDE BASE DE DATOS SQL (TPV EXTERNO)
# ============================================================

def sincronizar_desde_sql(conn_str, tabla_ventas, fecha_desde=None):
    """Sincroniza ventas desde una base de datos SQL de TPV externo."""
    if not SQL_ENABLED:
        LOG_SYNC.warning("pyodbc no instalado. No se puede conectar a SQL TPV.")
        return

    try:
        conn   = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        query  = f"SELECT codigo, cantidad, fecha FROM {tabla_ventas}"
        if fecha_desde:
            query += f" WHERE fecha >= '{fecha_desde.strftime('%Y-%m-%d')}'"

        cursor.execute(query)
        for codigo, cantidad, fecha in cursor.fetchall():
            exito = registrar_venta(str(codigo), int(cantidad))
            if exito:
                LOG_SYNC.info("Venta registrada: %s uds de %r desde SQL TPV", cantidad, codigo)
            else:
                motivo = "Artículo inexistente o stock insuficiente"
                LOG_SYNC.warning("Venta ignorada: %s uds de %r -> %s", cantidad, codigo, motivo)
                registrar_error(codigo, cantidad, fecha, motivo)
    except Exception:
        LOG_SYNC.exception("Error al consultar SQL")
    finally:
        conn.close()


# ============================================================
# BLOQUE MONITOR DE ARCHIVOS EN TIEMPO REAL (WATCHDOG)
# ============================================================

if WATCHDOG_ENABLED:

    class VentasHandler(FileSystemEventHandler):
        def __init__(self, archivo):
            self.archivo = archivo

        def on_modified(self, event):
            if event.src_path.endswith(self.archivo):
                LOG_SYNC.info("Cambios detectados en archivo, sincronizando...")
                sincronizar_desde_archivo(self.archivo)

    def modo_monitor(archivo, directorio="."):
        event_handler = VentasHandler(archivo)
        observer = Observer()
        observer.schedule(event_handler, path=directorio, recursive=False)
        observer.start()
        LOG_SYNC.info("Monitorizando ventas en tiempo real.")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            LOG_SYNC.info("Monitor detenido.")
        observer.join()


# ============================================================
# BLOQUE SINCRONIZACIÓN PARALELA CONTINUA
# ============================================================

def sincronizar_continuo_parallel(
    archivo=None,
    url_api=None,
    token_api=None,
    conn_str_sql=None,
    tabla_sql=None,
    intervalo_api=60,
    intervalo_sql=60,
    modo_tiempo_real=False,
):
    """Sincroniza archivo, API y SQL en paralelo usando hilos daemon."""
    crear_tabla_errores()
    ultima_fecha_api = datetime.now() - timedelta(days=1)
    ultima_fecha_sql = datetime.now() - timedelta(days=1)
    threads = []

    if archivo:
        if modo_tiempo_real and WATCHDOG_ENABLED:
            t_file = Thread(target=modo_monitor, args=(archivo,))
            t_file.daemon = True
            threads.append(t_file)
        else:
            def file_loop():
                while True:
                    sincronizar_desde_archivo(archivo)
                    sleep(1)
            t_file = Thread(target=file_loop)
            t_file.daemon = True
            threads.append(t_file)

    if url_api and token_api:
        def api_loop():
            nonlocal ultima_fecha_api
            while True:
                sincronizar_desde_api(url_api, token_api, fecha_desde=ultima_fecha_api)
                ultima_fecha_api = datetime.now()
                sleep(intervalo_api)
        t_api = Thread(target=api_loop)
        t_api.daemon = True
        threads.append(t_api)

    if SQL_ENABLED and conn_str_sql and tabla_sql:
        def sql_loop():
            nonlocal ultima_fecha_sql
            while True:
                sincronizar_desde_sql(conn_str_sql, tabla_sql, fecha_desde=ultima_fecha_sql)
                ultima_fecha_sql = datetime.now()
                sleep(intervalo_sql)
        t_sql = Thread(target=sql_loop)
        t_sql.daemon = True
        threads.append(t_sql)

    for t in threads:
        t.start()

    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        LOG_SYNC.info("Sincronización paralela detenida.")
