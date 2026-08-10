"""
Conector DIRECTO al origen (Fase 4): base de datos del ERP de origen (ODBC / SQLAlchemy) o API REST. DEGRADABLE:
requiere el driver correspondiente; si falta, error honesto. Devuelve filas (list[dict]) que alimentan el MISMO
pipeline (`motor.analizar_filas`/`simular_filas`/`ejecutar_filas`). Reutiliza drivers presentes; sin motor nuevo.
SOLO LECTURA del origen.
"""

import logging

logger = logging.getLogger("importacion.conector")


def _dicts(cur) -> list:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) if not isinstance(r, dict) else r for r in cur.fetchall()]


def leer_consulta(query, *, conexion=None, url=None, limite=None) -> list:
    """Ejecuta un SELECT en la BD de ORIGEN. `conexion` = conexión DBAPI ya abierta (pymysql/pyodbc/…); o `url`
    = cadena SQLAlchemy (mysql+pymysql://…, mssql+pyodbc://…, postgresql://…). Devuelve list[dict]."""
    if conexion is not None:
        with conexion.cursor() as cur:
            cur.execute(query)
            filas = _dicts(cur)
    elif url:
        from sqlalchemy import create_engine, text
        eng = create_engine(url)
        try:
            with eng.connect() as c:
                res = c.execute(text(query))
                claves = list(res.keys())
                filas = [dict(zip(claves, row)) for row in res]
        finally:
            eng.dispose()
    else:
        raise ValueError("Indica `conexion` (DBAPI) o `url` (SQLAlchemy) del origen.")
    return filas[:limite] if limite else filas


def leer_odbc(dsn, query, *, limite=None) -> list:
    """Lee vía ODBC (pyodbc). DEGRADABLE: sin el driver 'pyodbc' → RuntimeError honesto."""
    try:
        import pyodbc
    except Exception as e:
        raise RuntimeError("Falta el driver ODBC ('pyodbc') para el conector directo.") from e
    conn = pyodbc.connect(dsn)
    try:
        return leer_consulta(query, conexion=conn, limite=limite)
    finally:
        conn.close()


def _extraer_lista(data) -> list:
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        for v in data.values():                     # {"data":[...]} / {"productos":[...]}
            if isinstance(v, list):
                return [d for d in v if isinstance(d, dict)]
        return [data]
    return []


def leer_api(url, *, fetch=None, limite=None) -> list:
    """Lee filas de una API REST que devuelve JSON. `fetch(url) -> obj` es inyectable (por defecto usa
    `requests.get(url).json()`), lo que permite probar sin red y soportar autenticación propia."""
    if fetch is None:
        def fetch(u):
            import requests
            r = requests.get(u, timeout=30)
            r.raise_for_status()
            return r.json()
    filas = _extraer_lista(fetch(url))
    return filas[:limite] if limite else filas
