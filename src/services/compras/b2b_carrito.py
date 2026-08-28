"""
Carrito de la Extranet de Empresa (Smart Suppliers · Fase B). Dos orígenes por línea: 'catalogo'
(añadida buscando en el catálogo B2B) o 'reposicion' (añadida desde "Desde reposición", enlazada a la
propuesta de `reabastecimiento.py` vía `id_reab_propuesta` para poder marcarla "Añadida" sin que
desaparezca de la lista de sugerencias hasta tramitar — requisito de negocio confirmado).
"""

import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("compras.b2b_carrito")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def anadir(token_sesion, *, id_suministrador, codigo, nombre, unidad_medida, cantidad,
          precio_unitario, origen="catalogo", id_reab_propuesta=None) -> dict:
    if int(cantidad) < 1:
        return {"ok": False, "error": "cantidad_debe_ser_mayor_o_igual_a_1"}
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO b2b_carrito_lineas (token_sesion, id_suministrador, codigo, nombre, "
                "unidad_medida, cantidad, precio_unitario, origen, id_reab_propuesta) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (token_sesion, id_suministrador, codigo, nombre, unidad_medida, int(cantidad),
                 float(precio_unitario), origen, id_reab_propuesta))
            id_linea = cur.lastrowid
            conn.commit()
        if origen == "reposicion" and id_reab_propuesta:
            from src.db import reabastecimiento as R
            R.cambiar_estado_propuesta(id_reab_propuesta, "en_carrito")
        return {"ok": True, "id_linea": id_linea}
    except Exception as e:
        logger.error("anadir(%s,%s): %s", token_sesion, codigo, e)
        return {"ok": False, "error": "error_interno"}


def listar(token_sesion) -> list[dict]:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM b2b_carrito_lineas WHERE token_sesion=%s ORDER BY creado_en",
                        (token_sesion,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar(%s): %s", token_sesion, e)
        return []


def quitar_linea(token_sesion, id_linea) -> bool:
    """Quita una línea. Si venía de 'Desde reposición', la propuesta vuelve a 'pendiente' (deja de
    estar "Añadida" en la lista de sugerencias)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT origen, id_reab_propuesta FROM b2b_carrito_lineas "
                        "WHERE id=%s AND token_sesion=%s", (id_linea, token_sesion))
            row = cur.fetchone()
            info = _fila(cur, row) if row else None
            cur.execute("DELETE FROM b2b_carrito_lineas WHERE id=%s AND token_sesion=%s",
                        (id_linea, token_sesion))
            ok = cur.rowcount > 0
            conn.commit()
        if ok and info and info.get("origen") == "reposicion" and info.get("id_reab_propuesta"):
            from src.db import reabastecimiento as R
            R.cambiar_estado_propuesta(info["id_reab_propuesta"], "pendiente")
        return ok
    except Exception as e:
        logger.error("quitar_linea(%s,%s): %s", token_sesion, id_linea, e)
        return False


def vaciar(token_sesion) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM b2b_carrito_lineas WHERE token_sesion=%s", (token_sesion,))
            conn.commit()
        return True
    except Exception as e:
        logger.error("vaciar(%s): %s", token_sesion, e)
        return False


def total(token_sesion) -> float:
    return round(sum(float(x["cantidad"]) * float(x["precio_unitario"]) for x in listar(token_sesion)), 2)
