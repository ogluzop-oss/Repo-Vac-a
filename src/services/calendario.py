"""
Calendario y agenda (FASE COM-8).

Eventos (reunión/cita/recordatorio/auditoría/revisión) con participantes. Consultas por rango
(día/semana/mes). Multiempresa y auditado. Puede enlazar a una entidad (ref_entidad/ref_id).
"""

import datetime as _dt
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("calendario")
TIPOS = ("evento", "reunion", "cita", "recordatorio", "auditoria", "revision")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_evento(titulo, inicio, *, fin=None, tipo="evento", descripcion=None, creado_por=None,
                 participantes=None, ref_entidad=None, ref_id=None, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    if tipo not in TIPOS:
        tipo = "evento"
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO calendario_eventos (id_empresa, titulo, tipo, inicio, fin, "
                        "descripcion, creado_por, ref_entidad, ref_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, titulo, tipo, inicio, fin, descripcion, creado_por, ref_entidad,
                         (str(ref_id) if ref_id is not None else None)))
            eid = cur.lastrowid
            for u in (participantes or []):
                cur.execute("INSERT IGNORE INTO calendario_participantes (id_empresa, id_evento, usuario) "
                            "VALUES (%s,%s,%s)", (id_empresa, eid, u))
            conn.commit()
        _audit("EVENTO_CALENDARIO", f"id={eid} {tipo}")
        # Notifica a los participantes.
        if participantes:
            try:
                from src.services import notificaciones
                notificaciones.emitir("calendario", f"Nuevo evento: {titulo}", str(inicio),
                                      modulo="calendario", usuarios=participantes, id_empresa=id_empresa)
            except Exception:
                pass
        return eid
    except Exception as e:
        logger.error("crear_evento: %s", e)
        return None


def eventos_rango(desde, hasta, *, usuario=None, id_empresa=None) -> list:
    """Eventos cuyo inicio cae en [desde, hasta]. Si `usuario`, solo en los que participa o creó."""
    id_empresa = _emp(id_empresa)
    q = "SELECT DISTINCT e.* FROM calendario_eventos e"
    cond = ["e.id_empresa=%s", "e.inicio>=%s", "e.inicio<=%s"]
    p = [id_empresa, str(desde), str(hasta)]
    if usuario is not None:
        q += " LEFT JOIN calendario_participantes pa ON pa.id_evento=e.id"
        cond.append("(e.creado_por=%s OR pa.usuario=%s)")
        p += [usuario, usuario]
    q += " WHERE " + " AND ".join(cond) + " ORDER BY e.inicio"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("eventos_rango: %s", e)
        return []


def eventos_dia(fecha, *, usuario=None, id_empresa=None) -> list:
    return eventos_rango(f"{fecha} 00:00:00", f"{fecha} 23:59:59", usuario=usuario, id_empresa=id_empresa)


def eventos_mes(anio, mes, *, usuario=None, id_empresa=None) -> list:
    import calendar as _cal
    ult = _cal.monthrange(int(anio), int(mes))[1]
    return eventos_rango(f"{anio}-{int(mes):02d}-01 00:00:00",
                         f"{anio}-{int(mes):02d}-{ult:02d} 23:59:59", usuario=usuario, id_empresa=id_empresa)


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("sistema", accion, "calendario_eventos", detalle)
    except Exception:
        pass
