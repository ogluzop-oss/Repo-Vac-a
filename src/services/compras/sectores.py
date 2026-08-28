"""
Sectores comerciales (Smart Suppliers · Fase A). Catálogo GLOBAL (no multiempresa: "Alimentación",
"Electrónica"... son taxonomía de plataforma, no datos de un tenant) + grafo de compatibilidad, usado
para el match Empresa↔Proveedor del catálogo B2B: una empresa de un sector solo debe ver proveedores
de su mismo sector o de un sector marcado explícitamente como compatible (evita cruces como un
proveedor de "Harinas" apareciendo en el portal de una empresa de "Electrónica").
"""

import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("compras.sectores")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def listar(*, solo_activos=True) -> list[dict]:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = "SELECT * FROM sectores_comerciales"
            if solo_activos:
                q += " WHERE activo=1"
            q += " ORDER BY nombre"
            cur.execute(q)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar: %s", e)
        return []


def obtener(sector_id) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM sectores_comerciales WHERE id=%s", (sector_id,))
            row = cur.fetchone()
            return _fila(cur, row) if row else None
    except Exception as e:
        logger.error("obtener(%s): %s", sector_id, e)
        return None


def crear(codigo: str, nombre: str) -> int | None:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO sectores_comerciales (codigo, nombre) VALUES (%s,%s)",
                        (codigo.strip().lower(), nombre.strip()))
            sid = cur.lastrowid
            conn.commit()
            return sid
    except Exception as e:
        logger.error("crear(%s): %s", codigo, e)
        return None


def marcar_compatibles(sector_id, sector_compatible_id) -> bool:
    """Marca dos sectores como compatibles. La relación es SIMÉTRICA (se guardan ambos sentidos) para
    que el match funcione consultando solo `sector_id` desde cualquiera de los dos lados."""
    if int(sector_id) == int(sector_compatible_id):
        return True  # un sector siempre es compatible consigo mismo (implícito, no hace falta fila)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT IGNORE INTO sectores_compatibles (sector_id, sector_compatible_id) "
                        "VALUES (%s,%s)", (sector_id, sector_compatible_id))
            cur.execute("INSERT IGNORE INTO sectores_compatibles (sector_id, sector_compatible_id) "
                        "VALUES (%s,%s)", (sector_compatible_id, sector_id))
            conn.commit()
        return True
    except Exception as e:
        logger.error("marcar_compatibles(%s,%s): %s", sector_id, sector_compatible_id, e)
        return False


def compatibles_de(sector_id) -> set:
    """IDs de sector que hacen match con `sector_id` (incluye el propio)."""
    if not sector_id:
        return set()
    out = {int(sector_id)}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT sector_compatible_id FROM sectores_compatibles WHERE sector_id=%s",
                        (sector_id,))
            for r in cur.fetchall():
                v = r[0] if not isinstance(r, dict) else r["sector_compatible_id"]
                out.add(int(v))
    except Exception as e:
        logger.error("compatibles_de(%s): %s", sector_id, e)
    return out


def son_compatibles(sector_a, sector_b) -> bool:
    if not sector_a or not sector_b:
        return False
    return int(sector_b) in compatibles_de(sector_a)
