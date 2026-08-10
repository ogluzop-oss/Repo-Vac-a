"""
Busqueda global de actividad (Paquete Enterprise 2, SUBFASE 2.5). Localiza por numero de
factura, cliente, articulo, usuario, pedido, evento, UUID, terminal o hash — todo sobre la cola
de eventos existente (uuid/ref/payload/hash), sin duplicar consultas. Respuesta acotada e indexada.
"""

import logging

from src.services.actividad import scope, timeline

logger = logging.getLogger("actividad.busqueda")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return None


def buscar_global(texto, id_empresa=None, *, usuario=None, perfil=None, limite=50) -> list:
    emp = _emp(id_empresa)
    t = (texto or "").strip()
    if not t:
        return []
    if isinstance(usuario, dict) and perfil is None:
        perfil = usuario.get("perfil")
    like = f"%{t}%"
    frag, sparams = scope.filtro_sql(usuario, perfil, alias="e")
    q = ("SELECT e.id, e.uuid, e.fecha_creacion, e.tipo, e.origen, e.usuario, e.prioridad, "
         "e.ref_entidad, e.ref_id, e.hash, e.payload, e.id_tienda "
         "FROM eventos e WHERE e.id_empresa=%s AND ("
         "e.uuid LIKE %s OR e.ref_id LIKE %s OR e.usuario LIKE %s OR e.tipo LIKE %s "
         "OR e.origen LIKE %s OR e.hash LIKE %s OR e.payload LIKE %s OR e.ref_entidad LIKE %s)")
    p = [emp, like, like, like, like, like, like, like, like]
    if frag:
        q += " AND " + frag; p += sparams
    q += " ORDER BY e.id DESC LIMIT %s"; p.append(int(limite))
    out = []
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(q, p)
            for r in cur.fetchall():
                g = (lambda i, k: r[i] if not isinstance(r, dict) else r[k])
                out.append({
                    "id": g(0, "id"), "uuid": g(1, "uuid"), "fecha": g(2, "fecha_creacion"),
                    "tipo": g(3, "tipo"), "tipo_legible": timeline._legible(g(3, "tipo")),
                    "origen": g(4, "origen"), "usuario": g(5, "usuario"), "prioridad": g(6, "prioridad"),
                    "ref_entidad": g(7, "ref_entidad"), "ref_id": g(8, "ref_id"), "hash": g(9, "hash"),
                    "resumen": timeline._resumen(g(10, "payload")), "id_tienda": g(11, "id_tienda"),
                })
    except Exception as e:
        logger.error("buscar_global: %s", e)
    return out
