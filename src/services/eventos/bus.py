"""
Event Bus corporativo (Fase 1) — API interna UNICA de eventos.

Todos los modulos deben comunicarse a traves de esta API (nunca llamandose entre si):
    publicar / suscribir / consumir / buscar / obtener / cancelar / reintentar / historial

Caracter OBSERVACIONAL en la Fase 1: los eventos se publican y persisten (tabla `eventos`
+ destinatarios/estado/historial/log), pero ningun modulo los consume todavia. `publicar`
es BULLETPROOF: nunca lanza excepcion, de modo que integrarla junto a un flujo certificado
(TPV, facturacion, kardex...) jamas puede romperlo.

Desacoplado: ningun modulo conoce la implementacion interna de otro; solo publica eventos.
Multiempresa/multitienda (empresa/tienda/almacen se resuelven del contexto activo).
"""

import logging
import time

from src.services.eventos import estados as E
from src.services.eventos import tipos as T
from src.services.eventos.modelo import Evento

logger = logging.getLogger("eventos.bus")

# Suscriptores en proceso: {tipo|"*": [handler, ...]}. En la Fase 1 no hay consumidores;
# queda listo para que fases posteriores registren manejadores sin tocar los publicadores.
_SUSCRIPTORES: dict[str, list] = {}


# ── Contexto (multiempresa/tienda/usuario) ────────────────────────────────────
def _empresa(id_empresa=None):
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


def _tienda(id_tienda=None) -> int:
    if id_tienda is not None:
        try:
            return int(id_tienda)
        except (TypeError, ValueError):
            return 0
    try:
        from src.db.conexion import tienda_actual_id_int
        return int(tienda_actual_id_int() or 0)
    except Exception:
        return 0


def _usuario(usuario=None):
    if usuario:
        return str(usuario)[:80]
    try:
        from src.db.usuario import sesion_global
        u = getattr(sesion_global, "usuario_actual", None) or {}
        if isinstance(u, dict):
            v = u.get("nombre") or u.get("usuario") or (str(u.get("id")) if u.get("id") else None)
            return str(v)[:80] if v else None
    except Exception:
        pass
    return None


# ── Helpers internos (dentro de una transaccion abierta) ──────────────────────
def _hist(cur, id_empresa, id_evento, accion, actor=None, detalle=None, duracion_ms=None):
    cur.execute("INSERT INTO eventos_historial (id_empresa, id_evento, accion, actor, detalle, "
                "duracion_ms) VALUES (%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_evento, accion, actor, (detalle or "")[:255], duracion_ms))


def _estado_log(cur, id_empresa, id_evento, anterior, nuevo, usuario=None, detalle=None):
    cur.execute("INSERT INTO eventos_estado (id_empresa, id_evento, estado_anterior, estado_nuevo, "
                "usuario, detalle) VALUES (%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_evento, anterior, nuevo, usuario, (detalle or "")[:255]))


def _log(id_empresa, id_evento, nivel, origen, mensaje):
    """Log tecnico del bus en su propia conexion (best-effort, nunca rompe)."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO eventos_log (id_empresa, id_evento, nivel, origen, mensaje) "
                        "VALUES (%s,%s,%s,%s,%s)", (id_empresa, id_evento, nivel, origen,
                                                    (mensaje or "")[:255]))
            conn.commit()
    except Exception:
        pass


def _dicts(cur, rows):
    try:
        from src.db.conexion import _filas_a_dicts
        return _filas_a_dicts(cur, rows)
    except Exception:
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in rows]


# ── Suscripcion (in-process; observacional en Fase 1) ─────────────────────────
def suscribir(tipo, handler) -> None:
    """Registra un manejador para un tipo de evento (o '*' para todos). No usado en Fase 1."""
    _SUSCRIPTORES.setdefault(str(tipo), []).append(handler)


def desuscribir(tipo, handler) -> None:
    lst = _SUSCRIPTORES.get(str(tipo))
    if lst and handler in lst:
        lst.remove(handler)


def _notificar_suscriptores(ev: Evento):
    for clave in (ev.tipo, "*"):
        for h in list(_SUSCRIPTORES.get(clave, [])):
            try:
                h(ev.to_dict())
            except Exception as e:
                logger.debug("suscriptor %s fallo en %s: %s", clave, ev.tipo, e)


# ── API PUBLICA ───────────────────────────────────────────────────────────────
def publicar(tipo, *, id_empresa=None, id_tienda=None, id_almacen=None, usuario=None,
             origen=None, destino=None, prioridad=None, ref_entidad=None, ref_id=None,
             payload=None, observaciones=None, destinatarios=None) -> dict | None:
    """Publica un evento (lo persiste como PENDIENTE) y avisa a los suscriptores en proceso.

    BULLETPROOF: nunca lanza excepcion. Devuelve el dict del evento o None si algo falla.
    Pensado para llamarse junto a un flujo certificado sin poder romperlo.
    """
    t0 = time.perf_counter()
    try:
        emp = _empresa(id_empresa)
        ev = Evento(
            tipo=str(tipo), id_empresa=emp, id_tienda=_tienda(id_tienda), id_almacen=id_almacen,
            usuario=_usuario(usuario), origen=origen, destino=destino,
            prioridad=prioridad or T.prioridad_defecto(tipo), estado=E.PENDIENTE,
            ref_entidad=ref_entidad, ref_id=(str(ref_id) if ref_id is not None else None),
            payload=payload, observaciones=observaciones)
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO eventos (uuid, tipo, prioridad, estado, id_empresa, id_tienda, "
                "id_almacen, usuario, origen, destino, version, schema_version, created_with, "
                "ref_entidad, ref_id, payload, hash, observaciones) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (ev.uuid, ev.tipo, ev.prioridad, ev.estado, ev.id_empresa, ev.id_tienda,
                 ev.id_almacen, ev.usuario, ev.origen, ev.destino, ev.version, ev.schema_version,
                 ev.created_with, ev.ref_entidad, ev.ref_id, ev.payload_json(), ev.hash,
                 ev.observaciones))
            ev.id = cur.lastrowid
            for d in (destinatarios or []):
                if isinstance(d, (list, tuple)):
                    destino_v, tipo_d = d[0], (d[1] if len(d) > 1 else "modulo")
                else:
                    destino_v, tipo_d = d, "modulo"
                cur.execute("INSERT INTO eventos_destinatarios (id_empresa, id_evento, destino, "
                            "tipo_destino) VALUES (%s,%s,%s,%s)",
                            (emp, ev.id, str(destino_v)[:80], str(tipo_d)[:12]))
            _hist(cur, emp, ev.id, "PUBLICADO", ev.usuario,
                  f"{ev.tipo} prio={ev.prioridad} origen={origen or '-'}",
                  int((time.perf_counter() - t0) * 1000))
            _estado_log(cur, emp, ev.id, None, E.PENDIENTE, ev.usuario, "publicado")
            conn.commit()
        _notificar_suscriptores(ev)
        return ev.to_dict()
    except Exception as e:
        logger.warning("publicar(%s): %s", tipo, e)
        _log(None, None, "ERROR", "bus.publicar", f"{tipo}: {e}")
        return None


def obtener(id_evento, *, id_empresa=None) -> dict | None:
    try:
        emp = _empresa(id_empresa)
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM eventos WHERE id=%s AND id_empresa=%s", (id_evento, emp))
            rows = cur.fetchall()
            d = _dicts(cur, rows)
            return d[0] if d else None
    except Exception as e:
        logger.error("obtener(%s): %s", id_evento, e)
        return None


def buscar(*, tipo=None, estado=None, prioridad=None, id_empresa=None, id_tienda=None,
           ref_entidad=None, ref_id=None, desde=None, hasta=None, limite=200) -> list:
    """Busca eventos por filtros. Devuelve lista de dicts (mas recientes primero)."""
    try:
        emp = _empresa(id_empresa)
        q = "SELECT * FROM eventos WHERE id_empresa=%s"
        p = [emp]
        if tipo:
            q += " AND tipo=%s"; p.append(tipo)
        if estado:
            q += " AND estado=%s"; p.append(estado)
        if prioridad:
            q += " AND prioridad=%s"; p.append(prioridad)
        if id_tienda is not None:
            q += " AND id_tienda=%s"; p.append(int(id_tienda))
        if ref_entidad:
            q += " AND ref_entidad=%s"; p.append(ref_entidad)
        if ref_id is not None:
            q += " AND ref_id=%s"; p.append(str(ref_id))
        if desde:
            q += " AND fecha_creacion>=%s"; p.append(desde)
        if hasta:
            q += " AND fecha_creacion<=%s"; p.append(hasta)
        q += " ORDER BY fecha_creacion DESC, id DESC LIMIT %s"; p.append(int(limite))
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return _dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("buscar: %s", e)
        return []


def _transicionar(id_evento, nuevo_estado, *, accion, id_empresa=None, usuario=None,
                  detalle=None, inc_reintentos=False) -> bool:
    try:
        emp = _empresa(id_empresa)
        usr = _usuario(usuario)
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT estado FROM eventos WHERE id=%s AND id_empresa=%s FOR UPDATE",
                        (id_evento, emp))
            r = cur.fetchone()
            if not r:
                return False
            actual = r[0] if not isinstance(r, dict) else r["estado"]
            if not E.puede_transicionar(actual, nuevo_estado):
                logger.debug("transicion invalida %s->%s (evento %s)", actual, nuevo_estado, id_evento)
                return False
            extra = ", reintentos=reintentos+1" if inc_reintentos else ""
            cur.execute(f"UPDATE eventos SET estado=%s, updated_with=%s{extra} "
                        "WHERE id=%s AND id_empresa=%s",
                        (nuevo_estado, "smart-eventos-1.0", id_evento, emp))
            _estado_log(cur, emp, id_evento, actual, nuevo_estado, usr, detalle)
            _hist(cur, emp, id_evento, accion, usr, detalle)
            conn.commit()
            return True
    except Exception as e:
        logger.error("transicionar(%s->%s): %s", id_evento, nuevo_estado, e)
        return False


def consumir(id_evento, *, destino=None, id_empresa=None, usuario=None, detalle=None) -> bool:
    """Marca un evento como PROCESADO (consumido). Si se indica `destino`, marca ademas ese
    destinatario. Registra el consumo en el historial. (Sin consumidores reales en Fase 1.)"""
    emp = _empresa(id_empresa)
    if destino:
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("UPDATE eventos_destinatarios SET estado='PROCESADO' "
                            "WHERE id_empresa=%s AND id_evento=%s AND destino=%s",
                            (emp, id_evento, str(destino)[:80]))
                conn.commit()
        except Exception as e:
            logger.debug("consumir destinatario: %s", e)
    ok = _transicionar(id_evento, E.PROCESANDOSE, accion="CONSUMO_INICIO",
                       id_empresa=emp, usuario=usuario, detalle=detalle)
    if ok:
        _transicionar(id_evento, E.PROCESADO, accion="CONSUMIDO",
                      id_empresa=emp, usuario=usuario, detalle=detalle or (destino or ""))
    return ok


def cancelar(id_evento, *, id_empresa=None, usuario=None, motivo=None) -> bool:
    return _transicionar(id_evento, E.CANCELADO, accion="CANCELADO",
                         id_empresa=id_empresa, usuario=usuario, detalle=motivo)


def reintentar(id_evento, *, id_empresa=None, usuario=None) -> bool:
    return _transicionar(id_evento, E.REINTENTANDO, accion="REINTENTO",
                         id_empresa=id_empresa, usuario=usuario, detalle="reintento manual",
                         inc_reintentos=True)


def archivar(id_evento, *, id_empresa=None, usuario=None) -> bool:
    return _transicionar(id_evento, E.ARCHIVADO, accion="ARCHIVADO",
                         id_empresa=id_empresa, usuario=usuario, detalle="archivado")


def historial(id_evento, *, id_empresa=None) -> list:
    """Historial completo del ciclo de vida del evento (quien creo/consumio/fallo, tiempos)."""
    try:
        emp = _empresa(id_empresa)
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM eventos_historial WHERE id_empresa=%s AND id_evento=%s "
                        "ORDER BY id", (emp, id_evento))
            return _dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("historial(%s): %s", id_evento, e)
        return []


def metricas(*, id_empresa=None) -> dict:
    """Recuento de eventos por estado (para diagnostico/observabilidad)."""
    try:
        emp = _empresa(id_empresa)
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT estado, COUNT(*) FROM eventos WHERE id_empresa=%s GROUP BY estado", (emp,))
            return {(r[0] if not isinstance(r, dict) else list(r.values())[0]):
                    (r[1] if not isinstance(r, dict) else list(r.values())[1])
                    for r in cur.fetchall()}
    except Exception as e:
        logger.error("metricas: %s", e)
        return {}
