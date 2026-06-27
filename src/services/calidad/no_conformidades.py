"""
CAL-B — No conformidades (NC). Ciclo abierta/en_analisis/accionada/cerrada/rechazada.
Asociable a lote/articulo/proveedor/cliente/OF/inspeccion. Workflow opcional. Multiempresa, auditado.
"""

import datetime as _dt
import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("calidad.nc")
ESTADOS = ("abierta", "en_analisis", "accionada", "cerrada", "rechazada")
_TRANS = {
    "abierta": {"en_analisis", "rechazada"},
    "en_analisis": {"accionada", "rechazada", "cerrada"},
    "accionada": {"cerrada", "en_analisis"},
}


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def abrir(descripcion, *, origen="interna", severidad="media", articulo=None, id_lote=None,
          id_proveedor=None, id_cliente=None, id_of=None, id_inspeccion=None, responsable=None,
          id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO no_conformidades (id_empresa, origen, descripcion, severidad, articulo, "
                        "id_lote, id_proveedor, id_cliente, id_of, id_inspeccion, responsable) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (eid, origen, descripcion[:255], severidad, articulo, id_lote, id_proveedor,
                         id_cliente, id_of, id_inspeccion, responsable))
            nid = cur.lastrowid
            cur.execute("UPDATE no_conformidades SET codigo=%s WHERE id=%s", (f"NC{nid:06d}", nid))
            conn.commit()
        log_auditoria("calidad", "NC_ABIERTA", "no_conformidades", f"nc={nid} {origen} sev={severidad}")
        _notificar(nid, descripcion, severidad, eid)
        return nid
    except Exception as e:
        logger.error("abrir NC: %s", e)
        return None


def cambiar_estado(id_nc, nuevo, *, id_empresa=None) -> dict:
    if nuevo not in ESTADOS:
        raise ValueError(f"estado invalido: {nuevo}")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT estado FROM no_conformidades WHERE id=%s", (id_nc,))
            r = cur.fetchone()
            if not r:
                return {"ok": False, "error": "NC inexistente"}
            actual = r[0] if not isinstance(r, dict) else list(r.values())[0]
            if nuevo != actual and nuevo not in _TRANS.get(actual, set()):
                return {"ok": False, "error": f"transicion {actual}->{nuevo} no permitida"}
            cierre = ", fecha_cierre=%s" if nuevo in ("cerrada", "rechazada") else ""
            params = [nuevo]
            if cierre:
                params.append(_dt.datetime.now())
            params.append(id_nc)
            cur.execute(f"UPDATE no_conformidades SET estado=%s{cierre} WHERE id=%s", params)
            conn.commit()
        log_auditoria("calidad", f"NC_{nuevo.upper()}", "no_conformidades", f"nc={id_nc}")
        return {"ok": True, "estado": nuevo}
    except ValueError:
        raise
    except Exception as e:
        logger.error("cambiar_estado NC: %s", e)
        return {"ok": False, "error": str(e)}


def obtener(id_nc) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM no_conformidades WHERE id=%s", (id_nc,))
            r = cur.fetchone()
            return _fila(cur, r) if r else None
    except Exception as e:
        logger.error("obtener NC: %s", e)
        return None


def listar(*, estado=None, origen=None, id_empresa=None, limite=500) -> list:
    eid = _emp(id_empresa)
    q = "SELECT * FROM no_conformidades WHERE id_empresa=%s"
    p = [eid]
    if estado:
        q += " AND estado=%s"; p.append(estado)
    if origen:
        q += " AND origen=%s"; p.append(origen)
    q += " ORDER BY fecha_apertura DESC LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar NC: %s", e)
        return []


def _notificar(nid, descripcion, severidad, eid):
    try:
        from src.services import notificaciones
        notificaciones.emitir("calidad", f"Nueva NC {nid}", descripcion, modulo="calidad",
                              prioridad="critica" if severidad == "alta" else "alta",
                              roles=["GERENTE", "ADMINISTRADOR"], id_empresa=eid)
    except Exception:
        pass
