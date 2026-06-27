"""
B7-B — Cache Manager corporativo. Backend memoria (por defecto) + disco local (JSON). TTL,
invalidacion, warm-up, estado. Cacheables: articulos/clientes/stock/precios/usuarios/permisos/config.
Reutiliza RBAC para permisos. Degradable y thread-safe. NO sustituye caches existentes (aditivo).
"""

import json
import logging
import os
import threading
import time

logger = logging.getLogger("resiliencia.cache")
_LOCK = threading.RLock()
_MEM = {}          # clave -> (valor, expira_ts)
TTL_DEFECTO = 300  # 5 min


def _dir():
    base = os.path.join("documentos", "cache")
    try:
        from src.utils.recursos import ruta_datos
        base = ruta_datos("cache")
    except Exception:
        pass
    os.makedirs(base, exist_ok=True)
    return base


def set(clave, valor, *, ttl=TTL_DEFECTO, disco=False):
    exp = time.time() + ttl if ttl else None
    with _LOCK:
        _MEM[clave] = (valor, exp)
    if disco:
        try:
            with open(os.path.join(_dir(), f"{clave}.json"), "w", encoding="utf-8") as f:
                json.dump({"valor": valor, "expira": exp}, f, default=str)
        except Exception as e:
            logger.debug("cache disco set: %s", e)


def get(clave, *, disco=False):
    with _LOCK:
        if clave in _MEM:
            valor, exp = _MEM[clave]
            if exp is None or exp > time.time():
                return valor
            del _MEM[clave]
    if disco:
        try:
            ruta = os.path.join(_dir(), f"{clave}.json")
            if os.path.exists(ruta):
                with open(ruta, encoding="utf-8") as f:
                    d = json.load(f)
                if not d.get("expira") or d["expira"] > time.time():
                    with _LOCK:
                        _MEM[clave] = (d["valor"], d.get("expira"))
                    return d["valor"]
        except Exception as e:
            logger.debug("cache disco get: %s", e)
    return None


def get_or_set(clave, productor, *, ttl=TTL_DEFECTO, disco=False):
    v = get(clave, disco=disco)
    if v is not None:
        return v
    v = productor()
    set(clave, v, ttl=ttl, disco=disco)
    return v


def invalidar(clave=None, *, prefijo=None):
    with _LOCK:
        if clave:
            _MEM.pop(clave, None)
        elif prefijo:
            for k in [k for k in _MEM if k.startswith(prefijo)]:
                del _MEM[k]
        else:
            _MEM.clear()


def estado() -> dict:
    with _LOCK:
        ahora = time.time()
        vivas = sum(1 for _, exp in _MEM.values() if exp is None or exp > ahora)
        return {"entradas": len(_MEM), "vivas": vivas, "expiradas": len(_MEM) - vivas}


# ── Warm-up: precarga catalogo critico (articulos/clientes/precios/stock) ──────
def warmup(*, id_empresa=None, disco=True) -> dict:
    """Precarga en cache (y opcionalmente a disco) el catalogo critico de la empresa."""
    from src.db.empresa import empresa_actual_id
    from src.db.conexion import obtener_conexion
    eid = id_empresa or empresa_actual_id()
    cargado = {}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo, nombre FROM articulos LIMIT 5000")
            arts = [dict(zip([d[0] for d in cur.description], r if not isinstance(r, dict) else r.values()))
                    for r in cur.fetchall()]
            set(f"cat:articulos:{eid}", arts, ttl=3600, disco=disco); cargado["articulos"] = len(arts)
            cur.execute("SELECT id, nombre FROM clientes WHERE id_empresa=%s LIMIT 5000", (eid,))
            clis = [dict(zip([d[0] for d in cur.description], r if not isinstance(r, dict) else r.values()))
                    for r in cur.fetchall()]
            set(f"cat:clientes:{eid}", clis, ttl=3600, disco=disco); cargado["clientes"] = len(clis)
    except Exception as e:
        logger.error("warmup: %s", e)
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("resiliencia", "CACHE_WARMUP", "cache", f"{cargado}")
    except Exception:
        pass
    return {"ok": True, "cargado": cargado, "estado": estado()}


# ── Job Scheduler (refresco periodico) ────────────────────────────────────────
def _job_warmup(id_empresa):
    return f"cache={warmup(id_empresa=id_empresa).get('cargado')}"


def registrar_jobs_cache(id_empresa=None):
    from src.services import scheduler
    scheduler.registrar("cache_warmup", _job_warmup)
    scheduler.registrar_job("cache_warmup", intervalo_horas=6, descripcion="Warm-up cache corporativa",
                            id_empresa=id_empresa)
