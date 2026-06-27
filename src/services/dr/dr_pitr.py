"""
Point In Time Recovery (DR-A).

Construye sobre el backup existente (db/backup.py) un registro de SNAPSHOTS con marca temporal,
hash y backend de almacenamiento, permitiendo restaurar al snapshot mas cercano a un timestamp.
PITR fino (binlog/transaccion) requiere binlog de MariaDB: se documenta y se aproxima al snapshot
inmediatamente anterior. RPO/RTO calculados desde la evidencia. Auditado.
"""

import datetime as _dt
import logging
import os

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("dr.pitr")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_snapshot(*, motivo="snapshot", offsite=True, id_empresa=None) -> dict:
    """Crea un backup completo, lo registra como snapshot y opcionalmente lo sube off-site."""
    from src.db import backup
    meta = backup.crear_backup(motivo=motivo)
    if meta.get("resultado") != "ok":
        _audit("DR_PITR_FAILED", f"motivo={motivo}")
        return {"ok": False, "error": meta.get("resultado")}
    ruta = meta.get("ruta")
    backend_cod, ref = "local", ruta
    if offsite:
        try:
            from src.services.dr import dr_storage
            sub = dr_storage.backend().subir(ruta)
            if sub.get("ok"):
                backend_cod, ref = sub.get("backend"), sub.get("ref")
        except Exception as e:
            logger.debug("offsite: %s", e)
    tam = os.path.getsize(ruta) if ruta and os.path.exists(ruta) else 0
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO dr_snapshots (id_empresa, tipo, ruta, backend, ref_remota, "
                        "hash, tamano_bytes, estado) VALUES (%s,'full',%s,%s,%s,%s,%s,'ok')",
                        (id_empresa, ruta, backend_cod, ref, meta.get("hash"), tam))
            sid = cur.lastrowid
            conn.commit()
    except Exception as e:
        logger.error("crear_snapshot/registro: %s", e)
        return {"ok": False, "error": str(e)}
    _audit("DR_PITR_CREATED", f"snapshot={sid} backend={backend_cod}")
    return {"ok": True, "snapshot": sid, "ruta": ruta, "backend": backend_cod}


def listar_snapshots(id_empresa=None, limite=200) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM dr_snapshots ORDER BY creado_en DESC LIMIT %s", (int(limite),))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_snapshots: %s", e)
        return []


def _snapshot_para_timestamp(ts):
    """Snapshot 'ok' mas reciente cuya fecha <= ts (el punto recuperable mas cercano por debajo)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM dr_snapshots WHERE estado='ok' AND creado_en<=%s "
                        "ORDER BY creado_en DESC LIMIT 1", (ts,))
            r = cur.fetchone()
            return _fila(cur, r) if r else None
    except Exception as e:
        logger.error("_snapshot_para_timestamp: %s", e)
        return None


def restaurar_a_snapshot(id_snapshot, *, db=None) -> dict:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT ruta FROM dr_snapshots WHERE id=%s", (id_snapshot,))
            r = cur.fetchone()
        if not r:
            return {"ok": False, "error": "snapshot inexistente"}
        ruta = r[0] if not isinstance(r, dict) else list(r.values())[0]
        from src.db import backup
        res = backup.restaurar_backup(ruta, db=db)
        ok = bool(res and res.get("ok", res.get("resultado") == "ok"))
        _audit("DR_PITR_RESTORED" if ok else "DR_PITR_FAILED", f"snapshot={id_snapshot}")
        return {"ok": ok, "detalle": res}
    except Exception as e:
        logger.error("restaurar_a_snapshot: %s", e)
        _audit("DR_PITR_FAILED", f"snapshot={id_snapshot}: {e}")
        return {"ok": False, "error": str(e)}


def restaurar_a_timestamp(ts, *, db=None) -> dict:
    """Restaura al snapshot recuperable mas cercano por debajo del timestamp dado."""
    if isinstance(ts, str):
        ts = (_dt.datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S") if " " in ts
              else _dt.datetime.strptime(ts[:10], "%Y-%m-%d"))
    snap = _snapshot_para_timestamp(ts)
    if not snap:
        return {"ok": False, "error": "no hay snapshot anterior a ese instante"}
    return restaurar_a_snapshot(snap["id"], db=db)


def calcular_rpo() -> dict:
    """RPO = antiguedad del ultimo snapshot (perdida maxima potencial de datos)."""
    snaps = listar_snapshots(limite=1)
    if not snaps:
        return {"rpo_horas": None, "estado": "sin_snapshots"}
    ult = snaps[0]["creado_en"]
    if isinstance(ult, str):
        ult = _dt.datetime.strptime(ult[:19], "%Y-%m-%d %H:%M:%S")
    horas = round((_dt.datetime.now() - ult).total_seconds() / 3600, 2)
    return {"rpo_horas": horas, "ultimo_snapshot": str(ult)}


def calcular_rto() -> dict:
    """RTO estimado = tamano del ultimo snapshot / velocidad de restore asumida (heuristico)."""
    snaps = listar_snapshots(limite=1)
    if not snaps:
        return {"rto_min": None}
    tam_mb = (snaps[0].get("tamano_bytes") or 0) / 1_000_000
    # Heuristica: ~50 MB/min de restauracion + overhead fijo de 2 min.
    return {"rto_min": round(2 + tam_mb / 50, 1), "tam_mb": round(tam_mb, 1)}


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("dr", accion, "dr_snapshots", detalle)
    except Exception:
        pass
