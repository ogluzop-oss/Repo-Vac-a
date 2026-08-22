"""
Accesores canónicos de `articulos`. Tras la PK compuesta (id_empresa, codigo) — migr 0181 — estas lecturas/
escrituras filtran por EMPRESA. Retrocompatibles (Strangler): `id_empresa` es opcional y por defecto se toma de
la sesión (`empresa_actual_id`), de modo que las llamadas existentes quedan correctamente aisladas por tenant
sin cambiarlas. En instalaciones de una sola empresa el comportamiento es idéntico.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("articulos.db")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id() or EMPRESA_DEFAULT_ID
    except Exception:
        return EMPRESA_DEFAULT_ID


# ============================================================
# ALTA DE ARTÍCULOS (Alta Rápida + Generador EAN-13)
# ============================================================
def existe_codigo(codigo, id_empresa=None) -> bool:
    """True si ya existe un artículo con ese código (EAN) en la empresa. Para validar unicidad del EAN."""
    if not codigo:
        return False
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM articulos WHERE codigo=%s AND id_empresa=%s LIMIT 1",
                        (str(codigo), id_empresa))
            return cur.fetchone() is not None
    except Exception as e:
        logger.error("existe_codigo(%s): %s", codigo, e)
        return False


def existe_nombre(nombre, id_empresa=None) -> bool:
    """True si ya existe un artículo con ese nombre (case-insensitive) en la empresa."""
    if not (nombre or "").strip():
        return False
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM articulos WHERE id_empresa=%s AND LOWER(TRIM(nombre))=LOWER(TRIM(%s)) "
                        "LIMIT 1", (id_empresa, nombre))
            return cur.fetchone() is not None
    except Exception as e:
        logger.error("existe_nombre(%s): %s", nombre, e)
        return False


def crear_articulo(codigo, nombre, *, precio=0, categoria=None, id_familia=None, unidad=None,
                   imagen=None, id_empresa=None) -> bool:
    """Alta de un artículo nuevo en el catálogo PERMANENTE `articulos`. `codigo` = EAN-13 generado.
    Queda disponible de inmediato en el buscador de Pedidos/Proveedores. No pisa uno existente."""
    if not codigo or not (nombre or "").strip():
        return False
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO articulos (codigo, id_empresa, nombre, precio, categoria, unidad, imagen, "
                "estado) VALUES (%s,%s,%s,%s,%s,%s,%s,'activo')",
                (str(codigo), id_empresa, nombre.strip(), float(precio or 0), categoria, unidad, imagen))
            conn.commit()
        if id_familia:
            try:
                from src.db import familias
                familias.asignar_familia(str(codigo), id_familia, id_empresa=id_empresa)
            except Exception as e:
                logger.debug("crear_articulo asignar_familia: %s", e)
        return True
    except Exception as e:
        logger.error("crear_articulo(%s): %s", codigo, e)
        return False


# ============================================================
# BLOQUE CONSULTA DE ARTÍCULOS
# ============================================================

def obtener_articulos(id_empresa=None):
    id_empresa = _emp(id_empresa)
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT codigo, nombre, Stock_total, precio, capacidad_lineal, bloqueado, "
            "ultima_recepcion, siguiente_recepcion, ubicacion_tienda FROM articulos WHERE id_empresa=%s",
            (id_empresa,)
        )
        return cursor.fetchall()


# ============================================================
# BLOQUE ACTUALIZACIÓN DE ARTÍCULOS
# ============================================================

def actualizar_precio(codigo, nuevo_precio, id_empresa=None):
    id_empresa = _emp(id_empresa)
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE articulos SET precio=%s WHERE codigo=%s AND id_empresa=%s",
            (nuevo_precio, codigo, id_empresa)
        )
        conn.commit()
    return True


def actualizar_emoji(codigo, emoji, id_empresa=None):
    """Actualiza el emoji representativo del artículo (presentacional, para el TPV táctil)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE articulos SET emoji=%s WHERE codigo=%s AND id_empresa=%s",
                           (emoji or None, codigo, id_empresa))
            conn.commit()
        return True
    except Exception:
        return False


# ============================================================
# FÍSICA DE SEGURIDAD DEL AUTOCOBRO (Capa 1)
# peso_unitario (kg) + tolerancia_peso (kg): master data que alimenta el control antifraude.
# ============================================================

def listar_codigo_nombre(id_empresa=None) -> list:
    """(codigo, nombre) de los artículos, ordenados por nombre. Para combos/sugerencias de la GUI
    (Fase 3 · cliente fino). Devuelve lista de tuplas."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo, nombre FROM articulos WHERE id_empresa=%s ORDER BY nombre",
                        (id_empresa,))
            return [((r["codigo"], r["nombre"]) if isinstance(r, dict) else (r[0], r[1]))
                    for r in cur.fetchall()]
    except Exception:
        return []


def buscar_uno(termino, id_empresa=None):
    """Primer artículo cuyo código coincide o cuyo nombre contiene `termino`. Devuelve
    (codigo, nombre, precio) o None. Fase 3 · cliente fino (extraído de etiquetas_precios)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo, nombre, precio FROM articulos "
                        "WHERE id_empresa=%s AND (codigo=%s OR nombre LIKE %s) LIMIT 1",
                        (id_empresa, termino, f"%{termino}%"))
            r = cur.fetchone()
            if not r:
                return None
            return (r["codigo"], r["nombre"], r["precio"]) if isinstance(r, dict) else (r[0], r[1], r[2])
    except Exception:
        return None


def obtener_imagen(codigo, id_empresa=None):
    """Imagen (BLOB/bytes) del artículo o None. Fase 3 · cliente fino (extraído de info_articulo)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT imagen FROM articulos WHERE codigo=%s AND id_empresa=%s", (codigo, id_empresa))
            r = cur.fetchone()
            if not r:
                return None
            return r["imagen"] if isinstance(r, dict) else r[0]
    except Exception:
        return None


def actualizar_imagen(codigo, imagen, id_empresa=None) -> bool:
    """Fija (o borra, con imagen=None) la imagen del artículo. Fase 3 · cliente fino."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE articulos SET imagen=%s WHERE codigo=%s AND id_empresa=%s",
                        (imagen, codigo, id_empresa))
            conn.commit()
        return True
    except Exception:
        return False


def obtener_stock(codigo, id_empresa=None):
    """Stock desglosado de un artículo → dict {nombre, lineal, almacen, central, esperado} o None.
    Fase 3 · cliente fino (extraído de mostrar_stock)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT nombre, COALESCE(Stock_tienda,0), COALESCE(Stock_total,0), "
                        "COALESCE(Stock_central,0), COALESCE(Stock_esperado,0) "
                        "FROM articulos WHERE codigo=%s AND id_empresa=%s", (codigo, id_empresa))
            row = cur.fetchone()
        if not row:
            return None
        v = list(row.values()) if isinstance(row, dict) else row
        return {"nombre": v[0], "lineal": v[1], "almacen": v[2], "central": v[3], "esperado": v[4]}
    except Exception:
        return None


def buscar_stock(query, id_familia=None, id_empresa=None) -> list:
    """Búsqueda por texto (+ familia opcional; id_familia=0 → sin familia). Devuelve tuplas
    (codigo, nombre, Stock_tienda, Stock_total, Stock_central). Fase 3 · cliente fino."""
    id_empresa = _emp(id_empresa)
    try:
        like = f"%{query}%"
        cond = "id_empresa=%s AND (codigo LIKE %s OR nombre LIKE %s)"
        params = [id_empresa, like, like]
        if id_familia == 0:
            cond += " AND id_familia IS NULL"
        elif id_familia is not None:
            cond += " AND id_familia=%s"
            params.append(id_familia)
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo, nombre, COALESCE(Stock_tienda,0), COALESCE(Stock_total,0), "
                        "COALESCE(Stock_central,0) FROM articulos WHERE " + cond +
                        " ORDER BY nombre ASC LIMIT 200", tuple(params))
            return cur.fetchall()
    except Exception:
        return []


def df_stock_export(id_empresa=None):
    """DataFrame (pandas) con el stock de todos los artículos para EXPORTAR: 6 columnas en orden
    (codigo, nombre, Stock lineal/almacen/central/esperado). La GUI pone las cabeceras traducidas.
    Fase 3 · cliente fino (extraído de mostrar_stock)."""
    import pandas as pd
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn:
            return pd.read_sql_query(
                "SELECT codigo, nombre, COALESCE(Stock_tienda,0), COALESCE(Stock_total,0), "
                "COALESCE(Stock_central,0), COALESCE(Stock_esperado,0) "
                "FROM articulos WHERE id_empresa=%s ORDER BY nombre ASC", conn, params=(id_empresa,))
    except Exception:
        return pd.DataFrame()


def importar_articulos_df(df) -> int:
    """Importa/actualiza artículos desde un DataFrame (columnas ya en minúscula). Crea como TEXT las
    columnas que no existan (import flexible) y hace UPSERT por `codigo`. Devuelve nº de filas.
    Fase 3 · cliente fino: lógica extraída y COMPARTIDA por las GUIs de importación (evita duplicar el
    ALTER dinámico + bulk INSERT en varias ventanas)."""
    if df is None or getattr(df, "empty", True):
        return 0
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='articulos'")
        existentes = {(r[0] if not isinstance(r, dict) else list(r.values())[0]).lower()
                      for r in cur.fetchall()}
        for col in df.columns:
            if col not in existentes:
                cur.execute(f"ALTER TABLE articulos ADD COLUMN `{col}` TEXT")
                existentes.add(col)
        n = 0
        for _, row in df.iterrows():
            cols = list(row.index)
            values = [row[c] for c in cols]
            col_names = ", ".join(f"`{c}`" for c in cols)
            placeholders = ", ".join(["%s"] * len(cols))
            updates = ", ".join(f"`{c}`=VALUES(`{c}`)" for c in cols if c != "codigo")
            cur.execute(f"INSERT INTO articulos ({col_names}) VALUES ({placeholders}) "
                        f"ON DUPLICATE KEY UPDATE {updates}", values)
            n += 1
        conn.commit()
    return n


# ── Reposición (extraído de gui/informe_reposicion — Fase 3 · cliente fino) ──────────────────────────
def asegurar_columna_repuesto() -> None:
    """Crea la columna `repuesto INTEGER DEFAULT 0` en `articulos` si no existe (best-effort)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM articulos LIKE 'repuesto'")
            if not cur.fetchone():
                cur.execute("ALTER TABLE articulos ADD COLUMN repuesto INTEGER DEFAULT 0")
                conn.commit()
    except Exception as e:
        logger.debug("asegurar_columna_repuesto: %s", e)


def listar_para_reposicion(id_empresa=None) -> list:
    """(codigo, nombre, Stock_total, Stock_tienda, Stock_esperado) de todos los artículos, para el
    cálculo de reposición. Devuelve tuplas."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo, nombre, COALESCE(Stock_total,0), COALESCE(Stock_tienda,0), "
                        "COALESCE(Stock_esperado,0) FROM articulos WHERE id_empresa=%s", (id_empresa,))
            return [tuple(r.values()) if isinstance(r, dict) else r for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_para_reposicion: %s", e)
        return []


def buscar_por_nombre(termino, id_empresa=None):
    """Primer artículo cuyo nombre contiene `termino` → dict {codigo, nombre, Stock_esperado} o None."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo, nombre, Stock_esperado FROM articulos "
                        "WHERE id_empresa=%s AND nombre LIKE %s LIMIT 1", (id_empresa, f"%{termino}%"))
            r = cur.fetchone()
            if not r:
                return None
            v = list(r.values()) if isinstance(r, dict) else r
            return {"codigo": v[0], "nombre": v[1], "Stock_esperado": v[2]}
    except Exception:
        return None


def listar_bajo_umbral(id_empresa=None) -> list:
    """(codigo, nombre, Stock_total, Stock_tienda, stock_esperado, capacidad_lineal) por nombre, para
    detectar artículos bajo umbral. Devuelve tuplas."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo, nombre, Stock_total, Stock_tienda, COALESCE(stock_esperado,0), "
                        "capacidad_lineal FROM articulos WHERE id_empresa=%s ORDER BY nombre ASC",
                        (id_empresa,))
            return [tuple(r.values()) if isinstance(r, dict) else r for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_bajo_umbral: %s", e)
        return []


def marcar_repuestos(items, id_empresa=None) -> int:
    """Bulk: fija Stock_tienda (lineal) y Stock_total (almacén). `items` = iterable de
    (codigo, nuevo_lineal, nuevo_almacen). Devuelve nº actualizados. Fase 3 · reposición."""
    id_empresa = _emp(id_empresa)
    n = 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for codigo, nuevo_lineal, nuevo_almacen in items:
                cur.execute("UPDATE articulos SET Stock_tienda=%s, Stock_total=%s "
                            "WHERE codigo=%s AND id_empresa=%s",
                            (nuevo_lineal, nuevo_almacen, codigo, id_empresa))
                n += 1
            conn.commit()
    except Exception as e:
        logger.error("marcar_repuestos: %s", e)
    return n


def marcar_repuesto_exportado(items, id_empresa=None) -> int:
    """Bulk: marca `repuesto=1`, fija Stock_tienda y ultima_recepcion. `items` = iterable de
    (codigo, stock_esperado, fecha). Devuelve nº actualizados. Fase 3 · reposición.
    (Corrige el bug pre-existente de placeholders `?` → `%s`, que hacía que este UPDATE fallara en
    silencio con pymysql y NUNCA persistiera el `repuesto=1`.)"""
    id_empresa = _emp(id_empresa)
    n = 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for codigo, stock_esperado, fecha in items:
                cur.execute("UPDATE articulos SET repuesto=1, Stock_tienda=%s, ultima_recepcion=%s "
                            "WHERE codigo=%s AND id_empresa=%s",
                            (stock_esperado, fecha, codigo, id_empresa))
                n += 1
            conn.commit()
    except Exception as e:
        logger.error("marcar_repuesto_exportado: %s", e)
    return n


def obtener_fisica_seguridad(codigo, id_empresa=None):
    """Devuelve {'peso_unitario': float|None, 'tolerancia_peso': float|None} del artículo (o None)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn:
            cur = conn.cursor()
            cur.execute("SELECT peso_unitario, tolerancia_peso FROM articulos WHERE codigo=%s AND id_empresa=%s",
                        (codigo, id_empresa))
            row = cur.fetchone()
            if not row:
                return None
            pu = float(row[0]) if row[0] is not None else None
            tp = float(row[1]) if row[1] is not None else None
            return {"peso_unitario": pu, "tolerancia_peso": tp}
    except Exception:
        return None


def guardar_fisica_seguridad(codigo, peso_unitario=None, tolerancia_peso=None, id_empresa=None):
    """Actualiza el peso esperado y la tolerancia del artículo (kg). Valores None/<=0 → NULL (usa
    los valores por defecto del motor). Devuelve (ok, mensaje)."""
    id_empresa = _emp(id_empresa)

    def _norm(v):
        try:
            v = float(str(v).replace(",", "."))   # tolera coma decimal
            return v if v > 0 else None
        except (TypeError, ValueError):
            return None
    pu, tp = _norm(peso_unitario), _norm(tolerancia_peso)
    try:
        with obtener_conexion() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM articulos WHERE codigo=%s AND id_empresa=%s", (codigo, id_empresa))
            if not cur.fetchone():
                return False, "Artículo no encontrado."
            cur.execute(
                "UPDATE articulos SET peso_unitario=%s, tolerancia_peso=%s WHERE codigo=%s AND id_empresa=%s",
                (pu, tp, codigo, id_empresa))
            conn.commit()
        return True, "Física de seguridad actualizada."
    except Exception as e:
        return False, f"Error al guardar: {e}"
