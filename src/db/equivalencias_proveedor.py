"""
Equivalencia/mapeo REFERENCIA DEL PROVEEDOR <-> ARTÍCULO INTERNO (migración 0316).

Petición explícita: tabla de equivalencias soportando un número ilimitado de referencias de
proveedor por EAN interno, con un mecanismo de seguridad REVERSIBLE para poder deshacer cualquier
equivalencia en cualquier etapa del proceso. No duplica ninguna tabla existente — es la primera
vez que este mapeo se modela en el ERP (confirmado por auditoría previa).

Flujo de uso:
  - Al dar de alta un artículo desde el Portal Empresa con una referencia de proveedor asociada
    (`portal_empresa_gestion.py`), se llama a `crear_equivalencia`.
  - Al escanear en recepción logística (`db/logistica.py`) un código que no existe como
    `articulos.codigo`, se intenta `resolver_por_referencia` antes de darlo por no encontrado.
  - `deshacer_equivalencia`/`reactivar_equivalencia` implementan el "undo" reversible pedido.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("equivalencias_proveedor")

ORIGENES = ("clasico", "b2b")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id() or EMPRESA_DEFAULT_ID
    except Exception:
        return EMPRESA_DEFAULT_ID


def crear_equivalencia(referencia_proveedor, codigo_articulo, *, id_proveedor=None,
                       origen_proveedor="clasico", nombre_proveedor=None, creado_por=None,
                       id_empresa=None) -> dict:
    """Crea (o REACTIVA si existía y estaba deshecha) la equivalencia referencia->código interno.
    Si la MISMA referencia de proveedor ya apuntaba a OTRO artículo, se actualiza para apuntar al
    nuevo (nunca queda una referencia apuntando a dos sitios a la vez)."""
    referencia_proveedor = str(referencia_proveedor or "").strip()
    codigo_articulo = str(codigo_articulo or "").strip().upper()
    if not referencia_proveedor or not codigo_articulo:
        return {"ok": False, "error": "datos_incompletos"}
    id_empresa = _emp(id_empresa)
    origen_proveedor = origen_proveedor if origen_proveedor in ORIGENES else "clasico"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM equivalencias_referencia_proveedor "
                "WHERE id_empresa=%s AND referencia_proveedor=%s AND "
                "(id_proveedor=%s OR (id_proveedor IS NULL AND %s IS NULL))",
                (id_empresa, referencia_proveedor, id_proveedor, id_proveedor))
            fila = cur.fetchone()
            if fila:
                id_fila = fila[0] if not isinstance(fila, dict) else fila["id"]
                cur.execute(
                    "UPDATE equivalencias_referencia_proveedor SET codigo_articulo=%s, "
                    "estado='activa', nombre_proveedor=COALESCE(%s, nombre_proveedor), "
                    "creado_por=COALESCE(%s, creado_por) WHERE id=%s",
                    (codigo_articulo, nombre_proveedor, creado_por, id_fila))
                conn.commit()
                return {"ok": True, "id": id_fila, "reactivada": True}
            cur.execute(
                "INSERT INTO equivalencias_referencia_proveedor "
                "(id_empresa, id_proveedor, origen_proveedor, nombre_proveedor, "
                " referencia_proveedor, codigo_articulo, estado, creado_por) "
                "VALUES (%s,%s,%s,%s,%s,%s,'activa',%s)",
                (id_empresa, id_proveedor, origen_proveedor, nombre_proveedor,
                 referencia_proveedor, codigo_articulo, creado_por))
            conn.commit()
            return {"ok": True, "id": cur.lastrowid, "reactivada": False}
    except Exception as e:
        logger.error("crear_equivalencia(%s -> %s): %s", referencia_proveedor, codigo_articulo, e)
        return {"ok": False, "error": "error_interno"}


def resolver_por_referencia(referencia_proveedor, *, id_proveedor=None, id_empresa=None) -> str | None:
    """Devuelve el código interno equivalente a `referencia_proveedor`, o None si no hay ninguna
    equivalencia ACTIVA registrada. Si se indica `id_proveedor`, se prioriza la equivalencia de
    ESE proveedor; si no se indica, se busca entre cualquier proveedor (una referencia puede
    coincidir por casualidad entre proveedores distintos, así que se prioriza la más reciente)."""
    referencia_proveedor = str(referencia_proveedor or "").strip()
    if not referencia_proveedor:
        return None
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if id_proveedor is not None:
                cur.execute(
                    "SELECT codigo_articulo FROM equivalencias_referencia_proveedor "
                    "WHERE id_empresa=%s AND referencia_proveedor=%s AND id_proveedor=%s "
                    "AND estado='activa' LIMIT 1",
                    (id_empresa, referencia_proveedor, id_proveedor))
                fila = cur.fetchone()
                if fila:
                    return fila[0] if not isinstance(fila, dict) else fila["codigo_articulo"]
            cur.execute(
                "SELECT codigo_articulo FROM equivalencias_referencia_proveedor "
                "WHERE id_empresa=%s AND referencia_proveedor=%s AND estado='activa' "
                "ORDER BY fecha_actualizacion DESC LIMIT 1",
                (id_empresa, referencia_proveedor))
            fila = cur.fetchone()
            return (fila[0] if not isinstance(fila, dict) else fila["codigo_articulo"]) if fila else None
    except Exception as e:
        logger.error("resolver_por_referencia(%s): %s", referencia_proveedor, e)
        return None


def listar_equivalencias_de_articulo(codigo_articulo, *, id_empresa=None, incluir_deshechas=False) -> list:
    """Todas las referencias de proveedor equivalentes a un artículo interno (para mostrarlas en
    su ficha / permitir deshacerlas una a una)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            query = ("SELECT id, id_proveedor, origen_proveedor, nombre_proveedor, "
                     "referencia_proveedor, estado, fecha_creacion FROM "
                     "equivalencias_referencia_proveedor WHERE id_empresa=%s AND codigo_articulo=%s")
            params = [id_empresa, str(codigo_articulo or "").strip().upper()]
            if not incluir_deshechas:
                query += " AND estado='activa'"
            query += " ORDER BY fecha_creacion DESC"
            cur.execute(query, tuple(params))
            cols = [d[0] for d in cur.description]
            filas = cur.fetchall()
            return [dict(zip(cols, f)) if not isinstance(f, dict) else f for f in filas]
    except Exception as e:
        logger.error("listar_equivalencias_de_articulo(%s): %s", codigo_articulo, e)
        return []


def buscar_unificado(query, *, id_empresa=None, sector_ids=None, limite=30) -> list[dict]:
    """Búsqueda unificada "Buscar artículo" (petición explícita, revisada): SOLO el catálogo
    INTERNO de la empresa (`articulos`) — las referencias de proveedor dejan de listarse como
    filas sueltas (ya no se consulta `b2b_catalogo`/`suministradores` aquí; ese universo de
    "productos del proveedor aún no vinculados" sigue existiendo para la detección de duplicados
    en pedidos, `portal_empresa_b2b.py::pagina_confirmar_duplicado`, sin relación con esta
    búsqueda). En su lugar, cada artículo trae sus propias `equivalencias` (activas, más reciente
    primero vía `listar_equivalencias_de_articulo`) para que la UI pueda mostrarlas TODAS cuando
    hay dos o más — ninguna equivalencia activa deja de ser válida al añadirse una nueva, así que
    se listan todas juntas, resaltando la más reciente. `sector_ids` se conserva por compatibilidad
    de firma, sin uso (ya no hay búsqueda de catálogo de proveedor aquí)."""
    query = (query or "").strip()
    if not query:
        return []
    id_empresa = _emp(id_empresa)
    resultados = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT codigo, nombre, precio, marca, seccion, es_complementario, es_promocional "
                "FROM articulos WHERE id_empresa=%s AND (codigo LIKE %s OR nombre LIKE %s) LIMIT %s",
                (id_empresa, f"%{query}%", f"%{query}%", limite))
            cols = [d[0] for d in cur.description]
            for fila in cur.fetchall():
                d = dict(zip(cols, fila)) if not isinstance(fila, dict) else fila
                d["origen"] = "empresa"
                d["equivalencias"] = listar_equivalencias_de_articulo(d["codigo"], id_empresa=id_empresa)
                resultados.append(d)
    except Exception as e:
        logger.error("buscar_unificado (empresa, %s): %s", query, e)

    return resultados


def deshacer_equivalencia(id_equivalencia, *, id_empresa=None) -> bool:
    """Deshace (desactiva) una equivalencia — mecanismo de seguridad REVERSIBLE pedido
    explícitamente. NUNCA borra la fila: solo pasa a estado='deshecha', conservando el historial
    para poder reactivarla (`reactivar_equivalencia`) si fue un error."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE equivalencias_referencia_proveedor SET estado='deshecha' "
                "WHERE id=%s AND id_empresa=%s", (id_equivalencia, id_empresa))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("deshacer_equivalencia(%s): %s", id_equivalencia, e)
        return False


def reactivar_equivalencia(id_equivalencia, *, id_empresa=None) -> bool:
    """Reactiva una equivalencia previamente deshecha."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE equivalencias_referencia_proveedor SET estado='activa' "
                "WHERE id=%s AND id_empresa=%s", (id_equivalencia, id_empresa))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("reactivar_equivalencia(%s): %s", id_equivalencia, e)
        return False
