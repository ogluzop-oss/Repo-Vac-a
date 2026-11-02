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
                   imagen=None, marca=None, seccion=None, es_complementario=False,
                   es_promocional=False, id_empresa=None) -> bool:
    """Alta de un artículo nuevo en el catálogo PERMANENTE `articulos`. `codigo` = EAN-13 generado.
    Queda disponible de inmediato en el buscador de Pedidos/Proveedores. No pisa uno existente.

    `marca`/`seccion` (migración 0317 / columna `seccion` ya existente): opcionales, usados por la
    detección de duplicados (Nombre+Talla+Marca+Color) y por el reetiquetado automático (etiqueta
    = ref. interna + PVP + sección) del Alta artículo del Portal Empresa.

    `es_complementario`/`es_promocional` (migración 0320, petición explícita): marcan el artículo
    para que sus ventas por TPV cuenten como "venta cruzada"/"venta promocional" en el Resumen de
    Ventas (`db.ventas_analitica.resumen_periodo`) — no cambian nada del flujo de venta en sí."""
    if not codigo or not (nombre or "").strip():
        return False
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO articulos (codigo, id_empresa, nombre, precio, categoria, unidad, imagen, "
                "marca, seccion, es_complementario, es_promocional, estado) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'activo')",
                (str(codigo), id_empresa, nombre.strip(), float(precio or 0), categoria, unidad, imagen,
                 marca, seccion, bool(es_complementario), bool(es_promocional)))
            conn.commit()
        if id_familia:
            try:
                from src.db import familias
                familias.asignar_familia(str(codigo), id_familia, id_empresa=id_empresa)
            except Exception as e:
                logger.debug("crear_articulo asignar_familia: %s", e)
        # Fase 1 (motor de eventos): publicacion OBSERVACIONAL, aditiva y bulletproof.
        try:
            from src.services import eventos as _EV
            _EV.publicar("ARTICULO_CREADO", id_empresa=id_empresa, origen="catalogo",
                         ref_entidad="articulo", ref_id=str(codigo),
                         payload={"nombre": nombre.strip()})
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error("crear_articulo(%s): %s", codigo, e)
        return False


def actualizar_articulo(codigo, id_empresa=None, **campos) -> bool:
    """Actualiza campos de un artículo YA EXISTENTE (solo los indicados). Mismo patrón que
    `db.proveedores.actualizar_proveedor`/`db.clientes.actualizar_cliente`: whitelist de columnas +
    UPDATE dinámico. `id_familia` se gestiona aparte vía `familias.asignar_familia` (mismo camino que
    ya usa `crear_articulo`), no como columna directa del UPDATE, para no duplicar esa lógica.

    `promo_activa`/`precio_promo` (Catálogo Web, Fase 1 PIM): estas DOS columnas ya existían en
    `articulos` y ya las LEÍA `services.catalogo.service._precio_efectivo` (precio tachado/real de
    cara al cliente) y `services.esl.sync` (etiquetas electrónicas) — pero ninguna pantalla las
    escribía todavía. Es el "Precio de comparación" que pedía el encargo de e-commerce: se expone
    aquí (reutilizando este mismo UPDATE genérico) en vez de añadir una columna nueva
    `precio_comparacion` en `catalogo_productos`, que habría duplicado exactamente este mecanismo."""
    permitidos = ("nombre", "descripcion", "precio", "categoria", "unidad", "imagen",
                 "promo_activa", "precio_promo", "marca", "seccion",
                 "es_complementario", "es_promocional")
    id_familia = campos.pop("id_familia", "__sin_tocar__")
    sets = {k: campos[k] for k in permitidos if k in campos}
    if not codigo:
        return False
    id_empresa = _emp(id_empresa)
    ok = True
    if sets:
        cols = ", ".join(f"{k}=%s" for k in sets)
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute(f"UPDATE articulos SET {cols} WHERE codigo=%s AND id_empresa=%s",
                            (*sets.values(), str(codigo), id_empresa))
                ok = cur.rowcount > 0
                conn.commit()
        except Exception as e:
            logger.error("actualizar_articulo(%s): %s", codigo, e)
            return False
    if id_familia != "__sin_tocar__":
        try:
            from src.db import familias
            familias.asignar_familia(str(codigo), id_familia, id_empresa=id_empresa)
        except Exception as e:
            logger.debug("actualizar_articulo asignar_familia: %s", e)
    if not sets and id_familia == "__sin_tocar__":
        return False
    try:
        from src.services import eventos as _EV
        _EV.publicar("ARTICULO_MODIFICADO", id_empresa=id_empresa, origen="catalogo",
                     ref_entidad="articulo", ref_id=str(codigo), payload={"campos": list(sets)})
    except Exception:
        pass
    return ok


# Mensaje ESTÁNDAR de toda la app para una referencia/código escaneado o tecleado que no existe
# en el sistema (petición explícita: un único texto reutilizado en todos los puntos de búsqueda,
# no un mensaje distinto por pantalla).
MENSAJE_CODIGO_NO_EXISTE = "Este código de artículo no existe en el sistema"


def detectar_posible_duplicado(nombre, *, talla=None, marca=None, color=None, id_empresa=None) -> dict | None:
    """Detección de duplicados antes de tramitar un pedido a proveedor (petición explícita):
    coincidencia EXACTA simultánea de Nombre + Talla + Marca + Color (los parámetros que no se
    indiquen —p. ej. un proveedor agrícola sin talla/color— simplemente no se exigen). Devuelve
    el artículo interno coincidente (dict con codigo/nombre/marca) o None si no hay ninguno.

    Talla/Color se leen de `producto_variantes` (el único sitio donde ya se modelan, módulo
    Textil) vía un LEFT JOIN — un artículo sin variantes nunca sale en esa combinación si se exige
    talla/color, lo cual es correcto: no se puede afirmar una coincidencia de talla/color sobre un
    artículo que no las tiene registradas."""
    nombre = (nombre or "").strip()
    if not nombre:
        return None
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            condiciones = ["a.id_empresa=%s", "LOWER(TRIM(a.nombre))=LOWER(TRIM(%s))"]
            params = [id_empresa, nombre]
            join = ""
            if talla or color:
                join = ("LEFT JOIN producto_variantes v ON v.id_empresa=a.id_empresa "
                       "AND v.codigo_variante=a.codigo")
                if talla:
                    condiciones.append("LOWER(TRIM(v.talla))=LOWER(TRIM(%s))")
                    params.append(talla)
                if color:
                    condiciones.append("LOWER(TRIM(v.color))=LOWER(TRIM(%s))")
                    params.append(color)
            if marca:
                condiciones.append("LOWER(TRIM(COALESCE(a.marca,'')))=LOWER(TRIM(%s))")
                params.append(marca)
            query = (f"SELECT a.codigo, a.nombre, a.marca FROM articulos a {join} "
                    f"WHERE {' AND '.join(condiciones)} LIMIT 1")
            cur.execute(query, tuple(params))
            fila = cur.fetchone()
            if not fila:
                return None
            if isinstance(fila, dict):
                return fila
            return {"codigo": fila[0], "nombre": fila[1], "marca": fila[2]}
    except Exception as e:
        logger.error("detectar_posible_duplicado(%s): %s", nombre, e)
        return None


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


def ficha_rfid(codigo, id_empresa=None) -> dict | None:
    """Ficha compacta de un artículo para el asistente de vinculación RFID (Paso 1: selección de
    artículo): nombre, categoría, precio y stock total en una sola consulta. None si no existe."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT codigo, nombre, categoria, precio, COALESCE(Stock_total,0), imagen "
                "FROM articulos WHERE codigo=%s AND id_empresa=%s", (str(codigo), id_empresa))
            r = cur.fetchone()
            if not r:
                return None
            v = list(r.values()) if isinstance(r, dict) else r
            return {"codigo": v[0], "nombre": v[1], "categoria": v[2], "precio": v[3],
                   "stock_total": v[4], "imagen": v[5]}
    except Exception as e:
        logger.error("ficha_rfid(%s): %s", codigo, e)
        return None


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


def marcar_stock_esperado(items, id_empresa=None) -> int:
    """Bulk: fija SOLO `Stock_esperado` (umbral mínimo de reposición). `items` = iterable de
    (codigo, nuevo_stock_esperado). Devuelve nº actualizados.

    A propósito NO reutiliza `marcar_repuesto_exportado` (bulk, pero marca además `repuesto=1` y
    `ultima_recepcion` — efectos secundarios del flujo de recepción de pedidos a reposición, no
    deseados en una importación de datos plana) ni `conexion.set_stock_esperado` (un único artículo,
    sin `id_empresa` — sin aislamiento por tenant). Fase migración centralizada (Catálogo Web)."""
    id_empresa = _emp(id_empresa)
    n = 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for codigo, nuevo_esperado in items:
                cur.execute("UPDATE articulos SET Stock_esperado=%s WHERE codigo=%s AND id_empresa=%s",
                            (nuevo_esperado, codigo, id_empresa))
                n += 1
            conn.commit()
    except Exception as e:
        logger.error("marcar_stock_esperado: %s", e)
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


def actualizar_requiere_lote(codigo, requiere_lote, id_empresa=None):
    """Activa/desactiva la trazabilidad por lote obligatoria del artículo (migr. 0259). Cuando
    está activo, la recepción (Logística/palés) exige lote+caducidad en vez de ofrecerlos como
    opcionales. Mismo patrón que `guardar_fisica_seguridad`: valida existencia, UPDATE simple,
    devuelve (ok, mensaje)."""
    id_empresa = _emp(id_empresa)
    val = 1 if requiere_lote else 0
    try:
        with obtener_conexion() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM articulos WHERE codigo=%s AND id_empresa=%s", (codigo, id_empresa))
            if not cur.fetchone():
                return False, "Artículo no encontrado."
            cur.execute("UPDATE articulos SET requiere_lote=%s WHERE codigo=%s AND id_empresa=%s",
                        (val, codigo, id_empresa))
            conn.commit()
        return True, "Trazabilidad por lote actualizada."
    except Exception as e:
        return False, f"Error al guardar: {e}"
