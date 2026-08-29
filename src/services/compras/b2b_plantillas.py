"""
Plantillas de aprovisionamiento recurrente (Smart Suppliers B2B · Fase 3). Guarda el carrito B2B
actual como plantilla nombrada; al reenviarla al carrito, el precio de cada línea se RE-RESUELVE contra
el catálogo vivo (nunca se reintroduce un precio guardado/obsoleto) vía `b2b_catalogo.precio_para_cantidad`.
"""

import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("compras.b2b_plantillas")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def guardar_desde_carrito(id_empresa, nombre: str, token_sesion) -> dict:
    """Crea una plantilla con las líneas actuales del carrito (código/nombre/unidad/cantidad; sin
    precio). Falla explícitamente si el carrito está vacío o el nombre viene vacío."""
    from src.services.compras import b2b_carrito

    nombre = (nombre or "").strip()
    if not nombre:
        return {"ok": False, "error": "nombre_obligatorio"}
    lineas = b2b_carrito.listar(token_sesion)
    if not lineas:
        return {"ok": False, "error": "carrito_vacio"}
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO b2b_plantillas (id_empresa, nombre) VALUES (%s,%s)",
                        (id_empresa, nombre))
            id_plantilla = cur.lastrowid
            for ln in lineas:
                cur.execute(
                    "INSERT INTO b2b_plantilla_lineas (id_plantilla, id_suministrador, codigo, "
                    "nombre, unidad_medida, cantidad) VALUES (%s,%s,%s,%s,%s,%s)",
                    (id_plantilla, ln["id_suministrador"], ln["codigo"], ln["nombre"],
                     ln["unidad_medida"], int(ln["cantidad"])))
            conn.commit()
        return {"ok": True, "id_plantilla": id_plantilla}
    except Exception as e:
        logger.error("guardar_desde_carrito(%s): %s", id_empresa, e)
        return {"ok": False, "error": "error_interno"}


def listar(id_empresa) -> list[dict]:
    """Plantillas de la empresa con el nº de líneas guardadas, más recientes primero."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT p.id, p.nombre, p.creado_en, COUNT(l.id) AS n_lineas "
                "FROM b2b_plantillas p LEFT JOIN b2b_plantilla_lineas l ON l.id_plantilla = p.id "
                "WHERE p.id_empresa=%s GROUP BY p.id, p.nombre, p.creado_en "
                "ORDER BY p.creado_en DESC", (id_empresa,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar(%s): %s", id_empresa, e)
        return []


def eliminar(id_empresa, id_plantilla) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM b2b_plantillas WHERE id=%s AND id_empresa=%s",
                        (id_plantilla, id_empresa))
            if not cur.fetchone():
                return False
            cur.execute("DELETE FROM b2b_plantilla_lineas WHERE id_plantilla=%s", (id_plantilla,))
            cur.execute("DELETE FROM b2b_plantillas WHERE id=%s AND id_empresa=%s",
                        (id_plantilla, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("eliminar(%s,%s): %s", id_empresa, id_plantilla, e)
        return False


def enviar_a_carrito(token_sesion, id_empresa, id_plantilla) -> dict:
    """Reenvía cada línea de la plantilla al carrito activo, re-resolviendo el artículo y su precio
    (por cantidad, con escalones si los hay) contra el catálogo VIVO. Las líneas cuyo artículo ya no
    exista o esté desactivado se omiten y se reportan (no rompen el resto)."""
    from src.services.compras import b2b_carrito, b2b_catalogo as CAT

    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM b2b_plantillas WHERE id=%s AND id_empresa=%s",
                        (id_plantilla, id_empresa))
            if not cur.fetchone():
                return {"ok": False, "error": "plantilla_no_encontrada"}
            cur.execute(
                "SELECT id_suministrador, codigo, cantidad FROM b2b_plantilla_lineas "
                "WHERE id_plantilla=%s", (id_plantilla,))
            lineas = [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("enviar_a_carrito(%s,%s): %s", id_empresa, id_plantilla, e)
        return {"ok": False, "error": "error_interno"}

    anadidas, omitidas = 0, []
    for ln in lineas:
        art = CAT.obtener_activo(ln["id_suministrador"], ln["codigo"])
        if not art:
            omitidas.append(ln["codigo"])
            continue
        cantidad = max(int(ln["cantidad"]), int(art["moq"]))
        precio = CAT.precio_para_cantidad(art, cantidad)
        r = b2b_carrito.anadir(token_sesion, id_suministrador=art["id_suministrador"],
                               codigo=art["codigo"], nombre=art["nombre"],
                               unidad_medida=art["unidad_medida"], cantidad=cantidad,
                               precio_unitario=precio, origen="plantilla")
        if r.get("ok"):
            anadidas += 1
        else:
            omitidas.append(ln["codigo"])
    return {"ok": True, "anadidas": anadidas, "omitidas": omitidas}
