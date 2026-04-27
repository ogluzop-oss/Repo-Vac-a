import os
import sqlite3
import pandas as pd
import requests
from datetime import datetime, timedelta
from threading import Thread
from time import sleep
from src.db.conexion import obtener_conexion
from src.utils.registro_venta import registrar_venta

# Intentar importar watchdog para monitor en tiempo real
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    WATCHDOG_ENABLED = True
except ImportError:
    WATCHDOG_ENABLED = False
    print("⚠️ Para usar monitor en tiempo real, instala watchdog: pip install watchdog")

# Intentar importar pyodbc para SQL
try:
    import pyodbc

    SQL_ENABLED = True
except ImportError:
    SQL_ENABLED = False


# -----------------------------
# FUNCIONES AUXILIARES
# -----------------------------
def crear_tabla_errores():
    """Crea la tabla ventas_errores si no existe"""
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ventas_errores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT,
                cantidad INTEGER,
                fecha TEXT,
                motivo TEXT
            )
        """
        )
        conn.commit()
    finally:
        conn.close()


def registrar_error(codigo, cantidad, fecha, motivo):
    """Guarda un error en la tabla ventas_errores"""
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ventas_errores (codigo, cantidad, fecha, motivo)
            VALUES (?, ?, ?, ?)
        """,
            (codigo, cantidad, fecha, motivo),
        )
        conn.commit()
    finally:
        conn.close()


# -----------------------------
# SINCRONIZACIONES
# -----------------------------
def sincronizar_desde_archivo(origen):
    """Sincroniza ventas desde un archivo Excel o CSV"""
    if not os.path.exists(origen):
        print(f"❌ No se encontró la fuente de datos: {origen}")
        return

    if origen.endswith((".xlsx", ".xls")):
        df = pd.read_excel(origen)
    elif origen.endswith(".csv"):
        df = pd.read_csv(origen)
    else:
        print("⚠️ Formato de archivo no soportado actualmente.")
        return

    df.columns = [col.strip().lower() for col in df.columns]
    mapeo_columnas = {
        "codigo": ["codigo", "id_articulo", "sku", "product_id"],
        "cantidad": ["cantidad", "qty", "units"],
        "fecha": ["fecha", "date", "datetime", "timestamp"],
    }

    columnas_finales = {}
    for clave, posibles in mapeo_columnas.items():
        for col in posibles:
            if col in df.columns:
                columnas_finales[clave] = col
                break
        if clave not in columnas_finales:
            print(f"❌ No se encontró columna válida para '{clave}' en el archivo.")
            return

    for _, row in df.iterrows():
        codigo = str(row[columnas_finales["codigo"]])
        cantidad = int(row[columnas_finales["cantidad"]])
        fecha = row.get(
            columnas_finales.get("fecha"), datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        exito = registrar_venta(codigo, cantidad)
        if exito:
            print(f"✅ Venta registrada: {cantidad} unidades de '{codigo}'")
        else:
            motivo = "Artículo inexistente o stock insuficiente"
            print(f"⚠️ Venta ignorada: {cantidad} unidades de '{codigo}' -> {motivo}")
            registrar_error(codigo, cantidad, fecha, motivo)


def sincronizar_desde_api(url_api, token, fecha_desde=None):
    """Sincroniza ventas desde API TPV"""
    headers = {"Authorization": f"Bearer {token}"}
    params = {}
    if fecha_desde:
        params["desde"] = fecha_desde.strftime("%Y-%m-%d")

    try:
        response = requests.get(url_api, headers=headers, params=params)
        response.raise_for_status()
        ventas = response.json()
    except Exception as e:
        print(f"❌ Error al consultar API: {e}")
        return

    for venta in ventas:
        codigo = str(venta["codigo"])
        cantidad = int(venta["cantidad"])
        fecha = venta.get("fecha", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        exito = registrar_venta(codigo, cantidad)
        if exito:
            print(
                f"✅ Venta registrada: {cantidad} unidades de '{codigo}' desde API TPV"
            )
        else:
            motivo = "Artículo inexistente o stock insuficiente"
            print(f"⚠️ Venta ignorada: {cantidad} unidades de '{codigo}' -> {motivo}")
            registrar_error(codigo, cantidad, fecha, motivo)


def sincronizar_desde_sql(conn_str, tabla_ventas, fecha_desde=None):
    """Sincroniza ventas desde base de datos SQL TPV"""
    if not SQL_ENABLED:
        print("⚠️ pyodbc no está instalado. No se puede conectar a SQL TPV")
        return

    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        query = f"SELECT codigo, cantidad, fecha FROM {tabla_ventas}"
        if fecha_desde:
            query += f" WHERE fecha >= '{fecha_desde.strftime('%Y-%m-%d')}'"

        cursor.execute(query)
        for codigo, cantidad, fecha in cursor.fetchall():
            exito = registrar_venta(str(codigo), int(cantidad))
            if exito:
                print(
                    f"✅ Venta registrada: {cantidad} unidades de '{codigo}' desde SQL TPV"
                )
            else:
                motivo = "Artículo inexistente o stock insuficiente"
                print(
                    f"⚠️ Venta ignorada: {cantidad} unidades de '{codigo}' -> {motivo}"
                )
                registrar_error(codigo, cantidad, fecha, motivo)
    except Exception as e:
        print(f"❌ Error al consultar SQL: {e}")
    finally:
        conn.close()


# -----------------------------
# MONITOR DE ARCHIVOS EN TIEMPO REAL
# -----------------------------
if WATCHDOG_ENABLED:

    class VentasHandler(FileSystemEventHandler):
        def __init__(self, archivo):
            self.archivo = archivo

        def on_modified(self, event):
            if event.src_path.endswith(self.archivo):
                print("📄 Cambios detectados en archivo, sincronizando...")
                sincronizar_desde_archivo(self.archivo)

    def modo_monitor(archivo, directorio="."):
        event_handler = VentasHandler(archivo)
        observer = Observer()
        observer.schedule(event_handler, path=directorio, recursive=False)
        observer.start()
        print("👀 Monitorizando ventas en tiempo real. Presiona Ctrl+C para salir.")
        try:
            import time

            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            print("🛑 Monitor detenido.")
        observer.join()


# -----------------------------
# SINCRONIZACIÓN EN PARALELO
# -----------------------------
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
    """
    Sincroniza archivo, API y SQL en paralelo usando hilos
    """
    crear_tabla_errores()
    ultima_fecha_api = datetime.now() - timedelta(days=1)
    ultima_fecha_sql = datetime.now() - timedelta(days=1)

    threads = []

    # Hilo archivo
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

    # Hilo API
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

    # Hilo SQL
    if SQL_ENABLED and conn_str_sql and tabla_sql:

        def sql_loop():
            nonlocal ultima_fecha_sql
            while True:
                sincronizar_desde_sql(
                    conn_str_sql, tabla_sql, fecha_desde=ultima_fecha_sql
                )
                ultima_fecha_sql = datetime.now()
                sleep(intervalo_sql)

        t_sql = Thread(target=sql_loop)
        t_sql.daemon = True
        threads.append(t_sql)

    # Iniciar todos los hilos
    for t in threads:
        t.start()

    # Mantener el main thread activo
    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        print("🛑 Sincronización paralela detenida.")
