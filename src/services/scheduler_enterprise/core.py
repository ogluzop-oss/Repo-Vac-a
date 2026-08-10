"""
Enterprise Scheduler (Fase III · B3) — planificador corporativo persistente.

Programación inmediata/diferida/diaria/…/cron con prioridad, reintentos, cancelación, logs y auditoría
(`scheduler_schedules` + `scheduler_ejecuciones`). Reutiliza el catálogo de jobs existente y ejecuta
callables registrados. Multiempresa. API-First (sin PyQt).
"""

import json
import logging

from src.db.conexion import _fila_a_dict, _filas_a_dicts, ensure_schema, obtener_conexion
from src.services.scheduler_enterprise import calendario as _cal

logger = logging.getLogger("scheduler_enterprise")

_JOBS: dict = {}   # clave → callable(params) -> None/valor


def registrar_job(clave, fn):
    """Registra un callable ejecutable por el scheduler. Punto de extensión."""
    _JOBS[clave] = fn
    return clave


def _resolver_job(clave):
    if clave in _JOBS:
        return _JOBS[clave]
    # Reutiliza el catálogo de jobs existente si expone callables.
    try:
        from src.services import scheduler_registry as _sr
        cat = {j.get("codigo"): j for j in _sr.catalogo()} if hasattr(_sr, "catalogo") else {}
        j = cat.get(clave)
        if j and callable(j.get("callable")):
            return j["callable"]
    except Exception:
        pass
    return None


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def crear_schedule(nombre, job, *, tipo="cron", expresion=None, params=None, prioridad="normal",
                   max_reintentos=0, id_empresa=None, usuario=None) -> int | None:
    id_empresa = _emp(id_empresa)
    prox = _cal.proxima(tipo, expresion)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scheduler_schedules (id_empresa, nombre, job, tipo, expresion, params, "
                "prioridad, estado, max_reintentos, proxima_ejecucion, usuario) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'activo',%s,%s,%s)",
                (id_empresa, nombre, job, tipo, expresion, json.dumps(params or {}), prioridad,
                 int(max_reintentos), prox, usuario))
            sid = cur.lastrowid
            conn.commit()
            return sid
    except Exception as e:
        logger.error("crear_schedule(%s): %s", nombre, e)
        return None


def listar_schedules(id_empresa=None, *, estado=None) -> list:
    id_empresa = _emp(id_empresa)
    q = "SELECT * FROM scheduler_schedules WHERE id_empresa=%s"
    p = [id_empresa]
    if estado:
        q += " AND estado=%s"; p.append(estado)
    q += " ORDER BY FIELD(prioridad,'alta','normal','baja'), proxima_ejecucion"
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("listar_schedules: %s", e)
        return []


def _set_estado(sid, estado) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE scheduler_schedules SET estado=%s, actualizado=NOW() WHERE id=%s",
                        (estado, sid))
            conn.commit()
            return True
    except Exception as e:
        logger.error("_set_estado(%s): %s", sid, e)
        return False


def cancelar(sid):  return _set_estado(sid, "cancelado")
def pausar(sid):    return _set_estado(sid, "pausado")
def reanudar(sid):  return _set_estado(sid, "activo")


def ejecutar_schedule(sid) -> dict:
    """Ejecuta un schedule ahora: corre el job con reintentos, registra la ejecución y reprograma la
    próxima (o finaliza si es puntual). Devuelve {ok, intentos, detalle}."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM scheduler_schedules WHERE id=%s", (sid,))
            sch = _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        return {"ok": False, "intentos": 0, "detalle": str(e)}
    if not sch or sch.get("estado") in ("cancelado", "pausado"):
        return {"ok": False, "intentos": 0, "detalle": "schedule no ejecutable"}
    fn = _resolver_job(sch.get("job"))
    params = _json(sch.get("params"))
    max_int = int(sch.get("max_reintentos") or 0)
    ok, detalle, intento = False, "", 0
    for intento in range(1, max_int + 2):
        try:
            if fn is None:
                raise RuntimeError(f"job '{sch.get('job')}' no registrado")
            fn(params)
            ok, detalle = True, "ok"
            break
        except Exception as e:
            detalle = str(e)
    # Registrar ejecución + reprogramar.
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO scheduler_ejecuciones (id_schedule, id_empresa, estado, intento, "
                        "detalle) VALUES (%s,%s,%s,%s,%s)",
                        (sid, sch.get("id_empresa"), "ok" if ok else "fallido", intento, detalle[:255]))
            prox = _cal.proxima(sch.get("tipo"), sch.get("expresion"))
            if prox and sch.get("tipo") not in ("inmediata", "diferida"):
                cur.execute("UPDATE scheduler_schedules SET ultima_ejecucion=NOW(), "
                            "proxima_ejecucion=%s WHERE id=%s", (prox, sid))
            else:
                cur.execute("UPDATE scheduler_schedules SET ultima_ejecucion=NOW(), "
                            "estado='finalizado', proxima_ejecucion=NULL WHERE id=%s", (sid,))
            conn.commit()
    except Exception as e:
        logger.debug("registrar ejecución %s: %s", sid, e)
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("scheduler", "EJECUCION", "scheduler_schedules",
                      f"id={sid} job={sch.get('job')} {'ok' if ok else 'fallido'}")
    except Exception:
        pass
    return {"ok": ok, "intentos": intento, "detalle": detalle}


def procesar_pendientes(id_empresa=None, *, limite=100) -> int:
    """Ejecuta los schedules vencidos (proxima_ejecucion <= ahora, estado activo). Devuelve el nº."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = ("SELECT id FROM scheduler_schedules WHERE estado='activo' AND proxima_ejecucion IS "
                 "NOT NULL AND proxima_ejecucion <= NOW()")
            p = []
            if id_empresa:
                q += " AND id_empresa=%s"; p.append(id_empresa)
            q += " ORDER BY FIELD(prioridad,'alta','normal','baja') LIMIT %s"; p.append(int(limite))
            cur.execute(q, p)
            ids = [r[0] if not isinstance(r, dict) else r.get("id") for r in cur.fetchall()]
    except Exception as e:
        logger.debug("procesar_pendientes: %s", e)
        return 0
    for sid in ids:
        ejecutar_schedule(sid)
    return len(ids)


def _json(v):
    if isinstance(v, dict):
        return v
    try:
        return json.loads(v) if v else {}
    except Exception:
        return {}
