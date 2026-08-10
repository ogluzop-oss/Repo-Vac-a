"""
Snapshots materializados del Gemelo Digital (Paquete Enterprise 8). Persiste una FOTO del estado
global por empresa en `dt_snapshots` para lectura instantanea del dashboard y como linea base de
consistencia. Es cache reconstruible; nunca fuente de verdad. Idempotente y best-effort.
"""

import hashlib
import json
import logging

from src.services.gemelo import fuentes as F

logger = logging.getLogger("gemelo.snapshot")


def guardar(id_empresa=None, *, ambito="global", estado=None, riesgo="BAJO") -> bool:
    emp = F.emp(id_empresa)
    try:
        cuerpo = json.dumps(estado or {}, default=str, ensure_ascii=False)
        h = hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO dt_snapshots (id_empresa, ambito, estado, riesgo, hash) "
                        "VALUES (%s,%s,%s,%s,%s)", (emp, ambito, cuerpo[:16_000_000], riesgo, h))
            c.commit()
        return True
    except Exception as e:
        logger.debug("guardar snapshot: %s", e)
        return False


def ultimo(id_empresa=None, *, ambito="global") -> dict | None:
    emp = F.emp(id_empresa)
    filas = F.filas("SELECT estado, riesgo, generado FROM dt_snapshots WHERE id_empresa=%s "
                    "AND ambito=%s ORDER BY generado DESC LIMIT 1", (emp, ambito))
    if not filas:
        return None
    f = filas[0]
    try:
        f["estado"] = json.loads(f.get("estado") or "{}")
    except Exception:
        f["estado"] = {}
    return f
