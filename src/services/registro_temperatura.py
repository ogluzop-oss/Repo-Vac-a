"""
Registro de temperaturas por tienda — control de cadena de frío (neveras/cámaras/congeladores),
registrado in situ por el personal OPERARIO/ADMINISTRADOR de cada tienda.

Distinto de la TAREA "revisar temperaturas" que un SUPERADMIN pueda programar en
`services.tareas_empleados`: aquello es solo el recordatorio; esto es la lectura real que el empleado
anota al hacer la comprobación.
"""

import logging

from src.db.conexion import obtener_conexion, transaccion

logger = logging.getLogger("services.registro_temperatura")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def registrar(id_tienda, equipo, valor, *, usuario=None, observaciones=None, id_empresa=None) -> dict:
    if not id_tienda:
        return {"ok": False, "error": "No hay tienda asociada a tu usuario."}
    equipo = (equipo or "").strip()
    if not equipo:
        return {"ok": False, "error": "Indica qué equipo has medido (nevera, cámara, congelador...)."}
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        return {"ok": False, "error": "El valor de temperatura no es válido."}
    eid = _emp(id_empresa)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO registros_temperatura (id_empresa, id_tienda, equipo, valor, "
                "observaciones, usuario) VALUES (%s,%s,%s,%s,%s,%s)",
                (eid, id_tienda, equipo, valor, (observaciones or "").strip() or None, usuario))
            rid = cur.lastrowid
        return {"ok": True, "id": rid}
    except Exception as e:
        logger.error("registrar: %s", e)
        return {"ok": False, "error": str(e)}


def listar(id_tienda, *, id_empresa=None, limite=50) -> list:
    if not id_tienda:
        return []
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, equipo, valor, observaciones, usuario, fecha_registro FROM "
                "registros_temperatura WHERE id_empresa=%s AND id_tienda=%s "
                "ORDER BY fecha_registro DESC LIMIT %s", (eid, id_tienda, int(limite)))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar: %s", e)
        return []
