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


def eliminar_evento(id_evento, id_empresa=None) -> bool:
    """Borra un evento (y sus participantes) por id. Devuelve True si se eliminó."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM calendario_participantes WHERE id_evento=%s AND id_empresa=%s",
                        (id_evento, id_empresa))
            cur.execute("DELETE FROM calendario_eventos WHERE id=%s AND id_empresa=%s",
                        (id_evento, id_empresa))
            afectadas = cur.rowcount
            conn.commit()
        if afectadas:
            _audit("EVENTO_CALENDARIO_ELIMINADO", f"id={id_evento}")
        return bool(afectadas)
    except Exception as e:
        logger.error("eliminar_evento(%s): %s", id_evento, e)
        return False


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


# ============================================================
# SINCRONIZACIÓN GOOGLE CALENDAR (solo LECTURA: Google → Smart Manager)
# ============================================================
def _fecha_google(valor: dict, *, es_fin=False) -> str | None:
    """Convierte el objeto start/end de un evento de Google Calendar a 'YYYY-MM-DD HH:MM:SS'
    (hora local, sin zona horaria — mismo formato que usa crear_evento). Soporta tanto eventos
    con hora (`dateTime`, con offset de zona) como eventos de día completo (`date`)."""
    if not valor:
        return None
    dt_str = valor.get("dateTime")
    if dt_str:
        try:
            dt = _dt.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    fecha = valor.get("date")
    if fecha:
        return f"{fecha} {'23:59:59' if es_fin else '00:00:00'}"
    return None


def _upsert_google_evento(id_empresa, ref_id, titulo, inicio, fin, descripcion) -> bool:
    """Upsert idempotente contra calendario_eventos, clave (id_empresa, ref_entidad=
    'google_calendar', ref_id=<id de evento de Google>): si ya existe, actualiza título/fechas;
    si no, la crea (creado_por=None para dejar claro que es importado, no creado por un humano
    aquí). Devuelve True si se procesó sin error (creado o actualizado)."""
    ref_id = str(ref_id)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM calendario_eventos WHERE id_empresa=%s AND ref_entidad=%s "
                        "AND ref_id=%s", (id_empresa, "google_calendar", ref_id))
            row = cur.fetchone()
            if row:
                eid = row[0] if not isinstance(row, dict) else list(row.values())[0]
                cur.execute("UPDATE calendario_eventos SET titulo=%s, inicio=%s, fin=%s, "
                            "descripcion=%s WHERE id=%s",
                            (titulo, inicio, fin, descripcion, eid))
            else:
                cur.execute(
                    "INSERT INTO calendario_eventos (id_empresa, titulo, tipo, inicio, fin, "
                    "descripcion, creado_por, ref_entidad, ref_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (id_empresa, titulo, "evento", inicio, fin, descripcion, None,
                     "google_calendar", ref_id))
            conn.commit()
        return True
    except Exception as e:
        logger.error("_upsert_google_evento(%s): %s", ref_id, e)
        return False


def sincronizar_google(id_correo: str, *, id_empresa=None) -> tuple[int, str]:
    """Trae los eventos de Google Calendar (API de SOLO LECTURA, scope calendar.readonly) del
    buzón Google conectado `id_correo` y los sincroniza en calendario_eventos (upsert idempotente
    por ref_entidad='google_calendar'/ref_id=<id del evento de Google>; reutiliza columnas ya
    existentes, sin migración). Devuelve (nº de eventos sincronizados, mensaje para el usuario).

    Honestidad: reutiliza `integraciones.calendario()` (ya auditado), que captura cualquier
    excepción de Google y la devuelve como {"ok": False, "detalle": str(excepcion)} — si esa
    excepción es un 403 por scope insuficiente (cuenta conectada con el scope antiguo, antes de
    ampliar GOOGLE_SCOPES), se traduce a un mensaje honesto pidiendo reconectar, nunca un
    traceback crudo."""
    id_empresa = _emp(id_empresa)
    try:
        from src.services import integraciones
        r = integraciones.calendario("listar", proveedor="google", cuenta=id_correo)
    except Exception as e:
        logger.error("sincronizar_google: %s", e)
        return 0, f"No se pudo sincronizar con Google Calendar: {e}"
    if not r.get("ok"):
        detalle = r.get("detalle") or ""
        try:
            from src.services.correo.servicio import _mensaje_si_scope_insuficiente
            msg_scope = _mensaje_si_scope_insuficiente(detalle)
        except Exception:
            msg_scope = None
        if msg_scope:
            logger.warning("sincronizar_google: scope insuficiente para %s", id_correo)
            return 0, msg_scope
        if r.get("estado") == "no_configurado":
            return 0, "La cuenta de Google no está conectada. Conéctala en Correo → Buzones."
        return 0, f"No se pudo sincronizar con Google Calendar: {detalle or r.get('estado')}"
    n = 0
    for ev in (r.get("eventos") or []):
        gid = ev.get("id")
        if not gid:
            continue
        inicio = _fecha_google(ev.get("start") or {})
        if inicio is None:
            continue
        fin = _fecha_google(ev.get("end") or {}, es_fin=True) or inicio
        titulo = ev.get("summary") or "(Sin título)"
        if _upsert_google_evento(id_empresa, gid, titulo, inicio, fin, ev.get("description")):
            n += 1
    _audit("CALENDARIO_SYNC_GOOGLE", f"{id_correo}: {n} evento(s)")
    return n, f"{n} evento(s) sincronizado(s) desde Google Calendar."


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("sistema", accion, "calendario_eventos", detalle)
    except Exception:
        pass
