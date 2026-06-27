"""
CAL-A — Planes de inspeccion + inspecciones (recepcion/produccion/expedicion).
Multiempresa, auditado. Si una inspeccion resulta 'rechazada', puede abrir una NC automaticamente.
"""

import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("calidad.inspecciones")
FASES = ("recepcion", "produccion", "expedicion")
RESULTADOS = ("pendiente", "aceptada", "rechazada", "condicional")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_plan(codigo, nombre, *, fase="recepcion", articulo=None, criterios=None, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO planes_inspeccion (id_empresa, codigo, nombre, fase, articulo, criterios) "
                        "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), "
                        "fase=VALUES(fase), articulo=VALUES(articulo), criterios=VALUES(criterios)",
                        (eid, codigo, nombre, fase if fase in FASES else "recepcion", articulo, criterios))
            cur.execute("SELECT id FROM planes_inspeccion WHERE id_empresa=%s AND codigo=%s", (eid, codigo))
            pid = cur.fetchone()
            conn.commit()
        log_auditoria("calidad", "CAL_PLAN_CREATED", "planes_inspeccion", f"plan={codigo}")
        return pid[0] if not isinstance(pid, dict) else list(pid.values())[0]
    except Exception as e:
        logger.error("crear_plan: %s", e)
        return None


def registrar_inspeccion(*, fase="recepcion", articulo=None, id_plan=None, id_lote=None, id_of=None,
                         id_proveedor=None, cantidad_inspeccionada=0, cantidad_rechazada=0,
                         resultado="pendiente", inspector=None, observaciones=None,
                         abrir_nc_si_rechazo=True, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    if resultado not in RESULTADOS:
        raise ValueError(f"resultado invalido: {resultado}")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO inspecciones (id_empresa, id_plan, fase, articulo, id_lote, id_of, "
                        "id_proveedor, cantidad_inspeccionada, cantidad_rechazada, resultado, inspector, "
                        "observaciones) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (eid, id_plan, fase, articulo, id_lote, id_of, id_proveedor,
                         cantidad_inspeccionada, cantidad_rechazada, resultado, inspector, observaciones))
            iid = cur.lastrowid
            conn.commit()
        log_auditoria("calidad", "CAL_INSPECCION", "inspecciones", f"insp={iid} {fase} {resultado}")
        nc = None
        if resultado == "rechazada" and abrir_nc_si_rechazo:
            from src.services.calidad import no_conformidades
            nc = no_conformidades.abrir(
                f"Inspeccion {fase} rechazada (insp {iid})", origen=fase, articulo=articulo,
                id_lote=id_lote, id_proveedor=id_proveedor, id_of=id_of, id_inspeccion=iid,
                severidad="alta", id_empresa=eid)
        return {"ok": True, "inspeccion": iid, "no_conformidad": nc}
    except ValueError:
        raise
    except Exception as e:
        logger.error("registrar_inspeccion: %s", e)
        return {"ok": False, "error": str(e)}


def listar(*, fase=None, resultado=None, id_empresa=None, limite=500) -> list:
    eid = _emp(id_empresa)
    q = "SELECT * FROM inspecciones WHERE id_empresa=%s"
    p = [eid]
    if fase:
        q += " AND fase=%s"; p.append(fase)
    if resultado:
        q += " AND resultado=%s"; p.append(resultado)
    q += " ORDER BY fecha DESC LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar: %s", e)
        return []
