"""
Motor de badges (Fase 3, SUBFASE 3.2/3.3/3.4). COMPLETAMENTE DESACOPLADO.

Cada modulo pregunta "¿cuantos eventos pendientes tengo?" y el numero se CALCULA al vuelo
desde la cola de eventos (Fase 1) — NUNCA se almacena. Un evento cuenta para el badge de una
tarjeta del menu si: es de prioridad que hace badge (3.4), esta dentro del alcance del usuario
(3.5) y de su empresa (3.6), y es POSTERIOR a la ultima vez que el usuario atendio ese modulo
(watermark en actividad_vistas). Al abrir el modulo, `marcar_visto` pone el contador a cero.
"""

import logging

from src.services.actividad import mapeo, scope

logger = logging.getLogger("actividad.badges")

_VENTANA_DIAS = 60   # antiguedad maxima considerada para badges (actividad reciente)


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


def _uid(usuario):
    if isinstance(usuario, dict):
        v = usuario.get("nombre") or usuario.get("usuario") or usuario.get("id")
        return str(v) if v is not None else None
    return str(usuario) if usuario is not None else None


def _watermarks(emp, uid) -> dict:
    if not uid:
        return {}
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT modulo, ultima_vista FROM actividad_vistas WHERE id_empresa=%s "
                        "AND usuario=%s", (emp, uid))
            out = {}
            for r in cur.fetchall():
                k = r[0] if not isinstance(r, dict) else r["modulo"]
                v = r[1] if not isinstance(r, dict) else r["ultima_vista"]
                out[k] = v
            return out
    except Exception as e:
        logger.debug("watermarks: %s", e)
        return {}


def _consultar_eventos(emp, usuario, perfil):
    """Consulta cruda de eventos recientes con badge (tipo/origen/prioridad/fecha), ya filtrados por
    alcance/empresa. Reutilizada por `contar()` y `contar_subtabs()` para no duplicar el SQL."""
    frag, params = scope.filtro_sql(usuario, perfil, alias="e")
    prios = "','".join(sorted(mapeo.PRIORIDADES_BADGE))
    q = ("SELECT e.tipo, e.origen, e.prioridad, e.fecha_creacion FROM eventos e WHERE e.id_empresa=%s "
         "AND e.estado NOT IN ('ARCHIVADO','CANCELADO') "
         f"AND e.prioridad IN ('{prios}') "
         f"AND e.fecha_creacion >= (NOW() - INTERVAL {_VENTANA_DIAS} DAY)")
    p = [emp]
    if frag:
        q += " AND " + frag
        p += params
    q += " ORDER BY fecha_creacion DESC LIMIT 5000"
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(q, p)
            out = []
            for r in cur.fetchall():
                tipo = r[0] if not isinstance(r, dict) else r["tipo"]
                origen = r[1] if not isinstance(r, dict) else r["origen"]
                prio = r[2] if not isinstance(r, dict) else r["prioridad"]
                fecha = r[3] if not isinstance(r, dict) else r["fecha_creacion"]
                out.append((tipo, origen, prio, fecha))
            return out
    except Exception as e:
        logger.error("consultar eventos: %s", e)
        return []


def contar(usuario=None, perfil=None, id_empresa=None) -> dict:
    """Devuelve {v_id: nº de eventos pendientes} para las tarjetas del menu. Solo v_id con >0.

    Si un evento resuelve a una pestaña (`mapeo.subtab_de_evento`, por `tipo` o por `origen`), el
    watermark que se consulta es el de esa pestaña concreta (`f"{vid}.{subtab}"`), no solo el del
    modulo — así, atender UNA pestaña no descuenta los eventos pendientes de las demás pestañas del
    mismo modulo (retrocompatible: un evento sin pestaña resuelta sigue usando el watermark de
    modulo de siempre)."""
    emp = _emp(id_empresa)
    if isinstance(usuario, dict) and perfil is None:
        perfil = usuario.get("perfil")
    uid = _uid(usuario)
    wm = _watermarks(emp, uid)

    counts = {}
    for tipo, origen, prio, fecha in _consultar_eventos(emp, usuario, perfil):
        vid = mapeo.vid_de_tipo(tipo)
        if not vid or not mapeo.hace_badge(prio):
            continue
        subtab = mapeo.subtab_de_evento(tipo, origen)
        clave_wm = f"{vid}.{subtab}" if subtab else vid
        ultima = wm.get(clave_wm)
        if ultima and fecha and fecha <= ultima:
            continue   # ya atendido por el usuario
        counts[vid] = counts.get(vid, 0) + 1
    return {k: v for k, v in counts.items() if v > 0}


def contar_subtabs(v_id, usuario=None, perfil=None, id_empresa=None) -> dict:
    """Devuelve {subtab: nº de eventos pendientes} para las pestañas de UN modulo (`v_id`). Solo
    cuenta eventos que resuelvan a una pestaña (`mapeo.subtab_de_evento`, por `tipo` o `origen`)
    cuyo `vid_de_tipo` coincida con `v_id`."""
    emp = _emp(id_empresa)
    if isinstance(usuario, dict) and perfil is None:
        perfil = usuario.get("perfil")
    uid = _uid(usuario)
    wm = _watermarks(emp, uid)

    counts = {}
    for tipo, origen, prio, fecha in _consultar_eventos(emp, usuario, perfil):
        if mapeo.vid_de_tipo(tipo) != v_id or not mapeo.hace_badge(prio):
            continue
        subtab = mapeo.subtab_de_evento(tipo, origen)
        if not subtab:
            continue
        ultima = wm.get(f"{v_id}.{subtab}")
        if ultima and fecha and fecha <= ultima:
            continue
        counts[subtab] = counts.get(subtab, 0) + 1
    return {k: v for k, v in counts.items() if v > 0}


def total(usuario=None, perfil=None, id_empresa=None) -> int:
    return sum(contar(usuario, perfil, id_empresa).values())


def marcar_visto(modulo, usuario=None, id_empresa=None) -> bool:
    """Pone a cero el badge de un modulo (actualiza el watermark del usuario a ahora)."""
    emp = _emp(id_empresa)
    uid = _uid(usuario)
    if not uid or not modulo:
        return False
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO actividad_vistas (id_empresa, usuario, modulo, ultima_vista) "
                        "VALUES (%s,%s,%s,NOW()) ON DUPLICATE KEY UPDATE ultima_vista=NOW()",
                        (emp, uid, str(modulo)[:40]))
            c.commit()
        return True
    except Exception as e:
        logger.error("marcar_visto(%s): %s", modulo, e)
        return False
